"""Companies: opening one (the only way a session gets a ServiceContext), creating, archiving and exporting.

create_company builds the whole company or nothing (decisions S1-S8, A6, A7, I1): the file is built and seeded
under a temporary name, then renamed and registered in one master transaction; any failure removes what was made.
"""
import dataclasses
import os
import re
import unicodedata
import uuid

import modules.database as database
from modules.services import accounts, auth, authz, chart_templates, clock, company_settings, storage
from modules.services.context import ServiceContext
from modules.services.errors import NotFoundError, ValidationError
from modules.services.paths import resolve_company_path
from modules.services.tx import read_connection, write_transaction


def open_company(session, company_id):
    """Check access, open the company file through the baseline guard, and return its context.

    1. The session's user is re-read (inactive: denied; password reset: must change first).
    2. The registry path is resolved under config.BASE_PROJECT_DIR; a path outside it
       is refused (ValidationError) and a missing file is never created (NotFoundError).
    3. The file goes through database.ensure_company_database: a stale or chain-built
       file raises SchemaUpgradeBlockedError and is left unchanged.
    4. Access: the Master, or the nearest Grant row with an active role
       (check_company_access; a denial is logged in the company's access_event).
    5. The Master's open is recorded as an 'Open company' access_event.
    6. The context's `today` is the company-local date from company_settings.timezone (decision H2).
    7. An archived company opens for the Master only (decision S9).
    """
    auth.active_user(session)
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT database_file_path, is_archived FROM company_registry WHERE company_id = ?",
                           (company_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError(f"No such company: {company_id}")
    if row["is_archived"] == 1 and not auth.active_user(session)["is_master"]:
        raise ValidationError("This company is archived. Ask the Master to restore it.")
    path = resolve_company_path(row["database_file_path"])
    if not os.path.isfile(path):
        raise NotFoundError("The company file is missing")
    database.ensure_company_database(path)  # pre-release: a no-op for current files, blocks stale ones
    context = ServiceContext(user_id=session.user_id, company_id=company_id, origin="Human",
                             company_db_path=path, master_db_path=session.master_db_path)
    authz.check_company_access(context)
    authz.record_company_open(context)
    return dataclasses.replace(context, today=clock.local_today(context.now, _company_timezone(path)))


def _company_timezone(path):
    conn = read_connection(path)
    try:
        row = conn.execute("SELECT timezone FROM company_settings WHERE id = 1").fetchone()
    finally:
        conn.close()
    return row["timezone"] if row else None


# --- Company codes (S1) ---------------------------------------------------------------------------

_CODE_PATTERN = re.compile(r"^[A-Z0-9]{3,10}$")
_RESERVED_FILE_NAMES = ({"CON", "PRN", "AUX", "NUL"} | {f"COM{n}" for n in range(1, 10)}
                        | {f"LPT{n}" for n in range(1, 10)})
_NOISE_WORDS = {"THE", "LLC", "LLP", "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED"}


def company_code_from_name(name):
    """A suggested company code: 3-10 uppercase letters and digits taken from the start of the name."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name or "") if not unicodedata.combining(c))
    words = [re.sub(r"[^A-Z0-9]", "", w) for w in plain.upper().split()]
    words = [w for w in words if w and w not in _NOISE_WORDS]
    code = ""
    for word in words:
        code += word
        if len(code) >= 3:
            break
    code = code[:10]
    return code + "X" * max(0, 3 - len(code))


def _check_code(code):
    if not isinstance(code, str) or not _CODE_PATTERN.fullmatch(code.upper()):
        raise ValidationError("A company code has 3 to 10 capital letters or digits")
    if code.upper() in _RESERVED_FILE_NAMES:
        raise ValidationError(f"{code.upper()} cannot be used as a company code; choose another")
    return code.upper()


def _free_code(taken, base):
    code, number = base, 1
    while code in taken:
        number += 1
        suffix = str(number)
        code = base[:10 - len(suffix)] + suffix
    return code


# --- Create ---------------------------------------------------------------------------------------

_DEFAULT = object()
_CONTROL_COLUMNS = ("allow_manual_control_je", "manual_entry_approval", "manual_entry_approval_threshold_cents",
                    "adjustment_periods_enabled", "warn_future_days", "warn_past_days")


def create_company(session, *, legal_name, first_fiscal_year, template=_DEFAULT, chart_csv=None, display_name=None,
                   code=None, parent_company_id=None, country=None, tax_id=None, fiscal_year_start_month=None,
                   date_format=None, timezone=None, require_separate_approver=None, admin_user_id=None):
    """Create a company file and register it. Returns {'company_id', 'company_code', 'database_file_path'}.

    Top-level companies: the Master only. A subsidiary (parent_company_id): a user holding company.create in the
    parent. A subsidiary copies its parent's chart, roles, approval policies and controls unless a template or a
    chart CSV is given (S7). The Master may name a user to become the new company's Admin; an Admin who creates
    a subsidiary becomes its Admin (S8). Nothing is left behind if any step fails.
    """
    parent_path = None
    if parent_company_id is None:
        auth.require_master(session)
    else:
        parent_context = open_company(session, parent_company_id)
        authz.authorize(parent_context, "company.create", record_type="company", record_id=parent_company_id)
        parent_path = parent_context.company_db_path
    creator = auth.active_user(session)

    # 1. Validate everything before creating anything.
    legal_name = legal_name.strip() if isinstance(legal_name, str) else ""
    if not legal_name:
        raise ValidationError("Enter the company's legal name")
    if chart_csv is not None and template is not _DEFAULT and template is not None:
        raise ValidationError("Choose a chart template or give your own chart, not both")
    copying = parent_path is not None and chart_csv is None and (template is _DEFAULT or template is None)
    if chart_csv is not None:
        rows = chart_templates.parse_chart(chart_csv)
    elif copying:
        rows = None
    elif template is None:
        raise ValidationError("Choose a chart template or give your own chart")
    else:
        rows = chart_templates.load_template("construction" if template is _DEFAULT else template)
    if (isinstance(first_fiscal_year, bool) or not isinstance(first_fiscal_year, int)
            or not 1900 <= first_fiscal_year <= 2200):
        raise ValidationError("Enter the first fiscal year to record, such as 2027")

    parent_settings = _read_parent_settings(parent_path) if copying else None
    if country is None:
        country = parent_settings["country"] if parent_settings and parent_settings["country"] else "US"
    defaults = company_settings.country_defaults(country)
    timezone = timezone or (parent_settings["timezone"] if parent_settings and parent_settings["timezone"]
                            else defaults["timezone"])
    if timezone not in company_settings.timezones_for(country):
        raise ValidationError(f"Choose a time zone for {country}")
    date_format = date_format or (parent_settings["date_format"] if parent_settings else defaults["date_format"])
    if date_format not in company_settings.DATE_FORMATS:
        raise ValidationError("Choose MM/DD/YYYY, DD/MM/YYYY or YYYY-MM-DD")
    if fiscal_year_start_month is None:
        fiscal_year_start_month = int(parent_settings["fiscal_year_start"][:2]) if parent_settings else 1
    if (isinstance(fiscal_year_start_month, bool) or not isinstance(fiscal_year_start_month, int)
            or not 1 <= fiscal_year_start_month <= 12):
        raise ValidationError("The fiscal year starts in month 1 to 12")
    if require_separate_approver is None:
        require_separate_approver = bool(parent_settings["require_separate_approver"]) if parent_settings else False

    admin_ids = _admin_user_ids(session, creator, parent_company_id, admin_user_id)

    master = read_connection(session.master_db_path)
    try:
        taken = {r[0] for r in master.execute("SELECT company_code FROM company_registry")}
    finally:
        master.close()
    code = _check_code(code) if code is not None else _free_code(taken, company_code_from_name(legal_name))
    if code in taken:
        raise ValidationError(f"The company code {code} is already used")
    relative = f"Companies/{code}.db"
    final = storage.data_path(relative)
    if os.path.exists(final):
        raise ValidationError(f"A company file named {code}.db already exists")
    temp = storage.data_path(f"Companies/{code}.tmp-{uuid.uuid4().hex[:8]}.db")

    # 2. Build the file under a temporary name, then rename and register in one master transaction.
    renamed = False
    try:
        os.makedirs(os.path.dirname(temp), exist_ok=True)
        database.ensure_company_database(temp)
        with write_transaction(temp, auth._Actor(session.user_id)) as conn:
            values = {"company_name": (display_name or "").strip() or legal_name,
                      "tax_id": (tax_id or "").strip() or None,
                      "fiscal_year_start": f"{fiscal_year_start_month:02d}-01", "base_currency": defaults["currency"],
                      "country": country, "timezone": timezone, "date_format": date_format,
                      "first_fiscal_year": first_fiscal_year,
                      "require_separate_approver": int(bool(require_separate_approver))}
            if copying:
                values.update({c: parent_settings[c] for c in _CONTROL_COLUMNS})
                rows = _chart_rows_from(parent_path)
            names = ", ".join(["id"] + list(values))
            conn.execute(f"INSERT INTO company_settings ({names}) VALUES ({', '.join('?' * (len(values) + 1))})",
                         (1, *values.values()))
            ids = accounts.seed_chart(conn, rows)
            for row in rows:
                if row["system_role"]:
                    conn.execute(
                        f"UPDATE company_settings SET {chart_templates.settings_column(row['system_role'])} = ? "
                        "WHERE id = 1", (ids[row["account_number"]],))
                if row.get("is_active") == 0:
                    conn.execute("UPDATE account SET is_active = 0 WHERE account_id = ?", (ids[row["account_number"]],))
            present = {r["system_role"] for r in rows if r["system_role"]}
            missing = [r for r in chart_templates.REQUIRED_ROLES if r not in present]
            if missing:
                raise ValidationError("The chart has no account for: " + ", ".join(missing))
            if copying:
                _copy_roles_policies_controls(conn, parent_path)
        with write_transaction(session.master_db_path, auth._Actor(session.user_id)) as conn:
            if conn.execute("SELECT 1 FROM company_registry WHERE company_code = ?", (code,)).fetchone():
                raise ValidationError(f"The company code {code} is already used")
            company_id = conn.execute(
                "INSERT INTO company_registry (company_code, legal_name, database_file_path, parent_company_id) "
                "VALUES (?, ?, ?, ?) RETURNING company_id",
                (code, legal_name, relative, parent_company_id)).fetchone()[0]
            os.replace(temp, final)
            renamed = True
            _grant_admins(conn, company_id, admin_ids)
    except BaseException:
        _remove_quietly(temp)
        if renamed:
            _remove_quietly(final)
        raise
    return {"company_id": company_id, "company_code": code, "database_file_path": relative}


def _remove_quietly(path):
    for candidate in (path, path + "-journal"):
        try:
            os.remove(candidate)
        except OSError:
            pass


def _grant_admins(conn, company_id, user_ids):
    for user_id in user_ids:
        conn.execute("INSERT INTO user_company_access (user_id, company_id, role_code, access_mode) "
                     "VALUES (?, ?, 'Admin', 'Grant')", (user_id, company_id))


def _admin_user_ids(session, creator, parent_company_id, admin_user_id):
    """Who gets the Admin role in the new company (S8), checked before anything is created."""
    ids = []
    if admin_user_id is not None:
        if isinstance(admin_user_id, bool) or not isinstance(admin_user_id, int):
            raise ValidationError("Choose an existing active user to be the Admin")
        conn = read_connection(session.master_db_path)
        try:
            row = conn.execute("SELECT is_active FROM app_user WHERE user_id = ?", (admin_user_id,)).fetchone()
        finally:
            conn.close()
        if row is None or row["is_active"] != 1:
            raise ValidationError("Choose an existing active user to be the Admin")
        ids.append(admin_user_id)
    if parent_company_id is not None and creator["is_master"] != 1 and session.user_id not in ids:
        ids.append(session.user_id)
    return ids


# --- Copying a parent (S7) ---------------------------------------------------------------------------

def _read_parent_settings(parent_path):
    conn = read_connection(parent_path)
    try:
        row = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValidationError("The parent company has no settings to copy")
    return dict(row)


def _chart_rows_from(parent_path):
    conn = read_connection(parent_path)
    try:
        settings = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        role_of = {settings[chart_templates.settings_column(r)]: r for r in chart_templates.SYSTEM_ROLES
                   if settings[chart_templates.settings_column(r)] is not None}
        found = conn.execute(
            "SELECT a.account_id, a.code, a.name, t.name AS account_type, a.subtype, a.normal_balance, a.control_type, "
            "a.is_postable, a.is_active, p.code AS parent_number FROM account AS a "
            "JOIN account_type AS t ON t.type_id = a.type_id LEFT JOIN account AS p ON p.account_id = a.parent_id "
            "ORDER BY a.code").fetchall()
    finally:
        conn.close()
    return [{"row": n, "account_number": r["code"], "name": r["name"], "parent_number": r["parent_number"],
             "account_type": r["account_type"], "subtype": r["subtype"], "normal_balance": r["normal_balance"] or "D",
             "control_type": r["control_type"], "is_postable": r["is_postable"], "is_active": r["is_active"],
             "system_role": role_of.get(r["account_id"])} for n, r in enumerate(found, start=2)]


def _copy_roles_policies_controls(conn, parent_path):
    parent = read_connection(parent_path)
    try:
        roles = parent.execute("SELECT * FROM role WHERE role_code <> 'Admin'").fetchall()
        grants = parent.execute(
            "SELECT role_code, permission_code FROM role_permission WHERE role_code <> 'Admin'").fetchall()
        limits = parent.execute("SELECT * FROM approval_limit WHERE role_code <> 'Admin'").fetchall()
        policies = parent.execute("SELECT * FROM approval_policy ORDER BY policy_id").fetchall()
        steps = parent.execute("SELECT * FROM approval_step ORDER BY policy_id, step_no, role_code").fetchall()
        switches = parent.execute("SELECT document_type, requires_approval FROM document_approval_setting").fetchall()
    finally:
        parent.close()
    for r in roles:
        conn.execute("INSERT INTO role (role_code, name, is_system, is_active, project_scope, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)",
                     (r["role_code"], r["name"], r["is_system"], r["is_active"], r["project_scope"], r["created_at"]))
    for g in grants:
        conn.execute("INSERT INTO role_permission (role_code, permission_code) VALUES (?, ?)",
                     (g["role_code"], g["permission_code"]))
    for lim in limits:
        conn.execute("INSERT INTO approval_limit (role_code, document_type, max_amount_cents) VALUES (?, ?, ?)",
                     (lim["role_code"], lim["document_type"], lim["max_amount_cents"]))
    new_ids = {}
    for p in policies:
        new_ids[p["policy_id"]] = conn.execute(
            "INSERT INTO approval_policy (name, document_type, min_amount_cents, max_amount_cents, is_active) "
            "VALUES (?, ?, ?, ?, ?) RETURNING policy_id",
            (p["name"], p["document_type"], p["min_amount_cents"], p["max_amount_cents"], p["is_active"])).fetchone()[0]
    for st in steps:
        conn.execute("INSERT INTO approval_step (policy_id, step_no, role_code, required_count) VALUES (?, ?, ?, ?)",
                     (new_ids[st["policy_id"]], st["step_no"], st["role_code"], st["required_count"]))
    for sw in switches:
        conn.execute("UPDATE document_approval_setting SET requires_approval = ? WHERE document_type = ?",
                     (sw["requires_approval"], sw["document_type"]))


# --- Lifecycle (S9): Master only, no in-app delete ----------------------------------------------------

def _registry_row(conn, company_id):
    row = conn.execute("SELECT * FROM company_registry WHERE company_id = ?", (company_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"No such company: {company_id}")
    return row


def archive_company(session, company_id):
    """Hide a company from the picker and make it unavailable to everyone but the Master. Its data stays."""
    auth.require_master(session)
    with write_transaction(session.master_db_path, auth._Actor(session.user_id)) as conn:
        _registry_row(conn, company_id)
        conn.execute("UPDATE company_registry SET is_archived = 1 WHERE company_id = ?", (company_id,))


def restore_company(session, company_id):
    auth.require_master(session)
    with write_transaction(session.master_db_path, auth._Actor(session.user_id)) as conn:
        _registry_row(conn, company_id)
        conn.execute("UPDATE company_registry SET is_archived = 0 WHERE company_id = ?", (company_id,))


def export_company(session, company_id):
    """Write a consistent copy of the company file to Exports/. Returns its path relative to the data folder."""
    user = auth.require_master(session)
    conn = read_connection(session.master_db_path)
    try:
        row = _registry_row(conn, company_id)
    finally:
        conn.close()
    source = resolve_company_path(row["database_file_path"])
    if not os.path.isfile(source):
        raise NotFoundError("The company file is missing")
    stamp = auth._iso(auth._now()).replace("-", "").replace(":", "").replace("T", "-")[:15]
    relative = f"Exports/{row['company_code']}-{stamp}.db"
    target = storage.data_path(relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    src = database.get_connection(source)
    dst = database.get_connection(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    auth._auth_write(session.master_db_path, lambda c: auth._insert_event(
        c, "Company exported", username=user["username"], user_id=session.user_id, actor_user_id=session.user_id))
    return relative


def list_companies(session, include_archived=False):
    """Companies the user may pick: the Master sees all; others see those they have a Grant for (S9 hides archived)."""
    user = auth.active_user(session)
    conn = read_connection(session.master_db_path)
    try:
        registry = [dict(r) for r in conn.execute(
            "SELECT company_id, company_code, legal_name, parent_company_id, is_archived, is_active "
            "FROM company_registry ORDER BY company_code")]
        access = {r["company_id"]: r["access_mode"] for r in conn.execute(
            "SELECT company_id, access_mode FROM user_company_access WHERE user_id = ?", (session.user_id,))}
    finally:
        conn.close()
    by_id = {c["company_id"]: c for c in registry}

    def allowed(company):
        cursor, seen = company, set()
        while cursor is not None and cursor["company_id"] not in seen:
            seen.add(cursor["company_id"])
            mode = access.get(cursor["company_id"])
            if mode is not None:
                return mode == "Grant"
            cursor = by_id.get(cursor["parent_company_id"])
        return False

    if user["is_master"] == 1:
        return [c for c in registry if include_archived or not c["is_archived"]]
    return [c for c in registry if not c["is_archived"] and allowed(c)]
