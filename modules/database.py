import contextlib
import hashlib
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from config import BACKUP_DIR, MIGRATIONS_DIR as _CONFIG_MIGRATIONS_DIR


MAX_DIMENSION_DEPTH = 10  # RP3 (2026-11-16; was 3)
MIGRATIONS_DIR = _CONFIG_MIGRATIONS_DIR
MIGRATIONS = [(1, "001_company.sql")]
MASTER_MIGRATIONS = [(1, "001_master.sql")]
BUSY_TIMEOUT_MS = 5000       # AX1: how long any connection waits for another writer's lock

_logger = logging.getLogger("strataledger")


class SchemaUpgradeBlockedError(Exception):
    def __init__(self, db_path, reason):
        self.db_path = os.fspath(db_path)
        self.reason = str(reason)
        super().__init__(f"Schema upgrade blocked for {self.db_path}: {self.reason}")


def _configure(conn):
    """AX1: every connection has foreign keys on (rule 4), the busy timeout and named-column rows."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


def get_connection(db_path):
    """Open a SQLite connection with foreign keys, the busy timeout and named-column rows (AX1)."""
    return _configure(sqlite3.connect(os.fspath(db_path)))


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
    return _configure(sqlite3.connect(uri, uri=True))


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


# --- Backups and restore (AX2) ------------------------------------------------------------------------------------
# One helper copies a database with sqlite3.Connection.backup: it reads every committed page, including pages still
# in the WAL, and never copies the -wal or -shm files. Each backup is `<stem>_<YYYYmmdd_HHMMSS_ffffff>_<reason>.db`
# in BACKUP_DIR, with its SHA-256 (K5, of the backup file itself) in `<backup>.sha256` beside it.

_REASON_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STAMP_FORMAT = "%Y%m%d_%H%M%S_%f"
_KEEP = (("day", 7), ("week", 4), ("month", 12))          # E7 retention


class RestoreRefusedError(Exception):
    """A restore was refused; `reason` says why and what to do next, and nothing was changed."""

    def __init__(self, db_path, reason):
        self.db_path = os.fspath(db_path)
        self.reason = str(reason)
        super().__init__(self.reason)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_reason(reason):
    if not isinstance(reason, str) or len(reason) > 40 or not _REASON_RE.fullmatch(reason):
        raise ValueError("A backup reason is 1-40 lower-case letters, digits and single hyphens")


def backup_database(db_path, *, reason):
    """Copy a database into BACKUP_DIR through the backup API (AX2). Returns {'path', 'sha256'}."""
    _check_reason(reason)
    db_path = os.fspath(db_path)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(db_path))[0]
    backup_path = os.path.join(BACKUP_DIR, f"{stem}_{datetime.now().strftime(_STAMP_FORMAT)}_{reason}.db")
    _copy_database(db_path, backup_path)
    digest = file_sha256(backup_path)
    with open(backup_path + ".sha256", "w", encoding="ascii", newline="") as handle:
        handle.write(digest + chr(10))
    return {"path": backup_path, "sha256": digest}


def _copy_database(source_path, target_path, *, source=None):
    """Copy through the backup API. The copy is left in rollback-journal mode, so the file alone is the whole
    database and its checksum covers everything (step-reviewer finding 1)."""
    source = source or _readonly_connection(source_path)
    try:
        target = _configure(sqlite3.connect(target_path))
        try:
            source.backup(target)
            target.execute("PRAGMA journal_mode = DELETE")
        finally:
            target.close()
    finally:
        source.close()


def _immutable_connection(path):
    """A read-only connection that reads only the main file: no -wal is applied and nothing is created beside it."""
    uri = f"{Path(path).resolve().as_uri()}?mode=ro&immutable=1"
    return _configure(sqlite3.connect(uri, uri=True))


def _backup_moments(db_path, reason):
    """{file name: moment} of the backups of one database for one reason."""
    stem = os.path.splitext(os.path.basename(os.fspath(db_path)))[0]
    pattern = re.compile(re.escape(stem) + r"_(\d{8}_\d{6}_\d{6})_" + re.escape(reason) + r"\.db")
    found = {}
    for name in (os.listdir(BACKUP_DIR) if os.path.isdir(BACKUP_DIR) else []):
        match = pattern.fullmatch(name)
        if match:
            found[name] = datetime.strptime(match.group(1), _STAMP_FORMAT)
    return found


def _period(moment, kind):
    if kind == "day":
        return moment.date()
    if kind == "week":
        return tuple(moment.isocalendar())[:2]
    return (moment.year, moment.month)


def prune_backups(db_path, *, reason):
    """E7 retention for one database's backups of one reason: keep the newest backup of each of the 7 newest days,
    the 4 newest ISO weeks and the 12 newest months that have one; delete the rest with their .sha256 files.
    Backups of other reasons and any other file are never touched. Returns the names deleted."""
    _check_reason(reason)
    moments = _backup_moments(db_path, reason)
    keep = set()
    for kind, count in _KEEP:
        newest = {}
        for name, moment in sorted(moments.items(), key=lambda item: item[1]):
            newest[_period(moment, kind)] = name
        keep |= {newest[period] for period in sorted(newest)[-count:]}
    deleted = sorted(set(moments) - keep)
    for name in deleted:
        for path in (os.path.join(BACKUP_DIR, name), os.path.join(BACKUP_DIR, name + ".sha256")):
            if os.path.isfile(path):
                os.remove(path)
    return deleted


STILL_OPEN = "The company is still open, so it was not restored. Close it everywhere and try again."


def _check_closed(db_path):
    """Refuse while any connection holds the file: Windows will not rename an open file. The file is renamed and
    renamed back; elsewhere this check passes and the hosted version restores in PostgreSQL instead."""
    probe = db_path + ".closed-check"
    try:
        os.rename(db_path, probe)
    except PermissionError:
        raise RestoreRefusedError(db_path, STILL_OPEN) from None
    try:
        os.rename(probe, db_path)
    except OSError:
        raise RestoreRefusedError(db_path, f"The company file could not be put back after the open-file check; it "
                                           f"is at {probe}. Rename it back to {os.path.basename(db_path)} before "
                                           "opening the company.") from None


def restore_database(backup_path, db_path, *, expected_sha256):
    """Put a backup back in place of a database that is closed (AX2, K5).

    Refused, with nothing changed: a backup whose SHA-256 is not `expected_sha256`, one that is not a sound
    database, or a target that is still open (Windows refuses to replace or delete an open file). Otherwise a
    safety backup of the current file is made first, the backup is copied beside the target, leftover -wal and
    -shm files are removed (so a stale WAL is never applied to the restored file), and the copy replaces the
    target. Returns {'safety_backup': its path, or None when there was no file}. The permission check and the
    Master's override of a checksum mismatch belong to the restore service (Phase 2.8)."""
    backup_path, db_path = os.fspath(backup_path), os.fspath(db_path)
    for suffix in ("-wal", "-journal"):
        if os.path.exists(backup_path + suffix):
            raise RestoreRefusedError(db_path, f"A {suffix[1:]} file sits beside the backup and is not covered by its "
                                               "checksum, so it was not restored. Choose another backup.")
    if file_sha256(backup_path) != expected_sha256:
        raise RestoreRefusedError(db_path, "The backup's checksum does not match, so it was not restored. Choose "
                                           "another backup.")
    try:
        check = _immutable_connection(backup_path)
        try:
            sound = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            check.close()
    except sqlite3.DatabaseError:
        sound = False
    if not sound:
        raise RestoreRefusedError(db_path, "That file is not a sound StrataLedger database, so it was not restored. "
                                           "Choose another backup.")
    staged = db_path + ".restoring"
    safety = None
    aside = []                   # the live -wal and -shm, kept until the replace has worked (finding 3)
    try:
        if os.path.isfile(db_path):
            _check_closed(db_path)
            safety = backup_database(db_path, reason="pre-restore")["path"]
        _copy_database(backup_path, staged, source=_immutable_connection(backup_path))
        for suffix in ("-wal", "-shm"):
            if os.path.exists(db_path + suffix):
                os.replace(db_path + suffix, db_path + suffix + ".restore-aside")
                aside.append(suffix)
        os.replace(staged, db_path)
    except PermissionError:
        for suffix in aside:
            os.replace(db_path + suffix + ".restore-aside", db_path + suffix)
        aside = []
        raise RestoreRefusedError(db_path, STILL_OPEN) from None
    finally:
        for leftover in [staged, staged + "-wal", staged + "-shm"] + [db_path + x + ".restore-aside" for x in aside]:
            if os.path.exists(leftover):
                os.remove(leftover)
    return {"safety_backup": safety}


def _ensure_wal(db_path):
    """AX1: master and company files are in WAL mode. An older file is switched once (no data changes) and the
    switch is logged."""
    conn = _configure(sqlite3.connect(db_path))
    try:
        if conn.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
            conn.execute("PRAGMA journal_mode = WAL")
            _logger.info("switched %s to WAL mode (AX1)", os.path.basename(db_path))
    finally:
        conn.close()


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
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")       # AX1: set when the file is built (outside the transaction)
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
        _ensure_wal(db_path)
        return

    if existed_before:
        backup_database(db_path, reason="pre-upgrade")
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
# Columns add-on SQL reads as NULL (secrets audit, STOP B): full bank numbers and tax ids are shown only through
# the services, which check view.bank_details and view.tax_ids. Every column of the audit tables (`audit_` names)
# reads as NULL too: their values can hold the same data.
_ADDON_HIDDEN_COLUMNS = {
    "bank_account": {"routing_number", "account_number"},
    "contact": {"tax_id", "exemption_cert_no"},
    "company_settings": {"tax_id"},
}
_ADDON_HIDDEN_TABLE_PREFIX = "audit_"


def _hidden_column(table, column):
    if not isinstance(table, str):
        return False
    table = table.lower()
    if table.startswith(_ADDON_HIDDEN_TABLE_PREFIX):
        return True
    return (column or "").lower() in _ADDON_HIDDEN_COLUMNS.get(table, ())


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
        if trigger is not None and self._audit_trigger(trigger):
            # HA9: one of this add-on's generated audit triggers (made by the runner, never by the add-on's SQL)
            # reads who is writing and appends to audit_log; it reads and writes nothing else outside the prefix.
            if action == sqlite3.SQLITE_READ or (action == sqlite3.SQLITE_INSERT and arg1 == "audit_log"):
                return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and _hidden_column(arg1, arg2):
            return sqlite3.SQLITE_IGNORE        # read as NULL: shown only through the services' permission checks
        if self._allowed(action, arg1, arg2, db_name):
            return sqlite3.SQLITE_OK
        self.refused.append((action, arg1, arg2, db_name, trigger))
        return sqlite3.SQLITE_DENY

    def _owns(self, name):
        return _owned(name, self.prefix, self.core)

    def _audit_trigger(self, name):
        found = _AUDIT_TRIGGER_RE.fullmatch(name)
        return found is not None and self._owns(found.group(1))

    def _allowed(self, action, arg1, arg2, db_name):
        if action in _READ_ACTIONS:
            return True
        if action == sqlite3.SQLITE_FUNCTION:
            return (arg2 or "").lower() not in _BANNED_FUNCTIONS
        if self.schema and action == sqlite3.SQLITE_UPDATE and (
                (arg1 == "sqlite_temp_master" and db_name == "temp")
                or (arg1 == "sqlite_sequence" and arg2 == "name" and db_name in (None, "main"))):
            # ALTER TABLE ... RENAME rewrites the temp schema (which holds nothing) and renames the table's
            # AUTOINCREMENT row; _check_schema_change then proves no core table's row changed.
            return True
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
            # A UNIQUE or non-integer PRIMARY KEY column makes SQLite build `sqlite_autoindex_<table>_N` itself.
            automatic = action in (sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_DROP_INDEX) and isinstance(arg1, str) \
                and isinstance(arg2, str) and arg1.startswith(f"sqlite_autoindex_{arg2}_")
            # HA9: dropping a table drops its audit triggers too; the runner rebuilds any that are missing after
            # every statement, so dropping one directly does not stop the audit either.
            audit = action == sqlite3.SQLITE_DROP_TRIGGER and isinstance(arg1, str) and self._audit_trigger(arg1)
            return (automatic or audit or self._owns(arg1)) and self._owns(arg2)
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
    if os.path.exists(migrations_dir) and not os.path.isdir(migrations_dir):
        raise AddonMigrationError(addon_key, "its migrations folder is a file; nothing was changed.")
    names = sorted(os.listdir(migrations_dir)) if os.path.isdir(migrations_dir) else []
    for name in names:
        if not name.lower().endswith(".sql"):
            continue
        found = pattern.fullmatch(name)
        if found is None:
            raise AddonMigrationError(addon_key, f"{name} is not named {addon_key}_NNN.sql; nothing was changed.")
        path = os.path.join(migrations_dir, name)
        real, base = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(migrations_dir))
        if os.path.dirname(real) != base:          # a link leading out of the folder (secrets audit LOW-4)
            raise AddonMigrationError(addon_key, f"{name} leads outside the add-on's migrations folder; nothing "
                                                 "was changed.")
        files[int(found.group(1))] = path
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


_SQL_TEXT_RE = re.compile(r"'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/", re.DOTALL)


def _sql_without_text(sql):
    """SQL with its string literals emptied and its comments turned into a space, so neither can hide or join
    words (`INSERT/**/INTO` stays two words)."""
    return _SQL_TEXT_RE.sub(lambda m: "''" if m.group(0).startswith("'") else " ", sql or "")


def _check_schema_change(conn, addon_key, before, after):
    """HA4 by result: every object added, changed or dropped is named with the prefix and sits on a prefixed table;
    no new trigger body writes a table outside it; and no add-on table references a table outside it (a cascade
    from a core table would run the add-on's triggers with no guard on, and a plain reference would block core
    deletes)."""
    prefix, core = addon_key + "_", core_table_names()
    for key in set(before) | set(after):
        if before.get(key) == after.get(key):
            continue
        kind, name = key
        tbl_name, sql = after.get(key) or before.get(key)
        audit = kind == "trigger" and _AUDIT_TRIGGER_RE.fullmatch(name)
        generated = bool(audit) and audit.group(1) == tbl_name          # made by _sync_audit_triggers (HA9)
        named = _owned(name, prefix, core) or (kind == "index" and name.startswith("sqlite_autoindex_" + prefix)) \
            or generated
        if not (named and _owned(tbl_name, prefix, core)):
            raise AddonMigrationError(addon_key, f"the {kind} {name} is outside the add-on's {prefix} tables; "
                                                 "nothing was changed.")
        if kind == "trigger" and key in after and not generated:
            for target in _TRIGGER_WRITE_RE.findall(_sql_without_text(sql)):
                if not _owned(target, prefix, core):
                    raise AddonMigrationError(addon_key, f"the trigger {name} writes {target}, outside the "
                                                         f"add-on's {prefix} tables; nothing was changed.")
        if kind == "table" and key in after:
            for row in conn.execute("SELECT \"table\" AS parent FROM pragma_foreign_key_list(?)", (name,)):
                if not _owned(row["parent"], prefix, core):
                    raise AddonMigrationError(addon_key, f"the table {name} refers to {row['parent']}, outside "
                                                         f"the add-on's {prefix} tables; nothing was changed.")


_AUDIT_TEMPLATE = "addon_audit_triggers.sql"
_AUDIT_TRIGGER_RE = re.compile(r"audit_(\w+)_(insert|update|delete)")
_PLAIN_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WITHOUT_ROWID_RE = re.compile(r"\bWITHOUT\s+ROWID\b", re.IGNORECASE)
_JSON_PAIRS = 60          # json_object / json_insert stay under SQLite's 127-argument limit


def _audit_template():
    """The three CREATE TRIGGER statements of migrations/addon_audit_triggers.sql, comments removed."""
    with open(os.path.join(MIGRATIONS_DIR, _AUDIT_TEMPLATE), "r", encoding="utf-8") as handle:
        text = handle.read()
    statements, statement = [], ""
    for line in text.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            bare = _COMMENT_RE.sub("", statement).strip()
            if bare:
                statements.append(bare)
            statement = ""
    return statements


def _audit_json(row, columns):
    """JSON of every column of NEW or OLD; past 60 columns json_insert adds the rest (it keeps NULL values).
    Column names are plain identifiers (checked first), so they are safe to place here."""
    chunks = [columns[i:i + _JSON_PAIRS] for i in range(0, len(columns), _JSON_PAIRS)]
    text = "json_object(" + ", ".join(f"'{c}', {row}.\"{c}\"" for c in chunks[0]) + ")"
    for chunk in chunks[1:]:
        text = "json_insert(" + text + ", " + ", ".join(f"'$.\"{c}\"', {row}.\"{c}\"" for c in chunk) + ")"
    return text


def _sync_audit_triggers(conn, addon_key, synced):
    """HA9: give every `<key>_` table the three standard audit triggers, rebuilt when its definition changed.
    `synced` maps each table to the definition its triggers were made for. Refuses a WITHOUT ROWID table (the
    audit row names the rowid) and a table or column name that is not letters, digits and underscores."""
    prefix, core = addon_key + "_", core_table_names()
    template = None
    tables = {r["name"]: r["sql"] for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'")
              if _owned(r["name"], prefix, core)}
    for table, sql in sorted(tables.items()):
        present = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?", (table,))}
        complete = {f"audit_{table}_{action}" for action in ("insert", "update", "delete")} <= present
        if synced.get(table) == sql and complete:
            continue
        if not _PLAIN_NAME_RE.fullmatch(table):
            raise AddonMigrationError(addon_key, f"the table name {table!r} is not plain letters, digits and "
                                                 "underscores; nothing was changed.")
        if _WITHOUT_ROWID_RE.search(_sql_without_text(sql)):
            raise AddonMigrationError(addon_key, f"the table {table} is WITHOUT ROWID; add-on tables keep a rowid so "
                                                 "their changes can be audit-logged. Nothing was changed.")
        columns = [r["name"] for r in conn.execute("SELECT name FROM pragma_table_info(?)", (table,))]
        for column in columns:
            if not _PLAIN_NAME_RE.fullmatch(column):
                raise AddonMigrationError(addon_key, f"the table {table} has a column named {column!r}; add-on "
                                                     "column names are plain letters, digits and underscores (name a "
                                                     "copied column with AS). Nothing was changed.")
        for name in sorted(present):
            if _AUDIT_TRIGGER_RE.fullmatch(name):
                conn.execute(f'DROP TRIGGER "{name}"')
        template = template or _audit_template()
        new, old = _audit_json("NEW", columns), _audit_json("OLD", columns)
        for statement in template:
            conn.execute(statement.replace("ON __TABLE__", f'ON "{table}"').replace("__TABLE__", table)
                         .replace("__NEW__", new).replace("__OLD__", old))
        synced[table] = sql
    for table in set(synced) - set(tables):
        del synced[table]


def _core_counters(conn, addon_key):
    """What an add-on migration must not change in sqlite_sequence: the rows of tables outside its prefix, except
    audit_log's, which the migration's own audit rows move (HA9). Returns (those rows, audit_log's seq)."""
    prefix, core = addon_key + "_", core_table_names()
    if not _table_exists(conn, "sqlite_sequence"):
        return [], None
    rows = [(r["name"], r["seq"]) for r in conn.execute("SELECT name, seq FROM sqlite_sequence")]
    audit = next((seq for name, seq in rows if name == "audit_log"), None)
    return sorted((name, seq) for name, seq in rows if name != "audit_log" and not _owned(name, prefix, core)), audit


def _check_counters(conn, addon_key, before):
    """Core counters are unchanged; audit_log's only moves forward, to its newest log_id; and every add-on counter
    row belongs to an add-on table that exists (a row renamed away from a core table is refused)."""
    prefix, core = addon_key + "_", core_table_names()
    rows, audit = _core_counters(conn, addon_key)
    newest = conn.execute("SELECT MAX(log_id) FROM audit_log").fetchone()[0] if _table_exists(conn, "audit_log") \
        else None
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    strays = [r["name"] for r in conn.execute("SELECT name FROM sqlite_sequence")
              if _owned(r["name"], prefix, core) and r["name"] not in tables] if _table_exists(conn, "sqlite_sequence") \
        else []
    moved_back = before[1] is not None and (audit is None or audit < before[1] or audit != newest)
    if rows != before[0] or moved_back or (audit is not None and audit != newest) or strays:
        raise AddonMigrationError(addon_key, "the migration changed a core table's AUTOINCREMENT counter; nothing "
                                             "was changed.")


def _applied_addon_versions(db_path, addon_key):
    conn = _readonly_connection(db_path)
    try:
        return {r["version"]: r["sha256"] for r in conn.execute(
            "SELECT version, sha256 FROM addon_schema_version WHERE addon_key = ?", (addon_key,))}
    finally:
        conn.close()


def apply_addon_migrations(db_path, addon_key, migrations_dir, *, audit=None):
    """Apply an add-on's pending `<key>_NNN.sql` files to a company file in ONE transaction, after a backup.

    Applied files must be unchanged (their SHA-256 is stored in addon_schema_version, HA6). Every statement runs
    under the add-on's schema authorizer, and the result is compared with sqlite_master before commit (HA4). After
    each statement every `<key>_` table gets the standard audit triggers (HA9), so the migration's own rows are
    logged; `audit` (tx.AuditStamp) names the person in those rows. Returns the versions applied (empty when none
    is pending). Raises AddonKeyError or AddonMigrationError, and then nothing was changed.
    """
    check_addon_key(addon_key)
    db_path = os.fspath(db_path)
    _check_baseline(db_path, MIGRATIONS)
    try:
        return _apply_addon_migrations(db_path, addon_key, os.fspath(migrations_dir), audit)
    except (UnicodeDecodeError, OSError) as error:      # a file that cannot be read, or the backup failed
        raise AddonMigrationError(addon_key, f"a migration file could not be read, or the backup failed; nothing "
                                             f"was changed. {error}") from error


def _apply_addon_migrations(db_path, addon_key, migrations_dir, audit):
    files = _addon_files(addon_key, migrations_dir)
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
    reason = f"addon-{addon_key}"
    backup_database(db_path, reason=reason)
    prune_backups(db_path, reason=reason)                  # E7 retention (secrets audit LOW-6)
    conn = get_connection(db_path)
    conn.isolation_level = None
    current = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if audit is not None:
                audit.begin(conn)
            before = _schema_objects(conn)
            counters = _core_counters(conn, addon_key)
            synced = {}
            _sync_audit_triggers(conn, addon_key, synced)        # tables from before HA9 get their triggers too
            for version, path, statements, digest in plan:
                current = os.path.basename(path)
                _run_addon_statements(conn, addon_key, current, statements, synced)
                conn.execute("INSERT INTO addon_schema_version (addon_key, version, sha256) VALUES (?, ?, ?)",
                             (addon_key, version, digest))
            current = None
            _check_schema_change(conn, addon_key, before, _schema_objects(conn))
            _check_counters(conn, addon_key, counters)
            problems = _verify_schema(conn)
            if problems:
                raise AddonMigrationError(addon_key, "the result failed verification; nothing was changed. "
                                          + "; ".join(problems))
            if audit is not None:
                audit.end(conn)
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


def _run_addon_statements(conn, addon_key, filename, statements, synced):
    guard = _AddonGuard(addon_key, schema=True)
    for sql in statements:
        conn.set_authorizer(guard)
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
        _sync_audit_triggers(conn, addon_key, synced)       # the runner's own step: no add-on authorizer
