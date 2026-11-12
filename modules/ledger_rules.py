"""Pure accounting rules shared by the service layer. No database access.

Document amounts are stored positive (decision 2, docs/controls_audit.md).
The sign comes from the document type, applied only here.
"""

# Sign relative to the contact's open balance (the AR side for customer
# documents, the AP side for vendor bills): an invoice or bill increases what
# is owed, a credit memo reduces it.
DOCUMENT_SIGN = {
    "Invoice": 1,
    "Bill": 1,
    "Credit Memo": -1,
}


def signed_cents(document_type, amount_cents):
    """Return amount_cents with the sign for document_type.

    amount_cents must be a non-negative int (stored amounts are positive).
    Raises ValueError for an unknown document type or a negative amount, and
    TypeError for anything that is not an int (bool, float and str included).
    """
    if document_type not in DOCUMENT_SIGN:
        raise ValueError(f"Unknown document type: {document_type!r}")
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        raise TypeError(f"amount_cents must be an int, got {type(amount_cents).__name__}")
    if amount_cents < 0:
        raise ValueError("Stored document amounts are positive; the sign comes from the type")
    return DOCUMENT_SIGN[document_type] * amount_cents
