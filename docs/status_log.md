# Status log

Dated history, moved unchanged from CLAUDE.md section 7 on 2026-11-12. Append one entry at the end of each
step. Branch names in the entries before the fresh-history repository (`phase1-ledger-integrity`, `master`,
`phase2-service-layer`) belong to the old local repository, not to this one. Nothing here is an instruction.

## History (CLAUDE.md section 1)

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
- The schema grew into the baseline in `migrations/` (section 5).
- Current work: see section 7 (the service layer comes first; the legacy
  screens are rewritten on top of it in Phase 3; the AI coworker is v1.2).

## Log

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
- 2026-11-12: First-run setup (decision S10). At startup `first_run_model.startup_check` routes: missing or no users
  -> the Welcome screen (nothing is built before the user presses Create Master), ready -> the launcher, unreadable
  (not a database, older baseline, damaged) -> an error dialog that names the file and closes the app without
  touching it. Invalid input builds no file; if the file is built but the Master cannot be created, the next launch
  shows setup again. Password and recovery code are held only until the sign-in and the screen then drops its
  references to them (it does not overwrite the memory); neither is ever logged; Continue clears the clipboard if
  it still holds the code, with or without dashes. `create_fresh_databases.py` is unchanged (a developer tool).
- 2026-11-12: S10 follow-up. Password maximum boundary tested (1023 and 1024 accepted, 1025 rejected). The Copy button
  on the recovery-code screen goes through `platform_support.copy_secret_text` (Windows clipboard-history and cloud
  exclusion requested, Tk fallback), the code screen adds a line that a copy may remain in clipboard history on some
  systems, and backlog item 12 (page key for the New Company screen) was added.
- 2026-11-12: Phase 2.5 step 1 (baseline additions; decisions R1-R9 in docs/decisions_2026-11-11.md). The
  previous baseline is kept in `archive/baseline_pre_2_5/`. `journal_entry`: source `Conversion`,
  `auto_reverse_date` (after the entry date, never on a reversal), `reversal_note` (required, non-blank, for Void
  and Correction; only on reversals); `reverses_entry_id` is no longer UNIQUE but has two partial unique indexes
  (one Void-or-Correction and one Accrual reversal per entry). `journal_line`: `is_control_override` and
  `is_rounding_adjustment` (0/1, default 0). Both locks and the journal audit triggers cover the new columns.
  `payment_allocation` names exactly one of invoice or deferral (CHECK). New close check `control_overrides`
  (warning). No services yet.
- 2026-11-12: Phase 2.5 step 2 (ledger core): `modules/services/ledger.py` with `create_entry`, `update_entry`,
  `delete_entry`, `get_entry`, `list_entries` for DRAFT entries, the single line check `check_lines` (and
  `check_entry_lines` for posting to re-run on stored lines), and the entry period taken from
  `periods.resolve_entry_period`. A draft in a closed period is refused. Human and Agent drafts may only use the
  manual sources (none, Manual, Adjustment); Import and System origin may use the others. `ledger.py` is the only
  file allowed to write `journal_entry`, `journal_line` or `entry_number_sequence` (static test). Posting, numbering,
  approvals, reversal and rounding are steps 3-6.
- 2026-11-12: Audit readiness design (`docs/audit_readiness_design.md`), decisions K1-K10 and P5 (hosted target
  PostgreSQL on Azure). Docs only. The 2.5 build order now runs 1b (chain schema), 3 (posting with sealing),
  1c (keystore) before steps 4-7.
- 2026-11-12: Phase 2.5 step 1b (ledger chain schema; previous baseline in `archive/baseline_pre_2_5_1b/`).
  `journal_entry`: `chain_version` (1), `chain_key_id` (FK), `chain_prev_hash`, `chain_hash` (64 lowercase hex),
  all NULL on drafts and all set once posted, locked after posting, in the audit JSON; unique seal. New
  `ledger_chain_key` (fingerprint only, one active, retire once, never deleted, audited) and `ledger_checkpoint`
  (append-only, MAC, audited). Close check `ledger_integrity` (warning). No trigger checks the previous hash or
  the key: `modules/services/ledger_chain.py` (pure: canonical form, `seal`, `fingerprint`, `new_key`,
  `verify_chain`, column classification) does, with hand-written golden vectors in
  `tests/data/ledger_chain_vectors.json`. Test helpers seal every post with a fixed test key. Decisions K11, K12.
- 2026-11-12: Phase 2.5 step 3 (posting). `ledger.post_journal_entry`: `je.post`, `confirm=True` for Human origin
  (R2), stored lines and period checked again, balance and two lines, date warnings for Human posts
  (`DateWarningsError`, `acknowledge_date_warnings`), controlled accounts (flag `is_control_override` before
  sealing, refuse when the control is off, AR/AP lines name the customer/vendor; R10), then in one transaction:
  lock, read and increment the counter, seal with the company's chain key, one UPDATE. Fails closed until step 4
  for anything needing approval and refuses reversals and automatic reversals until step 5 (R11).
  `modules/services/keys.py`: `KeyProvider`, `NullKeyProvider` (the default: no posting), `FixedKeyProvider`
  (tests only, `STRATALEDGER_ALLOW_TEST_KEYS`), `SecretKey`. `periods.entry_date_warnings`; close check
  `control_overrides` built and `ledger_integrity` registered (runs from step 3b). Decisions R10-R14. Until step
  1c the app has no real key provider, so nothing can be posted outside the tests.
- 2026-11-12: Phase 2.5 step 3b (verification; previous baselines in `archive/baseline_pre_2_5_3b/`).
  `modules/services/ledger_verify.py`: `verify_ledger` (full / incremental, read-only reads, results OK / Broken /
  Unavailable with reason codes Link, Hash, Gap, Void mismatch, Key fingerprint, Truncated, Marker, plain
  messages), checkpoint rows with a MAC (`ledger_chain.checkpoint_mac`) in the file and mirrored in the master
  (new master table `chain_checkpoint`), and the `ledger_integrity` close check (full, once per close action).
  Permission `ledger.verify` (sensitive; Admin, Controller). `ServiceContext.read_only`; `write_transaction`
  refuses company writes from it. Key provider `get_key(company_id, key_id)`. `tools/benchmark_ledger_verify.py`.
  Decisions K13-K17.
- 2026-11-12: 3b follow-up: `ledger_verify.checkpoint_on_close` signs a checkpoint (file and master) when a company
  is closed (logout) and at app exit (`App.close_company_ledger`, `App.on_app_exit` on WM_DELETE_WINDOW). Decision
  K18.
- 2026-11-12: Password recovery design (`docs/password_recovery_design.md`, docs only): v1.0 Admin/Master reset and
  personal backup codes, the Master path after step 1c, email last, TOTP v1.1. Proposed build step "2.8 Password
  recovery" after 2.5; screens in Phase 3.
- 2026-11-12: Small fixes (7e7af5c). `views_dashboard.PAGE_KEY = "customers.dashboard"` and `tests/test_page_keys.py`
  (every view's PAGE_KEY equals the key the sidebar and `App.navigate_to` route to it; the routes table must list
  every sidebar key). The Copilot worktree and its two branches were removed. Period close, Books closed through and
  year close sign their full verification as a `Period close` / `Year close` checkpoint (file and master) after the
  close commits (`ledger_verify.record_close_checkpoint`; a failed write is logged and reported, never undoes the
  close).
- 2026-11-12: Password recovery decisions PW1-PW11 (35e2bb1; docs/decisions_2026-11-11.md; design section 12
  updated). The proposals were accepted with two changes: an Admin reset offers "Also make new backup codes", ON by
  default (PW7), and a user whose backup codes were made by an Admin is prompted at each sign-in to make their own
  set (PW11).
- 2026-11-12: CLAUDE.md restructured (docs only): the dated history moved here, the plan to docs/roadmap.md, the
  design decisions to docs/design_decisions.md, the long file map to docs/file_map.md, and path-scoped rules to
  `.claude/rules/`; accuracy fixes to CLAUDE.md, docs/CLAUDE_UI.md, `.github/copilot-instructions.md` and the
  agent files.
- 2026-11-12: Design-chat mockups and unreviewed Theme/`ui_components` changes parked on the local branch
  `draft/ui-mockups` (not pushed; backlog 15).
- 2026-11-12: Review fixes to the close checkpoints and page keys. `record_close_checkpoint` never raises after the
  close has committed: a refused permission is logged and reported in `checkpoint_error` like a failed write. It
  signs only a period or year that is closed and a verification whose chain hash is the stored one. A checkpoint
  saved in the company file but not the master says so (`CHECKPOINT_PARTLY_SAVED`). `tests/test_page_keys.py` now
  runs the app's real router on a stand-in window and reads off which view module each sidebar key opens and
  which row it marks active, instead of a hand-written table.
- 2026-11-12: Mutation check of the close checkpoints (44 mutants, 36 killed); tests for the five real gaps
  (fbbabe2). A verification or close that signs no checkpoint now always says why in `no_checkpoint_reason` (no
  ledger key on this computer, no active key in the company, or the write failed); it is never silent.
- 2026-11-12: `export_company` returns a warning that the copy cannot be verified on another computer (KS11,
  e89d214). Key store decisions KS1-KS11 recorded (971ca70).
- 2026-11-12: Step 1c sub-step 1: `cryptography==50.0.2` pinned in requirements.txt (Apache-2.0 OR BSD-3-Clause,
  OpenSSL 4.0.3 built in); `requirements-dev.txt` holds pytest and PyInstaller 6.22.3. A one-file PyInstaller
  build runs AES-GCM and scrypt (+3.7 MB); `tools/check_frozen_crypto.py` repeats the check.
- 2026-11-12: `mockups/` moved out of the repository to C:\Users\marka\StrataLedger_mockups (21 files, hashes
  checked); roadmap backlog 15 says so (602e7dd). `draft/ui-mockups` unchanged (older copy).
- 2026-11-12: Step 1c sub-step 2: `platform_support.machine_protect` / `machine_unprotect`, DPAPI machine scope,
  no prompt, label `DPAPI_ENTROPY`; every failure is `MachineKeyError` with fixed text (b844825).
- 2026-11-12: Step 1c sub-step 3: `modules/services/key_wrap.py`, the only importer of `cryptography`: AES-256-GCM
  `wrap_key` / `unwrap_key` bound to the row by associated data, `recovery_kek` (scrypt with its own salt behind a
  label, KS2); `SecretKey.use_for_aead` (KS4); `passwords.normalize_recovery_code` (9fe2260).
- 2026-11-12: Step 1c sub-step 4: master baseline gains `installation_key` and `company_key` (no audit triggers,
  KS9), the key `auth_event` types and `auth_event.company_id`. The development master was rebuilt (the old file
  is in Backups/); `Companies/COMBUZZ.db` is untouched and no longer registered.

## Known issues as recorded on 2026-11-12 (full text)

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
  first Master is created by the first-run screen (S10), or in the terminal by
  `scripts/create_fresh_databases.py --apply`; companies are created through
  the New Company screen or `scripts/create_fresh_databases.py --sample-company
  CODE --apply` (a construction-template test company made with the existing
  Master; it does not rebuild the master).
- Nothing calls `logging_setup.configure_logging()` when the app starts, so the
  `strataledger` logger has no file handler and rule 12's log file is not
  written by the running app (only by tests).
- The context returned by `open_company` is kept for the whole session, so its
  `now` and `today` are the time the company was opened. A screen must get a
  fresh context for each action before it posts, closes a period or approves
  (posted_at is sealed into the chain). Not built yet.
- The launcher's "Open Existing Ledger File" button passes a file path where
  `open_company` expects a company id, so it always ends in "No such company",
  and it runs the baseline runner on the chosen file before any sign-in. The
  launcher list also shows archived companies (it reads `company_registry`
  itself instead of calling `companies.list_companies`). Phase 3.
- `modules/ui_components.py` was never imported by the app before 2.4 Part 2 and had two missing tokens
  (`Theme.warning_glow` and `Theme.radius_lg`, now added) plus `Theme.create_scrollbar`, which still does not
  exist (used by `DataTable`), and hardcoded hex colours in the modal's badge styles. Phase 3 fixes them when the
  other screens adopt the shared components.
- The tests share one hidden Tk window (`tk_app` in `tests/conftest.py`): several Tk roots in one process
  intermittently fail on Windows.
- The seven tests that use the real Windows clipboard (`tests/test_platform_support.py`, marker
  `live_clipboard`) are deselected by default because another program can change the clipboard mid-test; run
  them with `STRATALEDGER_LIVE_CLIPBOARD=1` when changing `platform_support.py`.
- `users.create_user` copies the role code into the legacy free-text
  `app_user.role`, which only the sidebar reads; `app_user.role` and the
  `role = 'Master'` half of the one-Master triggers are removed from the
  baseline in Phase 3. The user profile screen still saves name and email with
  raw SQL until Phase 3 (the password part calls `auth.change_password`).
- A development database built from an older baseline is blocked by the
  baseline guard until it is rebuilt (section 6, "Fresh start").
- The sidebar's `NAV_ITEMS` role tuples (`app_strata.pyw`) hide items by role
  name. Replaced by permission-based visibility in Phase 3; the service layer
  enforces and the UI only hides (rule 10).
