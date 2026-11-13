"""Step 1c sub-step 9: a new key epoch when a company's ledger key is lost (KS8; audit design 2.7, "Key lost").

ledger_keys.start_new_key_epoch(session, company_id, confirm_company_code=...), Master only, for a company whose
active key cannot be opened on this computer while the installation key can (a key store that is locked refuses,
KS6). The company code must be typed. The old key is retired as 'Key lost', a new key becomes active (wrapped in
the master, 'Ledger key lost' auth_event), and posting can go on: the next entry chains to the last stored hash.
The data stays readable; entries sealed with the lost key can no longer be verified. Since Step 1d the epoch signs
a 'Key lost' checkpoint and a full check is OK with that range reported as unverified (never Broken); see
tests/test_key_lost_checkpoint.py.
"""
import dataclasses
import sqlite3
from pathlib import Path

import pytest

import config
from modules.services import companies, key_store, keys, ledger, ledger_keys, ledger_verify
from modules.services.errors import KeyStoreLockedError, PermissionDeniedError, ValidationError
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_company_keys import _create, _installation, _two_postable_accounts
from tests.test_key_store import FakeMachineWrap


def _context(world, company_id):
    return dataclasses.replace(companies.open_company(world.root, company_id), now="2026-03-20T10:00:00+00:00",
                               today="2026-03-20")


def _post(context, cents):
    debit, credit = _two_postable_accounts(context)
    entry_id = ledger.create_entry(context, entry_date="2026-03-15", lines=[
        {"account_id": debit, "debit_cents": cents}, {"account_id": credit, "credit_cents": cents}])
    ledger.post_journal_entry(context, entry_id, confirm=True, acknowledge_date_warnings=True)


def _rows(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


@pytest.fixture
def lost(world, monkeypatch):
    """A company with two posted entries whose key this installation never stored (made under the test key, as if
    the company file came from elsewhere), and an unlocked LocalKeyProvider."""
    world.root = world.session(world.user("root", master=True))
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(lh.TEST_CHAIN_KEY))
    created = _create(world.root)
    context = _context(world, created["company_id"])
    _post(context, 1000)
    _post(context, 2000)
    _installation(world, FakeMachineWrap())
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap()))
    world.company = created
    world.company_path = Path(config.BASE_PROJECT_DIR) / created["database_file_path"]
    return created


def _audit(world):
    """Every audit row of both files and every auth_event (a refusal that is not a permission denial adds none)."""
    return (_rows(world.company_path, "SELECT * FROM audit_log"), _rows(world.master, "SELECT * FROM audit_log"),
            _rows(world.master, "SELECT * FROM auth_event"))


def _epoch(world, session=None, code=None):
    return ledger_keys.start_new_key_epoch(session or world.root, world.company["company_id"],
                                           confirm_company_code=code if code is not None else
                                           world.company["company_code"])


def _snapshot(world):
    return (_rows(world.company_path, "SELECT * FROM ledger_chain_key"),
            _rows(world.master, "SELECT company_key_id FROM company_key"),
            _rows(world.master, "SELECT event_id FROM auth_event WHERE event_type = 'Ledger key lost'"))


def test_a_lost_key_is_retired_and_a_new_one_becomes_active(world, lost):
    [old] = _rows(world.company_path, "SELECT key_id FROM ledger_chain_key")
    result = _epoch(world)
    rows = {r["key_id"]: r for r in _rows(world.company_path, "SELECT * FROM ledger_chain_key")}
    assert rows[old["key_id"]]["retire_reason"] == "Key lost" and rows[old["key_id"]]["is_active"] == 0
    assert rows[result["new_key_id"]]["is_active"] == 1 and result["old_key_id"] == old["key_id"]
    [stored] = _rows(world.master, "SELECT fingerprint FROM company_key")
    assert stored["fingerprint"] == rows[result["new_key_id"]]["fingerprint"]


def test_the_result_names_the_last_entry_that_can_no_longer_be_verified(world, lost):
    result = _epoch(world)
    assert result["unverifiable_through"] == 2
    assert result["message"] == ("A new ledger key was started. Entries up to JE-000002 were sealed with the lost "
                                 "key and can no longer be verified; their data is unchanged.")


def test_the_epoch_is_recorded_as_an_auth_event_naming_the_company(world, lost):
    _epoch(world)
    events = _rows(world.master, "SELECT user_id, company_id FROM auth_event WHERE event_type = 'Ledger key lost'")
    assert events == [{"user_id": world.root.user_id, "company_id": world.company["company_id"]}]


def test_posting_goes_on_after_the_epoch_and_old_entries_are_unverified_not_broken(world, lost):
    result = _epoch(world)
    context = _context(world, world.company["company_id"])
    _post(context, 3000)
    entries = _rows(world.company_path, "SELECT chain_key_id, chain_prev_hash, chain_hash FROM journal_entry "
                                        "ORDER BY entry_number")
    assert entries[2]["chain_key_id"] == result["new_key_id"]
    assert entries[2]["chain_prev_hash"] == entries[1]["chain_hash"]
    result = ledger_verify.verify_ledger(context, mode="full")
    assert (result["status"], result["unverified_through"]) == ("OK", 2)
    assert _rows(world.company_path, "SELECT * FROM ledger_checkpoint WHERE result = 'Broken'") == []


def test_an_empty_ledger_has_nothing_unverifiable(world, monkeypatch):
    world.root = world.session(world.user("root", master=True))
    created = _create(world.root, "Empty Books")
    _installation(world, FakeMachineWrap())
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap()))
    result = ledger_keys.start_new_key_epoch(world.root, created["company_id"],
                                             confirm_company_code=created["company_code"])
    assert result["unverifiable_through"] == 0
    assert result["message"] == "A new ledger key was started. No entries were sealed with the lost key."


def test_a_key_that_is_still_available_is_rotated_instead(world, monkeypatch):
    world.root = world.session(world.user("root", master=True))
    _installation(world, FakeMachineWrap())
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap()))
    created = _create(world.root)
    with pytest.raises(ValidationError) as caught:
        ledger_keys.start_new_key_epoch(world.root, created["company_id"],
                                        confirm_company_code=created["company_code"])
    assert str(caught.value) == ledger_keys.KEY_STILL_AVAILABLE
    [row] = _rows(Path(config.BASE_PROJECT_DIR) / created["database_file_path"], "SELECT * FROM ledger_chain_key")
    assert row["is_active"] == 1


@pytest.mark.parametrize("code", ["", "WRONG", "acme"])
def test_the_company_code_must_be_typed(world, lost, code):
    before, audit = _snapshot(world), _audit(world)
    with pytest.raises(ValidationError):
        _epoch(world, code=code)
    assert _snapshot(world) == before and _audit(world) == audit


def test_only_the_master_starts_a_new_key(world, lost):
    before = _snapshot(world)
    admin = world.session(world.user("admin"))
    with pytest.raises(PermissionDeniedError):
        _epoch(world, session=admin)
    assert _snapshot(world) == before


def test_a_locked_key_store_cannot_start_a_new_key(world, lost, monkeypatch):
    """The installation key itself is locked or lost: no new company key can be stored (decision pending)."""
    before, audit = _snapshot(world), _audit(world)
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap(
        fail_unprotect=True)))
    with pytest.raises(KeyStoreLockedError):
        _epoch(world)
    assert _snapshot(world) == before and _audit(world)[1:] == audit[1:]


def test_after_an_epoch_the_new_key_can_be_rotated(world, lost):
    """Step 1c review: rotation needs only the CURRENT key, so the old lost key never blocks it (no loop between
    'start a new ledger key' and 'rotate it instead'). Since Step 1d (KS16) the rotation signs its checkpoint: the
    check is OK with the unverified range."""
    epoch = _epoch(world)
    context = _context(world, world.company["company_id"])
    _post(context, 3000)
    rotated = ledger_keys.rotate_chain_key(world.root, world.company["company_id"])
    assert rotated["old_key_id"] == epoch["new_key_id"]
    assert rotated["checkpoint"]["status"] == "OK" and rotated["checkpoint"]["recorded_in"] == ["company", "master"]
    assert rotated["checkpoint"]["unverified_through"] == 2
    rows = _rows(world.company_path, "SELECT retire_reason, is_active FROM ledger_chain_key ORDER BY key_id")
    assert rows == [{"retire_reason": "Key lost", "is_active": 0}, {"retire_reason": "Rotation", "is_active": 0},
                    {"retire_reason": None, "is_active": 1}]
    _post(_context(world, world.company["company_id"]), 4000)
