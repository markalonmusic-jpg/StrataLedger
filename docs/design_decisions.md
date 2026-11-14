# Design decisions already made

Moved unchanged from CLAUDE.md (sections 0, 0b and 6) on 2026-11-12. CLAUDE.md keeps the short form of the
two principles; this file is their full text plus every decision by topic. Check each decision against the
baseline before building; the database wins on naming. docs/decisions_2026-11-11.md holds the owner's
decisions by code and wins over this file.

## Principle: graduated controls (CLAUDE.md section 0)

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

## Principle: ease of use (CLAUDE.md section 0b)

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

## Decisions by topic (CLAUDE.md section 6)

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
- The agent's tools are the service functions plus read-only views. Its own database connection is read-only
  (planned for Phase 6, docs/ai_copilot_design.md section 2 rule 1): every write it causes is a staged row made
  by a write service with origin Agent. No agent code exists today; what is built is the `AGENT_ALLOWED`
  allow-list that `authorize` applies to Agent-origin contexts (`permissions.py`, `authz.py`) and the read-only
  `tx.read_connection` (`mode=ro`) that services use for reads.
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
  helper (`modules/services/clock.utc_now_iso()`; `auth._now()` is the one
  exception, see Known issues). Columns that default to
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
- The development databases (`system_master.db`, `Companies/*.db`) hold test
  data only. They are rebuilt, never upgraded: the master by the first-run
  screen or `scripts/create_fresh_databases.py` (dry run by default), a
  company by the New Company screen or `--sample-company CODE --apply`. A
  file built from an older baseline is blocked by the baseline guard
  (section 5), so the app cannot open a stale file by accident. The baseline
  is never applied to a real file without explicit approval.

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

**Cash basis and the cash flow statement (DECIDED 2026-11-13, decisions CB1, CF1)**
- The books are always accrual. Cash basis is a report view: an Accrual / Cash switch on every financial
  report, combinable with the A1 basis, with a company default; every report and export names both bases.
- Cash view: invoice and bill amounts are recognized when payments are applied, prorated across lines by the
  paid share (jobs and dimensions stay right); unpaid AR and AP drop out; card purchases are paid on the card
  date; sales tax follows the paid share. Non-cash entries (depreciation, POC, accrued payroll, deferral and
  prepaid amortization, auto-reversing accruals and their reversals) are removed. Prepaids are expense when
  paid; deferred revenue is revenue when received; customer deposits stay a liability until applied; fixed
  assets stay at cost; manual AR/AP entries stay in and are flagged; retainage drops out until paid.
- Cash flow statement (CF1): direct method, management view. Operating receipts and payments by category,
  totalling to cash-basis net income (check line); investing; financing; other balance-sheet cash movements;
  beginning plus change equals ending cash (bank, petty cash, undeposited funds; transfers between them
  excluded). Every account has a cash flow category defaulted from its type and control type, changeable with
  an audit entry. The tie-out is checked, never forced: an Unclassified line with drill-down, and a non-zero
  Unclassified line is a close warning. Lines drill down; Excel export (docs/export_design.md); period
  comparison. A GAAP indirect-method statement is a possible later report.

**Job-driven dimensions (DECIDED 2026-11-13, decision JD1)**
- A line with a job takes the dimensions the job defines and they cannot be edited on the line; types the job
  does not define stay editable; a line with no job is fully editable. No override: change the job's settings
  or take the job off the line (the previous values stay as a starting point).
- The job is per line; a document's default job fills new lines.
- Drafts follow later changes to the job's dimensions; sent and posted documents keep what they were posted
  with.
- One shared service function resolves a line's dimensions for invoices, bills, journal entry lines and time
  entries; screens only show its result.
- "Require dimensions on lines without a job" is a future control, off by default.

