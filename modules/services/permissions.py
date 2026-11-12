"""The permission registry: the single source of truth for permission codes.

Code asks "may this user do bill.approve?", never "is this user an Admin?"
(docs/roles_permissions_design.md section 1). The baseline seeds the same rows
into each company's permission table so screens can list them; a test checks
the two are identical. A new module adds its codes here and in the baseline.
"""
from collections import namedtuple

Permission = namedtuple("Permission", "module description is_sensitive")

PERMISSIONS = {
    # Company
    "company.settings": Permission("Company", "Change company settings", False),
    "company.users.manage": Permission("Company", "Create users and assign roles and access", False),
    "company.roles.manage": Permission("Company", "Create and edit roles and approval limits", False),
    "company.backup": Permission("Company", "Back up and export the company", False),
    "company.restore": Permission("Company", "Restore the company from a backup", True),
    # Periods
    "period.close": Permission("Periods", "Close a fiscal period", False),
    "period.reopen": Permission("Periods", "Reopen a closed fiscal period (reason required)", True),
    "period.view": Permission("Periods", "View fiscal periods", False),
    # Ledger
    "je.create": Permission("Ledger", "Create journal entries", False),
    "je.post": Permission("Ledger", "Post journal entries", False),
    "je.approve": Permission("Ledger", "Approve journal entries", True),
    "je.reverse": Permission("Ledger", "Reverse posted journal entries", False),
    "account.manage": Permission("Ledger", "Create and edit accounts", False),
    "ledger.view": Permission("Ledger", "View the general ledger", False),
    # Customers / AR
    "customer.manage": Permission("Customers / AR", "Create and edit customers", False),
    "invoice.create": Permission("Customers / AR", "Create invoices", False),
    "invoice.send": Permission("Customers / AR", "Send (post) invoices", False),
    "invoice.void": Permission("Customers / AR", "Void invoices", False),
    "payment.receive": Permission("Customers / AR", "Receive customer payments", False),
    "credit_memo.create": Permission("Customers / AR", "Create credit memos", False),
    "ar.view": Permission("Customers / AR", "View receivables", False),
    # Vendors / AP
    "vendor.manage": Permission("Vendors / AP", "Create and edit vendors", False),
    "bill.create": Permission("Vendors / AP", "Enter vendor bills", False),
    "bill.approve": Permission("Vendors / AP", "Approve vendor bills", True),
    "bill.override_match": Permission("Vendors / AP", "Override a purchase order match exception", True),
    "bill.void": Permission("Vendors / AP", "Void vendor bills", False),
    "payment.make": Permission("Vendors / AP", "Pay vendor bills", False),
    "payment.approve": Permission("Vendors / AP", "Approve payments", True),
    "payment.release_hold": Permission("Vendors / AP", "Release a compliance hold on payment", True),
    "ap.view": Permission("Vendors / AP", "View payables", False),
    # Purchasing
    "po.create": Permission("Purchasing", "Create purchase orders", False),
    "po.approve": Permission("Purchasing", "Approve purchase orders", True),
    "subcontract.approve": Permission("Purchasing", "Approve subcontracts", True),
    "receiving.stock": Permission("Purchasing", "Receive stock into the warehouse", False),
    "receiving.jobsite": Permission("Purchasing", "Confirm delivery tickets at the job site", False),
    "po.view": Permission("Purchasing", "View purchase orders", False),
    # Inventory
    "inventory.pull": Permission("Inventory", "Pull inventory to a job", False),
    "inventory.adjust": Permission("Inventory", "Adjust inventory quantities", False),
    "inventory.count": Permission("Inventory", "Count inventory", False),
    "inventory.view": Permission("Inventory", "View inventory", False),
    # Projects / CRM
    "project.create": Permission("Projects / CRM", "Create projects and leads", False),
    "project.manage": Permission("Projects / CRM", "Manage projects", False),
    "estimate.create": Permission("Projects / CRM", "Create estimates", False),
    "estimate.approve": Permission("Projects / CRM", "Approve estimates", True),
    "change_order.create": Permission("Projects / CRM", "Create change orders", False),
    "change_order.approve": Permission("Projects / CRM", "Approve change orders", True),
    "contract.approve": Permission("Projects / CRM", "Approve contracts", True),
    "project.view": Permission("Projects / CRM", "View projects", False),
    # Pay applications
    "payapp.create": Permission("Pay applications", "Create pay applications", False),
    "payapp.approve": Permission("Pay applications", "Approve pay applications", True),
    "retainage.release": Permission("Pay applications", "Release retainage", False),
    # Fixed assets
    "asset.create": Permission("Fixed assets", "Create fixed assets", False),
    "asset.dispose": Permission("Fixed assets", "Dispose of fixed assets", False),
    "asset.approve": Permission("Fixed assets", "Approve asset disposals", True),
    "depreciation.run": Permission("Fixed assets", "Run depreciation", False),
    "asset.view": Permission("Fixed assets", "View fixed assets", False),
    # Loans
    "loan.manage": Permission("Loans", "Manage loans", False),
    "loan.view": Permission("Loans", "View loans", False),
    # Payroll / time
    "time.enter": Permission("Payroll / time", "Enter time", False),
    "time.approve": Permission("Payroll / time", "Approve time", True),
    "payroll.view": Permission("Payroll / time", "View wages and payroll", True),
    "payroll.import": Permission("Payroll / time", "Import payroll", True),
    # Imports
    "import.run": Permission("Imports", "Run imports into staging", False),
    "import.approve": Permission("Imports", "Approve staged import batches", True),
    # Sensitive data
    "view.tax_ids": Permission("Sensitive data", "See tax IDs unmasked", True),
    "view.bank_details": Permission("Sensitive data", "See bank details unmasked", True),
    # Reports
    "report.financial": Permission("Reports", "Run financial reports", False),
    "report.job_cost": Permission("Reports", "Run job cost reports", False),
    "report.export": Permission("Reports", "Export reports", False),
    # AI
    "ai.use": Permission("AI", "Open and use the AI Copilot", False),
    "ai.settings": Permission("AI", "Change AI keys, data sharing and budget", False),
    # Audit
    "audit.view": Permission("Audit", "View the audit trail", True),
}

# An agent (origin 'Agent') may use ONLY these codes, and only when the user it
# runs as holds them. Everything else is denied to an agent, Admin and Master
# included, before any database read. This is an explicit list on purpose: a
# code added to the registry later is denied to agents until it is added here.
AGENT_ALLOWED = frozenset({
    # every *.view code that is not sensitive (no payroll.view, audit.view,
    # view.tax_ids, view.bank_details: no code with is_sensitive is agent-allowed)
    "period.view", "ledger.view", "ar.view", "ap.view", "po.view", "inventory.view", "project.view",
    "asset.view", "loan.view",
    # every report.* code except report.export
    "report.financial", "report.job_cost",
    # drafting only; agents never approve, post, void or change settings
    "ai.use", "import.run", "invoice.create", "bill.create", "je.create", "credit_memo.create",
})

# Permissions that project scope applies to. A role with project_scope =
# 'Assigned' may use these only for projects in user_project_scope; without a
# project they are denied (a bill with no project included, by decision).
PROJECT_SCOPED = frozenset({
    "project.manage", "project.view", "estimate.create", "estimate.approve", "change_order.create",
    "change_order.approve", "payapp.create", "payapp.approve", "retainage.release", "receiving.jobsite",
    "inventory.pull", "time.enter", "time.approve", "report.job_cost", "bill.approve", "po.approve",
    "subcontract.approve",
})

# Document types that can go through an approval chain (same list as the
# approval_policy / approval_request CHECK in the baseline).
DOCUMENT_TYPES = (
    "Bill", "Journal entry", "Payment", "Purchase order", "Subcontract", "Pay application",
    "Import batch", "Asset disposal", "Estimate", "Change order", "Contract",
)

# Document types that approval_limit rows can be set for (its CHECK list):
# every approval document type.
LIMIT_DOCUMENT_TYPES = DOCUMENT_TYPES

# Permission needed to submit (and to cancel on edit) a document's approval request.
SUBMIT_PERMISSION = {
    "Bill": "bill.create",
    "Journal entry": "je.create",
    "Payment": "payment.make",
    "Purchase order": "po.create",
    "Subcontract": "po.create",
    "Pay application": "payapp.create",
    "Import batch": "import.run",
    "Asset disposal": "asset.dispose",
    "Estimate": "estimate.create",
    "Change order": "change_order.create",
    "Contract": "project.manage",
}

# Permission needed to approve or reject a document in an approval chain.
# je.approve is separate from je.post.
APPROVE_PERMISSION = {
    "Bill": "bill.approve",
    "Journal entry": "je.approve",
    "Payment": "payment.approve",
    "Purchase order": "po.approve",
    "Subcontract": "subcontract.approve",
    "Pay application": "payapp.approve",
    "Import batch": "import.approve",
    "Asset disposal": "asset.approve",
    "Estimate": "estimate.approve",
    "Change order": "change_order.approve",
    "Contract": "contract.approve",
}
