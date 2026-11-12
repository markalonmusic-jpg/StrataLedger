# Starter role templates

Status: **APPROVED by the owner on 2026-11-11** (decision S6), with the answers in section 4. `create_company`
seeds these roles in every new company built from a template or a CSV chart; a subsidiary that copies its parent
gets the parent's roles instead (S7). The code is `modules/services/role_templates.py`;
`tests/test_role_templates.py` checks it against the tables below, so change both together.

Sensitive codes (marked `*` in the registry) are never part of None / View / Standard / Full. They are listed
separately in section 3. Approval limits (`approval_limit`) are not set by any template: the Controls page asks
for them when a company turns approvals on. Admin is fixed and holds all 74 codes.

## 1. What each level means, by module

| Module | View | Standard (includes View) | Full (includes Standard) |
|---|---|---|---|
| Company | none | `company.backup` | `company.settings`, `company.users.manage`, `company.roles.manage`, `company.create` |
| Periods | `period.view` | `period.close` | (reopen is sensitive, section 3) |
| Ledger | `ledger.view` | `je.create`, `je.post`, `je.reverse` | `account.manage` |
| Customers / AR | `ar.view` | `customer.manage`, `invoice.create`, `invoice.send`, `payment.receive`, `credit_memo.create` | `invoice.void` |
| Vendors / AP | `ap.view` | `vendor.manage`, `bill.create`, `payment.make` | `bill.void` |
| Purchasing | `po.view` | `po.create`, `receiving.stock` | `receiving.jobsite` |
| Inventory | `inventory.view` | `inventory.pull`, `inventory.count` | `inventory.adjust` |
| Projects / CRM | `project.view` | `estimate.create`, `change_order.create` | `project.create`, `project.manage` |
| Pay applications | none | `payapp.create` | `retainage.release` |
| Fixed assets | `asset.view` | `asset.create`, `depreciation.run` | `asset.dispose` |
| Loans | `loan.view` | `loan.manage` | same as Standard |
| Time | none | `time.enter` | same as Standard |
| Imports | none | `import.run` | same as Standard |
| Reports | `report.financial` | `report.job_cost` | `report.export` |
| AI | none | `ai.use` | `ai.settings` |

## 2. The roles (None / View / Standard / Full)

| Module | Controller | Accountant | AP Clerk | AR Clerk | General Manager | Project Manager | Warehouse | Foreman | Payroll | Sales | Viewer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Company | Standard | None | None | None | None | None | None | None | None | None | None |
| Periods | Standard | Standard | None | None | View | None | None | None | View | None | View |
| Ledger | Full | Full | None | None | View | None | None | None | View | None | View |
| Customers / AR | Full | Standard | None | Standard | View | None | None | None | None | View | View |
| Vendors / AP | Full | Standard | None | None | View | View | None | None | None | None | View |
| Purchasing | Standard | View | None | None | Standard | Standard | View | None | None | None | View |
| Inventory | View | View | None | None | View | View | Standard | None | None | None | View |
| Projects / CRM | View | View | None | None | Full | Standard | None | View | None | Standard | View |
| Pay applications | Standard | None | None | None | Standard | Standard | None | None | None | None | None |
| Fixed assets | Full | Standard | None | None | None | None | None | None | None | None | View |
| Loans | Full | View | None | None | None | None | None | None | None | None | View |
| Time | None | None | None | None | None | Standard | None | Standard | Standard | None | None |
| Imports | Standard | Standard | None | None | None | None | None | None | Standard | None | None |
| Reports | Full | Standard | None | None | Standard | Standard | None | None | View | None | Standard |
| AI | Standard | Standard | None | None | Standard | None | None | None | None | None | None |

Exact extra codes (on top of the levels above)
- AP Clerk: `vendor.manage`, `bill.create`, `ap.view`, `po.create`, `po.view`. Cannot approve or pay.
- Foreman: `receiving.jobsite`.
- Sales: `customer.manage`, `invoice.create` (draft invoices only: no `invoice.send` or `invoice.void`).

Project scope: Project Manager and Foreman are **Assigned** (only their projects); every other role is **All**.
The General chart template omits Project Manager, General Manager, Warehouse and Foreman (S6).

## 3. Sensitive permissions, per role (Yes = granted)

| Code | Controller | Accountant | AP Clerk | AR Clerk | General Manager | Project Manager | Warehouse | Foreman | Payroll | Sales | Viewer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `period.reopen` | Yes | | | | | | | | | | |
| `year.reopen` | Yes | | | | | | | | | | |
| `company.restore` | | | | | | | | | | | |
| `je.approve` | Yes | | | | | | | | | | |
| `bill.approve` | Yes | | | | Yes | Yes | | | | | |
| `bill.override_match` | Yes | | | | | | | | | | |
| `payment.approve` | Yes | | | | | | | | | | |
| `payment.release_hold` | Yes | | | | | | | | | | |
| `po.approve` | Yes | | | | Yes | Yes | | | | | |
| `subcontract.approve` | | | | | Yes | Yes | | | | | |
| `estimate.approve` | | | | | Yes | | | | | | |
| `change_order.approve` | | | | | Yes | Yes | | | | | |
| `contract.approve` | | | | | Yes | | | | | | |
| `payapp.approve` | Yes | | | | Yes | | | | | | |
| `asset.approve` | Yes | | | | | | | | | | |
| `time.approve` | | | | | Yes | Yes | | | Yes | | |
| `import.approve` | Yes | | | | | | | | | | |
| `payroll.view` | Yes | | | | | | | | Yes | | |
| `payroll.import` | | | | | | | | | Yes | | |
| `view.tax_ids` | Yes | | | | | | | | | | |
| `view.bank_details` | Yes | | | | | | | | | | |
| `audit.view` | Yes | | | | | | | | | | |

## 4. Owner's answers (2026-11-11)
1. Controller holds both `period.reopen` and `year.reopen` (decision L7 amended). Reopening a closed year needs
   two confirmations in the UI and a typed year name (see L7 amended in the decisions record).
2. Accountant also edits the chart: Ledger is Full (adds `account.manage`).
3. Payroll imports are approved by the Controller (`import.approve`); Payroll imports but does not approve.
4. Sales creates draft invoices (`invoice.create`) but cannot send or void them.
5. No approval limits in the templates; the Controls page asks for limits when a company turns approvals on.

Noted for a later review (as approved, these roles do not hold them): Warehouse has no `receiving.stock`
(Purchasing is View), and Project Manager has no `project.manage` (Projects is Standard).
