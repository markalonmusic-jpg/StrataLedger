"""Closing and reopening periods and years (decisions L1, L2, L7 amended, B1, 0b amended)."""
import dataclasses
import sqlite3

import pytest

from modules.services import companies, company_settings as cs, periods
from modules.services.errors import PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)


@pytest.fixture
def master(world):
    return world.session(world.user("root", master=True))


@pytest.fixture
def ctx(world, master):
    created = companies.create_company(master, legal_name="Acme Builders", code="ACME", first_fiscal_year=2027,
                                       template="general")
    return dataclasses.replace(companies.open_company(master, created["company_id"]), today="2027-06-15")


def as_role(world, ctx, role, name):
    user = world.user(name)
    with world._master() as c:
        c.execute("INSERT INTO user_company_access (user_id, company_id, role_code) VALUES (?, ?, ?)",
                  (user, ctx.company_id, role))
    return dataclasses.replace(ctx, user_id=user)


def raw(ctx):
    conn = sqlite3.connect(ctx.company_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def q(ctx, sql, params=()):
    conn = raw(ctx)
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def pid(ctx, name):
    return q(ctx, "SELECT period_id FROM fiscal_period WHERE name = ?", (name,))[0]["period_id"]


def yid(ctx, name):
    return q(ctx, "SELECT year_id FROM fiscal_year WHERE name = ?", (name,))[0]["year_id"]


def is_closed(ctx, name):
    return q(ctx, "SELECT is_closed FROM fiscal_period WHERE name = ?", (name,))[0]["is_closed"]


def history(ctx):
    return q(ctx, "SELECT h.action, h.via, h.reason, h.user_id, p.name AS period, y.name AS year "
                  "FROM period_status_history h LEFT JOIN fiscal_period p ON p.period_id = h.period_id "
                  "LEFT JOIN fiscal_year y ON y.year_id = h.year_id ORDER BY h.history_id")


def close_months(ctx, *numbers, year="FY2027"):
    for n in numbers:
        periods.close_period(ctx, pid(ctx, f"{year}-{n:02d}"), acknowledge_warnings=True)


def draft_entry(ctx, entry_date, period_name):
    conn = raw(ctx)
    try:
        conn.execute("INSERT INTO journal_entry (entry_date, period_id, created_by) VALUES (?, ?, 1)",
                     (entry_date, pid(ctx, period_name)))
        conn.commit()
    finally:
        conn.close()


# --- Close checks (L2) ------------------------------------------------------------------------

def test_clean_first_period_closes_without_warnings_and_writes_history(ctx):
    checks = periods.close_checks(ctx, pid(ctx, "FY2027-01"))
    assert {c["code"]: c["ok"] for c in checks} == {"draft_entries": True, "earlier_period_open": True,
                                                    "pending_approvals": True}
    periods.close_period(ctx, pid(ctx, "FY2027-01"))
    row = q(ctx, "SELECT * FROM fiscal_period WHERE name = 'FY2027-01'")[0]
    assert row["is_closed"] == 1 and row["closed_by"] == ctx.user_id and row["closed_at"] == ctx.now
    assert history(ctx) == [{"action": "Close", "via": "Period close", "reason": None, "user_id": ctx.user_id,
                             "period": "FY2027-01", "year": "FY2027"}]


def test_out_of_order_close_is_a_warning(ctx):
    with pytest.raises(periods.CloseWarningsError) as caught:
        periods.close_period(ctx, pid(ctx, "FY2027-03"))
    assert [w["code"] for w in caught.value.warnings] == ["earlier_period_open"]
    assert is_closed(ctx, "FY2027-03") == 0
    periods.close_period(ctx, pid(ctx, "FY2027-03"), acknowledge_warnings=True)
    assert is_closed(ctx, "FY2027-03") == 1


def test_draft_entries_warn_and_can_be_made_a_block(ctx):
    draft_entry(ctx, "2027-01-10", "FY2027-01")
    with pytest.raises(periods.CloseWarningsError):
        periods.close_period(ctx, pid(ctx, "FY2027-01"))
    periods.set_close_check_mode(ctx, "draft_entries", "block")
    with pytest.raises(ValidationError) as caught:
        periods.close_period(ctx, pid(ctx, "FY2027-01"), acknowledge_warnings=True)
    assert not isinstance(caught.value, periods.CloseWarningsError) and "draft" in str(caught.value).lower()
    assert is_closed(ctx, "FY2027-01") == 0
    assert q(ctx, "SELECT mode FROM period_close_check WHERE check_code = 'draft_entries'") == [{"mode": "block"}]
    assert q(ctx, "SELECT COUNT(*) AS n FROM audit_log WHERE table_name = 'period_close_check'") == [{"n": 1}]


def test_pending_approval_check(ctx):
    draft_entry(ctx, "2027-01-10", "FY2027-01")
    entry = q(ctx, "SELECT entry_id FROM journal_entry")[0]["entry_id"]
    conn = raw(ctx)
    conn.execute("INSERT INTO approval_request (document_type, record_type, record_id, amount_cents, created_by, "
                 "chain_json, status, submitted_by, submitted_at) VALUES ('Journal entry', 'journal_entry', ?, 100, "
                 "1, '[]', 'Pending', 1, '2027-01-10T00:00:00+00:00')", (entry,))
    conn.commit()
    conn.close()
    checks = {c["code"]: c["ok"] for c in periods.close_checks(ctx, pid(ctx, "FY2027-01"))}
    assert checks["pending_approvals"] is False and checks["draft_entries"] is False


def test_close_check_mode_validation_and_permission(world, ctx):
    for code, mode in (("nope", "block"), ("draft_entries", "stop")):
        with pytest.raises(ValidationError):
            periods.set_close_check_mode(ctx, code, mode)
    accountant = as_role(world, ctx, "Accountant", "acc")
    with pytest.raises(PermissionDeniedError):
        periods.set_close_check_mode(accountant, "draft_entries", "block")


def test_closing_twice_is_refused(ctx):
    periods.close_period(ctx, pid(ctx, "FY2027-01"))
    with pytest.raises(ValidationError):
        periods.close_period(ctx, pid(ctx, "FY2027-01"))


# --- Reopen (L7, 0b amended) -------------------------------------------------------------------

def test_reopen_needs_confirm_and_a_reason(ctx):
    periods.close_period(ctx, pid(ctx, "FY2027-01"))
    for kwargs in ({"reason": "Fix", "confirm": False}, {"reason": "Fix"}, {"reason": "  ", "confirm": True},
                   {"reason": None, "confirm": True}):
        with pytest.raises((ValidationError, TypeError)):
            periods.reopen_period(ctx, pid(ctx, "FY2027-01"), **kwargs)
    assert is_closed(ctx, "FY2027-01") == 1
    periods.reopen_period(ctx, pid(ctx, "FY2027-01"), reason="Late invoice", confirm=True)
    assert is_closed(ctx, "FY2027-01") == 0
    assert history(ctx)[-1] == {"action": "Reopen", "via": "Period close", "reason": "Late invoice",
                                "user_id": ctx.user_id, "period": "FY2027-01", "year": "FY2027"}
    row = q(ctx, "SELECT closed_at, closed_by FROM fiscal_period WHERE name = 'FY2027-01'")[0]
    assert row == {"closed_at": None, "closed_by": None}


def test_reopen_an_open_period_is_refused(ctx):
    with pytest.raises(ValidationError):
        periods.reopen_period(ctx, pid(ctx, "FY2027-01"), reason="x", confirm=True)


def test_reopen_needs_period_reopen(world, ctx):
    periods.close_period(ctx, pid(ctx, "FY2027-01"))
    accountant = as_role(world, ctx, "Accountant", "acc")          # can close, cannot reopen
    with pytest.raises(PermissionDeniedError):
        periods.reopen_period(accountant, pid(ctx, "FY2027-01"), reason="x", confirm=True)
    controller = as_role(world, ctx, "Controller", "ctl")
    periods.reopen_period(controller, pid(ctx, "FY2027-01"), reason="x", confirm=True)


def test_close_needs_period_close(world, ctx):
    viewer = as_role(world, ctx, "Viewer", "v")
    with pytest.raises(PermissionDeniedError):
        periods.close_period(viewer, pid(ctx, "FY2027-01"))
    accountant = as_role(world, ctx, "Accountant", "acc")
    periods.close_period(accountant, pid(ctx, "FY2027-01"))
    agent = dataclasses.replace(ctx, origin="Agent")
    with pytest.raises(PermissionDeniedError):
        periods.close_period(agent, pid(ctx, "FY2027-02"))


# --- Books closed through (L1) ------------------------------------------------------------------

def test_moving_books_closed_through_forward_closes_whole_periods(ctx):
    result = periods.set_books_closed_through(ctx, "2027-03-15", acknowledge_warnings=True)
    assert result["closed"] == ["FY2027-01", "FY2027-02"]          # March is only half over
    assert [is_closed(ctx, f"FY2027-0{n}") for n in (1, 2, 3)] == [1, 1, 0]
    assert q(ctx, "SELECT books_closed_through FROM company_settings") == [{"books_closed_through": "2027-03-15"}]
    assert [h["via"] for h in history(ctx)] == ["Books closed through"] * 2


def test_forward_move_respects_blocking_checks(ctx):
    draft_entry(ctx, "2027-02-10", "FY2027-02")
    periods.set_close_check_mode(ctx, "draft_entries", "block")
    with pytest.raises(ValidationError):
        periods.set_books_closed_through(ctx, "2027-02-28", acknowledge_warnings=True)
    assert [is_closed(ctx, f"FY2027-0{n}") for n in (1, 2)] == [0, 0]          # all or nothing
    assert q(ctx, "SELECT books_closed_through FROM company_settings") == [{"books_closed_through": None}]


def test_backward_move_dry_run_changes_nothing(ctx):
    periods.set_books_closed_through(ctx, "2027-04-30", acknowledge_warnings=True)
    before = (history(ctx), q(ctx, "SELECT * FROM fiscal_period"), q(ctx, "SELECT * FROM company_settings"))
    preview = periods.set_books_closed_through(ctx, "2027-02-28", dry_run=True)
    assert preview["reopen"] == ["FY2027-03", "FY2027-04"] and preview["dry_run"] is True
    assert (history(ctx), q(ctx, "SELECT * FROM fiscal_period"), q(ctx, "SELECT * FROM company_settings")) == before


def test_backward_move_needs_confirm_reason_and_period_reopen(world, ctx):
    periods.set_books_closed_through(ctx, "2027-04-30", acknowledge_warnings=True)
    with pytest.raises(ValidationError):
        periods.set_books_closed_through(ctx, "2027-02-28", reason="Audit fix")            # no confirm
    with pytest.raises(ValidationError):
        periods.set_books_closed_through(ctx, "2027-02-28", reason=" ", confirm=True)      # blank reason
    accountant = as_role(world, ctx, "Accountant", "acc")
    with pytest.raises(PermissionDeniedError):
        periods.set_books_closed_through(accountant, "2027-02-28", reason="x", confirm=True)
    assert is_closed(ctx, "FY2027-04") == 1
    result = periods.set_books_closed_through(ctx, "2027-02-28", reason="Audit fix", confirm=True)
    assert result["reopened"] == ["FY2027-03", "FY2027-04"]
    assert [is_closed(ctx, f"FY2027-0{n}") for n in (1, 2, 3, 4)] == [1, 1, 0, 0]
    last = history(ctx)[-2:]
    assert all(h["action"] == "Reopen" and h["via"] == "Books closed through" and h["reason"] == "Audit fix"
               for h in last)


def test_reopening_a_period_moves_books_closed_through_back(ctx):
    periods.set_books_closed_through(ctx, "2027-03-31", acknowledge_warnings=True)
    periods.reopen_period(ctx, pid(ctx, "FY2027-02"), reason="Fix", confirm=True)
    assert q(ctx, "SELECT books_closed_through FROM company_settings") == [{"books_closed_through": "2027-01-31"}]


def test_books_closed_through_rejects_bad_dates(ctx):
    for bad in ("31/03/2027", "2027-02-30", ""):
        with pytest.raises(ValidationError):
            periods.set_books_closed_through(ctx, bad, acknowledge_warnings=True)


# --- Posting and adjustment periods (A1) ---------------------------------------------------------------

def _post_into(ctx, period_name, entry_date):
    from tests import ledger_helpers as lh
    conn = raw(ctx)
    try:
        account = q(ctx, "SELECT account_id FROM account WHERE is_postable = 1 LIMIT 2")
        entry = conn.execute("INSERT INTO journal_entry (entry_date, period_id, created_by) VALUES (?, ?, 1) "
                             "RETURNING entry_id", (entry_date, pid(ctx, period_name))).fetchone()[0]
        conn.execute("INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, ?, 100, 0)",
                     (entry, account[0]["account_id"]))
        conn.execute("INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, ?, 0, 100)",
                     (entry, account[1]["account_id"]))
        lh.post(conn, entry)
        conn.commit()
    finally:
        conn.close()


def test_audit_adjustment_posts_into_open_13_while_12_is_closed(ctx):
    close_months(ctx, *range(1, 13))
    _post_into(ctx, "FY2027-13", "2027-12-31")
    with pytest.raises(sqlite3.IntegrityError):
        _post_into(ctx, "FY2027-12", "2027-12-31")


# --- Year close (B1) ---------------------------------------------------------------------------------

def test_year_close_needs_months_1_to_12_closed(ctx):
    close_months(ctx, *range(1, 12))
    with pytest.raises(ValidationError) as caught:
        periods.close_year(ctx, yid(ctx, "FY2027"))
    assert "FY2027-12" in str(caught.value)


def test_year_close_closes_13_and_14_and_locks_the_year(ctx):
    close_months(ctx, *range(1, 13))
    periods.close_year(ctx, yid(ctx, "FY2027"))
    year = q(ctx, "SELECT * FROM fiscal_year WHERE name = 'FY2027'")[0]
    assert year["is_year_closed"] == 1 and year["closed_by"] == ctx.user_id
    assert is_closed(ctx, "FY2027-13") == 1 and is_closed(ctx, "FY2027-14") == 1
    last = history(ctx)[-3:]
    assert [(h["action"], h["via"], h["period"]) for h in last] == [
        ("Close", "Year close", "FY2027-13"), ("Close", "Year close", "FY2027-14"), ("Year close", "Year close", None)]
    assert q(ctx, "SELECT COUNT(*) AS n FROM journal_entry") == [{"n": 0}]          # no closing entries
    with pytest.raises(ValidationError):
        periods.close_year(ctx, yid(ctx, "FY2027"))


def test_year_close_creates_the_next_year_if_it_is_missing(ctx):
    close_months(ctx, *range(1, 13))
    close_months(ctx, *range(1, 13), year="FY2028")
    periods.close_year(ctx, yid(ctx, "FY2027"))
    periods.close_year(ctx, yid(ctx, "FY2028"))
    assert "FY2029" in [y["name"] for y in periods.list_years(ctx)]


def test_period_in_a_closed_year_cannot_be_reopened(ctx):
    close_months(ctx, *range(1, 13))
    periods.close_year(ctx, yid(ctx, "FY2027"))
    with pytest.raises(ValidationError) as caught:
        periods.reopen_period(ctx, pid(ctx, "FY2027-05"), reason="x", confirm=True)
    assert "reopen the year" in str(caught.value).lower()
    with pytest.raises(sqlite3.IntegrityError):                  # the database agrees
        conn = raw(ctx)
        try:
            conn.execute("UPDATE fiscal_period SET is_closed = 0, closed_at = NULL, closed_by = NULL "
                         "WHERE name = 'FY2027-05'")
        finally:
            conn.close()


def test_year_close_needs_period_close(world, ctx):
    close_months(ctx, *range(1, 13))
    viewer = as_role(world, ctx, "Viewer", "v")
    with pytest.raises(PermissionDeniedError):
        periods.close_year(viewer, yid(ctx, "FY2027"))


# --- Year reopen (L7 amended) ----------------------------------------------------------------------

@pytest.fixture
def closed_year(ctx):
    close_months(ctx, *range(1, 13))
    periods.close_year(ctx, yid(ctx, "FY2027"))
    return yid(ctx, "FY2027")


@pytest.mark.parametrize("name", ["fy2027", "FY2026", "FY2027 ", " FY2027", "", None, "2027"])
def test_reopen_year_refuses_a_wrong_or_missing_name(ctx, closed_year, name):
    with pytest.raises(ValidationError):
        periods.reopen_year(ctx, closed_year, reason="Auditor adjustment", confirm_year_name=name)
    assert q(ctx, "SELECT is_year_closed FROM fiscal_year WHERE year_id = ?", (closed_year,)) == [{"is_year_closed": 1}]


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_reopen_year_refuses_a_blank_reason(ctx, closed_year, reason):
    with pytest.raises(ValidationError):
        periods.reopen_year(ctx, closed_year, reason=reason, confirm_year_name="FY2027")


def test_reopen_year_with_the_exact_name(ctx, closed_year):
    periods.reopen_year(ctx, closed_year, reason="Auditor adjustment", confirm_year_name="FY2027")
    year = q(ctx, "SELECT * FROM fiscal_year WHERE year_id = ?", (closed_year,))[0]
    assert (year["is_year_closed"], year["closed_at"], year["closed_by"]) == (0, None, None)
    assert history(ctx)[-1] == {"action": "Year reopen", "via": "Year reopen", "reason": "Auditor adjustment",
                                "user_id": ctx.user_id, "period": None, "year": "FY2027"}
    assert is_closed(ctx, "FY2027-05") == 1                       # periods stay closed
    periods.reopen_period(ctx, pid(ctx, "FY2027-05"), reason="Fix", confirm=True)
    assert is_closed(ctx, "FY2027-05") == 0


def test_reopen_year_permissions(world, ctx, closed_year):
    accountant = as_role(world, ctx, "Accountant", "acc")
    with pytest.raises(PermissionDeniedError):
        periods.reopen_year(accountant, closed_year, reason="x", confirm_year_name="FY2027")
    controller = as_role(world, ctx, "Controller", "ctl")         # L7 amended: Controller may
    periods.reopen_year(controller, closed_year, reason="x", confirm_year_name="FY2027")


def test_reopen_year_of_an_open_year_is_refused(ctx):
    with pytest.raises(ValidationError):
        periods.reopen_year(ctx, yid(ctx, "FY2027"), reason="x", confirm_year_name="FY2027")


def test_history_cannot_be_edited(ctx):
    periods.close_period(ctx, pid(ctx, "FY2027-01"))
    conn = raw(ctx)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE period_status_history SET reason = 'x'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM period_status_history")
    finally:
        conn.close()
