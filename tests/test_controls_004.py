"""Migration 004: High controls from docs/controls_audit.md and decisions 3-7."""
import json
import re
import sqlite3

import pytest

import modules.database as database
from tests.ledger_helpers import (
    APPROVER, USER, atomic, ensure_period, make_account, make_contact, make_entry, make_invoice,
    make_period, make_reversal, make_series, post, posted_entry, rejects, send_invoice, set_period_closed,
    set_user, type_id,
)

CONTROL_TYPES = [
    "AR", "AP", "Sales tax", "Deferral", "Retainage", "Over/under billing",
    "Employee advance", "Employee material advance", "Inventory",
    "Fixed asset cost", "Accumulated depreciation", "Depreciation expense", "Equipment cost recovery",
    "Loan principal", "Loan current portion",
]

# Every date column in the company schema and every 0/1 flag column.
DATE_COLUMNS = {
    "bank_reconciliation": ["statement_date"],
    "change_order": ["submitted_date", "approved_date", "effective_date"],
    "contract": ["contract_date", "start_date", "completion_date"],
    "deferral": ["start_date", "end_date", "cancelled_date"],
    "deferral_schedule_line": ["amort_date"],
    "fiscal_period": ["start_date", "end_date"],
    "import_batch": ["period_start", "period_end"],
    "invoice": ["issue_date", "due_date"],
    "invoice_line": ["service_start_date", "service_end_date"],
    "invoice_series": ["valid_until"],
    "journal_entry": ["entry_date"],
    "payment": ["payment_date"],
    "poc_snapshot": ["as_of_date"],
    "progress_billing_application": ["period_to_date"],
    "saas_subscription": ["next_billing_cycle_date"],
    "saas_usage_telemetry": ["logged_at_date"],
    "staged_transaction": ["txn_date"],
    "subscription": ["start_date", "end_date"],
    "time_entry": ["work_date"],
}
FLAG_COLUMNS = {
    "account": ["is_postable", "is_active", "is_deferral_account"],
    "bank_reconciliation": ["is_complete"],
    "company_addon": ["enabled"],
    "company_settings": ["manual_entry_approval"],
    "contact": ["is_customer", "is_vendor", "is_employee", "is_active"],
    "fiscal_period": ["is_closed"],
    "invoice": ["is_eis_transmitted"],
    "invoice_line": ["is_retainage_line"],
    "invoice_series": ["is_active"],
    "journal_entry": ["is_posted", "is_void"],
    "journal_line": ["is_retainage_line"],
}
AUDITED_TABLES_004 = {
    "journal_entry": ("insert", "update", "delete"),
    "fiscal_period": ("insert", "update", "delete"),
    "account": ("insert", "update", "delete"),
    "invoice": ("insert", "update", "delete"),
    "payment": ("insert", "update", "delete"),
    "payment_allocation": ("insert", "update", "delete"),
    "company_settings": ("insert", "update"),
    "invoice_series": ("insert", "update", "delete"),
    "company_addon": ("insert", "update", "delete"),
    "bank_reconciliation": ("insert", "update", "delete"),
}


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def table_sql(conn, table):
    return conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()[0]


def entry(conn, entry_id):
    return dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone())


# --- Periods (decision 4, P3, P4) ---------------------------------------------

def test_entry_needs_a_period(conn):
    ensure_period(conn, "2026-03-15")
    assert rejects(conn, "INSERT INTO journal_entry (entry_date, created_by) VALUES ('2026-03-15', 1)")


def test_period_must_cover_entry_date(conn):
    march = ensure_period(conn, "2026-03-15")
    april = ensure_period(conn, "2026-04-15")
    assert rejects(conn, "INSERT INTO journal_entry (entry_date, period_id) VALUES ('2026-03-15', ?)", (april,))
    entry_id = make_entry(conn, [], entry_date="2026-03-15", period_id=march)
    assert rejects(conn, "UPDATE journal_entry SET entry_date = '2026-04-02' WHERE entry_id = ?", (entry_id,))
    conn.execute("UPDATE journal_entry SET entry_date = '2026-04-02', period_id = ? WHERE entry_id = ?",
                 (april, entry_id))


def test_period_shape_checks(conn):
    assert rejects(conn, "INSERT INTO fiscal_period (name, start_date, end_date) VALUES ('X', '2026-03-31', '2026-03-01')")
    assert rejects(conn, "INSERT INTO fiscal_period (name, start_date, end_date, is_closed) VALUES ('X', '2026-03-01', '2026-03-31', 2)")
    assert rejects(conn, "INSERT INTO fiscal_period (name, start_date, end_date, is_closed) VALUES ('X', '2026-03-01', '2026-03-31', 1)")
    conn.execute(
        "INSERT INTO fiscal_period (name, start_date, end_date, is_closed, closed_at, closed_by) "
        "VALUES ('X', '2026-03-01', '2026-03-31', 1, '2026-04-01 09:00:00', 1)"
    )


def test_periods_are_contiguous_without_overlap(conn):
    ins = "INSERT INTO fiscal_period (name, start_date, end_date) VALUES (?, ?, ?)"
    conn.execute(ins, ("Mar", "2026-03-01", "2026-03-31"))
    assert rejects(conn, ins, ("May", "2026-05-01", "2026-05-31"))       # gap after
    assert rejects(conn, ins, ("Jan", "2026-01-01", "2026-01-31"))       # gap before
    assert rejects(conn, ins, ("Overlap", "2026-03-15", "2026-04-15"))   # overlap
    conn.execute(ins, ("Apr", "2026-04-01", "2026-04-30"))               # append
    conn.execute(ins, ("Feb", "2026-02-01", "2026-02-28"))               # prepend


def test_only_first_or_last_unused_period_can_be_deleted(conn):
    for day in ("2026-02-01", "2026-03-01", "2026-04-01"):
        ensure_period(conn, day)
    middle = ensure_period(conn, "2026-03-01")
    assert rejects(conn, "DELETE FROM fiscal_period WHERE period_id = ?", (middle,))
    conn.execute("DELETE FROM fiscal_period WHERE period_id = ?", (ensure_period(conn, "2026-04-01"),))
    conn.execute("DELETE FROM fiscal_period WHERE period_id = ?", (ensure_period(conn, "2026-02-01"),))


def test_period_dates_locked_once_used_and_inner_edges_fixed(conn):
    ensure_period(conn, "2026-03-01")
    april = ensure_period(conn, "2026-04-01")
    march = ensure_period(conn, "2026-03-01")
    assert rejects(conn, "UPDATE fiscal_period SET end_date = '2026-03-30' WHERE period_id = ?", (march,))
    conn.execute("UPDATE fiscal_period SET end_date = '2026-05-31' WHERE period_id = ?", (april,))  # outer edge
    make_entry(conn, [], entry_date="2026-04-10")
    assert rejects(conn, "UPDATE fiscal_period SET end_date = '2026-04-30' WHERE period_id = ?", (april,))
    conn.execute("UPDATE fiscal_period SET name = 'Apr-May' WHERE period_id = ?", (april,))


# --- Journal entries (T2, T3, L3) ---------------------------------------------

def test_line_needs_an_entry(conn):
    account_id = make_account(conn, "1000")
    assert rejects(conn, "INSERT INTO journal_line (entry_id, account_id, debit_cents) VALUES (NULL, ?, 100)",
                   (account_id,))


def test_new_entry_columns(conn):
    entry_id = make_entry(conn, [])
    row = entry(conn, entry_id)
    assert row["origin"] == "Human"
    assert {"entry_number", "posted_by", "posted_at", "approved_by", "approved_at"} <= set(row)
    for origin in ("Agent", "Import", "System"):
        conn.execute("UPDATE journal_entry SET origin = ? WHERE entry_id = ?", (origin, entry_id))
    assert rejects(conn, "UPDATE journal_entry SET origin = 'Robot' WHERE entry_id = ?", (entry_id,))


def test_approver_cannot_be_creator(conn):
    entry_id = make_entry(conn, [], created_by=USER)
    assert rejects(conn, "UPDATE journal_entry SET approved_by = ?, approved_at = '2026-03-15 10:00:00' "
                         "WHERE entry_id = ?", (USER, entry_id))
    assert rejects(conn, "UPDATE journal_entry SET approved_by = ? WHERE entry_id = ?", (APPROVER, entry_id))
    conn.execute("UPDATE journal_entry SET approved_by = ?, approved_at = '2026-03-15 10:00:00' WHERE entry_id = ?",
                 (APPROVER, entry_id))


@pytest.mark.parametrize("missing", ["created_by", "posted_by", "posted_at"])
def test_posting_needs_who_and_when(conn, missing):
    entry_id = make_entry(conn, [(100, 0), (0, 100)], created_by=None if missing == "created_by" else USER)
    conn.execute("UPDATE entry_number_sequence SET last_number = last_number + 1")
    values = {"posted_by": USER, "posted_at": "2026-03-15 10:00:00"}
    if missing != "created_by":
        values[missing] = None
    assert rejects(
        conn,
        "UPDATE journal_entry SET is_posted = 1, entry_number = 1, posted_by = ?, posted_at = ? WHERE entry_id = ?",
        (values["posted_by"], values["posted_at"], entry_id),
    )


def test_posted_entries_get_gapless_numbers(conn):
    first, second = posted_entry(conn), posted_entry(conn)
    assert (entry(conn, first)["entry_number"], entry(conn, second)["entry_number"]) == (1, 2)
    draft = make_entry(conn, [(100, 0), (0, 100)])
    assert rejects(conn, "UPDATE journal_entry SET entry_number = 99 WHERE entry_id = ?", (draft,))
    conn.execute("UPDATE entry_number_sequence SET last_number = last_number + 1")
    # The number must be exactly the counter; a wrong one is rejected.
    assert rejects(conn, "UPDATE journal_entry SET is_posted = 1, entry_number = 7, posted_by = 1, "
                         "posted_at = '2026-03-15 10:00:00' WHERE entry_id = ?", (draft,))
    # The counter cannot move again while number 3 is unused.
    assert rejects(conn, "UPDATE entry_number_sequence SET last_number = last_number + 1")
    conn.execute("UPDATE journal_entry SET is_posted = 1, entry_number = 3, posted_by = 1, "
                 "posted_at = '2026-03-15 10:00:00' WHERE entry_id = ?", (draft,))


def test_entry_counter_only_moves_by_one(conn):
    assert rejects(conn, "UPDATE entry_number_sequence SET last_number = 5")
    assert rejects(conn, "DELETE FROM entry_number_sequence")
    assert rejects(conn, "INSERT INTO entry_number_sequence (id, last_number) VALUES (2, 0)")


def test_posted_entry_new_columns_are_locked(conn):
    entry_id = posted_entry(conn)
    for assignment in ("entry_number = 50", "posted_by = 9", "posted_at = '2030-01-01 00:00:00'",
                       "origin = 'System'", "approved_by = 9, approved_at = '2026-03-15 10:00:00'"):
        assert rejects(conn, f"UPDATE journal_entry SET {assignment} WHERE entry_id = ?", (entry_id,))


def test_void_reversal_still_works(conn):
    original = posted_entry(conn)
    post(conn, make_reversal(conn, original, "Void"))
    assert entry(conn, original)["is_void"] == 1


# --- Chart of accounts (A1, A2, decision 5) -----------------------------------

def test_account_types_are_seeded(conn):
    rows = dict(conn.execute("SELECT name, normal_balance FROM account_type"))
    assert rows == {"Asset": "D", "Liability": "C", "Equity": "C", "Revenue": "C", "Expense": "D"}


def test_account_needs_a_type(conn):
    assert rejects(conn, "INSERT INTO account (code, name) VALUES ('1000', 'Cash')")


@pytest.mark.parametrize("control_type", CONTROL_TYPES)
def test_control_types_accepted(conn, control_type):
    make_account(conn, "C-1", control_type=control_type)


def test_unknown_control_type_rejected(conn):
    assert rejects(conn, "INSERT INTO account (code, name, type_id, control_type) VALUES ('X', 'X', ?, 'Fixed assets')",
                   (type_id(conn),))
    make_account(conn, "N-1")  # NULL = not controlled


def test_account_with_posted_history_is_locked(conn):
    entry_id = posted_entry(conn)
    account_id = conn.execute("SELECT account_id FROM journal_line WHERE entry_id = ? LIMIT 1", (entry_id,)).fetchone()[0]
    parent = make_account(conn, "P-1")
    for assignment, params in (("code = 'NEW'", ()), ("type_id = ?", (type_id(conn, "Expense"),)),
                               ("parent_id = ?", (parent,)), ("control_type = 'AR'", ())):
        assert rejects(conn, f"UPDATE account SET {assignment} WHERE account_id = ?", (*params, account_id))
    conn.execute("UPDATE account SET name = 'Renamed' WHERE account_id = ?", (account_id,))
    unused = make_account(conn, "U-1")
    conn.execute("UPDATE account SET code = 'U-2', control_type = 'AP' WHERE account_id = ?", (unused,))


def test_draft_lines_do_not_lock_an_account(conn):
    make_entry(conn, [(100, 0), (0, 100)])
    account_id = conn.execute("SELECT account_id FROM journal_line LIMIT 1").fetchone()[0]
    conn.execute("UPDATE account SET code = 'CHANGED' WHERE account_id = ?", (account_id,))


# --- Invoices (C4, C5, C8, decision 3, ledger_side) ---------------------------

def test_ledger_side_rules(conn):
    contact_id = make_contact(conn)
    ins = ("INSERT INTO invoice (invoice_type, ledger_side, contact_id, issue_date, due_date) "
           "VALUES (?, ?, ?, '2026-03-01', '2026-03-31')")
    assert rejects(conn, ins, ("Invoice", "Purchase", contact_id))
    assert rejects(conn, ins, ("Bill", "Sales", contact_id))
    assert rejects(conn, ins, ("Invoice", None, contact_id))
    assert rejects(conn, ins, (None, "Sales", contact_id))
    for args in (("Invoice", "Sales"), ("Bill", "Purchase"), ("Credit Memo", "Sales"), ("Credit Memo", "Purchase")):
        conn.execute(ins, (*args, contact_id))


def test_sales_invoice_is_numbered_from_its_series(conn):
    series_id = make_series(conn, "Invoice", "SI-")
    first, second = make_invoice(conn, status="Sent"), make_invoice(conn, status="Sent")
    rows = conn.execute(
        "SELECT series_id, sequence_number, invoice_number FROM invoice WHERE invoice_id IN (?, ?) ORDER BY invoice_id",
        (first, second),
    ).fetchall()
    assert [tuple(r) for r in rows] == [(series_id, 1, "SI-000001"), (series_id, 2, "SI-000002")]
    memo = make_invoice(conn, itype="Credit Memo", status="Sent")
    assert conn.execute("SELECT invoice_number FROM invoice WHERE invoice_id = ?", (memo,)).fetchone()[0] == "CM-000001"


def sending(conn, invoice_id, series_id, number, text=None):
    """SQL that leaves Draft with an explicit number; the counter is bumped first."""
    conn.execute("UPDATE invoice_series SET last_number = last_number + 1 WHERE series_id = ?", (series_id,))
    return ("UPDATE invoice SET status = 'Sent', series_id = ?, sequence_number = ?, invoice_number = ? "
            "WHERE invoice_id = ?", (series_id, number, text or f"SI-{number:06d}", invoice_id))


def test_number_must_equal_counter_and_format(conn):
    series_id = make_series(conn, "Invoice", "SI-")
    invoice_id = make_invoice(conn)
    sql, params = sending(conn, invoice_id, series_id, 5)
    assert rejects(conn, sql, params)                          # counter is at 1
    sql, params = ("UPDATE invoice SET status = 'Sent', series_id = ?, sequence_number = 1, invoice_number = 'SI-1' "
                   "WHERE invoice_id = ?", (series_id, invoice_id))
    assert rejects(conn, sql, params)                          # wrong text format
    conn.execute("UPDATE invoice SET status = 'Sent', series_id = ?, sequence_number = 1, invoice_number = 'SI-000001' "
                 "WHERE invoice_id = ?", (series_id, invoice_id))


def test_sales_send_needs_active_matching_series(conn):
    inactive = make_series(conn, "Invoice", "OLD-", active=0)
    memo_series = make_series(conn, "Credit Memo", "CM-")
    invoice_id = make_invoice(conn)
    with pytest.raises(sqlite3.IntegrityError):
        send_invoice(conn, invoice_id, series_id=inactive)
    with pytest.raises(sqlite3.IntegrityError):
        send_invoice(conn, invoice_id, series_id=memo_series)
    assert rejects(conn, "UPDATE invoice SET status = 'Sent', invoice_number = 'X-1' WHERE invoice_id = ?", (invoice_id,))


def test_registered_range_and_validity(conn):
    series_id = make_series(conn, "Invoice", "SI-", registered=(1001, 1002), valid_until="2026-12-31",
                            authority_ref="ATP-123")
    make_invoice(conn, status="Sent")
    make_invoice(conn, status="Sent")
    third = make_invoice(conn)
    with pytest.raises(sqlite3.IntegrityError):
        send_invoice(conn, third, series_id=series_id)       # beyond registered_to
    assert conn.execute("SELECT last_number FROM invoice_series WHERE series_id = ?", (series_id,)).fetchone()[0] == 1002
    expired = make_series(conn, "Invoice", "EX-", valid_until="2026-02-28")
    late = make_invoice(conn)
    with pytest.raises(sqlite3.IntegrityError):
        send_invoice(conn, late, series_id=expired)          # issue_date 2026-03-01 is after valid_until


def test_series_shape_and_counter(conn):
    ins = ("INSERT INTO invoice_series (document_type, prefix, registered_from, registered_to) VALUES (?, ?, ?, ?)")
    assert rejects(conn, ins, ("Bill", "B-", None, None))
    assert rejects(conn, ins, ("Invoice", None, None, None))
    assert rejects(conn, ins, ("Invoice", "SI-", 100, None))
    assert rejects(conn, ins, ("Invoice", "SI-", 200, 100))
    series_id = make_series(conn, "Invoice", "SI-")
    assert rejects(conn, "UPDATE invoice_series SET last_number = 5 WHERE series_id = ?", (series_id,))
    conn.execute("UPDATE invoice_series SET last_number = 1 WHERE series_id = ?", (series_id,))
    assert rejects(conn, "UPDATE invoice_series SET last_number = 0 WHERE series_id = ?", (series_id,))


def test_used_series_is_locked_except_counter_and_active(conn):
    series_id = make_series(conn, "Invoice", "SI-", registered=(1, 100))
    make_invoice(conn, status="Sent")
    for assignment in ("prefix = 'X-'", "registered_to = 200", "authority_ref = 'ATP-9'", "document_type = 'Credit Memo'"):
        assert rejects(conn, f"UPDATE invoice_series SET {assignment} WHERE series_id = ?", (series_id,))
    conn.execute("UPDATE invoice_series SET is_active = 0 WHERE series_id = ?", (series_id,))
    assert rejects(conn, "DELETE FROM invoice_series WHERE series_id = ?", (series_id,))


def test_draft_holds_no_number_and_numbers_never_change(conn):
    series_id = make_series(conn, "Invoice", "SI-")
    draft = make_invoice(conn)
    assert rejects(conn, "UPDATE invoice SET sequence_number = 1 WHERE invoice_id = ?", (draft,))
    sent = make_invoice(conn, status="Sent")
    for assignment in ("sequence_number = 9", "invoice_number = 'SI-000009'", "series_id = NULL", "ledger_side = 'Purchase'"):
        assert rejects(conn, f"UPDATE invoice SET {assignment} WHERE invoice_id = ?", (sent,))
    conn.execute("UPDATE invoice SET status = 'Void' WHERE invoice_id = ?", (sent,))
    assert conn.execute("SELECT invoice_number FROM invoice WHERE invoice_id = ?", (sent,)).fetchone()[0] == "SI-000001"


def test_sales_numbers_unique_company_wide(conn):
    make_series(conn, "Invoice", "SI-")
    other = make_series(conn, "Invoice", "SI-")  # same prefix, separate counter
    make_invoice(conn, status="Sent")
    clash = make_invoice(conn)
    with pytest.raises(sqlite3.IntegrityError):
        send_invoice(conn, clash, series_id=other)


def test_purchase_documents_are_numbered_manually(conn):
    bill = make_invoice(conn, itype="Bill")
    assert rejects(conn, "UPDATE invoice SET status = 'Sent' WHERE invoice_id = ?", (bill,))   # no number
    series_id = make_series(conn, "Invoice", "SI-")
    assert rejects(conn, "UPDATE invoice SET status = 'Sent', invoice_number = 'V-77', series_id = ? WHERE invoice_id = ?",
                   (series_id, bill))
    conn.execute("UPDATE invoice SET status = 'Sent', invoice_number = 'V-77' WHERE invoice_id = ?", (bill,))
    vendor_credit = make_invoice(conn, itype="Credit Memo", ledger_side="Purchase", number="VC-1", status="Sent")
    assert conn.execute("SELECT series_id FROM invoice WHERE invoice_id = ?", (vendor_credit,)).fetchone()[0] is None


def test_leaving_draft_needs_contact_and_matching_subtotal(conn):
    make_series(conn, "Invoice", "SI-")
    no_contact = conn.execute(
        "INSERT INTO invoice (invoice_type, ledger_side, issue_date, due_date) VALUES ('Invoice', 'Sales', '2026-03-01', '2026-03-31') "
        "RETURNING invoice_id"
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        send_invoice(conn, no_contact)
    wrong_subtotal = make_invoice(conn, lines=((2, 250), (1, 99)))
    conn.execute("UPDATE invoice SET subtotal_cents = 1 WHERE invoice_id = ?", (wrong_subtotal,))
    with pytest.raises(sqlite3.IntegrityError):
        send_invoice(conn, wrong_subtotal)
    conn.execute("UPDATE invoice SET subtotal_cents = 599 WHERE invoice_id = ?", (wrong_subtotal,))
    send_invoice(conn, wrong_subtotal)


def test_one_entry_one_document(conn):
    entry_id = posted_entry(conn)
    make_invoice(conn, status="Sent", entry_id=entry_id)
    with pytest.raises(sqlite3.IntegrityError):
        make_invoice(conn, status="Sent", entry_id=entry_id)
    assert rejects(conn, "INSERT INTO payment (payment_date, amount_cents, entry_id) VALUES ('2026-03-05', 10, ?)",
                   (entry_id,))
    other = posted_entry(conn)
    conn.execute("INSERT INTO payment (payment_date, amount_cents, entry_id) VALUES ('2026-03-05', 10, ?)", (other,))
    assert rejects(conn, "INSERT INTO payment (payment_date, amount_cents, entry_id) VALUES ('2026-03-05', 10, ?)", (other,))


def test_eis_flag_change_is_audit_logged(conn):
    invoice_id = make_invoice(conn, status="Sent")
    conn.execute("UPDATE invoice SET is_eis_transmitted = 1 WHERE invoice_id = ?", (invoice_id,))
    row = conn.execute(
        "SELECT old_value, new_value FROM audit_log WHERE table_name = 'invoice' AND record_id = ? "
        "ORDER BY log_id DESC LIMIT 1", (invoice_id,)
    ).fetchone()
    assert (json.loads(row[0])["is_eis_transmitted"], json.loads(row[1])["is_eis_transmitted"]) == (0, 1)


# --- Ledger keys (C11, X1) ------------------------------------------------------

@pytest.mark.parametrize("column", ["contact_id", "project_id", "cost_code_id", "deferral_id", "batch_id", "recon_id"])
def test_journal_line_tags_must_exist(conn, column):
    entry_id = make_entry(conn, [(100, 0)])
    assert rejects(conn, f"UPDATE journal_line SET {column} = 999999 WHERE entry_id = ?", (entry_id,))


def test_invoice_batch_must_exist(conn):
    invoice_id = make_invoice(conn)
    assert rejects(conn, "UPDATE invoice SET batch_id = 999999 WHERE invoice_id = ?", (invoice_id,))


def make_recon(conn):
    account_id = make_account(conn, f"BANK-{conn.execute('SELECT COUNT(*) FROM account').fetchone()[0]}")
    return conn.execute(
        "INSERT INTO bank_reconciliation (account_id, statement_date, statement_balance_cents) "
        "VALUES (?, '2026-03-31', 0) RETURNING recon_id", (account_id,)
    ).fetchone()[0]


def test_reconciling_posted_lines(conn):
    entry_id = posted_entry(conn)
    line_id = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? LIMIT 1", (entry_id,)).fetchone()[0]
    recon = make_recon(conn)
    conn.execute("UPDATE journal_line SET recon_id = ? WHERE line_id = ?", (recon, line_id))   # allowed on posted line
    assert rejects(conn, "UPDATE journal_line SET recon_id = ?, memo = 'x' WHERE line_id = ?", (recon, line_id))
    conn.execute("UPDATE bank_reconciliation SET is_complete = 1 WHERE recon_id = ?", (recon,))
    assert rejects(conn, "UPDATE journal_line SET recon_id = NULL WHERE line_id = ?", (line_id,))
    assert rejects(conn, "UPDATE bank_reconciliation SET is_complete = 0 WHERE recon_id = ?", (recon,))
    assert rejects(conn, "UPDATE bank_reconciliation SET statement_balance_cents = 5 WHERE recon_id = ?", (recon,))
    assert rejects(conn, "DELETE FROM bank_reconciliation WHERE recon_id = ?", (recon,))
    other_line = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? AND line_id != ?",
                              (entry_id, line_id)).fetchone()[0]
    assert rejects(conn, "UPDATE journal_line SET recon_id = ? WHERE line_id = ?", (recon, other_line))


def make_dimension(conn):
    type_id_ = conn.execute("INSERT INTO dimension_type (name) VALUES ('Dept') RETURNING dimension_type_id").fetchone()[0]
    values = [
        conn.execute("INSERT INTO dimension_value (dimension_type_id, code, name) VALUES (?, ?, ?) RETURNING dimension_value_id",
                     (type_id_, code, code)).fetchone()[0]
        for code in ("OPS", "SALES")
    ]
    return type_id_, values


def test_journal_line_dimensions(conn):
    dim_type, (ops, sales) = make_dimension(conn)
    entry_id = make_entry(conn, [(100, 0), (0, 100)])
    line_id = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? LIMIT 1", (entry_id,)).fetchone()[0]
    ins = "INSERT INTO journal_line_dimension (line_id, dimension_type_id, dimension_value_id) VALUES (?, ?, ?)"
    conn.execute(ins, (line_id, dim_type, ops))
    assert rejects(conn, ins, (line_id, dim_type, sales))          # one value per type
    assert rejects(conn, ins, (line_id, dim_type + 1, sales))      # value must belong to the type
    post(conn, entry_id)
    assert rejects(conn, "DELETE FROM journal_line_dimension WHERE line_id = ?", (line_id,))
    other = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? AND line_id != ?", (entry_id, line_id)).fetchone()[0]
    assert rejects(conn, ins, (other, dim_type, sales))


# --- Data quality, settings, add-ons (D1, D2, decisions 6-7) ----------------------

def test_every_date_column_is_iso_checked(conn):
    missing = []
    for table, columns in DATE_COLUMNS.items():
        sql = table_sql(conn, table)
        for column in columns:
            if not re.search(rf"\b{column}\s+IS\s+date\(\s*{column}\s*\)", sql, re.IGNORECASE):
                missing.append(f"{table}.{column}")
    assert missing == []


def test_every_flag_column_is_zero_or_one(conn):
    missing = []
    for table, columns in FLAG_COLUMNS.items():
        sql = table_sql(conn, table)
        for column in columns:
            if not re.search(rf"\b{column}\s+IN\s*\(\s*0\s*,\s*1\s*\)", sql, re.IGNORECASE):
                missing.append(f"{table}.{column}")
    assert missing == []


@pytest.mark.parametrize("sql", [
    "INSERT INTO contact (name, is_vendor) VALUES ('X', 2)",
    "INSERT INTO time_entry (contact_id, work_date, hours, wage_cents, burden_cents) VALUES (1, '03/01/2026', 1, 1, 1)",
    "INSERT INTO deferral (original_amount_cents, start_date, end_date) VALUES (100, '2026-01-01', '2026-13-01')",
    "INSERT INTO staged_transaction (txn_date) VALUES ('yesterday')",
])
def test_date_and_flag_samples(conn, sql):
    make_contact(conn)
    assert rejects(conn, sql)


def test_company_settings_defaults(conn):
    conn.execute("INSERT INTO company_settings (id, company_name, fiscal_year_start) VALUES (1, 'Co', '01-01')")
    row = dict(conn.execute("SELECT * FROM company_settings").fetchone())
    assert (row["base_currency"], row["manual_entry_approval"], row["manual_entry_approval_threshold_cents"]) == ("USD", 0, None)
    assert rejects(conn, "UPDATE company_settings SET manual_entry_approval_threshold_cents = -1")
    assert rejects(conn, "UPDATE company_settings SET manual_entry_approval_threshold_cents = 12.5")
    assert rejects(conn, "UPDATE company_settings SET base_currency = NULL")
    conn.execute("UPDATE company_settings SET manual_entry_approval = 1, manual_entry_approval_threshold_cents = 500000")


def test_no_fx_before_phase_4(conn):
    contact_id = make_contact(conn)
    assert conn.execute("SELECT dflt_value FROM pragma_table_info('invoice') WHERE name = 'currency'").fetchone()[0] is None
    assert conn.execute("SELECT dflt_value FROM pragma_table_info('payment') WHERE name = 'currency'").fetchone()[0] is None
    assert rejects(conn, "INSERT INTO invoice (invoice_type, ledger_side, contact_id, issue_date, due_date, exchange_rate) "
                         "VALUES ('Invoice', 'Sales', ?, '2026-03-01', '2026-03-31', 56.2)", (contact_id,))
    assert rejects(conn, "INSERT INTO payment (payment_date, amount_cents, exchange_rate) VALUES ('2026-03-01', 1, 0.5)")


def test_addon_tables(conn):
    conn.execute("INSERT INTO company_addon (addon_key, enabled, enabled_at, enabled_by, addon_version) "
                 "VALUES ('ph_tax', 1, '2026-03-01 00:00:00', 1, '0.1')")
    conn.execute("INSERT INTO addon_schema_version (addon_key, version) VALUES ('ph_tax', 1)")
    assert rejects(conn, "INSERT INTO addon_schema_version (addon_key, version) VALUES ('ph_tax', 1)")
    assert rejects(conn, "UPDATE company_addon SET enabled = 2")
    for table in ("company_addon", "addon_schema_version"):
        assert conn.execute(f"SELECT COUNT(*) FROM pragma_foreign_key_list('{table}')").fetchone()[0] == 0
    conn.execute("UPDATE company_addon SET enabled = 0 WHERE addon_key = 'ph_tax'")      # disable
    assert conn.execute("SELECT COUNT(*) FROM addon_schema_version").fetchone()[0] == 1   # nothing dropped


# --- Guards -------------------------------------------------------------------------

def test_no_view_filters_on_is_void(conn):
    for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view'"):
        assert "is_void" not in sql, name


def test_audit_triggers_cover_every_column_004(conn):
    missing = []
    for table, events in AUDITED_TABLES_004.items():
        columns = [c["name"] for c in conn.execute(f'PRAGMA table_info("{table}")')]
        for event in events:
            row = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name = ?",
                               (f"audit_{table}_{event}",)).fetchone()
            if row is None:
                missing.append(f"audit_{table}_{event} (no trigger)")
                continue
            for prefix in {"insert": ["NEW"], "delete": ["OLD"], "update": ["OLD", "NEW"]}[event]:
                missing += [f"audit_{table}_{event}: {prefix}.{c}" for c in columns if f"{prefix}.{c}" not in row[0]]
    assert missing == []


def test_invoice_lock_covers_new_columns(conn):
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'invoice_lock'").fetchone()[0]
    for column in ("ledger_side", "series_id", "sequence_number"):
        assert f"NEW.{column} IS OLD.{column}" in sql


def test_journal_line_lock_compares_every_column(conn):
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'journal_line_lock_update_posted'").fetchone()[0]
    for column in conn.execute("PRAGMA table_info(journal_line)"):
        if column["name"] != "recon_id":  # the one column reconciliation may change
            assert f"NEW.{column['name']} IS OLD.{column['name']}" in sql, column["name"]


@pytest.mark.parametrize("status, entry", [("Sent", False), ("Paid", False), ("Void", False),
                                           ("Covered by advance", False), ("Draft", True)])
def test_invoices_are_created_as_plain_drafts(conn, status, entry):
    """Leave-Draft rules (number, series, contact, subtotal) can't be skipped by inserting past Draft."""
    contact_id = make_contact(conn)
    entry_id = posted_entry(conn) if entry else None
    assert rejects(
        conn,
        "INSERT INTO invoice (invoice_type, ledger_side, contact_id, invoice_number, issue_date, due_date, status, entry_id) "
        "VALUES ('Invoice', 'Sales', ?, 'FAKE-1', '2026-03-01', '2026-03-31', ?, ?)",
        (contact_id, status, entry_id),
    )
