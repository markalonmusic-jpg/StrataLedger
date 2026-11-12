import hashlib
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from config import BACKUP_DIR, MIGRATIONS_DIR as _CONFIG_MIGRATIONS_DIR


MAX_DIMENSION_DEPTH = 3
MIGRATIONS_DIR = _CONFIG_MIGRATIONS_DIR
MIGRATIONS = [(1, "001_company.sql")]
MASTER_MIGRATIONS = [(1, "001_master.sql")]


class SchemaUpgradeBlockedError(Exception):
    def __init__(self, db_path, reason):
        self.db_path = os.fspath(db_path)
        self.reason = str(reason)
        super().__init__(f"Schema upgrade blocked for {self.db_path}: {self.reason}")


def get_connection(db_path):
    """Open a SQLite connection with foreign keys and named-column rows enabled."""
    conn = sqlite3.connect(os.fspath(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_readonly_connection(db_path):
    """Public read-only connection (writes raise OperationalError). Caller closes it."""
    return _readonly_connection(db_path)


def _readonly_connection(db_path):
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table_name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _current_version(db_path):
    if not os.path.isfile(db_path):
        return 0
    conn = _readonly_connection(db_path)
    try:
        if not _table_exists(conn, "schema_version"):
            return 0
        row = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
        return row["version"] or 0
    finally:
        conn.close()


# --- Pre-release baseline guard -------------------------------------------------
# Until the first release the schema is ONE baseline file per database kind, and
# development databases are rebuilt from it (CLAUDE.md section 5). At build the
# runner stores a SHA-256 of the baseline text in the database; opening a file
# whose stored hash differs, is missing, or whose version is above the
# baseline's is blocked. This guard is replaced by versioned migrations at the
# first release.
_REBUILD_HINT = "Rebuild it with scripts/create_fresh_databases.py (nothing was changed)."


def _baseline_hash(migrations):
    """SHA-256 of the baseline SQL text; line endings do not matter."""
    path = os.path.join(MIGRATIONS_DIR, migrations[0][1])
    with open(path, "r", encoding="utf-8", newline=None) as handle:
        text = handle.read().replace(chr(13) + chr(10), chr(10))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stored_baseline_hash(conn):
    if not _table_exists(conn, "schema_baseline"):
        return None
    row = conn.execute("SELECT sha256 FROM schema_baseline WHERE id = 1").fetchone()
    return row["sha256"] if row else None


def _check_baseline(db_path, migrations):
    """Block files that were not built from the current baseline. Never writes."""
    if not os.path.isfile(db_path):
        return
    conn = _readonly_connection(db_path)
    try:
        has_tables = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
        ).fetchone() is not None
        if not _table_exists(conn, "schema_version"):
            if has_tables:
                raise SchemaUpgradeBlockedError(
                    db_path, "This database was not built from the current baseline. " + _REBUILD_HINT)
            return
        version = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()["version"] or 0
        if version == 0:
            return
        if version > migrations[-1][0]:
            raise SchemaUpgradeBlockedError(
                db_path,
                f"This database is at schema version {version}, above this application's version "
                f"{migrations[-1][0]}. " + _REBUILD_HINT,
            )
        if _stored_baseline_hash(conn) != _baseline_hash(migrations):
            raise SchemaUpgradeBlockedError(
                db_path, "This database was built from a different schema baseline. " + _REBUILD_HINT)
    finally:
        conn.close()


def _record_baseline_hash(conn, migrations):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_baseline (id INTEGER PRIMARY KEY CHECK (id = 1), sha256 TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_baseline (id, sha256) VALUES (1, ?)", (_baseline_hash(migrations),)
    )


def _backup_database(db_path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    basename = os.path.basename(db_path)
    stem, suffix = os.path.splitext(basename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = os.path.join(BACKUP_DIR, f"{stem}_{timestamp}{suffix or '.db'}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def _ensure_schema_version_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")


_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
# The runner owns the transaction and the foreign_keys setting. A script that
# commits, rolls back or toggles foreign keys would break the all-or-nothing upgrade.
_FORBIDDEN_STATEMENT_RE = re.compile(
    r"^(BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE|VACUUM|ATTACH|DETACH)\b"
    r"|^PRAGMA\s+(\w+\.)?(foreign_keys|legacy_alter_table|journal_mode)\b",
    re.IGNORECASE,
)


def _execute_sql_script(conn, script_path):
    with open(script_path, "r", encoding="utf-8") as script_file:
        script = script_file.read().replace(
            "__MAX_DIMENSION_DEPTH__",
            str(MAX_DIMENSION_DEPTH),
        )

    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            sql = statement.strip()
            if _COMMENT_RE.sub("", sql).strip():
                if _FORBIDDEN_STATEMENT_RE.match(_COMMENT_RE.sub("", sql).strip()):
                    raise ValueError(
                        f"{os.path.basename(script_path)} must not manage transactions or "
                        f"connection settings: {sql.splitlines()[0]!r}"
                    )
                conn.execute(sql)
            statement = ""
    if _COMMENT_RE.sub("", statement).strip():
        raise sqlite3.OperationalError("Migration script contains an incomplete SQL statement")


def _verify_schema(conn):
    """Return a list of problems found by the foreign key and integrity checks."""
    problems = []
    try:
        for row in conn.execute("PRAGMA foreign_key_check"):
            problems.append(
                f"foreign key violation: {row[0]} rowid {row[1]} -> {row[2]} (constraint {row[3]})"
            )
    except sqlite3.DatabaseError as error:
        # Raised when a foreign key points at a missing or non-unique parent column.
        problems.append(f"foreign key check failed: {error}")
    integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        problems.extend(f"integrity check: {message}" for message in integrity)
    return problems


def _apply_migrations(db_path, migrations, migration_kind):
    """Apply every pending migration in ONE transaction, verified before commit.

    All pending scripts share a single transaction because an intermediate
    version can be unsound on its own (001 alone fails the foreign key check),
    and committing between scripts would leave a half-upgraded file if a later
    one failed. Foreign keys are switched off outside the transaction (the
    pragma is a no-op inside one) so scripts can rebuild tables; the
    foreign_key_check before COMMIT then proves the result is consistent.
    """
    conn = sqlite3.connect(os.fspath(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    version = None
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        try:
            current_version = 0
            if _table_exists(conn, "schema_version"):
                row = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
                current_version = row["version"] or 0
            pending = [(v, name) for v, name in migrations if v > current_version]
            if not pending:
                # Another caller upgraded the file between our read-only version
                # check and taking the write lock. Leave the file untouched.
                conn.execute("ROLLBACK")
                return

            _ensure_schema_version_table(conn)
            for version, filename in pending:
                _execute_sql_script(conn, os.path.join(MIGRATIONS_DIR, filename))
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            if current_version == 0:
                _record_baseline_hash(conn, migrations)

            version = None
            problems = _verify_schema(conn)
            if problems:
                raise SchemaUpgradeBlockedError(
                    db_path,
                    "Upgraded schema failed verification; nothing was changed. " + "; ".join(problems),
                )
            conn.execute("COMMIT")
        except Exception as error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            if isinstance(error, SchemaUpgradeBlockedError):
                raise
            where = f"migration {version:03d}" if version is not None else "upgrade preparation"
            raise SchemaUpgradeBlockedError(
                db_path, f"{where} failed and was rolled back; nothing was changed. {error}"
            ) from error
    finally:
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        finally:
            conn.close()


def _upgrade_database(db_path, migrations, migration_kind):
    db_path = os.fspath(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    existed_before = os.path.isfile(db_path)
    _check_baseline(db_path, migrations)
    if _current_version(db_path) >= migrations[-1][0]:
        return

    if existed_before:
        _backup_database(db_path)
    try:
        _apply_migrations(db_path, migrations, migration_kind)
    except SchemaUpgradeBlockedError:
        if not existed_before and os.path.isfile(db_path):
            os.remove(db_path)
        raise


def ensure_company_database(db_path):
    """Create or upgrade a company database to the latest version."""
    _upgrade_database(os.fspath(db_path), MIGRATIONS, "company")


def ensure_master_database(db_path):
    """Upgrade the central authentication and company registry database."""
    _upgrade_database(db_path, MASTER_MIGRATIONS, "master")
