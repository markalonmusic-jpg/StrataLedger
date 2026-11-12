"""companies.create_company and the company lifecycle (decisions S1-S9, A6, A7, I1)."""
import os
import sqlite3

import pytest

import config
from modules.services import accounts, chart_templates, companies, company_settings as cs
from modules.services.csv_table import CsvError
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)


@pytest.fixture
def master(world):
    return world.session(world.user("root", master=True))


def company_conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def file_of(world, code):
    return os.path.join(config.BASE_PROJECT_DIR, "Companies", f"{code}.db")


def rows_in(path, sql, params=()):
    conn = company_conn(path)
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def registry(world, code):
    found = world.master_rows("SELECT * FROM company_registry WHERE company_code = ?", (code,))
    return found[0] if found else None


def create(session, name="Acme Builders", **kwargs):
    args = dict(legal_name=name, first_fiscal_year=2027, template="construction")
    args.update(kwargs)
    return companies.create_company(session, **args)


def grant_access(world, user_id, company_id, role_code, mode="Grant"):
    with world._master() as c:
        c.execute("INSERT INTO user_company_access (user_id, company_id, role_code, access_mode) VALUES (?, ?, ?, ?)",
                  (user_id, company_id, role_code, mode))


def add_role(path, code, permissions):
    conn = company_conn(path)
    try:
        conn.execute("INSERT INTO role (role_code, name, is_system, is_active, project_scope, created_at) "
                     "VALUES (?, ?, 0, 1, 'All', '2026-01-01T00:00:00+00:00')", (code, code))
        for p in permissions:
            conn.execute("INSERT INTO role_permission VALUES (?, ?)", (code, p))
        conn.commit()
    finally:
        conn.close()


# --- Company codes (S1) -------------------------------------------------------------------------

@pytest.mark.parametrize("name,code", [
    ("Acme Builders", "ACME"), ("The Home Depot", "HOME"), ("AB Builders Inc", "ABBUILDERS"),
    ("Élan Construction", "ELAN"), ("3M Company", "3MX"), ("!!", "XXX"), ("A", "AXX"),
    ("Superlongcompanyname LLC", "SUPERLONGC"), ("Zed", "ZED"),
])
def test_code_suggested_from_the_name(name, code):
    suggested = companies.company_code_from_name(name)
    assert suggested == code
    assert 3 <= len(suggested) <= 10 and suggested == suggested.upper()


@pytest.mark.parametrize("code", ["AB", "ABCDEFGHIJK", "AB-1", "AB 1", "CON", "PRN", "AUX", "NUL", "COM1", "LPT9", ""])
def test_bad_codes_are_refused_before_anything_is_created(world, master, code):
    with pytest.raises(ValidationError):
        create(master, code=code)
    assert not os.path.exists(os.path.join(config.BASE_PROJECT_DIR, "Companies")) or not os.listdir(
        os.path.join(config.BASE_PROJECT_DIR, "Companies"))
    assert world.master_rows("SELECT * FROM company_registry WHERE company_code NOT IN ('PARENT','CHILD','OTHER')") == []


def test_lowercase_code_is_uppercased(world, master):
    created = create(master, code="acme1")
    assert created["company_code"] == "ACME1" and registry(world, "ACME1")


def test_code_must_be_unique_and_the_file_is_not_replaced(world, master):
    first = create(master, code="ACME")
    before = open(file_of(world, "ACME"), "rb").read()
    with pytest.raises(ValidationError):
        create(master, name="Other Co", code="ACME")
    assert open(file_of(world, "ACME"), "rb").read() == before
    assert len(world.master_rows("SELECT * FROM company_registry WHERE company_code = 'ACME'")) == 1
    assert first["company_id"]


def test_omitted_code_is_suggested_and_made_unique(world, master):
    one = create(master, name="Acme Builders")
    two = create(master, name="Acme Builders")
    assert one["company_code"] == "ACME" and two["company_code"] == "ACME2"


def test_code_cannot_change_once_set(world, master):
    created = create(master)
    with pytest.raises(sqlite3.IntegrityError):
        with world._master() as c:
            c.execute("UPDATE company_registry SET company_code = 'NEWCODE' WHERE company_id = ?",
                      (created["company_id"],))


# --- The new company (S5, A6, A7) -----------------------------------------------------------------

def test_construction_company_is_fully_built(world, master):
    created = create(master, name="Acme Builders", tax_id="12-3456789")
    path = file_of(world, "ACME")
    assert os.path.isfile(path)
    reg = registry(world, "ACME")
    assert (reg["legal_name"], reg["parent_company_id"], reg["is_archived"], reg["is_active"]) == (
        "Acme Builders", None, 0, 1)
    assert reg["database_file_path"].replace("\\", "/") == "Companies/ACME.db"
    s = rows_in(path, "SELECT * FROM company_settings WHERE id = 1")[0]
    assert (s["company_name"], s["base_currency"], s["country"], s["timezone"], s["date_format"]) == (
        "Acme Builders", "USD", "US", "America/Los_Angeles", "MM/DD/YYYY")
    assert (s["fiscal_year_start"], s["first_fiscal_year"], s["require_separate_approver"], s["tax_id"]) == (
        "01-01", 2027, 0, "12-3456789")
    assert rows_in(path, "SELECT COUNT(*) AS n FROM account")[0]["n"] == 88
    for role in chart_templates.REQUIRED_ROLES:
        assert s[chart_templates.settings_column(role)] is not None
    assert created["company_id"] == reg["company_id"]


def test_pointers_point_at_the_right_accounts(world, master):
    create(master)
    path = file_of(world, "ACME")
    row = rows_in(path, "SELECT a.code, a.name, a.control_type FROM company_settings s "
                        "JOIN account a ON a.account_id = s.ar_acct_id")[0]
    assert (row["code"], row["control_type"]) == ("1110", "AR")
    bank = rows_in(path, "SELECT a.code FROM company_settings s JOIN account a ON a.account_id = s.default_bank_acct_id")
    assert bank == [{"code": "1010"}]


def test_general_template_and_subtypes_and_contra_balances(world, master):
    create(master, template="general")
    path = file_of(world, "ACME")
    assert rows_in(path, "SELECT COUNT(*) AS n FROM account")[0]["n"] == 72
    contra = rows_in(path, "SELECT normal_balance, subtype FROM account WHERE code = '3020'")
    assert contra[0]["normal_balance"] == "D"
    assert rows_in(path, "SELECT COUNT(*) AS n FROM account WHERE subtype IS NULL")[0]["n"] == 0


def test_philippines_defaults(world, master):
    create(master, country="PH")
    s = rows_in(file_of(world, "ACME"), "SELECT * FROM company_settings WHERE id = 1")[0]
    assert (s["country"], s["base_currency"], s["timezone"]) == ("PH", "PHP", "Asia/Manila")


def test_explicit_timezone_date_format_and_fiscal_year(world, master):
    create(master, timezone="America/Chicago", date_format="YYYY-MM-DD", fiscal_year_start_month=7,
           first_fiscal_year=2028, require_separate_approver=True, display_name="Acme")
    s = rows_in(file_of(world, "ACME"), "SELECT * FROM company_settings WHERE id = 1")[0]
    assert (s["timezone"], s["date_format"], s["fiscal_year_start"], s["first_fiscal_year"]) == (
        "America/Chicago", "YYYY-MM-DD", "07-01", 2028)
    assert s["require_separate_approver"] == 1 and s["company_name"] == "Acme"


@pytest.mark.parametrize("kwargs", [
    {"legal_name": " "}, {"country": "FR"}, {"timezone": "Mars/Olympus"}, {"timezone": "Asia/Manila"},
    {"date_format": "DD-MM-YY"}, {"fiscal_year_start_month": 0}, {"fiscal_year_start_month": 13},
    {"first_fiscal_year": 1800}, {"first_fiscal_year": "2027"}, {"first_fiscal_year": None},
])
def test_bad_setup_values_create_nothing(world, master, kwargs):
    with pytest.raises(ValidationError):
        create(master, **kwargs)
    assert world.master_rows("SELECT * FROM company_registry WHERE company_code NOT IN ('PARENT','CHILD','OTHER')") == []


def test_unknown_template_is_not_found_and_creates_nothing(world, master):
    with pytest.raises(NotFoundError):
        create(master, template="nope")
    assert registry(world, "ACME") is None


def test_own_csv_chart(world, master):
    text = ("account_number,name,parent_number,account_type,subtype,normal_balance,control_type,is_postable,system_role\n"
            "1000,Assets,,Asset,x,D,,0,\n1010,Checking,1000,Asset,x,D,,1,default_bank\n1110,AR,1000,Asset,x,D,AR,1,ar\n"
            "2000,Liabilities,,Liability,x,C,,0,\n2010,AP,2000,Liability,x,C,AP,1,ap\n"
            "2200,Tax,2000,Liability,x,C,Sales tax payable,1,sales_tax_payable\n3000,Equity,,Equity,x,C,,0,\n"
            "3100,RE,3000,Equity,x,C,,1,retained_earnings\n3900,OBE,3000,Equity,x,C,,1,opening_balance_equity\n")
    create(master, template=None, chart_csv=text)
    assert rows_in(file_of(world, "ACME"), "SELECT COUNT(*) AS n FROM account")[0]["n"] == 9


def test_invalid_own_csv_reports_rows_and_creates_nothing(world, master):
    with pytest.raises(CsvError) as caught:
        create(master, template=None, chart_csv="account_number,name,account_type,normal_balance,is_postable\n"
                                              "12,Short,Asset,D,1\n")
    assert caught.value.errors
    assert registry(world, "ACME") is None and not os.path.exists(file_of(world, "ACME"))


def test_template_and_csv_are_mutually_exclusive(world, master):
    with pytest.raises(ValidationError):
        create(master, template="general", chart_csv="x")
    with pytest.raises(ValidationError):
        create(master, template=None)


def test_new_company_opens_through_the_normal_path_and_is_audited(world, master):
    created = create(master)
    context = companies.open_company(master, created["company_id"])
    assert context.company_db_path.lower() == file_of(world, "ACME").lower() or os.path.samefile(
        context.company_db_path, file_of(world, "ACME"))
    log = rows_in(file_of(world, "ACME"), "SELECT DISTINCT user_id FROM audit_log WHERE table_name IN "
                                          "('account', 'company_settings')")
    assert log == [{"user_id": master.user_id}]
    assert cs.missing_required_roles(context) == []


def test_starter_roles_are_seeded_from_the_approved_table(world, master):
    from modules.services import role_templates as rt
    create(master)
    path = file_of(world, "ACME")
    roles = {r["role_code"]: r["project_scope"] for r in rows_in(path, "SELECT role_code, project_scope FROM role")}
    assert set(roles) == {"Admin"} | set(rt.ROLES)
    assert roles["Project Manager"] == "Assigned" and roles["Controller"] == "All"
    for role in rt.ROLES:
        granted = {r["permission_code"] for r in rows_in(
            path, "SELECT permission_code FROM role_permission WHERE role_code = ?", (role,))}
        assert granted == rt.permissions_for(role), role
    assert rows_in(path, "SELECT COUNT(*) AS n FROM approval_limit") == [{"n": 0}]


def test_general_template_omits_the_construction_roles(world, master):
    create(master, template="general")
    roles = {r["role_code"] for r in rows_in(file_of(world, "ACME"), "SELECT role_code FROM role")}
    assert not roles & {"Project Manager", "General Manager", "Warehouse", "Foreman"}
    assert {"Controller", "Viewer", "Sales"} <= roles


# --- All or nothing --------------------------------------------------------------------------------

def _nothing_left(world):
    folder = os.path.join(config.BASE_PROJECT_DIR, "Companies")
    return (not os.path.exists(folder) or os.listdir(folder) == []) and registry(world, "ACME") is None


def test_failure_while_seeding_the_chart_leaves_nothing(world, master, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(accounts, "seed_chart", boom)
    with pytest.raises(RuntimeError):
        create(master)
    assert _nothing_left(world)


def test_failure_while_registering_leaves_nothing(world, master, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        create(master)
    assert _nothing_left(world)


def test_failure_after_the_rename_removes_the_file_and_the_registry_row(world, master, monkeypatch):
    original = companies._grant_admins

    def boom(*a, **k):
        raise RuntimeError("late failure")
    monkeypatch.setattr(companies, "_grant_admins", boom)
    with pytest.raises(RuntimeError):
        create(master)
    assert _nothing_left(world)
    monkeypatch.setattr(companies, "_grant_admins", original)
    create(master)                       # the same code works afterwards
    assert registry(world, "ACME")


# --- Who may create, and who becomes Admin (S8) ------------------------------------------------

def test_a_non_master_cannot_create_a_top_level_company(world):
    user = world.user("bob")
    with pytest.raises(PermissionDeniedError):
        create(world.session(user))
    assert world.master_rows("SELECT event_type FROM auth_event WHERE event_type = 'Denied'")
    assert registry(world, "ACME") is None


def test_master_can_name_a_user_to_become_admin(world, master):
    alice = world.user("alice")
    created = create(master, admin_user_id=alice)
    access = world.master_rows("SELECT user_id, role_code, access_mode FROM user_company_access WHERE company_id = ?",
                               (created["company_id"],))
    assert access == [{"user_id": alice, "role_code": "Admin", "access_mode": "Grant"}]


@pytest.mark.parametrize("bad", [9999, "x"])
def test_unknown_admin_user_is_refused_before_anything_is_created(world, master, bad):
    with pytest.raises(ValidationError):
        create(master, admin_user_id=bad)
    assert _nothing_left(world)


def test_inactive_admin_user_is_refused(world, master):
    ghost = world.user("ghost", active=False)
    with pytest.raises(ValidationError):
        create(master, admin_user_id=ghost)
    assert _nothing_left(world)


def _parent_with_admin(world, master):
    boss = world.user("boss")
    parent = create(master, name="Parent Holdings", code="PARENTCO", template="general", admin_user_id=boss)
    return boss, parent


def test_parent_admin_creates_a_subsidiary_and_becomes_its_admin(world, master):
    boss, parent = _parent_with_admin(world, master)
    child = create(world.session(boss), name="Child Works", parent_company_id=parent["company_id"])
    reg = registry(world, child["company_code"])
    assert reg["parent_company_id"] == parent["company_id"]
    access = world.master_rows("SELECT user_id, role_code FROM user_company_access WHERE company_id = ?",
                               (child["company_id"],))
    assert {"user_id": boss, "role_code": "Admin"} in access


def test_master_creating_a_subsidiary_needs_no_access_row(world, master):
    _, parent = _parent_with_admin(world, master)
    child = create(master, name="Child Works", parent_company_id=parent["company_id"])
    assert world.master_rows("SELECT * FROM user_company_access WHERE company_id = ?", (child["company_id"],)) == []


def test_user_without_company_create_cannot_make_a_subsidiary(world, master):
    _, parent = _parent_with_admin(world, master)
    path = file_of(world, "PARENTCO")
    add_role(path, "CLERK", ["ledger.view"])
    clerk = world.user("clerk")
    grant_access(world, clerk, parent["company_id"], "CLERK")
    with pytest.raises(PermissionDeniedError):
        create(world.session(clerk), name="Sneaky", parent_company_id=parent["company_id"])
    assert registry(world, "SNEAKY") is None


def test_user_with_no_access_to_the_parent_cannot_make_a_subsidiary(world, master):
    _, parent = _parent_with_admin(world, master)
    stranger = world.user("stranger")
    with pytest.raises(PermissionDeniedError):
        create(world.session(stranger), name="Sneaky", parent_company_id=parent["company_id"])
    assert registry(world, "SNEAKY") is None


def test_unknown_parent(world, master):
    with pytest.raises(NotFoundError):
        create(master, parent_company_id=9999)


# --- Subsidiaries copy the parent (S7) ---------------------------------------------------------------

def test_subsidiary_copies_chart_pointers_roles_policies_and_controls(world, master):
    parent = create(master, name="Parent Holdings", code="PARENTCO", template="general",
                    require_separate_approver=True)
    ppath = file_of(world, "PARENTCO")
    add_role(ppath, "BOOKKEEPER", ["ledger.view", "je.create"])
    conn = company_conn(ppath)
    conn.execute("UPDATE company_settings SET allow_manual_control_je = 0, manual_entry_approval = 1, "
                 "warn_past_days = 45, date_format = 'YYYY-MM-DD', timezone = 'America/Chicago' WHERE id = 1")
    conn.execute("UPDATE document_approval_setting SET requires_approval = 1 WHERE document_type = 'Bill'")
    conn.execute("INSERT INTO approval_policy (name, document_type, min_amount_cents) VALUES ('Big bills', 'Bill', 100000)")
    conn.execute("INSERT INTO approval_step (policy_id, step_no, role_code, required_count) VALUES (1, 1, 'BOOKKEEPER', 2)")
    conn.commit()
    conn.close()

    child = create(master, name="Child Works", parent_company_id=parent["company_id"], template=None)
    cpath = file_of(world, child["company_code"])
    assert rows_in(cpath, "SELECT code, name, control_type, normal_balance, is_postable FROM account ORDER BY code") == \
        rows_in(ppath, "SELECT code, name, control_type, normal_balance, is_postable FROM account ORDER BY code")
    s = rows_in(cpath, "SELECT * FROM company_settings WHERE id = 1")[0]
    assert (s["require_separate_approver"], s["allow_manual_control_je"], s["manual_entry_approval"],
            s["warn_past_days"], s["date_format"], s["timezone"]) == (1, 0, 1, 45, "YYYY-MM-DD", "America/Chicago")
    assert s["company_name"] == "Child Works" and s["tax_id"] is None
    assert rows_in(cpath, "SELECT a.code FROM company_settings s JOIN account a ON a.account_id = s.ar_acct_id") == \
        [{"code": "1110"}]
    assert {r["role_code"] for r in rows_in(cpath, "SELECT role_code FROM role")} ==         {r["role_code"] for r in rows_in(ppath, "SELECT role_code FROM role")}
    assert "BOOKKEEPER" in {r["role_code"] for r in rows_in(cpath, "SELECT role_code FROM role")}
    assert {r["permission_code"] for r in rows_in(
        cpath, "SELECT permission_code FROM role_permission WHERE role_code = 'BOOKKEEPER'")} == {"ledger.view", "je.create"}
    assert rows_in(cpath, "SELECT requires_approval FROM document_approval_setting WHERE document_type = 'Bill'") == \
        [{"requires_approval": 1}]
    policy = rows_in(cpath, "SELECT p.name, s.role_code, s.required_count FROM approval_policy p "
                            "JOIN approval_step s USING (policy_id)")
    assert policy == [{"name": "Big bills", "role_code": "BOOKKEEPER", "required_count": 2}]


def test_subsidiary_with_its_own_template_does_not_copy(world, master):
    parent = create(master, name="Parent Holdings", code="PARENTCO", template="general")
    child = create(master, name="Child Works", parent_company_id=parent["company_id"], template="construction")
    assert rows_in(file_of(world, child["company_code"]), "SELECT COUNT(*) AS n FROM account")[0]["n"] == 88


def test_subsidiary_without_template_or_csv_copies_by_default(world, master):
    parent = create(master, name="Parent Holdings", code="PARENTCO", template="general")
    child = companies.create_company(master, legal_name="Child Works", first_fiscal_year=2027,
                                     parent_company_id=parent["company_id"])
    assert rows_in(file_of(world, child["company_code"]), "SELECT COUNT(*) AS n FROM account")[0]["n"] == 72


# --- Archive, restore, export, list (S9) -----------------------------------------------------------

def test_archive_hides_the_company_and_restore_brings_it_back(world, master):
    created = create(master)
    alice = world.user("alice")
    grant_access(world, alice, created["company_id"], "Admin")
    companies.archive_company(master, created["company_id"], confirm_company_code="ACME")
    assert registry(world, "ACME")["is_archived"] == 1
    with pytest.raises(ValidationError) as caught:
        companies.open_company(world.session(alice), created["company_id"])
    assert "archived" in str(caught.value).lower()
    companies.open_company(master, created["company_id"])                # the Master still can
    assert created["company_id"] not in [c["company_id"] for c in companies.list_companies(world.session(alice))]
    assert created["company_id"] not in [c["company_id"] for c in companies.list_companies(master)]
    assert created["company_id"] in [c["company_id"] for c in companies.list_companies(master, include_archived=True)]
    companies.restore_company(master, created["company_id"], confirm_company_code="ACME")
    assert created["company_id"] in [c["company_id"] for c in companies.list_companies(world.session(alice))]
    companies.open_company(world.session(alice), created["company_id"])
    changes = world.master_rows("SELECT action, user_id FROM audit_log WHERE table_name = 'company_registry' "
                                "AND action = 'Update' AND record_id = ?", (created["company_id"],))
    assert len(changes) == 2 and all(c["user_id"] == master.user_id for c in changes)


def test_archive_restore_export_are_master_only(world, master):
    created = create(master)
    alice = world.user("alice")
    grant_access(world, alice, created["company_id"], "Admin")
    asession = world.session(alice)
    for call in (companies.archive_company, companies.restore_company):
        with pytest.raises(PermissionDeniedError):
            call(asession, created["company_id"], confirm_company_code="ACME")
    with pytest.raises(PermissionDeniedError):
        companies.export_company(asession, created["company_id"])
    assert registry(world, "ACME")["is_archived"] == 0


def test_archive_and_restore_unknown_company(world, master):
    for call in (companies.archive_company, companies.restore_company):
        with pytest.raises(NotFoundError):
            call(master, 9999, confirm_company_code="ACME")
    with pytest.raises(NotFoundError):
        companies.export_company(master, 9999)


@pytest.mark.parametrize("typed", [None, "", "acme", "ACME ", "ACM", "OTHER"])
def test_archive_and_restore_need_the_code_typed_exactly(world, master, typed):
    created = create(master)
    with pytest.raises(ValidationError):
        companies.archive_company(master, created["company_id"], confirm_company_code=typed)
    assert registry(world, "ACME")["is_archived"] == 0
    companies.archive_company(master, created["company_id"], confirm_company_code="ACME")
    with pytest.raises(ValidationError):
        companies.restore_company(master, created["company_id"], confirm_company_code=typed)
    assert registry(world, "ACME")["is_archived"] == 1


def test_export_makes_a_consistent_copy_and_logs_it(world, master):
    created = create(master)
    relative = companies.export_company(master, created["company_id"])
    assert relative.replace("\\", "/").startswith("Exports/ACME-") and relative.endswith(".db")
    copy = os.path.join(config.BASE_PROJECT_DIR, relative)
    assert os.path.isfile(copy)
    assert rows_in(copy, "SELECT company_name FROM company_settings WHERE id = 1") == [{"company_name": "Acme Builders"}]
    assert rows_in(copy, "PRAGMA integrity_check") == [{"integrity_check": "ok"}]
    events = world.master_rows("SELECT event_type, user_id FROM auth_event WHERE event_type = 'Company exported'")
    assert events == [{"event_type": "Company exported", "user_id": master.user_id}]


def test_list_companies_for_a_regular_user_shows_only_granted_companies(world, master):
    one = create(master, name="One Co")
    two = create(master, name="Two Co")
    alice = world.user("alice")
    grant_access(world, alice, one["company_id"], "Admin")
    listed = companies.list_companies(world.session(alice))
    assert [c["company_id"] for c in listed] == [one["company_id"]]
    assert {"company_code", "legal_name", "parent_company_id", "is_archived"} <= set(listed[0])
    assert two["company_id"] in [c["company_id"] for c in companies.list_companies(master)]


# --- Time zone data is required (H2; no silent fallback) ---------------------------------------------

def test_open_company_refuses_when_time_zone_data_is_missing(world, master, monkeypatch):
    import zoneinfo
    from modules.services.errors import InstallationError
    created = create(master)

    def missing(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)
    monkeypatch.setattr(zoneinfo, "ZoneInfo", missing)
    with pytest.raises(InstallationError) as caught:
        companies.open_company(master, created["company_id"])
    assert "reinstall" in str(caught.value).lower()


def test_open_company_gives_the_company_local_date(world, master):
    import dataclasses  # noqa: F401
    created = create(master, country="PH")
    context = companies.open_company(master, created["company_id"])
    from modules.services import clock
    assert context.today == clock.local_today(context.now, "Asia/Manila")


# --- Who may open the New Company screen (creation_options) ------------------------------------------

def test_master_may_create_top_level_and_under_any_active_company(world, master):
    one = create(master, name="One Co")
    two = create(master, name="Two Co")
    companies.archive_company(master, two["company_id"], confirm_company_code=two["company_code"])
    options = companies.creation_options(master)
    assert options["top_level"] is True
    offered = {p["company_id"] for p in options["parents"]}
    assert one["company_id"] in offered and two["company_id"] not in offered
    assert {"company_id", "company_code", "legal_name"} <= set(options["parents"][0])


def test_parent_admin_may_only_create_subsidiaries(world, master):
    boss = world.user("boss")
    parent = create(master, name="Parent Co", code="PARENTCO", admin_user_id=boss)
    child = create(master, name="Child Co", code="CHILDCO", parent_company_id=parent["company_id"])
    create(master, name="Other Co", code="OTHERCO")                       # boss has no access here
    options = companies.creation_options(world.session(boss))
    assert options["top_level"] is False
    assert sorted(p["company_id"] for p in options["parents"]) == sorted([parent["company_id"], child["company_id"]])


def test_user_without_company_create_gets_nothing(world, master):
    parent = create(master, name="Parent Co", code="PARENTCO")
    add_role(file_of(world, "PARENTCO"), "CLERK", ["ledger.view"])
    clerk = world.user("clerk")
    grant_access(world, clerk, parent["company_id"], "CLERK")
    assert companies.creation_options(world.session(clerk)) == {"top_level": False, "parents": []}
    assert companies.creation_options(world.session(world.user("stranger"))) == {"top_level": False, "parents": []}


def test_archived_company_is_not_offered_as_a_parent(world, master):
    boss = world.user("boss")
    parent = create(master, name="Parent Co", code="PARENTCO", admin_user_id=boss)
    companies.archive_company(master, parent["company_id"], confirm_company_code="PARENTCO")
    assert companies.creation_options(world.session(boss))["parents"] == []


def test_check_company_code_is_public_and_uppercases():
    assert companies.check_company_code("acme1") == "ACME1"
    with pytest.raises(ValidationError):
        companies.check_company_code("ab")
