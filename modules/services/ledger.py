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
chain has no hole. Reversals (step 5) and automatic reversals are refused here.

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

from modules.services import approvals, keys, ledger_chain, periods
from modules.services.authz import authorize
from modules.services.errors import (
    KeyUnavailableError, NotFoundError, PeriodClosedError, PostingError, ValidationError,
)
from modules.services.tx import read_connection, write_transaction

CREATE = "je.create"
POST = "je.post"
RECORD_TYPE = "journal_entry"
IMPORT_POSTED_BY_A_PERSON = ("An imported entry is posted by a person after review; sign in and post it from the "
                             "approved entries.")
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


# --- Posting (step 3) ------------------------------------------------------------------------------------------

class DateWarningsError(ValidationError):
    """The entry date is far ahead or behind (L6); post again with acknowledge_date_warnings=True.

    `warnings` is the list from periods.entry_date_warnings: [{'code', 'message'}].
    """

    def __init__(self, message, warnings):
        super().__init__(message)
        self.warnings = warnings


def _money(cents):
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100:,}.{cents % 100:02d}"


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


def _approval_gate(state, needed, digest, debits):
    """Refuse posting unless the approvals allow it (R15, R20). Returns (approved_by, approved_at) or (None, None).

    A Pending request blocks every entry. An Approved request must match the entry now (digest, amount and, when
    approval is needed, the document type), whether or not approval is still needed.
    """
    status = state["status"] if state else None
    if status == "Pending":
        raise PostingError(f"This entry is waiting for approval (step {state['step']} of {state['steps']}); "
                           "post it when the approval is complete.")
    if status == "Approved":
        if (state["document_digest"] != digest or state["amount_cents"] != debits
                or (needed is not None and state["document_type"] != needed)):
            raise PostingError("The approved entry does not match the entry now; send it for approval again.")
        return state["approved_by"], state["approved_at"]
    if needed is None:
        return None, None
    if status == "Rejected":
        raise PostingError(f"This entry was rejected: {state['reason']}. Change it and send it for approval again.")
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
        raise PostingError("This entry has an automatic reversal date, which is not available yet; "
                           "clear the date to post it")
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
        raise PostingError(f"This entry does not balance: debits {_money(debits)}, credits {_money(credits)}")
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
    """
    authorize(context, CREATE, record_type=RECORD_TYPE, record_id=entry_id)
    conn = read_connection(context.company_db_path)
    try:
        entry, _, rows, debits, _ = _postable(conn, entry_id)
        needed = approval_document_type(conn, entry, _settings(conn), debits)
        digest = _entry_digest(conn, entry)
        state = approvals.request_state(conn, RECORD_TYPE, entry_id)
    finally:
        conn.close()
    if needed is None:
        raise ValidationError("This entry can be posted directly; it does not need approval.")
    if state is not None and state["status"] == "Pending":
        raise ValidationError("This entry is already waiting for approval.")
    if state is not None and state["status"] == "Approved" and state["document_digest"] == digest:
        raise ValidationError("This entry is already approved; post it.")
    projects = {r["project_id"] for r in rows}
    project_id = projects.pop() if len(projects) == 1 else None
    return approvals.submit_for_approval(context, needed, RECORD_TYPE, entry_id, debits,
                                         created_by=entry["created_by"], project_id=project_id,
                                         document_digest=digest)


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
                                      record_id=entry_id)


def post_journal_entry(context, entry_id, *, confirm=False, acknowledge_date_warnings=False):
    """Post a draft: check it again, number it, seal it. Returns {'entry_id', 'entry_number', 'warnings'}.

    A Human-origin post needs confirm=True (R2). Date warnings (L6, Human origin only) raise DateWarningsError
    until acknowledge_date_warnings=True; they never block an open period.
    """
    authorize(context, POST, record_type=RECORD_TYPE, record_id=entry_id)
    if context.origin == "Human" and confirm is not True:
        raise ValidationError("Confirm the posting first; a posted entry can only be corrected by reversing it")
    if context.origin == "Import":
        raise PostingError(IMPORT_POSTED_BY_A_PERSON)
    _check_creator_may_post(context, entry_id)
    company_code = _company_code(context)
    with write_transaction(context.company_db_path, context) as conn:
        entry, period, rows, debits, overrides = _postable(conn, entry_id)
        needed = approval_document_type(conn, entry, _settings(conn), debits)
        approved_by, approved_at = _approval_gate(approvals.request_state(conn, RECORD_TYPE, entry_id), needed,
                                                  _entry_digest(conn, entry), debits)
        warnings = []
        if context.origin == "Human" and not period["is_adjustment_period"]:
            warnings = [w for w in periods.entry_date_warnings(conn, entry["entry_date"], context.today)
                        if w["code"] in ("future", "past")]
            if warnings and not acknowledge_date_warnings:
                raise DateWarningsError("Check the date before posting: " + " ".join(w["message"] for w in warnings),
                                        warnings)
        key_id, key = _active_key(conn, context)
        if overrides:                  # before sealing: the flag is part of the seal
            conn.execute(f"UPDATE journal_line SET is_control_override = 1 WHERE line_id IN "
                         f"({', '.join('?' * len(overrides))})", overrides)
        number = _next_entry_number(conn)
        prev_hash = _chain_head(conn)
        header = dict(entry)
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
        try:
            conn.execute(
                "UPDATE journal_entry SET is_posted = 1, entry_number = ?, posted_by = ?, posted_at = ?, "
                "approved_by = ?, approved_at = ?, chain_version = ?, chain_key_id = ?, chain_prev_hash = ?, "
                "chain_hash = ? WHERE entry_id = ?",
                (number, context.user_id, context.now, approved_by, approved_at, ledger_chain.CHAIN_VERSION, key_id,
                 prev_hash, chain_hash, entry_id))
        except sqlite3.IntegrityError as exc:
            raise PostingError(f"The entry could not be posted: {exc}") from None
    return {"entry_id": entry_id, "entry_number": number, "warnings": warnings}
