"""scripts/create_fresh_databases.py: dry run by default, moves never deletes, refuses when unsafe."""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

import modules.database as database

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "create_fresh_databases.py"


@pytest.fixture
def script(monkeypatch):
    spec = importlib.util.spec_from_file_location("create_fresh_databases", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "app_is_running", lambda: [])  # tests never depend on real processes
    return module


@pytest.fixture
def layout(tmp_path, backup_dir):
    root = tmp_path / "project"
    (root / "Companies").mkdir(parents=True)
    master = root / "system_master.db"
    company = root / "Companies" / "CHRM.db"
    for path in (master, company):
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE marker (note TEXT)")
        conn.execute("INSERT INTO marker VALUES (?)", (path.name,))
        conn.commit()
        conn.close()
    return {"root": root, "master": master, "company": company, "backups": tmp_path / "Backups"}


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in Path(root).rglob("*") if p.is_file()}


def run(script, layout, *extra):
    return script.main(["--master-path", str(layout["master"]), "--backup-dir", str(layout["backups"]), *extra])


def test_dry_run_changes_nothing(script, layout, capsys):
    before = snapshot(layout["root"])
    assert run(script, layout) == 0
    assert snapshot(layout["root"]) == before
    assert not layout["backups"].exists()
    out = capsys.readouterr().out
    assert "DRY RUN" in out and str(layout["master"]) in out and str(layout["company"]) in out
    assert f"schema_version {database.MASTER_MIGRATIONS[-1][0]}" in out


def test_apply_creates_master_at_latest_version_with_no_users(script, layout):
    original = layout["master"].read_bytes()
    company_before = layout["company"].read_bytes()
    assert run(script, layout, "--apply") == 0
    conn = sqlite3.connect(f"{layout['master'].resolve().as_uri()}?mode=ro", uri=True)
    try:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == database.MASTER_MIGRATIONS[-1][0]
        assert conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM company_registry").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()
    moved = list(layout["backups"].glob("*/system_master.db"))
    assert len(moved) == 1 and moved[0].read_bytes() == original  # moved, byte for byte, never deleted
    assert layout["company"].read_bytes() == company_before  # untouched


def test_second_apply_is_safe(script, layout):
    assert run(script, layout, "--apply") == 0
    first_fresh = layout["master"].read_bytes()
    assert run(script, layout, "--apply") == 0
    folders = sorted(layout["backups"].iterdir())
    assert len(folders) == 2 and len({f.name for f in folders}) == 2
    assert sorted(p.read_bytes() == first_fresh for p in layout["backups"].glob("*/system_master.db")) == [False, True]
    assert layout["master"].exists()


def test_fresh_file_without_existing_target(script, tmp_path, backup_dir):
    master = tmp_path / "new" / "system_master.db"
    assert script.main(["--master-path", str(master), "--backup-dir", str(tmp_path / "Backups"), "--apply"]) == 0
    assert master.exists() and not (tmp_path / "Backups").exists()


def test_locked_target_is_refused(script, layout):
    before = snapshot(layout["root"])
    holder = sqlite3.connect(layout["master"], isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    try:
        assert run(script, layout, "--apply") == script.EXIT_REFUSED
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert snapshot(layout["root"]) == before and not layout["backups"].exists()


def test_running_app_is_refused_even_in_dry_run(script, layout, monkeypatch, capsys):
    before = layout["master"].read_bytes()
    monkeypatch.setattr(script, "app_is_running", lambda: ["pythonw.exe app_strata.pyw"])
    assert run(script, layout) == script.EXIT_REFUSED
    assert run(script, layout, "--apply") == script.EXIT_REFUSED
    assert "REFUSED" in capsys.readouterr().out and layout["master"].read_bytes() == before


def test_script_never_hashes_or_inserts_users_itself(script):
    source = SCRIPT.read_text(encoding="utf-8")
    assert "scrypt" not in source and "INSERT INTO app_user" not in source and "hashlib" not in source
    assert "getpass" in source and "auth.create_first_master" in source


def answers(monkeypatch, script, *, yes="y", username="owner", first="Ann", last="Owner", email="ann@x.test",
            passwords=("correct horse battery", "correct horse battery")):
    replies = iter([yes, username, first, last, email])
    monkeypatch.setattr(script, "_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
    secrets = iter(passwords)
    monkeypatch.setattr(script.getpass, "getpass", lambda prompt="": next(secrets))


def test_apply_can_create_the_first_master_and_shows_the_recovery_code_once(script, layout, monkeypatch, capsys,
                                                                              caplog):
    answers(monkeypatch, script)
    assert run(script, layout, "--apply") == 0
    out = capsys.readouterr().out
    assert "correct horse battery" not in out and "correct horse battery" not in caplog.text
    assert "store this safely" in out.lower()
    code_lines = [line for line in out.splitlines() if line.strip().startswith("RECOVERY CODE:")]
    assert len(code_lines) == 1
    code = code_lines[0].split(":", 1)[1].strip()
    assert code not in caplog.text
    from modules.services import auth
    assert auth.login(layout["master"], "owner", "correct horse battery").is_master
    auth.recover_master(layout["master"], code, "another long passphrase")


def test_mismatched_passwords_create_nothing(script, layout, monkeypatch, capsys):
    answers(monkeypatch, script, passwords=("correct horse battery", "different horse battery"))
    assert run(script, layout, "--apply") == script.EXIT_FAILED
    conn = sqlite3.connect(layout["master"])
    assert conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
    conn.close()
    assert "do not match" in capsys.readouterr().out


def test_declining_creates_no_master(script, layout, monkeypatch):
    answers(monkeypatch, script, yes="n")
    assert run(script, layout, "--apply") == 0
    conn = sqlite3.connect(layout["master"])
    assert conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
    conn.close()


def test_non_interactive_apply_skips_the_prompt(script, layout, monkeypatch, capsys):
    monkeypatch.setattr(script, "_interactive", lambda: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("prompted without a terminal"))
    assert run(script, layout, "--apply") == 0
    assert "first Master" in capsys.readouterr().out
