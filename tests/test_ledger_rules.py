"""F2-F7: ledger integrity rules enforced by the company schema."""
import re
import sqlite3

import pytest

import modules.database as database

POSTED = "Posted journal entries"
MONEY_COLUMNS_WITHOUT_SUFFIX = {("progress_billing_application", "less_previous_applied")}
MASTER_ONLY_TABLES = {"app_user", "company_registry", "user_company_access"}


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def user_tables(conn):
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


# Schema version 4+ needs service-like helpers (covering periods, posting
# numbers, invoice series); they live in tests/ledger_helpers.py.
from tests.ledger_helpers import (  # noqa: E402
    ensure_period, make_account, make_entry, make_period, post, set_period_closed,
)


@pytest.fixture
def posted_entry(conn):
    entry_id = make_entry(conn, [(1000, 0), (0, 1000)])
    post(conn, entry_id)
    return entry_id


def test_posted_lock_trigger_compares_every_journal_entry_column(conn):
    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='journal_entry_lock_posted'"
    ).fetchone()[0]
    for column in conn.execute("PRAGMA table_info(journal_entry)"):
        name = column["name"]
        if name not in {"is_posted", "is_void"}:
            assert f"NEW.{name} IS OLD.{name}" in trigger_sql, name


# --- F2: foreign keys point at real columns ---------------------------------

def test_every_foreign_key_targets_an_existing_column(conn):
    problems = []
    for table in user_tables(conn):
        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            parent = fk["table"]
            parent_columns = {c["name"]: c for c in conn.execute(f'PRAGMA table_info("{parent}")')}
            if not parent_columns:
                problems.append(f"{table}.{fk['from']} -> missing table {parent}")
            elif fk["to"] is not None and fk["to"] not in parent_columns:
                problems.append(f"{table}.{fk['from']} -> {parent}.{fk['to']} (no such column)")
    assert problems == []
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_project_budget_and_estimate_line_are_usable(conn):
    contact_id = conn.execute("INSERT INTO contact (name) VALUES ('Client') RETURNING contact_id").fetchone()[0]
    cost_code_id = conn.execute(
        "INSERT INTO cost_code (code, name, cost_type_label) VALUES ('03-300', 'Concrete', 'Cement') "
        "RETURNING cost_code_id"
    ).fetchone()[0]
    estimate_id = conn.execute(
        "INSERT INTO estimate (estimate_number, name, contact_id) VALUES ('EST-1', 'Bid', ?) "
        "RETURNING estimate_id",
        (contact_id,),
    ).fetchone()[0]
    line_ids = [
        conn.execute(
            "INSERT INTO estimate_line (estimate_id, cost_code_id, quantity, unit_of_measure, "
            "estimated_unit_cost_cents, estimated_extended_cost_cents, price_to_customer_cents) "
            "VALUES (?, ?, 1, 'Bags', 100, 100, 150) RETURNING line_id",
            (estimate_id, cost_code_id),
        ).fetchone()[0]
        for _ in range(2)
    ]
    conn.execute(
        "INSERT INTO project_budget (cost_code_id, estimate_line_id, budget_cents) VALUES (?, ?, 100)",
        (cost_code_id, line_ids[0]),
    )
    conn.execute("DELETE FROM estimate_line WHERE line_id = ?", (line_ids[1],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM estimate_line WHERE line_id = ?", (line_ids[0],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO project_budget (estimate_line_id, budget_cents) VALUES (999999, 100)"
        )


# --- F3: posted entries are locked ------------------------------------------

def test_posted_entry_cannot_be_unposted(conn, posted_entry):
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute("UPDATE journal_entry SET is_posted = 0 WHERE entry_id = ?", (posted_entry,))
    assert conn.execute(
        "SELECT is_posted FROM journal_entry WHERE entry_id = ?", (posted_entry,)
    ).fetchone()[0] == 1


@pytest.mark.parametrize("assignment", [
    "description = 'edited'",
    "entry_date = '2026-04-01'",
    "reference = 'X'",
    "is_posted = 1",
    "is_void = 1, description = 'void with edit'",
])
def test_posted_entry_header_is_locked(conn, posted_entry, assignment):
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute(f"UPDATE journal_entry SET {assignment} WHERE entry_id = ?", (posted_entry,))


def test_posted_entry_cannot_be_deleted(conn, posted_entry):
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute("DELETE FROM journal_entry WHERE entry_id = ?", (posted_entry,))


def test_posted_entry_lines_are_locked(conn, posted_entry):
    line_id, account_id = conn.execute(
        "SELECT line_id, account_id FROM journal_line WHERE entry_id = ? ORDER BY line_id", (posted_entry,)
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute(
            "INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, ?, 5, 0)",
            (posted_entry, account_id),
        )
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute("UPDATE journal_line SET memo = 'edited' WHERE line_id = ?", (line_id,))
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute("DELETE FROM journal_line WHERE line_id = ?", (line_id,))
    draft_id = make_entry(conn, [(1, 0)])
    draft_line = conn.execute("SELECT line_id FROM journal_line WHERE entry_id = ?", (draft_id,)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute("UPDATE journal_line SET entry_id = ? WHERE line_id = ?", (posted_entry, draft_line))


def test_posted_entry_is_voided_only_by_a_void_reversal(conn, posted_entry):
    from tests.test_controls_003 import make_reversal

    before = dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (posted_entry,)).fetchone())
    with pytest.raises(sqlite3.IntegrityError, match=POSTED):
        conn.execute("UPDATE journal_entry SET is_void = 1 WHERE entry_id = ?", (posted_entry,))

    post(conn, make_reversal(conn, posted_entry, "Void"))

    after = dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (posted_entry,)).fetchone())
    assert after == {**before, "is_void": 1}
    for assignment in ("is_void = 0", "description = 'edited'", "is_posted = 0"):
        with pytest.raises(sqlite3.IntegrityError, match=POSTED):
            conn.execute(f"UPDATE journal_entry SET {assignment} WHERE entry_id = ?", (posted_entry,))


def test_posted_flags_only_accept_zero_or_one(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO journal_entry (entry_date, period_id, is_posted) VALUES ('2026-01-01', ?, 2)",
                     (ensure_period(conn, '2026-01-01'),))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO journal_entry (entry_date, period_id, is_void) VALUES ('2026-01-01', ?, 'yes')",
                     (ensure_period(conn, '2026-01-01'),))


# --- F4: closed periods -------------------------------------------------------

def test_posting_into_closed_period_is_rejected(conn):
    period_id = make_period(conn, "2026-03", "2026-03-01", "2026-03-31", closed=True)
    entry_id = make_entry(conn, [(500, 0), (0, 500)], period_id=period_id)
    with pytest.raises(sqlite3.IntegrityError, match="closed"):
        post(conn, entry_id)


def test_posting_dated_inside_closed_period_is_rejected(conn):
    make_period(conn, "2026-03", "2026-03-01", "2026-03-31", closed=True)
    entry_id = make_entry(conn, [(500, 0), (0, 500)], entry_date="2026-03-20")
    with pytest.raises(sqlite3.IntegrityError, match="closed"):
        post(conn, entry_id)


def test_posting_into_open_period_succeeds(conn):
    make_period(conn, "2026-03", "2026-03-01", "2026-03-31", closed=True)
    open_id = make_period(conn, "2026-04", "2026-04-01", "2026-04-30", closed=False)
    entry_id = make_entry(conn, [(500, 0), (0, 500)], entry_date="2026-04-02", period_id=open_id)
    post(conn, entry_id)
    assert conn.execute("SELECT is_posted FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()[0] == 1


# --- F5: posting rule ---------------------------------------------------------

@pytest.mark.parametrize("lines", [
    pytest.param([], id="no-lines"),
    pytest.param([(0, 0)], id="one-blank-line"),
    pytest.param([(500, 0)], id="one-line"),
    pytest.param([(0, 0), (0, 0)], id="two-blank-lines"),
    pytest.param([(500, 0), (0, 500), (0, 0)], id="balanced-plus-blank-line"),
    pytest.param([(500, 0), (0, 400)], id="unbalanced"),
    pytest.param([(500, 0), (None, 500)], id="null-side"),
])
def test_invalid_entries_cannot_post(conn, lines):
    entry_id = make_entry(conn, lines)
    with pytest.raises(sqlite3.IntegrityError):
        post(conn, entry_id)
    assert conn.execute("SELECT is_posted FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()[0] == 0


def test_line_with_both_sides_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        make_entry(conn, [(500, 500), (0, 0)])


def test_balanced_entry_posts(conn):
    entry_id = make_entry(conn, [(700, 0), (300, 0), (0, 1000)])
    post(conn, entry_id)
    assert conn.execute("SELECT is_posted FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone()[0] == 1


def test_entries_still_cannot_be_inserted_as_posted(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO journal_entry (entry_date, period_id, is_posted) VALUES ('2026-01-01', ?, 1)",
                     (ensure_period(conn, '2026-01-01'),))


# --- F6: master user IDs are plain integers -----------------------------------

def test_company_has_no_master_tables(conn):
    tables = set(user_tables(conn))
    assert tables.isdisjoint(MASTER_ONLY_TABLES)
    assert "audit_log" in tables
    for table in tables:
        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            assert fk["table"] not in MASTER_ONLY_TABLES, f"{table}.{fk['from']} -> {fk['table']}"


def test_user_ids_store_without_local_user_table(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    contact_id = conn.execute("INSERT INTO contact (name) VALUES ('Client') RETURNING contact_id").fetchone()[0]
    conn.execute("INSERT INTO journal_entry (entry_date, period_id, created_by) VALUES ('2026-01-01', ?, 42)",
                 (ensure_period(conn, '2026-01-01'),))
    conn.execute(
        "INSERT INTO project (project_number, name, contact_id, assigned_pm_id) VALUES ('P-1', 'Job', ?, 42)",
        (contact_id,),
    )
    conn.execute("INSERT INTO staged_transaction (approved_by) VALUES (42)")
    conn.execute(
        "INSERT INTO audit_log (user_id, table_name, record_id, action) VALUES (42, 'journal_entry', 1, 'Insert')"
    )
    assert conn.execute("SELECT created_by FROM journal_entry").fetchone()[0] == 42


# --- F7: money columns hold integers only -------------------------------------

def money_columns(conn):
    for table in user_tables(conn):
        for column in conn.execute(f'PRAGMA table_info("{table}")'):
            name = column["name"]
            if name.endswith("_cents") or (table, name) in MONEY_COLUMNS_WITHOUT_SUFFIX:
                yield table, name, bool(column["notnull"])


def test_every_money_column_has_integer_check(conn):
    missing = []
    for table, column, _notnull in money_columns(conn):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0]
        pattern = rf"typeof\(\s*\"?{column}\"?\s*\)\s*=\s*'integer'"
        if not re.search(pattern, sql, re.IGNORECASE):
            missing.append(f"{table}.{column}")
    assert missing == []
    assert len(list(money_columns(conn))) > 50


@pytest.fixture
def money_rows(conn):
    """Insert statements for one money column per table, taking the value as the last parameter."""
    contact_id = conn.execute("INSERT INTO contact (name) VALUES ('Worker') RETURNING contact_id").fetchone()[0]
    entry_id = make_entry(conn, [])
    account_id = make_account(conn, "M-1")
    return {
        "journal_line": (
            "INSERT INTO journal_line (entry_id, account_id, credit_cents, debit_cents) VALUES (?, ?, 0, ?)",
            (entry_id, account_id),
        ),
        "time_entry": (
            "INSERT INTO time_entry (contact_id, work_date, hours, burden_cents, wage_cents) "
            "VALUES (?, '2026-01-01', 8, 0, ?)",
            (contact_id,),
        ),
        "invoice": (
            "INSERT INTO invoice (invoice_type, ledger_side, invoice_number, issue_date, due_date, total_cents) "
            "VALUES ('Invoice', 'Sales', lower(hex(randomblob(8))), '2026-01-01', '2026-01-31', ?)",
            (),
        ),
        "project_budget": ("INSERT INTO project_budget (budget_cents) VALUES (?)", ()),
    }


@pytest.mark.parametrize("table", ["journal_line", "time_entry", "invoice", "project_budget"])
@pytest.mark.parametrize("bad_value", [25.5, "25.50", "abc", b"\x01"])
def test_money_columns_reject_non_integers(conn, money_rows, table, bad_value):
    sql, params = money_rows[table]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (*params, bad_value))


@pytest.mark.parametrize("table", ["journal_line", "time_entry", "invoice", "project_budget"])
def test_money_columns_accept_integers(conn, money_rows, table):
    sql, params = money_rows[table]
    conn.execute(sql, (*params, 2550))


def test_nullable_money_columns_still_accept_null(conn):
    conn.execute(
        "INSERT INTO invoice (invoice_type, ledger_side, invoice_number, issue_date, due_date, total_cents) "
        "VALUES ('Invoice', 'Sales', 'N-1', '2026-01-01', '2026-01-31', NULL)"
    )
    conn.execute("INSERT INTO staged_transaction (amount_cents) VALUES (NULL)")
