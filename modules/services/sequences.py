"""Number sequences that are not tied to a document table.

next_voucher_number takes the caller's connection and must run inside the caller's write transaction, so a
number and the bill that uses it commit (or roll back) together. Numbers may have gaps when a draft is
deleted but are never issued twice (decision 1.3). Journal entry numbers are separate (gapless, assigned at
posting) and live with the ledger service.
"""
VOUCHER_PREFIX = "VCH"


def next_voucher_number(conn):
    """The next bill voucher number, 'VCH-1001' and up."""
    number = conn.execute(
        "UPDATE voucher_sequence SET last_number = last_number + 1 WHERE id = 1 RETURNING last_number").fetchone()[0]
    return f"{VOUCHER_PREFIX}-{number}"
