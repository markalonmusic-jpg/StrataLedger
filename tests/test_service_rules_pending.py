"""Rules enforced by the Phase 2 service layer, not the schema (expected to fail until then).

These are strict xfails: when Phase 2 implements a rule, its test starts
passing, pytest reports XPASS as a failure, and the marker must be removed.
The service names used here (modules.services.*) are PROPOSED; Phase 2 may
rename them, updating these tests.
"""
import pytest

import modules.database as database
from tests.ledger_helpers import (
    APPROVER, USER, make_account, make_entry, make_invoice, make_period, posted_entry,
)

pending = pytest.mark.xfail(strict=True, reason="Phase 2 service layer (controls audit)")


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def services():
    from modules.services import billing, errors, ledger  # noqa: F401  (Phase 2)
    return ledger, billing, errors.ServiceRuleError


def entry_on(conn, account_kwargs):
    entry_id = make_entry(conn, [])
    special = make_account(conn, "S-1", **account_kwargs)
    other = make_account(conn, "O-1")
    conn.execute("INSERT INTO journal_line (entry_id, account_id, debit_cents) VALUES (?, ?, 100)", (entry_id, special))
    conn.execute("INSERT INTO journal_line (entry_id, account_id, credit_cents) VALUES (?, ?, 100)", (entry_id, other))
    return entry_id


@pending
@pytest.mark.parametrize("account_kwargs", [{"is_postable": 0}, {"is_active": 0}])
def test_cannot_post_to_header_or_inactive_account(conn, account_kwargs):
    ledger, _, ServiceRuleError = services()
    with pytest.raises(ServiceRuleError):
        ledger.post_entry(conn, entry_on(conn, account_kwargs), user_id=USER)


@pending
def test_manual_entry_to_controlled_account_is_blocked(conn):
    """Decision 5."""
    ledger, _, ServiceRuleError = services()
    with pytest.raises(ServiceRuleError):
        ledger.post_entry(conn, entry_on(conn, {"control_type": "AR"}), user_id=USER)


@pending
def test_manual_entry_over_threshold_needs_approval(conn):
    """Decision 6: setting on, threshold 1000 cents, entry of 5000 cents with no approver."""
    ledger, _, ServiceRuleError = services()
    conn.execute("INSERT INTO company_settings (id, company_name, fiscal_year_start, manual_entry_approval, "
                 "manual_entry_approval_threshold_cents) VALUES (1, 'Co', '01-01', 1, 1000)")
    entry_id = make_entry(conn, [(5000, 0), (0, 5000)])
    with pytest.raises(ServiceRuleError):
        ledger.post_entry(conn, entry_id, user_id=USER)
    ledger.approve_entry(conn, entry_id, user_id=APPROVER)
    ledger.post_entry(conn, entry_id, user_id=USER)


@pending
@pytest.mark.parametrize("origin", ["Agent", "Import"])
def test_agent_and_import_entries_always_need_human_approval(conn, origin):
    """Decision 6: even with the approval setting off."""
    ledger, _, ServiceRuleError = services()
    entry_id = make_entry(conn, [(100, 0), (0, 100)], origin=origin)
    with pytest.raises(ServiceRuleError):
        ledger.post_entry(conn, entry_id, user_id=USER)


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
