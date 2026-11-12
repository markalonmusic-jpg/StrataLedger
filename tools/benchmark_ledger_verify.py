"""Benchmark ledger verification (decision K12: measured and reported, not a pass/fail test).

Builds a throwaway company database in a temporary folder with N sealed entries of 3 lines each, then times a
full verification and an incremental verification of 100 new entries after a checkpoint. Nothing outside the
temporary folder is touched. The posting triggers are dropped in the throwaway file so it can be filled quickly;
the verification code is the real one.

    python tools/benchmark_ledger_verify.py [N]        (default 100000)
"""
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import modules.database as database  # noqa: E402
from modules.services import ledger_chain, ledger_verify  # noqa: E402

KEY = bytes(range(32))
CODE = "BENCH"


def build(path, count):
    database.ensure_company_database(path)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name IN "
                                "('journal_entry', 'journal_line', 'entry_number_sequence')").fetchall():
        conn.execute(f'DROP TRIGGER "{name}"')
    conn.execute("BEGIN")
    period = conn.execute("INSERT INTO fiscal_period (name, start_date, end_date, is_closed) "
                          "VALUES ('2026-03', '2026-03-01', '2026-03-31', 0) RETURNING period_id").fetchone()[0]
    type_id = conn.execute("SELECT type_id FROM account_type WHERE name = 'Asset'").fetchone()[0]
    accounts = [conn.execute("INSERT INTO account (code, name, type_id) VALUES (?, ?, ?) RETURNING account_id",
                             (code, f"Account {code}", type_id)).fetchone()[0] for code in ("1010", "1020", "4010")]
    key_id = conn.execute("INSERT INTO ledger_chain_key (fingerprint, created_at) VALUES (?, '2026-01-01T00:00:00Z') "
                          "RETURNING key_id", (ledger_chain.fingerprint(KEY),)).fetchone()[0]
    conn.execute("COMMIT")
    append(conn, period, accounts, key_id, 1, count)
    conn.close()
    return period, accounts, key_id


def append(conn, period, accounts, key_id, first, count):
    prev = ledger_chain.GENESIS
    if first > 1:
        prev = conn.execute("SELECT chain_hash FROM journal_entry WHERE entry_number = ?", (first - 1,)).fetchone()[0]
    entries, lines = [], []
    line_id = (conn.execute("SELECT COALESCE(MAX(line_id), 0) FROM journal_line").fetchone()[0]) + 1
    for number in range(first, first + count):
        amount = 100 + number % 997
        header = {"entry_id": number, "entry_number": number, "entry_date": "2026-03-15", "period_id": period,
                  "reference": None, "description": f"Entry {number}", "source": "Manual", "origin": "Human",
                  "created_by": 1, "created_at": "2026-03-15 09:00:00", "posted_by": 1,
                  "posted_at": "2026-03-15T10:00:00+00:00", "approved_by": None, "approved_at": None,
                  "reverses_entry_id": None, "reversal_reason": None, "reversal_note": None,
                  "auto_reverse_date": None, "chain_version": 1, "chain_key_id": key_id}
        entry_lines = []
        for account, debit, credit in ((accounts[0], amount, 0), (accounts[1], amount, 0), (accounts[2], 0, 2 * amount)):
            entry_lines.append({"line_id": line_id, "entry_id": number, "account_id": account, "debit_cents": debit,
                                "credit_cents": credit, "memo": None, "contact_id": None, "project_id": None,
                                "cost_code_id": None, "deferral_id": None, "batch_id": None, "is_retainage_line": 0,
                                "external_ref": None, "is_control_override": 0, "is_rounding_adjustment": 0})
            line_id += 1
        chain_hash = ledger_chain.seal(KEY, CODE, prev, ledger_chain.canonical_entry(header, entry_lines, ()))
        entries.append({**header, "is_posted": 1, "is_void": 0, "chain_prev_hash": prev, "chain_hash": chain_hash})
        lines.extend(entry_lines)
        prev = chain_hash
    conn.execute("BEGIN")
    columns = list(entries[0])
    conn.executemany(f"INSERT INTO journal_entry ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                     [tuple(e[c] for c in columns) for e in entries])
    line_columns = list(lines[0])
    conn.executemany(f"INSERT INTO journal_line ({', '.join(line_columns)}) VALUES "
                     f"({', '.join('?' * len(line_columns))})", [tuple(l[c] for c in line_columns) for l in lines])
    conn.execute("UPDATE entry_number_sequence SET last_number = ?", (first + count - 1,))
    conn.execute("COMMIT")


def checkpoint(conn, key_id, through):
    head = conn.execute("SELECT chain_hash FROM journal_entry WHERE entry_number = ?", (through,)).fetchone()[0]
    row = {"created_at": "2026-03-20T00:00:00+00:00", "created_by": 1, "kind": "Verify", "scope": "Full",
           "result": "OK", "through_entry_number": through, "chain_hash": head, "first_broken_entry_number": None,
           "key_id": key_id, "ref_type": None, "ref_id": None}
    row["mac"] = ledger_chain.checkpoint_mac(KEY, CODE, row)
    conn.execute(f"INSERT INTO ledger_checkpoint ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                 tuple(row.values()))


def timed(conn, mode):
    start = time.perf_counter()
    result = ledger_verify.verify_connection(conn, CODE, lambda key_id: KEY, mode=mode)
    return time.perf_counter() - start, result


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "bench.db")
        started = time.perf_counter()
        period, accounts, key_id = build(path, count)
        print(f"built {count} entries x 3 lines in {time.perf_counter() - started:.1f} s")
        conn = sqlite3.connect(path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        seconds, result = timed(conn, "full")
        print(f"full verify of {count} entries: {seconds:.2f} s, {result['status']} through {result['through_entry_number']}")
        checkpoint(conn, key_id, count)
        append(conn, period, accounts, key_id, count + 1, 100)
        seconds, result = timed(conn, "incremental")
        print(f"incremental verify of 100 new entries: {seconds:.3f} s, {result['status']} ({result['scope']}) "
              f"through {result['through_entry_number']}")
        conn.close()


if __name__ == "__main__":
    main()
