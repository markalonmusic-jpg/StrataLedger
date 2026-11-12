# File map and design-doc index

Moved unchanged from CLAUDE.md section 2 on 2026-11-12. CLAUDE.md keeps the short map. Update a design doc's
status line here when its area is built.

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
  scope, and the Master / Admin model. Services BUILT in Phases 2.2-2.4
  (`permissions.py`, `authz.py`, `approvals.py`, `users.py`,
  `role_templates.py`); the role screens are Phase 3.
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
- `docs/decisions_2026-11-11.md` - the owner's decisions by code (A1, H2, K3, S10...). `docs/design.md` -
  DRAFT visual spec (docs/CLAUDE_UI.md wins). `docs/role_templates.md`, `docs/csv_import_design.md`.
- `modules/services/` - the service layer (rules 7, 10, 11, 15): every write and every protected read.
  `tx.py` (the write transaction and read connection), `context.py` (`ServiceContext`), `authz.py`
  (`authorize`), `errors.py` (typed exceptions), then one module per area (auth, users, companies, accounts,
  contacts, periods, approvals, ledger, ledger_chain, ledger_verify, keys...). Section 7 says what each step built.
- `tests/` - pytest suite. `scripts/` and `tools/` - developer tools. `.claude/agents/` - subagents.
- `modules/` - screens and the database layer. LEGACY screens (the files in `CONNECT_ALLOW_LIST` in
  tests/test_static_rules.py: `views_billing.py`, `views_payroll.py`, `views_registry.py`, `views_wizard.py`,
  `views_user_profile.py`, and the launcher in `app_strata.pyw`) still run their own SQL; Phase 3 rewrites
  them. Do not copy their patterns. The pattern to copy is `views_first_run.py` + `first_run_model.py`.
  - `database.py` - connections (`PRAGMA foreign_keys=ON`), the baseline
    runner and the pre-release hash guard.
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
  - `views_new_user.py` and `views_user_profile.py` - global user provisioning
    and profile management.
  - `ai_agent.py` - planned (Phase 6), provider adapter (Gemini first); see
    docs/ai_copilot_design.md.
