"""Phase 2.7 step B2: tests that kill the mutation-tester's surviving mutants (B-numbers in docs/status_log.md).

Each test names the mutants it kills. The equivalent survivors and their reasons are listed in docs/next_step.md."""
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
import modules.database as database
from modules.services.tx import AuditStamp
from tests.test_addon_database import KEY, applied, company, migrations, objects  # noqa: F401
from tests.test_addon_audit import audit_rows, company_rows, triggers  # noqa: F401
from tests.test_connections_backup import _fake_backups, _changed_copy, _crashed_with_wal, sha256


def stamp():
    return AuditStamp(SimpleNamespace(user_id=7, now="2026-11-17T00:00:00+00:00"))


@pytest.mark.parametrize("reason", ["a--b", "-a", "a-", "Manual", "MANUAL-x"])
def test_reason_shapes_refused(fresh_company, backup_dir, reason):
    with pytest.raises(ValueError):
        database.backup_database(fresh_company, reason=reason)


def test_reason_40_ok(fresh_company, backup_dir):
    database.backup_database(fresh_company, reason="x" * 40)


def test_two_backups_distinct_and_sidecar_text(fresh_company, backup_dir):
    a = database.backup_database(fresh_company, reason="manual")
    b = database.backup_database(fresh_company, reason="manual")
    assert a["path"] != b["path"]
    assert Path(a["path"] + ".sha256").read_text() == a["sha256"] + "\n"


def test_prune_bad_reason_and_missing_dir(tmp_path, backup_dir):
    with pytest.raises(ValueError):
        database.prune_backups(tmp_path / "company.db", reason="Bad Reason")
    assert not backup_dir.exists()
    assert database.prune_backups(tmp_path / "company.db", reason="addon-demo") == []


def test_prune_only_this_database(backup_dir):
    start = datetime(2026, 11, 17, 12)
    _fake_backups(backup_dir, "company", "addon-demo", [start - timedelta(days=d) for d in range(40)])
    other = _fake_backups(backup_dir, "master", "addon-demo", [start - timedelta(days=d) for d in range(40)])
    database.prune_backups(backup_dir / "company.db", reason="addon-demo")
    assert all((backup_dir / n).exists() for n in other)


def test_prune_stem_with_regex_chars(backup_dir):
    start = datetime(2026, 11, 17, 12)
    mine = _fake_backups(backup_dir, "a.b", "addon-demo", [start - timedelta(days=d) for d in range(40)])
    other = _fake_backups(backup_dir, "aXb", "addon-demo", [start - timedelta(days=d) for d in range(40)])
    database.prune_backups(backup_dir / "a.b.db", reason="addon-demo")
    assert all((backup_dir / n).exists() for n in other)


def test_prune_months_across_years(backup_dir):
    start = datetime(2026, 11, 17, 12)
    old = _fake_backups(backup_dir, "company", "addon-demo", [datetime(2024, 1, 5), datetime(2025, 1, 5)])
    _fake_backups(backup_dir, "company", "addon-demo", [start - timedelta(days=d) for d in range(40)])
    database.prune_backups(backup_dir / "company.db", reason="addon-demo")
    assert all((backup_dir / n).exists() for n in old)           # two different Januaries are two months


def test_restore_refuses_check_failure_db(backup_dir, tmp_path):
    bad = tmp_path / "bad.db"
    c = sqlite3.connect(bad)
    c.execute("CREATE TABLE t (x)"); c.execute("CREATE INDEX i ON t (x)")
    c.executemany("INSERT INTO t VALUES (?)", [(n,) for n in range(50)]); c.commit()
    c.execute("PRAGMA writable_schema = ON")
    c.execute("UPDATE sqlite_master SET sql = 'CREATE INDEX i ON t (x DESC)' WHERE name = 'i'"); c.commit()
    c.close(); c = sqlite3.connect(bad)
    assert c.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
    c.close()
    with pytest.raises(database.RestoreRefusedError, match="sound"):
        database.restore_database(bad, tmp_path / "t.db", expected_sha256=sha256(bad))


def test_restore_refuses_unsound_but_readable(fresh_company, backup_dir, tmp_path):
    result = database.backup_database(fresh_company, reason="manual")
    data = bytearray(Path(result["path"]).read_bytes())
    # zero a page that is neither the header nor the first schema page
    pages = len(data) // 4096
    for i in range(pages // 2, pages // 2 + 3):
        data[i * 4096:(i + 1) * 4096] = b"\xff" * 4096
    bad = tmp_path / "bad.db"
    bad.write_bytes(bytes(data))
    with pytest.raises(database.RestoreRefusedError):
        database.restore_database(bad, fresh_company, expected_sha256=sha256(bad))


def test_restore_leaves_no_aside_and_missing_target(fresh_company, backup_dir, tmp_path):
    result = _changed_copy(fresh_company, backup_dir)
    for suffix in ("-wal", "-shm"):
        Path(str(fresh_company) + suffix).write_bytes(b"stale" * 100)
    database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    assert not [n for n in os.listdir(fresh_company.parent) if "aside" in n]


def test_restore_into_missing_target(fresh_company, backup_dir, tmp_path):
    result = database.backup_database(fresh_company, reason="manual")
    target = tmp_path / "new" / "x.db"
    target.parent.mkdir()
    out = database.restore_database(result["path"], target, expected_sha256=result["sha256"])
    assert out == {"safety_backup": None} and target.exists()


def test_keyboard_interrupt_during_replace_puts_wal_back(fresh_company, backup_dir, monkeypatch):
    result = database.backup_database(fresh_company, reason="manual")
    _crashed_with_wal(fresh_company)
    real = os.replace

    def refuse(src, dst):
        if str(dst) == str(fresh_company):
            raise KeyboardInterrupt()
        return real(src, dst)
    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(KeyboardInterrupt):
        database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    monkeypatch.setattr(os, "replace", real)
    conn = database.get_readonly_connection(fresh_company)
    try:
        assert conn.execute("SELECT x FROM late_row").fetchall()[0][0] == 99
    finally:
        conn.close()


def test_wal_header_backup_creates_nothing_beside(fresh_company, backup_dir, tmp_path):
    # a backup file whose header still says WAL (as an older backup or a hand-copied file would)
    live = tmp_path / "walmode.db"
    c = sqlite3.connect(live)
    c.execute("PRAGMA journal_mode = WAL"); c.execute("CREATE TABLE t (x)"); c.execute("INSERT INTO t VALUES (1)")
    c.commit(); c.close()
    backup_dir.mkdir(exist_ok=True)
    bk = backup_dir / "walmode_20260101_000000_000000_manual.db"
    shutil.copy2(live, bk)
    target = tmp_path / "t.db"
    database.restore_database(bk, target, expected_sha256=sha256(bk))
    assert not [n for n in os.listdir(backup_dir) if n.endswith(("-wal", "-shm"))]


# ---- guards and runner ----------------------------------------------------------------------------------------

def test_handler_guard_refuses_sqlite_sequence_update(company):
    conn = database.get_connection(company)
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        with database.addon_write_guard(conn, KEY):
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute("UPDATE sqlite_sequence SET name = 'demo_x' WHERE name = 'audit_log'")
    finally:
        conn.close()


def test_guard_unit_direct():
    g = database._AddonGuard(KEY, schema=False)
    S = sqlite3
    assert g(S.SQLITE_INSERT, "journal_line", None, "main", "audit_demo_a_insert") == S.SQLITE_DENY
    assert g(S.SQLITE_INSERT, "audit_log", None, "main", "audit_account_insert") == S.SQLITE_DENY
    assert g(S.SQLITE_INSERT, "audit_log", None, "main", "audit_demo_a_insert") == S.SQLITE_OK
    assert g(S.SQLITE_INSERT, "audit_log", None, "main", "audit_demo_a_insert_x") == S.SQLITE_DENY
    s = database._AddonGuard(KEY, schema=True)
    assert s(S.SQLITE_CREATE_TRIGGER, "audit_demo_a_insert", "demo_a", "main", None) == S.SQLITE_DENY
    assert s(S.SQLITE_UPDATE, "sqlite_sequence", "seq", "main", None) == S.SQLITE_DENY
    assert s(S.SQLITE_UPDATE, "sqlite_temp_master", "sql", "main", None) == S.SQLITE_DENY


def run(company, tmp_path, files, audit=None):
    return database.apply_addon_migrations(company, KEY, migrations(tmp_path, files), audit=audit)


@pytest.mark.parametrize("which", ["insert", "update", "delete"])
def test_any_dropped_audit_trigger_is_rebuilt(company, tmp_path, which):
    run(company, tmp_path, {"demo_001.sql": f"CREATE TABLE demo_a (x);\nDROP TRIGGER audit_demo_a_{which};\n"
                                            "INSERT INTO demo_a (x) VALUES (1);\nUPDATE demo_a SET x = 2;\nDELETE FROM demo_a;\n"})
    assert [a for _, a, _, _ in audit_rows(company_rows(company), "demo_a")] == ["Insert", "Update", "Delete"]


def test_addons_own_trigger_survives_resync(company, tmp_path):
    run(company, tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\nCREATE TABLE demo_b (y);\n"
                                            "CREATE TRIGGER demo_a_t AFTER INSERT ON demo_a BEGIN INSERT INTO demo_b (y) VALUES (1); END;\n"
                                            "ALTER TABLE demo_a ADD COLUMN z;\n"})
    assert "demo_a_t" in triggers(company, "demo_a")


def test_counter_rename_to_existing_tables_refused(company, tmp_path):
    raw = sqlite3.connect(company)
    raw.execute("INSERT INTO audit_log (table_name, record_id, action) VALUES ('x', 1, 'Insert')")
    raw.execute("INSERT INTO sqlite_sequence (name, seq) SELECT 'journal_entry', 5 "
                "WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'journal_entry')")
    raw.commit(); raw.close()
    for script in ["UPDATE sqlite_sequence SET name = 'demo_a' WHERE name = 'journal_entry';"]:
        with pytest.raises(database.AddonMigrationError):
            run(company, tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n" + script + "\n"})

def test_audit_end_clears_context_and_rows_carry_user(company, tmp_path):
    run(company, tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, x);\n"
                                            "INSERT INTO demo_a (x) VALUES (1);\nUPDATE demo_a SET a_id = 9;\nDELETE FROM demo_a;\n"}, audit=stamp())
    conn = database.get_readonly_connection(company)
    try:
        ctx = dict(conn.execute("SELECT user_id, terminal_id, software_version_tag FROM audit_context WHERE id = 1").fetchone())
        rows = [dict(r) for r in conn.execute("SELECT * FROM audit_log WHERE table_name = 'demo_a' ORDER BY log_id")]
    finally:
        conn.close()
    assert ctx == {"user_id": None, "terminal_id": None, "software_version_tag": None}
    assert [r["action"] for r in rows] == ["Insert", "Update", "Delete"]
    assert all(r["user_id"] == 7 and r["terminal_id"] and r["software_version_tag"] for r in rows)
    assert rows[2]["new_value"] is None and rows[0]["old_value"] is None
    assert rows[1]["record_id"] == 9                                             # NEW.rowid after the key changed
    assert list(json.loads(rows[0]["new_value"])) == ["a_id", "x"]


def test_pre_ha9_table_gets_seed_row_logged(company, tmp_path):
    raw = sqlite3.connect(company)
    raw.execute("CREATE TABLE demo_old (x)")
    raw.commit(); raw.close()
    run(company, tmp_path, {"demo_001.sql": "INSERT INTO demo_old (x) VALUES (1);\n"})
    assert [a for _, a, _, _ in audit_rows(company_rows(company), "demo_old")] == ["Insert"]


@pytest.mark.parametrize("script, ok", [
    ("CREATE TABLE demo_a (x TEXT DEFAULT 'without rowid');", True),
    ("CREATE TABLE demo_a (k TEXT PRIMARY KEY) without rowid;", False),
    ('CREATE TABLE demo_a ("1a" TEXT);', False),
])
def test_name_and_rowid_edges(company, tmp_path, script, ok):
    if ok:
        run(company, tmp_path, {"demo_001.sql": script + "\n"})
    else:
        with pytest.raises(database.AddonMigrationError):
            run(company, tmp_path, {"demo_001.sql": script + "\n"})


def test_own_counter_seq_update_refused(company, tmp_path):
    with pytest.raises(database.AddonMigrationError):
        run(company, tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (id INTEGER PRIMARY KEY AUTOINCREMENT, x);\n"
                                                "INSERT INTO demo_a (x) VALUES (1);\nUPDATE sqlite_sequence SET seq = 100 WHERE name = 'demo_a';\n"})


def test_baseline_asv_update_audited(company):
    raw = sqlite3.connect(company)
    raw.execute("INSERT INTO addon_schema_version (addon_key, version, sha256) VALUES ('k', 1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')")
    raw.execute("UPDATE addon_schema_version SET sha256 = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'")
    raw.commit()
    rows = raw.execute("SELECT action FROM audit_log WHERE table_name = 'addon_schema_version' ORDER BY log_id").fetchall()
    raw.close()
    assert [r[0] for r in rows] == ["Insert", "Update"]


def test_remove_quietly_keeps_going(tmp_path):
    from modules.services import companies
    (tmp_path / "x.db-wal").write_bytes(b"1")
    (tmp_path / "x.db-shm").write_bytes(b"1")
    companies._remove_quietly(str(tmp_path / "x.db"))
    assert os.listdir(tmp_path) == []


def test_config_edges(tmp_path, monkeypatch):
    assert config.resolve_data_dir({"STRATALEDGER_DATA_DIR": "rel_dir"}, False, "/r") == os.path.abspath("rel_dir")
    home = tmp_path / "h"; home.mkdir()
    assert config.resolve_data_dir({"HOME": str(home)}, False, "/r") == str(home / "StrataLedger-dev")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(home))
    assert config.resolve_data_dir({}, False, "/r") == str(home / "StrataLedger-dev")
    blocker = tmp_path / "blocker"; blocker.write_text("x")
    assert config.resolve_data_dir({"LOCALAPPDATA": str(blocker)}, False, "/r") == os.path.join(str(blocker), "StrataLedger-dev")


def test_schema_change_unit(company):
    conn = database.get_readonly_connection(company)
    def run_check(after):
        database._check_schema_change(conn, KEY, {}, after)
    for after in [
        {("trigger", "audit_demo_b_insert"): ("demo_a", "CREATE TRIGGER x")},
        {("trigger", "audit_demo_a_insert_x"): ("demo_a", "CREATE TRIGGER x")},
        {("index", "audit_demo_a_insert"): ("demo_a", "CREATE INDEX x ON demo_a (x)")},
        {("trigger", "demo_t"): ("journal_line", "CREATE TRIGGER x")},
    ]:
        with pytest.raises(database.AddonMigrationError):
            run_check(after)
    run_check({("trigger", "audit_demo_a_insert"): ("demo_a", "CREATE TRIGGER x AFTER INSERT ON demo_a BEGIN INSERT INTO journal_line VALUES (1); END")})
    conn.close()


def test_scrollbar_orientation_and_command(tk_app):
    import customtkinter as ctk
    from config import Theme
    frame = ctk.CTkFrame(tk_app)
    try:
        cmd = lambda *a: None
        bar = Theme.create_scrollbar(frame, orientation="horizontal", command=cmd)
        assert bar.cget("orientation") == "horizontal"
        assert bar.cget("command") is cmd
    finally:
        frame.destroy()


def test_orphan_counter_row_does_not_block_a_migration(company, tmp_path):
    """B165: a counter row for no table, outside the add-on's prefix, is not the migration's doing."""
    raw = sqlite3.connect(company)
    raw.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('orphan', 3)")
    raw.commit(); raw.close()
    assert run(company, tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (x);\n"}) == [1]


from tests.authz_world import world  # noqa
from tests.test_addons import setup, resources, admin, draft, journal, write_addon  # noqa
from tests.test_ledger_posting import ctx_for, env, keyed  # noqa


def test_record_denial_keeps_permission(setup):
    from modules.services import authz
    before = len(setup.events("PARENT"))
    authz.record_denial(ctx_for(setup), "journal.post")
    written = setup.events("PARENT")[before:]
    assert [(e["event_type"], e["permission_code"]) for e in written] == [("Denied", "journal.post")]


def test_a_second_audit_log_counter_row_is_refused(company, tmp_path):
    """Mutation-tester finding (not a mutant): renaming an add-on counter row to audit_log leaves two audit_log
    rows in sqlite_sequence; the migration is refused."""
    with pytest.raises(database.AddonMigrationError, match="counter"):
        run(company, tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (id INTEGER PRIMARY KEY AUTOINCREMENT, x);\n"
                                                "INSERT INTO demo_a (id, x) VALUES (100000, 1);\n"
                                                "UPDATE sqlite_sequence SET name = 'audit_log' WHERE name = 'demo_a';\n"})
