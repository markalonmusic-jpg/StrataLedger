"""Step 1c sub-step 8: rotating a company's ledger key (docs/audit_readiness_design.md 2.7, "Rotation").

ledger_keys.rotate_chain_key(session, company_id), Master only:
1. a full ledger check under the current key (refused if that key is not available here: rotating needs it, and a
   lost key takes the key-lost path instead);
2. the new key, wrapped, into the master (`company_key`) with a 'Ledger key rotated' auth_event;
3. in the company file the old key is retired ('Rotation') and the new one becomes active;
4. a signed 'Key rotation' checkpoint of the check in step 1, MACed with the new key, in the file and the mirror.
The next entry is sealed with the new key and chains to the old key's last hash; old keys are kept forever, so
every entry still verifies.
"""
import dataclasses
import sqlite3
from pathlib import Path

import pytest

import config
from modules.services import companies, key_store, keys, ledger, ledger_keys, ledger_verify
from modules.services.errors import KeyStoreLockedError, KeyUnavailableError, PermissionDeniedError
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_company_keys import _create, _installation, _two_postable_accounts, real_keys  # noqa: F401
from tests.test_key_store import FakeMachineWrap


def _context(world, company_id):
    return dataclasses.replace(companies.open_company(world.root, company_id), now="2026-03-20T10:00:00+00:00",
                               today="2026-03-20")


def _post(context, cents=1000):
    debit, credit = _two_postable_accounts(context)
    entry_id = ledger.create_entry(context, entry_date="2026-03-15", lines=[
        {"account_id": debit, "debit_cents": cents}, {"account_id": credit, "credit_cents": cents}])
    ledger.post_journal_entry(context, entry_id, confirm=True, acknowledge_date_warnings=True)
    return entry_id


def _rows(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


@pytest.fixture
def company(world, real_keys):
    created = _create(world.root)
    context = _context(world, created["company_id"])
    _post(context, 1000)
    _post(context, 2000)
    world.company = created
    world.company_path = Path(config.BASE_PROJECT_DIR) / created["database_file_path"]
    return created


def test_rotation_retires_the_old_key_and_activates_a_new_one(world, company):
    [old] = _rows(world.company_path, "SELECT key_id FROM ledger_chain_key")
    result = ledger_keys.rotate_chain_key(world.root, company["company_id"])
    assert result["old_key_id"] == old["key_id"] and result["new_key_id"] != old["key_id"]
    rows = {r["key_id"]: r for r in _rows(world.company_path, "SELECT * FROM ledger_chain_key")}
    assert rows[old["key_id"]]["is_active"] == 0 and rows[old["key_id"]]["retire_reason"] == "Rotation"
    assert rows[old["key_id"]]["retired_at"] is not None
    assert rows[result["new_key_id"]]["is_active"] == 1
    stored = _rows(world.master, "SELECT fingerprint FROM company_key WHERE company_id = ?", (company["company_id"],))
    assert {r["fingerprint"] for r in stored} == {r["fingerprint"] for r in rows.values()}


def test_rotation_signs_a_key_rotation_checkpoint_with_the_new_key(world, company):
    result = ledger_keys.rotate_chain_key(world.root, company["company_id"])
    [checkpoint] = _rows(world.company_path, "SELECT * FROM ledger_checkpoint WHERE kind = 'Key rotation'")
    assert (checkpoint["result"], checkpoint["through_entry_number"], checkpoint["key_id"]) == (
        "OK", 2, result["new_key_id"])
    assert result["checkpoint"]["status"] == "OK" and result["checkpoint"]["recorded_in"] == ["company", "master"]
    mirrors = _rows(world.master, "SELECT kind, key_id FROM chain_checkpoint WHERE kind = 'Key rotation'")
    assert mirrors == [{"kind": "Key rotation", "key_id": result["new_key_id"]}]


def test_rotation_is_recorded_as_an_auth_event_naming_the_company(world, company):
    ledger_keys.rotate_chain_key(world.root, company["company_id"])
    events = _rows(world.master, "SELECT user_id, company_id FROM auth_event WHERE event_type = 'Ledger key rotated'")
    assert events == [{"user_id": world.root.user_id, "company_id": company["company_id"]}]


def test_after_rotation_new_entries_use_the_new_key_and_every_entry_still_verifies(world, company, real_keys):
    result = ledger_keys.rotate_chain_key(world.root, company["company_id"])
    context = _context(world, company["company_id"])
    _post(context, 3000)
    entries = _rows(world.company_path, "SELECT entry_number, chain_key_id, chain_prev_hash, chain_hash "
                                        "FROM journal_entry ORDER BY entry_number")
    assert [e["chain_key_id"] for e in entries] == [result["old_key_id"]] * 2 + [result["new_key_id"]]
    assert entries[2]["chain_prev_hash"] == entries[1]["chain_hash"]
    assert ledger_verify.verify_ledger(context, mode="full")["status"] == "OK"
    assert ledger_verify.verify_ledger(context, mode="incremental")["status"] == "OK"
    real_keys.get_key(company["company_id"], result["old_key_id"])           # the old key is kept


def test_a_second_rotation_keeps_every_key(world, company):
    ledger_keys.rotate_chain_key(world.root, company["company_id"])
    ledger_keys.rotate_chain_key(world.root, company["company_id"])
    rows = _rows(world.company_path, "SELECT is_active, retire_reason FROM ledger_chain_key ORDER BY key_id")
    assert rows == [{"is_active": 0, "retire_reason": "Rotation"}] * 2 + [{"is_active": 1, "retire_reason": None}]
    assert ledger_verify.verify_ledger(_context(world, company["company_id"]), mode="full")["status"] == "OK"


def test_an_empty_ledger_can_be_rotated(world, real_keys):
    created = _create(world.root, "Empty Books")
    result = ledger_keys.rotate_chain_key(world.root, created["company_id"])
    assert result["checkpoint"]["through_entry_number"] == 0 and result["checkpoint"]["status"] == "OK"


def _unchanged(world, company):
    return (_rows(world.company_path, "SELECT * FROM ledger_chain_key"),
            _rows(world.master, "SELECT company_key_id FROM company_key"),
            _rows(world.company_path, "SELECT checkpoint_id FROM ledger_checkpoint"))


def test_only_the_master_rotates(world, company):
    before = _unchanged(world, company)
    clerk = world.session(world.user("clerk"))
    world.grant(clerk.user_id, "OTHER", "Admin")
    with pytest.raises(PermissionDeniedError):
        ledger_keys.rotate_chain_key(clerk, company["company_id"])
    assert _unchanged(world, company) == before


def test_rotation_is_refused_while_the_key_store_is_locked(world, company, monkeypatch):
    before = _unchanged(world, company)
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap(
        fail_unprotect=True)))
    with pytest.raises(KeyStoreLockedError):
        ledger_keys.rotate_chain_key(world.root, company["company_id"])
    assert _unchanged(world, company) == before


def test_rotation_is_refused_when_the_current_key_is_not_available_here(world, company, monkeypatch):
    """A company whose key cannot be opened here takes the key-lost path, never rotation."""
    before = _unchanged(world, company)
    conn = sqlite3.connect(world.master)
    conn.execute("DROP TRIGGER company_key_no_delete")          # simulate a master that lost this company's key
    conn.execute("DELETE FROM company_key")
    conn.commit()
    conn.close()
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap()))
    with pytest.raises(KeyUnavailableError) as caught:
        ledger_keys.rotate_chain_key(world.root, company["company_id"])
    assert str(caught.value) == ledger_keys.ROTATION_NEEDS_KEY
    after = _unchanged(world, company)
    assert after[0] == before[0] and after[2] == before[2]
