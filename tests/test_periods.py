"""periods.py: fiscal years, periods 1-14, auto-creation and entry dates (decisions A1, S2, S3, S4, L6)."""
import dataclasses
import sqlite3
from datetime import date

import pytest

from modules.services import companies, company_settings as cs, periods
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)


@pytest.fixture
def master(world):
    return world.session(world.user("root", master=True))


def make_company(master, *, month=1, year=2027, code="ACME"):
    created = companies.create_company(master, legal_name="Acme Builders", code=code, first_fiscal_year=year,
                                       fiscal_year_start_month=month, template="general")
    return companies.open_company(master, created["company_id"])


def raw(ctx):
    conn = sqlite3.connect(ctx.company_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def years(ctx):
    conn = raw(ctx)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM fiscal_year ORDER BY start_date")]
    finally:
        conn.close()


def period_rows(ctx, year_name):
    conn = raw(ctx)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT p.* FROM fiscal_period p JOIN fiscal_year y ON y.year_id = p.fiscal_year_id "
            "WHERE y.name = ? ORDER BY p.period_number", (year_name,))]
    finally:
        conn.close()


# --- The calendar (pure) ---------------------------------------------------------------------

@pytest.mark.parametrize("month,fy,start,end", [
    (1, 2027, "2027-01-01", "2027-12-31"),
    (7, 2027, "2026-07-01", "2027-06-30"),       # S2: Jul 2026 - Jun 2027 is FY2027
    (3, 2028, "2027-03-01", "2028-02-29"),       # ends on a leap day
    (3, 2027, "2026-03-01", "2027-02-28"),
    (12, 2027, "2026-12-01", "2027-11-30"),
])
def test_fiscal_year_bounds_and_name(month, fy, start, end):
    bounds = periods.fiscal_year_bounds(month, fy)
    assert (bounds[0].isoformat(), bounds[1].isoformat()) == (start, end)
    assert periods.year_name(bounds[1]) == f"FY{fy}"


def test_month_periods_cover_the_year_without_gaps():
    start, end = periods.fiscal_year_bounds(7, 2028)
    months = periods.month_periods(start, end)
    assert len(months) == 12
    assert months[0] == (1, date(2027, 7, 1), date(2027, 7, 31))
    assert months[7] == (8, date(2028, 2, 1), date(2028, 2, 29))       # leap February
    assert months[-1][2] == end
    for (_, _, previous_end), (_, next_start, _) in zip(months, months[1:]):
        assert (next_start - previous_end).days == 1


# --- Seeding at company creation (S3, S4, A1) ------------------------------------------------------

def test_new_company_has_the_first_year_and_the_next(world, master):
    ctx = make_company(master, month=7, year=2027)
    found = years(ctx)
    assert [(y["name"], y["start_date"], y["end_date"], y["is_year_closed"]) for y in found] == [
        ("FY2027", "2026-07-01", "2027-06-30", 0), ("FY2028", "2027-07-01", "2028-06-30", 0)]
    rows = period_rows(ctx, "FY2027")
    assert [r["period_number"] for r in rows] == list(range(1, 15))
    assert (rows[0]["start_date"], rows[0]["end_date"], rows[0]["name"]) == ("2026-07-01", "2026-07-31", "FY2027-01")
    assert [r["is_adjustment_period"] for r in rows] == [0] * 12 + [1, 1]


def test_periods_13_and_14_are_dated_the_last_day_of_the_year(world, master):
    ctx = make_company(master, month=7, year=2027)
    p13, p14 = period_rows(ctx, "FY2027")[12:]
    assert (p13["start_date"], p13["end_date"]) == ("2027-06-30", "2027-06-30")
    assert (p14["start_date"], p14["end_date"]) == ("2027-06-30", "2027-06-30")
    assert p13["name"] == "FY2027-13" and p14["name"] == "FY2027-14"


def test_leap_february_period(world, master):
    ctx = make_company(master, month=1, year=2028)
    feb = period_rows(ctx, "FY2028")[1]
    assert (feb["start_date"], feb["end_date"]) == ("2028-02-01", "2028-02-29")


def test_adjustment_period_must_be_dated_the_year_end(world, master):
    ctx = make_company(master)
    conn = raw(ctx)
    try:
        year_id = conn.execute("SELECT year_id FROM fiscal_year WHERE name = 'FY2027'").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO fiscal_period (name, start_date, end_date, fiscal_year_id, period_number, "
                         "is_adjustment_period) VALUES ('X', '2027-06-30', '2027-06-30', ?, 13, 1)", (year_id,))
        with pytest.raises(sqlite3.IntegrityError):              # 13 must be flagged as an adjustment period
            conn.execute("INSERT INTO fiscal_period (name, start_date, end_date, fiscal_year_id, period_number) "
                         "VALUES ('Y', '2027-12-31', '2027-12-31', ?, 13)", (year_id,))
    finally:
        conn.close()


# --- Visibility (S4) ------------------------------------------------------------------------------

def test_periods_13_and_14_are_hidden_unless_the_control_is_on(world, master):
    ctx = make_company(master)
    shown = [p["period_number"] for p in periods.list_periods(ctx) if p["year_name"] == "FY2027"]
    assert shown == list(range(1, 13))
    cs.update_setting(ctx, "adjustment_periods_enabled", True)
    shown = [p["period_number"] for p in periods.list_periods(ctx) if p["year_name"] == "FY2027"]
    assert shown == list(range(1, 15))
    everything = periods.list_periods(ctx, include_adjustment=True)
    assert len(everything) == 28


def test_list_years(world, master):
    ctx = make_company(master)
    assert [y["name"] for y in periods.list_years(ctx)] == ["FY2027", "FY2028"]


# --- Auto-create 60 days ahead (S3) ---------------------------------------------------------------

def test_next_year_is_created_exactly_60_days_before_it_starts(world, master):
    ctx = make_company(master, month=1, year=2027)                   # FY2027 and FY2028 exist
    early = dataclasses.replace(ctx, today="2028-11-01")             # FY2029 starts 2029-01-01: 61 days away
    assert periods.ensure_upcoming_years(early) == []
    assert [y["name"] for y in years(ctx)] == ["FY2027", "FY2028"]
    due = dataclasses.replace(ctx, today="2028-11-02")               # exactly 60 days before
    assert periods.ensure_upcoming_years(due) == ["FY2029"]
    assert [y["name"] for y in years(ctx)][-1] == "FY2029"
    assert periods.ensure_upcoming_years(due) == []                  # idempotent


def test_several_missing_years_are_created_in_order(world, master):
    ctx = make_company(master, month=7, year=2027)
    late = dataclasses.replace(ctx, today="2031-01-15")
    # FY2031 is Jul 2030 - Jun 2031; FY2032 starts 2031-07-01, 167 days away, so it is not due yet.
    assert periods.ensure_upcoming_years(late) == ["FY2029", "FY2030", "FY2031"]
    assert len(period_rows(ctx, "FY2031")) == 14


def test_open_company_creates_due_years(world, master, monkeypatch):
    created = companies.create_company(master, legal_name="Old Co", code="OLDCO", first_fiscal_year=2020,
                                       template="general")
    ctx = companies.open_company(master, created["company_id"])       # today is 2026 or later: years were added
    names = [y["name"] for y in years(ctx)]
    assert names[0] == "FY2020" and len(names) >= 7 and names == sorted(names)


# --- Which period an entry belongs to (A1; approved answer 1) -----------------------------------

def test_ordinary_year_end_entry_lands_in_period_12(world, master):
    ctx = make_company(master)
    conn = raw(ctx)
    try:
        period = periods.resolve_entry_period(conn, "2027-12-31")
        number = conn.execute("SELECT period_number FROM fiscal_period WHERE period_id = ?", (period,)).fetchone()[0]
    finally:
        conn.close()
    assert number == 12


def _period_id(ctx, name):
    conn = raw(ctx)
    try:
        return conn.execute("SELECT period_id FROM fiscal_period WHERE name = ?", (name,)).fetchone()[0]
    finally:
        conn.close()


def test_explicit_period_13_needs_the_control_and_the_year_end_date(world, master):
    ctx = make_company(master)
    p13 = _period_id(ctx, "FY2027-13")
    conn = raw(ctx)
    try:
        with pytest.raises(ValidationError):                         # control off
            periods.resolve_entry_period(conn, "2027-12-31", p13)
    finally:
        conn.close()
    cs.update_setting(ctx, "adjustment_periods_enabled", True)
    conn = raw(ctx)
    try:
        assert periods.resolve_entry_period(conn, "2027-12-31", p13) == p13
        with pytest.raises(ValidationError):                         # another date
            periods.resolve_entry_period(conn, "2027-12-30", p13)
        with pytest.raises(ValidationError):                         # an ordinary period that does not hold the date
            periods.resolve_entry_period(conn, "2027-12-31", _period_id(ctx, "FY2027-01"))
        assert periods.resolve_entry_period(conn, "2027-01-15", _period_id(ctx, "FY2027-01")) == \
            _period_id(ctx, "FY2027-01")
        with pytest.raises(NotFoundError):
            periods.resolve_entry_period(conn, "2040-01-01")
    finally:
        conn.close()


def test_report_basis_periods(world, master):
    ctx = make_company(master)
    conn = raw(ctx)
    try:
        year_id = conn.execute("SELECT year_id FROM fiscal_year WHERE name = 'FY2027'").fetchone()[0]
        numbers = {}
        for basis in ("pre_adjustment", "gaap", "tax"):
            ids = periods.period_ids_for_basis(conn, year_id, basis)
            numbers[basis] = sorted(r[0] for r in conn.execute(
                f"SELECT period_number FROM fiscal_period WHERE period_id IN ({','.join('?' * len(ids))})",
                ids))
        with pytest.raises(ValidationError):
            periods.period_ids_for_basis(conn, year_id, "made_up")
    finally:
        conn.close()
    assert numbers["pre_adjustment"] == list(range(1, 13))
    assert numbers["gaap"] == list(range(1, 14))
    assert numbers["tax"] == list(range(1, 15))


def test_entry_in_period_13_is_excluded_before_adjustments(world, master):
    from tests import ledger_helpers as lh
    ctx = make_company(master)
    cs.update_setting(ctx, "adjustment_periods_enabled", True)
    p13 = _period_id(ctx, "FY2027-13")
    conn = raw(ctx)
    try:
        entry = conn.execute("INSERT INTO journal_entry (entry_date, period_id, created_by) VALUES "
                             "('2027-12-31', ?, 1) RETURNING entry_id", (p13,)).fetchone()[0]
        year_id = conn.execute("SELECT year_id FROM fiscal_year WHERE name = 'FY2027'").fetchone()[0]
        pre = periods.period_ids_for_basis(conn, year_id, "pre_adjustment")
        gaap = periods.period_ids_for_basis(conn, year_id, "gaap")
        conn.commit()
    finally:
        conn.close()
    assert p13 not in pre and p13 in gaap and entry


# --- Date warnings (L6) ---------------------------------------------------------------------------------

def test_date_warnings_never_block(world, master):
    ctx = dataclasses.replace(make_company(master), today="2027-06-15")
    assert periods.check_entry_date(ctx, "2027-06-20") == []
    future = periods.check_entry_date(ctx, "2027-07-16")              # 31 days ahead (default 30)
    assert [w["code"] for w in future] == ["future"]
    past = periods.check_entry_date(ctx, "2027-03-16")                # 91 days back (default 90)
    assert [w["code"] for w in past] == ["past"]
    assert periods.check_entry_date(ctx, "2027-07-15") == [] and periods.check_entry_date(ctx, "2027-03-17") == []
    assert [w["code"] for w in periods.check_entry_date(ctx, "2035-01-01")] == ["future", "no_period"]
    cs.update_setting(ctx, "warn_future_days", 0)
    assert [w["code"] for w in periods.check_entry_date(ctx, "2027-06-16")] == ["future"]


def test_date_in_a_closed_period_is_an_error_not_a_warning(world, master):
    ctx = dataclasses.replace(make_company(master), today="2027-06-15")
    periods.close_period(ctx, _period_id(ctx, "FY2027-01"), acknowledge_warnings=True)
    with pytest.raises(ValidationError):
        periods.check_entry_date(ctx, "2027-01-10")
    with pytest.raises(ValidationError):
        periods.check_entry_date(ctx, "not a date")


# --- Changing the fiscal year start (answer 3) ---------------------------------------------------------

def test_start_month_can_change_while_there_are_no_entries(world, master):
    ctx = make_company(master, month=1, year=2027)
    periods.change_fiscal_year_start(ctx, 7)
    assert [(y["name"], y["start_date"]) for y in years(ctx)] == [("FY2027", "2026-07-01"), ("FY2028", "2027-07-01")]
    assert len(period_rows(ctx, "FY2027")) == 14
    conn = raw(ctx)
    try:
        assert conn.execute("SELECT fiscal_year_start FROM company_settings").fetchone()[0] == "07-01"
    finally:
        conn.close()


def test_start_month_change_refused_once_there_are_entries(world, master):
    ctx = make_company(master)
    conn = raw(ctx)
    conn.execute("INSERT INTO journal_entry (entry_date, period_id, created_by) VALUES ('2027-03-01', ?, 1)",
                 (_period_id(ctx, "FY2027-03"),))
    conn.commit()
    conn.close()
    with pytest.raises(ValidationError):
        periods.change_fiscal_year_start(ctx, 7)
    assert years(ctx)[0]["start_date"] == "2027-01-01"


def test_start_month_change_needs_company_settings_and_a_valid_month(world, master):
    ctx = make_company(master)
    for bad in (0, 13, "7"):
        with pytest.raises(ValidationError):
            periods.change_fiscal_year_start(ctx, bad)
    viewer = world.user("viewer")
    with world._master() as c:
        c.execute("INSERT INTO user_company_access (user_id, company_id, role_code) VALUES (?, ?, 'Viewer')",
                  (viewer, ctx.company_id))
    with pytest.raises(PermissionDeniedError):
        periods.change_fiscal_year_start(dataclasses.replace(ctx, user_id=viewer), 7)


def test_reads_need_period_view(world, master):
    ctx = make_company(master)
    nobody = world.user("nobody")
    with world._master() as c:
        c.execute("INSERT INTO user_company_access (user_id, company_id, role_code) VALUES (?, ?, 'AP Clerk')",
                  (nobody, ctx.company_id))
    other = dataclasses.replace(ctx, user_id=nobody)
    for call in (lambda: periods.list_periods(other), lambda: periods.list_years(other),
                 lambda: periods.check_entry_date(other, "2027-01-01")):
        with pytest.raises(PermissionDeniedError):
            call()
