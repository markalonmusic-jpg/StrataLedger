"""Refusals are plain sentences with no permission code (decision R27; CLAUDE.md section 0b, rule 14).

A refusal says why and what to do next. The permission code goes to the denial log (access_event.permission_code)
only, never into the message a person sees.
"""
import ast
import re
from pathlib import Path

import pytest

from modules.services import approvals, auth, authz, errors, ledger, permissions, users
from modules.services.errors import PermissionDeniedError, ValidationError
from tests.authz_world import PASSWORD, world  # noqa: F401  (fixture)
from tests.test_approvals import CO, actions, policy, submit, team  # noqa: F401  (fixtures and helpers)
from tests.test_users_access import org  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ROOT / "modules" / "services"

# A permission code is two lower-case words joined by a dot. At least two letters on each side, so a decimal
# ("1,000.00"), "e.g." and a version ("v1.2") never match.
CODE_SHAPE = re.compile(r"\b([a-z][a-z_]+)\.([a-z][a-z_]+)\b")
# The only allowed code-shaped words: file names a sentence may name. Keep this tiny.
FILE_EXTENSIONS = {
    "db",   # a database file such as system_master.db
    "sql",  # a schema file such as 001_company.sql
}
DENY_CALLS = {"deny", "_deny", "_deny_master"}


def code_like(text):
    """The code-shaped words in text, file names excepted."""
    return [m.group(0) for m in CODE_SHAPE.finditer(text) if m.group(2) not in FILE_EXTENSIONS]


def _service_error_names():
    tree = ast.parse((SERVICES / "errors.py").read_text(encoding="utf-8"))
    names = {"ServiceError"}
    changed = True
    while changed:
        changed = False
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name not in names and any(
                    isinstance(base, ast.Name) and base.id in names for base in node.bases):
                names.add(node.name)
                changed = True
    return names


def _call_name(node):
    return node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)


def message_violations(source, filename="<source>", error_names=None):
    """Code-shaped literals, and f-strings interpolating a permission, in refusal calls."""
    error_names = error_names or _service_error_names()
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or _call_name(node) not in error_names | DENY_CALLS:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                if _call_name(node) in DENY_CALLS and len(node.args) > 1 and sub is node.args[1]:
                    continue    # a deny call's permission argument goes to the log, not the message
                for word in code_like(sub.value):
                    found.append(f"{filename}:{sub.lineno}: {word!r} in a refusal")
            if isinstance(sub, ast.FormattedValue):
                names = {n.id for n in ast.walk(sub.value) if isinstance(n, ast.Name)}
                names |= {n.attr for n in ast.walk(sub.value) if isinstance(n, ast.Attribute)}
                if any("permission" in name for name in names):
                    found.append(f"{filename}:{sub.lineno}: a permission is put into a refusal")
    found += _sentence_violations(source, filename)
    return found


def _sentence_violations(source, filename):
    """Sentences kept outside the call: module-level constants (and dicts or tuples of them) holding a sentence
    (a string with a space; a bare code has none), and what a function named *_message returns."""
    found = []
    tree = ast.parse(source)
    places = [node.value for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value]
    for func in ast.walk(tree):
        if isinstance(func, ast.FunctionDef) and func.name.endswith("_message"):
            places += [n.value for n in ast.walk(func) if isinstance(n, ast.Return) and n.value is not None]
    for place in places:
        for sub in ast.walk(place):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and " " in sub.value:
                for word in code_like(sub.value):
                    found.append(f"{filename}:{sub.lineno}: {word!r} in a sentence")
            if isinstance(sub, ast.FormattedValue) and any(
                    "permission" in getattr(n, "id", getattr(n, "attr", "")) for n in ast.walk(sub.value)):
                found.append(f"{filename}:{sub.lineno}: a permission is put into a sentence")
    return found


# --- The static scan --------------------------------------------------------------------------------------

def test_no_service_refusal_names_a_permission_code():
    found = []
    for path in sorted(SERVICES.glob("*.py")):
        found += message_violations(path.read_text(encoding="utf-8"), path.name)
    assert found == []


@pytest.mark.parametrize("source", [
    'raise PermissionDeniedError("Not permitted: je.approve")',
    'raise ValidationError("You need company.users.manage for this")',
    'raise PermissionDeniedError(f"Not permitted: {permission}")',
    'raise auth.PermissionDeniedError(f"Not permitted: {permission_code}")',
    'authz.deny(context, "je.post", message="Ask for je.post")',
    'authz._deny(context, "je.post", "User", None, None, "Ask for je.post")',
    'NOT_ALLOWED = "Not permitted: je.approve"',
    'MESSAGES = {"x": "You need ledger.view for this."}',
    'def limit_message(code):\n    return f"Your role lacks {code}" + " (see je.approve)"',
    'def limit_message(permission):\n    return f"Not permitted: {permission}"',
])
def test_the_scan_catches_a_code_in_a_refusal(source):
    assert message_violations(source) != []


@pytest.mark.parametrize("source", [
    'raise ValidationError("The file system_master.db is newer; rebuild it from 001_company.sql.")',
    'raise PostingError("Debits 1,000.00 and credits 999.99 differ; fix a line, e.g. the first.")',
    'raise ValidationError("Saved by StrataLedger v1.2; update the app.")',
    'authz.deny(context, "je.post", message="Ask a colleague to post it.")',
    'raise ValueError(f"Unknown permission code: {permission!r}")',   # a programming error, never shown
    'USERS_MANAGE = "company.users.manage"',                            # a code constant, not a sentence
    'LOG = "Saved to system_master.db; rebuild from 001_master.sql if it fails."',
])
def test_the_scan_passes_file_names_decimals_and_plain_sentences(source):
    assert message_violations(source) == []


# --- Every default sentence, for every code -------------------------------------------------------------

def test_every_default_sentence_is_plain_and_says_what_to_do():
    """Every code, every reason, both origins (one test: about 1,800 sentences, all failures listed)."""
    bad = []
    for code in sorted(permissions.PERMISSIONS):
        for reason in sorted(authz.DENIAL_REASONS):
            for origin in ("Human", "Agent"):
                message = authz.denial_message(origin, code, reason)
                if (code in message or code_like(message) or "; " not in message or not message.endswith(".")
                        or not message[0].isupper()):
                    bad.append((code, reason, origin, message))
    assert bad == []


def test_the_default_sentence_names_the_action_in_words():
    assert authz.denial_message("Human", "je.approve", authz.ROLE) == (
        "Your role does not allow you to approve journal entries; ask an Admin to add this to your role.")
    assert authz.denial_message("Human", "invoice.send", authz.ROLE) == (
        "Your role does not allow you to send invoices; ask an Admin to add this to your role.")
    assert authz.denial_message("Agent", "je.post", authz.AGENT) == authz.AGENT_CANNOT_POST
    assert authz.AGENT_CANNOT_POST == (
        "The AI assistant cannot post entries; a person posts the entry after it is approved.")
    assert authz.denial_message("Agent", "bill.approve", authz.AGENT) == (
        "The AI assistant cannot approve vendor bills; a person must do this.")


# --- authorize() ------------------------------------------------------------------------------------------

def _denied(world, call):
    with pytest.raises(PermissionDeniedError) as error:
        call()
    message = str(error.value)
    assert code_like(message) == []
    return message, world.events(CO)[-1]


def test_a_role_without_the_permission(world, team):
    message, event = _denied(world, lambda: authz.authorize(team["ctx"]("clerk"), "je.post"))
    assert message == "Your role does not allow you to post journal entries; ask an Admin to add this to your role."
    assert event["permission_code"] == "je.post"


def test_the_agent_cannot_post(world, team):
    message, event = _denied(world, lambda: authz.authorize(team["ctx"]("admin", origin="Agent"), "je.post"))
    assert message == "The AI assistant cannot post entries; a person posts the entry after it is approved."
    assert (event["permission_code"], event["actor_type"]) == ("je.post", "Agent")


def test_the_agent_cannot_post_through_the_ledger(world, team):
    with pytest.raises(PermissionDeniedError) as error:
        ledger.post_journal_entry(team["ctx"]("admin", origin="Agent"), 1)
    assert str(error.value) == authz.AGENT_CANNOT_POST
    assert world.events(CO)[-1]["permission_code"] == "je.post"


def test_project_scope(world, team):
    world.role(CO, "SitePM", ["bill.approve"], scope="Assigned")
    site_pm = world.user("sitepm")
    world.grant(site_pm, CO, "SitePM")
    project_id = world.project(CO)
    message, event = _denied(world, lambda: authz.authorize(world.ctx(site_pm, CO), "bill.approve", project_id))
    assert message == ("You can approve vendor bills only for projects assigned to you; "
                       "ask an Admin to assign this project to you.")
    assert event["permission_code"] == "bill.approve"
    message, _ = _denied(world, lambda: authz.authorize(world.ctx(site_pm, CO), "bill.approve"))
    assert message == ("You can approve vendor bills only for a project assigned to you; "
                       "choose one of your projects first.")


def test_no_access_to_the_company(world, team):
    stranger = world.user("stranger")
    message, event = _denied(world, lambda: authz.authorize(world.ctx(stranger, CO), "ledger.view"))
    assert message == "You do not have access to this company; ask an Admin to give you access."
    assert event["permission_code"] == "ledger.view"
    message, _ = _denied(world, lambda: authz.check_company_access(world.ctx(stranger, CO)))
    assert message == "You do not have access to this company; ask an Admin to give you access."


def test_an_inactive_role(world, team):
    world.set_role_active(CO, "Clerk", False)
    message, _ = _denied(world, lambda: authz.authorize(team["ctx"]("clerk"), "bill.create"))
    assert message == ("Your role in this company is inactive; ask an Admin to reactivate it or give you "
                       "another role.")


def test_an_inactive_user(world, team):
    world.set_user_active(team["clerk"], False)
    message, _ = _denied(world, lambda: authz.authorize(team["ctx"]("clerk"), "bill.create"))
    assert message == "Your user account is inactive; ask an Admin or the Master to reactivate it."


def test_an_archived_company(world, team):
    world.set_company_active(CO, False)
    message, _ = _denied(world, lambda: authz.authorize(team["ctx"]("admin"), "ledger.view"))
    assert message == "This company is archived; only the Master can back it up or restore it."


def test_the_wrong_company_file(world, team, tmp_path):
    import dataclasses
    context = dataclasses.replace(team["ctx"]("admin"), company_db_path=str(world.path("OTHER")))
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(context, "ledger.view")
    assert str(error.value) == ("This company file is not the one registered for the company; close it and open "
                                "the company from the company list.")


# --- Approvals ---------------------------------------------------------------------------------------------

def test_an_approver_out_of_step_order(world, team):
    policy(team, [(1, "PM", 1), (2, "Controller", 1)])
    request_id = submit(team)
    message, event = _denied(world, lambda: approvals.approve(team["ctx"]("ctrl1"), request_id))
    assert message == ("Step 1 of 2 must be approved first by someone in the PM role; "
                       "you can approve step 2 once it is complete.")
    assert event["permission_code"] == "bill.approve"
    assert actions(world, request_id) == []


def test_an_approver_whose_role_is_not_in_the_chain(world, team):
    policy(team, [(1, "PM", 1)])
    request_id = submit(team)
    message, event = _denied(world, lambda: approvals.approve(team["ctx"]("ctrl1"), request_id))
    assert message == "Step 1 of 1 needs approval by someone in the PM role; ask them to approve it."
    assert event["permission_code"] == "bill.approve"


def test_a_step_open_to_two_roles_names_both(world, team):
    world.role(CO, "Auditor", ["bill.approve"])
    world.limit(CO, "Auditor", "Bill", 10_000_000)
    auditor = world.user("auditor")
    world.grant(auditor, CO, "Auditor")
    policy(team, [(1, "PM", 1), (1, "Controller", 1)])
    request_id = submit(team)
    message, _ = _denied(world, lambda: approvals.approve(world.ctx(auditor, CO), request_id))
    assert message == "Step 1 of 1 needs approval by someone in the Controller or PM role; ask them to approve it."


def test_an_approver_with_no_limit_for_the_document(world, team):
    world.role(CO, "Helper", ["bill.approve"])
    helper = world.user("helper")
    world.grant(helper, CO, "Helper")
    request_id = submit(team, amount=5_000)
    message, event = _denied(world, lambda: approvals.approve(world.ctx(helper, CO), request_id))
    assert message == ("Your role has no approval limit for a bill; ask an Admin to set one, or ask someone in "
                       "the Controller or PM role, or an Admin, to approve it.")
    assert event["permission_code"] == "bill.approve"


def test_an_approver_over_their_limit(world, team):
    request_id = submit(team, amount=200_000)
    message, event = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message == ("This amount (2,000.00) is over your approval limit (1,000.00); ask someone in the "
                       "Controller role or an Admin to approve it.")
    assert event["permission_code"] == "bill.approve"


def test_over_every_limit_leaves_an_admin(world, team):
    request_id = submit(team, amount=20_000_000)
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("ctrl1"), request_id))
    assert message == ("This amount (200,000.00) is over your approval limit (100,000.00); ask an Admin to "
                       "approve it.")


def test_an_inactive_role_is_not_offered_as_an_approver(world, team):
    world.set_role_active(CO, "Controller", False)
    request_id = submit(team, amount=200_000)
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message.endswith("ask an Admin to approve it.")


def test_a_reject_needs_a_reason(world, team):
    request_id = submit(team)
    with pytest.raises(ValidationError) as error:
        approvals.reject(team["ctx"]("pm1"), request_id, "  ")
    assert str(error.value) == "Give a reason for rejecting it, so the preparer knows what to fix."


def test_the_creator_cannot_approve_with_separation_on(world, team):
    request_id = submit(team, by="clerk", created_by="pm1")
    message, event = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message == ("This company needs a different person to approve the document you created; "
                       "ask a colleague to approve it.")
    assert event["permission_code"] == "bill.approve"


# --- Master-only and user management --------------------------------------------------------------------

def test_a_master_only_action(world, org):
    with pytest.raises(PermissionDeniedError) as error:
        auth.require_master(org["s"]("admin"), "master.change_password")
    assert str(error.value) == "Only the Master can do this; ask the Master to sign in and do it."
    assert world.master_rows("SELECT permission_code FROM auth_event WHERE event_type = 'Denied'")[-1] == {
        "permission_code": "master.change_password"}


def test_an_inactive_account_is_told_so(world, org):
    world.set_user_active(org["staff"], False)
    with pytest.raises(PermissionDeniedError) as error:
        auth.active_user(org["s"]("staff"))
    assert str(error.value) == "Your user account is inactive; ask an Admin or the Master to reactivate it."


def test_only_the_master_gives_the_admin_role(world, org):
    with pytest.raises(PermissionDeniedError) as error:
        users.set_role(org["s"]("admin"), org["staff"], org["cid"]("PARENT"), "Admin")
    assert str(error.value) == "Only the Master can give someone the Admin role; ask the Master."


def test_a_user_manager_cannot_give_a_broader_role(world, org):
    with pytest.raises(PermissionDeniedError) as error:
        users.set_role(org["s"]("mgr"), org["staff"], org["cid"]("PARENT"), "Broad")
    assert str(error.value) == ("You can only assign a role whose permissions your own role also has; "
                                "ask an Admin.")


def test_only_the_master_changes_an_admin(world, org):
    users.grant_access(org["s"]("master"), org["admin2"], org["cid"]("PARENT"), "Admin")
    with pytest.raises(PermissionDeniedError) as error:
        users.deny_access(org["s"]("admin"), org["admin2"], org["cid"]("PARENT"))
    assert str(error.value) == "Only the Master can change or remove an Admin's access; ask the Master."


def test_password_reset_refusals(world, org):
    with pytest.raises(PermissionDeniedError) as error:
        users.reset_password(org["s"]("mgr"), org["admin"], "a brand new passphrase")
    assert str(error.value) == ("Only the Master can reset the password of the Master or an Admin; "
                                "ask the Master.")
    with pytest.raises(PermissionDeniedError) as error:
        users.reset_password(org["s"]("admin"), org["client"], "a brand new passphrase")
    assert str(error.value) == ("You can reset passwords only for users in a company where you manage users; "
                                "ask an Admin.")
    assert {r["permission_code"] for r in world.master_rows(
        "SELECT permission_code FROM auth_event WHERE event_type = 'Denied'")} == {"company.users.manage"}


def test_errors_module_is_scanned():
    """The scan reads the error names from errors.py, so a new error type is covered without a list."""
    assert {"PermissionDeniedError", "PostingError", "KeyUnavailableError"} <= _service_error_names()
    assert errors.ServiceError.__name__ in _service_error_names()


# --- Review fixes ------------------------------------------------------------------------------------------

def test_the_agent_sentence_is_only_for_codes_an_agent_may_never_use():
    """An allowed code the user's role lacks gets the role sentence, for an agent too."""
    assert authz.denial_message("Agent", "ledger.view", authz.ROLE) == (
        "Your role does not allow you to view the general ledger; ask an Admin to add this to your role.")


def test_the_agent_running_as_a_user_without_the_role_gets_the_role_sentence(world, team):
    message, _ = _denied(world, lambda: authz.authorize(team["ctx"]("clerk", origin="Agent"), "je.create"))
    assert message.startswith("Your role does not allow you to create journal entries")


def test_a_user_without_access_learns_nothing_about_an_archived_company(world, team):
    stranger = world.user("stranger")
    world.set_company_active(CO, False)
    message, _ = _denied(world, lambda: authz.authorize(world.ctx(stranger, CO), "ledger.view"))
    assert message == "You do not have access to this company; ask an Admin to give you access."


def test_a_user_without_access_learns_nothing_about_a_missing_company(world, team):
    import dataclasses
    stranger = world.user("stranger")
    context = dataclasses.replace(world.ctx(stranger, CO), company_id=9999)
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(context, "ledger.view")
    assert str(error.value) == "You do not have access to this company; ask an Admin to give you access."


def test_the_master_is_told_to_restore_an_archived_company_first(world, team):
    world.set_company_active(CO, False)
    message, _ = _denied(world, lambda: authz.authorize(team["ctx"]("master"), "ledger.view"))
    assert message == "This company is archived; restore it from the company list first, then try again."


def test_a_read_only_company_says_what_to_do(world, team):
    import dataclasses
    from modules.services.tx import write_transaction
    context = dataclasses.replace(team["ctx"]("admin"), read_only=True)
    with pytest.raises(PermissionDeniedError) as error:
        with write_transaction(context.company_db_path, context):
            pass
    assert str(error.value) == ("This company is open read-only; open it with a role that can make changes, "
                                "or ask an Admin.")


def test_acting_twice_on_a_request_says_what_happens_next(world, team):
    policy(team, [(1, "PM", 2)])
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    with pytest.raises(ValidationError) as error:
        approvals.approve(team["ctx"]("pm1"), request_id)
    assert str(error.value) == ("You have already acted on this approval request; another approver completes "
                                "the open step.")


# --- Mutation-test gaps (db67342) ---------------------------------------------------------------------------

def _approver(world, code, name=None, cents=10_000_000):
    world.role(CO, code, ["bill.approve"])
    world.limit(CO, code, "Bill", cents)
    if name:
        with world._company(CO) as c:
            c.execute("UPDATE role SET name = ? WHERE role_code = ?", (name, code))
    user = world.user(code.lower())
    world.grant(user, CO, code)
    return world.ctx(user, CO)


def test_the_master_learns_that_a_company_is_missing(world, team):
    import dataclasses
    context = dataclasses.replace(team["ctx"]("master"), company_id=9999)
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(context, "ledger.view")
    assert str(error.value) == ("This company is no longer in the company list; close it and open a company "
                                "from the list.")


def test_an_access_row_naming_a_missing_role_is_no_access(world, team):
    ghost = world.user("ghost")
    world.grant(ghost, CO, "GhostRole")
    message, _ = _denied(world, lambda: authz.authorize(world.ctx(ghost, CO), "ledger.view"))
    assert message == "You do not have access to this company; ask an Admin to give you access."


def test_deny_without_a_code_or_message_is_the_no_access_sentence(world, team):
    message, event = _denied(world, lambda: authz.deny(team["ctx"]("clerk")))
    assert message == "You do not have access to this company; ask an Admin to give you access."
    assert event["permission_code"] is None


def test_the_admin_role_is_never_listed_as_a_role_that_can_approve(world, team):
    assert world.rows(CO, "SELECT 1 FROM role_permission WHERE role_code = 'Admin' "
                          "AND permission_code = 'bill.approve'")      # the Admin role holds it
    world.limit(CO, "Admin", "Bill", 10 ** 12)
    request_id = submit(team, amount=200_000)
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message.endswith("ask someone in the Controller role or an Admin to approve it.")


def test_a_limit_equal_to_the_amount_can_approve(world, team):
    request_id = submit(team, amount=10_000_000)              # exactly the Controller limit
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message.endswith("ask someone in the Controller role or an Admin to approve it.")


def test_the_default_separation_sentence_for_the_creator(world, team):
    with pytest.raises(PermissionDeniedError) as error:
        approvals.check_separate_approver(team["ctx"]("pm1"), team["pm1"])
    assert str(error.value) == ("This company needs a different person to approve the document you created; "
                                "ask a colleague to approve it.")


def test_acting_again_on_a_later_step_is_already_acted_not_the_step_sentence(world, team):
    policy(team, [(1, "PM", 1), (2, "Controller", 1)])
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    with pytest.raises(ValidationError) as error:
        approvals.approve(team["ctx"]("pm1"), request_id)
    assert str(error.value) == approvals.ALREADY_ACTED


def test_the_in_transaction_recheck_says_already_acted(world, team):
    from modules.services.tx import write_transaction
    policy(team, [(1, "PM", 2)])
    request_id = submit(team)
    ctx = team["ctx"]("pm1")
    plan = approvals._plan(ctx, approvals._load_request(ctx, request_id))   # planned before the user acts
    approvals.approve(ctx, request_id)
    with pytest.raises(ValidationError) as error:
        with write_transaction(ctx.company_db_path, ctx) as conn:
            approvals._record(conn, ctx, plan, "Approve", None)
    assert str(error.value) == approvals.ALREADY_ACTED


def test_after_step_one_the_sentence_names_step_two(world, team):
    policy(team, [(1, "PM", 1), (2, "Controller", 1)])
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("pm2"), request_id))
    assert message == "Step 2 of 2 needs approval by someone in the Controller role; ask them to approve it."


def test_only_the_unfilled_role_of_a_step_is_named(world, team):
    outsider = _approver(world, "Auditor")
    policy(team, [(1, "PM", 1), (1, "Controller", 1)])
    request_id = submit(team)
    approvals.approve(team["ctx"]("pm1"), request_id)
    message, _ = _denied(world, lambda: approvals.approve(outsider, request_id))
    assert message == "Step 1 of 1 needs approval by someone in the Controller role; ask them to approve it."


def test_roles_are_named_by_their_names_in_name_order(world, team):
    outsider = _approver(world, "Auditor")
    with world._company(CO) as c:
        c.execute("UPDATE role SET name = 'Alpha PMs' WHERE role_code = 'PM'")
        c.execute("UPDATE role SET name = 'Zeta Controllers' WHERE role_code = 'Controller'")
    policy(team, [(1, "PM", 1), (1, "Controller", 1)])
    request_id = submit(team)
    message, _ = _denied(world, lambda: approvals.approve(outsider, request_id))
    assert message == ("Step 1 of 1 needs approval by someone in the Alpha PMs or Zeta Controllers role; "
                       "ask them to approve it.")


def test_three_roles_in_a_step_are_listed_with_commas(world, team):
    _approver(world, "Treasurer")
    outsider = _approver(world, "Auditor")
    policy(team, [(1, "PM", 1), (1, "Controller", 1), (1, "Treasurer", 1)])
    request_id = submit(team)
    message, _ = _denied(world, lambda: approvals.approve(outsider, request_id))
    assert message == ("Step 1 of 1 needs approval by someone in the Controller, PM or Treasurer role; "
                       "ask them to approve it.")


# --- R34: a limit refusal names only roles someone holds -------------------------------------------------------

def _limit_refusal(world, team, amount=200_000, by="pm1"):
    request_id = submit(team, amount=amount)
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"](by), request_id))
    return message


def test_a_role_with_a_covering_limit_but_no_holder_is_not_named(world, team):
    world.role(CO, "Treasurer", ["bill.approve"])
    world.limit(CO, "Treasurer", "Bill", 10_000_000)        # covers the amount, but nobody holds it
    assert _limit_refusal(world, team).endswith("ask someone in the Controller role or an Admin to approve it.")


@pytest.mark.parametrize("how", ["inactive", "denied", "revoked", "master"])
def test_a_role_whose_only_holders_cannot_act_is_not_named(world, team, how):
    for name in ("ctrl1", "ctrl2"):
        if how == "inactive":
            world.set_user_active(team[name], False)
        elif how == "denied":
            world.grant(team[name], CO, "Controller", mode="Deny")
        else:
            world.revoke(team[name], CO)
    if how == "master":                                     # the Master is not counted as a role holder
        world.grant(team["master"], CO, "Controller")
    assert _limit_refusal(world, team) == ("This amount (2,000.00) is over your approval limit (1,000.00); "
                                           "ask an Admin to approve it.")


def test_one_active_holder_is_enough(world, team):
    world.set_user_active(team["ctrl1"], False)
    assert _limit_refusal(world, team).endswith("ask someone in the Controller role or an Admin to approve it.")


def test_no_limit_and_no_holder_says_ask_an_admin(world, team):
    world.role(CO, "Helper", ["bill.approve"])
    helper = world.user("helper")
    world.grant(helper, CO, "Helper")
    for name in ("pm1", "pm2", "pm3", "ctrl1", "ctrl2"):
        world.revoke(team[name], CO)
    request_id = submit(team, amount=5_000)
    message, _ = _denied(world, lambda: approvals.approve(world.ctx(helper, CO), request_id))
    assert message == "Your role has no approval limit for a bill; ask an Admin to set one or to approve it."


def test_a_holder_through_the_parent_company_counts(world, team):
    child = "CHILD"
    world.role(child, "Clerk", ["bill.create"])
    world.role(child, "Small", ["bill.approve"])
    world.role(child, "Treasurer", ["bill.approve"])
    world.limit(child, "Small", "Bill", 100)
    world.limit(child, "Treasurer", "Bill", 10_000_000)
    clerk, small, treasurer = world.user("cclerk"), world.user("small"), world.user("treasurer")
    world.grant(clerk, child, "Clerk")
    world.grant(small, child, "Small")
    world.grant(treasurer, CO, "Treasurer")                 # no row in CHILD: the parent's row applies
    request_id = approvals.submit_for_approval(world.ctx(clerk, child), "Bill", "invoice", 1, 5_000,
                                               created_by=clerk)
    with pytest.raises(PermissionDeniedError) as error:
        approvals.approve(world.ctx(small, child), request_id)
    assert str(error.value).endswith("ask someone in the Treasurer role or an Admin to approve it.")
    world.grant(treasurer, child, "Treasurer", mode="Deny")  # the nearest row denies: no longer a holder
    with pytest.raises(PermissionDeniedError) as error:
        approvals.approve(world.ctx(small, child), request_id)
    assert str(error.value).endswith("; ask an Admin to approve it.")


# --- R37: with separation on, the creator and the submitter are not counted as holders ---------------------

def _only_ctrl1_holds_controller(world, team):
    world.revoke(team["ctrl2"], CO)
    world.grant_permission(CO, "Controller", "bill.create")     # so ctrl1 can send a bill for approval


@pytest.mark.parametrize("act", ["approve", "reject"])
@pytest.mark.parametrize("role", ["creator", "submitter"])
def test_the_creator_or_submitter_is_not_counted_with_separation_on(world, team, role, act):
    _only_ctrl1_holds_controller(world, team)
    by, created_by = ("clerk", "ctrl1") if role == "creator" else ("ctrl1", "clerk")
    request_id = submit(team, amount=200_000, by=by, created_by=created_by)
    if act == "approve":
        def call():
            return approvals.approve(team["ctx"]("pm1"), request_id)
    else:
        def call():
            return approvals.reject(team["ctx"]("pm1"), request_id, "wrong vendor")
    message, _ = _denied(world, call)
    assert message == ("This amount (2,000.00) is over your approval limit (1,000.00); ask an Admin to "
                       "approve it.")


@pytest.mark.parametrize("role", ["creator", "submitter"])
def test_the_creator_or_submitter_still_counts_with_separation_off(world, team, role):
    _only_ctrl1_holds_controller(world, team)
    world.settings(CO, require_separate_approver=0)
    by, created_by = ("clerk", "ctrl1") if role == "creator" else ("ctrl1", "clerk")
    request_id = submit(team, amount=200_000, by=by, created_by=created_by)
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message.endswith("ask someone in the Controller role or an Admin to approve it.")


def test_another_holder_is_still_named_with_separation_on(world, team):
    request_id = submit(team, amount=200_000, by="clerk", created_by="ctrl1")   # ctrl2 still holds it
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message.endswith("ask someone in the Controller role or an Admin to approve it.")


def test_no_limit_and_only_the_creator_holds_says_ask_an_admin(world, team):
    _only_ctrl1_holds_controller(world, team)
    for name in ("pm1", "pm2", "pm3"):
        world.revoke(team[name], CO)
    world.role(CO, "Helper", ["bill.approve"])
    helper = world.user("helper")
    world.grant(helper, CO, "Helper")
    request_id = submit(team, amount=5_000, by="clerk", created_by="ctrl1")
    message, _ = _denied(world, lambda: approvals.approve(world.ctx(helper, CO), request_id))
    assert message == "Your role has no approval limit for a bill; ask an Admin to set one or to approve it."


def test_a_missing_settings_row_counts_as_separation_on_for_the_count(world, team):
    _only_ctrl1_holds_controller(world, team)
    with world._company(CO) as c:
        c.execute("DELETE FROM company_settings")
    request_id = submit(team, amount=200_000, by="clerk", created_by="ctrl1")
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"]("pm1"), request_id))
    assert message.endswith("ask an Admin to approve it.")


# --- R39: with separation on, the "ask" target leaves out the creator and submitter ------------------------

NO_ONE_ELSE = ("No one else in this company can approve it; add another approver, or turn off separation of duties "
               "in Settings > Controls.")


def _no_controllers(world, team):
    for name in ("ctrl1", "ctrl2"):
        world.revoke(team[name], CO)


def _over_limit(world, team, *, by, created_by, approver="pm1"):
    request_id = submit(team, amount=200_000, by=by, created_by=created_by)
    message, _ = _denied(world, lambda: approvals.approve(team["ctx"](approver), request_id))
    return message


@pytest.mark.parametrize("by, created_by", [("clerk", "admin"), ("admin", "clerk")])
def test_the_only_admin_as_creator_or_submitter_leaves_the_master(world, team, by, created_by):
    _no_controllers(world, team)
    assert _over_limit(world, team, by=by, created_by=created_by) == (
        "This amount (2,000.00) is over your approval limit (1,000.00); ask the Master to approve it.")


def test_another_active_admin_is_asked(world, team):
    _no_controllers(world, team)
    world.grant(world.user("admin2"), CO, "Admin")
    assert _over_limit(world, team, by="clerk", created_by="admin").endswith("; ask another Admin to approve it.")


def test_an_inactive_or_denied_other_admin_does_not_count(world, team):
    _no_controllers(world, team)
    inactive, denied = world.user("admin2"), world.user("admin3")
    world.grant(inactive, CO, "Admin")
    world.set_user_active(inactive, False)
    world.grant(denied, CO, "Admin", mode="Deny")
    assert _over_limit(world, team, by="clerk", created_by="admin").endswith("; ask the Master to approve it.")


def test_a_role_holder_is_named_with_the_master(world, team):
    world.revoke(team["ctrl1"], CO)                                  # ctrl2 still holds Controller
    assert _over_limit(world, team, by="clerk", created_by="admin").endswith(
        "; ask someone in the Controller role or the Master to approve it.")


def test_a_role_holder_alone_when_the_admin_and_the_master_are_left_out(world, team):
    world.revoke(team["ctrl1"], CO)
    assert _over_limit(world, team, by="admin", created_by="master").endswith(
        "; ask someone in the Controller role to approve it.")


def test_no_one_else_when_the_admin_and_the_master_are_both_left_out(world, team):
    _no_controllers(world, team)
    assert _over_limit(world, team, by="admin", created_by="master") == NO_ONE_ELSE


def test_no_one_else_with_no_limit_row_either(world, team):
    _no_controllers(world, team)
    for name in ("pm1", "pm2", "pm3"):
        world.revoke(team[name], CO)
    world.role(CO, "Helper", ["bill.approve"])
    helper = world.user("helper")
    world.grant(helper, CO, "Helper")
    request_id = submit(team, amount=5_000, by="admin", created_by="master")
    message, _ = _denied(world, lambda: approvals.approve(world.ctx(helper, CO), request_id))
    assert message == NO_ONE_ELSE


def test_no_limit_row_with_the_admin_left_out_asks_the_master_to_approve(world, team):
    _no_controllers(world, team)
    for name in ("pm1", "pm2", "pm3"):
        world.revoke(team[name], CO)
    world.role(CO, "Helper", ["bill.approve"])
    helper = world.user("helper")
    world.grant(helper, CO, "Helper")
    request_id = submit(team, amount=5_000, by="clerk", created_by="admin")
    message, _ = _denied(world, lambda: approvals.approve(world.ctx(helper, CO), request_id))
    assert message == ("Your role has no approval limit for a bill; ask an Admin to set one, or ask the Master to "
                       "approve it.")


def test_with_separation_off_the_admin_creator_is_still_asked(world, team):
    _no_controllers(world, team)
    world.settings(CO, require_separate_approver=0)
    assert _over_limit(world, team, by="clerk", created_by="admin").endswith("; ask an Admin to approve it.")


def test_an_admin_not_left_out_is_still_an_admin(world, team):
    _no_controllers(world, team)                                    # the clerk created it; the Admin may approve
    assert _over_limit(world, team, by="clerk", created_by="clerk").endswith("; ask an Admin to approve it.")


def test_no_admin_in_the_company_and_none_left_out_asks_the_master(world, team):
    # Review of R39: "an Admin" only when an active Admin exists; with none, the Master.
    _no_controllers(world, team)
    world.revoke(team["admin"], CO)
    assert _over_limit(world, team, by="clerk", created_by="clerk").endswith("; ask the Master to approve it.")


def test_an_inactive_master_is_not_asked(world, team):
    _no_controllers(world, team)
    world.set_user_active(team["master"], False)
    assert _over_limit(world, team, by="clerk", created_by="admin") == NO_ONE_ELSE


def test_reject_also_leaves_out_the_admin_creator(world, team):
    _no_controllers(world, team)
    request_id = submit(team, amount=200_000, by="clerk", created_by="admin")
    message, _ = _denied(world, lambda: approvals.reject(team["ctx"]("pm1"), request_id, "wrong vendor"))
    assert message == ("This amount (2,000.00) is over your approval limit (1,000.00); ask the Master to approve "
                       "it.")


def test_a_missing_settings_row_leaves_out_the_admin_creator(world, team):
    _no_controllers(world, team)
    with world._company(CO) as c:
        c.execute("DELETE FROM company_settings")
    assert _over_limit(world, team, by="clerk", created_by="admin").endswith("; ask the Master to approve it.")


def test_two_role_holders_are_named_with_the_master(world, team):
    world.revoke(team["ctrl1"], CO)                                  # ctrl2 still holds Controller
    world.role(CO, "Treasurer", ["bill.approve"])
    world.limit(CO, "Treasurer", "Bill", 10_000_000)
    world.grant(world.user("treasurer"), CO, "Treasurer")
    assert _over_limit(world, team, by="clerk", created_by="admin").endswith(
        "; ask someone in the Controller or Treasurer role, or the Master, to approve it.")


# --- R36: access is checked before the file ---------------------------------------------------------------------

def _wrong_file(context, world):
    import dataclasses
    return dataclasses.replace(context, company_db_path=str(world.path("OTHER")))


def test_a_user_without_access_and_a_wrong_file_is_told_only_no_access(world, team):
    stranger = world.user("stranger")
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(_wrong_file(world.ctx(stranger, CO), world), "ledger.view")
    assert str(error.value) == "You do not have access to this company; ask an Admin to give you access."
    assert world.events("OTHER") == []                  # nothing is written into a file that is not CO's
    with pytest.raises(PermissionDeniedError) as error:
        authz.check_company_access(_wrong_file(world.ctx(stranger, CO), world))
    assert str(error.value) == "You do not have access to this company; ask an Admin to give you access."
    assert authz.is_allowed(_wrong_file(world.ctx(stranger, CO), world), "ledger.view") is False
    assert world.events("OTHER") == []


def test_a_user_without_access_and_the_right_file_is_still_logged(world, team):
    stranger = world.user("stranger")
    with pytest.raises(PermissionDeniedError):
        authz.authorize(world.ctx(stranger, CO), "ledger.view")
    assert world.events(CO)[-1]["permission_code"] == "ledger.view"


def test_a_denied_user_and_a_wrong_file_is_told_only_no_access(world, team):
    world.grant(team["clerk"], CO, "Clerk", mode="Deny")
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(_wrong_file(team["ctx"]("clerk"), world), "ledger.view")
    assert str(error.value) == "You do not have access to this company; ask an Admin to give you access."
    assert world.events("OTHER") == []


def test_a_user_with_access_and_a_wrong_file_is_told_the_file_is_wrong(world, team):
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(_wrong_file(team["ctx"]("clerk"), world), "ledger.view")
    assert str(error.value) == authz._FIXED_MESSAGES[authz.WRONG_FILE]


def test_the_master_is_told_the_file_is_wrong_even_for_an_archived_company(world, team):
    world.set_company_active(CO, False)
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(_wrong_file(team["ctx"]("master"), world), "company.backup")
    assert str(error.value) == authz._FIXED_MESSAGES[authz.WRONG_FILE]


def test_an_archived_company_with_access_and_a_wrong_file_is_told_the_file_is_wrong(world, team):
    world.set_company_active(CO, False)
    with pytest.raises(PermissionDeniedError) as error:
        authz.authorize(_wrong_file(team["ctx"]("clerk"), world), "ledger.view")
    assert str(error.value) == authz._FIXED_MESSAGES[authz.WRONG_FILE]
