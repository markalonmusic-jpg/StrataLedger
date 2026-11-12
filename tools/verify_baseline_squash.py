"""Prove that the baseline files equal the migration chain they replaced.

Builds a database from the archived chain (archive/migrations_chain_v5/) and one
from the current baseline (migrations/), for both the company and the master
database, and compares:

  * every sqlite_master row (type, name, tbl_name, raw SQL text);
  * table_xinfo, index_xinfo and foreign_key_list for every table and index;
  * the rows of every table (this covers the seeds: permission, role,
    role_permission, audit_context, account_type, entry_number_sequence, and
    the empty company_settings).

Not compared, by design:
  * schema_version contents (the chain has 1-5 / 1-3, the baseline has 1) and
    the runner-owned schema_baseline table;
  * role.created_at (the seed uses the current time);
  * sqlite_sequence rows with seq = 0 (rebuilt tables carry them, a direct
    CREATE TABLE does not; both start numbering at 1).

Valid only for the squash commit itself ("Squash migrations into baseline v1").
Later baseline edits (the approval_request fix, the cleanups) intentionally
differ from the archived chain, so the tool reports differences from then on.

Usage (from the project root):
    python tools/verify_baseline_squash.py
Exit status 0 means zero differences.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import modules.database as database  # noqa: E402

CHAIN_DIR = ROOT / "archive" / "migrations_chain_v5"
CHAIN = {
    "company": [(1, "001_company.sql"), (2, "002_company.sql"), (3, "003_company.sql"),
                (4, "004_company.sql"), (5, "005_company.sql")],
    "master": [(1, "001_master.sql"), (2, "002_master.sql"), (3, "003_master.sql")],
}
SKIP_TABLES = {"schema_version", "schema_baseline", "sqlite_sequence"}
MASKED = {("role", "created_at")}


def build(kind, workdir, chain):
    path = os.path.join(workdir, f"{kind}_{'chain' if chain else 'baseline'}.db")
    saved = (database.MIGRATIONS_DIR, database.MIGRATIONS, database.MASTER_MIGRATIONS, database.BACKUP_DIR)
    try:
        database.BACKUP_DIR = os.path.join(workdir, "Backups")
        if chain:
            database.MIGRATIONS_DIR = str(CHAIN_DIR)
            database.MIGRATIONS = CHAIN["company"]
            database.MASTER_MIGRATIONS = CHAIN["master"]
        (database.ensure_company_database if kind == "company" else database.ensure_master_database)(path)
    finally:
        database.MIGRATIONS_DIR, database.MIGRATIONS, database.MASTER_MIGRATIONS, database.BACKUP_DIR = saved
    return path


def snapshot(path):
    conn = sqlite3.connect(path)
    snap = {}
    try:
        masters = conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        for kind, name, tbl_name, sql in masters:
            if name in SKIP_TABLES:
                continue
            snap[("master", kind, name)] = (tbl_name, sql)
            if kind == "table":
                snap[("xinfo", name)] = conn.execute(f'PRAGMA table_xinfo("{name}")').fetchall()
                snap[("fk", name)] = sorted(conn.execute(f'PRAGMA foreign_key_list("{name}")').fetchall())
                columns = [c[1] for c in conn.execute(f'PRAGMA table_info("{name}")')]
                keep = [i for i, c in enumerate(columns) if (name, c) not in MASKED]
                rows = [tuple(r[i] for i in keep) for r in conn.execute(f'SELECT * FROM "{name}"')]
                snap[("rows", name)] = sorted(rows, key=repr)
            elif kind == "index":
                snap[("index_xinfo", name)] = conn.execute(f'PRAGMA index_xinfo("{name}")').fetchall()
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").fetchone():
            snap[("sequence",)] = sorted(conn.execute("SELECT name, seq FROM sqlite_sequence WHERE seq > 0").fetchall())
    finally:
        conn.close()
    return snap


def compare(kind, a, b):
    problems = []
    for key in sorted(set(a) | set(b), key=repr):
        if a.get(key, "<missing>") != b.get(key, "<missing>"):
            problems.append(f"{kind}: {key} differs")
    return problems


def main():
    problems = []
    with tempfile.TemporaryDirectory() as workdir:
        for kind in ("company", "master"):
            chain_snap = snapshot(build(kind, workdir, chain=True))
            base_snap = snapshot(build(kind, workdir, chain=False))
            diffs = compare(kind, chain_snap, base_snap)
            tables = sum(1 for k in base_snap if k[0] == "master" and k[1] == "table")
            indexes = sum(1 for k in base_snap if k[0] == "master" and k[1] == "index")
            triggers = sum(1 for k in base_snap if k[0] == "master" and k[1] == "trigger")
            seeded = sum(len(v) for k, v in base_snap.items() if k[0] == "rows")
            print(f"{kind}: {tables} tables, {indexes} indexes, {triggers} triggers, "
                  f"{seeded} seed rows compared; differences: {len(diffs)}")
            problems.extend(diffs)
    for line in problems:
        print("DIFF", line)
    print("ZERO DIFFERENCES" if not problems else f"{len(problems)} DIFFERENCES")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
