# Starter role templates: DRAFT for owner review

Status: **draft, not seeded.** `create_company` creates only the fixed Admin role until you approve this file.
After approval a follow-up change seeds these roles from it, with a test that every role's permissions are in the
registry (`modules/services/permissions.py`, 74 codes). Decision S6 names the roles; the permission sets below are
my proposal from docs/roles_permissions_design.md section 4. Edit freely.

Sensitive codes (marked `*`) are never part of None / View / Standard / Full. They are listed separately in section 3
and are off unless a role is given them. Approval limits (`approval_limit`) are not set by any template: until
you set a limit for a role, the default single-approver chain applies and that role cannot approve above 0.

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

| Module | Admin | Controller | Accountant | AP Clerk | AR Clerk | General Mgr | Project Mgr | Warehouse | Foreman | Payroll | Sales | Viewer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Company | Full | Standard | None | None | None | None | None | None | None | None | None | None |
| Periods | Full | Standard | Standard | None | None | View | None | None | None | View | None | View |
| Ledger | Full | Full | Standard | None | None | View | None | None | None | View | None | View |
| Customers / AR | Full | Full | Standard | None | Standard | View | None | None | None | None | View | View |
| Vendors / AP | Full | Full | Standard | see note A | None | View | View | None | None | None | None | View |
| Purchasing | Full | Standard | View | see note A | None | Standard | Standard | View | see note B | None | None | View |
| Inventory | Full | View | View | None | None | View | View | Standard | None | None | None | View |
| Projects / CRM | Full | View | View | None | None | Full | Standard | None | View | None | Standard | View |
| Pay applications | Full | Standard | None | None | None | Standard | Standard | None | None | None | None | None |
| Fixed assets | Full | Full | Standard | None | None | None | None | None | None | None | None | View |
| Loans | Full | Full | View | None | None | None | None | None | None | None | None | View |
| Time | Full | None | None | None | None | None | Standard | None | Standard | Standard | None | None |
| Imports | Full | Standard | Standard | None | None | None | None | None | None | Standard | None | None |
| Reports | Full | Full | Standard | None | None | Standard | Standard | None | None | View | None | Standard |
| AI | Full | Standard | Standard | None | None | Standard | None | None | None | None | None | None |

Notes
- A. AP Clerk: `vendor.manage`, `bill.create`, `ap.view`, `po.create`, `po.view` only. Cannot approve or pay (no
  `payment.make`).
- B. Foreman: exactly `receiving.jobsite`, `time.enter`, `project.view`, nothing else in Purchasing.
- Project scope: Project Manager and Foreman use scope **Assigned** (only projects they are assigned to); General
  Manager and all other roles use scope **All**.
- The General (non-construction) chart template omits the Project Manager, General Manager, Warehouse and Foreman
  roles (S6).

## 3. Sensitive permissions, per role (Yes = granted, blank = not granted)

| Code | Admin | Controller | Accountant | AP Clerk | AR Clerk | General Mgr | Project Mgr | Warehouse | Foreman | Payroll | Sales | Viewer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `period.reopen` | Yes | Yes | | | | | | | | | | |
| `year.reopen` | Yes | | | | | | | | | | | |
| `company.restore` | Yes | | | | | | | | | | | |
| `je.approve` | Yes | Yes | | | | | | | | | | |
| `bill.approve` | Yes | Yes | | | | Yes | Yes | | | | | |
| `bill.override_match` | Yes | Yes | | | | | | | | | | |
| `payment.approve` | Yes | Yes | | | | | | | | | | |
| `payment.release_hold` | Yes | Yes | | | | | | | | | | |
| `po.approve` | Yes | Yes | | | | Yes | Yes | | | | | |
| `subcontract.approve` | Yes | | | | | Yes | Yes | | | | | |
| `estimate.approve` | Yes | | | | | Yes | | | | | | |
| `change_order.approve` | Yes | | | | | Yes | Yes | | | | | |
| `contract.approve` | Yes | | | | | Yes | | | | | | |
| `payapp.approve` | Yes | Yes | | | | Yes | | | | | | |
| `asset.approve` | Yes | Yes | | | | | | | | | | |
| `time.approve` | Yes | | | | | Yes | Yes | | | Yes | | |
| `import.approve` | Yes | Yes | | | | | | | | | | |
| `payroll.view` | Yes | Yes | | | | | | | | Yes | | |
| `payroll.import` | Yes | | | | | | | | | Yes | | |
| `view.tax_ids` | Yes | Yes | | | | | | | | | | |
| `view.bank_details` | Yes | Yes | | | | | | | | | | |
| `audit.view` | Yes | Yes | | | | | | | | | | |

Admin holds every one of the 74 codes (fixed, already seeded). The Master holds all through its own path.

## 4. Questions for you
1. Should the **Controller** be able to reopen a period (`period.reopen`, per decision L7) but not a closed year
   (`year.reopen`, Admin only)? The table assumes yes.
2. **Accountant** here cannot edit the chart (`account.manage`) or close the company's settings. Add
   `account.manage` to Accountant?
3. **Payroll** holds `payroll.import` and `time.approve` but not `import.approve`; payroll imports then need
   the Controller. Right?
4. **Sales**: customers and estimates but no invoicing. OK, or should Sales create draft invoices?
5. Starting approval limits (for example Project Manager up to $10,000 on bills) are left unset. Do you want
   suggested numbers in the template, or set them per company?
