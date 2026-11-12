"""The general ledger service: draft journal entries (Phase 2.5, step 2).

This is the only module that writes `journal_entry`, `journal_line` and the entry counter (CLAUDE.md rule 7; a
static test fails if any other file does). Step 2 covers drafts only: create, update, delete and read, with every
line checked by one function (`check_lines`). Posting, numbering, approvals, reversals, voids and rounding come in
later steps and call the same functions.

* A draft may be unbalanced or empty; the balance, line count and closed-period rules are enforced when posting
  (the baseline trigger is the backstop).
* The period comes from the entry date through `periods.resolve_entry_period` (A1); this module never works it
  out itself. A draft cannot be dated in a closed period.
* Lines may only use active, postable accounts that have no child accounts (C2). The check runs when a draft is
  created or changed and is available as `check_entry_lines` so posting can run it again on the stored lines,
  because an account can be deactivated after a draft was saved.
* Amounts are integer cents: floats, strings and booleans are refused.
* `is_control_override` and `is_rounding_adjustment` are set by the posting code, never by a caller.
* Manual sources only (none, Manual, Adjustment) for Human and Agent origin: a person cannot label a draft with a
  document source to escape the manual-entry rules. Import and System origin may use the others.
* Drafts record the context's origin, so an Agent draft stays an Agent entry through posting. Nothing here stores
  or assumes anything about hashing: columns are always named in SQL, never positional, and rows are read by name.
"""
import sqlite3
from datetime import date

from modules.services import periods
from modules.services.authz import authorize
from modules.services.errors import NotFoundError, PeriodClosedError, PostingError, ValidationError
from modules.services.tx import read_connection, write_transaction

CREATE = "je.create"
VIEW = "ledger.view"
MANUAL_SOURCES = (None, "Manual", "Adjustment")
OTHER_SOURCES = ("Invoice", "Bill", "Payment", "Payroll", "Import", "Deferral", "Completion", "Conversion")
LINE_FIELDS = ("account_id", "debit_cents", "credit_cents", "memo", "contact_id", "project_id", "cost_code_id",
               "external_ref")
STATES = ("draft", "posted")
_UNSET = object()


# --- Small checks -------------------------------------------------------------------------------------

def _text(value, what):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"The {what} must be text")
    return value.strip() or None


def _iso_date(value, what):
    if not isinstance(value, str):
        raise ValidationError(f"Enter the {what} as YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{value} is not a valid {what}; enter it as YYYY-MM-DD") from None
    if parsed.isoformat() != value:
        raise ValidationError(f"Enter the {what} as YYYY-MM-DD")
    return value


def _source(context, source):
    if source in MANUAL_SOURCES:
        return source
    if source not in OTHER_SOURCES:
        raise ValidationError(f"'{source}' is not an entry source")
    if context.origin not in ("Import", "System"):
        raise ValidationError(f"A {context.origin.lower()} entry is a manual entry; the source '{source}' is "
                              "used only by documents and imports")
    return source


def _cents(value, what):
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{what} must be a whole number of cents")
    if value < 0:
        raise ValidationError(f"{what} cannot be negative")
    return value


def _check_accounts(conn, rows):
    """Every line's account must exist, be active and postable, and have no child accounts (C2)."""
    for number, row in enumerate(rows, start=1):
        account = conn.execute("SELECT account_id, code, name, is_active, is_postable FROM account "
                               "WHERE account_id = ?", (row["account_id"],)).fetchone()
        if account is None:
            raise ValidationError(f"Line {number}: that account does not exist")
        label = f"{account['code']} {account['name']}"
        if not account["is_active"]:
            raise PostingError(f"Line {number}: account {label} is inactive; choose an active account")
        has_children = conn.execute("SELECT 1 FROM account WHERE parent_id = ? LIMIT 1",
                                    (account["account_id"],)).fetchone()
        if not account["is_postable"] or has_children:
            raise PostingError(f"Line {number}: account {label} is a header account; "
                               "choose one of its sub-accounts")


def check_lines(conn, lines):
    """The one place a line is validated. Returns the cleaned lines; raises ValidationError or PostingError.

    `lines` is a list of dicts with account_id and exactly one of debit_cents / credit_cents (a positive whole
    number of cents), plus optional memo, contact_id, project_id, cost_code_id and external_ref. A draft may be
    unbalanced; balance is checked when posting.
    """
    if not isinstance(lines, (list, tuple)):
        raise ValidationError("The lines must be a list")
    cleaned = []
    for number, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            raise ValidationError(f"Line {number}: each line must be a set of fields")
        unknown = sorted(set(line) - set(LINE_FIELDS))
        if unknown:
            raise ValidationError(f"Line {number}: '{unknown[0]}' cannot be set on a line")
        account_id = line.get("account_id")
        if isinstance(account_id, bool) or not isinstance(account_id, int):
            raise ValidationError(f"Line {number}: choose an account")
        debit = _cents(line.get("debit_cents"), f"Line {number}: the debit")
        credit = _cents(line.get("credit_cents"), f"Line {number}: the credit")
        if (debit > 0) == (credit > 0):
            raise ValidationError(f"Line {number}: enter either a debit or a credit amount, not both or neither")
        clean = {"account_id": account_id, "debit_cents": debit, "credit_cents": credit,
                 "memo": _text(line.get("memo"), "memo"), "external_ref": _text(line.get("external_ref"), "reference")}
        for field, table in (("contact_id", "contact"), ("project_id", "project"), ("cost_code_id", "cost_code")):
            value = line.get(field)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int) or conn.execute(
                        f"SELECT 1 FROM {table} WHERE {field} = ?", (value,)).fetchone() is None:
                    raise ValidationError(f"Line {number}: that {table.replace('_', ' ')} does not exist")
            clean[field] = value
        cleaned.append(clean)
    _check_accounts(conn, cleaned)
    return cleaned


def check_entry_lines(conn, entry_id):
    """Run the account rules again on an entry's stored lines (posting calls this)."""
    rows = conn.execute("SELECT account_id FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                        (entry_id,)).fetchall()
    _check_accounts(conn, rows)


def _insert_lines(conn, entry_id, lines):
    for line in lines:
        conn.execute(
            "INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents, memo, contact_id, "
            "project_id, cost_code_id, external_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, line["account_id"], line["debit_cents"], line["credit_cents"], line["memo"],
             line["contact_id"], line["project_id"], line["cost_code_id"], line["external_ref"]))


def _open_period(conn, entry_date, period_id):
    """The period for the date (through periods.resolve_entry_period); a closed period is an error."""
    resolved = periods.resolve_entry_period(conn, entry_date, period_id)
    period = conn.execute("SELECT name, is_closed FROM fiscal_period WHERE period_id = ?", (resolved,)).fetchone()
    if period["is_closed"]:
        raise PeriodClosedError(f"{period['name']} is closed; choose a date in an open period")
    return resolved


def _check_auto_reverse(entry_date, auto_reverse_date):
    if auto_reverse_date is None:
        return None
    _iso_date(auto_reverse_date, "automatic reversal date")
    if auto_reverse_date <= entry_date:
        raise ValidationError("The automatic reversal date must be after the entry date")
    return auto_reverse_date


def _draft(conn, entry_id):
    """The entry row if it is an editable draft."""
    row = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
    if row is None:
        raise NotFoundError("That journal entry does not exist")
    if row["is_posted"]:
        raise PostingError("A posted entry cannot be changed; reverse it instead")
    return row


# --- Writing drafts ---------------------------------------------------------------------------------------

def create_entry(context, *, entry_date, lines=(), description=None, reference=None, source=None,
                 period_id=None, auto_reverse_date=None):
    """Save a new draft entry and return its id. Nothing is posted and no entry number is taken."""
    authorize(context, CREATE, record_type="journal_entry")
    source = _source(context, source)
    description, reference = _text(description, "description"), _text(reference, "reference")
    with write_transaction(context.company_db_path, context) as conn:
        resolved = _open_period(conn, entry_date, period_id)
        auto_reverse_date = _check_auto_reverse(entry_date, auto_reverse_date)
        cleaned = check_lines(conn, lines)
        entry_id = conn.execute(
            "INSERT INTO journal_entry (entry_date, period_id, reference, description, source, created_by, origin, "
            "auto_reverse_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING entry_id",
            (entry_date, resolved, reference, description, source, context.user_id, context.origin,
             auto_reverse_date)).fetchone()[0]
        _insert_lines(conn, entry_id, cleaned)
    return entry_id


def update_entry(context, entry_id, *, entry_date=_UNSET, description=_UNSET, reference=_UNSET, source=_UNSET,
                 period_id=None, auto_reverse_date=_UNSET, lines=None):
    """Change a draft. Fields left out stay as they are; `lines`, when given, replaces all the lines."""
    authorize(context, CREATE, record_type="journal_entry", record_id=entry_id)
    with write_transaction(context.company_db_path, context) as conn:
        current = _draft(conn, entry_id)
        if current["reverses_entry_id"] is not None:
            raise PostingError("A reversal draft is made by the reverse or void action and is not edited here")
        values = {
            "entry_date": current["entry_date"] if entry_date is _UNSET else entry_date,
            "description": current["description"] if description is _UNSET else _text(description, "description"),
            "reference": current["reference"] if reference is _UNSET else _text(reference, "reference"),
            "source": current["source"] if source is _UNSET else _source(context, source),
            "auto_reverse_date": current["auto_reverse_date"] if auto_reverse_date is _UNSET else auto_reverse_date,
            "period_id": current["period_id"],
        }
        if entry_date is not _UNSET or period_id is not None:
            values["period_id"] = _open_period(conn, values["entry_date"], period_id)
        values["auto_reverse_date"] = _check_auto_reverse(values["entry_date"], values["auto_reverse_date"])
        cleaned = check_lines(conn, lines) if lines is not None else None
        conn.execute(
            "UPDATE journal_entry SET entry_date = ?, period_id = ?, reference = ?, description = ?, source = ?, "
            "auto_reverse_date = ? WHERE entry_id = ?",
            (values["entry_date"], values["period_id"], values["reference"], values["description"],
             values["source"], values["auto_reverse_date"], entry_id))
        if cleaned is not None:
            conn.execute("DELETE FROM journal_line WHERE entry_id = ?", (entry_id,))
            _insert_lines(conn, entry_id, cleaned)


def delete_entry(context, entry_id):
    """Delete a draft and its lines. A posted entry is corrected with a reversal, never deleted."""
    authorize(context, CREATE, record_type="journal_entry", record_id=entry_id)
    with write_transaction(context.company_db_path, context) as conn:
        _draft(conn, entry_id)
        try:
            conn.execute("DELETE FROM journal_line WHERE entry_id = ?", (entry_id,))
            conn.execute("DELETE FROM journal_entry WHERE entry_id = ?", (entry_id,))
        except sqlite3.IntegrityError:
            raise ValidationError("This entry is used by another record and cannot be deleted") from None


# --- Reading ------------------------------------------------------------------------------------------------

def get_entry(context, entry_id):
    """One entry as a dict with `lines` and the debit and credit totals."""
    authorize(context, VIEW, record_type="journal_entry", record_id=entry_id)
    conn = read_connection(context.company_db_path)
    try:
        row = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
        if row is None:
            raise NotFoundError("That journal entry does not exist")
        entry = dict(row)
        entry["lines"] = [dict(r) for r in conn.execute(
            "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))]
    finally:
        conn.close()
    entry["total_debit_cents"] = sum(line["debit_cents"] for line in entry["lines"])
    entry["total_credit_cents"] = sum(line["credit_cents"] for line in entry["lines"])
    return entry


def list_entries(context, *, state=None):
    """Entries oldest first, optionally only 'draft' or 'posted' ones (without lines)."""
    authorize(context, VIEW, record_type="journal_entry")
    if state not in (None, *STATES):
        raise ValidationError("Choose draft or posted")
    sql = "SELECT * FROM journal_entry"
    if state:
        sql += f" WHERE is_posted = {1 if state == 'posted' else 0}"
    conn = read_connection(context.company_db_path)
    try:
        return [dict(r) for r in conn.execute(sql + " ORDER BY entry_id")]
    finally:
        conn.close()
