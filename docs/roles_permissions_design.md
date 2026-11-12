# Roles, permissions and approval limits: design draft

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
Existing facts (from the schema report, 2026-11-11): `app_user` and
`user_company_access` live in `system_master.db`; `app_user.role` is a text
column with a CHECK of ten values (Master, Admin, Accountant, HR, AP, AR, Sales,
Marketing, PM, Warehouse); `user_company_access` has only user_id and
company_id; `company_registry.parent_company_id` already exists. Role is checked
today only for sidebar visibility. There is no Viewer role in the schema.

Conventions follow CLAUDE.md: all writes through service functions, posted
records locked, human approval only, no cross-database foreign keys.

---

## 1. Principles

1. **The service layer enforces; the UI only hides.** Every service function that
   writes or reads protected data checks the caller's permission. A hidden
   button is a convenience, never the control.
2. **Permissions are fixed in code; roles are bundles of permissions.** Code
   asks "may this user do `bill.approve`?", never "is this user an Admin?".
3. **A user's role is per company** (Master is the exception: a user-level flag with universal access in its installation; Admin is company-scoped and also covers subsidiaries). One login can be an Admin in one company
   and a Viewer in another (`user_company_access`).
4. **Separation of duties** is a per-company setting chosen at setup (section 5).
5. **The AI Copilot never holds approve, post, void, close or settings
   permissions,** even when the logged-in user has them (section 8).

---

## 2. Where it lives (PROPOSED)

- `system_master.db`: `app_user`, `user_company_access` (adds `role_code` text,
  no foreign key across files).
- Each company file: `role` (code, name, is_system, is_active), `role_permission`
  (role_code, permission_code), `approval_limit`, `user_project_scope`.
  Roles belong to the company, so the Master or that company's Admin can tailor them per company and the
  hosted version needs no change in shape.
- The permission list itself is code (a registry), seeded into a `permission`
  table at upgrade so screens can list it. A migration adds new permissions
  without deleting any.
- Role and access changes are audit-logged (who, what, before/after) and take
  effect on the user's next action (checked on every call, never cached for the
  session).

---

## 3. Permission list (PROPOSED, grouped by module)

| Module | Permissions |
|---|---|
| Company | `company.settings`, `company.users.manage`, `company.roles.manage`, `company.backup`, `company.restore` |
| Periods | `period.close`, `period.reopen`, `period.view` |
| Ledger | `je.create`, `je.approve`, `je.post`, `je.reverse`, `account.manage`, `ledger.view` |
| Customers / AR | `customer.manage`, `invoice.create`, `invoice.send`, `invoice.void`, `payment.receive`, `credit_memo.create`, `ar.view` |
| Vendors / AP | `vendor.manage`, `bill.create`, `bill.approve`, `bill.override_match`, `bill.void`, `payment.make`, `payment.approve`, `payment.release_hold`, `ap.view` |
| Purchasing | `po.create`, `po.approve`, `subcontract.approve`, `receiving.stock` (warehouse), `receiving.jobsite` (foreman delivery tickets), `po.view` |
| Inventory | `inventory.pull`, `inventory.adjust`, `inventory.count`, `inventory.view` |
| Projects / CRM | `project.create`, `project.manage`, `estimate.create`, `estimate.approve`, `change_order.create`, `change_order.approve`, `contract.approve`, `project.view` |
| Pay applications | `payapp.create`, `payapp.approve`, `retainage.release` |
| Fixed assets | `asset.create`, `asset.dispose`, `asset.approve`, `depreciation.run`, `asset.view` |
| Loans | `loan.manage`, `loan.view` |
| Payroll / time | `time.enter`, `time.approve`, `payroll.view` (wages), `payroll.import` |
| Imports | `import.run`, `import.approve` |
| Sensitive data | `view.tax_ids`, `view.bank_details` |
| Reports | `report.financial`, `report.job_cost`, `report.export` |
| AI | `ai.use`, `ai.settings` |
| Audit | `audit.view` |

`je.approve`, `payment.approve`, `asset.approve` and `contract.approve` (added
2026-11-11) are the approve permissions for journal entries, payments, asset
disposals and contracts in approval chains (section 5A). `je.post` stays
separate from `je.approve`.

Anything not listed (for example a new module) adds its permissions in its own
change, with the roles that should get them.

---

## 4. Roles (DECIDED: fully customizable, except Master and Admin)

- **Fixed:** Admin (a company role) and Master (a user-level flag, section 9).
  Their permission sets cannot be edited, renamed or deleted.
- **Everything else is custom.** The Master, or the Admin of that company, creates roles with any name and
  sets each role's access with a checklist by module (section 3). The editor
  shows each module with quick settings (None, View only, Standard, Full) that
  expand to the individual permissions, so any permission can be ticked or
  unticked. Sensitive permissions (wages, tax IDs, bank details, approvals,
  overrides, period reopen) are listed separately and are off unless ticked.
- New modules add permissions that are OFF for custom roles and ON for Admin.
- A role in use cannot be deleted until its users are reassigned. Renaming is
  free. Role edits are audit-logged with before/after and apply on the user's
  next action.
- **Starter templates** (offered when a company is created, then freely edited,
  renamed or removed): Controller, Accountant, AP Clerk, AR Clerk, Project
  Manager, Warehouse, Foreman, Viewer. Suggested contents:

| Template | Suggested holds |
|---|---|
| Controller | All accounting, close and reopen periods, approvals; no user/role management |
| Accountant | Entries, bills, invoices, reports; no reopen, no settings |
| AP Clerk | `vendor.manage`, `bill.create`, `po.create`, `ap.view`; cannot approve or pay |
| AR Clerk | `customer.manage`, `invoice.create`, `payment.receive`, `ar.view` |
| General Manager (Construction Manager) | All of a Project Manager, plus all projects (scope: All), `po.approve`/`bill.approve` up to a higher limit, job-cost and financial reports |
| Project Manager | Projects, estimates, change orders; `bill.approve`, `time.approve`, `po.approve`, `subcontract.approve` within limits and for assigned projects; job-cost reports |
| Warehouse | `receiving.stock`, `inventory.pull`, `inventory.count`, `inventory.view` |
| Foreman | `receiving.jobsite`, `time.enter`, assigned projects only |
| Viewer | `*.view` and reports; no sensitive fields |

---

## 5. Approvals and separation of duties

- **Approval limits.** `approval_limit` holds (role_code, document type, max
  amount_cents). A user may approve only up to their role's limit; larger
  amounts need a higher role. Limits are policy data, not code, and reuse the
  `policy_rule` thresholds where one exists (PO required, override limits).
- **Separation of duties is chosen by the Master when the company is set up**
  (DECIDED), not forced. The setup wizard asks plainly: "Separate duties
  (a different person approves) or small team (one person may do both)?" and
  stores `require_separate_approver` per company. The Master or that
  company's Admin can change it later (logged, visible in the audit trail). The text below describes the ON behavior:
  the person who created a bill, journal entry, payment batch, PO, time
  approval, import batch or write-off cannot be the one who approves or posts
  it. Applies to: bills, journal entries, payments, POs, subcontracts, pay
  applications, imports, asset disposals, period reopen.
- **Small teams.** With the setting OFF (the Master's choice at setup). That is logged,
  shown on a banner in the audit report, and every self-approved item carries
  a flag so a reviewer can find them.
- **Overrides** (match exceptions, compliance holds) need their own permission
  and always record a reason.
- **Period close and reopen** need `period.close` / `period.reopen`;
  reopening requires a reason and is audit-logged.

---

## 5A. Multiple approvers (DECIDED 2026-11-11)

Some companies need more than one approver. Approval is a chain of steps,
configured per company as data. A company that sets nothing gets the single
approval described in section 5: one approver who holds the permission and
has a high enough limit.

- **Policy.** A policy applies to one document type and an amount band
  (min, max; no upper bound when max is empty). Bands for a document type
  must not overlap (service check, with a test).
- **Steps.** A policy has steps that run in order of `step_no`. Steps with the
  same `step_no` are parallel: all must be met before the next step opens.
- **Slots.** Each step names a role and `required_count` (default 1). That
  many DIFFERENT people who hold the role, hold the document's permission and
  have an `approval_limit` covering the amount must approve.
- **One person, one slot.** A person fills at most one slot in the whole
  chain, whatever roles they hold. Master and Admin follow the same rule.
- **Separation of duties.** When `require_separate_approver` = 1 the creator
  can fill no slot. When 0 the creator may approve and the action is flagged
  `self_approved`.
- **Rejection.** Any rejection ends the request (status Rejected, reason
  required).
- **Snapshot.** The chain is copied onto the request at submit time. Editing
  the policy later never changes requests already in progress.
- **Edits cancel.** Editing the document (amount, lines, accounts, vendor)
  after submit cancels the request; it must be resubmitted and approved from
  step 1.
- **Posting gate.** The document can be posted or paid only when its request
  is Approved. `approved_by` / `approved_at` on the document hold the LAST
  approver and keep their CHECK (the approver is not the creator when the
  setting is on).
- **Agents.** Agents never approve (the approve permissions are in the agent
  never-list, section 8), and no step can name an agent.
- **Tables** (company database): `approval_policy`, `approval_step`,
  `approval_request` (at most one Pending request per record) and
  `approval_action` (append-only; one action per person per request). They
  replace `crm_approval_rule` / `crm_approval_instance`, which the CRM /
  project lifecycle migration drops.

---

## 6. Data scope

- **Project scope is a setting on the ROLE** (All projects, or Assigned projects only). DECIDED: Project Manager and Foreman are Assigned only; the General Manager template is All projects.
- **Project scope detail:** a role may be limited to assigned projects.
  `user_project_scope` lists the projects a user is assigned to. Foremen and
  (PROPOSED) project managers see and act only on their assigned projects;
  Admin, Controller, Accountant and Viewer see all. Scope applies to project
  lists, job-cost reports, receiving tickets, time entry and approvals, and
  is enforced in the same service checks and read views.
- **Field sensitivity:** wages and payroll need `payroll.view`; tax IDs
  `view.tax_ids`; bank details `view.bank_details`. Without them the field is
  masked in screens, reports, exports and AI reads (one shared helper).

---

## 7. Enforcement design

- A single `authorize(context, permission, project_id=None)` function in the
  service layer. Every write service and every sensitive read calls it first.
  It raises a custom exception (for example `PermissionDeniedError`) and the UI
  shows a plain message; `database.py` never renders anything.
- `context` carries `user_id`, `company_id`, `role_code`, `origin`, and for AI
  runs `agent_run_id`. It is the same context that sets `audit_context` for the
  audit triggers.
- Denied attempts on write actions are audit-logged (who, what, when), without
  logging sensitive field values.
- A static test lists every service function that writes and fails if one does
  not call `authorize`.
- Password rules and hashing stay as in CLAUDE.md (scrypt/bcrypt); user
  provisioning and profile screens already exist (`views_new_user.py`,
  `views_user_profile.py`) and gain the role/permission pickers.

---

## 8. AI Copilot

- The agent runs as the logged-in user. Read tools are filtered by that user's
  permissions and project scope; masked fields stay masked.
- The agent's tool registry never includes approve, post, void, reverse, close,
  reopen, override, release-hold, settings, role or user permissions, even for
  an Admin. These are not delegable.
- `ai.use` is required to open the Copilot; `ai.settings` to change keys,
  data-sharing and budget (Admin and Master by default).

---

## 9. Master and Admin (DECIDED model: CPA firm / multi-client)

The product serves both a single business with subsidiaries and a CPA firm with
many clients.

- **Master = the owner of the installation** (the firm, or the business owner).
  One Master per installation. Universal access: the Master can open every
  company in the installation and holds every permission in all of them.
  Creates and archives companies, creates Admins, and sets up the
  installation (licensing, backup of everything).
- **Admin = company-specific, assigned by the Master only.** An Admin has
  master-level control of its own company AND its subsidiaries, and nothing
  outside them. It can create and manage users, create and edit roles, set
  approval limits, change company settings, back up, export and restore its own
  company, and do all accounting in it. It cannot see any other company, and it
  cannot create or remove a Master or another Admin.

| | Master | Admin (own company + subsidiaries) |
|---|---|---|
| Companies | Creates, archives; opens all | Works in assigned companies; creates subsidiaries under a company it administers (it becomes Admin of the new one); cannot archive |
| Users | Creates any user; grants access to any company | Creates users for its company; assigns roles; deactivates access |
| Admin role | Assigns and removes | Cannot assign |
| Roles | Creates and edits in any company | Creates and edits in its company |
| Settings (incl. separation of duties) | Yes | Yes (logged, visible to the Master) |
| Approval limits | Sets | Sets (Admin itself unlimited) |
| Accounting, posting, approvals, period reopen | Yes, in all companies | Yes, in its companies |
| Backup / export / restore | All companies | Its companies |
| AI key and data-sharing opt-in | Yes | Yes (key stays on each computer) |
| Cross-client visibility | Everything in the installation | Nothing outside its companies |

**Subsidiaries.** Companies form a parent/child hierarchy (`company_registry`
parent link: confirm in the live schema). Access granted at a parent company
covers its subsidiaries by default, and can be narrowed per child.

**Firm staff.** The firm's staff are ordinary users with access rows (and roles)
on the clients they serve; the UI offers bulk "assign to clients". They are not
Masters. The firm's Master remains one per installation.

**Privacy between clients.** User lists, role lists and audit views are filtered
to the viewer's companies. An Admin creating a user whose email already exists
in the installation gets a neutral message ("ask your Master to grant access");
it never reveals the other account.

**Transparency and audit.**
- Master actions are logged with an actor type of Master; opening a company as
  Master writes an access event. The client's Admin can see these events, and
  cannot remove the Master's access.
- Neither Master nor Admin bypasses separation of duties (if the company has it
  on), approval limits or the audit trail.
- The last Admin of a company and the Master cannot be removed.
- Destructive actions (archive a company, restore over existing data) need a
  recent backup, a typed confirmation and are audit-logged.
- A client leaving the firm: the Admin can export its company file; the Master
  archives it. (Handoff details belong in the backup/restore design.)
- **Migrating the old role column.** `app_user.role` becomes only a Master flag
  (`is_master`), and its CHECK list is removed. Company roles live in
  `user_company_access.role_code`. The ten old values become starter templates:
  AP -> AP Clerk, AR -> AR Clerk, PM -> Project Manager, Warehouse ->
  Warehouse, Accountant -> Accountant, Admin -> Admin, HR (payroll and time),
  Sales (CRM and estimates), Marketing (campaign work), plus Viewer. Existing
  databases are rebuilt from migrations, so no data is converted.
- Sidebar visibility (`NAV_ITEMS` role tuples) is replaced by permission-based
  visibility in Phase 3.

---

## 10. Tests required

Each permission denied and allowed at the service layer; UI hiding is not
tested as a control; role change effective on the next call; per-company roles
(same user, two companies); approval limit boundary; separation of duties
blocks self-approval and the OFF setting logs and flags it; last Admin
protected; project scope hides other projects in lists, reports and receiving;
masked fields in screens, exports and AI reads; AI cannot reach approve/post
functions even for an Admin (static test on the tool registry); every write
service calls `authorize` (static test); denied attempts logged without
values; permission migration adds new permissions without removing; Master
has universal access and opening a company is logged; Admin cannot see other companies or assign the Admin role; subsidiary access inheritance; audit trail for role and access changes.

---

## 11. Placement

- Phase 2 (service layer): the permission registry, `authorize`, role tables,
  `user_company_access.role_code`, approval limits, project scope, tests.
- Phase 3 (screens): role and permission editor, user provisioning pickers,
  masked-field behavior.
- Each later module adds its permissions with its own migration.
- Migration numbers assigned in build order. A master-database migration is
  needed for `role_code`.

---

## 12. Decisions and open questions

Decided: starter templates editable; Project Managers and Foremen limited to
assigned projects, General Manager sees all (scope is a role setting);
separation of duties chosen at setup; one Master per installation with
universal access; Admin assigned by the Master only, company-scoped with
master-level control inside it and its subsidiaries.

Also decided: an Admin may create a subsidiary under a company it administers
and is automatically its Admin; access at a parent covers its subsidiaries by
default (narrowable per child); a client leaving is handled by export and
archive, not by revoking the Master.

Open:
1. Does the parent/child link already exist in `company_registry`? (report from
   the live schema)
2. Does creating a subsidiary count against the installation's licence/company
   limit (decided with licensing)?
