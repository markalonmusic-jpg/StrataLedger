"""Number sequences: bill vouchers and the invoice and credit memo series.

next_voucher_number takes the caller's connection and must run inside the caller's write transaction, so a
number and the bill that uses it commit (or roll back) together. Numbers may have gaps when a draft is
deleted but are never issued twice (decision 1.3). Journal entry numbers are separate (gapless, assigned at
posting) and live with the ledger service.
"""
from modules.services.errors import ValidationError

VOUCHER_PREFIX = "VCH"


def next_voucher_number(conn):
    """The next bill voucher number, 'VCH-1001' and up."""
    number = conn.execute(
        "UPDATE voucher_sequence SET last_number = last_number + 1 WHERE id = 1 RETURNING last_number").fetchone()[0]
    return f"{VOUCHER_PREFIX}-{number}"


DEFAULT_PREFIXES = {"Invoice": "INV-", "Credit Memo": "CM-"}     # decision R6


def next_invoice_number(conn, context, document_type):
    """The next number of an invoice or credit memo, taken from its series inside the caller's write transaction.

    Gapless: the series counter moves by one and the number commits (or rolls back) with the document (section 0).
    With no active series, the default unregistered series is created (R6), except for a company with the
    Philippines tax add-on, which must register one. A registered series stops at its last number and after its
    valid-until date (context.today). Returns {'series_id', 'sequence_number', 'invoice_number'}.
    """
    if document_type not in DEFAULT_PREFIXES:
        raise ValidationError("Numbers come from a series for an Invoice or Credit Memo only")
    series = conn.execute(
        "SELECT series_id, prefix, last_number, registered_to, valid_until FROM invoice_series "
        "WHERE document_type = ? AND is_active = 1 ORDER BY series_id LIMIT 1", (document_type,)).fetchone()
    if series is None:
        if conn.execute("SELECT 1 FROM company_addon WHERE addon_key = 'ph_tax' AND enabled = 1").fetchone():
            raise ValidationError(f"Register an invoice series for {document_type.lower()}s before you send one")
        series_id = conn.execute(
            "INSERT INTO invoice_series (document_type, prefix) VALUES (?, ?) RETURNING series_id",
            (document_type, DEFAULT_PREFIXES[document_type])).fetchone()[0]
        series = conn.execute("SELECT series_id, prefix, last_number, registered_to, valid_until FROM invoice_series "
                              "WHERE series_id = ?", (series_id,)).fetchone()
    if series["valid_until"] is not None and context.today > series["valid_until"]:
        raise ValidationError(f"The {series['prefix']} series expired on {series['valid_until']}; register a new "
                              "series before you send this document")
    number = series["last_number"] + 1
    if series["registered_to"] is not None and number > series["registered_to"]:
        raise ValidationError(f"The {series['prefix']} series is used up (it ends at {series['registered_to']}); "
                              "register a new series before you send this document")
    conn.execute("UPDATE invoice_series SET last_number = ? WHERE series_id = ?", (number, series["series_id"]))
    return {"series_id": series["series_id"], "sequence_number": number,
            "invoice_number": f"{series['prefix']}{number:06d}"}
