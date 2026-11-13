"""Rules enforced by the Phase 2 service layer, not the schema (expected to fail until then).

These are strict xfails: when Phase 2 implements a rule, its test starts
passing, pytest reports XPASS as a failure, and the marker must be removed.
The service names used here (modules.services.*) are PROPOSED; Phase 2 may
rename them, updating these tests.

Step 4 rewrote six of them against the real services (decision R25): the approval rules are in
tests/test_ledger_approvals.py, the account and controlled-account rules in tests/test_ledger_posting.py.
"""
import pytest

import modules.database as database
from tests.ledger_helpers import USER, make_invoice, make_period, posted_entry

pending = pytest.mark.xfail(strict=True, reason="Phase 2 service layer (controls audit)")


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def services():
    from modules.services import billing, errors, ledger  # noqa: F401  (Phase 2)
    return ledger, billing, errors.ServiceRuleError


@pending
def test_reversal_cannot_predate_original(conn):
    ledger, _, ServiceRuleError = services()
    original = posted_entry(conn, entry_date="2026-03-20")
    with pytest.raises(ServiceRuleError):
        ledger.reverse_entry(conn, original, reason="Void", entry_date="2026-03-10", user_id=USER)


@pending
def test_payment_cannot_be_over_allocated(conn):
    _, billing, ServiceRuleError = services()
    invoice_id = make_invoice(conn, status="Sent", lines=((1, 1000),))
    payment_id = conn.execute("INSERT INTO payment (payment_date, amount_cents) VALUES ('2026-03-05', 600) "
                              "RETURNING payment_id").fetchone()[0]
    with pytest.raises(ServiceRuleError):
        billing.allocate_payment(conn, payment_id, invoice_id=invoice_id, amount_cents=700, user_id=USER)
    billing.allocate_payment(conn, payment_id, invoice_id=invoice_id, amount_cents=600, user_id=USER)
    second = conn.execute("INSERT INTO payment (payment_date, amount_cents) VALUES ('2026-03-06', 600) "
                          "RETURNING payment_id").fetchone()[0]
    with pytest.raises(ServiceRuleError):  # invoice has only 400 open
        billing.allocate_payment(conn, second, invoice_id=invoice_id, amount_cents=500, user_id=USER)


@pending
def test_allocation_targets_exactly_one_document(conn):
    _, billing, ServiceRuleError = services()
    payment_id = conn.execute("INSERT INTO payment (payment_date, amount_cents) VALUES ('2026-03-05', 600) "
                              "RETURNING payment_id").fetchone()[0]
    with pytest.raises(ServiceRuleError):
        billing.allocate_payment(conn, payment_id, amount_cents=100, user_id=USER)


@pending
def test_reopening_a_period_needs_a_logged_reason(conn):
    ledger, _, ServiceRuleError = services()
    period_id = make_period(conn, "2026-03", "2026-03-01", "2026-03-31", closed=True)
    with pytest.raises(ServiceRuleError):
        ledger.reopen_period(conn, period_id, user_id=USER, reason="")
    ledger.reopen_period(conn, period_id, user_id=USER, reason="Late vendor bill")
    logged = conn.execute("SELECT new_value FROM audit_log WHERE table_name = 'fiscal_period' "
                          "ORDER BY log_id DESC LIMIT 1").fetchone()[0]
    assert "Late vendor bill" in logged


@pending
def test_numbering_service_assigns_next_number(conn):
    _, billing, _ = services()
    invoice_id = make_invoice(conn)
    billing.send_invoice(conn, invoice_id, user_id=USER)
    assert conn.execute("SELECT invoice_number FROM invoice WHERE invoice_id = ?", (invoice_id,)).fetchone()[0]


@pending
def test_period_is_set_from_entry_date(conn):
    ledger, _, _ = services()
    make_period(conn, "2026-03", "2026-03-01", "2026-03-31", closed=False)
    entry_id = ledger.create_entry(conn, entry_date="2026-03-15", lines=[], user_id=USER)
    assert conn.execute("SELECT period_id FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()[0]
