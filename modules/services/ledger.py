"""The general ledger service: draft journal entries (step 2) and posting (step 3) of Phase 2.5.

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

from modules.services import approvals, keys, ledger_chain, money, periods
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
LINE_FIELDS = ("account_id", "debit_cents", "credit_cents", "memo", "contact_id", "project_id", "cost_code_id",
               "external_ref")
STATES = ("draft", "posted")
# R40: entries a person may void or correct by source; a document's entry is voided through its document.
REVERSIBLE_SOURCES = (None, "Manual", "Adjustment", "Import", "Payroll", "Conversion")
DOCUMENT_SOURCE_WORDS = {"Invoice": ("an invoice", "invoice"), "Bill": ("a bill", "bill"),
                         "Payment": ("a payment", "payment"), "Deferral": ("a deferral", "deferral"),
                         "Completion": ("a percentage-of-completion entry", "percentage-of-completion entry")}
ONLY_A_PERSON_REVERSES = "Only a person can void or correct an entry; sign in and do it from the entry."
# The line fields a reversal copies as they are (debit and credit are swapped), R45.
MIRRORED_LINE_FIELDS = ("account_id", "memo", "contact_id", "project_id", "cost_code_id", "deferral_id", "batch_id",
                        "is_retainage_line", "external_ref", "is_control_override", "is_rounding_adjustment")
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


def _stored_lines(conn, entry_id):
    """The entry's lines as check_lines returns them, in order (to spot a re-save of the same lines)."""
    return [{field: row[field] for field in LINE_FIELDS} for row in conn.execute(
        f"SELECT {', '.join(LINE_FIELDS)} FROM journal_line WHERE entry_id = ? ORDER BY line_id", (entry_id,))]


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
    debits = sum(r["debit_cents"] or 0 for r in rows)
    credits = sum(r["credit_cents"] or 0 for r in rows)
    if debits != credits or debits <= 0:
        raise PostingError(f"This entry does not balance: debits {money.text(debits)}, credits {money.text(credits)}")
    overrides = _control_overrides(conn, rows, _settings(conn)) if entry["source"] in MANUAL_SOURCES else []
    return entry, period, rows, debits, overrides


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
    return number


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
