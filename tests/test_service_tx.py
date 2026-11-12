import sqlite3

import pytest

import config
import modules.database as database
from modules.services.context import ServiceContext
from modules.services.errors import ValidationError
from modules.services.tx import read_connection, write_transaction


def make_context(user_id=1, origin="Human"):
    return ServiceContext(user_id=user_id, company_id=1, origin=origin,
                          company_db_path="company.db", master_db_path="master.db")


def insert_account(conn, code="1000"):
    # account is audited by triggers (003/004); account_type 1 is seeded.
    conn.execute("INSERT INTO account (code, name, type_id) VALUES (?, 'Cash', 1)", (code,))


def count_accounts(db_path):
    conn = database.get_connection(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    finally:
        conn.close()


def audit_context_row(db_path):
    conn = database.get_connection(db_path)
    try:
        return dict(conn.execute("SELECT * FROM audit_context WHERE id = 1").fetchone())
    finally:
        conn.close()


def test_commit_on_success(fresh_company):
    with write_transaction(fresh_company, make_context()) as conn:
        insert_account(conn)
    assert count_accounts(fresh_company) == 1


def test_rollback_on_exception(fresh_company):
    with pytest.raises(RuntimeError):
        with write_transaction(fresh_company, make_context()) as conn:
            insert_account(conn)
            raise RuntimeError("boom")
    assert count_accounts(fresh_company) == 0


def test_rollback_on_constraint_error(fresh_company):
    with pytest.raises(sqlite3.IntegrityError):
        with write_transaction(fresh_company, make_context()) as conn:
            insert_account(conn)
            insert_account(conn)  # duplicate code
    assert count_accounts(fresh_company) == 0


def test_foreign_keys_on_inside_transaction(fresh_company):
    with write_transaction(fresh_company, make_context()) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO account (code, name, type_id) VALUES ('9', 'Bad', 99999)")


def test_connection_closed_after_success_and_failure(fresh_company):
    with write_transaction(fresh_company, make_context()) as conn:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")

    with pytest.raises(RuntimeError):
        with write_transaction(fresh_company, make_context()) as conn:
            raise RuntimeError("boom")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_audit_log_gets_user_and_tags_from_context(fresh_company):
    with write_transaction(fresh_company, make_context(user_id=42)) as conn:
        insert_account(conn)
    conn = database.get_connection(fresh_company)
    try:
        row = conn.execute(
            "SELECT user_id, terminal_id, software_version_tag FROM audit_log "
            "WHERE table_name = 'account' AND action = 'Insert'"
        ).fetchone()
    finally:
        conn.close()
    assert row["user_id"] == 42
    assert row["terminal_id"]
    assert row["software_version_tag"] == config.APP_VERSION


def test_audit_context_is_reset_to_null_after_commit(fresh_company):
    with write_transaction(fresh_company, make_context(user_id=42)) as conn:
        insert_account(conn)
    row = audit_context_row(fresh_company)
    assert row["user_id"] is None
    assert row["terminal_id"] is None
    assert row["software_version_tag"] is None


def test_clock_gives_utc_iso_8601_with_an_explicit_offset():
    from modules.services.clock import utc_now_iso
    stamp = utc_now_iso()
    assert stamp.endswith("+00:00") and "T" in stamp and len(stamp) == len("2026-01-01T00:00:00+00:00")


def test_set_at_is_utc_iso_8601_and_set_during_transaction(fresh_company):
    seen = {}
    with write_transaction(fresh_company, make_context()) as conn:
        seen.update(dict(conn.execute("SELECT * FROM audit_context WHERE id = 1").fetchone()))
    assert seen["user_id"] == 1
    assert seen["software_version_tag"] == config.APP_VERSION
    assert seen["set_at"].endswith("+00:00") or seen["set_at"].endswith("Z")
    assert "T" in seen["set_at"]


def test_audit_context_unchanged_after_failed_transaction(fresh_company):
    before = audit_context_row(fresh_company)
    with pytest.raises(RuntimeError):
        with write_transaction(fresh_company, make_context(user_id=42)) as conn:
            insert_account(conn)
            raise RuntimeError("boom")
    assert audit_context_row(fresh_company) == before


def test_user_never_leaks_between_transactions(fresh_company):
    with write_transaction(fresh_company, make_context(user_id=5)) as conn:
        insert_account(conn, "1000")
    with write_transaction(fresh_company, make_context(user_id=6)) as conn:
        insert_account(conn, "2000")
    conn = database.get_connection(fresh_company)
    try:
        users = [
            r[0]
            for r in conn.execute("SELECT user_id FROM audit_log WHERE table_name = 'account' ORDER BY log_id")
        ]
    finally:
        conn.close()
    assert users == [5, 6]


def test_invalid_origin_rejected_before_any_connection(fresh_company):
    # The context cannot even be built with a bad origin.
    with pytest.raises(ValidationError):
        make_context(origin="Robot")


def test_write_transaction_is_exclusive_until_commit(fresh_company):
    with write_transaction(fresh_company, make_context()) as conn:
        insert_account(conn)
        other = sqlite3.connect(str(fresh_company), timeout=0.1)
        try:
            with pytest.raises(sqlite3.OperationalError):
                other.execute("BEGIN IMMEDIATE")
        finally:
            other.close()


def test_read_connection_reads_and_cannot_write(fresh_company):
    with write_transaction(fresh_company, make_context()) as conn:
        insert_account(conn)
    conn = read_connection(fresh_company)
    try:
        assert conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO account (code, name, type_id) VALUES ('2', 'X', 1)")
    finally:
        conn.close()


def test_get_readonly_connection_is_public_and_read_only(fresh_company):
    conn = database.get_readonly_connection(fresh_company)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM audit_context")
    finally:
        conn.close()


def test_audit_context_uses_the_context_clock_not_the_system_clock(fresh_company):
    import dataclasses
    context = dataclasses.replace(make_context(), now="2031-02-03T04:05:06+00:00", today="2031-02-03")
    seen = {}
    with write_transaction(fresh_company, context) as conn:
        seen.update(dict(conn.execute("SELECT * FROM audit_context WHERE id = 1").fetchone()))
    assert seen["set_at"] == "2031-02-03T04:05:06+00:00"
