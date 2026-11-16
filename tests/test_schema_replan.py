"""STOP 1 of the consolidated baseline update (decisions RP1-RP11; docs/design.md section 10).

Schema only: every addition is a column, table, CHECK, lock, audit trigger or index in the baselines. The services
that use them come in STOP 2 (Phase 2.5 Step 7) and later steps.
"""
import re
import sqlite3

import pytest

import modules.database as database
from tests.ledger_helpers import (
    ensure_period, make_account, make_contact, make_entry, make_invoice, make_reversal, post, posted_entry,
    rejects,
)


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


@pytest.fixture
def master(tmp_path, backup_dir):
    path = tmp_path / "master.db"
    database.ensure_master_database(path)
    connection = database.get_connection(path)
    yield connection
    connection.close()


def columns(conn, table):
    return {row["name"]: row for row in conn.execute(f'PRAGMA table_info("{table}")')}


def table_sql(conn, name):
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None


def insert(conn, table, **values):
    names = ", ".join(values)
    marks = ", ".join("?" * len(values))
    return conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(values.values())).lastrowid


def insert_sql(table, **values):
    return (f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
            tuple(values.values()))


# --- payment_allocation: Step 7 columns, one source, release once (RP11) -------------------------------------

def make_payment(conn, entry_id=None, amount=1000):
    contact = make_contact(conn, "Payer")
    return conn.execute(
        "INSERT INTO payment (direction, contact_id, payment_date, amount_cents, entry_id) "
        "VALUES ('Received', ?, '2026-03-20', ?, ?) RETURNING payment_id", (contact, amount, entry_id)).fetchone()[0]


def allocation(conn, *, payment_id=None, credit_memo_id=None, invoice_id=None, amount=100, applied="2026-03-21"):
    invoice_id = invoice_id or make_invoice(conn, status="Sent")
    return insert(conn, "payment_allocation", payment_id=payment_id, credit_memo_id=credit_memo_id,
                  invoice_id=invoice_id, amount_applied_cents=amount, applied_date=applied,
                  created_by=1, created_at="2026-03-21T09:00:00+00:00")


RELEASE = ("UPDATE payment_allocation SET released_at = '2026-03-25T09:00:00+00:00', released_by = 1, "
           "release_reason = 'Payment voided' WHERE allocation_id = ?")


def test_allocation_has_the_step_7_columns(conn):
    cols = columns(conn, "payment_allocation")
    for name in ("applied_date", "credit_memo_id", "created_by", "created_at", "released_at", "released_by",
                 "release_reason"):
        assert name in cols, name
    assert cols["applied_date"]["notnull"] == 1


def test_allocation_needs_an_applied_date(conn):
    payment_id = make_payment(conn)
    invoice_id = make_invoice(conn, status="Sent")
    assert rejects(conn, *insert_sql("payment_allocation", payment_id=payment_id, invoice_id=invoice_id,
                                     amount_applied_cents=100))
    assert rejects(conn, *insert_sql("payment_allocation", payment_id=payment_id, invoice_id=invoice_id,
                                     amount_applied_cents=100, applied_date="21/03/2026"))


def test_allocation_names_exactly_one_source(conn):
    payment_id = make_payment(conn)
    memo = make_invoice(conn, itype="Credit Memo")
    invoice_id = make_invoice(conn, status="Sent")
    base = {"invoice_id": invoice_id, "amount_applied_cents": 100, "applied_date": "2026-03-21"}
    assert rejects(conn, *insert_sql("payment_allocation", **base))
    assert rejects(conn, *insert_sql("payment_allocation", payment_id=payment_id, credit_memo_id=memo, **base))
    assert not rejects(conn, *insert_sql("payment_allocation", payment_id=payment_id, **base))
    assert not rejects(conn, *insert_sql("payment_allocation", credit_memo_id=memo, **base))


def test_a_credit_memo_source_must_be_a_sales_credit_memo(conn):
    invoice_id = make_invoice(conn, status="Sent")
    other_invoice = make_invoice(conn)
    vendor_credit = make_invoice(conn, itype="Credit Memo", ledger_side="Purchase")
    base = {"invoice_id": invoice_id, "amount_applied_cents": 100, "applied_date": "2026-03-21"}
    assert rejects(conn, *insert_sql("payment_allocation", credit_memo_id=other_invoice, **base))
    assert rejects(conn, *insert_sql("payment_allocation", credit_memo_id=vendor_credit, **base))


def test_release_fields_are_all_set_or_all_empty(conn):
    allocation_id = allocation(conn, payment_id=make_payment(conn))
    assert rejects(conn, "UPDATE payment_allocation SET released_at = '2026-03-25T09:00:00+00:00' "
                         "WHERE allocation_id = ?", (allocation_id,))
    assert rejects(conn, "UPDATE payment_allocation SET released_by = 1, release_reason = 'x' "
                         "WHERE allocation_id = ?", (allocation_id,))
    # Each half of the CHECK on its own: a date and a person but no reason, a date and a reason but no person.
    assert rejects(conn, "UPDATE payment_allocation SET released_at = '2026-03-25T09:00:00+00:00', released_by = 1 "
                         "WHERE allocation_id = ?", (allocation_id,))
    assert rejects(conn, "UPDATE payment_allocation SET released_at = '2026-03-25T09:00:00+00:00', "
                         "release_reason = 'x' WHERE allocation_id = ?", (allocation_id,))
    assert not rejects(conn, RELEASE, (allocation_id,))


def test_allocations_of_a_draft_source_can_change(conn):
    allocation_id = allocation(conn, payment_id=make_payment(conn))
    assert not rejects(conn, "UPDATE payment_allocation SET amount_applied_cents = 50 WHERE allocation_id = ?",
                       (allocation_id,))
    assert not rejects(conn, "DELETE FROM payment_allocation WHERE allocation_id = ?", (allocation_id,))


@pytest.mark.parametrize("source", ["payment", "credit memo"])
def test_a_posted_source_allocation_is_released_once_and_never_deleted(conn, source):
    entry_id = posted_entry(conn)
    if source == "payment":
        allocation_id = allocation(conn, payment_id=make_payment(conn, entry_id=entry_id))
    else:
        memo = make_invoice(conn, itype="Credit Memo", status="Sent", entry_id=entry_id)
        allocation_id = allocation(conn, credit_memo_id=memo)
    assert rejects(conn, "UPDATE payment_allocation SET amount_applied_cents = 50 WHERE allocation_id = ?",
                   (allocation_id,))
    assert rejects(conn, "UPDATE payment_allocation SET applied_date = '2026-03-22' WHERE allocation_id = ?",
                   (allocation_id,))
    assert rejects(conn, "DELETE FROM payment_allocation WHERE allocation_id = ?", (allocation_id,))
    # A release that also changes the amount is not a release.
    assert rejects(conn, "UPDATE payment_allocation SET released_at = '2026-03-25T09:00:00+00:00', released_by = 1, "
                         "release_reason = 'x', amount_applied_cents = 50 WHERE allocation_id = ?", (allocation_id,))
    # RP11: release follows the void; a live posted source cannot be quietly unapplied.
    assert rejects(conn, RELEASE, (allocation_id,))
    post(conn, make_reversal(conn, entry_id, "Void"))
    assert rejects(conn, "DELETE FROM payment_allocation WHERE allocation_id = ?", (allocation_id,))
    # Each change keeps the row valid (one source, one target), so only the release-only lock can refuse it.
    other_source = (("payment_id", make_payment(conn)) if source == "payment"
                    else ("credit_memo_id", make_invoice(conn, itype="Credit Memo")))
    for column, value in (other_source, ("invoice_id", make_invoice(conn, status="Sent")),
                          ("created_by", 9), ("created_at", "2026-01-01T00:00:00+00:00"),
                          ("allocation_id", 9999), ("amount_applied_cents", 50), ("applied_date", "2026-03-22")):
        assert rejects(conn, "UPDATE payment_allocation SET released_at = '2026-03-25T09:00:00+00:00', released_by = 1, "
                             f"release_reason = 'x', {column} = ? WHERE allocation_id = ?", (value, allocation_id)), column
    conn.execute(RELEASE, (allocation_id,))
    assert rejects(conn, "UPDATE payment_allocation SET release_reason = 'changed' WHERE allocation_id = ?",
                   (allocation_id,))
    assert rejects(conn, "UPDATE payment_allocation SET released_at = NULL, released_by = NULL, "
                         "release_reason = NULL WHERE allocation_id = ?", (allocation_id,))
    assert rejects(conn, "DELETE FROM payment_allocation WHERE allocation_id = ?", (allocation_id,))


def test_a_released_deferral_allocation_keeps_its_deferral(conn):
    entry_id = posted_entry(conn)
    payment_id = make_payment(conn, entry_id=entry_id)
    deferrals = [conn.execute("INSERT INTO deferral (original_amount_cents, start_date, end_date) "
                              "VALUES (1200, '2026-03-01', '2027-02-28') RETURNING deferral_id").fetchone()[0]
                 for _ in range(2)]
    allocation_id = insert(conn, "payment_allocation", payment_id=payment_id, deferral_id=deferrals[0],
                           amount_applied_cents=100, applied_date="2026-03-21")
    post(conn, make_reversal(conn, entry_id, "Void"))
    assert rejects(conn, "UPDATE payment_allocation SET released_at = '2026-03-25T09:00:00+00:00', released_by = 1, "
                         "release_reason = 'x', deferral_id = ? WHERE allocation_id = ?", (deferrals[1], allocation_id))
    assert not rejects(conn, RELEASE, (allocation_id,))


def test_a_voided_credit_memo_cannot_be_applied(conn):
    entry_id = posted_entry(conn)
    memo = make_invoice(conn, itype="Credit Memo", status="Sent", entry_id=entry_id)
    post(conn, make_reversal(conn, entry_id, "Void"))
    invoice_id = make_invoice(conn, status="Sent")
    assert rejects(conn, *insert_sql("payment_allocation", credit_memo_id=memo, invoice_id=invoice_id,
                                     amount_applied_cents=100, applied_date="2026-03-21"))


def test_switching_an_allocation_to_a_non_credit_memo_source_is_refused(conn):
    memo = make_invoice(conn, itype="Credit Memo")
    allocation_id = allocation(conn, credit_memo_id=memo)
    sale = make_invoice(conn)
    assert rejects(conn, "UPDATE payment_allocation SET credit_memo_id = ? WHERE allocation_id = ?", (sale, allocation_id))
    vendor_credit = make_invoice(conn, itype="Credit Memo", ledger_side="Purchase")
    assert rejects(conn, "UPDATE payment_allocation SET credit_memo_id = ? WHERE allocation_id = ?",
                   (vendor_credit, allocation_id))
    other_memo = make_invoice(conn, itype="Credit Memo")
    assert not rejects(conn, "UPDATE payment_allocation SET credit_memo_id = ? WHERE allocation_id = ?",
                       (other_memo, allocation_id))


# --- ledger: entities and line clearing (RP2) ----------------------------------------------------------------

def test_company_entity_table(conn):
    cols = columns(conn, "company_entity")
    assert {"entity_id", "code", "name", "parent_entity_id", "is_active", "is_eliminations", "created_at"} <= set(cols)
    parent = insert(conn, "company_entity", code="PARENT", name="Parent Co")
    insert(conn, "company_entity", code="SUB", name="Subsidiary", parent_entity_id=parent)
    row = conn.execute("SELECT is_active, is_eliminations FROM company_entity WHERE entity_id = ?", (parent,)).fetchone()
    assert tuple(row) == (1, 0)
    assert rejects(conn, *insert_sql("company_entity", code="PARENT", name="Again"))
    assert rejects(conn, *insert_sql("company_entity", code="X", name="X", is_eliminations=2))
    assert rejects(conn, *insert_sql("company_entity", code="Y", name="Y", parent_entity_id=9999))


def test_journal_line_carries_entity_and_clearing_ids(conn):
    cols = columns(conn, "journal_line")
    assert "entity_id" in cols and "clearing_id" in cols
    fks = {row["from"]: row["table"] for row in conn.execute("PRAGMA foreign_key_list(journal_line)")}
    assert fks["entity_id"] == "company_entity"
    assert "clearing_id" not in fks


def test_draft_lines_take_a_clearing_id_and_posted_lines_keep_it(conn):
    entity = insert(conn, "company_entity", code="E1", name="Entity 1")
    entry_id = make_entry(conn, [(500, 0), (0, 500)])
    line_id = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? LIMIT 1", (entry_id,)).fetchone()[0]
    conn.execute("UPDATE journal_line SET clearing_id = 7, entity_id = ? WHERE line_id = ?", (entity, line_id))
    post(conn, entry_id)
    assert rejects(conn, "UPDATE journal_line SET clearing_id = 8 WHERE line_id = ?", (line_id,))
    assert rejects(conn, "UPDATE journal_line SET clearing_id = NULL WHERE line_id = ?", (line_id,))
    assert rejects(conn, "UPDATE journal_line SET entity_id = NULL WHERE line_id = ?", (line_id,))


def test_reconciling_a_posted_line_cannot_move_its_entity_or_clearing_group(conn):
    """recon_id is the one column reconciliation may change; the two new ids ride along only unchanged."""
    entity = insert(conn, "company_entity", code="E2", name="Entity 2")
    entry_id = make_entry(conn, [(500, 0), (0, 500)])
    line_id, account_id = conn.execute("SELECT line_id, account_id FROM journal_line WHERE entry_id = ? LIMIT 1",
                                       (entry_id,)).fetchone()
    conn.execute("UPDATE journal_line SET clearing_id = 7, entity_id = ? WHERE line_id = ?", (entity, line_id))
    post(conn, entry_id)
    recon = insert(conn, "bank_reconciliation", account_id=account_id, statement_date="2026-03-31",
                   statement_balance_cents=0)
    assert rejects(conn, "UPDATE journal_line SET recon_id = ?, entity_id = NULL WHERE line_id = ?", (recon, line_id))
    assert rejects(conn, "UPDATE journal_line SET recon_id = ?, clearing_id = 8 WHERE line_id = ?", (recon, line_id))
    assert not rejects(conn, "UPDATE journal_line SET recon_id = ? WHERE line_id = ?", (recon, line_id))


def test_open_item_index_and_account_marker(conn):
    cols = columns(conn, "account")
    assert cols["track_clearing_id"]["notnull"] == 1
    account_id = make_account(conn, "9100")
    assert conn.execute("SELECT track_clearing_id FROM account WHERE account_id = ?", (account_id,)).fetchone()[0] == 0
    assert rejects(conn, "UPDATE account SET track_clearing_id = 2 WHERE account_id = ?", (account_id,))
    indexed = [tuple(r["name"] for r in conn.execute(f"PRAGMA index_info('{ix['name']}')"))
               for ix in conn.execute("PRAGMA index_list(journal_line)")]
    assert ("account_id", "clearing_id") in indexed


# --- contacts and vendors (RP1) ------------------------------------------------------------------------------

CONTACT_COLUMNS = ("customer_type", "first_name", "last_name", "tax_exempt_status", "exemption_reason",
                   "exemption_cert_no", "exemption_expires_at", "bank_details_on_file", "bank_payee_id", "memo",
                   "payment_term_id")


def test_contact_has_the_new_columns(conn):
    cols = columns(conn, "contact")
    for name in CONTACT_COLUMNS:
        assert name in cols, name
    contact_id = make_contact(conn)
    row = conn.execute("SELECT tax_exempt_status, bank_details_on_file FROM contact WHERE contact_id = ?",
                       (contact_id,)).fetchone()
    assert tuple(row) == ("Taxable", 0)


BANK_NUMBER_WORDS = re.compile(
    r"(^|_)(routing\w*|account_n(o|um)\w*|acct_no|iban|swift|bic|sort_code|aba|bsb|clabe)(_|$)")


def test_no_table_stores_third_party_bank_numbers(conn):
    """RP1: only the company's own bank_account keeps (protected) numbers; no other table has a place for them."""
    found = []
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"):
        if table == "bank_account":
            continue
        found += [f"{table}.{name}" for name in columns(conn, table) if BANK_NUMBER_WORDS.search(name)]
    assert found == []


def test_contact_tax_ids_and_certificates_never_reach_the_audit_log(conn):
    conn.execute("UPDATE audit_context SET user_id = 1, terminal_id = 'test' WHERE id = 1")
    inserted = conn.execute("INSERT INTO contact (name, tax_id, tax_exempt_status, exemption_reason, exemption_cert_no) "
                            "VALUES ('Vendor', '11-2223334', 'Exempt', 'Resale', 'CERT-77708888') "
                            "RETURNING contact_id").fetchone()[0]
    contact_id = make_contact(conn)
    conn.execute("UPDATE contact SET tax_id = '12-3456789', tax_exempt_status = 'Exempt', exemption_reason = 'Resale', "
                 "exemption_cert_no = 'CERT-55501234' WHERE contact_id = ?", (contact_id,))
    conn.execute("UPDATE contact SET tax_id = '98-7654321' WHERE contact_id = ?", (contact_id,))
    conn.execute("DELETE FROM contact WHERE contact_id = ?", (contact_id,))
    everything = " ".join(str(tuple(r)) for r in conn.execute("SELECT * FROM audit_log"))
    for secret in ("12-3456789", "123456789", "98-7654321", "987654321", "CERT-55501234", "55501234",
                   "11-2223334", "112223334", "CERT-77708888", "77708888"):
        assert secret not in everything
    first = conn.execute("SELECT new_value FROM audit_log WHERE table_name = 'contact' AND action = 'Insert' "
                         "AND record_id = ?", (inserted,)).fetchone()[0]
    assert "3334" in first and "8888" in first
    logged = [r["new_value"] for r in conn.execute(
        "SELECT new_value FROM audit_log WHERE table_name = 'contact' AND action = 'Update' ORDER BY log_id")]
    assert "6789" in logged[0] and "1234" in logged[0] and "4321" in logged[1]


@pytest.mark.parametrize("column, value", [("customer_type", "Company"), ("tax_exempt_status", "Partly"),
                                           ("bank_details_on_file", 2)])
def test_contact_value_checks(conn, column, value):
    contact_id = make_contact(conn)
    assert rejects(conn, f"UPDATE contact SET {column} = ? WHERE contact_id = ?", (value, contact_id))


def test_customer_type_values(conn):
    contact_id = make_contact(conn)
    for value in ("Individual", "Business", None):
        assert not rejects(conn, "UPDATE contact SET customer_type = ? WHERE contact_id = ?", (value, contact_id))


def test_exemption_details_need_exempt_status(conn):
    contact_id = make_contact(conn)
    assert rejects(conn, "UPDATE contact SET exemption_cert_no = 'C-1' WHERE contact_id = ?", (contact_id,))
    assert rejects(conn, "UPDATE contact SET exemption_reason = 'Resale' WHERE contact_id = ?", (contact_id,))
    assert rejects(conn, "UPDATE contact SET exemption_expires_at = '2027-01-01' WHERE contact_id = ?", (contact_id,))
    assert not rejects(conn, "UPDATE contact SET tax_exempt_status = 'Exempt', exemption_reason = 'Resale', "
                             "exemption_cert_no = 'C-1', exemption_expires_at = '2027-01-01' WHERE contact_id = ?",
                       (contact_id,))
    assert rejects(conn, "UPDATE contact SET exemption_expires_at = 'soon' WHERE contact_id = ?", (contact_id,))


def test_contact_site_belongs_to_a_contact(conn):
    contact_id = make_contact(conn)
    insert(conn, "contact_site", contact_id=contact_id, name="Main office")
    assert rejects(conn, *insert_sql("contact_site", contact_id=9999, name="Nowhere"))
    assert rejects(conn, *insert_sql("contact_site", contact_id=contact_id, name=None))
    assert rejects(conn, *insert_sql("contact_site", contact_id=contact_id, name="Yard", is_billing=2))


# --- documents, revisions, periods and locks -----------------------------------------------------------------

def test_invoice_has_the_new_columns(conn):
    cols = columns(conn, "invoice")
    for name in ("voucher_number", "revision_no", "supersedes_id", "sent_at", "sent_to", "void_reason", "memo",
                 "is_opening", "payment_term_id"):
        assert name in cols, name
    invoice_id = make_invoice(conn)
    row = conn.execute("SELECT revision_no, is_opening FROM invoice WHERE invoice_id = ?", (invoice_id,)).fetchone()
    assert tuple(row) == (1, 0)
    assert rejects(conn, "UPDATE invoice SET revision_no = 0 WHERE invoice_id = ?", (invoice_id,))
    assert rejects(conn, "UPDATE invoice SET is_opening = 2 WHERE invoice_id = ?", (invoice_id,))
    assert rejects(conn, "UPDATE invoice SET supersedes_id = 9999 WHERE invoice_id = ?", (invoice_id,))


def test_voucher_numbers_are_for_purchase_documents_and_unique(conn):
    bill = make_invoice(conn, itype="Bill")
    other_bill = make_invoice(conn, itype="Bill")
    sale = make_invoice(conn)
    assert rejects(conn, "UPDATE invoice SET voucher_number = 'VCH-000001' WHERE invoice_id = ?", (sale,))
    assert rejects(conn, "UPDATE invoice SET voucher_number = 'V-1' WHERE invoice_id = ?", (bill,))
    assert not rejects(conn, "UPDATE invoice SET voucher_number = 'VCH-000001' WHERE invoice_id = ?", (bill,))
    conn.execute("UPDATE invoice SET voucher_number = 'VCH-000001' WHERE invoice_id = ?", (bill,))
    assert rejects(conn, "UPDATE invoice SET voucher_number = 'VCH-000001' WHERE invoice_id = ?", (other_bill,))


@pytest.mark.parametrize("column", ["sent_at", "sent_to", "void_reason"])
def test_a_sent_invoice_records_send_and_void_details_once(conn, column):
    invoice_id = make_invoice(conn, status="Sent", entry_id=posted_entry(conn))
    conn.execute(f"UPDATE invoice SET {column} = 'first' WHERE invoice_id = ?", (invoice_id,))
    assert rejects(conn, f"UPDATE invoice SET {column} = 'second' WHERE invoice_id = ?", (invoice_id,))
    assert rejects(conn, f"UPDATE invoice SET {column} = NULL WHERE invoice_id = ?", (invoice_id,))


@pytest.mark.parametrize("column, value", [("memo", "changed"), ("revision_no", 2), ("is_opening", 1),
                                           ("supersedes_id", "other"), ("payment_term_id", "term")])
def test_new_invoice_columns_are_frozen_once_sent(conn, column, value):
    invoice_id = make_invoice(conn, status="Sent", entry_id=posted_entry(conn))
    if value == "other":
        value = make_invoice(conn)
    elif value == "term":
        value = insert(conn, "payment_term", name="Net 10", days_due=10)
    assert rejects(conn, f"UPDATE invoice SET {column} = ? WHERE invoice_id = ?", (value, invoice_id))


def test_a_sent_bills_voucher_number_is_frozen(conn):
    bill = make_invoice(conn, itype="Bill")
    conn.execute("UPDATE invoice SET voucher_number = 'VCH-000009' WHERE invoice_id = ?", (bill,))
    conn.execute("UPDATE invoice SET status = 'Sent', invoice_number = 'B-9' WHERE invoice_id = ?", (bill,))
    assert rejects(conn, "UPDATE invoice SET voucher_number = 'VCH-000010' WHERE invoice_id = ?", (bill,))


def test_a_sales_invoice_never_enters_a_pay_run(conn):
    sale = make_invoice(conn, status="Sent")
    assert rejects(conn, "UPDATE invoice SET status = 'In pay run' WHERE invoice_id = ?", (sale,))


def test_a_bill_moves_into_and_out_of_a_pay_run(conn):
    bill = make_invoice(conn, itype="Bill", status="Sent")
    conn.execute("UPDATE invoice SET status = 'In pay run' WHERE invoice_id = ?", (bill,))
    assert rejects(conn, "UPDATE invoice SET status = 'Void' WHERE invoice_id = ?", (bill,))
    conn.execute("UPDATE invoice SET status = 'Sent' WHERE invoice_id = ?", (bill,))
    conn.execute("UPDATE invoice SET status = 'In pay run' WHERE invoice_id = ?", (bill,))
    conn.execute("UPDATE invoice SET status = 'Paid' WHERE invoice_id = ?", (bill,))
    draft = make_invoice(conn, itype="Bill")
    assert rejects(conn, "UPDATE invoice SET status = 'In pay run' WHERE invoice_id = ?", (draft,))


def test_fiscal_period_lock(conn):
    period_id = ensure_period(conn, "2026-03-15")
    insert(conn, "fiscal_period_lock", period_id=period_id, area="Sales", locked_by=1,
           locked_at="2026-04-01T09:00:00+00:00", reason="March sales reviewed")
    assert rejects(conn, *insert_sql("fiscal_period_lock", period_id=period_id, area="Sales"))
    assert rejects(conn, *insert_sql("fiscal_period_lock", period_id=period_id, area="Everything"))
    assert rejects(conn, *insert_sql("fiscal_period_lock", period_id=9999, area="Banking"))
    for area in ("Purchases", "Banking", "Payroll", "Inventory", "Journal"):
        assert not rejects(conn, *insert_sql("fiscal_period_lock", period_id=period_id, area=area))


def test_audit_log_has_a_reason(conn, master):
    assert "reason" in columns(conn, "audit_log")
    assert "reason" in columns(master, "audit_log")


def test_lock_documents_after_posting_is_off_by_default(conn):
    column = columns(conn, "company_settings")["lock_documents_after_posting"]
    assert column["notnull"] == 1 and column["dflt_value"] == "0"
    assert "lock_documents_after_posting IN (0, 1)" in table_sql(conn, "company_settings")


def test_every_document_type_has_an_approval_toggle_and_all_are_off(conn):
    rows = dict(conn.execute("SELECT document_type, requires_approval FROM document_approval_setting").fetchall())
    for document_type in ("Invoice", "Credit Memo", "Vendor credit", "Pay run", "Estimate", "Bill", "Payment"):
        assert rows[document_type] == 0, document_type
    assert set(rows.values()) == {0}
    assert table_sql(conn, "approval_rule") is None  # RP9: no second place for approval toggles


# --- hierarchy: cost codes (RP5), dimensions (RP3) and service types (RP4) -----------------------------------

def cost_code(conn, code, level=None, parent=None):
    values = {"code": code, "name": code, "cost_type_label": "Labor", "parent_id": parent}
    if level is not None:
        values["level"] = level
    return insert(conn, "cost_code", **values)


def test_cost_code_levels(conn):
    cols = columns(conn, "cost_code")
    assert {"parent_id", "level", "is_active"} <= set(cols)
    division = cost_code(conn, "03")
    assert tuple(conn.execute("SELECT level, is_active FROM cost_code WHERE cost_code_id = ?",
                              (division,)).fetchone()) == (1, 1)
    code = cost_code(conn, "03-300", 2, division)
    cost_code(conn, "03-300-10", 3, code)
    assert rejects(conn, *insert_sql("cost_code", code="X1", name="x", cost_type_label="L", level=1, parent_id=division))
    assert rejects(conn, *insert_sql("cost_code", code="X2", name="x", cost_type_label="L", level=2))
    assert rejects(conn, *insert_sql("cost_code", code="X3", name="x", cost_type_label="L", level=3,
                                     parent_id=division))
    assert rejects(conn, *insert_sql("cost_code", code="X4", name="x", cost_type_label="L", level=2, parent_id=code))
    assert rejects(conn, *insert_sql("cost_code", code="X5", name="x", cost_type_label="L", level=4, parent_id=code))
    assert rejects(conn, "UPDATE cost_code SET level = 3 WHERE cost_code_id = ?", (code,))
    assert rejects(conn, "UPDATE cost_code SET is_active = 2 WHERE cost_code_id = ?", (code,))


def test_a_cost_code_with_sub_codes_cannot_change_level(conn):
    division = cost_code(conn, "04")
    code = cost_code(conn, "04-200", 2, division)
    cost_code(conn, "04-200-10", 3, code)
    # Level 1 with no parent passes the parent checks; only the children rule refuses it.
    assert rejects(conn, "UPDATE cost_code SET level = 1, parent_id = NULL WHERE cost_code_id = ?", (code,))
    childless = cost_code(conn, "04-300", 2, division)
    assert not rejects(conn, "UPDATE cost_code SET level = 1, parent_id = NULL WHERE cost_code_id = ?", (childless,))


def test_re_parenting_a_cost_code_keeps_one_level_up(conn):
    division = cost_code(conn, "05")
    code = cost_code(conn, "05-100", 2, division)
    other = cost_code(conn, "05-200", 2, division)
    sub_code = cost_code(conn, "05-100-10", 3, code)
    assert rejects(conn, "UPDATE cost_code SET parent_id = ? WHERE cost_code_id = ?", (division, sub_code))
    assert not rejects(conn, "UPDATE cost_code SET parent_id = ? WHERE cost_code_id = ?", (other, sub_code))


def test_dimension_depth_limit_is_ten():
    assert database.MAX_DIMENSION_DEPTH == 10


def test_service_types_stages_and_triggers(conn):
    service_type = insert(conn, "service_type", code="REMODEL", name="Remodel")
    assert rejects(conn, *insert_sql("service_type", code="REMODEL", name="Again"))
    stage = insert(conn, "service_stage", service_type_id=service_type, phase="Sales", name="Lead", sort_order=1)
    insert(conn, "service_stage", service_type_id=service_type, phase="Delivery", name="Completed", sort_order=9,
           allows_costs=1, allows_billing=1, is_closed_stage=1)
    assert rejects(conn, *insert_sql("service_stage", service_type_id=service_type, phase="Sales", name="Lead"))
    assert rejects(conn, *insert_sql("service_stage", service_type_id=service_type, phase="Warranty", name="W"))
    assert rejects(conn, *insert_sql("service_stage", service_type_id=9999, phase="Sales", name="Orphan"))
    trigger = insert(conn, "stage_trigger", stage_id=stage, event="Enter", action="create_task")
    assert rejects(conn, *insert_sql("stage_trigger", stage_id=stage, event="Whenever", action="create_task"))
    assert rejects(conn, *insert_sql("stage_trigger", stage_id=stage, event="Enter", action=None))
    run = insert(conn, "stage_trigger_run", trigger_id=trigger, record_type="Project", record_id=1,
                 event_key="enter:1", ran_at="2026-03-01T09:00:00+00:00", result="Done")
    # Idempotent: the same event for the same record runs once.
    assert rejects(conn, *insert_sql("stage_trigger_run", trigger_id=trigger, record_type="Project", record_id=1,
                                     event_key="enter:1", ran_at="2026-03-01T09:01:00+00:00", result="Done"))
    assert not rejects(conn, *insert_sql("stage_trigger_run", trigger_id=trigger, record_type="Project", record_id=1,
                                         event_key="enter:2", ran_at="2026-03-02T09:00:00+00:00", result="Done"))
    assert rejects(conn, *insert_sql("stage_trigger_run", trigger_id=trigger, record_type="Project", record_id=2,
                                     event_key="enter:2", ran_at="2026-03-01T09:00:00+00:00", result="Maybe"))
    assert rejects(conn, "UPDATE stage_trigger_run SET result = 'Failed' WHERE run_id = ?", (run,))
    assert rejects(conn, "DELETE FROM stage_trigger_run WHERE run_id = ?", (run,))
    assert table_sql(conn, "pipeline_stage") is None


def test_project_points_at_a_service_type_and_stage(conn):
    fks = {row["from"]: row["table"] for row in conn.execute("PRAGMA foreign_key_list(project)")}
    assert fks["service_type_id"] == "service_type"
    assert fks["service_stage_id"] == "service_stage"


# --- core v1.0 tables ----------------------------------------------------------------------------------------

@pytest.fixture
def bank(conn):
    account_id = make_account(conn, "1010")
    return insert(conn, "bank_account", account_id=account_id, bank_name="Bank")


def test_pay_run_and_lines(conn, bank):
    run = insert(conn, "pay_run", run_number="PR-0001", bank_account_id=bank, created_by=1,
                 created_at="2026-03-01T09:00:00+00:00")
    assert conn.execute("SELECT status FROM pay_run WHERE pay_run_id = ?", (run,)).fetchone()[0] == "Draft"
    assert rejects(conn, *insert_sql("pay_run", run_number="PR-0001", bank_account_id=bank))
    assert rejects(conn, *insert_sql("pay_run", run_number="PR-0002", bank_account_id=bank, status="Sent"))
    bill = make_invoice(conn, itype="Bill", status="Sent")
    sale = make_invoice(conn, status="Sent")
    line = insert(conn, "pay_run_line", pay_run_id=run, invoice_id=bill, amount_cents=1000)
    assert conn.execute("SELECT status FROM pay_run_line WHERE line_id = ?", (line,)).fetchone()[0] == "Open"
    assert rejects(conn, *insert_sql("pay_run_line", pay_run_id=run, invoice_id=bill, amount_cents=10))
    assert rejects(conn, *insert_sql("pay_run_line", pay_run_id=run, invoice_id=sale, amount_cents=10))
    assert rejects(conn, "UPDATE pay_run_line SET invoice_id = ? WHERE line_id = ?", (sale, line))
    other_bill = make_invoice(conn, itype="Bill", status="Sent")
    assert rejects(conn, *insert_sql("pay_run_line", pay_run_id=run, invoice_id=other_bill, amount_cents=0))
    assert rejects(conn, *insert_sql("pay_run_line", pay_run_id=run, invoice_id=other_bill, amount_cents=10.5))
    # Paid needs the payment, the date paid and the reference.
    assert rejects(conn, "UPDATE pay_run_line SET status = 'Paid' WHERE line_id = ?", (line,))
    payment_id = make_payment(conn)
    assert rejects(conn, "UPDATE pay_run_line SET status = 'Paid', payment_id = ?, date_paid = '2026-03-05' "
                         "WHERE line_id = ?", (payment_id, line))
    assert rejects(conn, "UPDATE pay_run_line SET status = 'Paid', payment_id = ?, payment_ref = 'BANK-77' "
                         "WHERE line_id = ?", (payment_id, line))
    assert rejects(conn, "UPDATE pay_run_line SET status = 'Paid', date_paid = '2026-03-05', payment_ref = 'BANK-77' "
                         "WHERE line_id = ?", (line,))
    # And the other way: an Open line does not carry a payment, a date paid and a reference.
    assert rejects(conn, "UPDATE pay_run_line SET payment_id = ?, date_paid = '2026-03-05', payment_ref = 'BANK-77' "
                         "WHERE line_id = ?", (payment_id, line))
    assert not rejects(conn, "UPDATE pay_run_line SET status = 'Paid', payment_id = ?, date_paid = '2026-03-05', "
                             "payment_ref = 'BANK-77' WHERE line_id = ?", (payment_id, line))


def test_bank_statement_lines_and_matches(conn, bank):
    line = insert(conn, "bank_statement_line", bank_account_id=bank, source="File", external_id="T1",
                  posted_date="2026-03-03", description="Deposit", amount_cents=1000)
    insert(conn, "bank_statement_line", bank_account_id=bank, source="Manual", posted_date="2026-03-03",
           amount_cents=-250)
    insert(conn, "bank_statement_line", bank_account_id=bank, source="Manual", posted_date="2026-03-03",
           amount_cents=-250)
    assert conn.execute("SELECT status FROM bank_statement_line WHERE statement_line_id = ?",
                        (line,)).fetchone()[0] == "Unmatched"
    assert rejects(conn, *insert_sql("bank_statement_line", bank_account_id=bank, source="File", external_id="T1",
                                     posted_date="2026-03-04", amount_cents=5))
    assert rejects(conn, *insert_sql("bank_statement_line", bank_account_id=bank, source="Fax",
                                     posted_date="2026-03-04", amount_cents=5))
    assert rejects(conn, *insert_sql("bank_statement_line", bank_account_id=bank, source="File",
                                     posted_date="2026-03-04", amount_cents=5.5))
    payment_id = make_payment(conn)
    entry_id = make_entry(conn, [(100, 0), (0, 100)])
    journal_line = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? LIMIT 1",
                                (entry_id,)).fetchone()[0]
    assert rejects(conn, *insert_sql("bank_statement_match", statement_line_id=line, amount_cents=1000))
    assert rejects(conn, *insert_sql("bank_statement_match", statement_line_id=line, payment_id=payment_id,
                                     journal_line_id=journal_line, amount_cents=1000))
    match = insert(conn, "bank_statement_match", statement_line_id=line, payment_id=payment_id, amount_cents=1000,
                   matched_by=1, matched_at="2026-03-04T09:00:00+00:00")
    assert rejects(conn, "UPDATE bank_statement_match SET amount_cents = 5 WHERE match_id = ?", (match,))
    assert rejects(conn, "DELETE FROM bank_statement_match WHERE match_id = ?", (match,))
    assert rejects(conn, "UPDATE bank_statement_match SET released_at = '2026-03-05T09:00:00+00:00' "
                         "WHERE match_id = ?", (match,))
    # Any update that is not a release is refused, even one that changes nothing.
    assert rejects(conn, "UPDATE bank_statement_match SET amount_cents = amount_cents WHERE match_id = ?", (match,))
    other_line = insert(conn, "bank_statement_line", bank_account_id=bank, source="Manual", posted_date="2026-03-05",
                        amount_cents=1)
    release = ("UPDATE bank_statement_match SET released_at = '2026-03-05T09:00:00+00:00', released_by = 1, "
               "release_reason = 'x', {} = ? WHERE match_id = ?")
    for column, value in (("match_id", 9999), ("statement_line_id", other_line), ("payment_id", make_payment(conn)),
                          ("amount_cents", 5), ("matched_by", 9), ("matched_at", "2026-01-01T00:00:00+00:00")):
        assert rejects(conn, release.format(column), (value, match)), column
    line_ids = [r[0] for r in conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? ORDER BY line_id",
                                           (entry_id,))]
    line_match = insert(conn, "bank_statement_match", statement_line_id=line, journal_line_id=line_ids[0],
                        amount_cents=100, matched_by=1, matched_at="2026-03-04T09:00:00+00:00")
    assert rejects(conn, release.format("journal_line_id"), (line_ids[1], line_match))
    conn.execute("UPDATE bank_statement_match SET released_at = '2026-03-05T09:00:00+00:00', released_by = 1, "
                 "release_reason = 'Wrong payment' WHERE match_id = ?", (match,))
    assert rejects(conn, "UPDATE bank_statement_match SET release_reason = 'x' WHERE match_id = ?", (match,))


def test_statement_lines_of_a_completed_reconciliation_are_locked(conn, bank):
    account_id = conn.execute("SELECT account_id FROM bank_account WHERE bank_account_id = ?", (bank,)).fetchone()[0]
    recon = insert(conn, "bank_reconciliation", account_id=account_id, statement_date="2026-03-31",
                   statement_balance_cents=0)
    line = insert(conn, "bank_statement_line", bank_account_id=bank, source="File", posted_date="2026-03-03",
                  amount_cents=1000)
    conn.execute("UPDATE bank_statement_line SET recon_id = ? WHERE statement_line_id = ?", (recon, line))
    conn.execute("UPDATE bank_reconciliation SET is_complete = 1 WHERE recon_id = ?", (recon,))
    assert rejects(conn, "UPDATE bank_statement_line SET recon_id = NULL WHERE statement_line_id = ?", (line,))
    assert rejects(conn, "DELETE FROM bank_statement_line WHERE statement_line_id = ?", (line,))
    loose = insert(conn, "bank_statement_line", bank_account_id=bank, source="Manual", posted_date="2026-03-04",
                   amount_cents=5)
    assert rejects(conn, "UPDATE bank_statement_line SET recon_id = ? WHERE statement_line_id = ?", (recon, loose))
    assert not rejects(conn, "DELETE FROM bank_statement_line WHERE statement_line_id = ?", (loose,))


def test_close_tasks_and_dependencies(conn):
    period_id = ensure_period(conn, "2026-03-15")
    first = insert(conn, "close_task", period_id=period_id, title="Reconcile bank", area="Banking")
    second = insert(conn, "close_task", period_id=period_id, title="Review AP", area="Purchases")
    row = conn.execute("SELECT status, is_blocking FROM close_task WHERE task_id = ?", (first,)).fetchone()
    assert tuple(row) == ("Open", 0)
    insert(conn, "close_task_dependency", task_id=second, depends_on_task_id=first)
    assert rejects(conn, *insert_sql("close_task_dependency", task_id=first, depends_on_task_id=first))
    assert rejects(conn, *insert_sql("close_task_dependency", task_id=second, depends_on_task_id=first))
    assert rejects(conn, *insert_sql("close_task", period_id=period_id, title="x", status="Late"))


def test_payment_terms(conn):
    term = insert(conn, "payment_term", name="Net 30", days_due=30)
    assert rejects(conn, *insert_sql("payment_term", name="Net 30", days_due=30))
    assert rejects(conn, *insert_sql("payment_term", name="Backwards", days_due=-1))
    contact_id = make_contact(conn)
    conn.execute("UPDATE contact SET payment_term_id = ? WHERE contact_id = ?", (term, contact_id))
    assert rejects(conn, "UPDATE contact SET payment_term_id = 9999 WHERE contact_id = ?", (contact_id,))


def test_custom_fields_store_one_typed_value(conn):
    money = insert(conn, "custom_field_def", record_type="Project", field_key="permit_fee", label="Permit fee",
                   data_type="Money")
    text = insert(conn, "custom_field_def", record_type="Contact", field_key="gate_code", label="Gate code",
                  data_type="Text")
    assert rejects(conn, *insert_sql("custom_field_def", record_type="Project", field_key="permit_fee",
                                     label="Again", data_type="Text"))
    assert rejects(conn, *insert_sql("custom_field_def", record_type="Project", field_key="x", label="x",
                                     data_type="Blob"))
    insert(conn, "custom_field_value", field_id=money, record_id=1, value_cents=2500)
    insert(conn, "custom_field_value", field_id=text, record_id=1, value_text="1234")
    assert rejects(conn, *insert_sql("custom_field_value", field_id=money, record_id=1, value_cents=10))
    assert rejects(conn, *insert_sql("custom_field_value", field_id=money, record_id=2, value_text="25.00"))
    assert rejects(conn, *insert_sql("custom_field_value", field_id=text, record_id=2, value_text="a",
                                     value_number=1.0))
    assert rejects(conn, *insert_sql("custom_field_value", field_id=money, record_id=3, value_cents=1.5))
    money_value = conn.execute("SELECT value_id FROM custom_field_value WHERE field_id = ?", (money,)).fetchone()[0]
    assert rejects(conn, "UPDATE custom_field_value SET value_cents = NULL, value_text = '25' WHERE value_id = ?",
                   (money_value,))


TYPED_COLUMNS = {"value_text": "x", "value_number": 2.5, "value_cents": 5, "value_date": "2026-03-01",
                 "value_bool": 1}
RIGHT_COLUMN = {"Text": "value_text", "Choice": "value_text", "Number": "value_number", "Money": "value_cents",
                "Date": "value_date", "Yes/No": "value_bool"}


@pytest.mark.parametrize("data_type", list(RIGHT_COLUMN))
def test_each_custom_field_type_uses_its_own_column(conn, data_type):
    field = insert(conn, "custom_field_def", record_type="Invoice", field_key=f"f_{data_type}", label=data_type,
                   data_type=data_type)
    right = RIGHT_COLUMN[data_type]
    value_id = insert(conn, "custom_field_value", field_id=field, record_id=1, **{right: TYPED_COLUMNS[right]})
    other = "y" if right == "value_text" else TYPED_COLUMNS[right]
    assert not rejects(conn, f"UPDATE custom_field_value SET {right} = ? WHERE value_id = ?", (other, value_id))
    for record_id, wrong in enumerate((c for c in TYPED_COLUMNS if c != right), start=2):
        assert rejects(conn, *insert_sql("custom_field_value", field_id=field, record_id=record_id,
                                         **{wrong: TYPED_COLUMNS[wrong]})), wrong
        assert rejects(conn, f"UPDATE custom_field_value SET {right} = NULL, {wrong} = ? WHERE value_id = ?",
                       (TYPED_COLUMNS[wrong], value_id)), wrong
    # An empty value is allowed, on insert and on update.
    assert not rejects(conn, *insert_sql("custom_field_value", field_id=field, record_id=99))
    assert not rejects(conn, f"UPDATE custom_field_value SET {right} = NULL WHERE value_id = ?", (value_id,))


def test_list_preferences_saved_views_and_dismissals(conn):
    insert(conn, "user_list_pref", user_id=1, list_key="invoices", columns_json="[]")
    assert rejects(conn, *insert_sql("user_list_pref", user_id=1, list_key="invoices"))
    insert(conn, "saved_view", user_id=1, list_key="invoices", name="Overdue", filters_json="{}")
    insert(conn, "saved_view", user_id=2, list_key="invoices", name="Overdue", filters_json="{}")
    assert rejects(conn, *insert_sql("saved_view", user_id=1, list_key="invoices", name="Overdue"))
    insert(conn, "alert_dismissal", user_id=1, alert_key="stale_checks",
           dismissed_at="2026-03-01T09:00:00+00:00")
    assert rejects(conn, *insert_sql("alert_dismissal", user_id=1, alert_key="stale_checks",
                                     dismissed_at="2026-03-02T09:00:00+00:00"))


# --- audit coverage for every new table and column -----------------------------------------------------------

ALL = ("insert", "update", "delete")
AUDITED_TABLES_REPLAN = {
    "contact": ALL, "contact_site": ALL, "company_entity": ALL, "fiscal_period_lock": ALL, "cost_code": ALL,
    "service_type": ALL, "service_stage": ALL, "stage_trigger": ALL, "stage_trigger_run": ("insert",),
    "pay_run": ALL, "pay_run_line": ALL, "bank_statement_line": ALL, "bank_statement_match": ("insert", "update"),
    "close_task": ALL, "close_task_dependency": ALL, "payment_term": ALL, "custom_field_def": ALL,
    "custom_field_value": ALL, "user_list_pref": ALL, "saved_view": ALL, "alert_dismissal": ALL,
    "invoice": ALL, "payment_allocation": ALL, "account": ALL, "project": ALL,
}


def missing_audit(conn, audited):
    missing = []
    for table, events in audited.items():
        names = list(columns(conn, table))
        for event in events:
            sql = table_sql(conn, f"audit_{table}_{event}")
            if sql is None:
                missing.append(f"audit_{table}_{event} (no trigger)")
                continue
            for prefix in {"insert": ["NEW"], "delete": ["OLD"], "update": ["OLD", "NEW"]}[event]:
                missing += [f"audit_{table}_{event}: {prefix}.{c}" for c in names if f"{prefix}.{c}" not in sql]
    return missing


def test_new_tables_and_columns_are_audited(conn):
    assert missing_audit(conn, AUDITED_TABLES_REPLAN) == []


def test_master_user_company_role_is_audited(master):
    assert missing_audit(master, {"user_company_role": ALL}) == []


def test_a_contact_change_writes_an_audit_row(conn):
    conn.execute("UPDATE audit_context SET user_id = 1, terminal_id = 'test' WHERE id = 1")
    contact_id = make_contact(conn)
    conn.execute("UPDATE contact SET bank_details_on_file = 1, bank_payee_id = 'ACME-01' WHERE contact_id = ?",
                 (contact_id,))
    actions = [r[0] for r in conn.execute(
        "SELECT action FROM audit_log WHERE table_name = 'contact' AND record_id = ? ORDER BY log_id", (contact_id,))]
    assert actions == ["Insert", "Update"]


# --- indexes: every foreign key column is indexed ------------------------------------------------------------

def unindexed_foreign_keys(connection):
    missing = []
    tables = [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        leading = set()
        for index in connection.execute(f'PRAGMA index_list("{table}")'):
            if index["partial"]:
                continue  # a partial index does not serve every lookup on its leading column
            info = connection.execute(f'PRAGMA index_info("{index["name"]}")').fetchall()
            if info:
                leading.add(info[0]["name"])
        pk = [r["name"] for r in connection.execute(f'PRAGMA table_info("{table}")') if r["pk"] == 1]
        leading.update(pk)
        for fk in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
            if fk["from"] not in leading:
                missing.append(f"{table}.{fk['from']}")
    return sorted(set(missing))


def test_no_unindexed_foreign_keys_in_the_company_file(conn):
    assert unindexed_foreign_keys(conn) == []


def test_no_unindexed_foreign_keys_in_the_master(master):
    assert unindexed_foreign_keys(master) == []


# --- master: several roles per user per company (RP10) -------------------------------------------------------

def test_user_company_role(master):
    user = master.execute("INSERT INTO app_user (username, password_hash, first_name, last_name, email) "
                          "VALUES ('pat', 'scrypt$x', 'Pat', 'Lee', 'pat@example.test') RETURNING user_id").fetchone()[0]
    company = master.execute("INSERT INTO company_registry (company_code, legal_name, database_file_path) "
                             "VALUES ('ACME', 'Acme', 'Companies/ACME.db') RETURNING company_id").fetchone()[0]
    insert(master, "user_company_role", user_id=user, company_id=company, role_code="Bookkeeper")
    insert(master, "user_company_role", user_id=user, company_id=company, role_code="Approver")
    assert rejects(master, *insert_sql("user_company_role", user_id=user, company_id=company,
                                       role_code="Bookkeeper"))
    assert rejects(master, *insert_sql("user_company_role", user_id=user, company_id=company, role_code=None))
    assert rejects(master, *insert_sql("user_company_role", user_id=9999, company_id=company, role_code="X"))
