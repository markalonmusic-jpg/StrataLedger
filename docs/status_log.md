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
- 2026-11-12: Step 1c sub-step 5: `auth.create_first_master` makes the installation key in the Master's
  transaction (`key_store.create_installation_key`): a DPAPI copy through the `machine_wrap` the first-run screen
  passes (`platform_support.DPAPI`) and a recovery-code copy. A DPAPI failure still creates the Master, with the
  key locked (`FirstMaster.ledger_key_locked`); a failed recovery copy creates nothing. An installation that has a
  key refuses a second first run (it used to upsert the recovery row after a wiped user table).
  `key_store.LocalKeyProvider` unlocks at start-up; `KeyStoreLockedError` added (2440664).
- 2026-11-12: Step 1c sub-step 6: `create_company` asks the provider for the company's first chain key before it
  builds anything (a locked or absent key store refuses with KS6's sentence and nothing is created), writes the
  active `ledger_chain_key` row in the file, and stores the wrapped key (`company_key`) and a `Ledger key created`
  auth_event in the registry's master transaction. `LocalKeyProvider.get_key` finds the key by the file's
  fingerprint (KS3). The app calls `App.start_key_store()` before the launcher and after first-run sign-in.
  The suite's test switch `key_store.use_test_key_for_new_companies` (only with STRATALEDGER_ALLOW_TEST_KEYS=1,
  KS7) is on for every test via tests/conftest.py. Posting works through the service outside tests from here;
  there is no posting screen yet. A real-DPAPI test runs first run, start-up, create company, post and verify.
  (f46d58b)
- 2026-11-12: Step 1c sub-step 7: every new Master recovery code re-wraps the installation key in the same
  transaction: `recover_master` (also restores the DPAPI copy for this computer; KS5 result when the copy is
  damaged), `change_master_password` (PW9: password and code) and `issue_recovery_code` (backlog 11: password,
  DPAPI copy opens the key; refused while locked). All return `CodeIssued`. The first-run code screen says
  plainly when the key could not be saved for this computer (`first_run_model.KEY_LOCKED_NOTICE`), and
  `scripts/create_fresh_databases.py` now passes the DPAPI wrap too (3cf790b).
- 2026-11-12: Step 1c sub-step 8: `ledger_keys.rotate_chain_key` (Master only): full check under the current key,
  new wrapped key in the master, old key retired as `Rotation`, new key active, `Key rotation` checkpoint signed
  with the new key. Entries after it chain across keys and every entry still verifies. `ledger_verify` gains
  `check_before_key_change` and `record_key_checkpoint` (4dabaa6).
- 2026-11-12: Step 1c sub-step 9: `ledger_keys.start_new_key_epoch` (Master, company code typed): a lost company
  key is retired as `Key lost` and a new one becomes active, so posting goes on; old entries stay readable and a
  full check is Unavailable. Open for the owner: no epoch checkpoint (needs a new result or kind and a verifier
  change), and a lost installation key cannot be replaced yet (audit design 2.7, sub-step 9) (896f54d).
- 2026-11-12: Step 1c review fixes (step-reviewer, secrets-auditor): `--sample-company` sets the key provider;
  rotation needs only the current key (no loop after a key-lost epoch); KS5 rebuilds a damaged recovery copy from
  this computer's DPAPI copy; `FirstMaster` / `CodeIssued` redact the code; the provider's cache follows the
  file's fingerprint; tests for the associated-data bindings, rotation failure paths, KS6's order and a
  log/audit/file leak check over five key flows. Backlog 17: restrict the data folder's permissions.
- 2026-11-12: Step 1c accepted. Docs only, to cut what each session reads: an index of every decision code at the
  top of docs/decisions_2026-11-11.md; the as-built notes and the Step 1b prompt moved from
  docs/audit_readiness_design.md to "Audit design history" below (the rules they held stay in the design, shorter);
  step-reviewer reads only the decisions and sections a step cites; CLAUDE.md section 8 gains the search-first
  and docs/next_step.md rules. Owner decisions recorded: Step 1d scope (key-lost checkpoint recorded as
  Unverified; a new installation key when the old one is lost), backlog 17 in the installer (Phase 5, required
  before v1.0), new backlog 18 (start-up warning when the data folder is readable by all users), and the Master's
  password change without the code stays until 2.8.
- 2026-11-12: Step 1d STOP 1 (9b94fb2): both baselines edited once (tag `baseline-pre-2.5-1d`, copies in
  archive/baseline_pre_2_5_1d/). `ledger_checkpoint` and the mirror gain kind `Key lost` with result
  `Unverified` (only together; the row names its key and the lost key); `installation_key` becomes append-only
  history with one active row; `company_key.installation_key_id`; auth_event `Installation key replaced`. The key
  store reads the active row. Development databases rebuilt (old master and the unregistered COMBUZZ.db moved to
  Backups/20261112-214913/). Suite 2077 passed, 7 deselected, 12 xfailed.
- 2026-11-12: Step 1d part A (STOP 2): `start_new_key_epoch` signs a `Key lost` checkpoint in the same company
  transaction as the key switch, then mirrors it (as the Master; a failed mirror keeps the epoch and says so). The
  verifier anchors on the latest valid epoch, starts at the entry after it, ignores checkpoints at or before it,
  and returns `unverified_through` / `unverified_reason`; messages name the range (`unverified_note`). The close
  check warns on the range in every mode; rotation after an epoch signs its checkpoint again. Decisions KS12-KS21
  recorded (with index rows). New tests/test_key_lost_checkpoint.py (36 tests).
- 2026-11-12: Step 1d part B (STOP 3): new `modules/services/installation_keys.py`: `replacement_preview`,
  `replace_installation_key` (Master, `NEW LEDGER KEY`, password, refused while the DPAPI copy opens; one master
  transaction retires the old key and makes a new one with a new recovery code; then every company, archived
  included, gets a key-lost epoch; per-company results), `remaining_companies`, `finish_remaining_companies`. The
  key store binds each installation key's copies to its row id (KS21; row 1 unchanged) and opens only company keys
  wrapped by the active installation key. New tests/test_installation_key_replace.py (24 tests); the leak check
  covers the flow.
- 2026-11-12: Step 1d review fixes (step-reviewer, secrets-auditor): after the new installation key commits nothing
  raises, so the new code is always returned (a path outside the folder fails that company only); an Unavailable
  result after an epoch carries the range; the key-free anchor checks run first, so an older copy restored after an
  epoch is Broken, not Unavailable; a deleted entry inside 1..N is a Gap; a lost key whose Key lost record was
  removed is a Marker break; the preview needs the machine wrap; the mirror logger logs the error type only; tests
  for each, and the leak check covers a failing company and the finish. The new service relies on auth's one
  allowed clock read (H2 known issue).
- 2026-11-13: Step 1d mutation check (mutation-tester): 126 mutations, 109 killed. Tests added for the 10 survivors
  that mattered, each now killed: a non-Master cannot list the companies left behind; a mistyped phrase is refused
  before the password (no failed sign-in); a failed mirror is named in that company's result; `_left_behind` needs
  the company's own fingerprint and its own company id; a new recovery code after a replacement re-wraps row 2; a
  company with no active key records no checkpoint; a Key lost row whose signing key does not match is a Marker
  break (not a crash); the intact-range wording for several entries; retiring may not change the DPAPI copy alone.
  Seven survivors are equivalent or defence in depth (docs/next_step.md). Suite 2162 passed.
- 2026-11-13: `installation_keys.KeyReplaced` is no longer a namedtuple: the new code is reached only through
  `.recovery_code` (no indexing, iteration, `_asdict`, `vars()` or JSON; redacted; not picklable or copyable).
  `auth.CodeIssued` and `auth.FirstMaster` are still namedtuples (reported to the owner).
- 2026-11-13: `auth.CodeIssued` and `auth.FirstMaster` are read-only classes too: `auth._HoldsACode` is now a
  slotted base (fields as read-only attributes; redacted repr and str; no indexing, iteration, `_asdict`,
  `vars()` or JSON; no pickling or copying), shared with `installation_keys.KeyReplaced`. Tests first.
- 2026-11-13: Step 4 STOP 1 (baseline; previous company baseline in `archive/baseline_pre_2_5_4/`, tag
  `baseline-pre-2.5-4`): `approval_request.document_digest` (64 hex, required for a journal entry's request, R15);
  audit triggers on `approval_request` (insert, update) and `approval_action` (insert); `approval_request` rows are
  never deleted (R16). Status rules stay in the service (H4). New tests/test_schema_approval_audit.py (16 tests);
  two raw-insert test helpers give the digest. Decisions R15-R24 recorded (the owner's answers to the Step 4
  plan). The master baseline did not change. Suite 2184 passed.
- 2026-11-13: Step 4 STOP 1 rebuild: development databases rebuilt from the new baseline (the old master moved to
  `Backups/20261113-024507/`; no company files existed). The script's first-Master prompt cannot be answered in a
  non-interactive shell (EOFError after the rebuild finished).
- 2026-11-13: Step 4 STOP 2 (part A): `companies.action_context` and `App.action_context` (R19; a fresh `now` and
  company-local `today` per post, approval, rejection and close; static test on the screens); approvals: an edit
  cancels a Pending or Approved request (R21), `cancel_in_transaction` for document services, approve and reject
  refuse Import and System origins (R23), status changes through `ALLOWED_STATUS_CHANGES` (R16); `authz.deny`
  takes a message. The stale-now known issue left CLAUDE.md. Suite 2230 passed.
- 2026-11-13: Step 4 STOP 3 (part B): `ledger.submit_entry_for_approval` and the posting gate (R15, R17, R20, R24):
  `approval_document_type` decides which entries need approval; posting refuses an entry with a Pending request,
  one that needs approval without an Approved request matching its digest, amount and type, and (separation on)
  one posted by its creator; it writes and seals the last approver. Import-origin contexts still cannot post (R18).
  `update_entry` / `delete_entry` cancel the request in the same transaction (R21). `ledger_chain.entry_digest`;
  `approvals.request_state`; `submit_for_approval` stores the digest and refuses an unchanged rejected document
  (R22). The close checkpoint uses `action_context()` (R26). Six pending xfails rewritten against the real
  services (R25): 12 xfailed became 6. New tests/test_ledger_approvals.py. Suite 2269 passed, 6 xfailed.
- 2026-11-13: Step 4 review fixes (step-reviewer, secrets-auditor): closing never blocks on any error (an unreadable
  file too); submit checks, digests and inserts in one write transaction (`approvals.authorize_submit`,
  `submit_in_transaction`), so a request is for the entry as it is then; re-saving the same lines is not a change
  (R22); with separation on, an approval the creator made while it was off no longer counts and the entry can be
  sent again (no dead end); an Import-context post is a logged denial; the creator-posting denial says what to do;
  a reason ending in a full stop is not doubled. Tests for each, the denial row's user and actor, rollback of the
  edit with its cancel, refused submits, a DEBUG-log check for the chain key, and the R19 checker scans
  `*_model.py`. Suite 2280 passed, 6 xfailed.
- 2026-11-13: Step 4 mutation check (mutation-tester): 112 mutations, 88 killed. Tests added for the 12 survivors
  that mattered, each now killed (separation off, no settings row, two projects, Payroll, dimensions in the digest,
  the last approval time, a self-approval in an earlier step, the changed-while-sending refusal,
  `App.action_context` with no company, the checker's lookalike call); the rest are equivalent or defence in depth
  (docs/next_step.md). New `tools/hand_check_step4.py` for the owner's hand check. Suite 2294 passed, 6 xfailed.
- 2026-11-13: The owner's answers to the Step 4 questions, R27-R31. R27: refusals are plain sentences with no
  permission code (`authz.denial_message` from the denial's reason; approval step order, role and limit sentences
  that name who can approve; Master-only and user-management sentences); static scans in
  tests/test_refusal_messages.py. R28: with separation on the submitter may not approve either. R29: the "only a
  person" denial names the approve permission. R30: rejection reasons never reach the log file
  (`ServiceError.log_message`, `logging_setup.LogMessageFilter`, a static ban on logging an error's text). R31:
  `create_fresh_databases.py --no-prompt`, and early end of input exits cleanly. New `money.py`. step-reviewer
  and secrets-auditor findings fixed (filter gaps, scan blind spots, the archived/missing-company oracle, the
  agent sentence, three sentences without a next step). Suite 2386 passed, 6 xfailed.
- 2026-11-13: R27-R31 mutation check (mutation-tester, db67342): 116 mutations, 88 killed. Tests added for the
  20 real gaps; 19 re-run and killed, the 20th unreachable (a policy step always names a role); the rest are
  equivalent (docs/next_step.md). Suite 2403 passed, 6 xfailed.
- 2026-11-13: The owner's answers to the four follow-up questions, R32-R36. R32: a failed sign-in never writes
  the typed username (log and auth_event name the user id or "unknown username"); the throttle key is an HMAC of
  the case-folded name under the master's new `throttle_secret` (baseline edited, empty development master
  rebuilt); idle throttle rows are purged after a day; usernames unique ignoring case. R33: `app_strata.pyw`
  starts the log file before the window. R34: a limit refusal names only roles an active user holds. R35: a
  database error in any write is `SaveFailedError` with a plain sentence; details go to the log only. R36: a
  user without access is told only that, and a wrong file is never written to. step-reviewer and
  secrets-auditor findings fixed (the wrong-file access_event row, case-variant accounts, the stored hash's
  lifetime, SecretKey, the R35 log chain). Suite 2443 passed, 6 xfailed.
- 2026-11-13: Owner answers to the three follow-up-2 questions, R37-R38. R37: with separation on, the limit
  refusal does not count the request's creator or submitter as a holder (no one left: ask an Admin). R38: every
  logger is under `strataledger` (font_loader moved; static test). Backlog 19: support bundles redact paths and
  the profile name. Suite 2455 passed, 6 xfailed.
- 2026-11-13: Owner answer to the follow-up-3 question, R39: with separation on, the limit refusal's "ask"
  target leaves out the creator and submitter ("another Admin", else "the Master", else "No one else in this
  company can approve it; ..."). Suite 2466 passed, 6 xfailed.
- 2026-11-13: Design batch (docs only, five commits 753ede4..35687fa): CB1 cash basis view and CF1 direct-method
  cash flow; JD1 job-driven dimensions (the task's J1 was taken); CM1-CM2 and docs/cloud_migration_design.md; B11a
  and docs/bank_feeds_design.md; docs/export_design.md. The owner accepted every proposed answer (CM3, BF1, EX1)
  and added the Ramp double-booking test requirement; every baseline gap is placed by step in docs/roadmap.md.
- 2026-11-13: step-reviewer on the R39 commit: approve with changes (tests only). Five R39 tests added (no Admin
  asks the Master, inactive Master, reject, missing settings row, two role holders), each proven against a mutant.
  Step 5 planned (docs/next_step.md), waiting for approval. Suite 2471 passed, 6 xfailed.
- 2026-11-13: Phase 2.5 Step 5, reversals and automatic reversals (R40-R47 recorded from the owner's answers; backlog
  21, the second-person control for voids, not built). One posting core; posting an accrual posts its automatic
  reversal in the same transaction; `void_entry` and `reverse_entry`; pair void; mirrors include dimensions;
  `display_description` shows the person's note. step-reviewer: approve with changes, fixed (period 13/14
  reversals, R48 provisional; race mapping; a period sentence; tests). mutation-tester: 92 mutations, 79 killed;
  the 5 real gaps now have tests that kill them, and 8 are equivalent. Suite 2561 passed, 5 xfailed.

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

## Audit design history (moved from docs/audit_readiness_design.md on 2026-11-12)

Moved unchanged. The rules in these notes are kept, shortened, in the design doc; these are the dated
notes as written at each step. The two open points in sub-step 9 were decided on 2026-11-12 for Step 1d.

### Section 2.7, Step 1c as built

* **As built in Step 1c sub-steps 5-6:**
  * The installation key's fingerprint is `HMAC-SHA256(key, "StrataLedger installation key fingerprint v1")`;
    the recovery copy's associated data is `("installation_key", 1, "recovery", fingerprint)`.
  * `auth.create_first_master(..., machine_wrap=)` makes the key in the Master's transaction. The first-run screen
    passes `platform_support.DPAPI`. Without a DPAPI copy the Master is created and `ledger_key_locked` is True;
    without a recovery copy nothing is created. An installation that already has a key refuses a second first run.
  * `LocalKeyProvider` is set by `App.start_key_store()` before the launcher and after first-run sign-in. It
    holds the installation key in memory for the life of the process and caches unwrapped chain keys.
  * `create_company` gets the chain key from the provider before building anything (KS6), then writes the file's
    key row and, in the registry's master transaction, the `company_key` row and a `Ledger key created`
    auth_event.
  * The first-run code screen says "The ledger key could not be saved for this computer. ..." when the DPAPI
    copy was not made (sub-step 7).
* **As built in Step 1c sub-step 7 (every new recovery code re-wraps the installation key):**
  * `auth.recover_master(path, code, new_password, machine_wrap=)` opens the key with the old code and, in the
    same transaction, re-wraps the recovery copy with the new code and the DPAPI copy for this computer (a new
    computer, or a key locked since first run, is restored this way). A failed DPAPI wrap keeps the old copy.
  * `auth.change_master_password(session, password, code, new_password)` (PW9) and `auth.issue_recovery_code(
    session, password, machine_wrap=)` (backlog 11: the DPAPI copy opens the key; refused while it is locked).
  * Each returns `CodeIssued(recovery_code, ledger_key_restored, message)`. A valid code whose copy does not open
    still resets the password, with `LEDGER_KEY_NOT_RESTORED` (KS5). Events: `Installation key rewrapped`,
    `Recovery code issued`, `Password changed`, `Master recovered`.
  * Not changed: `auth.change_password` still lets the Master change the password without the code (no PW9
    screen exists yet); step 2.8 switches the Master's screen to `change_master_password`.
* **As built in Step 1c sub-step 8 (rotation):** `ledger_keys.rotate_chain_key(session, company_id)`, Master only
  (no new company permission, so the company baseline is unchanged). Order: the key store must be able to make a
  key; a full check under the current key (refused with `ROTATION_NEEDS_KEY` when that key is not available here);
  the new wrapped key and a `Ledger key rotated` auth_event in the master; the old key retired (`Rotation`) and the
  new one active in the company file; then the check signed as a `Key rotation` checkpoint with the NEW key
  (`ref_type` `ledger_chain_key`, `ref_id` the retired key), in the file and the mirror. A rotation over a Broken
  ledger is allowed and its checkpoint says Broken. A checkpoint that cannot be saved never undoes the rotation
  (`checkpoint_error`).
* **As built in Step 1c sub-step 9 (key lost):** `ledger_keys.start_new_key_epoch(session, company_id,
  confirm_company_code=)`, Master only, the company code typed. For a company whose active key cannot be opened
  here while the installation key can (refused with `KEY_STILL_AVAILABLE` when the key still opens: rotate it).
  The old key is retired as `Key lost`, a new key becomes active (wrapped in the master, `Ledger key lost`
  auth_event; the company file's audit trigger records the retirement), and posting goes on: the next entry
  chains to the last stored hash. A full check stays Unavailable (never Broken) because the old entries need the
  lost key; the result names the last entry sealed before the epoch. **Two open points (owner decision):**
  1. **No epoch checkpoint is signed.** `ledger_checkpoint.result` allows only OK and Broken, and signing
     unverified history as OK would claim a check that did not happen; the incremental verifier would also
     re-check the anchor entry with the lost key. An honest epoch needs a new result or kind (for example
     `Key lost` with result `Unverified`) and a verifier that starts after the epoch's entry. Both change the
     company baseline.
  2. **A lost installation key** (DPAPI unusable and the recovery code lost, or KS5's damaged copy) loses every
     company key at once, and no new company key can be stored, because `installation_key` can never be replaced.
     Recovering needs a new installation key epoch (replace the row, recorded, with every company then starting
     a new key), which changes the master baseline's `installation_key_same_key` trigger.
* **Changed after the Step 1c review:**
  * Rotation needs only the CURRENT key to open here (not the whole history): after a key-lost epoch the full
    check is Unavailable, the rotation goes on and signs no checkpoint, and its result says why. This removes a
    loop in which rotation sent the user to the epoch and the epoch sent them back to rotation.
  * KS5: when the recovery copy is damaged but this computer's DPAPI copy opens, `recover_master` and
    `change_master_password(..., machine_wrap=)` rebuild the recovery copy from it with the new code.
    `LEDGER_KEY_NOT_RESTORED` now means both copies failed (open point 2 above).
  * `LocalKeyProvider` reads the company file's fingerprint on every `get_key` and caches by fingerprint, so a
    company file replaced in the same session (restore, Phase 5) never gets the key cached for the file it
    replaced.
  * `FirstMaster` and `CodeIssued` show `<redacted>` for the code and cannot be pickled or copied.
  * `scripts/create_fresh_databases.py --sample-company` sets the `LocalKeyProvider` itself.
  * For step 2.8: after a recovery restores the key, the running app must call `App.start_key_store()` again,
    or it stays locked until the next start.

Rotation and key-lost text as it stood before the trim:

* **Rotation:** "Rotate ledger key" (Master) creates a new key, retires the old one (`Rotation`) and writes
  a checkpoint. The next entry is sealed with the new key and chains to the old key's last hash. Old keys
  are kept, wrapped, forever, because verification needs them.
* **Key lost** (DPAPI unusable and recovery code lost): the ledger data is still readable (the chain is not
  encryption). Entries sealed with the lost key can no longer be verified. The Master starts a new key epoch
  (`Key lost`, recorded with a checkpoint and a sensitive audit entry); Audit-ready mode shows "history
  before entry N cannot be verified" until the next year close.


### Section 16, Steps 1b and 3b as built

#### As built in Step 1b (differences from section 14)
* `journal_line.entry_id` is hashed too (the line list in 2.2 now says so), so a line moved to another entry
  breaks both entries. `journal_line_dimension.line_id` is classified as excluded because it only groups
  dimensions under their hashed line.
* Date fields (`entry_date`, `auto_reverse_date`) must be text; an integer date is refused.
* The test helper that adds the fixed test key is `ensure_test_chain_key` (a `test_` name would be collected
  by pytest).
* SQLite's integer affinity turns the text '1' into the integer 1, so the schema tests do not treat a numeric
  string as a wrong type.

#### As built in Step 3b (verification)
* **Service:** `ledger_verify.verify_ledger(context, mode="incremental" | "full")`, permission `ledger.verify`
  (K7, K13). It reads through a read-only connection, then records in two short writes: a `ledger_checkpoint`
  row (kind Verify, scope, result, through, first broken, key_id, MAC) and its mirror in the master's new
  `chain_checkpoint` table. A read-only context (`ServiceContext.read_only`, the Auditor's open, section 6)
  records in the master only; `tx.write_transaction` refuses a company-file write from such a context.
* **Result:** status `OK`, `Broken` or `Unavailable`. Broken names the first broken entry: number, JE number,
  date, who posted it (name from the master), and a reason code: `Link`, `Hash`, `Gap`, `Void mismatch`,
  `Key fingerprint`, `Truncated`, `Marker`. The message is plain language, names that entry and a next step,
  and contains no hash or key. Unavailable (the key provider cannot supply a needed key) is never recorded as
  a checkpoint and the message says plainly it is not a sign of tampering.
* **Checkpoint MAC** (`ledger_chain.checkpoint_mac`): HMAC-SHA256 under the chain key named by the row's
  key_id, over the tag `SLCP1`, the company code and the canonical JSON of the checkpoint fields. The latest OK
  checkpoint in the file and the latest OK mirror in the master are both checked; a bad MAC is `Marker`.
* **Incremental (K15):** it starts at the last OK checkpoint. It checks that the checkpointed entry still has
  the recorded hash, re-checks that entry's link and recomputes its seal, then checks every entry after it.
  It does not re-read the entries before the checkpoint: an edit inside the already-verified range is found
  only by a **full** check, which is what re-proves older entries (run at every period and year close, on
  demand, and before backups once the backup service exists). With no OK checkpoint, incremental runs full.
* **Whole-ledger checks in both modes:** the void cross-check, and truncation against the latest OK
  checkpoints (file and master) and the entry counter. Restoring an older copy of the file is caught by the
  master's mirror ("this looks like an older copy of the company file").
* **Automatic checkpoints:** `ledger_verify.checkpoint_on_close(context)` signs a checkpoint (company file
  and master mirror) whenever a company is closed in the app (logout) and when the app exits. It is system
  upkeep (no permission), runs an incremental check (full when there is no checkpoint yet), records OK or
  Broken like `verify_ledger`, records nothing when no key is available, and never raises (a failure is
  logged).
* **Documented limit:** if the last entries are cut, the counter is rolled back as well, and no checkpoint
  exists in the file or the master, the shorter chain is consistent and verifies. Because a checkpoint is now
  written at every company close and app exit, this gap exists only before a ledger's first close (or when no
  key was available at every close). The master's mirror catches a cut tail afterwards even if the file's own
  checkpoints are deleted too. Printed checkpoints in an auditor's hands cover the rest (section 3).
* **Close check:** `ledger_integrity` runs one full verification per close action (period close, Books
  closed through, year close, and the close-check preview), over the caller's connection, not recorded.
  Broken follows the check's mode (warning by default, block when set, L2); Unavailable is always a warning
  that says the check could not run.
* **Keys:** the provider interface is now `get_key(company_id, key_id)`; the test provider can hold several
  keys. **Step 1c:** the local provider must keep every retired key (wrapped, never deleted), because
  verification asks for the key named by each entry's `chain_key_id`; a missing retired key makes
  verification Unavailable, not Broken.
* **Benchmarks (K12, measured 2026-11-12 on the development machine, `tools/benchmark_ledger_verify.py`):**
  full verification of 100,000 entries with 3 lines each took 25.4 s and 28.0 s (two runs; target 10 s);
  incremental verification of 100 new entries after a checkpoint at 100,000 took 0.34 s and 0.37 s (target
  0.2 s). Both miss the targets. A profile shows about half of the full check is building the canonical form
  in Python and a sixth is JSON encoding, so the seal itself is not the cost; the incremental check's fixed cost
  is the whole-ledger SQL (mainly the void cross-check), which grows with the ledger. Follow-up: backlog
  item 14. Whatever the speed, screens run full verification in the background with progress (2.6).

### Section 14, the Step 1b prompt (built)

#### Step 1b prompt (ready to paste)

> **Phase 2.5 Step 1b: baseline schema for the tamper-evident ledger chain** (docs/audit_readiness_design.md
> sections 2, 3, 12). Design decisions K1-K10 and P5 apply. Tests first; each step green; commit by
> explicit path; push.
>
> **0. Save the previous baseline first** (no migrations): copy `migrations/001_company.sql` to
> `archive/baseline_pre_2_5_1b/001_company.sql` with a README naming the commit, and tag that commit
> `baseline-pre-2.5-1b`. The master baseline does not change in 1b.
>
> **1. Tests to write first** (they must fail before the baseline edit):
> - `tests/test_schema_ledger_chain.py`:
>   - drafts have all four chain columns NULL;
>   - posting with any chain column missing is refused;
>   - a posted entry with a draft-style NULL seal is refused;
>   - hex CHECKs reject uppercase, 63 or 65 characters and non-hex;
>   - `chain_version` other than 1 is refused;
>   - `chain_key_id` must reference `ledger_chain_key`;
>   - duplicate `chain_hash` is refused (partial unique);
>   - each chain column is locked once posted (parametrized update);
>   - the Void reversal still sets `is_void` on a sealed original;
>   - `ledger_chain_key`: one active key, no delete, a key can be retired once (is_active 1 to 0 with
>     `retired_at` and `retire_reason`), other columns are locked, a retired key cannot be reactivated;
>   - `ledger_checkpoint`: insert allowed; no update; no delete;
>     `(result = 'Broken') = (first_broken_entry_number IS NOT NULL)`;
>     `(through_entry_number = 0) = (chain_hash IS NULL)`; scope required exactly for kind Verify; MAC
>     format; the insert writes an audit row;
>   - the `journal_entry` audit JSON (insert, update and delete triggers, including the post snapshot)
>     carries the four chain columns;
>   - `period_close_check` has `ledger_integrity` seeded as a warning.
> - `tests/test_ledger_chain.py` (pure module, no database for most tests):
>   - golden vectors in `tests/data/ledger_chain_vectors.json`;
>   - canonical form rules (sorted keys, timestamp normalisation, line and dimension order, float
>     refused);
>   - each hashed field changes the hash; excluded fields do not;
>   - the column classification test against `PRAGMA table_info` of `journal_entry`, `journal_line` and
>     `journal_line_dimension`.
>
> **2. Baseline edits** (`migrations/001_company.sql`):
> - `journal_entry` new columns:
>   - `chain_version INTEGER CHECK (chain_version IS NULL OR chain_version = 1)`
>   - `chain_key_id INTEGER REFERENCES ledger_chain_key(key_id)`
>   - `chain_prev_hash TEXT CHECK (chain_prev_hash IS NULL OR (length(chain_prev_hash) = 64 AND chain_prev_hash NOT GLOB '*[^0-9a-f]*'))`
>   - `chain_hash TEXT CHECK (chain_hash IS NULL OR (length(chain_hash) = 64 AND chain_hash NOT GLOB '*[^0-9a-f]*'))`
>   - `CHECK (is_posted = 1 OR (chain_version IS NULL AND chain_key_id IS NULL AND chain_prev_hash IS NULL AND chain_hash IS NULL))`
>   - `CHECK (is_posted = 0 OR (chain_version IS NOT NULL AND chain_key_id IS NOT NULL AND chain_prev_hash IS NOT NULL AND chain_hash IS NOT NULL))`
> - `CREATE UNIQUE INDEX journal_entry_chain_hash_unique ON journal_entry (chain_hash) WHERE chain_hash IS NOT NULL;`
> - New table `ledger_chain_key`: `key_id INTEGER PRIMARY KEY AUTOINCREMENT`,
>   `fingerprint TEXT NOT NULL UNIQUE` (64 lowercase hex, CHECK), `created_at TEXT NOT NULL`,
>   `created_by INTEGER`, `is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))`,
>   `retired_at TEXT`, `retire_reason TEXT CHECK (retire_reason IN ('Rotation', 'Key lost', 'Compromised'))`,
>   `CHECK ((is_active = 1) = (retired_at IS NULL))`, `CHECK ((retired_at IS NULL) = (retire_reason IS NULL))`.
>   Constraints:
>   - `CREATE UNIQUE INDEX ledger_chain_key_one_active ON ledger_chain_key (is_active) WHERE is_active = 1;`
>   - trigger `ledger_chain_key_no_delete`;
>   - trigger `ledger_chain_key_retire_only`: an update may only move `is_active` from 1 to 0 and set
>     `retired_at` / `retire_reason`; every other column stays.
>   - audit insert and update triggers.
> - New table `ledger_checkpoint`: `checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT`,
>   `created_at TEXT NOT NULL`, `created_by INTEGER`,
>   `kind TEXT NOT NULL CHECK (kind IN ('Verify', 'Period close', 'Year close', 'Report export', 'Backup', 'Restore', 'Key rotation', 'Manual'))`,
>   `scope TEXT CHECK (scope IN ('Incremental', 'Full'))`,
>   `result TEXT NOT NULL CHECK (result IN ('OK', 'Broken'))`,
>   `through_entry_number INTEGER NOT NULL CHECK (typeof(through_entry_number) = 'integer' AND through_entry_number >= 0)`,
>   `chain_hash TEXT` (hex CHECK), `first_broken_entry_number INTEGER`,
>   `key_id INTEGER REFERENCES ledger_chain_key(key_id)`, `ref_type TEXT`, `ref_id INTEGER`,
>   `mac TEXT NOT NULL` (hex CHECK), plus:
>   - `CHECK ((kind = 'Verify') = (scope IS NOT NULL))`
>   - `CHECK ((result = 'Broken') = (first_broken_entry_number IS NOT NULL))`
>   - `CHECK ((through_entry_number = 0) = (chain_hash IS NULL))`
>
>   Triggers `ledger_checkpoint_no_update`, `ledger_checkpoint_no_delete`, and the audit insert trigger.
> - `journal_entry_lock_posted`: add `NEW.chain_version IS OLD.chain_version`, the same for `chain_key_id`,
>   `chain_prev_hash` and `chain_hash`.
> - The `journal_entry` audit triggers (insert, update both branches, delete): add the four chain columns.
> - `period_close_check`: add `'ledger_integrity'` to the CHECK and seed it (mode `warn`).
> - **No trigger checks the previous hash or the active key** (owner decision): the service computes the
>   chain and verification catches mismatches.
>
> **3. Pure module** `modules/services/ledger_chain.py` (no database writes, no keys stored):
> `HASHED_ENTRY`, `EXCLUDED_ENTRY`, `HASHED_LINE`, `EXCLUDED_LINE`, `canonical_entry(header, lines, dims)`,
> `seal(key_bytes, company_code, prev_hash, canonical) -> hex`, `GENESIS = "0" * 64`.
>
> **4. Test helpers:** `tests/ledger_helpers.post` seals with a fixed test key (insert one active
> `ledger_chain_key` row with that key's fingerprint on first use) and writes the four chain columns in the
> posting UPDATE. Route the three raw posting UPDATEs in `tests/test_controls_004.py` through it, or give
> them the chain columns. Adapt any other test that posts by raw SQL.
>
> **5. Verify:** full suite green (state counts), the new tests failed before the edit, `git status` clean
> after the commit. Update CLAUDE.md (status entry, the Step 1b line in the 2.5 roadmap). **STOP after
> Step 1b and report:** what changed in the baseline, the tests adapted, counts and the commit hash. Do not
> start Step 3.

- 2026-11-14: R48 made final by the owner (accepted as built). When the period-13 or 14 target's period is
  closed, the reversal is refused with "reopen it with a reason, or date the void in the next fiscal year" and
  never moved; four tests (void, correction, next-year void, pair void). Suite 2565 passed, 7 deselected,
  5 xfailed. Step 6 (rounding) planned in docs/next_step.md; waiting for approval (Q1-Q3).

- 2026-11-14: Phase 2.5 Step 6 done (rounding and document entries; L8, R1, R49-R55). Owner answers recorded:
  R49 (the rounding line is written at save and worked out again on every save; posting checks it again, R53),
  R50 (`create_entry`/`update_entry` take manual sources only), R51 (2 cents or more is refused when the importer
  saves it, naming the entry, its rows and the difference; nothing is saved). `ledger.create_document_entry`,
  `ServiceContext.as_system`/`as_import` and a static caller test (R54). Review fixes (R55, provisional): Import
  and Payroll only with origin Import; document drafts changed only through their document. R48: a test confirms
  `periods.reopen_period` reopens periods 13 and 14 with a reason, so the sentence stands. Commits 513aedc,
  0695522. Mutation check: 53 mutants, 48 killed; the 5 survivors (the rounding line's recognition and its empty
  fields) now have tests (suite 2740 passed, 7 deselected, 5 xfailed; test_ledger_rounding.py: as-read over the three sources, nothing copied from other
  lines, four look-alike lines), and each kills its mutant. Hand check tools/hand_check_step6.py passes.

- 2026-11-14: R55 made final by the owner, with Conversion added. Conversion entries, like Import and Payroll, are
  saved by `create_document_entry` only with origin Import, so they always need one human review and post=True is
  refused for them (a System context could save and post them unreviewed before). Typed opening balances (a future
  wizard) take the same path; with separation of duties off (the default) the person who entered them may review
  them. Five new tests in tests/test_ledger_rounding.py; Conversion tests that saved as System moved to origin
  Import plus a review. Suite 2745 passed, 7 deselected, 5 xfailed. Step 7 planned in docs/next_step.md; waiting
  for approval.

- 2026-11-15: Docs cleanup (no code or baseline change). Eight design drafts for unbuilt areas that only other docs
  cited moved to archive/design_drafts_2026-11/ (AI Copilot, bank feeds, cloud migration, export, inventory and
  fixed assets, loans, pay applications, Philippines tax), with a README; citations in docs/roadmap.md,
  docs/design_decisions.md and docs/decisions_2026-11-11.md repointed. Docs cited by CLAUDE.md, code, tests, the
  baselines, agents or rules stay in docs/. Empty stubs modules/_init_.py and app_stratacrm.py removed.
  docs/file_map.md updated (also lists archive/baseline_pre_2_5_1d, baseline_pre_2_5_4, instructions). Suite 2745
  passed, 7 deselected, 5 xfailed.

- 2026-11-15: Owner architecture and design rulings recorded (docs only; no code, test or baseline change).
  CLAUDE.md: posted journal lines append-only and journal entries reverse-only; posted invoices, credit memos,
  bills and vendor credits editable by reverse-and-repost while `Lock documents after posting` is OFF (default);
  every approval toggle, Estimate Approval included, OFF by default; subsidiaries may be entities in the parent's
  file (rule 3); the HTML front end over `pywebview` and a local API (AQ2; rule 5, section 2); a planned domain
  summary (section 5.4); reading `archive/design_drafts_2026-11/` allowed when roadmap or decisions cite it.
  docs/design.md rewritten as the system and product design (old visual spec archived); AQ1/AQ2 index rows in
  docs/decisions_2026-11-11.md; roadmap and next_step: the consolidated pre-release baseline update, then Step 7.
  Open questions in docs/design.md section 11 (B9 NACHA vs `bank_payee_id`, `clearing_id` and the chain,
  dimension depth cap of 3, service types vs `pipeline_stage`, cost code levels). Suite 2745 passed,
  7 deselected, 5 xfailed.

- 2026-11-16: STOP 1 of the consolidated baseline update (before Step 7). Decisions RP1-RP11 recorded (B9, D7 and H6
  amended). Baselines saved to archive/baseline_pre_replan/ (tag `baseline-pre-replan` on 499c8d5). Tests first
  (54 failed on the old baseline). Both baselines edited in place:
  - entities and `journal_line.entity_id` / `clearing_id` (frozen after posting, sealed: chain v1 edited in
    place, vectors regenerated, RP8);
  - contact and invoice columns, `contact_site`, `fiscal_period_lock`, `audit_log.reason`, the
    `lock_documents_after_posting` control, four more approval toggles (all OFF);
  - Step 7 `payment_allocation` columns, with posted-source rows released once and never deleted (RP11);
  - 3-level cost codes, dimension depth 10, service types replacing `pipeline_stage`;
  - pay runs, bank statement lines and matches, close tasks, payment terms, custom fields, list preferences;
  - master `user_company_role` (schema only);
  - audit triggers on every new table and column, and a full index on every foreign key (136 added).

  Reversals mirror `entity_id` and `clearing_id`. Development master rebuilt. Suite 2798 passed, 7 deselected,
  5 xfailed. STOP 2 (Step 7) planned in docs/next_step.md.
  Review fixes:
  - step-reviewer: release only after the source is voided; no allocation from a voided credit memo; no delete
    of a reconciled statement line; a test per lock clause; reversal mirroring of the two new ids proven;
    docs.
  - secrets-auditor: contact tax id and certificate number masked to the last four in the audit log; RP1
    test widened to every table.
  Suite 2818 passed, 7 deselected, 5 xfailed.
  Mutation check (on 35ffbb7): 122 mutants, 89 killed; tests for the 33 survivors in a4bc3d7; the rerun killed
  all 33. Suite 2821 passed, 7 deselected, 5 xfailed. STOP 1 done; STOP 2 (Step 7) planned in docs/next_step.md.

- 2026-11-16: Phase 2.5 Step 7 (STOP 2) done; Phase 2.5 is complete.
  - Owner answers recorded as R56-R58, and review decisions as R59 and R60.
  - `payments.py` (allocate, release_allocations, open_item, clearing_lines).
  - Ledger: clearing ids on document entries (NEW_CLEARING; only on tracked accounts; a group is joined only once
    posted, for the same contact), exempt_from_approval for application entries only, void_document_entry, and
    leaf cost codes at save and at post.
  - `sequences.next_invoice_number` (R6, ph_tax, range, valid_until against the issue date, first usable series).
  - AR and AP accounts are marked to keep open items.
  - Baseline: `payment_allocation.application_entry_id`; the credit-memo source triggers accept vendor credits
    (archive/baseline_pre_2_5_7, tag baseline-pre-2.5-7).
  - The five xfails are real tests; tests/test_service_rules_pending.py is removed. The billing allow-list row
    shrank to {"Invoice"}.
  - COMBUZZ.db moved to Backups/; development master rebuilt. tools/hand_check_step7.py passes.
  - Commit f931d7a, then the review fixes (step-reviewer: approve with changes, all fixed; secrets-auditor:
    nothing leaks, two fixes, LOW 2 left open in docs/next_step.md).
  - Suite 2933 passed, 7 deselected, 0 xfailed.
  Mutation check (on fc0cbc5): 141 mutants.
  - 115 killed, plus 1 by tests/test_voucher_sequence.py; 4 equivalent.
  - Tests for the other 22 in bd29f11; the rerun killed all 22.
  Suite 2959 passed, 7 deselected, 0 xfailed. STOP 2 done; Phase 2.7 planned in docs/next_step.md.

- 2026-11-17: Phase 2.7 STOP A (multi-role permissions) built.
  - Owner answers recorded as MR1-MR7 (STOP A), HA1-HA6 (STOP B) and FR1 (STOP C), with their index rows.
  - `authz`: roles from `user_company_role` (else `role_code`), union of active roles, Admin in any role, project
    scope only when every granting role is Assigned, the highest approval limit (MR2-MR4); `Access.role_codes`,
    `granting_roles`.
  - `approvals`: slots matched against any active role, one slot per person (MR5).
  - `users`: the broader-role check, Admin guards and last-Admin check read the effective roles.
  - `payments.allocate`: side first, one sentence for someone with neither right (MR6, closes LOW 2).
  - CLAUDE.md trimmed to 199 lines (MR7).
  - Suite 3002 passed, 7 deselected.
  Review fixes (4c46ef4, 9e022b9):
  - step-reviewer (approve with changes): MR8, so the single-role services replace or clear the role rows; the
    Admin-anywhere check reads the effective roles; ROLES_CHANGED; tests for Master and Admin any-role slots and
    the full neither-right matrix.
  - secrets-auditor: nothing leaks; LOW 2 closed; INFO-B (the Master's sentence) fixed; LOW-A left for the owner.
  Mutation check (on 9e022b9): 87 mutants, 67 killed, 6 equivalent; tests for the other 14 are in
  tests/test_mutation_stop_a_extra.py. Suite 3027 passed, 7 deselected. STOP A done; STOP B planned in
  docs/next_step.md.

- 2026-11-17: Phase 2.7 STOP B (hooks, add-ons, add-on migrations) built.
  - Owner answers: MR8 confirmed with "This removes: <roles>" (`ConfirmationRequiredError`, `confirm_removal`,
    `{'removed_roles'}`, audit-logged by the delete trigger); MR9 closes LOW-A for the source and the target.
  - Baseline: `addon_schema_version.sha256` (HA6) and the `addon.manage` seed (HA5, sensitive, Admin and Master).
    Previous baseline in archive/baseline_pre_2_7_b (tag baseline-pre-2.7-b); development master rebuilt.
  - `database.py`: `check_addon_key`, `addon_write_guard` (SQLite authorizer, HA2), `apply_addon_migrations` (HA4).
  - `hooks.py` and `addons.py` (HA1, HA3, HA7); `ledger._seal_and_post` fires `entry.posted` / `entry.voided`;
    `open_company` calls `addons.prepare_company`.
  - Commit 3c961c3. step-reviewer: approve with changes; fixes in the next commit (no references from add-on
    tables to core tables, trigger text without comments or strings, per-company broken marks, a caught refusal
    still fails, read-only opens apply nothing, unreadable files refused, the handle keeps no connection, MR9
    for targets).
  - Review fixes in 1b5f723 (suite 3185 passed). secrets-auditor: nothing Critical or High; fixed MEDIUM-1 (add-on
    SQL reads bank numbers, tax ids and the audit tables as NULL), LOW-2 (no add-on error message in the log),
    LOW-3 (the handle is described as a guard against mistakes, not a sandbox), LOW-4 (linked migration files),
    LOW-5 (data folder inside the add-ons folder); LOW-6 (backups made on open) left for the owner.
  - Mutation check (on 9b2f1f1): 262 mutants, 155 killed; the non-equivalent survivors are covered by
    tests/test_mutation_stop_b_extra.py (59 tests, each spot-checked against its mutant). One bug found and fixed:
    the migration guard refused `sqlite_autoindex_<table>_N`, so an add-on table could not have a UNIQUE or text
    PRIMARY KEY column (HA7). Suite 3262 passed, 1 skipped, 7 deselected. STOP B done; STOP C planned in
    docs/next_step.md (not built).

- 2026-11-17: Phase 2.7 step B2 (owner prompt): workflow rules, connections and backups, add-on audit, decisions.
  - Part A (785ca30): docs/workflow_standards.md is now .claude/rules/workflow-standards.md (always loaded); CLAUDE.md
    section 8 points to it and puts Codex in its own worktree; AGENTS.md points to CLAUDE.md; .codex/agents checked
    for secrets and committed.
  - AX1: foreign keys and a 5-second busy timeout on every connection; master and company files are WAL (set at
    build, switched and logged at open). AX2: `backup_database` on Connection.backup with a .sha256 (K5),
    `prune_backups` (E7) for add-on migration backups (closes LOW-6), `restore_database` (checksum, soundness,
    company closed, safety backup, stale -wal/-shm removed). AX3: source runs use %LOCALAPPDATA%\StrataLedger-dev.
  - HA9: generated audit triggers on add-on tables (migrations/addon_audit_triggers.sql), baseline audit triggers on
    addon_schema_version (the empty development databases need no rebuild: the source-run data folder is new).
    Found while building: an add-on table could not be renamed or dropped (the guard refused the temp schema and
    sqlite_sequence updates and the audit trigger drops); now allowed, with a check that no core AUTOINCREMENT
    counter moved.
  - SystemExit in a handler becomes AddonError; the Agent refusal in hooks.fire writes a denial row after the
    rollback. Theme.create_scrollbar.
  - Decisions: AX1-AX8, AG1-AG8, HA8-HA10, RI1 (replan inputs), FR1 amended (no packs, no cap, no schema change).
  - Suite before the reviews: 3313 passed, 1 skipped, 7 deselected (2 WAL-sidecar test expectations then fixed).
  - Commit 8e5979c. step-reviewer: changes needed (1 high, 2 medium, 6 low). Fixed in the next commit: a backup
    is a rollback-journal file and a restore reads it immutable and refuses a -wal or -journal beside it (high:
    a planted WAL bypassed K5's checksum); add-on table and column names are plain identifiers (medium); the live
    -wal and -shm are set aside and put back if the replace fails (medium); the open-file check never leaves the
    file renamed silently; an add-on counter row must belong to an existing add-on table and audit_log's counter
    only moves forward; a failure while logging the deferred denial never hides the refusal; the helper
    connections are configured; the AX3 note on the repo-root files. Left for the owner: the committed
    .codex/agents files. Suite 3327 passed, 1 skipped, 7 deselected.
  - secrets-auditor on 3340b32: nothing Critical or High. Fixed: pruning removes a backup's -wal, -shm and
    -journal (L1); a failed company creation removes WAL sidecars (L2); restore leftovers, .sha256, Exports/ and
    Secrets/ are git-ignored (L3); any failed replace puts the live WAL back (L4); a test proves the audit triggers
    never unmask a hidden column (L5). Left for the owner: M1 (master backups keep old key blobs, never pruned)
    and M2 (no rule against secrets in add-on tables, which HA9 audit-logs whole).

  - mutation-tester on 2698385: 250 mutants. 158 are killed by the B2 test files and 7 more by
    tests/test_service_tx.py (B182-B188). 85 survived: 55 were real gaps, now killed by
    tests/test_mutation_b2_extra.py (38 tests), and 30 are equivalent (reasons in docs/next_step.md). It also
    found a defect: an add-on migration could leave a second audit_log row in sqlite_sequence. It is fixed, test
    first: `_check_counters` refuses a counter name that appears twice.

- 2026-11-18: B2 approved by the owner, with answers built in one commit.
  - AX2 note: `pre-upgrade` and `pre-restore` safety backups are never pruned; `addon-<key>` backups keep E7 pruning
    (7 days, 4 weeks, 12 months; the owner kept the LOW-6 fix); the `.sha256` file detects corruption only.
  - HA11 (secrets audit M2): add-on migrations refuse secret-looking column names; secrets go only in
    DATA_DIR\Secrets (tests/test_addon_secret_columns.py, 49 tests). test_addon_secrets' copy test now gives its
    target columns neutral names; its reads of the sensitive source columns are unchanged.
  - M1 went to Phase 2.8 (list older master backups at a recovery-code reissue, offer to delete, log the choice).
    `fields.manage` may join the baseline seed in STOP C (Admin and Master, not AGENT_ALLOWED).
  - Agents: .codex/agents kept and synced with .claude/agents (CLAUDE.md 8); Codex copies map the Claude tier to
    model_reasoning_effort; mutation-tester mutates only the functions the step's commits changed.
  - A PreToolUse hook (.claude/settings.json, .claude/hooks/pre_commit_pytest.py, tests/test_commit_hook.py) runs
    the full suite before any git commit and blocks it on failure; timeout 2400 s (the suite takes 18 minutes).
    CLAUDE.md 8: Codex reviews pushed commits read-only after each STOP.
  - Suite 3440 passed, 1 skipped, 7 deselected.
- 2026-11-18: B2 owner-answers review fixes (not yet approved).
  - secrets-auditor on b4ea844 (HA11). Fixed, tests first:
    - HIGH-1: the project's own secret types (recovery, backup and reset codes; chain, HMAC, installation, master,
      encryption, signing and session keys; DPAPI, salt, hash, OTP, JWT and short forms of password) are refused.
    - HIGH-2: names are split at digits as well, plurals are matched, and the long forms (secret, token, credential)
      are found inside run-together or all-capital names.
    - LOW-1: an add-on table already in the file is checked even with nothing pending.
    - LOW-2: a refused or failed add-on statement is named by file and number, never by its SQL text or a SQLite
      message that could quote a literal; only identifier-only messages (no such table, already exists) are kept.
    - MEDIUM-1 recorded in HA11: the name check is a safety net; "sensitive columns" is PROPOSED, not built.
      INFO-1 (hook output) and INFO-2 (a public routing number in a test) left as they are.
  - HA8 (Codex finding): a frozen build whose RESOURCE_DIR or RESOURCE_DIR/addons this account can write loads no
    add-ons, logs it and says one sentence; source runs are exempt (tests/test_addon_install_folder.py, 13 tests).
  - Commit hook: pytest-xdist 3.8.0 in requirements-dev.txt; the hook runs `pytest -q -n auto --dist loadgroup` and
    blocks the commit if xdist is missing; timeout 2400 s to 900 s. Three parallel full runs: 306, 328, 313 s (18
    minutes in one process), all green; no test needed a single worker. Plain `python -m pytest -q` is unchanged.
  - Suite 3551 passed, 1 skipped.
- 2026-11-18: owner answers on 997305c (not yet approved).
  - HA8 reads the folder's ACL, not this process's access (platform_support.folder_open_to_non_admins, P3; the app
    hands it to addons.use_folder_check). Off when Users, Authenticated Users, Everyone, Interactive or the user's
    own SID (not elevated) can write, modify or create in RESOURCE_DIR or RESOURCE_DIR/addons; an elevated admin
    on a proper install keeps add-ons; an unreadable ACL, a NULL DACL or no check handed over keeps them off. The
    probe-file check is removed. tests/test_platform_folder_acl.py (51 tests, real C:\Program Files reads as
    admin-only), tests/test_addon_install_folder.py rewritten.
  - Add-on SQLite errors: the error type only in the installed build, the full message in source runs.
  - Parallel runs found the five first-run tests that use the real system clipboard racing across workers: they
    are now one xdist_group, with a guard test. Three parallel runs: 289, 296, 301 s, all green.
  - Suite 3606 passed, 1 skipped.
- 2026-11-18: step-reviewer on 997305c..7aeb3f4 (approve with changes). Fixed, tests first:
  - H1 and a root cause: pytest-xdist 3.8's xdist_group does nothing under pytest 9.2 (it renames item._nodeid,
    which pytest 9 no longer reads), so the "grouped" clipboard tests ran in parallel and raced. Replaced by a
    `system_clipboard` marker whose tests (and live_clipboard ones) hold a cross-process file lock
    (tests/conftest.py, tests/test_clipboard_lock.py); every other first-run test gets an in-memory clipboard. Tests
    that simulate another program now write through the Windows clipboard API (Tk's write gives up silently when
    the clipboard is busy). The hook runs `pytest -q -n auto` (no --dist loadgroup).
  - The product's clipboard open now retries for about a second (was 0.2 s): on a busy computer Continue could leave
    the recovery code on the clipboard.
  - L1: allow entries the ACL reader does not parse count as open. L4: the xdist test skips without xdist. L5: H1
    bans ctypes and platform_support in services. L6: company open with add-ons off logs the HA8 reason, not "not
    installed". L7: live-clipboard tests hold the lock.
  - For the owner: M1 (add-on subfolders and files are not checked), M2 (allow-list of admin SIDs instead of a
    list of non-admin groups), M3 (the user's own SID when elevated), L2 and L3 (HA11 misses and false positives).
  - Three parallel runs: 504, 499, 525 s (other jobs were running on the machine), all green. Suite 3617 passed,
    1 skipped.
- 2026-11-18: mutation-tester on 997305c..6afd131: 145 mutants, 102 killed; 33 real gaps now killed by
  tests/test_mutation_b2_review_extra.py (44 tests, each mutant re-applied and seen to fail); 10 equivalent, with
  reasons in docs/next_step.md.
- 2026-11-18: KS12 epoch-anchor tie (Codex keys/chain finding), tests first. Two key losses with no posting between
  them left two 'Key lost' rows at the same entry, and `_epoch_anchor` kept the file's row on a tie, so a copy
  restored from between the losses verified OK. On a tie the mirror now wins when it is another event the file
  does not hold (key_id or MAC); the file's row stays when it is the same event or the file also holds the
  mirror's event (the later loss's mirror write failed). tests/test_key_lost_epoch_tie.py (11 tests). Suite 3672
  passed, 1 skipped.
- 2026-11-18: step-reviewer on 7a704a2 (approve with changes). Fixed, test first: the "file also holds the mirror's
  event" lookup could be met by a decoy row copied from the master into the file (proved by a probe), so the
  tie now reads only the file's latest row: it stays only when its signed ref_id is the mirror's key_id. KS12
  records this carve-out as PROPOSED for the owner, with its fail-safe cost. Suite 3675 passed, 1 skipped.
- 2026-11-18: mutation-tester on 7a704a2..3a792cc (`_epoch_anchor`): 44 mutants, 41 killed, 3 equivalent (reasons
  in docs/next_step.md). The commit hook once blocked on tests/test_voucher_sequence.py (6 threads, 5 of them
  'database is locked' past the 5 s busy timeout) while other heavy jobs ran on the machine; not reproduced in
  300 tries; left for the owner.
- 2026-11-18: owner answers on the B2 review step and the KS12 tie, tests first.
  - KS12: the tie exception is approved and recorded as decided (PROPOSED removed).
  - HA8 M1-M3: an allow-list (SYSTEM, Administrators, TrustedInstaller); any other principal with a change right
    or ownership turns add-ons off, the user's own account included when elevated (the token is no longer read;
    `current_token` removed). Every folder and file under RESOURCE_DIR\addons is checked (`storage.resource_tree`;
    a tree that cannot be listed counts as open). CREATOR OWNER/GROUP on inherit-only entries are placeholders.
  - HA11 L2/L3: mypwd, acctnum, client_key, nonce and similar refused; names ending in id or count allowed except
    session_id; account numbers and hashes stay refused (RP1).
  - tests/test_voucher_sequence.py: that test's own connections wait 60 s for the lock; the app keeps 5 s (AX1).
  - AX9 and AX10 not recorded: their text is not in the repo or this session (asked the owner to resend).
  - step-reviewer (approve with changes), fixed test first: an id or count of a value that is the secret (tin_id,
    account_number_id, hash_id) stays refused; non_certified, keyword and "wd" names no longer caught (the pwd run
    is now the words mypwd and userpwd); sessionid refused; a symbolic link or junction in the add-ons tree turns
    add-ons off; a control character and a joined line in platform_support.py. Left for the owner: the HA8
    sentence says "this account" though any principal outside the allow-list now trips it; the tree is read twice
    when a company opens with an add-on enabled.
- 2026-11-18: mutation-tester on 55a0e2b: 132 mutants, 99 killed; 23 real gaps now killed by
  tests/test_mutation_owner_answers_extra.py (sorting in resource_tree, the link check's first and last entries,
  islink, a missing program folder, and HA11 words, pairs, runs and value words); 10 equivalent (docs/next_step.md).
- 2026-11-18: owner answers, tests first: the product name people see is Melara (`config.APP_NAME`), used in the
  three service sentences that named StrataLedger; a static test refuses the old name in service strings. New HA8
  sentence. CREATOR OWNER handling accepted. AX9-AX10 recorded (docs only) and added to docs/CLAUDE_UI.md 10A.
  Folder, variable, installer and repo renames and the installer's HA8 check are on the U1 list (docs/next_step.md).
- 2026-11-18: fix mode on fc6efe0 (owner answers): new HA8 sentence ("...permissions allow changes by accounts other
  than the system and Administrators group..."); inherit-only CREATOR ACEs ignored (owner), logic unchanged, tests
  added for both conditions; the static name test is case-insensitive with a shrink-only identifier list;
  tests/test_clipboard_lock.py no longer races other xdist workers for the shared lock.
- 2026-11-18: owner approved the owner-answers round (fc6efe0) and its fix mode (d7a8073; hook run 3916 passed,
  2 skipped). The next step runs in a separate session (docs/next_step.md).
- 2026-11-18: Phase 2.7 STOP C, the custom fields service (FR1 as amended by CODE_CHANGES 27), tests first:
  `modules/services/custom_fields.py` (tests/test_custom_fields.py). One seed row: `fields.manage` (Company,
  sensitive; Admin and the Master only; not agent-allowed). Owner answers: values read exactly when the record
  reads (Contact by kind, Invoice ar.view, Bill ap.view, Project project.view with scope); set with the record's
  own edit check; the Agent never sets; Estimate refused until an estimate service exists; posted invoices and
  bills editable, refused in a closed period or with Lock documents after posting on; audit by the baseline
  triggers (old and new). Contact bank-number names refused. Listed for 2.9: field columns, Estimate read code,
  the contacts "either manager" check, area locks (docs/next_step.md).
- 2026-11-18: step-reviewer on e61dec2 (approve with changes, nothing must-fix); findings 1-5 and 8 fixed test first: 64-bit bounds, no-write checks on refusals, H5 filter, missing-contact denial, Agent view codes only, no-op updates write nothing (docs/next_step.md).
- 2026-11-18: mutation-tester on e61dec2 and 67e9f56: 151 mutants, 124 killed by existing tests, 20 by tests/test_mutation_stop_c_extra.py, 7 equivalent (docs/next_step.md). STOP C awaits the owner's approval.
- 2026-11-18: owner approved STOP C (e61dec2, 67e9f56, 769bfd3; hook run 4158 passed, 2 skipped). Step 2.9 runs
  in a new session (docs/next_step.md).
- 2026-11-18: Codex batch 2 posting fixes (before 2.9, owner), tests first. R21: `ledger.update_entry` cancels an
  approval request only when the R15 digest differs before and after the save (no-change saves keep it; date,
  line, amount, dimension, description and reference changes cancel). C4/L2 deferral close check not built: the
  baseline has the deferral tables but no service writes them; listed with B14's payment void service under
  Deferred (docs/next_step.md).
- 2026-11-18: step-reviewer on the Codex batch 2 diff (approve with changes; R21 decision text amended in f629f2f);
  mutation-tester on f629f2f: 20 mutants on update_entry, 19 killed, 1 gap (a changed source kept unsaved) now
  killed by tests/test_mutation_codex_batch2_extra.py. Awaits the owner's approval.
- 2026-11-18: owner approved the Codex batch 2 posting fixes (f629f2f, 0137b34; hook run 4169 passed, 2 skipped).
  Step 2.9 runs in a new session (docs/next_step.md).
- 2026-11-19: owner approved the step 2.9 area 18 doc (docs/replan_2.9/area_18_admin_security_audit.md; draft
  6e9cdf8, owner answers Q1-Q17 and the access seed tables 2a3b497; hook run 4169 passed, 2 skipped). Owner answers
  Q18-Q24 (2026-11-19): all A; C8 closed by Q24 A, C9 by Q18 A. The next session starts in a new chat.
- 2026-11-19: owner approved area 18 as Owner-approved (Q18-Q24 all A, C8 and C9 closed; d38e11e) and the commit hook
  timeout stopgap 900 s -> 1500 s (55df6ef; hook runs 4169 passed, 2 skipped). Quiet-machine timing run
  (`-n auto --durations=25`): 243.7 s, slowest test 14.1 s; the 862 s run was machine load (Codex QA scripts).
- 2026-11-19: area 18 seed tables aligned with Q20 A (shipped Payroll template) and Q22 A (`retainage.release` in Controller);
  scratch check: 77 codes placed (7 Admin-only), no level default holds a sensitive code, every template inside its caps.
  Roadmap reordered to the owner's phase order (AI is Phase 5, installer Phase 6, hosted after). Tests never touch the real
  clipboard in a normal run: autouse `fake_clipboard` in conftest; real-clipboard tests are `live_clipboard` (deselected
  unless STRATALEDGER_LIVE_CLIPBOARD=1, file lock kept); `system_clipboard` marker removed. 3 parallel full runs with
  text on the clipboard: 4173 passed, 2 skipped each.
- 2026-11-19: report builder service contracts drafted (docs/contracts/reports.md; Q1-Q18, 2.9 list). 3cf3428 holds the
  area 18 seed-table and roadmap edits from the parallel Sonnet session (owner 2026-11-19); its message is wrong; no rewrite.
- 2026-11-19: owner approved the report builder service contracts (docs/contracts/reports.md, Owner-approved; draft 3d237d3,
  fix mode 1 221b996 Q1-Q18, fix mode 2 e869ecf Q19-Q26; hook runs 4173 passed, 2 skipped). Section 12 feeds the 2.9 replan
  (area 17, KPI freeze in area 13, money.view seeds in area 18). Stopped at the owner's request; no next step started.
- 2026-11-19: Step 2.9 schema replan, area 13 (close and locks), docs only: docs/replan_2.9/area_13_close_and_locks.md.
  Draft dfb26b6; owner answers Q1-Q24 (Q4 B, Q12 B, Q15 B, Q16 B, the rest A), the F13 approval and the KS15 fix
  recorded in dac81ec; two dated amendment lines added later (ending cash, deferral tie-out by role). Proposes
  `lock_area` and `period_lock` (reason to lock and to unlock), one shared `period_locks.check_open`, the close checklist
  (templates, system and custom tasks, dependencies guarded by the service only), due dates and reviewed-by,
  `period_close_snapshot` (five figures per close, insert-only), the KPI freeze hook and the period balance summary
  writer. Owner-approved 2026-11-19 (planning marked it in the working doc). Hook runs 4173 passed, 2 skipped.
- 2026-11-19: Step 2.9 schema replan, area 12 (bank and reconciliation), docs only:
  docs/replan_2.9/area_12_bank_and_reconciliation.md. Draft d9032ea; owner answers Q1-Q20 (all A) and amendments to
  areas 13 and 18 in a837bc1; permission placement revised in d239f32 (`bank.feed` and `bank.reconcile` at Accountant
  Standard, `bank.unreconcile` in the Controller template). Proposes `bank_line_clearing` (cleared state off
  `journal_line`), match targets by bank line, one unmatch service with lock checks, reconciliation states
  (Reopened, Changed after finish) finishing only at $0.00, deposits and transfers, `bank_account.kind`. Owner-approved
  2026-11-19. Hook runs 4173 passed, 2 skipped.
- 2026-11-19: Step 2.9 schema replan, area 10 (prepaid, deferrals, reclass, period balance summary), docs only:
  docs/replan_2.9/area_10_prepaid_deferrals_reclass.md. Draft 3f79eb3; owner answers Q1-Q19 (all A, Q2 and Q10 with the
  owner's detail) and amendments to areas 13 and 18 in 77938bc; `je.reclass` added to the Controller and Staff
  accountant templates in a46501a. Proposes the deferral schedule tables as one subledger (runner, catch-up, void in one
  transaction), insert-only `reclass_line`, the two deferral close checks and `ledger_period_balance` written only in
  `ledger._seal_and_post`. Owner-approved 2026-11-19. Hook runs 4173 passed, 2 skipped.
- 2026-11-19: commit hook change (887da07, owner 2026-11-19): when every staged file is under docs/ the hook skips the
  suite, prints "docs only: suite skipped (N files)" and records it in the temp result file; anything else (a file
  outside docs/, a rename into or out of docs/, nothing staged, a git error, or a command that changes the staged set
  such as add, -a or --amend) runs the full suite as before, timeout 1500 s. 37 new tests in tests/test_commit_hook.py
  (4210 passed, 2 skipped). 2514794, the first docs-only commit, skipped the suite ("docs only: suite skipped (4 files)").
  docs/next_step.md overwritten: areas 18, 13, 12 and 10 owner-approved, next is area 17 (field registry, list layouts,
  report builder).
- 2026-11-19: Step 2.9 schema replan, area 17 (field registry, list layouts, report builder, KPIs and measures), docs only:
  docs/replan_2.9/area_17_fields_layouts_reports.md. Draft 809fb22; owner answers Q1-Q25 (A except Q12 B and Q13 B)
  recorded in fded8c4. Proposes a code field registry, per-user list layouts and a company default, financial and
  Records layouts with formula tokens as rows, saved reports with typed parameters and packs, in-app schedules, KPIs
  frozen in the close transaction (also for periods 13 and 14 when the basis includes them), non-financial measures,
  combined runs by account number, and `money.view`, `report.records`, `report.design` and `report.schedule`. A
  customer or vendor filter reads `journal_line` (summary key unchanged). The amendments touched area 13 (section 4.5,
  the freeze on periods 13 and 14), area 18 (audit exemption for display and event rows, the four codes, three
  templates, AGENT_ALLOWED) and docs/contracts/reports.md (share modes, pack items, `split_by` and `job_budget`,
  derived measures stored only at close, KPIs for periods 13 and 14). Owner-approved 2026-11-19. Docs only, so the
  commit hook skipped the suite ("docs only: suite skipped").
- 2026-11-19: Step 2.9 schema replan, area 8 (PM stages, service types, schedules, change orders, forecast), docs only:
  docs/replan_2.9/area_8_pm_schedules.md. Draft 3d15762; owner answers Q1-Q24 (A except Q6 C and Q13 A with a label)
  and the amendment to area 18 in c835d20; the on-hold rule and the approval in the commit that follows. Proposes one
  `service_type` list with stage roles and an append-only `project_stage_history`, Closed with an outcome (Completed or
  Cancelled) and a cancel reason list, `project.status` dropped for an on-hold flag with an append-only hold history
  (on hold is a label and warnings only; no posting refused), schedule templates and job schedules with insert-only
  baselines from change orders, delay reasons, calendar items and crews (label setting, default "Crew"/"Crews"),
  change orders with field events and a lock on approved lines, and `job_forecast_line` with insert-only forecast
  revisions (eight figures per cost code and totals) under `job.forecast.edit` and `job.budget.transfer`; also
  `service_type.rate_card_id` (owner 8:40 PM). The amendment to area 18 (section 1.2 reasons and section 2.4 codes)
  adds six codes (`job.forecast.edit`, `job.budget.transfer`, `job.schedule.edit`, `schedule.template.manage`,
  `service_type.manage`, `job.stage.backdate`; 86 to 92 seeded), the Accountant cap to 71 and the Operations cap to 37,
  and the area 8 reasons; no derived or exempt tables. Owner-approved 2026-11-19. Docs only, so the commit hook
  skipped the suite ("docs only: suite skipped").
- 2026-11-19/20 area 15 CRM: draft 2237b63, answers 03477c0 and this commit ("Area 15 fix mode 2"); amendment lines
  in areas 8 and 18; awaiting owner approval.
- 2026-11-20 area 15 CRM owner-approved (2237b63, 03477c0, 3b8108b); amendment lines in areas 8 and 18; area 18 seeded
  codes 102.
- 2026-11-20 area 6 estimates and contracts owner-approved (2c82148, d297397, b0bea27); amendment lines in areas 8, 15
  and 18; seeded codes 107.
- 2026-11-20 area 7 jobs, budgets, cost codes, dimensions owner-approved (7bab6f0, 7ebcd4f, 8b68381, d582c7e, 64519fd,
  this commit); amendment lines in areas 6, 8, 10, 13, 15, 17 and 18; seeded codes 111; shipped Service manager
  template.
- 2026-11-20 Git hook repair: confirmed Python 3.11.9, pytest 9.2.0 and pytest-xdist under the non-admin `marka`
  identity. Replaced the obsolete Claude PreToolUse settings test with coverage for the tracked `.githooks/pre-commit`
  wrapper; `tests/test_commit_hook.py`: 68 passed. Full suite before that replacement: 4,208 passed, 2 skipped,
  2 failed in 327.98 s. The commit-hook settings failure is addressed; the remaining failure,
  `test_the_real_reader_gives_the_owner_and_exact_masks`, is caused by inherited `Modify` ACEs on pytest's `%TEMP%`
  directory for `CodexSandboxUsers` and SID `S-1-5-21-3876112204-1666981215-754291341-1030728988`. The ACL test was
  not changed or skipped; `tests/test_platform_folder_acl.py` passed 177 tests. **Commit: none; push: none.**
  Staged hook/settings/CLAUDE changes remain staged; `tests/test_commit_hook.py` is unstaged. Planning handoff open.
- 2026-11-20 Git hook repair rerun: focused `test_the_real_reader_gives_the_owner_and_exact_masks` failed in 0.18 s;
  full suite after the hook-test replacement: 4,209 passed, 2 skipped, 1 failed in 315.94 s. The sole failure is the
  same ACL assertion. The failing pytest temp folder is owned by `MARKALENOVOLAP\marka` and inherits `Modify,
  Synchronize` ACEs for `markalenovolap\CodexSandboxUsers` and SID
  `S-1-5-21-3876112204-1666981215-754291341-1030728988`; SYSTEM, Administrators and `marka` have FullControl.
  The ACL test remains unchanged. **Commit: none; push: none.** Stop for planning review of a non-weakening test
  environment resolution.
- 2026-11-20 dedicated-basetemp attempt: `PYTEST_ADDOPTS` was unset. The focused ACL test was run with
  `--basetemp=C:\Users\marka\.pytest-strataledger-acl`; pytest interpreted the backslashes as escapes and instead
  created `C:\Users\marka\StrataLedger-clean\Usersmarka.pytest-strataledger-acl`. The focused test failed its exact
  mask assertion there (1 failed in 0.15 s). That misplaced test temp was removed; no ACL inspection or full-suite run
  followed because the focused run failed. Next attempt must pass the same absolute basetemp using forward slashes in
  `PYTEST_ADDOPTS` and verify pytest actually used it before continuing. No commit or push.
- 2026-11-20 service-quote planning reconciliation: updated area 6 sections 1.3, 2.3, 3.3, 3.5, 5.3, 9.3 and 10.2;
  area 7 section 1.3; area 8 sections 1.3 and 3.1; and area 15 section 3.5 with the confirmed service-quote rules.
  Area 17 section 4.4 already states Warranty/goodwill reporting by `cost_destination`. Updated
  `docs/next_step.md` with the current planning state and area 5, 14 and 18 handoffs. Area 5 invoice tax/accepted-line
  carry-forward and area 14 send-back routing remain for their owners; area 18 owns the `service_goodwill` role.
  Planning only: no tests run; no code, migrations or baselines changed. **Commit: none; push: none.** Existing
  unrelated tracked and untracked worktree paths are preserved. Next: planning review, then owner selects the next
  area; do not begin baseline/code work before full replan approval.
- 2026-11-20 service-quote reconciliation follow-up: area 18 sections 4.2, 4.3 and 4.5 now define the configurable
  `service_goodwill` System account mapping, its company-baseline landing and later tests. A company may map it to the
  Warranty Expense GL account, while the role and area 7 `cost_destination` remain distinct for area 17 reporting.
  Read-only cross-area consistency review completed for areas 6, 7, 8, 15, 17 and 18; findings are held for planning
  review. `git diff --check` is the verification; no tests, staging, commit or push. Existing unrelated changes and
  untracked paths remain preserved.
- 2026-11-20 service-quote consistency corrections: area 6 §§9.3–9.4 align signed totals and budget with accepted
  work, area 7 §§1.3 and 1.6 and area 8 §7 distinguish warranty from goodwill, and area 15 §0 ties In progress
  to the start of estimate cost work. Docs review only. Commit and push pending owner review.
- 2026-11-20 Phase 2.9 area 5 drafted for review. Sections 0–7 cover customer intake, signed quote billing and
  tax, sales documents, receivables, controls and cross-area boundaries. Q1–Q10 await Mark. Docs only.
  Tests, staging, commit and push: none.
- 2026-11-20 5:00 PM owner decision: closed area 5 Q5 default precedence in §8 and aligned area 6 §5.3 and
  area 8 §1.3. Sample service types ship with Due on completion and no deposit. The revision copies its
  service type's configured schedule. Planning only. Tests, staging, commit and push: none.
- 2026-11-20 area 5 review: applied the 5:15 PM Q5 decisions to billing rules, conflicts and later tests.
  Area 5 §5.3 lists four Area 4 dependencies. Refreshed §7, including the remaining paid multi-job edit and
  cleared-refund void questions. Planning only. Tests, staging, commit and push: none.
- 2026-11-20 owner approved Area 5 Q2–Q4. Section 8.2 records identity and issue, one-job sales invoices,
  same-number allocations and paid voids. Updated planned tests and flagged the owner pay app issue boundary.
  Q5 remains closed. Planning only. Tests, staging, commit and push: none.
- 2026-11-20 Area 4/5 boundary confirmed against the 8:30 PM owner entry. Owner approval claims one linked
  invoice draft and locks the certified pay app. Area 5 issues or sends through normal posting. Area 4 retains
  billed-to-date timing and void/reissue rules. Q6–Q7 remain for review. Tests, staging, commit and push: none.
- 2026-11-20 Mark approved Area 5 Q6–Q7 product rules. Area 5 records source quantity claims, the pre-tax NTE
  block, frozen issue tax and linked credit/refund treatment, plus planned tests and source/tax handoffs.
  Q1 and Q8–Q10 and the stated dependencies remain for review. Tests, staging, commit and push: none.
- 2026-11-20 Mark approved Area 5 Q1 and Q8 product rules. Sections 1.3, 4.2, 5.2, 7 and 8.4 record contact
  people, historical statement cutoffs, exact sent copies and planned tests. Primary replacement and retention
  duration remain open alongside Q9–Q10 and the tax and source handoffs. No tests, staging, commit or push.
- 2026-11-20 Area 5 follow-ups: signing preserves an existing customer's primary and saves the signer on the
  revision. Sent statement retention follows company policy, with retain-and-review when absent. Q9–Q10 and the
  Area 4, tax and source handoffs remain open. Planning only. No tests, staging, commit or push.
- 2026-11-20 Mark approved Area 5 Q9–Q10. Section 8.5 records refund sources and reversals, per-write-off expense
  selection, authority and approval defaults. Planned tests and handoffs updated. No tests, staging, commit or push.
- 2026-11-21 Area 4 draft ready for owner review. It records certified draft creation, deposit and retainage
  inputs, proposed billed-to-date effects and draft cancellation options. Q1–Q5 await Mark. No tests, staging,
  commit or push.
- 2026-11-21 Mark approved Area 4 draft cancellation and billed-to-date timing. Sections 4–7 record claim
  disposition, effective posted effects, schema and planned tests. Q2–Q4, Q5 authority and invoice edits,
  and decertification remain open. Planning only. No tests, staging, commit or push.
- 2026-11-21 Mark approved Area 4 Q2 and Q3. Updated funded deposit and posted retainage rules, schema and
  planned tests. Q4, Q5 invoice edits and authority, and decertification remain open. No tests, staging,
  commit or push.
- 2026-11-21 Mark approved Area 4 Q4: inclusive accounting-effective-date cut-off with revision-level source evidence; a late posting or correction that changes a sent application requires a new revision; missing/zero budget needs an authorized, reasoned manual amount or percentage; stored-material installation is a linked equal transfer with zero cumulative earned-value change. Updated schema notes, planned tests, shared decisions and handoff. Q5 authority and invoice-only edits, plus decertification, remain for review. Planning only; whitespace checked, no tests, staging, commit or push.

- 2026-11-21 Mark sent Payments/AR triage (1:45 AM). Added must-fix source inputs and named proof tests for posted/as-of status, operation-ID retries, allocation release and stable invoice identity, deferral target consistency, close locks, service boundaries, authorities and account routing to the schema-replan Inbox inputs and `docs/next_step.md`. Recorded the mockup findings in the UX research inbox. Docs only; no tests or code changes.
- 2026-11-21 Mark approved Area 4 Q1 and Q5 (2:50 AM). Recorded the PM/customer approval flow, Reject behavior before and after invoice posting, invoice draft certified-amount edit boundary, business roles, schema event notes, and named planned tests. Updated the Area 4 handoff and decision brief. Docs only; whitespace checked; no tests or code changes.
- 2026-11-21 Mark sent users, controls and audit-history triage (3:10 AM). Closed Area 18 O6 from Area 13's attachment-removal lock rule and updated the planned lock test. Confirmed the remaining access, audit-history, settings-preview and reason requirements are already covered. Sent the 11 UX findings and the Approvals retest handoff to the UX inbox. Docs only; whitespace checked; no tests or code changes.
- 2026-11-22 Folded the owner decisions of 2026-11-22 (items 1–26, OD-01 to OD-18) and the 12:47 PM follow-ups into Phase 2.9: Area 4 Q5–Q7 decided (`payapp.adjust`, logged PM request, adjust creates a new revision); Area 5 recorded approved (2:15 AM) with §9 amendments and Q11/Q12 decided; Q12 replaces the 11/20 tax-freeze rule (signed price pre-tax, tax at invoicing) with dated amendments in Areas 5, 6, 7, 8, 15 and the service-quote reconciliation; Area 18 §8 (chart of accounts, system accounts, four new sensitive codes, 111 → 115, Q25 decided); Area 10 recurring auto-post confirmed; Areas 7 and 17 amendments; undrafted-area decisions and v1.1 field scope inputs in next_step, Area 8 and Area 18. Docs only.
- 2026-11-22 Owner round 2 (1:56 PM): Area 5 Q7a, Q7b, Q7e (accrual-only sales tax; write-off posts in full with no tax split) and Q8 (7-year statement retention, flagged, never auto-deleted) decided; Area 5 is ready for full-plan approval. Area 17 gains the "Sales tax in written-off invoices" report. Area 6: signed `tax_cents` renamed `estimated_tax_cents`, `total_cents` no longer signed, signing tests renamed; Hughes values are pre-tax. Area 15 expected value corrected to the sent `contract_total_cents`. Docs only.
- 2026-11-22 Owner decided the Area 17 written-off sales tax report shows the proportional share for a partial write-off (invoice tax × share written off; $82.50 × 50% = $41.25), with a planned test. Docs only.
- 2026-11-24 Added test_entry_numbers_continue_across_fiscal_years (tests/test_ledger_posting.py): entries dated 2026-12-31 and 2027-01-02 with an FY2026 year close between them are JE-000001 and JE-000002; the close posts nothing (B1) and the sequence never resets by year (L4). Test only; no code change.
- 2026-11-24 Folded the mockup code-hygiene audit (items 1-15) and the owner answers of 2:55 PM (unapplied customer payments), 3:05 PM (OD-80, OD-81), 7:30 PM and 8:15 PM (write-off credit hold, close-checklist Skip) as dated amendments: CLAUDE_UI.md rule 6, design.md section 1, Areas 5, 6, 10, 13, 17 and 18, next_step. Planning proposals unless an owner answer applies; items 4, 6 and 14 already covered. Docs only.
- 2026-11-24 Drafted Phase 2.9 Area 1, payments and receipts (docs/replan_2.9/area_1_payments_receipts.md), from the outline approved by the owner 8:55 PM (Q1, Q2, Q3, Q4, Q6, Q7, Q8; Q5 and Q9 recommended defaults): user-chosen receipt destination and deposit account, unapplied cash on the Unapplied customer payments role, user Unapply with RP11 rewritten, a company-editable payment method list, no payment.void, optional receipt fee, operation IDs and as-of status for applications, refund, write-off and statement services. Pointers in Areas 2, 5, 6, 10, 12 and 18 §8.12 and beside RP11. Docs only; awaiting approval.

- 2026-11-24 Drafted Phase 2.9 Area 14, approvals (docs/replan_2.9/area_14_approvals.md), with the owner answers of 10:05 PM and 10:20 PM (Q1-Q8): `approval_kind` with 21 kinds (six new, all OFF), policies and steps by anyone with permission, the job's PM, a role, people or a chain with a backup, one inbox; reasons only on Reject and Send back; edits after approval void it (Bills keep Area 3 Q4), a posted document edit is held as a pending revision; the lock check runs again at final approval; unavailable approvers move to the backup, Admin or the Master; the submitter may self-approve with a reason when no other eligible approver exists. Reviewer (Opus) and two Sonnet QA passes fixed. Pointers in Areas 1, 2, 3, 5, 6, 8, 13, 15 and 18, next_step and roadmap. Docs only; Q8 answered 10:40 PM (option A: journal entries excluded from the fallback; the triggers stay). Awaiting approval.
- 2026-11-24 Area 14 (approvals) approved by the owner at 10:40 PM after the final QA (Opus reviewer and Sonnet QA; text fixes only, no integrity change): Q8 option A, journal entries excluded from the self-approval fallback and the two separate-approver triggers stay; tests added for the Special cutoff and the Q8 exclusion; 14 of 21 areas approved. Docs only.

- 2026-11-24 Drafted Phase 2.9 Area 9, materials, units, purchase orders, subcontracts and inventory (docs/replan_2.9/area_9_materials_pos_inventory.md), with the owner answers of 11:05 to 11:35 PM: add-and-deactivate units (OD-51 settled), stock tracking as a Company control OFF by default, one commitment record for POs and subcontracts, free-text to-be-coded request lines, and a driving read-only cost code on every line that has a material code. Opus review and Sonnet QA fixed; the cost code rule checked against OD-80 and Areas 6, 7 and 3 (conflicts flagged in section 15). Pointers in Areas 3, 6, 7, 8, 10, 13, 14 and 18. Docs only; awaiting approval; Q1-Q7 open.

- 2026-11-24 Revised Phase 2.9 Area 9 for the owner answers to section 16 Q1 to Q7 (11:30 to 11:43 PM): matching is a Company control OFF by default; stock costing is moving average or FIFO picked once and locked; no free-text PO lines; a bill line matched to a PO line is locked to its job and cost code (the override removed); units can be reactivated; a recoded request line takes the material's cost code and notifies the PM; a bill's price difference on stock splits between stock value and a new controlled Stock price differences role, with no purchase price variance; one item list (a stocked item is a material code), with the 64 versus 18 sample mismatch and the inventory unit picker mismatch reported. Pointers corrected in Areas 3, 6, 10 and 18 and an amendment appended to docs/po_ap_matching_design.md. Docs only; awaiting approval.
- 2026-11-25 Area 9 (materials, units, purchase orders, subcontracts and inventory) approved by the owner at 12:31 AM after the last fix: "Hold bills that do not match the receipt" holds the bill before approval and routes it to the job's project manager (live Settings > ERP text), not payment; both matching controls are OFF by default. 15 of 21 areas approved. Docs only.

- 2026-11-25 Drafted Phase 2.9 Area 20, connections, company email, capture inbox, company calendar, notifications and Playbook (docs/replan_2.9/area_20_connections_email_notifications.md), with the owner answers of 12:37 AM (every notice in-app always and email opt-in per user and per kind; weather OFF until an Admin turns it on) and the earlier CAP-04, CONN and OD-24 decisions: a mailbox connection with no secrets in the company file, an insert-only email log, a capture tray with human-confirmed drafts and 30-day retention, a company calendar with a stable UID and its own SEQUENCE, a notification feed moved here from Area 21, and Playbook tables. Pointers in Areas 2, 3, 6, 8, 9, 14, 15 and 18 and markers on three next_step lines. Opus review and Sonnet QA fixed. Docs only; awaiting approval; A20-Q1 to Q4 open.
- 2026-11-25 Revised Phase 2.9 Area 20 and Area 9 for the owner answers of 12:50 and 12:53 AM: desktop secrets in the Windows credential store (AG1's DATA_DIR\Secrets superseded), mail read every 15 minutes while the app is open (Admin may choose 5) plus Check now, the weather service receives only the job site address, a purged capture message leaves a content-free stub (fingerprint, sender, dates); serial tracking is in per material code, OFF by default, recorded at receipt, picked at pull and kept on the job's record (new stock_serial and stock_serial_history tables, Area 9 section 8.3). Docs only; Planning reviews, then the owner approves Areas 9 and 20 together.
- 2026-11-25 Areas 9 and 20 approved by the owner at 1:00 AM as committed in 43e824e: Area 20 (connections, company email, capture inbox, calendar, notifications, Playbook) owner-approved, and Area 9 re-approved with serial tracking (section 8.3). 16 of 21 areas approved; Area 1 drafted and awaiting approval; Areas 11, 16, 19 and 21 to draft. Docs only.

- 2026-11-25 Drafted Phase 2.9 Area 11, fixed assets, depreciation, disposals and loans (docs/replan_2.9/area_11_fixed_assets_depreciation_loans.md), with the owner answers of 1:21 AM (straight-line and declining balance; book depreciation only): an asset register on the Area 10 schedule pattern, a monthly depreciation run with a balanced worked entry, a disposal record carrying the decided ASSET-02/03/04 rules and three worked disposal entries, loans whose payments are drafted as bills split into principal and interest, and a current-portion reclass control (OFF). Pointers in Areas 3, 10, 13, 14 and 18. One Sonnet QA pass fixed. Docs only; awaiting approval; A11-Q1 to Q4 open.
- 2026-11-25 Revised Phase 2.9 Area 11 for the owner answers of 2:09 AM (split shown always with a posting control OFF; a loan paid to the dealer is the dealer's bill plus a loan-funded payment, Dr Accounts payable / Cr Loans payable with no bank line; disposal month setting with Full month default and No depreciation in the disposal month, truck gain $3,720.00 versus $2,746.67; job charging stores the flag and rate only) and two planning fixes (November never charged twice; line-of-credit example ties at $65,000.00 then $55,000.00). Docs only; awaiting approval.
- 2026-11-25 Owner approval at 2:49 AM: Area 1 (payments and receipts, 61706a1, with the Loan funded payment method and the A1-LOC line-of-credit rule) and Area 11 (fixed assets, depreciation, disposals and loans, c464cc1) approved; the area headers, next_step and roadmap record it. 18 of 21 areas approved; Areas 16, 19 and 21 to draft. Docs only.

- 2026-11-25 Drafted Phase 2.9 Area 16, custom fields (docs/replan_2.9/area_16_custom_fields.md): the baseline `custom_field_def` and `custom_field_value` kept; Lead and Case record types (Area 15 Q23 A); a `custom_field_service_type` scope with a shown-from stage per service type; a User data type; board-card flag, help text and row version; warnings (never limits) at more than 2 board-card fields and over 20 active fields; Remove stays Make inactive; the area posts nothing. Pointers in Areas 6, 8, 15, 17 and 18. One Sonnet QA pass. Docs only; awaiting approval; A16-Q1 to Q5 open.

- 2026-11-25 Revised Phase 2.9 Area 16 for the owner answers of 2:58, 3:05 and 3:09 AM: a CRM custom field belongs to one service type, then one stage (the definition carries service_type_id and stage_id; no scope table, no Applies to), CRM lead fields only; a service type change keeps the old type's values hidden and audit-logged; a User field picks any active user; no custom fields for service cases ('Case' removed from Area 15 Q23 A); job delivery-stage fields stay a separate set, not designed here. Pointers corrected in Areas 6, 7, 8, 15 and 17. Docs only; awaiting approval; A16-Q6 to Q8 open.

- 2026-11-25 Revised Phase 2.9 Area 16 for the owner answer of 3:47 AM: custom fields are for CRM leads only; record_type allows 'Lead' only; the company-wide custom fields on Estimate, Contact, Invoice, Bill and Project are dropped (they use built-in fields and notes); Area 6 Q25 A is withdrawn; old rows are archived read-only in custom_field_legacy, not deleted (planning reading); matching tests and hand-offs removed and test_custom_field_record_type_is_lead_only added; open questions renumbered A16-Q7 to Q9. Pointers in Areas 3, 6, 7, 8, 13, 15, 17 and 18. Docs only; awaiting approval.

- 2026-11-25 Area 16 recorded the owner answers of 11:39 AM: A16-Q7 (A) a lead field shows from its stage onward; A16-Q8 (A) Copy skips and lists a field with no matching stage; A16-Q9 (A) job delivery-stage fields are a later, separate set, jobs get no company-wide fields. Examples now use lead stages (Site assessed, Proposal reviewed). No open owner questions; A16-Q4 stays a planning reading. Docs only; awaiting approval.

- 2026-11-25 Owner approval 1:18 PM: Area 16 (custom fields, 23a8b6b) approved; 19 of 21 areas approved (18, 13, 12, 10, 17, 8, 15, 6, 7, 5, 4, 3, 2, 14, 9, 20, 1, 11, 16). Areas 19 and 21 to draft. Docs only.

- 2026-11-25 Drafted Phase 2.9 Area 19, payroll import (docs/replan_2.9/area_19_payroll_import.md): staged batch and `payroll_import_line`, a mandatory review digest, one balanced entry with job and cost code and a credit to Payroll clearing, `time_entry` rows with source links and negative reversal rows, an optional Labor accrual control (OFF) with automatic reversal, wages hidden without `payroll.view`. Pointers in Areas 5, 12, 14 and 18. Sonnet QA pass. Docs only; awaiting approval; Q1 to Q7 open.

- 2026-11-25 Revised Phase 2.9 Area 19 for the owner answers A19-Q1 to Q9, Q3b and Q7b (2:15 to 3:00 PM): entry from the file's rows; file kept as long as the entry; the labor accrual built in v1 as a separate accrual posting type (`journal_line.cost_nature`, Actual, Accrued and Total, profit with and without accruals, never in T&M or a pay app; pointers in Areas 5, 7 and 17); Q4, Q5, Q6 recorded; "Card and spend import" as its own v1.1 area (Area 12 pointer updated); burden split by who pays (Accrued burden; 1,655,660 and 40,000 example); 0-hour and negative rows (50000 and -18000 example); 1 cent does not block Post, 2 cents or more does. Docs only; awaiting approval.

- 2026-11-25 Area 19: recorded owner A19-Q10 (3:15 PM): job percent complete and budget-to-actual count Actual plus Accrued (budget 5,000,000, Actual 1,000,000, accrual 453,120 -> 29.1%); the all-job-cost-accruals rule is an owner rule (Q3b); one area set (producers 19, 9, 3; readers 7, 17, 5) with pointers added in Areas 3 and 9 and the Area 5, 7 and 17 pointers updated. Docs only; Area 19 still awaiting approval.

- 2026-11-25 Drafted Phase 2.9 Area 21, whole-app setup and conversion (docs/replan_2.9/area_21_whole_app_setup_conversion.md): `row_version` and `StaleVersionError`, `company_policy` records, the opening balances conversion batch (one linked entry per item, OBE close), company creation and switching, entities and consolidation, the calendar query and per-user alert state, other whole-app items; 13 owner questions open. Pointers in Areas 3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 and 20. Docs only; awaiting the owner's answers.

- 2026-11-25 Revised Area 21 for owner answers A21-Q1 to Q13, Q2b and Q5b: per-entity balance; elimination draft in the month-end review; intercompany AR/AP charge at payment (50,000 example); one opening depreciation entry per asset; no automatic OBE move (hard warning and a choice; example OBE 5,425,333 -> 0 with Owner's capital 1,000,000 and Retained earnings 4,425,333); two conversion methods, no Retained earnings roll unless a year end, monthly trial balance change (6,000,000 example); policy records, row_version, mid-month go-live, full subsidiary copy, alerts, export and reassign answers recorded. Pointers in Areas 1, 2, 3, 5, 7, 8, 11, 13, 16, 18 and the decisions file. Docs only; awaiting owner approval.

- 2026-11-25 Area 21: recorded owner A21-Q2c (both cross-charging cases, each stating whose books hold the supplier bill; 50,000 WSB/WEC examples for case 1 and case 2; clearing accounts per entity pair; tests for both cases including no double expense in case 1); Area 1 and Area 3 pointers updated; Design message appended to to_design.md at the owner's request. Docs only; awaiting owner approval.

- 2026-11-25 Area 21 §7 revised to the design chat's intercompany model (owner A21-Q2d): 1800/2800 clearing at bill entry, automatic transfer to 1210/2210 at payment, case 1 uses the same transfer, split bills (50/30/20 of 1,000,000) stored per bill with the last row absorbing rounding, elimination nets 1800/2800 for unpaid bills and 1210/2210 after transfer, memo 'Paid by WSB' with no AP posting; chart check found 2210 = Use Tax Payable (clash, not renumbered) and AP = 2010, AR = 1110; Area 1 and 3 pointers and next_step updated. Docs only; awaiting owner approval.

- 2026-11-25 Area 21: recorded owner A21-Q2e (New IC AP number): IC AP is 2220 everywhere in Area 21 (Use Tax Payable stays 2210; 1210, 1800, 2800 stay); account-number open item closed; Area 1 and 3 pointers updated; design told in to_design.md. Docs only; awaiting owner approval.

- 2026-11-25 Area 21: recorded owner A21-Q13a to Q13d (automatic for anyone with the WSB user in WEC's audit trail; block the save when either company's period is closed, same for transfer, voids and credit memos; pay run full amount, net later, 500,000 less 100,000 = 400,000; no split on PO-matched bills); four section 13 items closed; tests added; design told in to_design.md. Docs only; awaiting owner approval.

- 2026-11-25 Area 21: recorded owner A21-Q2f (companies assign their own GL codes; accounts are found by role, stock numbers are defaults only); checked Area 1/3 (no chart setup there; existing system_role mechanism and Area 18 section 8.1 cover six roles), added the four intercompany roles, a 'System accounts' setup task and per-entity-pair mapping; tests by role; pointers in Areas 1, 3, 18; design told in to_design.md. Docs only; awaiting owner approval.

- 2026-11-25 Area 21: per-counterparty role mapping defaults to one account per role for all partners, separated by the trading-partner tag on each line; pair rows override (planning reading). Docs only.

- 2026-11-25 Area 21: recorded owner A21-Q13e (Available after pay run, full run plus IC line, 25,510,412 cents example), Q13f (transfer posts with the payment, no separate approval), Q13g (OBE stays open until an Admin turns it off at a zero balance; close checklist item; Area 18 section 8.1 exception flagged); three section 13 items closed; tests added; pointers in Areas 2, 13, 18; design told in to_design.md. Docs only; awaiting owner approval.

- 2026-11-25 Area 21 (whole-app setup, conversion, entities, intercompany) approved by the owner at 024efb3 (10:18 PM, "Approve Area 21 (Recommended)"); status set to approved in the area file and next_step.md; all 21 areas approved. Docs only.

- 2026-11-26 Area 18: recorded owner CON-Q9 to Q13 in section 2.4.4 (Controller = Accountant · Manager; General Manager preset, updating Q21; Viewer = View only on all 3 roles; preset list = 15 shipped + General Manager + Viewer + saved; preset sets role and level, level editable); Admin row and matrix grouping marked Planning reading; area stays approved. Docs only.

- 2026-11-26 Area 18: recorded owner CON-Q14 (General Manager preset, Defaults + reports): report.job_cost already in both caps, report.financial outside them; preset adds Accountant · View only with three Remove overrides (planning reading), scope All; final code list in section 2.4.4; the codes-and-scope item closed; area stays approved. Docs only.

- 2026-11-26 Area 18: custom-access fixes: checked the 34-code General Manager list against the caps (list right; printed caps table stale, current caps printed: 80, 32, 46), added a 10-pair create-and-approve list as a Planning reading, listed the shipped-template gaps, recorded owner CON-Q15 (deleting a template in use: Admin picks, default keep as personal changes); area stays approved. Docs only.

- 2026-11-26 Area 18: reprinted the six stale shipped-template code lists with amendments merged and the two union rows as explicit lists (cap-checked in Python); placed Area 9's three codes and Area 14's 11 approve codes as Planning readings (cap, level, template); added 14 create-and-approve pairs; caps re-counted (80, 32, 46) -> (99, 34, 51); area stays approved. Docs only.

- 2026-11-26 Area 18: printed the full current caps (Accountant 80, Sales rep 32, Operations 46), all 15 shipped template lists with the placements marked, the 14 placements and 24 create-and-approve pairs, in full, in to_design.md ("Full caps and template lists"); counts and cap checks in Python ((99, 34, 51) with the placements); removed the stale "Next: an area chosen by the owner" section from next_step.md. Docs only; Area 18 stays approved.

- 2026-11-26 Area 18: answered for design that a shipped template's code list is added on top of the level defaults (effective-access rule steps 2 to 4, section 2.7), with the level that gives bank.feed, bank.reconcile and lead.view/create/edit to Controller, Staff accountant, Sales rep and Sales manager; fixed the * marking of section 8.2's four codes (decided, no *); in to_design.md under "Template and level: how they combine". Docs only; no Area 18 change.

- 2026-11-26 Area 18: recorded owner CON-Q16 (Controller and Staff accountant templates both hold customer_refund.issue, invoice.write_off and payment.unapply); Controller 37 + 33 sensitive, Staff accountant 18 + 3 sensitive, both inside the Accountant cap (99, checked in Python); Controller trips 15 create-and-approve pairs, Staff accountant none; lists in to_design.md under "CON-Q16: refund and write-off codes in templates". Docs only.
