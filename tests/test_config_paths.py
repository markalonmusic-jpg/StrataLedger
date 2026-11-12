"""Where the app finds its code and its data (decision P2a).

RESOURCE_DIR is the folder the app runs from (sys._MEIPASS when frozen, else the folder of
config.py). DATA_DIR holds the databases, backups, logs and uploads: STRATALEDGER_DATA_DIR if
set, else the repo folder when running from source, else %PROGRAMDATA%\\StrataLedger when frozen.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import config
import modules.database as database
from tests.test_static_rules import ROOT, SKIP_DIRS

# --- Pure resolution (no import-time side effects) ----------------------------------------------


def test_env_var_wins_when_running_from_source(tmp_path):
    data = tmp_path / "mydata"
    assert config.resolve_data_dir({"STRATALEDGER_DATA_DIR": str(data)}, frozen=False,
                                   resource_dir="/res") == str(data)


def test_source_run_uses_the_repo_folder(tmp_path):
    assert config.resolve_data_dir({}, frozen=False, resource_dir=str(tmp_path)) == str(tmp_path)


def test_empty_env_var_is_ignored(tmp_path):
    assert config.resolve_data_dir({"STRATALEDGER_DATA_DIR": "  "}, frozen=False,
                                   resource_dir=str(tmp_path)) == str(tmp_path)


def test_frozen_uses_programdata_and_creates_it(tmp_path):
    programdata = tmp_path / "ProgramData"
    programdata.mkdir()
    result = config.resolve_data_dir({"PROGRAMDATA": str(programdata)}, frozen=True,
                                     resource_dir=str(tmp_path / "bundle"))
    assert result == str(programdata / "StrataLedger")
    assert (programdata / "StrataLedger").is_dir()


def test_frozen_env_var_still_wins(tmp_path):
    data = tmp_path / "mydata"
    env = {"STRATALEDGER_DATA_DIR": str(data), "PROGRAMDATA": str(tmp_path / "pd")}
    assert config.resolve_data_dir(env, frozen=True, resource_dir="/res") == str(data)
    assert not (tmp_path / "pd").exists()          # nothing created for an unused default


def test_frozen_without_programdata_falls_back_to_the_user_profile(tmp_path):
    result = config.resolve_data_dir({"USERPROFILE": str(tmp_path)}, frozen=True, resource_dir="/res")
    assert result == str(tmp_path / "StrataLedger")
    assert (tmp_path / "StrataLedger").is_dir()


def test_frozen_data_dir_is_never_the_bundle(tmp_path):
    bundle = tmp_path / "bundle"
    result = config.resolve_data_dir({"PROGRAMDATA": str(tmp_path / "pd")}, frozen=True, resource_dir=str(bundle))
    assert not result.startswith(str(bundle))


def test_resource_dir_cases(tmp_path):
    assert config.resolve_resource_dir(frozen=True, meipass=str(tmp_path / "mei"), executable="x") == str(tmp_path / "mei")
    exe = tmp_path / "app" / "StrataLedger.exe"
    assert config.resolve_resource_dir(frozen=True, meipass=None, executable=str(exe)) == str(exe.parent)
    from_source = config.resolve_resource_dir(frozen=False, meipass=None, executable="x")
    assert os.path.normcase(from_source) == os.path.normcase(str(Path(config.__file__).resolve().parent))


def test_build_paths_derives_everything(tmp_path):
    data, res = str(tmp_path / "data"), str(tmp_path / "res")
    paths = config.build_paths(data, res)
    assert paths["MASTER_DB_PATH"] == os.path.join(data, "system_master.db")
    for name, folder in (("COMPANIES_DIR", "Companies"), ("UPLOAD_DIR", "Uploaded_Files"),
                         ("BACKUP_DIR", "Backups"), ("LOG_DIR", "Logs")):
        assert paths[name] == os.path.join(data, folder)
    assert paths["LOG_FILE"] == os.path.join(data, "Logs", "strataledger.log")
    for name, folder in (("MIGRATIONS_DIR", "migrations"), ("FONT_DIR", "fonts"),
                         ("TEMPLATES_DIR", "templates"), ("HELP_DIR", "help")):
        assert paths[name] == os.path.join(res, folder)


# --- The real module, imported fresh in a child process -----------------------------------------

def _run(code, env_extra, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("STRATALEDGER_DATA_DIR", "PROGRAMDATA", "USERPROFILE")}
    env.update(env_extra)
    program = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n{code}"
    done = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, env=env,
                          cwd=str(tmp_path), timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()


def test_import_with_env_var(tmp_path):
    out = _run("import config\nprint(config.DATA_DIR)\nprint(config.BASE_PROJECT_DIR)\nprint(config.MASTER_DB_PATH)\n"
               "print(config.RESOURCE_DIR)\nprint(config.FONT_DIR)",
               {"STRATALEDGER_DATA_DIR": str(tmp_path / "d")}, tmp_path)
    assert out[0] == out[1] == str(tmp_path / "d")
    assert out[2] == str(tmp_path / "d" / "system_master.db")
    assert out[3] == str(ROOT)
    assert out[4] == str(ROOT / "fonts")


def test_import_from_source_defaults_to_the_repo(tmp_path):
    out = _run("import config\nprint(config.DATA_DIR)", {}, tmp_path)
    assert out == [str(ROOT)]


def test_import_frozen(tmp_path):
    bundle, programdata = tmp_path / "mei", tmp_path / "pd"
    programdata.mkdir()
    out = _run("sys.frozen = True\nsys._MEIPASS = %r\nimport config\nprint(config.DATA_DIR)\nprint(config.RESOURCE_DIR)\n"
               "print(config.MIGRATIONS_DIR)" % str(bundle),
               {"PROGRAMDATA": str(programdata)}, tmp_path)
    assert out == [str(programdata / "StrataLedger"), str(bundle), str(bundle / "migrations")]
    assert (programdata / "StrataLedger").is_dir()


# --- Existing behaviour keeps working ------------------------------------------------------------

def test_alias_and_exported_names_exist():
    assert config.BASE_PROJECT_DIR == config.DATA_DIR
    for name in ("MASTER_DB_PATH", "COMPANIES_DIR", "UPLOAD_DIR", "BACKUP_DIR", "LOG_DIR", "LOG_FILE",
                 "RESOURCE_DIR", "MIGRATIONS_DIR", "FONT_DIR", "TEMPLATES_DIR", "HELP_DIR", "APP_VERSION"):
        assert hasattr(config, name), name


def test_migrations_come_from_the_resource_folder():
    assert database.MIGRATIONS_DIR == config.MIGRATIONS_DIR
    assert os.path.isfile(os.path.join(database.MIGRATIONS_DIR, "001_company.sql"))


def test_services_still_honour_a_patched_base_dir(tmp_path, monkeypatch):
    from modules.services import paths
    monkeypatch.setattr(config, "BASE_PROJECT_DIR", str(tmp_path))
    inside = tmp_path / "Companies" / "X.db"
    assert os.path.normcase(paths.resolve_company_path("Companies/X.db")) == os.path.normcase(str(inside.resolve()))


# --- No hardcoded machine path anywhere -------------------------------------------------------------

CODE_SUFFIXES = {".py", ".pyw", ".bat", ".cmd", ".vbs", ".ps1", ".sql", ".json", ".cfg", ".ini", ".toml"}
# Built from pieces so this file does not contain the pattern it forbids.
MACHINE_PATH = re.compile(r"[A-Za-z]:[\\/]+" + "Users" + r"[\\/]", re.IGNORECASE)


def test_no_hardcoded_user_paths_in_code():
    offenders = {}
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.suffix.lower() not in CODE_SUFFIXES or SKIP_DIRS.intersection(rel.parts):
            continue
        hits = [n for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
                if MACHINE_PATH.search(line)]
        if hits:
            offenders[rel.as_posix()] = hits
    assert not offenders, f"hardcoded machine path in code: {offenders}"


def test_machine_path_checker_flags_a_sample():
    assert MACHINE_PATH.search("x = r'C:" + "\\Users" + "\\someone\\app'")
    assert MACHINE_PATH.search("c:/" + "users" + "/someone")
    assert not MACHINE_PATH.search("os.path.join(DATA_DIR, 'Users')")
