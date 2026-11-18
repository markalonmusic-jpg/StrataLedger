# File map and design-doc index

Moved unchanged from CLAUDE.md section 2 on 2026-11-12. CLAUDE.md keeps the short map. Update a design doc's
status line here when its area is built.

Paths are defined once in `config.py` (decision P2a); never hardcode a path
anywhere else, and no machine path (such as a user profile folder) may appear
in code (`tests/test_config_paths.py` fails on one).
- `RESOURCE_DIR`: the folder the app runs from (`sys._MEIPASS` when frozen,
  else the folder of `config.py`). Read-only: migrations, fonts, templates, help.
- `DATA_DIR`: where the app writes (databases, `Companies/`, `Backups/`,
  `Logs/`, `Uploaded_Files/`). `STRATALEDGER_DATA_DIR` if set; else
  `%LOCALAPPDATA%\StrataLedger-dev` when running from source (AX3, never the
  repo); else `%PROGRAMDATA%\StrataLedger` when frozen.
  `BASE_PROJECT_DIR` is kept as an alias of `DATA_DIR`.

- `app_strata.pyw` - main entry point, QuickBooks-style
  "No Company Open" launcher, session state manager (`self.db` pointer), and
  master layout (Sidebar + Workspace + right-hand AI Copilot drawer).
- `config.py` - theme styling (`Theme` class), `RESOURCE_DIR` / `DATA_DIR` and the paths derived from them.
- `templates/coa/` - the approved chart-of-accounts templates (`construction.csv`, `general.csv`, decision I1)
  and their README. Read through `modules/services/storage.py` and `chart_templates.py`; "Import my own CSV"
  uses the same parser (`csv_table.py`).
- `requirements.txt` - runtime packages (`customtkinter`, `tzdata`, `cryptography` pinned for the key store, KS1).
  `requirements-dev.txt` adds the developer tools (pytest, PyInstaller); `tools/check_frozen_crypto.py` checks a
  frozen build still runs AES-GCM. `tzdata` is a hard requirement: if a
  company's time zone cannot be loaded, `open_company` raises `InstallationError` ("reinstall"); there is no
  fallback to the UTC date. The test environment installs it too, and the time-zone tests never skip.
- `migrations/` - the baseline schema, one file per database kind
  (`001_company.sql`, `001_master.sql`), which `database.py` runs to build
  databases at runtime. Until the first release these files are edited
  directly (section 5); after it, changes are numbered 002 and up.
- `archive/migrations_chain_v5/` - the migration chain that preceded the
  baseline (company 001-005, master 001-003). Historical, never applied.
  Do not read, search or copy from `archive/` unless the task names it.
- `archive/baseline_pre_2_5/` - the company baseline as it stood before the Phase 2.5 edits (tag
  `baseline-pre-2.5`). Historical, never applied.
- `archive/baseline_pre_2_5_1b/` - the company baseline before 2.5 step 1b (tag `baseline-pre-2.5-1b`).
  Historical, never applied.
- `archive/baseline_pre_2_5_3b/` - the company and master baselines before 2.5 step 3b (tag
  `baseline-pre-2.5-3b`). Historical, never applied.
- `archive/baseline_pre_2_5_1d/` - the company and master baselines before 2.5 step 1d. Historical, never applied.
- `archive/baseline_pre_2_5_4/` - the company baseline before 2.5 step 4 (tag `baseline-pre-2.5-4`). Historical,
  never applied.
- `archive/instructions/` - superseded Claude Code prompts and addenda. History only.
- `archive/design_drafts_2026-11/` - design drafts for unbuilt areas that nothing but other docs cited (moved
  2026-11-15): AI Copilot, bank feeds, cloud migration, export, inventory and fixed assets, loans, pay
  applications, Philippines tax; and the old CustomTkinter visual spec (from `docs/design.md`, 2026-11-15).
  Its README lists them; move one back to `docs/` when its step starts.
- `accounting_librebase.db` - reference snapshot of the company baseline,
  generated on demand (see section 5). Not read at runtime; not kept in git.
- `system_master.db` - global authentication and routing database
  (`app_user`, `company_registry`, `user_company_access`). Never put company
  accounting tables (`contact`, `invoice`, `journal_entry`, etc.) here.
- `Companies/` - isolated `.db` file per company/subsidiary
  (`Companies/<CODE>.db`).
- `.db` files are not tracked by git (`.gitignore`).
- `docs/accounting_schema.txt` - planning reference for the schema (see
  section 5).
- `docs/crm_pm_design.md` - design draft for the CRM, project lifecycle,
  service cases, customer/vendor codes and throughput tracking. NOT BUILT,
  except customer and vendor codes (Phase 2.6, `services/contacts.py`).
  Read it before touching anything in these areas.
- `docs/controls_audit.md` - controls and analytics audit of the schema, with
  the decisions taken and what each migration closed.
- `docs/schema_audit.md` - the first (Phase 1) schema audit.
- `docs/po_ap_matching_design.md` - design draft for purchase orders,
  subcontracts, receiving and PO-to-AP matching, with retainage payable.
  NOT BUILT.
- `docs/roles_permissions_design.md` - design draft for roles (per company,
  customizable), permissions, approval limits, separation of duties, project
  scope, and the Master / Admin model. Services BUILT in Phases 2.2-2.4
  (`permissions.py`, `authz.py`, `approvals.py`, `users.py`,
  `role_templates.py`); approvals wired into ledger posting in 2.5 step 4
  (`ledger.submit_entry_for_approval`, the posting gate); refusals are plain sentences with no permission code
  (`authz.denial_message`, R27; amounts in sentences through `money.py`); the role and approval screens are
  Phase 3.
- `docs/audit_readiness_design.md` - design for audit readiness: threat model, the keyed HMAC chain over
  posted entries, checkpoints, keys (KeyProvider, DPAPI, recovery-code wrap), encryption at rest (after v1),
  the Auditor role, audit trail reports, Audit-ready mode, backup checksums, and the Step 1b prompt.
  PARTLY BUILT (2.5 steps 1b, 3, 3b: chain schema, sealing on post, verification and checkpoints). Not built:
  the keystore (step 1c), encryption, the Auditor role, the reports and backups.
- `docs/password_recovery_design.md` - design for password recovery: Admin/Master reset with a generated
  temporary password (72 h, forced change), personal backup codes for regular users, the Master's recovery
  code for every change (re-wraps the installation key, Step 1c), abuse limits, session end after a reset,
  optional email (last), TOTP hook (v1.1). NOT BUILT; decided (PW1-PW11).
- `docs/help_system_design.md` - design for the built-in offline help (`help/*.md`
  articles, `modules/services/help.py`, the `?` / F1 panel, the `page_key` of
  every screen). Content is deferred to the end of v1.0. NOT BUILT.
- Design docs are read before touching their areas. Where a design doc's
  PROPOSED migration numbers differ from section 7, section 7 wins.
- `docs/next_step.md` - the next step's plan, open questions, counts and HEAD, overwritten at each STOP; a new
  session reads it first (CLAUDE.md section 8).
- `docs/decisions_2026-11-11.md` - the owner's decisions by code, with an index of every code at the top (find
  one by searching its code). `docs/role_templates.md`, `docs/csv_import_design.md`.
- `docs/design.md` - the authoritative system and product design (owner rulings, 2026-11-15; AQ1, AQ2):
  databases and in-file entities, append-only lines and `clearing_id`, editable posted documents vs reverse-only
  journal entries, `bank_statement_line` and tick-off reconciliation, the two-step Pay Run and `bank_payee_id`,
  service types, Estimate = Contract, cost codes, dimensions, receiving, pay apps, the `pywebview` front end.
  Mostly PLANNED; section 10 lists what the baseline lacks, section 11 the open questions. Its earlier
  CustomTkinter visual spec is archive/design_drafts_2026-11/visual_spec_customtkinter.md (CLAUDE_UI.md governs
  screens).
- `modules/services/` - the service layer (rules 7, 10, 11, 15): every write and every protected read.
  `tx.py` (the write transaction and read connection; a database error in a write is logged and raised as
  `SaveFailedError`, R35), `context.py` (`ServiceContext`), `authz.py`
  (`authorize`), `errors.py` (typed exceptions), then one module per area (auth, users, companies, accounts,
  contacts, periods, approvals, ledger, ledger_chain, ledger_verify, keys...). Section 7 says what each step built.
  `key_wrap.py` (Step 1c) is the only importer of `cryptography`: AES-256-GCM key wrapping bound to its row by
  associated data, and the recovery-code key from scrypt (KS2, KS4). `key_store.py` (Step 1c) makes the
  installation key at first run (`auth.create_first_master(..., machine_wrap=)`; DPAPI copy plus recovery copy)
  and holds `LocalKeyProvider`, which unlocks it at start-up (status unlocked, locked or missing), makes and
  stores each new company's chain key and finds it by fingerprint; `App.start_key_store()` sets it as the
  provider. The test switch `use_test_key_for_new_companies` works only under STRATALEDGER_ALLOW_TEST_KEYS.
  Since Step 1d it reads the ACTIVE `installation_key` row (the table keeps history) and records which
  installation key wrapped each company key. `ledger_keys.py` rotates a company key and starts a key-lost epoch,
  whose `Key lost` checkpoint `ledger_verify.py` signs in the same transaction; `ledger_verify.py` then verifies
  from the entry after it and reports the earlier range as unverified (`unverified_note`).
  `installation_keys.py` (Step 1d) replaces a lost installation key (Master, typed `NEW LEDGER KEY`) and starts a
  key-lost epoch in every company; `remaining_companies` / `finish_remaining_companies` complete any left behind.
  `hooks.py` and `addons.py` (Phase 2.7 STOP B, HA1-HA7): `ledger._seal_and_post` fires `entry.posted` (and
  `entry.voided` for a Void) through `hooks.fire`, inside the posting transaction; only enabled add-ons' handlers
  run, under `database.addon_write_guard`. `addons.py` is the only importer of add-on code, from
  `RESOURCE_DIR/addons/<key>/` (`addon.json`, `addon.py`, `migrations/<key>_NNN.sql`); `addon.manage` gates it.
- `tests/` - pytest suite. `scripts/` and `tools/` - developer tools. `.claude/agents/` - subagents.
- `modules/` - screens and the database layer. LEGACY screens (the files in `CONNECT_ALLOW_LIST` in
  tests/test_static_rules.py: `views_billing.py`, `views_payroll.py`, `views_registry.py`, `views_wizard.py`,
  `views_user_profile.py`, and the launcher in `app_strata.pyw`) still run their own SQL; Phase 3 rewrites
  them. Do not copy their patterns. The pattern to copy is `views_first_run.py` + `first_run_model.py`.
  - `database.py` - connections (foreign keys on, 5-second busy timeout; WAL files, AX1), the baseline
    runner and the pre-release hash guard; `backup_database`, `prune_backups` (E7) and `restore_database` (AX2,
    K5 checksum); the add-on handler write guard (SQLite authorizer, HA2) and the add-on migration runner
    (`apply_addon_migrations`, HA4, HA6), which gives add-on tables audit triggers from
    `migrations/addon_audit_triggers.sql` (HA9).
  - `views_dashboard.py` - Customers Command Center / Flight Deck.
  - `views_registry.py` - Customer Master List with live SQL search filtering.
  - `views_wizard.py` - Customer Intake & Edit form (Construction and B2B SaaS
    channels).
  - `views_billing.py` - LEGACY multi-line Invoice/Bill/Credit Memo form. Not working: its SQL names
    tables and columns that are not in the baseline (`chart_of_accounts`, `dimension_node`,
    `contact.display_name`, `project.project_name`, `invoice_line.parent_dimension_id`).
  - `views_payroll.py` - workforce HR and time-entry logging (`time_entry`).
  - `views_new_company.py` - the four-step New Company wizard (decision S5) over
    `companies.create_company`; no SQL. Its defaults, checks and error wording are in
    `new_company_model.py` (no Tk, unit tested). It asks for a sign-in first (the launcher has no user);
    only the Master, or an Admin creating a subsidiary, gets past it.
  - `views_first_run.py` - the first-run setup screen (decision S10), shown instead of the login when
    `system_master.db` is missing or has no users: Welcome form, create the Master, the one-time recovery code
    (Copy button, required "I have saved this code" box), sign in, then offer "Create your first company" or
    "Later". Routing, form checks and wording are in `first_run_model.py` (no Tk, unit tested); the state check is
    `auth.inspect_master`. Page key `setup.first_run`.
  - `platform_support.py` - the one place for operating-system calls (decision P3), plain `ctypes`, no package.
    `copy_secret_text` puts the recovery code on the clipboard and, on Windows, also writes the formats
    `ExcludeClipboardContentFromMonitorProcessing`, `CanIncludeInClipboardHistory` (0) and
    `CanUploadToCloudClipboard` (0) to ask Windows to keep it out of clipboard history and cloud sync;
    `read_clipboard_text` and `clear_clipboard` use the Windows API too (Tk can serve a stale copy). The flags are
    REQUESTED: we could not observe Windows honouring them, because clipboard history is off on the development
    machine, so the screen warns that a copy may remain in history on some systems. Any Windows failure falls back to
    the Tk clipboard quietly; the text is never logged. `font_loader.py` still has its own `ctypes` use and moves
    here later (a test lists the only two files allowed to hold Windows calls).
    `machine_protect` / `machine_unprotect` (Step 1c) wrap the installation key with DPAPI in machine scope, no
    prompt, with the label `DPAPI_ENTROPY`; every failure is `MachineKeyError` with fixed text. The app hands them
    to the key store; services never import this module (H1).
  - `views_new_user.py` and `views_user_profile.py` - global user provisioning
    and profile management.
  - `ai_agent.py` - planned (Phase 6), provider adapter (Gemini first); see
    archive/design_drafts_2026-11/ai_copilot_design.md.
