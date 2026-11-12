"""User and access services (docs/roles_permissions_design.md sections 9-10)."""
import pytest

from modules.services import auth, authz, users
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import PASSWORD, world  # noqa: F401  (fixture)

NEW = "a brand new passphrase"


@pytest.fixture
def org(world):
    """Master; an Admin of PARENT (covers CHILD); a user manager in PARENT; OTHER is a separate client."""
    for company in ("PARENT", "CHILD", "OTHER"):
        world.role(company, "Viewer", ["ledger.view"])
    world.role("PARENT", "UserMgr", ["company.users.manage", "ledger.view", "je.create"])
    world.role("PARENT", "Same", ["company.users.manage", "ledger.view", "je.create"])
    world.role("PARENT", "Broad", ["ledger.view", "je.post"])
    people = {"master": world.user("owner", master=True)}
    for name in ("admin", "admin2", "mgr", "staff", "client"):
        people[name] = world.user(name)
    world.grant(people["admin"], "PARENT", "Admin")
    world.grant(people["mgr"], "PARENT", "UserMgr")
    world.grant(people["staff"], "PARENT", "Viewer")
    world.grant(people["client"], "OTHER", "Viewer")
    people["s"] = lambda name: world.session(people[name])
    people["cid"] = world.company_id
    return people


def access(world, user_id):
    return {(r["company_id"], r["role_code"], r["access_mode"])
            for r in world.master_rows("SELECT * FROM user_company_access WHERE user_id = ?", (user_id,))}


def can(world, user_id, company, code="ledger.view"):
    try:
        authz.authorize(world.ctx(user_id, company), code)
    except PermissionDeniedError:
        return False
    return True


# --- create_user ----------------------------------------------------------------------------

def test_master_creates_a_user_without_a_company(world, org):
    user_id = users.create_user(org["s"]("master"), "newbie", PASSWORD, "N", "B", "newbie@x.test")
    assert access(world, user_id) == set()
    auth.login(world.master, "newbie", PASSWORD)


def test_admin_creates_a_user_with_access_in_its_company(world, org):
    user_id = users.create_user(org["s"]("admin"), "hire", PASSWORD, "H", "I", "hire@x.test",
                                company_id=org["cid"]("CHILD"), role_code="Viewer")
    assert access(world, user_id) == {(org["cid"]("CHILD"), "Viewer", "Grant")}
    assert can(world, user_id, "CHILD")


def test_non_master_cannot_create_a_user_without_a_company(world, org):
    with pytest.raises(PermissionDeniedError):
        users.create_user(org["s"]("admin"), "loose", PASSWORD, "L", "O", "loose@x.test")
    assert world.master_rows("SELECT event_type FROM auth_event WHERE event_type = 'Denied'")


def test_admin_cannot_create_users_outside_its_companies(world, org):
    with pytest.raises(PermissionDeniedError):
        users.create_user(org["s"]("admin"), "spy", PASSWORD, "S", "P", "spy@x.test",
                          company_id=org["cid"]("OTHER"), role_code="Viewer")
    assert world.master_rows("SELECT * FROM app_user WHERE username = 'spy'") == []


def test_create_user_validates_inputs(world, org):
    master = org["s"]("master")
    with pytest.raises(ValidationError):
        users.create_user(master, "x", "short", "A", "B", "a@x.test")
    with pytest.raises(ValidationError):
        users.create_user(master, "bad name!", PASSWORD, "A", "B", "a@x.test")
    with pytest.raises(ValidationError):
        users.create_user(master, "okname", PASSWORD, "", "B", "a@x.test")
    with pytest.raises(ValidationError):
        users.create_user(master, "okname", PASSWORD, "A", "B", "no-at-sign")
    with pytest.raises(ValidationError):
        users.create_user(master, "okname", PASSWORD, "A", "B", "a@x.test", company_id=org["cid"]("PARENT"))
    with pytest.raises(ValidationError):
        users.create_user(master, "staff", PASSWORD, "A", "B", "unique@x.test")  # username taken


def test_duplicate_email_gives_a_non_master_a_neutral_message(world, org):
    messages = set()
    for email in ("client@x.test", "CLIENT@X.TEST", "staff@x.test"):  # another client's user, and its own
        with pytest.raises(ValidationError) as error:
            users.create_user(org["s"]("admin"), "dupe", PASSWORD, "D", "U", email,
                              company_id=org["cid"]("PARENT"), role_code="Viewer")
        messages.add(str(error.value))
    assert messages == {"This person may already have an account. Ask your Master to grant access."}
    assert "client" not in next(iter(messages))


def test_duplicate_email_tells_the_master_plainly(world, org):
    with pytest.raises(ValidationError) as error:
        users.create_user(org["s"]("master"), "dupe", PASSWORD, "D", "U", "client@x.test")
    assert "already used" in str(error.value)


# --- The Admin role is the Master's to give and take ---------------------------------------------

def test_only_the_master_assigns_the_admin_role(world, org):
    with pytest.raises(PermissionDeniedError):
        users.grant_access(org["s"]("admin"), org["staff"], org["cid"]("CHILD"), "Admin")
    with pytest.raises(PermissionDeniedError):
        users.set_role(org["s"]("admin"), org["staff"], org["cid"]("PARENT"), "Admin")
    with pytest.raises(PermissionDeniedError):
        users.create_user(org["s"]("admin"), "boss2", PASSWORD, "B", "O", "boss2@x.test",
                          company_id=org["cid"]("PARENT"), role_code="Admin")
    users.grant_access(org["s"]("master"), org["admin2"], org["cid"]("PARENT"), "Admin")
    assert can(world, org["admin2"], "CHILD", "company.settings")


def test_only_the_master_removes_the_admin_role(world, org):
    users.grant_access(org["s"]("master"), org["admin2"], org["cid"]("PARENT"), "Admin")
    with pytest.raises(PermissionDeniedError):
        users.set_role(org["s"]("admin"), org["admin2"], org["cid"]("PARENT"), "Viewer")
    with pytest.raises(PermissionDeniedError):
        users.deny_access(org["s"]("admin"), org["admin2"], org["cid"]("PARENT"))
    users.set_role(org["s"]("master"), org["admin2"], org["cid"]("PARENT"), "Viewer")
    assert not can(world, org["admin2"], "PARENT", "company.settings")


# --- Last Admin and the Master are protected ------------------------------------------------------

def test_the_last_admin_cannot_be_removed(world, org):
    master = org["s"]("master")
    with pytest.raises(ValidationError):
        users.set_role(master, org["admin"], org["cid"]("PARENT"), "Viewer")
    with pytest.raises(ValidationError):
        users.deny_access(master, org["admin"], org["cid"]("PARENT"))
    with pytest.raises(ValidationError):
        users.deactivate_user(master, org["admin"])
    assert can(world, org["admin"], "PARENT", "company.settings")


def test_a_child_whose_only_admin_is_inherited_keeps_it(world, org):
    # admin covers CHILD only through PARENT; denying admin on CHILD would leave CHILD with no Admin.
    with pytest.raises(ValidationError):
        users.deny_access(org["s"]("master"), org["admin"], org["cid"]("CHILD"))


def test_an_admin_can_be_removed_when_another_remains(world, org):
    master = org["s"]("master")
    users.grant_access(master, org["admin2"], org["cid"]("PARENT"), "Admin")
    users.set_role(master, org["admin"], org["cid"]("PARENT"), "Viewer")
    assert not can(world, org["admin"], "PARENT", "company.settings")


def test_the_master_cannot_be_deactivated_or_given_access_rows(world, org):
    with pytest.raises(ValidationError):
        users.deactivate_user(org["s"]("master"), org["master"])
    with pytest.raises(ValidationError):
        users.grant_access(org["s"]("master"), org["master"], org["cid"]("PARENT"), "Viewer")


def test_deactivate_user_is_master_only(world, org):
    with pytest.raises(PermissionDeniedError):
        users.deactivate_user(org["s"]("admin"), org["staff"])
    users.deactivate_user(org["s"]("master"), org["staff"])
    assert not can(world, org["staff"], "PARENT")
    with pytest.raises(NotFoundError):
        users.deactivate_user(org["s"]("master"), 9999)


# --- Access changes and inheritance ------------------------------------------------------------

def test_grant_set_and_deny_take_effect_on_the_next_call(world, org):
    admin = org["s"]("admin")
    newbie = world.user("newbie")
    assert not can(world, newbie, "CHILD")
    users.grant_access(admin, newbie, org["cid"]("CHILD"), "Viewer")
    assert can(world, newbie, "CHILD")
    world.role("CHILD", "Poster", ["je.post"])
    users.set_role(admin, newbie, org["cid"]("CHILD"), "Poster")
    assert can(world, newbie, "CHILD", "je.post") and not can(world, newbie, "CHILD")
    users.deny_access(admin, newbie, org["cid"]("CHILD"))
    assert not can(world, newbie, "CHILD", "je.post")


def test_deny_on_a_child_narrows_inherited_access(world, org):
    users.deny_access(org["s"]("admin"), org["staff"], org["cid"]("CHILD"))
    assert can(world, org["staff"], "PARENT") and not can(world, org["staff"], "CHILD")


def test_admin_acts_only_in_its_tree(world, org):
    with pytest.raises(PermissionDeniedError):
        users.grant_access(org["s"]("admin"), org["staff"], org["cid"]("OTHER"), "Viewer")
    with pytest.raises(PermissionDeniedError):
        users.deny_access(org["s"]("admin"), org["client"], org["cid"]("OTHER"))


def test_role_must_exist_and_be_active_in_the_target_company(world, org):
    with pytest.raises(NotFoundError):
        users.grant_access(org["s"]("admin"), org["staff"], org["cid"]("CHILD"), "UserMgr")  # only in PARENT
    world.set_role_active("CHILD", "Viewer", False)
    with pytest.raises(ValidationError):
        users.grant_access(org["s"]("admin"), org["staff"], org["cid"]("CHILD"), "Viewer")


def test_set_role_needs_an_existing_grant(world, org):
    with pytest.raises(NotFoundError):
        users.set_role(org["s"]("admin"), org["staff"], org["cid"]("CHILD"), "Viewer")


def test_services_need_users_manage(world, org):
    staff = org["s"]("staff")
    with pytest.raises(PermissionDeniedError):
        users.grant_access(staff, org["admin2"], org["cid"]("PARENT"), "Viewer")
    with pytest.raises(PermissionDeniedError):
        users.create_user(staff, "xx2", PASSWORD, "A", "B", "xx2@x.test", company_id=org["cid"]("PARENT"),
                          role_code="Viewer")


# --- Privilege ceiling --------------------------------------------------------------------------

def test_user_manager_may_assign_equal_or_narrower_roles(world, org):
    mgr = org["s"]("mgr")
    users.grant_access(mgr, org["admin2"], org["cid"]("PARENT"), "Viewer")
    users.set_role(mgr, org["admin2"], org["cid"]("PARENT"), "Same")
    users.create_user(mgr, "narrow", PASSWORD, "N", "A", "narrow@x.test", company_id=org["cid"]("PARENT"),
                      role_code="Viewer")


def test_user_manager_cannot_assign_a_broader_role_and_the_attempt_is_logged(world, org):
    mgr = org["s"]("mgr")
    for action in (
        lambda: users.grant_access(mgr, org["admin2"], org["cid"]("PARENT"), "Broad"),
        lambda: users.set_role(mgr, org["staff"], org["cid"]("PARENT"), "Broad"),
        lambda: users.create_user(mgr, "wide", PASSWORD, "W", "I", "wide@x.test", company_id=org["cid"]("PARENT"),
                                  role_code="Broad"),
    ):
        with pytest.raises(PermissionDeniedError):
            action()
    denied = [e for e in world.events("PARENT") if e["event_type"] == "Denied"]
    assert len(denied) == 3 and {e["permission_code"] for e in denied} == {"company.users.manage"}
    assert world.master_rows("SELECT * FROM app_user WHERE username = 'wide'") == []


def test_admin_and_master_have_no_ceiling(world, org):
    users.grant_access(org["s"]("admin"), org["admin2"], org["cid"]("PARENT"), "Broad")


# --- reset_password ----------------------------------------------------------------------------------

def test_master_resets_anyone_and_the_user_must_change(world, org):
    users.reset_password(org["s"]("master"), org["client"], NEW)
    session = auth.login(world.master, "client", NEW)
    assert session.must_change_password
    events = world.master_rows("SELECT event_type, user_id, actor_user_id FROM auth_event WHERE event_type = 'Password reset'")
    assert events == [{"event_type": "Password reset", "user_id": org["client"], "actor_user_id": org["master"]}]


def test_admin_resets_only_users_in_its_companies(world, org):
    users.reset_password(org["s"]("admin"), org["staff"], NEW)
    with pytest.raises(PermissionDeniedError):
        users.reset_password(org["s"]("admin"), org["client"], NEW)


def test_non_master_cannot_reset_the_master_or_an_admin(world, org):
    users.grant_access(org["s"]("master"), org["admin2"], org["cid"]("OTHER"), "Admin")
    with pytest.raises(PermissionDeniedError):
        users.reset_password(org["s"]("admin"), org["master"], NEW)
    with pytest.raises(PermissionDeniedError):
        users.reset_password(org["s"]("mgr"), org["admin"], NEW)
    users.grant_access(org["s"]("master"), org["admin2"], org["cid"]("PARENT"), "Viewer")
    with pytest.raises(PermissionDeniedError):
        users.reset_password(org["s"]("admin"), org["admin2"], NEW)  # Admin elsewhere


def test_reset_checks_the_password_policy(world, org):
    with pytest.raises(ValidationError):
        users.reset_password(org["s"]("master"), org["staff"], "short")


# --- Audit trail ------------------------------------------------------------------------------------

def test_access_and_role_changes_are_audited_with_the_actor(world, org):
    admin = org["s"]("admin")
    newbie = world.user("newbie")
    users.grant_access(admin, newbie, org["cid"]("CHILD"), "Viewer")
    users.deny_access(admin, newbie, org["cid"]("CHILD"))
    rows = world.master_rows(
        "SELECT action, user_id, new_value FROM audit_log WHERE table_name = 'user_company_access' ORDER BY log_id")
    assert [(r["action"], r["user_id"]) for r in rows][-2:] == [("Insert", org["admin"]), ("Update", org["admin"])]
    assert '"access_mode":"Deny"' in rows[-1]["new_value"].replace(" ", "")


def test_no_audit_row_ever_holds_a_password_hash(world, org):
    users.create_user(org["s"]("master"), "newbie", PASSWORD, "N", "B", "newbie@x.test")
    users.reset_password(org["s"]("master"), org["staff"], NEW)
    for row in world.master_rows("SELECT old_value, new_value FROM audit_log"):
        text = (row["old_value"] or "") + (row["new_value"] or "")
        assert "password_hash" not in text and "scrypt$" not in text
