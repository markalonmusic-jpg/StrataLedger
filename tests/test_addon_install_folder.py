"""HA8: add-ons load only from a program folder this account cannot change (Codex finding, owner 2026-11-18).

In the installed (frozen) build, before discover or load reads or imports any add-on, the app checks whether
RESOURCE_DIR or RESOURCE_DIR\\addons can be written by the account running it. If either can, no add-on is found
or loaded, the reason is logged, and enable and load say one sentence (addons.ADDONS_OFF). A run from source is
exempt: a developer's checkout is always writable. The check makes and removes a probe file (storage.py), because
os.access does not read Windows folder permissions.
"""
import logging
import os
from pathlib import Path

import pytest

import config
from modules.services import addons, hooks, ledger, storage
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


@pytest.fixture
def installed(resources, monkeypatch):
    """A frozen build with one add-on whose code leaves imported.txt beside itself when it is imported."""
    folder = write_addon(resources, "demo", name="Demo Notes", code=MARKER_CODE)
    monkeypatch.setattr(config, "FROZEN", True)
    return folder


def writable(monkeypatch, answers):
    """Pretend the probe found these folders writable: {relative or None (RESOURCE_DIR): bool}."""
    seen = []

    def probe(relative=None):
        seen.append(relative)
        return answers[relative]
    monkeypatch.setattr(storage, "resource_dir_writable", probe)
    return seen


def test_the_sentence_is_the_owners():
    assert addons.ADDONS_OFF == SENTENCE


@pytest.mark.parametrize("answers", [{None: True, "addons": False}, {None: False, "addons": True},
                                     {None: True, "addons": True}])
def test_a_frozen_build_with_a_writable_program_folder_loads_nothing(installed, monkeypatch, caplog, answers):
    writable(monkeypatch, answers)
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert addons.discover() == {}
        with pytest.raises(AddonError) as raised:
            addons.load("demo")
    assert str(raised.value) == SENTENCE
    assert not (installed / "imported.txt").exists()
    assert not hooks.is_loaded("demo")
    assert any("can be changed by this account" in r.getMessage() for r in caplog.records)


def test_enable_says_the_sentence_and_changes_nothing(setup, monkeypatch):
    monkeypatch.setattr(config, "FROZEN", True)
    writable(monkeypatch, {None: True, "addons": True})
    before = setup.rows("PARENT", "SELECT * FROM company_addon")
    with pytest.raises(AddonError, match="reinstall StrataLedger to Program Files"):
        addons.enable(admin(setup), "demo")
    assert setup.rows("PARENT", "SELECT * FROM company_addon") == before
    assert setup.rows("PARENT", "SELECT name FROM sqlite_master WHERE name = 'demo_seen'") == []


def test_posting_with_an_enabled_addon_says_the_sentence_and_saves_nothing(setup, monkeypatch):
    """Enabled earlier; this run is a frozen build in a changeable folder. Posting stops with HA8's sentence (not
    "not installed") and rolls back, as for any add-on that cannot start."""
    addons.enable(admin(setup), "demo")
    hooks._clear()                                   # a new process: nothing loaded yet
    monkeypatch.setattr(config, "FROZEN", True)
    writable(monkeypatch, {None: False, "addons": True})
    before = journal(setup)
    entry_id = draft(setup)
    with pytest.raises(AddonError) as raised:
        ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert str(raised.value) == SENTENCE
    assert [r for r in journal(setup) if r["is_posted"]] == [r for r in before if r["is_posted"]]


def test_a_frozen_build_with_a_read_only_program_folder_loads(installed, monkeypatch):
    seen = writable(monkeypatch, {None: False, "addons": False})
    assert set(addons.discover()) == {"demo"}
    addons.load("demo")
    assert (installed / "imported.txt").exists() and hooks.is_loaded("demo")
    assert None in seen and "addons" in seen           # both folders are checked


def test_a_source_run_is_exempt_even_though_its_folder_is_writable(resources, monkeypatch):
    folder = write_addon(resources, "demo", name="Demo Notes", code=MARKER_CODE)
    monkeypatch.setattr(config, "FROZEN", False)
    assert storage.resource_dir_writable() and storage.resource_dir_writable("addons")     # really writable
    addons.load("demo")
    assert (folder / "imported.txt").exists() and hooks.is_loaded("demo")


def test_the_real_check_turns_a_frozen_build_with_a_writable_folder_off(installed):
    """No stand-in for the probe: tmp_path is writable by this account, so a frozen build refuses it."""
    assert addons.discover() == {}
    assert not (installed / "imported.txt").exists()


def test_source_runs_are_not_frozen():
    assert config.FROZEN is False


# --- the probe (storage.py, H3) --------------------------------------------------------------------------------------

def test_the_probe_finds_a_writable_folder_and_leaves_nothing_behind(resources):
    (resources / "addons").mkdir()
    assert storage.resource_dir_writable() is True
    assert storage.resource_dir_writable("addons") is True
    assert sorted(os.listdir(resources)) == ["addons"] and os.listdir(resources / "addons") == []


def test_the_probe_says_no_when_a_file_cannot_be_made(resources, monkeypatch):
    def refuse(*args, **kwargs):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(storage.tempfile, "mkstemp", refuse)
    assert storage.resource_dir_writable() is False


def test_a_missing_addons_folder_is_not_writable_but_its_parent_still_counts(resources):
    assert storage.resource_dir_writable("addons") is False
    assert not Path(resources, "addons").exists()                # the probe makes no folder
    assert storage.resource_dir_writable() is True
