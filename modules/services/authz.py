"""authorize(): the service layer's permission check (CLAUDE.md rule 10).

docs/roles_permissions_design.md sections 7-9. Every service function that
writes, or reads protected data, calls authorize() first, before it opens its
write transaction (a static test enforces the order).

Decision order, first match wins:
 1. Unknown permission code: ValueError (a programming error; nothing logged).
 2. Agent origin and the code is not in AGENT_ALLOWED: deny (Admin and Master
    included), before any database read.
 3. Master DB: the user must exist and be active. A user whose password was
    reset (must_change_password) gets PasswordChangeRequiredError instead.
 4. Master DB: the company must exist and be active, and context.company_db_path
    must be the registered file (resolved under BASE_PROJECT_DIR); a mismatch is
    denied without writing into the wrong file. An inactive company is denied
    to everyone, except the Master for company.backup / company.restore.
 5. The Master (app_user.is_master = 1): allow.
 6. Master DB: the user's access row for the company, else the nearest one up
    the parent_company_id chain. 'Deny', no row, or no role_code: deny.
 7. Company DB: the role must exist and be active. Admin: allow. Otherwise the
    role must hold the permission.
 8. Project scope: a role with project_scope 'Assigned' may use a
    PROJECT_SCOPED permission only for a project in user_project_scope, and is
    denied when no project is given.

Both databases are read on EVERY call through fresh read-only connections, so a
role, access or scope change applies on the next call. A denial raises
PermissionDeniedError with a plain sentence that says why and what to do next
(decision R27: never the permission code), and writes an access_event holding
the code in its own short transaction, committed independently, so the log
survives the caller's rollback. If that write cannot get the lock, the event is
written to the error log file instead; the denial is raised either way.
"""
import logging
import re
import sqlite3
from collections import namedtuple

import modules.database as database
from modules.services import money, permissions
from modules.services.errors import PasswordChangeRequiredError, PermissionDeniedError, ValidationError
from modules.services.paths import resolve_company_path, same_file

ACCESS_EVENT_BUSY_TIMEOUT_MS = 2000
_MASTER_ONLY_WHEN_INACTIVE = frozenset({"company.backup", "company.restore"})
_logger = logging.getLogger("strataledger")

Access = namedtuple("Access", "is_master role_code")

# Why a permission check denied (decision R27). The sentence comes from the reason; the code goes to the log only.
AGENT = "agent"                        # an agent asked for a code outside AGENT_ALLOWED
ROLE = "role"                          # the role does not hold the permission
PROJECT = "project"                    # project scope: the project is not assigned to the user
NO_PROJECT = "no project"              # project scope: no project was given
NO_ACCESS = "no access"                # no access row, a Deny row, no role, or the role is missing
ROLE_INACTIVE = "role inactive"
USER_INACTIVE = "user inactive"        # inactive or missing user
NO_COMPANY = "no company"              # the company is not in the registry
ARCHIVED = "archived"                  # an inactive company, for a user with access to it
ARCHIVED_MASTER = "archived, master"   # an inactive company, for the Master (anything but backup or restore)
WRONG_FILE = "wrong file"              # the context's file is not the registered one
DENIAL_REASONS = frozenset({AGENT, ROLE, PROJECT, NO_PROJECT, NO_ACCESS, ROLE_INACTIVE, USER_INACTIVE, NO_COMPANY,
                            ARCHIVED, ARCHIVED_MASTER, WRONG_FILE})

AGENT_CANNOT_POST = "The AI assistant cannot post entries; a person posts the entry after it is approved."
USER_INACTIVE_MESSAGE = "Your user account is inactive; ask an Admin or the Master to reactivate it."
_FIXED_MESSAGES = {
    NO_ACCESS: "You do not have access to this company; ask an Admin to give you access.",
    ROLE_INACTIVE: "Your role in this company is inactive; ask an Admin to reactivate it or give you another role.",
    USER_INACTIVE: USER_INACTIVE_MESSAGE,
    NO_COMPANY: "This company is no longer in the company list; close it and open a company from the list.",
    ARCHIVED: "This company is archived; only the Master can back it up or restore it.",
    ARCHIVED_MASTER: "This company is archived; restore it from the company list first, then try again.",
    WRONG_FILE: "This company file is not the one registered for the company; close it and open the company "
                "from the company list.",
}


def denial_message(origin, permission, reason):
    """The sentence a person sees for a denial: why, and what to do next. Never the permission code (R27)."""
    if reason in _FIXED_MESSAGES:
        return _FIXED_MESSAGES[reason]
    action = _action_words(permission)
    if reason == AGENT:     # a code an agent may never use; an allowed code its user's role lacks gets the role one
        if permission == "je.post":
            return AGENT_CANNOT_POST
        return f"The AI assistant cannot {action}; a person must do this."
    if reason == PROJECT:
        return f"You can {action} only for projects assigned to you; ask an Admin to assign this project to you."
    if reason == NO_PROJECT:
        return f"You can {action} only for a project assigned to you; choose one of your projects first."
    return f"Your role does not allow you to {action}; ask an Admin to add this to your role."


def _action_words(permission):
    """'Send (post) invoices' -> 'send invoices': the permission's description as words inside a sentence."""
    entry = permissions.PERMISSIONS.get(permission)
    if entry is None:
        return "do this"
    words = re.sub(r"\s*\([^)]*\)", "", entry.description).strip()
    return words[:1].lower() + words[1:]


class _WrongCompanyFile(Exception):
    """The context's company_db_path is not the file registered for its company."""


def authorize(context, permission, project_id=None, *, record_type=None, record_id=None):
    """Return None if allowed; otherwise log the denial and raise PermissionDeniedError."""
    if permission not in permissions.PERMISSIONS:
        raise ValueError(f"Unknown permission code: {permission!r}")
    if context.origin == "Agent" and permission not in permissions.AGENT_ALLOWED:
        _deny(context, permission, "Agent", record_type, record_id, denial_message(context.origin, permission, AGENT))
    allowed, is_master, reason = _checked_decide(context, permission, project_id)
    if not allowed:
        _deny(context, permission, _actor_type(context, is_master), record_type, record_id,
              denial_message(context.origin, permission, reason))


def is_allowed(context, permission, project_id=None):
    """The same decision as authorize(), without logging or raising on a plain denial."""
    if permission not in permissions.PERMISSIONS:
        raise ValueError(f"Unknown permission code: {permission!r}")
    if context.origin == "Agent" and permission not in permissions.AGENT_ALLOWED:
        return False
    try:
        return _decide(context, permission, project_id)[0]
    except _WrongCompanyFile:
        return False


def check_company_access(context):
    """May the user open this company at all? (Master, or a Grant row with an active role.)

    The same order as authorize() without a permission code; a denial is logged
    with record_type 'company'. An inactive company opens only for the Master.
    """
    allowed, is_master, reason = _checked_decide(context, None, None)
    if not allowed:
        _deny(context, None, _actor_type(context, is_master), "company", context.company_id,
              denial_message(context.origin, None, reason))


def _checked_decide(context, permission, project_id):
    try:
        return _decide(context, permission, project_id)
    except _WrongCompanyFile:
        _logger.error("context company file does not match the registry: company_id=%s user=%s permission=%s",
                      context.company_id, context.user_id, permission)
        raise PermissionDeniedError(_FIXED_MESSAGES[WRONG_FILE]) from None


def deny(context, permission=None, *, record_type=None, record_id=None, message=None):
    """Log a denial decided by another service rule and raise PermissionDeniedError.

    Used for rules beyond the permission itself (an approval slot the user cannot
    fill, the separate-approver rule, a non-person approving). `message` is the
    sentence the person sees; without one it is the role sentence for the permission
    (denial_message). Call it before opening a write transaction.
    """
    is_master = False if context.origin == "Agent" else current_access(context).is_master
    _deny(context, permission, _actor_type(context, is_master), record_type, record_id, message)


def current_access(context):
    """The user's Master flag and effective role code in the context's company (read fresh)."""
    master = database.get_readonly_connection(context.master_db_path)
    try:
        user = master.execute("SELECT is_master FROM app_user WHERE user_id = ?", (context.user_id,)).fetchone()
        if user is None:
            return Access(False, None)
        if user["is_master"] == 1:
            return Access(True, None)
        return Access(False, _access_role(master, context.user_id, context.company_id))
    finally:
        master.close()


def record_company_open(context):
    """Write an 'Open company' access_event when the Master opens a company. Returns True if written."""
    if not current_access(context).is_master:
        return False
    _write_access_event(context.company_db_path, user_id=context.user_id, actor_type="Master",
                        event_type="Open company", origin=context.origin, now=context.now)
    return True


def check_approval_limit(context, document_type, amount_cents, project_id=None, *, record_type=None, record_id=None):
    """Authorize the document's approve permission, then its approval limit.

    Master and Admin are unlimited. Otherwise the role needs an approval_limit row
    for the document type with max_amount_cents >= amount_cents.
    """
    if document_type not in permissions.APPROVE_PERMISSION:
        raise ValueError(f"Unknown document type: {document_type!r}")
    permission = permissions.APPROVE_PERMISSION[document_type]
    authorize(context, permission, project_id, record_type=record_type, record_id=record_id)
    access = current_access(context)
    if access.is_master or access.role_code == "Admin":
        return
    company = database.get_readonly_connection(context.company_db_path)
    try:
        row = company.execute(
            "SELECT max_amount_cents FROM approval_limit WHERE role_code = ? AND document_type = ?",
            (access.role_code, document_type),
        ).fetchone()
    finally:
        company.close()
    if row is None or amount_cents > row["max_amount_cents"]:
        who = _who_can_approve(context, permission, document_type, amount_cents)
        if row is None:
            message = (f"Your role has no approval limit for {_with_article(document_type.lower())}; ask an Admin "
                       f"to set one, or ask {who} to approve it.")
        else:
            message = (f"This amount ({money.text(amount_cents)}) is over your approval limit "
                       f"({money.text(row['max_amount_cents'])}); ask {who} to approve it.")
        _deny(context, permission, "User", record_type, record_id, message)


def _who_can_approve(context, permission, document_type, amount_cents):
    """'someone in the Controller or PM role, or an Admin': the active roles holding the permission whose limit
    covers the amount, by name. An Admin can always approve."""
    company = database.get_readonly_connection(context.company_db_path)
    try:
        names = [r["name"] for r in company.execute(
            "SELECT role.name FROM role "
            "JOIN role_permission ON role_permission.role_code = role.role_code "
            "AND role_permission.permission_code = ? "
            "JOIN approval_limit ON approval_limit.role_code = role.role_code AND approval_limit.document_type = ? "
            "WHERE role.is_active = 1 AND role.role_code <> 'Admin' AND approval_limit.max_amount_cents >= ? "
            "ORDER BY role.name", (permission, document_type, amount_cents))]
    finally:
        company.close()
    if not names:
        return "an Admin"
    if len(names) == 1:
        return f"someone in the {names[0]} role or an Admin"
    return f"someone in the {', '.join(names[:-1])} or {names[-1]} role, or an Admin,"   # "...or an Admin, to approve it"


def _with_article(noun):
    return ("an " if noun[:1] in "aeiou" else "a ") + noun


# --- internals -----------------------------------------------------------------------

def _decide(context, permission, project_id):
    """Return (allowed, is_master, reason); reason is None when allowed. Reads both databases; never writes."""
    master = database.get_readonly_connection(context.master_db_path)
    try:
        user = master.execute(
            "SELECT is_active, is_master, must_change_password FROM app_user WHERE user_id = ?", (context.user_id,)
        ).fetchone()
        if user is None or user["is_active"] != 1:
            return False, False, USER_INACTIVE
        if user["must_change_password"] == 1:
            raise PasswordChangeRequiredError("Change your password before continuing")
        is_master = user["is_master"] == 1
        company = master.execute(
            "SELECT is_active, database_file_path FROM company_registry WHERE company_id = ?", (context.company_id,)
        ).fetchone()
        if company is None:     # only the Master learns that the company is missing (no oracle for others)
            return False, is_master, NO_COMPANY if is_master else NO_ACCESS
        try:
            registered = resolve_company_path(company["database_file_path"])
        except ValidationError:
            raise _WrongCompanyFile() from None
        if not same_file(registered, context.company_db_path):
            raise _WrongCompanyFile()
        if company["is_active"] != 1:
            allowed = is_master and (permission is None or permission in _MASTER_ONLY_WHEN_INACTIVE)
            if allowed:
                return True, True, None
            if is_master:
                return False, True, ARCHIVED_MASTER
            # Only a user with access to the company learns that it is archived.
            has_access = _access_role(master, context.user_id, context.company_id) is not None
            return False, False, ARCHIVED if has_access else NO_ACCESS
        if is_master:
            return True, True, None
        role_code = _access_role(master, context.user_id, context.company_id)
    finally:
        master.close()
    if role_code is None:
        return False, False, NO_ACCESS

    company = database.get_readonly_connection(context.company_db_path)
    try:
        role = company.execute(
            "SELECT is_active, project_scope FROM role WHERE role_code = ?", (role_code,)
        ).fetchone()
        if role is None:
            return False, False, NO_ACCESS
        if role["is_active"] != 1:
            return False, False, ROLE_INACTIVE
        if permission is None:  # check_company_access: an active role is enough
            return True, False, None
        if role_code != "Admin" and company.execute(
            "SELECT 1 FROM role_permission WHERE role_code = ? AND permission_code = ?", (role_code, permission)
        ).fetchone() is None:
            return False, False, ROLE
        if role["project_scope"] == "Assigned" and permission in permissions.PROJECT_SCOPED:
            if project_id is None:
                return False, False, NO_PROJECT
            if company.execute(
                "SELECT 1 FROM user_project_scope WHERE user_id = ? AND project_id = ?", (context.user_id, project_id)
            ).fetchone() is None:
                return False, False, PROJECT
        return True, False, None
    finally:
        company.close()


def _access_role(master, user_id, company_id):
    """Role code from the nearest access row (this company, then up the parent chain); None if denied."""
    seen = set()
    current = company_id
    while current is not None and current not in seen:
        seen.add(current)
        row = master.execute(
            "SELECT role_code, access_mode FROM user_company_access WHERE user_id = ? AND company_id = ?",
            (user_id, current),
        ).fetchone()
        if row is not None:
            return None if row["access_mode"] == "Deny" else row["role_code"]
        parent = master.execute(
            "SELECT parent_company_id FROM company_registry WHERE company_id = ?", (current,)
        ).fetchone()
        current = parent["parent_company_id"] if parent else None
    return None


def _actor_type(context, is_master):
    if context.origin == "Agent":
        return "Agent"
    return "Master" if is_master else "User"


def _deny(context, permission, actor_type, record_type, record_id, message=None):
    _write_access_event(
        context.company_db_path, user_id=context.user_id, actor_type=actor_type, event_type="Denied",
        permission_code=permission, record_type=record_type, record_id=record_id, origin=context.origin,
        now=context.now,
    )
    if message is None:
        message = denial_message(context.origin, permission, ROLE if permission else NO_ACCESS)
    raise PermissionDeniedError(message)


def _write_access_event(company_db_path, *, user_id, actor_type, event_type, now, permission_code=None,
                        record_type=None, record_id=None, origin=None):
    """Append one access_event in its own short transaction. Never stores field values.

    Excluded from the rule-10 static test by name: it is the denial log writer.
    On a lock or database error the event goes to the error log file instead.
    """
    try:
        conn = database.get_connection(company_db_path)
        try:
            conn.isolation_level = None
            database.set_busy_timeout(conn, ACCESS_EVENT_BUSY_TIMEOUT_MS)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO access_event (occurred_at, user_id, actor_type, event_type, permission_code, "
                    "record_type, record_id, origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (now, user_id, actor_type, event_type, permission_code, record_type, record_id, origin),
                )
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
        return True
    except sqlite3.Error as error:
        _logger.error(
            "access_event not written (%s): event=%s permission=%s user=%s actor=%s record_type=%s record_id=%s",
            error, event_type, permission_code, user_id, actor_type, record_type, record_id,
        )
        return False
