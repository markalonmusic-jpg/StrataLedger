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
PermissionDeniedError carrying only the permission code, and writes an
access_event in its own short transaction, committed independently, so the log
survives the caller's rollback. If that write cannot get the lock, the event is
written to the error log file instead; the denial is raised either way.
"""
import logging
import sqlite3
from collections import namedtuple

import modules.database as database
from modules.services import permissions
from modules.services.errors import PasswordChangeRequiredError, PermissionDeniedError, ValidationError
from modules.services.paths import resolve_company_path, same_file

ACCESS_EVENT_BUSY_TIMEOUT_MS = 2000
_MASTER_ONLY_WHEN_INACTIVE = frozenset({"company.backup", "company.restore"})
_logger = logging.getLogger("strataledger")

Access = namedtuple("Access", "is_master role_code")


class _WrongCompanyFile(Exception):
    """The context's company_db_path is not the file registered for its company."""


def authorize(context, permission, project_id=None, *, record_type=None, record_id=None):
    """Return None if allowed; otherwise log the denial and raise PermissionDeniedError."""
    if permission not in permissions.PERMISSIONS:
        raise ValueError(f"Unknown permission code: {permission!r}")
    if context.origin == "Agent" and permission not in permissions.AGENT_ALLOWED:
        _deny(context, permission, "Agent", record_type, record_id)
    allowed, is_master = _checked_decide(context, permission, project_id)
    if not allowed:
        _deny(context, permission, _actor_type(context, is_master), record_type, record_id)


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
    allowed, is_master = _checked_decide(context, None, None)
    if not allowed:
        _deny(context, None, _actor_type(context, is_master), "company", context.company_id)


def _checked_decide(context, permission, project_id):
    try:
        return _decide(context, permission, project_id)
    except _WrongCompanyFile:
        _logger.error("context company file does not match the registry: company_id=%s user=%s",
                      context.company_id, context.user_id)
        raise PermissionDeniedError(f"Not permitted: {permission}" if permission else "Not permitted") from None


def deny(context, permission=None, *, record_type=None, record_id=None, message=None):
    """Log a denial decided by another service rule and raise PermissionDeniedError.

    Used for rules beyond the permission itself (an approval slot the user cannot
    fill, the separate-approver rule, a non-person approving). `message` replaces
    the default "Not permitted" sentence. Call it before opening a write transaction.
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
        _deny(context, permission, "User", record_type, record_id)


# --- internals -----------------------------------------------------------------------

def _decide(context, permission, project_id):
    """Return (allowed, is_master). Reads both databases; never writes."""
    master = database.get_readonly_connection(context.master_db_path)
    try:
        user = master.execute(
            "SELECT is_active, is_master, must_change_password FROM app_user WHERE user_id = ?", (context.user_id,)
        ).fetchone()
        if user is None or user["is_active"] != 1:
            return False, False
        if user["must_change_password"] == 1:
            raise PasswordChangeRequiredError("Change your password before continuing")
        is_master = user["is_master"] == 1
        company = master.execute(
            "SELECT is_active, database_file_path FROM company_registry WHERE company_id = ?", (context.company_id,)
        ).fetchone()
        if company is None:
            return False, is_master
        try:
            registered = resolve_company_path(company["database_file_path"])
        except ValidationError:
            raise _WrongCompanyFile() from None
        if not same_file(registered, context.company_db_path):
            raise _WrongCompanyFile()
        if company["is_active"] != 1:
            if permission is None:
                return is_master, is_master
            return is_master and permission in _MASTER_ONLY_WHEN_INACTIVE, is_master
        if is_master:
            return True, True
        role_code = _access_role(master, context.user_id, context.company_id)
    finally:
        master.close()
    if role_code is None:
        return False, False

    company = database.get_readonly_connection(context.company_db_path)
    try:
        role = company.execute(
            "SELECT is_active, project_scope FROM role WHERE role_code = ?", (role_code,)
        ).fetchone()
        if role is None or role["is_active"] != 1:
            return False, False
        if permission is None:  # check_company_access: an active role is enough
            return True, False
        if role_code != "Admin" and company.execute(
            "SELECT 1 FROM role_permission WHERE role_code = ? AND permission_code = ?", (role_code, permission)
        ).fetchone() is None:
            return False, False
        if role["project_scope"] == "Assigned" and permission in permissions.PROJECT_SCOPED:
            if project_id is None:
                return False, False
            if company.execute(
                "SELECT 1 FROM user_project_scope WHERE user_id = ? AND project_id = ?", (context.user_id, project_id)
            ).fetchone() is None:
                return False, False
        return True, False
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
        message = f"Not permitted: {permission}" if permission else "Not permitted"
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
