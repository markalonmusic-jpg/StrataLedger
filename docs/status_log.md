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
