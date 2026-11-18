"""Tests added after the STOP B mutation check (HEAD 9b2f1f1): each one fails when one surviving mutant is in place.

The mutant ids (D = database.py, H = hooks.py, A = addons.py, L = ledger.py, U = users.py, P = payments.py,
S = storage.py) are the mutation-tester's; the report is summarised in docs/status_log.md (2026-11-17).
"""
import dataclasses
import json
import logging
import sqlite3

import pytest

import config
import modules.database as database
from modules.services import addons, companies, hooks, ledger, payments, storage, users
from modules.services.errors import AddonError, PermissionDeniedError, ValidationError
from modules.services.tx import write_transaction
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_addon_database import KEY, applied, conn, company, migrations, objects  # noqa: F401
from tests.test_addons import DEMO_001, admin, draft, post, resources, seen, setup, write_addon  # noqa: F401
from tests.test_ledger_posting import ctx_for, env, keyed  # noqa: F401  (fixtures and helpers)
from tests.test_payments import allocate, document, pay, payment  # noqa: F401
from tests.test_users_access import _role_rows, org  # noqa: F401


# --- database.py: keys, the handler guard, the migration runner -------------------------------------------------------

def test_the_schema_guard_tables_are_core():                                                        # D8
    for name in ("schema_version", "schema_baseline"):
        assert name in database.core_table_names()
    with pytest.raises(database.AddonKeyError):
        database.check_addon_key("schema")


@pytest.mark.parametrize("sql", [
    "CREATE TABLE demo_x (y)",
    "ALTER TABLE demo_note ADD COLUMN y TEXT",
    "DROP TABLE demo_note",
    "CREATE INDEX demo_ix ON demo_note (text)",
    "CREATE TRIGGER demo_tr AFTER INSERT ON demo_note BEGIN SELECT 1; END",
])
def test_a_handler_cannot_change_even_its_own_schema(conn, sql):                                    # D35
    """D35 is equivalent (any schema change also writes sqlite_master, refused outside schema mode); this pins it."""
    with database.addon_write_guard(conn, KEY) as guard:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)
    assert guard.refused
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'demo_note'").fetchone() is not None


TRIGGER = "CREATE TABLE demo_ok (x);\nCREATE TRIGGER demo_tr AFTER INSERT ON demo_ok BEGIN {body} END;"


@pytest.mark.parametrize("script", [
    "ANALYZE;",                                                                                     # D43
    TRIGGER.format(body="REPLACE INTO journal_line (line_id) VALUES (1);"),                         # D55
    TRIGGER.format(body="DELETE FROM journal_line;"),                                               # D56
    TRIGGER.format(body="INSERT OR IGNORE INTO company_addon (addon_key, enabled) VALUES ('x', 1);"),  # D57
    TRIGGER.format(body="UPDATE OR ABORT journal_entry SET description = 'x';"),                    # D58
    TRIGGER.format(body='UPDATE "journal_entry" SET description = \'x\';'),                         # D59
    TRIGGER.format(body="update journal_entry set description = 'x';"),                            # D60
])
def test_more_refused_scripts_change_nothing(company, tmp_path, script):
    folder = migrations(tmp_path, {"demo_001.sql": script + "\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before and applied(company) == []


@pytest.mark.parametrize("body", [
    "INSERT INTO demo_log (t) VALUES ('INSERT INTO journal_entry');",                               # D71
    "INSERT INTO demo_log (t) VALUES ('x'); -- UPDATE journal_entry SET description = 'x'\n",      # D74
    "/* DELETE FROM journal_line;\n UPDATE journal_entry SET description = 'x'; */ "
    "INSERT INTO demo_log (t) VALUES ('x');",                                                       # D75
])
def test_strings_and_comments_in_a_trigger_body_are_not_writes(company, tmp_path, body):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_log (t TEXT);\n"
                                                   + TRIGGER.format(body=body) + "\n"})
    assert database.apply_addon_migrations(company, KEY, folder) == [1]


@pytest.mark.parametrize("name", ["demo_01.sql", "demo_002.SQL", "demo_002.sql.sql"])           # D61, D63, D64
def test_a_migration_name_must_be_exact(company, tmp_path, name):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n", name: "CREATE TABLE demo_b (x);\n"})
    with pytest.raises(database.AddonMigrationError, match="named"):
        database.apply_addon_migrations(company, KEY, folder)
    assert applied(company) == []


def test_an_addon_table_with_its_own_unique_index_is_accepted(company, tmp_path):                  # D79
    """Found by this test: the guard refused SQLite's own sqlite_autoindex_demo_u_N, so UNIQUE could not be used."""
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_u (code TEXT PRIMARY KEY, n TEXT UNIQUE);\n"})
    assert database.apply_addon_migrations(company, KEY, folder) == [1]
    (folder / "demo_002.sql").write_text("DROP TABLE demo_u;\n", encoding="utf-8")
    assert database.apply_addon_migrations(company, KEY, folder) == [2]


def test_an_automatic_index_on_a_core_table_is_still_refused(conn):
    guard = database._AddonGuard(KEY, schema=True)
    assert guard(sqlite3.SQLITE_CREATE_INDEX, "sqlite_autoindex_journal_entry_9", "journal_entry", "main",
                 None) == sqlite3.SQLITE_DENY
    assert guard(sqlite3.SQLITE_CREATE_INDEX, "sqlite_autoindex_demo_u_1", "demo_u", "main",
                 None) == sqlite3.SQLITE_OK
    assert guard(sqlite3.SQLITE_CREATE_INDEX, "ledger_ix", "demo_u", "main", None) == sqlite3.SQLITE_DENY
    assert database._AddonGuard(KEY, schema=False)(sqlite3.SQLITE_CREATE_INDEX, "sqlite_autoindex_demo_u_1",
                                                    "demo_u", "main", None) == sqlite3.SQLITE_DENY


def test_a_stale_baseline_is_refused_before_any_addon_migration(company, tmp_path):                 # D90
    raw = sqlite3.connect(company)
    try:
        raw.execute("UPDATE schema_baseline SET sha256 = ?", ("0" * 64,))
        raw.commit()
    finally:
        raw.close()
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n"})
    with pytest.raises(database.SchemaUpgradeBlockedError):
        database.apply_addon_migrations(company, KEY, folder)
    raw = sqlite3.connect(company)
    try:
        assert raw.execute("SELECT name FROM sqlite_master WHERE name = 'demo_a'").fetchall() == []
    finally:
        raw.close()


def test_a_failed_backup_is_a_migration_error(company, tmp_path, monkeypatch):                      # D91
    def no_backup(db_path):
        raise OSError("disk full")
    monkeypatch.setattr(database, "_backup_database", no_backup)
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match="backup"):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before


def test_a_gap_in_the_applied_history_is_refused(company, tmp_path):                                # D96, D97
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n",
                                   "demo_002.sql": "CREATE TABLE demo_b (x);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    raw = sqlite3.connect(company)
    try:
        raw.execute("DELETE FROM addon_schema_version WHERE addon_key = ? AND version = 1", (KEY,))
        raw.commit()
    finally:
        raw.close()
    (folder / "demo_003.sql").write_text("CREATE TABLE demo_c (x);\n", encoding="utf-8")
    with pytest.raises(database.AddonMigrationError, match="gap"):
        database.apply_addon_migrations(company, KEY, folder)


def test_a_result_that_breaks_a_foreign_key_is_refused(company, tmp_path):                         # D104
    folder = migrations(tmp_path, {"demo_001.sql": (
        "CREATE TABLE demo_p (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE demo_c (p INTEGER REFERENCES demo_p(id) DEFERRABLE INITIALLY DEFERRED);\n"
        "INSERT INTO demo_c (p) VALUES (5);\n")})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before and applied(company) == []


# --- hooks.py ---------------------------------------------------------------------------------------------------------

def test_two_handlers_for_one_event_both_run(setup, resources):                                     # H7
    write_addon(resources, "twin", code='''
        def register(hooks):
            hooks.on("entry.posted", first)
            hooks.on("entry.posted", second)

        def first(db, payload):
            db.execute("INSERT INTO twin_n (n) VALUES (1)")

        def second(db, payload):
            db.execute("INSERT INTO twin_n (n) VALUES (2)")
        ''', files={"twin_001.sql": "CREATE TABLE twin_n (n INTEGER);\n"})
    addons.enable(admin(setup), "twin")
    post(setup)
    assert setup.rows("PARENT", "SELECT n FROM twin_n ORDER BY rowid") == [{"n": 1}, {"n": 2}]


def test_the_log_says_where_the_error_was_raised_but_not_its_message():                             # H12
    def explode():
        raise RuntimeError("card 4111")
    try:
        explode()
    except RuntimeError as error:
        text = hooks.describe_error(error)
    assert text.startswith("RuntimeError at ")
    assert "test_mutation_stop_b_extra.py:" in text and "in explode" in text
    assert "4111" not in text


def test_a_handle_kept_by_one_handler_is_closed_for_the_next(setup, resources):                      # H15, H17, H36
    write_addon(resources, "keep", code='''
        KEPT = []

        def register(hooks):
            hooks.on("entry.posted", first)
            hooks.on("entry.posted", second)

        def first(db, payload):
            KEPT.append(db)

        def second(db, payload):
            try:
                KEPT[-1].execute("INSERT INTO keep_n (state) VALUES ('open')")
            except RuntimeError:
                db.execute("INSERT INTO keep_n (state) VALUES ('closed')")
        ''', files={"keep_001.sql": "CREATE TABLE keep_n (state TEXT);\n"})
    addons.enable(admin(setup), "keep")
    post(setup)
    assert setup.rows("PARENT", "SELECT state FROM keep_n") == [{"state": "closed"}]


def test_addons_run_in_key_order(setup, resources):                                                 # H21
    for key, other in (("zeta", "alpha"), ("alpha", "zeta")):
        write_addon(resources, key, code=f'''
            def register(hooks):
                hooks.on("entry.posted", handler)

            def handler(db, payload):
                try:
                    n = db.execute("SELECT count(*) AS n FROM {other}_seen")[0]["n"]
                except Exception:
                    n = -1
                db.execute("INSERT INTO {key}_seen (n) VALUES (?)", (n,))
            ''', files={f"{key}_001.sql": f"CREATE TABLE {key}_seen (n INTEGER);\n"})
    addons.enable(admin(setup), "zeta")                     # enabled first, runs second
    addons.enable(admin(setup), "alpha")
    post(setup)
    assert setup.rows("PARENT", "SELECT n FROM alpha_seen") == [{"n": 0}]
    assert setup.rows("PARENT", "SELECT n FROM zeta_seen") == [{"n": 1}]


PEEK = '''
    def register(hooks):
        hooks.on("entry.posted", posted)
        hooks.on("entry.voided", voided)

    def posted(db, payload):
        import json
        db.execute("INSERT INTO peek_seen (body) VALUES (?)", (json.dumps(dict(payload)),))

    def voided(db, payload):
        import json
        db.execute("INSERT INTO peek_seen (body) VALUES (?)", (json.dumps(dict(payload)),))
    '''


def peeked(env):
    return [json.loads(r["body"]) for r in env.rows("PARENT", "SELECT body FROM peek_seen ORDER BY rowid")]


def test_a_caller_payload_cannot_override_the_context_fields(setup, resources):                    # H31
    write_addon(resources, "peek", code=PEEK, files={"peek_001.sql": "CREATE TABLE peek_seen (body TEXT);\n"})
    addons.enable(admin(setup), "peek")
    context = ctx_for(setup)
    with write_transaction(context.company_db_path, context) as conn:
        hooks.fire(conn, context, "entry.posted", {"entry_id": 1, "event": "entry.voided", "company_id": 999,
                                                   "user_id": 999, "now": "2000-01-01T00:00:00+00:00"})
    body = peeked(setup)[0]
    assert (body["event"], body["company_id"], body["user_id"], body["now"]) == (
        "entry.posted", context.company_id, context.user_id, context.now)


def test_the_void_payloads_in_full(setup, resources):                                               # L1, L5, L9, L10, L12
    write_addon(resources, "peek", code=PEEK, files={"peek_001.sql": "CREATE TABLE peek_seen (body TEXT);\n"})
    addons.enable(admin(setup), "peek")
    draft(setup)                                            # an unposted draft, so entry ids and numbers differ
    entry_id, posted = post(setup)
    void = ledger.void_entry(ctx_for(setup), entry_id, note="wrong", confirm=True)
    total = setup.rows("PARENT", "SELECT SUM(debit_cents) AS d FROM journal_line WHERE entry_id = ?",
                       (entry_id,))[0]["d"]
    first, second, third = peeked(setup)
    assert first["debit_cents"] == total and first["reversal_reason"] is None
    void_date = setup.rows("PARENT", "SELECT entry_date FROM journal_entry WHERE entry_id = ?",
                           (void["entry_id"],))[0]["entry_date"]
    assert {k: second[k] for k in ("event", "entry_id", "entry_number", "reverses_entry_id", "reversal_reason",
                                   "debit_cents", "entry_date")} == {
        "event": "entry.posted", "entry_id": void["entry_id"], "entry_number": void["entry_number"],
        "reverses_entry_id": entry_id, "reversal_reason": "Void", "debit_cents": total, "entry_date": void_date}
    assert {k: third[k] for k in ("event", "entry_id", "void_entry_id", "void_entry_number", "entry_date")} == {
        "event": "entry.voided", "entry_id": entry_id, "void_entry_id": void["entry_id"],
        "void_entry_number": void["entry_number"], "entry_date": void_date}
    assert void["entry_number"] != void["entry_id"] and posted["entry_number"] != entry_id


# --- addons.py --------------------------------------------------------------------------------------------------------

def _break_and_open(setup, resources):
    addons.enable(admin(setup), "demo")
    path = resources / "addons" / "demo" / "migrations" / "demo_001.sql"
    path.write_text(DEMO_001 + "-- edited\n", encoding="utf-8")
    hooks._clear()
    companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    with pytest.raises(AddonError, match="could not set up its tables"):
        post(setup)
    path.write_text(DEMO_001, encoding="utf-8")


def test_a_fixed_addon_works_again_after_the_next_open(setup, resources):                           # H14, A48
    _break_and_open(setup, resources)
    companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    entry_id, result = post(setup)
    assert seen(setup)[-1] == ("entry.posted", entry_id, result["entry_number"])


def test_a_fixed_addon_works_again_after_enable(setup, resources):                                  # A34
    _break_and_open(setup, resources)
    addons.enable(admin(setup), "demo")
    entry_id, result = post(setup)
    assert seen(setup)[-1] == ("entry.posted", entry_id, result["entry_number"])


@pytest.mark.parametrize("manifest", [123, None, ["demo"], "demo"])                                 # A8
def test_a_manifest_that_is_not_an_object_is_skipped(setup, resources, caplog, manifest):
    (resources / "addons" / "demo" / "addon.json").write_text(json.dumps(manifest), encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert addons.discover() == {}
    assert "demo" in caplog.text


@pytest.mark.parametrize("field, value", [("name", 5), ("name", "  "), ("version", 2), ("version", "")])  # A11, A12
def test_a_manifest_name_and_version_are_non_blank_text(setup, resources, caplog, field, value):
    manifest = {"key": "demo", "name": "Demo", "version": "1.0", field: value}
    (resources / "addons" / "demo" / "addon.json").write_text(json.dumps(manifest), encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert addons.discover() == {}


def test_a_folder_without_addon_py_is_not_listed(setup, resources):                                  # A13
    (resources / "addons" / "demo" / "addon.py").unlink()
    assert "demo" not in addons.discover()
    assert addons.list_addons(admin(setup)) == []


def test_the_manifest_name_and_version_are_trimmed(setup, resources):                                # A14, A15
    (resources / "addons" / "demo" / "addon.json").write_text(json.dumps(
        {"key": "demo", "name": "  Demo Notes ", "version": " 1.2 "}), encoding="utf-8")
    info = addons.discover()["demo"]
    assert (info["name"], info["version"]) == ("Demo Notes", "1.2")


def test_list_shows_a_disabled_addon_as_off(setup):                                                  # A25
    addons.enable(admin(setup), "demo")
    addons.disable(admin(setup), "demo")
    (row,) = addons.list_addons(admin(setup))
    assert row["enabled"] is False and row["installed"] is True


def test_enable_in_a_read_only_company_changes_nothing(setup):                                       # A31
    with pytest.raises(PermissionDeniedError, match="read-only"):
        addons.enable(dataclasses.replace(admin(setup), read_only=True), "demo")
    assert setup.rows("PARENT", "SELECT * FROM addon_schema_version") == []
    assert setup.rows("PARENT", "SELECT name FROM sqlite_master WHERE name = 'demo_seen'") == []


def test_enable_again_turns_it_back_on_with_the_new_version(setup, resources):                       # A36, A37
    addons.enable(admin(setup), "demo")
    addons.disable(admin(setup), "demo")
    (resources / "addons" / "demo" / "addon.json").write_text(json.dumps(
        {"key": "demo", "name": "Demo Notes", "version": "2.0"}), encoding="utf-8")
    addons.enable(admin(setup), "demo")
    assert setup.rows("PARENT", "SELECT enabled, addon_version FROM company_addon") == [
        {"enabled": 1, "addon_version": "2.0"}]


def test_company_open_leaves_a_disabled_addon_alone(setup, resources):                               # A43
    addons.enable(admin(setup), "demo")
    addons.disable(admin(setup), "demo")
    write_addon(resources, "demo", name="Demo Notes", files={
        "demo_001.sql": DEMO_001, "demo_002.sql": "CREATE TABLE demo_more (x);\n"})
    hooks._clear()
    companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    assert [r["version"] for r in setup.rows("PARENT", "SELECT version FROM addon_schema_version")] == [1]
    assert not hooks.is_loaded("demo")


def test_company_open_survives_an_addon_whose_code_fails_to_import(setup, resources, caplog):         # A49
    addons.enable(admin(setup), "demo")
    (resources / "addons" / "demo" / "addon.py").write_text("raise ImportError('nope')\n", encoding="utf-8")
    hooks._clear()
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    assert not hooks.is_loaded("demo")


# --- users.py (MR8) ---------------------------------------------------------------------------------------------------

def test_the_same_role_in_another_company_is_kept(world, org):                                       # U4
    world.grant(org["staff"], "OTHER", "Viewer")
    world.add_roles(org["staff"], "OTHER", "Viewer")
    world.add_roles(org["staff"], "PARENT", "Viewer", "Broad")
    users.grant_access(org["s"]("master"), org["staff"], org["cid"]("PARENT"), "UserMgr", confirm_removal=True)
    assert _role_rows(world, org["staff"], org["cid"]("OTHER")) == ["Viewer"]
    users.deny_access(org["s"]("master"), org["staff"], org["cid"]("PARENT"))
    assert _role_rows(world, org["staff"], org["cid"]("OTHER")) == ["Viewer"]


@pytest.mark.parametrize("flag", [1, "yes", "True"])                                                 # U7
def test_only_true_confirms_a_removal(world, org, flag):
    world.add_roles(org["staff"], "PARENT", "Broad")
    with pytest.raises(users.ConfirmationRequiredError):
        users.set_role(org["s"]("master"), org["staff"], org["cid"]("PARENT"), "Viewer", confirm_removal=flag)
    assert _role_rows(world, org["staff"], org["cid"]("PARENT")) == ["Broad"]


@pytest.mark.parametrize("service", ["grant_access", "set_role"])                                    # U13, U14
def test_the_last_admin_sentence_comes_before_the_confirmation(world, org, service):
    world.add_roles(org["admin"], "PARENT", "Admin", "Broad")
    with pytest.raises(ValidationError, match="without an Admin") as refused:
        getattr(users, service)(org["s"]("master"), org["admin"], org["cid"]("PARENT"), "Viewer")
    assert not isinstance(refused.value, users.ConfirmationRequiredError)


def test_grant_keeps_the_row_of_the_role_being_granted(world, org):                                  # U16
    world.add_roles(org["staff"], "PARENT", "Viewer", "Broad")
    result = users.grant_access(org["s"]("master"), org["staff"], org["cid"]("PARENT"), "Viewer",
                                confirm_removal=True)
    assert result == {"removed_roles": ["Broad"]}
    assert _role_rows(world, org["staff"], org["cid"]("PARENT")) == ["Viewer"]


# --- payments.py (MR9) ------------------------------------------------------------------------------------------------

def test_the_one_side_sentences_exactly():                                                            # P14
    assert payments.ONE_SIDE_ONLY == {
        "payment.receive": "Choose a customer payment or credit memo; your role cannot apply vendor payments or "
                           "credits, so ask an Admin if you need to.",
        "payment.make": "Choose a vendor payment or credit; your role cannot apply customer payments or credit "
                        "memos, so ask an Admin if you need to.",
    }


@pytest.mark.parametrize("target", ["memo", "malformed"])                                            # P11, P12
def test_a_one_side_holder_gets_the_one_side_sentence_for_a_target_that_is_no_invoice(pay, target):
    source = payment(pay, posted=False)
    ref = ("invoice", document(pay, "credit_memo")) if target == "memo" else ("payment", 1)
    pay.remove_permission("PARENT", "POSTER", "payment.make")
    with pytest.raises(PermissionDeniedError) as denied:
        allocate(pay, ("payment", source), ref, 100)
    assert str(denied.value) == payments.ONE_SIDE_ONLY["payment.receive"]


# --- storage.py -------------------------------------------------------------------------------------------------------

def test_list_resource_dirs(tmp_path, monkeypatch):                                                  # S2, S3, S5
    monkeypatch.setattr(config, "RESOURCE_DIR", str(tmp_path))
    for name in ("zeta", "alpha", "mid"):
        (tmp_path / "addons" / name).mkdir(parents=True)
    (tmp_path / "addons" / "beta.txt").write_text("x", encoding="utf-8")
    assert storage.list_resource_dirs("addons") == ["alpha", "mid", "zeta"]
    assert storage.list_resource_dirs("missing") == []
