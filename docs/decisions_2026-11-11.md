# StrataLedger decisions record (2026-11-11)

Status: DECIDED by the product owner. This file is the source for the
CLAUDE.md and design-doc updates. Where a design doc disagrees, this file
wins until CLAUDE.md is updated. Do NOT edit decisions here without asking.

## Index (one line per decision code; search the code to find its text)

Find a decision with a text search for its code (for example `KS6`), then read only that line or section. A
session that adds a decision code adds its row here. Two code letters repeat: C1-C5 are deferrals (section 2)
and C1-C6 the chart of accounts (Round 2); L7 has two amendments in section I.

Principles and reconciled decisions:
- 0 Graduated controls: integrity rules always on, controls off by default (section 0)
- 0b Ease of use: simple by default, power one step away (section 0b; amended in section I)
- 1.1 Manual entries to controlled accounts allowed and flagged (A5)
- 1.2 Undeposited Funds optional; six required accounts (B3, A6)
- 1.3 Bill voucher numbers from their own sequence, gaps allowed (B7)
- 1.4 The UI guide is docs/CLAUDE_UI.md (E12)
- 1.5 Management view excludes tax-strategy accounts; tax basis is periods 1-14 (A1)
- 1.6 Approvals off by default per document type
- 1.7 Built code that had to change after 2.3

A. Company setup and chart of accounts (section 2):
- A1 Fiscal year, adjustment periods 13 and 14, report basis selector
- A2 Company date format; ISO dates stored
- A3 Account normal balance and contra toggle
- A4 Retainage receivable and Retainage payable control types
- A5 Controlled account types; GRNI variance clearing
- A6 System account pointers on company_settings
- A7 Chart templates on the Create Company screen
- A8 The approval engine is the only approval mechanism
- A9 Require a different approver: default off

B. Posting, payments, bank rec, year-end (section 2):
- B1 No closing entries; year-end locks the year
- B2 Invoice Paid when net due is zero; retainage separate
- B3 Receipt destinations, bank deposits, processor payouts
- B4 Unapplied customer payments
- B5 Vendor credit memos
- B6 Credit memos and payments share one allocation table
- B7 Voucher numbers (see 1.3)
- B8 Bills approved and off hold before a payment run
- B9 Check printing and NACHA ACH export
- B10 Undo only the latest reconciliation
- B11 CSV and OFX/QFX statement import; no live feeds in v1 (amended by B11a)
- B11a v1.0 feed seam and file provider; Ramp in v1.1; aggregators later; relay hosted
- BF1 Bank feeds design questions answered as proposed; a Ramp charge is never booked twice
- B12 Credit cards reconcile on the same screen
- B13 journal_entry.source_doc_type and source_doc_id
- B14 Voiding a received payment

C. Deferrals, subscriptions, recurring (section 2):
- C1 Early cancellation of a deferral
- C2 saas_subscription billing plans
- C3 One recurring_template for invoices, bills and entries
- C4 Period close blocked by unposted deferrals (amended by L2)
- C5 Full-month proration by default

D. Construction, v1.1 (section 2):
- D1 Expected job loss accrued in full
- D2 Cumulative WIP entry, auto-reversed
- D3 project.poc_method
- D4 Separate Retainage Release document
- D5 Retainage rates
- D6 Optional tax codes on pay application lines
- D7 Completed stage and pipeline_stage.allows_billing
- D8 T&M billing
- D9 Estimates and sign_contract
- D10 cost_forecast append-only

E. Scope and operations (section 2):
- E1 Release order v1.0, v1.1, v1.2
- E2 Sales and use tax
- E3 1099 reporting
- E4 Conversion wizard
- E5 Consolidated reports
- E6 One base currency per company
- E7 Backup schedule and retention
- E8 Payroll import and labor accrual
- E9 Customer statements, AR aging, email through company SMTP
- E10 Desktop licence and hosted pricing
- E11 origin on journal_entry, staged_transaction and audit_log
- E12 Archive superseded docs; standard names

F. Import mappings (section 2):
- F1 Mapping kinds
- F2 Mapping targets
- F3 import_source types
- F4 Mapping uniqueness and match order
- F5 import.mapping.manage; deactivate and add
- F6 CSV column layouts per company and source
- F7 Employees are contacts; wages masked

G. Report presets and prompt-to-report (section 2):
- G1 Built-in report preset library
- G2 User presets, private or shared
- G3 Plain-language prompt per preset
- G4 Prompt-to-report with the AI (v1.2)
- G5 Prompt box without the AI (local keyword match)
- G6 Date words resolved by the app
- G7 Reports run under the user's permissions

P. Platform and files (Round 2):
- P1 One computer per installation
- P2 Company files only in the Companies folder
- P2a Resource folder and data folder
- P3 Windows 10 and 11 only; portable code
- P4 New private repository with fresh history
- P5 Hosted target PostgreSQL on Azure

S. Company setup (Round 2):
- S1 Company code
- S2 Fiscal year names
- S3 First fiscal year and automatic periods
- S4 Periods 13 and 14 hidden until turned on
- S5 Four-step Create Company wizard
- S6 Starter roles
- S7 New subsidiary copies the parent
- S8 Admin of a new company or subsidiary
- S9 Companies archived, never deleted
- S10 First-run setup screen (in section J)

C. Chart of accounts (Round 2):
- C1 Account numbers, 4-8 digits
- C2 Up to 4 levels; parents take no postings
- C3 Editing names, numbers, type and normal balance
- C4 Bank routing and account numbers masked
- C5 Dimensions offered after setup
- C6 Required dimension per account (control)

L. Ledger and periods (Round 2):
- L1 Books closed through and the period-close screen
- L2 Period-close checks warn by default, can block
- L3 One accounting date per document
- L4 One gapless journal entry sequence
- L5 Auto-reversing entries
- L6 Date warnings
- L7 Period and year reopen (amended twice in section I)
- L8 Import rounding of one cent

U. Packaging, updates, licensing and support:
- U1 PyInstaller and Inno Setup, code-signed
- U2 Daily update check against a signed manifest
- U3 Offline signed licence; perpetual use
- U4 Support bundle
- U5 Standard SQLite in v1; encryption later
- U6 Update flow

Uncoded items in "L5-L8 and remaining items": Theme (light theme deferred), Sample company, Accounting
sign-off, Help.

H. SaaS readiness and portability:
- H1 Services are UI- and OS-free
- H2 Clock and today come from the context
- H3 Storage abstraction
- H4 Where rules live
- H5 Portable SQL in services
- H6 Screen specs and design tokens

I. Management report layouts and KPIs:
- I1 Chart templates approved
- I2 Report layouts
- I3 KPIs
- I4 KPIs split by dimension

J. Budgets, forecasts and FP&A:
- J1 KPI calc mode and require_at_close
- J2 Budgets
- J3 Rolling forecasts
- J4 Excel FP&A export
- J5 AI reforecast skill

R. Phase 2.5 ledger and billing services:
- R1 Rounding applies to three entry sources
- R2 confirm=True on posts, voids and reversals
- R3 Agent-origin approvals
- R4 Pair void and reversal slots
- R5 Manual-entry approval threshold
- R6 Default unregistered invoice series
- R7 Payment allocation in 2.5
- R8 What a manual entry is
- R9 Control overrides and reversal notes
- R10 Controlled accounts and required contacts
- R11 Posting fails closed until approvals exist
- R12 Date warnings for Human-origin posts only
- R13 Posting checks the chain key fingerprint
- R14 Posting needs je.post only
- R15 An approval request carries the entry's content digest
- R16 Approval requests and actions are audited; requests never deleted
- R17 Separation of duties also covers posting
- R18 Import-origin entries approved one at a time until batch review
- R19 A fresh context for every post, approval and close
- R20 Which entries need approval; R11 lifted only through approval
- R21 Any edit or delete cancels the approval
- R22 Rejection needs a reason; resubmit only after a change
- R23 Only a human approves or rejects
- R24 Posting records and seals the last approver
- R25 The stale ledger xfails are rewritten in step 4
- R26 The close checkpoint is signed with a fresh context
- R27 Refusals are plain sentences; permission codes go to the log only
- R28 With separation on, the submitter may not approve either
- R29 The "only a person" denial names the approve permission
- R30 Rejection reasons never reach the log file
- R31 The rebuild script has a non-interactive mode
- R32 A failed sign-in never logs or stores the typed username
- R33 The app starts its log file at start-up
- R34 A limit refusal names only roles someone holds
- R35 Database errors in a save are a plain sentence; details go to the log
- R36 Access is checked before the company file
- R37 With separation on, a limit refusal does not count the creator or submitter
- R38 Every logger is under the app logger
- R39 With separation on, a limit refusal's "ask" target leaves out the creator and submitter
- R40 Which posted entries a person may void or correct (manual, Import, Payroll, Conversion)
- R41 Void and Correction dates
- R42 Voids and corrections need no second person (a backlog control may add one)
- R43 A reversal cannot be reversed
- R44 An accrual with an automatic reversal cannot be corrected, only voided as a pair
- R45 Reversals mirror dimensions too (service check)
- R46 Generated reversal descriptions; the person's note shown with them
- R47 How the automatic reversal is posted
- R48 A reversal dated its target's date stays in period 13 or 14 (provisional)

K. Audit readiness:
- K1 DPAPI machine scope, limit stated
- K2 cryptography library for the recovery wrap
- K3 Broken chain warns; Audit-ready mode blocks
- K4 Auditor sees sensitive fields only if granted
- K5 Restore with a mismatched checksum
- K6 audit_log chaining on the backlog
- K7 ledger.verify permission
- K8 Chain key leaves only in the company bundle
- K9 Auditor starter role
- K10 U5 stands; encryption after v1
- K11 Accountant does not get ledger.verify
- K12 Verification speed targets are benchmarks
- K13 ledger.verify is sensitive
- K14 Checkpoints mirrored in the master
- K15 Incremental verification anchor
- K16 Unavailable is never tampering
- K17 Measured verification speed
- K18 Automatic checkpoints at close and exit

PW. Password recovery:
- PW1 Temporary password expires after 72 hours
- PW2 Who can reset an Admin
- PW3 user.reset_password permission
- PW4 App-generated temporary password
- PW5 Backup codes
- PW6 Installation-level email settings
- PW7 Reset offers new backup codes
- PW8 Throttles
- PW9 Master password changes need the recovery code
- PW10 Password policy additions
- PW11 Prompt to replace admin-issued backup codes

KS. Key store, Phase 2.5 step 1c:
- KS1 cryptography pinned; PyInstaller a developer tool
- KS2 Recovery key-encryption key from hashlib.scrypt
- KS3 get_key matches by fingerprint
- KS4 SecretKey.use_for_aead
- KS5 Valid code, damaged wrap
- KS6 Create company refused while the key is locked
- KS7 Test key hook for create_company
- KS8 Key-lost epoch service in 1c; screen in Phase 3
- KS9 Master key tables not audited
- KS10 The master holds every company's keys
- KS11 Export warning until the key bundle exists
- KS12 Key-lost checkpoint (Key lost / Unverified) written with the epoch
- KS13 A lost installation key can be replaced; installation_key keeps history
- KS14 Status stays OK; every result shows the unverified range
- KS15 Unverified range is a close warning, never a block, with no expiry
- KS16 Rotation after an epoch signs its checkpoint again
- KS17 Typed phrase NEW LEDGER KEY and the company count before replacing
- KS18 A found lost key does not re-verify the old range in 1d
- KS19 Archived companies get an epoch too
- KS20 The replace service lives in installation_keys.py
- KS21 Each installation key's copies are bound to its own row id

CB, CF. Cash basis and cash flow (section "Reports, dimensions, cloud move and bank feeds"):
- CB1 Cash basis is a report view; books stay on accrual
- CF1 Direct-method cash flow statement with account cash flow categories

JD. Job-driven dimensions (same section):
- JD1 A line's job sets its dimensions; locked while the job is on the line (task name J1; J1 is taken)

CM. Moving a company to the cloud (same section; docs/cloud_migration_design.md):
- CM1 "Move to the cloud / Invite your team" keeps every record and a verifiable history
- CM2 Sign-ins move: hashes upgraded at first cloud sign-in, email login, verify once, 2FA for Admins and Master
- CM3 Cloud migration design questions 1-10 answered as proposed

EX. Export (same section; docs/export_design.md):
- EX1 Export design questions 1-8 answered as proposed

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

## KS (continued). Key lost and a new installation key, Phase 2.5 step 1d (decided 2026-11-12)

The step 1d plan was approved with these answers (design: docs/audit_readiness_design.md 2.6, 2.7).
- KS12 A key-lost epoch writes a signed `Key lost` checkpoint (result `Unverified`) in the same company transaction
  that retires the lost key and activates the new one: through the last entry sealed before it, with that entry's
  stored hash as is, signed by the new key, naming the lost key. The master mirror is written afterwards; if it
  fails the epoch stands and the result says so. The verifier reports the range up to it as Unverified (key lost),
  never Broken, and verifies from the next entry. Only the latest epoch counts.
- KS13 The Master can create a new installation key when the old one is lost (password and a typed confirmation, a
  recorded event); every company then enters a key-lost epoch. `installation_key` is append-only history with one
  active row; `company_key` names the installation key that wrapped it.
- KS14 After an epoch the status stays `OK` (or Broken / Unavailable for the new epoch) with `unverified_through`
  and `unverified_reason`. Every verification result shown on a screen, report or export shows the unverified range
  next to it, and the message is never empty when `unverified_through` is set (a test proves it).
- KS15 The unverified range is a warning in the `ledger_integrity` close check in every mode, never a block. The
  note "entries JE-000001 to JE-N cannot be verified" has no expiry: it stays on every close report and export that
  covers those periods, and on the Audit-ready page (replaces "until the next year close").
- KS16 Rotation after an epoch signs its `Key rotation` checkpoint as usual (the full check is OK with the
  unverified range). "Unavailable, no checkpoint" remains only for a key missing with no epoch.
- KS17 Replacing the installation key needs the typed phrase `NEW LEDGER KEY`, after a screen that says every
  company's history up to today will no longer be verifiable and shows how many companies get a new key epoch
  (a Master-only read service returns that count, so the screen and the service agree).
- KS18 A lost key found again later (an old master backup, a found recovery code) is not used to verify the old
  range in 1d; the range stays Unverified. Restoring keys belongs to the backup and key-bundle work (backlog 16).
- KS19 When the installation key is replaced, every company in the registry gets an epoch, archived included, and
  the result lists each one.
- KS20 The replace service is a new module, `modules/services/installation_keys.py`, calling auth's password and
  recovery-code helpers, so auth.py does not grow.
- KS21 Each installation key's recovery copy and DPAPI copy are bound to its own row id plus its fingerprint (key
  id 1 keeps its current binding). A copy from one installation key row is refused on another row (tested).

Added with Phase 2.5 step 4 (approvals in posting), 2026-11-13 (owner's answers to the Step 4 plan):
- R15 A journal entry's approval request stores `document_digest`: SHA-256 (hex) of the entry's canonical form,
  the same form `ledger_chain` seals (posting fields empty), so approval and sealing check the same content.
  Posting refuses unless the newest approved request's digest equals the entry as it is now; resubmission is
  refused until the digest differs from the last rejected one. Required for journal entries in the baseline.
- R16 `approval_request` (insert, update) and `approval_action` (insert) are in the audit log, every column;
  an `approval_request` row is never deleted (trigger). Which status changes are allowed (Pending to Approved,
  Rejected or Cancelled; Approved to Cancelled) is a service rule (H4), not a trigger.
- R17 With `require_separate_approver` = 1 the entry's creator can neither approve nor post it, for every entry
  (also one that needs no approval). Off by default (control, section 0).
- R18 In step 4 an Import-origin entry is approved one entry at a time (document type "Import batch",
  `import.approve`). The review of a whole batch comes with the Imports phase and must still count as the one
  human review (integrity).
- R19 Posting, approval, rejection, period close, books closed through and year close each take `now` and
  `today` from a fresh context built for that action (`companies.action_context`); a static test checks the
  screens. H2 holds: no new clock read in services.
- R20 An entry needs an approved request before it posts when: its origin is Agent or Import (always, whatever
  the controls); it is a manual entry with manual-entry approval on and debits strictly over the threshold, or
  no threshold (R5); or its document source's type has "requires approval" on (1.6). R11's refusals are lifted
  only through approval. An entry with a Pending request cannot be posted directly.
- R21 Any edit or delete of a draft cancels its Pending or Approved request in the same transaction; it must be
  resubmitted and approved from step 1.
- R22 A rejection needs a reason; the rejected request and its action stay for the audit trail. The entry can be
  resubmitted after it has changed (R15).
- R23 Only a Human-origin context approves or rejects (integrity): Agent is also refused by `authorize`
  (`AGENT_ALLOWED` never holds an approve code, `je.post` or `je.reverse`; static test), and Import and System
  contexts are refused by the approval service.
- R24 Posting an approved entry writes `approved_by` and `approved_at` from the last approving action; both are
  sealed in the chain (already hashed fields).
- R25 (owner, STOP 2 answer 2, confirming plan answer 6) The pending xfails `cannot_post_to_header_or_inactive_account`
  (both cases) and `manual_entry_to_controlled_account_is_blocked` are rewritten in step 4 against the real
  services, with the approval xfails R5 and Agent/Import: the controlled-account test is the
  `allow_manual_control_je` = 0 case (R9), and the default (1) posts the line and flags it.
- R26 (owner, STOP 2 answer 1) `App.close_company_ledger`, used at logout and app exit, signs its checkpoint with
  `action_context()`, so the checkpoint records the time the company was closed. Closing never blocks: a context
  that cannot be built is logged and the checkpoint skipped.
- R27 (owner, Step 4 STOP answer 3) No message a person sees contains a permission code. Every refusal says why
  and what to do next; the code is kept in the denial log (`access_event.permission_code`, `auth_event`) only.
  `authz.denial_message(origin, permission, reason)` builds the default sentence from the permission's
  description and the reason for the denial (role, project scope, no access, inactive role or user, archived
  company, wrong file, agent). The AI assistant trying to post is told "The AI assistant cannot post entries; a
  person posts the entry after it is approved." An approver out of step order is told which step comes first,
  by which role, and when they can act; a role that fits no open step is told which role can; a missing or
  exceeded approval limit names the roles whose limit covers the amount, and an Admin. A rejection without a
  reason asks for one "so the preparer knows what to fix". Master-only actions and the user-management refusals
  have their own sentences. tests/test_refusal_messages.py scans every service refusal for code-shaped words
  (two lower-case words joined by a dot, two letters or more each side, so decimals and "e.g." pass; the only
  allowed words are file names ending in .db or .sql) and for a permission put into an f-string, in refusal
  calls, in module-level sentences and in what `*_message` functions return. The AI-assistant sentence is used
  only for a code an agent may never use; an allowed code the user's role lacks gets the role sentence. A user
  without access to a company is told only that (not whether it exists or is archived); the Master is told to
  restore an archived company first.
- R28 (owner, Step 4 STOP answer 1) With `require_separate_approver` on, neither the creator nor the submitter of
  a document may approve or reject it (a logged denial: "...approve the entry you sent for approval; ask a
  colleague..."). With it off, an approval by either is flagged `self_approved` (R3), so the posting gate's
  self-approval check (step 4) also catches the submitter's approval once separation is turned on. Posting's
  creator rule (R17) is unchanged. The baseline comment on `self_approved` is not edited (pre-release hash).
- R29 (owner, Step 4 STOP answer 2) The "only a person may approve" denial (R23) reads the request first, so its
  `access_event` row names the approve permission (`je.approve`, `import.approve`, ...); a missing request is
  denied with no code. It is still denied before any write.
- R30 (owner, Step 4 STOP answer 4) Rejection reasons are never written to the log file. A refusal that quotes the
  reason (posting a rejected entry, resubmitting it unchanged) carries a fixed `log_message` without it
  (`ServiceError(..., log_message=...)`, `errors.log_text`); the file handler's `LogMessageFilter` writes that
  sentence instead of the error's text wherever the error object is logged: as the message, as an argument and
  in the traceback, searching causes, contexts (also after `from None`) and exception groups, so an error that
  quotes a hidden one is cleaned too. The filter cannot see an error's text logged as a string, so a static test
  forbids logger calls that pass an f-string, `str()`, `repr()`, `.args`, `%`/`.format()` text,
  `format_exc()` or a reason, in modules/ and app_strata.pyw. Another static test requires `log_message=` on
  every service error that quotes a reason (any `reason_text(` call). The person still sees the reason; it stays
  in `approval_action.reason`.
- R31 (owner, Step 4 STOP answer 5) `scripts/create_fresh_databases.py --apply --no-prompt` rebuilds without
  asking to create the first Master and exits 0. Input that ends early (a shell that reports a terminal but has
  no input, as Git Bash run by a tool) ends with "No answer was read; no Master was created." and exit 0.
- R32 (owner, Step 4 follow-up answer 1) A failed sign-in never writes the typed username. The log line and
  auth_event name the user id when the typed name matches an account; otherwise the log says "unknown username"
  and the auth_event row has neither a username nor a user id (the event type says what happened). Successful
  events keep the account's own name. The per-username throttle key is HMAC-SHA256 of the stripped, case-folded
  name under a 32-byte installation secret (`throttle_secret` in the master, made on the first failure), so
  case variants share one counter, and a new username may not match an existing one ignoring case (two accounts
  differing only in case would share a counter); Master recovery keeps the fixed key '#recovery'. Limit, stated: the secret
  is in the same file, so someone holding the master file can test guesses against a stored key, and an HMAC
  guess is cheap (unlike scrypt); the names are not readable and cannot be matched against a ready-made list. To
  keep that window short, a throttle row with no failure and no lock for a day is deleted (on the next failure
  or successful sign-in), so a password typed into the username box stays as a hash only until a day has passed and someone
  next signs in or fails.
  The secret is held as a `SecretKey` (redacted repr, no pickling). The DPAPI-held installation key was not used
  because sign-in must stay throttled while the key store is locked (KS12).
- R33 (owner, Step 4 follow-up answer 2) `app_strata.pyw` calls `start_logging()` before the window: the log
  file is `DATA_DIR\Logs\strataledger.log`, rotating at 1 MB with five backups, with the R30 filter. If it cannot
  be opened the app still starts and says so once: "The log file could not be opened, so errors will not be
  recorded; check that the data folder can be written."
- R34 (owner, Step 4 follow-up answer 3) An approval-limit refusal names only roles whose limit covers the amount
  and that at least one active user other than the Master holds in the company (the nearest access row, as in
  the access check; Deny holds nothing). If none is left it says to ask an Admin ("...ask an Admin to set one or
  to approve it." / "...ask an Admin to approve it.").
- R35 (owner, Step 4 follow-up answer 4) A database error that reaches `tx.write_transaction` (any service
  write, posting included) is rolled back, logged with its details, and raised as `SaveFailedError` with no
  cause attached: "Something went wrong saving this; nothing was saved. The details are in the log." Services
  that turn a known database error into their own sentence still do so inside the transaction. Service errors
  and programming errors pass through unchanged.
- R36 (owner, Step 4 follow-up answer 5) For anyone but the Master, access decides the sentence before the file
  does: a user without access (no row, or a Deny row) is told only that they have no access, even when the
  company file is also the wrong one. A user with access, and the Master, are told the file is not the registered one. The file check
  still comes before anything reads or writes the company file: a wrong file is never given an access_event row
  (the log line records it), whichever sentence the user gets.
- R37 (owner, 2026-11-13, answer to the R34 question) When require_separate_approver is on (or the company has no
  settings row, the safe default), the approval-limit refusal leaves the request's creator and submitter out when
  it counts who holds a role that could approve: they may not approve it (R17, R28). If no holder is left, it
  says to ask an Admin. With separation off they count as before. Applies to approve and reject.
- R38 (owner, 2026-11-13) Every logger in the app is `strataledger` or under it, so its lines reach the log
  file and pass the R30 filter; `modules/font_loader.py` moved to `strataledger.fonts`. A static test checks
  every `getLogger` call in `app_strata.pyw` and `modules/`. Paths in the log are not redacted now; support
  bundles redact them (roadmap backlog 19).
- R39 (owner, 2026-11-13, answer to the R37 question) With separation on, the approval-limit refusal's "ask"
  target also leaves out the request's creator and submitter (R37 already leaves them out of the role holders).
  In order: "another Admin" when one of them is an Admin and another active Admin holds the Admin role in the
  company (by the nearest-row rule; a Deny row holds nothing); "an Admin" when neither of them is an Admin and an
  active Admin exists (the wording is unchanged); otherwise "the Master" when the Master is active and is neither
  of them; otherwise, if no role holder is left either, the whole refusal is "No one else in this company can
  approve it; add another approver, or turn off separation of duties in Settings > Controls." (also when the role
  has no limit row). Role holders who are left are still named ("someone in the Controller role or the Master";
  "someone in the Controller role" when no Admin or Master is left). With separation off, nothing changes.

## Reports, dimensions, cloud move and bank feeds (decided 2026-11-13)

Owner decisions from the planning chat on 2026-11-13, recorded in the design batch. Each item names the design
doc that carries the detail.

### CB. Cash and accrual basis

- CB1 (owner, 2026-11-13) Cash and accrual basis.
  - The books are always kept on accrual. Cash basis is a report view only: nothing posts differently and the
    ledger chain is unaffected.
  - Every financial report has an Accrual / Cash switch, separate from and combinable with the A1 basis
    (Pre-adjustment, GAAP, Tax, Management). A company setting picks the default. Every report and export is
    labelled with both bases.
  - Cash view: invoice revenue and bill expense are recognized on the date each payment is applied, prorated
    across the document's lines by the paid share, so jobs and dimensions stay correct. Unpaid AR and AP, and
    the revenue and expense behind them, drop out. Credit card purchases count as paid on the card date. Sales
    tax follows the paid share.
  - Non-cash entries are removed: depreciation, percentage-of-completion adjustments, accrued payroll, deferral
    and prepaid amortization, and auto-reversing accruals together with their reversals.
  - Prepaid payments are expensed on the date paid, to the account they would amortize into. Deferred revenue
    received is revenue on the date the cash was received. Customer deposits held in a deposit account stay a
    liability until applied.
  - Fixed asset purchases stay on the balance sheet at cost (no depreciation in the cash view).
  - Manual journal entries to AR or AP stay in and are flagged on the report. Retainage receivable and
    retainage payable drop out until paid.
  - Later: a per-company list of accounts excluded from the cash view.

### CF. Cash flow statement

- CF1 (owner, 2026-11-13) Cash flow statement, direct method, management view.
  - Direct method, for lenders and investors. Operating activities show gross cash receipts and payments by
    category: received from customers, paid to vendors and suppliers, paid to employees, interest paid, taxes
    paid, other operating. They total to the cash-basis net income (CB1), shown as a check line.
  - Then investing (fixed assets purchased or sold) and financing (loan proceeds, loan principal repaid, owner
    contributions and draws), plus other balance-sheet cash movements (deposits held, sales tax collected vs
    remitted, payroll liabilities, credit card balance change). Beginning cash plus the net change equals ending
    cash.
  - Every operating account maps to one of the operating categories, defaulted from its account type and
    changeable with an audit entry.
  - Cash means bank, petty cash and undeposited funds accounts. Transfers between them are excluded.
  - Every balance-sheet account has a cash flow category (operating, investing, financing, cash), defaulted from
    its type and control type (fixed assets: investing; loans and equity: financing; bank: cash) and changeable
    with an audit entry.
  - The tie-out to the ending bank and cash balances is checked, never forced: anything unclassified shows on an
    Unclassified line with drill-down, and a non-zero Unclassified line is a close-checklist warning (L2).
  - Every line drills down to its entries and documents. The statement exports to Excel with its basis and
    period labelled, and supports period comparison. A GAAP indirect-method statement is a possible later
    report.

### JD. Job-driven dimensions

- JD1 (owner, 2026-11-13; the owner's task called it J1, renamed because J1 is the KPI calc mode decision) Job-driven
  dimensions. When a document line has a job (project), the line's dimensions are taken from the job's dimension
  settings and cannot be edited; with no job, the line's dimensions are editable.
  - Only the dimension types the job defines are locked; the others stay editable.
  - The job is per line. A document may carry a default job that fills new lines.
  - Drafts follow changes to the job's dimensions; sent or posted documents keep the values they were posted
    with.
  - No override: to change a job line's dimensions, change the job's settings or remove the job from the line.
  - Applies to invoices, bills, journal entry lines and time entries, through one shared service function that
    resolves a line's dimensions; screens only display the result.
  - Clearing the job unlocks the dimensions and keeps the previous values as a starting point.
  - "Require dimensions on lines without a job" is a future control, off by default (section 0).

### CM. Moving a company to the cloud

Design: docs/cloud_migration_design.md.
- CM1 (owner, 2026-11-13) The desktop app offers "Move to the cloud / Invite your team", which moves a company into
  the hosted version (PostgreSQL on Azure, P5), keeping every journal entry, contact, job and attachment, with the
  history still verifiable. Easy to find but never nagging (section 0b).
- CM2 (owner, 2026-11-13) Sign-ins move as seamlessly as possible.
  - Accounts, roles, company access and approval limits move automatically.
  - The desktop password keeps working: the scrypt hash is moved and upgraded to the cloud scheme at the first
    cloud sign-in. Users sign in with their email address.
  - Each user verifies their email once. Two-factor sign-in is required for Admins and the Master and offered to
    everyone else.
  - Recovery codes, backup codes and temporary passwords do not move; the cloud uses normal account recovery.
  - The pre-flight lists any user without an email address and blocks the move until each has one.

### B (continued). Bank feeds

Design: docs/bank_feeds_design.md.
- B11a (owner-approved 2026-11-11, recorded 2026-11-13; amends B11 "no live feeds in v1")
  - v1.0 ships the feed seam only: a provider interface, a shared staging path, and the file import (CSV,
    OFX/QFX) as the first provider. No live connection ships in v1.0.
  - v1.1 ships the Ramp provider (card and payables data, customer-supplied API credential).
  - Aggregators (Plaid-style) are later, as an optional add-on where the customer supplies their own credentials.
    A hosted relay belongs to the hosted product (and becomes natural there, P5).
  - Reason: a desktop installer cannot safely hold a vendor-wide secret.

### Design batch accepted (owner, 2026-11-13)

The owner accepted the design batch and answered every open question in the three new design docs as proposed.
Each doc's question section holds the answers; read them there.
- CM3 docs/cloud_migration_design.md section 10, questions 1-10, as proposed: legacy hashes kept 90 days; the
  Master becomes the company's Owner; a company user map keeps desktop user ids; an unconfirmed move expires after 7
  days; no move back in this feature; one company per move; only the Master starts a move; the desktop is not
  locked during upload (the switch is refused if anything changed); a breached-password check at the first cloud
  sign-in where the identity provider offers it; the package is a ZIP with fixed member names.
- BF1 docs/bank_feeds_design.md section 14, questions 1-6, as proposed: secrets in encrypted files under
  `DATA_DIR/Secrets/` keyed from the installation key; a 60-minute sync timer per company; Ramp card lines in
  both the holding area and the statement lines; no write-back to Ramp in v1.1; a 45-day re-read window, to be
  confirmed; `bank.reconcile` and `bank.unreconcile` added with bank reconciliation. Added: a test requirement
  that a Ramp card charge is never booked twice (holding-area entry vs statement line; section 12).
- EX1 docs/export_design.md section 14, questions 1-8, as proposed: XlsxWriter writes and openpyxl reads; exports
  go to `Exports/<company code>/` through storage with "Save a copy as..."; 250,000-row Excel limit, a
  confirmation above 50,000, CSV streamed; `SUBTOTAL(9, ...)` totals; Excel dates in the company format and CSV
  in ISO; a `Report export` checkpoint for journal-based reports only; the Auditor gets `report.export` when its
  template exists, Viewer does not; full-width trigger characters neutralized.

Added with Phase 2.5 step 5 (reversals and automatic reversals), 2026-11-13 (owner's answers to the Step 5 plan, all
as proposed):
- R40 A person may void or correct a posted entry whose source is manual (none, Manual, Adjustment), Import, Payroll
  or Conversion. An entry from a document (Invoice, Bill, Payment, Deferral, Completion) is refused with a sentence
  that says to void the document instead; the documents' own void services (Phase 4; B14 for payments) use the
  narrow ledger path (docs/audit_readiness_design.md section 13).
- R41 A Void is dated the original's date by default and may be any later date in an open period, never earlier. In
  a pair void (R4) each Void is dated its own target's date, so if either period is closed nothing is written. A
  Correction is dated today by default and may be any date on or after the original's.
- R42 A void or correction needs only `je.reverse` (and `confirm=True`, R2), not a second person: separation of
  duties (R17) does not apply to the reversal actions, which create and post in one audited action. A control
  "voids and corrections need a second person" (off by default, listed on the Audit-ready page) is on the backlog
  (roadmap item 21), not built.
- R43 A reversal of any kind cannot itself be voided or corrected; a person enters a new entry to change its effect.
- R44 An entry that has an automatic (Accrual) reversal cannot be corrected: void it (both are voided together, R4)
  and enter a new accrual.
- R45 A reversal mirrors its original line by line, dimensions included. The service checks the dimensions and a
  test proves it; the baseline trigger, which compares accounts, contacts, projects, cost codes and deferrals but
  not dimensions, is not changed (H4).
- R46 Generated descriptions: "Automatic reversal of JE-000012: <original description>", "Void of JE-000012: ..."
  and "Correction of JE-000012: ...", with the original's reference. The person's reversal note is kept in
  `reversal_note` and shown with the generated description: `get_entry` and `list_entries` return a
  `display_description` that holds both ("Void of JE-000012: Rent (note: wrong account)").
- R47 The automatic reversal (L5) is posted in the same transaction as its original, right after it: origin System,
  created and posted by the person who posted the original, the original's source, no approval fields and no
  confirm (R2); the original's approval covers it because the digest includes `auto_reverse_date`. If the reversal
  date has no period, or its period is closed, the whole post is refused before anything is numbered.
- R48 (Step 5 review, 2026-11-13; PROVISIONAL, built this way and waiting for the owner's confirmation) A Void or
  Correction dated its target's own date, when the target is in adjustment period 13 or 14, is posted in that same
  period, with no date warnings (R12), so the Pre-adjustment, GAAP and Tax bases each net to zero. A later date
  takes the month period that holds it. Without this, a Void of a period-13 entry would land in period 12 (and be
  refused once period 12 is closed, which also blocked a period-13 accrual's pair void for good).

