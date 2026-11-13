"""Approval chains and the separate-approver rule (docs/roles_permissions_design.md 5A).

A policy covers one document type and an amount band. Its steps run in order of
step_no; steps with the same step_no are parallel. Each step names a role and
how many DIFFERENT people holding it must approve. A person fills at most one
slot per request. Normal users fill a slot only for their current role; the
Master and Admin may fill any slot (still once). With no matching policy the
default chain is one approval by anyone holding the approve permission with a
covering limit. The chain is copied onto the request at submit time, so policy
changes never affect a request in progress. Any rejection ends the request.

Only a Human-origin context approves or rejects (R23). Any edit or delete of the
document cancels its Pending or Approved request (R21); document services call
cancel_in_transaction inside their own write so the two are one change. Status
changes follow ALLOWED_STATUS_CHANGES (R16; a service rule, not a trigger, H4).

Every public writer authorizes before opening its write transaction (rule 10).
All denials (permission, limit, slot, separate approver) are raised before the
write transaction opens, so they are logged in their own transaction.
approvals.py never writes approved_by / approved_at on documents: the document
services do that at post time, after is_approved().
"""
import json
import sqlite3
from collections import namedtuple

from modules.services import authz, permissions
from modules.services.authz import authorize, check_approval_limit
from modules.services.errors import NotFoundError, ValidationError
from modules.services.tx import read_connection, write_transaction

_NO_UPPER_BOUND = 2 ** 63 - 1
DEFAULT_CHAIN = [{"step_no": 1, "role_code": None, "required_count": 1}]
ALLOWED_STATUS_CHANGES = {
    "Pending": {"Approved", "Rejected", "Cancelled"},
    "Approved": {"Cancelled"},
    "Rejected": set(),
    "Cancelled": set(),
}
_CANCELLABLE = ("Pending", "Approved")
ONLY_A_PERSON = "Only a person can approve or reject; sign in and do it yourself."
_NOUN = {"journal_entry": "entry"}    # how a refusal names the record; "document" otherwise

Slot = namedtuple("Slot", "step_no role_code")
_Plan = namedtuple("_Plan", "request chain slot stored_role self_approved privileged role_code")


# --- The separate-approver rule (shared by approvals and later services) ---------------------

def check_separate_approver(context, created_by_user_id, *, permission_code=None, record_type=None,
                            record_id=None):
    """Apply require_separate_approver to an approval or posting by context.user_id.

    Returns True when the approver is the creator and the company allows it (the
    action must then be flagged self-approved), False when they differ. When the
    setting is on (or no settings row exists: the safe default) and the approver
    is the creator, logs a denial and raises PermissionDeniedError. Applies to
    the Master and Admin too. Call it before opening a write transaction.
    """
    if created_by_user_id != context.user_id:
        return False
    conn = read_connection(context.company_db_path)
    try:
        row = conn.execute("SELECT require_separate_approver FROM company_settings WHERE id = 1").fetchone()
    finally:
        conn.close()
    if row is None or row["require_separate_approver"] == 1:
        authz.deny(context, permission_code, record_type=record_type, record_id=record_id)
    return True


# --- Is approval needed at all? (decision 1.6) --------------------------------------------------

def is_approval_required(context, document_type):
    """Does this kind of document need an approval before it posts? Off by default for every type.

    Journal entries follow company_settings.manual_entry_approval; the other types follow their row in
    document_approval_setting. When this is False a document posts directly and submit_for_approval is
    not called. When it is True and no policy covers the amount, the default single-approver chain applies.
    """
    _check_document_type(document_type)
    conn = read_connection(context.company_db_path)
    try:
        if document_type == "Journal entry":
            row = conn.execute("SELECT manual_entry_approval AS flag FROM company_settings WHERE id = 1").fetchone()
        else:
            row = conn.execute("SELECT requires_approval AS flag FROM document_approval_setting "
                               "WHERE document_type = ?", (document_type,)).fetchone()
    finally:
        conn.close()
    return bool(row and row["flag"])


# --- Requests ------------------------------------------------------------------------------

def submit_for_approval(context, document_type, record_type, record_id, amount_cents, *, created_by,
                        project_id=None, document_digest=None):
    """Create a Pending approval request for a document. Returns its request_id.

    document_digest (R15): the document's content digest; a document whose newest request was Rejected with
    the same digest is refused until it changes (R22). Required by the baseline for journal entries.
    """
    _check_document_type(document_type)
    _check_cents(amount_cents, "amount_cents")
    if not record_type or record_id is None:
        raise ValidationError("record_type and record_id are required")
    if isinstance(created_by, bool) or not isinstance(created_by, int):
        raise ValidationError("created_by must be a user id")
    authorize(context, permissions.SUBMIT_PERMISSION[document_type], project_id,
              record_type=record_type, record_id=record_id)
    with write_transaction(context.company_db_path, context) as conn:
        newest = request_state(conn, record_type, record_id)
        if (newest is not None and newest["status"] == "Rejected" and document_digest is not None
                and newest["document_digest"] == document_digest):
            raise ValidationError(f"Change the {_NOUN.get(record_type, 'document')} before sending it again; "
                                  f"it was rejected: {newest['reason']}.")
        policy_id, chain = _chain_for(conn, document_type, amount_cents)
        try:
            return conn.execute(
                "INSERT INTO approval_request (document_type, record_type, record_id, amount_cents, policy_id, "
                "created_by, project_id, chain_json, status, submitted_by, submitted_at, document_digest) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?) RETURNING request_id",
                (document_type, record_type, record_id, amount_cents, policy_id, created_by, project_id,
                 json.dumps(chain), context.user_id, context.now, document_digest),
            ).fetchone()[0]
        except sqlite3.IntegrityError as error:
            if "approval_request.record_type" in str(error):
                raise ValidationError("This record already has a pending approval request") from error
            raise


def approve(context, request_id):
    """Fill this user's slot in the request's open step. Returns the new status."""
    _require_person(context, request_id)
    request = _load_request(context, request_id)
    check_approval_limit(context, request["document_type"], request["amount_cents"], request["project_id"],
                         record_type="approval_request", record_id=request_id)
    plan = _plan(context, request)
    with write_transaction(context.company_db_path, context) as conn:
        return _record(conn, context, plan, "Approve", None)


def reject(context, request_id, reason):
    """Reject the request from this user's slot in the open step; ends the request."""
    if reason is None or not str(reason).strip():
        raise ValidationError("A reason is required to reject")
    _require_person(context, request_id)
    request = _load_request(context, request_id)
    check_approval_limit(context, request["document_type"], request["amount_cents"], request["project_id"],
                         record_type="approval_request", record_id=request_id)
    plan = _plan(context, request)
    with write_transaction(context.company_db_path, context) as conn:
        return _record(conn, context, plan, "Reject", str(reason).strip())


def cancel_on_edit(context, record_type, record_id):
    """Cancel the record's Pending or Approved request because the document was edited (R21).

    Returns True if one was cancelled. The document must then be resubmitted and approved from step 1.
    A document service that edits in its own write transaction calls cancel_in_transaction instead.
    """
    conn = read_connection(context.company_db_path)
    try:
        live = _live_requests(conn, record_type, record_id)
    finally:
        conn.close()
    if not live:
        return False
    authorize(context, permissions.SUBMIT_PERMISSION[live[0]["document_type"]], live[0]["project_id"],
              record_type=record_type, record_id=record_id)
    with write_transaction(context.company_db_path, context) as conn:
        return cancel_in_transaction(conn, context, record_type, record_id)


def cancel_in_transaction(conn, context, record_type, record_id):
    """Inside the caller's write transaction: cancel the record's Pending or Approved requests (R21).

    The caller has already authorized the edit (for a journal entry, je.create, which is also the submit
    permission), so the cancel and the edit commit or roll back together. completed_at is the edit's now.
    Returns True if a request was cancelled.
    """
    live = _live_requests(conn, record_type, record_id)
    for request in live:
        _change_status(conn, request["request_id"], "Cancelled", context.now)
    return bool(live)


def is_approved(conn, record_type, record_id):
    """True when the record's newest approval request is Approved (the posting / payment gate)."""
    row = conn.execute(
        "SELECT status FROM approval_request WHERE record_type = ? AND record_id = ? "
        "ORDER BY request_id DESC LIMIT 1", (record_type, record_id),
    ).fetchone()
    return row is not None and row[0] == "Approved"


def request_state(conn, record_type, record_id):
    """The record's newest approval request as a dict, or None (the posting gate reads this).

    Keys: request_id, status, document_type, amount_cents, document_digest, created_by, reason (the rejection's,
    else None), step and steps (the open step's position and the number of steps; step is None when every step
    is complete), approved_by and approved_at (the last Approve action, else None).
    """
    row = conn.execute(
        "SELECT request_id, status, document_type, amount_cents, document_digest, created_by, chain_json "
        "FROM approval_request WHERE record_type = ? AND record_id = ? ORDER BY request_id DESC LIMIT 1",
        (record_type, record_id)).fetchone()
    if row is None:
        return None
    state = dict(row)
    chain = json.loads(state.pop("chain_json"))
    acted = [dict(r) for r in conn.execute(
        "SELECT step_no, role_code, user_id, decision, reason, acted_at FROM approval_action WHERE request_id = ? "
        "ORDER BY action_id", (state["request_id"],))]
    step_nos = sorted({slot["step_no"] for slot in chain})
    open_steps = [n for n in step_nos if any(_filled(slot, acted) < slot["required_count"]
                                             for slot in chain if slot["step_no"] == n)]
    approvals_made = [a for a in acted if a["decision"] == "Approve"]
    rejections = [a for a in acted if a["decision"] == "Reject"]
    state.update(
        steps=len(step_nos), step=step_nos.index(open_steps[0]) + 1 if open_steps else None,
        reason=rejections[-1]["reason"] if rejections else None,
        approved_by=approvals_made[-1]["user_id"] if approvals_made else None,
        approved_at=approvals_made[-1]["acted_at"] if approvals_made else None,
    )
    return state


# --- Policies and limits (company.roles.manage) ------------------------------------------------

def create_policy(context, name, document_type, min_amount_cents, max_amount_cents, steps):
    """Create an active policy with its steps. Policies are never edited in place:
    deactivate the old one and create a new one. Bands of active policies for one
    document type must not overlap. steps: iterable of (step_no, role_code, required_count).
    """
    _check_document_type(document_type)
    if not name or not str(name).strip():
        raise ValidationError("A policy needs a name")
    _check_cents(min_amount_cents, "min_amount_cents")
    if max_amount_cents is not None:
        _check_cents(max_amount_cents, "max_amount_cents")
        if max_amount_cents < min_amount_cents:
            raise ValidationError("max_amount_cents is below min_amount_cents")
    steps = _check_steps(steps)
    authorize(context, "company.roles.manage")
    with write_transaction(context.company_db_path, context) as conn:
        for _, role_code, _ in steps:
            if conn.execute("SELECT 1 FROM role WHERE role_code = ?", (role_code,)).fetchone() is None:
                raise NotFoundError(f"No such role: {role_code}")
        _check_no_overlap(conn, document_type, min_amount_cents, max_amount_cents)
        policy_id = conn.execute(
            "INSERT INTO approval_policy (name, document_type, min_amount_cents, max_amount_cents) "
            "VALUES (?, ?, ?, ?) RETURNING policy_id",
            (str(name).strip(), document_type, min_amount_cents, max_amount_cents),
        ).fetchone()[0]
        conn.executemany(
            "INSERT INTO approval_step (policy_id, step_no, role_code, required_count) VALUES (?, ?, ?, ?)",
            [(policy_id, step_no, role_code, count) for step_no, role_code, count in steps],
        )
        return policy_id


def deactivate_policy(context, policy_id):
    """Stop a policy applying to new requests. Requests already submitted keep their copied chain."""
    authorize(context, "company.roles.manage")
    with write_transaction(context.company_db_path, context) as conn:
        cursor = conn.execute("UPDATE approval_policy SET is_active = 0 WHERE policy_id = ?", (policy_id,))
        if cursor.rowcount == 0:
            raise NotFoundError(f"No such approval policy: {policy_id}")


def set_approval_limit(context, role_code, document_type, max_amount_cents):
    """Create or change a role's approval limit for one document type. Admin is unlimited."""
    if document_type not in permissions.LIMIT_DOCUMENT_TYPES:
        raise ValidationError(f"Approval limits cannot be set for {document_type!r}")
    _check_cents(max_amount_cents, "max_amount_cents")
    if role_code == "Admin":
        raise ValidationError("Admin has no approval limit")
    authorize(context, "company.roles.manage")
    with write_transaction(context.company_db_path, context) as conn:
        if conn.execute("SELECT 1 FROM role WHERE role_code = ?", (role_code,)).fetchone() is None:
            raise NotFoundError(f"No such role: {role_code}")
        conn.execute(
            "INSERT INTO approval_limit (role_code, document_type, max_amount_cents) VALUES (?, ?, ?) "
            "ON CONFLICT (role_code, document_type) DO UPDATE SET max_amount_cents = excluded.max_amount_cents",
            (role_code, document_type, max_amount_cents),
        )


# --- internals ---------------------------------------------------------------------------------

def _require_person(context, request_id):
    """R23: only a Human-origin context approves or rejects. Logged, before any read of the request."""
    if context.origin != "Human":
        authz.deny(context, record_type="approval_request", record_id=request_id, message=ONLY_A_PERSON)


def _live_requests(conn, record_type, record_id):
    return [dict(r) for r in conn.execute(
        "SELECT request_id, document_type, project_id FROM approval_request "
        "WHERE record_type = ? AND record_id = ? AND status IN (?, ?) ORDER BY request_id",
        (record_type, record_id, *_CANCELLABLE))]


def _change_status(conn, request_id, new_status, now):
    """Inside a write transaction: move a request to new_status if ALLOWED_STATUS_CHANGES permits it (R16)."""
    row = conn.execute("SELECT status FROM approval_request WHERE request_id = ?", (request_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No such approval request: {request_id}")
    if new_status not in ALLOWED_STATUS_CHANGES[row["status"]]:
        raise ValidationError(f"An approval request that is {row['status']} cannot become {new_status}")
    cursor = conn.execute(
        "UPDATE approval_request SET status = ?, completed_at = ? WHERE request_id = ? AND status = ?",
        (new_status, now, request_id, row["status"]))
    if cursor.rowcount != 1:
        raise ValidationError("The approval request changed; try again")


def _check_document_type(document_type):
    if document_type not in permissions.DOCUMENT_TYPES:
        raise ValueError(f"Unknown document type: {document_type!r}")


def _check_cents(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{name} must be a whole number of cents, zero or more")


def _check_steps(steps):
    checked = []
    for step in steps or ():
        step_no, role_code, required_count = step
        for value, label in ((step_no, "step_no"), (required_count, "required_count")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValidationError(f"{label} must be a whole number, 1 or more")
        if not role_code or not isinstance(role_code, str):
            raise ValidationError("Each step names a role")
        checked.append((step_no, role_code, required_count))
    if not checked:
        raise ValidationError("A policy needs at least one step")
    if len({(s, r) for s, r, _ in checked}) != len(checked):
        raise ValidationError("A role appears twice in the same step")
    return sorted(checked)


def _check_no_overlap(conn, document_type, low, high):
    clash = conn.execute(
        "SELECT name FROM approval_policy WHERE is_active = 1 AND document_type = ? "
        "AND min_amount_cents <= ? AND (max_amount_cents IS NULL OR max_amount_cents >= ?) LIMIT 1",
        (document_type, _NO_UPPER_BOUND if high is None else high, low),
    ).fetchone()
    if clash is not None:
        raise ValidationError(f"The amount band overlaps the active policy {clash['name']!r}")


def _chain_for(conn, document_type, amount_cents):
    matches = conn.execute(
        "SELECT policy_id FROM approval_policy WHERE is_active = 1 AND document_type = ? "
        "AND min_amount_cents <= ? AND (max_amount_cents IS NULL OR max_amount_cents >= ?)",
        (document_type, amount_cents, amount_cents),
    ).fetchall()
    if len(matches) > 1:
        raise ValidationError("More than one active approval policy covers this amount; fix the overlapping bands")
    if not matches:
        return None, DEFAULT_CHAIN
    policy_id = matches[0]["policy_id"]
    chain = [dict(step_no=r["step_no"], role_code=r["role_code"], required_count=r["required_count"])
             for r in conn.execute(
                 "SELECT step_no, role_code, required_count FROM approval_step WHERE policy_id = ? "
                 "ORDER BY step_no, role_code", (policy_id,))]
    if not chain:
        raise ValidationError("The matching approval policy has no steps")
    return policy_id, chain


def _load_request(context, request_id):
    conn = read_connection(context.company_db_path)
    try:
        request = conn.execute("SELECT * FROM approval_request WHERE request_id = ?", (request_id,)).fetchone()
    finally:
        conn.close()
    if request is None:
        raise NotFoundError(f"No such approval request: {request_id}")
    if request["status"] != "Pending":
        raise ValidationError(f"The approval request is {request['status']}")
    return dict(request)


def _actions(conn, request_id):
    return [dict(r) for r in conn.execute(
        "SELECT step_no, role_code, user_id, decision FROM approval_action WHERE request_id = ? ORDER BY action_id",
        (request_id,))]


def _filled(slot, actions):
    return sum(1 for a in actions if a["decision"] == "Approve" and a["step_no"] == slot["step_no"]
               and (slot["role_code"] is None or a["role_code"] == slot["role_code"]))


def _open_slot(chain, actions, role_code, privileged):
    """The slot this user would fill in the lowest open step, or None if they cannot fill one."""
    for step_no in sorted({s["step_no"] for s in chain}):
        open_slots = [s for s in chain if s["step_no"] == step_no and _filled(s, actions) < s["required_count"]]
        if not open_slots:
            continue
        for slot in open_slots:
            if slot["role_code"] is None or privileged or slot["role_code"] == role_code:
                return Slot(step_no, slot["role_code"])
        return None
    return None


def _complete(chain, actions):
    return all(_filled(slot, actions) >= slot["required_count"] for slot in chain)


def _plan(context, request):
    """Every check that can deny, done before the write transaction opens."""
    record = dict(record_type="approval_request", record_id=request["request_id"])
    permission = permissions.APPROVE_PERMISSION[request["document_type"]]
    self_approved = check_separate_approver(context, request["created_by"], permission_code=permission, **record)
    access = authz.current_access(context)
    privileged = access.is_master or access.role_code == "Admin"
    chain = json.loads(request["chain_json"])
    conn = read_connection(context.company_db_path)
    try:
        actions = _actions(conn, request["request_id"])
    finally:
        conn.close()
    if any(a["user_id"] == context.user_id for a in actions):
        raise ValidationError("You have already acted on this approval request")
    slot = _open_slot(chain, actions, access.role_code, privileged)
    if slot is None:
        authz.deny(context, permission, **record)
    stored_role = slot.role_code or access.role_code or ("Master" if access.is_master else None)
    return _Plan(request, chain, slot, stored_role, self_approved, privileged, access.role_code)


def _record(conn, context, plan, decision, reason):
    """Inside the write transaction: re-check the request did not change, then record the action."""
    request_id = plan.request["request_id"]
    status = conn.execute("SELECT status FROM approval_request WHERE request_id = ?", (request_id,)).fetchone()[0]
    if status != "Pending":
        raise ValidationError(f"The approval request is {status}")
    actions = _actions(conn, request_id)
    if any(a["user_id"] == context.user_id for a in actions):
        raise ValidationError("You have already acted on this approval request")
    if _open_slot(plan.chain, actions, plan.role_code, plan.privileged) != plan.slot:
        raise ValidationError("The approval request changed; try again")
    now = context.now
    conn.execute(
        "INSERT INTO approval_action (request_id, step_no, role_code, user_id, decision, reason, self_approved, "
        "acted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (request_id, plan.slot.step_no, plan.stored_role, context.user_id, decision, reason,
         int(plan.self_approved), now),
    )
    actions.append({"step_no": plan.slot.step_no, "role_code": plan.stored_role, "user_id": context.user_id,
                    "decision": decision})
    if decision == "Reject":
        status = "Rejected"
    elif _complete(plan.chain, actions):
        status = "Approved"
    else:
        return "Pending"
    _change_status(conn, request_id, status, now)
    return status
