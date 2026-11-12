"""Baseline master schema: is_master flag, no role CHECK, user_company_access.role_code / access_mode."""
import sqlite3

import pytest

import modules.database as database
from tests.ledger_helpers import rejects

USER_COLUMNS = "username, password_hash, first_name, last_name, email, role"


@pytest.fixture
def fresh(tmp_path, backup_dir):
    path = tmp_path / "fresh_master.db"
    database.ensure_master_database(path)
    c = database.get_connection(path)
    yield c
    c.close()


def add_user(c, username, role="Admin", is_master=None):
    columns, values = USER_COLUMNS, [username, "h", "F", "L", f"{username}@x.test", role]
    if is_master is not None:
        columns += ", is_master"
        values.append(is_master)
    c.execute(f"INSERT INTO app_user ({columns}) VALUES ({', '.join('?' * len(values))})", values)


def error_message(c, sql, params=()):
    with pytest.raises(sqlite3.IntegrityError) as caught:
        c.execute("SAVEPOINT probe")
        try:
            c.execute(sql, params)
        finally:
            c.execute("ROLLBACK TO probe")
            c.execute("RELEASE probe")
    return str(caught.value)


# --- Version ------------------------------------------------------------------------

# --- is_master and the one-Master rule -----------------------------------------------------

def test_is_master_column(fresh):
    columns = {r["name"]: r for r in fresh.execute("PRAGMA table_info(app_user)")}
    assert columns["is_master"]["notnull"] == 1
    assert columns["is_master"]["dflt_value"] == "0"
    add_user(fresh, "newbie")
    assert fresh.execute("SELECT is_master FROM app_user WHERE username = 'newbie'").fetchone()[0] == 0
    assert rejects(fresh, "UPDATE app_user SET is_master = 2 WHERE username = 'newbie'")
    assert rejects(fresh, "UPDATE app_user SET is_master = NULL WHERE username = 'newbie'")


def test_partial_unique_index_on_is_master(fresh):
    row = fresh.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'app_user' AND sql LIKE '%is_master%'"
    ).fetchone()
    assert row is not None
    normalized = " ".join(row[0].lower().split())
    assert "unique" in normalized and "where is_master = 1" in normalized


def test_only_one_user_may_have_the_flag(fresh):
    add_user(fresh, "first", role=None, is_master=1)
    message = error_message(fresh, f"INSERT INTO app_user ({USER_COLUMNS}, is_master) VALUES ('second', 'h', 'F', 'L', 'e', NULL, 1)")
    assert "one Master" in message


def test_a_second_user_with_role_master_is_rejected_with_a_clear_message(fresh):
    if fresh.execute("SELECT COUNT(*) FROM app_user WHERE is_master = 1").fetchone()[0] == 0:
        add_user(fresh, "owner", role="Master", is_master=1)
    message = error_message(
        fresh, f"INSERT INTO app_user ({USER_COLUMNS}) VALUES ('rival', 'h', 'F', 'L', 'r@x.test', 'Master')")
    assert "Only one Master user is allowed" in message


def test_role_master_conflicts_with_the_flag_in_either_direction(fresh):
    add_user(fresh, "flagged", role="Admin", is_master=1)
    # role text 'Master' on someone else while another user holds the flag
    assert "Only one Master" in error_message(
        fresh, f"INSERT INTO app_user ({USER_COLUMNS}) VALUES ('texty', 'h', 'F', 'L', 't@x.test', 'Master')")
    add_user(fresh, "plain", role="Admin")
    assert "Only one Master" in error_message(fresh, "UPDATE app_user SET role = 'Master' WHERE username = 'plain'")
    assert "Only one Master" in error_message(fresh, "UPDATE app_user SET is_master = 1 WHERE username = 'plain'")


def test_role_master_text_first_then_flag_on_another_is_rejected(fresh):
    add_user(fresh, "texty", role="Master")  # the old screens can still write this
    assert "Only one Master" in error_message(
        fresh, f"INSERT INTO app_user ({USER_COLUMNS}, is_master) VALUES ('flagged', 'h', 'F', 'L', 'f@x.test', 'Admin', 1)")


def test_the_master_row_can_still_be_edited(fresh):
    if fresh.execute("SELECT COUNT(*) FROM app_user WHERE is_master = 1").fetchone()[0] == 0:
        add_user(fresh, "owner", role="Master", is_master=1)
    fresh.execute("UPDATE app_user SET first_name = 'Renamed', is_active = 1 WHERE is_master = 1")
    fresh.execute("UPDATE app_user SET is_master = 1 WHERE is_master = 1")


# --- Role CHECK dropped, column kept --------------------------------------------------------

def test_role_column_stays_but_check_is_gone(fresh):
    columns = {r["name"]: r for r in fresh.execute("PRAGMA table_info(app_user)")}
    assert "role" in columns and columns["role"]["dflt_value"] is None
    sql = " ".join(fresh.execute("SELECT sql FROM sqlite_master WHERE name = 'app_user'").fetchone()[0].lower().split())
    assert "check (role in" not in sql
    add_user(fresh, "viewer1", role="Viewer")
    add_user(fresh, "nobody", role=None)
    assert fresh.execute("SELECT role FROM app_user WHERE username = 'viewer1'").fetchone()[0] == "Viewer"


def test_column_set_is_the_old_set_plus_is_master(fresh):
    names = [r["name"] for r in fresh.execute("PRAGMA table_info(app_user)")]
    assert names == ["user_id", "username", "password_hash", "first_name", "last_name", "email", "role",
                     "job_title", "is_active", "created_at", "is_master", "must_change_password"]


# --- user_company_access --------------------------------------------------------------------

def test_user_company_access_new_columns(fresh):
    columns = {r["name"]: r for r in fresh.execute("PRAGMA table_info(user_company_access)")}
    assert columns["role_code"]["type"] == "TEXT" and columns["role_code"]["notnull"] == 0
    assert columns["access_mode"]["notnull"] == 1 and columns["access_mode"]["dflt_value"] == "'Grant'"
    fks = {fk["from"]: fk["table"] for fk in fresh.execute("PRAGMA foreign_key_list(user_company_access)")}
    assert fks == {"user_id": "app_user", "company_id": "company_registry"}  # no FK for role_code


def test_access_mode_values(fresh):
    add_user(fresh, "u1")
    fresh.execute("INSERT INTO company_registry (company_code, legal_name, database_file_path) VALUES ('C1', 'C1', 'c1.db')")
    fresh.execute("INSERT INTO company_registry (company_code, legal_name, database_file_path) VALUES ('C2', 'C2', 'c2.db')")
    fresh.execute("INSERT INTO user_company_access (user_id, company_id) VALUES (1, 1)")
    assert fresh.execute("SELECT access_mode, role_code FROM user_company_access").fetchone()[:] == ("Grant", None)
    fresh.execute("INSERT INTO user_company_access (user_id, company_id, role_code, access_mode) VALUES (1, 2, 'Whatever', 'Deny')")
    assert rejects(fresh, "UPDATE user_company_access SET access_mode = 'Maybe'")
    assert rejects(fresh, "UPDATE user_company_access SET access_mode = NULL")


def test_deleting_a_user_removes_their_company_access(fresh):
    add_user(fresh, "u1")
    fresh.execute("INSERT INTO company_registry (company_code, legal_name, database_file_path) VALUES ('C1', 'C1', 'c1.db')")
    fresh.execute("INSERT INTO user_company_access (user_id, company_id) VALUES (1, 1)")
    fresh.execute("DELETE FROM app_user WHERE user_id = 1")
    assert fresh.execute("SELECT COUNT(*) FROM user_company_access").fetchone()[0] == 0


# --- The first Master (auth.create_first_master replaces create_initial_master_user) --------------

def test_first_master_gets_the_flag(tmp_path, backup_dir):
    from modules.services import auth
    path = tmp_path / "new_master.db"
    auth.create_first_master(path, "owner", "correct horse battery", "Ann", "Owner", "ann@x.test")
    c = database.get_connection(path)
    row = c.execute("SELECT role, is_master FROM app_user WHERE username = 'owner'").fetchone()
    c.close()
    assert tuple(row) == ("Master", 1)


def test_first_master_only_when_empty(tmp_path, backup_dir):
    from modules.services import auth
    from modules.services.errors import ValidationError
    path = tmp_path / "new_master.db"
    auth.create_first_master(path, "owner", "correct horse battery", "Ann", "Owner", "ann@x.test")
    with pytest.raises(ValidationError):
        auth.create_first_master(path, "another", "correct horse battery", "B", "C", "b@x.test")
    assert not hasattr(database, "create_initial_master_user")


# --- Master audit, auth tables (Phase 2.3) ------------------------------------------------------

def test_master_has_an_audit_context_row_that_cannot_be_deleted(fresh):
    assert [tuple(r) for r in fresh.execute("SELECT id, user_id FROM audit_context")] == [(1, None)]
    assert rejects(fresh, "DELETE FROM audit_context")


def test_master_audit_log_is_append_only(fresh):
    add_user(fresh, "u1")
    assert fresh.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1
    assert rejects(fresh, "UPDATE audit_log SET user_id = 3")
    assert rejects(fresh, "DELETE FROM audit_log")


MASTER_AUDITED = {"app_user": ("insert", "update", "delete"), "user_company_access": ("insert", "update", "delete"),
                  "company_registry": ("insert", "update", "delete")}


def test_master_audit_triggers_cover_every_column_but_the_password_hash(fresh):
    missing = []
    for table, events in MASTER_AUDITED.items():
        columns = [c["name"] for c in fresh.execute(f'PRAGMA table_info("{table}")')]
        for event in events:
            row = fresh.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                                (f"audit_{table}_{event}",)).fetchone()
            if row is None:
                missing.append(f"audit_{table}_{event}")
                continue
            for prefix in {"insert": ["NEW"], "delete": ["OLD"], "update": ["OLD", "NEW"]}[event]:
                for column in columns:
                    if column == "password_hash":
                        continue
                    if f"{prefix}.{column}" not in row[0]:
                        missing.append(f"audit_{table}_{event}: {prefix}.{column}")
            if table == "app_user":
                assert "'password_hash'" not in row[0], event
    assert missing == []


def test_audit_rows_name_the_actor_and_never_hold_the_hash(fresh):
    fresh.execute("UPDATE audit_context SET user_id = 1 WHERE id = 1")
    add_user(fresh, "u1")
    fresh.execute("UPDATE app_user SET password_hash = 'scrypt$new' WHERE username = 'u1'")
    fresh.execute("UPDATE app_user SET first_name = 'Renamed' WHERE username = 'u1'")
    rows = [dict(r) for r in fresh.execute("SELECT * FROM audit_log WHERE table_name = 'app_user' ORDER BY log_id")]
    assert [r["action"] for r in rows] == ["Insert", "Update", "Update"]
    assert {r["user_id"] for r in rows} == {1}
    assert '"password_changed":1' in rows[1]["new_value"]
    assert '"password_changed":0' in rows[2]["new_value"]
    for r in rows:
        assert "scrypt" not in (r["old_value"] or "") + (r["new_value"] or "")
        assert "password_hash" not in (r["old_value"] or "") + (r["new_value"] or "")


def test_registry_and_access_changes_are_audited(fresh):
    add_user(fresh, "u1")
    fresh.execute("INSERT INTO company_registry (company_code, legal_name, database_file_path) VALUES ('C1', 'C1', 'c1.db')")
    fresh.execute("INSERT INTO user_company_access (user_id, company_id, role_code) VALUES (1, 1, 'Viewer')")
    fresh.execute("UPDATE user_company_access SET access_mode = 'Deny'")
    tables = [r[0] for r in fresh.execute("SELECT table_name FROM audit_log ORDER BY log_id")]
    assert tables == ["app_user", "company_registry", "user_company_access", "user_company_access"]


def test_must_change_password_column(fresh):
    add_user(fresh, "u1")
    assert fresh.execute("SELECT must_change_password FROM app_user").fetchone()[0] == 0
    assert rejects(fresh, "UPDATE app_user SET must_change_password = 2")


def test_auth_event_is_append_only_and_checked(fresh):
    fresh.execute("INSERT INTO auth_event (occurred_at, event_type, username) VALUES ('t', 'Login failed', 'x')")
    assert rejects(fresh, "INSERT INTO auth_event (occurred_at, event_type) VALUES ('t', 'Peeked')")
    assert rejects(fresh, "INSERT INTO auth_event (occurred_at, event_type) VALUES (NULL, 'Login')")
    assert rejects(fresh, "UPDATE auth_event SET username = 'y'")
    assert rejects(fresh, "DELETE FROM auth_event")
    columns = {r["name"] for r in fresh.execute("PRAGMA table_info(auth_event)")}
    assert columns == {"event_id", "occurred_at", "event_type", "username", "user_id", "actor_user_id",
                       "permission_code", "company_id"}  # no password, hash, code or key column


def test_login_throttle_and_recovery_tables(fresh):
    fresh.execute("INSERT INTO login_throttle (throttle_key, failed_count) VALUES ('x', 1)")
    assert rejects(fresh, "INSERT INTO login_throttle (throttle_key, failed_count) VALUES ('y', -1)")
    fresh.execute("INSERT INTO master_recovery (id, code_hash, created_at) VALUES (1, 'scrypt$h', 't')")
    assert rejects(fresh, "INSERT INTO master_recovery (id, code_hash, created_at) VALUES (2, 'scrypt$h', 't')")
    triggers = {r[0] for r in fresh.execute("SELECT tbl_name FROM sqlite_master WHERE type = 'trigger'")}
    assert "master_recovery" not in triggers and "login_throttle" not in triggers  # never audited
