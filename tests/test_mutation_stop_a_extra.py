"""Tests written to kill the survivors of the Phase 2.7 STOP A mutation run (not committed)."""
import pytest

from modules.services import approvals, authz, users
from modules.services.errors import PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_authz_multi_role import CO, chain  # noqa: F401  (fixture)
from tests.test_authz_multi_role import _request
from tests.test_users_access import NEW, org  # noqa: F401  (fixture)
from tests.test_payments import allocate, document, payment, pay  # noqa: F401  (fixtures and helpers)
from tests.test_ledger_posting import ctx_for, env, keyed  # noqa: F401


def _denied(call, *args, **kwargs):
    with pytest.raises(PermissionDeniedError) as denied:
        call(*args, **kwargs)
    return str(denied.value)


# --- authz ---

def test_the_highest_limit_counts_when_it_sits_on_the_later_sorted_role(world):
    """A29b: the lower limit is on the role that sorts first."""
    user_id = world.user("lim")
    world.role(CO, "Alow", ["bill.approve"])
    world.role(CO, "Zhigh", ["bill.approve"])
    world.limit(CO, "Alow", "Bill", 1_000)
    world.limit(CO, "Zhigh", "Bill", 5_000)
    world.grant(user_id, CO, None)
    world.add_roles(user_id, CO, "Alow", "Zhigh")
    authz.check_approval_limit(world.ctx(user_id, CO), "Bill", 5_000)


def _limit_world(world):
    clerk, boss = world.user("clerk"), world.user("boss")
    world.role(CO, "Clerk", ["bill.approve"])
    world.role(CO, "Boss", ["bill.approve"])
    world.limit(CO, "Clerk", "Bill", 10)
    world.limit(CO, "Boss", "Bill", 5_000)
    world.grant(clerk, CO, "Clerk")
    world.grant(boss, CO, None)
    world.role(CO, "Aaa", ["ledger.view"])
    world.add_roles(boss, CO, "Aaa", "Boss")
    return clerk, boss


def test_a_role_holder_through_a_later_sorted_role_is_named(world):
    """A35: the holder's Boss role sorts after Aaa."""
    clerk, boss = _limit_world(world)
    assert "someone in the Boss role" in _denied(authz.check_approval_limit, world.ctx(clerk, CO), "Bill", 4_000)


def test_a_left_out_user_is_not_named_as_a_role_holder(world):
    """A32: the only Boss is left out (separation of duties), so no one else can approve."""
    clerk, boss = _limit_world(world)
    message = _denied(authz.check_approval_limit, world.ctx(clerk, CO), "Bill", 4_000, not_counted={boss})
    assert message == authz.NO_ONE_ELSE_CAN_APPROVE


def test_an_admin_through_a_later_sorted_role_row_is_an_available_admin(world):
    """A34: Admin sorts after Aaa in the role rows."""
    clerk, boss = _limit_world(world)
    admin = world.user("adm")
    world.grant(admin, CO, None)
    world.add_roles(admin, CO, "Aaa", "Admin")
    message = _denied(authz.check_approval_limit, world.ctx(clerk, CO), "Bill", 4_000, not_counted={boss})
    assert "an Admin" in message and message != authz.NO_ONE_ELSE_CAN_APPROVE


def test_a_null_role_grant_is_no_access_not_a_wrong_file(world):
    """A3: a Grant row without a role gives no roles, so a wrong company file is not revealed to it."""
    user_id = world.user("nullrole")
    world.grant(user_id, CO, None)
    wrong = world.ctx(user_id, CO)
    wrong = type(wrong)(user_id=wrong.user_id, company_id=wrong.company_id, origin=wrong.origin,
                        company_db_path=str(world.path("OTHER")), master_db_path=wrong.master_db_path)
    assert "do not have access" in _denied(authz.authorize, wrong, "ledger.view")


# --- approvals ---

def test_the_later_step_hint_is_not_given_to_someone_who_cannot_fill_it(world, chain):
    """P6: the PM cannot fill step 2 (Controller), so no hint to wait for step 1."""
    request_id = _request(chain, [(1, "Manager", 1), (2, "Controller", 1)])
    message = _denied(approvals.approve, chain["ctx"]("pm"), request_id)
    assert "you can approve" not in message and "Step 1 of 2 needs approval" in message


def test_the_later_step_hint_counts_the_second_role(world, chain):
    """P7: the user holds Controller and PM; step 2 needs PM, the second role."""
    request_id = _request(chain, [(1, "Manager", 1), (2, "PM", 1)])
    assert "you can approve step 2 once it is complete" in _denied(approvals.approve, chain["ctx"]("both"), request_id)


def test_record_refuses_when_the_slot_was_taken_after_the_plan(world, chain):
    """P14: _record re-checks the open slot inside the write transaction."""
    from modules.services.tx import write_transaction
    request_id = _request(chain, [(1, "PM", 1), (1, "Controller", 1)])
    context = chain["ctx"]("both")
    plan = approvals._plan(context, approvals._load_request(context, request_id))
    assert plan.slot.role_code == "Controller"
    assert approvals.approve(chain["ctx"]("ctrl"), request_id) == "Pending"     # the Controller slot is filled meanwhile
    with write_transaction(context.company_db_path, context) as conn:
        with pytest.raises(ValidationError, match="changed"):
            approvals._record(conn, context, plan, "Approve", None)


# --- users ---

def _admin2_behind_a_lower_role(world, org):
    world.role("PARENT", "Acct", ["ledger.view"])
    world.grant(org["admin2"], "PARENT", None)
    world.add_roles(org["admin2"], "PARENT", "Acct", "Admin")


def test_an_admin_behind_a_lower_sorted_role_is_protected(world, org):
    """U8, U10: Acct sorts before Admin."""
    _admin2_behind_a_lower_role(world, org)
    with pytest.raises(PermissionDeniedError):
        users.deny_access(org["s"]("admin"), org["admin2"], org["cid"]("PARENT"))
    with pytest.raises(PermissionDeniedError):
        users.reset_password(org["s"]("mgr"), org["admin2"], NEW)


def test_an_admin_behind_a_lower_sorted_role_counts_as_the_admin_of_the_company(world, org):
    """U13."""
    _admin2_behind_a_lower_role(world, org)
    users.set_role(org["s"]("master"), org["admin"], org["cid"]("PARENT"), "Viewer")


def test_an_archived_company_without_an_admin_does_not_block_a_deactivation(world, org):
    """U14: only active companies must keep an Admin."""
    world.grant(org["admin2"], "OTHER", "Admin")
    world.set_company_active("OTHER", False)
    users.deactivate_user(org["s"]("master"), org["admin2"])


def test_grant_access_keeps_the_role_rows_of_another_company(world, org):
    """U19."""
    world.grant(org["staff"], "OTHER", "Viewer")
    world.add_roles(org["staff"], "OTHER", "Viewer")
    users.grant_access(org["s"]("master"), org["staff"], org["cid"]("PARENT"), "UserMgr")
    rows = world.master_rows("SELECT role_code FROM user_company_role WHERE user_id = ? AND company_id = ?",
                             (org["staff"], org["cid"]("OTHER")))
    assert [r["role_code"] for r in rows] == ["Viewer"]


# --- payments ---

def test_the_master_in_an_archived_company_logs_the_side_of_the_source(pay):
    """Y8: a purchases-side source logs payment.make, not payment.receive."""
    bill, source = document(pay, "bill"), payment(pay, "Made", posted=False)
    master = pay.user("owner", master=True)
    pay.set_company_active("PARENT", False)
    with pytest.raises(PermissionDeniedError, match="This company is archived"):
        allocate(pay, ("payment", source), ("invoice", bill), 100, context=ctx_for(pay, user=master))
    assert pay.events("PARENT")[-1]["permission_code"] == "payment.make"
