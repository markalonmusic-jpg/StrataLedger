# StrataLedger schema audit (read-only)

**Status: historical (2026-11-11).** Written against the old migration chain; the schema is now baseline v1 (CLAUDE.md section 5). Kept for the record; do not treat its open findings as current.

**Date:** 2026-11-10 · **Scope:** `migrations/001_company.sql`, `migrations/001_master.sql`, `modules/database.py`, `accounting_librebase.db`, `docs/accounting_schema.txt`, and the code checked against the CLAUDE.md section 3 rules.
**Method:** I built fresh company and master databases from the migrations in a scratch folder, then compared them with `accounting_librebase.db` using `PRAGMA table_xinfo`, `foreign_key_list`, `index_list`, CHECKs and triggers. I upgraded *copies* of every real database file. I tested the rules by inserting rows into a scratch copy. Project `.db` files were opened read-only, and their modification times are unchanged.

---

## Summary

| # | Finding | Severity |
|---|---|---|
| 1 | The migrations and `accounting_librebase.db` **do not match exactly**. Every difference is a deliberate improvement in the migrations, plus one leftover legacy table in the `.db`. | Decision |
| 2 | **`Companies/COMBUZZ.db` will be upgraded into a broken schema** the next time it's opened. Old `invoice`/`invoice_line` tables survive the upgrade, but the file is still marked version 1. | **Critical** |
| 3 | `project_budget.estimate_line_id` references a column that doesn't exist. With FKs on, **any insert into `project_budget` and any delete from `estimate_line` fails** (in both the migrations and the `.db`). | **Critical** |
| 4 | A posted journal entry can be **unposted, then its lines edited or deleted**. Rule 8 isn't enforced. | **High** |
| 5 | Company DBs contain their own empty `app_user` table, and `created_by`/`approved_by` FKs point at it. Any write that records a master `user_id` **fails its FK check** (open decision 4/5). | **High** |
| 6 | Upgrading `system_master.db` keeps its old `app_user`/`company_registry` definitions (no role CHECK, nullable names) and a `company_profile` table with 1 row, but still marks the file version 1. | Medium |
| 7 | `views_billing.py` reads and writes legacy tables and columns (`chart_of_accounts`, `dimension_node`, `parent_dimension_id`). It will fail against any upgraded company file. | High (Phase 3) |
| 8 | Not enforced anywhere: an open period at posting, 2+ lines per entry, postable accounts, `external_ref` uniqueness, the payment-allocation "exactly one of" rule, staged-line totals, and locks on schedule lines, snapshots and change orders. | Medium |

**Recommendation:** make the **migrations authoritative**. CLAUDE.md section 4 already describes the migrated schema (`invoice.terms`, `invoice_line.sort_order`, the cascade), not the `.db`. Refresh `accounting_librebase.db` from the migrations as a reference snapshot, or retire it. Fix findings 2–5 in a `002_company.sql`/`002_master.sql` migration before Phase 2 builds on the schema. **Don't open COMBUZZ.db in the app until finding 2 is fixed.** All real files are already backed up to `C:\Users\marka\StrataLedger_Backups\2026-11-10\`.

---

## 1. Migrations vs `accounting_librebase.db`

Both have 55 tables. The `.db` has no `schema_version` row.

| Object | `accounting_librebase.db` | Migrations | Notes |
|---|---|---|---|
| `chart_of_accounts` | present | **dropped** (`database.py:124-126` drops it when empty) | legacy 5-table leftover; `account` replaces it |
| `time_entry` | **missing** | present (`001_company.sql:740`) | added by the migration |
| `invoice.terms` | missing | `TEXT DEFAULT 'Net 30'` + CHECK (`:402`) | |
| `invoice` unique | none | `UNIQUE(invoice_type, contact_id, invoice_number)` | |
| `invoice` → `project` FK | missing | present | |
| `invoice_line.sort_order` | missing | `INTEGER DEFAULT 0` | |
| `invoice_line.cost_code_id` | `TEXT DEFAULT NULL`, no FK | `INTEGER` FK → `cost_code` | type fix |
| `invoice_line.invoice_id` | `NO ACTION` | `ON DELETE CASCADE` | |
| `invoice_line_dimension` PK | `(line_id, dimension_value_id)` | `(line_id, dimension_type_id)` + composite FK `(dimension_value_id, dimension_type_id)` | enforces one value per type per line |
| `dimension_value` unique | `code` | `code` + `(dimension_value_id, dimension_type_id)` | needed by the composite FK above |
| `app_user.job_title` | `NOT NULL`, no default | `NOT NULL DEFAULT ''` | |
| Triggers | **0** | **7** (`:644-739`) | dimension depth/type, balance on post, no direct post, posted-line locks |

The master migration matches the `.db` for its 5 tables, apart from the `job_title` default.

**Conclusion:** they don't match, but every difference goes in the direction the migrations intend. Nothing in the `.db` is missing from the migrations except the legacy `chart_of_accounts`.

## 2. `database.py` vs the rules

Good:
- It never imports Tkinter (rule 5) and raises `SchemaUpgradeBlockedError` instead.
- It backs up before every upgrade of an existing file (`_upgrade_database`, `database.py:188-197`; rule 9).
- Each migration runs in `BEGIN IMMEDIATE` and rolls back on error (`:170-183`).
- `get_connection` enables FKs (`:23-28`).

Problems:
- **Legacy detection is incomplete** (`_is_legacy_company_schema`, `:72-87`; `_legacy_company_has_rows`, `:90-94`; `_prepare_company_migration`, `:120-126`). It checks and drops only `contact`, `project`, `chart_of_accounts` and `journal_entry`. Any other pre-existing table survives, because `001_company.sql` uses `CREATE TABLE IF NOT EXISTS`, and the file is still stamped version 1.
  - Simulated on a copy of `Companies/COMBUZZ.db`: the upgrade "succeeds". The old `invoice` (`UNIQUE(invoice_number)`, no CHECKs, 15 missing columns) and the old `invoice_line` (`invoice_line_id`, FK → the now-dropped `chart_of_accounts`, FKs → `dimension_node`) are kept. After that, `PRAGMA foreign_key_check` reports mismatches on `deferral`, `invoice_line_dimension` and `project_budget`. There are 42 schema differences from a fresh database.
  - The same `IF NOT EXISTS` issue affects any table whose old definition differs, not just tables in legacy files.
- **The master upgrade is partial** (`_prepare_master_migration`, `:129-156`). It drops only *empty* legacy tables, so `system_master.db`'s `company_profile` (1 row) stays in the master database, which CLAUDE.md section 2 forbids. It patches `app_user` with only two `ALTER`s, so the existing table keeps nullable `first_name`/`last_name`/`email`, has no role CHECK, and keeps `role DEFAULT 'Admin'`. `company_registry` keeps `NO ACTION` instead of `SET NULL` on the parent and has no `is_active` CHECK. 13 differences from a fresh database.
- **Master tables inside company DBs** (open decision 5): `001_company.sql` creates `app_user` (`:20`), `audit_log` (`:33`), `company_registry` (`:87`) and `user_company_access` (`:638`) in every company file. The FKs from `journal_entry.created_by`, `staged_transaction.approved_by`, `audit_log.user_id`, `crm_*` user columns and `user_company_access` point at this always-empty local `app_user`.
  - Tested: `INSERT INTO journal_entry (entry_date, created_by) VALUES ('2026-11-10', 1)` → **FOREIGN KEY constraint failed**.
  - Open decision 4's plan (store the master `user_id` as a plain integer with no FK) needs a migration that rebuilds these tables without those FKs.
- `create_initial_master_user` (`:226-236`) stores whatever it receives as `password_hash`, and every caller passes plain text (rule 6).

## 3. Planning doc vs live schema

The doc defines 35 tables. The live schema has 20 tables the doc doesn't mention: `company_profile`, `company_registry`, `user_company_access`, `dimension_type`, `dimension_value`, `invoice_line_dimension`, `file_attachment`, `progress_billing_application`, `purchase_order_subcontract`, `subscription`, `saas_subscription`, `saas_usage_telemetry`, and 9 `crm_*` tables. The database wins on names (CLAUDE.md section 5). The differences:

**Fields that are named differently or missing**

| Table | Doc | Live |
|---|---|---|
| `estimate_line` | PK `estimate_line_id`, `unit`, `unit_cost_cents`, `extended_cost_cents`, `description`, `markup_pct`, `sort_order` | PK `line_id`, `unit_of_measure`, `estimated_unit_cost_cents`, `estimated_extended_cost_cents`, `price_to_customer_cents`. No description, markup or sort order. **The PK rename is the cause of finding 3.** |
| `time_entry` | `time_id`, `batch_id`, `external_ref`, `bill_rate_cents` | `time_entry_id`, `source_batch_id`, **no `external_ref`, no `bill_rate_cents`** |
| `estimate` | `version`, `supersedes_id`, `project_id`, `estimate_date`, `valid_until`, `overhead_pct`, `profit_pct`, `contingency_pct`, `notes` | all missing; has `assigned_pm_id`, `source_opportunity_id`. **Versioned estimates (CLAUDE.md section 6) aren't possible.** |
| `cost_code` | `category`, `counts_toward_progress`, FK `account_id` | `cost_type_label` instead of `category`; **no `counts_toward_progress`**, which the POC rule in CLAUDE.md section 6 needs; `account_id` has no FK |
| `project` | `project_code`, `estimate_id`, `start_date`, `end_date`, `poc_method` | `project_number`, `source_estimate_id`, `original_budget_cents`, `revised_budget_cents`, `assigned_pm_id`; **no `poc_method`** and no dates |
| `contact` | `payroll_employee_id` | missing; live adds `bir_registered_name`, `entity_type` and `mailing_*` |
| `app_user` | roles `[Admin, Accountant, Project manager, Viewer]` | roles `Master, Admin, Accountant, HR, AP, AR, Sales, Marketing, PM, Warehouse`; adds name, email, `password_hash`, `job_title` |
| `poc_snapshot` | — | matches |

**FKs the doc declares that the live schema leaves as plain integers:**
- `journal_line`: `contact_id`, `recon_id`, `project_id`, `cost_code_id`, `deferral_id`, `batch_id`
- `company_settings`: all 5 `*_acct_id` columns
- `cost_code.account_id`
- `deferral`: `project_id`, `cost_code_id`
- `import_mapping`: `project_id`, `cost_code_id`
- `staged_line`: `project_id`, `cost_code_id`
- `payment_allocation.deferral_id`
- `invoice.batch_id`
- `contract_line.change_order_id`

**Value lists that differ:**
- `project.status`: doc `Bid/Active/Complete/Closed`, live `Mobilization/In Progress/Suspended/Completed/Closed Out`.
- `estimate.status`: live has no `Superseded`.
- `import_batch.batch_type`: live drops `Statement payment` and adds `Labor Accrual`.

**Duplicate concepts in the live schema:** `change_order`/`change_order_line` alongside `crm_change_order`/`crm_change_line`, and `subscription` alongside `saas_subscription`. Decide which pair is canonical.

**Doc rules with no enforcement in the schema:** see section 4d.

## 4. Code vs CLAUDE.md rules

`Outdated/` is excluded because nothing imports it. It also contains raw connections, plaintext logins and the token (`Outdated/app_fast.py:39`).

### 4a. `sqlite3.connect` outside `database.get_connection` (rule 4: FKs off)
- `app_strata.pyw:95`, `app_strata.pyw:172`
- `modules/views_billing.py:270`, `:283`, `:295`, `:311`, `:369`, `:504`
- `modules/views_new_company.py:19`, `:165`, `:175`
- `modules/views_new_user.py:100`
- `modules/views_payroll.py:68`
- `modules/views_registry.py:63`
- `modules/views_user_profile.py:46`, `:107`
- `modules/views_wizard.py:39`, `:281`
- `modules/database.py:33` (`_readonly_connection`, used only for read-only version checks, so acceptable)

### 4b. Raw INSERT/UPDATE/DELETE outside a service module (rule 7)
There's no service module yet, so every write is in UI code:
- `modules/views_billing.py:507` (invoice), `:524` (invoice_line), `:538` (UPDATE invoice)
- `modules/views_new_company.py:168` (company_registry), `:178` (company_profile)
- `modules/views_new_user.py:102` (app_user)
- `modules/views_payroll.py:70` (time_entry)
- `modules/views_user_profile.py:111`, `:116` (UPDATE app_user)
- `modules/views_wizard.py:45` (UPDATE contact), `:56` (contact), `:67` (`INSERT OR REPLACE` saas_subscription)
- `modules/database.py:233` (`create_initial_master_user`; database layer, acceptable as-is)

### 4c. Money as REAL/FLOAT (rule 1)
- **Schema:** every `*_cents` column is declared `INTEGER`. The REAL columns are all quantities, rates or percentages, which rule 1 allows: `contract.retainage_pct`, `crm_change_line.quantity_change`, `crm_opportunity.probability_pct`, `estimate_line.quantity`, `invoice.exchange_rate`, `invoice.cwt_rate`, `invoice_line.quantity`, `payment.exchange_rate`, `poc_snapshot.pct_complete`, `purchase_order_subcontract.retainage_pct`, `tax_rate.rate`, `time_entry.hours`.
- **But the tables aren't `STRICT`, and no column has a `typeof()` CHECK, so INTEGER columns accept non-integers.** Tested: `time_entry.wage_cents = '25.50'` is stored as REAL `25.5`, and `burden_cents = 'abc'` is stored as TEXT.
- **Code:**
  - `modules/views_payroll.py:62-72` inserts raw entry text into `wage_cents`/`burden_cents` (and `hours`, `contact_id`) with no conversion. That's REAL or TEXT in the database, and dollars versus cents is ambiguous.
  - `modules/views_billing.py:438-439`, `:482-486` and `:496` parse prices with `float()` and convert with `int(round(x * 100))`. Correct in most cases, but it's float arithmetic; use `Decimal`.
  - `modules/views_wizard.py:66` uses `int()` on MRR (the placeholder says "in Cents"), which is fine.

### 4d. Triggers and CHECKs mapped to rules

| Constraint (`001_company.sql`) | Rule | Gap found by testing |
|---|---|---|
| `journal_entry_require_balance_on_post` (`:708`) | 2 | Requires ≥1 line, not 2+. **A single line with 0 debit and 0 credit posts.** Doesn't check the period is open or the accounts are postable. |
| `journal_entry_no_direct_post` (`:719`) | 2 | — |
| `journal_line` CHECKs `debit_cents >= 0`, `credit_cents >= 0`, `debit_cents = 0 OR credit_cents = 0` (`:466-477`) | 1, 2 | `entry_id` and `account_id` are nullable, so orphan lines and lines without an account are accepted |
| `journal_line_lock_insert/update/delete_posted` (`:726-739`) | 8 | **`UPDATE journal_entry SET is_posted = 0` is allowed, which unlocks the lines.** The posted header can be edited, and deleted once its lines are removed. |
| `dimension_value_validate_insert/update` (`:644`, `:665`) | — (section 4 dimension convention) | — |
| `invoice_line_dimension` composite PK/FK | — (section 4) | — |
| `crm_opportunity.deal_value_cents >= 0` (`:228`), `saas_subscription.base_mrr_cents >= 0` (`:573`) | 1 (sign only) | |
| `company_settings.id = 1` (`:99`) | — (single-row settings) | |
| ~45 status/type value-list CHECKs (e.g. `:395`, `:402`, `:403`, `:454`, `:612`) | — (domain values, not a numbered rule) | |

**Rules nothing enforces:**
- **Rule 3** (isolation): this is an architecture rule, and the master tables inside company DBs work against it.
- **Rule 4**: enforced only if every connection goes through `get_connection` (see 4a).
- **Rule 5**: code only. `database.py` complies.
- **Rule 6**: nothing. Passwords are plaintext, and the token is at `app_strata.pyw:40`.
- **Rule 7**: nothing (see 4b).
- **Rule 8**: only partly (see the unpost gap above). There are no locks on posted `deferral_schedule_line` or `poc_snapshot` rows, on approved `change_order` rows, or on `Sent` invoices.
- **Rule 9**: enforced in code (`database.py:62-69`, `:195-196`).

Doc rules with no enforcement:
- Posting requires an open period (tested: **posts into a closed period**).
- Only postable, active accounts can take lines.
- `external_ref` is unique per source (no unique index on `staged_transaction`; `time_entry` has no `external_ref` column at all).
- Staged lines add up to the transaction amount.
- `payment_allocation` has exactly one of `invoice_id`/`deferral_id` (tested: a row with **neither** is accepted).
- Posted schedule lines, approved change orders and posted snapshots are locked.

### 4e. Hardcoded paths
- `config.py:3`: `BASE_PROJECT_DIR = r"C:\Users\marka\StrataLedger"`. This is the one allowed definition, but it could be derived with `Path(__file__).parent`.
- `StrataLedger.bat:3`, `LibreBase.bat:3`: `C:\Users\marka\AppData\Local\Programs\Python\Python311\pythonw.exe`
- `launch_ledger.vbs:2`: the Python path above plus `C:\Users\marka\StrataLedger\app_strata.pyw`
- `Outdated/app_fast.py:30-31`, `Outdated/app_fast_copy.py:22-23` (not imported)

### 4f. Screen code against the migrated schema (Phase 3 input)
`modules/views_billing.py` uses legacy names that don't exist after the upgrade:
- `contact.display_name` (`:271-274`)
- `project.project_name` (`:285`)
- `FROM chart_of_accounts` (`:297`)
- `FROM dimension_node` (`:313`, `:371`)
- `invoice_line.parent_dimension_id`/`sub_dimension_id`/`amount_cents` (`:524`)

Its success message says "posted" (`:544`), but it saves a `Draft` invoice with no journal entry.

## 5. State of the real files (context)

| File | `schema_version` | Rows | What opening it would do |
|---|---|---|---|
| `system_master.db` | none | app_user 2, company_registry 3, company_profile 1 | partial upgrade (finding 6); runs at the next app launch |
| `comp_strata.db` | none | company_profile 1 | clean upgrade (0 differences from fresh) |
| `Companies/CHRM.db` | none | company_profile 2 | clean upgrade (0 differences), but `project_budget` FK mismatch (finding 3) |
| `Companies/COMBUZZ.db` | none | company_profile 1 | **broken upgrade** (finding 2) |
| `accounting_librebase.db` | none | company_settings 1, app_user 1, company_profile 1 | not opened by the app |

## 6. Test coverage

`tests/test_database.py` (8 tests, all passing) covers migrations, legacy blocking, dimension depth and one value per dimension type. **No test covers the posting triggers, the posted-line locks, unposting, or the master partial upgrade.** CLAUDE.md section 8 asks for a test for every rule that's enforced.

## 7. Decisions needed

1. **Source of truth:** migrations (recommended) or the `.db`. If migrations: refresh the `.db` snapshot from them or delete it, and update CLAUDE.md sections 2 and 5.
2. **Fix migration `002`:** rebuild `invoice`/`invoice_line` for legacy files (or block them like populated legacy files), fix `project_budget.estimate_line_id` → `estimate_line(line_id)`, remove the master tables and their FKs from company DBs, block unposting, and rebuild the master `app_user`/`company_registry`. Decide whether `system_master.db`'s `company_profile` row should move or be dropped.
3. **Doc vs schema gaps you want closed:** versioned estimates, `counts_toward_progress`, `poc_method`, `time_entry.external_ref`, and the missing FKs. Or update the doc to match.
4. **Canonical tables:** `change_order` or `crm_change_order`, and `subscription` or `saas_subscription`.
5. Whether to make money tables `STRICT` (SQLite ≥ 3.37) or add `typeof()` CHECKs.
