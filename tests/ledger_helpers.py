"""Test helpers that act like the (future) Phase 2 service layer, for schema version 4+.

Migration 004 requires what a service will do: entries carry the fiscal period
that covers their date, posting stamps a gapless entry number and who/when,
and sales documents take their number from an invoice series when they leave
Draft. Each multi-step helper runs inside a savepoint, like a service
transaction, so a rejected step leaves nothing half-done.
"""
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from modules.services import ledger_chain

USER = 1
APPROVER = 2
# Step 1b: the fixed chain key and company code the helpers seal with (tests only; never a real key).
TEST_CHAIN_KEY = hashlib.sha256(b"StrataLedger tests: fixed chain key").digest()
TEST_COMPANY_CODE = "TEST"


@contextmanager
def atomic(conn, name="helper"):
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        conn.execute(f"ROLLBACK TO {name}")
        conn.execute(f"RELEASE {name}")
        raise
    conn.execute(f"RELEASE {name}")


# --- periods -----------------------------------------------------------------

def _month_bounds(day):
    first = day.replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    return first, following - timedelta(days=1)


def _insert_period(conn, start, end, *, name=None, closed=False):
    return conn.execute(
        "INSERT INTO fiscal_period (name, start_date, end_date, is_closed, closed_at, closed_by) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING period_id",
        (
            name or start.isoformat()[:7],
            start.isoformat(),
            end.isoformat(),
            1 if closed else 0,
            "2026-01-01 00:00:00" if closed else None,
            USER if closed else None,
        ),
    ).fetchone()[0]


def ensure_period(conn, entry_date):
    """Return the period covering entry_date, adding contiguous month periods if needed."""
    row = conn.execute(
        "SELECT period_id FROM fiscal_period WHERE ? BETWEEN start_date AND end_date", (entry_date,)
    ).fetchone()
    if row:
        return row[0]
    target = date.fromisoformat(entry_date)
    bounds = conn.execute("SELECT MIN(start_date), MAX(end_date) FROM fiscal_period").fetchone()
    if bounds[0] is None:
        start, end = _month_bounds(target)
        return _insert_period(conn, start, end)
    first, last = date.fromisoformat(bounds[0]), date.fromisoformat(bounds[1])
    while target > last:
        start = last + timedelta(days=1)
        start, end = start, _month_bounds(start)[1]
        _insert_period(conn, start, end)
        last = end
    while target < first:
        end = first - timedelta(days=1)
        start = _month_bounds(end)[0]
        _insert_period(conn, start, end)
        first = start
    return ensure_period(conn, entry_date)


def make_period(conn, name, start, end, *, closed):
    """Create a period, or reuse the one with exactly these dates and set its state."""
    row = conn.execute(
        "SELECT period_id FROM fiscal_period WHERE start_date = ? AND end_date = ?", (start, end)
    ).fetchone()
    if row is None:
        ensure_period(conn, start)  # fills any gap before it
        row = conn.execute(
            "SELECT period_id FROM fiscal_period WHERE start_date = ? AND end_date = ?", (start, end)
        ).fetchone()
        if row is None:
            return _insert_period(conn, date.fromisoformat(start), date.fromisoformat(end), name=name, closed=closed)
    is_closed = conn.execute("SELECT is_closed FROM fiscal_period WHERE period_id = ?", (row[0],)).fetchone()[0]
    if bool(is_closed) != bool(closed):
        set_period_closed(conn, row[0], closed)
    return row[0]


def set_period_closed(conn, period_id, closed):
    if closed:
        conn.execute(
            "UPDATE fiscal_period SET is_closed = 1, closed_at = '2026-01-01 00:00:00', closed_by = ? "
            "WHERE period_id = ?",
            (USER, period_id),
        )
    else:
        conn.execute("UPDATE fiscal_period SET is_closed = 0 WHERE period_id = ?", (period_id,))


# --- accounts and entries ----------------------------------------------------

def type_id(conn, name="Asset"):
    return conn.execute("SELECT type_id FROM account_type WHERE name = ?", (name,)).fetchone()[0]


def make_account(conn, code, **columns):
    values = {"code": code, "name": f"Account {code}", "type_id": type_id(conn), **columns}
    sql = (f"INSERT INTO account ({', '.join(values)}) VALUES ({', '.join('?' * len(values))}) "
           "RETURNING account_id")
    return conn.execute(sql, tuple(values.values())).fetchone()[0]


def make_entry(conn, lines, *, entry_date="2026-03-15", period_id=None, created_by=USER, **columns):
    period_id = period_id or ensure_period(conn, entry_date)
    values = {"entry_date": entry_date, "period_id": period_id, "description": "test",
              "created_by": created_by, **columns}
    entry_id = conn.execute(
        f"INSERT INTO journal_entry ({', '.join(values)}) VALUES ({', '.join('?' * len(values))}) "
        "RETURNING entry_id",
        tuple(values.values()),
    ).fetchone()[0]
    for index, (debit, credit) in enumerate(lines):
        account_id = make_account(conn, f"{entry_id}-{index}")
        conn.execute(
            "INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, ?, ?, ?)",
            (entry_id, account_id, debit, credit),
        )
    return entry_id


def ensure_test_chain_key(conn):
    """The ledger_chain_key row for TEST_CHAIN_KEY, added (as the active key) on first use."""
    fingerprint = ledger_chain.fingerprint(TEST_CHAIN_KEY)
    row = conn.execute("SELECT key_id FROM ledger_chain_key WHERE fingerprint = ?", (fingerprint,)).fetchone()
    if row:
        return row[0]
    return conn.execute(
        "INSERT INTO ledger_chain_key (fingerprint, created_at, created_by) "
        "VALUES (?, '2026-01-01T00:00:00+00:00', ?) RETURNING key_id", (fingerprint, USER)).fetchone()[0]


def seal_columns(conn, entry_id, entry_number, posted_by, posted_at, *, key=TEST_CHAIN_KEY, key_id=None):
    """The four chain columns for posting entry_id as entry_number, sealed like the service will (step 3)."""
    key_id = key_id or ensure_test_chain_key(conn)
    previous = conn.execute("SELECT chain_hash FROM journal_entry WHERE entry_number = ?",
                            (entry_number - 1,)).fetchone()
    prev_hash = previous[0] if previous and previous[0] else ledger_chain.GENESIS
    header = dict(conn.execute("SELECT * FROM journal_entry WHERE entry_id = ?", (entry_id,)).fetchone())
    header.update(entry_number=entry_number, posted_by=posted_by, posted_at=posted_at,
                  chain_version=ledger_chain.CHAIN_VERSION, chain_key_id=key_id)
    lines = [dict(r) for r in conn.execute("SELECT * FROM journal_line WHERE entry_id = ?", (entry_id,))]
    dims = [dict(r) for r in conn.execute(
        "SELECT d.* FROM journal_line_dimension AS d JOIN journal_line AS l ON l.line_id = d.line_id "
        "WHERE l.entry_id = ?", (entry_id,))]
    chain_hash = ledger_chain.seal(key, TEST_COMPANY_CODE, prev_hash, ledger_chain.canonical_entry(header, lines, dims))
    return {"chain_version": ledger_chain.CHAIN_VERSION, "chain_key_id": key_id, "chain_prev_hash": prev_hash,
            "chain_hash": chain_hash}


def post(conn, entry_id, *, user=USER):
    """Post like the service will: take the next entry number, stamp who and when, and seal the entry."""
    with atomic(conn, "post_entry"):
        conn.execute("UPDATE entry_number_sequence SET last_number = last_number + 1 WHERE id = 1")
        number = conn.execute("SELECT last_number FROM entry_number_sequence WHERE id = 1").fetchone()[0]
        posted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        seal = seal_columns(conn, entry_id, number, user, posted_at)
        conn.execute(
            "UPDATE journal_entry SET is_posted = 1, entry_number = ?, posted_by = ?, posted_at = ?, "
            "chain_version = ?, chain_key_id = ?, chain_prev_hash = ?, chain_hash = ? WHERE entry_id = ?",
            (number, user, posted_at, seal["chain_version"], seal["chain_key_id"], seal["chain_prev_hash"],
             seal["chain_hash"], entry_id),
        )


def make_reversal(conn, original_id, reason, *, entry_date="2026-03-16", period_id=None, lines=None, note=None):
    """A Void or Correction carries a reversal note (required by the baseline); an Accrual reversal needs none."""
    period_id = period_id or ensure_period(conn, entry_date)
    if note is None and reason in ("Void", "Correction"):
        note = f"test {reason.lower()}"
    reversal_id = conn.execute(
        "INSERT INTO journal_entry (entry_date, period_id, reverses_entry_id, reversal_reason, reversal_note, "
        "created_by) VALUES (?, ?, ?, ?, ?, ?) RETURNING entry_id",
        (entry_date, period_id, original_id, reason, note, USER),
    ).fetchone()[0]
    if lines is None:
        lines = [
            (row[0], row[2], row[1])
            for row in conn.execute(
                "SELECT account_id, debit_cents, credit_cents FROM journal_line WHERE entry_id = ?",
                (original_id,),
            )
        ]
    for account_id, debit, credit in lines:
        conn.execute(
            "INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, ?, ?, ?)",
            (reversal_id, account_id, debit, credit),
        )
    return reversal_id


def posted_entry(conn, amount=1000, **kwargs):
    entry_id = make_entry(conn, [(amount, 0), (0, amount)], **kwargs)
    post(conn, entry_id)
    return entry_id


# --- invoices ----------------------------------------------------------------

def make_contact(conn, name="Client"):
    return conn.execute("INSERT INTO contact (name) VALUES (?) RETURNING contact_id", (name,)).fetchone()[0]


def make_series(conn, document_type="Invoice", prefix=None, *, registered=(None, None),
                valid_until=None, active=1, authority_ref=None):
    prefix = prefix or {"Invoice": "SI-", "Credit Memo": "CM-"}[document_type]
    start, end = registered
    return conn.execute(
        "INSERT INTO invoice_series (document_type, prefix, last_number, registered_from, registered_to, "
        "authority_ref, valid_until, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING series_id",
        (document_type, prefix, (start - 1) if start else 0, start, end, authority_ref, valid_until, active),
    ).fetchone()[0]


def series_for(conn, document_type):
    row = conn.execute(
        "SELECT series_id FROM invoice_series WHERE document_type = ? AND is_active = 1 ORDER BY series_id LIMIT 1",
        (document_type,),
    ).fetchone()
    return row[0] if row else make_series(conn, document_type)


def make_invoice(conn, *, itype="Invoice", ledger_side=None, contact_id=None, lines=((1, 1000),),
                 status="Draft", entry_id=None, number=None):
    ledger_side = ledger_side or ("Purchase" if itype == "Bill" else "Sales")
    contact_id = contact_id or make_contact(conn)
    subtotal = sum(round(quantity * price) for quantity, price in lines)
    invoice_id = conn.execute(
        "INSERT INTO invoice (invoice_type, ledger_side, contact_id, invoice_number, issue_date, due_date, "
        "subtotal_cents, total_cents) VALUES (?, ?, ?, ?, '2026-03-01', '2026-03-31', ?, ?) RETURNING invoice_id",
        (itype, ledger_side, contact_id, number, subtotal, subtotal),
    ).fetchone()[0]
    for quantity, price in lines:
        conn.execute(
            "INSERT INTO invoice_line (invoice_id, quantity, unit_price_cents) VALUES (?, ?, ?)",
            (invoice_id, quantity, price),
        )
    path = {"Draft": [], "Sent": ["Sent"], "Paid": ["Sent", "Paid"], "Void": ["Sent", "Void"],
            "Covered by advance": ["Covered by advance"]}[status]
    for index, step in enumerate(path):
        if index == 0:
            send_invoice(conn, invoice_id, status=step, entry_id=entry_id)
        else:
            conn.execute("UPDATE invoice SET status = ? WHERE invoice_id = ?", (step, invoice_id))
    return invoice_id


def send_invoice(conn, invoice_id, *, status="Sent", entry_id=None, series_id=None):
    """Leave Draft like the service will: sales documents take the next series number."""
    invoice_type, side, current_number = conn.execute(
        "SELECT invoice_type, ledger_side, invoice_number FROM invoice WHERE invoice_id = ?", (invoice_id,)
    ).fetchone()
    with atomic(conn, "send_invoice"):
        if side == "Sales":
            series_id = series_id or series_for(conn, invoice_type)
            conn.execute("UPDATE invoice_series SET last_number = last_number + 1 WHERE series_id = ?", (series_id,))
            conn.execute(
                "UPDATE invoice SET status = ?, entry_id = ?, series_id = s.series_id, "
                "sequence_number = s.last_number, invoice_number = s.prefix || printf('%06d', s.last_number) "
                "FROM (SELECT * FROM invoice_series WHERE series_id = ?) AS s WHERE invoice_id = ?",
                (status, entry_id, series_id, invoice_id),
            )
        else:
            conn.execute(
                "UPDATE invoice SET status = ?, entry_id = ?, invoice_number = ? WHERE invoice_id = ?",
                (status, entry_id, current_number or f"B-{invoice_id}", invoice_id),
            )


def set_user(conn, user_id):
    conn.execute("UPDATE audit_context SET user_id = ?, terminal_id = 'test' WHERE id = 1", (user_id,))


def rejects(conn, sql, params=()):
    """True if the statement is rejected by a constraint or trigger."""
    try:
        with atomic(conn, "probe"):
            conn.execute(sql, params)
    except sqlite3.IntegrityError:
        return True
    return False
