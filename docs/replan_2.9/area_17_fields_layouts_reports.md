# Step 2.9 schema replan, area 17: field registry, list layouts, report builder, KPIs and measures

Status: **Drafted 2026-11-19** for the owner. Docs only: nothing here changes code, a baseline, a migration or a
test. Nothing is built until the owner marks area 17 owner-approved in `Strata_Teams\schema_replan_2026-11-17.md`.
Every table, column, code and check below is PROPOSED until then. Choices for the owner are in section 13.

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`: row 17, the source keys and the "Inbox inputs" section (it lists no
  message for area 17; the area 17 messages are in `inbox\archive\to_planning_done.md`, below).
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md`: 2026-11-15 "report builder (owner)" and "Report
  builder and consolidation question", "Owner answers (2:08 PM)", "Per-user list layout preferences (2:13 PM)",
  "Public field registry for column pickers and filters (2:14 PM)".
- `Strata_Teams\inbox\archive\to_planning_done.md`: 2026-11-18 "operating plans", "report definitions with two kinds,
  and records report sources", "financial layouts, formulas, non-financial data, dynamic dates (schema)";
  2026-11-19 "report builder service contracts" (2:27 AM).
- `Strata_Teams\shared_decisions.md`: 2026-11-15 "report builder", "resizable columns", "column picker fields";
  2026-11-18 3:14, 3:16, 3:19 and 3:22 PM, and "R32 addition, View switch and saved views"; 2026-11-19 12:45 AM
  (money.view).
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 92, 100 and 156 (the task's "C92, C100, C156"; these are
  CODE_CHANGES sections, not decision codes).
- docs/contracts/reports.md (owner-approved, e869ecf): sections 1-9, 11 answers and 12 (the service shapes this area
  stores).
- docs/decisions_2026-11-11.md by code: A1, CB1, CF1, C4, E11, EX1, G6, G7, RP2, JD1, H4, H5 and AG6-AG8 (index
  lines); CLAUDE.md rules 1, 7, 10 and 15.
- Approved areas: 13 (sections 4.5 and 6, close call order, answers Q18-Q21), 10 (section 4 summary, section 2
  `reclass_line`), 12 (section 5.3 cash set), 18 (sections 1-2 and the dated amendment lines).
- `migrations/001_company.sql`, `modules/services/permissions.py`, `periods.py`, `custom_fields.py`.

---

## 0. Summary

| # | Topic | Proposal in one line | Baseline |
|---|-------|----------------------|----------|
| 1 | Field registry | A code catalogue (`field_registry.py`, hosted-ready), not a table; custom fields join it at read time from `custom_field_def` by their immutable `field_key`; every field names the permission that shows it | none (code) |
| 2 | List layouts | `user_list_pref` kept (per user, display only, widths inside `columns_json`); one new `company_list_default` (Admin); resolved user → company → built-in | company |
| 3 | Layouts | `report_layout` (financial or records), a tree of groups and formulas, accounts in groups, auto-include rules, formula tokens as rows, charts, and the Records parts; built-in layouts made by an upkeep from code | company |
| 4 | Saved reports and packs | `saved_report` with typed parameters (dynamic date presets stored as presets), compare and filter rows, `report_pack` and its items, sharing | company |
| 5 | Schedules | `report_schedule`, recipients, runs and in-app deliveries; runs while the app is open, one catch-up at sign-in, as the owner | company |
| 6 | KPIs | `kpi` and insert-only `kpi_value`, frozen in the close transaction by one writer; null with a note, never blocks | company |
| 7 | Measures | `nonfinancial_measure` and `nonfinancial_value`; typed values locked with the closed period; derived values live while open, frozen at close | company |
| 8 | Combined runs | No new table beyond the saved report's company list; accounts matched by number; unmatched accounts as their own rows with a warning | company |
| 9 | Running | Reads the period summary (area 10); "As reclassed" changes detail rows only; `money.view` enforced before any read; two company settings and `account.cash_flow_category` | company |
| 10 | Permissions | `money.view`, `report.records`, `report.design`, `report.schedule` placed in the caps and levels; templates and AGENT_ALLOWED decided | company |

Master file: no change (user ids in this area are plain integers, as everywhere in the company file).
Counts: 30 new company-file tables, 4 new columns on existing tables (two on `company_settings`, one on `account`,
`user_list_pref.updated_at`), 4 permission rows (77 + 3 + 2 + 4 = 86 seeded codes after areas 12, 10 and 17).

---

## 1. Field registry and custom field exposure

### 1.1 Current state

- **No registry exists.** No module lists the public fields of any list or record type. The lists' columns are
  defined only in the mockups (CODE_CHANGES 92: catalogs for bills, invoices, purchase orders, vendors, customers,
  jobs; other lists show Memo, Created by/at, Last changed by/at plus Dimensions).
- Custom fields: `custom_field_def` (`migrations/001_company.sql:4117-4128`: `record_type` CHECK IN ('Contact',
  'Invoice', 'Bill', 'Project', 'Estimate'), `field_key`, `label`, `data_type`, `choices_json`, `is_required`,
  `is_active`, `sort_order`; UNIQUE (`record_type`, `field_key`)) and `custom_field_value` (`:4130-4142`, one typed
  column per type). `custom_fields.list_fields` (`modules/services/custom_fields.py:280`) and `get_values` (`:301`)
  already apply the per-record-type read permission (Invoice `ar.view`, Bill `ap.view`, Project `project.view` with
  scope, Contact by kind). `field_key` never changes (FR1). `Lead` is not a record type yet (area 15 or 16).
- Today a Money custom field has `data_type = 'Money'` and is stored in `value_cents`.

### 1.2 Decided

- 11-15 2:14 PM: a registry per list or record type: field key, label, type (text, date, money in cents, number,
  boolean), group (this record, related record, dimension, custom field), description, the permission needed to
  see it, whether it can be filtered and summed. Internal columns (ids, `password_hash`, keys, tokens,
  `audit_context`, sync markers) are never in it. Related-record fields come through defined joins. Hosted-ready:
  it lives with the services, not the UI. The Filter dropdown, the column picker and the report builder all use it.
- CODE_CHANGES 92: public fields only; a field the user cannot see (pay rates without wage access) is left out
  entirely, not greyed.
- Contracts 5.1-5.2: the source catalogue is defined in code, not by users; each field has `field_id`, `label`,
  `type`, `money`, `custom`, `groupable`, `summaries`, `buckets`; custom fields are `cf.<record>.<key>`; money
  fields are left out for a viewer without `money.view`.

### 1.3 Proposed

- **No table for built-in fields.** A code module `field_registry.py` holds, per list key and per Records source, an
  ordered list of field entries (shape above plus `permission` and `join`). `report_sources.py` (the Records source
  catalogue, contracts 5.1) is built on the same entries, so a field is defined once.
- **Custom fields join at read time** from `custom_field_def` for the record types a list or source covers: active
  fields only are offered, keyed `cf.<record_type>.<field_key>` (the immutable key, never `field_id`). Type map:
  Text → text, Choice → choice (with its active choices), Number → number, Money → money (`money: true`), Date →
  date, Yes/No → bool. Visibility is the record type's own read permission (section 1.1). A deactivated field is not
  offered, but a saved layout, saved report or column preference that already uses it keeps working and shows its
  label with "(inactive)" (Q1).
- **Permission per field:** each entry names one existing permission code (`ar.view`, `ap.view`, `project.view`,
  `payroll.view` for pay rates and wages, `view.tax_ids`, `view.bank_details`, ...). A user's catalogue is the entries
  whose code the user holds, minus money fields without `money.view`. The Agent's catalogue is built the same way
  from `AGENT_ALLOWED` (a sensitive code is never agent-allowed).
- **Deny-list by construction:** an entry cannot be added for a column whose name matches the internal list
  (`password_hash`, any `*_hash`, `*_key`, `token`, `secret`, `salt`, `routing_number`, `account_number`,
  `chain_*`, `audit_*`, `terminal_id`), enforced by a static test.
- **Bank and tax numbers** stay out unless `view.bank_details` or `view.tax_ids` (C4, K4); contact fields named like
  bank numbers are refused as custom fields already (`custom_fields.py`, RP1).
- Services: `field_registry.list_fields(context, list_key | source_id)`; no write.

### 1.4 How it lands, effects, tests

- Baseline: nothing (other areas add `Lead` to `custom_field_def.record_type`, contracts 12 item 17).
- Effects: none on existing services; `custom_fields.list_fields` is called, not changed.
- Tests to write later: no deny-listed column name is reachable from any entry; every entry's permission code is in
  the registry of `permissions.py`; every `*_cents` backed field is `money: true`; a viewer without `money.view` sees
  no money field in the catalogue; a viewer without `payroll.view` sees no wage field; a custom Money field is a
  money field; an inactive custom field is not offered but still resolves for a saved definition; the Agent catalogue
  holds no sensitive-code field; related fields appear only through a defined join.

---

## 2. List layout preferences (per user, display only)

### 2.1 Current state

- `user_list_pref` (`:4171-4178`): `user_id` (a master user id, plain integer, no FK), `list_key`, `columns_json`,
  `sort_json`, `page_size` (positive integer); PK (`user_id`, `list_key`). `saved_view` (`:4180-4189`): `user_id`,
  `list_key`, `name`, `filters_json`, `is_default`; UNIQUE (`user_id`, `list_key`, `name`). Both **have audit
  triggers** (`:5505-5608`) and area 18 lists both as audited (area 18 section 1.1, lines 112-113).
- No service reads or writes either table; `tests/test_schema_replan.py:717-722` only checks the keys.
- The mockup saves widths in the browser as `sl-w-<page>-<table id>` (CODE_CHANGES 156). That is a mockup detail:
  production keeps them server-side per user (11-15 2:13 PM; hosted: the same per user).

### 2.2 Decided

- 11-15 2:13 PM: widths, shown, hidden and order are remembered per user, per list, in a small per-user preferences
  store: UI only, **not audit-logged, never shared**. Hosted: per user.
- CODE_CHANGES 92: Reset columns (back to the default); **Save as company default (Admin)**; the checkbox, the
  record's name or number, and Action are locked; only public fields appear.
- R32 addition (11-18 1:52 AM): saved views and the List/Board switch sit on the title row; `saved_view` is as built.

### 2.3 Proposed

- **`user_list_pref` stays.** `columns_json` holds an ordered list of `{"field": "<registry key>", "width": <px>}`
  (order is the shown order; a field not listed is hidden; widths 40 to 1000, whole numbers); `sort_json` as built.
  Add `updated_at` TEXT NOT NULL (from `context.now`). No `row_version` (display only, last write wins; Q3).
- **`company_list_default`** (new): `list_key` TEXT PRIMARY KEY, `columns_json`, `sort_json`, `page_size`, `set_by`
  INTEGER NOT NULL, `set_at` TEXT NOT NULL, `row_version` INTEGER NOT NULL DEFAULT 1. Written only by an Admin
  (`company.settings`), audited.
- **Resolution order** (service `list_prefs.resolve`): the user's own row; else the company default; else the
  registry's built-in default order. Reset deletes the user's row (so the company default applies).
- **Validation:** `list_key` must be a registry list key; a field id must be in the registry; unknown ids are
  refused on save. On read, a field the user can no longer see (a lost permission, an inactive custom field with no
  value) is skipped without error and the stored row is left as it is.
- **Services** (`list_prefs.py`): `get_layout`, `save_layout`, `reset_layout`, `save_company_default`,
  `clear_company_default`. A user may only touch their own row (the service takes the user from the context, never
  from the request). The Agent has no preferences.
- `saved_view` is unchanged here; whether views can be shared is not decided and not built (section 14).

### 2.4 How it lands, effects, tests

- Baseline: `company_list_default` and its audit triggers; `user_list_pref.updated_at`. If Q4 A is answered, the audit
  triggers of `user_list_pref` and `saved_view` are dropped instead of kept (area 18's lists change).
- Effects: `tests/test_schema_replan.py:717` keeps its key assertions; `tests/test_controls_004.py` audit lists change
  only under Q4 A.
- Tests to write later: resolution order; a company default is Admin-only and audited; a user's save never changes
  another user's row; unknown field refused; a lost permission hides the column without deleting the preference; a
  width outside 40-1000 refused; locked columns cannot be hidden; Reset returns the company default; the same list key
  for two users stays separate.

---

## 3. Layouts: financial, records, formulas, charts

### 3.1 Current state

None: no report, layout, KPI, measure or pack table exists (grep of `001_company.sql`). `periods.BASES` has only
`pre_adjustment`, `gaap` and `tax` (`periods.py:27`); `period_ids_for_basis` (`:215`) raises for the Management basis
that contracts 4.1 and A1 name, so the report engine applies "1-13 without `is_tax_strategy_only` accounts"
(`account.is_tax_strategy_only`, `:585`) itself. There is no formula engine, no dimension service and no report
service. The `ledger_checkpoint` kind 'Report export' exists (`:535`).

### 3.2 Decided

- 11-18 inbox "financial layouts, formulas, non-financial data" items 1-5, 8; "report definitions" item 1; 3:19 and
  3:22 PM; contracts 2.2, 2.3, 3 and 12 items 1-6: kinds financial and records; types P&L, balance sheet, cash flow,
  combined; built-in layouts read-only, "make a copy" clones; a tree of groups, formulas and charts; one group per
  account per layout; auto-include rules (account range or type); two rules that can catch the same account are
  refused at save (contracts Q3 A); formulas stored as tokens, circular and deleted references rejected, kind and
  `report_type` fixed after the first save; layout deleted only when unused; formulas use the shown sign (contracts
  Q4 A); formats Number, Currency, Percent, Ratio; conditional summaries on Records columns (contracts Q11 A); up to 3
  group-bys with date buckets; no KPI flag on items (contracts Q5).

### 3.3 Proposed schema

**`report_layout`**

| Column | Type and constraint |
|--------|---------------------|
| `layout_id` | INTEGER PRIMARY KEY |
| `kind` | TEXT NOT NULL CHECK IN ('financial', 'records') |
| `report_type` | TEXT CHECK IN ('profit_and_loss', 'balance_sheet', 'cash_flow', 'combined'); CHECK (`kind` = 'financial') = (`report_type` IS NOT NULL) |
| `scope` | TEXT NOT NULL DEFAULT 'single' CHECK IN ('single', 'combined'); CHECK (`kind` = 'financial' OR `scope` = 'single') |
| `name` | TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120); unique ignoring case, checked by the service in the write transaction (no `COLLATE NOCASE`, H5) |
| `description` | TEXT CHECK (length <= 1000) |
| `built_in` | INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1) |
| `built_in_key` | TEXT UNIQUE; CHECK (`built_in` = 1) = (`built_in_key` IS NOT NULL) |
| `built_in_version` | INTEGER (the app's version of that layout, Q5) |
| `copied_from_id` | INTEGER REFERENCES report_layout |
| `source_id` | TEXT (a Records source key from code; CHECK (`kind` = 'records') = (`source_id` IS NOT NULL)) |
| `created_by`, `created_at`, `updated_by`, `updated_at` | INTEGER, TEXT (UTC with offset, from `context.now`) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

**`layout_item`** (groups and formulas; charts are their own table, F1)

| Column | Type and constraint |
|--------|---------------------|
| `item_id` | INTEGER PRIMARY KEY |
| `layout_id` | INTEGER NOT NULL REFERENCES report_layout ON DELETE CASCADE |
| `parent_id` | INTEGER REFERENCES layout_item (a group; checked by the service) |
| `sort` | INTEGER NOT NULL |
| `type` | TEXT NOT NULL CHECK IN ('group', 'formula') |
| `name` | TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120) |
| `positive_when` | TEXT CHECK IN ('credit', 'debit') (groups; formulas none) |
| `over_plan_is` | TEXT NOT NULL DEFAULT 'neutral' CHECK IN ('good', 'bad', 'neutral') |
| `show_total`, `collapsed`, `hidden`, `show_accounts`, `hide_if_zero` | INTEGER NOT NULL 0/1 (a group's display options; `hide_if_zero` also applies to formulas) |
| `format` | TEXT CHECK IN ('number', 'currency', 'percent', 'ratio') (formulas) |
| `decimals` | INTEGER CHECK BETWEEN 0 AND 4 (formulas) |
| `total_method` | TEXT CHECK IN ('calculate', 'sum', 'average', 'last') (formulas) |

CHECK (`type` = 'group') = (`positive_when` IS NOT NULL) and (`type` = 'formula') = (`format` IS NOT NULL AND
`decimals` IS NOT NULL AND `total_method` IS NOT NULL). Index (`layout_id`, `parent_id`, `sort`). Child rows carry no
`row_version` of their own: the whole tree is saved with the layout and guarded by `report_layout.row_version`.

**`layout_group_account`**: `layout_id`, `item_id` (the group), `account_id` REFERENCES account (RESTRICT); UNIQUE
(`layout_id`, `account_id`) (an account sits in at most one group per layout).

**`layout_auto_include`**: `auto_include_id`, `layout_id`, `item_id` (the group), `rule_kind` CHECK IN
('account_range', 'account_type', 'role', 'cash_set'), `from_code`, `to_code` (TEXT, range), `account_type_id`
REFERENCES account_type and `subtype` TEXT (type), `role_key` TEXT (one of the company's system-account roles,
`company_settings.*_acct_id`), cash set (area 12 section 5.3: every `bank_account` kind except Credit card, plus the
undeposited funds role). A CHECK per kind requires exactly its own columns. Explicit `layout_group_account` rows win
over rules; overlapping rules are refused at save by the service (contracts Q3 A). Q6 decides the rule kinds.

**`formula_token`** (one row per token; replaces JSON text so a deleted item, KPI or measure is found by query)

| Column | Type and constraint |
|--------|---------------------|
| `token_id` | INTEGER PRIMARY KEY |
| `item_id` | INTEGER REFERENCES layout_item ON DELETE CASCADE |
| `column_id` | INTEGER REFERENCES records_column ON DELETE CASCADE; CHECK exactly one of `item_id`, `column_id` is set |
| `position` | INTEGER NOT NULL; UNIQUE (`item_id`, `position`) and (`column_id`, `position`) |
| `t` | TEXT NOT NULL CHECK IN ('ref', 'num', 'op', 'paren') |
| `ref_kind` | TEXT CHECK IN ('group', 'formula', 'kpi', 'measure', 'system', 'column', 'company_group', 'company_account') |
| `ref_item_id` | INTEGER REFERENCES layout_item (RESTRICT) (group, formula, company_group) |
| `ref_column_id` | INTEGER REFERENCES records_column (RESTRICT) (column) |
| `kpi_id`, `measure_id` | INTEGER REFERENCES kpi, nonfinancial_measure (RESTRICT) |
| `system_key` | TEXT CHECK IN ('days_in_period', 'days_in_year', 'days_elapsed_in_year') |
| `company_id`, `account_code` | INTEGER (a master company id, no FK), TEXT (combined layouts only; the account number as in that company, section 8) |
| `num_value` | TEXT (a decimal string, validated by the service; not money, so not cents) |
| `op` | TEXT CHECK IN ('+', '-', '*', '/') |
| `paren` | TEXT CHECK IN ('(', ')') |

A CHECK per `t` requires exactly the columns of that token type. Circular references (direct, through other
formulas, or through a KPI sourced from the formula) are found by a graph walk in the service (a CHECK cannot see a
path). `RESTRICT` makes the database refuse a delete of a referenced item, KPI or measure; the service turns that
into the contracts' sentence.

**`report_chart`** and **`report_chart_series`**: `chart_id`, `layout_id`, `name`, `chart_type` CHECK IN ('bar',
'line', 'donut', 'waterfall'), `chart_column` CHECK IN (1, 2), `chart_order`; series rows (`chart_id`, `position`,
`item_id` REFERENCES layout_item or `column_id` REFERENCES records_column; exactly one). A donut takes one value
column (service rule).

**Records parts**
- **`records_column`**: `column_id`, `layout_id`, `position`, `kind` CHECK IN ('field', 'formula'), `field_id` TEXT
  (a registry key; CHECK (`kind` = 'field') = (`field_id` IS NOT NULL)), `label`, `summary` CHECK IN ('none',
  'count', 'sum', 'avg', 'min', 'max'), `format` CHECK IN ('number', 'currency', 'percent', 'ratio', 'text',
  'date'), `decimals`.
- **`records_column_condition`**: `condition_id`, `column_id`, `position`, `field_id`, `op` (CHECK IN the contracts'
  list: eq, ne, in, not_in, gt, gte, lt, lte, between, is_empty, not_empty, contains), `value_json` TEXT (an array
  of literals; contracts Q11 A conditional summaries, for "won ÷ closed").
- **`records_group_by`**: `layout_id`, `level` BETWEEN 1 AND 3, `field_id`, `bucket` CHECK IN ('day', 'week',
  'month', 'quarter', 'year') or NULL; PK (`layout_id`, `level`).
- **`records_sort`**: `layout_id`, `position`, `column_id`, `direction` CHECK IN ('asc', 'desc').
- **`records_filter`**: `layout_id`, `position`, `field_id`, `op`, `value_json`, `preset` (a dynamic date preset).

References to registry fields are text keys from code (a catalogue cannot be a foreign key). A custom field is
stored as `cf.<record_type>.<field_key>`, which never changes (FR1), so a rename cannot break it.

**Built-in layouts (Q5):** `built_in = 1` rows with a `built_in_key` are created and refreshed by an idempotent
upkeep at company open (as `periods.ensure_upcoming_years`, S3), from definitions in code; they are read-only by a
service rule, "Make a copy" clones into a company layout, and saved reports and KPIs can point at them like any
layout. A built-in layout never names an account number: it uses account type and subtype, role and cash-set rules.
In this pass: Profit and loss (standard), Balance sheet (standard) and one blank layout per kind; the construction
layouts (job profitability, WIP schedule, board summary) arrive with the areas that own their data (Q25).

### 3.4 How it lands in the baselines

Company only: the tables above with their indexes, audit triggers (area 18) and integer CHECKs in the baseline's
style (`typeof(...) = 'integer'`, listed in docs/audit_readiness_design.md section 16 for the PostgreSQL rewrite).
Every development database is blocked and rebuilt (CLAUDE.md 5.2; list them and ask first, rule 9). No seed rows.

### 3.5 Effects on existing services and tests

None (nothing reads these tables). New modules: `report_layouts.py` (definitions, copy, usage, delete rules),
`report_formulas.py` (validate, operands, evaluate), `report_sources.py` (Records catalogue). Layout writes
authorize first (`report.design`, rule 10); `get_layout` and `list_layouts` need the run permission for the kind.

### 3.6 Tests to write later

- The contracts' sample layouts round-trip (JSON in = JSON out); `kind` and `report_type` cannot change after the
  first save; a built-in layout refuses save and delete and copies cleanly.
- An account in two groups is refused by the key; two overlapping auto-include rules are refused at save; a parent
  account brings its sub-tree; `unassigned_accounts` lists accounts in no group and no rule.
- A formula that refers to itself, to a deleted item, or through a KPI to itself is refused with its position; a
  referenced item cannot be deleted (the database refuses, the service says why); division by zero is `null`.
- A Records layout with a conditional summary computes won ÷ closed; more than 3 group-bys refused; a field the
  viewer cannot see in a saved layout makes the run fail with the contracts' sentence, not silently drop.
- A stale `row_version` on a layout save is refused (g4); a layout in use cannot be deleted (Q7).
- No built-in layout contains an account number (static scan of the definitions).

---

## 4. Saved reports, dynamic dates and packs

### 4.1 Current state

None. Mockup `reports.html` and `report-pack.html` show My reports (Name · Based on · Owner · Last run · Shared with)
and packs (Pack · Reports · Period · Schedule · Last sent) (CODE_CHANGES 100).

### 4.2 Decided

- 11-18 3:22 PM and inbox item 7: a saved report keeps layout + parameters; dates are stored as a dynamic preset
  (this month, last closed month, QTD, YTD, last 12 months) or fixed dates; the plan version is kept as saved; packs
  use saved reports and can hold both kinds. Presets are resolved by the app from `context.today` and the fiscal
  calendar, never by the AI (G6; contracts 4.1 lists the presets, `last_closed_month` is the latest closed month).
- Contracts 2.4-2.6, contracts Q12 A (pack dates replace each report's dates), Q13 A, Q21 A (a combined report is saved
  with its company list and is not scheduled).
- CODE_CHANGES 100: Shared with Only me · Specific people · Everyone with Reports access; packs hold Cover page,
  Contents (auto), reports and text pages.

### 4.3 Proposed schema

**`saved_report`**

| Column | Type and constraint |
|--------|---------------------|
| `saved_report_id` | INTEGER PRIMARY KEY |
| `layout_id` | INTEGER NOT NULL REFERENCES report_layout (RESTRICT) |
| `name` | TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120) |
| `owner_user_id` | INTEGER NOT NULL (master user id) |
| `share_mode` | TEXT NOT NULL DEFAULT 'private' CHECK IN ('private', 'people', 'everyone') (Q8) |
| `dates_mode` | TEXT NOT NULL CHECK IN ('preset', 'fixed', 'periods') |
| `dates_preset` | TEXT CHECK IN ('this_month', 'last_month', 'last_closed_month', 'this_quarter', 'last_quarter', 'quarter_to_date', 'this_fiscal_year', 'fiscal_year_to_date', 'last_fiscal_year', 'last_12_months') |
| `date_from`, `date_to` | TEXT dates, `date_from <= date_to` (fixed mode) |
| `columns_mode` | TEXT CHECK IN ('single_period', 'by_period', 'by_quarter', 'by_year') (financial) |
| `range_preset` | TEXT (the preset for a by-period range) |
| `add_total`, `show_adjustment_periods` | INTEGER NOT NULL DEFAULT 0 |
| `basis_method` | TEXT CHECK IN ('accrual', 'cash') |
| `basis_adjustments` | TEXT CHECK IN ('pre_adjustment', 'gaap', 'tax', 'management') |
| `entity_mode` | TEXT NOT NULL DEFAULT 'company' CHECK IN ('company', 'entities') (consolidated is refused until built) |
| `reclass_view` | TEXT NOT NULL DEFAULT 'as_reclassed' CHECK IN ('as_reclassed', 'full_trail') |
| `date_field_id` | TEXT (Records: the registry date field the range applies to) |
| `split_by` | TEXT CHECK IN ('job', 'job_type', 'pm', 'dimension', 'cost_code', 'month', 'entity') (Q11) |
| `split_dimension_type_id` | INTEGER REFERENCES dimension_type (when `split_by` = 'dimension') |
| `last_run_at` | TEXT (set by an explicit `mark_run` call, never by a run itself) |
| `created_by`, `created_at`, `updated_by`, `updated_at`, `row_version` | as `report_layout` |

CHECKs tie the date columns to `dates_mode` (preset needs `dates_preset`; fixed needs both dates; periods needs rows in
`saved_report_scope`), and the financial-only columns to a financial layout (service rule, as the layout kind is
another table).

**`saved_report_compare`**: `saved_report_id`, `position` BETWEEN 1 AND 2, `type` CHECK IN ('prior_period',
'prior_year', 'plan', 'job_budget'), `plan_version_id` INTEGER REFERENCES operating_plan_version (area 7; RESTRICT);
CHECK (`type` = 'plan') = (`plan_version_id` IS NOT NULL). 'job_budget' only under Q11. A plan version used here
cannot be deleted (it can be archived, as the 11-18 3:14 PM decision says).

**`saved_report_filter`**: `saved_report_id`, `position`, `kind` CHECK IN ('dimension', 'project', 'cost_code',
'contact', 'field'), then the one typed reference the kind needs: `dimension_type_id` + `dimension_value_id` +
`include_children`; `project_id`; `cost_code_id`; `contact_id` (Q12); or `field_id` + `op` + `value_json` + `preset`
(Records). Foreign keys RESTRICT, so a job or dimension value used by a saved report is deactivated, not deleted.

**`saved_report_scope`**: `saved_report_id`, `scope_kind` CHECK IN ('period', 'entity', 'company'), `ref_id` INTEGER
(a `fiscal_period.period_id`, a `company_entity.entity_id`, or a master company id for a combined report; only the
first two are checked by FK, the third by the service), `sort`; UNIQUE (`saved_report_id`, `scope_kind`, `ref_id`).

**`report_share`**: `share_id`, exactly one of `saved_report_id` or `pack_id`, `user_id`; UNIQUE per owner row and
user. Used only when `share_mode` = 'people'.

**`report_pack`**: `pack_id`, `name`, `owner_user_id`, `share_mode`, `pack_dates_mode` / `pack_dates_preset` /
`pack_dates_from` / `pack_dates_to` (NULL mode keeps each report's own dates, contracts Q12 A), `created_*`, `updated_*`,
`row_version`. **`report_pack_item`**: `pack_item_id`, `pack_id`, `sort`, `item_kind` CHECK IN ('cover', 'contents',
'report', 'text'), `saved_report_id` REFERENCES saved_report (RESTRICT; required for 'report'), `title`, `body_text`
(max 4000; cover and text pages) (Q9).

### 4.4 Services, effects, tests

- `saved_reports.py` and `packs.py`: list, get, save (version), delete, `mark_run`. Read needs the run permission of
  the kind; saving an own private report needs the run permission; a shared one needs `report.design` (contracts
  2.1). A shared report is run with the viewer's own permissions and row limits (G7), never the owner's.
- Layout usage (`layout_usage`) counts saved reports, packs through their items, and active KPIs; delete refusals use
  the contracts' sentence (F7, Q7).
- Tests to write later: every preset resolves against a fixed `context.today` and a non-calendar fiscal year
  (`last_closed_month` follows `is_closed`); a fixed range with from after to is refused; a saved plan version
  survives a newer version being added; deleting a plan version, job or dimension value used by a saved report is
  refused with the report's name; a pack with pack dates overrides each report's dates and a pack with none does not;
  a shared report run by a user who lacks the permission is refused, not hidden; `mark_run` is the only writer of
  `last_run_at` (a run writes nothing, file compare); a combined saved report keeps its company list; `share_mode`
  'people' needs at least one recipient and each must be a company user.

---

## 5. Schedules and in-app delivery

### 5.1 Current state

None. The baseline has no scheduler, no outbox and no notification table (grep of `001_company.sql`). Files go
through `storage.py` (H3).

### 5.2 Decided

- Contracts 7.3 (contracts Q2 A, Q18 B): a schedule runs while the app is open on a computer where its owner is signed in to
  that company; a run due while closed runs once at the next sign-in (caught up); delivery is in-app only in v1 (an
  outbox list and an in-app notification); no email; each run uses the **owner's permissions at run time** (G7);
  recipients are users of the company who can run the report; a combined report cannot be scheduled (contracts Q21 A).
- CODE_CHANGES 100: frequency, "N business days after close or a fixed day", "Only send after the period is closed
  (on)", recipients, message, Send to me for review first.
- Area 10's deferral runner is the same pattern (while open, origin System, no approval).

### 5.3 Proposed schema

- **`report_schedule`**: `schedule_id`, `name`, `target_kind` CHECK IN ('saved_report', 'pack'), `saved_report_id` /
  `pack_id` (exactly one, RESTRICT), `format` CHECK IN ('pdf', 'excel'), `when_rule` CHECK IN ('monthly', 'weekly',
  'after_period_close'), `day_of_month` BETWEEN 1 AND 31, `weekday` BETWEEN 0 AND 6, `delay_days` BETWEEN 0 AND 23
  (business days, using area 13's work week and holidays), `only_after_close` INTEGER NOT NULL DEFAULT 1, `message`
  (max 1000), `owner_user_id`, `is_active`, `last_fired_period_id` REFERENCES fiscal_period, `last_fired_date` TEXT
  (the two catch-up markers: what the last run covered), `created_*`, `updated_*`, `row_version`.
- **`report_schedule_recipient`**: `schedule_id`, `user_id`; PK both.
- **`report_schedule_run`**: `run_id`, `schedule_id`, `due_for_period_id` / `due_for_date` (what it covers),
  `started_at`, `finished_at`, `status` CHECK IN ('delivered', 'partly_delivered', 'skipped', 'failed'), `message`
  (one plain sentence), `file_storage_key` and `file_name` and `size_bytes` (through `storage.py`, a relative key
  never a path), `caught_up` INTEGER, `run_as_user_id`. Insert-only except `finished_at`, `status`, `message` and
  the file columns while the run completes (service rule).
- **`report_delivery`**: `delivery_id`, `run_id`, `recipient_user_id`, `delivered_at`, `read_at` (NULL = unread;
  this is the in-app notification, Q19). The outbox read re-checks that the recipient can still run the report.

### 5.4 Service rules

`report_schedules.py`: `list`, `get`, `save` (authorize `report.schedule` plus the run permissions), `delete`,
`run_now`, `list_runs`, `list_delivered`, and `post_due(context)` called by the app on company open and on its timer,
the same hook as area 10's `deferrals.post_due` (H2: `today` from the context). `post_due` finds the schedules whose
due period or date is later than their `last_fired_*`, runs each once as its owner (the owner must hold the
permissions now; otherwise the run is `skipped` and the owner is told why), and records the run. A pack renders the
reports the owner may run and lists the others in the run message (contracts 7.2 `skipped`).

### 5.5 Tests to write later

An `after_period_close` schedule fires once when the month closes and not again on reopen and re-close unless the
period is closed again with a new close event; a month missed while the app was closed runs once at sign-in, not once
per missed day; a run uses the owner's permissions (an owner who lost `money.view` gets `skipped` with a reason); a
recipient who cannot run the report is refused at save; a recipient reads only their own deliveries; two app windows
cannot fire the same due run twice (the `last_fired_*` update is in the same transaction as the run row); a combined
saved report cannot be scheduled; the Agent cannot save, run or read a schedule.

---

## 6. KPIs

### 6.1 Current state

No KPI table. `periods._close` (`modules/services/periods.py:339`) sets the closed flag and writes the history row; the
close snapshot and the freeze hook are area 13's proposals (sections 4.3 and 4.5).

### 6.2 Decided

Contracts 2.7 and contracts Q5, Q24-Q26 (owner 2026-11-19): a KPI is its own record (name, source: a group or formula of a
layout, or a measure; format); each has a value per period, live while the period is open and **frozen** when it
closes, in the close transaction, with its own rows per close (a reopen and re-close keep the earlier rows); reports
read the latest frozen value for a closed period; the KPI keeps its own basis (accrual by default and the company's
adjustment default) and `range_method` (sum, average, last, or recalculate); a KPI added after a period closed has no
frozen value for it; a value that fails (division by zero) is stored as null with a note and never blocks the close;
frozen rows are insert-only, never edited, and audited (AX4). Area 13 section 4.5 fixes the call order: checks →
closed flag → history row → snapshot → KPI values → commit → checkpoint. Delete blocks: a layout item or layout used
by an active KPI; a measure used by one.

### 6.3 Proposed schema

**`kpi`**: `kpi_id`, `name` (unique ignoring case, service), `source_kind` CHECK IN ('group', 'formula', 'measure'),
`layout_id` REFERENCES report_layout (RESTRICT), `item_id` REFERENCES layout_item (RESTRICT), `measure_id` REFERENCES
nonfinancial_measure (RESTRICT) (CHECK: group or formula needs `layout_id` and `item_id`; measure needs `measure_id`),
`format` CHECK IN ('number', 'currency', 'percent', 'ratio'), `decimals` BETWEEN 0 AND 4, `over_plan_is`,
`basis_method` CHECK IN ('accrual', 'cash') DEFAULT 'accrual', `basis_adjustments` CHECK IN ('pre_adjustment',
'gaap', 'tax', 'management') DEFAULT 'pre_adjustment', `range_method` CHECK IN ('sum', 'average', 'last',
'recalculate'), `is_active` DEFAULT 1, `created_*`, `updated_*`, `row_version`. A KPI has no dimension or job filters
(a company figure). `layout_id` must be a financial layout of one `report_type`; the source item may be in a layout
that other users edit, so editing that item is refused while an active KPI uses it (contracts 2.2 sentence).

**`kpi_value`** (insert-only)

| Column | Type and constraint |
|--------|---------------------|
| `kpi_value_id` | INTEGER PRIMARY KEY |
| `kpi_id` | INTEGER NOT NULL REFERENCES kpi (RESTRICT) |
| `period_id` | INTEGER NOT NULL REFERENCES fiscal_period |
| `close_event_id` | INTEGER NOT NULL REFERENCES period_status_history(history_id) (the Close row, area 13) |
| `value_cents` | INTEGER, integer CHECK (format Currency) |
| `value_decimal` | TEXT (a decimal string, other formats) |
| `note` | TEXT CHECK (length BETWEEN 1 AND 300); required when both values are NULL |
| `kpi_row_version`, `layout_row_version` | INTEGER NOT NULL (the definitions at freeze, Q15) |
| `frozen_at`, `frozen_by` | TEXT, INTEGER NOT NULL |

CHECK at most one of `value_cents`, `value_decimal`; CHECK (value both NULL) = (`note` IS NOT NULL); UNIQUE (`kpi_id`,
`close_event_id`); index (`kpi_id`, `period_id`, `close_event_id`). Triggers refuse UPDATE and DELETE (integrity of
the closed record, as area 13's `period_close_snapshot`; H4 allows an integrity backstop). Audit trigger on insert.

### 6.4 Writer and rules

- **One writer:** `kpis.freeze_for_close(conn, context, period, close_event_id)`, called only from `periods._close`
  (area 13 call order) inside the close transaction; a static test allows no other writer of `kpi_value`. It
  evaluates every active KPI's source on the KPI's basis for that single period, from the period summary written in
  the same transaction (area 10 section 4), so the frozen figure and the closed ledger agree.
- **Periods:** values are frozen for the twelve month periods. Periods 13 and 14 store none; a year or total column
  with `range_method` `recalculate` computes live, and `sum`, `average` and `last` use months 1-12 (Q13).
- **Failures:** a failed value is stored as null with a note and never blocks. What counts as a failure is Q14.
- **Reads** (`get_kpi_values`): `frozen` (latest close event's row), `live`, or `not_frozen`; `history` lists every
  close's row; `live_now` and `differs` are computed by the service (contracts 2.7). Needs `report.financial` and
  `money.view`.
- **Editing a KPI** never changes frozen rows. Deactivating keeps them. Deleting is refused while a formula token
  refers to it.

### 6.5 Tests to write later

Every active KPI gets one row per close, in the close transaction; a rolled-back close leaves none (area 13 tests
extend); reopen and re-close adds a second row and keeps the first; a KPI created later has no frozen row (`not_frozen`);
a division by zero stores null with its note and the close succeeds; UPDATE and DELETE are refused; a KPI that refers
to a formula that refers to the KPI is refused at save; periods 13 and 14 store none; `kpi_row_version` equals the
KPI's version at the close; the frozen value does not change when the layout is edited afterwards; the frozen value
equals the live value computed at the close date.

---

## 7. Non-financial measures

### 7.1 Current state

No tables. `custom_field_value` holds per-record values, not monthly company figures.

### 7.2 Decided

11-18 inbox item 6 and contracts section 6: company-defined monthly measures (kW installed, roof squares,
headcount) with a unit, source typed or from jobs (a rule over the Jobs source), usable in formulas; typed values
override derived ones; `aggregate_over_periods` (sum, average, last) for quarter, year and total columns; typed
values **locked with the period** and editable again only after a reopen, each change audited with before and after
(contracts Q16 B); derived values keep the value they had when the period closed; import is all-or-nothing and a value for a
closed period is an error row; a derived value is a company figure computed with no row limits (contracts Q17 A);
deactivation is refused while a formula or KPI uses the measure. Area 13 Q19 A: only a full close locks measures
(partial locks do not).

### 7.3 Proposed schema

- **`nonfinancial_measure`**: `measure_id`, `name` (unique ignoring case, service), `unit` (max 20), `decimals`
  BETWEEN 0 AND 4, `aggregate_over_periods` CHECK IN ('sum', 'average', 'last'), `source_type` CHECK IN ('typed',
  'from_jobs'), `rule_source_id` TEXT (a Records source key, `src_jobs`), `rule_summary` CHECK IN ('count', 'sum',
  'avg', 'min', 'max'), `rule_field_id` TEXT, `rule_date_field_id` TEXT (CHECK: `from_jobs` needs all four, `typed`
  none), `is_active`, `created_*`, `updated_*`, `row_version`. **`nonfinancial_measure_filter`**: `measure_id`,
  `position`, `field_id`, `op`, `value_json` (the rule's job filters).
- **`nonfinancial_value`**: `value_id`, `measure_id` (RESTRICT), `period_id` REFERENCES fiscal_period (a month period;
  the service refuses 13 and 14), `typed_value` REAL, `derived_value` REAL, `origin` CHECK IN ('Typed', 'Import'),
  `import_id` REFERENCES nonfinancial_import, `entered_by`, `entered_at`, `derived_at` (set when frozen at close),
  `row_version`; UNIQUE (`measure_id`, `period_id`). Quantities may be REAL (CLAUDE.md rule 1 reserves integer cents
  for money); display rounding follows `decimals`. The effective value is the typed one if present, else the derived
  one.
- **`nonfinancial_import`** (Q18): `import_id`, `fiscal_year_id`, `file_name`, `storage_key` (the uploaded file kept
  through `storage.py`), `row_count`, `value_count`, `imported_by`, `imported_at`. A rejected file stores nothing
  (all-or-nothing, with the error list returned, never saved).

### 7.4 Rules

- **Typed save:** authorize `report.design`; refuse a closed period (`PeriodClosedError`, the contracts' sentence);
  a value in an open period but locked for Journal entries is allowed (partial locks do not apply, area 13 Q19 A).
- **Derived values (Q16):** for an open period they are computed live at read, from the Jobs source with no row
  limits, and are **not stored**; the period close stores them in the close transaction (`derived_value`,
  `derived_at`), the same call that freezes KPIs, so a closed period never moves. A reopen leaves the stored value;
  the next close overwrites it (the change is in the audit log). Contracts 6.4 says derived values are recomputed
  and written on every report run; this draft does not let a read write (F9).
- **Definition check:** a `from_jobs` rule that uses a money field is refused at save unless the definer holds
  `money.view`; the derived figure is a company total, shown to anyone who can run a report using it.
- **Dependencies:** `formula_token.measure_id` and `kpi.measure_id` are RESTRICT, so a used measure cannot be deleted;
  `deactivate_measure` names the layouts.

### 7.5 Tests to write later

A typed value is refused in a closed period and allowed after a reopen with an audit row; an import with one bad cell
imports nothing and returns every error; an import value for a closed period is an error; a derived value is not
stored until the close and then equals what the live computation gave on the close date; a later job change does not
move a closed period's derived value; `typed` overrides `derived`; periods 13 and 14 refused; a measure used by a
formula or KPI cannot be deleted or deactivated; the rule cannot use a money field without `money.view`; the Agent
cannot define or enter values.

---

## 8. Combined runs across company files

### 8.1 Current state

`company_registry` and `user_company_access` (master file: `migrations/001_master.sql:47-68`) already list the companies a
user can open; `companies.open_company` builds a `ServiceContext` per company (`companies.py:22`). No report service
exists. There is no consolidation inside a file (`company_entity`, `:3871`, has no consolidation service).

### 8.2 Decided

Contracts 4.7 (contracts Q14 B, Q19 B, Q20-Q23 A) and CODE_CHANGES 100: one report across several company files, **no
consolidation and no automatic eliminations** (eliminations are formula rows using `company_group` and
`company_account` operands); only companies the user can open in this sign-in (Deny wins, not archived) and holds
`report.financial` and `money.view` in; each company's figures come from its own file's services, then are added into
a Combined column; **accounts are matched by account number** (the one stated exception to "never by number"); an
account in another company whose number is not in this company's chart is shown as its own row labelled with its
company, under the group its number or type fits, or "Not in any group", counted in the totals, and listed in a
warning; currencies must match; dimension, job, cost code and contact filters, entities and plan comparisons are
refused; KPIs are not combined; a combined report can be saved (with its company list) and added to packs, but not
scheduled.

### 8.3 Proposed schema

No new table. `report_layout.scope` = 'combined' (section 3.3); `formula_token.company_id` and `account_code` (3.3);
`saved_report_scope` rows with `scope_kind` = 'company' hold the company list (4.3); `saved_report.entity_mode` stays
'company'. Master company ids are plain integers with no foreign key (the files are separate databases).

### 8.4 Service rules and tests

- `report_combined.py`: `list_combinable_companies`, `run_combined`, `drill_combined`. The run re-checks access in
  each company's own file with its own `ServiceContext` before reading anything; one failure refuses the whole run,
  naming the company; a file whose schema is stale (`SchemaUpgradeBlockedError`) refuses the run naming it.
- Matching: `account.code` string equality; matching never uses name or type; unmatched accounts come back in
  `unmatched_accounts` and in a `warnings` entry.
- Tests to write later: the Combined column equals the sum of the company columns (fixture of two files); an
  unmatched account appears once under its fitting group and in the totals and the warning; mismatched currencies
  refused; a company the user cannot open is not offered and a forced id is refused; Deny wins over Grant; an archived
  company is refused; a combined layout is the only kind that accepts company operands; a company formula is `—` in
  the company columns; a combined saved report cannot be scheduled; no dimension or job filter is accepted; each
  company's own run equals its single-company report.

---

## 9. Running reports

### 9.1 Reading the period summary (area 10 section 4)

- Today there is no summary, no report engine and no dimension service. `journal_line` is indexed by account,
  project, cost code, contact, entity and entry (`:5773-5863`) but not by period (the period is on `journal_entry`).
- The engine reads `ledger_period_balance`: a P&L cell sums summary rows for the column's period ids
  (`period_ids_for_basis`, with Management handled by the engine, section 3.1); a balance sheet cell sums every
  period up to the column's end date, computed as one running pass over the periods, not one query per column.
  Dimension and job filters narrow the summary by `project_id`, `cost_code_id` or a precomputed set of
  `dimension_set_id` values; the 'management' basis drops accounts with `is_tax_strategy_only`.
- **Requests to area 10** (a dated amendment line there when this area is approved): a covering index
  `ledger_period_balance (period_id, account_id, debit_cents, credit_cents)` for the unfiltered path, and an index
  `dimension_set_member (dimension_value_id, dimension_set_id)` for the set lookup. The summary has **no contact
  key**, so the customer or vendor filter in contracts 4.1 cannot be answered from it (F8, Q12).
- Cash basis runs from payments and allocations at run time (contracts Q9 A) and is not in the speed budget.
- **Performance target (contracts Q10 A):** a 12-column P&L with a plan comparison on 250,000 posted lines in under 1
  second, accrual, no contact filter. Q20 decides where the test runs.

### 9.2 "As reclassed" (contracts 4.4; area 10 section 2)

Amounts are the GL's in both views (the summary serves both); only drill and detail rows differ. The service reads
`reclass_line` (`root_journal_line_id`, `original_journal_line_id`, `side`, the original's name, date, memo, item and
job): a reclass pair shows as the original line under its latest account from the reclass date on; chains follow
`root_journal_line_id` to the latest In line in range; grouping by name, job and item uses the original's details.
Closed figures and the close snapshot never change. No table in this area.

### 9.3 money.view and permissions at run time

- `run_financial`, `drill`, `run_combined` and KPI reads need the run permission **and** `money.view` (contracts Q7 A),
  checked before any read; `report.job_cost` runs need `money.view` too. A Records run that uses a money field
  anywhere (column, filter, sort, group-by, formula column) is refused before the query with "This report uses money
  fields your role can't see." (contracts Q15 B); the field catalogue leaves money fields out for such a viewer. Drills,
  exports, PDFs, packs and scheduled runs run the same checks as the viewer (a pack lists the refused report in
  `skipped`).
- Row limits (project scope MR3, own-records limits, contact sides) are applied **before** grouping so totals count
  only visible rows.
- The Agent runs reports only through `AGENT_ALLOWED`; it never exports (G7), designs or schedules (Q24).

### 9.4 Company settings and the cash flow category

- `company_settings.report_basis_default` TEXT NOT NULL DEFAULT 'accrual' CHECK IN ('accrual', 'cash') (CB1: "a
  company setting picks the default") and `company_settings.report_adjustments_default` TEXT NOT NULL DEFAULT
  'pre_adjustment' CHECK IN ('pre_adjustment', 'gaap', 'tax', 'management') (contracts Q24 A). Both permissive defaults,
  audited; the company settings audit triggers (`:3536` onward) add the two columns (Q17).
- `account.cash_flow_category` TEXT NULL CHECK IN ('cash', 'investing', 'financing', 'op_customers', 'op_vendors',
  'op_employees', 'op_interest', 'op_taxes', 'op_other') (CF1: each account has a category, defaulted from its type
  and control type, changeable with an audit entry). NULL means "use the default derived from the account's type,
  subtype and control type" (computed by the service), so chart templates need no new column. The cash set is
  area 12's (section 5.3), not an account category on a card account. The cash flow statement's computation and rows
  are not in the contracts; this pass stores the layout type and the column only (section 14; Q17).

### 9.5 Exports and output files

Excel and PDF files are written through `storage.py` (H3) and returned as handles; EX1's limits apply to Records
exports (250,000 rows, a confirmation above 50,000). EX1 says a `Report export` checkpoint is signed "for
journal-based reports only"; whether P&L and balance sheet exports count is Q22.

---

## 10. Permissions: placement (amendments to area 18)

### 10.1 Current state

`report.financial`, `report.job_cost` and `report.export` exist (`001_company.sql:1248-1250`;
`modules/services/permissions.py:98-100`); `AGENT_ALLOWED` holds `report.financial` and `report.job_cost`
(`permissions.py:118-121`: "every report.* code except report.export", G7). `money.view`, `report.records`,
`report.design` and `report.schedule` do not exist. Area 18's seed tables (sections 2.4.1-2.4.3) place none of them;
contracts section 12 item 14 states the owner's rows for `money.view` and leaves the others to planning.

### 10.2 Proposed codes (all not sensitive; module Reports)

| Code | Used by |
|------|---------|
| `money.view` | any money in any report: financial runs, KPI reads, Records money fields, exports |
| `report.records` | run Records reports and read the Records field catalogue |
| `report.design` | save layouts, KPIs, measures and shared saved reports and packs |
| `report.schedule` | save, run now and delete schedules |

### 10.3 Placement (Q21; area 18 carries the dated amendment when approved)

- **Caps (2.4.1):** the Accountant cap gains all four (68 codes with areas 12 and 10); the Sales rep and Operations
  caps gain `money.view`, `report.records` and `report.design` (14 → 17 and 30 → 33). `report.schedule` only in the
  Accountant cap.
- **Level defaults (2.4.2, cumulative, no sensitive code):** `money.view` in Accountant · View only (it already holds
  `report.financial` and `report.job_cost`), Sales rep · Manager and Operations · Standard (contracts item 14);
  `report.records` in Accountant · Standard, Sales rep · Standard and Operations · Standard; `report.design` in
  Accountant · Manager, Sales rep · Manager and Operations · Manager; `report.schedule` in Accountant · Manager.
- **Templates (2.4.3):** the Accountant templates (Controller, Staff accountant, Payroll, AP clerk, AR clerk) are on
  the Accountant role, whose View only level already gives `money.view`. Sales manager, Project manager and Estimator
  name `report.job_cost` but sit on levels that may not hold `money.view`, so each adds `money.view` in its
  non-sensitive column (Q23); the two union templates inherit. Controller also adds `report.schedule` (it holds
  `report.export` today); no other template changes.
- **AGENT_ALLOWED:** `money.view` and `report.records` (read-only codes) are added so the Assistant keeps running
  financial reports as G7 says; `report.design`, `report.schedule` and `report.export` are not (Q24).
- **Placement check, in words:** every new code is in the Accountant cap; every level default stays inside its role's
  cap and holds no sensitive code; View only holds no write code (`money.view` is a read code); each template sits
  inside the union of its roles' caps. The scratch check in area 18 section 2.4 is re-run when this is built (area 18
  section 2.6).

---

## 11. Row version (rule g4) and audit

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `report_layout`, `saved_report`, `report_pack`, `kpi`, `nonfinancial_measure`, `report_schedule`, `company_list_default` | yes | yes |
| `nonfinancial_value` | typed value | yes |
| `layout_item`, `layout_group_account`, `layout_auto_include`, `formula_token`, `report_chart`, `report_chart_series`, `records_*`, `saved_report_compare`, `saved_report_filter`, `saved_report_scope`, `report_share`, `report_pack_item`, `report_schedule_recipient`, `nonfinancial_measure_filter` | saved with their parent row | no (the parent's `row_version` guards the whole tree) |
| `kpi_value`, `nonfinancial_import`, `report_schedule_run`, `report_delivery` | insert-only, or one completion update | no |
| `user_list_pref` | last write wins | no (Q3) |

- **Audit (area 18 section 1):** every new table has insert, update and delete triggers, except the event and display
  rows Q4 may exempt (`report_schedule_run`, `report_delivery`, `user_list_pref`, `saved_view`). `kpi_value`,
  `nonfinancial_value` and `nonfinancial_import` are audited (AX4), with before and after on every change. Services
  pass the reason through `tx.py`; no new action needs a required reason (no new control is added).
- Integrity backstops here guard only closed-record data: `kpi_value` insert-only. Everything else (read-only
  built-ins, one-group-per-account is a key; the rest are service rules, H4).
- Controls: none added. The settings in 9.4 are permissive defaults, not controls.

---

## 12. Conflicts with decisions (flagged, not resolved)

- **F1 Charts as layout items.** Contracts 2.2 shows a chart as an item of `type: "chart"` in the tree, and section 12
  item 2 lists `chart` as an item type beside item 5's `layout_chart`. This draft stores charts in `report_chart`
  and `report_chart_series` (one table for both kinds, since a records chart's series are columns); the service still
  presents a chart item in the contracts' JSON. No question: the service output is unchanged.
- **F2 Sharing.** Contracts 2.4 has `shared: true|false`; CODE_CHANGES 100 (owner 11-15) has Only me · Specific people ·
  Everyone with Reports access. Q8.
- **F3 Pack contents.** Contracts 2.5 holds saved reports only; CODE_CHANGES 100 shows Cover page, Contents (auto),
  reports and text pages. Q9.
- **F4 Where the plan version lives.** 11-18 inbox item 7 puts `plan_version_id` on the saved report; contracts 2.4
  puts it inside `compare` (up to two compare columns). This draft uses compare rows.
- **F5 Preferences and audit.** 11-15 2:13 PM: the per-user store is not audit-logged and never shared. The baseline
  audits `user_list_pref` and `saved_view` (`:5505-5608`) and area 18 (owner-approved) lists them as audited and
  exempts only derived tables and three named categories. Q4.
- **F6 Account ranges.** The 11-18 decision lets a group take "an account range so new GL accounts join
  automatically", which is a rule by account number; the task rule says accounts are found by role or group rules, never
  by number, with combined-run matching as the one exception. This draft keeps the range as a user-defined group rule
  and keeps every shipped layout number-free. Q6.
- **F7 Deleting a layout.** Contracts 2.1 and the 11-18 inbox item 8 refuse deletion only while a pack uses it; a saved
  report or an active KPI that uses it would otherwise have a dangling reference. Q7.
- **F8 Contact filter vs the summary.** Contracts 4.1 allows a customer or vendor filter on financial runs; area 10's
  summary key (`period`, `account`, `entity`, `project`, `cost_code`, `dimension_set`) has no contact, so that filter
  cannot use the summary and cannot meet the 1 second budget. Q12.
- **F9 Derived measures written on every run.** Contracts 6.4: `refresh_derived_measures` recomputes and writes derived
  values for open periods "on every report run". A read that writes conflicts with the rule that reads write nothing
  (workflow-standards prevention rule; CLAUDE.md rule 7). Q16.
- **F10 Builder features the contracts omit.** CODE_CHANGES 100 (owner 11-15, confirmed 2:03 PM) lists columns "split by
  Job, Job type, PM, Profit center, Cost center, Cost code, Month, Entity" and a Budget and Variance column from job
  budgets; the approved contracts have `columns.mode` only by period, quarter and year, and compare types prior
  period, prior year and plan. Job cost reports (job profitability, WIP schedule) have no `report_type`. Q11.
- **F11 KPI freeze never blocks.** Contracts 2.7: a failed value is null with a note and never blocks the close.
  Area 13's freeze runs inside the close transaction, so an unexpected error would roll the close back. Q14.
- **F12 Consolidation entity.** CODE_CHANGES 100 and the 11-15 answer show an Entity "consolidated" with an
  Eliminations column for subsidiaries inside one file; contracts 4.1 refuses `entity.mode: consolidated` until
  consolidation is built (planned). No schema here; `entity_mode` has no 'consolidated' value.
- **F13 AGENT_ALLOWED.** G7 says the Assistant can run reports but never export; area 18's pattern and areas 12 and 10
  keep new codes out of `AGENT_ALLOWED`; but a financial run needs `money.view` (contracts Q7 A), so leaving it out
  would silently remove the Assistant's financial reports. Q24.
- **F14 Report export checkpoint.** EX1: a `Report export` checkpoint "for journal-based reports only"; not stated
  for the summary-based P&L and balance sheet. Q22.
- **F15 Area 18 and area 10 amendments.** Area 18's approved seed tables do not place the four codes or the template
  changes; area 10's approved summary lacks the two indexes. Adding them amends approved areas (dated lines when this
  area is approved).
- **F16 Management basis.** `periods.BASES` has no 'management' (`periods.py:27`) while A1 and contracts 4.1 do. The
  report engine adds it; no schema.

---

## 13. Questions for the owner

Recommended option first.

**Q1. Custom fields in the registry.** (section 1)
- A. Every active custom field of a covered record type is offered automatically (permission: the record type's read
  code; Money fields are money fields). An inactive field is not offered but keeps working in saved definitions.
- B. A per-field flag "Show in reports and column pickers" (default on) in `custom_field_def` (area 16 adds it).

**Q2. Company default list layout.** (section 2)
- A. A `company_list_default` table; an Admin saves it from the column picker (audited).
- B. No company default in v1; "Save as company default" is dropped from the picker.

**Q3. `row_version` on display-only preferences.** (g4)
- A. `user_list_pref` and `saved_view`: last write wins, no `row_version`; the company default has one.
- B. A `row_version` on all three; a stale save returns the shared "Changed by someone else" conflict.

**Q4. Audit of preferences and event rows.** (F5, area 18)
- A. Exempt `user_list_pref`, `saved_view` (display only, 11-15 2:13 PM), `report_schedule_run` and `report_delivery`
  (event records, area 18's third category); drop the two triggers that exist; area 18 gets a dated amendment.
- B. Audit all of them.

**Q5. Built-in layouts.** (section 3.3)
- A. Rows made and refreshed by an idempotent upkeep at company open from code (`built_in_key`, `built_in_version`);
  read-only; copy to edit.
- B. Seeded in the baseline (changes after release need a migration).
- C. Code-only (no rows); a saved report cannot point at a built-in layout.

**Q6. Auto-include rule kinds.** (F6)
- A. `account_range` (company layouts only), `account_type`, `role` and `cash_set`; shipped layouts use only the last
  three.
- B. `account_range` and `account_type` only.

**Q7. Deleting a layout.** (F7)
- A. Refused while any saved report, pack item (through its saved report) or active KPI uses it, naming them.
- B. Refused only for packs and KPIs; saved reports that use it are deleted with it.

**Q8. Sharing a saved report or pack.** (F2)
- A. Three modes, as the mockup: private, specific people (`report_share`), everyone with Reports access.
- B. A boolean shared flag, as the contracts.

**Q9. Pack contents.** (F3)
- A. Items of kind cover, contents, report and text (the mockup).
- B. Saved reports only.

**Q10. How saved report parameters are stored.** (section 4.3)
- A. Typed columns and child rows (compare, filter, scope), so a used plan version, job, cost code or dimension value
  is found by query and its delete refused.
- B. One JSON column; references checked only by the service.

**Q11. The builder features the contracts omit.** (F10)
- A. Add `saved_report.split_by` (and `split_dimension_type_id`) and the compare type `job_budget` to the schema now;
  job cost reports are financial layouts with job filters, split-by columns and job budget compare (no new
  `report_type`); the contracts get a later amendment for the shapes.
- B. Leave them out of v1; job cost reports are Records reports on the Jobs source.

**Q12. Customer or vendor filter on financial reports.** (F8)
- A. Add `contact_id` to the period summary key (a dated amendment to area 10) so every filter reads the summary.
- B. A contact-filtered run reads `journal_line` through its `contact_id` index and is outside the 1 second budget.
- C. Drop the contact filter from financial runs (Records reports keep theirs).

**Q13. KPI values for periods 13 and 14.**
- A. None; values are frozen for the twelve month periods, and year or total columns use `recalculate` or months 1-12.
- B. Also frozen for 13 and 14 when the KPI's basis includes them.

**Q14. KPI freeze failures.** (F11)
- A. Any failure evaluating a KPI (typed or unexpected) is stored as null with a note ("Could not be calculated"),
  logged, and the close continues.
- B. Only typed formula failures are stored as null; an unexpected error rolls the close back and is logged.

**Q15. What a frozen KPI value records of its definition.**
- A. `kpi_row_version` and `layout_row_version` (a pointer into the audit log's before and after).
- B. Nothing; the audit log is enough.

**Q16. Derived measures.** (F9)
- A. Computed live for open periods (never stored by a read) and stored once, in the close transaction; reads write
  nothing.
- B. Stored on every report run for open periods, as the contracts say.

**Q17. Settings and the cash flow category now.** (section 9.4)
- A. Add `report_basis_default`, `report_adjustments_default` and `account.cash_flow_category` (NULL = default from
  type) now; the cash flow statement itself is built later.
- B. Add them with the cash flow work.

**Q18. Measure import record.**
- A. A small `nonfinancial_import` table (file kept through `storage.py`), as area 7's plan imports.
- B. No table; the audit rows on the values are the record.

**Q19. In-app notification for a delivered report.**
- A. `report_delivery.read_at` is the unread marker; a general notification feed is a later area.
- B. Build a general `notification` table now and use it here.

**Q20. The 250,000-line speed test.** (contracts Q10 A)
- A. A `perf` marker, deselected by default (like `live_clipboard`), run explicitly at the build step's review gate and
  before a release.
- B. In the normal suite (the file is built once per test worker; adds time to every full run).

**Q21. Where the four codes are placed.** (section 10.3)
- A. As proposed: all four in the Accountant cap; `money.view`, `report.records` and `report.design` also in the Sales
  rep and Operations caps; levels and Controller's `report.schedule` as in 10.3.
- B. Narrower: `report.design` and `report.schedule` in the Accountant cap only.

**Q22. Report export checkpoints.** (F14)
- A. Financial exports (P&L, balance sheet, cash flow, combined) sign a `Report export` checkpoint (they are computed
  from the ledger); Records exports and measure files do not.
- B. Only GL-style reports (trial balance, general ledger, journal entry lists), as EX1 reads.

**Q23. Templates and `money.view`.** (section 10.3)
- A. Add `money.view` to the Sales manager, Project manager and Estimator templates' non-sensitive column.
- B. No template change; a user below the level that holds it gets it by an Add override.

**Q24. AGENT_ALLOWED.** (F13)
- A. Add `money.view` and `report.records`; not `report.design`, `report.schedule` or `report.export`.
- B. Add none (the Assistant can no longer run financial reports).
- C. Add `money.view` only.

**Q25. Built-in layouts in this pass.**
- A. Profit and loss (standard), Balance sheet (standard) and one blank layout per kind; job profitability, WIP
  schedule and the board summary come with the areas that own their data.
- B. All seven mockup templates now.

---

## 14. Open items (not decisions)

- **Area 7:** `operating_plan_version` and `operating_plan_line` (`saved_report_compare.plan_version_id` references the
  first); job budgets (`project_budget`, `:282`) for a job budget compare (Q11).
- **Areas 6, 8, 15:** the Records source tables (`lead`, stage and status history, `activity`, `service_case`, the
  lead-to-job link, the sales rep on the contract) and `custom_field_def.record_type` 'Lead' (contracts 12 items 16-17);
  until they exist those sources are not offered. Estimates and Jobs sources can ship first.
- **Area 10:** a dated amendment adds the two indexes (9.1) and, under Q12 A, the contact key.
- **Area 13:** `periods._close` calls `kpis.freeze_for_close` and `measures.freeze_derived` after the snapshot (the
  call order is already in area 13 section 4.5); both are one transaction with the close.
- **Area 12:** the cash set used by the `cash_set` auto-include rule and the cash flow report.
- **Area 18:** the four permission rows, caps, levels, template and `AGENT_ALLOWED` lines (Q21, Q23, Q24), and the
  exempt-list change under Q4 A; the seeded code count becomes 86.
- **Area 21:** `row_version` mechanics and `StaleVersionError`; a general notification feed (Q19); whether
  `saved_view` can be shared.
- **Not designed by the contracts and not built in 2.9:** the cash flow statement's rows (CF1, direct method), the
  consolidated entity report (F12) and the drill-down handle format (an opaque token re-derived and re-authorized at
  call; no table).
- **Backups (area 18 and 2.8):** whether the delivered-report outbox files are part of a complete company backup
  (they are point-in-time copies of reports); today only attachments are named.
- **Services this area adds** (none exist): `field_registry`, `list_prefs`, `report_layouts`, `report_formulas`,
  `report_sources`, `saved_reports`, `packs`, `report_run`, `report_records`, `report_combined`, `kpis`, `measures`,
  `report_schedules`, `report_output`.
