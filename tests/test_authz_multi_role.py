"""Several roles per user per company (decisions RP10, MR2-MR5).

* user_company_access stays the gate: the nearest row up the parent chain, and a Deny row wins (MR2).
* The roles are that row's company's user_company_role rows, else its role_code (the fallback). Inactive or
  missing roles are skipped; the permissions are the union; Admin in any role allows everything (MR2).
* Project scope applies only when every role granting the permission is Assigned (MR3).
* The approval limit is the highest among the active roles that hold the approve permission (MR4).
* One person fills at most one slot of an approval chain, even through two roles (MR5).
"""
import pytest

from modules.services import approvals, authz
from modules.services.errors import PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)

CO = "PARENT"


def allowed(context, permission, project_id=None):
    try:
        authz.authorize(context, permission, project_id)
    except PermissionDeniedError:
        return False
    return True


def denial(context, permission, project_id=None):
    with pytest.raises(PermissionDeniedError) as denied:
        authz.authorize(context, permission, project_id)
    return str(denied.value)


@pytest.fixture
def two_roles(world):
    """A user holding View (ledger.view) and Entry (je.create) through user_company_role; the access row's own
    role_code is Other (ar.view), which the rows replace."""
    user_id = world.user("multi")
    world.role(CO, "View", ["ledger.view"])
    world.role(CO, "Entry", ["je.create"])
    world.role(CO, "Other", ["ar.view"])
    world.grant(user_id, CO, "Other")
    world.add_roles(user_id, CO, "View", "Entry")
    return user_id


# --- MR2: the union, the fallback, the gate ------------------------------------------------------------------

def test_permissions_are_the_union_of_the_roles(world, two_roles):
    ctx = world.ctx(two_roles, CO)
    assert allowed(ctx, "ledger.view")
    assert allowed(ctx, "je.create")
    assert not allowed(ctx, "je.post")
    assert authz.is_allowed(ctx, "ledger.view") and authz.is_allowed(ctx, "je.create")
    assert not authz.is_allowed(ctx, "je.post")


def test_the_rows_replace_the_access_role_code(world, two_roles):
    assert not allowed(world.ctx(two_roles, CO), "ar.view")


def test_with_no_rows_the_access_role_code_is_the_role(world):
    user_id = world.user("single")
    world.role(CO, "Other", ["ar.view"])
    world.grant(user_id, CO, "Other")
    assert allowed(world.ctx(user_id, CO), "ar.view")
    assert authz.current_access(world.ctx(user_id, CO)).role_codes == ("Other",)


def test_rows_of_another_company_are_not_the_fallbacks_concern(world):
    """Rows for OTHER do not stop PARENT's access row from using its role_code."""
    user_id = world.user("elsewhere")
    world.role(CO, "Other", ["ar.view"])
    world.role("OTHER", "View", ["ledger.view"])
    world.grant(user_id, CO, "Other")
    world.add_roles(user_id, "OTHER", "View")
    assert allowed(world.ctx(user_id, CO), "ar.view")


def test_an_inactive_role_is_skipped(world, two_roles):
    world.set_role_active(CO, "Entry", False)
    ctx = world.ctx(two_roles, CO)
    assert allowed(ctx, "ledger.view")
    assert not allowed(ctx, "je.create")
    assert authz.current_access(ctx).role_codes == ("View",)


def test_every_role_inactive_is_the_inactive_role_denial(world, two_roles):
    world.set_role_active(CO, "Entry", False)
    world.set_role_active(CO, "View", False)
    assert "role in this company is inactive" in denial(world.ctx(two_roles, CO), "ledger.view")
    with pytest.raises(PermissionDeniedError):
        authz.check_company_access(world.ctx(two_roles, CO))


def test_a_missing_role_is_skipped_and_no_existing_role_is_no_access(world):
    user_id = world.user("ghost")
    world.role(CO, "View", ["ledger.view"])
    world.grant(user_id, CO, None)
    world.add_roles(user_id, CO, "Gone", "View")
    assert allowed(world.ctx(user_id, CO), "ledger.view")
    other = world.user("ghost2")
    world.grant(other, CO, None)
    world.add_roles(other, CO, "Gone")
    assert "do not have access" in denial(world.ctx(other, CO), "ledger.view")


def test_a_deny_row_wins_over_the_roles(world, two_roles):
    world.grant(two_roles, CO, None, mode="Deny")
    assert "do not have access" in denial(world.ctx(two_roles, CO), "ledger.view")
    assert authz.current_access(world.ctx(two_roles, CO)).role_codes == ()


def test_roles_without_an_access_row_give_no_access(world):
    user_id = world.user("rowsonly")
    world.role(CO, "View", ["ledger.view"])
    world.add_roles(user_id, CO, "View")
    assert "do not have access" in denial(world.ctx(user_id, CO), "ledger.view")
    with pytest.raises(PermissionDeniedError):
        authz.check_company_access(world.ctx(user_id, CO))


def test_an_inherited_access_row_brings_its_own_companys_roles(world):
    """CHILD has no access row, so PARENT's row applies, with PARENT's role rows; CHILD's rows are not read."""
    user_id = world.user("inherit")
    for company in (CO, "CHILD"):
        world.role(company, "View", ["ledger.view"])
        world.role(company, "Entry", ["je.create"])
    world.grant(user_id, CO, None)
    world.add_roles(user_id, CO, "View")
    world.add_roles(user_id, "CHILD", "Entry")
    ctx = world.ctx(user_id, "CHILD")
    assert allowed(ctx, "ledger.view")
    assert not allowed(ctx, "je.create")


def test_admin_in_any_role_allows_everything(world, two_roles):
    world.add_roles(two_roles, CO, "Admin")
    ctx = world.ctx(two_roles, CO)
    assert allowed(ctx, "je.post") and allowed(ctx, "company.settings")
    assert authz.current_access(ctx).is_admin


def test_one_active_role_opens_the_company(world, two_roles):
    world.set_role_active(CO, "Entry", False)
    authz.check_company_access(world.ctx(two_roles, CO))


def test_current_access_lists_the_active_roles_sorted(world, two_roles):
    access = authz.current_access(world.ctx(two_roles, CO))
    assert access.role_codes == ("Entry", "View")
    assert not access.is_master and not access.is_admin


def test_a_change_to_the_rows_applies_on_the_next_call(world, two_roles):
    ctx = world.ctx(two_roles, CO)
    assert not allowed(ctx, "ar.view")
    world.add_roles(two_roles, CO, "Other")
    assert allowed(ctx, "ar.view")


# --- MR3: project scope ----------------------------------------------------------------------------------------

@pytest.fixture
def scoped(world):
    user_id = world.user("scoped")
    world.role(CO, "Site", ["bill.approve"], scope="Assigned")
    world.grant(user_id, CO, None)
    world.add_roles(user_id, CO, "Site")
    return user_id, world.project(CO)


def test_scope_applies_when_every_granting_role_is_assigned(world, scoped):
    user_id, project_id = scoped
    world.role(CO, "Site2", ["bill.approve"], scope="Assigned")
    world.add_roles(user_id, CO, "Site2")
    ctx = world.ctx(user_id, CO)
    assert not allowed(ctx, "bill.approve")
    assert not allowed(ctx, "bill.approve", project_id)
    world.assign(CO, user_id, project_id)
    assert allowed(ctx, "bill.approve", project_id)


def test_one_granting_role_with_all_projects_lifts_the_scope(world, scoped):
    user_id, project_id = scoped
    world.role(CO, "Wide", ["bill.approve"], scope="All")
    world.add_roles(user_id, CO, "Wide")
    ctx = world.ctx(user_id, CO)
    assert allowed(ctx, "bill.approve")
    assert allowed(ctx, "bill.approve", project_id)


def test_a_wide_role_without_the_permission_does_not_lift_the_scope(world, scoped):
    user_id, project_id = scoped
    world.role(CO, "Wide", ["ledger.view"], scope="All")
    world.add_roles(user_id, CO, "Wide")
    assert not allowed(world.ctx(user_id, CO), "bill.approve", project_id)


def test_an_inactive_wide_role_does_not_lift_the_scope(world, scoped):
    user_id, project_id = scoped
    world.role(CO, "Wide", ["bill.approve"], scope="All", active=False)
    world.add_roles(user_id, CO, "Wide")
    assert not allowed(world.ctx(user_id, CO), "bill.approve", project_id)


# --- MR4: the highest approval limit ----------------------------------------------------------------------------

@pytest.fixture
def limits(world):
    user_id = world.user("limits")
    world.role(CO, "Low", ["bill.approve"])
    world.role(CO, "High", ["bill.approve"])
    world.limit(CO, "Low", "Bill", 1_000)
    world.limit(CO, "High", "Bill", 5_000)
    world.grant(user_id, CO, None)
    world.add_roles(user_id, CO, "Low", "High")
    return user_id


def test_the_highest_limit_across_the_roles_applies(world, limits):
    ctx = world.ctx(limits, CO)
    authz.check_approval_limit(ctx, "Bill", 5_000)
    with pytest.raises(PermissionDeniedError, match="over your approval limit"):
        authz.check_approval_limit(ctx, "Bill", 5_001)
    assert "(50.00)" in str(pytest.raises(PermissionDeniedError, authz.check_approval_limit, ctx, "Bill", 5_001).value)


def test_a_role_without_the_approve_permission_brings_no_limit(world, limits):
    world.role(CO, "Huge", ["ledger.view"])
    world.limit(CO, "Huge", "Bill", 10**9)
    world.add_roles(limits, CO, "Huge")
    with pytest.raises(PermissionDeniedError):
        authz.check_approval_limit(world.ctx(limits, CO), "Bill", 5_001)


def test_an_inactive_role_brings_no_limit(world, limits):
    world.set_role_active(CO, "High", False)
    ctx = world.ctx(limits, CO)
    authz.check_approval_limit(ctx, "Bill", 1_000)
    with pytest.raises(PermissionDeniedError):
        authz.check_approval_limit(ctx, "Bill", 1_001)


def test_a_role_with_no_limit_row_does_not_cancel_another_roles_limit(world, limits):
    world.role(CO, "NoRow", ["bill.approve"])
    world.add_roles(limits, CO, "NoRow")
    authz.check_approval_limit(world.ctx(limits, CO), "Bill", 5_000)


def test_admin_through_a_role_row_is_unlimited(world, limits):
    world.add_roles(limits, CO, "Admin")
    authz.check_approval_limit(world.ctx(limits, CO), "Bill", 10**12)


def test_the_refusal_names_a_role_held_only_through_a_role_row(world, limits):
    clerk = world.user("clerk")
    world.role(CO, "Clerk", ["bill.approve"])
    world.limit(CO, "Clerk", "Bill", 10)
    world.grant(clerk, CO, "Clerk")
    with pytest.raises(PermissionDeniedError, match="someone in the High role"):
        authz.check_approval_limit(world.ctx(clerk, CO), "Bill", 4_000)


def test_another_admin_through_a_role_row_is_named(world):
    """_admin_target: an Admin held through user_company_role counts as an Admin."""
    world.settings(CO, require_separate_approver=1)
    first, second = world.user("admin1"), world.user("admin2")
    world.grant(first, CO, "Admin")
    world.grant(second, CO, None)
    world.add_roles(second, CO, "Admin")
    clerk = world.user("clerk2")
    world.role(CO, "Clerk", ["bill.approve"])
    world.grant(clerk, CO, "Clerk")
    with pytest.raises(PermissionDeniedError, match="ask another Admin"):
        authz.check_approval_limit(world.ctx(clerk, CO), "Bill", 1, not_counted={first})


# --- MR5: one slot per person per chain ------------------------------------------------------------------------

@pytest.fixture
def chain(world):
    world.settings(CO, require_separate_approver=1)
    world.role(CO, "Clerk", ["bill.create"])
    world.role(CO, "PM", ["bill.approve"])
    world.role(CO, "Controller", ["bill.approve"])
    world.role(CO, "Manager", ["company.roles.manage"])
    world.limit(CO, "PM", "Bill", 100_000)
    world.limit(CO, "Controller", "Bill", 100_000)
    people = {name: world.user(name) for name in ("clerk", "both", "ctrl", "pm", "mgr")}
    world.grant(people["clerk"], CO, "Clerk")
    world.grant(people["mgr"], CO, "Manager")
    world.grant(people["ctrl"], CO, "Controller")
    world.grant(people["pm"], CO, "PM")
    world.grant(people["both"], CO, None)
    world.add_roles(people["both"], CO, "PM", "Controller")
    people["ctx"] = lambda name: world.ctx(people[name], CO)
    return people


def _request(chain_people, steps):
    approvals.create_policy(chain_people["ctx"]("mgr"), "P", "Bill", 0, None, steps)
    return approvals.submit_for_approval(chain_people["ctx"]("clerk"), "Bill", "invoice", 1, 5_000,
                                         created_by=chain_people["clerk"])


def _actions(world, request_id):
    return [(a["user_id"], a["step_no"], a["role_code"]) for a in world.rows(
        CO, "SELECT * FROM approval_action WHERE request_id = ? ORDER BY action_id", (request_id,))]


def test_two_roles_never_fill_two_steps(world, chain):
    request_id = _request(chain, [(1, "PM", 1), (2, "Controller", 1)])
    assert approvals.approve(chain["ctx"]("both"), request_id) == "Pending"
    with pytest.raises(ValidationError, match="already acted"):
        approvals.approve(chain["ctx"]("both"), request_id)
    assert approvals.approve(chain["ctx"]("ctrl"), request_id) == "Approved"
    assert _actions(world, request_id) == [(chain["both"], 1, "PM"), (chain["ctrl"], 2, "Controller")]


def test_two_roles_never_fill_two_parallel_slots(world, chain):
    request_id = _request(chain, [(1, "PM", 1), (1, "Controller", 1)])
    assert approvals.approve(chain["ctx"]("both"), request_id) == "Pending"
    with pytest.raises(ValidationError, match="already acted"):
        approvals.approve(chain["ctx"]("both"), request_id)
    assert approvals.approve(chain["ctx"]("pm"), request_id) == "Approved"
    assert _actions(world, request_id) == [(chain["both"], 1, "Controller"), (chain["pm"], 1, "PM")]


def test_two_roles_never_reject_after_approving(world, chain):
    request_id = _request(chain, [(1, "PM", 1), (2, "Controller", 1)])
    approvals.approve(chain["ctx"]("both"), request_id)
    with pytest.raises(ValidationError, match="already acted"):
        approvals.reject(chain["ctx"]("both"), request_id, "no")


def test_a_second_role_fills_a_slot_the_first_cannot(world, chain):
    """The PM slot is already filled; the person's Controller role fills step 2's slot."""
    request_id = _request(chain, [(1, "PM", 1), (2, "Controller", 1)])
    approvals.approve(chain["ctx"]("pm"), request_id)
    assert approvals.approve(chain["ctx"]("both"), request_id) == "Approved"
    assert _actions(world, request_id) == [(chain["pm"], 1, "PM"), (chain["both"], 2, "Controller")]


def test_the_default_chain_stores_the_first_role_holding_the_permission(world, chain):
    world.role(CO, "Aaa", ["ledger.view"])
    world.add_roles(chain["both"], CO, "Aaa")
    request_id = approvals.submit_for_approval(chain["ctx"]("clerk"), "Bill", "invoice", 1, 5_000,
                                               created_by=chain["clerk"])
    assert approvals.approve(chain["ctx"]("both"), request_id) == "Approved"
    assert _actions(world, request_id) == [(chain["both"], 1, "Controller")]


def test_an_admin_through_a_role_row_fills_any_slot_once(world, chain):
    world.add_roles(chain["both"], CO, "Admin")
    request_id = _request(chain, [(1, "Manager", 1), (2, "Controller", 1)])
    assert approvals.approve(chain["ctx"]("both"), request_id) == "Pending"
    with pytest.raises(ValidationError, match="already acted"):
        approvals.approve(chain["ctx"]("both"), request_id)
    assert _actions(world, request_id) == [(chain["both"], 1, "Manager")]


def test_the_later_step_hint_counts_every_role(world, chain):
    """Step 1 needs a Manager; the person's Controller role can fill step 2, and the refusal says so."""
    request_id = _request(chain, [(1, "Manager", 1), (2, "Controller", 1)])
    with pytest.raises(PermissionDeniedError, match="you can approve step 2 once it is complete"):
        approvals.approve(chain["ctx"]("both"), request_id)
