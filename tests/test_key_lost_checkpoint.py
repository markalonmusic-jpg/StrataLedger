"""Step 1d part A: the key-lost checkpoint and verification after a key epoch (docs/audit_readiness_design.md 2.6,
2.7 "Key lost"; decisions KS12, KS14-KS16).

* `ledger_keys.start_new_key_epoch` writes a signed 'Key lost' checkpoint (result 'Unverified') in the SAME company
  transaction that retires the lost key and activates the new one: through_entry_number = N (the last entry sealed
  before the epoch), chain_hash = the stored hash of entry N as is, key_id = the new key (it signs the MAC),
  ref_type 'ledger_chain_key', ref_id = the key retired as lost. The master mirror is written afterwards; if it
  fails the epoch stands and the result says so.
* The verifier anchors on the latest valid epoch E: E's MAC checks under its key, ref_id is retired as 'Key lost',
  and the stored hash at N is E's chain_hash (a failure is Broken, never Unverified). Entries 1..N are not hashed
  (a documented limit: a change there is not found); entries after N are verified as before. The result is OK (or
  Broken / Unavailable for the new epoch) with unverified_through = N and unverified_reason 'Key lost', and the
  message names the range without any hash or key.
* The close check warns, never blocks, on the unverified range; rotation after an epoch signs its checkpoint again.
"""
import dataclasses
import shutil
import sqlite3
from pathlib import Path

import pytest

import config
from modules.services import companies, key_store, keys, ledger, ledger_chain, ledger_keys, ledger_verify
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_company_keys import _create, _installation, _two_postable_accounts
from tests.test_key_store import FakeMachineWrap

NOW = "2026-03-20T10:00:00+00:00"


def _context(world, company_id=None):
    return dataclasses.replace(companies.open_company(world.root, company_id or world.company["company_id"]),
                               now=NOW, today="2026-03-20")


def _post(context, cents):
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


def _tamper(world, *statements):
    """Edit the company file as an outside tool would: drop the guarding triggers, then run SQL."""
    conn = sqlite3.connect(world.company_path)
    try:
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name IN "
                                    "('journal_entry', 'journal_line', 'ledger_checkpoint', 'ledger_chain_key', "
                                    "'entry_number_sequence')"
                                    ).fetchall():
            conn.execute(f'DROP TRIGGER "{name}"')
        for statement in statements:
            conn.execute(*statement) if isinstance(statement, tuple) else conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def _fresh_provider(monkeypatch, world):
    provider = key_store.LocalKeyProvider(world.master, FakeMachineWrap())
    monkeypatch.setattr(keys, "_provider", provider)
    return provider


@pytest.fixture
def lost(world, monkeypatch):
    """A company with two posted entries, checked once (an OK checkpoint signed with its key), whose key this
    installation never stored: made under the test key, as if the company file came from elsewhere."""
    world.root = world.session(world.user("root", master=True))
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(lh.TEST_CHAIN_KEY))
    created = _create(world.root)
    world.company = created
    world.company_path = Path(config.BASE_PROJECT_DIR) / created["database_file_path"]
    context = _context(world)
    _post(context, 1000)
    _post(context, 2000)
    assert ledger_verify.verify_ledger(context, mode="full")["status"] == "OK"     # signed with the lost key
    _installation(world, FakeMachineWrap())
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    _fresh_provider(monkeypatch, world)
    return created


def _epoch(world):
    return ledger_keys.start_new_key_epoch(world.root, world.company["company_id"],
                                           confirm_company_code=world.company["company_code"])


def _hash_of(world, number):
    return _rows(world.company_path, "SELECT chain_hash FROM journal_entry WHERE entry_number = ?",
                 (number,))[0]["chain_hash"]


def _key_lost_rows(world):
    return (_rows(world.company_path, "SELECT * FROM ledger_checkpoint WHERE kind = 'Key lost'"),
            _rows(world.master, "SELECT * FROM chain_checkpoint WHERE kind = 'Key lost'"))


def _full(world):
    return ledger_verify.verify_ledger(_context(world), mode="full")


def _incremental(world):
    return ledger_verify.verify_ledger(_context(world), mode="incremental")


# --- The checkpoint the epoch writes -------------------------------------------------------------------------------

def test_the_epoch_writes_one_signed_key_lost_checkpoint_in_the_file_and_the_mirror(world, lost):
    [old] = _rows(world.company_path, "SELECT key_id FROM ledger_chain_key")
    result = _epoch(world)
    [row], [mirror] = _key_lost_rows(world)
    expected = {"kind": "Key lost", "scope": None, "result": "Unverified", "through_entry_number": 2,
                "chain_hash": _hash_of(world, 2), "first_broken_entry_number": None, "key_id": result["new_key_id"],
                "ref_type": "ledger_chain_key", "ref_id": old["key_id"], "created_by": world.root.user_id}
    assert {k: row[k] for k in expected} == expected
    assert {k: mirror[k] for k in expected} == expected
    assert mirror["company_checkpoint_id"] == row["checkpoint_id"] and mirror["recorded_from"] == "Company file"
    assert mirror["mac"] == row["mac"]
    new_key = keys.get_provider().get_key(world.company["company_id"], result["new_key_id"]).use_for_hmac()
    assert row["mac"] == ledger_chain.checkpoint_mac(new_key, world.company["company_code"], row)
    assert (result["checkpoint_id"], result["recorded_in"]) == (row["checkpoint_id"], ["company", "master"])
    assert "checkpoint_error" not in result


def test_an_empty_ledger_epoch_records_through_zero_and_leaves_nothing_unverified(world, monkeypatch):
    world.root = world.session(world.user("root", master=True))
    monkeypatch.setattr(keys, "_provider", keys.FixedKeyProvider(lh.TEST_CHAIN_KEY))
    world.company = _create(world.root, "Empty Books")
    world.company_path = Path(config.BASE_PROJECT_DIR) / world.company["database_file_path"]
    _installation(world, FakeMachineWrap())
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    _fresh_provider(monkeypatch, world)
    _epoch(world)
    [row], [_mirror] = _key_lost_rows(world)
    assert (row["through_entry_number"], row["chain_hash"]) == (0, None)
    result = _full(world)
    assert (result["status"], result["unverified_through"], result["unverified_reason"]) == ("OK", None, None)


def test_no_epoch_exists_without_its_checkpoint(world, lost, monkeypatch):
    """A failure inside the company transaction undoes the retirement and the new key together."""
    [old] = _rows(world.company_path, "SELECT key_id FROM ledger_chain_key")

    def failing(*args, **kwargs):
        raise RuntimeError("disk full")
    monkeypatch.setattr(ledger_chain, "checkpoint_mac", failing)
    with pytest.raises(RuntimeError):
        _epoch(world)
    assert _rows(world.company_path, "SELECT key_id, is_active FROM ledger_chain_key") == [
        {"key_id": old["key_id"], "is_active": 1}]
    assert _key_lost_rows(world) == ([], [])


def test_a_failed_mirror_keeps_the_epoch_and_says_so(world, lost, monkeypatch):
    real = ledger_verify._insert_mirror

    def failing(*args, **kwargs):
        raise RuntimeError("master busy")
    monkeypatch.setattr(ledger_verify, "_insert_mirror", failing)
    result = _epoch(world)
    assert result["checkpoint_error"] == ledger_verify.KEY_LOST_CHECKPOINT_NOT_MIRRORED
    assert result["recorded_in"] == ["company"]
    [active] = _rows(world.company_path, "SELECT key_id FROM ledger_chain_key WHERE is_active = 1")
    assert active["key_id"] == result["new_key_id"]
    rows, mirrors = _key_lost_rows(world)
    assert len(rows) == 1 and mirrors == []
    monkeypatch.setattr(ledger_verify, "_insert_mirror", real)
    assert _full(world)["unverified_through"] == 2                  # the file's record is used


# --- Verification after an epoch -----------------------------------------------------------------------------------

@pytest.mark.parametrize("check", [_full, _incremental])
def test_after_an_epoch_both_checks_are_ok_with_the_unverified_range(world, lost, check):
    _epoch(world)
    result = check(world)
    assert (result["status"], result["through_entry_number"]) == ("OK", 2)
    assert (result["unverified_through"], result["unverified_reason"]) == (2, "Key lost")
    _post(_context(world), 3000)
    result = check(world)
    assert (result["status"], result["through_entry_number"], result["unverified_through"]) == ("OK", 3, 2)
    assert result["chain_hash"] == _hash_of(world, 3)


def test_without_an_epoch_there_is_no_unverified_range(world, lost):
    result = ledger_verify.verify_ledger(_context(world), mode="full")       # the key is simply missing
    assert result["status"] == "Unavailable"
    assert (result["unverified_through"], result["unverified_reason"]) == (None, None)


def test_incremental_continues_from_an_ok_checkpoint_after_the_epoch(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    assert _full(world)["status"] == "OK"
    _post(_context(world), 4000)
    result = _incremental(world)
    assert (result["status"], result["scope"], result["through_entry_number"], result["unverified_through"]) == (
        "OK", "Incremental", 4, 2)


@pytest.mark.parametrize("check", [_full, _incremental])
def test_a_changed_entry_after_the_epoch_is_broken_at_that_entry(world, lost, check):
    _epoch(world)
    entry_id = _post(_context(world), 3000)
    _post(_context(world), 4000)
    _tamper(world, ("UPDATE journal_line SET memo = 'changed' WHERE entry_id = ?", (entry_id,)))
    result = check(world)
    assert result["status"] == "Broken"
    assert (result["first_broken"]["entry_number"], result["first_broken"]["reason"]) == (3, "Hash")
    assert result["unverified_through"] == 2


def test_a_changed_entry_before_the_epoch_is_not_found(world, lost):
    """Documented limit (audit design 2.7): entries sealed with the lost key cannot be verified at all."""
    _epoch(world)
    _post(_context(world), 3000)
    _tamper(world, "UPDATE journal_line SET memo = 'changed' WHERE entry_id = (SELECT entry_id FROM journal_entry "
                   "WHERE entry_number = 1)")
    result = _full(world)
    assert (result["status"], result["unverified_through"]) == ("OK", 2)


@pytest.mark.parametrize("check", [_full, _incremental])
def test_a_changed_hash_at_the_epoch_entry_is_broken(world, lost, check):
    _epoch(world)
    _post(_context(world), 3000)
    _tamper(world, ("UPDATE journal_entry SET chain_hash = ? WHERE entry_number = 2", ("f" * 64,)))
    result = check(world)
    assert (result["status"], result["first_broken"]["entry_number"], result["first_broken"]["reason"]) == (
        "Broken", 2, "Hash")
    assert result["unverified_through"] is None


def test_a_cut_ledger_before_the_epoch_entry_is_truncated(world, lost):
    _epoch(world)
    _tamper(world, "DELETE FROM journal_line WHERE entry_id = (SELECT entry_id FROM journal_entry "
                   "WHERE entry_number = 2)", "DELETE FROM journal_entry WHERE entry_number = 2")
    result = _full(world)
    assert (result["status"], result["first_broken"]["entry_number"], result["first_broken"]["reason"]) == (
        "Broken", 2, "Truncated")


def _forge_key_lost(world, *, ref_id=None, sign=True, through=2):
    """Add a Key lost row to the company file, signed with the active (new) key unless sign is False."""
    [active] = _rows(world.company_path, "SELECT key_id FROM ledger_chain_key WHERE is_active = 1")
    row = {"created_at": "2026-03-21T00:00:00+00:00", "created_by": world.root.user_id, "kind": "Key lost",
           "scope": None, "result": "Unverified", "through_entry_number": through,
           "chain_hash": _hash_of(world, through), "first_broken_entry_number": None, "key_id": active["key_id"],
           "ref_type": "ledger_chain_key", "ref_id": ref_id if ref_id is not None else active["key_id"]}
    key = keys.get_provider().get_key(world.company["company_id"], active["key_id"]).use_for_hmac()
    row["mac"] = ledger_chain.checkpoint_mac(key, world.company["company_code"], row) if sign else "e" * 64
    _tamper(world, (f"INSERT INTO ledger_checkpoint ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                    tuple(row.values())))


def test_an_unsigned_key_lost_row_is_a_marker_break(world, lost):
    epoch = _epoch(world)
    _post(_context(world), 3000)
    _forge_key_lost(world, ref_id=epoch["old_key_id"], sign=False, through=3)
    result = _full(world)
    assert (result["status"], result["first_broken"]["reason"]) == ("Broken", "Marker")
    assert result["unverified_through"] is None


def test_a_key_lost_row_naming_an_active_key_is_a_marker_break(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    _forge_key_lost(world, through=3)                             # well signed, but its "lost" key is the active one
    result = _full(world)
    assert (result["status"], result["first_broken"]["reason"]) == ("Broken", "Marker")


def test_a_forged_epoch_without_a_lost_key_is_a_marker_break(world, real_keys_company):
    """A company whose key was never lost: a signed Key lost row cannot hide its history."""
    _forge_key_lost(world)
    assert (_full(world)["status"], _full(world)["first_broken"]["reason"]) == ("Broken", "Marker")


@pytest.fixture
def real_keys_company(world, monkeypatch):
    world.root = world.session(world.user("root", master=True))
    _installation(world, FakeMachineWrap())
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    _fresh_provider(monkeypatch, world)
    world.company = _create(world.root)
    world.company_path = Path(config.BASE_PROJECT_DIR) / world.company["database_file_path"]
    _post(_context(world), 1000)
    _post(_context(world), 2000)
    return world.company


def test_a_forged_mirror_key_lost_row_is_a_marker_break(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    [row], _mirrors = _key_lost_rows(world)
    conn = sqlite3.connect(world.master)
    try:
        conn.execute("INSERT INTO chain_checkpoint (company_id, company_checkpoint_id, recorded_from, created_at, "
                     "created_by, kind, scope, result, through_entry_number, chain_hash, key_id, ref_type, ref_id, "
                     "mac) VALUES (?, 99, 'Company file', ?, 1, 'Key lost', NULL, 'Unverified', 3, ?, ?, "
                     "'ledger_chain_key', ?, ?)",
                     (world.company["company_id"], NOW, _hash_of(world, 3), row["key_id"], row["ref_id"], "e" * 64))
        conn.commit()
    finally:
        conn.close()
    assert (_full(world)["status"], _full(world)["first_broken"]["reason"]) == ("Broken", "Marker")


def _lose_the_active_key(world, monkeypatch):
    """Make the active key unavailable here, as a lost master copy would."""
    [active] = _rows(world.company_path, "SELECT fingerprint FROM ledger_chain_key WHERE is_active = 1")
    conn = sqlite3.connect(world.master)
    try:
        conn.execute("DROP TRIGGER company_key_no_delete")
        conn.execute("DELETE FROM company_key WHERE fingerprint = ?", (active["fingerprint"],))
        conn.commit()
    finally:
        conn.close()
    _fresh_provider(monkeypatch, world)


def test_two_epochs_only_the_latest_counts(world, lost, monkeypatch):
    _epoch(world)
    _post(_context(world), 3000)
    _lose_the_active_key(world, monkeypatch)
    second = _epoch(world)
    assert second["unverifiable_through"] == 3
    _post(_context(world), 4000)
    for check in (_full, _incremental):
        result = check(world)
        assert (result["status"], result["through_entry_number"], result["unverified_through"]) == ("OK", 4, 3)


def test_an_older_ok_checkpoint_signed_with_the_lost_key_no_longer_makes_it_unavailable(world, lost):
    """The fixture checked the ledger with the lost key (file and mirror). After the epoch it is ignored."""
    assert _rows(world.company_path, "SELECT 1 FROM ledger_checkpoint WHERE kind = 'Verify' AND result = 'OK'")
    _epoch(world)
    assert _full(world)["status"] == "OK" and _incremental(world)["status"] == "OK"


def test_a_cut_tail_after_the_epoch_is_still_truncated(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    _post(_context(world), 4000)
    assert _full(world)["status"] == "OK"                         # an OK checkpoint through JE-000004
    _tamper(world, "DELETE FROM journal_line WHERE entry_id = (SELECT entry_id FROM journal_entry "
                   "WHERE entry_number = 4)", "DELETE FROM journal_entry WHERE entry_number = 4",
            "UPDATE entry_number_sequence SET last_number = 3")
    result = _full(world)
    assert (result["status"], result["first_broken"]["entry_number"], result["first_broken"]["reason"]) == (
        "Broken", 4, "Truncated")


# --- What the result says (Q1) -------------------------------------------------------------------------------------

def _close_check(world, mode):
    context = _context(world)
    conn = sqlite3.connect(context.company_db_path)
    conn.row_factory = sqlite3.Row
    try:
        return ledger_verify.integrity_check(conn, context, "March 2026", mode)
    finally:
        conn.close()


def _rotation_result(world):
    return ledger_keys.rotate_chain_key(world.root, world.company["company_id"])["checkpoint"]


SOURCES = {"full": _full, "incremental": _incremental, "close check": lambda w: _close_check(w, "block"),
           "rotation": _rotation_result}


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("posted_after", [0, 1])
def test_the_message_names_the_unverified_range_and_holds_no_secret(world, lost, source, posted_after):
    epoch = _epoch(world)
    for i in range(posted_after):
        _post(_context(world), 3000 + i)
    result = SOURCES[source](world)
    message = result["message"]
    assert message and "JE-000001 to JE-000002 cannot be verified because their key was lost" in message
    if source != "close check":
        assert result["unverified_through"] == 2
    provider = keys.get_provider()
    secrets = [lh.TEST_CHAIN_KEY.hex(), provider.get_key(world.company["company_id"],
                                                         epoch["new_key_id"]).use_for_hmac().hex()]
    secrets += [r["chain_hash"] for r in _rows(world.company_path, "SELECT chain_hash FROM journal_entry")]
    secrets += [r["mac"] for r in _rows(world.company_path, "SELECT mac FROM ledger_checkpoint")]
    for secret in secrets:
        assert secret not in message


def test_the_ok_message_says_which_entries_were_verified(world, lost):
    _epoch(world)
    assert _full(world)["message"] == ("Entries JE-000001 to JE-000002 cannot be verified because their key was "
                                       "lost. No entries have been posted since, so there was nothing else to check.")
    _post(_context(world), 3000)
    _post(_context(world), 4000)
    assert _full(world)["message"] == ("Entries JE-000001 to JE-000002 cannot be verified because their key was "
                                       "lost. Entries JE-000003 to JE-000004 were verified and match their seals.")


def test_a_broken_message_after_an_epoch_names_both_ranges(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    entry_id = _post(_context(world), 4000)
    _tamper(world, ("UPDATE journal_line SET memo = 'changed' WHERE entry_id = ?", (entry_id,)))
    message = _full(world)["message"]
    assert "Ledger check failed at entry JE-000004" in message
    assert "Entries JE-000003 to JE-000003 are intact." not in message
    assert "Entry JE-000003 before it is intact." in message
    assert "Entries JE-000001 to JE-000002 cannot be verified because their key was lost." in message
    assert "Entries before it are intact" not in message


# --- The close check (KS15) ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["warn", "block"])
def test_the_close_check_warns_and_never_blocks_on_the_unverified_range(world, lost, mode):
    _epoch(world)
    check = _close_check(world, mode)
    assert (check["ok"], check["mode"]) == (False, "warn")
    assert check["message"] == ledger_verify.unverified_note(2) + (
        " No entries have been posted since, so there was nothing else to check.")


def test_a_broken_new_epoch_still_follows_the_close_check_mode(world, lost):
    _epoch(world)
    entry_id = _post(_context(world), 3000)
    _tamper(world, ("UPDATE journal_line SET memo = 'changed' WHERE entry_id = ?", (entry_id,)))
    check = _close_check(world, "block")
    assert (check["ok"], check["mode"]) == (False, "block")
    assert ledger_verify.unverified_note(2) in check["message"]


# --- Rotation after an epoch (KS16) --------------------------------------------------------------------------------

def test_rotation_after_an_epoch_signs_its_checkpoint_again(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    rotated = ledger_keys.rotate_chain_key(world.root, world.company["company_id"])
    checkpoint = rotated["checkpoint"]
    assert (checkpoint["status"], checkpoint["recorded_in"], checkpoint["unverified_through"]) == (
        "OK", ["company", "master"], 2)
    [row] = _rows(world.company_path, "SELECT * FROM ledger_checkpoint WHERE kind = 'Key rotation'")
    assert (row["result"], row["through_entry_number"], row["key_id"]) == ("OK", 3, rotated["new_key_id"])
    _post(_context(world), 4000)
    result = _full(world)
    assert (result["status"], result["through_entry_number"], result["unverified_through"]) == ("OK", 4, 2)


def test_the_mirror_writer_checks_the_master_itself(world, lost):
    """Rule 10: mirror_key_lost_checkpoint writes the master only as the Master; anyone else gets no copy."""
    _epoch(world)
    [row], [_mirror] = _key_lost_rows(world)
    clerk = world.session(world.user("clerk"))
    result = ledger_verify.mirror_key_lost_checkpoint(clerk, _context(world), row)
    assert result["checkpoint_error"] == ledger_verify.KEY_LOST_CHECKPOINT_NOT_MIRRORED
    assert len(_key_lost_rows(world)[1]) == 1
    denied = _rows(world.master, "SELECT user_id FROM auth_event WHERE event_type = 'Denied'")
    assert {"user_id": clerk.user_id} in denied


# --- Review of Step 1d ---------------------------------------------------------------------------------------------

def test_an_unavailable_result_after_an_epoch_still_names_the_range(world, lost, monkeypatch):
    _epoch(world)
    _post(_context(world), 3000)
    _lose_the_active_key(world, monkeypatch)
    result = _full(world)
    assert (result["status"], result["unverified_through"], result["unverified_reason"]) == (
        "Unavailable", 2, "Key lost")
    assert ledger_verify.unverified_note(2) in result["message"]
    assert ledger_verify.unverified_note(2) in _close_check(world, "block")["message"]


def test_an_older_copy_restored_after_an_epoch_is_broken_not_unavailable(world, lost, tmp_path):
    older = tmp_path / "before_the_epoch.db"
    shutil.copy2(world.company_path, older)
    _epoch(world)
    _post(_context(world), 3000)
    shutil.copy2(older, world.company_path)                 # the mirror still holds the Key lost row
    result = _full(world)
    assert (result["status"], result["first_broken"]["reason"]) == ("Broken", "Marker")
    assert "older copy" in result["first_broken"]["detail"]


def test_deleting_every_key_lost_record_is_a_marker_break(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    assert _full(world)["status"] == "OK"
    _tamper(world, "DELETE FROM ledger_checkpoint WHERE kind = 'Key lost'")
    conn = sqlite3.connect(world.master)
    try:
        conn.execute("DROP TRIGGER chain_checkpoint_no_delete")
        conn.execute("DELETE FROM chain_checkpoint WHERE kind = 'Key lost'")
        conn.commit()
    finally:
        conn.close()
    for check in (_full, _incremental):
        result = check(world)
        assert (result["status"], result["first_broken"]["entry_number"], result["first_broken"]["reason"]) == (
            "Broken", 1, "Marker")


def test_a_deleted_entry_inside_the_unverified_range_is_a_gap(world, lost):
    _epoch(world)
    _tamper(world, "DELETE FROM journal_line WHERE entry_id = (SELECT entry_id FROM journal_entry "
                   "WHERE entry_number = 1)", "DELETE FROM journal_entry WHERE entry_number = 1")
    result = _full(world)
    assert (result["status"], result["first_broken"]["entry_number"], result["first_broken"]["reason"]) == (
        "Broken", 1, "Gap")


def test_a_key_lost_row_naming_a_rotated_key_is_a_marker_break(world, lost):
    epoch = _epoch(world)
    _post(_context(world), 3000)
    ledger_keys.rotate_chain_key(world.root, world.company["company_id"])     # the epoch key is now 'Rotation'
    _forge_key_lost(world, ref_id=epoch["new_key_id"], through=3)
    assert (_full(world)["status"], _full(world)["first_broken"]["reason"]) == ("Broken", "Marker")


def test_a_key_lost_row_naming_no_key_is_a_marker_break(world, lost):
    _epoch(world)
    _post(_context(world), 3000)
    _forge_key_lost(world, ref_id=999, through=3)
    assert (_full(world)["status"], _full(world)["first_broken"]["reason"]) == ("Broken", "Marker")
