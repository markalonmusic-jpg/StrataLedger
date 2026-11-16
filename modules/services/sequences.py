"""Number sequences: bill vouchers and the invoice and credit memo series.

next_voucher_number takes the caller's connection and must run inside the caller's write transaction, so a
number and the bill that uses it commit (or roll back) together. Numbers may have gaps when a draft is
deleted but are never issued twice (decision 1.3). Journal entry numbers are separate (gapless, assigned at
posting) and live with the ledger service.
"""
import re

from modules.services.errors import ValidationError

VOUCHER_PREFIX = "VCH"


def next_voucher_number(conn):
    """The next bill voucher number, 'VCH-1001' and up."""
    number = conn.execute(
        "UPDATE voucher_sequence SET last_number = last_number + 1 WHERE id = 1 RETURNING last_number").fetchone()[0]
    return f"{VOUCHER_PREFIX}-{number}"


DEFAULT_PREFIXES = {"Invoice": "INV-", "Credit Memo": "CM-"}     # decision R6


def _series_problem(series, issue_date, ph_tax):
    """Why this active series cannot number a document dated issue_date, or None."""
    if ph_tax and series["registered_to"] is None:
        return (f"The {series['prefix']} series is not registered, and a company with the Philippines tax add-on "
                "numbers only from a registered series; register one before you send this document")
    if series["valid_until"] is not None and issue_date > series["valid_until"]:
        return (f"The {series['prefix']} series expired on {series['valid_until']}; register a new series before "
                "you send this document")
    if series["registered_to"] is not None and series["last_number"] + 1 > series["registered_to"]:
        return (f"The {series['prefix']} series is used up (it ends at {series['registered_to']}); register a new "
                "series before you send this document")
    return None


def next_invoice_number(conn, context, document_type, *, issue_date):
    """The next number of an invoice or credit memo dated issue_date, from its series, inside the caller's write
    transaction.

    Gapless: the series counter moves by one and the number commits (or rolls back) with the document (section 0).
    The first active series that can number the document is used (oldest first). With no active series, the default
    unregistered series is created (R6), except for a company with the Philippines tax add-on, which numbers only
    from a registered series. A registered series stops at its last number, and no series numbers a document dated
    after its valid-until date (the leave-Draft trigger checks the same date). Returns {'series_id',
    'sequence_number', 'invoice_number'}.
    """
    if document_type not in DEFAULT_PREFIXES:
        raise ValidationError("Numbers come from a series for an Invoice or Credit Memo only")
    if not isinstance(issue_date, str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", issue_date):
        raise ValidationError("The issue date must be a date like 2026-03-06")
    ph_tax = conn.execute("SELECT 1 FROM company_addon WHERE addon_key = 'ph_tax' AND enabled = 1").fetchone() is not None
    candidates = conn.execute(
        "SELECT series_id, prefix, last_number, registered_to, valid_until FROM invoice_series "
        "WHERE document_type = ? AND is_active = 1 ORDER BY series_id", (document_type,)).fetchall()
    series, first_problem = None, None
    for candidate in candidates:
        problem = _series_problem(candidate, issue_date, ph_tax)
        if problem is None:
            series = candidate
            break
        first_problem = first_problem or problem
    if series is None:
        if first_problem:
            raise ValidationError(first_problem)
        if ph_tax:
            raise ValidationError(f"Register an invoice series for {document_type.lower()}s before you send one")
        series_id = conn.execute(
            "INSERT INTO invoice_series (document_type, prefix) VALUES (?, ?) RETURNING series_id",
            (document_type, DEFAULT_PREFIXES[document_type])).fetchone()[0]
        series = conn.execute("SELECT series_id, prefix, last_number, registered_to, valid_until FROM invoice_series "
                              "WHERE series_id = ?", (series_id,)).fetchone()
    number = series["last_number"] + 1
    conn.execute("UPDATE invoice_series SET last_number = ? WHERE series_id = ?", (number, series["series_id"]))
    return {"series_id": series["series_id"], "sequence_number": number,
            "invoice_number": f"{series['prefix']}{number:06d}"}
