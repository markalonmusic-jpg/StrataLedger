"""Payment and credit allocation, Phase 2.5 step 7 (decisions R7, B2, B4, B6, RP11, R56-R58).

An allocation applies a payment or a credit memo (the source) to an invoice or bill (the target). It is the
subledger link; the ledger side is the clearing groups (R57): every open item (an invoice's or bill's AR/AP line, a
credit memo's, a payment's unapplied remainder) opens a group whose id is its own line id, and the lines that settle
it carry the same id, so a group that nets to zero is settled.

* allocate(context, ...) checks the amounts, contact, side, statuses and the applied date, authorizes the existing
  receive or pay permission (R56) and writes the allocation. A draft source writes the row only: its posting splits
  its AR/AP side per allocation (clearing_lines, Phase 4). A posted source cannot have its lines changed, so a
  zero-net application entry moves the amount from the source's group to the target's (R58).
* release_allocations(conn, context, ...) runs inside the void of the payment or credit memo: once the source's
  entry is voided (RP11) it posts the opposite of every application entry, stamps the release and reopens a Paid
  target.
* open_item and clearing_lines are the read helpers the invoice, bill and payment posting services use (R57).
"""
import re
from datetime import date

from modules.services import authz, ledger, money, periods
from modules.services.authz import authorize
from modules.services.errors import NotFoundError, PeriodClosedError, ValidationError
from modules.services.tx import read_connection, write_transaction

# R56: the receive and pay permissions cover applying payments and credits on their side.
SIDE_PERMISSION = {"Sales": "payment.receive", "Purchase": "payment.make"}
CONTROL_TYPE = {"Sales": "AR", "Purchase": "AP"}
LOCK_AREA = {"Sales": "Sales", "Purchase": "Purchases"}
TARGET_TYPE = {"Sales": "Invoice", "Purchase": "Bill"}
OPEN_WORD = {"Sales": "receivable", "Purchase": "payable"}
ISO_DATE = re.compile(r"\d{4}-\d\d-\d\d")


# --- reading the documents -------------------------------------------------------------------------------------

def open_item(conn, entry_id, side):
    """The line of a document's entry that opened its clearing group: on an AR (Sales) or AP (Purchase) control
    account, with clearing_id equal to its own line id. Returns {'line_id', 'account_id', 'clearing_id'} or None."""
    if entry_id is None:
        return None
    row = conn.execute(
        "SELECT l.line_id, l.account_id, l.clearing_id FROM journal_line AS l "
        "JOIN account AS a ON a.account_id = l.account_id "
        "WHERE l.entry_id = ? AND l.clearing_id = l.line_id AND a.control_type = ? ORDER BY l.line_id LIMIT 1",
        (entry_id, CONTROL_TYPE[side])).fetchone()
    return dict(row) if row else None


def _ref(value, kinds, message):
    if (not isinstance(value, (tuple, list)) or len(value) != 2 or value[0] not in kinds
            or isinstance(value[1], bool) or not isinstance(value[1], int)):
        raise ValidationError(message)
    return value[0], value[1]


def _entry_is_void(conn, entry_id):
    if entry_id is None:
        return False
    row = conn.execute("SELECT is_void FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()
    return bool(row and row["is_void"])


def _live_allocated(conn, column, record_id):
    return conn.execute(f"SELECT COALESCE(SUM(amount_applied_cents), 0) FROM payment_allocation "
                        f"WHERE {column} = ? AND released_at IS NULL", (record_id,)).fetchone()[0]


def _source(conn, source):
    kind, record_id = _ref(source, ("payment", "credit_memo"), "Choose the payment or credit memo to apply")
    if kind == "payment":
        row = conn.execute("SELECT * FROM payment WHERE payment_id = ?", (record_id,)).fetchone()
        if row is None:
            raise NotFoundError("That payment does not exist")
        if row["direction"] not in ("Received", "Made"):
            raise ValidationError("Set whether the payment was received or made before you apply it")
        side = "Sales" if row["direction"] == "Received" else "Purchase"
        return {"kind": kind, "id": record_id, "side": side, "contact_id": row["contact_id"],
                "date": row["payment_date"], "total": row["amount_cents"], "entry_id": row["entry_id"],
                "column": "payment_id", "label": "the payment", "noun": "payment"}
    row = conn.execute("SELECT * FROM invoice WHERE invoice_id = ? AND invoice_type = 'Credit Memo'",
                       (record_id,)).fetchone()
    if row is None:
        raise ValidationError("Choose the payment or credit memo to apply")
    side = row["ledger_side"]
    noun = "credit memo" if side == "Sales" else "vendor credit"
    return {"kind": kind, "id": record_id, "side": side, "contact_id": row["contact_id"], "date": row["issue_date"],
            "total": row["total_cents"], "entry_id": row["entry_id"], "column": "credit_memo_id",
            "label": f"the {noun}", "noun": noun, "status": row["status"]}


def _target(conn, target):
    _, record_id = _ref(target, ("invoice",), "Choose the invoice or bill to apply it to")
    row = conn.execute("SELECT * FROM invoice WHERE invoice_id = ? AND invoice_type IN ('Invoice', 'Bill')",
                       (record_id,)).fetchone()
    if row is None:
        raise ValidationError("Choose the invoice or bill to apply it to")
    noun = "invoice" if row["invoice_type"] == "Invoice" else "bill"
    number = row["invoice_number"]
    return {"id": record_id, "side": row["ledger_side"], "type": row["invoice_type"], "contact_id": row["contact_id"],
            "date": row["issue_date"], "status": row["status"], "entry_id": row["entry_id"],
            "open_cents": row["total_cents"] - row["retainage_cents"] - _live_allocated(conn, "invoice_id", record_id),
            "label": f"{noun} {number}" if number else f"the {noun}", "noun": noun}


# --- the rules -------------------------------------------------------------------------------------------------

def _amount(amount_cents):
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValidationError("The amount to apply must be a positive amount in whole cents")
    return amount_cents


def _applied_date(value):
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise ValidationError("The applied date must be a date like 2026-03-06")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValidationError("The applied date must be a date like 2026-03-06") from None
    return value


def _check_period(conn, applied_date, side):
    """The applied date is in an open period and the area is not locked (the closed-period integrity rule)."""
    period_id = periods.resolve_entry_period(conn, applied_date)
    period = conn.execute("SELECT name, is_closed FROM fiscal_period WHERE period_id = ?", (period_id,)).fetchone()
    if period["is_closed"]:
        raise PeriodClosedError(f"{period['name']} is closed; choose an applied date in an open period")
    area = LOCK_AREA[side]
    if conn.execute("SELECT 1 FROM fiscal_period_lock WHERE period_id = ? AND area = ? AND is_locked = 1",
                    (period_id, area)).fetchone():
        raise ValidationError(f"{area} is locked for {period['name']}; choose a later applied date or ask an "
                              "Admin to unlock it")


def _plan(conn, source, target, amount_cents, applied_date):
    """Everything allocate checks, read inside the given connection. Returns the plan or raises."""
    src = _source(conn, source)
    tgt = _target(conn, target)
    side = src["side"]
    if tgt["type"] != TARGET_TYPE[side]:
        kind = "received" if side == "Sales" else "made"
        what = f"A payment {kind}" if src["kind"] == "payment" else f"A {src['noun']}"
        # The target is on the other side, which the caller may not see (R56), so the sentence does not name it.
        raise ValidationError(f"{what} applies to {'an invoice' if side == 'Sales' else 'a bill'}; choose one")
    if src["contact_id"] != tgt["contact_id"]:
        raise ValidationError(f"{src['label'].capitalize()} and {tgt['label']} must be for the same customer or "
                              "vendor")
    if tgt["status"] == "Draft" or tgt["entry_id"] is None:
        raise ValidationError(f"{tgt['label'].capitalize()} has not been sent yet; send it before you apply a "
                              f"{src['noun']}")
    if tgt["status"] == "Void" or _entry_is_void(conn, tgt["entry_id"]):
        raise ValidationError(f"{tgt['label'].capitalize()} is void; it cannot take a {src['noun']}")
    if tgt["status"] == "Paid":
        raise ValidationError(f"{tgt['label'].capitalize()} is already paid")
    target_item = open_item(conn, tgt["entry_id"], side)
    if target_item is None:
        raise ValidationError(f"{tgt['label'].capitalize()} has no open {OPEN_WORD[side]} line to match; it was "
                              "posted without one")
    if src.get("status") == "Void" or _entry_is_void(conn, src["entry_id"]):
        raise ValidationError(f"{src['label'].capitalize()} was voided; it cannot be applied")
    source_item = None
    if src["entry_id"] is not None:
        source_item = open_item(conn, src["entry_id"], side)
        if source_item is None:
            raise ValidationError(f"{src['label'].capitalize()} has no unapplied {OPEN_WORD[side]} line to apply")
    unapplied = src["total"] - _live_allocated(conn, src["column"], src["id"])
    if amount_cents > unapplied:
        raise ValidationError(f"Only {money.text(unapplied)} of {src['label']} is unapplied; apply that much or "
                              "less")
    if amount_cents > tgt["open_cents"]:
        raise ValidationError(f"Only {money.text(tgt['open_cents'])} is open on {tgt['label']}; apply that much or "
                              "less")
    for document, name in ((src, src["label"]), (tgt, tgt["label"])):
        if applied_date < document["date"]:
            raise ValidationError(f"The applied date is before the date of {name} ({document['date']}); choose "
                                  "a later date")
    _check_period(conn, applied_date, side)
    return {"side": side, "source": src, "target": tgt, "source_item": source_item, "target_item": target_item}


# --- writing ---------------------------------------------------------------------------------------------------

def _post_application(conn, context, entry_date, description, lines):
    """R58, R59: the application entry is a system consequence of the allocation, so document approval does not
    gate it (as the R47 automatic reversal)."""
    return ledger.create_document_entry(conn, context.as_system(), source="Payment", entry_date=entry_date,
                                        lines=lines, description=description, post=True,
                                        exempt_from_approval=True)["entry_id"]


def _source_side(conn, source):
    """Only the side of the source (Sales or Purchase), read before authorizing so nothing else is disclosed."""
    kind, record_id = _ref(source, ("payment", "credit_memo"), "Choose the payment or credit memo to apply")
    if kind == "payment":
        row = conn.execute("SELECT direction FROM payment WHERE payment_id = ?", (record_id,)).fetchone()
        if row is None or row["direction"] not in ("Received", "Made"):
            raise ValidationError("Choose the payment or credit memo to apply")
        return "Sales" if row["direction"] == "Received" else "Purchase"
    row = conn.execute("SELECT ledger_side FROM invoice WHERE invoice_id = ? AND invoice_type = 'Credit Memo'",
                       (record_id,)).fetchone()
    if row is None:
        raise ValidationError("Choose the payment or credit memo to apply")
    return row["ledger_side"]


def _application_lines(plan, amount_cents):
    """Sales: Dr the source's group, Cr the target's. Purchase: Dr the target's group, Cr the source's."""
    src_item, tgt_item = plan["source_item"], plan["target_item"]
    debit, credit = (src_item, tgt_item) if plan["side"] == "Sales" else (tgt_item, src_item)
    contact = plan["target"]["contact_id"]
    return [{"account_id": debit["account_id"], "debit_cents": amount_cents, "contact_id": contact,
             "clearing_id": debit["clearing_id"]},
            {"account_id": credit["account_id"], "credit_cents": amount_cents, "contact_id": contact,
             "clearing_id": credit["clearing_id"]}]


def _settle_status(conn, invoice_id):
    """B2: an invoice or bill whose net due (total - retainage - live allocations) is zero is Paid."""
    row = conn.execute("SELECT status, total_cents, retainage_cents FROM invoice WHERE invoice_id = ?",
                       (invoice_id,)).fetchone()
    due = row["total_cents"] - row["retainage_cents"] - _live_allocated(conn, "invoice_id", invoice_id)
    if due == 0 and row["status"] in ("Sent", "In pay run"):
        conn.execute("UPDATE invoice SET status = 'Paid' WHERE invoice_id = ?", (invoice_id,))
        return "Paid"
    if due > 0 and row["status"] == "Paid":
        conn.execute("UPDATE invoice SET status = 'Sent' WHERE invoice_id = ?", (invoice_id,))
        return "Sent"
    return row["status"]


CANNOT_APPLY = ("Your role does not allow you to apply payments or credits; ask an Admin to add receiving or "
                "making payments to your role.")


def allocate(context, *, source, target, amount_cents, applied_date):
    """Apply a payment or credit memo (source) to an invoice or bill (target).

    source is ("payment", payment_id) or ("credit_memo", invoice_id); target is ("invoice", invoice_id) for an
    invoice or a bill. Returns {'allocation_id', 'application_entry_id' (None for a draft source),
    'target_status'}.
    """
    if context.origin == "Agent":                 # the AI never moves money (section 0): refused before any read
        authorize(context, SIDE_PERMISSION["Sales"], record_type="payment_allocation")
    amount_cents = _amount(amount_cents)
    applied_date = _applied_date(applied_date)
    # MR6 (LOW 2): the source's side is read first, so a denial logs that side's permission. Someone holding
    # neither permission gets one sentence whether the source exists or not, and on either side.
    conn = read_connection(context.company_db_path)
    try:
        try:
            side, missing = _source_side(conn, source), None
        except ValidationError as error:
            side, missing = None, error
    finally:
        conn.close()
    if not any(authz.is_allowed(context, code) for code in SIDE_PERMISSION.values()):
        authz.check_company_access(context)       # an inactive user or no access: that sentence instead
        authz.deny(context, SIDE_PERMISSION[side or "Sales"], record_type="payment_allocation",
                   message=CANNOT_APPLY)
    if missing is not None:
        raise missing
    authorize(context, SIDE_PERMISSION[side], record_type="payment_allocation")
    with write_transaction(context.company_db_path, context) as conn:
        plan = _plan(conn, source, target, amount_cents, applied_date)
        if plan["side"] != side:
            raise ValidationError("The payment or credit memo changed while you were applying it; try again")
        src, tgt = plan["source"], plan["target"]
        entry_id = None
        if plan["source_item"] is not None:
            entry_id = _post_application(conn, context, applied_date, f"Apply {src['label']} to {tgt['label']}",
                                         _application_lines(plan, amount_cents))
        allocation_id = conn.execute(
            f"INSERT INTO payment_allocation ({src['column']}, invoice_id, amount_applied_cents, applied_date, "
            "created_by, created_at, application_entry_id) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING allocation_id",
            (src["id"], tgt["id"], amount_cents, applied_date, context.user_id, context.now, entry_id)).fetchone()[0]
        status = _settle_status(conn, tgt["id"])
    return {"allocation_id": allocation_id, "application_entry_id": entry_id, "target_status": status}


def release_allocations(conn, context, *, source, reason, entry_date):
    """Inside the void of a payment or credit memo: release each of its live allocations once (RP11).

    A posted source's entry must already be voided. An allocation that posted an application entry has that entry
    voided (a ledger Void reversal dated entry_date, R59: never before the application, in an open period whose
    area is not locked, needing no approval); every released allocation is stamped and a Paid target reopens.
    Returns {'released': [allocation ids], 'entries': [the Void reversals' entry ids]}.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("Give a reason for releasing the allocations")
    entry_date = _applied_date(entry_date)
    src = _source(conn, source)
    if src["entry_id"] is not None and not _entry_is_void(conn, src["entry_id"]):
        raise ValidationError(f"Void the {src['noun']} before releasing its allocations")
    released, entries = [], []
    for row in conn.execute(f"SELECT allocation_id, invoice_id, application_entry_id FROM payment_allocation "
                            f"WHERE {src['column']} = ? AND released_at IS NULL ORDER BY allocation_id",
                            (src["id"],)).fetchall():
        if row["application_entry_id"] is not None:
            _check_period(conn, entry_date, src["side"])
            entries.append(ledger.void_document_entry(
                conn, context.as_system(), row["application_entry_id"], entry_date=entry_date,
                note=f"Release of allocation {row['allocation_id']}: {reason.strip()}"))
        conn.execute("UPDATE payment_allocation SET released_at = ?, released_by = ?, release_reason = ? "
                     "WHERE allocation_id = ?", (context.now, context.user_id, reason.strip(), row["allocation_id"]))
        _settle_status(conn, row["invoice_id"])
        released.append(row["allocation_id"])
    return {"released": released, "entries": entries}


def clearing_lines(conn, *, side, account_id, contact_id, amount_cents, allocations):
    """R57: a payment's AR (Sales: credits) or AP (Purchase: debits) side, split into one line per allocated
    document carrying that document's clearing id, plus a remainder line that opens a new group.

    allocations is a list of (invoice_id, amount_cents). The Phase 4 payment posting service passes the result to
    ledger.create_document_entry with the payment's cash line."""
    if side not in SIDE_PERMISSION:
        raise ValidationError("The side is Sales or Purchase")
    amount_cents = _amount(amount_cents)
    key = "credit_cents" if side == "Sales" else "debit_cents"
    lines, applied = [], 0
    for invoice_id, part in allocations:
        part = _amount(part)
        row = conn.execute("SELECT entry_id FROM invoice WHERE invoice_id = ?", (invoice_id,)).fetchone()
        item = open_item(conn, row["entry_id"] if row else None, side)
        if item is None:
            raise ValidationError(f"Document {invoice_id} has no open {OPEN_WORD[side]} line to match")
        # The group is joined on the account that opened it (the document's own AR or AP account).
        lines.append({"account_id": item["account_id"], key: part, "contact_id": contact_id,
                      "clearing_id": item["clearing_id"]})
        applied += part
    if applied > amount_cents:
        raise ValidationError(f"The allocations ({money.text(applied)}) are more than the payment "
                              f"({money.text(amount_cents)})")
    if amount_cents > applied:
        lines.append({"account_id": account_id, key: amount_cents - applied, "contact_id": contact_id,
                      "clearing_id": ledger.NEW_CLEARING})
    return lines
