"""Approval chains (docs/roles_permissions_design.md section 5A) and the separate-approver rule."""
import json

import pytest

import modules.database as database
from modules.services import approvals
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)

CO = "PARENT"


@pytest.fixture
def team(world):
    """Clerk enters bills; PMs and Controllers approve them; Admin and Master exist."""
    world.settings(CO, require_separate_approver=1)
    world.role(CO, "Clerk", ["bill.create"])
    world.role(CO, "PM", ["bill.approve", "bill.create"])
    world.role(CO, "Controller", ["bill.approve"])
    world.role(CO, "Manager", ["company.roles.manage"])
    world.limit(CO, "PM", "Bill", 100_000)
    world.limit(CO, "Controller", "Bill", 10_000_000)
    people = {}
    for name, role in (("clerk", "Clerk"), ("pm1", "PM"), ("pm2", "PM"), ("pm3", "PM"),
                       ("ctrl1", "Controller"), ("ctrl2", "Controller"), ("admin", "Admin"), ("mgr", "Manager")):
        people[name] = world.user(name)
        world.grant(people[name], CO, role)
    people["master"] = world.user("owner", master=True)
    people["ctx"] = lambda name, origin="Human": world.ctx(people[name], CO, origin)
    return people


def submit(team, amount=5_000, record_id=1, by="clerk", created_by=None):
    return approvals.submit_for_approval(
        team["ctx"](by), "Bill", "invoice", record_id, amount,
        created_by=team[created_by or by])


def approved(world, record_id):
    conn = database.get_readonly_connection(world.path(CO))
    try:
        return approvals.is_approved(conn, "invoice", record_id)
    finally:
        conn.close()


def request_row(world, request_id):
    return world.rows(CO, "SELECT * FROM approval_request WHERE request_id = ?", (request_id,))[0]


def actions(world, request_id):
    return world.rows(CO, "SELECT * FROM approval_action WHERE request_id = ? ORDER BY action_id", (request_id,))


def policy(team, steps, low=0, high=None, name="P", document_type="Bill"):
    return approvals.create_policy(team["ctx"]("mgr"), name, document_type, low, high, steps)


# --- Default single approval ----------------------------------------------------------------

def test_default_single_approval(world, team):
    request_id = submit(team)
    row = request_row(world, request_id)
    assert (row["status"], row["policy_id"], row["created_by"], row["submitted_by"]) == ("Pending", None, team["clerk"], team["clerk"])
    assert json.loads(row["chain_json"]) == [{"step_no": 1, "role_code": None, "required_count": 1}]
    assert row["submitted_at"].endswith("+00:00")
    assert approved(world, 1) is False

    assert approvals.approve(team["ctx"]("pm1"), request_id) == "Approved"
    row = request_row(world, request_id)
    assert row["status"] == "Approved" and row["completed_at"]
    assert [(a["user_id"], a["decision"], a["step_no"], a["role_code"]) for a in actions(world, request_id)] == [
        (team["pm1"], "Approve", 1, "PM")]
    assert approved(world, 1) is True


def test_default_approval_still_needs_permission_and_limit(world, team):
    request_id = submit(team, amount=200_000)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"]("pm1"), request_id)  # over the PM limit
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"]("clerk"), request_id)  # no bill.approve
    assert approvals.approve(team["ctx"]("ctrl1"), request_id) == "Approved"


def test_submit_needs_the_submit_permission(world, team):
    with pytest.raises(PermissionDeniedError):
        approvals.submit_for_approval(team["ctx"]("ctrl1"), "Bill", "invoice", 1, 10, created_by=team["ctrl1"])


def test_only_one_pending_request_per_record(world, team):
    submit(team)
    with pytest.raises(ValidationError):
        submit(team)


def test_bad_inputs(world, team):
    with pytest.raises(ValueError):
        approvals.submit_for_approval(team["ctx"]("clerk"), "Invoice", "invoice", 1, 10, created_by=team["clerk"])
    with pytest.raises(ValidationError):
        approvals.submit_for_approval(team["ctx"]("clerk"), "Bill", "invoice", 1, 10.5, created_by=team["clerk"])
    with pytest.raises(ValidationError):
        approvals.submit_for_approval(team["ctx"]("clerk"), "Bill", "invoice", 1, -1, created_by=team["clerk"])
    with pytest.raises(NotFoundError):
        approvals.approve(team["ctx"]("pm1"), 999)


# --- Chains ----------------------------------------------------------------------------------

def test_two_step_chain(world, team):
    policy(team, [(1, "PM", 1), (2, "Controller", 1)])
    request_id = submit(team)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"]("ctrl1"), request_id)  # step 2 is not open yet
    assert approvals.approve(team["ctx"]("pm1"), request_id) == "Pending"
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"]("pm2"), request_id)  # step 1 is full; step 2 needs a Controller
    assert approvals.approve(team["ctx"]("ctrl1"), request_id) == "Approved"
    assert [(a["step_no"], a["role_code"]) for a in actions(world, request_id)] == [(1, "PM"), (2, "Controller")]


def test_parallel_steps_must_all_be_met(world, team):
    policy(team, [(1, "PM", 1), (1, "Controller", 1)])
    request_id = submit(team)
    assert approvals.approve(team["ctx"]("ctrl1"), request_id) == "Pending"
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"]("ctrl2"), request_id)  # the Controller slot is full
    assert approvals.approve(team["ctx"]("pm1"), request_id) == "Approved"


def test_two_of_n_in_one_step(world, team):
    policy(team, [(1, "PM", 2)])
    request_id = submit(team)
    assert approvals.approve(team["ctx"]("pm1"), request_id) == "Pending"
    assert approvals.approve(team["ctx"]("pm2"), request_id) == "Approved"


def test_same_person_cannot_fill_two_slots(world, team):
    policy(team, [(1, "PM", 2)])
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    with pytest.raises(ValidationError):
        approvals.approve(team["ctx"]("pm1"), request_id)


def test_admin_and_master_fill_any_slot_but_only_once_across_steps(world, team):
    policy(team, [(1, "PM", 1), (2, "Controller", 1)])
    request_id = submit(team)
    assert approvals.approve(team["ctx"]("admin"), request_id) == "Pending"  # fills the PM slot
    with pytest.raises(ValidationError):
        approvals.approve(team["ctx"]("admin"), request_id)  # cannot also fill step 2
    assert approvals.approve(team["ctx"]("master"), request_id) == "Approved"
    assert [(a["user_id"], a["role_code"]) for a in actions(world, request_id)] == [
        (team["admin"], "PM"), (team["master"], "Controller")]


def test_person_with_two_roles_fills_one_slot(world, team):
    # pm3 is moved to Controller after approving step 1 as a PM; still one slot per person.
    policy(team, [(1, "PM", 1), (2, "Controller", 1)])
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm3"), request_id)
    world.grant(team["pm3"], CO, "Controller")
    with pytest.raises(ValidationError):
        approvals.approve(team["ctx"]("pm3"), request_id)


# --- Separation of duties ---------------------------------------------------------------------------

@pytest.mark.parametrize("creator", ["pm1", "admin", "master"])
def test_creator_cannot_approve_when_separation_is_on(world, team, creator):
    request_id = submit(team, by="clerk", created_by=creator)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"](creator), request_id)
    assert request_row(world, request_id)["status"] == "Pending"
    assert world.events(CO)[-1]["permission_code"] == "bill.approve"


def test_creator_approval_is_flagged_when_separation_is_off(world, team):
    world.settings(CO, require_separate_approver=0)
    request_id = submit(team, by="pm1")
    assert approvals.approve(team["ctx"]("pm1"), request_id) == "Approved"
    assert actions(world, request_id)[0]["self_approved"] == 1


def test_check_separate_approver_helper(world, team):
    ctx = team["ctx"]("pm1")
    assert approvals.check_separate_approver(ctx, team["clerk"]) is False
    with pytest.raises(PermissionDeniedError):
        approvals.check_separate_approver(ctx, team["pm1"])
    world.settings(CO, require_separate_approver=0)
    assert approvals.check_separate_approver(ctx, team["pm1"]) is True


def test_missing_settings_row_means_separation_on(world):
    user_id = world.user("solo")
    world.grant(user_id, "OTHER", "Admin")
    with pytest.raises(PermissionDeniedError):
        approvals.check_separate_approver(world.ctx(user_id, "OTHER"), user_id)


# --- Rejection --------------------------------------------------------------------------------

def test_reject_ends_the_request_and_needs_a_reason(world, team):
    policy(team, [(1, "PM", 2)])
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    for blank in ("", "   ", None):
        with pytest.raises(ValidationError):
            approvals.reject(team["ctx"]("pm2"), request_id, blank)
    assert approvals.reject(team["ctx"]("pm2"), request_id, "Wrong vendor") == "Rejected"
    row = request_row(world, request_id)
    assert row["status"] == "Rejected" and row["completed_at"]
    assert actions(world, request_id)[-1]["reason"] == "Wrong vendor"
    with pytest.raises(ValidationError):
        approvals.approve(team["ctx"]("pm3"), request_id)
    assert approved(world, 1) is False


def test_reject_needs_an_eligible_approver(world, team):
    request_id = submit(team)
    with pytest.raises(PermissionDeniedError):
        approvals.reject(team["ctx"]("clerk"), request_id, "No")


# --- Policy bands ----------------------------------------------------------------------------

def test_band_selection_at_the_boundaries(world, team):
    small = policy(team, [(1, "PM", 1)], low=0, high=99_999, name="small")
    large = policy(team, [(1, "Controller", 1)], low=100_000, high=None, name="large")
    for amount, expected in ((0, small), (99_999, small), (100_000, large), (10**10, large)):
        request_id = submit(team, amount=amount, record_id=amount + 1)
        assert request_row(world, request_id)["policy_id"] == expected, amount


def test_amount_between_bands_uses_the_default_chain(world, team):
    policy(team, [(1, "Controller", 1)], low=100_000, high=200_000)
    request_id = submit(team, amount=50)
    assert request_row(world, request_id)["policy_id"] is None


def test_overlapping_bands_are_rejected_at_create_time(world, team):
    policy(team, [(1, "PM", 1)], low=0, high=100_000, name="a")
    for low, high in ((100_000, None), (50, 60), (0, 0)):
        with pytest.raises(ValidationError):
            policy(team, [(1, "PM", 1)], low=low, high=high, name="b")
    policy(team, [(1, "PM", 1)], low=100_001, high=None, name="c")
    policy(team, [(1, "PM", 1)], low=0, high=100_000, name="other type", document_type="Payment")


def test_overlapping_bands_are_rejected_at_submit_time(world, team):
    policy(team, [(1, "PM", 1)], low=0, high=100, name="a")
    # Bypass the service to plant an overlap, as a damaged file might have.
    from tests.authz_world import _Conn
    with _Conn(world.path(CO)) as c:
        c.execute("INSERT INTO approval_policy (name, document_type, min_amount_cents, max_amount_cents) "
                  "VALUES ('planted', 'Bill', 50, NULL)")
    with pytest.raises(ValidationError):
        submit(team, amount=75)


def test_inactive_policies_are_ignored(world, team):
    pid = policy(team, [(1, "Controller", 1)])
    approvals.deactivate_policy(team["ctx"]("mgr"), pid)
    assert request_row(world, submit(team))["policy_id"] is None
    policy(team, [(1, "PM", 1)], name="replacement")  # a deactivated band no longer overlaps


def test_policy_edit_does_not_affect_a_pending_request(world, team):
    pid = policy(team, [(1, "Controller", 1)])
    request_id = submit(team)
    approvals.deactivate_policy(team["ctx"]("mgr"), pid)
    policy(team, [(1, "PM", 1)], name="new")
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"]("pm1"), request_id)  # the copied chain still needs a Controller
    assert approvals.approve(team["ctx"]("ctrl1"), request_id) == "Approved"


def test_policy_steps_are_validated(world, team):
    with pytest.raises(ValidationError):
        policy(team, [])
    with pytest.raises(ValidationError):
        policy(team, [(0, "PM", 1)])
    with pytest.raises(ValidationError):
        policy(team, [(1, "PM", 0)])
    with pytest.raises(NotFoundError):
        policy(team, [(1, "NoSuchRole", 1)])
    with pytest.raises(ValidationError):
        policy(team, [(1, "PM", 1)], low=10, high=5)


def test_policy_and_limit_services_need_roles_manage(world, team):
    with pytest.raises(PermissionDeniedError):
        approvals.create_policy(team["ctx"]("pm1"), "x", "Bill", 0, None, [(1, "PM", 1)])
    pid = policy(team, [(1, "PM", 1)])
    with pytest.raises(PermissionDeniedError):
        approvals.deactivate_policy(team["ctx"]("pm1"), pid)
    with pytest.raises(PermissionDeniedError):
        approvals.set_approval_limit(team["ctx"]("pm1"), "PM", "Bill", 1)


def test_deactivate_unknown_policy(world, team):
    with pytest.raises(NotFoundError):
        approvals.deactivate_policy(team["ctx"]("mgr"), 999)


def test_set_approval_limit_creates_and_updates(world, team):
    ctx = team["ctx"]("mgr")
    approvals.set_approval_limit(ctx, "Clerk", "Bill", 500)
    approvals.set_approval_limit(ctx, "Clerk", "Bill", 900)
    assert world.rows(CO, "SELECT max_amount_cents FROM approval_limit WHERE role_code = 'Clerk'") == [{"max_amount_cents": 900}]
    with pytest.raises(ValidationError):
        approvals.set_approval_limit(ctx, "Admin", "Bill", 1)  # Admin is unlimited
    with pytest.raises(NotFoundError):
        approvals.set_approval_limit(ctx, "NoSuchRole", "Bill", 1)
    with pytest.raises(ValidationError):
        approvals.set_approval_limit(ctx, "Clerk", "Bill", -1)
    with pytest.raises(ValidationError):
        approvals.set_approval_limit(ctx, "Clerk", "Invoice", 1)  # not an approval document type


# --- Edits cancel ------------------------------------------------------------------------------

def test_edit_after_submit_cancels_and_resubmit_starts_at_step_one(world, team):
    policy(team, [(1, "PM", 1), (2, "Controller", 1)])
    first = submit(team)
    approvals.approve(team["ctx"]("pm1"), first)
    assert approvals.cancel_on_edit(team["ctx"]("clerk"), "invoice", 1) is True
    row = request_row(world, first)
    assert row["status"] == "Cancelled" and row["completed_at"]
    second = submit(team)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"]("ctrl1"), second)  # back at step 1
    approvals.approve(team["ctx"]("pm2"), second)
    approvals.approve(team["ctx"]("ctrl1"), second)
    assert approved(world, 1) is True


def test_cancel_with_nothing_pending_is_a_no_op(world, team):
    assert approvals.cancel_on_edit(team["ctx"]("clerk"), "invoice", 77) is False


def test_cancel_needs_the_submit_permission(world, team):
    submit(team)
    with pytest.raises(PermissionDeniedError):
        approvals.cancel_on_edit(team["ctx"]("ctrl1"), "invoice", 1)


# --- Agents -----------------------------------------------------------------------------------

@pytest.mark.parametrize("who", ["pm1", "admin", "master"])
def test_agent_cannot_approve_or_reject(world, team, who):
    request_id = submit(team)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(team["ctx"](who, origin="Agent"), request_id)
    with pytest.raises(PermissionDeniedError):
        approvals.reject(team["ctx"](who, origin="Agent"), request_id, "no")
    assert actions(world, request_id) == []


def test_agent_can_submit_a_bill_it_drafted(world, team):
    request_id = approvals.submit_for_approval(team["ctx"]("clerk", origin="Agent"), "Bill", "invoice", 5, 10,
                                               created_by=team["clerk"])
    assert request_row(world, request_id)["status"] == "Pending"


# --- Project scope on requests ------------------------------------------------------------------

def test_scoped_approver_needs_the_requests_project(world, team):
    world.role(CO, "SitePM", ["bill.approve"], scope="Assigned")
    world.limit(CO, "SitePM", "Bill", 100_000)
    site_pm = world.user("sitepm")
    world.grant(site_pm, CO, "SitePM")
    project_id = world.project(CO)
    request_id = approvals.submit_for_approval(team["ctx"]("clerk"), "Bill", "invoice", 9, 10,
                                               created_by=team["clerk"], project_id=project_id)
    assert request_row(world, request_id)["project_id"] == project_id
    with pytest.raises(PermissionDeniedError):
        approvals.approve(world.ctx(site_pm, CO), request_id)
    world.assign(CO, site_pm, project_id)
    assert approvals.approve(world.ctx(site_pm, CO), request_id) == "Approved"


# --- Limits for every document type ----------------------------------------------------------

@pytest.mark.parametrize("document_type, approve_code, submit_code", [
    ("Estimate", "estimate.approve", "estimate.create"),
    ("Change order", "change_order.approve", "change_order.create"),
    ("Contract", "contract.approve", "project.manage"),
])
def test_non_admin_with_a_covering_limit_can_approve(world, team, document_type, approve_code, submit_code):
    world.role(CO, "Estimator", [submit_code])
    world.role(CO, "Approver", [approve_code])
    estimator, approver = world.user("estimator"), world.user("approver2")
    world.grant(estimator, CO, "Estimator")
    world.grant(approver, CO, "Approver")
    approvals.set_approval_limit(team["ctx"]("mgr"), "Approver", document_type, 50_000)
    request_id = approvals.submit_for_approval(world.ctx(estimator, CO), document_type, "estimate", 1, 50_000,
                                               created_by=estimator)
    assert approvals.approve(world.ctx(approver, CO), request_id) == "Approved"
    over = approvals.submit_for_approval(world.ctx(estimator, CO), document_type, "estimate", 2, 50_001,
                                         created_by=estimator)
    with pytest.raises(PermissionDeniedError):
        approvals.approve(world.ctx(approver, CO), over)


# --- Step 4 part A: edits after approval, one transaction, person only, status rules ---------

def test_edit_after_approval_cancels_the_approval(world, team):
    """R21 (G1): an approved document edited afterwards is no longer approved."""
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    assert approved(world, 1) is True
    edit = team["ctx"]("clerk")
    assert approvals.cancel_on_edit(edit, "invoice", 1) is True
    row = request_row(world, request_id)
    assert (row["status"], row["completed_at"]) == ("Cancelled", edit.now)
    assert approved(world, 1) is False
    assert [a["decision"] for a in actions(world, request_id)] == ["Approve"]  # the approval stays on record


def test_edit_after_rejection_leaves_the_rejection(world, team):
    """R22: the rejected request stays Rejected with its reason; an edit has nothing to cancel."""
    request_id = submit(team)
    approvals.reject(team["ctx"]("pm1"), request_id, "wrong vendor")
    assert approvals.cancel_on_edit(team["ctx"]("clerk"), "invoice", 1) is False
    row = request_row(world, request_id)
    assert row["status"] == "Rejected"
    assert actions(world, request_id)[0]["reason"] == "wrong vendor"


def test_cancel_in_transaction_is_part_of_the_callers_change(world, team):
    """R21 (G2): the cancel and the edit commit or roll back together."""
    from modules.services.tx import write_transaction
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    ctx = team["ctx"]("clerk")
    with pytest.raises(RuntimeError):
        with write_transaction(ctx.company_db_path, ctx) as conn:
            assert approvals.cancel_in_transaction(conn, ctx, "invoice", 1) is True
            raise RuntimeError("the edit failed")
    assert request_row(world, request_id)["status"] == "Approved"
    with write_transaction(ctx.company_db_path, ctx) as conn:
        assert approvals.cancel_in_transaction(conn, ctx, "invoice", 1) is True
        assert approvals.cancel_in_transaction(conn, ctx, "invoice", 1) is False  # nothing left to cancel
    assert request_row(world, request_id)["status"] == "Cancelled"


def test_cancel_in_transaction_cancels_pending(world, team):
    from modules.services.tx import write_transaction
    request_id = submit(team)
    ctx = team["ctx"]("clerk")
    with write_transaction(ctx.company_db_path, ctx) as conn:
        assert approvals.cancel_in_transaction(conn, ctx, "invoice", 1) is True
    assert request_row(world, request_id)["status"] == "Cancelled"
    assert approvals.cancel_on_edit(ctx, "invoice", 1) is False


@pytest.mark.parametrize("origin", ["Import", "System"])
@pytest.mark.parametrize("who", ["pm1", "admin", "master"])
def test_only_a_person_approves_or_rejects(world, team, origin, who):
    """R23 (G4): an Import or System context holding the approve permission is refused, and the denial logged."""
    request_id = submit(team)
    with pytest.raises(PermissionDeniedError, match="Only a person"):
        approvals.approve(team["ctx"](who, origin=origin), request_id)
    with pytest.raises(PermissionDeniedError, match="Only a person"):
        approvals.reject(team["ctx"](who, origin=origin), request_id, "no")
    assert actions(world, request_id) == []
    assert request_row(world, request_id)["status"] == "Pending"
    denials = world.rows(CO, "SELECT user_id, actor_type, origin, record_type, record_id FROM access_event "
                             "WHERE event_type = 'Denied'")
    expected = {"user_id": team[who], "actor_type": "Master" if who == "master" else "User", "origin": origin,
                "record_type": "approval_request", "record_id": request_id}
    assert denials[-2:] == [expected] * 2


@pytest.mark.parametrize("old, new, allowed", [
    ("Pending", "Approved", True), ("Pending", "Rejected", True), ("Pending", "Cancelled", True),
    ("Approved", "Cancelled", True),
    ("Approved", "Pending", False), ("Approved", "Rejected", False),
    ("Rejected", "Approved", False), ("Rejected", "Cancelled", False), ("Rejected", "Pending", False),
    ("Cancelled", "Approved", False), ("Cancelled", "Pending", False), ("Cancelled", "Rejected", False),
    ("Pending", "Pending", False), ("Approved", "Approved", False),
])
def test_request_status_changes(world, team, old, new, allowed):
    """R16: the allowed status changes are a service rule (H4), checked on every write."""
    from modules.services.tx import write_transaction
    request_id = submit(team)
    ctx = team["ctx"]("admin")
    if old != "Pending":
        with write_transaction(ctx.company_db_path, ctx) as conn:
            approvals._change_status(conn, request_id, old, ctx.now)
    with write_transaction(ctx.company_db_path, ctx) as conn:
        if allowed:
            approvals._change_status(conn, request_id, new, ctx.now)
        else:
            with pytest.raises(ValidationError):
                approvals._change_status(conn, request_id, new, ctx.now)
    assert request_row(world, request_id)["status"] == (new if allowed else old)


def test_status_changes_table_is_the_decided_one():
    assert approvals.ALLOWED_STATUS_CHANGES == {
        "Pending": {"Approved", "Rejected", "Cancelled"}, "Approved": {"Cancelled"},
        "Rejected": set(), "Cancelled": set()}
