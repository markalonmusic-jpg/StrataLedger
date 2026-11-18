"""The key-lost epoch anchor when the file's and the mirror's latest 'Key lost' rows are at the same entry (Codex
keys/chain finding; owner 2026-11-18).

Two key losses with no posting between them give two 'Key lost' checkpoints with the same through_entry_number.
`ledger_verify._epoch_anchor` used the file's row on such a tie, so a copy of the file restored from before the
second loss anchored on the stale first checkpoint and the check said OK (or Unavailable) instead of Broken. On a
tie the master's mirror now wins when the two rows differ (key_id or MAC), unless the file's latest row retired the
mirror's key (its ref_id is the mirror's key_id: the later loss's mirror write failed, so the file is further on).
That test reads only the file's latest row, whose MAC the check verifies next (ref_id is signed), so a decoy row
copied from the master into the file cannot sway it (step-reviewer finding on 7a704a2). The same event keeps the
file's row, so its wording ("the company file's record") is unchanged.
"""
import shutil
import sqlite3

import pytest

from modules.services import ledger_verify
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_key_lost_checkpoint import (  # noqa: F401  (fixture and helpers)
    _context, _epoch, _full, _incremental, _key_lost_rows, _lose_the_active_key, _post, _rows, lost)


def _two_epochs_at_the_same_entry(world, monkeypatch, tmp_path):
    """Epoch 1 at JE-000002, a copy of the file, then epoch 2 at JE-000002 too. Returns the copy's path."""
    _epoch(world)
    between = tmp_path / "between_the_epochs.db"
    shutil.copy2(world.company_path, between)
    _lose_the_active_key(world, monkeypatch)
    second = _epoch(world)
    assert second["unverifiable_through"] == 2
    rows, mirrors = _key_lost_rows(world)
    assert [r["through_entry_number"] for r in rows] == [2, 2]
    assert [m["through_entry_number"] for m in mirrors] == [2, 2]
    return between


@pytest.mark.parametrize("check", [_full, _incremental])
def test_a_copy_restored_from_between_two_epochs_at_the_same_entry_is_an_older_copy(world, lost, monkeypatch,
                                                                                    tmp_path, check):
    between = _two_epochs_at_the_same_entry(world, monkeypatch, tmp_path)
    shutil.copy2(between, world.company_path)                     # the mirror still holds the second Key lost row
    result = check(world)
    assert (result["status"], result["first_broken"]["reason"]) == ("Broken", "Marker")
    assert "older copy" in result["first_broken"]["detail"]


def _insert_decoy(path, mirror, checkpoint_id):
    """Copy the master's latest Key lost row into the file under a lower id: everything an attacker who edits only
    the company file can do with what the master shows."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("INSERT INTO ledger_checkpoint (checkpoint_id, created_at, created_by, kind, scope, result, "
                     "through_entry_number, chain_hash, first_broken_entry_number, key_id, ref_type, ref_id, mac) "
                     "VALUES (?, ?, NULL, 'Key lost', NULL, 'Unverified', ?, ?, NULL, ?, 'ledger_chain_key', ?, ?)",
                     (checkpoint_id, mirror["created_at"], mirror["through_entry_number"], mirror["chain_hash"],
                      mirror["key_id"], mirror["ref_id"], mirror["mac"]))
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("check", [_full, _incremental])
def test_a_decoy_copy_of_the_mirror_row_does_not_hide_the_older_copy(world, lost, monkeypatch, tmp_path, check):
    between = _two_epochs_at_the_same_entry(world, monkeypatch, tmp_path)
    shutil.copy2(between, world.company_path)
    _rows_, mirrors = _key_lost_rows(world)
    _insert_decoy(world.company_path, mirrors[-1], -1)
    result = check(world)
    assert (result["status"], result["first_broken"]["reason"]) == ("Broken", "Marker")
    assert "older copy" in result["first_broken"]["detail"]


@pytest.mark.parametrize("check", [_full, _incremental])
def test_the_current_file_after_two_epochs_at_the_same_entry_is_ok(world, lost, monkeypatch, tmp_path, check):
    _two_epochs_at_the_same_entry(world, monkeypatch, tmp_path)
    _post(_context(world), 3000)
    result = check(world)
    assert (result["status"], result["through_entry_number"], result["unverified_through"]) == ("OK", 3, 2)


def test_on_a_tie_the_same_event_keeps_the_files_record():
    row = {"checkpoint_id": 7, "through_entry_number": 2, "key_id": 5, "ref_id": 4, "mac": "m2", "kind": "Key lost"}
    mirror = dict(row, chain_checkpoint_id=40, company_checkpoint_id=7)
    assert ledger_verify._epoch_anchor(_conn_with(row), mirror)[0] == "company"


@pytest.mark.parametrize("changed", [{"key_id": 6}, {"mac": "other"}])
def test_on_a_tie_a_different_mirror_row_wins(changed):
    row = {"checkpoint_id": 7, "through_entry_number": 2, "key_id": 5, "ref_id": 4, "mac": "m2", "kind": "Key lost"}
    mirror = dict(row, chain_checkpoint_id=40, **changed)
    assert ledger_verify._epoch_anchor(_conn_with(row), mirror) == ("master", mirror)


def test_on_a_tie_the_files_latest_row_that_retired_the_mirrors_key_is_further_on():
    """The later loss's mirror write failed: the file's latest row (key 5) retired the mirror's key (4)."""
    earlier = {"checkpoint_id": 6, "through_entry_number": 2, "key_id": 4, "ref_id": 3, "mac": "m1", "kind": "Key lost"}
    latest = {"checkpoint_id": 7, "through_entry_number": 2, "key_id": 5, "ref_id": 4, "mac": "m2", "kind": "Key lost"}
    mirror = dict(earlier, chain_checkpoint_id=40)
    assert ledger_verify._epoch_anchor(_conn_with(earlier, latest), mirror) == ("company", latest)


def test_on_a_tie_a_matching_row_elsewhere_in_the_file_does_not_count():
    """Only the file's latest row decides: a copy of the mirror's row under a lower id is ignored."""
    stale = {"checkpoint_id": 7, "through_entry_number": 2, "key_id": 4, "ref_id": 3, "mac": "m1", "kind": "Key lost"}
    mirror = {"through_entry_number": 2, "key_id": 5, "ref_id": 4, "mac": "m2", "kind": "Key lost"}
    decoy = dict(mirror, checkpoint_id=-1)
    assert ledger_verify._epoch_anchor(_conn_with(decoy, stale), mirror) == ("master", mirror)


def test_a_mirror_behind_the_file_still_loses():
    row = {"checkpoint_id": 7, "through_entry_number": 3, "key_id": 5, "ref_id": 4, "mac": "m2", "kind": "Key lost"}
    mirror = dict(row, through_entry_number=2, key_id=4, ref_id=3, mac="m1")
    assert ledger_verify._epoch_anchor(_conn_with(row), mirror)[0] == "company"


def test_with_no_file_row_the_mirror_is_used_and_with_neither_there_is_none():
    mirror = {"through_entry_number": 0, "key_id": 4, "ref_id": 3, "mac": "m1", "kind": "Key lost"}
    assert ledger_verify._epoch_anchor(_conn_with(None), mirror) == ("master", mirror)
    assert ledger_verify._epoch_anchor(_conn_with(None), None) is None


def test_the_second_epochs_mirror_failing_keeps_the_files_newer_row(world, lost, monkeypatch, tmp_path):
    """File ahead of the mirror at a tie (the second epoch's mirror write failed): the file's row is the newer
    event, its key is in the file, so the check is OK, not an older copy."""
    _epoch(world)
    _lose_the_active_key(world, monkeypatch)

    def failing(*args, **kwargs):
        raise RuntimeError("master busy")
    real = ledger_verify._insert_mirror
    monkeypatch.setattr(ledger_verify, "_insert_mirror", failing)
    _epoch(world)
    monkeypatch.setattr(ledger_verify, "_insert_mirror", real)
    rows, mirrors = _key_lost_rows(world)
    assert len(rows) == 2 and len(mirrors) == 1
    result = _full(world)
    assert (result["status"], result["unverified_through"]) == ("OK", 2)


def _conn_with(*rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ledger_checkpoint (checkpoint_id INTEGER PRIMARY KEY, kind TEXT, "
                 "through_entry_number INTEGER, key_id INTEGER, ref_id INTEGER, mac TEXT)")
    for row in rows:
        if row is None:
            continue
        conn.execute("INSERT INTO ledger_checkpoint (checkpoint_id, kind, through_entry_number, key_id, ref_id, "
                     "mac) VALUES (:checkpoint_id, :kind, :through_entry_number, :key_id, :ref_id, :mac)", row)
    return conn
