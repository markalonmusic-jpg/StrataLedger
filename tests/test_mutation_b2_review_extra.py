"""Mutation tests for the B2 review step (997305c, 7aeb3f4, 6afd131): each test kills a mutant that survived the
mutation-tester run of 2026-11-18. The equivalent survivors are listed in docs/next_step.md with their reasons."""
import importlib
import logging
import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest

import config
import modules.database as database
from modules import platform_support as ps
from modules.services import addons, hooks, storage
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_addon_database import KEY, company, migrations, objects  # noqa: F401  (fixture and helpers)
from tests.test_addon_install_folder import MARKER_CODE, check
from tests.test_addons import admin, resources, setup, write_addon  # noqa: F401  (fixtures and helpers)
from tests.test_config_paths import _run
from tests.test_ledger_posting import env, keyed  # noqa: F401  (fixtures)
from tests.test_platform_folder_acl import ADMINS, FULL, MODIFY, PROGRAM_FILES, USER, USERS, ace, acl

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude", "hooks",
                         "pre_commit_pytest.py")


@pytest.fixture(autouse=True)
def _no_check_left_behind():
    yield
    addons.use_folder_check(None)


# --- HA11: _looks_secret ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("column", [
    "pws",                                   # a plural of a two-letter word
    "userPin", "clientSsn",                  # only the camel-case split finds these
    "pass1word", "api2key",                  # digits split words; the digit words are dropped
    "session_ids", "install_keys", "enc_keys", "pin_codes",      # pairs are matched in the singular
])
def test_these_names_are_refused(column):
    assert database._looks_secret(column), column


def test_an_ordinary_run_is_taken_out_as_a_break_not_joined_up():
    """'tokeniz' is removed as a break, so the letters around it do not join into a secret run."""
    assert not database._looks_secret("passtokenizword")


# --- HA11: _check_existing_columns -----------------------------------------------------------------------------------

def _add_column(company_path, table, column):
    raw = sqlite3.connect(company_path)
    try:
        raw.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        raw.commit()
    finally:
        raw.close()


def test_every_addon_table_is_checked_not_only_the_first(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY);\n"
                                                   "CREATE TABLE demo_b (b_id INTEGER PRIMARY KEY);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    _add_column(company, "demo_b", "feed_token")
    with pytest.raises(database.AddonMigrationError, match="demo_b"):
        database.apply_addon_migrations(company, KEY, folder)


def test_a_table_of_a_longer_key_is_not_this_addons(company, tmp_path):
    """Key `demo` owns `demo_` tables only; `demobar_x` (another add-on's) is not checked as demo's."""
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    raw = sqlite3.connect(company)
    try:
        raw.execute("CREATE TABLE demobar_x (x_id INTEGER PRIMARY KEY, feed_token TEXT)")
        raw.commit()
    finally:
        raw.close()
    assert database.apply_addon_migrations(company, KEY, folder) == []


# --- HA11: failure messages ------------------------------------------------------------------------------------------

def test_a_reach_outside_refusal_has_no_chained_cause(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_first (x);\nDELETE FROM addon_schema_version;\n"})
    with pytest.raises(database.AddonMigrationError, match="reaches outside") as raised:
        database.apply_addon_migrations(company, KEY, folder)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_the_runners_own_failure_names_the_file_and_chains_nothing(company, tmp_path, monkeypatch):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_first (x);\n"})
    real = database._sync_audit_triggers
    calls = []

    def failing(conn, addon_key, synced):
        calls.append(1)
        if len(calls) > 1:                           # the first call runs before any file is current
            raise sqlite3.OperationalError("boom")
        return real(conn, addon_key, synced)
    monkeypatch.setattr(database, "_sync_audit_triggers", failing)
    with pytest.raises(database.AddonMigrationError) as raised:
        database.apply_addon_migrations(company, KEY, folder)
    assert "demo_001.sql failed (boom) and was rolled back" in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


# --- HA8: addons_off, prepare_company, storage -----------------------------------------------------------------------

def test_a_frozen_build_with_no_check_logs_why(resources, monkeypatch, caplog):
    monkeypatch.setattr(config, "FROZEN", True)
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert addons.addons_off() == addons.ADDONS_OFF
    assert any("no program-folder check was set up" in r.getMessage() for r in caplog.records)


def test_opening_a_company_with_nothing_enabled_reads_no_folder_permissions(setup, monkeypatch, caplog):
    monkeypatch.setattr(config, "FROZEN", True)
    asked = check(monkeypatch, {"program"})
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        addons.prepare_company(admin(setup))
    assert asked == [] and not caplog.records


def test_opening_a_company_brings_up_every_enabled_addon(setup):
    write_addon(setup.resources, "second", name="Second Notes", code="def register(hooks):\n    pass\n",
                files={"second_001.sql": "CREATE TABLE second_seen (seen_id INTEGER PRIMARY KEY);\n"})
    addons.enable(admin(setup), "demo")
    addons.enable(admin(setup), "second")
    hooks._clear()
    addons.prepare_company(admin(setup))
    assert hooks.is_loaded("demo") and hooks.is_loaded("second")


def test_resource_root_is_the_resolved_resource_folder_not_the_data_folder(resources):
    assert config.RESOURCE_DIR != config.DATA_DIR
    winding = os.path.join(config.RESOURCE_DIR, "sub", "..")
    os.makedirs(os.path.join(config.RESOURCE_DIR, "sub"))
    config.RESOURCE_DIR = winding                           # restored by the resources fixture's monkeypatch
    assert storage.resource_root() == os.path.realpath(winding) == os.path.realpath(str(resources))


def test_addons_off_asks_about_the_resource_folder(resources, monkeypatch):
    write_addon(resources, "demo", code=MARKER_CODE)
    monkeypatch.setattr(config, "FROZEN", True)
    asked = []
    addons.use_folder_check(lambda path: asked.append(path) or False)
    addons.addons_off()
    root = os.path.realpath(str(resources))
    tree = [os.path.join(root, *p.split("/")) for p in ("addons", "addons/demo", "addons/demo/migrations",
            "addons/demo/addon.json", "addons/demo/addon.py", "addons/demo/migrations/demo_001.sql")]
    assert asked == [root] + tree


# --- The commit hook and config.FROZEN -------------------------------------------------------------------------------

def test_xdist_available_asks_for_xdist(monkeypatch):
    spec = importlib.util.spec_from_file_location("pre_commit_pytest_m", HOOK_PATH)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    asked = []
    monkeypatch.setattr(hook.importlib.util, "find_spec",
                        lambda name: asked.append(name) or (None if name == "xdist" else object()))
    assert hook.xdist_available() is False and asked == ["xdist"]


def test_config_frozen_follows_sys_frozen(tmp_path):
    out = _run("sys.frozen = True\nsys._MEIPASS = %r\nimport config\nprint(config.FROZEN)" % str(tmp_path / "mei"),
               {"PROGRAMDATA": str(tmp_path)}, tmp_path)
    assert out == ["True"]


# --- The clipboard retry ---------------------------------------------------------------------------------------------

def test_a_clipboard_that_stays_busy_is_tried_exactly_fifty_times(monkeypatch):
    monkeypatch.setattr(ps.time, "sleep", lambda seconds: None)
    tries = []
    with pytest.raises(OSError):
        ps._open_clipboard(SimpleNamespace(OpenClipboard=lambda owner: tries.append(1) and False))
    assert len(tries) == ps._OPEN_TRIES == 50


# --- HA8: the ACL rules ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bit", [1 << n for n in range(32) if ps.CHANGE_RIGHTS & (1 << n)])
def test_every_change_right_on_its_own_counts(bit):
    assert ps.non_admin_writers(acl(*PROGRAM_FILES.entries, ace(USERS, bit))) == [USERS]


def test_the_change_rights_are_exactly_these():
    assert ps.CHANGE_RIGHTS == (0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x10000000
                                | 0x40000000)


def test_a_callback_allow_entry_counts():
    entry = ace(USERS, MODIFY, ace_type=ps.ACCESS_ALLOWED_CALLBACK)
    assert ps.non_admin_writers(acl(*PROGRAM_FILES.entries, entry)) == [USERS]


def test_a_sid_is_listed_once():
    twice = acl(ace(USERS, MODIFY), ace(USERS, FULL), ace(USER, FULL), owner=USER)
    assert ps.non_admin_writers(twice) == [USER, USERS]


def test_an_open_folder_is_logged_with_its_path_and_writers(tmp_path, caplog):
    with caplog.at_level(logging.ERROR, logger="strataledger.platform"):
        assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=lambda p: acl(ace(USERS, MODIFY))) is True
    assert any(str(tmp_path) in r.getMessage() and USERS in r.getMessage() for r in caplog.records)


def test_off_windows_the_reader_refuses(monkeypatch, tmp_path):
    monkeypatch.setattr(ps, "IS_WINDOWS", False)
    with pytest.raises(NotImplementedError):
        ps.read_folder_acl(str(tmp_path))


windows_only = pytest.mark.skipif(not ps.IS_WINDOWS, reason="reads a real Windows ACL")


@windows_only
def test_the_real_reader_gives_the_owner_and_exact_masks(tmp_path):
    """tmp_path is made by this user under their profile: owned by them (or Administrators when elevated), with
    full control (0x1F01FF) for them, SYSTEM and Administrators."""
    folder = ps.read_folder_acl(str(tmp_path))
    masks = {e.sid: e.mask for e in folder.entries if e.type == ps.ACCESS_ALLOWED}
    users = [sid for sid in masks if sid.startswith("S-1-5-21-")]
    assert folder.owner in set(users) | {ADMINS}
    assert users and all(masks[sid] == FULL for sid in users) and masks.get("S-1-5-18") == FULL


@windows_only
def test_the_real_reader_reads_a_file_and_refuses_a_missing_path(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    assert ps.read_folder_acl(str(path)).entries
    with pytest.raises(OSError, match="not found"):
        ps.read_folder_acl(str(tmp_path / "missing.txt"))


def test_sys_is_untouched():
    assert not getattr(sys, "frozen", False)
