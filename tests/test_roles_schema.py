"""Baseline company schema: roles, permissions, approval limits and approval chains."""
import json
import sqlite3

import pytest

import modules.database as database
from modules.services.permissions import PERMISSIONS
from tests.ledger_helpers import rejects, set_user

# The Python registry is the source of truth (tests/test_permissions_registry.py
# checks it against the seeded table row by row).
ALL_CODES = set(PERMISSIONS)

SENSITIVE = {
    "payroll.view", "payroll.import", "view.tax_ids", "view.bank_details",
    "bill.approve", "po.approve", "subcontract.approve", "estimate.approve", "change_order.approve",
    "payapp.approve", "time.approve", "import.approve",
    "bill.override_match", "period.reopen", "year.reopen", "payment.release_hold",
    "company.restore", "audit.view",
    "je.approve", "payment.approve", "asset.approve", "contract.approve",
}

NEW_TABLES = {
    "permission", "role", "role_permission", "approval_limit", "user_project_scope", "access_event",
    "approval_policy", "approval_step", "approval_request", "approval_action",
}


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def count(c, table):
    return c.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def make_role(c, code="PM", scope="All"):
    c.execute(
        "INSERT INTO role (role_code, name, is_system, project_scope, created_at) VALUES (?, ?, 0, ?, '2026-01-01T00:00:00+00:00')",
        (code, code, scope),
    )


def make_project(c):
    contact = c.execute("INSERT INTO contact (name) VALUES ('C') RETURNING contact_id").fetchone()[0]
    return c.execute(
        "INSERT INTO project (project_number, name, contact_id, assigned_pm_id) VALUES ('P-1', 'Job', ?, 1) "
        "RETURNING project_id",
        (contact,),
    ).fetchone()[0]


# --- Version and shape ------------------------------------------------------------

def test_new_tables_exist(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert NEW_TABLES <= tables


# --- Permission registry and Admin -----------------------------------------------------

def test_permission_rows_match_the_design_list(conn):
    rows = conn.execute("SELECT permission_code, module, description, is_sensitive FROM permission").fetchall()
    assert {r["permission_code"] for r in rows} == ALL_CODES
    assert all(r["module"] and r["description"] for r in rows)


def test_sensitive_flags(conn):
    flagged = {r[0] for r in conn.execute("SELECT permission_code FROM permission WHERE is_sensitive = 1")}
    assert flagged == SENSITIVE


def test_permission_checks(conn):
    assert rejects(conn, "INSERT INTO permission VALUES ('x.y', 'm', 'd', 2)")
    assert rejects(conn, "INSERT INTO permission VALUES ('x.y', 'm', 'd', NULL)")
    assert rejects(conn, "INSERT INTO permission VALUES ('x.y', NULL, 'd', 0)")
    assert rejects(conn, "INSERT INTO permission VALUES ('x.y', 'm', NULL, 0)")


def test_admin_role_is_seeded(conn):
    rows = conn.execute("SELECT * FROM role").fetchall()
    assert [r["role_code"] for r in rows] == ["Admin"]
    admin = rows[0]
    assert (admin["name"], admin["is_system"], admin["is_active"], admin["project_scope"]) == ("Admin", 1, 1, "All")
    assert admin["created_at"]


def test_admin_holds_every_permission(conn):
    granted = {r[0] for r in conn.execute("SELECT permission_code FROM role_permission WHERE role_code = 'Admin'")}
    assert granted == ALL_CODES


def test_role_checks(conn):
    stamp = "'2026-01-01T00:00:00+00:00'"
    assert rejects(conn, f"INSERT INTO role VALUES ('A', 'A', 2, 1, 'All', {stamp})")
    assert rejects(conn, f"INSERT INTO role VALUES ('A', 'A', 0, 2, 'All', {stamp})")
    assert rejects(conn, f"INSERT INTO role VALUES ('A', 'A', 0, 1, 'Some', {stamp})")
    assert rejects(conn, "INSERT INTO role VALUES ('A', 'A', 0, 1, 'All', NULL)")
    assert rejects(conn, f"INSERT INTO role VALUES ('A2', 'Admin', 0, 1, 'All', {stamp})")  # name UNIQUE
    make_role(conn, "PM", "Assigned")
    assert conn.execute("SELECT is_active FROM role WHERE role_code = 'PM'").fetchone()[0] == 1


def test_role_permission_needs_real_role_and_permission(conn):
    make_role(conn)
    conn.execute("INSERT INTO role_permission VALUES ('PM', 'bill.approve')")
    assert rejects(conn, "INSERT INTO role_permission VALUES ('PM', 'bill.approve')")
    assert rejects(conn, "INSERT INTO role_permission VALUES ('PM', 'nope.nope')")
    assert rejects(conn, "INSERT INTO role_permission VALUES ('Ghost', 'bill.approve')")


def test_admin_row_cannot_be_changed_or_deleted(conn):
    assert rejects(conn, "UPDATE role SET name = 'Boss' WHERE role_code = 'Admin'")
    assert rejects(conn, "UPDATE role SET is_active = 0 WHERE role_code = 'Admin'")
    assert rejects(conn, "UPDATE role SET project_scope = 'Assigned' WHERE role_code = 'Admin'")
    assert rejects(conn, "DELETE FROM role WHERE role_code = 'Admin'")


def test_admin_grants_cannot_be_removed_but_can_be_added(conn):
    before = count(conn, "role_permission")
    assert rejects(conn, "DELETE FROM role_permission WHERE role_code = 'Admin' AND permission_code = 'je.post'")
    assert rejects(conn, "DELETE FROM role_permission WHERE role_code = 'Admin'")
    assert rejects(conn, "UPDATE role_permission SET permission_code = 'ai.use' WHERE role_code = 'Admin' AND permission_code = 'je.post'")
    assert count(conn, "role_permission") == before
    # A later migration can add a permission and grant it to Admin.
    conn.execute("INSERT INTO permission VALUES ('future.thing', 'future', 'A later module', 0)")
    conn.execute("INSERT INTO role_permission VALUES ('Admin', 'future.thing')")
    assert count(conn, "role_permission") == before + 1


def test_other_roles_can_be_edited_and_deleted(conn):
    make_role(conn)
    conn.execute("INSERT INTO role_permission VALUES ('PM', 'bill.approve')")
    conn.execute("UPDATE role SET name = 'Project Manager' WHERE role_code = 'PM'")
    conn.execute("DELETE FROM role WHERE role_code = 'PM'")
    assert conn.execute("SELECT COUNT(*) FROM role_permission WHERE role_code = 'PM'").fetchone()[0] == 0


# --- Approval limits, project scope ---------------------------------------------------

def test_approval_limit(conn):
    make_role(conn)
    for doc in ("Bill", "Journal entry", "Payment", "Purchase order", "Subcontract", "Pay application",
                "Import batch", "Asset disposal"):
        conn.execute("INSERT INTO approval_limit VALUES ('PM', ?, 1000)", (doc,))
    for doc in ("Estimate", "Change order", "Contract"):
        conn.execute("INSERT INTO approval_limit VALUES ('PM', ?, 1000)", (doc,))
    assert rejects(conn, "INSERT INTO approval_limit VALUES ('PM', 'Invoice', 1000)")
    assert rejects(conn, "INSERT INTO approval_limit VALUES ('PM', 'Bill', 5)")  # duplicate key
    make_role(conn, "AP")
    assert rejects(conn, "INSERT INTO approval_limit VALUES ('AP', 'Bill', -1)")
    assert rejects(conn, "INSERT INTO approval_limit VALUES ('AP', 'Bill', 12.5)")
    assert rejects(conn, "INSERT INTO approval_limit VALUES ('AP', 'Bill', NULL)")
    assert rejects(conn, "INSERT INTO approval_limit VALUES ('Ghost', 'Bill', 1)")
    conn.execute("INSERT INTO approval_limit VALUES ('AP', 'Bill', 0)")


def test_user_project_scope_has_no_user_fk_but_a_project_fk(conn):
    project_id = make_project(conn)
    fks = {fk["from"]: fk["table"] for fk in conn.execute("PRAGMA foreign_key_list(user_project_scope)")}
    assert fks == {"project_id": "project"}
    conn.execute("INSERT INTO user_project_scope VALUES (999, ?)", (project_id,))  # a master user id
    assert rejects(conn, "INSERT INTO user_project_scope VALUES (999, ?)", (project_id,))
    assert rejects(conn, "INSERT INTO user_project_scope VALUES (1, 424242)")
    assert rejects(conn, "INSERT INTO user_project_scope VALUES (NULL, ?)", (project_id,))


# --- access_event ---------------------------------------------------------------------

def test_access_event_accepts_and_checks(conn):
    conn.execute(
        "INSERT INTO access_event (occurred_at, user_id, actor_type, event_type, permission_code, record_type, record_id, origin) "
        "VALUES ('2026-01-01T00:00:00+00:00', 5, 'User', 'Denied', 'je.post', 'journal_entry', 9, 'Human')"
    )
    conn.execute(
        "INSERT INTO access_event (occurred_at, user_id, actor_type, event_type) "
        "VALUES ('2026-01-01T00:00:00+00:00', 1, 'Master', 'Open company')"
    )
    assert rejects(conn, "INSERT INTO access_event (occurred_at, actor_type, event_type) VALUES ('t', 'Robot', 'Denied')")
    assert rejects(conn, "INSERT INTO access_event (occurred_at, actor_type, event_type) VALUES ('t', 'User', 'Peeked')")
    assert rejects(conn, "INSERT INTO access_event (occurred_at, actor_type, event_type) VALUES (NULL, 'User', 'Denied')")


def test_access_event_is_append_only(conn):
    conn.execute(
        "INSERT INTO access_event (occurred_at, actor_type, event_type) VALUES ('t', 'User', 'Denied')"
    )
    assert rejects(conn, "UPDATE access_event SET user_id = 3")
    assert rejects(conn, "DELETE FROM access_event")
    assert count(conn, "access_event") == 1


def test_access_event_has_no_value_columns(conn):
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(access_event)")}
    assert columns == {"event_id", "occurred_at", "user_id", "actor_type", "event_type", "permission_code",
                       "record_type", "record_id", "origin"}


# --- company_settings.require_separate_approver ----------------------------------------------

def test_require_separate_approver_setting(conn):
    if count(conn, "company_settings") == 0:
        conn.execute("INSERT INTO company_settings (id, company_name, fiscal_year_start) VALUES (1, 'Co', '01-01')")
    assert conn.execute("SELECT require_separate_approver FROM company_settings").fetchone()[0] == 0  # decided default
    assert rejects(conn, "UPDATE company_settings SET require_separate_approver = 2")
    assert rejects(conn, "UPDATE company_settings SET require_separate_approver = NULL")
    conn.execute("UPDATE company_settings SET require_separate_approver = 1")


def test_setting_change_is_audit_logged(conn):
    if count(conn, "company_settings") == 0:
        conn.execute("INSERT INTO company_settings (id, company_name, fiscal_year_start) VALUES (1, 'Co', '01-01')")
    set_user(conn, 7)
    conn.execute("UPDATE company_settings SET require_separate_approver = 1")
    row = conn.execute(
        "SELECT user_id, old_value, new_value FROM audit_log WHERE table_name = 'company_settings' AND action = 'Update'"
    ).fetchone()
    assert row["user_id"] == 7
    assert json.loads(row["old_value"])["require_separate_approver"] == 0
    assert json.loads(row["new_value"])["require_separate_approver"] == 1


# --- Audit triggers -------------------------------------------------------------------

AUDITED_005 = {
    "role": ("insert", "update", "delete"),
    "role_permission": ("insert", "update", "delete"),
    "approval_limit": ("insert", "update", "delete"),
    "user_project_scope": ("insert", "update", "delete"),
    "approval_policy": ("insert", "update", "delete"),
    "approval_step": ("insert", "update", "delete"),
    "company_settings": ("insert", "update"),
}


def test_audit_triggers_cover_every_column_005(conn):
    missing = []
    for table, events in AUDITED_005.items():
        columns = [c["name"] for c in conn.execute(f'PRAGMA table_info("{table}")')]
        for event in events:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name = ?", (f"audit_{table}_{event}",)
            ).fetchone()
            if row is None:
                missing.append(f"audit_{table}_{event} (no trigger)")
                continue
            for prefix in {"insert": ["NEW"], "delete": ["OLD"], "update": ["OLD", "NEW"]}[event]:
                missing += [f"audit_{table}_{event}: {prefix}.{c}" for c in columns if f"{prefix}.{c}" not in row[0]]
    assert missing == []


def audit_actions(c, table):
    return [r[0] for r in c.execute("SELECT action FROM audit_log WHERE table_name = ? ORDER BY log_id", (table,))]


def test_role_changes_are_audited_with_the_user(conn):
    set_user(conn, 11)
    make_role(conn)
    conn.execute("INSERT INTO role_permission VALUES ('PM', 'bill.approve')")
    conn.execute("INSERT INTO approval_limit VALUES ('PM', 'Bill', 500)")
    conn.execute("UPDATE approval_limit SET max_amount_cents = 900 WHERE role_code = 'PM'")
    conn.execute("UPDATE role SET name = 'Project Manager' WHERE role_code = 'PM'")
    project_id = make_project(conn)
    conn.execute("INSERT INTO user_project_scope VALUES (3, ?)", (project_id,))
    conn.execute("DELETE FROM user_project_scope")
    conn.execute("DELETE FROM approval_limit")
    conn.execute("DELETE FROM role_permission WHERE role_code = 'PM'")
    conn.execute("DELETE FROM role WHERE role_code = 'PM'")
    assert audit_actions(conn, "role") == ["Insert", "Update", "Delete"]
    assert audit_actions(conn, "role_permission") == ["Insert", "Delete"]
    assert audit_actions(conn, "approval_limit") == ["Insert", "Update", "Delete"]
    assert audit_actions(conn, "user_project_scope") == ["Insert", "Delete"]
    users = {r[0] for r in conn.execute(
        "SELECT user_id FROM audit_log WHERE table_name IN ('role', 'role_permission', 'approval_limit', 'user_project_scope')")}
    assert users == {11}
    update = conn.execute(
        "SELECT old_value, new_value FROM audit_log WHERE table_name = 'approval_limit' AND action = 'Update'"
    ).fetchone()
    assert json.loads(update["old_value"])["max_amount_cents"] == 500
    assert json.loads(update["new_value"])["max_amount_cents"] == 900


def test_approval_policy_and_step_changes_are_audited(conn):
    make_role(conn)
    set_user(conn, 4)
    pid = conn.execute(
        "INSERT INTO approval_policy (name, document_type) VALUES ('Big bills', 'Bill') RETURNING policy_id").fetchone()[0]
    sid = conn.execute(
        "INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 1, 'PM') RETURNING step_id", (pid,)).fetchone()[0]
    conn.execute("UPDATE approval_step SET required_count = 2 WHERE step_id = ?", (sid,))
    conn.execute("UPDATE approval_policy SET is_active = 0 WHERE policy_id = ?", (pid,))
    conn.execute("DELETE FROM approval_policy WHERE policy_id = ?", (pid,))  # cascades to its steps
    assert audit_actions(conn, "approval_policy") == ["Insert", "Update", "Delete"]
    assert audit_actions(conn, "approval_step") == ["Insert", "Update", "Delete"]


# --- Approval chain tables ---------------------------------------------------------------

DOC_TYPES = ["Bill", "Journal entry", "Payment", "Purchase order", "Subcontract", "Pay application",
             "Import batch", "Asset disposal", "Estimate", "Change order", "Contract"]


def make_policy(c, doc="Bill", low=0, high=None, name="P"):
    return c.execute(
        "INSERT INTO approval_policy (name, document_type, min_amount_cents, max_amount_cents) "
        "VALUES (?, ?, ?, ?) RETURNING policy_id", (name, doc, low, high)).fetchone()[0]


def make_request(c, record_id=1, status="Pending", policy_id=None, record_type="invoice"):
    completed_at = None if status == "Pending" else "2026-01-02T00:00:00+00:00"
    return c.execute(
        "INSERT INTO approval_request (document_type, record_type, record_id, amount_cents, policy_id, chain_json, "
        "status, created_by, submitted_by, submitted_at, completed_at) "
        "VALUES ('Bill', ?, ?, 5000, ?, '[]', ?, 1, 1, '2026-01-01T00:00:00+00:00', ?) RETURNING request_id",
        (record_type, record_id, policy_id, status, completed_at)).fetchone()[0]


def raw_request(doc="Bill", record_id=3, amount="1", chain="'[]'", status="Pending", policy="NULL",
                submitted_by="1", submitted_at="'2026-01-01T00:00:00+00:00'", completed_at=None,
                created_by="1", project_id="NULL"):
    """An approval_request INSERT with every column spelled out, for rejection tests."""
    if completed_at is None:
        completed_at = "NULL" if status == "Pending" else "'2026-01-02T00:00:00+00:00'"
    return ("INSERT INTO approval_request (document_type, record_type, record_id, amount_cents, chain_json, status, "
            "policy_id, created_by, project_id, submitted_by, submitted_at, completed_at) VALUES "
            f"('{doc}', 'invoice', {record_id}, {amount}, {chain}, '{status}', {policy}, {created_by}, {project_id}, "
            f"{submitted_by}, {submitted_at}, {completed_at})")


def test_policy_document_types_and_amounts(conn):
    for i, doc in enumerate(DOC_TYPES):
        make_policy(conn, doc, name=f"p{i}")
    assert rejects(conn, "INSERT INTO approval_policy (name, document_type) VALUES ('x', 'Invoice')")
    assert rejects(conn, "INSERT INTO approval_policy (name, document_type) VALUES (NULL, 'Bill')")
    assert rejects(conn, "INSERT INTO approval_policy (name, document_type, min_amount_cents) VALUES ('x', 'Bill', -1)")
    assert rejects(conn, "INSERT INTO approval_policy (name, document_type, min_amount_cents) VALUES ('x', 'Bill', 1.5)")
    assert rejects(conn, "INSERT INTO approval_policy (name, document_type, min_amount_cents, max_amount_cents) "
                             "VALUES ('x', 'Bill', 100, 50)")
    assert rejects(conn, "INSERT INTO approval_policy (name, document_type, is_active) VALUES ('x', 'Bill', 2)")
    row = conn.execute("SELECT min_amount_cents, max_amount_cents, is_active FROM approval_policy WHERE name = 'p0'").fetchone()
    assert tuple(row) == (0, None, 1)  # defaults: from zero, no upper bound, active


def test_policy_band_boundaries_are_inclusive_values(conn):
    make_policy(conn, low=0, high=0, name="zero")  # a band of exactly zero is allowed
    make_policy(conn, low=100, high=100, name="exact", doc="Payment")


def test_step_rules(conn):
    make_role(conn)
    pid = make_policy(conn)
    conn.execute("INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 1, 'PM')", (pid,))
    assert conn.execute("SELECT required_count FROM approval_step").fetchone()[0] == 1
    assert rejects(conn, "INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 1, 'PM')", (pid,))
    conn.execute("INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 1, 'Admin')", (pid,))  # parallel
    assert rejects(conn, "INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 0, 'PM')", (pid,))
    assert rejects(conn, "INSERT INTO approval_step (policy_id, step_no, role_code, required_count) VALUES (?, 2, 'PM', 0)", (pid,))
    assert rejects(conn, "INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 2, 'Ghost')", (pid,))
    assert rejects(conn, "INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (999, 1, 'PM')")


def test_deleting_a_policy_deletes_its_steps(conn):
    make_role(conn)
    pid = make_policy(conn)
    conn.execute("INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 1, 'PM')", (pid,))
    conn.execute("DELETE FROM approval_policy WHERE policy_id = ?", (pid,))
    assert count(conn, "approval_step") == 0


def test_a_role_used_by_a_step_cannot_be_deleted(conn):
    make_role(conn)
    pid = make_policy(conn)
    conn.execute("INSERT INTO approval_step (policy_id, step_no, role_code) VALUES (?, 1, 'PM')", (pid,))
    assert rejects(conn, "DELETE FROM role WHERE role_code = 'PM'")


def test_request_rules(conn):
    make_request(conn, 1)
    for status in ("Approved", "Rejected", "Cancelled"):
        make_request(conn, 1, status=status)  # many finished requests per record are fine
    assert rejects(conn, raw_request(record_id=1))  # second Pending for the same record
    make_request(conn, 2)  # another record
    make_request(conn, 1, record_type="journal_entry")  # same id, other record type
    conn.execute(raw_request(record_id=3))  # the raw helper builds a valid row
    assert rejects(conn, raw_request(record_id=4, status="Done"))
    assert rejects(conn, raw_request(record_id=4, doc="Invoice"))
    assert rejects(conn, raw_request(record_id=4, amount="1.5"))
    assert rejects(conn, raw_request(record_id=4, chain="NULL"))
    assert rejects(conn, raw_request(record_id=4, policy="999"))


def test_request_records_the_creator_and_an_optional_project(conn):
    assert rejects(conn, raw_request(record_id=4, created_by="NULL"))
    assert rejects(conn, raw_request(record_id=4, project_id="424242"))  # project must exist
    project_id = make_project(conn)
    conn.execute(raw_request(record_id=4, project_id=str(project_id)))
    fks = {fk["from"]: fk["table"] for fk in conn.execute("PRAGMA foreign_key_list(approval_request)")}
    assert fks == {"policy_id": "approval_policy", "project_id": "project"}  # created_by: master user id, no FK


def test_request_must_say_who_submitted_and_when(conn):
    assert rejects(conn, raw_request(record_id=4, submitted_by="NULL"))
    assert rejects(conn, raw_request(record_id=4, submitted_at="NULL"))
    conn.execute(raw_request(record_id=4))


def test_completed_at_is_set_exactly_when_the_request_is_finished(conn):
    assert rejects(conn, raw_request(record_id=5, status="Pending", completed_at="'2026-01-02T00:00:00+00:00'"))
    for status in ("Approved", "Rejected", "Cancelled"):
        assert rejects(conn, raw_request(record_id=5, status=status, completed_at="NULL")), status
        conn.execute(raw_request(record_id=5, status=status))
    request_id = make_request(conn, 6)
    assert rejects(conn, "UPDATE approval_request SET status = 'Approved' WHERE request_id = ?", (request_id,))
    assert rejects(conn, "UPDATE approval_request SET completed_at = 't' WHERE request_id = ?", (request_id,))
    conn.execute("UPDATE approval_request SET status = 'Approved', completed_at = 't' WHERE request_id = ?", (request_id,))


def test_a_pending_request_can_finish_and_then_be_resubmitted(conn):
    request_id = make_request(conn, 1)
    conn.execute("UPDATE approval_request SET status = 'Cancelled', completed_at = 't' WHERE request_id = ?", (request_id,))
    make_request(conn, 1)  # resubmitted after an edit


def test_default_request_has_no_policy(conn):
    request_id = make_request(conn, 1)
    assert conn.execute("SELECT policy_id FROM approval_request WHERE request_id = ?", (request_id,)).fetchone()[0] is None


def test_action_rules(conn):
    request_id = make_request(conn)
    insert = ("INSERT INTO approval_action (request_id, step_no, role_code, user_id, decision, reason, self_approved, acted_at) "
              "VALUES (?, 1, 'PM', ?, ?, ?, ?, '2026-01-01T00:00:00+00:00')")
    conn.execute(insert, (request_id, 10, "Approve", None, 0))
    conn.execute(insert, (request_id, 11, "Reject", "Wrong vendor", 0))
    assert rejects(conn, insert, (request_id, 10, "Approve", None, 0))  # same person twice
    assert rejects(conn, insert, (request_id, 12, "Reject", None, 0))  # reject needs a reason
    assert rejects(conn, insert, (request_id, 12, "Reject", "   ", 0))
    assert rejects(conn, insert, (request_id, 12, "Reject", "", 0))
    assert rejects(conn, insert, (request_id, 12, "Maybe", None, 0))
    assert rejects(conn, insert, (request_id, 12, "Approve", None, 2))
    assert rejects(conn, insert, (request_id, None, "Approve", None, 0))
    assert rejects(conn, insert, (999, 13, "Approve", None, 0))
    conn.execute(insert, (request_id, 14, "Approve", None, 1))  # self-approved is recorded, not blocked here


def test_action_is_append_only(conn):
    request_id = make_request(conn)
    conn.execute(
        "INSERT INTO approval_action (request_id, step_no, role_code, user_id, decision, self_approved, acted_at) "
        "VALUES (?, 1, 'PM', 10, 'Approve', 0, 't')", (request_id,))
    assert rejects(conn, "UPDATE approval_action SET decision = 'Reject', reason = 'x'")
    assert rejects(conn, "DELETE FROM approval_action")
    assert count(conn, "approval_action") == 1


def test_action_user_id_has_no_foreign_key(conn):
    fks = {fk["from"]: fk["table"] for fk in conn.execute("PRAGMA foreign_key_list(approval_action)")}
    assert fks == {"request_id": "approval_request"}


# --- Whole-schema guards --------------------------------------------------------------------

def test_no_company_foreign_key_points_at_master_tables(conn):
    from tests.test_ledger_rules import MASTER_ONLY_TABLES, user_tables
    for table in user_tables(conn):
        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            assert fk["table"] not in MASTER_ONLY_TABLES, f"{table}.{fk['from']}"


def test_foreign_key_and_integrity_checks_are_clean(conn):
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert [r[0] for r in conn.execute("PRAGMA integrity_check")] == ["ok"]
