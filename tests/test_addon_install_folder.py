"""HA8: add-ons load only from a program folder non-admins cannot change (Codex finding; owner 2026-11-18).

In the installed (frozen) build, before discover or load reads or imports any add-on, the service asks the folder
check the app handed it (addons.use_folder_check; platform_support.folder_open_to_non_admins reads the folder's
ACL, P3) about RESOURCE_DIR and RESOURCE_DIR\\addons. If either is open to a non-admin principal, or no check was
handed over, no add-on is found or loaded, the reason is logged, and enable, load and posting say one sentence
(addons.ADDONS_OFF). A run from source is exempt: a developer's checkout is always writable.
"""
import logging
import os

import pytest

import config
from modules.services import addons, hooks, ledger
from modules.services.errors import AddonError
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_addons import admin, journal, resources, setup, write_addon  # noqa: F401  (fixtures and helpers)
from tests.test_ledger_posting import ctx_for, draft, env, keyed  # noqa: F401  (fixtures and helpers)

MARKER_CODE = '''
import pathlib
pathlib.Path(__file__).with_name("imported.txt").write_text("yes")


def register(hooks):
    pass
'''

SENTENCE = ("Add-ons are off because the program folder can be changed by this account; reinstall StrataLedger to "
            "Program Files.")


@pytest.fixture(autouse=True)
def _no_check_left_behind():
    yield
    addons.use_folder_check(None)


def check(monkeypatch, open_folders):
    """A stand-in folder check: True for the folders named open ('program' = RESOURCE_DIR, 'addons')."""
    asked = []

    def folder_check(path):
        name = "addons" if os.path.basename(path) == "addons" else "program"
        asked.append(name)
        return name in open_folders
    addons.use_folder_check(folder_check)
    return asked


@pytest.fixture
def installed(resources, monkeypatch):
    """A frozen build with one add-on whose code leaves imported.txt beside itself when it is imported."""
    folder = write_addon(resources, "demo", name="Demo Notes", code=MARKER_CODE)
    monkeypatch.setattr(config, "FROZEN", True)
    return folder


def test_the_sentence_is_the_owners():
    assert addons.ADDONS_OFF == SENTENCE


@pytest.mark.parametrize("open_folders", [{"program"}, {"addons"}, {"program", "addons"}])
def test_a_loose_acl_turns_addons_off(installed, monkeypatch, caplog, open_folders):
    check(monkeypatch, open_folders)
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert addons.discover() == {}
        with pytest.raises(AddonError) as raised:
            addons.load("demo")
    assert str(raised.value) == SENTENCE
    assert not (installed / "imported.txt").exists() and not hooks.is_loaded("demo")
    assert any("non-admin" in r.getMessage() for r in caplog.records)


def test_an_admin_only_acl_keeps_addons_on(installed, monkeypatch):
    asked = check(monkeypatch, set())
    assert set(addons.discover()) == {"demo"}
    addons.load("demo")
    assert (installed / "imported.txt").exists() and hooks.is_loaded("demo")
    assert set(asked) == {"program", "addons"}             # both folders are checked


def test_a_frozen_build_with_no_check_handed_over_keeps_addons_off(installed):
    assert addons.discover() == {}
    with pytest.raises(AddonError, match="reinstall StrataLedger to Program Files"):
        addons.load("demo")
    assert not (installed / "imported.txt").exists()


def test_a_missing_addons_folder_checks_only_the_program_folder(resources, monkeypatch):
    monkeypatch.setattr(config, "FROZEN", True)
    asked = check(monkeypatch, set())
    assert addons.discover() == {} and asked == ["program"]


def test_enable_says_the_sentence_and_changes_nothing(setup, monkeypatch):
    monkeypatch.setattr(config, "FROZEN", True)
    check(monkeypatch, {"addons"})
    before = setup.rows("PARENT", "SELECT * FROM company_addon")
    with pytest.raises(AddonError, match="reinstall StrataLedger to Program Files"):
        addons.enable(admin(setup), "demo")
    assert setup.rows("PARENT", "SELECT * FROM company_addon") == before
    assert setup.rows("PARENT", "SELECT name FROM sqlite_master WHERE name = 'demo_seen'") == []


def test_posting_with_an_enabled_addon_says_the_sentence_and_saves_nothing(setup, monkeypatch):
    """Enabled earlier; this run is a frozen build in a loose folder. Posting stops with HA8's sentence (not
    "not installed") and rolls back, as for any add-on that cannot start."""
    addons.enable(admin(setup), "demo")
    hooks._clear()                                   # a new process: nothing loaded yet
    monkeypatch.setattr(config, "FROZEN", True)
    check(monkeypatch, {"program"})
    before = journal(setup)
    entry_id = draft(setup)
    with pytest.raises(AddonError) as raised:
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert str(raised.value) == SENTENCE
    assert [r for r in journal(setup) if r["is_posted"]] == [r for r in before if r["is_posted"]]


def test_a_source_run_is_exempt_and_never_asks(resources, monkeypatch):
    folder = write_addon(resources, "demo", name="Demo Notes", code=MARKER_CODE)
    monkeypatch.setattr(config, "FROZEN", False)
    asked = check(monkeypatch, {"program", "addons"})
    addons.load("demo")
    assert (folder / "imported.txt").exists() and hooks.is_loaded("demo") and asked == []


def test_source_runs_are_not_frozen():
    assert config.FROZEN is False


def test_the_app_hands_the_platform_check_to_the_service():
    source = (config.RESOURCE_DIR and open(os.path.join(os.path.dirname(os.path.abspath(config.__file__)),
                                                        "app_strata.pyw"), encoding="utf-8").read())
    assert "addons.use_folder_check(platform_support.folder_open_to_non_admins)" in source
