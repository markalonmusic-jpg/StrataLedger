"""Connections, backups and restore (Phase 2.7 step B2: AX1, AX2, AX3).

* AX1: every connection from modules/database.py has foreign keys on and a 5-second busy timeout (the migration
  runner turns foreign keys off only for its own build, then on again). Master and company files are in WAL mode:
  set when they are built, checked when they are opened (an older file is switched and the switch is logged).
* AX2: one backup helper on sqlite3.Connection.backup. It copies committed pages, including those still in the
  WAL; it never copies -wal or -shm; it writes the backup's SHA-256 beside it (K5). The baseline runner, the add-on
  migration runner (E7 retention, secrets audit LOW-6) and the safety backup before a restore all use it. A restore
  checks the checksum, needs the company closed, and removes leftover -wal and -shm files.
* AX3: running from source without STRATALEDGER_DATA_DIR keeps data outside the repo.
"""
import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import config
import modules.database as database

ROOT = Path(__file__).resolve().parent.parent


def pragmas(conn):
    return (conn.execute("PRAGMA foreign_keys").fetchone()[0], conn.execute("PRAGMA busy_timeout").fetchone()[0])


def journal_mode(path):
    raw = sqlite3.connect(path)
    try:
        return raw.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        raw.close()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- AX1: connection settings ------------------------------------------------------------------------------------

def test_the_busy_timeout_is_five_seconds():
    assert database.BUSY_TIMEOUT_MS == 5000


def test_write_and_read_only_connections_have_foreign_keys_and_the_busy_timeout(fresh_company):
    for opener in (database.get_connection, database.get_readonly_connection):
        conn = opener(fresh_company)
        try:
            assert pragmas(conn) == (1, 5000), opener.__name__
        finally:
            conn.close()


def test_the_migration_runner_connection_has_the_busy_timeout(tmp_path, monkeypatch, backup_dir):
    seen = []
    real = database._verify_schema

    def spy(conn):
        seen.append(conn.execute("PRAGMA busy_timeout").fetchone()[0])
        return real(conn)
    monkeypatch.setattr(database, "_verify_schema", spy)
    database.ensure_company_database(tmp_path / "new.db")
    assert seen == [5000]
    conn = database.get_connection(tmp_path / "new.db")
    try:
        assert pragmas(conn) == (1, 5000)          # foreign keys are back on for every later connection
    finally:
        conn.close()


def test_the_addon_runner_connection_has_foreign_keys_and_the_busy_timeout(fresh_company, tmp_path, monkeypatch):
    seen = []
    real = database._verify_schema

    def spy(conn):
        seen.append(pragmas(conn))
        return real(conn)
    monkeypatch.setattr(database, "_verify_schema", spy)
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "demo_001.sql").write_text("CREATE TABLE demo_a (x);\n", encoding="utf-8")
    database.apply_addon_migrations(fresh_company, "demo", folder)
    assert seen == [(1, 5000)]


@pytest.mark.parametrize("build", ["company", "master"])
def test_new_files_are_built_in_wal_mode(tmp_path, backup_dir, build):
    path = tmp_path / f"{build}.db"
    (database.ensure_company_database if build == "company" else database.ensure_master_database)(path)
    assert journal_mode(path) == "wal"


@pytest.mark.parametrize("build", ["company", "master"])
def test_an_older_file_is_switched_to_wal_when_opened_and_the_switch_is_logged(tmp_path, backup_dir, caplog, build):
    path = tmp_path / f"{build}.db"
    ensure = database.ensure_company_database if build == "company" else database.ensure_master_database
    ensure(path)
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA journal_mode = DELETE")
    raw.close()
    before = sha256(path)
    with caplog.at_level(logging.INFO, logger="strataledger"):
        ensure(path)
    assert journal_mode(path) == "wal"
    assert "WAL" in caplog.text and path.name in caplog.text
    assert not backup_dir.exists() or os.listdir(backup_dir) == []               # no data change, so no backup
    assert before != sha256(path)                                               # only the header changed
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="strataledger"):
        ensure(path)
    assert "WAL" not in caplog.text                                             # logged once


def test_a_read_only_open_never_switches_the_mode(fresh_company):
    raw = sqlite3.connect(fresh_company)
    raw.execute("PRAGMA journal_mode = DELETE")
    raw.close()
    conn = database.get_readonly_connection(fresh_company)
    conn.execute("SELECT COUNT(*) FROM account").fetchone()
    conn.close()
    assert journal_mode(fresh_company) == "delete"


# --- AX2: the backup helper --------------------------------------------------------------------------------------

def test_a_backup_contains_a_write_that_is_still_in_the_wal(fresh_company, backup_dir):
    writer = sqlite3.connect(fresh_company)
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.execute("CREATE TABLE IF NOT EXISTS probe (x)")
    writer.execute("INSERT INTO probe VALUES (42)")
    writer.commit()
    try:
        assert os.path.getsize(str(fresh_company) + "-wal") > 0                  # not checkpointed yet
        result = database.backup_database(fresh_company, reason="manual")
    finally:
        writer.close()
    copy = sqlite3.connect(result["path"])
    try:
        assert copy.execute("SELECT x FROM probe").fetchall() == [(42,)]
    finally:
        copy.close()


def test_a_backup_never_copies_wal_or_shm_and_records_its_checksum(fresh_company, backup_dir):
    keep_open = database.get_connection(fresh_company)            # so -wal and -shm exist beside the source
    try:
        keep_open.execute("SELECT 1").fetchone()
        result = database.backup_database(fresh_company, reason="manual")
    finally:
        keep_open.close()
    path = Path(result["path"])
    assert path.parent == backup_dir and path.name.startswith("company_") and path.name.endswith("_manual.db")
    assert not [name for name in os.listdir(backup_dir) if name.endswith(("-wal", "-shm"))]
    assert result["sha256"] == sha256(path)                         # K5: the checksum is of the backup file
    assert Path(str(path) + ".sha256").read_text(encoding="utf-8").strip() == result["sha256"]


@pytest.mark.parametrize("reason", ["", "Bad Reason", "a/b", "x" * 41, None])
def test_a_backup_reason_is_a_short_slug(fresh_company, backup_dir, reason):
    with pytest.raises(ValueError):
        database.backup_database(fresh_company, reason=reason)


def test_the_baseline_runner_backs_up_through_the_helper(tmp_path, backup_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(database, "backup_database", lambda path, *, reason: calls.append((Path(path), reason)))
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    raw.close()
    database.ensure_company_database(path)                       # version 0 with schema_version: built in place
    assert calls == [(path, "pre-upgrade")]


def test_the_addon_runner_backs_up_through_the_helper_and_prunes(fresh_company, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(database, "backup_database", lambda path, *, reason: calls.append(("backup", reason)))
    monkeypatch.setattr(database, "prune_backups", lambda path, *, reason: calls.append(("prune", reason)))
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "demo_001.sql").write_text("CREATE TABLE demo_a (x);\n", encoding="utf-8")
    database.apply_addon_migrations(fresh_company, "demo", folder)
    assert calls == [("backup", "addon-demo"), ("prune", "addon-demo")]


def _fake_backups(backup_dir, stem, reason, moments):
    backup_dir.mkdir(exist_ok=True)
    names = []
    for moment in moments:
        name = f"{stem}_{moment.strftime('%Y%m%d_%H%M%S_%f')}_{reason}.db"
        (backup_dir / name).write_bytes(b"x")
        (backup_dir / (name + ".sha256")).write_text("0" * 64, encoding="utf-8")
        names.append(name)
    return names


def test_retention_keeps_seven_daily_four_weekly_and_twelve_monthly(backup_dir):
    """E7: the newest backup of each of the 7 newest days, the 4 newest ISO weeks and the 12 newest months."""
    start = datetime(2026, 11, 17, 12, 0, 0)
    moments = [start - timedelta(days=d, hours=h) for d in range(0, 500, 1) for h in (0, 3)]
    names = _fake_backups(backup_dir, "company", "addon-demo", moments)
    other = _fake_backups(backup_dir, "company", "pre-restore", [start - timedelta(days=400)])
    unrelated = backup_dir / "notes.txt"
    unrelated.write_text("keep", encoding="utf-8")
    database.prune_backups(backup_dir / ".." / "company.db", reason="addon-demo")
    kept = sorted(n for n in os.listdir(backup_dir) if n.endswith("_addon-demo.db"))
    by_moment = dict(zip(names, moments))
    expected = set()
    for key, count in ((lambda m: m.date(), 7), (lambda m: m.isocalendar()[:2], 4), (lambda m: (m.year, m.month), 12)):
        newest = {}
        for name, moment in sorted(by_moment.items(), key=lambda item: item[1]):
            newest[key(moment)] = name
        expected |= {newest[k] for k in sorted(newest)[-count:]}
    assert set(kept) == expected
    assert all((backup_dir / (n + ".sha256")).exists() for n in kept)
    assert not [n for n in os.listdir(backup_dir) if n.endswith(".sha256") and n[:-7] not in os.listdir(backup_dir)]
    assert (backup_dir / other[0]).exists() and unrelated.exists()       # another reason, and other files, stay


# --- AX2: restore ------------------------------------------------------------------------------------------------

def _changed_copy(fresh_company, backup_dir):
    result = database.backup_database(fresh_company, reason="manual")
    conn = database.get_connection(fresh_company)
    try:
        conn.execute("CREATE TABLE after_backup (x)")
        conn.commit()
    finally:
        conn.close()
    return result


def test_a_restore_puts_the_backup_back_after_a_safety_backup(fresh_company, backup_dir):
    result = _changed_copy(fresh_company, backup_dir)
    out = database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    safety = Path(out["safety_backup"])
    assert safety.name.endswith("_pre-restore.db")
    check = sqlite3.connect(safety)
    try:
        assert check.execute("SELECT name FROM sqlite_master WHERE name = 'after_backup'").fetchall()   # the old state
    finally:
        check.close()
    conn = database.get_readonly_connection(fresh_company)
    try:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'after_backup'").fetchall() == []
    finally:
        conn.close()
    database.ensure_company_database(fresh_company)                    # the baseline guard accepts it


def test_a_restore_removes_leftover_wal_and_shm(fresh_company, backup_dir):
    result = _changed_copy(fresh_company, backup_dir)
    for suffix in ("-wal", "-shm"):
        Path(str(fresh_company) + suffix).write_bytes(b"stale" * 100)
    database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    for suffix in ("-wal", "-shm"):
        assert not Path(str(fresh_company) + suffix).exists()
    conn = database.get_readonly_connection(fresh_company)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_a_restore_refuses_a_wrong_checksum_and_changes_nothing(fresh_company, backup_dir):
    result = _changed_copy(fresh_company, backup_dir)
    before = sha256(fresh_company)
    with pytest.raises(database.RestoreRefusedError, match="checksum"):
        database.restore_database(result["path"], fresh_company, expected_sha256="0" * 64)
    assert sha256(fresh_company) == before
    assert not [n for n in os.listdir(backup_dir) if "pre-restore" in n]


def test_a_restore_refuses_a_file_that_is_not_a_database(fresh_company, backup_dir, tmp_path):
    bogus = tmp_path / "bogus.db"
    bogus.write_bytes(b"not a database" * 100)
    with pytest.raises(database.RestoreRefusedError):
        database.restore_database(bogus, fresh_company, expected_sha256=sha256(bogus))


@pytest.mark.skipif(os.name != "nt", reason="Windows refuses to replace a file another connection holds open")
def test_a_restore_refuses_while_the_company_is_open(fresh_company, backup_dir):
    result = _changed_copy(fresh_company, backup_dir)
    holder = database.get_connection(fresh_company)
    try:
        holder.execute("SELECT 1 FROM account").fetchone()
        with pytest.raises(database.RestoreRefusedError, match="still open"):
            database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    finally:
        holder.close()
    assert not [n for n in os.listdir(backup_dir) if "pre-restore" in n]          # refused before the safety copy
    assert not Path(str(fresh_company) + ".restoring").exists()
    conn = database.get_readonly_connection(fresh_company)
    try:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'after_backup'").fetchall()   # unchanged
    finally:
        conn.close()


# --- AX3: the data folder when running from source -------------------------------------------------------------

def test_a_source_run_keeps_data_outside_the_repo(tmp_path):
    local = tmp_path / "Local"
    result = config.resolve_data_dir({"LOCALAPPDATA": str(local)}, frozen=False, resource_dir=str(ROOT))
    assert result == str(local / "StrataLedger-dev")
    assert Path(result).is_dir()
    assert os.path.commonpath([result, str(ROOT)]) != str(ROOT)


def test_a_source_run_without_localappdata_uses_the_home_folder(tmp_path):
    result = config.resolve_data_dir({"USERPROFILE": str(tmp_path)}, frozen=False, resource_dir=str(ROOT))
    assert result == str(tmp_path / "StrataLedger-dev")


def test_the_live_source_run_data_folder_is_outside_the_repo():
    if os.environ.get(config.DATA_DIR_ENV):
        pytest.skip("STRATALEDGER_DATA_DIR is set for this run")
    assert os.path.commonpath([config.DATA_DIR, str(ROOT)]) != str(ROOT)


# --- step-reviewer findings on 8e5979c -------------------------------------------------------------------------

def test_a_backup_is_a_rollback_journal_file_so_its_checksum_covers_everything(fresh_company, backup_dir):
    """Finding 1: a WAL-mode backup would let a -wal planted beside it change what a restore puts back."""
    result = database.backup_database(fresh_company, reason="manual")
    assert journal_mode(result["path"]) == "delete"
    assert sha256(result["path"]) == result["sha256"]


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_a_restore_refuses_a_backup_with_a_file_beside_it(fresh_company, backup_dir, suffix):
    result = _changed_copy(fresh_company, backup_dir)
    Path(result["path"] + suffix).write_bytes(b"planted" * 100)
    before = sha256(fresh_company)
    with pytest.raises(database.RestoreRefusedError, match="beside"):
        database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    assert sha256(fresh_company) == before


def test_checking_a_backup_leaves_nothing_beside_it(fresh_company, backup_dir):
    result = _changed_copy(fresh_company, backup_dir)
    database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    assert not [n for n in os.listdir(backup_dir) if n.endswith(("-wal", "-shm", "-journal"))]


def _crashed_with_wal(fresh_company):
    """The live file plus a -wal holding a committed row, as after a crash (no connection open)."""
    import shutil
    writer = sqlite3.connect(fresh_company)
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.execute("CREATE TABLE late_row (x)")
    writer.execute("INSERT INTO late_row VALUES (99)")
    writer.commit()
    copies = {suffix: Path(str(fresh_company) + suffix).read_bytes() for suffix in ("", "-wal")}
    writer.close()
    for suffix, data in copies.items():
        Path(str(fresh_company) + suffix).write_bytes(data)
    shm = Path(str(fresh_company) + "-shm")
    if shm.exists():
        shm.unlink()
    assert Path(str(fresh_company) + "-wal").stat().st_size > 0
    shutil.rmtree(Path(fresh_company).parent / "unused", ignore_errors=True)


def test_a_failed_replace_keeps_the_live_wal(fresh_company, backup_dir, monkeypatch):
    """Finding 3: the live file's -wal is put back when the restore cannot replace the file."""
    result = database.backup_database(fresh_company, reason="manual")
    _crashed_with_wal(fresh_company)
    real_replace = os.replace

    def refuse(src, dst):
        if str(dst) == str(fresh_company):
            raise PermissionError("locked")
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(database.RestoreRefusedError, match="still open"):
        database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    monkeypatch.setattr(os, "replace", real_replace)
    conn = database.get_readonly_connection(fresh_company)
    try:
        assert conn.execute("SELECT x FROM late_row").fetchall()[0][0] == 99
    finally:
        conn.close()
    assert not [n for n in os.listdir(Path(fresh_company).parent) if "aside" in n or n.endswith(".restoring")]


def test_a_rename_back_that_fails_is_refused_with_the_path(fresh_company, backup_dir, monkeypatch):
    """Finding 4: the company file is never left under the check name without saying so."""
    result = _changed_copy(fresh_company, backup_dir)
    real_rename, calls = os.rename, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("busy")
        return real_rename(src, dst)
    monkeypatch.setattr(os, "rename", flaky)
    with pytest.raises(database.RestoreRefusedError) as refused:
        database.restore_database(result["path"], fresh_company, expected_sha256=result["sha256"])
    assert ".closed-check" in str(refused.value)


def test_the_helper_connections_have_the_busy_timeout(fresh_company, backup_dir, monkeypatch):
    """Finding 9: the backup target and the WAL check use the configured connection too."""
    seen = []
    real = database._configure

    def spy(conn):
        seen.append(True)
        return real(conn)
    monkeypatch.setattr(database, "_configure", spy)
    database.backup_database(fresh_company, reason="manual")
    count = len(seen)
    assert count >= 2                                  # the source and the target
    database._ensure_wal(os.fspath(fresh_company))
    assert len(seen) == count + 1
