"""role_templates.py against the approved docs/role_templates.md (decision S6)."""
import re
from pathlib import Path

import pytest

from modules.services import permissions, role_templates as rt

DOC = Path(__file__).resolve().parent.parent / "docs" / "role_templates.md"


def _sections():
    text = DOC.read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.M)
    return {p.split("\n", 1)[0].strip(): p for p in parts[1:]}


def _table(section):
    rows = [line for line in section.splitlines() if line.startswith("|")]
    cells = [[c.strip() for c in line.strip().strip("|").split("|")] for line in rows]
    header, body = cells[0], [r for r in cells[2:]]
    return header, body


def test_doc_is_approved():
    assert "APPROVED" in DOC.read_text(encoding="utf-8").split("\n", 4)[2]


def test_levels_table_matches_the_code():
    header, body = _table(_sections()["1. What each level means, by module"])
    assert header == ["Module", "View", "Standard (includes View)", "Full (includes Standard)"]
    for module, *levels in body:
        for level, cell in zip(("View", "Standard", "Full"), levels):
            assert set(re.findall(r"`([^`]+)`", cell)) == set(rt.MODULE_LEVELS[module][level]), (module, level)


def test_role_matrix_matches_the_code():
    header, body = _table(_sections()["2. The roles (None / View / Standard / Full)"])
    roles = header[1:]
    assert roles == list(rt.ROLES)
    for module, *levels in body:
        for role, level in zip(roles, levels):
            assert rt.ROLES[role]["levels"][module] == level, (role, module)


def test_extra_codes_match_the_code():
    section = _sections()["2. The roles (None / View / Standard / Full)"]
    block = section.split("Exact extra codes", 1)[1].split("\n\n", 1)[0]
    listed = {}
    for line in block.splitlines():
        found = re.match(r"- ([A-Za-z ]+): (.*)", line.strip())
        if found:
            listed[found.group(1)] = set(re.findall(r"`([a-z_.]+)`", found.group(2).split("(")[0]))
    for role, data in rt.ROLES.items():
        assert set(data["extra"]) == listed.get(role, set()), role


def test_sensitive_table_matches_the_code():
    header, body = _table(_sections()["3. Sensitive permissions, per role (Yes = granted)"])
    roles = header[1:]
    for code_cell, *marks in body:
        code = code_cell.strip("`")
        for role, mark in zip(roles, marks):
            assert (code in rt.ROLES[role]["sensitive"]) == (mark == "Yes"), (role, code)


def test_every_code_is_real_and_sensitive_codes_only_come_from_the_sensitive_list():
    for role, data in rt.ROLES.items():
        codes = rt.permissions_for(role)
        assert codes <= set(permissions.PERMISSIONS), role
        sensitive = {c for c in codes if permissions.PERMISSIONS[c].is_sensitive}
        assert sensitive == set(data["sensitive"]), role
    for module, levels in rt.MODULE_LEVELS.items():
        for codes in levels.values():
            assert not any(permissions.PERMISSIONS[c].is_sensitive for c in codes), module


@pytest.mark.parametrize("role,has,lacks", [
    ("Controller", {"period.reopen", "year.reopen", "import.approve", "account.manage"}, {"company.settings"}),
    ("Accountant", {"account.manage", "je.post", "period.close"}, {"period.reopen", "je.approve"}),
    ("AP Clerk", {"bill.create", "po.create"}, {"payment.make", "bill.approve"}),
    ("Sales", {"invoice.create", "customer.manage", "estimate.create"}, {"invoice.send", "invoice.void"}),
    ("Payroll", {"payroll.import", "time.approve"}, {"import.approve"}),
    ("Foreman", {"receiving.jobsite", "time.enter", "project.view"}, {"po.create"}),
    ("Viewer", {"ledger.view", "report.job_cost"}, {"report.export", "audit.view"}),
])
def test_owner_answers(role, has, lacks):
    codes = rt.permissions_for(role)
    assert has <= codes and not (lacks & codes)


def test_scopes_and_template_sets():
    assert {r for r, d in rt.ROLES.items() if d["scope"] == "Assigned"} == {"Project Manager", "Foreman"}
    assert rt.roles_for_template("construction") == list(rt.ROLES)
    assert set(rt.roles_for_template("general")) == set(rt.ROLES) - {
        "Project Manager", "General Manager", "Warehouse", "Foreman"}
