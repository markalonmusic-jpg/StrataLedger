"""Fiscal years and periods: creation, entry periods, close and reopen (decisions A1, S2-S4, L1, L2, L6, L7, B1, 0b).

* A fiscal year is named by the calendar year it ends in (FY2027 = Jul 2026 - Jun 2027 for a July start). It has
  12 monthly periods plus period 13 (audit adjustments) and 14 (tax adjustments), both dated its last day.
  Periods 13 and 14 are hidden unless the company turns on the Adjustment periods control.
* A new company gets its first year and the next; later years are created 60 days before they start
  (ensure_upcoming_years, run when a company is opened).
* Closing runs the close checks: each is a warning by default and can be made a block (L2). Warnings must be
  acknowledged. Closing never posts entries; retained earnings is calculated in reports (B1).
* Reopening needs `period.reopen`, an explicit confirm and a reason. A period in a closed year cannot be
  reopened until the year is reopened, which needs `year.reopen`, a reason and the year's name typed exactly.
* Every close and reopen writes period_status_history (append-only). Date arithmetic is done here in Python and
  passed to SQL as values (H5).
"""
import re
import sqlite3
from datetime import date, timedelta

from modules.services.authz import authorize
from modules.services.errors import NotFoundError, ValidationError
from modules.services.tx import read_connection, write_transaction

CHECK_CODES = ("draft_entries", "earlier_period_open", "pending_approvals")
CHECK_MODES = ("warn", "block")
BASES = {"pre_adjustment": 12, "gaap": 13, "tax": 14}
CREATE_AHEAD_DAYS = 60
_ISO_DATE = re.compile(r"\d{4}-\d\d-\d\d")


class CloseWarningsError(ValidationError):
    """Closing would go ahead past one or more warnings; call again with acknowledge_warnings=True.

    `warnings` lists the failing warning checks: [{'code', 'message', 'period'}].
    """

    def __init__(self, message, warnings):
        super().__init__(message)
        self.warnings = warnings


# --- The calendar (pure) --------------------------------------------------------------------------

def fiscal_year_bounds(start_month, fiscal_year):
    """(first day, last day) of the fiscal year named FY<fiscal_year> for a year starting in start_month."""
    if start_month == 1:
        return date(fiscal_year, 1, 1), date(fiscal_year, 12, 31)
    return date(fiscal_year - 1, start_month, 1), date(fiscal_year, start_month, 1) - timedelta(days=1)


def year_name(end_date):
    return f"FY{end_date.year}"


def month_periods(start, end):
    """[(number, first day, last day)] for the 12 months from start to end."""
    months, cursor, number = [], start, 1
    while cursor <= end:
        following = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        months.append((number, cursor, following - timedelta(days=1)))
        cursor, number = following, number + 1
    return months


def _parse_date(value, what="date"):
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ValidationError(f"Enter the {what} as YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{value} is not a real date") from None


def _clean_reason(reason):
    text = reason.strip() if isinstance(reason, str) else ""
    if not text:
        raise ValidationError("Give a reason; it is kept in the period history")
    return text


def _require_confirm(confirm):
    if confirm is not True:
        raise ValidationError("Confirm this change first; it can change reports that were already run")


# --- Creating years (inside a caller's transaction) -----------------------------------------------

def _create_year(conn, start_month, fiscal_year):
    start, end = fiscal_year_bounds(start_month, fiscal_year)
    name = year_name(end)
    year_id = conn.execute("INSERT INTO fiscal_year (name, start_date, end_date) VALUES (?, ?, ?) RETURNING year_id",
                           (name, start.isoformat(), end.isoformat())).fetchone()[0]
    for number, first, last in month_periods(start, end):
        conn.execute("INSERT INTO fiscal_period (name, start_date, end_date, fiscal_year_id, period_number) "
                     "VALUES (?, ?, ?, ?, ?)", (f"{name}-{number:02d}", first.isoformat(), last.isoformat(),
                                                year_id, number))
    for number in (13, 14):
        conn.execute("INSERT INTO fiscal_period (name, start_date, end_date, fiscal_year_id, period_number, "
                     "is_adjustment_period) VALUES (?, ?, ?, ?, ?, 1)",
                     (f"{name}-{number}", end.isoformat(), end.isoformat(), year_id, number))
    return name


def seed_years(conn, start_month, first_year, count=2):
    """The first fiscal year to record and the following one (S3). Returns their names."""
    return [_create_year(conn, start_month, first_year + n) for n in range(count)]


def _start_month(conn):
    row = conn.execute("SELECT fiscal_year_start FROM company_settings WHERE id = 1").fetchone()
    return int(row["fiscal_year_start"][:2]) if row and row["fiscal_year_start"] else 1


def _years_due(conn, today):
    """Names of the years that should exist by `today` but do not yet (created in order)."""
    last = conn.execute("SELECT name, end_date FROM fiscal_year ORDER BY end_date DESC LIMIT 1").fetchone()
    if last is None:
        return []
    month, number, due = _start_month(conn), int(last["name"][2:]), []
    next_start = date.fromisoformat(last["end_date"]) + timedelta(days=1)
    while (next_start - today).days <= CREATE_AHEAD_DAYS:
        number += 1
        due.append(number)
        next_start = fiscal_year_bounds(month, number)[1] + timedelta(days=1)
    return [(month, n) for n in due]


def ensure_upcoming_years(context):
    """Create every fiscal year that starts within 60 days of context.today (S3). Returns the new names.

    Run by open_company. Excluded from the rule-10 static test by name: it is system upkeep, not a user action,
    and it runs as the user who opened the company so the audit log shows who triggered it.
    """
    today = date.fromisoformat(context.today)
    conn = read_connection(context.company_db_path)
    try:
        due = _years_due(conn, today)
    finally:
        conn.close()
    if not due:
        return []
    with write_transaction(context.company_db_path, context) as conn:
        return [_create_year(conn, month, number) for month, number in _years_due(conn, today)]


# --- Reads ------------------------------------------------------------------------------------------

def _settings(conn):
    return conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()


def list_years(context):
    authorize(context, "period.view", record_type="fiscal_year")
    conn = read_connection(context.company_db_path)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM fiscal_year ORDER BY start_date")]
    finally:
        conn.close()


def list_periods(context, year_id=None, include_adjustment=None):
    """Periods in date order. 13 and 14 appear only when the Adjustment periods control is on (S4), unless asked."""
    authorize(context, "period.view", record_type="fiscal_period")
    conn = read_connection(context.company_db_path)
    try:
        if include_adjustment is None:
            settings = _settings(conn)
            include_adjustment = bool(settings and settings["adjustment_periods_enabled"])
        sql = ("SELECT p.period_id, p.name, p.fiscal_year_id AS year_id, y.name AS year_name, p.period_number, "
               "p.start_date, p.end_date, p.is_closed, p.is_adjustment_period FROM fiscal_period AS p "
               "LEFT JOIN fiscal_year AS y ON y.year_id = p.fiscal_year_id WHERE 1 = 1")
        params = []
        if year_id is not None:
            sql += " AND p.fiscal_year_id = ?"
            params.append(year_id)
        if not include_adjustment:
            sql += " AND p.is_adjustment_period = 0"
        sql += " ORDER BY p.start_date, p.is_adjustment_period, p.period_number"
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def resolve_entry_period(conn, entry_date, period_id=None):
    """The period an entry belongs to (A1). Inside the caller's transaction.

    Without period_id: the month period that holds entry_date (on the year's last day, that is period 12).
    With period_id: an ordinary period must hold the date; period 13 or 14 is accepted only when the date is the
    year's last day and the Adjustment periods control is on.
    """
    day = _parse_date(entry_date, "entry date").isoformat()
    if period_id is None:
        row = conn.execute("SELECT period_id FROM fiscal_period WHERE is_adjustment_period = 0 "
                           "AND ? BETWEEN start_date AND end_date", (day,)).fetchone()
        if row is None:
            raise NotFoundError(f"There is no fiscal period for {day}")
        return row[0]
    period = conn.execute("SELECT * FROM fiscal_period WHERE period_id = ?", (period_id,)).fetchone()
    if period is None:
        raise NotFoundError("That fiscal period does not exist")
    if period["is_adjustment_period"]:
        settings = _settings(conn)
        if not (settings and settings["adjustment_periods_enabled"]):
            raise ValidationError("Adjustment periods are turned off for this company (Settings > Controls)")
        if day != period["start_date"]:
            raise ValidationError(f"An entry in {period['name']} must be dated {period['start_date']}, "
                                  "the last day of the fiscal year")
        return period_id
    if not period["start_date"] <= day <= period["end_date"]:
        raise ValidationError(f"{day} is not in {period['name']}")
    return period_id


def period_ids_for_basis(conn, year_id, basis):
    """Period ids of a year for a report basis: pre_adjustment (1-12), gaap (1-13), tax (1-14) (A1)."""
    if basis not in BASES:
        raise ValidationError("Choose the pre-adjustment, GAAP/audited or tax basis")
    return [r[0] for r in conn.execute(
        "SELECT period_id FROM fiscal_period WHERE fiscal_year_id = ? AND period_number <= ? ORDER BY period_number",
        (year_id, BASES[basis]))]


def check_entry_date(context, entry_date):
    """Warnings for an entry date (L6): far in the future or past, or no period yet. Never blocks.

    A date in a closed period is an error (ValidationError), not a warning.
    """
    authorize(context, "period.view", record_type="fiscal_period")
    day = _parse_date(entry_date, "entry date")
    today = date.fromisoformat(context.today)
    conn = read_connection(context.company_db_path)
    try:
        settings = _settings(conn)
        period = conn.execute("SELECT name, is_closed FROM fiscal_period WHERE is_adjustment_period = 0 "
                              "AND ? BETWEEN start_date AND end_date", (day.isoformat(),)).fetchone()
    finally:
        conn.close()
    if period is not None and period["is_closed"]:
        raise ValidationError(f"{period['name']} is closed; choose a date in an open period")
    future_days = settings["warn_future_days"] if settings else 30
    past_days = settings["warn_past_days"] if settings else 90
    warnings = []
    if (day - today).days > future_days:
        warnings.append({"code": "future", "message": f"This date is more than {future_days} days ahead. Is it right?"})
    if (today - day).days > past_days:
        warnings.append({"code": "past", "message": f"This date is more than {past_days} days ago. Is it right?"})
    if period is None:
        warnings.append({"code": "no_period", "message": "There is no fiscal period for this date yet."})
    return warnings


# --- Close checks (L2) ------------------------------------------------------------------------------

def _period(conn, period_id):
    row = conn.execute("SELECT p.*, y.name AS year_name, y.is_year_closed FROM fiscal_period AS p "
                       "LEFT JOIN fiscal_year AS y ON y.year_id = p.fiscal_year_id WHERE p.period_id = ?",
                       (period_id,)).fetchone()
    if row is None:
        raise NotFoundError("That fiscal period does not exist")
    return row


def _sort_key(row):
    return (row["start_date"], row["is_adjustment_period"], row["period_number"] or 0)


def _run_checks(conn, period):
    modes = {r["check_code"]: r["mode"] for r in conn.execute("SELECT check_code, mode FROM period_close_check")}
    drafts = conn.execute("SELECT COUNT(*) FROM journal_entry WHERE period_id = ? AND is_posted = 0 AND is_void = 0",
                          (period["period_id"],)).fetchone()[0]
    earlier = [r["name"] for r in conn.execute(
        "SELECT name, start_date, is_adjustment_period, period_number FROM fiscal_period WHERE is_closed = 0 "
        "AND period_id <> ?", (period["period_id"],)) if _sort_key(r) < _sort_key(period)]
    pending = conn.execute(
        "SELECT COUNT(*) FROM approval_request AS r JOIN journal_entry AS e "
        "ON r.record_type = 'journal_entry' AND r.record_id = e.entry_id "
        "WHERE r.status = 'Pending' AND e.period_id = ?", (period["period_id"],)).fetchone()[0]
    results = [
        ("draft_entries", drafts == 0, f"{drafts} draft entr{'y is' if drafts == 1 else 'ies are'} dated in this period"),
        ("earlier_period_open", not earlier, "Earlier periods are still open: " + ", ".join(sorted(earlier))),
        ("pending_approvals", pending == 0, f"{pending} entr{'y is' if pending == 1 else 'ies are'} waiting for approval"),
    ]
    return [{"code": code, "mode": modes.get(code, "warn"), "ok": ok, "message": None if ok else message,
             "period": period["name"]} for code, ok, message in results]


def close_checks(context, period_id):
    """The close checks for a period, without closing it: [{'code', 'mode', 'ok', 'message', 'period'}]."""
    authorize(context, "period.view", record_type="fiscal_period", record_id=period_id)
    conn = read_connection(context.company_db_path)
    try:
        return _run_checks(conn, _period(conn, period_id))
    finally:
        conn.close()


def _judge(results, acknowledge_warnings):
    blocks = [r for r in results if not r["ok"] and r["mode"] == "block"]
    if blocks:
        raise ValidationError("This cannot close yet: " + "; ".join(f"{r['period']}: {r['message']}" for r in blocks))
    warnings = [r for r in results if not r["ok"]]
    if warnings and not acknowledge_warnings:
        raise CloseWarningsError("Review these warnings before closing: " + "; ".join(
            f"{r['period']}: {r['message']}" for r in warnings), warnings)


def _history(conn, context, *, period_id=None, year_id=None, action, via, reason=None):
    conn.execute("INSERT INTO period_status_history (period_id, year_id, action, via, reason, user_id, acted_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)", (period_id, year_id, action, via, reason, context.user_id, context.now))


def _close(conn, context, period, via):
    conn.execute("UPDATE fiscal_period SET is_closed = 1, closed_at = ?, closed_by = ? WHERE period_id = ?",
                 (context.now, context.user_id, period["period_id"]))
    _history(conn, context, period_id=period["period_id"], year_id=period["fiscal_year_id"], action="Close", via=via)


def _reopen(conn, context, period, via, reason):
    if period["is_year_closed"]:
        raise ValidationError(f"{period['year_name']} is closed; reopen the year first")
    conn.execute("UPDATE fiscal_period SET is_closed = 0, closed_at = NULL, closed_by = NULL WHERE period_id = ?",
                 (period["period_id"],))
    _history(conn, context, period_id=period["period_id"], year_id=period["fiscal_year_id"], action="Reopen",
             via=via, reason=reason)


# --- Close and reopen a period ------------------------------------------------------------------------

def close_period(context, period_id, *, acknowledge_warnings=False):
    """Close one period after its checks (L2). Warnings need acknowledge_warnings=True; blocks always stop it."""
    authorize(context, "period.close", record_type="fiscal_period", record_id=period_id)
    with write_transaction(context.company_db_path, context) as conn:
        period = _period(conn, period_id)
        if period["is_closed"]:
            raise ValidationError(f"{period['name']} is already closed")
        _judge(_run_checks(conn, period), acknowledge_warnings)
        _close(conn, context, period, "Period close")


def reopen_period(context, period_id, *, reason=None, confirm=False):
    """Reopen a closed period (L7): needs period.reopen, confirm=True and a reason. Logged in the history."""
    authorize(context, "period.reopen", record_type="fiscal_period", record_id=period_id)
    _require_confirm(confirm)
    reason = _clean_reason(reason)
    with write_transaction(context.company_db_path, context) as conn:
        period = _period(conn, period_id)
        if not period["is_closed"]:
            raise ValidationError(f"{period['name']} is not closed")
        _reopen(conn, context, period, "Period close", reason)
        settings = _settings(conn)
        through = settings["books_closed_through"] if settings else None
        if not period["is_adjustment_period"] and through is not None and through >= period["start_date"]:
            moved = date.fromisoformat(period["start_date"]) - timedelta(days=1)
            conn.execute("UPDATE company_settings SET books_closed_through = ? WHERE id = 1", (moved.isoformat(),))


# --- Books closed through (L1) ---------------------------------------------------------------------------

def set_books_closed_through(context, through_date, *, reason=None, confirm=False, dry_run=False,
                             acknowledge_warnings=False):
    """Lock every month that ends on or before through_date, or move the date back (which reopens months).

    Forward needs period.close and runs each month's close checks. Backward needs period.reopen, confirm=True and
    a reason; dry_run=True returns the months it would reopen (or close) and changes nothing.
    """
    new = _parse_date(through_date, "date").isoformat()
    conn = read_connection(context.company_db_path)
    try:
        settings = _settings(conn)
        if settings is None:
            raise NotFoundError("This company has no settings yet")
        old = settings["books_closed_through"]
    finally:
        conn.close()
    forward = old is None or new > old
    authorize(context, "period.close" if forward else "period.reopen", record_type="company_settings")
    if old == new:
        return {"dry_run": dry_run, "closed": [], "reopened": []}
    if forward and dry_run:
        return _forward_preview(context, new)
    if forward:
        with write_transaction(context.company_db_path, context) as conn:
            names, results = [], []
            for row in _open_through(conn, new):
                period = _period(conn, row["period_id"])
                # The months close in order in this one transaction, so an earlier month is never left open.
                results += [r for r in _run_checks(conn, period) if r["code"] != "earlier_period_open"]
                _close(conn, context, period, "Books closed through")
                names.append(row["name"])
            _judge(results, acknowledge_warnings)
            conn.execute("UPDATE company_settings SET books_closed_through = ? WHERE id = 1", (new,))
        return {"dry_run": False, "closed": names}
    if dry_run:
        conn = read_connection(context.company_db_path)
        try:
            return {"dry_run": True, "reopen": [r["name"] for r in _closed_after(conn, new)]}
        finally:
            conn.close()
    _require_confirm(confirm)
    reason = _clean_reason(reason)
    with write_transaction(context.company_db_path, context) as conn:
        names = []
        for row in _closed_after(conn, new):
            _reopen(conn, context, _period(conn, row["period_id"]), "Books closed through", reason)
            names.append(row["name"])
        conn.execute("UPDATE company_settings SET books_closed_through = ? WHERE id = 1", (new,))
    return {"dry_run": False, "reopened": names}


def _closed_after(conn, day):
    return conn.execute("SELECT period_id, name FROM fiscal_period WHERE is_adjustment_period = 0 AND is_closed = 1 "
                        "AND end_date > ? ORDER BY start_date", (day,)).fetchall()


def _open_through(conn, day):
    return conn.execute("SELECT period_id, name FROM fiscal_period WHERE is_adjustment_period = 0 AND is_closed = 0 "
                        "AND end_date <= ? ORDER BY start_date", (day,)).fetchall()


def _forward_preview(context, new):
    conn = read_connection(context.company_db_path)
    try:
        rows = _open_through(conn, new)
        warnings = [r for row in rows for r in _run_checks(conn, _period(conn, row["period_id"]))
                    if not r["ok"] and r["code"] != "earlier_period_open"]
        return {"dry_run": True, "close": [r["name"] for r in rows], "warnings": warnings}
    finally:
        conn.close()


# --- Years (B1, L7 amended) ------------------------------------------------------------------------------

def _year(conn, year_id):
    row = conn.execute("SELECT * FROM fiscal_year WHERE year_id = ?", (year_id,)).fetchone()
    if row is None:
        raise NotFoundError("That fiscal year does not exist")
    return row


def close_year(context, year_id):
    """Lock a fiscal year (B1): months 1-12 must be closed; 13 and 14 are closed with it. No closing entries."""
    authorize(context, "period.close", record_type="fiscal_year", record_id=year_id)
    with write_transaction(context.company_db_path, context) as conn:
        year = _year(conn, year_id)
        if year["is_year_closed"]:
            raise ValidationError(f"{year['name']} is already closed")
        still_open = [r["name"] for r in conn.execute(
            "SELECT name FROM fiscal_period WHERE fiscal_year_id = ? AND is_adjustment_period = 0 AND is_closed = 0 "
            "ORDER BY period_number", (year_id,))]
        if still_open:
            raise ValidationError(f"Close these periods first: {', '.join(still_open)}")
        if conn.execute("SELECT 1 FROM fiscal_year WHERE start_date > ?", (year["end_date"],)).fetchone() is None:
            _create_year(conn, _start_month(conn), int(year["name"][2:]) + 1)
        for row in conn.execute("SELECT period_id FROM fiscal_period WHERE fiscal_year_id = ? "
                                "AND is_adjustment_period = 1 AND is_closed = 0 ORDER BY period_number",
                                (year_id,)).fetchall():
            _close(conn, context, _period(conn, row["period_id"]), "Year close")
        conn.execute("UPDATE fiscal_year SET is_year_closed = 1, closed_at = ?, closed_by = ? WHERE year_id = ?",
                     (context.now, context.user_id, year_id))
        _history(conn, context, year_id=year_id, action="Year close", via="Year close")


def reopen_year(context, year_id, reason=None, confirm_year_name=None):
    """Reopen a closed fiscal year (L7 amended): year.reopen, a reason and the year's name typed exactly.

    The year opens; its periods stay closed until each is reopened with reopen_period.
    """
    authorize(context, "year.reopen", record_type="fiscal_year", record_id=year_id)
    reason = _clean_reason(reason)
    with write_transaction(context.company_db_path, context) as conn:
        year = _year(conn, year_id)
        if not year["is_year_closed"]:
            raise ValidationError(f"{year['name']} is not closed")
        if not isinstance(confirm_year_name, str) or confirm_year_name != year["name"]:
            raise ValidationError(f"Type the year's name exactly as shown ({year['name']}) to reopen it")
        conn.execute("UPDATE fiscal_year SET is_year_closed = 0, closed_at = NULL, closed_by = NULL WHERE year_id = ?",
                     (year_id,))
        _history(conn, context, year_id=year_id, action="Year reopen", via="Year reopen", reason=reason)


# --- Controls and setup -----------------------------------------------------------------------------------

def set_close_check_mode(context, check_code, mode):
    """Make a close check a warning (default) or a hard block (L2). Logged."""
    authorize(context, "company.settings", record_type="period_close_check")
    if check_code not in CHECK_CODES:
        raise ValidationError(f"'{check_code}' is not a period-close check")
    if mode not in CHECK_MODES:
        raise ValidationError("A check is either a warning (warn) or a block (block)")
    with write_transaction(context.company_db_path, context) as conn:
        conn.execute("UPDATE period_close_check SET mode = ? WHERE check_code = ?", (mode, check_code))


def change_fiscal_year_start(context, start_month, first_year=None):
    """Change the month the fiscal year starts. Only while the company has no journal entries: years are rebuilt."""
    authorize(context, "company.settings", record_type="fiscal_year")
    if isinstance(start_month, bool) or not isinstance(start_month, int) or not 1 <= start_month <= 12:
        raise ValidationError("The fiscal year starts in month 1 to 12")
    with write_transaction(context.company_db_path, context) as conn:
        if conn.execute("SELECT 1 FROM journal_entry LIMIT 1").fetchone():
            raise ValidationError("The fiscal year start cannot change once the company has journal entries")
        if conn.execute("SELECT 1 FROM period_status_history LIMIT 1").fetchone():
            raise ValidationError("The fiscal year start cannot change once a period has been closed")
        names = [r["name"] for r in conn.execute("SELECT name FROM fiscal_year ORDER BY start_date")]
        settings = _settings(conn)
        if first_year is None:
            first_year = settings["first_fiscal_year"] or (int(names[0][2:]) if names else None)
        if not isinstance(first_year, int) or isinstance(first_year, bool):
            raise ValidationError("Enter the first fiscal year to record, such as 2027")
        try:
            conn.execute("DELETE FROM fiscal_period WHERE is_adjustment_period = 1")
            for (period_id,) in conn.execute("SELECT period_id FROM fiscal_period ORDER BY start_date DESC").fetchall():
                conn.execute("DELETE FROM fiscal_period WHERE period_id = ?", (period_id,))
            conn.execute("DELETE FROM fiscal_year")
        except sqlite3.IntegrityError:
            raise ValidationError("Records already use these periods, so the fiscal year cannot be rebuilt") from None
        seed_years(conn, start_month, first_year, count=max(2, len(names)))
        conn.execute("UPDATE company_settings SET fiscal_year_start = ?, first_fiscal_year = ? WHERE id = 1",
                     (f"{start_month:02d}-01", first_year))
