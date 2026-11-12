"""Phase 2.5 step 1: baseline additions for the ledger and billing services.

Each addition is integrity (CHECK, index, lock or audit coverage, decision H4); the posting rules
that use them live in modules/services/ledger.py and billing.py and are tested there.
"""
import json
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


def entry(conn, entry_id):
    return dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone())


def insert_entry_sql(**columns):
    values = {"entry_date": "2026-03-15", "description": "t", "created_by": 1, **columns}
    names = ", ".join(["period_id", *values])
    marks = ", ".join(["(SELECT period_id FROM fiscal_period WHERE '2026-03-15' BETWEEN start_date AND end_date)",
                       *["?"] * len(values)])
    return f"INSERT INTO journal_entry ({names}) VALUES ({marks})", tuple(values.values())


# --- journal_entry.source: 'Conversion' (L8) ---------------------------------

def test_conversion_is_an_entry_source(conn):
    ensure_period(conn, "2026-03-15")
    assert not rejects(conn, *insert_entry_sql(source="Conversion"))
    assert rejects(conn, *insert_entry_sql(source="Opening"))


# --- journal_entry.auto_reverse_date (L5) ------------------------------------

@pytest.mark.parametrize("value, rejected", [
    ("2026-04-01", False),
    ("2026-03-16", False),
    ("2026-03-15", True),    # same day as the entry
    ("2026-03-14", True),    # before the entry
    ("04/01/2026", True),    # not ISO
    ("2026-02-30", True),    # not a date
])
def test_auto_reverse_date_is_an_iso_date_after_the_entry(conn, value, rejected):
    ensure_period(conn, "2026-03-15")
    assert rejects(conn, *insert_entry_sql(auto_reverse_date=value)) is rejected


def test_a_reversal_cannot_schedule_its_own_auto_reversal(conn):
    original = posted_entry(conn)
    ensure_period(conn, "2026-03-15")
    assert rejects(conn, *insert_entry_sql(reverses_entry_id=original, reversal_reason="Accrual reversal",
                                           auto_reverse_date="2026-04-01"))


# --- journal_entry.reversal_note ---------------------------------------------

@pytest.mark.parametrize("reason, note, rejected", [
    ("Void", None, True),
    ("Void", "   ", True),
    ("Void", "", True),
    ("Void", "Duplicate of entry 12", False),
    ("Correction", None, True),
    ("Correction", "Wrong account", False),
    ("Accrual reversal", None, False),
])
def test_void_and_correction_need_a_note(conn, reason, note, rejected):
    original = posted_entry(conn)
    assert rejects(conn, *insert_entry_sql(reverses_entry_id=original, reversal_reason=reason,
                                           reversal_note=note)) is rejected


def test_only_a_reversal_carries_a_reversal_note(conn):
    ensure_period(conn, "2026-03-15")
    assert rejects(conn, *insert_entry_sql(reversal_note="not a reversal"))


# --- reversal slots: one Void/Correction and one Accrual reversal per entry --

def test_reverses_entry_id_has_no_plain_unique(conn):
    table_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'journal_entry'").fetchone()[0]
    line = next(text for text in table_sql.splitlines() if "reverses_entry_id INTEGER" in text)
    assert "UNIQUE" not in line
    indexes = {row[0]: row[1] for row in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'journal_entry'")}
    assert "'Void', 'Correction'" in indexes["journal_entry_one_void_or_correction"]
    assert "'Accrual reversal'" in indexes["journal_entry_one_accrual_reversal"]


@pytest.mark.parametrize("first, second, allowed", [
    ("Void", "Void", False),
    ("Void", "Correction", False),
    ("Correction", "Void", False),
    ("Correction", "Correction", False),
    ("Accrual reversal", "Accrual reversal", False),
    ("Accrual reversal", "Void", True),
    ("Accrual reversal", "Correction", True),   # allowed by the schema; ledger.reverse_entry refuses it
    ("Void", "Accrual reversal", True),          # allowed by the schema; a voided entry never posts one
])
def test_reversal_slots(conn, first, second, allowed):
    original = posted_entry(conn)
    make_reversal(conn, original, first)
    if allowed:
        make_reversal(conn, original, second)
    else:
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            make_reversal(conn, original, second)


def gl_balance(conn, *, through=None):
    sql = ("SELECT l.account_id, SUM(l.debit_cents - l.credit_cents) FROM journal_line AS l "
           "JOIN journal_entry AS e ON e.entry_id = l.entry_id WHERE e.is_posted = 1")
    params = ()
    if through:
        sql += " AND e.entry_date <= ?"
        params = (through,)
    return {account: total for account, total in conn.execute(sql + " GROUP BY l.account_id", params) if total}


def test_the_accrual_pair_can_be_voided_at_schema_level(conn):
    accrual = posted_entry(conn, 5000, entry_date="2026-03-31", auto_reverse_date="2026-04-01")
    auto = make_reversal(conn, accrual, "Accrual reversal", entry_date="2026-04-01")
    post(conn, auto)
    assert gl_balance(conn, through="2026-03-31")      # the accrual stands at month end
    assert gl_balance(conn) == {}                       # and is gone after the reversal date

    void_original = make_reversal(conn, accrual, "Void", entry_date="2026-04-10")
    void_auto = make_reversal(conn, auto, "Void", entry_date="2026-04-10")
    post(conn, void_original)
    post(conn, void_auto)

    assert entry(conn, accrual)["is_void"] == 1
    assert entry(conn, auto)["is_void"] == 1
    assert gl_balance(conn) == {}


# --- journal_line flags: is_control_override (A5) and is_rounding_adjustment (L8)

@pytest.mark.parametrize("column", ["is_control_override", "is_rounding_adjustment"])
def test_line_flags_default_to_zero_and_take_zero_or_one(conn, column):
    entry_id = make_entry(conn, [(100, 0), (0, 100)])
    account = make_account(conn, "9001")
    line = conn.execute("INSERT INTO journal_line (entry_id, account_id, debit_cents) VALUES (?, ?, 1) "
                        "RETURNING line_id", (entry_id, account)).fetchone()[0]
    assert conn.execute(f"SELECT {column} FROM journal_line WHERE line_id = ?", (line,)).fetchone()[0] == 0
    assert not rejects(conn, f"UPDATE journal_line SET {column} = 1 WHERE line_id = ?", (line,))
    assert rejects(conn, f"UPDATE journal_line SET {column} = 2 WHERE line_id = ?", (line,))
    assert rejects(conn, f"UPDATE journal_line SET {column} = NULL WHERE line_id = ?", (line,))


@pytest.mark.parametrize("column", ["is_control_override", "is_rounding_adjustment"])
def test_line_flags_are_locked_once_posted(conn, column):
    entry_id = posted_entry(conn)
    line = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ? LIMIT 1", (entry_id,)).fetchone()[0]
    assert rejects(conn, f"UPDATE journal_line SET {column} = 1 WHERE line_id = ?", (line,))


@pytest.mark.parametrize("column, value", [
    ("auto_reverse_date", "2026-05-01"),
    ("reversal_note", "changed"),
])
def test_new_entry_columns_are_locked_once_posted(conn, column, value):
    original = posted_entry(conn)
    reversal = make_reversal(conn, original, "Void")
    post(conn, reversal)
    target = reversal if column == "reversal_note" else original
    assert rejects(conn, f"UPDATE journal_entry SET {column} = ? WHERE entry_id = ?", (value, target))


def test_lock_trigger_names_the_new_columns(conn):
    entry_lock = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'journal_entry_lock_posted'").fetchone()[0]
    line_lock = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'journal_line_lock_update_posted'").fetchone()[0]
    for column in ("auto_reverse_date", "reversal_note"):
        assert f"NEW.{column} IS OLD.{column}" in entry_lock
    for column in ("is_control_override", "is_rounding_adjustment"):
        assert f"NEW.{column} IS OLD.{column}" in line_lock


# --- audit coverage -----------------------------------------------------------

def audit_rows(conn, entry_id):
    return [dict(row) for row in conn.execute(
        "SELECT action, old_value, new_value FROM audit_log WHERE table_name = 'journal_entry' AND record_id = ? "
        "ORDER BY log_id", (entry_id,))]


def test_audit_records_the_new_entry_and_line_columns(conn):
    original = posted_entry(conn, auto_reverse_date="2026-04-01")
    reversal = make_reversal(conn, original, "Void", note="Entered twice")
    post(conn, reversal)

    inserted = json.loads(audit_rows(conn, original)[0]["new_value"])
    assert inserted["auto_reverse_date"] == "2026-04-01"
    posted = json.loads(next(r for r in audit_rows(conn, reversal) if r["action"] == "Post")["new_value"])
    assert posted["reversal_note"] == "Entered twice"
    assert {"is_control_override", "is_rounding_adjustment"} <= set(posted["lines"][0])
    for trigger in ("audit_journal_entry_insert", "audit_journal_entry_update", "audit_journal_entry_delete"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (trigger,)).fetchone()[0]
        assert "'auto_reverse_date'" in sql and "'reversal_note'" in sql


# --- payment_allocation: exactly one target document --------------------------

@pytest.fixture
def payment(conn):
    contact = make_contact(conn, "Payer")
    return conn.execute("INSERT INTO payment (direction, contact_id, payment_date, amount_cents) "
                        "VALUES ('Received', ?, '2026-03-20', 1000) RETURNING payment_id", (contact,)).fetchone()[0]


def deferral(conn):
    return conn.execute("INSERT INTO deferral (original_amount_cents, start_date, end_date) "
                        "VALUES (1200, '2026-03-01', '2027-02-28') RETURNING deferral_id").fetchone()[0]


def allocation_sql(payment_id, invoice_id, deferral_id):
    return ("INSERT INTO payment_allocation (payment_id, invoice_id, deferral_id, amount_applied_cents) "
            "VALUES (?, ?, ?, 100)", (payment_id, invoice_id, deferral_id))


def test_allocation_names_an_invoice_or_a_deferral(conn, payment):
    invoice = make_invoice(conn, status="Sent")
    assert not rejects(conn, *allocation_sql(payment, invoice, None))
    assert not rejects(conn, *allocation_sql(payment, None, deferral(conn)))


def test_allocation_needs_exactly_one_target(conn, payment):
    invoice = make_invoice(conn, status="Sent")
    assert rejects(conn, *allocation_sql(payment, None, None))
    assert rejects(conn, *allocation_sql(payment, invoice, deferral(conn)))


# --- period_close_check: control_overrides (A5, L2) ---------------------------

def test_control_overrides_close_check_is_seeded_as_a_warning(conn):
    modes = dict(conn.execute("SELECT check_code, mode FROM period_close_check").fetchall())
    assert modes["control_overrides"] == "warn"
    assert not rejects(conn, "UPDATE period_close_check SET mode = 'block' WHERE check_code = 'control_overrides'")
    assert rejects(conn, "INSERT INTO period_close_check (check_code) VALUES ('made_up')")
