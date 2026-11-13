"""Phase 2.5 step 4 baseline: the approval tables are audited, a request is never deleted, and a journal entry's
request carries the digest of the content that was approved (decisions R15, R16).

* approval_request.document_digest: 64 lowercase hex characters (SHA-256 of the entry's canonical form, the same
  form the ledger chain seals), required when the request is for a journal entry, optional for other documents
  until their services use it.
* audit triggers: approval_request insert and update, approval_action insert (approval_action is append-only, so
  it has no update or delete to audit); every column is in the audit JSON.
* approval_request cannot be deleted (a rejected or cancelled request stays for the audit trail). Which status
  changes are allowed is a service rule (H4), not a trigger.
"""
import json
import sqlite3

import pytest

import modules.database as database
from tests.ledger_helpers import rejects, set_user

DIGEST = "ab" * 32


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def _request(conn, *, record_type="journal_entry", record_id=1, digest=DIGEST, status="Pending"):
    completed_at = None if status == "Pending" else "2026-01-02T00:00:00+00:00"
    return conn.execute(
        "INSERT INTO approval_request (document_type, record_type, record_id, amount_cents, chain_json, status, "
        "created_by, submitted_by, submitted_at, completed_at, document_digest) "
        "VALUES ('Journal entry', ?, ?, 500, '[]', ?, 1, 1, '2026-01-01T00:00:00+00:00', ?, ?) RETURNING request_id",
        (record_type, record_id, status, completed_at, digest)).fetchone()[0]


# --- document_digest ---------------------------------------------------------------------------------------------

def test_a_journal_entry_request_carries_a_digest(conn):
    _request(conn)
    assert conn.execute("SELECT document_digest FROM approval_request").fetchone()[0] == DIGEST


@pytest.mark.parametrize("digest", [None, "AB" * 32, "ab" * 31, "ab" * 33, "zz" * 32, "", 12])
def test_a_journal_entry_request_without_a_good_digest_is_refused(conn, digest):
    with pytest.raises(sqlite3.IntegrityError):
        _request(conn, digest=digest)


def test_other_documents_may_omit_the_digest_but_not_give_a_bad_one(conn):
    _request(conn, record_type="bill", digest=None)
    with pytest.raises(sqlite3.IntegrityError):
        _request(conn, record_type="bill", record_id=2, digest="not hex")


# --- Never deleted -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["Pending", "Approved", "Rejected", "Cancelled"])
def test_a_request_is_never_deleted(conn, status):
    request_id = _request(conn, status=status)
    assert rejects(conn, "DELETE FROM approval_request WHERE request_id = ?", (request_id,))
    assert conn.execute("SELECT COUNT(*) FROM approval_request").fetchone()[0] == 1


def test_status_changes_are_left_to_the_service(conn):
    """H4: no trigger decides the workflow; the service does (tests/test_ledger_approvals.py)."""
    request_id = _request(conn, status="Approved")
    conn.execute("UPDATE approval_request SET status = 'Cancelled' WHERE request_id = ?", (request_id,))


# --- Audit triggers -----------------------------------------------------------------------------------------------

AUDITED = {"approval_request": ("insert", "update"), "approval_action": ("insert",)}


def test_audit_triggers_cover_every_column(conn):
    missing = []
    for table, events in AUDITED.items():
        columns = [c["name"] for c in conn.execute(f'PRAGMA table_info("{table}")')]
        for event in events:
            row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                               (f"audit_{table}_{event}",)).fetchone()
            if row is None:
                missing.append(f"audit_{table}_{event} (no trigger)")
                continue
            for prefix in {"insert": ["NEW"], "update": ["OLD", "NEW"]}[event]:
                missing += [f"audit_{table}_{event}: {prefix}.{c}" for c in columns if f"{prefix}.{c}" not in row[0]]
    assert missing == []


def _audit(conn, table):
    return [dict(r) for r in conn.execute("SELECT user_id, record_id, action, old_value, new_value FROM audit_log "
                                          "WHERE table_name = ? ORDER BY log_id", (table,))]


def test_submit_decide_and_cancel_are_in_the_audit_log(conn):
    set_user(conn, 9)
    request_id = _request(conn)
    conn.execute("INSERT INTO approval_action (request_id, step_no, role_code, user_id, decision, reason, "
                 "self_approved, acted_at) VALUES (?, 1, 'Admin', 9, 'Reject', 'Wrong account', 0, "
                 "'2026-01-02T00:00:00+00:00')", (request_id,))
    conn.execute("UPDATE approval_request SET status = 'Rejected', completed_at = '2026-01-02T00:00:00+00:00' "
                 "WHERE request_id = ?", (request_id,))
    requests = _audit(conn, "approval_request")
    assert [(r["action"], r["user_id"], r["record_id"]) for r in requests] == [
        ("Insert", 9, request_id), ("Update", 9, request_id)]
    assert json.loads(requests[0]["new_value"])["document_digest"] == DIGEST
    assert json.loads(requests[1]["old_value"])["status"] == "Pending"
    assert json.loads(requests[1]["new_value"])["status"] == "Rejected"
    [action] = _audit(conn, "approval_action")
    assert action["action"] == "Insert" and action["user_id"] == 9
    assert json.loads(action["new_value"])["reason"] == "Wrong account"
