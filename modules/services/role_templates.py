"""The starter roles a new company gets (decision S6; approved table in docs/role_templates.md).

Each role is described the way the doc describes it: a level per module (None / View / Standard / Full, where
each level includes the ones below it), a few exact extra codes, the sensitive codes it holds, and its project
scope. tests/test_role_templates.py checks this file against the doc's tables, so the two cannot drift.
Admin is not here: it is fixed and seeded by the baseline with every code. No approval limits are set
(decision 5 of the review): the Controls page asks for them when a company turns approvals on.
"""
LEVELS = ("None", "View", "Standard", "Full")

MODULE_LEVELS = {
    "Company": {"View": [], "Standard": ["company.backup"],
                "Full": ["company.settings", "company.users.manage", "company.roles.manage", "company.create"]},
    "Periods": {"View": ["period.view"], "Standard": ["period.close"], "Full": []},
    "Ledger": {"View": ["ledger.view"], "Standard": ["je.create", "je.post", "je.reverse"], "Full": ["account.manage"]},
    "Customers / AR": {"View": ["ar.view"],
                       "Standard": ["customer.manage", "invoice.create", "invoice.send", "payment.receive",
                                    "credit_memo.create"],
                       "Full": ["invoice.void"]},
    "Vendors / AP": {"View": ["ap.view"], "Standard": ["vendor.manage", "bill.create", "payment.make"],
                     "Full": ["bill.void"]},
    "Purchasing": {"View": ["po.view"], "Standard": ["po.create", "receiving.stock"], "Full": ["receiving.jobsite"]},
    "Inventory": {"View": ["inventory.view"], "Standard": ["inventory.pull", "inventory.count"],
                  "Full": ["inventory.adjust"]},
    "Projects / CRM": {"View": ["project.view"], "Standard": ["estimate.create", "change_order.create"],
                       "Full": ["project.create", "project.manage"]},
    "Pay applications": {"View": [], "Standard": ["payapp.create"], "Full": ["retainage.release"]},
    "Fixed assets": {"View": ["asset.view"], "Standard": ["asset.create", "depreciation.run"], "Full": ["asset.dispose"]},
    "Loans": {"View": ["loan.view"], "Standard": ["loan.manage"], "Full": []},
    "Time": {"View": [], "Standard": ["time.enter"], "Full": []},
    "Imports": {"View": [], "Standard": ["import.run"], "Full": []},
    "Reports": {"View": ["report.financial"], "Standard": ["report.job_cost"], "Full": ["report.export"]},
    "AI": {"View": [], "Standard": ["ai.use"], "Full": ["ai.settings"]},
}
MODULES = tuple(MODULE_LEVELS)


def _row(**levels):
    unknown = set(levels) - {m.replace(" / ", "_").replace(" ", "_").lower() for m in MODULES}
    assert not unknown, unknown
    return {m: levels.get(m.replace(" / ", "_").replace(" ", "_").lower(), "None") for m in MODULES}


# Order is the order in the doc.
ROLES = {
    "Controller": {
        "levels": _row(company="Standard", periods="Standard", ledger="Full", customers_ar="Full", vendors_ap="Full",
                       purchasing="Standard", inventory="View", projects_crm="View", pay_applications="Standard",
                       fixed_assets="Full", loans="Full", imports="Standard", reports="Full", ai="Standard"),
        "extra": [],
        "sensitive": ["period.reopen", "year.reopen", "je.approve", "bill.approve", "bill.override_match",
                      "payment.approve", "payment.release_hold", "po.approve", "payapp.approve", "asset.approve",
                      "import.approve", "payroll.view", "view.tax_ids", "view.bank_details", "audit.view"],
        "scope": "All",
    },
    "Accountant": {
        "levels": _row(periods="Standard", ledger="Full", customers_ar="Standard", vendors_ap="Standard",
                       purchasing="View", inventory="View", projects_crm="View", fixed_assets="Standard", loans="View",
                       imports="Standard", reports="Standard", ai="Standard"),
        "extra": [],
        "sensitive": [],
        "scope": "All",
    },
    "AP Clerk": {
        "levels": _row(),
        "extra": ["vendor.manage", "bill.create", "ap.view", "po.create", "po.view"],
        "sensitive": [],
        "scope": "All",
    },
    "AR Clerk": {
        "levels": _row(customers_ar="Standard"),
        "extra": [],
        "sensitive": [],
        "scope": "All",
    },
    "General Manager": {
        "levels": _row(periods="View", ledger="View", customers_ar="View", vendors_ap="View", purchasing="Standard",
                       inventory="View", projects_crm="Full", pay_applications="Standard", reports="Standard",
                       ai="Standard"),
        "extra": [],
        "sensitive": ["bill.approve", "po.approve", "subcontract.approve", "estimate.approve", "change_order.approve",
                      "contract.approve", "payapp.approve", "time.approve"],
        "scope": "All",
        "construction_only": True,
    },
    "Project Manager": {
        "levels": _row(vendors_ap="View", purchasing="Standard", inventory="View", projects_crm="Standard",
                       pay_applications="Standard", time="Standard", reports="Standard"),
        "extra": [],
        "sensitive": ["bill.approve", "po.approve", "subcontract.approve", "change_order.approve", "time.approve"],
        "scope": "Assigned",
        "construction_only": True,
    },
    "Warehouse": {
        "levels": _row(purchasing="View", inventory="Standard"),
        "extra": [],
        "sensitive": [],
        "scope": "All",
        "construction_only": True,
    },
    "Foreman": {
        "levels": _row(projects_crm="View", time="Standard"),
        "extra": ["receiving.jobsite"],
        "sensitive": [],
        "scope": "Assigned",
        "construction_only": True,
    },
    "Payroll": {
        "levels": _row(periods="View", ledger="View", time="Standard", imports="Standard", reports="View"),
        "extra": [],
        "sensitive": ["time.approve", "payroll.view", "payroll.import"],
        "scope": "All",
    },
    "Sales": {
        "levels": _row(customers_ar="View", projects_crm="Standard"),
        "extra": ["customer.manage", "invoice.create"],
        "sensitive": [],
        "scope": "All",
    },
    "Viewer": {
        "levels": _row(periods="View", ledger="View", customers_ar="View", vendors_ap="View", purchasing="View",
                       inventory="View", projects_crm="View", fixed_assets="View", loans="View", reports="Standard"),
        "extra": [],
        "sensitive": [],
        "scope": "All",
    },
}


def codes_for_level(module, level):
    """Every code a level grants in one module (a level includes the levels below it)."""
    if level not in LEVELS:
        raise ValueError(level)
    codes = []
    for step in LEVELS[1:LEVELS.index(level) + 1]:
        codes += MODULE_LEVELS[module][step]
    return codes


def permissions_for(role_code):
    role = ROLES[role_code]
    codes = set(role["extra"]) | set(role["sensitive"])
    for module, level in role["levels"].items():
        codes |= set(codes_for_level(module, level))
    return codes


def roles_for_template(template_key):
    """The starter roles for a chart template. The General template omits the construction roles (S6)."""
    return [code for code, role in ROLES.items()
            if not (template_key == "general" and role.get("construction_only"))]


def seed_starter_roles(conn, template_key, created_at):
    """Insert the starter roles and their permissions inside the caller's transaction."""
    for code in roles_for_template(template_key):
        conn.execute("INSERT INTO role (role_code, name, is_system, is_active, project_scope, created_at) "
                     "VALUES (?, ?, 0, 1, ?, ?)", (code, code, ROLES[code]["scope"], created_at))
        for permission in sorted(permissions_for(code)):
            conn.execute("INSERT INTO role_permission (role_code, permission_code) VALUES (?, ?)", (code, permission))
