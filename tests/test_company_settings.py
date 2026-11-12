"""company_settings.py: the Controls page, setup facts and system accounts (decisions 0, 1.6, A6, A9, L6)."""
import pytest

from modules.services import accounts, approvals, company_settings as cs
from modules.services.errors import PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)


@pytest.fixture
def admin(world):
    world.settings("PARENT", require_separate_approver=0)
    user = world.user("admin")
    world.role("PARENT", "ADM", ["company.settings", "account.manage", "ledger.view", "je.create", "je.approve"])
    world.grant(user, "PARENT", "ADM")
    return world.ctx(user, "PARENT")


def settings_row(world):
    return world.rows("PARENT", "SELECT * FROM company_settings WHERE id = 1")[0]


def audit(world, table="company_settings"):
    return world.rows("PARENT", "SELECT * FROM audit_log WHERE table_name = ? ORDER BY log_id", (table,))


# --- Defaults are permissive (section 0) ------------------------------------------------------

def test_defaults_are_permissive(world, admin):
    s = cs.get_settings(admin)
    assert s["require_separate_approver"] == 0
    assert s["allow_manual_control_je"] == 1
    assert s["manual_entry_approval"] == 0
    assert s["adjustment_periods_enabled"] == 0
    assert (s["warn_future_days"], s["warn_past_days"]) == (30, 90)
    assert s["date_format"] == "MM/DD/YYYY"
    assert all(v == 0 for v in cs.get_document_approvals(admin).values())


def test_document_approval_switches_cover_every_type_but_journal_entry(admin):
    switches = cs.get_document_approvals(admin)
    assert set(switches) == {"Bill", "Payment", "Purchase order", "Subcontract", "Pay application",
                             "Import batch", "Asset disposal", "Estimate", "Change order", "Contract"}


# --- Changing a control ---------------------------------------------------------------------

@pytest.mark.parametrize("name", ["require_separate_approver", "allow_manual_control_je",
                                  "adjustment_periods_enabled", "manual_entry_approval"])
def test_each_switch_can_be_turned_on_and_off_and_is_logged(world, admin, name):
    before = len(audit(world))
    cs.update_setting(admin, name, True)
    assert settings_row(world)[name] == 1
    cs.update_setting(admin, name, False)
    assert settings_row(world)[name] == 0
    entries = audit(world)[before:]
    assert len(entries) == 2 and all(e["user_id"] == admin.user_id for e in entries)
    assert f'"{name}":1' in entries[0]["new_value"].replace(" ", "")


def test_values_are_validated(admin):
    bad = [("date_format", "DD-MM-YY"), ("warn_future_days", -1), ("warn_past_days", "x"),
           ("timezone", "Mars/Olympus"), ("require_separate_approver", 2), ("base_currency", "EUR"),
           ("country", "PH"), ("company_name", "x"), ("nonsense", 1)]
    for name, value in bad:
        with pytest.raises(ValidationError):
            cs.update_setting(admin, name, value)


def test_dates_numbers_and_timezone_can_change(world, admin):
    cs.update_setting(admin, "date_format", "YYYY-MM-DD")
    cs.update_setting(admin, "warn_future_days", 10)
    cs.update_setting(admin, "warn_past_days", 0)
    cs.update_setting(admin, "timezone", "America/Chicago")
    row = settings_row(world)
    assert (row["date_format"], row["warn_future_days"], row["warn_past_days"], row["timezone"]) == (
        "YYYY-MM-DD", 10, 0, "America/Chicago")


def test_manual_entry_threshold(world, admin):
    cs.update_setting(admin, "manual_entry_approval_threshold_cents", 50000)
    assert settings_row(world)["manual_entry_approval_threshold_cents"] == 50000
    cs.update_setting(admin, "manual_entry_approval_threshold_cents", None)
    with pytest.raises(ValidationError):
        cs.update_setting(admin, "manual_entry_approval_threshold_cents", -5)


def test_setting_needs_company_settings_permission(world, admin):
    user = world.user("clerk")
    world.role("PARENT", "CL", ["ledger.view"])
    world.grant(user, "PARENT", "CL")
    with pytest.raises(PermissionDeniedError):
        cs.update_setting(world.ctx(user, "PARENT"), "require_separate_approver", True)
    with pytest.raises(PermissionDeniedError):
        cs.get_settings(world.ctx(user, "PARENT"))
    agent = world.ctx(admin.user_id, "PARENT", origin="Agent")
    with pytest.raises(PermissionDeniedError):
        cs.update_setting(agent, "require_separate_approver", True)


# --- Per-document "requires approval" (1.6) ------------------------------------------------------

def test_approval_off_by_default_and_follows_the_switch(world, admin):
    assert approvals.is_approval_required(admin, "Bill") is False
    cs.set_document_approval(admin, "Bill", True)
    assert approvals.is_approval_required(admin, "Bill") is True
    assert approvals.is_approval_required(admin, "Payment") is False
    cs.set_document_approval(admin, "Bill", False)
    assert approvals.is_approval_required(admin, "Bill") is False


def test_journal_entry_uses_manual_entry_approval(world, admin):
    assert approvals.is_approval_required(admin, "Journal entry") is False
    cs.update_setting(admin, "manual_entry_approval", True)
    assert approvals.is_approval_required(admin, "Journal entry") is True
    with pytest.raises(ValidationError):
        cs.set_document_approval(admin, "Journal entry", True)       # its switch is manual_entry_approval


def test_document_approval_change_is_logged_and_validated(world, admin):
    cs.set_document_approval(admin, "Contract", True)
    logged = audit(world, "document_approval_setting")
    assert len(logged) == 1 and logged[0]["user_id"] == admin.user_id
    with pytest.raises(ValidationError):
        cs.set_document_approval(admin, "Nonsense", True)
    with pytest.raises(PermissionDeniedError):
        cs.set_document_approval(world.ctx(world.user("x"), "PARENT"), "Bill", True)


# --- Separate approver trigger (1.7 / A9) -----------------------------------------------------

def _entry_with(world, created, approved):
    from tests import ledger_helpers as lh
    with world._company("PARENT") as c:
        period = lh.ensure_period(c, "2026-03-15")
        c.execute("INSERT INTO journal_entry (entry_date, period_id, created_by, approved_by, approved_at) "
                  "VALUES ('2026-03-15', ?, ?, ?, '2026-03-15T00:00:00+00:00')", (period, created, approved))


def test_self_approval_is_allowed_when_the_setting_is_off_and_blocked_when_on(world, admin):
    import sqlite3
    _entry_with(world, 5, 5)                                         # off: allowed
    cs.update_setting(admin, "require_separate_approver", True)
    with pytest.raises(sqlite3.IntegrityError):
        _entry_with(world, 5, 5)
    _entry_with(world, 5, 6)                                         # a different user is fine


def test_self_approval_blocked_on_update_when_on(world, admin):
    import sqlite3
    from tests import ledger_helpers as lh
    cs.update_setting(admin, "require_separate_approver", True)
    with world._company("PARENT") as c:
        period = lh.ensure_period(c, "2026-03-15")
        entry = c.execute("INSERT INTO journal_entry (entry_date, period_id, created_by) "
                          "VALUES ('2026-03-15', ?, 5) RETURNING entry_id", (period,)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        with world._company("PARENT") as c:
            c.execute("UPDATE journal_entry SET approved_by = 5, approved_at = '2026-03-16T00:00:00+00:00' "
                      "WHERE entry_id = ?", (entry,))


# --- System accounts (A6) -----------------------------------------------------------------------

def test_set_system_account_and_missing_required_roles(world, admin):
    assert cs.missing_required_roles(admin) == list(cs.REQUIRED_ROLES)
    ar = accounts.create_account(admin, "1110", "AR", "Asset", control_type="AR")
    cs.set_system_account(admin, "ar", ar)
    assert settings_row(world)["ar_acct_id"] == ar
    assert "ar" not in cs.missing_required_roles(admin)
    assert cs.get_system_accounts(admin)["ar"] == ar


def test_system_account_must_be_active_postable_and_a_known_role(world, admin):
    header = accounts.create_account(admin, "1000", "Cash", "Asset")
    accounts.create_account(admin, "1010", "Checking", "Asset", parent_id=header)
    inactive = accounts.create_account(admin, "1020", "Old", "Asset")
    accounts.deactivate_account(admin, inactive)
    for account_id in (header, inactive, 9999):
        with pytest.raises(ValidationError):
            cs.set_system_account(admin, "default_bank", account_id)
    leaf = accounts.create_account(admin, "1030", "Ok", "Asset")
    with pytest.raises(ValidationError):
        cs.set_system_account(admin, "made_up", leaf)


def test_system_account_change_is_logged(world, admin):
    leaf = accounts.create_account(admin, "1030", "Ok", "Asset")
    cs.set_system_account(admin, "default_bank", leaf)
    assert '"default_bank_acct_id":%d' % leaf in audit(world)[-1]["new_value"].replace(" ", "")


# --- Reference data ---------------------------------------------------------------------------------

def test_country_defaults():
    assert cs.country_defaults("US") == {"currency": "USD", "timezone": "America/Los_Angeles",
                                         "date_format": "MM/DD/YYYY"}
    assert cs.country_defaults("PH") == {"currency": "PHP", "timezone": "Asia/Manila", "date_format": "MM/DD/YYYY"}
    with pytest.raises(ValidationError):
        cs.country_defaults("FR")


def test_timezone_choices_per_country():
    assert "America/Chicago" in cs.timezones_for("US") and "Asia/Manila" not in cs.timezones_for("US")
    assert cs.timezones_for("PH") == ["Asia/Manila"]
