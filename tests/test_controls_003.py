"""Migration 003: critical controls (controls audit L1, P1, P2, C1-C3, T1) and decisions 1-2."""
import json
import sqlite3

import pytest

import modules.database as database
from tests.ledger_helpers import (
    ensure_period, make_account, make_entry, make_invoice, make_period, make_reversal, post,
    posted_entry, send_invoice, set_period_closed,
)

POSTED = "Posted journal entries"
BAD_DATES = ["03/20/2026", "2026-3-5", "2026-02-30", "2026-03-20 10:00"]
AUDITED_TABLES = {
    "journal_entry": ("insert", "update", "delete"),
    "fiscal_period": ("insert", "update", "delete"),
    "account": ("insert", "update", "delete"),
    "invoice": ("insert", "update", "delete"),
    "payment": ("insert", "update", "delete"),
    "payment_allocation": ("insert", "update", "delete"),
    "company_settings": ("insert", "update"),
}


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def entry_row(conn, entry_id):
    return dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone())


# --- L1: every line has an account ------------------------------------------

def test_line_without_account_is_rejected(conn):
    entry_id = make_entry(conn, [])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, NULL, 100, 0)",
            (entry_id,),
        )


# --- P1: strict ISO dates ---------------------------------------------------

@pytest.mark.parametrize("bad_date", BAD_DATES)
def test_entry_date_must_be_iso(conn, bad_date):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO journal_entry (entry_date) VALUES (?)", (bad_date,))


@pytest.mark.parametrize("bad_date", BAD_DATES)
@pytest.mark.parametrize("column", ["start_date", "end_date"])
def test_period_dates_must_be_iso(conn, column, bad_date):
    values = {"start_date": "2026-03-01", "end_date": "2026-03-31", column: bad_date}
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fiscal_period (name, start_date, end_date) VALUES ('P', ?, ?)",
            (values["start_date"], values["end_date"]),
        )


@pytest.mark.parametrize("bad_date", BAD_DATES)
@pytest.mark.parametrize("column", ["issue_date", "due_date"])
def test_invoice_dates_must_be_iso(conn, column, bad_date):
    values = {"issue_date": "2026-03-01", "due_date": "2026-03-31", column: bad_date}
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO invoice (invoice_type, ledger_side, invoice_number, issue_date, due_date) "
            "VALUES ('Invoice', 'Sales', 'D-1', ?, ?)",
            (values["issue_date"], values["due_date"]),
        )


@pytest.mark.parametrize("bad_date", BAD_DATES)
def test_payment_date_must_be_iso(conn, bad_date):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO payment (payment_date, amount_cents) VALUES (?, 100)", (bad_date,))


def test_valid_iso_dates_are_accepted(conn):
    conn.execute("INSERT INTO fiscal_period (name, start_date, end_date) VALUES ('Feb', '2026-02-01', '2026-02-28')")
    conn.execute("INSERT INTO journal_entry (entry_date, period_id) VALUES ('2026-02-28', ?)",
                 (ensure_period(conn, '2026-02-28'),))


# --- Decision 1: void = reversing entry --------------------------------------

def test_is_void_cannot_be_set_directly(conn):
    draft_id = make_entry(conn, [(100, 0), (0, 100)])
    posted_id = posted_entry(conn)
    for entry_id in (draft_id, posted_id):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE journal_entry SET is_void = 1 WHERE entry_id = ?", (entry_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO journal_entry (entry_date, period_id, is_void) VALUES ('2026-03-01', ?, 1)",
                     (ensure_period(conn, '2026-03-01'),))


def test_posting_void_reversal_voids_original(conn):
    original = posted_entry(conn)
    before = entry_row(conn, original)
    reversal = make_reversal(conn, original, "Void")

    post(conn, reversal)

    assert entry_row(conn, original) == {**before, "is_void": 1}
    assert entry_row(conn, reversal)["is_posted"] == 1
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute("UPDATE journal_entry SET is_void = 0 WHERE entry_id = ?", (original,))


def test_accrual_reversal_does_not_void(conn):
    original = posted_entry(conn)
    reversal = make_reversal(conn, original, "Accrual reversal")
    post(conn, reversal)
    assert entry_row(conn, original)["is_void"] == 0


def test_reversal_must_mirror_original(conn):
    original = posted_entry(conn, 1000)
    lines = [
        (row["account_id"], row["credit_cents"] // 2, row["debit_cents"] // 2)
        for row in conn.execute("SELECT * FROM journal_line WHERE entry_id = ?", (original,))
    ]
    partial = make_reversal(conn, original, "Void", lines=lines)
    with pytest.raises(sqlite3.IntegrityError, match="mirror"):
        post(conn, partial)
    assert entry_row(conn, original)["is_void"] == 0


def test_reversal_on_wrong_accounts_is_rejected(conn):
    original = posted_entry(conn, 1000)
    other_a, other_b = make_account(conn, "X-1"), make_account(conn, "X-2")
    reversal = make_reversal(conn, original, "Correction", lines=[(other_a, 1000, 0), (other_b, 0, 1000)])
    with pytest.raises(sqlite3.IntegrityError, match="mirror"):
        post(conn, reversal)


def test_cannot_reverse_a_draft(conn):
    draft = make_entry(conn, [(100, 0), (0, 100)])
    reversal = make_reversal(conn, draft, "Void")
    with pytest.raises(sqlite3.IntegrityError):
        post(conn, reversal)


def test_entry_can_only_be_reversed_once(conn):
    original = posted_entry(conn)
    make_reversal(conn, original, "Accrual reversal")
    with pytest.raises(sqlite3.IntegrityError):
        make_reversal(conn, original, "Void")


def test_cannot_reverse_a_voided_entry(conn):
    original = posted_entry(conn)
    first = make_reversal(conn, original, "Void")
    post(conn, first)
    # A voided entry's existing reversal occupies the unique slot; a reversal of
    # the reversal is allowed, but the original itself cannot be reversed again.
    with pytest.raises(sqlite3.IntegrityError):
        make_reversal(conn, original, "Void")


def test_reversal_into_closed_period_is_rejected(conn):
    original = posted_entry(conn, entry_date="2026-03-10")
    closed = make_period(conn, "2026-04", "2026-04-01", "2026-04-30", closed=True)
    reversal = make_reversal(conn, original, "Void", entry_date="2026-04-05", period_id=closed)
    with pytest.raises(sqlite3.IntegrityError, match="closed"):
        post(conn, reversal)
    assert entry_row(conn, original)["is_void"] == 0


def test_original_in_closed_period_can_be_voided_in_open_period(conn):
    march = make_period(conn, "2026-03", "2026-03-01", "2026-03-31", closed=False)
    original = posted_entry(conn, entry_date="2026-03-10", period_id=march)
    set_period_closed(conn, march, True)
    april = make_period(conn, "2026-04", "2026-04-01", "2026-04-30", closed=False)
    reversal = make_reversal(conn, original, "Void", entry_date="2026-04-02", period_id=april)

    post(conn, reversal)

    assert entry_row(conn, original)["is_void"] == 1


@pytest.mark.parametrize("reverses, reason", [
    (False, "Void"),        # reason without a reversed entry
    (True, None),           # reversed entry without a reason
    (True, "Mistake"),      # unknown reason
])
def test_reversal_reason_pairs_with_reverses_entry_id(conn, reverses, reason):
    original = posted_entry(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journal_entry (entry_date, period_id, reverses_entry_id, reversal_reason) VALUES (?, ?, ?, ?)",
            ("2026-03-01", ensure_period(conn, "2026-03-01"), original if reverses else None, reason),
        )


def test_lock_trigger_compares_reversal_reason(conn):
    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='journal_entry_lock_posted'"
    ).fetchone()[0]
    assert "NEW.reversal_reason IS OLD.reversal_reason" in trigger_sql


# --- C1-C3: locked documents -------------------------------------------------

def test_draft_invoice_is_editable_and_deletable(conn):
    invoice_id = make_invoice(conn)
    conn.execute("UPDATE invoice SET total_cents = 5, due_date = '2026-04-30' WHERE invoice_id = ?", (invoice_id,))
    conn.execute("UPDATE invoice_line SET unit_price_cents = 5 WHERE invoice_id = ?", (invoice_id,))
    conn.execute("INSERT INTO invoice_line (invoice_id, unit_price_cents) VALUES (?, 1)", (invoice_id,))
    conn.execute("DELETE FROM invoice WHERE invoice_id = ?", (invoice_id,))


@pytest.mark.parametrize("status", ["Sent", "Paid", "Void", "Covered by advance"])
def test_non_draft_invoice_cannot_be_deleted_or_edited(conn, status):
    invoice_id = make_invoice(conn, status=status)
    line_id = conn.execute("SELECT line_id FROM invoice_line WHERE invoice_id = ?", (invoice_id,)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM invoice WHERE invoice_id = ?", (invoice_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE invoice SET total_cents = 1 WHERE invoice_id = ?", (invoice_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE invoice_line SET unit_price_cents = 1 WHERE line_id = ?", (line_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM invoice_line WHERE line_id = ?", (line_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO invoice_line (invoice_id, unit_price_cents) VALUES (?, 1)", (invoice_id,))
    draft = make_invoice(conn)
    draft_line = conn.execute("SELECT line_id FROM invoice_line WHERE invoice_id = ?", (draft,)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE invoice_line SET invoice_id = ? WHERE line_id = ?", (invoice_id, draft_line))


def test_invoice_with_posted_entry_is_locked(conn):
    entry_id = posted_entry(conn)
    invoice_id = make_invoice(conn, status="Sent", entry_id=entry_id)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM invoice WHERE invoice_id = ?", (invoice_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE invoice SET entry_id = NULL WHERE invoice_id = ?", (invoice_id,))


def test_locked_invoice_line_dimensions_are_locked(conn):
    type_id = conn.execute("INSERT INTO dimension_type (name) VALUES ('Dept') RETURNING dimension_type_id").fetchone()[0]
    value_id = conn.execute(
        "INSERT INTO dimension_value (dimension_type_id, code, name) VALUES (?, 'OPS', 'Ops') RETURNING dimension_value_id",
        (type_id,),
    ).fetchone()[0]
    invoice_id = make_invoice(conn)
    line_id = conn.execute("SELECT line_id FROM invoice_line WHERE invoice_id = ?", (invoice_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO invoice_line_dimension (line_id, dimension_type_id, dimension_value_id) VALUES (?, ?, ?)",
        (line_id, type_id, value_id),
    )
    send_invoice(conn, invoice_id)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM invoice_line_dimension WHERE line_id = ?", (line_id,))


ALLOWED_MOVES = {
    ("Draft", "Sent"), ("Sent", "Paid"), ("Paid", "Sent"), ("Sent", "Void"),
    ("Draft", "Covered by advance"), ("Sent", "Covered by advance"),
}
STATUSES = ["Draft", "Sent", "Paid", "Void", "Covered by advance"]


@pytest.mark.parametrize(
    "start, target", [(a, b) for a in STATUSES for b in STATUSES if a != b], ids=lambda value: str(value).replace(" ", "_")
)
def test_invoice_status_moves(conn, start, target):
    invoice_id = make_invoice(conn, status=start)
    sql = "UPDATE invoice SET status = ? WHERE invoice_id = ?"
    if (start, target) in ALLOWED_MOVES:
        if start == "Draft":
            send_invoice(conn, invoice_id, status=target)  # leaving Draft takes a number (004)
        else:
            conn.execute(sql, (target, invoice_id))
    else:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, (target, invoice_id))


def test_void_invoice_needs_voided_entry(conn):
    entry_id = posted_entry(conn)
    invoice_id = make_invoice(conn, status="Sent", entry_id=entry_id)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE invoice SET status = 'Void' WHERE invoice_id = ?", (invoice_id,))
    post(conn, make_reversal(conn, entry_id, "Void"))
    conn.execute("UPDATE invoice SET status = 'Void' WHERE invoice_id = ?", (invoice_id,))


def make_payment(conn, entry_id=None, amount=1000):
    return conn.execute(
        "INSERT INTO payment (payment_date, amount_cents, entry_id) VALUES ('2026-03-05', ?, ?) RETURNING payment_id",
        (amount, entry_id),
    ).fetchone()[0]


def test_unposted_payment_is_editable(conn):
    payment_id = make_payment(conn)
    conn.execute("UPDATE payment SET amount_cents = 5 WHERE payment_id = ?", (payment_id,))
    conn.execute("DELETE FROM payment WHERE payment_id = ?", (payment_id,))


def test_posted_payment_is_locked(conn):
    payment_id = make_payment(conn, entry_id=posted_entry(conn))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE payment SET amount_cents = 5 WHERE payment_id = ?", (payment_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE payment SET entry_id = NULL WHERE payment_id = ?", (payment_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM payment WHERE payment_id = ?", (payment_id,))


def test_allocations_of_posted_payment(conn):
    entry_id = posted_entry(conn)
    payment_id = make_payment(conn, entry_id=entry_id)
    invoice_id = make_invoice(conn, status="Sent")
    allocation_id = conn.execute(
        "INSERT INTO payment_allocation (payment_id, invoice_id, amount_applied_cents) VALUES (?, ?, 1000) "
        "RETURNING allocation_id",
        (payment_id, invoice_id),
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE payment_allocation SET amount_applied_cents = 5 WHERE allocation_id = ?", (allocation_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM payment_allocation WHERE allocation_id = ?", (allocation_id,))

    post(conn, make_reversal(conn, entry_id, "Void"))

    conn.execute("DELETE FROM payment_allocation WHERE allocation_id = ?", (allocation_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO payment_allocation (payment_id, invoice_id, amount_applied_cents) VALUES (?, ?, 10)",
            (payment_id, invoice_id),
        )


# --- T1: audit trail ----------------------------------------------------------

def set_user(conn, user_id):
    conn.execute("UPDATE audit_context SET user_id = ?, terminal_id = 'test' WHERE id = 1", (user_id,))


def audit_rows(conn, table, record_id=None):
    sql = "SELECT * FROM audit_log WHERE table_name = ?"
    params = [table]
    if record_id is not None:
        sql += " AND record_id = ?"
        params.append(record_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY log_id", params)]


def test_audit_log_is_append_only(conn):
    conn.execute("INSERT INTO audit_log (table_name, record_id, action) VALUES ('x', 1, 'Insert')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE audit_log SET action = 'Delete'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM audit_log")


def test_posting_writes_audit_row_with_user_and_lines(conn):
    set_user(conn, 7)
    entry_id = make_entry(conn, [(1000, 0), (0, 1000)])
    post(conn, entry_id)
    rows = [r for r in audit_rows(conn, "journal_entry", entry_id) if r["action"] == "Post"]
    assert len(rows) == 1
    assert rows[0]["user_id"] == 7 and rows[0]["terminal_id"] == "test"
    new_value = json.loads(rows[0]["new_value"])
    assert new_value["is_posted"] == 1
    assert sorted((l["debit_cents"], l["credit_cents"]) for l in new_value["lines"]) == [(0, 1000), (1000, 0)]


def test_void_writes_audit_row(conn):
    original = posted_entry(conn)
    post(conn, make_reversal(conn, original, "Void"))
    assert [r["action"] for r in audit_rows(conn, "journal_entry", original)][-1] == "Void"


def test_other_changes_write_audit_rows(conn):
    period_id = make_period(conn, "2026-03", "2026-03-01", "2026-03-31", closed=False)
    set_period_closed(conn, period_id, True)
    period_rows = audit_rows(conn, "fiscal_period", period_id)
    assert [r["action"] for r in period_rows] == ["Insert", "Update"]
    assert json.loads(period_rows[1]["old_value"])["is_closed"] == 0
    assert json.loads(period_rows[1]["new_value"])["is_closed"] == 1

    invoice_id = make_invoice(conn)
    conn.execute("DELETE FROM invoice WHERE invoice_id = ?", (invoice_id,))
    assert audit_rows(conn, "invoice", invoice_id)[-1]["action"] == "Delete"

    account_id = make_account(conn, "9000")
    conn.execute("UPDATE account SET name = 'Renamed' WHERE account_id = ?", (account_id,))
    assert json.loads(audit_rows(conn, "account", account_id)[-1]["new_value"])["name"] == "Renamed"


def test_draft_entry_delete_is_audited(conn):
    entry_id = make_entry(conn, [])
    conn.execute("DELETE FROM journal_entry WHERE entry_id = ?", (entry_id,))
    assert [r["action"] for r in audit_rows(conn, "journal_entry", entry_id)] == ["Insert", "Delete"]


def test_audit_triggers_cover_every_column(conn):
    missing = []
    for table, events in AUDITED_TABLES.items():
        columns = [c["name"] for c in conn.execute(f'PRAGMA table_info("{table}")')]
        for event in events:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name = ?", (f"audit_{table}_{event}",)
            ).fetchone()
            if row is None:
                missing.append(f"audit_{table}_{event} (no trigger)")
                continue
            prefixes = {"insert": ["NEW"], "delete": ["OLD"], "update": ["OLD", "NEW"]}[event]
            for column in columns:
                for prefix in prefixes:
                    if f"{prefix}.{column}" not in row[0]:
                        missing.append(f"audit_{table}_{event}: {prefix}.{column}")
    assert missing == []


# --- Decision 2: 'Credit Memo', positive amounts, one sign function -----------

def test_credit_memo_spelling(conn):
    make_invoice(conn, itype="Credit Memo")
    with pytest.raises(sqlite3.IntegrityError):
        make_invoice(conn, itype="Credit memo")


@pytest.mark.parametrize("sql", [
    "INSERT INTO invoice (invoice_type, ledger_side, invoice_number, issue_date, due_date, total_cents) "
    "VALUES ('Invoice', 'Sales', 'NEG', '2026-03-01', '2026-03-31', -1)",
    "INSERT INTO invoice (invoice_type, ledger_side, invoice_number, issue_date, due_date, tax_cents) "
    "VALUES ('Invoice', 'Sales', 'NEG', '2026-03-01', '2026-03-31', -1)",
    "INSERT INTO invoice_line (unit_price_cents) VALUES (-100)",
    "INSERT INTO invoice_line (quantity, unit_price_cents) VALUES (-1, 100)",
    "INSERT INTO payment (payment_date, amount_cents) VALUES ('2026-03-01', -500)",
    "INSERT INTO payment (payment_date, amount_cents) VALUES ('2026-03-01', 0)",
    "INSERT INTO payment_allocation (amount_applied_cents) VALUES (-5)",
    "INSERT INTO payment_allocation (amount_applied_cents) VALUES (0)",
])
def test_document_amounts_are_positive(conn, sql):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_signed_cents():
    from modules.ledger_rules import DOCUMENT_SIGN, signed_cents

    assert set(DOCUMENT_SIGN) == {"Invoice", "Credit Memo", "Bill"}
    assert signed_cents("Invoice", 1250) == 1250
    assert signed_cents("Bill", 1250) == 1250
    assert signed_cents("Credit Memo", 1250) == -1250
    for bad in [("Credit memo", 1), ("Invoice", -1), ("Invoice", 12.5), ("Invoice", "100"), ("Invoice", True)]:
        with pytest.raises((ValueError, TypeError)):
            signed_cents(*bad)


def test_invoice_lock_compares_every_invoice_column(conn):
    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='invoice_lock'"
    ).fetchone()[0]
    for column in conn.execute("PRAGMA table_info(invoice)"):
        name = column["name"]
        if name != "status":  # status is governed by invoice_status_flow
            assert f"NEW.{name} IS OLD.{name}" in trigger_sql, name


def test_eis_flag_can_be_set_on_sent_invoice(conn):
    invoice_id = make_invoice(conn, status="Sent")
    conn.execute("UPDATE invoice SET is_eis_transmitted = 1 WHERE invoice_id = ?", (invoice_id,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE invoice SET is_eis_transmitted = 0 WHERE invoice_id = ?", (invoice_id,))
