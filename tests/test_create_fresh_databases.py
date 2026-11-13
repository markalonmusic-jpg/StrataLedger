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
    assert "machine_wrap=platform_support.DPAPI" in source      # Step 1c: the script's Master gets a DPAPI copy
    assert "KEY_LOCKED_NOTICE" in source


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


def test_no_prompt_skips_the_question_even_with_a_terminal(script, layout, monkeypatch, capsys):
    """R31: --no-prompt rebuilds and exits cleanly without asking for the first Master."""
    monkeypatch.setattr(script, "_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("prompted with --no-prompt"))
    assert run(script, layout, "--apply", "--no-prompt") == 0
    assert "--no-prompt: the first Master was not created" in capsys.readouterr().out
    conn = sqlite3.connect(layout["master"])
    assert conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize("ends_at", ["question", "details", "password"])
def test_no_answer_read_exits_cleanly(script, layout, monkeypatch, capsys, ends_at):
    """R31: a terminal that reports a tty but has no input (Git Bash) ends with a sentence, not an EOFError."""
    replies = iter({"question": [], "details": ["y", "owner"], "password": ["y", "owner", "A", "O", "a@x.test"]}[ends_at])

    def reply(prompt=""):
        try:
            return next(replies)
        except StopIteration:
            raise EOFError from None
    monkeypatch.setattr(script, "_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", reply)
    monkeypatch.setattr(script.getpass, "getpass", reply)
    assert run(script, layout, "--apply") == 0
    assert "No answer was read; no Master was created." in capsys.readouterr().out
    conn = sqlite3.connect(layout["master"])
    assert conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
    conn.close()


# --- --sample-company CODE ------------------------------------------------------------------------------

@pytest.fixture
def sample_layout(tmp_path, backup_dir, monkeypatch):
    """A real fresh master with one Master user, and the data folder pointed at tmp_path. Its installation key has a
    machine copy made by a fake DPAPI, which the script's platform_support.DPAPI is pointed at."""
    import config
    from modules import platform_support
    from modules.services import auth, keys
    from tests.test_key_store import FakeMachineWrap
    monkeypatch.setattr(config, "BASE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(platform_support, "DPAPI", FakeMachineWrap())
    monkeypatch.setattr(keys, "_provider", keys.get_provider())       # the script sets the provider; undo it after
    master = tmp_path / "system_master.db"
    database.ensure_master_database(master)
    auth.create_first_master(str(master), "root", "correct horse battery", "Root", "User", "r@x.test",
                             machine_wrap=platform_support.DPAPI)
    return {"master": master, "root": tmp_path, "backups": tmp_path / "Backups"}


def test_sample_company_uses_the_real_key_store_outside_the_suite(script, sample_layout, monkeypatch):
    """Step 1c review: the script sets the LocalKeyProvider itself, so it works without the suite's test switch."""
    from modules.services import key_store, keys
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    assert run_sample(script, sample_layout, "--sample-company", "TESTCO", "--apply") == 0
    assert registry_codes(sample_layout["master"]) == ["TESTCO"]
    conn = sqlite3.connect(sample_layout["master"])
    try:
        assert conn.execute("SELECT COUNT(*) FROM company_key").fetchone()[0] == 1
    finally:
        conn.close()


def test_sample_company_says_so_when_the_key_is_locked(script, sample_layout, monkeypatch, capsys):
    from modules import platform_support
    from modules.services import key_store
    from tests.test_key_store import FakeMachineWrap
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    monkeypatch.setattr(platform_support, "DPAPI", FakeMachineWrap(fail_unprotect=True))
    assert run_sample(script, sample_layout, "--sample-company", "TESTCO", "--apply") == script.EXIT_FAILED
    assert registry_codes(sample_layout["master"]) == []
    assert script.KEY_LOCKED in capsys.readouterr().out


def run_sample(script, layout, *extra):
    return script.main(["--master-path", str(layout["master"]), "--backup-dir", str(layout["backups"]), *extra])


def registry_codes(master):
    conn = sqlite3.connect(master)
    try:
        return [r[0] for r in conn.execute("SELECT company_code FROM company_registry")]
    finally:
        conn.close()


def test_sample_company_dry_run_writes_nothing(script, sample_layout, capsys):
    before = snapshot(sample_layout["root"])
    assert run_sample(script, sample_layout, "--sample-company", "TESTCO") == 0
    assert snapshot(sample_layout["root"]) == before
    out = capsys.readouterr().out
    assert "TESTCO" in out and "root" in out and "Dry run" in out


def test_sample_company_is_built_from_the_construction_template(script, sample_layout, capsys, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("the sample step must not ask questions"))
    monkeypatch.setattr("getpass.getpass", lambda *a: pytest.fail("the sample step must not ask for a password"))
    master_before = sample_layout["master"].read_bytes()
    assert run_sample(script, sample_layout, "--sample-company", "TESTCO", "--apply") == 0
    assert registry_codes(sample_layout["master"]) == ["TESTCO"]
    company = sample_layout["root"] / "Companies" / "TESTCO.db"
    conn = sqlite3.connect(company)
    try:
        assert conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 88
        assert conn.execute("SELECT COUNT(*) FROM fiscal_year").fetchone()[0] == 2
        assert conn.execute("SELECT ar_acct_id IS NOT NULL FROM company_settings").fetchone()[0] == 1
    finally:
        conn.close()
    assert not sample_layout["backups"].exists()                       # the Master file was not rebuilt or moved
    assert sample_layout["master"].read_bytes() != master_before         # only the registry row was added
    assert "TESTCO" in capsys.readouterr().out


def test_sample_company_uses_the_existing_master_and_opens(script, sample_layout):
    from modules.services import auth, companies
    run_sample(script, sample_layout, "--sample-company", "TESTCO", "--apply")
    # The Master's password is unchanged and the company opens for them.
    session = auth.login(str(sample_layout["master"]), "root", "correct horse battery")
    company_id = companies.list_companies(session)[0]["company_id"]
    assert companies.open_company(session, company_id).company_id == company_id


@pytest.mark.parametrize("code", ["ab", "AB CD", "CON", "TOOLONGCODE1", ""])
def test_sample_company_refuses_a_bad_code(script, sample_layout, code, capsys):
    assert run_sample(script, sample_layout, "--sample-company", code, "--apply") == script.EXIT_FAILED
    assert registry_codes(sample_layout["master"]) == []
    assert "code" in capsys.readouterr().out.lower()


def test_sample_company_refuses_a_code_already_used(script, sample_layout, capsys):
    run_sample(script, sample_layout, "--sample-company", "TESTCO", "--apply")
    assert run_sample(script, sample_layout, "--sample-company", "TESTCO", "--apply") == script.EXIT_FAILED
    assert registry_codes(sample_layout["master"]) == ["TESTCO"]
    assert "already" in capsys.readouterr().out.lower()


def test_sample_company_needs_an_existing_master_user(script, tmp_path, backup_dir, monkeypatch, capsys):
    import config
    monkeypatch.setattr(config, "BASE_PROJECT_DIR", str(tmp_path))
    master = tmp_path / "system_master.db"
    database.ensure_master_database(master)                              # fresh, no users
    layout = {"master": master, "backups": tmp_path / "Backups"}
    assert run_sample(script, layout, "--sample-company", "TESTCO", "--apply") == script.EXIT_FAILED
    assert "Master" in capsys.readouterr().out
    missing = {"master": tmp_path / "nope.db", "backups": tmp_path / "Backups"}
    assert run_sample(script, missing, "--sample-company", "TESTCO", "--apply") == script.EXIT_FAILED
    assert not (tmp_path / "nope.db").exists()


def test_sample_company_refuses_while_the_app_is_running(script, sample_layout, monkeypatch, capsys):
    monkeypatch.setattr(script, "app_is_running", lambda: ["pythonw app_strata.pyw"])
    assert run_sample(script, sample_layout, "--sample-company", "TESTCO", "--apply") == script.EXIT_REFUSED
    assert registry_codes(sample_layout["master"]) == []
