"""Bank account details: routing and account numbers (decision C4).

The full numbers are stored in bank_account and nowhere else. Without `view.bank_details` (and always for
an Agent) they are returned masked to the last four digits. The baseline audit trigger logs only the last
four digits, so the full numbers never reach the audit log, and nothing here is ever sent to the AI.
"""
from modules.services.authz import authorize, is_allowed
from modules.services.errors import NotFoundError, ValidationError
from modules.services.tx import read_connection, write_transaction

MANAGE = "account.manage"
VIEW = "ledger.view"
SEE_UNMASKED = "view.bank_details"
HOLDER_TYPES = ("Asset", "Liability")      # a bank account, or a credit card


def _digits(value, label, low, high):
    text = (value or "").strip()
    if not (text.isascii() and text.isdigit() and low <= len(text) <= high):
        raise ValidationError(f"The {label} must be {low if low == high else f'{low} to {high}'} digits, numbers only")
    return text


def _mask(text):
    return "*" * (len(text) - 4) + text[-4:] if len(text) > 4 else text


def set_bank_details(context, account_id, *, bank_name, routing_number, account_number):
    """Save or replace the bank details of an asset (bank) or liability (card) account."""
    authorize(context, MANAGE, record_type="bank_account", record_id=account_id)
    routing = _digits(routing_number, "routing number", 9, 9)
    number = _digits(account_number, "account number", 4, 17)
    with write_transaction(context.company_db_path, context) as conn:
        account = conn.execute(
            "SELECT t.name AS type_name FROM account AS a JOIN account_type AS t ON t.type_id = a.type_id "
            "WHERE a.account_id = ?", (account_id,)).fetchone()
        if account is None:
            raise NotFoundError("That account no longer exists")
        if account["type_name"] not in HOLDER_TYPES:
            raise ValidationError("Bank details belong on a bank (asset) or card (liability) account")
        conn.execute(
            "INSERT INTO bank_account (account_id, bank_name, routing_number, account_number, account_last4) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (account_id) DO UPDATE SET bank_name = excluded.bank_name, "
            "routing_number = excluded.routing_number, account_number = excluded.account_number, "
            "account_last4 = excluded.account_last4",
            (account_id, (bank_name or "").strip() or None, routing, number, number[-4:]))


def get_bank_details(context, account_id):
    """The details, or None if none are saved. Masked unless the user holds view.bank_details."""
    authorize(context, VIEW, record_type="bank_account", record_id=account_id)
    full = is_allowed(context, SEE_UNMASKED)
    conn = read_connection(context.company_db_path)
    try:
        row = conn.execute("SELECT * FROM bank_account WHERE account_id = ?", (account_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "account_id": row["account_id"],
        "bank_name": row["bank_name"],
        "routing_number": row["routing_number"] if full else _mask(row["routing_number"]),
        "account_number": row["account_number"] if full else _mask(row["account_number"]),
        "account_last4": row["account_last4"],
        "masked": not full,
    }
