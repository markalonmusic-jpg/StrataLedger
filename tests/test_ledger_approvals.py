"""Approvals in posting, Phase 2.5 step 4 (decisions R5, R15-R24; docs/roles_permissions_design.md 5A).

ledger.submit_entry_for_approval sends a draft for approval; ledger.post_journal_entry posts an entry that needs
approval only when its newest request is Approved for the entry exactly as it is now (R15, R20), and seals the
last approver (R24). Any edit or delete cancels the request in the same transaction (R21).
"""
import dataclasses
import sqlite3

import pytest

from modules.services import approvals, ledger, ledger_chain
from modules.services.errors import PermissionDeniedError, PostingError, ValidationError
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_posting import (  # noqa: F401  (fixtures and helpers)
    A, NOW, TODAY, entry_row, env, keyed, lines, refused, settings, verify,
)

LATER = "2026-03-21T09:30:00+00:00"


@pytest.fixture
def team(env):
    """poster drafts and posts; appr1-3 and ctrl approve; clerk only drafts; admin is Admin."""
    env.role("PARENT", "APPROVER", ["je.approve", "import.approve", "ledger.view"])
    env.role("PARENT", "CONTROLLER", ["je.approve", "ledger.view"])
    env.role("PARENT", "CLERK", ["je.create", "ledger.view"])
    env.role("PARENT", "BILLAPPROVER", ["bill.approve", "ledger.view"])
    env.limit("PARENT", "APPROVER", "Journal entry", 10 ** 12)
    env.limit("PARENT", "APPROVER", "Import batch", 10 ** 12)
    env.limit("PARENT", "CONTROLLER", "Journal entry", 10 ** 12)
    env.limit("PARENT", "BILLAPPROVER", "Bill", 10 ** 12)
    env.limit("PARENT", "POSTER", "Journal entry", 10 ** 12)
    people = {"poster": env.user_id}
    for name, role in (("appr1", "APPROVER"), ("appr2", "APPROVER"), ("appr3", "APPROVER"),
                       ("ctrl", "CONTROLLER"), ("clerk", "CLERK"), ("billappr", "BILLAPPROVER"),
                       ("poster2", "POSTER"), ("admin", "Admin")):
        people[name] = env.user(name)
        env.grant(people[name], "PARENT", role)
    env.grant_permission("PARENT", "POSTER", "import.run")       # submits an Import-origin entry
    env.people = people
    return env


def as_(env, name, origin="Human", now=NOW):
    return dataclasses.replace(env.ctx(env.people[name], "PARENT", origin), now=now, today=TODAY)


def make(env, who="poster", origin="Human", amount=1000, **kwargs):
    return ledger.create_entry(as_(env, who, origin), entry_date="2026-03-15", lines=lines(env, amount), **kwargs)


def post(env, entry_id, who="poster", origin="Human", now=NOW):
    confirm = {"confirm": True} if origin == "Human" else {}
    return ledger.post_journal_entry(as_(env, who, origin, now), entry_id, **confirm)


def submit(env, entry_id, who="poster", origin="Human"):
    return ledger.submit_entry_for_approval(as_(env, who, origin), entry_id)


def requests(env, entry_id):
    return env.rows("PARENT", "SELECT * FROM approval_request WHERE record_type = 'journal_entry' AND record_id = ? "
                              "ORDER BY request_id", (entry_id,))


def actions_of(env, request_id):
    return env.rows("PARENT", "SELECT * FROM approval_action WHERE request_id = ? ORDER BY action_id", (request_id,))


def tamper(env, sql, params=()):
    conn = sqlite3.connect(env.path("PARENT"))
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


# --- R20: which entries need approval ------------------------------------------------------------------------

def test_a_manual_entry_with_approval_off_posts_directly_and_cannot_be_submitted(team):
    entry_id = make(team)
    with pytest.raises(ValidationError, match="can be posted directly"):
        submit(team, entry_id)
    assert requests(team, entry_id) == []
    post(team, entry_id)
    assert entry_row(team, entry_id)["is_posted"] == 1
    assert (entry_row(team, entry_id)["approved_by"], entry_row(team, entry_id)["approved_at"]) == (None, None)


@pytest.mark.parametrize("threshold, amount, needs", [
    (None, 1, True),           # on with no threshold: every manual entry
    (1000, 1000, False),       # equal to the threshold posts directly (R5)
    (1000, 1001, True),        # one cent over needs approval
    (5000, 1000, False),
])
def test_manual_entry_over_threshold_needs_approval(team, threshold, amount, needs):
    """R5 (was a pending xfail): equal to the threshold posts directly, one cent over needs approval."""
    settings(team, manual_entry_approval=1, manual_entry_approval_threshold_cents=threshold)
    entry_id = make(team, amount=amount)
    if not needs:
        post(team, entry_id)
        assert entry_row(team, entry_id)["is_posted"] == 1
        return
    refused(team, lambda: post(team, entry_id), PostingError, "send it for approval")
    request_id = submit(team, entry_id)
    request = requests(team, entry_id)[0]
    assert (request["request_id"], request["document_type"], request["amount_cents"], request["status"]) == (
        request_id, "Journal entry", amount, "Pending")
    approvals.approve(as_(team, "appr1"), request_id)
    post(team, entry_id)
    assert entry_row(team, entry_id)["is_posted"] == 1


def test_agent_entries_always_need_human_approval(team):
    """R20 (was a pending xfail): with every control off."""
    _origin_needs_a_human_approval(team, "Agent")


def test_import_entries_always_need_human_approval(team):
    """R18, R20 (was a pending xfail): with every control off; one human review."""
    _origin_needs_a_human_approval(team, "Import")


def _origin_needs_a_human_approval(team, origin):
    settings(team, manual_entry_approval=0, require_separate_approver=0, allow_manual_control_je=1)
    entry_id = make(team, origin=origin)
    refused(team, lambda: post(team, entry_id), PostingError, "send it for approval")
    request_id = submit(team, entry_id, origin=origin)
    assert requests(team, entry_id)[0]["document_type"] == ("Journal entry" if origin == "Agent" else "Import batch")
    with pytest.raises(PermissionDeniedError):
        approvals.approve(as_(team, "appr1", origin), request_id)       # never the agent or the import itself
    approvals.approve(as_(team, "appr1"), request_id)
    if origin == "Import":
        refused(team, lambda: post(team, entry_id, origin="Import"), PermissionDeniedError, "posted by a person")
    post(team, entry_id)
    row = entry_row(team, entry_id)
    assert (row["is_posted"], row["origin"], row["approved_by"]) == (1, origin, team.people["appr1"])


def test_an_agent_cannot_post_even_an_approved_entry(team):
    entry_id = make(team, origin="Agent")
    approvals.approve(as_(team, "appr1"), submit(team, entry_id, origin="Agent"))
    refused(team, lambda: post(team, entry_id, origin="Agent"), PermissionDeniedError)


def test_a_document_entry_whose_type_needs_approval(team):
    with team._company("PARENT") as c:
        c.execute("UPDATE document_approval_setting SET requires_approval = 1 WHERE document_type = 'Bill'")
    entry_id = make(team, origin="System", source="Bill")
    refused(team, lambda: post(team, entry_id, origin="System"), PostingError, "send it for approval")
    team.grant_permission("PARENT", "POSTER", "bill.create")
    request_id = submit(team, entry_id, origin="System")
    assert requests(team, entry_id)[0]["document_type"] == "Bill"
    with pytest.raises(PermissionDeniedError):
        approvals.approve(as_(team, "appr1"), request_id)           # je.approve is not bill.approve
    approvals.approve(as_(team, "billappr"), request_id)
    post(team, entry_id, origin="System")
    assert entry_row(team, entry_id)["approved_by"] == team.people["billappr"]


def test_a_pending_request_blocks_direct_posting_even_when_approval_is_not_required(team):
    settings(team, manual_entry_approval=1, manual_entry_approval_threshold_cents=None)
    entry_id = make(team)
    submit(team, entry_id)
    settings(team, manual_entry_approval=0)
    refused(team, lambda: post(team, entry_id), PostingError, "waiting for approval")


# --- R3 and R17: separation of duties --------------------------------------------------------------------------

def test_separation_off_the_run_as_human_approves_an_agent_entry_and_is_flagged(team):
    settings(team, require_separate_approver=0)
    team.grant_permission("PARENT", "APPROVER", "je.create")
    entry_id = make(team, who="appr1", origin="Agent")
    request_id = submit(team, entry_id, who="appr1", origin="Agent")
    assert requests(team, entry_id)[0]["created_by"] == team.people["appr1"]
    approvals.approve(as_(team, "appr1"), request_id)
    assert actions_of(team, request_id)[0]["self_approved"] == 1


def test_separation_on_a_different_human_must_approve_and_post(team):
    settings(team, require_separate_approver=1)
    entry_id = make(team, who="poster", origin="Agent")
    request_id = submit(team, entry_id, origin="Agent")
    team.grant_permission("PARENT", "POSTER", "je.approve")
    with pytest.raises(PermissionDeniedError):
        approvals.approve(as_(team, "poster"), request_id)
    approvals.approve(as_(team, "appr1"), request_id)
    assert actions_of(team, request_id)[-1]["self_approved"] == 0
    refused(team, lambda: post(team, entry_id), PermissionDeniedError)           # R17: the creator cannot post
    post(team, entry_id, who="poster2")
    assert entry_row(team, entry_id)["posted_by"] == team.people["poster2"]


def test_separation_on_covers_posting_an_entry_that_needs_no_approval(team):
    """R17: for every entry, also one that needs no approval."""
    settings(team, require_separate_approver=1)
    entry_id = make(team)
    refused(team, lambda: post(team, entry_id), PermissionDeniedError)
    denial = team.rows("PARENT", "SELECT * FROM access_event WHERE event_type = 'Denied' ORDER BY rowid DESC")[0]
    assert (denial["permission_code"], denial["record_type"], denial["record_id"]) == (
        "je.post", "journal_entry", entry_id)
    post(team, entry_id, who="poster2")


def test_separation_off_the_creator_posts(team):
    settings(team, require_separate_approver=0)
    post(team, make(team))


# --- chains and limits -------------------------------------------------------------------------------------------

def _require_approval(team):
    settings(team, manual_entry_approval=1, manual_entry_approval_threshold_cents=None)


def test_a_two_step_chain_must_finish_before_posting(team):
    _require_approval(team)
    approvals.create_policy(as_(team, "admin"), "Two steps", "Journal entry", 0, None,
                            [(1, "APPROVER", 1), (2, "CONTROLLER", 1)])
    entry_id = make(team)
    request_id = submit(team, entry_id)
    refused(team, lambda: post(team, entry_id), PostingError, r"step 1 of 2")
    approvals.approve(as_(team, "appr1"), request_id)
    refused(team, lambda: post(team, entry_id), PostingError, r"step 2 of 2")
    approvals.approve(as_(team, "ctrl"), request_id)
    post(team, entry_id, now=LATER)
    acted = actions_of(team, request_id)[-1]
    row = entry_row(team, entry_id)
    assert (row["approved_by"], row["approved_at"]) == (team.people["ctrl"], acted["acted_at"])


def test_two_of_three_in_one_step(team):
    _require_approval(team)
    approvals.create_policy(as_(team, "admin"), "Two of three", "Journal entry", 0, None, [(1, "APPROVER", 2)])
    entry_id = make(team)
    request_id = submit(team, entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    refused(team, lambda: post(team, entry_id), PostingError, r"step 1 of 1")
    with pytest.raises(ValidationError):
        approvals.approve(as_(team, "appr1"), request_id)              # one person, one slot
    approvals.approve(as_(team, "appr3"), request_id)
    post(team, entry_id)
    assert entry_row(team, entry_id)["approved_by"] == team.people["appr3"]


def test_an_approval_limit_too_low_is_denied(team):
    _require_approval(team)
    approvals.set_approval_limit(as_(team, "admin"), "APPROVER", "Journal entry", 999)
    entry_id = make(team, amount=1000)
    request_id = submit(team, entry_id)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(as_(team, "appr1"), request_id)
    approvals.approve(as_(team, "ctrl"), request_id)
    post(team, entry_id)


# --- R21: edits and deletes cancel ------------------------------------------------------------------------------

def test_an_edit_after_approval_cancels_it_and_resubmission_starts_at_step_one(team):
    _require_approval(team)
    approvals.create_policy(as_(team, "admin"), "Two steps", "Journal entry", 0, None,
                            [(1, "APPROVER", 1), (2, "CONTROLLER", 1)])
    entry_id = make(team)
    first = submit(team, entry_id)
    approvals.approve(as_(team, "appr1"), first)
    approvals.approve(as_(team, "ctrl"), first)
    edit = as_(team, "poster", now=LATER)
    ledger.update_entry(edit, entry_id, description="changed after approval")
    request = requests(team, entry_id)[0]
    assert (request["status"], request["completed_at"]) == ("Cancelled", LATER)
    refused(team, lambda: post(team, entry_id), PostingError, "cancelled because the entry was changed")
    second = submit(team, entry_id)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(as_(team, "ctrl"), second)                    # back at step 1
    approvals.approve(as_(team, "appr2"), second)
    approvals.approve(as_(team, "ctrl"), second)
    post(team, entry_id)


def test_an_edit_while_pending_cancels_in_the_same_transaction(team):
    _require_approval(team)
    entry_id = make(team)
    submit(team, entry_id)
    with pytest.raises(ValidationError):
        ledger.update_entry(as_(team, "poster"), entry_id, entry_date="not a date")
    assert requests(team, entry_id)[0]["status"] == "Pending"           # a failed edit cancels nothing
    ledger.update_entry(as_(team, "poster"), entry_id, lines=lines(team, 2000))
    assert requests(team, entry_id)[0]["status"] == "Cancelled"


def test_delete_cancels_the_request(team):
    _require_approval(team)
    entry_id = make(team)
    request_id = submit(team, entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    ledger.delete_entry(as_(team, "poster"), entry_id)
    assert requests(team, entry_id)[0]["status"] == "Cancelled"


# --- R22: rejection --------------------------------------------------------------------------------------------

def test_a_rejected_entry_must_change_before_it_is_sent_again(team):
    _require_approval(team)
    entry_id = make(team)
    request_id = submit(team, entry_id)
    approvals.reject(as_(team, "appr1"), request_id, "wrong account")
    refused(team, lambda: post(team, entry_id), PostingError, r"rejected \(wrong account\)")
    with pytest.raises(ValidationError, match="Change the entry before sending it again; it was rejected: "
                                              "wrong account"):
        submit(team, entry_id)
    ledger.update_entry(as_(team, "poster"), entry_id, description="fixed the account")
    rejected = requests(team, entry_id)[0]
    assert rejected["status"] == "Rejected"                              # the rejected request stays
    assert actions_of(team, request_id)[0]["reason"] == "wrong account"
    second = submit(team, entry_id)
    approvals.approve(as_(team, "appr1"), second)
    post(team, entry_id)


def test_submit_is_refused_while_pending_or_when_already_approved(team):
    _require_approval(team)
    entry_id = make(team)
    request_id = submit(team, entry_id)
    with pytest.raises(ValidationError, match="already waiting for approval"):
        submit(team, entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    with pytest.raises(ValidationError, match="already approved"):
        submit(team, entry_id)


def test_submit_runs_the_posting_checks(team):
    _require_approval(team)
    unbalanced = ledger.create_entry(as_(team, "poster"), entry_date="2026-03-15", lines=[
        {"account_id": A(team, "cash"), "debit_cents": 100}, {"account_id": A(team, "sales"), "credit_cents": 90}])
    with pytest.raises(PostingError, match="does not balance"):
        submit(team, unbalanced)
    one_line = ledger.create_entry(as_(team, "poster"), entry_date="2026-03-15",
                                   lines=[{"account_id": A(team, "cash"), "debit_cents": 100}])
    with pytest.raises(PostingError, match="two lines"):
        submit(team, one_line)
    ar_without_customer = ledger.create_entry(as_(team, "poster"), entry_date="2026-03-15",
                                              lines=lines(team, debit="ar"))
    with pytest.raises(PostingError, match="must name the customer"):
        submit(team, ar_without_customer)
    assert team.rows("PARENT", "SELECT * FROM approval_request") == []


def test_submit_needs_je_create(team):
    _require_approval(team)
    entry_id = make(team)
    with pytest.raises(PermissionDeniedError):
        submit(team, entry_id, who="appr1")


# --- R15: the approved content is the posted content -------------------------------------------------------------

def test_the_request_stores_the_entry_digest(team):
    _require_approval(team)
    entry_id = make(team)
    submit(team, entry_id)
    digest = requests(team, entry_id)[0]["document_digest"]
    header = entry_row(team, entry_id)
    entry_lines = team.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ?", (entry_id,))
    assert len(digest) == 64 and digest == ledger_chain.entry_digest(header, entry_lines)


@pytest.mark.parametrize("column, value", [
    ("document_digest", "0" * 64), ("amount_cents", 999), ("document_type", "Import batch")])
def test_posting_refuses_a_tampered_request(team, column, value):
    _require_approval(team)
    entry_id = make(team)
    request_id = submit(team, entry_id)
    approvals.approve(as_(team, "appr1"), request_id)
    tamper(team, f"UPDATE approval_request SET {column} = ? WHERE request_id = ?", (value, request_id))
    refused(team, lambda: post(team, entry_id), PostingError, "does not match")


def test_posting_refuses_an_entry_changed_behind_the_service(team):
    _require_approval(team)
    entry_id = make(team)
    approvals.approve(as_(team, "appr1"), submit(team, entry_id))
    tamper(team, "UPDATE journal_line SET memo = 'slipped in' WHERE entry_id = ?", (entry_id,))
    refused(team, lambda: post(team, entry_id), PostingError, "does not match")


# --- R24: the last approver is recorded and sealed ----------------------------------------------------------------

def test_the_approver_is_sealed(team):
    _require_approval(team)
    entry_id = make(team)
    request_id = submit(team, entry_id)
    approvals.approve(as_(team, "appr1", now=LATER), request_id)
    post(team, entry_id)
    row = entry_row(team, entry_id)
    assert (row["approved_by"], row["approved_at"]) == (team.people["appr1"], LATER)
    assert verify(team)["ok"]
    tamper(team, "DROP TRIGGER journal_entry_lock_posted")
    tamper(team, "UPDATE journal_entry SET approved_by = ? WHERE entry_id = ?", (team.people["appr2"], entry_id))
    assert verify(team)["first_broken"]["entry_number"] == 1


# --- R16: the audit log records submit, approve, reject and cancel -----------------------------------------------

def test_the_audit_log_records_the_approval_history(team):
    _require_approval(team)
    entry_id = make(team)
    first = submit(team, entry_id)
    approvals.reject(as_(team, "appr1"), first, "no")
    ledger.update_entry(as_(team, "poster"), entry_id, description="again")
    second = submit(team, entry_id)
    approvals.approve(as_(team, "appr1"), second)
    ledger.update_entry(as_(team, "poster"), entry_id, description="and again")
    log = team.rows("PARENT", "SELECT table_name, record_id, action, new_value FROM audit_log "
                              "WHERE table_name IN ('approval_request', 'approval_action') ORDER BY log_id")
    request_events = [(e["record_id"], e["action"]) for e in log if e["table_name"] == "approval_request"]
    assert request_events == [(first, "Insert"), (first, "Update"), (second, "Insert"), (second, "Update"),
                              (second, "Update")]
    assert sum(1 for e in log if e["table_name"] == "approval_action") == 2
    assert '"Cancelled"' in log[-1]["new_value"]


# --- R15: the digest -----------------------------------------------------------------------------------------------

def test_entry_digest_ignores_the_posting_fields():
    header = {f: None for f in ledger_chain.HASHED_ENTRY}
    header.update(entry_id=1, entry_date="2026-03-15", period_id=3, origin="Human", created_by=1,
                  created_at="2026-03-15T00:00:00+00:00")
    line = {f: None for f in ledger_chain.HASHED_LINE}
    line.update(line_id=1, entry_id=1, account_id=5, debit_cents=10, credit_cents=0, is_retainage_line=0,
                is_control_override=0, is_rounding_adjustment=0)
    base = ledger_chain.entry_digest(header, [line])
    posted = dict(header, entry_number=7, posted_by=2, posted_at="2026-03-16T00:00:00+00:00", approved_by=3,
                  approved_at="2026-03-16T00:00:00+00:00", chain_version=1, chain_key_id=1)
    assert ledger_chain.entry_digest(posted, [line]) == base
    assert ledger_chain.entry_digest(dict(header, description="x"), [line]) != base
    assert ledger_chain.entry_digest(header, [dict(line, debit_cents=11)]) != base
    assert len(base) == 64 and int(base, 16) >= 0


# --- Step 4 review fixes ---------------------------------------------------------------------------------------

def test_a_self_approval_made_before_separation_was_turned_on_must_be_redone(team):
    """No dead end: separation turned on after the run-as human approved their own agent entry."""
    settings(team, require_separate_approver=0)
    team.grant_permission("PARENT", "APPROVER", "je.create")
    entry_id = make(team, who="appr1", origin="Agent")
    approvals.approve(as_(team, "appr1"), submit(team, entry_id, who="appr1", origin="Agent"))
    settings(team, require_separate_approver=1)
    refused(team, lambda: post(team, entry_id), PostingError, "approved by the person who created it")
    second = submit(team, entry_id, who="appr1", origin="Agent")             # allowed again
    approvals.approve(as_(team, "appr2"), second)
    post(team, entry_id)
    assert entry_row(team, entry_id)["approved_by"] == team.people["appr2"]


def test_an_unchanged_line_resave_keeps_a_rejected_entry_blocked(team):
    """R22: re-saving the same lines is not a change."""
    _require_approval(team)
    entry_id = make(team)
    approvals.reject(as_(team, "appr1"), submit(team, entry_id), "check it")
    sql = "SELECT line_id FROM journal_line WHERE entry_id = ? ORDER BY line_id"
    before = team.rows("PARENT", sql, (entry_id,))
    ledger.update_entry(as_(team, "poster"), entry_id, lines=lines(team, 1000))
    assert team.rows("PARENT", sql, (entry_id,)) == before
    with pytest.raises(ValidationError, match="Change the entry"):
        submit(team, entry_id)
    ledger.update_entry(as_(team, "poster"), entry_id, lines=lines(team, 1200))     # a real change
    submit(team, entry_id)


def test_a_rejection_reason_ending_in_a_period_is_not_doubled(team):
    _require_approval(team)
    entry_id = make(team)
    approvals.reject(as_(team, "appr1"), submit(team, entry_id), "Wrong account.")
    with pytest.raises(PostingError) as posting:
        post(team, entry_id)
    with pytest.raises(ValidationError) as resubmit:
        submit(team, entry_id)
    for error in (posting.value, resubmit.value):
        assert ".." not in str(error) and "Wrong account" in str(error)


def test_submit_reads_the_entry_inside_its_own_transaction(team, monkeypatch):
    """An edit that lands between the first read and the write is caught: the request carries the new digest."""
    _require_approval(team)
    entry_id = make(team)
    real = approvals.authorize_submit

    def edit_in_between(context, *args, **kwargs):
        real(context, *args, **kwargs)
        ledger.update_entry(as_(team, "poster"), entry_id, description="edited meanwhile")

    monkeypatch.setattr(approvals, "authorize_submit", edit_in_between)
    submit(team, entry_id)
    monkeypatch.setattr(approvals, "authorize_submit", real)
    header = entry_row(team, entry_id)
    entry_lines = team.rows("PARENT", "SELECT * FROM journal_line WHERE entry_id = ?", (entry_id,))
    assert header["description"] == "edited meanwhile"
    assert requests(team, entry_id)[0]["document_digest"] == ledger_chain.entry_digest(header, entry_lines)


@pytest.mark.parametrize("action", ["update", "delete"])
def test_the_edit_and_the_cancel_are_one_transaction(team, monkeypatch, action):
    """R21: if the cancel fails, the edit is rolled back too."""
    _require_approval(team)
    entry_id = make(team)
    submit(team, entry_id)
    real = approvals.cancel_in_transaction

    def cancel_then_fail(*args):
        real(*args)
        raise RuntimeError("the cancel failed")

    monkeypatch.setattr(approvals, "cancel_in_transaction", cancel_then_fail)
    with pytest.raises(RuntimeError):
        if action == "update":
            ledger.update_entry(as_(team, "poster"), entry_id, description="changed")
        else:
            ledger.delete_entry(as_(team, "poster"), entry_id)
    assert entry_row(team, entry_id)["description"] != "changed"
    assert requests(team, entry_id)[0]["status"] == "Pending"


def test_refused_submits_leave_no_request(team):
    entry_id = make(team)
    with pytest.raises(ValidationError):
        submit(team, entry_id)                                              # can be posted directly
    _require_approval(team)
    request_id = submit(team, entry_id)
    with pytest.raises(ValidationError):
        submit(team, entry_id)                                              # already waiting
    approvals.approve(as_(team, "appr1"), request_id)
    with pytest.raises(ValidationError):
        submit(team, entry_id)                                              # already approved
    assert [r["request_id"] for r in requests(team, entry_id)] == [request_id]


def test_the_creator_posting_denial_says_what_to_do(team):
    settings(team, require_separate_approver=1)
    entry_id = make(team)
    with pytest.raises(PermissionDeniedError, match="different person to post"):
        post(team, entry_id)


def test_an_import_context_posting_is_a_logged_denial(team):
    entry_id = make(team, origin="Import")
    approvals.approve(as_(team, "appr1"), submit(team, entry_id, origin="Import"))
    with pytest.raises(PermissionDeniedError, match="posted by a person"):
        post(team, entry_id, origin="Import")
    denial = team.rows("PARENT", "SELECT * FROM access_event WHERE event_type = 'Denied' ORDER BY rowid DESC")[0]
    assert (denial["user_id"], denial["origin"], denial["permission_code"], denial["record_type"],
            denial["record_id"]) == (team.people["poster"], "Import", "je.post", "journal_entry", entry_id)
    assert entry_row(team, entry_id)["is_posted"] == 0


def test_the_approval_flow_never_logs_the_chain_key(team, caplog, tmp_path):
    """secrets-auditor finding 1: submit, approve, refuse and post with DEBUG logging on."""
    import base64
    import logging
    handler = logging.FileHandler(tmp_path / "debug.log", encoding="utf-8")
    logging.getLogger().addHandler(handler)
    caplog.set_level(logging.DEBUG)
    errors = []
    try:
        _require_approval(team)
        entry_id = make(team)
        request_id = submit(team, entry_id)
        for attempt in (lambda: post(team, entry_id), lambda: submit(team, entry_id)):
            try:
                attempt()
            except Exception as error:  # noqa: BLE001  (collected to check their text)
                errors.append(error)
        approvals.approve(as_(team, "appr1"), request_id)
        tamper(team, "UPDATE approval_request SET amount_cents = 1 WHERE request_id = ?", (request_id,))
        try:
            post(team, entry_id)
        except PostingError as error:
            errors.append(error)
        tamper(team, "UPDATE approval_request SET amount_cents = 1000 WHERE request_id = ?", (request_id,))
        post(team, entry_id)
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
    assert len(errors) == 3 and entry_row(team, entry_id)["is_posted"] == 1
    key = lh.TEST_CHAIN_KEY
    forms = {key.hex(), key.hex().upper(), base64.b64encode(key).decode(), key.hex()[:16]}
    text = (tmp_path / "debug.log").read_text(encoding="utf-8") + caplog.text + "".join(
        str(e) + repr(e) for e in errors)
    assert [form for form in forms if form in text] == []
