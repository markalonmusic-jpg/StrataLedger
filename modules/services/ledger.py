"""The general ledger service: draft journal entries (step 2) and posting (step 3) of Phase 2.5.

This is the only module that writes `journal_entry`, `journal_line` and the entry counter (CLAUDE.md rule 7; a
static test fails if any other file does). Step 2 covers drafts only: create, update, delete and read, with every
line checked by one function (`check_lines`). Posting, numbering, approvals, reversals, voids and rounding came in
later steps and call the same functions.

* A draft may be unbalanced or empty; the balance, line count and closed-period rules are enforced when posting
  (the baseline trigger is the backstop).
* The period comes from the entry date through `periods.resolve_entry_period` (A1); this module never works it
  out itself. A draft cannot be dated in a closed period.
* Lines may only use active, postable accounts that have no child accounts (C2). The check runs when a draft is
  created or changed and is available as `check_entry_lines` so posting can run it again on the stored lines,
  because an account can be deactivated after a draft was saved.
* Amounts are integer cents: floats, strings and booleans are refused.
* `is_control_override` (set when posting) and `is_rounding_adjustment` (set when saving, R49) are set by this
  module, never by a caller.
* `create_entry` and `update_entry` take manual sources only (none, Manual, Adjustment), for every origin (R50): a
  person cannot label a draft with a document source to escape the manual-entry rules. Document, import, payroll
  and conversion entries are made only by `create_document_entry`, inside the caller's transaction (section 13).
* Drafts record the context's origin, so an Agent draft stays an Agent entry through posting. Columns are always
  named in SQL, never positional, and rows are read by name.

Posting (`post_journal_entry`, step 3) runs every check again on the stored draft, then, in ONE write transaction:
sets the control-override flags, locks the entry counter row, reads it, increments it, seals the entry with the
company's chain key (docs/audit_readiness_design.md 2.5) and writes is_posted, the number, who and when and the
four chain columns in ONE update. Any failure rolls the whole transaction back, so numbers stay gapless and the
chain has no hole. `_seal_and_post` is that core; every entry is posted through it, so one transaction may post
several entries in turn and still number and chain them without a gap.

Reversals (step 5, L5, R4, R40-R47):
* Posting an entry with `auto_reverse_date` posts its Accrual reversal right after it, in the same transaction:
  origin System, created and posted by the person who posted, the original's source, no approval fields. If the
  reversal date has no period or its period is closed, nothing is posted (R47).
* `void_entry` posts a Void reversal (the trigger then marks the original void) and `reverse_entry` a Correction.
  Only a person, with `je.reverse`, `confirm=True` and a note; no second person (R42) and no approval (R8). Only
  manual, Import, Payroll and Conversion entries (R40); never a reversal (R43). A Void defaults to the original's
  date, a Correction to today, and neither may be dated before the original (R41). Voiding an accrual that has an
  automatic reversal voids both, each on its target's date, or nothing (R4); such an accrual cannot be corrected
  (R44). A reversal dated its target's own date in period 13 or 14 stays in that period (R48).
* A reversal mirrors its original line by line: debit and credit swapped, every other line field and flag and
  every dimension copied (R45). The account rules and the A5 control are not applied again: a correction must
  stay possible after an account is closed or the control is turned off.
* Reads return `display_description`: the description, with the person's reversal note after it (R46).

Rounding and document entries (step 6, L8, R1, R49-R54): `create_document_entry` is the one way a document,
import, payroll or conversion entry is made, inside the caller's write transaction (audit design section 13). An
Import, Payroll or Conversion entry out of balance by exactly 1 cent gets one flagged 1-cent line to the rounding
account when it is saved, worked out again on every save; 2 cents or more is refused when it is saved, naming the
entry, its file rows and the difference. Posting checks every rounding line again (R53). Import, Payroll and
Conversion entries are saved only with origin Import, so each is reviewed by a person before it posts (R55).

Approvals (step 4, R15-R24): an entry needs an Approved request before it posts when its origin is Agent or
Import, when it is a manual entry over the manual-entry approval threshold, or when its document type requires
approval (`approval_document_type`). `submit_entry_for_approval` runs the posting checks and sends it with the
entry's digest; posting re-reads the newest request inside its transaction and refuses unless it is Approved
for the entry exactly as it is now, then writes and seals the last approver. A Pending request blocks posting
of any entry. Any edit or delete cancels the request in the same transaction. With require_separate_approver
on, the entry's creator cannot post it (R17). Only a person posts an Import-origin entry until the Imports phase
builds batch review (R18).
"""
import sqlite3
from datetime import date

from modules.services import approvals, hooks, keys, ledger_chain, money, periods
from modules.services.authz import authorize, deny
from modules.services.errors import (
    KeyUnavailableError, NotFoundError, PeriodClosedError, PostingError, ValidationError,
)
from modules.services.tx import read_connection, write_transaction

CREATE = "je.create"
POST = "je.post"
REVERSE = "je.reverse"
RECORD_TYPE = "journal_entry"
IMPORT_POSTED_BY_A_PERSON = ("An imported entry is posted by a person after review; sign in and post it from the "
                             "approved entries.")
CREATOR_CANNOT_POST = ("This company needs a different person to post an entry you created; ask a colleague to "
                       "post it.")
SELF_APPROVED = ("This entry was approved by the person who created it or sent it for approval; send it for approval "
                 "again so someone else approves it.")
# R30: the log file gets this instead of the rejection refusal, which quotes the reason a person typed.
REJECTED_LOG = "This entry was rejected; change it and send it for approval again."
# Document sources whose document type has its own "requires approval" switch (decision 1.6).
DOCUMENT_APPROVAL_TYPES = {"Bill": "Bill", "Payment": "Payment", "Import": "Import batch", "Payroll": "Import batch"}
# A manual line to these controlled accounts must name the contact (A5): (contact flag, word).
CONTACT_RULES = {"AR": ("is_customer", "customer"), "AP": ("is_vendor", "vendor")}
VIEW = "ledger.view"
MANUAL_SOURCES = (None, "Manual", "Adjustment")
OTHER_SOURCES = ("Invoice", "Bill", "Payment", "Payroll", "Import", "Deferral", "Completion", "Conversion")
# L8, R1: only these may carry the one-cent rounding line (R49-R53).
ROUNDING_SOURCES = ("Import", "Payroll", "Conversion")
ROUNDING_MEMO = "Rounding (1 cent)"
# Saved only with origin Import, so they always need one human review (CLAUDE.md section 0, R18, R55). Typed opening
# balances are Conversion entries too (R55).
IMPORTER_SOURCES = ("Import", "Payroll", "Conversion")
LINE_FIELDS = ("account_id", "debit_cents", "credit_cents", "memo", "contact_id", "project_id", "cost_code_id",
               "external_ref")
STATES = ("draft", "posted")
# R57: a document entry's line may open a clearing group (the group's id is then the line's own id) or join an
# existing group on the same account by giving that group's id.
NEW_CLEARING = "new"
# R40: entries a person may void or correct by source; a document's entry is voided through its document.
REVERSIBLE_SOURCES = (None, "Manual", "Adjustment", "Import", "Payroll", "Conversion")
DOCUMENT_SOURCE_WORDS = {"Invoice": ("an invoice", "invoice"), "Bill": ("a bill", "bill"),
                         "Payment": ("a payment", "payment"), "Deferral": ("a deferral", "deferral"),
                         "Completion": ("a percentage-of-completion entry", "percentage-of-completion entry")}
ONLY_A_PERSON_REVERSES = "Only a person can void or correct an entry; sign in and do it from the entry."
# The line fields a reversal copies as they are (debit and credit are swapped), R45.
MIRRORED_LINE_FIELDS = ("account_id", "memo", "contact_id", "project_id", "cost_code_id", "deferral_id", "batch_id",
                        "is_retainage_line", "external_ref", "is_control_override", "is_rounding_adjustment",
                        # RP2: a reversal stays in its original's entity and clearing group, so the group nets out.
                        "entity_id", "clearing_id")
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


def _source(source):
    """A draft's source through create_entry or update_entry: manual sources only, for every origin (R50)."""
    if source in MANUAL_SOURCES:
        return source
    if source not in OTHER_SOURCES:
        raise ValidationError(f"'{source}' is not an entry source")
    raise ValidationError(f"This is a manual entry; the source '{source}' is used only by documents and imports, "
                          "which make their entries through their own service")


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


def _check_cost_codes(conn, rows, error):
    """RP5: a line posts only to an active leaf cost code: not a level 1 division, not a code with active
    sub-codes. `error` is ValidationError when saving and PostingError when posting."""
    for number, row in enumerate(rows, start=1):
        if row["cost_code_id"] is None:
            continue
        code = conn.execute("SELECT code, level, is_active FROM cost_code WHERE cost_code_id = ?",
                            (row["cost_code_id"],)).fetchone()
        if not code["is_active"]:
            raise error(f"Line {number}: cost code {code['code']} is inactive; choose an active code")
        if code["level"] == 1:
            raise error(f"Line {number}: post to a cost code or sub-code, not the division {code['code']}")
        if conn.execute("SELECT 1 FROM cost_code WHERE parent_id = ? AND is_active = 1 LIMIT 1",
                        (row["cost_code_id"],)).fetchone():
            raise error(f"Line {number}: cost code {code['code']} has sub-codes; post to one of its sub-codes")


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
    _check_cost_codes(conn, cleaned, ValidationError)
    return cleaned


def check_entry_lines(conn, entry_id):
    """Run the account and cost-code rules again on an entry's stored lines (posting calls this)."""
    rows = conn.execute("SELECT account_id, cost_code_id FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                        (entry_id,)).fetchall()
    _check_accounts(conn, rows)
    _check_cost_codes(conn, rows, PostingError)


def _stored_lines(conn, entry_id):
    """The entry's lines as _rounded returns them, in order (to spot a re-save of the same lines)."""
    fields = LINE_FIELDS + ("is_rounding_adjustment",)
    return [{field: row[field] for field in fields} for row in conn.execute(
        f"SELECT {', '.join(fields)} FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))]


def _insert_lines(conn, entry_id, lines):
    """Insert the lines in order and return their new line ids."""
    return [conn.execute(
        "INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents, memo, contact_id, "
        "project_id, cost_code_id, external_ref, is_rounding_adjustment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "RETURNING line_id",
        (entry_id, line["account_id"], line["debit_cents"], line["credit_cents"], line["memo"],
         line["contact_id"], line["project_id"], line["cost_code_id"], line["external_ref"],
         line.get("is_rounding_adjustment", 0))).fetchone()[0] for line in lines]


def _clearing_requests(conn, lines, source):
    """R57: the clearing id each document line asks for (None, NEW_CLEARING or an existing group's id), and the
    lines without the key, ready for check_lines. Importers cannot set clearing ids."""
    if not isinstance(lines, (list, tuple)):
        return [], lines
    requests, plain = [], []
    for number, line in enumerate(lines, start=1):
        if not isinstance(line, dict) or "clearing_id" not in line:
            requests.append(None)
            plain.append(line)
            continue
        value = line["clearing_id"]
        plain.append({k: v for k, v in line.items() if k != "clearing_id"})
        if value is None:
            requests.append(None)
            continue
        if source in IMPORTER_SOURCES:
            raise ValidationError(f"Line {number}: an imported entry cannot set a clearing id; it is set when the "
                                  "documents are matched")
        if value != NEW_CLEARING and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValidationError(f"Line {number}: a clearing id is a new group or an existing group's number")
        requests.append(value)
    return requests, plain


def _check_clearing_groups(conn, requests, cleaned):
    """R57, R60: a clearing group lives on an account that keeps open items (track_clearing_id). An existing group
    is named by its opening line (clearing_id = line_id): posted, on the same account, for the same contact."""
    for number, (value, line) in enumerate(zip(requests, cleaned), start=1):
        if value is None:
            continue
        account = conn.execute("SELECT code, track_clearing_id FROM account WHERE account_id = ?",
                               (line["account_id"],)).fetchone()
        if not account["track_clearing_id"]:
            raise ValidationError(f"Line {number}: account {account['code']} does not keep open items, so it has no "
                                  "clearing groups; use the receivable or payable account")
        if value == NEW_CLEARING:
            continue
        opening = conn.execute(
            "SELECT l.contact_id FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id "
            "WHERE l.line_id = ? AND l.clearing_id = l.line_id AND l.account_id = ? AND e.is_posted = 1",
            (value, line["account_id"])).fetchone()
        if opening is None:
            raise ValidationError(f"Line {number}: clearing group {value} is not an open item posted on this account")
        if opening["contact_id"] != line["contact_id"]:
            raise ValidationError(f"Line {number}: clearing group {value} belongs to another customer or vendor")


def _apply_clearing(conn, requests, line_ids):
    for value, line_id in zip(requests, line_ids):
        if value is not None:
            conn.execute("UPDATE journal_line SET clearing_id = ? WHERE line_id = ?",
                         (line_id if value == NEW_CLEARING else value, line_id))


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


# --- Rounding (L8, R1, R49-R52) ----------------------------------------------------------------------------

def _source_rows(source_rows):
    """The file rows an Import, Payroll or Conversion entry came from: a non-empty list of row numbers (R51)."""
    if (not isinstance(source_rows, (list, tuple)) or not source_rows
            or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in source_rows)):
        raise ValidationError("Give the file rows this entry came from (a list of row numbers), so a balance error "
                              "can name them.")
    return tuple(source_rows)


def _rows_text(rows):
    """(4, 5, 7, 9) -> 'rows 4-5, 7, 9'; (8,) -> 'row 8'."""
    numbers = sorted(set(rows))
    runs = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number != previous + 1:
            runs.append(f"{start}-{previous}" if previous != start else f"{start}")
            start = number
        previous = number
    runs.append(f"{start}-{previous}" if previous != start else f"{start}")
    return ("row " if len(numbers) == 1 else "rows ") + ", ".join(runs)


def _entry_label(reference, entry_date, source_rows):
    """How a balance error names the entry: 'Entry PR-0412 (rows 12-15)' or 'The entry dated 2026-03-15'."""
    label = f"Entry {reference}" if reference else f"The entry dated {entry_date}"
    return f"{label} ({_rows_text(source_rows)})" if source_rows else label


def _rounding_account(conn, label):
    """The rounding account from Company Settings, usable for a line (C2); refused with what to do (R52)."""
    settings = _settings(conn)
    account_id = settings["rounding_variance_acct_id"] if settings is not None else None
    if account_id is None:
        raise ValidationError(f"{label} is out of balance by 0.01 and no rounding account is set; choose one in "
                              "Company Settings > Accounts, or correct the amounts.")
    account = conn.execute("SELECT code, name, is_active, is_postable FROM account WHERE account_id = ?",
                           (account_id,)).fetchone()
    has_children = conn.execute("SELECT 1 FROM account WHERE parent_id = ? LIMIT 1", (account_id,)).fetchone()
    problem = ("is inactive" if not account["is_active"]
               else "is a header account" if not account["is_postable"] or has_children else None)
    if problem:
        raise ValidationError(f"{label} is out of balance by 0.01 and the rounding account {account['code']} "
                              f"{account['name']} {problem}; choose another in Company Settings > Accounts, or "
                              "correct the amounts.")
    return account_id


def _rounded(conn, source, cleaned, label, *, importing=True):
    """The lines to store and the difference (debits - credits) before rounding (R49, R51).

    An Import, Payroll or Conversion entry that is out by exactly 1 cent gets one more line, last: 1 cent on the
    other side to the rounding account, flagged is_rounding_adjustment. Out by 2 cents or more is refused, so the
    caller's transaction saves nothing. Any other source is stored as it is (posting refuses an imbalance).
    """
    stored = [dict(line, is_rounding_adjustment=0) for line in cleaned]
    if source not in ROUNDING_SOURCES:
        return stored, 0
    difference = sum(l["debit_cents"] for l in cleaned) - sum(l["credit_cents"] for l in cleaned)
    if difference == 0:
        return stored, 0
    if abs(difference) > 1:
        again = "import it again" if importing else "save again"
        raise ValidationError(f"{label} is out of balance by {money.text(abs(difference))}; only a 1-cent rounding "
                              f"difference is balanced automatically, so nothing was saved. Correct the amounts "
                              f"and {again}.")
    stored.append({"account_id": _rounding_account(conn, label), "debit_cents": 1 if difference < 0 else 0,
                   "credit_cents": 1 if difference > 0 else 0, "memo": ROUNDING_MEMO, "contact_id": None,
                   "project_id": None, "cost_code_id": None, "external_ref": None, "is_rounding_adjustment": 1})
    return stored, difference


def _draft(conn, entry_id):
    """The entry row if it is an editable draft. A document's draft (invoice, bill, payment, deferral,
    percentage of completion) is changed only through its document, so its lines never escape the manual-entry
    rules (R50, R55); an import, payroll or conversion draft may be corrected during its review."""
    row = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
    if row is None:
        raise NotFoundError("That journal entry does not exist")
    if row["is_posted"]:
        raise PostingError("A posted entry cannot be changed; reverse it instead")
    if row["source"] not in MANUAL_SOURCES and row["source"] not in ROUNDING_SOURCES:
        made_by, document = DOCUMENT_SOURCE_WORDS[row["source"]]
        raise PostingError(f"This entry was made by {made_by}; change the {document} instead.")
    return row


# --- Writing drafts ---------------------------------------------------------------------------------------

def create_entry(context, *, entry_date, lines=(), description=None, reference=None, source=None,
                 period_id=None, auto_reverse_date=None):
    """Save a new draft entry and return its id. Nothing is posted and no entry number is taken."""
    authorize(context, CREATE, record_type="journal_entry")
    source = _source(source)
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


def _without_rounding_line(conn, entry_id, given):
    """The given lines without the draft's current rounding line, when it was sent back exactly as read (a screen
    that shows every line saves all of them); _rounded then works it out again (R49)."""
    current = conn.execute("SELECT account_id, debit_cents, credit_cents FROM journal_line WHERE entry_id = ? "
                           "AND is_rounding_adjustment = 1", (entry_id,)).fetchone()
    if current is None:
        return given
    for index, line in enumerate(given):
        if ((line["account_id"], line["debit_cents"], line["credit_cents"], line["memo"]) ==
                (current["account_id"], current["debit_cents"], current["credit_cents"], ROUNDING_MEMO)
                and line["contact_id"] is None and line["project_id"] is None and line["cost_code_id"] is None
                and line["external_ref"] is None):
            return given[:index] + given[index + 1:]
    return given


def update_entry(context, entry_id, *, entry_date=_UNSET, description=_UNSET, reference=_UNSET, source=_UNSET,
                 period_id=None, auto_reverse_date=_UNSET, lines=None):
    """Change a draft. Fields left out stay as they are; `lines`, when given, replaces all the lines."""
    authorize(context, CREATE, record_type="journal_entry", record_id=entry_id)
    with write_transaction(context.company_db_path, context) as conn:
        current = _draft(conn, entry_id)
        if current["reverses_entry_id"] is not None:
            raise PostingError("A reversal draft is made by the reverse or void action and is not edited here")
        if source is not _UNSET and current["source"] not in MANUAL_SOURCES and source != current["source"]:
            raise ValidationError(f"An import or document entry keeps its source ({current['source']}); delete the "
                                  "draft and make it again instead.")
        values = {
            "entry_date": current["entry_date"] if entry_date is _UNSET else entry_date,
            "description": current["description"] if description is _UNSET else _text(description, "description"),
            "reference": current["reference"] if reference is _UNSET else _text(reference, "reference"),
            "source": current["source"] if source is _UNSET or source == current["source"] else _source(source),
            "auto_reverse_date": current["auto_reverse_date"] if auto_reverse_date is _UNSET else auto_reverse_date,
            "period_id": current["period_id"],
        }
        if entry_date is not _UNSET or period_id is not None:
            values["period_id"] = _open_period(conn, values["entry_date"], period_id)
        values["auto_reverse_date"] = _check_auto_reverse(values["entry_date"], values["auto_reverse_date"])
        cleaned = None
        if lines is not None:                                     # R49: worked out again on every save
            given = check_lines(conn, lines)
            if values["source"] in ROUNDING_SOURCES:
                given = _without_rounding_line(conn, entry_id, given)
            cleaned, _ = _rounded(conn, values["source"], given,
                                  _entry_label(values["reference"], values["entry_date"], None), importing=False)
        if cleaned is not None and cleaned == _stored_lines(conn, entry_id):
            cleaned = None                     # the same lines again: not a change (R22 compares the digest)
        conn.execute(
            "UPDATE journal_entry SET entry_date = ?, period_id = ?, reference = ?, description = ?, source = ?, "
            "auto_reverse_date = ? WHERE entry_id = ?",
            (values["entry_date"], values["period_id"], values["reference"], values["description"],
             values["source"], values["auto_reverse_date"], entry_id))
        if cleaned is not None:
            conn.execute("DELETE FROM journal_line WHERE entry_id = ?", (entry_id,))
            _insert_lines(conn, entry_id, cleaned)
        approvals.cancel_in_transaction(conn, context, RECORD_TYPE, entry_id)        # R21: one change


def delete_entry(context, entry_id):
    """Delete a draft and its lines. A posted entry is corrected with a reversal, never deleted."""
    authorize(context, CREATE, record_type="journal_entry", record_id=entry_id)
    with write_transaction(context.company_db_path, context) as conn:
        _draft(conn, entry_id)
        approvals.cancel_in_transaction(conn, context, RECORD_TYPE, entry_id)        # R21: one change
        try:
            conn.execute("DELETE FROM journal_line WHERE entry_id = ?", (entry_id,))
            conn.execute("DELETE FROM journal_entry WHERE entry_id = ?", (entry_id,))
        except sqlite3.IntegrityError:
            raise ValidationError("This entry is used by another record and cannot be deleted") from None


# --- Document entries: the one narrow path (audit design section 13, R50, R54) ----------------------------------

def create_document_entry(conn, context, *, source, entry_date, lines, description=None, reference=None,
                          source_rows=None, post=False, exempt_from_approval=False):
    """Save (and with post=True, post) a document, import, payroll or conversion entry inside the caller's write
    transaction, so the document and its entry are written together or not at all.

    It does not authorize: the calling service has already authorized the person for its own permission. The
    context's origin is System or Import (`context.as_system()` / `as_import()`); a static test fixes which modules
    may call this and with which literal source. Import, Payroll and Conversion entries give `source_rows` (the
    file rows they came from) and are rounded by one cent or refused (R49, R51); for other sources source_rows is
    not used. Import, Payroll and Conversion entries need origin Import (R55). post=True posts at once, as one
    action of the document's service: an imported entry is posted by a person after its review (R18), an entry
    whose document type needs approval is refused, and the R17 creator rule does not apply (it is for a draft a
    person posts later; a document's separation is its own approval).

    A line may carry `clearing_id` (R57): NEW_CLEARING opens a group whose id is the line's own id, an int joins
    the existing group on the same account that that opening line started. Importers cannot set it.
    exempt_from_approval is only for an allocation's application entry (R59, payments.py; a static test fixes
    the caller): it is a system consequence of the allocation, like the R47 automatic reversal.

    Returns {'entry_id', 'entry_number' (None unless posted), 'rounding_cents'}: the difference (debits - credits)
    the rounding line balanced, 1 (a 1-cent credit), -1 (a 1-cent debit) or 0.
    """
    if context.origin not in ("System", "Import"):
        raise ValidationError("A document entry is made by its document's service (origin System or Import), "
                              "not by a person or an agent directly.")
    if source not in OTHER_SOURCES:
        raise ValidationError(f"'{source}' is not a document or import source; make a manual entry with "
                              "create_entry instead.")
    if source in IMPORTER_SOURCES and context.origin != "Import":         # section 0: always one human review
        article = "An" if source == "Import" else "A"
        raise ValidationError(f"{article} {source.lower()} entry is saved by its importer (origin Import), so a "
                              "person reviews it before it posts; save it as an import and send it for review.")
    if post and context.origin == "Import":
        raise ValidationError("An imported entry is posted by a person after its review; save it without "
                              "posting.")
    if source in ROUNDING_SOURCES:
        source_rows = _source_rows(source_rows)
    description, reference = _text(description, "description"), _text(reference, "reference")
    _iso_date(entry_date, "date")
    period_id = _open_period(conn, entry_date, None)
    clearing, lines = _clearing_requests(conn, lines, source)
    cleaned = check_lines(conn, lines)
    _check_clearing_groups(conn, clearing, cleaned)
    stored, difference = _rounded(conn, source, cleaned, _entry_label(reference, entry_date, source_rows))
    entry_id = conn.execute(
        "INSERT INTO journal_entry (entry_date, period_id, reference, description, source, created_by, origin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING entry_id",
        (entry_date, period_id, reference, description, source, context.user_id, context.origin)).fetchone()[0]
    _apply_clearing(conn, clearing, _insert_lines(conn, entry_id, stored))
    number = None
    if post:
        entry, _, _, debits, _ = _postable(conn, entry_id)
        if not exempt_from_approval and approval_document_type(conn, entry, _settings(conn), debits) is not None:
            raise PostingError("This entry needs approval before it posts; save it without posting and send it "
                               "for approval.")
        key_id, key = _active_key(conn, context)
        number = _seal_and_post(conn, context, entry_id, _company_code(context), key_id, key)
    return {"entry_id": entry_id, "entry_number": number, "rounding_cents": difference}


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
    entry["display_description"] = display_description(entry)
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
        entries = [dict(r) for r in conn.execute(sql + " ORDER BY entry_id")]
    finally:
        conn.close()
    for entry in entries:
        entry["display_description"] = display_description(entry)
    return entries


def display_description(entry):
    """The description as a screen shows it: a reversal's generated text with the person's note after it (R46)."""
    description, note = entry["description"], entry["reversal_note"]
    if not note:
        return description
    return f"{description} (note: {note})" if description else f"(note: {note})"


# --- Posting (step 3) ------------------------------------------------------------------------------------------

class DateWarningsError(ValidationError):
    """The entry date is far ahead or behind (L6); post again with acknowledge_date_warnings=True.

    `warnings` is the list from periods.entry_date_warnings: [{'code', 'message'}].
    """

    def __init__(self, message, warnings):
        super().__init__(message)
        self.warnings = warnings


def _company_code(context):
    conn = read_connection(context.master_db_path)
    try:
        row = conn.execute("SELECT company_code FROM company_registry WHERE company_id = ?",
                           (context.company_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError("This company is not registered on this computer")
    return row["company_code"]


def _settings(conn):
    return conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()


def approval_document_type(conn, entry, settings, debits):
    """The approval document type an entry needs before it posts (R20), or None when it posts directly.

    Agent origin: always (Journal entry). Import origin: always (Import batch, R18). A manual entry: when
    manual-entry approval is on and its debits are strictly over the threshold, or no threshold is set (R5).
    A document source: when its document type requires approval (1.6).
    """
    if entry["origin"] == "Import":
        return "Import batch"
    if entry["origin"] == "Agent":
        return "Journal entry"
    if entry["source"] in MANUAL_SOURCES:
        if settings is not None and settings["manual_entry_approval"]:
            threshold = settings["manual_entry_approval_threshold_cents"]
            if threshold is None or debits > threshold:
                return "Journal entry"
        return None
    document_type = DOCUMENT_APPROVAL_TYPES.get(entry["source"])
    if document_type:
        row = conn.execute("SELECT requires_approval FROM document_approval_setting WHERE document_type = ?",
                           (document_type,)).fetchone()
        if row is not None and row["requires_approval"]:
            return document_type
    return None


def _entry_digest(conn, entry):
    """The R15 digest of the entry as stored now (before posting sets any flag)."""
    entry_lines = conn.execute("SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                               (entry["entry_id"],)).fetchall()
    dimensions = conn.execute(
        "SELECT d.* FROM journal_line_dimension AS d JOIN journal_line AS l ON l.line_id = d.line_id "
        "WHERE l.entry_id = ?", (entry["entry_id"],)).fetchall()
    return ledger_chain.entry_digest(entry, entry_lines, dimensions)


def _approval_gate(state, needed, digest, debits, separate):
    """Refuse posting unless the approvals allow it (R15, R20). Returns (approved_by, approved_at) or (None, None).

    A Pending request blocks every entry. An Approved request must match the entry now (digest, amount and, when
    approval is needed, the document type), whether or not approval is still needed. With separation on, an
    approval the creator or the submitter made while it was off no longer counts (R28).
    """
    status = state["status"] if state else None
    if status == "Pending":
        raise PostingError(f"This entry is waiting for approval (step {state['step']} of {state['steps']}); "
                           "post it when the approval is complete.")
    if status == "Approved":
        if (state["document_digest"] != digest or state["amount_cents"] != debits
                or (needed is not None and state["document_type"] != needed)):
            raise PostingError("The approved entry does not match the entry now; send it for approval again.")
        if separate and state["self_approved"]:
            raise PostingError(SELF_APPROVED)
        return state["approved_by"], state["approved_at"]
    if needed is None:
        return None, None
    if status == "Rejected":
        raise PostingError(f"This entry was rejected ({approvals.reason_text(state['reason'])}); change it and "
                           "send it for approval again.", log_message=REJECTED_LOG)
    if status == "Cancelled":
        raise PostingError("The approval was cancelled because the entry was changed; send it for approval again.")
    raise PostingError("This entry needs approval before it posts; send it for approval first.")


def _postable(conn, entry_id):
    """Every posting check that does not depend on approval. Returns (entry, period, rows, debits, overrides)."""
    entry = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
    if entry is None:
        raise NotFoundError("That journal entry does not exist")
    if entry["is_posted"]:
        raise PostingError("This entry is already posted")
    if entry["reverses_entry_id"] is not None:
        raise PostingError("A reversal is posted by the reverse or void action, not here")
    if entry["auto_reverse_date"] is not None:
        _auto_reversal_period(conn, entry["auto_reverse_date"])        # R47: refused before anything is numbered
    period_id = periods.resolve_entry_period(conn, entry["entry_date"], entry["period_id"])
    period = conn.execute("SELECT name, is_closed, is_adjustment_period FROM fiscal_period WHERE period_id = ?",
                          (period_id,)).fetchone()
    if period["is_closed"]:
        raise PeriodClosedError(f"{period['name']} is closed; reopen it or date the entry in an open period")
    check_entry_lines(conn, entry_id)
    rows = conn.execute("SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,)).fetchall()
    if len(rows) < 2:
        raise PostingError("A journal entry needs at least two lines to post")
    _check_rounding_lines(conn, entry, rows)
    debits = sum(r["debit_cents"] or 0 for r in rows)
    credits = sum(r["credit_cents"] or 0 for r in rows)
    if debits != credits or debits <= 0:
        raise PostingError(f"This entry does not balance: debits {money.text(debits)}, credits {money.text(credits)}")
    overrides = _control_overrides(conn, rows, _settings(conn)) if entry["source"] in MANUAL_SOURCES else []
    return entry, period, rows, debits, overrides


def _check_rounding_lines(conn, entry, rows):
    """R53 (integrity): at most one rounding line, of exactly 1 cent, on the rounding account, and only on an
    Import, Payroll or Conversion entry. Callers cannot set the flag (it is not in LINE_FIELDS); this catches a
    line changed by any other way before it is sealed."""
    flagged = [(number, row) for number, row in enumerate(rows, start=1) if row["is_rounding_adjustment"]]
    if not flagged:
        return
    if entry["source"] not in ROUNDING_SOURCES:
        raise PostingError(f"Line {flagged[0][0]} is marked as a rounding line, which only import, payroll and "
                           "conversion entries may have; nothing was posted.")
    if len(flagged) > 1:
        raise PostingError("This entry has more than one rounding line; nothing was posted.")
    number, row = flagged[0]
    if (row["debit_cents"] or 0) + (row["credit_cents"] or 0) != 1:
        raise PostingError(f"Line {number}: a rounding line is exactly 1 cent; nothing was posted.")
    settings = _settings(conn)
    if settings is None or row["account_id"] != settings["rounding_variance_acct_id"]:
        raise PostingError(f"Line {number}: the rounding line is not on the rounding account in Company Settings > "
                           "Accounts; save the entry again to work it out again.")


def _control_overrides(conn, rows, settings):
    """The manual lines that post to controlled accounts (A5). Refused when the control is off; a manual AR or
    AP line must name its customer or vendor. Returns the line ids to flag is_control_override."""
    allowed = settings["allow_manual_control_je"] if settings is not None else 1
    flagged = []
    for number, row in enumerate(rows, start=1):
        account = conn.execute("SELECT code, name, control_type FROM account WHERE account_id = ?",
                               (row["account_id"],)).fetchone()
        if account["control_type"] is None:
            continue
        label = f"{account['code']} {account['name']}"
        if not allowed:
            raise PostingError(f"Line {number}: {label} is a controlled account ({account['control_type']}) and "
                               "manual entries to it are turned off in Settings > Controls; use the document that "
                               "posts to it instead")
        rule = CONTACT_RULES.get(account["control_type"])
        if rule:
            flag, word = rule
            contact = None
            if row["contact_id"] is not None:
                contact = conn.execute(f"SELECT {flag} FROM contact WHERE contact_id = ?",
                                       (row["contact_id"],)).fetchone()
            if contact is None or not contact[flag]:
                raise PostingError(f"Line {number}: a manual line to {label} must name the {word}")
        flagged.append(row["line_id"])
    return flagged


def _active_key(conn, context):
    """The company's active chain key from the key provider, checked against the fingerprint in the file."""
    row = conn.execute("SELECT key_id, fingerprint FROM ledger_chain_key WHERE is_active = 1").fetchone()
    if row is None:
        raise KeyUnavailableError(keys.NO_KEY_MESSAGE)
    key = keys.get_provider().get_key(context.company_id, row["key_id"])
    if ledger_chain.fingerprint(key.use_for_hmac()) != row["fingerprint"]:
        raise KeyUnavailableError(f"The ledger key on this computer does not match this company's key "
                                  f"(key {row['key_id']}); nothing was posted.")
    return row["key_id"], key


def _next_entry_number(conn):
    """Lock the counter row, read, increment (L4). SQLite: BEGIN IMMEDIATE (write_transaction) already holds the
    write lock. PostgreSQL: SELECT ... FOR UPDATE on this row. A rollback returns the number."""
    last = conn.execute("SELECT last_number FROM entry_number_sequence WHERE id = 1").fetchone()["last_number"]
    conn.execute("UPDATE entry_number_sequence SET last_number = ? WHERE id = 1", (last + 1,))
    return last + 1


def _chain_head(conn):
    row = conn.execute("SELECT chain_hash FROM journal_entry WHERE is_posted = 1 "
                       "ORDER BY entry_number DESC LIMIT 1").fetchone()
    return row["chain_hash"] if row is not None else ledger_chain.GENESIS


def submit_entry_for_approval(context, entry_id):
    """Send a draft for approval (R20). Returns the approval request id.

    Runs every posting check that does not depend on approval, then submits the entry's document type, its
    total debits and its digest (R15). Refused for an entry that can be posted directly, while a request is
    waiting, once it is approved and unchanged, and after a rejection until the entry has changed (R22).
    The checks, the digest and the new request are one write transaction, so the request is for the entry as
    it is then; a first read only finds the document type whose submit permission is authorized (rule 10).
    """
    authorize(context, CREATE, record_type=RECORD_TYPE, record_id=entry_id)
    conn = read_connection(context.company_db_path)
    try:
        needed, project_id = _submission(conn, entry_id)[:2]
    finally:
        conn.close()
    approvals.authorize_submit(context, needed, project_id, record_type=RECORD_TYPE, record_id=entry_id)
    with write_transaction(context.company_db_path, context) as conn:
        now_needed, now_project, entry, debits, settings = _submission(conn, entry_id)
        if (now_needed, now_project) != (needed, project_id):
            raise ValidationError("The entry changed while it was being sent; send it for approval again.")
        digest = _entry_digest(conn, entry)
        state = approvals.request_state(conn, RECORD_TYPE, entry_id)
        if state is not None and state["status"] == "Pending":
            raise ValidationError("This entry is already waiting for approval.")
        if (state is not None and state["status"] == "Approved" and state["document_digest"] == digest
                and not (approvals.separation_required(settings) and state["self_approved"])):
            raise ValidationError("This entry is already approved; post it.")
        return approvals.submit_in_transaction(conn, context, needed, RECORD_TYPE, entry_id, debits,
                                               created_by=entry["created_by"], project_id=project_id,
                                               document_digest=digest)


def _submission(conn, entry_id):
    """(document type, project, entry, debits, settings) for a submission; refuses one that needs no approval."""
    entry, _, rows, debits, _ = _postable(conn, entry_id)
    settings = _settings(conn)
    needed = approval_document_type(conn, entry, settings, debits)
    if needed is None:
        raise ValidationError("This entry can be posted directly; it does not need approval.")
    projects = {r["project_id"] for r in rows}
    return needed, (projects.pop() if len(projects) == 1 else None), entry, debits, settings


def _check_creator_may_post(context, entry_id):
    """R17: with require_separate_approver on, the entry's creator cannot post it (logged, before the write)."""
    conn = read_connection(context.company_db_path)
    try:
        row = conn.execute("SELECT created_by FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError("That journal entry does not exist")
    approvals.check_separate_approver(context, row["created_by"], permission_code=POST, record_type=RECORD_TYPE,
                                      record_id=entry_id, message=CREATOR_CANNOT_POST)


def post_journal_entry(context, entry_id, *, confirm=False, acknowledge_date_warnings=False):
    """Post a draft: check it again, number it, seal it. Returns {'entry_id', 'entry_number', 'warnings',
    'reversal_entry_id', 'reversal_entry_number'} (the last two None unless the entry has an automatic reversal).

    A Human-origin post needs confirm=True (R2). Date warnings (L6, Human origin only) raise DateWarningsError
    until acknowledge_date_warnings=True; they never block an open period. An entry with auto_reverse_date also
    posts its Accrual reversal in the same transaction (L5, R47).
    """
    authorize(context, POST, record_type=RECORD_TYPE, record_id=entry_id)
    if context.origin == "Human" and confirm is not True:
        raise ValidationError("Confirm the posting first; a posted entry can only be corrected by reversing it")
    if context.origin == "Import":                     # R18: logged like any other denial
        deny(context, POST, record_type=RECORD_TYPE, record_id=entry_id, message=IMPORT_POSTED_BY_A_PERSON)
    _check_creator_may_post(context, entry_id)
    company_code = _company_code(context)
    with write_transaction(context.company_db_path, context) as conn:
        entry, period, rows, debits, overrides = _postable(conn, entry_id)
        settings = _settings(conn)
        needed = approval_document_type(conn, entry, settings, debits)
        approved_by, approved_at = _approval_gate(approvals.request_state(conn, RECORD_TYPE, entry_id), needed,
                                                  _entry_digest(conn, entry), debits,
                                                  approvals.separation_required(settings))
        warnings = []
        if context.origin == "Human" and not period["is_adjustment_period"]:
            warnings = _date_warnings(conn, entry["entry_date"], context, acknowledge_date_warnings)
        key_id, key = _active_key(conn, context)
        if overrides:                  # before sealing: the flag is part of the seal
            conn.execute(f"UPDATE journal_line SET is_control_override = 1 WHERE line_id IN "
                         f"({', '.join('?' * len(overrides))})", overrides)
        number = _seal_and_post(conn, context, entry_id, company_code, key_id, key, approved_by, approved_at)
        reversal_id = reversal_number = None
        if entry["auto_reverse_date"] is not None:                       # L5, R47: same transaction, right after
            reversal_id = _insert_reversal(conn, context, entry, number, "Accrual reversal",
                                           entry_date=entry["auto_reverse_date"],
                                           period_id=_auto_reversal_period(conn, entry["auto_reverse_date"]),
                                           note=None, origin="System")
            reversal_number = _seal_and_post(conn, context, reversal_id, company_code, key_id, key)
    return {"entry_id": entry_id, "entry_number": number, "warnings": warnings,
            "reversal_entry_id": reversal_id, "reversal_entry_number": reversal_number}


def _date_warnings(conn, entry_date, context, acknowledged):
    """L6 warnings for a Human-origin post; raises DateWarningsError until they are acknowledged."""
    warnings = [w for w in periods.entry_date_warnings(conn, entry_date, context.today)
                if w["code"] in ("future", "past")]
    if warnings and not acknowledged:
        raise DateWarningsError("Check the date before posting: " + " ".join(w["message"] for w in warnings),
                                warnings)
    return warnings


def _seal_and_post(conn, context, entry_id, company_code, key_id, key, approved_by=None, approved_at=None):
    """The posting core, inside the caller's transaction: step the locked counter, chain to the head, seal the
    entry as stored, and write is_posted, the number, who and when and the four chain columns in ONE update.
    Returns the entry number. Every entry is posted through here (L4, audit design 2.5)."""
    header = dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone())
    number = _next_entry_number(conn)
    prev_hash = _chain_head(conn)
    header.update(entry_number=number, posted_by=context.user_id, posted_at=context.now,
                  approved_by=approved_by, approved_at=approved_at,
                  chain_version=ledger_chain.CHAIN_VERSION, chain_key_id=key_id)
    sealed_lines = [dict(r) for r in conn.execute(
        "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))]
    dimensions = [dict(r) for r in conn.execute(
        "SELECT d.* FROM journal_line_dimension AS d JOIN journal_line AS l ON l.line_id = d.line_id "
        "WHERE l.entry_id = ?", (entry_id,))]
    chain_hash = ledger_chain.seal(key.use_for_hmac(), company_code, prev_hash,
                                   ledger_chain.canonical_entry(header, sealed_lines, dimensions))
    # A database error here reaches write_transaction: logged, shown as SaveFailedError (R35).
    conn.execute(
        "UPDATE journal_entry SET is_posted = 1, entry_number = ?, posted_by = ?, posted_at = ?, "
        "approved_by = ?, approved_at = ?, chain_version = ?, chain_key_id = ?, chain_prev_hash = ?, "
        "chain_hash = ? WHERE entry_id = ?",
        (number, context.user_id, context.now, approved_by, approved_at, ledger_chain.CHAIN_VERSION, key_id,
         prev_hash, chain_hash, entry_id))
    _fire_posted(conn, context, header, number, sealed_lines)
    return number


def _fire_posted(conn, context, header, number, sealed_lines):
    """HA1: enabled add-ons hear of every posted entry, inside this transaction (an add-on error rolls it back,
    HA2); a Void reversal also tells them which entry it voided."""
    hooks.fire(conn, context, "entry.posted", {
        "entry_id": header["entry_id"], "entry_number": number, "entry_date": header["entry_date"],
        "source": header["source"], "origin": header["origin"], "reverses_entry_id": header["reverses_entry_id"],
        "reversal_reason": header["reversal_reason"],
        "debit_cents": sum(line["debit_cents"] for line in sealed_lines)})
    if header["reversal_reason"] == "Void":
        hooks.fire(conn, context, "entry.voided", {
            "entry_id": header["reverses_entry_id"], "void_entry_id": header["entry_id"],
            "void_entry_number": number, "entry_date": header["entry_date"]})


# --- Reversals (step 5) ---------------------------------------------------------------------------------------

def _je(number):
    return f"JE-{number:06d}"


def _auto_reversal_period(conn, reverse_date):
    """The open period for an automatic reversal date (R47); a missing or closed period refuses the post."""
    try:
        period_id = periods.resolve_entry_period(conn, reverse_date)
    except NotFoundError:
        raise PostingError(f"The automatic reversal date ({reverse_date}) has no fiscal period yet; add the fiscal "
                           "year or change the date.") from None
    period = conn.execute("SELECT name, is_closed FROM fiscal_period WHERE period_id = ?", (period_id,)).fetchone()
    if period["is_closed"]:
        raise PeriodClosedError(f"The automatic reversal date ({reverse_date}) is in {period['name']}, which is "
                                "closed; reopen it or change the date.")
    return period_id


def _reversal_description(kind, number, description):
    """R46: 'Void of JE-000012: Rent'; the person's note stays in reversal_note (see display_description)."""
    prefix = {"Accrual reversal": "Automatic reversal", "Void": "Void", "Correction": "Correction"}[kind]
    text = f"{prefix} of {_je(number)}"
    return f"{text}: {description}" if description else text


def _insert_reversal(conn, context, target, target_number, kind, *, entry_date, period_id, note, origin):
    """Insert the mirror of a posted entry as a draft reversal, inside the caller's transaction (it is posted next
    by _seal_and_post, so no reversal draft is ever left behind). Returns its entry id. The slot indexes refuse a
    second Void or Correction, also when two people act at once (R4)."""
    try:
        reversal_id = conn.execute(
            "INSERT INTO journal_entry (entry_date, period_id, reference, description, source, created_by, origin, "
            "reverses_entry_id, reversal_reason, reversal_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "RETURNING entry_id",
            (entry_date, period_id, target["reference"],
             _reversal_description(kind, target_number, target["description"]), target["source"], context.user_id,
             origin, target["entry_id"], kind, note)).fetchone()[0]
    except sqlite3.IntegrityError:
        # Lost the race for the slot (another Void or Correction committed after the plan's check): say so.
        # Anything else is a real database error, left to write_transaction (R35).
        taken = conn.execute("SELECT 1 FROM journal_entry WHERE reverses_entry_id = ? AND reversal_reason IN "
                             "('Void', 'Correction')", (target["entry_id"],)).fetchone()
        if kind != "Accrual reversal" and taken is not None:
            raise PostingError(f"{_je(target_number)} has already been voided or corrected.") from None
        raise
    columns = ("entry_id", "debit_cents", "credit_cents") + MIRRORED_LINE_FIELDS
    insert = (f"INSERT INTO journal_line ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))}) "
              "RETURNING line_id")
    pairs = []
    for line in conn.execute("SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                             (target["entry_id"],)).fetchall():
        values = (reversal_id, line["credit_cents"], line["debit_cents"]) + tuple(
            line[field] for field in MIRRORED_LINE_FIELDS)
        pairs.append((line["line_id"], conn.execute(insert, values).fetchone()[0]))
    _copy_dimensions(conn, pairs)
    _check_mirror(conn, target["entry_id"], reversal_id, target_number)
    return reversal_id


def void_document_entry(conn, context, entry_id, *, entry_date, note):
    """Post a Void reversal of a document's own entry inside the caller's write transaction (R59: an allocation's
    application entry, when the allocation is released). It does not authorize: the calling document service has.
    The reversal mirrors every line, clearing ids included, is never dated before the original (R41), goes into an
    open period and needs no approval. Returns the reversal's entry id."""
    note = _text(note, "note")
    if not note:
        raise ValidationError("Say why in the note, so the reason stays with the entry.")
    _iso_date(entry_date, "date")
    target = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
    if target is None or not target["is_posted"]:
        raise ValidationError("Only a posted entry can be voided")
    if target["is_void"] or _slot_taken(conn, entry_id):
        raise PostingError(f"{_je(target['entry_number'])} has already been voided or corrected.")
    if entry_date < target["entry_date"]:
        raise ValidationError(f"The void cannot be dated before {_je(target['entry_number'])} "
                              f"({target['entry_date']}); choose {target['entry_date']} or later")
    period_id = _open_period(conn, entry_date, None)
    reversal_id = _insert_reversal(conn, context, target, target["entry_number"], "Void", entry_date=entry_date,
                                   period_id=period_id, note=note, origin=context.origin)
    key_id, key = _active_key(conn, context)
    _seal_and_post(conn, context, reversal_id, _company_code(context), key_id, key)
    return reversal_id


def _copy_dimensions(conn, pairs):
    """Copy every dimension of each original line onto its mirror line, verbatim (R45; never re-resolved, JD1)."""
    for old_id, new_id in pairs:
        for dim in conn.execute("SELECT dimension_type_id, dimension_value_id FROM journal_line_dimension "
                                "WHERE line_id = ?", (old_id,)).fetchall():
            conn.execute("INSERT INTO journal_line_dimension (line_id, dimension_type_id, dimension_value_id) "
                         "VALUES (?, ?, ?)", (new_id, dim["dimension_type_id"], dim["dimension_value_id"]))


def _mirror_shape(conn, entry_id, swap):
    shape = []
    for line in conn.execute("SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                             (entry_id,)).fetchall():
        dims = sorted((d["dimension_type_id"], d["dimension_value_id"]) for d in conn.execute(
            "SELECT dimension_type_id, dimension_value_id FROM journal_line_dimension WHERE line_id = ?",
            (line["line_id"],)))
        sides = (line["credit_cents"], line["debit_cents"]) if swap else (line["debit_cents"], line["credit_cents"])
        shape.append((sides, tuple(line[field] for field in MIRRORED_LINE_FIELDS), tuple(dims)))
    return shape


def _check_mirror(conn, original_id, reversal_id, original_number):
    """R45: the reversal mirrors the original line by line, dimensions and flags included. The baseline trigger
    compares the line keys only, so the service checks the whole line (H4)."""
    if _mirror_shape(conn, original_id, swap=True) != _mirror_shape(conn, reversal_id, swap=False):
        raise PostingError(f"The reversal does not mirror {_je(original_number)}; nothing was posted.")


def _slot_taken(conn, entry_id):
    """A Void or Correction of this entry exists (they share one slot, R4)."""
    return conn.execute("SELECT 1 FROM journal_entry WHERE reverses_entry_id = ? "
                        "AND reversal_reason IN ('Void', 'Correction')", (entry_id,)).fetchone() is not None


def _reversal_period(conn, entry_date, target):
    """(period id, period row) for a reversal of target dated entry_date. A reversal dated its target's own date in
    adjustment period 13 or 14 belongs to that period, so every report basis nets to zero (A1, R48); any other date
    takes the month period that holds it."""
    target_period = conn.execute("SELECT period_id, name, is_closed, is_adjustment_period FROM fiscal_period "
                                 "WHERE period_id = ?", (target["period_id"],)).fetchone()
    if entry_date == target["entry_date"] and target_period["is_adjustment_period"]:
        return target_period["period_id"], target_period
    try:
        period_id = periods.resolve_entry_period(conn, entry_date)
    except NotFoundError:
        raise PostingError(f"There is no fiscal period for {entry_date} yet; add the fiscal year or choose another "
                           "date.") from None
    period = conn.execute("SELECT period_id, name, is_closed, is_adjustment_period FROM fiscal_period "
                          "WHERE period_id = ?", (period_id,)).fetchone()
    return period_id, period


def void_entry(context, entry_id, *, note=None, entry_date=None, confirm=False, acknowledge_date_warnings=False):
    """Void a posted entry: post its mirror as a Void reversal; the original is marked void (R40-R46).

    The Void is dated the original's date unless a later date is given (R41). An accrual that has an automatic
    reversal is voided with it, each Void on its target's date, or not at all (R4). Returns {'entry_id' and
    'entry_number' (the Void of the entry itself), 'voided_entry_ids', 'warnings'}.
    """
    return _reverse(context, entry_id, "Void", note, entry_date, confirm, acknowledge_date_warnings)


def reverse_entry(context, entry_id, *, note=None, entry_date=None, confirm=False, acknowledge_date_warnings=False):
    """Correct a posted entry: post its mirror as a Correction. The original stays standing and the person enters
    the corrected entry as a new draft (R40-R46). Dated today unless another date on or after the original's is
    given (R41). Returns the same shape as void_entry, with an empty 'voided_entry_ids'."""
    return _reverse(context, entry_id, "Correction", note, entry_date, confirm, acknowledge_date_warnings)


def _reverse(context, entry_id, kind, note, entry_date, confirm, acknowledge_date_warnings):
    """Void or Correction. Only je.reverse and confirm (R2, R8, R42); rule 10's order: authorize, then the write."""
    authorize(context, REVERSE, record_type=RECORD_TYPE, record_id=entry_id)
    if context.origin != "Human":                      # Agent is refused by authorize (je.reverse is not allowed)
        deny(context, REVERSE, record_type=RECORD_TYPE, record_id=entry_id, message=ONLY_A_PERSON_REVERSES)
    word = "void" if kind == "Void" else "correction"
    if confirm is not True:
        raise ValidationError(f"Confirm the {word} first; it is posted at once and cannot be edited")
    note = _text(note, "note")
    if not note:
        raise ValidationError("Say why in the note, so the reason stays with the entry.")
    if entry_date is not None:
        _iso_date(entry_date, "date")
    company_code = _company_code(context)
    with write_transaction(context.company_db_path, context) as conn:
        target = conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
        plan = _reversal_plan(conn, context, target, kind, word, entry_date)
        warnings = []
        for _, _, day, period in plan:
            if period["is_adjustment_period"]:             # R12: no date warnings in period 13 or 14
                continue
            for warning in _date_warnings(conn, day, context, acknowledge_date_warnings):
                if warning not in warnings:
                    warnings.append(warning)
        key_id, key = _active_key(conn, context)
        posted = []
        for row, row_number, day, period in plan:
            reversal_id = _insert_reversal(conn, context, row, row_number, kind, entry_date=day,
                                           period_id=period["period_id"], note=note, origin="Human")
            posted.append((reversal_id, _seal_and_post(conn, context, reversal_id, company_code, key_id, key)))
    voided = [row["entry_id"] for row, _, _, _ in plan] if kind == "Void" else []
    return {"entry_id": posted[0][0], "entry_number": posted[0][1], "voided_entry_ids": voided,
            "warnings": warnings}


def _reversal_plan(conn, context, target, kind, word, entry_date):
    """Every check on the target, then [(row to reverse, its number, the reversal's date, its period row)] in
    posting order."""
    if target is None:
        raise NotFoundError("That journal entry does not exist")
    if not target["is_posted"]:
        raise PostingError("Only a posted entry can be voided or corrected; change or delete the draft instead.")
    number = target["entry_number"]
    if target["reverses_entry_id"] is not None:
        if target["reversal_reason"] == "Accrual reversal":
            original = _je(_entry_number(conn, target["reverses_entry_id"]))
            raise PostingError(f"{_je(number)} is the automatic reversal of {original}; void {original} and both "
                               "are voided together.")
        raise PostingError(f"{_je(number)} is a reversal; enter a new entry to change its effect.")        # R43
    if target["is_void"]:
        raise PostingError(f"{_je(number)} is already void.")
    if target["source"] not in REVERSIBLE_SOURCES:                                                      # R40
        made_by, document = DOCUMENT_SOURCE_WORDS.get(target["source"], ("a document", "document"))
        raise PostingError(f"This entry was made by {made_by}; void the {document} instead.")
    if _slot_taken(conn, target["entry_id"]):
        raise PostingError(f"{_je(number)} has already been voided or corrected.")
    auto = conn.execute("SELECT * FROM journal_entry WHERE reverses_entry_id = ? "
                        "AND reversal_reason = 'Accrual reversal'", (target["entry_id"],)).fetchone()
    if auto is None:
        day = entry_date or (target["entry_date"] if kind == "Void" else context.today)
        if day < target["entry_date"]:
            raise ValidationError(f"A {word} cannot be dated before the entry it reverses ({target['entry_date']}).")
        _, period = _reversal_period(conn, day, target)
        if period["is_closed"] and period["is_adjustment_period"]:        # R48: it stays there, never moves
            raise PeriodClosedError(f"{period['name']} is closed; reopen it with a reason, or date the {word} in "
                                    "the next fiscal year.")
        if period["is_closed"]:
            raise PeriodClosedError(f"{period['name']} is closed; reopen it or choose a date in an open period")
        return [(target, number, day, period)]
    if kind == "Correction":                                                                            # R44
        raise PostingError(f"{_je(number)} has an automatic reversal ({_je(auto['entry_number'])}); void "
                           f"{_je(number)} and both are voided together, then enter a new accrual.")
    if entry_date is not None:
        raise ValidationError("An accrual and its automatic reversal are each voided on their own date; leave the "
                              "date empty.")
    plan = []                                                                                  # R4, R41
    for row, row_number in ((target, number), (auto, auto["entry_number"])):
        _, period = _reversal_period(conn, row["entry_date"], row)
        if period["is_closed"]:
            raise PeriodClosedError(f"{_je(number)} and its automatic reversal {_je(auto['entry_number'])} are "
                                    f"voided together, and {period['name']} is closed; reopen it first.")
        plan.append((row, row_number, row["entry_date"], period))
    return plan


def _entry_number(conn, entry_id):
    return conn.execute("SELECT entry_number FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()[0]
