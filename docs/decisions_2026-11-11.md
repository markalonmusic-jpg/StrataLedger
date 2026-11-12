# StrataLedger decisions record (2026-11-11)

Status: DECIDED by the product owner. This file is the source for the
CLAUDE.md and design-doc updates. Where a design doc disagrees, this file
wins until CLAUDE.md is updated. Do NOT edit decisions here without asking.

---

## 0. Design principle: graduated controls (top-level rule)

StrataLedger defaults to QuickBooks-level flexibility for a small business.
As a company grows it can switch on stronger controls, approvals, audit
requirements and posting restrictions, without moving to another system.
The goal is a product a small business can use on day one that can become
CPA-grade and audit-ready later. It is not a NetSuite clone.

Two kinds of rule:

**Integrity rules: always on, never configurable.** These protect the
books from being wrong, not just from being uncontrolled.
- Integer cents; balanced double entry checked in the posting transaction.
- Posted records are locked; corrections are reversals or new documents.
- The audit log records every change and cannot be edited or deleted.
- Nothing posts into a closed period (closing periods is optional; a
  period that is never closed stays open).
- Sales invoices that require a registered series (Philippines add-on)
  stay gapless.
- Permissions are enforced in the service layer (`authorize`), and the AI
  never posts, approves or moves money.

**Controls: configurable, OFF or permissive by default.** A company turns
them on in settings (Admin or Master; every change is audit-logged).
- Separation of duties (`require_separate_approver`, default 0).
- Approval required per document type (default: not required, see 1.6).
- Manual journal entries to controlled accounts (`allow_manual_control_je`,
  default 1: allowed and flagged).
- PO matching (two/three-way) and its tolerances; compliance holds.
- Period-close checklist hard blocks (deferral tie-out etc.) apply only
  when the company closes periods.
- Project scope for roles, approval limits, approval chains.

Rule for new features: when a check could reasonably be optional, build it
as a setting with a permissive default, list it on the Company Settings
"Controls" page, and log every change to it. When unsure whether something
is integrity or control, ask.

## 0b. Design principle: ease of use (UX/UI)

The same idea as graduated controls, applied to screens: simple by default,
power one step away.
- Plain language on every screen (no accounting jargon where a plain word
  works; jargon shown as a tooltip).
- Sensible defaults everywhere; a new user can finish a task without
  changing any setting.
- Progressive disclosure: advanced options and controls that are OFF stay
  hidden until the company turns them on (Settings > Controls).
- Presets first: common tasks and reports are one click (section G).
- Wizards for setup and rare tasks (company creation, conversion,
  year-end); fast keyboard-friendly forms for daily entry.
- Every list is searchable and filterable; every number drills down to the
  documents behind it.
- Drafts are safe: anything not posted can be changed or deleted; posting
  shows a plain preview of the journal entry first.
- Errors say what to do next, in one sentence (no codes or stack traces).
- Screens follow docs/CLAUDE_UI.md.

---

## 1. Reconciled decisions (these override the pasted answer file)

1.1 **A5 manual entries to controlled accounts:** `allow_manual_control_je`
DEFAULT 1 (allowed), per the owner's follow-up and section 0. Every such
line sets `journal_line.is_control_override = 1` and appears on the
period-close review. A manual line to AR or AP must name the customer or
vendor (a PO-linked account must name the PO), so subledgers still tie.

1.2 **B3 and A6 Undeposited Funds:** optional, not one of the required
accounts. Receipts default to Undeposited Funds only when the company has
that pointer set; otherwise the user picks the bank or any account. Required
before first posting: AR, AP, sales tax payable, default bank, retained
earnings, opening balance equity (six).

1.3 **B7 voucher numbers:** bills get a system voucher number (VCH-1001)
from their own `voucher_sequence`, NOT from `invoice_series` (that table is
for sales series with registered ranges). Voucher numbers are assigned at
entry and may have gaps when drafts are deleted. The vendor's invoice number
is kept; a duplicate per vendor is a warning, not a block. Sales invoices
get a gapless series number at send/post.

1.4 **E12 naming:** the UI guide is `docs/CLAUDE_UI.md`. There is no
`modules/CLAUDE.md`; fix references that name it.

1.5 **A1 management view:** accounts carry `is_tax_strategy_only` (default
0). Management View = GAAP/Audited basis (periods 1-13) excluding those
accounts. Tax Basis = periods 1-14 (audit adjustments come before tax
adjustments).

1.6 **New, from section 0: approvals off by default.** Each document type
has a company setting "requires approval" (default off). When off,
`submit_for_approval` is not required and documents post directly. When on
and no policy covers the amount, the default single-approver chain applies.
Journal entries keep the existing `manual_entry_approval` setting as their
"requires approval" switch.

1.7 **Built code that must change** (schedule after 2.3):
- `require_separate_approver` default 0 (in the 2.3 prompt).
- approvals.py: honour the per-document "requires approval" setting (1.6).
- The unconditional `journal_entry` CHECK `approved_by IS NOT created_by`
  becomes a trigger that applies only when `require_separate_approver = 1`
  (already a Known issue for 2.5).
- `allow_manual_control_je` default 1 and `journal_line.is_control_override`.

---

## 2. Decisions by section

### A. Company setup and chart of accounts (for 2.4)
- A1 Fiscal year: any start month, 12 monthly periods, plus period 13
  (audit adjustments) and period 14 (tax adjustments), both dated the last
  day of the fiscal year (`is_adjustment_period = 1`), each closed
  separately. Report basis selector on every financial report:
  Pre-adjustment (1-12), GAAP/Audited (1-13), Tax (1-14), Management (see
  1.5).
- A2 `company_settings.date_format` (MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD);
  the database always stores ISO dates.
- A3 `account.normal_balance` (D/C) defaults from account type, with a
  contra-account toggle before first posting. Storage keeps `debit_cents`
  and `credit_cents`; reports use signed (debit - credit) and present
  positive numbers by normal balance.
- A4 Control types `Retainage receivable` and `Retainage payable` replace
  `Retainage`.
- A5 Controlled types: AR, AP, Retainage receivable, Retainage payable,
  Sales tax payable, Use tax payable, Undeposited funds, GRNI (Accrued
  receipts), Inventory, Fixed assets, Loans. Manual entries per 1.1. GRNI
  variances cleared by an approved "Clear GRNI variance" document to
  Purchase Price Variance or Inventory Adjustments.
- A6 System account pointers on `company_settings` as real foreign keys
  (list in the decisions doc; six required, see 1.2; others required when
  their feature is first used). Source tracking per B13. The Create Company
  wizard ends with an optional "Enter starting balances" step that opens the
  conversion wizard (E4).
- A7 Templates on the Create Company screen: Construction (default),
  General (service/SaaS), Import my own CSV; include the added accounts
  (Undeposited Funds, Customer Deposits, Accrued Liabilities, Payroll Tax
  Liabilities, Current Portion of LTD, Loan Closing Costs, a Credit Card
  account per card, Owner Draws, Interest Income, Bank Charges, Gain/Loss on
  Disposal, Inventory Adjustments, Purchase Price Variance, Warranty
  Expense, Indirect Job Costs, Provision for Job Losses, Accrued Job Losses).
- A8 The approval engine (approval_policy / steps / requests) is the only
  approval mechanism, including manual journal entries.
- A9 `require_separate_approver` default 0, with a setup toggle "Require a
  different user to approve entries and bills"; self-approvals are flagged
  in the audit report.

### B. Posting, payments, bank rec, year-end (for Phase 4)
- B1 No closing entries. Year-end locks the year (`is_year_closed = 1`);
  retained earnings is calculated in reports.
- B2 An invoice is Paid when its net due (total - retainage) is zero;
  retainage is tracked separately until a Retainage Release collects it.
- B3 Receipts can go to Undeposited Funds, a bank, a processor clearing
  account (Square, Stripe, PayPal) or any account. A Bank Deposit groups
  receipts; processor payouts record fees. Bank matching can match many
  receipts to one bank line.
- B4 Unapplied customer payments sit as an unapplied credit on the
  customer's AR (shown in a separate Unapplied Credits column on AR aging),
  with an option to post to Customer Deposits or Unearned Revenue instead.
- B5 Vendor credit memos: Dr AP / Cr expense; applied to future bills or
  turned into a refund request with cash received against it.
- B6 Credit memos and payments share one allocation table.
- B7 See 1.3.
- B8 Bills must be approved (when approval is on) and off compliance hold
  before a Payment Run; runs use the Payment approval chain when approval
  is on.
- B9 Check printing on standard stock with check numbers per bank account;
  NACHA ACH export.
- B10 Undo only the latest reconciliation per account, `bank.unreconcile`
  permission, reason required, logged.
- B11 CSV and OFX/QFX statement import into a matching screen; no live
  feeds in v1.
- B12 Credit cards reconcile on the same screen.
- B13 `journal_entry.source_doc_type` + `source_doc_id` (+ existing
  `invoice.entry_id`); do not reuse the existing `source_type` name.
- B14 Voiding a received payment reverses it, releases allocations,
  reopens invoices and offers an NSF fee invoice.

### C. Deferrals, subscriptions, recurring
- C1 Early cancellation: recognize the remainder now, or reclass to a
  refund receivable/payable; approval when approvals are on.
- C2 `saas_subscription` is the recurring billing plan that generates
  draft invoices; billed-in-advance lines create deferrals.
- C3 One `recurring_template` for invoices, bills and journal entries;
  generates drafts.
- C4 Period close is blocked if deferral lines for the period are unposted
  or the subledger does not tie to the GL (applies when the company closes
  periods).
- C5 Full-month proration by default (15th cutoff); daily per deferral.

### D. Construction (v1.1)
- D1 Full expected loss accrued when estimated total cost exceeds revised
  contract (Dr Provision for Job Losses / Cr Accrued Job Losses).
- D2 Cumulative WIP entry at period end, auto-reversed on day 1.
- D3 `project.poc_method`: Cost-to-cost (default), Manual percent (reason
  required), Completed contract.
- D4 Separate Retainage Release document (partial and final); merge the
  new pay-app draft into docs/pay_applications_design.md.
- D5 Retainage rate from the contract; logged line overrides; separate
  stored-materials rate.
- D6 Optional tax codes on pay application lines (off by default).
- D7 Completed = first Closeout stage (allows_costs = 1, allows_billing =
  1); add `pipeline_stage.allows_billing`; month-end Keep open / Close out
  review.
- D8 T&M billing in v1.1: bill rates per role/employee
  (`time_entry.bill_rate_cents`), material markup, Unbilled T&M screen.
- D9 Estimates use the Estimate approval chain (when on); only the primary
  revision; `sign_contract()` locks it and creates budget and SOV.
- D10 `cost_forecast` append-only per job, cost code and period.

### E. Scope and operations
- E1 Release order: v1.0 core accounting -> v1.1 construction -> v1.2 AI
  Copilot. Rewrite the CLAUDE.md roadmap to match.
- E2 Manual combined tax codes (basis points), invoice sales tax,
  self-assessed use tax on bills, liability report, tax payment.
- E3 1099: vendor flag and box, cash-basis payments excluding card
  payments, missing W-9/TIN warnings, e-file CSV export.
- E4 Conversion wizard: trial balance into Opening Balance Equity -> open
  AR/AP as documents -> tie-out -> lock and close OBE.
- E5 Consolidated TB, P&L and balance sheet across parent and
  subsidiaries by account code; tagged intercompany balances listed for
  manual elimination.
- E6 One base currency per company in v1.
- E7 Backups on open/close and nightly; keep 7 daily, 4 weekly, 12
  monthly; optional second folder; safety backup before restore.
- E8 Payroll: import the provider's journal through staging with hold and
  approve; `time_entry` allocates labor to jobs; auto-reversing month-end
  labor accrual.
- E9 Customer statements, AR aging, optional late fees, PDF email through
  the company's SMTP (credentials in the OS keyring).
- E10 Per-installation desktop licence, unlimited companies; per-company
  pricing for hosted.
- E11 `origin` lives on journal_entry, staged_transaction and audit_log;
  reword CLAUDE.md.
- E12 Archive superseded instruction docs; mark schema_audit.md
  historical; standardize names (see 1.4).

### F. Import mappings
- F1 Kinds: provider GL account, earning, employer tax, employee
  withholding, deduction, benefit, reimbursement, department, location,
  class, job/project, employee, vendor, card/merchant category, card
  holder, bank/card account.
- F2 Targets: account, project (FK), cost code (FK), contact, dimension
  values.
- F3 `import_source` is company-extensible, typed Payroll, Spend, Bank,
  Conversion, Other.
- F4 Unique (source, kind, value) for active rows; match exact mapping ->
  coding rules -> AI suggestion; unmapped lines block approval; "save as
  mapping" from review.
- F5 `import.mapping.manage` permission; audited; deactivate-and-add, never
  edit in place; staged lines copy coding at import.
- F6 CSV column layouts saved per company and source.
- F7 Employees are contacts with `is_employee = 1`; wages masked behind
  `payroll.view`.

### G. Report presets and prompt-to-report (added 2026-11-11)
- G1 Report presets: a built-in library, for example P&L this month vs
  last month, P&L year to date vs last year, balance sheet at period end,
  cash flow, trial balance, AR and AP aging, sales tax liability, 1099
  summary, job cost by project, WIP schedule (v1.1). Each preset is a
  saved report definition: report type, date range expressed in words
  ("last fiscal quarter", "year to date"), comparison, report basis (A1),
  filters (dimensions, projects, accounts) and layout.
- G2 Users save their own presets from any report ("Save as preset"),
  private or shared with the company. Presets store no numbers, only the
  definition, so they always run on current data.
- G3 Every preset has a plain-language prompt ("Show profit and loss for
  last quarter compared to the same quarter last year") shown as a button
  and usable as a template.
- G4 Prompt-to-report with the AI (v1.2, with the Copilot): the user types
  or picks a prompt; the AI chooses the preset and fills its parameters as
  structured data; the app shows "Run P&L, Jan-Mar 2027 vs Jan-Mar 2026,
  GAAP basis?" and runs the report locally on confirm. Running a report
  sends no ledger numbers to the AI provider. Asking the AI to explain or
  summarize a report's numbers is a separate step that requires the
  company's data-sharing opt-in.
- G5 Without the AI (v1.0, or no API key): the same prompt box matches
  typed words to presets locally (keyword search, no network), so presets
  and the prompt box work offline and with no subscription.
- G6 Date words ("last quarter", "this fiscal year") are resolved by the
  app from the company's fiscal calendar, never by the AI, so results
  match the company's periods.
- G7 Reports run under the user's own permissions (report.financial,
  report.job_cost; masked fields stay masked). The AI's allow-list already
  includes report codes except report.export, so it can run but never
  export a report.

---

## Round 2 (decided 2026-11-11, evening)

Source: the "Plan to v1.0 and Questions, Round 2" doc. Items not listed
here (L5-L8, U1-U6) are still open.

### P. Platform and files
- P1 Desktop v1 is one computer per installation. Several users may log in
  there one at a time (or via Remote Desktop to that computer). Opening a
  company file from a network share is refused. Simultaneous multi-computer
  work is the hosted version.
- P2 Company files live only in the installation's `Companies` folder;
  never a user-chosen folder. Off-site safety comes from backups copied to
  a second folder (E7), which may be cloud-synced.
- P2a Code and data are separate folders, both worked out at runtime
  (never a hardcoded machine path):
  - Resource folder (read-only: code, chart templates, help, fonts): the
    folder the app runs from (the PyInstaller bundle folder when packaged).
  - Data folder (writable: system_master.db, Companies, Backups, Logs,
    Uploaded_Files): the STRATALEDGER_DATA_DIR environment variable if
    set; otherwise the repository folder when running from source;
    otherwise %PROGRAMDATA%\StrataLedger for the installed app.
    ProgramData is shared by every Windows account on the computer, which
    P1 needs; the installer gives it the right permissions.
  - Tests always set their own temporary data folder.
- P3 v1 supports Windows 10 and 11 only. Code stays portable (no
  Windows-only calls outside one platform module) so macOS can follow.
- P4 Start a new private GitHub repository from the current code with
  fresh history (the old history contains the removed token and test
  passwords). The old local repository is kept as an archive.
- P5 Hosted target (decided 2026-11-12): PostgreSQL, expected on Azure Database for PostgreSQL. Keep SQL
  portable; rules stay in services (H4); the posted-entry locks and the void trigger live in one per-dialect
  place and will be rewritten, not ported; numbering and the hash chain use explicit counter-row locking that
  ports; hosted is multi-tenant (not designed now); secrets sit behind one wrapper so Azure Key Vault can
  replace DPAPI; a hosted relay for bank feeds becomes natural in the hosted product.

### S. Company setup (2.4)
- S1 Company code suggested from the name, editable at setup, 3-10
  uppercase letters and digits, unique in the installation, immutable;
  file is `Companies/<CODE>.db`.
- S2 Fiscal years are named by the calendar year they end in (Jul 2026 -
  Jun 2027 = FY2027), always shown with their dates.
- S3 Setup asks for the first fiscal year to record (default current);
  periods are created for that year through next year; later years are
  created automatically 60 days before they start. A conversion cutover
  inside a year is allowed.
- S4 Periods 13 and 14 are always created, hidden in pickers and reports
  until "Adjustment periods" is turned on in Controls.
- S5 Four-step wizard: (1) legal name, display name, code, country (US or
  Philippines), currency (from country), tax ID (optional); (2) fiscal year
  start month, first year, date format (from country); (3) chart template;
  (4) "require a different user to approve" (off). Then the optional
  "Enter starting balances". Address, logo, invoice details later in
  Company Settings.
- S6 Starter roles: Admin (fixed) plus Controller, Accountant, AP Clerk,
  AR Clerk, General Manager, Project Manager, Warehouse, Foreman, Payroll,
  Sales, Viewer. The General template omits Project Manager, General
  Manager, Warehouse and Foreman.
- S7 A new subsidiary copies the parent's chart, roles, approval policies
  and controls by default; option to start from a template instead.
- S8 An Admin who creates a subsidiary becomes its Admin. When the Master
  creates a company, the wizard asks whether to give a named user the
  Admin role; the Master needs no access row.
- S9 Companies are archived (read-only, hidden from the picker, still
  backed up), restored or exported by the Master; there is no in-app
  delete.

### C. Chart of accounts
- C1 Every account has a 4-8 digit number, auto-suggested from its parent
  and type; lists sort by name or number.
- C2 Up to 4 levels. Any account that has child accounts cannot receive
  postings, at any level, so parent subtotals always equal their children.
- C3 Names editable (logged). Numbers editable by an Admin (logged),
  blocked while an active mapping or preset refers to the number by text.
  Type and normal balance locked after posting. Merge later.
- C4 Full routing and account numbers stored in the company file for
  checks and ACH; shown masked (last 4) without view.bank_details; never
  sent to the AI; never written in full to the audit log.
- C5 No dimensions at setup; Company Settings offers Class and Location in
  one click, plus custom dimensions.
- C6 Required dimension per account is a control, off by default.

### L. Ledger and periods
- L1 Two ways to lock months, one mechanism: a "Books closed through" date
  in Company Settings, or the formal period-close screen. Both set
  fiscal_period.is_closed.
- L2 Every period-close check is a warning by default and can be made a
  hard block in Controls. This amends C4: the deferral tie-out blocks close
  only when the company turns that check on.
- L3 One accounting date per document decides the period; bills also keep
  the vendor's invoice date and due date for aging and terms.
- L4 One continuous gapless journal entry sequence per company (JE-000001),
  assigned at posting, never reset by year.

### U. Packaging, updates, licensing and support (decided 2026-11-11)
- U1 Packaging: PyInstaller one-folder build wrapped in an Inno Setup
  Windows installer, code-signed so Windows SmartScreen accepts it.
- U2 Updates: a non-blocking daily check against a signed `version.json`
  manifest; an "Update available" pill in the top bar; the installer's
  SHA-256 is verified before it runs; never updates while a company is
  open; schema upgrades rely on the runner's backup-before-migration.
- U6 Update flow (approved; combines with U2): opt-out version check on
  launch -> download -> verify signature and SHA-256 -> back up
  system_master.db and every company database -> ask the user to install.
  Updates never install silently and never require a subscription.
- U3 Licence: offline Ed25519-signed installation licence, unlimited
  companies and subsidiaries in desktop v1 (E10). The licence to use the
  app is perpetual; an optional update plan covers new versions. An expired
  update plan never locks anyone out of their own accounting data.
- U4 Support: "Export support bundle" zips redacted app logs and version
  details. Company `.db` files are included only with explicit opt-in.
- U5 Standard SQLite in v1; optional SQLCipher encryption at rest after
  v1. Setup guide recommends Windows BitLocker.

### L5-L8 and remaining items (decided 2026-11-11)
- L5 Auto-reversing entries: optional `journal_entry.auto_reverse_date`.
  Posting the entry also creates and posts its reversal, dated
  auto_reverse_date, in the same transaction (reversal_reason 'Accrual
  reversal'; the target period must exist and be open). Voiding the
  original voids its unposted-in-effect reversal pair together.
- L6 Date warnings: `company_settings.warn_future_days` (default 30) and
  `warn_past_days` (default 90) trigger a confirmation prompt; they never
  block posting into an open period.
- L7 Period reopen: `period.reopen` permission (seeded to Admin and
  Controller) with a mandatory logged reason in `period_status_history`.
  Reopening a period in a closed fiscal year needs a separate sensitive
  permission `year.reopen` (seeded to Admin only; the Master holds all) and
  clears the year-closed flag with an audit entry. Code checks permissions,
  never role names.
- L8 Import rounding: external multi-line imports (CSV, payroll,
  conversion) may auto-balance a difference of exactly 1 cent to
  `company_settings.rounding_variance_acct_id`, with an info flag on the
  line. 2 cents or more is rejected. Manual journal entries have zero
  tolerance.
- Theme: light theme deferred to after v1.0. Phase 3 must use
  `config.Theme` tokens only (no colors in views), so a later theme needs
  no view changes.
- Sample company: `scripts/seed_sample_company.py`, deterministic, in
  v1.1, with construction jobs, pay applications and reconciled bank items.
- Accounting sign-off: the product owner reviews all accounting defaults,
  chart templates and statements; no external CPA review checkpoint.
  (The Philippine tax professional review of the ph_tax add-on is a
  separate item and still stands unless the owner removes it.)
- Help: offline Markdown help (`help/*.md`) opened with `?` or F1 from the
  top bar, one page per screen.

Round 2 is fully decided.

---

## H. SaaS readiness and portability (decided 2026-11-11)

StrataLedger is desktop-first with a hosted multi-tenant version planned.
Business logic must port to a FastAPI service and PostgreSQL (and the
screens to a web front end) without being rewritten. The rules below
apply to all new code; existing code is brought in line when its step is
next touched. Paths use the real package name `modules/services/`.

### H1. Services are UI- and OS-free
- `modules/services/*.py` never imports tkinter, customtkinter, dialogs or
  OS-specific helpers. Inputs are plain types (str, int, bool, dict, list,
  dataclasses); money is always integer cents (Decimal only for rates and
  quantities, never money). Results are plain dicts or dataclasses; errors
  are typed exceptions. A static test enforces the import rule.

### H2. Clock and "today" come from the context
- Services never call datetime.now(), date.today() or read UI state. The
  context carries `now` (UTC ISO 8601) and `today` (ISO date).
- `today` is the company's local date, not the UTC date: add
  `company_settings.timezone` (IANA name, chosen at setup from the
  country, for example America/Los_Angeles or Asia/Manila). Otherwise an
  entry made at 6 pm in California would default to tomorrow's date.
- `clock.utc_now_iso()` stays as the one place that reads the system
  clock; it is called when the context is built (open_company, login),
  not inside services. Tests pass fixed times.

### H3. Storage abstraction
- Files (attachments, exports, backups, chart templates, help, support
  bundles) go through `modules/services/storage.py`: a local-disk backend
  now, an object-storage backend for hosted. Services never build Windows
  paths. The company database location stays with database.py and the
  registry (decision P2); in hosted mode the context carries a tenant
  handle instead of file paths.

### H4. Where rules live (reconciles "no new triggers")
- Workflow and control rules (approvals, graduated controls, limits,
  matching, warnings) live only in services. No new triggers for them.
- Integrity rules keep a database-level backstop: CHECK, NOT NULL, unique
  and foreign keys, plus triggers only for immutability (posted-record
  lock, codes never change), append-only tables and the audit trail. These
  are re-created in PostgreSQL when the hosted version is built, and every
  one has a service-level twin and a test, so the backstop and the rule
  never disagree.
- The audit context is set only through `tx.py`. In SQLite it is the
  one-row `audit_context` table (safe: one writer at a time). In
  PostgreSQL it becomes per-transaction settings (SET LOCAL), because a
  shared one-row table is unsafe with concurrent transactions. No code
  outside tx.py touches audit_context.

### H5. Portable SQL in services
- No SQLite-only functions in service queries (date('now'), strftime,
  julianday, INSERT OR REPLACE, GROUP_CONCAT); dates and times are passed
  as bind parameters. Use standard INSERT, UPDATE and INSERT ... ON
  CONFLICT. Booleans stay 0/1 and timestamps ISO text in SQLite; the
  PostgreSQL port maps them to boolean and timestamptz.
- Keys come from `cursor.lastrowid` or `INSERT ... RETURNING` (both work
  in SQLite 3.35+ and PostgreSQL); service code never reads
  sqlite_sequence (tests may).
- SQLite connection settings (PRAGMAs such as busy_timeout, foreign_keys)
  live only in database.py's connection helpers, never in services.
- All SQL goes through the connection helper, so placeholder style can be
  converted in one place for PostgreSQL.
- Hosted tenancy keeps decision CRM "one database per company": in
  PostgreSQL that is one schema per company, so queries need no tenant
  column.

### H6. Screen specs and design tokens
- Screen specs (layout zones, columns, the five states: empty, loading,
  editable, locked, error) are written before code, in docs/CLAUDE_UI.md
  and the module design docs. No separate UI_SCREEN_BLUEPRINTS.md unless
  the owner asks for one; docs/design.md stays a draft subordinate to
  docs/CLAUDE_UI.md.
- All visual values (colors, type scale, spacing, radii) live in
  config.Theme; views contain no literal styling. This also makes the
  deferred light theme a token change only.

### I. Management report layouts and KPIs (decided 2026-11-11)
- I1 Chart of accounts templates in docs/coa_draft/ are APPROVED by the
  owner; 2.4 copies them to templates/coa/.
- I2 Report layouts: named, company-defined groupings of accounts into
  lines and subtotals for management reporting, separate from the chart
  hierarchy; several per company; each account maps to at most one line per
  layout; unmapped accounts show in an "Unmapped" line so totals tie to the
  GL. Used by report presets (G) and the Management basis (A1). Built in the
  v1.0 reports step.
- I3 KPIs: kpi_definition (name, unit count/money cents/percent, rollup sum
  or point-in-time, manual or calculated) and one kpi_value per KPI per
  period (entered_by, note). Values lock with the period close; corrections
  need a reopen with a logged reason. "KPIs entered" is a period-close check
  (warning by default, can be a block). Reports can use KPIs in ratios.
  v1.0: manual KPIs plus calculated revenue and gross margin; CRM KPIs
  (leads, conversion) in v1.1.
- I4 KPIs can be split by dimension: a kpi_definition lists which
  dimension types it is recorded by (for example Department or Profit
  Center), and each kpi_value can carry a dimension_value_id (NULL = whole
  company). Company totals roll up from the dimension values for "sum"
  KPIs; "point-in-time" KPIs (headcount) also sum across dimensions unless
  the definition says the company figure is entered separately. Reports can
  then show ratios by department or profit center (for example revenue per
  head by profit center), matching the GL's dimension tags.
- L7 amended (2026-11-11): year.reopen is seeded to Admin and
  Controller. Reopening a closed year needs two confirmations in the UI
  (1: a warning of the impact, Continue/Cancel; 2: type the year name,
  e.g. FY2027, plus a reason). The service reopen_year requires reason and
  confirm_year_name matching the year's name, so no caller can skip it.
- L7 amended: reopening a period, or moving Books closed through back,
  needs one confirmation in the UI that names the period(s) affected and
  warns that reports may change (Reopen/Cancel), then a reason. Year
  reopen keeps its two confirmations.
- 0b amended: every risky action asks 'Are you sure?' on press before
  anything changes: reopen/close period or year, Books closed through,
  post, void, reverse, archive/restore company, restore backup, delete
  draft. Cancel is the default button (Enter never confirms). Reopen year
  and archive/restore also need the name typed. Services require an
  explicit confirm for reopen, year reopen, archive/restore and backup
  restore, so no screen can skip it.

### J. Budgets, forecasts and FP&A (decided 2026-11-11)
- J1 KPIs keep the I3/I4 design (kpi_definition, kpi_value with optional
  dimension_value_id). Additions: kpi_definition.calc_mode Manual or Auto
  (Auto computed from posted data, time_entry, projects or subscriptions);
  kpi_definition.require_at_close: when 1, the period-close check "KPIs
  entered" covers that KPI (warning by default, block if the company sets
  it, per L2). KPI values hold actuals only; forecasts live in J2-J3.
- J2 Budgets (v1.0): budget_version (name, fiscal year, type Annual budget,
  status Draft/Approved/Locked) and budget_line (version, account, period,
  optional dimension_value_id, amount_cents). A locked version never
  changes; edits make a new version. Budget-vs-actual reports by account,
  layout (I2) and dimension. Budget approval uses the approval engine when
  approvals are on.
- J3 Rolling forecasts (FP&A release, after v1.1 construction): forecast
  versions (3+9, 6+6, 9+3) built from the latest locked budget plus closed
  actuals; driver rules (KPI x rate, % of revenue or labor, job
  cost_forecast backlog burn); "Roll forward" replaces closed periods with
  actuals and recalculates open periods. Rates may be decimals; every stored
  amount is integer cents, rounded half-up per line, with the rounding
  difference on the last period. Service: modules/services/fpa.py.
- J4 Excel FP&A export (FP&A release): StrataLedger writes its own
  workbook (Rolling Forecast with ACTUAL/FORECAST headers and live
  formulas, KPIs and Drivers, Job and Dept Detail, and a flat
  _STRATA_ACTUALS table). Refreshing actuals rewrites only StrataLedger's
  own export file or a separate actuals file; it never opens or saves a
  user's own model (the Excel library would drop their charts and pivots).
  Analysts link their models to the actuals file with Excel's Power Query
  refresh.
- J5 AI reforecast skill (AI release): the AI may analyse actual-vs-budget
  and KPI trends and propose a draft forecast version for human review; it
  never approves, locks or saves a version, and all amounts are computed by
  the fpa service, not by the AI.
- S10 First-run setup is a GUI screen: when
  system_master.db is missing or has no users, the app shows a Welcome
  screen instead of login: build the master database, create the Master
  (username, first/last name, email, password twice, 12+ characters),
  show the recovery code once with a Copy button and a required 'I have
  saved this code' checkbox, then sign in and offer 'Create your first
  company' or 'Later'. Cancelling creates no user; the screen returns on
  next launch. The recovery code and password are never logged.

## Phase 2.5 ledger and billing services (decided 2026-11-12)

Answers to the 2.5 plan's questions. Integrity unless marked control.
- R1 Rounding (L8) applies to three entry sources: CSV import (`Import`), payroll import (`Payroll`) and
  conversion (`Conversion`, a new `journal_entry.source` value). Only those may carry a one-cent
  `is_rounding_adjustment` line to `rounding_variance_acct_id`; manual entries have zero tolerance.
- R2 `confirm=True` is required on a Human-origin `post_journal_entry`, and always on `void_entry` and
  `reverse_entry`. Imports, system posts and the system-made auto-reversal do not take it.
- R3 Agent-origin entries: with `require_separate_approver` off, the human the agent ran as may approve, and the
  approval is flagged `self_approved`; with it on, a different human must approve.
- R4 Pair void (L5): an entry has one Void-or-Correction reversal slot and one Accrual-reversal slot (two partial
  unique indexes). Voiding an accrual that has an auto-reversal voids both; if either the original's or the
  reversal's period is closed, the whole pair-void fails with a one-sentence error and nothing is written.
- R5 Manual-entry approval threshold (control): approval is needed when total debits are strictly over the
  threshold; an entry equal to it posts; with the setting on and no threshold, every manual entry needs approval.
- R6 Invoice numbering: the first send of an Invoice or Credit Memo with no series creates a default unregistered
  series ("INV-", "CM-", no registered range). Not for a company with the `ph_tax` add-on enabled, which must
  have a registered series.
- R7 Payment allocation in 2.5: same contact, a Received payment to a Sales invoice only, any open status (not
  Draft, Void or Paid); the invoice is marked Paid when its net due (total minus retainage minus allocations, B2)
  reaches zero. The allocation table stays open for credit memos and vendor-side allocation (B4-B6).
- R8 A manual entry is one whose source is empty, `Manual` or `Adjustment`. User-made Void and Correction
  reversals are exempt from threshold approval but need `je.reverse`, a reversal note and `confirm=True`.
- R9 Manual lines to controlled accounts (A5, control) are flagged `is_control_override` and reported by the
  `control_overrides` period-close check (warning by default, can be a block, L2). `reversal_note` is required
  and non-blank for Void and Correction, not for an Accrual reversal.

Added with Phase 2.5 step 3 (posting), 2026-11-12:
- R10 Every account with a `control_type` is a controlled account for A5. A manual line to an AR account
  must name a customer (a contact with `is_customer`), and to an AP account a vendor (`is_vendor`); the
  other controlled types need no contact. Naming the purchase order on a PO-linked account (GRNI) cannot be
  built until the PO table exists (v1.1).
- R11 Until step 4 builds approvals, posting fails closed with "This entry needs the approval step, which is
  not available yet." for: Agent- or Import-origin entries (and Import contexts); manual entries that qualify
  for manual-entry approval (R5); entries whose document source (Bill, Payment, Import, Payroll) has
  "requires approval" on. Reversal drafts are posted only by the reverse and void actions, and an entry with
  an automatic reversal date is refused, both until step 5.
- R12 Date warnings (L6) apply to Human-origin posts only, for dates far ahead or behind; they are not raised
  for an entry in adjustment period 13 or 14, which is always dated the year end.
- R13 Posting checks the provider's chain key against the fingerprint of the company's active
  `ledger_chain_key`; no active key, no provider key or a mismatch refuses the post (K3).
- R14 Posting needs `je.post` only; the date check it runs internally (`periods.entry_date_warnings`) does not
  need `period.view`.

Added with Phase 2.5 step 3b (verification), 2026-11-12:
- K13 `ledger.verify` is a sensitive permission (module Audit), so it is held only where granted by name:
  Admin (every code), Controller (starter template), the Auditor role when Phase 3 adds it, and the Master.
  The Accountant does not get it (K11).
- K14 Every ledger checkpoint is mirrored in the master (`chain_checkpoint`, append-only, same fields and MAC),
  so restoring an older copy of a company file is detected; a read-only (Auditor) verification is recorded
  there only.
- K15 Incremental verification starts at the last OK checkpoint and re-checks the checkpointed entry (stored
  hash, link and recomputed seal) and every entry after it; full verification re-proves everything. The
  `ledger_integrity` close check always runs full.
- K16 Unavailable (no key for a needed key id) is reported as such, never as tampering, and is never recorded
  as a checkpoint; in the close checks it is always a warning.
- K18 A signed checkpoint is written automatically when a company is closed (logout) and at app exit
  (system upkeep, no permission, never blocks closing), so the "no checkpoint yet" truncation gap exists only
  before a ledger's first close.
- K17 Measured verification speed misses the K12 targets (full 100k entries: about 26 s; incremental 100
  entries: about 0.35 s); speeding it up is backlog item 14, not a blocker for step 1c.

## K. Audit readiness (decided 2026-11-12)

Design: docs/audit_readiness_design.md. Build order: 2.5 Step 1b (chain schema), then Step 3 (posting seals
through a KeyProvider interface; a fixed key in tests; posting refused when no real key is available), then
Step 1c (keystore, recovery-code wrap). Step 1c lands before any screen can post and before 2.5 is done.
- K1 The installation key is wrapped with DPAPI in machine scope, so every Windows account on the computer
  can open the app (P1). Limit, stated plainly: any local user who can run code can unwrap it; DPAPI protects
  against a copied disk or file, not against another account on the running computer.
- K2 Add the `cryptography` library for the recovery-code wrap (AES-GCM), after confirming its licence and
  the PyInstaller build.
- K3 A broken chain warns and still allows posting by default; in Audit-ready mode posting is blocked until a
  full verification passes. Nothing is ever posted without the chain key.
- K4 The Auditor sees sensitive fields (tax IDs, bank details, wages) only if an Admin grants them.
- K5 Restoring a backup whose checksum does not match is refused, except for the Master with a typed
  confirmation and a reason; a safety backup is made first and the restore is flagged on the Audit-ready
  checklist.
- K6 Chaining `audit_log` goes on the backlog.
- K7 New permission `ledger.verify` (run "Verify ledger integrity"), seeded to Admin, Controller and Auditor.
- K8 The chain key leaves the installation only inside the passphrase-protected company bundle, exported and
  imported by the Master only.
- K9 Auditor becomes a 12th starter role: read-only, all non-sensitive views and reports, `audit.view`,
  `ledger.verify`; it cannot post, approve or change settings.
- K10 U5 stands: standard SQLite in v1.0; SQLCipher-type encryption at rest after v1, when the go/no-go
  checklist in the design is green.
- K11 The Accountant does not get `ledger.verify`; they see the verification result on the period-close
  checklist.
- K12 Verification speed targets are benchmarks to measure and report when the verify service is built, not
  pass/fail tests: a full check of 100k entries (3 lines each) in 10 seconds, an incremental check of 100 new
  entries in 0.2 seconds.

## PW. Password recovery (decided 2026-11-12)

Design: docs/password_recovery_design.md (answers to its section 12). Already decided by the owner in the
design's header: v1.0 has two recovery paths (an Admin or the Master resets a regular user; personal backup
codes for every regular user), email is an optional add-on with the lowest priority, an authenticator (TOTP)
comes in v1.1, and passwords are never emailed. All of these are integrity rules, not controls.
- PW1 A temporary password expires 72 hours after it is issued (`app_user.temp_password_expires_at`).
- PW2 Only the Master can reset an Admin. An Admin can reset neither the Master nor a user who is Admin in any
  company.
- PW3 New sensitive permission `user.reset_password` (module Company), seeded to Admin; it replaces
  `company.users.manage` as the reset gate, so managing users and resetting passwords can be split.
- PW4 The app generates the temporary password (16 characters, unambiguous base32, groups of four, 80 bits);
  the Admin no longer types one. It is shown once with the secret-safe Copy and an "I have handed this over"
  button that clears the clipboard.
- PW5 Backup codes: 10 codes of 10 base32 characters (50 bits), each stored as a scrypt hash with its own salt;
  every attempt checks all 10 slots (a dummy hash for used or superseded slots and unknown users); a warning at
  2 codes left or fewer.
- PW6 Email settings are installation-level, managed by the Master; a company's Admin may see them read-only.
- PW7 (changed from the proposal) An Admin or Master reset offers "Also make new backup codes", ON by default.
  When it is on, the reset supersedes the user's old set in the same transaction and the Admin's handover
  screen shows the temporary password and the 10 new codes once. When it is turned off, the user's existing
  codes stay valid. Either choice is recorded in `auth_event`.
- PW8 Throttle: per account, today's values (5 wrong attempts, then 30 seconds doubling to 15 minutes; a success
  clears the key); per installation, 20 failed recovery attempts (backup code or recovery code, any username)
  in 15 minutes pause "Forgot password" for everyone for 15 minutes. Password sign-in is never paused by it.
- PW9 Every Master password change needs the recovery code (with the current password for a change, alone for a
  forgotten password). Each use issues a new code at once and re-wraps the installation key with it in the same
  transaction (Step 1c), so the Master saves a new code every time; the screen says so before they start.
- PW10 The policy additions (not only spaces; not the username in any letter case) apply to every new password
  from the build step on. Existing passwords are not forced to change.
- PW11 (changed from the proposal) When an Admin or the Master issues a user's backup codes (PW7 or a reissue),
  the user is PROMPTED at their next sign-in, after any forced password change, to make their own set: "Your
  administrator made these backup codes, so they have seen them. Make your own set now?" with "Make new codes"
  and "Later". "Later" lets the user in; the prompt returns at every sign-in until the current set is one the
  user issued. The test is the set's `issued_by` (not the user), so no extra flag is stored.

## KS. Key store, Phase 2.5 step 1c (decided 2026-11-12)

The step 1c plan was approved with these answers (design: docs/audit_readiness_design.md 2.7).
- KS1 Add `cryptography` (pinned in requirements.txt) for AES-256-GCM. PyInstaller is a developer tool, kept out of
  the runtime requirements.
- KS2 The recovery-code key-encryption key comes from `hashlib.scrypt` (N=2^15, r=8, p=1, its own salt, never the
  login hash's), not from `cryptography`'s scrypt. The recovery code holds 160 random bits.
- KS3 `KeyProvider.get_key(company_id, key_id)` keeps its signature; the local provider matches the master's
  wrapped key to the company's `ledger_chain_key` row by fingerprint.
- KS4 `SecretKey` gets a second accessor, `use_for_aead()`, for AES-GCM, so every use of the bytes stays named.
- KS5 If the recovery code is valid but the installation key cannot be unwrapped with it (a damaged wrap), the
  Master's password is still reset and the result says "the ledger key could not be restored", so the key-lost
  path can follow.
- KS6 Creating a company is refused while the installation key is locked (DPAPI failed and no recovery yet):
  "Ask the Master to restore the ledger key with the recovery code first."
- KS7 `create_company` takes a key-store hook so the test suite can use its fixed test key. The hook works only
  when STRATALEDGER_ALLOW_TEST_KEYS is "1", like `FixedKeyProvider`, and a test proves it refuses otherwise.
- KS8 The key-lost epoch (new key, old retired as `Key lost`, a checkpoint) is a service in step 1c; its screen
  is Phase 3.
- KS9 The master key tables carry no audit triggers (like `master_recovery`), so wrapped blobs never reach
  `audit_log`; each change writes an `auth_event` without the blob.
- KS10 `system_master.db` holds every company's wrapped chain keys. Losing it makes every company's ledger
  unverifiable (the data stays readable). The backup design (Phase 5) must back up the master with every company
  backup.
- KS11 Until the passphrase-protected key bundle exists (K8), `export_company` returns a warning that the exported
  file cannot be verified on another computer, and the export screen shows it. The bundle (Master only) is on the
  backlog for the backup step.
