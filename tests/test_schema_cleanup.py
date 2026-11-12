"""Pre-release cleanup of unused baseline objects (CLAUDE.md section 6, Schema cleanup)."""
import pytest

import modules.database as database


@pytest.fixture
def conn(fresh_company):
    connection = database.get_connection(fresh_company)
    yield connection
    connection.close()


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_estimate_no_longer_points_at_crm_opportunity(conn):
    columns = [c["name"] for c in conn.execute("PRAGMA table_info(estimate)")]
    assert columns == ["estimate_id", "estimate_number", "name", "contact_id", "assigned_pm_id",
                       "total_cost_cents", "total_price_cents", "status", "created_at"]
    assert [fk["table"] for fk in conn.execute("PRAGMA foreign_key_list(estimate)")] == ["contact"]


CRM_TABLES = [
    "crm_opportunity", "crm_change_order", "crm_change_line", "crm_activity_stream", "crm_stage_history",
    "crm_pipeline", "crm_stage", "crm_approval_rule", "crm_approval_instance",
]


@pytest.mark.parametrize("table", CRM_TABLES)
def test_crm_table_is_gone(conn, table):
    assert table not in tables(conn)


def test_nothing_in_the_schema_mentions_the_old_crm_tables(conn):
    mentions = [name for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")
                if "crm_" in sql]
    assert mentions == []


def test_the_replacement_tables_exist(conn):
    # The approval chain tables replace crm_approval_rule / crm_approval_instance.
    assert {"approval_policy", "approval_step", "approval_request", "approval_action"} <= tables(conn)
    # change_order / change_order_line are the canonical change-order tables.
    assert {"change_order", "change_order_line"} <= tables(conn)


def test_purchase_order_subcontract_is_gone(conn):
    # Replaced by the PO / subcontract design (docs/po_ap_matching_design.md); nothing read it.
    assert "purchase_order_subcontract" not in tables(conn)
    mentions = [name for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")
                if "purchase_order_subcontract" in sql]
    assert mentions == []


def test_company_profile_is_gone_from_the_baseline(conn):
    # Part 2 of 2.4: the New Company screen no longer writes it and nothing reads it.
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "company_profile" not in names
