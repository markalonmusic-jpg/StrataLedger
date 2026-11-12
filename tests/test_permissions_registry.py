"""The Python permission registry is the source of truth for the seeded permission table."""
import pytest

import modules.database as database
from modules.services import permissions as p

DOCUMENT_TYPES = ("Bill", "Journal entry", "Payment", "Purchase order", "Subcontract", "Pay application",
                  "Import batch", "Asset disposal", "Estimate", "Change order", "Contract")


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def test_registry_equals_the_seeded_permission_table(conn):
    rows = {r["permission_code"]: (r["module"], r["description"], r["is_sensitive"])
            for r in conn.execute("SELECT * FROM permission")}
    registry = {code: (perm.module, perm.description, int(perm.is_sensitive)) for code, perm in p.PERMISSIONS.items()}
    assert rows == registry


def test_admin_holds_every_registry_permission(conn):
    granted = {r[0] for r in conn.execute("SELECT permission_code FROM role_permission WHERE role_code = 'Admin'")}
    assert granted == set(p.PERMISSIONS)


def test_new_approve_permissions_exist_and_are_sensitive():
    for code in ("je.approve", "payment.approve", "asset.approve", "contract.approve"):
        assert p.PERMISSIONS[code].is_sensitive


def test_agent_allowed_is_exactly_the_decided_list():
    expected = (
        {c for c in p.PERMISSIONS if c.endswith(".view")}
        | {c for c in p.PERMISSIONS if c.startswith("report.") and c != "report.export"}
        | {"ai.use", "import.run", "invoice.create", "bill.create", "je.create", "credit_memo.create"}
    ) - {c for c, perm in p.PERMISSIONS.items() if perm.is_sensitive}
    assert set(p.AGENT_ALLOWED) == expected


def test_no_sensitive_code_is_agent_allowed():
    sensitive = {c for c, perm in p.PERMISSIONS.items() if perm.is_sensitive}
    assert {"payroll.view", "view.tax_ids", "view.bank_details", "audit.view"} <= sensitive
    assert sensitive.isdisjoint(p.AGENT_ALLOWED)
    assert isinstance(p.AGENT_ALLOWED, frozenset)  # an explicit list: new codes are not added by a rule


def test_no_approve_or_post_permission_is_agent_allowed():
    for code in p.AGENT_ALLOWED:
        assert not code.endswith((".approve", ".post", ".void", ".reverse", ".close", ".reopen", ".settings",
                                  ".manage", ".release", ".release_hold", ".override_match")), code
    assert "report.export" not in p.AGENT_ALLOWED


def test_project_scoped_is_the_decided_list():
    assert set(p.PROJECT_SCOPED) == {
        "project.manage", "project.view", "estimate.create", "estimate.approve", "change_order.create",
        "change_order.approve", "payapp.create", "payapp.approve", "retainage.release", "receiving.jobsite",
        "inventory.pull", "time.enter", "time.approve", "report.job_cost", "bill.approve", "po.approve",
        "subcontract.approve",
    }
    assert "project.create" not in p.PROJECT_SCOPED


def test_every_listed_code_is_in_the_registry():
    for name in ("AGENT_ALLOWED", "PROJECT_SCOPED"):
        assert set(getattr(p, name)) <= set(p.PERMISSIONS), name
    assert set(p.SUBMIT_PERMISSION.values()) <= set(p.PERMISSIONS)
    assert set(p.APPROVE_PERMISSION.values()) <= set(p.PERMISSIONS)


def test_approval_limits_cover_every_document_type(conn):
    assert tuple(p.LIMIT_DOCUMENT_TYPES) == DOCUMENT_TYPES
    limit_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'approval_limit'").fetchone()[0]
    for document_type in DOCUMENT_TYPES:
        assert f"'{document_type}'" in limit_sql


def test_document_maps_cover_every_document_type(conn):
    assert tuple(p.DOCUMENT_TYPES) == DOCUMENT_TYPES
    assert set(p.SUBMIT_PERMISSION) == set(DOCUMENT_TYPES) == set(p.APPROVE_PERMISSION)
    policy_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'approval_policy'").fetchone()[0]
    for document_type in DOCUMENT_TYPES:
        assert f"'{document_type}'" in policy_sql


def test_document_maps_are_the_decided_ones():
    assert p.SUBMIT_PERMISSION == {
        "Bill": "bill.create", "Journal entry": "je.create", "Payment": "payment.make",
        "Purchase order": "po.create", "Subcontract": "po.create", "Pay application": "payapp.create",
        "Import batch": "import.run", "Asset disposal": "asset.dispose", "Estimate": "estimate.create",
        "Change order": "change_order.create", "Contract": "project.manage",
    }
    assert p.APPROVE_PERMISSION == {
        "Bill": "bill.approve", "Journal entry": "je.approve", "Payment": "payment.approve",
        "Purchase order": "po.approve", "Subcontract": "subcontract.approve", "Pay application": "payapp.approve",
        "Import batch": "import.approve", "Asset disposal": "asset.approve", "Estimate": "estimate.approve",
        "Change order": "change_order.approve", "Contract": "contract.approve",
    }
    assert p.APPROVE_PERMISSION["Journal entry"] != "je.post"
    for code in p.APPROVE_PERMISSION.values():
        assert p.PERMISSIONS[code].is_sensitive and code not in p.AGENT_ALLOWED
