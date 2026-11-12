# StrataLedger (Accounting LibreBase) - Project Context for Claude Code

Read this file at the start of every session. It is the project's history,
rules, design decisions and roadmap. Update the "Status" section in section 7
at the end of each phase.

---

## 0. Design principle: graduated controls (top-level rule)

Source: docs/decisions_2026-11-11.md section 0 (wins over any design doc
until this file says otherwise).

StrataLedger defaults to QuickBooks-level flexibility for a small business.
As a company grows it can switch on stronger controls, approvals, audit
requirements and posting restrictions, without moving to another system. The
goal is a product a small business can use on day one that can become
CPA-grade and audit-ready later. It is not a NetSuite clone.

Two kinds of rule:

**Integrity rules: always on, never configurable.** They protect the books
from being wrong, not just from being uncontrolled.
- Integer cents; balanced double entry checked in the posting transaction.
- Posted records are locked; corrections are reversals or new documents.
- The audit log records every change and cannot be edited or deleted.
- Nothing posts into a closed period (closing periods is optional; a period
  that is never closed stays open).
- Sales invoices that require a registered series (Philippines add-on) stay
  gapless.
- Permissions are enforced in the service layer (`authorize`), and the AI
  never posts, approves or moves money.
- Agent-origin entries always need a human approval.
- Import-origin batches always need one human review before posting (the
  staging hold).

**Controls: configurable, OFF or permissive by default.** A company turns
them on in settings (Admin or Master; every change is audit-logged).
- Separation of duties (`require_separate_approver`, default 0).
- Approval required per document type (default: not required).
- Manual journal entries to controlled accounts (`allow_manual_control_je`,
  default 1: allowed and flagged).
- PO matching (two/three-way) and its tolerances; compliance holds.
- Period-close checklist hard blocks apply only when the company closes
  periods.
- Project scope for roles, approval limits, approval chains.
- A multi-step approval chain, or a separate approver, for imports.

**Approvals: integrity vs control.** The human approval of an agent-origin
entry and the one human review of an import-origin batch are integrity (the
staging hold). A multi-step chain or a separate approver for imports is a
control, off by default. In Phase 2.5 the test
`test_agent_and_import_entries_always_need_human_approval` is split into these
two rules (one test for Agent, one for Import).

Rule for new features: when a check could reasonably be optional, build it as
a setting with a permissive default, list it on the Company Settings
"Controls" page, and log every change to it. When unsure whether something is
integrity or control, ask.

## 0b. Design principle: ease of use (UX/UI)

The same idea as graduated controls, applied to screens: simple by default,
power one step away.
- Plain language on every screen (jargon only as a tooltip).
- Sensible defaults; a new user can finish a task without changing a setting.
- Progressive disclosure: advanced options and controls that are OFF stay
  hidden until the company turns them on (Settings > Controls).
- Presets first: common tasks and reports are one click (section 6, "Report
  presets and prompt-to-report").
- Wizards for setup and rare tasks (company creation, conversion, year-end);
  fast keyboard-friendly forms for daily entry.
- Every list is searchable and filterable; every number drills down to the
  documents behind it.
- Drafts are safe: anything not posted can be changed or deleted; posting
  shows a plain preview of the journal entry first.
- Errors say what to do next, in one sentence (no codes or stack traces).
- Screens follow docs/CLAUDE_UI.md.

---

## 1. Project vision and history

**StrataLedger** is a desktop, subscription-free accounting platform built in
Python 3 with CustomTkinter and SQLite. It is for businesses and CPAs who want
full local data ownership without recurring SaaS fees.

**Target capabilities:** multi-company management (QuickBooks Desktop style),
project costing, percentage-of-completion (POC), construction contracts and
estimates, deferred revenue, prepayments, custom multi-level dimensions, and
automated imports from third-party tools (Gusto, Rippling, Ramp).

**History:**
- The app began as a prototype UI (`app_fast.pyw` / `app_strata.pyw`) on a
  lightweight 5-table SQLite setup.
- Planning started as a LibreOffice Base idea ("Accounting LibreBase"), then
  moved to a Python/SQLite desktop app.
- The schema grew into a 60-table design (`accounting_librebase.db`).
- Current work: bring the legacy UI views and the database layer in line with
  the authoritative 60-table schema, then wire up the AI coworker.

---

## 2. Directory and file structure

Paths are defined once in `config.py` (decision P2a); never hardcode a path
anywhere else, and no machine path (such as a user profile folder) may appear
in code (`tests/test_config_paths.py` fails on one).
- `RESOURCE_DIR`: the folder the app runs from (`sys._MEIPASS` when frozen,
  else the folder of `config.py`). Read-only: migrations, fonts, templates, help.
- `DATA_DIR`: where the app writes (databases, `Companies/`, `Backups/`,
  `Logs/`, `Uploaded_Files/`). `STRATALEDGER_DATA_DIR` if set; else the repo
  folder when running from source; else `%PROGRAMDATA%\StrataLedger` when frozen.
  `BASE_PROJECT_DIR` is kept as an alias of `DATA_DIR`.

- `app_strata.pyw` - main entry point, QuickBooks-style
  "No Company Open" launcher, session state manager (`self.db` pointer), and
  master layout (Sidebar + Workspace + right-hand AI Copilot drawer).
  `Outdated/app_fast.py` is the old prototype and is not imported.
- `config.py` - theme styling (`Theme` class), `RESOURCE_DIR` / `DATA_DIR` and the paths derived from them.
- `templates/coa/` - the approved chart-of-accounts templates (`construction.csv`, `general.csv`, decision I1)
  and their README. Read through `modules/services/storage.py` and `chart_templates.py`; "Import my own CSV"
  uses the same parser (`csv_table.py`).
- `requirements.txt` - runtime packages (`customtkinter`, `tzdata`). `tzdata` is a hard requirement: if a
  company's time zone cannot be loaded, `open_company` raises `InstallationError` ("reinstall"); there is no
  fallback to the UTC date. The test environment installs it too, and the time-zone tests never skip.
- `migrations/` - the baseline schema, one file per database kind
  (`001_company.sql`, `001_master.sql`), which `database.py` runs to build
  databases at runtime. Until the first release these files are edited
  directly (section 5); after it, changes are numbered 002 and up.
- `archive/migrations_chain_v5/` - the migration chain that preceded the
  baseline (company 001-005, master 001-003). Historical, never applied (git
  tag `schema-chain-v5`).
- `accounting_librebase.db` - reference snapshot of the 60-table company
  schema (see section 5). Not read at runtime.
- `system_master.db` - global authentication and routing database
  (`app_user`, `company_registry`, `user_company_access`). Never put company
  accounting tables (`contact`, `invoice`, `journal_entry`, etc.) here.
- `Companies/` - isolated `.db` file per company/subsidiary
  (e.g. `CHRM.db`, `COMBUZZ.db`). `comp_strata.db` is an older company file
  in the root folder.
- `.db` files are not tracked by git (`.gitignore`).
- `docs/accounting_schema.txt` - planning reference for the schema (see
  section 5).
- `docs/crm_pm_design.md` - design draft for the CRM, project lifecycle,
  service cases, customer/vendor codes and throughput tracking. NOT BUILT.
  Read it before touching anything in these areas.
- `docs/inventory_fixed_assets_design.md` - design draft for inventory (lots,
  serials, employee material advances, returns), fixed assets and equipment
  charging, and controlled accounts. NOT BUILT.
- `docs/loans_design.md` - design draft for loans payable (schedules,
  current/long-term split). NOT BUILT.
- `docs/philippines_tax_design.md` - design draft for the Philippines tax
  add-on (VAT, withholding, certificates, filing tracker, e-invoicing).
  NOT BUILT; needs a Philippine tax professional's review.
- `docs/controls_audit.md` - controls and analytics audit of the schema, with
  the decisions taken and what each migration closed.
- `docs/schema_audit.md` - the first (Phase 1) schema audit.
- `docs/ai_copilot_design.md` - design draft for the AI Copilot: provider
  adapter, credentials, safety rules, settings, tools and skill packs.
  NOT BUILT.
- `docs/pay_applications_design.md` - design draft for pay applications (SOV
  progress billing) and retainage receivable. NOT BUILT.
- `docs/po_ap_matching_design.md` - design draft for purchase orders,
  subcontracts, receiving and PO-to-AP matching, with retainage payable.
  NOT BUILT.
- `docs/roles_permissions_design.md` - design draft for roles (per company,
  customizable), permissions, approval limits, separation of duties, project
  scope, and the Master / Admin model. NOT BUILT.
- Design docs are read before touching their areas. Where a design doc's
  PROPOSED migration numbers differ from section 7, section 7 wins.
- `modules/` - UI views and database helpers:
  - `database.py` - database initialization, connection helper
    (`PRAGMA foreign_keys=ON`), versioned schema migrations.
  - `views_dashboard.py` - Customers Command Center / Flight Deck.
  - `views_registry.py` - Customer Master List with live SQL search filtering.
  - `views_wizard.py` - Customer Intake & Edit form (Construction and B2B SaaS
    channels).
  - `views_billing.py` - multi-line Invoice/Bill/Credit Memo form with project
    links and dynamic dimensions.
  - `views_payroll.py` - workforce HR and time-entry logging (`time_entry`).
  - `views_new_company.py` - the four-step New Company wizard (decision S5) over
    `companies.create_company`; no SQL. Its defaults, checks and error wording are in
    `new_company_model.py` (no Tk, unit tested). It asks for a sign-in first (the launcher has no user);
    only the Master, or an Admin creating a subsidiary, gets past it.
  - `views_new_user.py` and `views_user_profile.py` - global user provisioning
    and profile management.
  - `ai_agent.py` - planned (Phase 6), provider adapter (Gemini first); see
    docs/ai_copilot_design.md.

---

## 3. Non-negotiable engineering and accounting rules

1. **Integer cents only.** All monetary amounts are `INTEGER` cents
   (`amount_cents`, `debit_cents`, `credit_cents`, `wage_cents`). Never use
   `REAL`/`FLOAT` for money. (Quantities, hours and percentages may be `REAL`.)
2. **Strict double-entry balance.** An entry cannot be posted unless it
   balances (`SUM(debit_cents) == SUM(credit_cents)`), and the posting
   function checks this in the same transaction. Unbalanced drafts may be
   saved.
3. **Multi-database isolation.** One master login (`system_master.db`) grants
   access to multiple isolated company `.db` files. All active workspace
   queries route through `parent_view.db`.
4. **Foreign keys enabled.** Every SQLite connection must execute
   `PRAGMA foreign_keys = ON;`.
5. **Separation of concerns.** `database.py` never renders Tkinter or
   CustomTkinter popups. Raise custom exceptions (e.g.
   `SchemaUpgradeBlockedError`); the UI layer catches and displays them.
6. **Security.** Hash passwords (`hashlib.scrypt` or `bcrypt`). Never commit
   plaintext credentials or hardcoded tokens.
7. **All database writes go through service functions** in one module. The UI
   and any future AI agent never run raw SQL writes.
8. **Posted records are locked.** Corrections use reversing entries, never
   edits or deletes of posted data.
9. **Back up first.** Copy a `.db` file that holds real data before any
   schema change. Until the first release the schema is one baseline and
   development databases are rebuilt from it (section 5); after the first
   release, schema changes ship as numbered, versioned migrations that bump
   `schema_version`. Never delete or rewrite a database file without asking.
10. **Every write service calls `authorize`.** The service layer enforces
    permissions; the UI only hides. Each service function that writes, or
    reads protected data, calls `authorize(context, permission, project_id)`
    first and raises a typed exception on denial. A static test fails if a
    write service does not (docs/roles_permissions_design.md section 7).
11. **Connections.** Every connection comes from `database.get_connection()`.
    Every write runs inside the service layer's write transaction, which sets
    `audit_context` (user_id, origin) before any SQL. A static test fails if
    `sqlite3.connect` appears outside `modules/database.py`, `tests/`,
    `scripts/` and `tools/`.
12. **No silent errors.** No `print()` for validation or database errors.
    Services raise typed exceptions; the UI shows a dialog; errors are also
    written to a log file whose path is defined in `config.py`.
13. **Auth.** Passwords are hashed with `hashlib.scrypt`, never stored or
    compared as plaintext. No hardcoded tokens. Opening a company checks
    `user_company_access`.
14. **Ease of use.** Every new screen follows section 0b (plain language,
    defaults, progressive disclosure, presets first, safe drafts, one-sentence
    errors) and docs/CLAUDE_UI.md. New optional checks follow section 0.
15. **Portability (hosted-ready).** Services must port to FastAPI and
    PostgreSQL without a rewrite (docs/decisions_2026-11-11.md H1-H6). In
    `modules/services/`: no UI, dialog or OS-specific imports (H1); no reading
    the system clock, `now` and `today` come from the context (H2); files go
    through `storage.py` (H3); `audit_context` is touched only in `tx.py`, and
    workflow rules live in services, not new triggers (H4); no SQLite-only SQL
    such as `date('now')`, `strftime`, `julianday`, `INSERT OR REPLACE`,
    `GROUP_CONCAT`, and PRAGMAs only in `database.py` (H5); visual values live
    in `config.Theme` (H6). `tests/test_static_portability.py` enforces H1, H2,
    H4 and H5; its allow-lists can only shrink.

---

## 4. Key schema conventions (from the live schema)

- **Contacts (`contact`):** `name`, `bir_registered_name`, `entity_type`,
  `is_customer`, `is_vendor`, `is_active`, `tax_id`, `email`, `phone`,
  `mailing_street`, `mailing_city`, `mailing_state`, `mailing_zip`.
- **Invoices (`invoice`, `invoice_line`):**
  - `invoice_type`: `'Invoice'`, `'Bill'`, `'Credit Memo'`.
  - `status`: `'Draft'`, `'Sent'`, `'Paid'`, `'Void'`.
  - `terms`: `'Due on Receipt'`, `'Net 15'`, `'Net 30'`, `'Net 60'`.
  - `invoice_line`: keyed on `line_id`, cascades on delete from `invoice_id`,
    includes `sort_order`.
- **Custom dimensions (`dimension_type`, `dimension_value`,
  `invoice_line_dimension`):**
  - `dimension_type` defines categories (Cost Center, Region, Profit Center).
  - `dimension_value` is hierarchical through `parent_value_id`; `code` is
    globally unique.
  - `invoice_line_dimension` links `line_id` to `dimension_value_id`.
- **Payroll / time (`time_entry`):** links `contact_id`, `project_id`,
  `cost_code_id` and `source_batch_id` (-> `import_batch`); stores `work_date`,
  `hours`, `wage_cents`, `burden_cents`.

---

## 5. Source of truth and reference documents

1. **The baseline files `migrations/001_company.sql` and
   `migrations/001_master.sql` are the schema source of truth** (decided after
   the 2026-11-10 schema audit, `docs/schema_audit.md`). Until the first
   release there is ONE baseline per database kind instead of a migration
   chain (decided 2026-11-11: nothing is released and no real data exists).
   Schema changes edit the baseline directly, with failing tests first, and
   development databases are rebuilt from it with
   `scripts/create_fresh_databases.py`. At the first release the baseline is
   frozen; later changes are numbered migrations 002 and up, and a released
   file is never edited. The chain that preceded the baseline is archived in
   `archive/migrations_chain_v5/` (tag `schema-chain-v5`);
   `tools/verify_baseline_squash.py` proved the baseline equal to it (zero
   differences) at the squash commit. `accounting_librebase.db` is a reference
   snapshot generated from the baseline by
   `scripts/build_reference_snapshot.py`, so the two cannot drift. It is not
   read at runtime. Never edit it by hand; regenerate it.
2. The migration runner (`database._apply_migrations`) applies all pending
   migrations in one transaction, runs `PRAGMA foreign_key_check` and
   `PRAGMA integrity_check` before commit, and on any failure rolls back,
   leaves the file unchanged and raises `SchemaUpgradeBlockedError`.
   Migration scripts must not manage transactions or `PRAGMA foreign_keys`.
   **Pre-release guard:** when it builds a database the runner stores a
   SHA-256 of the baseline text in it (table `schema_baseline`, line endings
   ignored). Opening a file whose stored hash differs or is missing, whose
   version is above the baseline's, or that has tables but no
   `schema_version` raises `SchemaUpgradeBlockedError` ("rebuild with
   scripts/create_fresh_databases.py") and leaves the file unchanged. This
   guard is pre-release only: it is replaced by versioned migrations at the
   first release.
3. `docs/accounting_schema.txt` is the planning reference. It records design
   intent, rules and open decisions from the schema planning sessions, and
   marks each rule as enforced by the schema or in the service layer. Table
   and field names there may differ from the live database (for example it
   says `batch_id` where the database uses `source_batch_id`).
4. Where the doc and the baseline schema differ, **the baseline wins**. Do
   not change either to match the other without asking. Report differences
   instead.

---

## 6. Design decisions already made

These come from the planning sessions. Check each against the live schema
before building; the database wins on naming.

**Imports (Gusto, Rippling, Ramp)**
- Imported data lands in staging tables first (`import_batch`,
  `staged_transaction`, `staged_line`). Staging is NOT part of the ledger.
- A batch posts only when every row is coded, approved by a person, and every
  bill payment is matched to its bill. Post bills first, then payments.
- `external_ref` is unique per source, so re-importing a file cannot create
  duplicates.
- `import_mapping` translates external categories, departments, jobs,
  employees and vendors into accounts, projects, cost codes and contacts.
- Payroll: prefer importing the payroll system's own journal entry as the cost
  source, with `time_entry` holding hours only (open decision, see section 9).

**Deferrals (one subledger for expense and revenue)**
- One deferral subledger with `kind` = Expense or Revenue, and
  `advance_type` = "Billed in advance" or "Paid in advance".
- Billed in advance: the bill/invoice exists first. Paid in advance: the
  payment comes first; attaching the bill later creates NO new ledger entry.
- A payment can be allocated to an invoice/bill or to a deferral, never both
  on the same allocation row.
- A schedule line is generated per period; the last period absorbs rounding.
  The subledger must tie out to the general ledger balance of the deferral
  accounts.
- Sales tax is never deferred. Invoice lines on POC or completed-contract
  projects do NOT create deferrals.

**Construction**
- Tables: estimates (versioned) and estimate lines; contracts and a schedule
  of values; change orders with change order lines; project budgets; cost
  codes with a `counts_toward_progress` flag.
- Revised contract = original contracts + approved change order revenue.
  Revised budget = original budget + approved change order cost.
- Change orders post nothing to the ledger by themselves. Approved change
  orders lock; fixes use a new change order.
- POC (cost-to-cost): percent complete = cost to date / (cost to date +
  estimated cost to complete). Earned revenue = percent x revised contract.
  Snapshots are cumulative, so mid-job changes are a catch-up in the period
  they take effect. Progress invoices post to contract revenue; the period-end
  entry adjusts to earned revenue with the offset to the underbilled /
  overbilled accounts. If estimated total cost exceeds revised contract,
  recognize the full expected loss immediately.
- Pending (unapproved) change orders: exclude pending revenue from POC; the
  project manager's estimate to complete covers pending costs.
- Revenue recognition defaults must be reviewed by a CPA before shipping.

**AI coworker (Phase 6) guardrails**
- The agent only proposes: single-record proposals open the real screen
  pre-filled and unsaved; only bulk items (receipts, CSV batches, staging
  coding) are staged through write services with origin = 'Agent', a run id
  and an agent_suggestion row. The agent's own DB connection is read-only. It
  never posts and never approves. Only a human user approves or posts.
  Every record says who made it with `origin` (Human, Agent, Import, System)
  and, for agent work, `agent_run_id`: `journal_entry.origin` exists
  (baseline; formerly migration 004); `staged_transaction.origin`, and `origin` plus
  `agent_run_id` on `audit_log` (copied from `audit_context` by the audit
  triggers), come with the AI support schema work (Phase 6).
- Keep agent suggestions separate from approved coding (a suggestions table
  with confidence, rationale, agent version and status).
- A document table stores source PDFs/receipts with a file hash so the same
  file is not processed twice.
- Run deterministic coding rules (vendor -> account) before calling the AI.
- The agent's tools are the service functions plus read-only views. Its
  database connection is read-only.
- AI is provider-neutral behind one adapter interface. v1 provider is the
  Gemini API using the customer's own key, stored only in the OS keyring. No
  consumer-account logins. Company data is sent only after an Admin opt-in and
  paid-tier confirmation. See docs/ai_copilot_design.md.

**CRM and project lifecycle (summary; full design in docs/crm_pm_design.md)**
- Internal-use CRM and project tool. Desktop version has no subscription;
  a hosted version is planned. Same schema and service layer; one database
  per company in both.
- A lead is a project from day one: one `project` record moves through one
  list of stages (Sales, signing milestone, Delivery, Closeout, Closed).
  There is no separate opportunity table.
- Signing the contract runs one service function: confirm the customer,
  assign the customer code, assign the job number, create the contract and
  original budget.
- No costs before signing (stage flag `allows_costs`). Invoices only to
  contacts that have a customer code.
- Closed projects are LOCKED and never reopen. Lost leads can be reopened.
- Repairs after closing are new service cases (`project.kind = 'Service
  case'`, `parent_project_id` = the closed job) in a separate Customer
  Support pipeline. Warranty cost is charged to the case, never to the
  closed job.
- Stage history tables are append-only. Every stage move or block change
  writes history in the same transaction, through one service function.
- All timestamps (`_at` fields) are UTC ISO 8601 text. Throughput measures
  (time in stage, conversion, aging, sales velocity, planned vs actual) are
  views over the history tables, not stored fields.
- `comment`, `attachment` and `notification` point at records by
  (record_type, record_id) and are validated in the service layer. Every
  other relationship uses a real foreign key.
- Items marked PROPOSED in docs/crm_pm_design.md are not decided. Do not
  build them as final.

**Customer codes**
- Automatic only; no manual entry or editing.
- customer_code = first 2 letters of the customer name (uppercase, accents
  removed, skip a leading The/A/An, ignore digits and punctuation, pad with
  X) + seq, zero-padded to at least 4 digits (AC0001). The number may grow
  beyond 4 digits. Sort by seq, not by the code text.
- Skip a leading The/A/An only when the next word starts with a letter:
  "The Home Depot" -> HO, "A Better Roof" -> BE, "A & B Plumbing" -> AB,
  "The 3M Company" -> TH, "The" alone -> TH, "A" alone -> AX. A name with no
  Latin letters (Chinese, Cyrillic, Greek, digits only) gets the prefix XX
  (DECIDED 2026-11-11; no transliteration). Built in
  `modules/services/contacts.py` (`code_prefix`, `format_code`).
- The number comes from the database: insert a row into customer_number
  (seq INTEGER PRIMARY KEY AUTOINCREMENT, contact_id UNIQUE) in the same
  transaction that sets the code, and use seq. Keep a unique index on
  customer_code as a second safeguard. Never compute the number with MAX+1.
- Assigned once, when a contact first becomes a customer: saving a new
  customer in the Create New Customer wizard, or signing a contract for a
  prospect. Both call the same service function. The UI never builds codes.
- Never changed and never reused. A customer with a code can only be made
  inactive, never deleted. A merged customer's code stays reserved.
- A contact with is_customer = 1 must have a customer_code (CHECK, added
  after the backfill).
- Run a duplicate check (name, tax_id, email) before creating a customer.
- Job number = customer_code + '-' + project_code, stored in
  project.project_number (AC0001-001). A service case's project_code is the
  parent job's project_code + '-S' + a 2-digit sequence (AC0001-001-S01).

**Vendor codes (DECIDED 2026-11-11: V prefix)**
- Same method with a separate vendor_number sequence table.
- vendor_code = 'V' + 2-letter prefix + seq, 4+ digits (VAC0001). Customer
  codes never match this pattern, so the formats cannot collide.
- Assigned once, when a contact first becomes a vendor. Imports (Ramp, etc.)
  never create vendors directly: the staging approval step matches existing
  vendors (name, tax_id, email) and creates a new one only on approval.
- A contact can hold both a customer_code and a vendor_code.

**Schema cleanup (DECIDED 2026-11-11)**
- `change_order` / `change_order_line` are the canonical change-order tables.
  Nothing reads `crm_opportunity`, `crm_change_order`, `crm_change_line`,
  `crm_activity_stream`, `crm_stage_history`, `crm_pipeline` and `crm_stage`
  except foreign keys among themselves, so they were removed from the
  baseline in Phase 2.2 cleanup commits (done 2026-11-11, one commit each):
  `estimate.source_opportunity_id` (redundant with `estimate.project_id`,
  which the CRM design always sets), then the nine `crm_*` tables, then
  `purchase_order_subcontract` (replaced by the PO design). Their roles are
  taken by `project` (a lead is a project), `change_order`,
  `change_order_line`, `activity`, `project_stage_history`, `pipeline` and
  `pipeline_stage` (docs/crm_pm_design.md section 4).
- `crm_approval_rule` and `crm_approval_instance` are replaced by the
  approval tables (`approval_policy`, `approval_step`, `approval_request`,
  `approval_action`, in the baseline; docs/roles_permissions_design.md
  section 5A) and were removed in the same cleanups.
- company_profile was removed from the baseline in 2.4 Part 2 (the New Company screen no longer writes it).
- `app_user.role` stays until Phase 3 rewrites its readers (login, `NAV_ITEMS`,
  `views_user_profile.py`, `views_new_user.py`); then it is removed from the
  baseline together with the `role = 'Master'` half of the one-Master
  triggers.
- `saas_subscription` stays until its relationship to the deferral subledger
  is decided (that part of controls audit decision 4 remains open).

**Timestamps**
- Service timestamps are UTC ISO 8601 with an explicit offset, written by one
  helper (`modules/services/clock.utc_now_iso()`). Columns that default to
  CURRENT_TIMESTAMP (`audit_log.logged_at`, etc.) use SQLite's format; this is
  a known inconsistency, not fixed now.

**Purchase orders and PO-to-AP matching (summary; docs/po_ap_matching_design.md)**
- Commitments (approved POs and subcontracts) post nothing to the ledger;
  they feed job cost and the estimate to complete.
- Receiving: warehouse staff receive stock (Dr Inventory / Cr Accrued
  Receipts); the job is costed at the pull ticket. Direct-to-job deliveries
  need a delivery ticket, confirmed by the foreman, before the cost is job
  costed (Dr Job cost / Cr Accrued Receipts); the project manager may
  approve a bill without one, costing it at the bill. Receiving rights are
  permissions in the roles design, not hardcoded roles.
- Matching: two-way (PO + bill) for services and subcontracts, three-way
  (PO + receipt + bill) for materials. Compare before tax is ON by default;
  tax is checked separately against the expected rate. Price and amount
  tolerance default 15%, set in `policy_rule` per company, vendor or PO;
  quantity over received/ordered defaults to 0%. Exceptions block approval
  and payment until resolved; overrides need a reason and a role.
- A clerk enters the bill and the project manager approves it; only a person
  approves a bill, a match override or a PO.
- Compliance hold (v1): a vendor missing a required document (insurance
  certificate, lien waiver) puts its bills on PAYMENT hold only, never
  approval hold; cleared or overridden by a role, logged.
- Retainage payable mirrors retainage receivable: a controlled account,
  released only through a release document.

**Report presets and prompt-to-report (DECIDED 2026-11-11, decisions section G)**
- G1 A built-in library of report presets (P&L this month vs last month, P&L
  year to date vs last year, balance sheet at period end, cash flow, trial
  balance, AR and AP aging, sales tax liability, 1099 summary, job cost by
  project, WIP schedule in v1.1). A preset is a saved report definition:
  report type, date range in words ("last fiscal quarter", "year to date"),
  comparison, report basis (A1), filters (dimensions, projects, accounts) and
  layout.
- G2 Users save their own presets from any report ("Save as preset"), private
  or shared with the company. Presets store no numbers, only the definition,
  so they always run on current data.
- G3 Every preset has a plain-language prompt ("Show profit and loss for last
  quarter compared to the same quarter last year"), shown as a button and
  usable as a template.
- G4 Prompt-to-report with the AI (v1.2, with the Copilot): the AI chooses
  the preset and fills its parameters as structured data; the app shows "Run
  P&L, Jan-Mar 2027 vs Jan-Mar 2026, GAAP basis?" and runs the report locally
  on confirm. Running a report sends no ledger numbers to the AI provider.
  Asking the AI to explain or summarize a report's numbers is a separate step
  that requires the company's data-sharing opt-in.
- G5 Without the AI (v1.0, or no API key): the same prompt box matches typed
  words to presets locally (keyword search, no network), so presets and the
  prompt box work offline and with no subscription.
- G6 Date words are resolved by the app from the company's fiscal calendar,
  never by the AI, so results match the company's periods.
- G7 Reports run under the user's own permissions (`report.financial`,
  `report.job_cost`; masked fields stay masked). The AI's allow-list includes
  report codes except `report.export`, so it can run but never export a
  report.
- Presets and the prompt box follow section 0b.

**Fresh start**
- The real databases (`system_master.db`, `comp_strata.db`, `Companies/*.db`)
  hold test data only and were built by the old chain (or are legacy
  files). They are rebuilt fresh by `scripts/create_fresh_databases.py`
  (dry-run only until approved), never upgraded. Until they are rebuilt the
  baseline guard (section 5) blocks them, so the app cannot open a stale
  file by accident. The script builds the master only until the Phase 2.4
  company creation service exists. The baseline is never applied to a real
  file without explicit approval.

**Country add-ons**
- Country-specific rules live in `addons/<key>/` (first one: `addons/ph_tax/`,
  design in docs/philippines_tax_design.md section 11).
- Core never imports an add-on. Core exposes hook points; an enabled add-on
  registers handlers for them. A disabled add-on registers nothing, so core
  behaves as if it did not exist.
- Add-on tables are prefixed (`ph_`) and keyed to core ids. An add-on never
  alters core tables.
- Add-on migrations have their own numbering (`ph_001`, ...) and are versioned
  in `addon_schema_version`. They are not part of the core series.
- Disabling an add-on hides its screens and stops its hooks. It never drops
  its tables or data, and posted documents stay locked.
- `company_addon` records which add-ons a company has enabled.

---

## 7. Roadmap and status

**Release plan (DECIDED 2026-11-11; docs/decisions_2026-11-11.md E1):**
v1.0 core accounting, then v1.1 construction, then v1.2 AI Copilot.
- **v1.0:** core accounting (Phases 2 to 5 below), plus fixed assets, loans and
  vendor refunds. Report presets with offline keyword matching (section 6).
- **v1.1:** construction (decisions section D, pay applications, projects,
  POC, T&M billing), plus POs and PO-to-AP matching and all inventory
  (construction-optimized).
- **v1.2:** AI Copilot (Phase 6), including AI-picked report presets.
- **Philippines add-on:** a separate add-on after v1.0 (`addons/ph_tax/`),
  pending a Philippine tax professional's review. Not part of any core release.

**Phases (current plan):**
- **Phase 1 - Database rebuild:** rebuild `database.py` from
  `accounting_librebase.db` with versioned `schema_version` migrations and safe
  handling of legacy empty 5-table company files. (Historical: on 2026-11-11
  the chain and the legacy handling were replaced by the pre-release baseline,
  section 5.)
- **Phase 2 - Service layer:** one connection helper that always enables
  foreign keys (built on `database.get_connection`), and service functions
  for every database write. The views stop running raw SQL writes. Built one
  step per prompt:
  - **2.1 Foundation:** `modules/services/` package; typed exceptions;
    `ServiceContext`; `write_transaction()` that sets `audit_context`; error
    log path in config; static tests for rule 11 and rule 12 (allow-list of
    current offenders, which shrinks to zero by end of Phase 3).
  - **2.2 Permissions core:** permission code registry (Python constant, the
    list in roles_permissions_design.md section 3), `authorize()`,
    `PermissionDeniedError`, denied-attempt audit, and the static test for
    rule 10. Done in 2.2b: `modules/services/permissions.py` (registry,
    `AGENT_ALLOWED` allow-list, `PROJECT_SCOPED`, document-type permission
    maps), `authz.py` (`authorize`, `check_approval_limit`,
    `record_company_open`), `approvals.py` (approval chains, the single
    `check_separate_approver` helper, policies and limits), `clock.py`. The roles and permissions tables (company and master) are in the
    baseline (done in 2.2a).
  - **2.3 Auth service (done):** scrypt hash/verify/change password, first Master
    creation, remove the hardcoded token, open-company service checking
    `user_company_access`.
  - **2.4 Company creation and periods**, in two commits:
    - **2.4a (done):** `companies.create_company` (all-or-nothing build, S1-S8: code, `company_settings`,
      chart from `templates/coa/` or the parent or the user's own CSV, system account pointers, Admin grant),
      `archive_company` / `restore_company` / `export_company` / `list_companies` (S9), `accounts.py` (C1-C3),
      `company_settings.py` (Controls page, per-document "requires approval" default off, system accounts),
      `bank_accounts.py` (C4, masked), `storage.py`, `csv_table.py`, `chart_templates.py`, `sequences.py`
      (voucher numbers), `ServiceContext.now` / `today`, and the H2 / H5 follow-through. The 11 starter roles
      (docs/role_templates.md, approved; code in `role_templates.py`, checked against the doc by a test) are
      seeded in every company built from a template or CSV; a copied subsidiary gets its parent's roles. No
      approval limits are seeded.
    - **2.4b (done):** `modules/services/periods.py`. `fiscal_year` (named by end year, S2) with 12 monthly
      periods plus 13 and 14 dated the year's last day (hidden unless the Adjustment periods control is on, S4);
      first year and the next at creation, later years 60 days ahead from `open_company` (S3);
      `resolve_entry_period` (ordinary entries take the month period, period 12 on the year's last day; 13/14
      only when passed explicitly, dated the year end, with the control on) and `period_ids_for_basis`
      (pre-adjustment 1-12, GAAP 1-13, tax 1-14); close checks as warnings or blocks (L2) with
      `period_close_check`; `reopen_period` (confirm + reason, L7); `set_books_closed_through` (forward closes,
      backward reopens with confirm + reason, dry run); `close_year` (B1, no closing entries) and `reopen_year`
      (year name typed exactly); `check_entry_date` (L6); `change_fiscal_year_start` (only with no entries).
      Every close and reopen writes the append-only `period_status_history`. Archive and restore need the
      company code typed (0b amended). The 2.5 ledger service must call `resolve_entry_period`.
  - **2.5 Ledger services:** the controls-audit rules; every test in
    tests/test_service_rules_pending.py flips from xfail to pass (strict
    xfail means each one must be un-marked as it is implemented).
  - **2.6 Customer and vendor codes (done):** `customer_number` and
    `vendor_number`, `contact.customer_code` / `vendor_code` (unique, CHECKed,
    immutable, coded contacts cannot be deleted), `modules/services/contacts.py`
    (create / update / deactivate, make_customer, make_vendor, find_duplicates
    with masked tax IDs). `contact.is_customer` now defaults to 0. Job numbers
    come with the CRM work.
  - **2.7 Hooks and add-ons:** hook registry, add-on registry, add-on
    migration runner (`addon_schema_version`).

  Scope of the phase (kept from the earlier plan):
  - hook registry, add-on registry and add-on migration runner;
  - the service-layer rules from the controls audit: postable and active
    accounts, reversal checks, payment over-allocation, period reopening
    with a logged reason, blocking manual entries to controlled accounts
    (decision 5), manual-entry approval (decision 6), invoice numbering from
    `invoice_series`, and setting `period_id` from `entry_date`. Their tests
    are marked expected-failure until then.
  - Roles and permissions (docs/roles_permissions_design.md): the permission
    registry, `authorize()`, per-company role tables, approval limits,
    project scope, and the company hierarchy with access inheritance from a
    parent company to its subsidiaries.
- **Phase 3 - Screen alignment:** align `views_wizard.py`,
  `views_registry.py`, `views_billing.py` and `views_payroll.py` to the
  authoritative schema and dynamic dimensions, calling the service layer.
  The app must ask before upgrading a database on launch.
  Roles: the role checklist editor (by module, with quick settings), the
  role and permission pickers in user provisioning, masked sensitive fields
  (wages, tax IDs, bank details), and bulk "assign to clients".
- **Phase 4 - Double-entry posting:** posting an invoice with status `'Sent'`
  generates balanced `journal_entry` and `journal_line` rows in the same
  transaction (`invoice.entry_id`).
- **Phase 5 - Cleanup and security:** fix package `__init__.py` imports and
  remove empty scripts. (Password hashing and removing the hardcoded token were
  done in Phase 2.3.)
- **Phase 6 - AI coworker (release v1.2):** wire the right-hand Copilot drawer to the
  provider adapter (Gemini first) (`modules/ai_agent.py`) to ingest PDFs/POs/receipts,
  suggest GL accounts and dimensions from company history, populate UI forms
  via structured JSON, and run pre-posting audit checks with human-in-the-loop
  approval. All AI work is built here, as one stretch, after the core
  services it reads from exist (docs/ai_copilot_design.md section 7):
  - Step 1: the AI support migration at the start of Phase 6; the AI
    credentials and connection service (OS keyring), the provider interface
    and the Gemini adapter, `ai_usage`, the data-sharing settings and
    `agent_suggestion`.
  - Step 2: `modules/views_ai_settings.py` (Admin/Master), the Copilot gear
    trigger, the "Agent proposals" queue screen and the Copilot drawer
    behavior from docs/CLAUDE_UI.md.
  - Step 3: the orchestrator (tool loop, skill router, audit, spend cap), then
    each skill pack as its domain's service is built and tested.
  - Until then the Copilot drawer is a visible placeholder and uses no
    network.

**Backlog (not yet scheduled; proposed order):**
1. Deferral subledger: schedule generation, period-end posting, tie-out.
2. Projects: cost codes, estimates, contracts, schedule of values, change
   orders, budgets.
3. POC snapshots and the adjusting entry.
4. Ramp staging, approval and posting; then payroll imports.
5. Pay applications (progress billing and retainage) and subcontract/purchase
   order commitments. Pay applications and retainage designed
   (docs/pay_applications_design.md); subcontracts and POs designed
   (docs/po_ap_matching_design.md).
6. Reports: trial balance, job cost, WIP schedule, deferral rollforward,
   AR/AP aging.
7. Backup/export, installer, licensing.
8. Customer code sequence table, customer_code field and the assignment
   service function (proposed for Phase 2); wizard shows the code
   (proposed for Phase 3).
9. After Phase 4, unscheduled: (a) pipeline, stages, stage history and the
   signing function; (b) CRM basics and collaboration; (c) service cases and
   the Customer Support pipeline; (d) throughput and profit views.
See docs/crm_pm_design.md section 11.
10. Philippines tax module (VAT, withholding, certificates, filing tracker,
    e-invoicing) as the `ph_tax` add-on, a separate add-on after v1.0: designed, not built. Needs a
    Philippine tax professional's review before it ships.

**Schema plan** (each change with failing tests first). Until the first
release there is one baseline per database kind (section 5), so planned
schema work is named, not numbered, and edits the baseline directly.
- Baseline v1 already contains: the base schema and ledger integrity
  (formerly migrations 001-003), the High controls from the controls audit
  (formerly 004: periods, posting numbers and approvals, invoice series,
  controlled-account types, ledger keys, add-on tables), and roles and
  permissions (Phase 2.2a): `permission` (the code registry), `role`,
  `role_permission`, `approval_limit`, `user_project_scope`, `access_event`,
  the approval chain tables (`approval_policy`, `approval_step`,
  `approval_request`, `approval_action`) and
  `company_settings.require_separate_approver`. Master side: `app_user.is_master`
  (one Master per installation, universal access), the `app_user.role` CHECK
  dropped (the column stays until Phase 3), and `user_company_access.role_code`
  (text, no cross-file FK) plus `access_mode` (Grant or Deny). Viewer is a
  starter role template, not a CHECK value.
  `company_registry.parent_company_id` already exists (self-referencing FK),
  so no new hierarchy column is needed.
Planned schema work, in build order (names only):
- Customer numbers (Phase 2.6): `customer_number`, `customer_code`.
- CRM / project lifecycle (docs/crm_pm_design.md), including the project
  stage flags `allows_costs` and `allows_billing` (pay applications,
  docs/pay_applications_design.md controls rule 5). The old `crm_*` tables are
  already gone (section 6 cleanup), so this work only adds.
  Pay applications (docs/pay_applications_design.md section 8):
  `progress_billing_line`, `retainage_release`,
  `cost_code.counts_toward_progress`, the FK from
  `contract_line.change_order_id` to `change_order`, and a retainage
  receivable account in `company_settings`.
  `account.control_type`: `Retainage` is split into `Retainage receivable`
  and `Retainage payable` in the CHECK (no data mapping before release); a
  test checks that every foreign key into `account` survives.
  (Done in 2.4a: the CHECK is now AR, AP, Retainage receivable, Retainage payable, Sales tax payable, Use tax
  payable, Undeposited funds, GRNI, Inventory, Fixed assets, Loans, Deferral, Over/under billing, Employee advance,
  Employee material advance. The old Fixed asset cost / Accumulated depreciation / Depreciation expense / Equipment
  cost recovery and Loan principal / Loan current portion values are now `Fixed assets` and `Loans`; the
  fixed-asset and loan design docs are updated when those steps are built.)
- Ledger line keys and controlled accounts.
- Inventory (v1.1).
- PO / subcontract / receiving / matching (docs/po_ap_matching_design.md; v1.1):
  after inventory. `purchase_order`, `purchase_order_line`,
  `purchase_order_change`, `goods_receipt`, `bill_match`, subcontract
  billing; controlled account type `Accrued receipts (GRNI)` (the `Retainage
  payable` type comes from the CRM / project lifecycle work).
- Fixed assets (v1.0).
- Vendor refunds (v1.0).
- Loans (v1.0).
- AI support, built at the start of Phase 6: agent_run,
  agent_suggestion, ai_usage, price table, AI settings in company_settings,
  staged_transaction.origin, and `origin` plus `agent_run_id` on `audit_log`
  and `audit_context` (docs/ai_copilot_design.md sections 2C and 7).
- The Philippines add-on is not in the core schema; its migrations are
  numbered `ph_001`, `ph_002`, ...
- At the first release the baseline is frozen and the pre-release hash guard
  is replaced by versioned migrations (002 and up).

**Status (update after each phase):**
- As of 2026-11-10: Phase 1 ledger integrity fixes done on branch
  `phase1-ledger-integrity`: atomic migration runner and migration 002
  (company + master) fixing audit findings F1-F8, with tests. Verified on
  copies of every real database; **not yet applied to the real files**
  (pending approval). Open: canonical subscription table (audit decision 4;
  the change-order table was decided on 2026-11-11, see section 6 "Schema
  cleanup"). Next: Phase 2 (service layer).
- 2026-11-10: CRM / project lifecycle design written
  (docs/crm_pm_design.md). No schema or code changes.
- 2026-11-10: controls audit (`docs/controls_audit.md`). Migration 003
  (critical controls; decisions 1 and 2: void = reversing entry,
  'Credit Memo', positive amounts) done on the same branch, verified on
  copies, not applied to the real company files. `system_master.db` was
  upgraded to version 2 at 22:16, most likely by an app launch (backups in
  `Backups/`); it carries one stray trigger from a runner race, since fixed.
  Next: migration 004 (High fixes, decisions 3-7).
- 2026-11-10: fresh-start decision (real databases will be rebuilt, not
  upgraded); add-on rules and the core migration plan recorded; inventory,
  fixed assets, loans and Philippines tax design docs added.
- 2026-11-10: migration 004 (High controls, decisions 3-7) done on the same
  branch and verified on copies; nothing applied to the real files.
  Service-layer rules from the controls audit have strict expected-failure
  tests (tests/test_service_rules_pending.py) until Phase 2.
- 2026-11-11: Phase 1 closed on `phase1-ledger-integrity` (30 commits ahead
  of `master`, nothing behind; merge pending approval, fast-forward).
  `scripts/create_fresh_databases.py` added: dry run by default, `--apply`
  moves the existing `system_master.db` to `Backups/YYYYMMDD-HHMMSS/` and
  builds a fresh one from the migrations; master only, no users, company
  files untouched and not registered. Two real files were upgraded by app
  launches during Phase 1 (`system_master.db` to version 2, `COMBUZZ.db` to
  version 4, both backed up by the runner); the fresh start supersedes them.
  Next: merge, then Phase 2 (service layer).
- 2026-11-11: Phase 1 merged to master (fast-forward); Phase 2 started on
  `phase2-service-layer`.
- 2026-11-11: Phase 2.1 (service foundation) and 2.2a (roles, permissions,
  approval limits and approval chains in the company schema; `is_master` and
  `access_mode` in the master schema) done. Same day, before any release, the
  migration chain was squashed into baseline v1 per database kind: tag
  `schema-chain-v5` and `archive/migrations_chain_v5/` keep the chain,
  `tools/verify_baseline_squash.py` showed zero differences, the baseline hash
  guard was added, and the legacy 5-table handling and upgrade-path tests were
  removed. The unused `crm_*` tables, `estimate.source_opportunity_id` and
  `purchase_order_subcontract` were then removed from the baseline.
- 2026-11-11: Phase 2.2b done: `authorize()` with the decided order (agent
  allow-list first, fresh master and company reads on every call, subsidiary
  inheritance with Deny narrowing, project scope), denials logged to
  `access_event` in their own transaction, approval chains (5A), and the rule-10
  static test. `ServiceContext` no longer carries a role. New approve
  permissions `je.approve`, `payment.approve`, `asset.approve`,
  `contract.approve`; `approval_request` gained `created_by` and `project_id`.
  Next: 2.3 (auth service).
- 2026-11-11: Phase 2.3 done: `passwords.py` (scrypt, per-user salt, one
  self-describing string, constant-time compare, 12-character minimum),
  `auth.py` (first Master with a one-time recovery code, login with per-username
  throttling, change password, Master recovery, must-change after a reset),
  `users.py` (create, deactivate, reset password, grant / set role / deny
  access, Master-only Admin role, last-Admin protection, privilege ceiling,
  neutral duplicate-email message), `companies.open_company` (path resolved
  under BASE_PROJECT_DIR, baseline guard, Master open logged). `authorize()`
  checks the context's file against the registry and refuses a must-change
  user. Master baseline: `audit_context`, audit triggers on `app_user` (never
  `password_hash`), `user_company_access` and `company_registry`,
  `login_throttle`, `auth_event`, `master_recovery`,
  `app_user.must_change_password`. Company baseline:
  `require_separate_approver` defaults to 0 (decided). Login, user creation and
  password change screens call the services; the hardcoded token and the
  plaintext login are gone. Next: 2.4 (company creation and periods).
- 2026-11-11: Phase 2.6 done (customer and vendor codes; built before 2.4).
  Baseline: `customer_number` / `vendor_number`, `contact.customer_code` and
  `vendor_code` with partial unique indexes, CHECKs (a customer or vendor must
  have its code), a trigger that blocks changing a set code, a trigger that
  blocks deleting a coded contact, and `is_customer DEFAULT 0`.
  `modules/services/contacts.py` added with 73 tests. Next: 2.4.
- 2026-11-11: Portability rules (decisions H1-H6) and static tests; private GitHub remote with fresh history;
  `config.RESOURCE_DIR` / `DATA_DIR` (P2a).
- 2026-11-12: Phase 2.4a done (see the roadmap entry for 2.4). Baseline additions: `account.normal_balance`,
  `subtype`, `is_tax_strategy_only`, the new `control_type` list; `company_settings` setup facts, controls and 27
  system account pointers; `document_approval_setting`, `voucher_sequence`, `bank_account`; permissions
  `company.create` and `year.reopen`; the self-approval trigger on `journal_entry` (only when
  `require_separate_approver = 1`); master `company_registry.is_archived` and an immutable company code.
  Decision C3 changed one old rule: an account number may change after posting (logged, Admin); type, parent,
  control type and normal balance still lock. Next: 2.4b, then 2.5.
- 2026-11-12: `tzdata` made a hard requirement (no UTC fallback); starter roles seeded from the approved
  docs/role_templates.md; decision L7 amended (`year.reopen` for Admin and Controller, typed year name).
- 2026-11-12: Phase 2.4b done (fiscal years and periods; see the roadmap entry). Baseline: `fiscal_year`,
  `fiscal_period.fiscal_year_id` / `period_number` / `is_adjustment_period`, `period_status_history`,
  `period_close_check`; the contiguity and delete triggers apply to month periods only, periods 13 and 14 must
  be dated the year end, the posting trigger judges an entry in 13 or 14 by its own period, and a period of a
  closed year cannot be reopened. Warehouse gained `receiving.stock` and Project Manager `project.manage`.
  Next: 2.5 (ledger services).
- 2026-11-12: 2.4b fixes (moving Books closed through back reopens only the months between the two dates;
  year close runs the close checks on periods 13 and 14). Phase 2.4 Part 2: the New Company screen
  (`views_new_company.py` + `new_company_model.py`) calls `companies.create_company` (with the
  new `companies.creation_options` and `check_company_code`); `company_profile` dropped; `create_fresh_databases.py --sample-company CODE`; `Theme.radius_lg` and `Theme.warning_glow` added.
  Next: 2.5 (ledger services).

**Known issues (code as it is today; fixed in the phase named):**
- H2 allow-list (`tests/test_static_portability.py`): only `auth._now()` still reads the clock. It stays on
  purpose until the auth functions take `now` as an argument, because throttle and recovery run before any
  context exists. `auth.login`, `companies.open_company` and `ServiceContext.__post_init__` are context builders
  and are exempt.
- `modules/views_wizard.py` inserts contacts with raw SQL and `is_customer = 1`
  but no `customer_code`, so the 2.6 CHECK rejects it. Phase 3 rewrites that
  screen to call `contacts.create_contact` (allow-listed under rule 11 until
  then).
- A fresh `system_master.db` has no users and no company_registry rows: the
  first Master is created by `scripts/create_fresh_databases.py --apply` (asked
  in the terminal) and companies are created again through the New Company
  screen or `scripts/create_fresh_databases.py --sample-company CODE --apply` (a
  construction-template test company made with the existing Master; it does not
  rebuild the master).
- `modules/ui_components.py` was never imported by the app before 2.4 Part 2 and had two missing tokens
  (`Theme.warning_glow` and `Theme.radius_lg`, now added) plus `Theme.create_scrollbar`, which still does not
  exist (used by `DataTable`), and hardcoded hex colours in the modal's badge styles. Phase 3 fixes them when the
  other screens adopt the shared components.
- The tests share one hidden Tk window (`tk_app` in `tests/conftest.py`): several Tk roots in one process
  intermittently fail on Windows.
- `users.create_user` copies the role code into the legacy free-text
  `app_user.role`, which only the sidebar reads; `app_user.role` and the
  `role = 'Master'` half of the one-Master triggers are removed from the
  baseline in Phase 3. The user profile screen still saves name and email with
  raw SQL until Phase 3 (the password part calls `auth.change_password`).
- Existing development databases (`system_master.db` at schema version 2,
  `Companies/*.db`, `comp_strata.db`) were built by the old chain or are
  legacy files. The baseline guard blocks them until they are rebuilt with
  `scripts/create_fresh_databases.py`, which builds the master only until the
  Phase 2.4 company creation service exists, so the app cannot open a company
  until then.
- The sidebar's `NAV_ITEMS` role tuples (`app_strata.pyw`) hide items by role
  name. Replaced by permission-based visibility in Phase 3; the service layer
  enforces and the UI only hides (rule 10).

---

## 8. Working agreement

- Work only on the phase or task named. Do not touch other areas.
- Start in plan mode: list the files you will change and why.
- Show diffs. Write tests for every rule you enforce, run them, and show the
  results.
- Commit at the end of each phase with a clear message.
- The git repo has one remote, `origin`, a private GitHub repository
  (`markalonmusic-jpg/StrataLedger`). Push `main` to it after each commit. The
  history was started fresh at the baseline commit, so it holds no earlier
  token or password; the old repo is kept as a local archive and is never
  pushed. Never commit `.db` files, credentials or tokens, and never
  force-push without asking.
- Back up `.db` files before any schema change; git does not track them.
- Only one tool edits the files at a time (Claude Code or GitHub Copilot).
  Commit and push between handoffs, and pull before starting.
- Finish every task with a summary: files changed, tests run, anything
  uncertain.
- Planning and review happen in the Claude chat; this tool performs the tasks
  from the prompts it is given.

---

## 9. Open decisions and notes for review

1. Payroll posting: import the payroll system's own journal (recommended) vs.
   reclass from a payroll clearing account. Also whether payroll imports get
   the same hold-and-approve step as Ramp.
2. Period-end accrual for labor worked but not yet in a payroll run.
3. A bill whose amount differs from its advance payment: flag for review
   (current plan) vs. post the difference to a variance account after
   approval.
4. ANSWERED BY THE BASELINE. Cross-database references: `app_user` lives in `system_master.db`, and
   SQLite cannot enforce foreign keys across database files. Fields like
   `created_by` and `approved_by` in a company database should store the master
   `user_id` as a plain integer (no FK). Confirm how the live schema handles
   this.
   Answer: the baseline stores `created_by`, `approved_by` and `audit_log.user_id`
   as plain INTEGER with no FK in the company file (only the master's own
   `audit_log` references `app_user`).
5. ANSWERED BY THE BASELINE. The planning doc places `app_user` and `audit_log` in the company database;
   the architecture places `app_user` in `system_master.db`. The architecture
   wins; reconcile during the audit.
   Answer: `app_user` exists only in `001_master.sql`; each company file has its
   own `audit_log`, and the master has a separate one for master-level events.
6. RESOLVED for desktop: customers bring their own key (v1 provider Gemini,
   key in the OS keyring; see docs/ai_copilot_design.md). Was: whether
   customers bring their own Claude API key or the product offers a local
   model (privacy and cost).
7. CRM / project design open questions: see docs/crm_pm_design.md section
   12 (vendor code V prefix, optional case fields, linear stages, warranty
   length, pausing cases, prospect in the wizard, closing checklist, desktop
   to hosted sync).
