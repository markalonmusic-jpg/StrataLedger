"""Users and company access (docs/roles_permissions_design.md section 9).

Every service re-reads the acting user from the master on every call. User and
access changes need company.users.manage in the TARGET company (so an Admin of
a parent covers its subsidiaries). On top of that:

* Only the Master assigns or removes the Admin role (directly or by denying an
  inherited Admin).
* Privilege ceiling: an actor who is neither Master nor Admin may assign only
  roles whose permission set is a subset of their own role's in that company.
* No change may leave a company without an active Admin (counting Admins
  inherited from a parent). The Master needs no access rows and cannot be
  deactivated.
* deactivate_user is Master only (a user can belong to clients the Admin cannot see).
* reset_password: the Master for anyone; others with company.users.manage only
  for users in their companies, never for the Master or anyone holding Admin.
* A non-Master creating a user whose email exists gets a neutral message.
"""
from modules.services import auth, authz, passwords
from modules.services.auth import _Actor, active_user, require_master
from modules.services.authz import authorize
from modules.services.context import ServiceContext
from modules.services.errors import NotFoundError, ValidationError
from modules.services.paths import resolve_company_path
from modules.services.tx import read_connection, write_transaction

NEUTRAL_EMAIL = "This person may already have an account. Ask your Master to grant access."
USERS_MANAGE = "company.users.manage"


# --- Users -------------------------------------------------------------------------------------

def create_user(session, username, password, first_name, last_name, email, *, company_id=None, role_code=None):
    """Create a user; with company_id and role_code, also grant access there. Returns the user_id."""
    auth.check_username(username)
    passwords.check_password_policy(password)
    auth.check_person(first_name, last_name, email)
    if (company_id is None) != (role_code is None):
        raise ValidationError("Give both a company and a role, or neither")
    actor = active_user(session)
    if company_id is None:
        require_master(session)
    else:
        context = _company_context(session, company_id)
        authorize(context, USERS_MANAGE, record_type="app_user")
        _check_assignable(actor, context, role_code)
    password_hash = passwords.hash_password(password)
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        if conn.execute("SELECT 1 FROM app_user WHERE lower(email) = lower(?)", (email.strip(),)).fetchone():
            raise ValidationError("That email address is already used by another user"
                                  if actor["is_master"] == 1 else NEUTRAL_EMAIL)
        if conn.execute("SELECT 1 FROM app_user WHERE username = ?", (username,)).fetchone():
            raise ValidationError("That username is not available")
        user_id = conn.execute(
            "INSERT INTO app_user (username, password_hash, first_name, last_name, email, role) "
            "VALUES (?, ?, ?, ?, ?, ?) RETURNING user_id",
            (username, password_hash, first_name.strip(), last_name.strip(), email.strip(), role_code),
        ).fetchone()[0]
        if company_id is not None:
            conn.execute("INSERT INTO user_company_access (user_id, company_id, role_code, access_mode) "
                         "VALUES (?, ?, ?, 'Grant')", (user_id, company_id, role_code))
        return user_id


def deactivate_user(session, target_user_id):
    """Master only. The Master and a company's last Admin cannot be deactivated."""
    require_master(session)
    target = _target(session, target_user_id)
    if target["is_master"] == 1:
        raise ValidationError("The Master cannot be deactivated")
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        before = _companies_without_admin(conn)
        conn.execute("UPDATE app_user SET is_active = 0 WHERE user_id = ?", (target_user_id,))
        _check_admins_kept(conn, before)


def reset_password(session, target_user_id, new_password):
    """Set a temporary password; the user must change it at next login."""
    passwords.check_password_policy(new_password)
    actor = active_user(session)
    target = _target(session, target_user_id)
    if target["user_id"] == actor["user_id"]:
        raise ValidationError("Use change password for your own account")
    authorize_reset(session, actor, target)
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        conn.execute("UPDATE app_user SET password_hash = ?, must_change_password = 1 WHERE user_id = ?",
                     (passwords.hash_password(new_password), target_user_id))
        conn.execute("DELETE FROM login_throttle WHERE throttle_key = ?", (target["username"],))
        auth._insert_event(conn, "Password reset", username=target["username"], user_id=target_user_id,
                           actor_user_id=session.user_id)


def authorize_reset(session, actor, target):
    """The Master may reset anyone; others need company.users.manage in a company where the
    target has access, and may never reset the Master or a user holding Admin anywhere."""
    if actor["is_master"] == 1:
        return
    if target["is_master"] == 1 or _holds_admin_anywhere(session, target["user_id"]):
        auth._deny_master(session, USERS_MANAGE)
    for company_id in _granted_companies(session, target["user_id"]):
        try:
            context = _company_context(session, company_id)
        except (NotFoundError, ValidationError):
            continue
        if authz.is_allowed(context, USERS_MANAGE):
            return
    auth._deny_master(session, USERS_MANAGE)


# --- Access ----------------------------------------------------------------------------------

def grant_access(session, target_user_id, company_id, role_code):
    """Give a user access to a company with a role (creates or replaces the row as a Grant)."""
    actor = active_user(session)
    context = _company_context(session, company_id)
    authorize(context, USERS_MANAGE, record_type="app_user", record_id=target_user_id)
    target = _target(session, target_user_id)
    if target["is_master"] == 1:
        raise ValidationError("The Master has access to every company and needs no access rows")
    _check_assignable(actor, context, role_code)
    _guard_admin_removal(actor, context, target_user_id, new_role=role_code)
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        before = _companies_without_admin(conn)
        conn.execute(
            "INSERT INTO user_company_access (user_id, company_id, role_code, access_mode) VALUES (?, ?, ?, 'Grant') "
            "ON CONFLICT (user_id, company_id) DO UPDATE SET role_code = excluded.role_code, access_mode = 'Grant'",
            (target_user_id, company_id, role_code))
        _check_admins_kept(conn, before)


def set_role(session, target_user_id, company_id, role_code):
    """Change the role on an existing Grant row."""
    actor = active_user(session)
    context = _company_context(session, company_id)
    authorize(context, USERS_MANAGE, record_type="app_user", record_id=target_user_id)
    _target(session, target_user_id)
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT 1 FROM user_company_access WHERE user_id = ? AND company_id = ? "
                           "AND access_mode = 'Grant'", (target_user_id, company_id)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError("That user has no access row in this company; use grant access")
    _check_assignable(actor, context, role_code)
    _guard_admin_removal(actor, context, target_user_id, new_role=role_code)
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        before = _companies_without_admin(conn)
        conn.execute("UPDATE user_company_access SET role_code = ? WHERE user_id = ? AND company_id = ?",
                     (role_code, target_user_id, company_id))
        _check_admins_kept(conn, before)


def deny_access(session, target_user_id, company_id):
    """Deny a user this company (also narrows access inherited from a parent)."""
    actor = active_user(session)
    context = _company_context(session, company_id)
    authorize(context, USERS_MANAGE, record_type="app_user", record_id=target_user_id)
    target = _target(session, target_user_id)
    if target["is_master"] == 1:
        raise ValidationError("The Master's access cannot be removed")
    _guard_admin_removal(actor, context, target_user_id, new_role=None)
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        before = _companies_without_admin(conn)
        conn.execute(
            "INSERT INTO user_company_access (user_id, company_id, role_code, access_mode) VALUES (?, ?, NULL, 'Deny') "
            "ON CONFLICT (user_id, company_id) DO UPDATE SET role_code = NULL, access_mode = 'Deny'",
            (target_user_id, company_id))
        _check_admins_kept(conn, before)


# --- internals -------------------------------------------------------------------------------

def _company_context(session, company_id):
    """A ServiceContext for the target company, its file resolved from the registry."""
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT database_file_path FROM company_registry WHERE company_id = ?",
                           (company_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError(f"No such company: {company_id}")
    return ServiceContext(user_id=session.user_id, company_id=company_id, origin="Human",
                          company_db_path=resolve_company_path(row["database_file_path"]),
                          master_db_path=session.master_db_path)


def _target(session, user_id):
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT user_id, username, is_master, is_active FROM app_user WHERE user_id = ?",
                           (user_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError(f"No such user: {user_id}")
    return row


def _role_permissions(context, role_code):
    """(is_active, permission set) for a role in the context's company, or None if it does not exist."""
    conn = read_connection(context.company_db_path)
    try:
        role = conn.execute("SELECT is_active FROM role WHERE role_code = ?", (role_code,)).fetchone()
        if role is None:
            return None
        codes = {r[0] for r in conn.execute("SELECT permission_code FROM role_permission WHERE role_code = ?",
                                             (role_code,))}
    finally:
        conn.close()
    return role["is_active"] == 1, codes


def _check_assignable(actor, context, role_code):
    info = _role_permissions(context, role_code)
    if info is None:
        raise NotFoundError(f"No such role in this company: {role_code}")
    active, codes = info
    if not active:
        raise ValidationError(f"The role {role_code} is inactive")
    if actor["is_master"] == 1:
        return
    if role_code == "Admin":
        authz.deny(context, USERS_MANAGE, record_type="role")
    actor_role = authz.current_access(context).role_code
    if actor_role == "Admin":
        return
    actor_info = _role_permissions(context, actor_role) if actor_role else None
    if actor_info is None or not codes <= actor_info[1]:
        authz.deny(context, USERS_MANAGE, record_type="role")


def _guard_admin_removal(actor, context, target_user_id, *, new_role):
    """Changing away from, or denying, an Admin (direct or inherited) is the Master's call."""
    if actor["is_master"] == 1 or new_role == "Admin":
        return
    conn = read_connection(context.master_db_path)
    try:
        current = authz._access_role(conn, target_user_id, context.company_id)
    finally:
        conn.close()
    if current == "Admin":
        authz.deny(context, USERS_MANAGE, record_type="app_user", record_id=target_user_id)


def _holds_admin_anywhere(session, user_id):
    conn = read_connection(session.master_db_path)
    try:
        return conn.execute("SELECT 1 FROM user_company_access WHERE user_id = ? AND role_code = 'Admin' "
                            "AND access_mode = 'Grant'", (user_id,)).fetchone() is not None
    finally:
        conn.close()


def _granted_companies(session, user_id):
    """Companies the user can reach: Grant rows and every subsidiary below them."""
    conn = read_connection(session.master_db_path)
    try:
        companies = [r[0] for r in conn.execute("SELECT company_id FROM company_registry")]
        return [c for c in companies if authz._access_role(conn, user_id, c) is not None]
    finally:
        conn.close()


def _companies_without_admin(conn):
    """Active companies with no active non-Master user whose effective role is Admin."""
    users = [r[0] for r in conn.execute(
        "SELECT user_id FROM app_user WHERE is_active = 1 AND is_master = 0 "
        "AND user_id IN (SELECT user_id FROM user_company_access)")]
    missing = set()
    for (company_id,) in conn.execute("SELECT company_id FROM company_registry WHERE is_active = 1").fetchall():
        if not any(authz._access_role(conn, user_id, company_id) == "Admin" for user_id in users):
            missing.add(company_id)
    return missing


def _check_admins_kept(conn, before):
    if _companies_without_admin(conn) - before:
        raise ValidationError("That would leave a company without an Admin")
