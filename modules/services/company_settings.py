"""Company settings and the Controls page (decisions 0, 1.6, A2, A6, A9, L6, S4, S5).

Every control defaults to permissive/off (section 0). Every change goes through write_transaction, so the
baseline audit triggers log who changed what, and needs `company.settings`. Facts fixed at setup (company
name, country, currency, fiscal year start) are not changed here.
"""
from modules.services import chart_templates
from modules.services.authz import authorize
from modules.services.errors import NotFoundError, ValidationError
from modules.services.permissions import DOCUMENT_TYPES
from modules.services.tx import read_connection, write_transaction

PERMISSION = "company.settings"
REQUIRED_ROLES = chart_templates.REQUIRED_ROLES

DATE_FORMATS = ("MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD")
SWITCHES = ("require_separate_approver", "allow_manual_control_je", "adjustment_periods_enabled",
            "manual_entry_approval")
COUNTS = ("warn_future_days", "warn_past_days")
# Journal entries use manual_entry_approval as their switch, so they have no row in document_approval_setting.
APPROVAL_DOCUMENT_TYPES = tuple(t for t in DOCUMENT_TYPES if t != "Journal entry")

COUNTRIES = {
    "US": {"currency": "USD", "timezone": "America/Los_Angeles", "date_format": "MM/DD/YYYY"},
    "PH": {"currency": "PHP", "timezone": "Asia/Manila", "date_format": "MM/DD/YYYY"},
}
TIMEZONES = {
    "US": ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles",
           "America/Anchorage", "Pacific/Honolulu", "America/Puerto_Rico"],
    "PH": ["Asia/Manila"],
}


def country_defaults(country):
    """Currency, time zone and date format a new company in this country starts with (S5)."""
    if country not in COUNTRIES:
        raise ValidationError("Choose United States (US) or Philippines (PH)")
    return dict(COUNTRIES[country])


def timezones_for(country):
    if country not in TIMEZONES:
        raise ValidationError("Choose United States (US) or Philippines (PH)")
    return list(TIMEZONES[country])


def _settings_row(conn):
    row = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
    if row is None:
        raise NotFoundError("This company has no settings yet")
    return row


# --- Reads -------------------------------------------------------------------------------------

def get_settings(context):
    authorize(context, PERMISSION, record_type="company_settings")
    conn = read_connection(context.company_db_path)
    try:
        return dict(_settings_row(conn))
    finally:
        conn.close()


def get_document_approvals(context):
    """{document type: 0 or 1}: does this kind of document need an approval before it posts?"""
    authorize(context, PERMISSION, record_type="document_approval_setting")
    conn = read_connection(context.company_db_path)
    try:
        return {r["document_type"]: r["requires_approval"] for r in conn.execute(
            "SELECT document_type, requires_approval FROM document_approval_setting ORDER BY document_type")}
    finally:
        conn.close()


def get_system_accounts(context):
    """{role: account_id or None} for every system account role."""
    authorize(context, PERMISSION, record_type="company_settings")
    conn = read_connection(context.company_db_path)
    try:
        row = _settings_row(conn)
        return {role: row[chart_templates.settings_column(role)] for role in chart_templates.SYSTEM_ROLES}
    finally:
        conn.close()


def missing_required_roles(context):
    """Required system accounts that are not set yet (they must exist before the first posting)."""
    accounts_by_role = get_system_accounts(context)
    return [role for role in REQUIRED_ROLES if accounts_by_role[role] is None]


# --- Writes --------------------------------------------------------------------------------------

def _clean_value(name, value):
    if name in SWITCHES:
        if value not in (0, 1, True, False) or isinstance(value, str):
            raise ValidationError("This setting is either on or off")
        return int(value)
    if name == "date_format":
        if value not in DATE_FORMATS:
            raise ValidationError("Choose MM/DD/YYYY, DD/MM/YYYY or YYYY-MM-DD")
        return value
    if name in COUNTS:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError("Enter a whole number of days, 0 or more")
        return value
    if name == "timezone":
        if value not in {z for zones in TIMEZONES.values() for z in zones}:
            raise ValidationError("Choose one of the listed time zones")
        return value
    if name == "manual_entry_approval_threshold_cents":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError("Enter an amount of 0 or more")
        return value
    raise ValidationError(f"'{name}' cannot be changed here")


def update_setting(context, name, value):
    """Change one control or preference. Logged by the baseline audit trigger."""
    authorize(context, PERMISSION, record_type="company_settings")
    value = _clean_value(name, value)
    with write_transaction(context.company_db_path, context) as conn:
        _settings_row(conn)
        conn.execute(f"UPDATE company_settings SET {name} = ? WHERE id = 1", (value,))


def set_document_approval(context, document_type, required):
    """Turn 'requires approval' on or off for one kind of document (decision 1.6, default off)."""
    authorize(context, PERMISSION, record_type="document_approval_setting")
    if document_type == "Journal entry":
        raise ValidationError("Journal entries use the 'manual entry approval' setting")
    if document_type not in APPROVAL_DOCUMENT_TYPES:
        raise ValidationError(f"'{document_type}' is not a kind of document that can need approval")
    if required not in (0, 1, True, False):
        raise ValidationError("This setting is either on or off")
    with write_transaction(context.company_db_path, context) as conn:
        conn.execute("UPDATE document_approval_setting SET requires_approval = ? WHERE document_type = ?",
                     (int(required), document_type))


def set_system_account(context, role, account_id):
    """Point a system role (accounts receivable, default bank...) at an active, postable account (A6)."""
    authorize(context, PERMISSION, record_type="company_settings")
    if role not in chart_templates.SYSTEM_ROLES:
        raise ValidationError(f"'{role}' is not a system account role")
    with write_transaction(context.company_db_path, context) as conn:
        account = conn.execute("SELECT is_active, is_postable FROM account WHERE account_id = ?",
                               (account_id,)).fetchone()
        if account is None:
            raise ValidationError("Choose an existing account")
        if not account["is_active"] or not account["is_postable"]:
            raise ValidationError("Choose an active account that can receive postings")
        _settings_row(conn)
        conn.execute(f"UPDATE company_settings SET {chart_templates.settings_column(role)} = ? WHERE id = 1",
                     (account_id,))
