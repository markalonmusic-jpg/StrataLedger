"""The add-on parts of modules/database.py (Phase 2.7 STOP B): the handler write guard (HA2) and the add-on
migration runner (HA4, HA6).

* While a handler runs, the SQLite authorizer lets it read anything and write only its own `<key>_` tables; no
  schema change, PRAGMA, ATTACH or transaction control. Writes made by a trigger body are checked the same way.
* An add-on key is lower-case letters and digits; a key whose prefix would match a core table is refused.
* Add-on migrations are `<key>_NNN.sql`, applied in one transaction after a backup, each recorded with its SHA-256.
  Refused, with nothing changed: an edited or missing applied file, a gap, an object outside the prefix, a trigger
  or index on another table, PRAGMA, ATTACH, transaction control.
"""
import os
import sqlite3

import pytest

import modules.database as database

KEY = "demo"


@pytest.fixture
def company(fresh_company):
    return fresh_company


@pytest.fixture
def conn(company):
    connection = database.get_connection(company)
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("CREATE TABLE demo_note (note_id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
    yield connection
    if connection.in_transaction:
        connection.execute("ROLLBACK")
    connection.close()


def migrations(tmp_path, files):
    folder = tmp_path / "migrations"
    folder.mkdir(exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def applied(company):
    conn = database.get_readonly_connection(company)
    try:
        return [(r["addon_key"], r["version"], r["sha256"]) for r in conn.execute(
            "SELECT addon_key, version, sha256 FROM addon_schema_version ORDER BY version")]
    finally:
        conn.close()


def objects(company):
    conn = database.get_readonly_connection(company)
    try:
        return sorted(tuple(r) for r in conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master"))
    finally:
        conn.close()


# --- Keys ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["demo", "ph", "tax2", "a1"])
def test_good_keys(key):
    database.check_addon_key(key)


@pytest.mark.parametrize("key", ["", "x", "Demo", "demo_x", "demo-x", "1demo", "a" * 32, None, 5,
                                 "journal", "invoice", "sqlite", "audit", "company", "payment"])
def test_bad_or_core_colliding_keys_are_refused(key):
    with pytest.raises(database.AddonKeyError):
        database.check_addon_key(key)


def test_the_core_tables_are_read_from_the_baseline():
    core = database.core_table_names()
    assert {"journal_entry", "journal_line", "audit_log", "company_addon", "addon_schema_version"} <= core
    assert all(name == name.lower() for name in core)


# --- The handler write guard (HA2) ---------------------------------------------------------------------------------

def test_a_handler_writes_its_own_tables_and_reads_anything(conn):
    with database.addon_write_guard(conn, KEY):
        conn.execute("INSERT INTO demo_note (text) VALUES ('hi')")
        conn.execute("UPDATE demo_note SET text = 'there'")
        assert conn.execute("SELECT COUNT(*) FROM journal_entry").fetchone()[0] == 0
        conn.execute("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 3) "
                     "INSERT INTO demo_note (text) SELECT i FROM n")
        conn.execute("DELETE FROM demo_note WHERE text = '1'")
    assert conn.execute("SELECT COUNT(*) FROM demo_note").fetchone()[0] == 3


@pytest.mark.parametrize("sql", [
    "INSERT INTO audit_log (table_name, record_id, action) VALUES ('x', 1, 'Insert')",
    "UPDATE journal_entry SET description = 'x'",
    "DELETE FROM journal_line",
    "UPDATE company_addon SET enabled = 1",
    "INSERT INTO addon_schema_version (addon_key, version, sha256) VALUES ('demo', 9, '" + "a" * 64 + "')",
    "UPDATE sqlite_sequence SET seq = 0",
    "CREATE TABLE demo_more (x)",
    "DROP TABLE demo_note",
    "ALTER TABLE demo_note ADD COLUMN y",
    "CREATE INDEX demo_ix ON demo_note (text)",
    "CREATE TEMP TABLE demo_tmp (x)",
    "PRAGMA foreign_keys = OFF",
    "PRAGMA table_info(journal_entry)",
    "ATTACH DATABASE ':memory:' AS other",
    "COMMIT",
    "SAVEPOINT demo",
    "SELECT load_extension('x')",
    "ANALYZE",
    "REINDEX",
])
def test_a_handler_cannot_write_core_tables_or_change_the_schema(conn, sql):
    before = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
    with database.addon_write_guard(conn, KEY) as guard:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)
    assert guard.refused                                   # what it tried is kept for the log
    assert conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == before
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_a_core_statement_prepared_before_the_guard_is_checked_again(conn):
    """Python caches prepared statements by their text; the guard must still refuse the very SQL core just ran."""
    sql = "UPDATE journal_entry SET description = 'x' WHERE entry_id = ?"
    conn.execute(sql, (1,))
    with database.addon_write_guard(conn, KEY):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql, (1,))


def test_a_trigger_body_writing_a_core_table_is_refused(conn):
    conn.execute("CREATE TRIGGER demo_note_spill AFTER INSERT ON demo_note BEGIN "
                 "UPDATE journal_entry SET description = 'x'; END")
    with database.addon_write_guard(conn, KEY):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("INSERT INTO demo_note (text) VALUES ('hi')")
    assert conn.execute("SELECT COUNT(*) FROM demo_note").fetchone()[0] == 0


def test_another_addons_tables_are_refused(conn):
    conn.execute("CREATE TABLE other_note (x)")
    with database.addon_write_guard(conn, KEY):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("INSERT INTO other_note (x) VALUES (1)")


def test_the_guard_is_removed_afterwards_even_on_error(conn):
    with pytest.raises(RuntimeError):
        with database.addon_write_guard(conn, KEY):
            raise RuntimeError("boom")
    conn.execute("UPDATE journal_entry SET description = 'x'")             # core may write again


def test_the_guard_refuses_a_bad_key(conn):
    with pytest.raises(database.AddonKeyError):
        with database.addon_write_guard(conn, "journal"):
            pass


# --- The add-on migration runner (HA4, HA6) -------------------------------------------------------------------------

GOOD_1 = "CREATE TABLE demo_note (note_id INTEGER PRIMARY KEY, text TEXT NOT NULL);\n" \
         "CREATE INDEX demo_note_text ON demo_note (text);\n" \
         "INSERT INTO demo_note (text) VALUES ('seed');\n"
GOOD_2 = "ALTER TABLE demo_note ADD COLUMN amount_cents INTEGER;\n" \
         "CREATE TRIGGER demo_note_guard BEFORE DELETE ON demo_note BEGIN SELECT RAISE(ABORT, 'no'); END;\n"


def test_migrations_apply_in_order_with_a_backup_and_their_hashes(company, tmp_path, backup_dir):
    folder = migrations(tmp_path, {"demo_001.sql": GOOD_1, "demo_002.sql": GOOD_2})
    assert database.apply_addon_migrations(company, KEY, folder) == [1, 2]
    rows = applied(company)
    assert [(k, v) for k, v, _ in rows] == [(KEY, 1), (KEY, 2)]
    assert rows[0][2] == database.addon_file_hash(folder / "demo_001.sql")
    assert len(os.listdir(backup_dir)) == 1
    assert database.apply_addon_migrations(company, KEY, folder) == []                 # nothing pending
    assert len(os.listdir(backup_dir)) == 1                                              # no second backup
    (folder / "demo_003.sql").write_text("CREATE TABLE demo_more (x);\n", encoding="utf-8")
    assert database.apply_addon_migrations(company, KEY, folder) == [3]


def test_the_hash_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a.sql", tmp_path / "b.sql"
    a.write_bytes(b"CREATE TABLE demo_x (y);\n")
    b.write_bytes(b"CREATE TABLE demo_x (y);\r\n")
    assert database.addon_file_hash(a) == database.addon_file_hash(b)


def test_an_edited_applied_file_is_refused(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": GOOD_1})
    database.apply_addon_migrations(company, KEY, folder)
    (folder / "demo_001.sql").write_text(GOOD_1 + "-- edited\n", encoding="utf-8")
    (folder / "demo_002.sql").write_text(GOOD_2, encoding="utf-8")
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match="demo_001.sql was changed after it was applied"):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before


def test_a_missing_applied_file_is_refused(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": GOOD_1, "demo_002.sql": GOOD_2})
    database.apply_addon_migrations(company, KEY, folder)
    (folder / "demo_002.sql").unlink()
    with pytest.raises(database.AddonMigrationError, match="demo_002.sql is missing"):
        database.apply_addon_migrations(company, KEY, folder)


@pytest.mark.parametrize("names, match", [
    (["demo_001.sql", "demo_003.sql"], "gap"),
    (["demo_002.sql"], "gap"),
    (["demo_001.sql", "demo_1.sql"], "named"),
    (["demo_001.sql", "other_002.sql"], "named"),
    (["demo_001.sql", "notes.sql"], "named"),
])
def test_names_and_gaps_are_checked(company, tmp_path, names, match):
    folder = migrations(tmp_path, {name: f"CREATE TABLE demo_t{i} (x);\n" for i, name in enumerate(names)})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=match):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before and applied(company) == []


BAD_SCRIPTS = [
    ("CREATE TABLE journal_extra (x);", "outside"),
    ("CREATE TABLE demo_ok (x);\nCREATE INDEX demo_ix ON journal_entry (description);", "outside"),
    ("CREATE INDEX journal_ix ON journal_entry (description);", "outside"),
    ("CREATE TRIGGER demo_tr AFTER INSERT ON journal_entry BEGIN SELECT 1; END;", "outside"),
    ("CREATE TABLE demo_ok (x);\nCREATE TRIGGER demo_tr AFTER INSERT ON demo_ok BEGIN "
     "UPDATE journal_entry SET description = 'x'; END;", "outside"),
    ("CREATE TABLE demo_ok (x);\nCREATE TRIGGER demo_tr AFTER INSERT ON demo_ok BEGIN "
     "INSERT INTO audit_log (table_name, record_id) VALUES ('x', 1); END;", "outside"),
    ("CREATE VIEW ledger_peek AS SELECT * FROM journal_entry;", "outside"),
    ("CREATE TABLE demo_ok (x);\nALTER TABLE demo_ok RENAME TO ledger_ok;", "outside"),
    ("INSERT INTO audit_log (table_name, record_id, action) VALUES ('x', 1, 'Insert');", "outside"),
    ("UPDATE company_addon SET enabled = 1;", "outside"),
    ("DELETE FROM addon_schema_version;", "outside"),
    ("DROP TABLE journal_line;", "outside"),
    ("ALTER TABLE journal_entry ADD COLUMN demo_x TEXT;", "outside"),
    ("PRAGMA foreign_keys = OFF;", "PRAGMA"),
    ("pragma writable_schema = 1;", "PRAGMA"),
    ("ATTACH DATABASE 'x.db' AS other;", "ATTACH"),
    ("DETACH DATABASE other;", "ATTACH"),
    ("BEGIN;", "transaction"),
    ("COMMIT;", "transaction"),
    ("SAVEPOINT x;", "transaction"),
    ("VACUUM;", "VACUUM"),
    ("CREATE TEMP TABLE demo_t (x);", "outside"),
    ("CREATE TABLE demo_ok (x", "incomplete"),
    # step-reviewer finding 1: a comment or a string must not hide a trigger's write to a core table
    ("CREATE TABLE demo_ok (x);\nCREATE TRIGGER demo_tr AFTER INSERT ON demo_ok BEGIN "
     "INSERT/**/INTO company_addon (addon_key, enabled) VALUES ('evil', 1); END;", "outside"),
    ("CREATE TABLE demo_ok (x);\nCREATE TRIGGER demo_tr AFTER INSERT ON demo_ok BEGIN "
     "SELECT '--'; UPDATE journal_entry SET description = 'x'; END;", "outside"),
    # ... and an add-on table may not reference a core table (a cascade would run its triggers unguarded)
    ("CREATE TABLE demo_link (addon_key TEXT REFERENCES company_addon(addon_key) ON DELETE CASCADE);", "refer"),
    ("CREATE TABLE demo_link (entry_id INTEGER REFERENCES journal_entry(entry_id));", "refer"),
    ("CREATE TABLE demo_ok (x);\nALTER TABLE demo_ok ADD COLUMN e INTEGER REFERENCES journal_entry(entry_id);",
     "refer"),
]


@pytest.mark.parametrize("script, match", BAD_SCRIPTS)
def test_refused_scripts_change_nothing(company, tmp_path, backup_dir, script, match):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_first (x);\n" + script + "\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=match) as refused:
        database.apply_addon_migrations(company, KEY, folder)
    assert refused.value.addon_key == KEY
    assert objects(company) == before and applied(company) == []


def test_a_failing_statement_rolls_back_every_file(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": GOOD_1, "demo_002.sql": "INSERT INTO demo_missing VALUES (1);\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match="demo_002.sql"):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before and applied(company) == []


def test_a_bad_key_is_refused_before_anything(company, tmp_path):
    folder = migrations(tmp_path, {"journal_001.sql": "CREATE TABLE journal_x (y);\n"})
    with pytest.raises(database.AddonKeyError):
        database.apply_addon_migrations(company, "journal", folder)


def test_core_tables_still_work_after_an_addon_migration(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": GOOD_1})
    database.apply_addon_migrations(company, KEY, folder)
    conn = database.get_connection(company)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()
    database.ensure_company_database(company)      # the baseline guard still accepts the file


def test_an_addon_table_may_reference_its_own_tables(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_parent (id INTEGER PRIMARY KEY);\n"
                                                   "CREATE TABLE demo_child (parent_id INTEGER REFERENCES "
                                                   "demo_parent(id) ON DELETE CASCADE);\n"})
    assert database.apply_addon_migrations(company, KEY, folder) == [1]


@pytest.mark.parametrize("problem", ["not utf-8", "folder is a file"])
def test_a_file_that_cannot_be_read_is_a_migration_error(company, tmp_path, problem):
    """step-reviewer finding 2: every failure is an AddonMigrationError, so the caller can say so."""
    if problem == "not utf-8":
        folder = migrations(tmp_path, {})
        (folder / "demo_001.sql").write_bytes("CREATE TABLE demo_café (x);\n".encode("cp1252"))
    else:
        folder = tmp_path / "migrations"
        folder.write_text("not a folder", encoding="utf-8")
    before = objects(company)
    with pytest.raises(database.AddonMigrationError):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before
