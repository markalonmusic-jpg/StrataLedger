"""authorize(): the service layer's permission check (docs/roles_permissions_design.md sections 7-10)."""
import logging
import sqlite3

import pytest

from modules.services import authz, permissions
from modules.services.errors import PermissionDeniedError
from modules.services.tx import write_transaction
from tests.authz_world import world  # noqa: F401  (fixture)

ALL_CODES = sorted(permissions.PERMISSIONS)


def allowed(context, permission, project_id=None):
    try:
        authz.authorize(context, permission, project_id)
    except PermissionDeniedError:
        return False
    return True


@pytest.fixture
def staff(world):
    """A normal user with role R in PARENT."""
    user_id = world.user("staff")
    world.role("PARENT", "R", ["ledger.view"])
    world.grant(user_id, "PARENT", "R")
    return user_id


# --- Programming errors -------------------------------------------------------------

def test_unknown_permission_is_a_programming_error_and_is_not_logged(world, staff):
    with pytest.raises(ValueError):
        authz.authorize(world.ctx(staff, "PARENT"), "nope.nope")
    assert world.events("PARENT") == []


# --- Each permission allowed and denied --------------------------------------------------

@pytest.mark.parametrize("code", ALL_CODES)
def test_each_permission_is_allowed_with_it_and_denied_without_it(world, code):
    holder, other = world.user("holder"), world.user("other")
    world.role("PARENT", "HAS", [code])
    world.role("PARENT", "LACKS", [c for c in ALL_CODES if c != code][:1])
    world.grant(holder, "PARENT", "HAS")
    world.grant(other, "PARENT", "LACKS")
    assert allowed(world.ctx(holder, "PARENT"), code)
    assert not allowed(world.ctx(other, "PARENT"), code)


# --- Changes apply on the next call (never cached) ---------------------------------------------

def test_role_permission_change_applies_on_the_next_call(world, staff):
    ctx = world.ctx(staff, "PARENT")
    assert not allowed(ctx, "je.create")
    world.grant_permission("PARENT", "R", "je.create")
    assert allowed(ctx, "je.create")
    world.remove_permission("PARENT", "R", "je.create")
    assert not allowed(ctx, "je.create")


def test_inactive_role_is_denied_on_the_next_call(world, staff):
    ctx = world.ctx(staff, "PARENT")
    assert allowed(ctx, "ledger.view")
    world.set_role_active("PARENT", "R", False)
    assert not allowed(ctx, "ledger.view")


def test_access_role_change_in_the_master_applies_on_the_next_call(world, staff):
    world.role("PARENT", "V", ["ar.view"])
    ctx = world.ctx(staff, "PARENT")
    assert not allowed(ctx, "ar.view")
    world.grant(staff, "PARENT", "V")
    assert allowed(ctx, "ar.view")
    assert not allowed(ctx, "ledger.view")


def test_inactive_user_is_denied(world, staff):
    ctx = world.ctx(staff, "PARENT")
    world.set_user_active(staff, False)
    assert not allowed(ctx, "ledger.view")


def test_missing_user_is_denied(world):
    assert not allowed(world.ctx(9999, "PARENT"), "ledger.view")


def test_role_code_missing_from_the_company_is_denied(world):
    user_id = world.user("ghost")
    world.grant(user_id, "PARENT", "NoSuchRole")
    assert not allowed(world.ctx(user_id, "PARENT"), "ledger.view")


def test_access_row_without_a_role_is_denied(world):
    user_id = world.user("norole")
    world.grant(user_id, "PARENT", None)
    assert not allowed(world.ctx(user_id, "PARENT"), "ledger.view")


# --- Per-company roles and the company tree -----------------------------------------------

def test_same_user_two_companies_two_roles(world):
    user_id = world.user("both")
    world.role("PARENT", "Accountant", ["je.create", "ledger.view"])
    world.role("OTHER", "Viewer", ["ledger.view"])
    world.grant(user_id, "PARENT", "Accountant")
    world.grant(user_id, "OTHER", "Viewer")
    assert allowed(world.ctx(user_id, "PARENT"), "je.create")
    assert not allowed(world.ctx(user_id, "OTHER"), "je.create")
    assert allowed(world.ctx(user_id, "OTHER"), "ledger.view")


def test_no_access_row_is_denied(world, staff):
    world.role("OTHER", "R", ["ledger.view"])
    assert not allowed(world.ctx(staff, "OTHER"), "ledger.view")


def test_access_at_the_parent_covers_the_subsidiary(world, staff):
    world.role("CHILD", "R", ["ledger.view"])  # the code resolves in the child's own role table
    assert allowed(world.ctx(staff, "CHILD"), "ledger.view")


def test_inherited_role_missing_in_the_child_is_denied(world, staff):
    assert not allowed(world.ctx(staff, "CHILD"), "ledger.view")


def test_deny_on_the_child_narrows_inherited_access(world, staff):
    world.role("CHILD", "R", ["ledger.view"])
    world.grant(staff, "CHILD", None, mode="Deny")
    assert not allowed(world.ctx(staff, "CHILD"), "ledger.view")
    assert allowed(world.ctx(staff, "PARENT"), "ledger.view")


def test_nearest_row_wins_grant_on_child_under_denied_parent(world):
    user_id = world.user("childonly")
    world.role("CHILD", "R", ["ledger.view"])
    world.grant(user_id, "PARENT", None, mode="Deny")
    world.grant(user_id, "CHILD", "R")
    assert allowed(world.ctx(user_id, "CHILD"), "ledger.view")
    assert not allowed(world.ctx(user_id, "PARENT"), "ledger.view")


def test_admin_of_the_parent_reaches_the_child_but_not_other_companies(world):
    admin = world.user("admin")
    world.grant(admin, "PARENT", "Admin")
    assert allowed(world.ctx(admin, "PARENT"), "company.settings")
    assert allowed(world.ctx(admin, "CHILD"), "company.settings")
    assert not allowed(world.ctx(admin, "OTHER"), "ledger.view")


# --- Master ---------------------------------------------------------------------------

@pytest.mark.parametrize("company", ["PARENT", "CHILD", "OTHER"])
def test_master_has_universal_access_without_access_rows(world, company):
    master = world.user("owner", master=True)
    for code in ALL_CODES:
        assert allowed(world.ctx(master, company), code, project_id=1), code


def test_master_opening_a_company_is_logged(world):
    master = world.user("owner", master=True)
    assert authz.record_company_open(world.ctx(master, "OTHER")) is True
    events = world.events("OTHER")
    assert len(events) == 1
    event = events[0]
    assert (event["event_type"], event["actor_type"], event["user_id"]) == ("Open company", "Master", master)
    assert event["occurred_at"].endswith("+00:00")


def test_normal_user_opening_a_company_writes_nothing(world, staff):
    assert authz.record_company_open(world.ctx(staff, "PARENT")) is False
    assert world.events("PARENT") == []


# --- Inactive (archived) company ---------------------------------------------------------------

def test_inactive_company_denies_everyone(world, staff):
    admin = world.user("admin")
    world.grant(admin, "PARENT", "Admin")
    world.set_company_active("PARENT", False)
    assert not allowed(world.ctx(staff, "PARENT"), "ledger.view")
    assert not allowed(world.ctx(admin, "PARENT"), "company.backup")


def test_inactive_company_allows_the_master_only_backup_and_restore(world):
    master = world.user("owner", master=True)
    world.set_company_active("PARENT", False)
    ctx = world.ctx(master, "PARENT")
    assert allowed(ctx, "company.backup")
    assert allowed(ctx, "company.restore")
    assert not allowed(ctx, "ledger.view")
    assert not allowed(ctx, "je.create")


# --- Agent ------------------------------------------------------------------------------

AGENT_DENIED = sorted(set(ALL_CODES) - set(permissions.AGENT_ALLOWED))


@pytest.mark.parametrize("code", AGENT_DENIED)
def test_agent_is_denied_every_code_outside_the_allow_list_as_master_and_as_admin(world, code):
    master = world.user("owner", master=True)
    admin = world.user("admin")
    world.grant(admin, "PARENT", "Admin")
    assert not allowed(world.ctx(master, "PARENT", origin="Agent"), code, project_id=1)
    assert not allowed(world.ctx(admin, "PARENT", origin="Agent"), code, project_id=1)


@pytest.mark.parametrize("code", sorted(permissions.AGENT_ALLOWED))
def test_agent_may_use_allowed_codes_that_the_user_holds(world, code):
    admin = world.user("admin")
    world.grant(admin, "PARENT", "Admin")
    assert allowed(world.ctx(admin, "PARENT", origin="Agent"), code, project_id=1)


def test_agent_still_needs_the_users_permission(world, staff):
    assert not allowed(world.ctx(staff, "PARENT", origin="Agent"), "ar.view")


def test_a_new_registry_code_is_denied_to_agents_by_default(world, monkeypatch):
    master = world.user("owner", master=True)
    monkeypatch.setitem(permissions.PERMISSIONS, "future.view",
                        permissions.Permission("Future", "A later module", False))
    assert allowed(world.ctx(master, "PARENT"), "future.view")
    assert not allowed(world.ctx(master, "PARENT", origin="Agent"), "future.view")


def test_agent_denial_happens_before_any_database_read(world, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("database read before the agent check")
    monkeypatch.setattr(authz.database, "get_readonly_connection", boom)
    master = world.user("owner", master=True)
    with pytest.raises(PermissionDeniedError):
        authz.authorize(world.ctx(master, "PARENT", origin="Agent"), "je.post")
    assert world.events("PARENT")[0]["actor_type"] == "Agent"


# --- Project scope -------------------------------------------------------------------------

@pytest.fixture
def pm(world):
    user_id = world.user("pm")
    world.role("PARENT", "PM", ["project.view", "bill.approve", "project.create", "ledger.view"], scope="Assigned")
    world.grant(user_id, "PARENT", "PM")
    return user_id


def test_assigned_role_reaches_only_its_projects(world, pm):
    mine, theirs = world.project("PARENT"), world.project("PARENT")
    world.assign("PARENT", pm, mine)
    ctx = world.ctx(pm, "PARENT")
    assert allowed(ctx, "project.view", mine)
    assert not allowed(ctx, "project.view", theirs)


def test_assigned_role_without_a_project_is_denied_on_scoped_permissions(world, pm):
    ctx = world.ctx(pm, "PARENT")
    assert not allowed(ctx, "project.view")
    assert not allowed(ctx, "bill.approve")  # a bill with no project: intended (2.2b decision 3)


def test_assigned_role_without_a_project_is_allowed_on_unscoped_permissions(world, pm):
    ctx = world.ctx(pm, "PARENT")
    assert allowed(ctx, "ledger.view")
    assert allowed(ctx, "project.create")


def test_all_scope_role_is_not_limited(world):
    user_id = world.user("gm")
    world.role("PARENT", "GM", ["project.view"], scope="All")
    world.grant(user_id, "PARENT", "GM")
    project_id = world.project("PARENT")
    assert allowed(world.ctx(user_id, "PARENT"), "project.view", project_id)
    assert allowed(world.ctx(user_id, "PARENT"), "project.view")


# --- Denial log -----------------------------------------------------------------------------

def test_denial_is_logged_without_values(world, staff):
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(world.ctx(staff, "PARENT"), "je.post", record_type="journal_entry", record_id=42)
    assert str(error.value) == "Not permitted: je.post"
    event = world.events("PARENT")[0]
    assert event == {
        "event_id": event["event_id"], "occurred_at": event["occurred_at"], "user_id": staff,
        "actor_type": "User", "event_type": "Denied", "permission_code": "je.post",
        "record_type": "journal_entry", "record_id": 42, "origin": "Human",
    }
    assert event["occurred_at"].endswith("+00:00")


def test_allowed_calls_write_nothing(world, staff):
    authz.authorize(world.ctx(staff, "PARENT"), "ledger.view")
    assert world.events("PARENT") == []


def test_denial_log_survives_the_callers_rollback(world, staff):
    ctx = world.ctx(staff, "PARENT")
    with pytest.raises(RuntimeError):
        try:
            authz.authorize(ctx, "je.post")
        except PermissionDeniedError:
            with write_transaction(world.path("PARENT"), ctx) as conn:
                conn.execute("INSERT INTO contact (name) VALUES ('rolled back')")
                raise RuntimeError("caller fails")
    assert len(world.events("PARENT")) == 1
    assert world.rows("PARENT", "SELECT * FROM contact WHERE name = 'rolled back'") == []


def test_denial_is_raised_and_logged_to_file_when_the_database_is_locked(world, staff, monkeypatch, caplog):
    monkeypatch.setattr(authz, "ACCESS_EVENT_BUSY_TIMEOUT_MS", 50)
    blocker = sqlite3.connect(world.path("PARENT"), isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with caplog.at_level(logging.ERROR, logger="strataledger"):
            with pytest.raises(PermissionDeniedError):
                authz.authorize(world.ctx(staff, "PARENT"), "je.post")
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert any("access_event" in r.getMessage() and "je.post" in r.getMessage() for r in caplog.records)
    assert world.events("PARENT") == []


# --- Approval limits ------------------------------------------------------------------------

@pytest.fixture
def approver(world):
    user_id = world.user("approver")
    world.role("PARENT", "AP", ["bill.approve"])
    world.limit("PARENT", "AP", "Bill", 100_000)
    world.grant(user_id, "PARENT", "AP")
    return user_id


def test_approval_limit_boundary(world, approver):
    ctx = world.ctx(approver, "PARENT")
    authz.check_approval_limit(ctx, "Bill", 100_000)
    with pytest.raises(PermissionDeniedError):
        authz.check_approval_limit(ctx, "Bill", 100_001)
    assert world.events("PARENT")[-1]["permission_code"] == "bill.approve"


def test_no_limit_row_is_denied(world, approver):
    world.grant_permission("PARENT", "AP", "po.approve")
    with pytest.raises(PermissionDeniedError):
        authz.check_approval_limit(world.ctx(approver, "PARENT"), "Purchase order", 1)


def test_limit_needs_the_approve_permission_first(world):
    user_id = world.user("nolimitperm")
    world.role("PARENT", "X", [])
    world.limit("PARENT", "X", "Bill", 10**9)
    world.grant(user_id, "PARENT", "X")
    with pytest.raises(PermissionDeniedError):
        authz.check_approval_limit(world.ctx(user_id, "PARENT"), "Bill", 1)


def test_admin_and_master_are_unlimited(world):
    admin, master = world.user("admin"), world.user("owner", master=True)
    world.grant(admin, "PARENT", "Admin")
    for user_id in (admin, master):
        authz.check_approval_limit(world.ctx(user_id, "PARENT"), "Bill", 10**12)


def test_limit_respects_project_scope(world):
    user_id = world.user("scopedpm")
    world.role("PARENT", "PM", ["bill.approve"], scope="Assigned")
    world.limit("PARENT", "PM", "Bill", 1000)
    world.grant(user_id, "PARENT", "PM")
    project_id = world.project("PARENT")
    with pytest.raises(PermissionDeniedError):
        authz.check_approval_limit(world.ctx(user_id, "PARENT"), "Bill", 10, project_id)
    world.assign("PARENT", user_id, project_id)
    authz.check_approval_limit(world.ctx(user_id, "PARENT"), "Bill", 10, project_id)
