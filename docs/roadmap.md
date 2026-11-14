# Roadmap

Moved unchanged from CLAUDE.md (section 7 plan and section 9) on 2026-11-12. CLAUDE.md section 7 keeps one
paragraph saying where the project stands; update both when a step is finished.

**Release plan (DECIDED 2026-11-11; docs/decisions_2026-11-11.md E1):**
v1.0 core accounting, then v1.1 construction, then v1.2 AI Copilot.
- **v1.0:** core accounting (Phases 2 to 5 below), plus fixed assets, loans and
  vendor refunds. Report presets with offline keyword matching (section 6).
  Required before v1.0: an action that issues the Master a new recovery code (after re-entering the password),
  because a code that was lost or never saved cannot be recovered today (backlog item 11).
  Final v1.0 task: **Help content.** Write the `help/*.md` guide set per
  docs/help_system_design.md sections 4-5, after all v1.0 modules are finalized
  and tested and before the installer build.
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
    Build order: step 1 (done), step 2 (done), **step 1b** (done: chain schema and the pure `ledger_chain.py`,
    docs/audit_readiness_design.md section 14), step 3 (posting seals every entry inside the posting
    transaction through the `KeyProvider` interface: a fixed key in tests, posting refused when no real key
    is available; done), **step 3b** (done: the verify service, incremental and full verification,
    checkpoints mirrored in the master, the `ledger_integrity` close check, end-to-end tamper tests), **step
    1c** (done: keystore: installation and company keys, DPAPI, recovery-code wrap, rotation, key-lost epoch),
    next **step 1d** (decided 2026-11-12, plan in docs/next_step.md): (1) a key-lost epoch writes a signed
    checkpoint that records the history before it as Unverified (key lost), and the verifier reports that range
    as Unverified, never Broken, and verifies the new epoch from its first entry; (2) the Master can create a new
    installation key when the old one is lost (password plus a typed confirmation, a recorded event), and every
    company then enters a key-lost epoch automatically; data stays readable and posting continues under new
    keys. Both baseline changes in one edit (previous baselines saved to archive/ with a tag, one rebuild).
    Done: the baseline edit and rebuild, part (1) the key-lost checkpoint and verifier (KS12, KS14-KS16) and
    part (2) replacing a lost installation key (KS13, KS17-KS21, `installation_keys.py`); screens in Phase 3.
    **Step 4** (done 2026-11-13, R15-R26): approvals in posting: submit for approval with the entry's digest,
    posting only with an Approved request that matches the entry, chains and limits, edits cancel, rejection
    needs a change, separation also covers posting, a fresh context per action, the last approver sealed.
    Then steps 5-7. Step 1c landed before any screen can post; 2.5 is not done until steps 5-7 are.
    Accepted until step 2.8: the Master can change the password without the recovery code
    (`auth.change_password`).
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
  Rule for every screen built or changed in this phase: it declares a stable
  `page_key` (docs/help_system_design.md section 3), and a screen is not
  finished without one.
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
   AR/AP aging. Also (decided 2026-11-13): the Accrual / Cash switch on every financial report (CB1) and the
   direct-method cash flow statement (CF1), both v1.0, both exported per docs/export_design.md. For them to
   work the data must keep: each payment allocation's date, amount and the invoice or bill it pays (the line
   split is computed from the document's posted lines); each account's cash flow category (Operating,
   Investing, Financing, Cash) and operating sub-category (customers, vendors, employees, interest, taxes,
   other); a marker on every non-cash entry (depreciation, POC, accrued payroll, amortization, auto-reversing
   accruals); and the loan principal vs interest split of each loan payment (docs/loans_design.md).
   Not in the baseline today (report only; to be added with failing tests first when the reports are built):
   (a) `payment_allocation` has no date of its own, so a payment applied later than its payment date (B4
   unapplied payments, B6 credit memos) has no apply date; it also has no credit-memo or loan target (B6,
   docs/loans_design.md). (b) `account` has no cash flow category or operating sub-category. (c) No marker for
   petty cash or credit card accounts: `control_type` has `Undeposited funds` only, banks are known through
   `bank_account`, cards only through `company_settings.credit_card_clearing_acct_id`. (d) Non-cash entries
   cannot all be told apart: `journal_entry.source` has no depreciation or POC value (the meaning of
   `Completion` is not documented) and B13 `source_doc_type` / `source_doc_id` are not in the baseline;
   auto-reversing accruals are known (`auto_reverse_date`, `reversal_reason = 'Accrual reversal'`). (e) The
   loan principal / interest columns (`invoice_line.loan_line_type`, `journal_line.loan_id`) wait for the
   loans step. (f) `company_settings` has no default report basis setting.
7. Backup/export, installer, licensing.
8. (Done in Phase 2.6: customer and vendor codes.) Still open: the wizard
   shows the code (Phase 3).
9. After Phase 4, unscheduled: (a) pipeline, stages, stage history and the
   signing function; (b) CRM basics and collaboration; (c) service cases and
   the Customer Support pipeline; (d) throughput and profit views.
See docs/crm_pm_design.md section 11.
10. Philippines tax module (VAT, withholding, certificates, filing tracker,
    e-invoicing) as the `ph_tax` add-on, a separate add-on after v1.0: designed, not built. Needs a
    Philippine tax professional's review before it ships.
11. Issue a new Master recovery code (REQUIRED BEFORE v1.0): a service that, after the Master re-enters the
    password, replaces the recovery code and shows the new one once. The first-run screen asks for confirmation if
    the window is closed before the first code is saved, but a code lost later cannot be recovered without this.
    Once the keystore exists (2.5 step 1c) this action must also re-wrap the installation key with the new code
    (docs/audit_readiness_design.md section 2.7). Designed in docs/password_recovery_design.md section 3 (the
    recovery code is required for every Master password change and a new one is issued each time).
12. DONE (49c9ac3): wire a `page_key` into the New Company screen (`views_new_company.py`, `setup.new_company`),
    as the first-run screen already has (`setup.first_run`); see docs/help_system_design.md section 3.
13. Chain `audit_log` like the ledger (decision K6; docs/audit_readiness_design.md).
14. Speed up ledger verification toward the K12 targets (decision K17): build the canonical form with less
    per-field work, and index or narrow the whole-ledger void and truncation queries so an incremental check
    stays fast as the ledger grows. Measure with `tools/benchmark_ledger_verify.py`. Whatever the speed, every
    screen that starts a full verification (Ledger integrity, period and year close, Books closed through,
    backups) runs it in the background with progress and a responsive window (docs/audit_readiness_design.md 2.6).
15. Review draft/ui-mockups (design-chat mockups plus unreviewed Theme/ui_components changes) at the start of Phase 3.
    The current mockups live in C:\Users\marka\StrataLedger_mockups (the copy on the draft branch is older).
16. With the backup step (Phase 5): the passphrase-protected company key bundle (Master only, K8), so an exported
    or backed-up company can be verified on another computer; then drop the `EXPORT_NOT_VERIFIABLE` warning
    (KS11). Every company backup also backs up `system_master.db` (KS10).
17. Restrict the data folder (`%PROGRAMDATA%\StrataLedger`) at install or first run so other local accounts
    cannot read `system_master.db`: today it keeps the inherited permissions, and the machine-scope DPAPI copy of
    the installation key opens for any local user who can read it (secrets audit of Step 1c; audit design 1).
    Decided 2026-11-12: built in the installer (Phase 5), REQUIRED BEFORE v1.0.
18. A start-up check that warns the Master when the data folder is readable by all users of the computer (with
    backlog 17, so a folder copied or created outside the installer is caught).
19. Support bundles (when built) redact absolute paths and the Windows profile name from the log files before
    they leave the computer (owner, 2026-11-13; the log itself keeps them; R38).

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

## Open decisions (CLAUDE.md section 9)

1. Payroll posting: import the payroll system's own journal (recommended) vs.
   reclass from a payroll clearing account. Also whether payroll imports get
   the same hold-and-approve step as Ramp.
2. Period-end accrual for labor worked but not yet in a payroll run.
3. A bill whose amount differs from its advance payment: flag for review
   (current plan) vs. post the difference to a variance account after
   approval.
4. ANSWERED: a company file stores master user ids (`created_by`,
   `approved_by`, `audit_log.user_id`) as plain INTEGER with no cross-file FK.
5. ANSWERED: `app_user` exists only in `001_master.sql`; each company file has
   its own `audit_log`, and the master has one for master-level events.
6. RESOLVED for desktop: customers bring their own key (Gemini first; see
   docs/ai_copilot_design.md).
7. CRM / project design open questions: see docs/crm_pm_design.md section
   12 (optional case fields, linear stages, warranty length, pausing cases,
   prospect in the wizard, closing checklist, desktop to hosted sync).
