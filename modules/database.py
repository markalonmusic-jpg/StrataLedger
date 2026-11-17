import contextlib
import hashlib
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from config import BACKUP_DIR, MIGRATIONS_DIR as _CONFIG_MIGRATIONS_DIR


MAX_DIMENSION_DEPTH = 10  # RP3 (2026-11-16; was 3)
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


def check_master_database(db_path):
    """Raise SchemaUpgradeBlockedError if the master file was not built from the current baseline. Never writes."""
    _check_baseline(os.fspath(db_path), MASTER_MIGRATIONS)


def set_busy_timeout(conn, milliseconds):
    """How long this connection waits for a lock held by another writer (H5: PRAGMAs live here only)."""
    conn.execute(f"PRAGMA busy_timeout = {int(milliseconds)}")


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


# --- Add-ons (Phase 2.7 STOP B: HA2, HA4, HA6) --------------------------------------------------------------------
# An add-on owns the tables named `<key>_...`. While one of its hook handlers runs inside a core transaction, the
# SQLite authorizer below lets it read anything and write only those tables (HA2). Its migrations may create and
# change only objects named with that prefix, on tables with that prefix (HA4), and each applied file is recorded
# with its SHA-256 (HA6). The authorizer sees the statements a trigger body runs too, so a trigger on an add-on
# table cannot write a core table while either guard is on.

class AddonKeyError(ValueError):
    """An add-on key is malformed, or its prefix would match a core table."""


class AddonMigrationError(Exception):
    """An add-on migration was refused or failed; the file was left unchanged."""

    def __init__(self, addon_key, reason):
        self.addon_key = addon_key
        self.reason = str(reason)
        super().__init__(f"Add-on {addon_key}: {self.reason}")


_ADDON_KEY_RE = re.compile(r"[a-z][a-z0-9]{1,30}")
_RESERVED_ADDON_KEYS = frozenset({"sqlite"})
_CREATE_TABLE_RE = re.compile(r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"\[`]?(\w+)", re.IGNORECASE | re.M)
_core_tables_cache = {}


def core_table_names():
    """Every table the company baseline creates, lower-case (read from the baseline file, cached by its hash)."""
    digest = _baseline_hash(MIGRATIONS)
    if digest not in _core_tables_cache:
        path = os.path.join(MIGRATIONS_DIR, MIGRATIONS[0][1])
        with open(path, "r", encoding="utf-8") as handle:
            text = _COMMENT_RE.sub("", handle.read())
        names = {name.lower() for name in _CREATE_TABLE_RE.findall(text)}
        _core_tables_cache.clear()
        _core_tables_cache[digest] = frozenset(names | {"schema_version", "schema_baseline"})
    return _core_tables_cache[digest]


def check_addon_key(addon_key):
    """Raise AddonKeyError unless the key is 2-31 lower-case letters and digits, starting with a letter, and no core
    table starts with `<key>_` (a key like `journal` would otherwise own journal_line)."""
    if not isinstance(addon_key, str) or not _ADDON_KEY_RE.fullmatch(addon_key):
        raise AddonKeyError(f"An add-on key is 2 to 31 lower-case letters and digits, starting with a letter; "
                            f"got {addon_key!r}")
    prefix = addon_key + "_"
    if addon_key in _RESERVED_ADDON_KEYS or any(name.startswith(prefix) for name in core_table_names()):
        raise AddonKeyError(f"The add-on key {addon_key!r} is reserved: core tables start with {prefix!r}")


def _owned(name, prefix, core):
    return isinstance(name, str) and name.lower().startswith(prefix) and name.lower() not in core


_READ_ACTIONS = {sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
_WRITE_ACTIONS = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}
_SCHEMA_TABLES = {"sqlite_master", "sqlite_schema"}
_BANNED_FUNCTIONS = {"load_extension"}


class _AddonGuard:
    """The authorizer for one add-on. `schema=True` (migrations) also allows creating, changing and dropping its own
    objects. Refused actions are kept in `refused` for the log."""

    def __init__(self, addon_key, *, schema):
        check_addon_key(addon_key)
        self.addon_key = addon_key
        self.prefix = addon_key + "_"
        self.core = core_table_names()
        self.schema = schema
        self.refused = []

    def __call__(self, action, arg1, arg2, db_name, trigger):
        if self._allowed(action, arg1, arg2, db_name):
            return sqlite3.SQLITE_OK
        self.refused.append((action, arg1, arg2, db_name, trigger))
        return sqlite3.SQLITE_DENY

    def _owns(self, name):
        return _owned(name, self.prefix, self.core)

    def _allowed(self, action, arg1, arg2, db_name):
        if action in _READ_ACTIONS:
            return True
        if action == sqlite3.SQLITE_FUNCTION:
            return (arg2 or "").lower() not in _BANNED_FUNCTIONS
        if db_name not in (None, "main"):
            return False
        if action in _WRITE_ACTIONS:
            # A CREATE, ALTER or DROP writes the schema table; that action itself was checked just before.
            return self._owns(arg1) or (self.schema and arg1 in _SCHEMA_TABLES)
        if not self.schema:
            return False
        if action in (sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_CREATE_VIEW,
                      sqlite3.SQLITE_DROP_VIEW):
            return self._owns(arg1)
        if action in (sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_CREATE_TRIGGER,
                      sqlite3.SQLITE_DROP_TRIGGER):
            return self._owns(arg1) and self._owns(arg2)
        if action == sqlite3.SQLITE_ALTER_TABLE:
            return self._owns(arg2)
        if action == sqlite3.SQLITE_REINDEX:   # CREATE INDEX asks for it on the new index
            return self._owns(arg1)
        return False                      # PRAGMA, ATTACH, DETACH, transactions, temp objects, ANALYZE, REINDEX...


@contextlib.contextmanager
def addon_write_guard(conn, addon_key):
    """While the block runs, `conn` may read anything and write only `<addon_key>_` tables: no schema change,
    PRAGMA, ATTACH or transaction control (HA2). Yields the guard; its `refused` lists what was refused."""
    guard = _AddonGuard(addon_key, schema=False)
    conn.set_authorizer(guard)           # this also expires the statements prepared before, so each is checked again
    try:
        yield guard
    finally:
        conn.set_authorizer(None)


def addon_file_hash(path):
    """SHA-256 of an add-on migration file's text; line endings do not matter (like the baseline hash)."""
    with open(path, "r", encoding="utf-8", newline=None) as handle:
        text = handle.read().replace(chr(13) + chr(10), chr(10))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_ADDON_FORBIDDEN_RE = re.compile(
    r"^(?P<tx>BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b|^(?P<pragma>PRAGMA)\b|^(?P<attach>ATTACH|DETACH)\b"
    r"|^(?P<vacuum>VACUUM)\b",
    re.IGNORECASE,
)
_FORBIDDEN_WORDS = {"tx": "transaction control", "pragma": "PRAGMA", "attach": "ATTACH or DETACH",
                    "vacuum": "VACUUM"}
_TRIGGER_WRITE_RE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+[\"\[`]?(\w+)",
    re.IGNORECASE)


def _addon_files(addon_key, migrations_dir):
    """{version: path} for `<key>_NNN.sql`, refusing any other .sql file and any gap from 001."""
    pattern = re.compile(re.escape(addon_key) + r"_(\d{3})\.sql")
    files = {}
    names = sorted(os.listdir(migrations_dir)) if os.path.isdir(migrations_dir) else []
    for name in names:
        if not name.lower().endswith(".sql"):
            continue
        found = pattern.fullmatch(name)
        if found is None:
            raise AddonMigrationError(addon_key, f"{name} is not named {addon_key}_NNN.sql; nothing was changed.")
        files[int(found.group(1))] = os.path.join(migrations_dir, name)
    if sorted(files) != list(range(1, len(files) + 1)):
        raise AddonMigrationError(addon_key, f"the migration files have a gap ({sorted(files)}); they are numbered "
                                             "from 001 without a gap. Nothing was changed.")
    return files


def _addon_statements(addon_key, path):
    with open(path, "r", encoding="utf-8") as handle:
        script = handle.read()
    statements, statement = [], ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            bare = _COMMENT_RE.sub("", statement).strip()
            if bare:
                found = _ADDON_FORBIDDEN_RE.match(bare)
                if found:
                    raise AddonMigrationError(addon_key, f"{os.path.basename(path)} uses "
                                                         f"{_FORBIDDEN_WORDS[found.lastgroup]}, which add-on "
                                                         "migrations may not; nothing was changed.")
                statements.append(statement.strip())
            statement = ""
    if _COMMENT_RE.sub("", statement).strip():
        raise AddonMigrationError(addon_key, f"{os.path.basename(path)} ends with an incomplete statement; nothing "
                                             "was changed.")
    return statements


def _schema_objects(conn):
    return {(r["type"], r["name"]): (r["tbl_name"], r["sql"])
            for r in conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master")}


def _check_schema_change(addon_key, before, after):
    """HA4 by result: every object added, changed or dropped is named with the prefix and sits on a prefixed table,
    and no new trigger body writes a table outside it."""
    prefix, core = addon_key + "_", core_table_names()
    for key in set(before) | set(after):
        if before.get(key) == after.get(key):
            continue
        kind, name = key
        tbl_name, sql = after.get(key) or before.get(key)
        named = _owned(name, prefix, core) or (kind == "index" and name.startswith("sqlite_autoindex_" + prefix))
        if not (named and _owned(tbl_name, prefix, core)):
            raise AddonMigrationError(addon_key, f"the {kind} {name} is outside the add-on's {prefix} tables; "
                                                 "nothing was changed.")
        if kind == "trigger" and key in after:
            for target in _TRIGGER_WRITE_RE.findall(_COMMENT_RE.sub("", sql or "")):
                if not _owned(target, prefix, core):
                    raise AddonMigrationError(addon_key, f"the trigger {name} writes {target}, outside the "
                                                         f"add-on's {prefix} tables; nothing was changed.")


def _applied_addon_versions(db_path, addon_key):
    conn = _readonly_connection(db_path)
    try:
        return {r["version"]: r["sha256"] for r in conn.execute(
            "SELECT version, sha256 FROM addon_schema_version WHERE addon_key = ?", (addon_key,))}
    finally:
        conn.close()


def apply_addon_migrations(db_path, addon_key, migrations_dir):
    """Apply an add-on's pending `<key>_NNN.sql` files to a company file in ONE transaction, after a backup.

    Applied files must be unchanged (their SHA-256 is stored in addon_schema_version, HA6). Every statement runs
    under the add-on's schema authorizer, and the result is compared with sqlite_master before commit (HA4).
    Returns the versions applied (empty when none is pending). Raises AddonKeyError or AddonMigrationError, and
    then nothing was changed.
    """
    check_addon_key(addon_key)
    db_path = os.fspath(db_path)
    _check_baseline(db_path, MIGRATIONS)
    files = _addon_files(addon_key, os.fspath(migrations_dir))
    done = _applied_addon_versions(db_path, addon_key)
    for version, digest in sorted(done.items()):
        name = f"{addon_key}_{version:03d}.sql"
        if version not in files:
            raise AddonMigrationError(addon_key, f"{name} is missing; it was applied to this company, so put it "
                                                 "back. Nothing was changed.")
        if addon_file_hash(files[version]) != digest:
            raise AddonMigrationError(addon_key, f"{name} was changed after it was applied; an applied file is "
                                                 "never edited, add a new one instead. Nothing was changed.")
    pending = [v for v in sorted(files) if v not in done]
    if not pending:
        return []
    if done and pending[0] != max(done) + 1:
        raise AddonMigrationError(addon_key, "the applied migrations have a gap; nothing was changed.")
    plan = [(v, files[v], _addon_statements(addon_key, files[v]), addon_file_hash(files[v])) for v in pending]
    _backup_database(db_path)
    conn = get_connection(db_path)
    conn.isolation_level = None
    current = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            before = _schema_objects(conn)
            for version, path, statements, digest in plan:
                current = os.path.basename(path)
                _run_addon_statements(conn, addon_key, current, statements)
                conn.execute("INSERT INTO addon_schema_version (addon_key, version, sha256) VALUES (?, ?, ?)",
                             (addon_key, version, digest))
            current = None
            _check_schema_change(addon_key, before, _schema_objects(conn))
            problems = _verify_schema(conn)
            if problems:
                raise AddonMigrationError(addon_key, "the result failed verification; nothing was changed. "
                                          + "; ".join(problems))
            conn.execute("COMMIT")
        except Exception as error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            if isinstance(error, AddonMigrationError):
                raise
            where = current or "the migration"
            raise AddonMigrationError(addon_key, f"{where} failed and was rolled back; nothing was changed. "
                                                 f"{error}") from error
    finally:
        conn.close()
    return pending


def _run_addon_statements(conn, addon_key, filename, statements):
    guard = _AddonGuard(addon_key, schema=True)
    conn.set_authorizer(guard)
    try:
        for sql in statements:
            try:
                conn.execute(sql)
            except sqlite3.DatabaseError:
                if guard.refused:
                    raise AddonMigrationError(addon_key, f"{filename} reaches outside the add-on's {addon_key}_ "
                                                         f"tables ({sql.splitlines()[0]!r}); nothing was "
                                                         "changed.") from None
                raise
    finally:
        conn.set_authorizer(None)
