"""Master baseline, Step 1c: the key store tables (docs/audit_readiness_design.md 2.7; KS3, KS9, KS10).

* installation_key: append-only history with one active row (Step 1d, KS13). Each row holds an installation key's
  public fingerprint and two wrapped copies: DPAPI machine scope (machine_blob, NULL while this computer has no
  DPAPI copy) and the recovery code (recovery_salt, 16 bytes; recovery_blob, an AES-GCM wrap of 61 bytes). The
  active row's blobs are re-wrapped in place; a lost key is retired ('Key lost') and a new row becomes active. The
  key itself (id, fingerprint, created_at) never changes, a retired row never changes or comes back, and no row is
  deleted.
* company_key: every company's wrapped keys, matched to the company file's ledger_chain_key by fingerprint, and
  naming the installation key that wrapped them (installation_key_id). Append-only; retirement is recorded in the
  company file. Kept even if the company leaves the registry.
* Neither table is audited (KS9), so no wrapped blob ever reaches audit_log; the services write an auth_event
  (now with an optional company_id) for each change, without the blob.
"""
import sqlite3

import pytest

import modules.database as database
from tests.ledger_helpers import rejects

FP = "a" * 64
FP2 = "b" * 64
SALT = b"\x01" * 16
WRAP = b"\x01" + b"\x02" * 60


@pytest.fixture
def fresh(tmp_path, backup_dir):
    path = tmp_path / "fresh_master.db"
    database.ensure_master_database(path)
    c = database.get_connection(path)
    c.execute("INSERT INTO company_registry (company_code, legal_name, database_file_path) "
              "VALUES ('ACME', 'Acme Ltd', 'Companies/ACME.db')")
    yield c
    c.close()


def _installation(c, **overrides):
    row = {"id": 1, "fingerprint": FP, "machine_blob": b"dpapi blob", "machine_wrapped_at": "2026-11-12T00:00:00+00:00",
           "recovery_salt": SALT, "recovery_blob": WRAP, "recovery_wrapped_at": "2026-11-12T00:00:00+00:00",
           "created_at": "2026-11-12T00:00:00+00:00"}
    row.update(overrides)
    c.execute(f"INSERT INTO installation_key ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
              list(row.values()))


def _installation_sql(**overrides):
    row = {"id": 1, "fingerprint": FP, "machine_blob": b"dpapi blob", "machine_wrapped_at": "t",
           "recovery_salt": SALT, "recovery_blob": WRAP, "recovery_wrapped_at": "t", "created_at": "t"}
    row.update(overrides)
    return (f"INSERT INTO installation_key ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
            list(row.values()))


def _company_key_sql(**overrides):
    row = {"company_id": 1, "purpose": "chain", "fingerprint": FP, "wrapped_key": WRAP, "installation_key_id": 1,
           "created_at": "t"}
    row.update(overrides)
    return (f"INSERT INTO company_key ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
            list(row.values()))


def _audit_count(c):
    return c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


# --- installation_key -------------------------------------------------------------------------------------------

def test_the_installation_key_row_holds_a_fingerprint_and_two_wraps(fresh):
    _installation(fresh)
    columns = {r["name"] for r in fresh.execute("PRAGMA table_info(installation_key)")}
    assert columns == {"id", "fingerprint", "machine_blob", "machine_wrapped_at", "recovery_salt", "recovery_blob",
                       "recovery_wrapped_at", "created_at", "is_active", "retired_at", "retire_reason"}
    row = fresh.execute("SELECT is_active, retired_at, retire_reason FROM installation_key").fetchone()
    assert tuple(row) == (1, None, None)


RETIRE = ("UPDATE installation_key SET is_active = 0, retired_at = '2026-11-12T01:00:00+00:00', "
          "retire_reason = 'Key lost' WHERE id = 1")


def test_only_one_installation_key_is_active(fresh):
    _installation(fresh)
    assert rejects(fresh, *_installation_sql())
    assert rejects(fresh, *_installation_sql(id=2, fingerprint=FP2))
    fresh.execute(RETIRE)
    _installation(fresh, id=2, fingerprint=FP2)
    assert [r[0] for r in fresh.execute("SELECT id FROM installation_key WHERE is_active = 1")] == [2]
    assert rejects(fresh, *_installation_sql(id=3, fingerprint="c" * 64))


def test_the_installation_key_id_is_never_reused(fresh):
    _installation(fresh)
    fresh.execute(RETIRE)
    fresh.execute("INSERT INTO installation_key (fingerprint, recovery_salt, recovery_blob, recovery_wrapped_at, "
                  "created_at) VALUES (?, ?, ?, 't', 't')", (FP2, SALT, WRAP))
    assert [r[0] for r in fresh.execute("SELECT id FROM installation_key ORDER BY id")] == [1, 2]
    assert "AUTOINCREMENT" in fresh.execute("SELECT sql FROM sqlite_master WHERE name = 'installation_key'"
                                            ).fetchone()[0].upper()


@pytest.mark.parametrize("assignment", [
    "is_active = 0", "is_active = 0, retired_at = 't'", "is_active = 0, retire_reason = 'Key lost'",
    "is_active = 0, retired_at = 't', retire_reason = 'Rotation'", "retired_at = 't', retire_reason = 'Key lost'",
    "is_active = 2",
])
def test_retirement_needs_the_date_and_the_reason_key_lost(fresh, assignment):
    _installation(fresh)
    assert rejects(fresh, f"UPDATE installation_key SET {assignment} WHERE id = 1")


@pytest.mark.parametrize("assignment, params", [
    ("is_active = 1, retired_at = NULL, retire_reason = NULL", ()), ("retired_at = 'later'", ()),
    ("machine_blob = NULL, machine_wrapped_at = NULL", ()), ("recovery_blob = ?", (b"\x01" + bytes(60),)),
    ("recovery_salt = ?", (b"\x09" * 16,)), ("recovery_wrapped_at = 'later'", ()),
])
def test_a_retired_key_cannot_change_or_come_back(fresh, assignment, params):
    _installation(fresh)
    fresh.execute(RETIRE)
    assert rejects(fresh, f"UPDATE installation_key SET {assignment} WHERE id = 1", params)
    row = fresh.execute("SELECT fingerprint, recovery_blob, machine_blob FROM installation_key WHERE id = 1").fetchone()
    assert (row[0], bytes(row[1]), bytes(row[2])) == (FP, WRAP, b"dpapi blob")       # its recovery copy is kept


@pytest.mark.parametrize("extra, params", [
    ("recovery_blob = ?", (b"\x01" + bytes(60),)), ("machine_blob = NULL, machine_wrapped_at = NULL", ()),
])
def test_retiring_does_not_also_rewrap(fresh, extra, params):
    _installation(fresh)
    assert rejects(fresh, "UPDATE installation_key SET is_active = 0, retired_at = 't', retire_reason = 'Key lost', "
                          f"{extra} WHERE id = 1", params)


def test_the_machine_copy_may_be_missing(fresh):
    """First run on a computer where DPAPI fails still stores the recovery copy (the key is then locked, KS6)."""
    _installation(fresh, machine_blob=None, machine_wrapped_at=None)
    assert fresh.execute("SELECT machine_blob FROM installation_key").fetchone()[0] is None


@pytest.mark.parametrize("overrides", [
    {"fingerprint": "A" * 64}, {"fingerprint": "a" * 63}, {"fingerprint": "g" * 64}, {"fingerprint": None},
    {"recovery_salt": b"\x01" * 15}, {"recovery_salt": "0" * 16}, {"recovery_salt": None},
    {"recovery_blob": WRAP[:-1]}, {"recovery_blob": "x" * 61}, {"recovery_blob": None},
    {"machine_blob": b"", "machine_wrapped_at": "t"}, {"machine_blob": "text", "machine_wrapped_at": "t"},
    {"machine_blob": None, "machine_wrapped_at": "t"}, {"machine_blob": b"blob", "machine_wrapped_at": None},
    {"recovery_wrapped_at": None}, {"created_at": None}, {"is_active": 2}, {"retire_reason": "Key lost"},
    {"is_active": 0}, {"is_active": 0, "retired_at": "t", "retire_reason": "Rotation"},
], ids=lambda o: ",".join(f"{k}={'None' if v is None else v if isinstance(v, int) else type(v).__name__ + str(len(v))}"
                            for k, v in o.items()))
def test_a_malformed_installation_key_row_is_refused(fresh, overrides):
    assert rejects(fresh, *_installation_sql(**overrides))


def test_the_wraps_can_be_rewritten_but_the_key_never_changes(fresh):
    _installation(fresh)
    fresh.execute("UPDATE installation_key SET machine_blob = ?, machine_wrapped_at = 'later', recovery_salt = ?, "
                  "recovery_blob = ?, recovery_wrapped_at = 'later'", (b"new dpapi", b"\x09" * 16, b"\x01" + bytes(60)))
    fresh.execute("UPDATE installation_key SET machine_blob = NULL, machine_wrapped_at = NULL")
    assert rejects(fresh, "UPDATE installation_key SET fingerprint = ?", (FP2,))
    assert rejects(fresh, "UPDATE installation_key SET created_at = 'other'")
    assert rejects(fresh, "UPDATE installation_key SET id = 2")


def test_the_installation_key_is_never_deleted(fresh):
    _installation(fresh)
    assert rejects(fresh, "DELETE FROM installation_key")
    fresh.execute(RETIRE)
    assert rejects(fresh, "DELETE FROM installation_key")


# --- company_key ------------------------------------------------------------------------------------------------

@pytest.fixture
def keyed(fresh):
    _installation(fresh)
    return fresh


def test_a_company_key_row_holds_the_wrapped_key_and_its_fingerprint(keyed):
    keyed.execute(*_company_key_sql())
    columns = {r["name"] for r in keyed.execute("PRAGMA table_info(company_key)")}
    assert columns == {"company_key_id", "company_id", "purpose", "fingerprint", "wrapped_key",
                       "installation_key_id", "created_at"}


@pytest.mark.parametrize("installation_key_id", [None, 2])
def test_a_company_key_names_a_real_installation_key(keyed, installation_key_id):
    assert rejects(keyed, *_company_key_sql(installation_key_id=installation_key_id))


def test_company_keys_wrapped_by_a_retired_installation_key_are_kept(keyed):
    keyed.execute(*_company_key_sql())
    keyed.execute(RETIRE)
    _installation(keyed, id=2, fingerprint=FP2)
    keyed.execute(*_company_key_sql(fingerprint=FP2, installation_key_id=2))
    assert [tuple(r) for r in keyed.execute("SELECT fingerprint, installation_key_id FROM company_key "
                                            "ORDER BY company_key_id")] == [(FP, 1), (FP2, 2)]
    assert rejects(keyed, "UPDATE company_key SET installation_key_id = 2 WHERE installation_key_id = 1")


@pytest.mark.parametrize("overrides", [
    {"purpose": "signing"}, {"purpose": None}, {"fingerprint": "A" * 64}, {"fingerprint": "a" * 65},
    {"wrapped_key": WRAP + b"\x00"}, {"wrapped_key": "x" * 61}, {"wrapped_key": None}, {"company_id": 99},
    {"company_id": None}, {"created_at": None},
], ids=lambda o: ",".join(f"{k}={'None' if v is None else v if isinstance(v, int) else len(v)}" for k, v in o.items()))
def test_a_malformed_company_key_row_is_refused(keyed, overrides):
    assert rejects(keyed, *_company_key_sql(**overrides))


def test_both_purposes_are_allowed_and_a_key_is_stored_once(keyed):
    keyed.execute(*_company_key_sql())
    keyed.execute(*_company_key_sql(fingerprint=FP2))
    keyed.execute(*_company_key_sql(purpose="encryption"))
    assert rejects(keyed, *_company_key_sql())


def test_company_keys_are_append_only(keyed):
    keyed.execute(*_company_key_sql())
    assert rejects(keyed, "UPDATE company_key SET wrapped_key = ?", (b"\x01" + bytes(60),))
    assert rejects(keyed, "UPDATE company_key SET fingerprint = ?", (FP2,))
    assert rejects(keyed, "DELETE FROM company_key")


def test_a_company_with_keys_cannot_leave_the_registry(keyed):
    keyed.execute(*_company_key_sql())
    assert rejects(keyed, "DELETE FROM company_registry WHERE company_id = 1")


# --- Never audited (KS9) -----------------------------------------------------------------------------------------

def test_the_key_tables_have_no_audit_and_never_reach_audit_log(fresh):
    before = _audit_count(fresh)
    _installation(fresh)
    fresh.execute("UPDATE installation_key SET recovery_blob = ?", (b"\x01" + bytes(60),))
    fresh.execute(*_company_key_sql())
    assert _audit_count(fresh) == before
    triggers = {r["name"]: r["sql"] for r in fresh.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' "
        "AND tbl_name IN ('installation_key', 'company_key')")}
    assert not [name for name, sql in triggers.items() if "audit_log" in sql]
    for row in fresh.execute("SELECT old_value, new_value FROM audit_log"):
        for value in row:
            assert value is None or "wrapped" not in value and "recovery_blob" not in value


# --- auth_event: the key events ----------------------------------------------------------------------------------

KEY_EVENTS = ("Installation key created", "Installation key rewrapped", "Recovery code issued", "Ledger key created",
              "Ledger key rotated", "Ledger key lost", "Installation key replaced")


@pytest.mark.parametrize("event_type", KEY_EVENTS)
def test_auth_event_records_the_key_events_with_a_company(fresh, event_type):
    fresh.execute("INSERT INTO auth_event (occurred_at, event_type, user_id, company_id) VALUES ('t', ?, 1, 1)",
                  (event_type,))


def test_auth_event_still_holds_no_secret_column(fresh):
    columns = {r["name"] for r in fresh.execute("PRAGMA table_info(auth_event)")}
    assert columns == {"event_id", "occurred_at", "event_type", "username", "user_id", "actor_user_id",
                       "permission_code", "company_id"}


# --- chain_checkpoint: the key-lost mirror (Step 1d, KS12) ---------------------------------------------------------

def _mirror_sql(**overrides):
    row = {"company_id": 1, "company_checkpoint_id": 1, "recorded_from": "Company file", "created_at": "t",
           "created_by": 1, "kind": "Key lost", "scope": None, "result": "Unverified", "through_entry_number": 3,
           "chain_hash": "a" * 64, "first_broken_entry_number": None, "key_id": 2, "ref_type": "ledger_chain_key",
           "ref_id": 1, "mac": "b" * 64}
    row.update(overrides)
    return (f"INSERT INTO chain_checkpoint ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
            list(row.values()))


def test_the_mirror_holds_a_key_lost_checkpoint(fresh):
    assert not rejects(fresh, *_mirror_sql())
    assert not rejects(fresh, *_mirror_sql(through_entry_number=0, chain_hash=None))


@pytest.mark.parametrize("overrides", [
    {"result": "OK"}, {"result": "Broken", "first_broken_entry_number": 2}, {"kind": "Verify", "scope": "Full"},
    {"kind": "Key rotation"}, {"first_broken_entry_number": 2}, {"key_id": None}, {"ref_type": None},
    {"ref_type": "journal_entry"}, {"ref_id": None},
])
def test_the_mirror_keeps_key_lost_and_unverified_together(fresh, overrides):
    assert rejects(fresh, *_mirror_sql(**overrides))
