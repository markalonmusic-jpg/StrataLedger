"""auth.inspect_master / master_setup_state: is this the first run? (decision S10)."""
import sqlite3

import pytest

import modules.database as database
from modules.services import auth


@pytest.fixture
def master(tmp_path, backup_dir):
    return tmp_path / "system_master.db"


def build(path):
    database.ensure_master_database(path)


def add_master(path):
    auth.create_first_master(str(path), "root", "correct horse battery", "Root", "User", "r@x.test")


def test_absent_file_is_missing(master):
    assert auth.master_setup_state(master) == "missing"
    assert auth.inspect_master(master) == ("missing", None)
    assert not master.exists()                       # looking never creates the file


def test_empty_file_is_missing(master):
    master.write_bytes(b"")
    assert auth.master_setup_state(master) == "missing"


def test_built_master_without_users(master):
    build(master)
    assert auth.inspect_master(master) == ("no_users", None)


def test_master_with_a_user_is_ready(master):
    build(master)
    add_master(master)
    assert auth.inspect_master(master) == ("ready", None)


@pytest.mark.parametrize("how,error_type", [
    ("garbage", "DatabaseError"),
    ("other_tables", "SchemaUpgradeBlockedError"),
    ("other_baseline", "SchemaUpgradeBlockedError"),
    ("too_new", "SchemaUpgradeBlockedError"),
])
def test_old_or_damaged_files_are_unreadable(master, how, error_type):
    if how == "garbage":
        master.write_bytes(b"this is not a database file at all " * 50)
    elif how == "other_tables":
        conn = sqlite3.connect(master)
        conn.execute("CREATE TABLE company_profile (x TEXT)")
        conn.commit()
        conn.close()
    elif how == "other_baseline":
        build(master)
        conn = sqlite3.connect(master)
        conn.execute("UPDATE schema_baseline SET sha256 = 'different'")
        conn.commit()
        conn.close()
    else:
        build(master)
        conn = sqlite3.connect(master)
        conn.execute("INSERT INTO schema_version (version) VALUES (999)")
        conn.commit()
        conn.close()
    assert auth.inspect_master(master) == ("unreadable", error_type)
    assert auth.master_setup_state(master) == "unreadable"


@pytest.mark.parametrize("state", ["empty", "built", "ready", "garbage", "other_tables"])
def test_inspecting_never_changes_the_file(master, state):
    if state == "empty":
        master.write_bytes(b"")
    elif state == "built":
        build(master)
    elif state == "ready":
        build(master)
        add_master(master)
    elif state == "garbage":
        master.write_bytes(b"not a database " * 40)
    else:
        conn = sqlite3.connect(master)
        conn.execute("CREATE TABLE x (y TEXT)")
        conn.commit()
        conn.close()
    before = master.read_bytes()
    mtime = master.stat().st_mtime_ns
    auth.inspect_master(master)
    assert master.read_bytes() == before and master.stat().st_mtime_ns == mtime
    assert not list(master.parent.glob("*.db-*")) and not (master.parent / "Backups").exists()


def test_a_second_user_does_not_matter(master):
    build(master)
    add_master(master)
    assert auth.master_setup_state(master) == "ready"
