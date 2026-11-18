"""Add-on audit and the small STOP B gaps (Phase 2.7 step B2; HA9, owner 2026-11-17).

* HA9: every `<key>_` table gets the standard audit triggers (insert, update, delete; every column as JSON), made by
  the add-on migration runner from migrations/addon_audit_triggers.sql, after each statement, so a migration's own
  seed rows are logged too. An add-on's SQL cannot make, change or drop an `audit_*` object. A handler's writes and
  the migration's rows are logged with the acting user; `addon_schema_version` is audit-logged by the baseline.
* A handler raising SystemExit fails like any other error (AddonError, the usual sentence); KeyboardInterrupt still
  propagates. The posting rolls back either way.
* hooks.fire refused for an Agent writes a denial row (after the caller's transaction rolls back).
"""
import json
import sqlite3

import pytest

import modules.database as database
from modules.services import addons, hooks, ledger
from modules.services.errors import AddonError, PermissionDeniedError
from modules.services.tx import write_transaction
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_addon_database import KEY, applied, company, migrations, objects  # noqa: F401
from tests.test_addons import admin, draft, journal, resources, setup, write_addon  # noqa: F401
from tests.test_ledger_posting import ctx_for, env, keyed  # noqa: F401  (fixtures and helpers)


def audit_rows(rows_of, table):
    return [(r["user_id"], r["action"], json.loads(r["old_value"]) if r["old_value"] else None,
             json.loads(r["new_value"]) if r["new_value"] else None)
            for r in rows_of(f"SELECT user_id, action, old_value, new_value FROM audit_log WHERE table_name = '{table}' "
                             "ORDER BY log_id")]


def company_rows(company):
    def rows(sql):
        conn = database.get_readonly_connection(company)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()
    return rows


def triggers(company, table):
    return sorted(r["name"] for r in company_rows(company)(
        f"SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = '{table}'"))


# --- the migration runner makes the audit triggers -----------------------------------------------------------------

def test_every_addon_table_gets_the_three_audit_triggers(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, label TEXT);\n"
                                                   "CREATE TABLE demo_b (n INTEGER);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    for table in ("demo_a", "demo_b"):
        assert triggers(company, table) == [f"audit_{table}_delete", f"audit_{table}_insert", f"audit_{table}_update"]


def test_a_migrations_own_rows_are_audit_logged_with_every_column(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, label TEXT);\n"
                                                   "INSERT INTO demo_a (label) VALUES ('seed');\n"
                                                   "UPDATE demo_a SET label = 'seed 2';\n"})
    database.apply_addon_migrations(company, KEY, folder)
    assert audit_rows(company_rows(company), "demo_a") == [
        (None, "Insert", None, {"a_id": 1, "label": "seed"}),
        (None, "Update", {"a_id": 1, "label": "seed"}, {"a_id": 1, "label": "seed 2"})]


def test_a_changed_table_gets_its_triggers_rebuilt(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY);\n",
                                   "demo_002.sql": "ALTER TABLE demo_a ADD COLUMN note TEXT;\n"
                                                   "INSERT INTO demo_a (note) VALUES ('x');\n"
                                                   "ALTER TABLE demo_a RENAME TO demo_c;\n"
                                                   "DELETE FROM demo_c;\n"})
    database.apply_addon_migrations(company, KEY, folder)
    assert triggers(company, "demo_c") == ["audit_demo_c_delete", "audit_demo_c_insert", "audit_demo_c_update"]
    assert [(a, old, new) for _, a, old, new in audit_rows(company_rows(company), "demo_a")] == [
        ("Insert", None, {"a_id": 1, "note": "x"})]
    assert [(a, old) for _, a, old, _ in audit_rows(company_rows(company), "demo_c")] == [
        ("Delete", {"a_id": 1, "note": "x"})]


def test_a_wide_table_is_logged_whole(company, tmp_path):
    columns = ", ".join(f"c{i} INTEGER" for i in range(150))
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_w ({columns});\n"
                                                   "INSERT INTO demo_w (c0, c149) VALUES (1, 2);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    (_, _, _, new), = audit_rows(company_rows(company), "demo_w")
    assert len(new) == 150 and new["c0"] == 1 and new["c149"] == 2 and new["c75"] is None


@pytest.mark.parametrize("script, match", [
    ("CREATE TABLE demo_a (x);\nCREATE TRIGGER audit_demo_a_insert AFTER INSERT ON demo_a BEGIN SELECT 1; END;",
     "audit_demo_a_insert"),
    ("CREATE TABLE demo_a (x);\nCREATE TRIGGER audit_demo_b_insert AFTER INSERT ON demo_a BEGIN SELECT 1; END;",
     "outside"),
    ("CREATE TABLE demo_a (k TEXT PRIMARY KEY) WITHOUT ROWID;", "ROWID"),
    ("CREATE TABLE demo_a (\"it's\" TEXT);", "column"),
])
def test_an_addon_cannot_make_or_dodge_its_audit_triggers(company, tmp_path, script, match):
    folder = migrations(tmp_path, {"demo_001.sql": script + "\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=match):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before and applied(company) == []


def test_dropping_an_audit_trigger_does_not_stop_the_audit(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\nDROP TRIGGER audit_demo_a_insert;\n"
                                                   "INSERT INTO demo_a (x) VALUES (7);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    assert triggers(company, "demo_a") == ["audit_demo_a_delete", "audit_demo_a_insert", "audit_demo_a_update"]
    assert [new for _, _, _, new in audit_rows(company_rows(company), "demo_a")] == [{"x": 7}]


def test_dropping_an_addon_table_drops_its_audit_triggers(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n", "demo_002.sql": "DROP TABLE demo_a;\n"})
    database.apply_addon_migrations(company, KEY, folder)
    assert triggers(company, "demo_a") == []


@pytest.mark.parametrize("script, match", [
    ("CREATE TABLE demo_src (v TEXT);\nCREATE TABLE demo_copy AS SELECT s.v || 'x' FROM demo_src AS s;", "column"),
    ('CREATE TABLE "demo_x_insert BEFORE INSERT ON demo_c BEGIN SELECT 1; END /*" (x);', "table name"),
    ('CREATE TABLE "demo_a b" (x);', "table name"),
    ('CREATE TABLE demo_a ("x y" TEXT);', "column"),
])
def test_addon_names_are_plain_letters_digits_and_underscores(company, tmp_path, script, match):
    """step-reviewer finding 2: no name reaches the generated trigger SQL unless it is a plain identifier."""
    folder = migrations(tmp_path, {"demo_001.sql": script + "\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=match):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before


def test_a_counter_row_renamed_away_from_audit_log_is_refused(company, tmp_path):
    """step-reviewer finding 5: an add-on counter row must belong to an add-on table that exists."""
    raw = sqlite3.connect(company)
    raw.execute("INSERT INTO audit_log (table_name, record_id, action) VALUES ('x', 1, 'Insert')")   # seq = max
    raw.commit()
    raw.close()
    folder = migrations(tmp_path, {"demo_001.sql": "UPDATE sqlite_sequence SET name = 'demo_zz' WHERE name = 'audit_log';\n"})
    with pytest.raises(database.AddonMigrationError, match="counter"):
        database.apply_addon_migrations(company, KEY, folder)


@pytest.mark.parametrize("script", [
    "UPDATE sqlite_sequence SET name = 'demo_x' WHERE name = 'journal_entry';",
    "UPDATE sqlite_sequence SET seq = 0 WHERE name = 'journal_entry';",
    "DELETE FROM sqlite_sequence WHERE name = 'journal_entry';",
])
def test_a_migration_cannot_touch_a_core_autoincrement_counter(company, tmp_path, script):
    raw = sqlite3.connect(company)
    raw.execute("INSERT INTO sqlite_sequence (name, seq) SELECT 'journal_entry', 5 "
                "WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'journal_entry')")
    raw.commit()
    raw.close()
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n" + script + "\n"})
    with pytest.raises(database.AddonMigrationError):
        database.apply_addon_migrations(company, KEY, folder)
    assert applied(company) == []


def test_an_autoincrement_addon_table_can_be_renamed(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (id INTEGER PRIMARY KEY AUTOINCREMENT, x);\n"
                                                   "INSERT INTO demo_a (x) VALUES (1);\n"
                                                   "ALTER TABLE demo_a RENAME TO demo_b;\n"})
    assert database.apply_addon_migrations(company, KEY, folder) == [1]


def test_the_template_is_read_from_the_migrations_folder():
    text = open(f"{database.MIGRATIONS_DIR}/addon_audit_triggers.sql", encoding="utf-8").read()
    assert text.count("CREATE TRIGGER") == 3 and "__TABLE__" in text


# --- the user is named; addon_schema_version is logged -------------------------------------------------------------

def test_enable_logs_the_migration_rows_and_its_version_row_with_the_user(setup, resources):
    write_addon(resources, "seed", code="def register(hooks):\n    pass\n", files={
        "seed_001.sql": "CREATE TABLE seed_x (x_id INTEGER PRIMARY KEY, label TEXT);\n"
                        "INSERT INTO seed_x (label) VALUES ('first');\n"})
    addons.enable(admin(setup), "seed")
    assert audit_rows(lambda sql: setup.rows("PARENT", sql), "seed_x") == [
        (setup.admin, "Insert", None, {"x_id": 1, "label": "first"})]
    (user, action, _, new), = audit_rows(lambda sql: setup.rows("PARENT", sql), "addon_schema_version")
    assert (user, action, new["addon_key"], new["version"]) == (setup.admin, "Insert", "seed", 1)


def test_a_handlers_writes_are_audit_logged_with_the_user(setup):
    addons.enable(admin(setup), "demo")
    entry_id = draft(setup)
    ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    rows = audit_rows(lambda sql: setup.rows("PARENT", sql), "demo_seen")
    assert [(user, action, new["event"], new["entry_id"]) for user, action, _, new in rows] == [
        (setup.user_id, "Insert", "entry.posted", entry_id)]


def test_a_handler_still_cannot_write_or_read_the_audit_tables(setup, resources):
    write_addon(resources, "snoop", code='''
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            rows = db.execute("SELECT user_id, terminal_id FROM audit_context")
            db.execute("INSERT INTO snoop_seen (user_id, terminal_id) VALUES (?, ?)",
                       (rows[0]["user_id"], rows[0]["terminal_id"]))
            db.execute("INSERT INTO audit_log (table_name, record_id, action) VALUES ('x', 1, 'Insert')")
        ''', files={"snoop_001.sql": "CREATE TABLE snoop_seen (user_id INTEGER, terminal_id TEXT);\n"})
    addons.enable(admin(setup), "snoop")
    with pytest.raises(AddonError):
        ledger.post_journal_entry(ctx_for(setup), draft(setup), confirm=True)


def test_a_handler_reads_the_audit_context_as_null(setup, resources):
    write_addon(resources, "snoop", code='''
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            rows = db.execute("SELECT user_id, terminal_id FROM audit_context")
            db.execute("INSERT INTO snoop_seen (user_id, terminal_id) VALUES (?, ?)",
                       (rows[0]["user_id"], rows[0]["terminal_id"]))
        ''', files={"snoop_001.sql": "CREATE TABLE snoop_seen (user_id INTEGER, terminal_id TEXT);\n"})
    addons.enable(admin(setup), "snoop")
    ledger.post_journal_entry(ctx_for(setup), draft(setup), confirm=True)
    assert setup.rows("PARENT", "SELECT user_id, terminal_id FROM snoop_seen") == [
        {"user_id": None, "terminal_id": None}]
    (user, _, _, new), = audit_rows(lambda sql: setup.rows("PARENT", sql), "snoop_seen")
    assert user == setup.user_id and new == {"user_id": None, "terminal_id": None}


# --- small gaps --------------------------------------------------------------------------------------------------

def _raising(resources, key, statement):
    write_addon(resources, key, code=f'''
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            db.execute("INSERT INTO {key}_n (n) VALUES (1)")
            {statement}
        ''', files={f"{key}_001.sql": f"CREATE TABLE {key}_n (n INTEGER);\n"})


def test_a_handler_raising_systemexit_fails_like_any_error(setup, resources):
    _raising(resources, "quit", "raise SystemExit(3)")
    addons.enable(admin(setup), "quit")
    entry_id = draft(setup)
    before = journal(setup)
    with pytest.raises(AddonError, match="The Quit Notes add-on could not finish, so nothing was saved"):
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert journal(setup) == before and setup.rows("PARENT", "SELECT * FROM quit_n") == []


def test_keyboard_interrupt_still_propagates_and_rolls_back(setup, resources):
    _raising(resources, "stop", "raise KeyboardInterrupt")
    addons.enable(admin(setup), "stop")
    entry_id = draft(setup)
    before = journal(setup)
    with pytest.raises(KeyboardInterrupt):
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert journal(setup) == before and setup.rows("PARENT", "SELECT * FROM stop_n") == []


def test_fire_refused_for_an_agent_writes_a_denial_row(setup):
    addons.enable(admin(setup), "demo")
    agent = ctx_for(setup, "Agent")
    events = len(setup.events("PARENT"))
    with pytest.raises(PermissionDeniedError, match="agent"):
        with write_transaction(agent.company_db_path, ctx_for(setup)) as conn:
            conn.execute("INSERT INTO demo_seen (event) VALUES ('before')")
            hooks.fire(conn, agent, "entry.posted", {"entry_id": 1})
    written = setup.events("PARENT")[events:]
    assert [(e["event_type"], e["actor_type"], e["origin"], e["record_type"]) for e in written] == [
        ("Denied", "Agent", "Agent", "addon_hook")]
    assert setup.rows("PARENT", "SELECT * FROM demo_seen") == []                     # rolled back


def test_the_agent_refusal_outside_a_transaction_helper_is_still_refused(setup):
    agent = ctx_for(setup, "Agent")
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(PermissionDeniedError):
            hooks.fire(conn, agent, "entry.posted", {})
    finally:
        conn.close()


def test_a_failure_while_logging_the_denial_does_not_hide_the_refusal(setup, monkeypatch, caplog):
    """step-reviewer finding 6."""
    from modules.services import authz

    def broken(*args, **kwargs):
        raise RuntimeError("log store gone")
    monkeypatch.setattr(authz, "record_denial", broken)
    agent = ctx_for(setup, "Agent")
    with pytest.raises(PermissionDeniedError, match="agent"):
        with write_transaction(agent.company_db_path, ctx_for(setup)) as conn:
            hooks.fire(conn, agent, "entry.posted", {"entry_id": 1})
    assert "denial" in caplog.text


def test_a_failed_company_creation_leaves_no_wal_files(tmp_path):
    """Secrets audit L2: the clean-up after a failed create removes the WAL sidecars too."""
    from modules.services import companies
    path = tmp_path / "x.tmp-1.db"
    for suffix in ("", "-journal", "-wal", "-shm"):
        (tmp_path / (path.name + suffix)).write_bytes(b"pages")
    companies._remove_quietly(str(path))
    assert list(tmp_path.iterdir()) == []

