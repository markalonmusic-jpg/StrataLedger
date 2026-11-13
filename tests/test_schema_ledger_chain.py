"""Phase 2.5 step 1b: baseline schema for the tamper-evident ledger chain (docs/audit_readiness_design.md 2, 3, 14).

The schema enforces only shape (CHECKs, the unique seal) and immutability (locks, append-only tables). It does
not check the previous hash or the active key: the posting service computes the chain and verification catches
mismatches (owner decision).
"""
import json
import sqlite3

import pytest

import modules.database as database
from modules.services import ledger_chain
from tests import ledger_helpers as lh
from tests.ledger_helpers import make_entry, make_reversal, post, posted_entry, rejects

CHAIN = ("chain_version", "chain_key_id", "chain_prev_hash", "chain_hash")
TS = "2026-03-15 10:00:00"
POSTED = "Posted journal entries"


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def entry(conn, entry_id):
    return dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone())


def next_number(conn):
    conn.execute("UPDATE entry_number_sequence SET last_number = last_number + 1 WHERE id = 1")
    return conn.execute("SELECT last_number FROM entry_number_sequence WHERE id = 1").fetchone()[0]


def post_sql(conn, entry_id, number, seal):
    """The posting UPDATE with explicit chain values (any of them may be overridden by the test)."""
    return (
        "UPDATE journal_entry SET is_posted = 1, entry_number = ?, posted_by = 1, posted_at = ?, "
        "chain_version = ?, chain_key_id = ?, chain_prev_hash = ?, chain_hash = ? WHERE entry_id = ?",
        (number, TS, seal["chain_version"], seal["chain_key_id"], seal["chain_prev_hash"], seal["chain_hash"],
         entry_id),
    )


def draft(conn):
    return make_entry(conn, [(100, 0), (0, 100)])


# --- journal_entry chain columns -------------------------------------------------------------------------

def test_drafts_have_no_seal(conn):
    row = entry(conn, draft(conn))
    assert all(row[column] is None for column in CHAIN)


def test_a_sealed_post_is_accepted(conn):
    entry_id = draft(conn)
    number = next_number(conn)
    seal = lh.seal_columns(conn, entry_id, number, 1, TS)
    conn.execute(*post_sql(conn, entry_id, number, seal))
    row = entry(conn, entry_id)
    assert {c: row[c] for c in CHAIN} == seal and row["chain_prev_hash"] == ledger_chain.GENESIS


@pytest.mark.parametrize("column", CHAIN)
def test_posting_with_a_chain_column_missing_is_refused(conn, column):
    entry_id = draft(conn)
    number = next_number(conn)
    seal = {**lh.seal_columns(conn, entry_id, number, 1, TS), column: None}
    assert rejects(conn, *post_sql(conn, entry_id, number, seal))


def test_an_unsealed_post_is_refused(conn):
    entry_id = draft(conn)
    number = next_number(conn)
    assert rejects(conn, "UPDATE journal_entry SET is_posted = 1, entry_number = ?, posted_by = 1, posted_at = ? "
                         "WHERE entry_id = ?", (number, TS, entry_id))


@pytest.mark.parametrize("column", CHAIN)
def test_a_draft_cannot_carry_a_seal(conn, column):
    entry_id = draft(conn)
    value = {"chain_version": 1, "chain_key_id": lh.ensure_test_chain_key(conn),
             "chain_prev_hash": "0" * 64, "chain_hash": "a" * 64}[column]
    assert rejects(conn, f"UPDATE journal_entry SET {column} = ? WHERE entry_id = ?", (value, entry_id))


@pytest.mark.parametrize("column", ["chain_hash", "chain_prev_hash"])
@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, "a" * 63 + " ", ""])
def test_hash_columns_take_64_lowercase_hex(conn, column, bad):
    entry_id = draft(conn)
    number = next_number(conn)
    seal = {**lh.seal_columns(conn, entry_id, number, 1, TS), column: bad}
    assert rejects(conn, *post_sql(conn, entry_id, number, seal))


@pytest.mark.parametrize("version", [0, 2])
def test_chain_version_is_1(conn, version):
    entry_id = draft(conn)
    number = next_number(conn)
    seal = {**lh.seal_columns(conn, entry_id, number, 1, TS), "chain_version": version}
    assert rejects(conn, *post_sql(conn, entry_id, number, seal))


def ensure_test_chain_key_must_name_a_key(conn):
    entry_id = draft(conn)
    number = next_number(conn)
    seal = {**lh.seal_columns(conn, entry_id, number, 1, TS), "chain_key_id": 999}
    assert rejects(conn, *post_sql(conn, entry_id, number, seal))


def test_a_seal_cannot_repeat(conn):
    first = posted_entry(conn)
    second = draft(conn)
    number = next_number(conn)
    seal = {**lh.seal_columns(conn, second, number, 1, TS), "chain_hash": entry(conn, first)["chain_hash"]}
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        conn.execute(*post_sql(conn, second, number, seal))


def test_the_schema_does_not_check_the_previous_hash(conn):
    """Owner decision: the service computes the link; verification (not a trigger) catches a wrong one."""
    posted_entry(conn)
    entry_id = draft(conn)
    number = next_number(conn)
    seal = {**lh.seal_columns(conn, entry_id, number, 1, TS), "chain_prev_hash": "c" * 64}
    assert not rejects(conn, *post_sql(conn, entry_id, number, seal))


@pytest.mark.parametrize("column, value", [
    ("chain_version", None), ("chain_key_id", None), ("chain_prev_hash", "d" * 64), ("chain_hash", "e" * 64),
])
def test_chain_columns_are_locked_once_posted(conn, column, value):
    entry_id = posted_entry(conn)
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute(f"UPDATE journal_entry SET {column} = ? WHERE entry_id = ?", (value, entry_id))


def test_lock_trigger_names_the_chain_columns(conn):
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'journal_entry_lock_posted'").fetchone()[0]
    for column in CHAIN:
        assert f"NEW.{column} IS OLD.{column}" in sql


def test_a_void_reversal_still_voids_a_sealed_original(conn):
    original = posted_entry(conn)
    before = entry(conn, original)
    post(conn, make_reversal(conn, original, "Void"))
    after = entry(conn, original)
    assert after == {**before, "is_void": 1}
    assert after["chain_hash"] == before["chain_hash"]


def test_the_helper_chain_links_each_entry_to_the_previous(conn):
    first, second = posted_entry(conn), posted_entry(conn)
    assert entry(conn, first)["chain_prev_hash"] == ledger_chain.GENESIS
    assert entry(conn, second)["chain_prev_hash"] == entry(conn, first)["chain_hash"]


# --- ledger_chain_key ------------------------------------------------------------------------------------------

def key_sql(fingerprint, *, active=1, retired_at=None, reason=None):
    return ("INSERT INTO ledger_chain_key (fingerprint, created_at, created_by, is_active, retired_at, retire_reason) "
            "VALUES (?, '2026-01-01T00:00:00+00:00', 1, ?, ?, ?)", (fingerprint, active, retired_at, reason))


def fp(n):
    return ledger_chain.fingerprint(bytes([n]) * 32)


def test_a_key_row_is_accepted_and_audited(conn):
    lh.set_user(conn, 1)
    key_id = conn.execute(*key_sql(fp(1))).lastrowid
    log = conn.execute("SELECT action, new_value FROM audit_log WHERE table_name = 'ledger_chain_key' "
                       "AND record_id = ?", (key_id,)).fetchall()
    assert [r["action"] for r in log] == ["Insert"] and json.loads(log[0]["new_value"])["fingerprint"] == fp(1)


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "a" * 65, "z" * 64, None])
def test_key_fingerprint_is_64_lowercase_hex(conn, bad):
    assert rejects(conn, *key_sql(bad))


def test_fingerprints_are_unique(conn):
    conn.execute(*key_sql(fp(1)))
    assert rejects(conn, *key_sql(fp(1), active=0, retired_at="2026-02-01T00:00:00+00:00", reason="Rotation"))


def test_only_one_key_is_active(conn):
    conn.execute(*key_sql(fp(1)))
    assert rejects(conn, *key_sql(fp(2)))
    assert not rejects(conn, *key_sql(fp(3), active=0, retired_at="2026-02-01T00:00:00+00:00", reason="Rotation"))


@pytest.mark.parametrize("active, retired_at, reason", [
    (1, "2026-02-01T00:00:00+00:00", "Rotation"),     # active but retired
    (0, None, None),                                  # inactive without a date
    (0, "2026-02-01T00:00:00+00:00", None),           # date without a reason
    (0, "2026-02-01T00:00:00+00:00", "Lost it"),      # unknown reason
])
def test_active_retired_and_reason_go_together(conn, active, retired_at, reason):
    assert rejects(conn, *key_sql(fp(1), active=active, retired_at=retired_at, reason=reason))


def test_keys_cannot_be_deleted(conn):
    key_id = conn.execute(*key_sql(fp(1))).lastrowid
    assert rejects(conn, "DELETE FROM ledger_chain_key WHERE key_id = ?", (key_id,))


RETIRE = "UPDATE ledger_chain_key SET is_active = 0, retired_at = '2026-02-01T00:00:00+00:00', retire_reason = ? WHERE key_id = ?"


@pytest.mark.parametrize("reason", ["Rotation", "Key lost", "Compromised"])
def test_a_key_can_be_retired_once(conn, reason):
    key_id = conn.execute(*key_sql(fp(1))).lastrowid
    conn.execute(RETIRE, (reason, key_id))
    assert tuple(conn.execute("SELECT is_active, retire_reason FROM ledger_chain_key WHERE key_id = ?",
                        (key_id,)).fetchone()) == (0, reason)
    assert rejects(conn, "UPDATE ledger_chain_key SET retire_reason = 'Compromised', retired_at = '2026-03-01T00:00:00+00:00' "
                         "WHERE key_id = ?", (key_id,))
    assert not rejects(conn, *key_sql(fp(2)))          # a new active key after retiring


def test_a_retired_key_cannot_be_reactivated(conn):
    key_id = conn.execute(*key_sql(fp(1))).lastrowid
    conn.execute(RETIRE, ("Rotation", key_id))
    assert rejects(conn, "UPDATE ledger_chain_key SET is_active = 1, retired_at = NULL, retire_reason = NULL "
                         "WHERE key_id = ?", (key_id,))


@pytest.mark.parametrize("assignment", [
    f"fingerprint = '{'b' * 64}'", "created_at = '2027-01-01T00:00:00+00:00'", "created_by = 2", "key_id = 50",
])
def test_other_key_columns_are_locked(conn, assignment):
    key_id = conn.execute(*key_sql(fp(1))).lastrowid
    assert rejects(conn, f"UPDATE ledger_chain_key SET {assignment} WHERE key_id = ?", (key_id,))
    conn.execute(RETIRE, ("Rotation", key_id))
    assert rejects(conn, f"UPDATE ledger_chain_key SET {assignment} WHERE key_id = ?", (key_id,))


def test_retiring_is_audited(conn):
    key_id = conn.execute(*key_sql(fp(1))).lastrowid
    conn.execute(RETIRE, ("Rotation", key_id))
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_log WHERE table_name = 'ledger_chain_key' "
                                          "AND record_id = ? ORDER BY log_id", (key_id,))]
    assert actions == ["Insert", "Update"]


# --- ledger_checkpoint -----------------------------------------------------------------------------------------

def checkpoint_sql(**overrides):
    values = {"created_at": "2026-03-31T23:00:00+00:00", "created_by": 1, "kind": "Verify", "scope": "Full",
              "result": "OK", "through_entry_number": 3, "chain_hash": "a" * 64, "first_broken_entry_number": None,
              "key_id": None, "ref_type": None, "ref_id": None, "mac": "b" * 64, **overrides}
    return (f"INSERT INTO ledger_checkpoint ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
            tuple(values.values()))


@pytest.mark.parametrize("kind", ["Verify", "Period close", "Year close", "Report export", "Backup", "Restore",
                                  "Key rotation", "Manual"])
def test_checkpoint_kinds(conn, kind):
    assert not rejects(conn, *checkpoint_sql(kind=kind, scope="Full" if kind == "Verify" else None))


def test_an_unknown_kind_is_refused(conn):
    assert rejects(conn, *checkpoint_sql(kind="Weekly", scope=None))


@pytest.mark.parametrize("kind, scope, rejected", [
    ("Verify", None, True), ("Verify", "Incremental", False), ("Verify", "Sometimes", True),
    ("Backup", "Full", True), ("Backup", None, False),
])
def test_scope_is_given_exactly_for_verify(conn, kind, scope, rejected):
    assert rejects(conn, *checkpoint_sql(kind=kind, scope=scope)) is rejected


@pytest.mark.parametrize("result, first_broken, rejected", [
    ("OK", None, False), ("OK", 2, True), ("Broken", None, True), ("Broken", 2, False), ("Maybe", None, True),
])
def test_result_and_first_broken_go_together(conn, result, first_broken, rejected):
    assert rejects(conn, *checkpoint_sql(result=result, first_broken_entry_number=first_broken)) is rejected


@pytest.mark.parametrize("through, chain_hash, rejected", [
    (0, None, False), (0, "a" * 64, True), (3, None, True), (-1, None, True), ("x", "a" * 64, True),
])
def test_an_empty_ledger_checkpoint_has_no_hash(conn, through, chain_hash, rejected):
    assert rejects(conn, *checkpoint_sql(through_entry_number=through, chain_hash=chain_hash)) is rejected


# Step 1d (KS12): the key-lost checkpoint. Kind 'Key lost' exactly when result is 'Unverified'; it names the new key
# that signs it and the key retired as lost, and it is never Broken (no first_broken_entry_number).

def key_lost_sql(conn, **overrides):
    key_id = lh.ensure_test_chain_key(conn)
    values = {"kind": "Key lost", "scope": None, "result": "Unverified", "key_id": key_id,
              "ref_type": "ledger_chain_key", "ref_id": key_id, **overrides}
    return checkpoint_sql(**values)


def test_a_key_lost_checkpoint_is_unverified(conn):
    assert not rejects(conn, *key_lost_sql(conn))
    assert not rejects(conn, *key_lost_sql(conn, through_entry_number=0, chain_hash=None))


@pytest.mark.parametrize("kind, scope, result, first_broken", [
    ("Key lost", None, "OK", None), ("Key lost", None, "Broken", 2), ("Verify", "Full", "Unverified", None),
    ("Key rotation", None, "Unverified", None), ("Key lost", None, "Unverified", 2), ("Key lost", "Full", "Unverified", None),
])
def test_key_lost_goes_with_unverified_and_nothing_else(conn, kind, scope, result, first_broken):
    assert rejects(conn, *key_lost_sql(conn, kind=kind, scope=scope, result=result,
                                       first_broken_entry_number=first_broken))


@pytest.mark.parametrize("overrides", [{"key_id": None}, {"ref_type": None}, {"ref_type": "journal_entry"},
                                       {"ref_id": None}])
def test_a_key_lost_checkpoint_names_its_new_key_and_the_lost_one(conn, overrides):
    assert rejects(conn, *key_lost_sql(conn, **overrides))


@pytest.mark.parametrize("column", ["mac", "chain_hash"])
@pytest.mark.parametrize("bad", ["B" * 64, "b" * 63, "x" * 64])
def test_checkpoint_hex_formats(conn, column, bad):
    assert rejects(conn, *checkpoint_sql(**{column: bad}))


def test_mac_and_created_at_are_required(conn):
    assert rejects(conn, *checkpoint_sql(mac=None))
    assert rejects(conn, *checkpoint_sql(created_at=None))


def test_checkpoint_key_must_exist(conn):
    assert rejects(conn, *checkpoint_sql(key_id=999))
    assert not rejects(conn, *checkpoint_sql(key_id=lh.ensure_test_chain_key(conn)))


def test_checkpoints_are_append_only_and_audited(conn):
    checkpoint_id = conn.execute(*checkpoint_sql()).lastrowid
    assert rejects(conn, "UPDATE ledger_checkpoint SET result = 'OK' WHERE checkpoint_id = ?", (checkpoint_id,))
    assert rejects(conn, "UPDATE ledger_checkpoint SET mac = ? WHERE checkpoint_id = ?", ("c" * 64, checkpoint_id))
    assert rejects(conn, "DELETE FROM ledger_checkpoint WHERE checkpoint_id = ?", (checkpoint_id,))
    log = conn.execute("SELECT action, new_value FROM audit_log WHERE table_name = 'ledger_checkpoint' "
                       "AND record_id = ?", (checkpoint_id,)).fetchall()
    assert [r["action"] for r in log] == ["Insert"]
    assert json.loads(log[0]["new_value"])["chain_hash"] == "a" * 64


# --- audit coverage and the close check ------------------------------------------------------------------------

def test_journal_audit_triggers_carry_the_chain_columns(conn):
    for trigger in ("audit_journal_entry_insert", "audit_journal_entry_update", "audit_journal_entry_delete"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (trigger,)).fetchone()[0]
        for column in CHAIN:
            assert f"'{column}'" in sql, (trigger, column)
    entry_id = posted_entry(conn)
    posted = conn.execute("SELECT new_value FROM audit_log WHERE table_name = 'journal_entry' AND record_id = ? "
                          "AND action = 'Post'", (entry_id,)).fetchone()[0]
    snapshot = json.loads(posted)
    assert {c: snapshot[c] for c in CHAIN} == {c: entry(conn, entry_id)[c] for c in CHAIN}


def test_ledger_integrity_close_check_is_seeded_as_a_warning(conn):
    modes = dict(conn.execute("SELECT check_code, mode FROM period_close_check").fetchall())
    assert modes["ledger_integrity"] == "warn"
