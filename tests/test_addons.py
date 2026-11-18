"""Hooks and add-ons, Phase 2.7 STOP B (decisions HA1-HA6).

* hooks (HA1, HA2): `entry.posted` and `entry.voided` fire from the ledger inside the posting transaction;
  `stage.entered` and `stage.left` are declared only. Only enabled add-ons' handlers run, never for an Agent
  context. A handler writes only its own `<key>_` tables; any handler error rolls the caller back with one sentence
  that names the add-on and the next step.
* addons (HA3, HA5): add-ons are discovered and imported only from RESOURCE_DIR/addons, never DATA_DIR. list,
  enable and disable need addon.manage (Admin and the Master). enable runs the add-on's migrations; disabling stops
  its hooks and drops nothing. Company open applies pending migrations of enabled add-ons.
"""
import ast
import json
import logging
import re
import textwrap
from pathlib import Path

import pytest

import config
from modules.services import addons, companies, hooks, ledger
from modules.services.errors import AddonError, NotFoundError, PermissionDeniedError, ValidationError
from modules.services.tx import write_transaction
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_posting import A, ctx_for, draft, env, keyed  # noqa: F401  (fixtures and helpers)

ROOT = Path(__file__).resolve().parent.parent

DEMO_HANDLERS = '''
def register(hooks):
    hooks.on("entry.posted", on_posted)
    hooks.on("entry.voided", on_voided)


def on_posted(db, payload):
    db.execute("INSERT INTO demo_seen (event, entry_id, entry_number) VALUES (?, ?, ?)",
               (payload["event"], payload["entry_id"], payload["entry_number"]))


def on_voided(db, payload):
    db.execute("INSERT INTO demo_seen (event, entry_id, entry_number) VALUES (?, ?, ?)",
               (payload["event"], payload["entry_id"], payload["void_entry_id"]))
'''
DEMO_001 = "CREATE TABLE demo_seen (seen_id INTEGER PRIMARY KEY, event TEXT NOT NULL, entry_id INTEGER, " \
           "entry_number INTEGER);\n"


def write_addon(root, key, *, name=None, code=DEMO_HANDLERS, files=None, manifest=None):
    folder = Path(root) / "addons" / key
    (folder / "migrations").mkdir(parents=True, exist_ok=True)
    (folder / "addon.json").write_text(json.dumps(manifest if manifest is not None else {
        "key": key, "name": name or f"{key.title()} Notes", "version": "1.0"}), encoding="utf-8")
    (folder / "addon.py").write_text(textwrap.dedent(code), encoding="utf-8")
    for filename, text in (files if files is not None else {f"{key}_001.sql": DEMO_001}).items():
        (folder / "migrations" / filename).write_text(text, encoding="utf-8")
    return folder


@pytest.fixture
def resources(tmp_path, monkeypatch):
    """RESOURCE_DIR and DATA_DIR are separate folders here, as in an installed copy."""
    resource_dir, data_dir = tmp_path / "res", tmp_path / "data"
    resource_dir.mkdir()
    data_dir.mkdir()
    monkeypatch.setattr(config, "RESOURCE_DIR", str(resource_dir))
    monkeypatch.setattr(config, "DATA_DIR", str(data_dir))
    hooks._clear()
    yield resource_dir
    hooks._clear()


@pytest.fixture
def setup(env, resources):
    """env (a POSTER who may post and reverse) plus an Admin and a Viewer, and the demo add-on installed."""
    env.grant_permission("PARENT", "POSTER", "je.reverse")
    env.admin = env.user("admin")
    env.grant(env.admin, "PARENT", "Admin")
    env.role("PARENT", "Viewer", ["ledger.view"])
    env.viewer = env.user("viewer")
    env.grant(env.viewer, "PARENT", "Viewer")
    write_addon(resources, "demo", name="Demo Notes")
    env.resources = resources
    return env


def admin(env, origin="Human"):
    return ctx_for(env, origin, user=env.admin)


def seen(env):
    return [(r["event"], r["entry_id"], r["entry_number"]) for r in env.rows(
        "PARENT", "SELECT event, entry_id, entry_number FROM demo_seen ORDER BY seen_id")]


def post(env, **kwargs):
    entry_id = draft(env, **kwargs)
    return entry_id, ledger.post_journal_entry(ctx_for(env), entry_id, confirm=True)


def journal(env):
    return env.rows("PARENT", "SELECT entry_id, is_posted, entry_number FROM journal_entry ORDER BY entry_id")


# --- hooks: events (HA1) ---------------------------------------------------------------------------------------------

def test_the_events():
    assert hooks.EVENTS == frozenset({"entry.posted", "entry.voided", "stage.entered", "stage.left"})
    ledger_source = (ROOT / "modules" / "services" / "ledger.py").read_text(encoding="utf-8")
    assert '"entry.posted"' in ledger_source and '"entry.voided"' in ledger_source
    for path in (ROOT / "modules").rglob("*.py"):              # declared only: nothing fires them yet
        if path.name != "hooks.py":
            source = path.read_text(encoding="utf-8")
            assert "stage.entered" not in source and "stage.left" not in source, path


def test_posting_fires_entry_posted_for_an_enabled_addon(setup):
    addons.enable(admin(setup), "demo")
    entry_id, result = post(setup)
    assert seen(setup) == [("entry.posted", entry_id, result["entry_number"])]


def test_an_addon_that_is_not_enabled_sees_nothing(setup):
    addons.load("demo")
    post(setup)
    assert setup.rows("PARENT", "SELECT name FROM sqlite_master WHERE name = 'demo_seen'") == []


def test_voiding_fires_entry_posted_for_the_void_and_entry_voided_for_the_original(setup):
    addons.enable(admin(setup), "demo")
    entry_id, posted = post(setup)
    void = ledger.void_entry(ctx_for(setup), entry_id, note="wrong", confirm=True)
    assert seen(setup) == [("entry.posted", entry_id, posted["entry_number"]),
                           ("entry.posted", void["entry_id"], void["entry_number"]),
                           ("entry.voided", entry_id, void["entry_id"])]


def test_an_accrual_and_its_automatic_reversal_each_fire(setup):
    addons.enable(admin(setup), "demo")
    entry_id, result = post(setup, auto_reverse_date="2026-04-01")
    assert seen(setup) == [("entry.posted", entry_id, result["entry_number"]),
                           ("entry.posted", result["reversal_entry_id"], result["reversal_entry_number"])]


def test_the_payload(setup, resources):
    write_addon(resources, "peek", code='''
        def register(hooks):
            hooks.on("entry.posted", look)

        def look(db, payload):
            import json
            try:
                payload["entry_id"] = 0
                writable = True
            except TypeError:
                writable = False
            db.execute("INSERT INTO peek_seen (body) VALUES (?)", (json.dumps(dict(payload, writable=writable)),))
        ''', files={"peek_001.sql": "CREATE TABLE peek_seen (body TEXT);\n"})
    addons.enable(admin(setup), "peek")
    entry_id, result = post(setup)
    body = json.loads(setup.rows("PARENT", "SELECT body FROM peek_seen")[0]["body"])
    assert body == {"event": "entry.posted", "entry_id": entry_id, "entry_number": result["entry_number"],
                    "entry_date": "2026-03-15", "source": None, "origin": "Human", "reverses_entry_id": None,
                    "reversal_reason": None, "debit_cents": body["debit_cents"], "company_id": setup.company_id(
                        "PARENT"), "user_id": setup.user_id, "now": ctx_for(setup).now, "writable": False}
    assert body["debit_cents"] > 0


def test_fire_is_refused_for_an_agent(setup):
    context = ctx_for(setup, "Agent")
    with write_transaction(context.company_db_path, ctx_for(setup)) as conn:
        with pytest.raises(PermissionDeniedError, match="agent"):
            hooks.fire(conn, context, "entry.posted", {"entry_id": 1})


def test_fire_and_on_refuse_an_unknown_event(setup):
    context = ctx_for(setup)
    with write_transaction(context.company_db_path, context) as conn:
        with pytest.raises(ValueError):
            hooks.fire(conn, context, "entry.deleted", {})
    with pytest.raises(ValueError):
        hooks.HookApi("demo", "Demo").on("entry.deleted", lambda db, payload: None)
    with pytest.raises(ValueError):
        hooks.HookApi("demo", "Demo").on("entry.posted", "not callable")


# --- hooks: a handler's limits and errors (HA2) ------------------------------------------------------------------

FAILING = {
    "raises": 'raise RuntimeError("secret detail 4111")',
    "core write": 'db.execute("UPDATE journal_entry SET description = \'hacked\'")',
    "audit write": 'db.execute("INSERT INTO audit_log (table_name, record_id, action) VALUES (\'x\', 1, \'Insert\')")',
    "commit": 'db.execute("COMMIT")',
    "pragma": 'db.execute("PRAGMA foreign_keys = OFF")',
    "attach": 'db.execute("ATTACH DATABASE \':memory:\' AS other")',
    "schema": 'db.execute("CREATE TABLE bad_x (y)")',
    "other addon": 'db.execute("INSERT INTO demo_seen (event) VALUES (\'spoof\')")',
}


@pytest.mark.parametrize("case", sorted(FAILING))
def test_a_failing_handler_rolls_the_posting_back_and_names_the_addon(setup, resources, caplog, case):
    write_addon(resources, "bad", name="Bad Helper", code=f'''
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            db.execute("INSERT INTO bad_log (n) VALUES (1)")
            {FAILING[case]}
        ''', files={"bad_001.sql": "CREATE TABLE bad_log (n INTEGER);\n"})
    addons.enable(admin(setup), "demo")
    addons.enable(admin(setup), "bad")
    entry_id = draft(setup)
    before = (journal(setup), setup.rows("PARENT", "SELECT * FROM entry_number_sequence"),
              setup.rows("PARENT", "SELECT * FROM audit_log ORDER BY log_id"))
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        with pytest.raises(AddonError) as failed:
            ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert str(failed.value) == ("The Bad Helper add-on could not finish, so nothing was saved; disable it in "
                                 "Company Settings > Add-ons and try again.")
    assert (journal(setup), setup.rows("PARENT", "SELECT * FROM entry_number_sequence"),
            setup.rows("PARENT", "SELECT * FROM audit_log ORDER BY log_id")) == before
    assert setup.rows("PARENT", "SELECT * FROM bad_log") == [] and seen(setup) == []
    assert "bad" in caplog.text and "entry.posted" in caplog.text            # the details go to the log
    assert "secret detail" not in str(failed.value)
    assert setup.rows("PARENT", "SELECT description FROM journal_entry WHERE description = 'hacked'") == []


def test_a_handler_cannot_keep_the_connection(setup, resources):
    write_addon(resources, "keep", code='''
        KEPT = []

        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            if KEPT:
                KEPT[0].execute("INSERT INTO keep_n (n) VALUES (2)")
            KEPT.append(db)
            db.execute("INSERT INTO keep_n (n) VALUES (1)")
        ''', files={"keep_001.sql": "CREATE TABLE keep_n (n INTEGER);\n"})
    addons.enable(admin(setup), "keep")
    post(setup)
    with pytest.raises(AddonError):
        post(setup)                         # the kept handle from the first posting is closed
    assert setup.rows("PARENT", "SELECT n FROM keep_n") == [{"n": 1}]


def test_the_handle_returns_rows_not_a_cursor(setup, resources):
    write_addon(resources, "rows", code='''
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            rows = db.execute("SELECT entry_id FROM journal_entry WHERE entry_id = ?", (payload["entry_id"],))
            assert rows == [{"entry_id": payload["entry_id"]}], rows
            assert not hasattr(db, "connection") and not hasattr(db, "commit")
            db.execute("INSERT INTO rows_n (n) VALUES (?)", (len(rows),))
        ''', files={"rows_001.sql": "CREATE TABLE rows_n (n INTEGER);\n"})
    addons.enable(admin(setup), "rows")
    post(setup)
    assert setup.rows("PARENT", "SELECT n FROM rows_n") == [{"n": 1}]


def test_an_enabled_addon_missing_from_this_computer_stops_posting(setup):
    addons.enable(admin(setup), "demo")
    hooks._clear()
    import shutil
    shutil.rmtree(setup.resources / "addons" / "demo")
    entry_id = draft(setup)
    with pytest.raises(AddonError, match="The demo add-on is turned on for this company but is not installed on "
                                         "this computer"):
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert journal(setup)[-1]["is_posted"] == 0


def test_disabling_stops_the_hooks_and_drops_nothing(setup):
    addons.enable(admin(setup), "demo")
    post(setup)
    assert addons.disable(admin(setup), "demo") == {"addon_key": "demo", "enabled": False}
    post(setup)
    assert len(seen(setup)) == 1
    assert setup.rows("PARENT", "SELECT version FROM addon_schema_version") == [{"version": 1}]


def test_an_addon_is_loaded_lazily_when_a_company_has_it_enabled(setup):
    addons.enable(admin(setup), "demo")
    hooks._clear()                          # a new process: nothing imported yet
    post(setup)
    assert len(seen(setup)) == 1


# --- addons: the registry (HA3, HA5) ---------------------------------------------------------------------------

def test_list_shows_installed_and_enabled_addons(setup, resources):
    write_addon(resources, "other", name="Other Thing")
    assert addons.list_addons(admin(setup)) == [
        {"addon_key": "demo", "name": "Demo Notes", "version": "1.0", "installed": True, "enabled": False,
         "schema_version": 0},
        {"addon_key": "other", "name": "Other Thing", "version": "1.0", "installed": True, "enabled": False,
         "schema_version": 0},
    ]
    addons.enable(admin(setup), "demo")
    import shutil
    shutil.rmtree(resources / "addons" / "demo")
    assert addons.list_addons(admin(setup))[0] == {"addon_key": "demo", "name": "demo", "version": "1.0",
                                                   "installed": False, "enabled": True, "schema_version": 1}


def test_enable_runs_the_migrations_and_is_audit_logged(setup):
    result = addons.enable(admin(setup), "demo")
    assert result == {"addon_key": "demo", "enabled": True, "migrations_applied": [1]}
    row = setup.rows("PARENT", "SELECT * FROM company_addon")[0]
    assert (row["enabled"], row["enabled_by"], row["enabled_at"], row["addon_version"]) == (
        1, setup.admin, ctx_for(setup).now, "1.0")
    audit = setup.rows("PARENT", "SELECT user_id, action FROM audit_log WHERE table_name = 'company_addon'")
    assert audit == [{"user_id": setup.admin, "action": "Insert"}]
    sha = setup.rows("PARENT", "SELECT sha256 FROM addon_schema_version")[0]["sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", sha)
    assert addons.enable(admin(setup), "demo")["migrations_applied"] == []          # again: nothing pending
    addons.disable(admin(setup), "demo")
    assert [r["action"] for r in setup.rows("PARENT", "SELECT action FROM audit_log WHERE table_name = "
                                                      "'company_addon' ORDER BY log_id")] == [
        "Insert", "Update", "Update"]


def test_the_master_may_manage_addons(setup):
    master = setup.user("owner", master=True)
    assert addons.enable(ctx_for(setup, user=master), "demo")["enabled"] is True


@pytest.mark.parametrize("who", ["poster", "viewer", "agent", "controller"])
def test_only_admin_and_the_master_manage_addons(setup, who):
    if who == "controller":
        from modules.services import role_templates
        setup.role("PARENT", "Controller", sorted(role_templates.permissions_for("Controller")))
        user = setup.user("ctl")
        setup.grant(user, "PARENT", "Controller")
        context = ctx_for(setup, user=user)
    else:
        context = {"poster": ctx_for(setup), "viewer": ctx_for(setup, user=setup.viewer),
                   "agent": admin(setup, "Agent")}[who]
    for call in (lambda: addons.list_addons(context), lambda: addons.enable(context, "demo"),
                 lambda: addons.disable(context, "demo")):
        with pytest.raises(PermissionDeniedError):
            call()
    assert setup.rows("PARENT", "SELECT * FROM company_addon") == []
    assert setup.events("PARENT")[-1]["permission_code"] == "addon.manage"


def test_enabling_an_addon_that_is_not_installed(setup):
    with pytest.raises(NotFoundError, match="not installed"):
        addons.enable(admin(setup), "nothere")
    with pytest.raises(NotFoundError):
        addons.disable(admin(setup), "nothere")


def test_a_refused_migration_enables_nothing(setup, resources):
    write_addon(resources, "sneak", name="Sneaky", files={
        "sneak_001.sql": "CREATE TABLE sneak_x (y);\nCREATE INDEX sneak_ix ON journal_entry (description);\n"})
    with pytest.raises(ValidationError) as refused:
        addons.enable(admin(setup), "sneak")
    assert str(refused.value).startswith("The Sneaky add-on could not set up its tables")
    assert "Nothing was changed" in str(refused.value)
    assert setup.rows("PARENT", "SELECT * FROM company_addon") == []
    assert setup.rows("PARENT", "SELECT name FROM sqlite_master WHERE name LIKE 'sneak%'") == []


# --- addons: where code comes from (HA3) ---------------------------------------------------------------------------

def test_addons_load_only_from_resource_dir_never_data_dir(setup, tmp_path):
    marker = tmp_path / "ran.txt"
    write_addon(config.DATA_DIR, "evil", code=f'''
        open({str(marker)!r}, "w").write("ran")

        def register(hooks):
            pass
        ''')
    assert [a["addon_key"] for a in addons.list_addons(admin(setup))] == ["demo"]
    with pytest.raises(NotFoundError):
        addons.enable(admin(setup), "evil")
    with pytest.raises(NotFoundError):
        addons.load("evil")
    assert not marker.exists()


def test_a_resource_addons_folder_inside_data_dir_is_refused(setup, monkeypatch, tmp_path):
    """RESOURCE_DIR pointed into DATA_DIR (while they differ) is treated as no add-ons at all."""
    write_addon(Path(config.DATA_DIR) / "inner", "demo")
    monkeypatch.setattr(config, "RESOURCE_DIR", str(Path(config.DATA_DIR) / "inner"))
    assert addons.discover() == {}


def test_the_addons_folder_is_resource_dir_addons():
    assert Path(addons.addons_dir()) == Path(config.RESOURCE_DIR) / "addons"


@pytest.mark.parametrize("manifest, match", [
    ({"key": "other", "name": "X", "version": "1"}, "folder"),
    ({"name": "X", "version": "1"}, "key"),
    ({"key": "demo", "version": "1"}, "name"),
    ({"key": "demo", "name": "X"}, "version"),
])
def test_a_bad_manifest_is_skipped_and_logged(setup, resources, caplog, manifest, match):
    import shutil
    shutil.rmtree(resources / "addons" / "demo")
    write_addon(resources, "demo", manifest=manifest)
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert addons.discover() == {}
    assert match in caplog.text


def test_a_key_that_would_own_core_tables_is_skipped(setup, resources, caplog):
    write_addon(resources, "journal")
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert "journal" not in addons.discover()
    assert "reserved" in caplog.text


def test_an_addon_registers_only_under_its_own_key(setup, resources):
    """The handle has no key to change, and a register() that fails turns nothing on."""
    write_addon(resources, "liar", code='''
        def register(hooks):
            hooks.addon_key = "demo"
        ''', files={})
    with pytest.raises(AddonError, match="The Liar Notes add-on could not start"):
        addons.enable(admin(setup), "liar")
    assert setup.rows("PARENT", "SELECT * FROM company_addon") == []
    assert not hooks.is_loaded("liar")


def test_an_addon_whose_code_fails_to_import_is_not_turned_on(setup, resources):
    write_addon(resources, "broken", code="raise ImportError('nope')\n", files={})
    with pytest.raises(AddonError, match="The Broken Notes add-on could not start"):
        addons.enable(admin(setup), "broken")
    assert setup.rows("PARENT", "SELECT * FROM company_addon") == []


# --- company open applies pending migrations (HA4) ---------------------------------------------------------------

def test_company_open_applies_pending_migrations_of_enabled_addons(setup, resources):
    setup.settings("PARENT", require_separate_approver=0)
    addons.enable(admin(setup), "demo")
    write_addon(resources, "demo", name="Demo Notes", files={
        "demo_001.sql": DEMO_001, "demo_002.sql": "CREATE TABLE demo_more (x);\n"})
    write_addon(resources, "idle", files={"idle_001.sql": "CREATE TABLE idle_x (y);\n"})     # not enabled
    companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    assert [r["version"] for r in setup.rows("PARENT", "SELECT version FROM addon_schema_version "
                                                       "WHERE addon_key = 'demo' ORDER BY version")] == [1, 2]
    assert setup.rows("PARENT", "SELECT name FROM sqlite_master WHERE name LIKE 'idle%'") == []


def test_company_open_with_a_broken_addon_still_opens_and_posting_says_why(setup, resources, caplog):
    addons.enable(admin(setup), "demo")
    (resources / "addons" / "demo" / "migrations" / "demo_001.sql").write_text(DEMO_001 + "-- edited\n",
                                                                                  encoding="utf-8")
    hooks._clear()
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    assert "demo_001.sql was changed" in caplog.text
    entry_id = draft(setup)
    with pytest.raises(AddonError, match="The Demo Notes add-on could not set up its tables"):
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)


# --- static rules ----------------------------------------------------------------------------------------------------

def _imports(path):
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def test_core_never_imports_addon_packages():
    sources = list((ROOT / "modules").rglob("*.py")) + [ROOT / "app_strata.pyw", ROOT / "config.py"]
    for path in sources:
        for name in _imports(path):
            assert name.split(".")[0] != "addons", (path, name)


def test_only_the_addon_registry_imports_code_by_path():
    found = [p.relative_to(ROOT).as_posix() for p in (ROOT / "modules").rglob("*.py")
             if re.search(r"spec_from_file_location|exec_module|__import__|import_module",
                          p.read_text(encoding="utf-8"))]
    assert found == ["modules/services/addons.py"]


def test_hooks_run_inside_the_callers_transaction():
    source = (ROOT / "modules" / "services" / "hooks.py").read_text(encoding="utf-8")
    assert "write_transaction" not in source and "get_connection" not in source


# --- step-reviewer fixes (STOP B) ------------------------------------------------------------------------------

def test_a_handler_that_swallows_a_refused_write_still_fails(setup, resources):
    write_addon(resources, "quiet", name="Quiet One", code="""
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            try:
                db.execute("UPDATE journal_entry SET description = 'x'")
            except Exception:
                pass
        """, files={})
    addons.enable(admin(setup), "quiet")
    entry_id = draft(setup)
    with pytest.raises(AddonError, match="The Quiet One add-on could not finish"):
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert journal(setup)[-1]["is_posted"] == 0


def test_the_handle_offers_only_execute(setup, resources):
    """Narrows mistakes only; not a sandbox (HA7: add-ons are trusted installation code)."""
    write_addon(resources, "probe", code="""
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            names = [n for n in dir(db) if not n.startswith("__")]
            db.execute("INSERT INTO probe_n (names) VALUES (?)", (",".join(names),))
        """, files={"probe_001.sql": "CREATE TABLE probe_n (names TEXT);\n"})
    addons.enable(admin(setup), "probe")
    post(setup)
    assert setup.rows("PARENT", "SELECT names FROM probe_n") == [{"names": "execute"}]


def test_a_broken_addon_in_one_company_does_not_stop_another(setup, resources):
    """The broken mark is per company file: CHILD's failed migration leaves PARENT posting."""
    import dataclasses
    other = admin(setup)
    child = dataclasses.replace(other, company_id=setup.company_id("CHILD"), company_db_path=str(setup.path("CHILD")))
    addons.enable(other, "demo")
    addons.enable(child, "demo")
    (resources / "addons" / "demo" / "migrations" / "demo_002.sql").write_text("CREATE TABLE demo_more (x);\n",
                                                                                  encoding="utf-8")
    with setup._company("CHILD") as c:              # CHILD's copy is now out of step: version 2 "applied" wrongly
        c.execute("INSERT INTO addon_schema_version (addon_key, version, sha256) VALUES ('demo', 2, ?)", ("0" * 64,))
    addons.prepare_company(other)                   # PARENT is fine
    addons.prepare_company(child)                   # marks demo broken in CHILD only
    post(setup)
    assert len(seen(setup)) == 1
    child_entry = None
    with pytest.raises(AddonError, match="could not set up its tables"):
        with write_transaction(child.company_db_path, child) as conn:
            hooks.fire(conn, child, "entry.posted", {"entry_id": child_entry})
    addons.prepare_company(other)                   # opening PARENT again does not clear CHILD's mark
    with pytest.raises(AddonError, match="could not set up its tables"):
        with write_transaction(child.company_db_path, child) as conn:
            hooks.fire(conn, child, "entry.posted", {"entry_id": child_entry})


def test_a_read_only_open_applies_no_migrations(setup, resources):
    import dataclasses
    addons.enable(admin(setup), "demo")
    write_addon(resources, "demo", name="Demo Notes", files={
        "demo_001.sql": DEMO_001, "demo_002.sql": "CREATE TABLE demo_more (x);\n"})
    addons.prepare_company(dataclasses.replace(admin(setup), read_only=True))
    assert setup.rows("PARENT", "SELECT name FROM sqlite_master WHERE name = 'demo_more'") == []


def test_company_open_with_an_enabled_addon_missing_from_this_computer(setup, caplog):
    import shutil
    addons.enable(admin(setup), "demo")
    hooks._clear()
    shutil.rmtree(setup.resources / "addons" / "demo")
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    assert "not installed" in caplog.text


def test_a_migration_file_that_is_not_utf8_does_not_stop_company_open(setup, resources, caplog):
    addons.enable(admin(setup), "demo")
    (resources / "addons" / "demo" / "migrations" / "demo_002.sql").write_bytes(
        "CREATE TABLE demo_café (x);\n".encode("cp1252"))
    hooks._clear()
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        companies.open_company(setup.session(setup.admin), setup.company_id("PARENT"))
    entry_id = draft(setup)
    with pytest.raises(AddonError, match="could not set up its tables"):
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    with pytest.raises(ValidationError, match="could not set up its tables"):
        addons.enable(admin(setup), "demo")
