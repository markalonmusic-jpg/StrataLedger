# Step 2.9 schema replan, area 7: jobs, job cost budgets, cost codes and cost types, dimensions, operating plan, WIP

Status: **Owner-approved 2026-11-20 (7bab6f0, answers 7ebcd4f, 8b68381, d582c7e, 64519fd and this commit)** (first
draft 2026-11-20, 7bab6f0; owner's answers recorded 2026-11-20, 2:25 AM, section 12). Docs only: nothing here
changes code, a baseline, a migration or a test. Every table, column, code and check below would be built only in the
2.9 baseline pass, after the replan is approved. PROPOSED items from the sources are not built as final. Amendment
lines the answers settle are written in areas 6, 8, 10, 13, 17 and 18 ("Amendment 2026-11-20 (owner 2:25 AM, from
area 7)"), and for the owner's 2:45 AM service-job decision in areas 6, 15 and 18 ("owner 2:45 AM, from area 7"),
whose sources the owner's 3:15 AM decision replaces ("owner 3:15 AM, from area 7; replaces the 2:45 AM sources"; the
withdrawn items are marked "Withdrawn 2026-11-20 (owner 3:15 AM)"); the rest stay open items (section 13).

Checked against (`Strata_Teams\shared_decisions.md`, by entry time): 2026-11-14 2:45 PM, 2:50 PM, 4:30 PM;
2026-11-15 2:08 PM, 3:52 PM; 2026-11-16 2:02 PM; 2026-11-18 2:14 AM, 1:25 PM, 3:14 PM, 3:16 PM; 2026-11-19 12:52 PM
(planning, chart rows), 2:20 PM, 9:28 PM, 11:20 PM (planning, estimate flow records); 2026-11-20 1:50 AM (planning,
decision audit answers: entities are area 21's), 2:25 AM (owner answers to this area).

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`: row 7 (A 11-14 new job, budget rights, jobs decisions; 11-15 dimension
  Required, dimension and cost code hierarchy; C 62, 73, 94, 111; D JD1; X project_dimension mapping; S 11-18 3:14 and
  3:16 PM) and the source keys. "Inbox inputs" lists nothing for area 7 alone; the area 8 forecast entry names the
  boundary with area 7 budgets.
- `Strata_Teams\planning_decision_audit_2026-11-20.md` section 5 (pending entries for area 7 and the ones to also read).
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md`: 2026-11-14 "New job screen (direct job creation),
  service and data notes", "job budget entry rights and the budget-required control", "thanks for the account
  numbers; Jobs decisions"; 2026-11-15 "Dimension Required setting replaces the proposed control" (1:45 PM), "Owner
  answers" (2:08 PM), "Dimension and cost code hierarchy" (3:52 PM), "persona audit, schema implications" (items 3, 8).
- `Strata_Teams\inbox\archive\to_planning_done.md`: 2026-11-18 "operating plans (company-level plan, schema, v1.0)".
- `Strata_Teams\inbox\to_planning.md`: 2026-11-20 1:15 AM "default accounts for the General conditions and Warranty
  cost codes".
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 62 (New job screen), 73 (the job's Budget vs actual card),
  94 (Dimensions and Required dimensions), 111 (one tree builder for dimensions and cost codes).
- `Strata_Teams\codex_reports\schema_gaps_vs_mockups_2026-11-18.md` (the `project_dimension` line).
- docs/next_step.md "Handed to later areas" (from areas 6, 8, 10, 13, 15, 17).
- docs/replan_2.9/area_8_pm_schedules.md sections 2.3, 3.1, 6.2-6.4, 7 (the boundary), F12, Q6, Q18, Q19;
  area_6_estimates_contracts.md sections 3.4, 9.3, 16 item 1; area_15_crm.md section 6; area_17 sections 4.3, 14
  (plan compare, `job_budget`); docs/contracts/reports.md section 12 item 11; area_10 section 4.2 (`dimension_set`);
  area_13 section 2.3 (`wip_current`, `manual_pct_complete`); area_18 sections 1.2 (audited tables) and 2.4 (codes).
- docs/decisions_2026-11-11.md by code: C5, C6 (chart), D1-D3, D9, D10, J2, J3, JD1, R45, RP3, RP5;
  docs/design_decisions.md "Customer codes"; docs/roadmap.md (JD1 notes, Phase 4).
- `migrations/001_company.sql` (cost_code, dimension tables, project, project_budget, poc_snapshot, journal_line,
  company_settings, contract, estimate_line, time_entry, user_project_scope, company_entity), `modules/database.py`,
  `modules/services/ledger.py`, `permissions.py`, `sequences.py`, `custom_fields.py`, `templates/coa/construction.csv`.

---

## 0. Summary

| # | Topic | Proposal in one line | Baseline |
|---|-------|----------------------|----------|
| 1 | The job record | One `project` DDL that gathers what areas 6, 8, 13 and 15 asked for, plus the New job screen's fields: job number from the customer code, a service job on a known job numbered from it (Q4 B), billing method (Q3 A), sales rep, customer PO, prevailing wage, recognition method; no draft jobs (Q1: a job exists only from a signed contract; a direct job writes a 'Direct' contract, Q2 A); `status`, the two cached budget totals (Q5 A) and `source_estimate_id` go | company |
| 2 | Job cost budget | `project_budget` becomes the one budget table: kind Original, Change order or Transfer, with its source link, who and when; the original locks at the first save; changes only by change orders and transfers (no approval); who may enter it is a company setting (Q9); "Require a budget before costs post" is a control, OFF | company |
| 3 | Cost codes and cost types | `cost_type` company list (five shipped); `cost_code.cost_type_id` NOT NULL replaces `cost_type_label`; default account and "counts toward % complete" inherited by sub-codes; codes fixed once saved and never reused; three levels kept (RP5) | company |
| 4 | Default accounts for General conditions and Warranty | General conditions defaults to 5070 Indirect Job Costs (Q15 A); warranty work is a service job posting to 5080 Warranty Expense in the open period, no reserve (Q16); defaults found by role, never by number (Q20 A) | company (template) |
| 5 | Dimensions | Which lines a dimension applies to; Required per dimension (Never, From job, Always) as a control (Q10); codes fixed; never deleted; moves logged; `project_dimension` for JD1 with one shared resolver; depth limit (Q11) | company |
| 6 | Operating plan | `operating_plan_version`, `operating_plan_line`, `operating_plan_import`; any number of named versions, no approved or default status; all-or-nothing import; never named "budget" | company |
| 7 | Job cost, Budget vs actual, warranty roll-up | Reads only: job cost from GL lines carrying the job (as recognized, area 10); committed from areas 4 and 9; a warranty service job's cost reported on the original job's Warranty line through the job link (Q16, Q17 A) | none |
| 8 | Percentage of completion and WIP | `project.poc_method` (D3), `poc_snapshot` gains who, when and the forecast revision used; WIP schedule of every open job grouped by service type; the WIP service is a build item (Q18) | company |
| 9 | Permissions, controls, settings | Existing `project.*` codes kept; new `job.budget.enter`, `cost_code.manage`, `dimension.manage`, `plan.manage` (Q9 A; Q14: the two manage codes held by Admin, Master and the Controller template, in no level); two settings and one per-dimension control, all logged, all R36 high-impact | master (codes) |
| 10 | Row version and audit | `row_version` on every editable table; imports and history insert-only; every new table audited | company |

Master file: only the new permission codes (registry rows). Entities inside one company file are area 21's (owner
2026-11-20 1:50 AM); nothing here designs them.

---

## 1. The job record (`project`)

### 1.1 Current state

- `project` (`001_company.sql:254-280`): `project_number` TEXT UNIQUE (comment "PRJ-2026-104"), `name`, `contact_id`
  NOT NULL, `source_estimate_id` FK estimate, `assigned_pm_id` INTEGER NOT NULL (a master user id, no FK),
  `original_budget_cents` and `revised_budget_cents` (cached totals, "forked dynamically via change logs"),
  `status` CHECK IN ('Mobilization', 'In Progress', 'Suspended', 'Completed', 'Closed Out'), `created_at` DATETIME
  DEFAULT CURRENT_TIMESTAMP, `service_type_id` and `service_stage_id` (RP4). Audited (`:5682-5744`).
- No job service exists (`modules/services/` has none). Tests insert jobs directly: `tests/authz_world.py:137`,
  `tests/test_ledger_rules.py:250`, `tests/test_roles_schema.py:53`.
- `user_project_scope` (`:1085`) gives project scope (MR3); `authz.py:27` refuses project-scoped work outside it.
- Customer codes and job numbers: design_decisions "Customer codes": job number = `customer_code` + '-' +
  `project_code` (AC0001-001); "a service case's project_code is the parent job's project_code + '-S' + a 2-digit
  sequence". No `project_code` column or job sequence exists; `sequences.py` has voucher and invoice series only.
- Columns other areas asked area 7 to write into this DDL: area 8 section 7 (close columns, `on_hold`, site, target
  dates, `manual_pct_*`, `billing_type`, `warranty_for_job_id`, `source_case_id`, `row_version`, drop `status`);
  area 15 section 6 (`sales_rep_user_id`, FK and index on `source_case_id`); area 6 section 16 item 1
  (`source_revision_id` replaces `source_estimate_id`).

### 1.2 Decided

| Decision | Source |
|----------|--------|
| A job can be created directly for an existing customer on a full New job screen; jobs from leads still come from signing | S 11-14 2:45 PM; A 11-14 "New job screen"; C62 |
| No draft jobs: a job exists only from a signed contract; a lead whose estimate isn't signed is the "draft". `project.is_draft` and every draft rule and test are dropped | owner 2026-11-20 2:25 AM, Q1 |
| New job (a direct job: migration, paper contract) writes a `contract` row through area 6's contract service with source 'Direct', no estimate revision and no lead; it needs the contract value, retainage, terms and the signed file (area 6 Q10: the signed copy is always required) | owner 2026-11-20 2:25 AM, Q2 A |
| A service job created from a case on a known job is numbered from it, `<job number>-S<two digits>` (AC0001-001-S01); other jobs take the customer's next number; the case keeps its CS- number and the link | owner 2026-11-20 2:25 AM, Q4 B |
| Every job has exactly one contract row. A service job's contract needs no signed file; its source is 'Service quote' (billable work over `service_quote_limit_cents`, default $1,000, through the estimate flow, accepted online or recorded by the rep), 'Case warranty' (Not billed, value $0, costs roll up to the original job's Warranty line) or 'Case T&M' (billable repairs under the limit at company rates frozen onto the contract, optional not-to-exceed). **Withdrawn 2026-11-20 (owner 3:15 AM)**: the three sources, the limit and "no signed file"; kept: one contract row per job, warranty work Not billed with value $0 and the Warranty roll-up | owner 2026-11-20 2:45 AM |
| Every service job starts from a signed quote (billable, warranty or no charge, T&M): a service quote is an estimate in the estimate flow with service terms; the rep prints it to PDF, the customer signs, and the rep uploads the signed PDF with Mark signed (signer name, the real signed date entered on upload, never the creation date). `contract.source` is only 'Estimate' (project or service quote) or 'Direct'; every contract starts as Signed. A quote started from a case links to the case and the customer and makes no lead. No quote limit | owner 2026-11-20 3:15 AM (replaces the 2:45 AM sources) |
| A case raised on a service job is numbered from the original (root) job (AC0001-001-S03, never -S01-S01); after S99 the number widens (S100) | owner 2026-11-20 2:45 AM (planning, accepted) |
| Billing method: fixed price, pay applications, milestones, T&M or not billed | S 11-14 2:45 PM; C62 section 3 |
| Job number from the customer code, never typed; assigned in the create transaction | A 11-14; C62; design_decisions "Customer codes" |
| Fields: job name, service type, PM (required), sold by, start and target finish, job site, site contact and phone, customer PO no., contract value, retainage %, terms, optional accepted estimate (locked on create) | A 11-14; C62 sections 1-3 |
| A draft job takes no costs and no invoices. Superseded by Q1 (owner 2026-11-20 2:25 AM): there are no draft jobs | A 11-14; C62 ("A draft job can't take costs or invoices"); Q1 |
| T&M jobs default bill lines to Billable with the job's markup | A 11-14; C62 section 3 |
| Another open job on the same site shows a note, never a block | C62 section 2 |
| A job gets a "Prevailing wage" flag now; certified payroll (WH-347) in v1.1 | S 11-14 4:10 PM (payroll, area 19) |
| The job page starts a CO, PO, bill, pay app or invoice, pull ticket or budget transfer prefilled with the job; Documents tab | S 11-14 4:30 PM |
| Jobs list shows PM, project stage (days vs target), forecast margin and an Action column; no summary row hides jobs | S 11-14 4:30 PM |
| No permission: "You can't create jobs. Ask an Admin." (`project.manage` in C62; `project.create` in the registry) | C62; `permissions.py` |
| `project.sales_rep_user_id`, copied from the lead at signing, editable afterwards with history (the audit log's before and after; no new table); `contract.sales_rep_user_id` keeps the rep at signing | S 11-19 11:20 PM; area 15 section 6 |
| Status columns: `project.status` dropped; Open, Complete and Closed derive from the stage and outcome; `on_hold` with insert-only history | area 8 Q6 C |
| Every change is audit-logged | C62; AX4 |

Amendment 2026-11-22 (owner_decisions_2026-11-22 item 25 and OD-03; R21 Jobs launcher): like Bills and Invoices,
clicking a Jobs row opens the 480 px drawer. The row menu keeps View (full page), and the drawer has Open full page.
Screen behaviour only: no schema or permission effect; the drawer reads the same job service as the full page.

### 1.3 Proposed schema

**`project`** (the full DDL; columns from other areas marked with their area):

| Column | Type and rule | From |
|--------|---------------|------|
| `project_id` | INTEGER PRIMARY KEY | kept |
| `project_number` | TEXT NOT NULL UNIQUE; `customer_code` + '-' + three-digit `project_seq` (AC0001-001), or, for a service job numbered from a known job (Q4 B), the root job's `project_number` + '-S' + `service_seq` padded to at least two digits (AC0001-001-S01 to -S99, then -S100; 2:45 AM); written by the service | kept; design_decisions; Q4 B; 2:45 AM |
| `project_seq` | INTEGER NULL CHECK (>= 1); UNIQUE (`contact_id`, `project_seq`); NULL exactly when `numbered_from_job_id` is set (CHECK) | new |
| `numbered_from_job_id`, `service_seq` | INTEGER NULL FK project (always the root job: when the case's job is itself a service job, its `numbered_from_job_id`; 2:45 AM); INTEGER NULL CHECK (>= 1; no upper limit, 2:45 AM); both set or both NULL (CHECK); UNIQUE (`numbered_from_job_id`, `service_seq`); set only by `create_service_job` when the case has a job (Q4 B; 3:15 AM: set by `create_from_signing` when the signed quote has a case with a job) | new |
| `name` | TEXT NOT NULL CHECK (length 1-200) | kept |
| `contact_id` | INTEGER NOT NULL FK contact (must be a customer; service) | kept |
| `service_type_id`, `service_stage_id` | kept (RP4); `service_type_id` NOT NULL for new jobs (service) | kept |
| `assigned_pm_id` | INTEGER NOT NULL (master user id, no FK) | kept |
| `sales_rep_user_id` | INTEGER NULL (master user id, no FK) | area 15 |
| `source_revision_id` | INTEGER NULL FK `estimate_revision` (area 6); replaces `source_estimate_id` | area 6 |
| `source_case_id` | INTEGER NULL; FK `service_case` and index added by area 15 | areas 8, 15 |
| `billing_method` | TEXT NOT NULL CHECK IN ('Progress billing', 'Milestones', 'Fixed price', 'Time and materials', 'Not billed') (Q3 A: area 6's schedule types plus Not billed, jobs only; Progress billing shows as "Pay applications" on job screens; signing copies the schedule type) | new |
| `customer_po` | TEXT NULL CHECK (length <= 60) | new |
| `is_prevailing_wage` | INTEGER NOT NULL DEFAULT 0 CHECK (0, 1) | new (area 19 reads it) |
| `poc_method` | TEXT NOT NULL DEFAULT 'Cost to cost' CHECK IN ('Cost to cost', 'Manual percent', 'Completed contract') | D3 |
| `manual_pct_complete`, `manual_pct_reason`, `manual_pct_by`, `manual_pct_at` | as area 8 section 3.1 | areas 8, 13 |
| `billing_type`, `warranty_for_job_id` | as area 8 section 3.1 | area 8 |
| `site_street`, `site_city`, `site_state`, `site_zip`, `target_start_on`, `target_finish_on` | as area 8 section 3.1 (Q9 A there) **(Amendment 2026-11-23: `target_start_on` NOT NULL **(start no longer required: Withdrawn 2026-11-24, Area 8 §12.16)**, `target_finish_on` dropped, `requested_completion_on` added; §14; "dropped" and `requested_completion_on` Withdrawn 2026-11-23 (owner 8:30 PM): `target_finish_on` stays editable with history, `estimated_completion_on` added, §14)** | area 8 |
| `site_contact_name`, `site_contact_phone` | TEXT NULL | C62 section 2 |
| `close_outcome`, `cancel_reason_id`, `cancel_reason_label`, `cancel_note`, `cancelled_at_stage_id`, `completed_on`, `closed_on`, `closed_at` | as area 8 section 2.3 and its amendment | area 8 |
| `on_hold` | INTEGER NOT NULL DEFAULT 0 CHECK (0, 1) | area 8 |
| `budget_locked_at`, `budget_locked_by` | TEXT NULL (UTC), INTEGER NULL; both set or both NULL (CHECK) | new (section 2) |
| `created_at`, `created_by`, `updated_at`, `updated_by` | TEXT NOT NULL (UTC from `context.now`), INTEGER | new (persona audit item 2) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 | rule g4 |

Dropped: `status` (area 8 Q6 C), `source_estimate_id` (area 6), `original_budget_cents` and `revised_budget_cents`
(Q5 A: derived from `project_budget`).

Amendment 2026-11-20 (owner 2:10 PM, service quote rules): the job stores the cost enterer and the PM separately
(`cost_enterer_user_id` INTEGER and `assigned_pm_id`). Both copy from the estimate; when the company has one Solo
user or controls are not set up, the PM defaults to the cost enterer. `billing_method` (billing kind: fixed price,
progress billing, milestones, time and materials, or not billed) is separate from `cost_destination` TEXT NOT NULL
CHECK IN ('Job', 'Warranty line', 'Service overhead'); CHECK constraints enforce valid combinations. Billable
methods use 'Job'; 'Warranty line' requires not billed and an original job; not billed without an original job uses
'Service overhead'. `warranty_for_job_id` is required for 'Warranty line' and NULL for 'Service overhead'. Warranty
costs go to the original job's Warranty line. Not billed work without an original job is `No charge (goodwill)`. Its Service overhead classification resolves the GL account through the configurable `service_goodwill` System account role.

Amendment 2026-11-20 (service-quote decision reconciliation): CHECK-valid pairs are billable `billing_method` values
with `cost_destination = 'Job'`; `billing_method = 'Not billed'` with `cost_destination = 'Warranty line'` only when
`warranty_for_job_id` names the original job; and `Not billed` with `cost_destination = 'Service overhead'` only when
there is no original job (goodwill). Warranty costs roll up to that original job's Warranty line; goodwill costs use
the company-mapped System account role `service_goodwill` (area 18), without hard-coding an account. The job stores
the estimate's separate cost-enterer and PM fields; Solo or unset separation controls default the PM to the cost
enterer.

Withdrawn 2026-11-20 (service-quote decision reconciliation): the older proposed `billing_type` and Warranty-only
classification in the project column table above is superseded by the `billing_method`/`cost_destination` pair and
CHECK-valid combinations above. `warranty_for_job_id` remains the original-job reference required for the
Warranty-line destination; area 8 retains the warranty-invoice refusal while consuming these area 7 fields.

Contract value, retainage %, terms, T&M markup and not-to-exceed for a direct job are not `project` columns: they
live on the contract record (Q2 A), so pay apps and invoices read one place for every job. Dropped by Q1: `is_draft`,
`activated_at`, `activated_by`.

**`project_number_seq`** (new): `contact_id` INTEGER PRIMARY KEY FK contact, `last_seq` INTEGER NOT NULL DEFAULT 0;
the sequence pattern (`sequences.py`), bumped inside the job's write transaction. Hosted: one row lock per customer.

**`project_service_seq`** (new; Q4 B): `project_id` INTEGER PRIMARY KEY FK project (the root job, 2:45 AM),
`last_seq` INTEGER NOT NULL DEFAULT 0; bumped in the service job's write transaction like `project_number_seq`.

**Job service (`jobs.py`)**:
- `create_job(context, input, row_version=None)` (New job, a direct job: migration or paper contract):
  `authorize(context, 'project.create')`; validate before writing that the selected customer exists and is active,
  the required PM is active and has access to the company and `project.view` (R25), and a contract amount, retainage,
  terms and the signed file are supplied (Q2 A; area 6 Q10). A contract amount of $0 is valid for warranty,
  goodwill or internal jobs; a negative amount is refused (owner, shared_decisions 2026-11-21 4:25 AM). Validate
  supplied `target_start_on` and `target_finish_on` as real calendar dates (for example, refuse 2026-02-31); refuse
  a finish earlier than the start, while allowing equal dates. These amount and date checks are always-on integrity
  rules and apply with controls OFF. Raise a field-specific error before job number allocation for each refusal.
  In one write transaction, assign the next customer job number, create the project and its Direct contract through
  area 6's contract service (no estimate revision and no lead), and, when supplied, save and lock the original
  budget through section 2's service. If any later step fails, roll back every write, including the project,
  contract, budget rows and sequence update. No "Save draft" (Q1).
- `update_job` (`project.manage`, project scope; R29 lookups stay read-only; `row_version`), `set_sales_rep` (logged,
  `project.manage`).
- `jobs.create_from_signing(context, ...)`: called by area 6's `contracts.mark_signed` in its transaction (area 6
  section 9.3 step 3).
- **Withdrawn 2026-11-20 (owner 3:15 AM)** (no direct case jobs; the numbering below is kept and moves to
  `create_from_signing`): `jobs.create_service_job(context, case_id, billing_type)`: called by area 15 ("Create service job"). When the case
  has a job (`service_case.project_id`), the number is the root job's number + '-S' + the next `service_seq`
  (AC0001-001-S01; a case on AC0001-001-S01 gives AC0001-001-S03 when S02 exists; S100 after S99; 2:45 AM); otherwise
  the customer's next number (Q4 B). The case keeps its CS- number and the link (`source_case_id`). In the same
  transaction it writes the job's one contract row through area 6's contract service (owner 2:45 AM), with no signed
  file:
  - 'Case warranty': `billing_type` 'Warranty', `billing_method` 'Not billed', contract value 0; costs roll up to the
    original job's Warranty line (Q16, Q17 A).
  - 'Case T&M': `billing_method` 'Time and materials'; the company rate card frozen onto the contract
    (`contract_rate_line`, area 6 section 6); optional `not_to_exceed_cents`.
- **Withdrawn 2026-11-20 (owner 3:15 AM)**: Service quote (owner 2:45 AM): billable service work over `company_settings.service_quote_limit_cents` does not
  create a job from the case; it starts the estimate flow (area 6, with service terms), and the job is created when
  the quote is accepted (online, or recorded by the rep), by `jobs.create_from_signing` with contract source 'Service
  quote'; `billing_method` copies the quote's schedule type (Fixed price or Time and materials).

Amendment 2026-11-20 (owner 3:15 AM, from area 7; replaces the 2:45 AM sources): every service job starts from a
signed quote (billable, warranty or no charge, T&M). "Create service job" on a case starts a service quote: an
estimate with `case_id` and the case's customer and no lead (area 6), run through the same estimate flow with service
terms; there is no quote limit and no job is created from the case directly. The job is created at Mark signed by
`jobs.create_from_signing`, the same action as projects (signed PDF, signer name, the real signed date), with the
contract source 'Estimate'. For a quote with a case: `source_case_id` is the case; when the case has a job, the number
is the root job's number + '-S' + the next `service_seq` (S100 after S99) and otherwise the customer's next number;
a Not billed quote may have contract value 0. Store billing method separately from cost destination. Warranty
requires `warranty_for_job_id` to name the original job and uses 'Warranty line' to roll costs up to that job.
No charge (goodwill) has no original job, uses 'Service overhead' and resolves costs through the company's
`service_goodwill` System account mapping (§4.3 and area 18 §4.2). A T&M quote's company rates and optional
`not_to_exceed_cents` are frozen onto the contract as for projects;
otherwise `billing_method` copies the quote's schedule type.
- No draft rule (Q1): no service checks a draft job, since none exists.
- The "same site" note and the Jobs list figures (days vs target, forecast margin) are reads, not columns.

Amendment 2026-11-21 (shared_decisions 2026-11-21 4:25 AM "new job amount and date checks", owner confirmed):
`create_job` above is rewritten in place: a $0 contract amount is valid, a negative one is refused, impossible dates
and a finish before the start are refused, all as always-on checks before a job number is allocated, with full
rollback.

### 1.4 How it lands in the baselines

`001_company.sql`: the `project` table rebuilt in the baseline (no released file yet, CLAUDE.md section 5.1), its
audit triggers rewritten for the new column list, `project_number_seq`, `project_service_seq` (Q4 B), the indexes (`contact_id`, `assigned_pm_id`,
`sales_rep_user_id`, `service_stage_id`, `warranty_for_job_id`). Master: the codes of section 9.

### 1.5 Effect on existing services and tests

- `ledger.py`: section 2's budget control beside `_check_cost_codes` (no draft-job check, Q1).
- `custom_fields.py:55` (Project read and write codes) unchanged.
- Tests that insert jobs (`authz_world.py:137`, `test_ledger_rules.py:250`, `test_roles_schema.py:53`) add the new
  NOT NULL columns (`project_seq`, `billing_method`, `created_at`); `test_schema_replan.py` gains the new checks.

### 1.6 Tests to write later

- `test_direct_job_validates_customer_pm_and_required_contract_inputs`: inactive or missing customer, inactive or
  unauthorized PM, and each missing Q2 A contract requirement (value, retainage, terms, signed file) are refused
  with a field-specific explanation before any project, contract or sequence write; a user without
  `project.create` is refused before the write transaction.
- `test_direct_job_rejects_negative_contract_amount_with_controls_off`: refuse a negative amount with a
  field-specific error before number allocation; verify no job, Direct contract or budget rows and no sequence
  change, even with controls OFF.
- `test_direct_job_accepts_zero_contract_amount_with_controls_off`: save a $0 contract amount and create the job
  and Direct contract successfully with controls OFF.
- `test_direct_job_rejects_impossible_target_date_with_controls_off`: refuse an impossible date such as
  `2026-02-31` with a field-specific error before number allocation; verify no job, Direct contract or budget rows
  and no sequence change, even with controls OFF.
- `test_direct_job_rejects_finish_before_start_with_controls_off`: refuse a finish date earlier than the start
  with a field-specific error before number allocation; verify no job, Direct contract or budget rows and no
  sequence change, even with controls OFF.
- `test_direct_job_accepts_finish_equal_to_start_with_controls_off`: accept equal valid start and finish dates
  with controls OFF.
- `test_direct_job_assigns_distinct_saved_numbers_and_ignores_typed_number`: two successfully saved jobs for one
  customer receive its code plus -001 and -002, regardless of a typed number.
- `test_direct_job_failure_rolls_back_project_contract_budget_and_sequence`: force failure after number allocation
  and during contract or supplied-budget creation; verify no project, Direct contract or partial budget rows remain
  and the customer's next sequence is unchanged.
- (Q2 A) a created direct job has one `contract` row with source 'Direct', no revision and no lead; contract value,
  retainage, terms and signed file are required.
- (Q4 B) a service job from a case on AC0001-001 is AC0001-001-S01, the next is -S02; a service job from a case with
  no job takes the customer's next number; the case keeps its CS- number.
- (2:45 AM) a case on AC0001-001-S01 numbers from AC0001-001 (the next free -S, never -S01-S01); after -S99 the next
  is -S100.
- **Withdrawn 2026-11-20 (owner 3:15 AM)**: (2:45 AM) every job has exactly one contract row; a Case warranty job's contract is Not billed with value 0 and no
  signed file; a Case T&M job's contract holds the company rates as of creation (a later rate card change leaves it
  unchanged) and an optional not-to-exceed.
- (3:15 AM) a case has no "create job" path: Create service job starts a quote with `case_id` and no lead; Mark
  signed on it without the signed PDF, the signer name or the signed date is refused; signing creates the service job
  numbered from the root job, with `source_case_id`. A zero-value Warranty quote requires an original job and rolls
  costs up to its Warranty line. A zero-value goodwill quote without an original job uses Service overhead and the
  configured `service_goodwill` account. A T&M quote keeps the company rates at signing and the optional not-to-exceed.
- (Q2 A) New job without the signed file, contract value, retainage or terms is refused; a created direct job has one
  `contract` row with source 'Direct', no revision and no lead.
- `create_job` without `project.create` is refused before the write transaction (rule 10).
- `status` is gone; the derived state reads from the stage and outcome (area 8 tests).
- A sales rep change writes one audit row with before and after; `contract.sales_rep_user_id` is unchanged.

Amendment 2026-11-21 (shared_decisions 2026-11-21 4:25 AM "new job amount and date checks", owner confirmed;
to_planning 2026-11-21 "Area 7 and 8 job identity and budget handoff"): the direct-job tests above are rewritten in
place as named tests for prerequisites, amount and date checks, numbering and rollback.

---

## 2. Job cost budget (`project_budget`)

### 2.1 Current state

- `project_budget` (`001_company.sql:282-293`): `project_id` NULL FK, `cost_code_id` NULL FK, `estimate_line_id` FK
  `estimate_line`, `co_line_id` FK `change_order_line`, `budget_cents` INTEGER NOT NULL. No kind, who, when, reason,
  lock or revision link. Audited per area 18 section 1.2 (listed). Test: `test_ledger_rules.py:70-99`.
- `project.original_budget_cents` and `revised_budget_cents` (`:266-270`) are cached totals no service writes.
- Area 8 (approved): change order approval writes one budget row per CO line "through area 7's budget service"
  (section 5.3); a budget transfer is two `project_budget` rows with `revision_id` (Q18 A); the forecast revision
  figures read original, CO and revised from `project_budget` (section 6.3). Area 6: Mark signed writes one row per
  cost code of the summary (section 9.3 step 4). Area 17: the `job_budget` compare reads `project_budget`.

### 2.2 Decided

| Decision | Source |
|----------|--------|
| Company setting "Who can enter a job's cost budget": anyone who can edit the job (default) · the job's PM · Accounting · PM or Accounting; enforced in the service; changes audit-logged | S 11-14 2:50 PM; A 11-14 "job budget entry rights" |
| Control "Require a budget before costs post", OFF by default; ON: a cost posting to a job with no locked budget raises a typed error naming the job | S 11-14 2:50 PM; A 11-14 |
| The original budget locks at create, or at the first save by an allowed person; later changes only through change orders and logged transfers | S 11-14 2:45 PM; A 11-14 (both messages) |
| Budget transfers between cost codes never need approval: a reason plus the log; no control | S 11-14 4:30 PM; A 11-14 "Jobs decisions" |
| Only Project manager, Controller, Admin and Master update a forecast or transfer budget; codes `job.forecast.edit`, `job.budget.transfer` (in area 18) | S 11-19 2:20 PM; area 8 section 6.2 |
| A user who cannot enter the budget still creates the job; the budget waits for the allowed person ("No budget yet", "Enter budget") | C62 section 4 |
| Budgets at any level of the cost code tree; a code with sub-codes budgets their sum | A 11-15 3:52 PM item 2; C111 |
| The estimate's summary by cost code becomes the job budget at signing | S 11-19 9:28 PM item 1; S 11-19 11:20 PM |
| "Budget" means only a job's cost budget (by job and cost code); the company plan is never called a budget | S 11-18 3:16 PM |

Amendment 2026-11-22 (owner_decisions_2026-11-22 item 26 and OD-02; Forecast Item 7, JOB-06 and the JOB-05 budget
transfer branch): wait for the canonical Stages 5–6 forecast and budget APIs and permissions. There is no temporary
adapter. The `job.forecast.edit` and budget transfer codes above stay as approved; the forecast and transfer
retests run against those canonical APIs once they exist. No schema change.

### 2.3 Proposed schema

**`project_budget`** (rebuilt; insert-only by design, Q8):

| Column | Type and rule |
|--------|---------------|
| `budget_id` | INTEGER PRIMARY KEY |
| `project_id` | INTEGER NOT NULL FK project |
| `cost_code_id` | INTEGER NOT NULL FK cost_code (not a division; Q6 and Q7 for the level rule) |
| `kind` | TEXT NOT NULL CHECK IN ('Original', 'Change order', 'Transfer') |
| `budget_cents` | INTEGER NOT NULL CHECK (typeof integer); negative allowed only for 'Change order' (a deduct CO) and 'Transfer' (the "from" row) (CHECK) |
| `source_revision_id` | INTEGER NULL FK `estimate_revision` (Original rows from an estimate; replaces `estimate_line_id`) |
| `co_line_id` | INTEGER NULL FK `change_order_line`; CHECK (`kind` = 'Change order') = (`co_line_id` IS NOT NULL) |
| `revision_id` | INTEGER NULL FK `job_forecast_revision` (area 8 Q18); CHECK (`kind` = 'Transfer') = (`revision_id` IS NOT NULL) |
| `reason` | TEXT NULL CHECK (length <= 1000); required for 'Transfer' (service) |
| `entered_by`, `entered_at` | INTEGER NOT NULL, TEXT NOT NULL (UTC) |

Indexes: (`project_id`, `cost_code_id`), (`co_line_id`), (`revision_id`). Dropped: `estimate_line_id` (budget rows
sum required and Accepted estimate lines by cost code, per area 6 §9.3).

Figures (reads, never stored; Q5 A): original = SUM of 'Original'; approved CO = SUM of 'Change order'; revised =
SUM of all kinds; per code and rolled up the tree (a parent shows the sum of its branch).

**Company settings** (`company_settings`, area 21 adds the row's `row_version`):
- `job_budget_entry` TEXT NOT NULL DEFAULT 'Job editors' CHECK IN ('Job editors', 'Job PM', 'Budget code',
  'PM or budget code') (Q9 A: "Accounting" becomes the holders of `job.budget.enter`, L7 codes, never role names).
- `require_budget_before_costs` INTEGER NOT NULL DEFAULT 0 CHECK (0, 1) (control, OFF).
Both changed by `company.settings` with a reason, audit-logged, listed on the Controls page, high-impact (R36,
area 18 section 4 amendment G9).

**Budget service (`job_budgets.py`)**:
- `set_original(context, project_id, lines, row_version)`: allowed by `job_budget_entry` (Job editors: `project.manage`
  with project scope; Job PM: `context.user_id` = `assigned_pm_id`; Budget code: `job.budget.enter`; PM or budget
  code: either); refused once `budget_locked_at` is set ("The original budget is locked. Use a change order or a
  budget transfer."); writes the 'Original' rows and sets `budget_locked_at`/`by` in one transaction; seeds area 8's
  `job_forecast_line` (ETC = budget per code, area 8 section 6.3).
- `set_original_from_signing(context, project_id, revision_id, summary_lines)`: called by area 6 in the Mark signed
  transaction; the signer's `contract.sign` stands in for the entry right (the estimate was priced and approved under
  area 6's rules).
- `add_change_order_rows(context, change_order_id, lines)`: called only by area 8's approval service.
- `add_transfer_rows(context, project_id, from_code, to_code, amount_cents, reason, revision_id)`: called only by area
  8's `transferBudget` (which authorizes `job.budget.transfer` and writes the revision first); never approval; the
  job total is unchanged; amount > 0; the "from" code may go negative only with a warning (rule 0).
- `require_budget_before_costs` ON: the ledger check (beside `_check_cost_codes`) refuses a cost line (an expense-type
  account in the Cost of sales subtype, or any line with a cost code) for a job with no `budget_locked_at`, naming the
  job. OFF: nothing is checked.

### 2.4 How it lands in the baselines

`001_company.sql`: `project_budget` rebuilt with its audit triggers; Q8 A adds `project_budget_no_update` and
`project_budget_no_delete` (integrity backstop: a budget row is never changed; corrections are new rows), the same kind
of lock as area 8's approved CO lines (area 8 Q17); the two `company_settings` columns.

### 2.5 Effect on existing services and tests

- `test_ledger_rules.py:70-99` (`estimate_line_id` on `project_budget`) is rewritten for `source_revision_id` and
  the new NOT NULL columns.
- `ledger.py` gains the control check; tests for posting with the control OFF stay unchanged.

### 2.6 Tests to write later

- Each `job_budget_entry` choice: the allowed user saves, the others are refused with the sentence; a user who
  cannot still creates the job.
- The second `set_original` is refused; a transfer and a CO row land; revised = original + CO + transfers; the job
  total is unchanged by a transfer.
- With Q8 A, UPDATE and DELETE of a budget row are refused by the trigger.
- The control OFF: a cost posts to a job with no budget; ON: the same posting is refused naming the job, and a job
  with a locked budget posts.
- The figures equal area 8's revision lines for the same job (one table, Q18 A).

---

## 3. Cost codes and cost types

### 3.1 Current state

- `cost_code` (`001_company.sql:30-48`): `code` TEXT UNIQUE, `name`, `cost_type_label` TEXT NOT NULL (free text,
  e.g. "Cement"), `account_id` INTEGER (no FK; "parent GL account cross-reference"), `parent_id`, `level` 1-3,
  `is_active`; CHECK (level 1) = (no parent). Triggers `cost_code_parent_level_insert`/`_update` (`:3922-3935`):
  a parent is one level up, a code with children cannot change level. Audited (`:4576-4626`).
- `ledger._check_cost_codes` (`ledger.py:176-190`, RP5): a line posts only to an active leaf code (not a division,
  not a code with active sub-codes).
- No `cost_type` table, no "counts toward % complete", no sort order, no who/when, no row version; `code` can be
  updated. Tests: `test_schema_replan.py:466-490` (levels), `test_ledger_clearing.py:113`,
  `test_ledger_rounding.py:523-526`, `test_ledger_rules.py:73` (all use `cost_type_label`).
- No shipped cost code list exists (`templates/` holds `coa/` only).

### 3.2 Decided

| Decision | Source |
|----------|--------|
| Three levels, Division → Code → Sub-code (16 → 16-100 → 16-100.10) | A 11-15 3:52 PM item 2; RP5; C111 |
| Sub-codes inherit cost type, default account and "counts toward % complete", each overridable | A 11-15 3:52 PM item 2; C111 |
| Postings go to active leaf codes (Divisions not postable) | RP5 (service check, built) |
| Codes are suggested from the parent, editable before the first save, then fixed; never reused (a used code is refused) | C111 |
| Moving a code to another parent keeps its level, is logged and re-rolls reports | C111 |
| A parent can't be made inactive while it has active children; making inactive asks a reason | C111 (dimensions and codes share the rule) |
| Bulk creation from a pasted indented list goes through the Import service (all or nothing, logged) | A 11-15 3:52 PM item 3 |
| Reports roll up any level; "show levels" is a report option | A 11-15 3:52 PM item 4 |
| `cost_type` is a company list, five shipped (Labor, Material, Equipment, Subcontract, Other); companies add their own; every cost code has one; a used type cannot be deleted | S 11-19 9:28 PM item 2; S 11-19 11:20 PM; area 6 section 3.2 |
| Pricing templates hold a markup per cost type (area 6); the estimate's summary shows cost type by cost code | S 11-19 11:20 PM |

### 3.3 Proposed schema

**`cost_type`** (new): `cost_type_id` PK, `name` TEXT NOT NULL UNIQUE (length 1-60), `is_shipped` 0/1, `is_active`
0/1 DEFAULT 1, `sort_order` INTEGER NOT NULL, `default_account_role` TEXT NULL (Q20 A), `created_at`, `created_by`,
`row_version`. Seeds: Labor, Material, Equipment, Subcontract, Other (`is_shipped = 1`). A used type is deactivated,
never deleted (FK RESTRICT from `cost_code`); a shipped type can be renamed and hidden, not deleted.

**`cost_code`** (changed):
- `cost_type_id` INTEGER NOT NULL FK `cost_type` (ON DELETE RESTRICT) replaces `cost_type_label`. The baseline is
  unreleased, so development databases are rebuilt (no data migration); an existing company's labels would map to
  types by name in a numbered migration only after release.
- `account_id` gets its FK (`REFERENCES account`, RESTRICT) and keeps its name; it is the code's default account,
  filled from the cost type's role at creation when empty (Q20 A).
- `counts_toward_pct` INTEGER NOT NULL DEFAULT 1 CHECK (0, 1).
- `sort_order` INTEGER NOT NULL DEFAULT 0; `created_at`, `created_by`, `updated_at`, `updated_by`; `row_version`.
- Trigger `cost_code_code_fixed` (integrity, H4 allows: a code is an identifier that postings and reports name):
  refuses any UPDATE OF `code`. Reuse is already refused by UNIQUE. A used code is never deleted (FK RESTRICT from
  `journal_line`, `project_budget`, `estimate_cost_line`, `change_order_line`); it is made inactive instead. A code
  that nothing references may be deleted, and its text stays taken only while the row exists.
- The service (`cost_codes.py`, `cost_code.manage`, Q14): create (code suggested, inherits the three fields from the
  parent), rename, move (same level; logged "Moved from 16 on 11/15"), deactivate (reason; refused while it has
  active children), paste a list (through the Import service, all or nothing).

Leaf rule for estimates and budgets: Q7.

### 3.4 How it lands in the baselines

`001_company.sql`: `cost_type` with seeds and audit triggers; `cost_code` rebuilt (new columns, FK, the fixed-code
trigger, updated audit triggers); the RP5 triggers kept.

### 3.5 Effect on existing services and tests

- `ledger._check_cost_codes` unchanged.
- Every test that inserts a cost code (listed in 3.1) passes `cost_type_id` instead of `cost_type_label`; a shared
  fixture helper avoids repeating it.

### 3.6 Tests to write later

- A sub-code created under a code copies its cost type, default account and `counts_toward_pct`; overriding one does
  not change the parent.
- UPDATE OF `code` is refused by the trigger; a second code with the same text is refused.
- Deactivating a parent with an active child is refused with the children named; a used cost type cannot be deleted.
- Move keeps the level; a move across levels is refused (RP5 trigger).
- A pasted list with one bad line imports nothing and returns the error list.

---

## 4. Default accounts for the General conditions and Warranty cost codes (owner inbox 2026-11-20 1:15 AM)

### 4.1 Current state

- The mockup (cost-codes.html) defaults 01-500 General conditions and Warranty to "6000 Overhead". In
  `templates/coa/construction.csv`, 6000 is "Operating Expenses", a header (`is_postable` 0, subtype Operating
  expense): it is neither postable nor a job cost.
- Job cost accounts in the chart (under 5000 Job Costs, subtype Cost of sales, none with a system role except 5055
  and 5096): 5010 Direct Field Labor; 5020 Field Payroll Taxes and Burden; 5030 Job Materials; 5040 Subcontractor
  Costs; 5050 Equipment Costs; 5060 Permits, Bonds and Job Insurance; 5070 Indirect Job Costs (Overhead); 5080
  Warranty Expense; 5090 Provision for Job Losses. Liabilities that could hold a reserve: 2330 Accrued Liabilities,
  2340 Accrued Job Losses (no warranty reserve account). Revenue: 4030 Service and Warranty Revenue.
- `company_settings.contract_cost_acct_id` (`:745`) exists, but no chart row carries a `contract_cost` role.
- Rule: code finds accounts by role, never by number (area 10 F11; area 13 section 2.3 amendment).

### 4.2 Decided

- A Warranty service job is Warranty / no charge (not invoiced); its costs are reported against the original job's
  warranty line (S 11-18 2:14 AM; see §1.3 for the current destination and original-job rules).
- Account numbers follow the repo construction chart (S 11-19 12:52 PM).
- Until the owner answers, the mockup leaves the default account blank for these two codes (inbox 1:15 AM).
  Answered 2026-11-20 2:25 AM (below).
- General conditions defaults to 5070 Indirect Job Costs (Overhead) (owner 2:25 AM, Q15 A).
- Warranty work is a service job ("works like a service job"): its costs post to the service job on the Warranty
  cost code, to the account with role `warranty_expense` (5080 Warranty Expense), in the open period; no reserve. Job
  cost reads add warranty service-job lines to the original job's Warranty line through the job link
  (`warranty_for_job_id`; Q17 A) (owner 2:25 AM, Q16).
- Accounts are found by role (owner 2:25 AM, Q20 A).

### 4.3 Proposed (by the answers, 2026-11-20 2:25 AM)

- Q15 A, Q16 (owner's wording), Q17 A and Q20 A settle this section.
- The chart template gains roles on 5070 (`job_overhead`) and 5080
  (`warranty_expense`); cost type Other's default role is `job_overhead`; the shipped cost code list (a new
  `templates/cost_codes/construction.csv`, read like the chart templates) names a role per code where it differs from
  its type's (Warranty → `warranty_expense`); `company_settings.warranty_cost_code_id` INTEGER NULL FK cost_code names
  the company's Warranty code for the roll-up.

Amendment 2026-11-20 (owner 2:20 PM, service quote rules): add the System account role `service_goodwill` for the
service overhead destination. Each company maps the role to an account (it may map to 5080 Warranty Expense); no
account number is hard-coded. Goodwill and Warranty remain distinct by `cost_destination`, regardless of whether
they map to the same account.

### 4.4 Tests to write later

- Applying the construction chart then the cost code list fills every code's `account_id` from roles; no code reads
  an account number; a chart without the role leaves the code's account empty and the setup lists it.
- (Q16, Q17 A) a warranty service job's cost posts to 5080 by role in the open period with no reserve entry, and
  appears on the original job's Warranty line in job cost and in Budget vs actual, and not again on the service job's
  own total in the roll-up.

---

## 5. Dimensions

### 5.1 Current state

- `dimension_type` (`001_company.sql:50-60`): `name` UNIQUE, `description`, `created_at` DATETIME DEFAULT
  CURRENT_TIMESTAMP. No which-lines rule, no Required setting, no active flag, no order, no row version.
- `dimension_value` (`:62-73`): `dimension_type_id` FK **ON DELETE CASCADE**, `code` TEXT UNIQUE (across all types),
  `name`, `parent_value_id` (ON DELETE SET NULL), `is_active`, `created_at`. Triggers
  `dimension_value_validate_insert`/`_update` (`:1356-1400`): same-type parent, no self-parent, no cycle, depth at
  most `MAX_DIMENSION_DEPTH` = 10 (`database.py:14`, RP3). `code` can be updated.
- `journal_line_dimension` (`:559`) and `invoice_line_dimension` (`:122`): one value per type per line, RESTRICT on
  the value; locked with their lines. Reversals copy dimensions verbatim (`ledger._copy_dimensions`, `ledger.py:1055`,
  R45, JD1).
- No `project_dimension` (the job's dimension settings); no shared resolver; `time_entry` and `staged_line` have no
  dimension table (roadmap Phase 4 notes, JD1).

### 5.2 Decided

| Decision | Source |
|----------|--------|
| Dimension values: parent link, depth unlimited (no cycles); moving a value with postings is allowed (report roll-up only), logged; never deleted; codes never change or get reused; a parent can't be inactive while it has active children | A 11-15 3:52 PM item 1; C111 |
| Required dimensions are a Company control, per dimension: never · from job · always; every change asks a reason and is logged | S 11-15 2:08 PM; A 11-15 1:45 PM; C94 |
| A dimension applies to chosen kinds of lines (revenue, expense, balance sheet) | C94 ("Which lines") |
| JD1: a line with a job takes the job's dimension values and can't edit them; other types stay editable; drafts follow the job; posted documents keep their values; no override; one shared service function for invoices, bills, journal lines and time entries | JD1 |
| R15: every GL impact card shows each line's job, cost code and each active dimension; "—" when empty; a missing required dimension shows a Check flag on the line and blocks posting with the reason; values filled from the job show "from job" | S 11-18 1:25 PM |
| One tree builder for dimensions and cost codes; pickers show the path; reports offer show levels | A 11-15 3:52 PM; C111 |
| No dimensions at setup; Class and Location offered in one click, plus custom dimensions | C5 (chart section) |
| The job type (service type) starts a job with profit and cost center values | C62 section 1 |

### 5.3 Proposed schema

**`dimension_type`** (changed): `applies_revenue`, `applies_expense`, `applies_balance_sheet` INTEGER NOT NULL
(0/1; defaults 1, 1, 0; CHECK at least one is 1); `required_mode` TEXT NOT NULL DEFAULT 'Never' CHECK IN ('Never',
'From job', 'Always') (Q10 A); `is_active` 0/1; `sort_order`; `created_at` TEXT (UTC), `created_by`; `row_version`.
`required_mode` changes need `company.settings` and a reason (a control: Controls page, R36 high-impact, logged).

**`dimension_value`** (changed): `dimension_type_id` FK becomes **ON DELETE RESTRICT** (a type with values is
deactivated, never deleted); `parent_value_id` ON DELETE RESTRICT; `sort_order`; `created_at` TEXT (UTC),
`created_by`, `updated_at`, `updated_by`; `row_version`. Trigger `dimension_value_code_fixed` refuses UPDATE OF
`code` (integrity, like the cost code). The depth check keeps RP3's limit of 10 levels and the refusal names the
limit (Q11 A). "Moved from Solar on 11/15" comes from the audit
log (no column).

**`project_dimension`** (new; JD1): `project_id` FK project, `dimension_type_id`, `dimension_value_id`, PRIMARY KEY
(`project_id`, `dimension_type_id`), FOREIGN KEY (`dimension_value_id`, `dimension_type_id`) REFERENCES
`dimension_value` (RESTRICT); `set_by`, `set_at`. Audited. Written by `jobs.set_dimensions` (`project.manage`,
project scope); filled at job creation from the service type's defaults (open item: area 8 amendment).

**One resolver (`dimensions.resolve_line(conn, account_id, project_id, given)`)**, used by every document service and
the posting preview: returns, per active dimension type that applies to the account's kind, the value (from the job
when the job sets that type, else the given value), a `from_job` flag and a `missing_required` flag. Posting refuses
a line with `missing_required` (one sentence naming the line and the dimension); saving a draft never refuses (drafts
may be incomplete). 'From job' requires the dimension only on lines with a job whose settings lack it; 'Always' on
every line of that kind. With every `required_mode` 'Never' (default) nothing is refused.

### 5.4 How it lands in the baselines

`001_company.sql`: the two tables rebuilt (new columns, RESTRICT, the fixed-code trigger, audit triggers per area 18
section 1.2); `project_dimension` with audit triggers. `database.py` is unchanged (Q11 A keeps the depth of 10).

### 5.5 Effect on existing services and tests

- `ledger.py` posting calls the resolver for the required check; `_copy_dimensions` (R45) unchanged (reversals keep
  the original values, never re-resolved).
- `test_schema_replan.py` dimension depth tests are unchanged (Q11 A).

### 5.6 Tests to write later

- Each `required_mode`: Never posts without a value; From job refuses only a job line whose job lacks the value;
  Always refuses any line of that kind without it; a balance-sheet line is not checked for a type that does not
  apply to balance sheet lines.
- A job line's value comes from `project_dimension`; a given value for a job-set type is ignored; clearing the job
  keeps the previous value as the starting point (JD1).
- Deleting a type with values is refused; UPDATE OF `code` refused; deactivating a parent with an active child
  refused; a move of a value with postings succeeds and writes one audit row.
- The posting preview returns the same flags the posting check uses.

---

## 6. Operating plan

### 6.1 Current state

Nothing in the baseline. J2 (2026-11-11) described `budget_version` (Draft/Approved/Locked) and `budget_line`; the
owner replaced it (F3). Area 17 already points `saved_report_compare.plan_version_id` at `operating_plan_version`
(area 17 section 4.3) and reads `operating_plan_line` directly (contracts section 4.6 item 6).

### 6.2 Decided

| Decision | Source |
|----------|--------|
| A company plan holds one amount per GL account per month, optionally by dimension; ships in v1.0; driver-based and rolling forecasts later | S 11-18 3:14 PM |
| Any number of named versions; no approved or default status; any version can be compared; a saved report or pack keeps its version | S 11-18 3:14 PM |
| Upload: template prefilled with accounts and 12 month columns (plus a column per active dimension, optional); preview with errors and totals; all-or-nothing with an error list; small changes in an on-screen grid; every import and edit logged | S 11-18 3:14 PM |
| Named "operating plan" in tables, services and screens; reports show "Plan" and "Variance vs plan"; "budget" means only a job's cost budget | S 11-18 3:16 PM |
| Version: name (unique), fiscal year, notes, who and when, archived (hidden from pickers, kept) | to_planning_done 11-18 "operating plans" item 1 |
| Lines: version, account, fiscal month, dimension values (blank = whole company), amount; unique on version + account + month + dimensions; stored in the ledger's sign (debit positive), shown in natural signs | item 2 |
| Imports: version, file name, rows, totals, who and when, result; unknown or inactive account, month outside the year, unknown dimension value or a duplicate key rejects the file | item 3 |
| Services: copy a version (optionally × %), export to the template, grid edits logged | item 4 |

### 6.3 Proposed schema

**`operating_plan_version`**: `plan_version_id` PK, `name` TEXT NOT NULL UNIQUE (length 1-100), `fiscal_year`
INTEGER NOT NULL (the company's fiscal year number), `notes` TEXT (<= 2000), `is_archived` 0/1, `copied_from_id`
INTEGER NULL FK self, `created_at`, `created_by`, `updated_at`, `updated_by`, `row_version`. Never deleted while a
saved report uses it (area 17 RESTRICT); otherwise deletable with a reason (logged).

**`operating_plan_line`**: `plan_line_id` PK, `plan_version_id` FK (ON DELETE CASCADE with its version),
`account_id` FK account (postable; the service checks active), `period_no` INTEGER NOT NULL CHECK (1-12) (Q13 A),
`dimension_set_id` INTEGER NULL (Q12 A: area 10's `dimension_set`; NULL = whole company), `amount_cents` INTEGER NOT
NULL (typeof integer; debit positive). Uniqueness: UNIQUE (`plan_version_id`, `account_id`, `period_no`,
`dimension_set_id`) WHERE `dimension_set_id` IS NOT NULL, and UNIQUE (`plan_version_id`, `account_id`, `period_no`)
WHERE `dimension_set_id` IS NULL (partial indexes; PostgreSQL has them, H5). `row_version` (grid edits).

**`operating_plan_import`** (insert-only): `import_id` PK, `plan_version_id` FK, `file_name`, `row_count`,
`totals_json` (per account type, natural signs), `result` CHECK IN ('Imported', 'Rejected'), `errors_json` (row,
column, reason; NULL when imported), `imported_by`, `imported_at`. The file itself is kept through `storage.py`
(H3) as an attachment of the import row (area 18). No-update and no-delete triggers (integrity: a record of what was
loaded).

**Service (`operating_plans.py`; `plan.manage` to change, `report.financial` to read)**: `create_version`,
`copy_version(source, name, factor_pct)` (rounding half up per line, rule 1), `import_template(version_id, file)`
(all-or-nothing inside one write transaction; a rejected file writes only its `operating_plan_import` row),
`export_template(version_id)`, `save_grid(version_id, changes, row_versions)`, `archive`, `delete`. No table, column
or service name contains "budget" (the inbox's "Done when").

### 6.4 How it lands, effects, tests

- Lands in `001_company.sql`: three tables, indexes, audit triggers, the import triggers. Area 17's FK from
  `saved_report_compare` lands in the same pass.
- Effects: none on existing services.
- Tests to write later: a file with one unknown account imports nothing and returns that row; a duplicate key is
  refused; a month 13 is refused; copy × 105% rounds per line; an archived version is not offered but its saved
  reports still run; a version used by a saved report cannot be deleted; signs round-trip (natural in the template,
  debit positive stored); no "budget" in the schema names (static test).

---

## 7. Job cost, Budget vs actual and the warranty roll-up (reads)

### 7.1 Current state and decided

- Job cost has no service. Area 10 decided job cost follows the GL entries that carry the job (a deferred line counts
  as recognized; S 11-19 1:21 AM). Area 8's forecast "committed" reads open PO lines and unbilled subcontract amounts
  through a function that returns 0 until areas 4 and 9 exist.
- C73: the job's Budget tab opens with "Budget vs actual": Budget (revised contract, revised cost budget) and Actual to
  date (billed to date, cost to date); Revenue, Cost, Gross margin, Margin %; amber under the budget margin, red when
  negative; actual margin uses billings, the forecast margin uses earned revenue.
- S 11-18 2:14 AM: a Warranty service job's costs are reported against the original job's warranty line.

### 7.2 Proposed (no tables)

- `job_cost.cost_to_date(conn, project_id, cost_code_id, as_of)`: SUM of posted `journal_line` debits minus credits
  on Cost of sales accounts carrying the job and code, through the period summary where it fits (area 10 section 4).
- `job_cost.budget_vs_actual(context, project_id)`: `project.view` (project scope) and `money.view` for the amounts
  (area 17 rule); revised contract from area 6's contract; billed to date from areas 4 and 5 (0 until built).
- Warranty roll-up (Q17 A): the reads add each Warranty job's cost lines to its `warranty_for_job_id` job under
  `company_settings.warranty_cost_code_id`, and show them once; the service job's own page still lists its lines.
- Area 17's job cost reports are financial layouts over the same reads (area 17 Q25 A); `src_jobs` offers the
  budget figures.

### 7.3 Tests to write later

- Cost to date equals the GL for the job and code, including a deferred line only as recognized.
- Budget vs actual without `money.view` returns no amounts.
- The warranty roll-up counts a warranty job's cost once, on the original job's Warranty line.

---

## 8. Percentage of completion and WIP

### 8.1 Current state

- `poc_snapshot` (`001_company.sql:697-720`): one row per job and period (UNIQUE), cost to date, excluded cost, ETC,
  revised contract, `pct_complete`, earned revenue to date and this period, billed to date, over/under billing,
  estimated gross profit, `entry_id` (the WIP entry). No method, who, when, or link to the forecast used. Audited per
  area 18 section 1.2 ("holds a person's estimate to complete").
- Roles exist for the WIP entry: `underbilled_acct_id`, `overbilled_acct_id`, `contract_revenue_acct_id`,
  `contract_cost_acct_id` (`:744-747`); chart rows 1200 (underbilled), 2300 (overbilled), 4010 (contract revenue),
  5090 and 2340 (job losses).
- Area 13 checks waiting on this: `wip_current` (the WIP entry later than every cost and ETC change) and
  `manual_pct_complete`; area 8's ETC lives in `job_forecast_line` with insert-only revisions.

### 8.2 Decided

| Decision | Source |
|----------|--------|
| `project.poc_method`: Cost to cost (default), Manual percent (reason required), Completed contract | D3 |
| Cumulative WIP entry at period end, auto-reversed on day 1 | D2 |
| Full expected loss accrued when estimated total cost exceeds the revised contract (Dr Provision for Job Losses / Cr Accrued Job Losses) | D1 |
| The WIP schedule shows every open job, grouped by service type | S 11-16 2:02 PM item 3 |
| A WIP entry older than the latest cost or estimate change fails the close check until recalculated | S 11-14 12:50 PM; area 13 section 2.2 |
| Cost codes carry "counts toward % complete" (excluded cost) | A 11-15 3:52 PM item 2 |

### 8.3 Proposed schema

- `project.poc_method` (section 1.3).
- `poc_snapshot` gains `poc_method` (the method used), `forecast_revision_id` INTEGER NULL FK
  `job_forecast_revision` (the last revision the ETC came from; NULL when the job has none), `computed_at` TEXT NOT
  NULL (UTC), `computed_by` INTEGER NOT NULL, `loss_provision_cents` INTEGER NOT NULL DEFAULT 0 (D1); recalculation
  replaces the open period's row in the WIP service's write transaction (the posted WIP entry is reversed and reposted
  through `ledger.py`, never edited); a closed period's row is never changed (area 13 locks).
- `wip_current` (area 13) compares `computed_at` with the latest posting carrying the job and the latest forecast
  revision.
- The WIP schedule is a Records source `src_wip` (area 17 amendment): every open job, grouped by service type, with
  the snapshot figures.
- The WIP service itself (`wip.py`) is a build item with the v1.1 construction work (Q18 A).

Amendment 2026-11-22 (tax on signed quotes; Area 5 Q12; flagged dependency): WIP contract value, earned revenue,
billed to date and over/under billing are pre-tax, and invoice tax is never part of billed to date. A direct job's
contract value is pre-tax. The original budget comes from estimate cost and is unchanged by Q12. Test:
`test_wip_over_under_billing_excludes_invoice_tax`.

### 8.4 Tests to write later

- Cost to cost excludes codes with `counts_toward_pct = 0`; manual percent needs a reason; completed contract
  recognizes nothing until Complete.
- A loss job books the full expected loss; the entry reverses on day 1.
- `wip_current` fails after a new cost or forecast revision and passes after a recalculation.

---

## 9. Permissions, controls and settings

### 9.1 Current state

Registry codes in use (`permissions.py`): `project.view`, `project.create`, `project.manage`, `report.job_cost`,
`account.manage`, `company.settings`; area 18 adds `job.forecast.edit`, `job.budget.transfer` (amendment from area
8). No code for cost codes, dimensions, the operating plan or budget entry.

### 9.2 Proposed codes (master registry; none sensitive; none in `AGENT_ALLOWED`)

| Code | Module | Use | Placement (area 18 amendment 2026-11-20, owner 2:25 AM) |
|------|--------|-----|------------------------------------------|
| `job.budget.enter` (Q9 A) | Projects | the "Budget code" choice of `job_budget_entry` | Accountant and Operations caps (the Operations cap so the Project manager template stays inside it); Accountant · Manager level; Controller and Project manager templates |
| `cost_code.manage` (Q14) | Lists | cost codes and cost types | Accountant and Operations caps; no level; Controller template; Admin and Master hold it; others by custom template or per-user Add |
| `dimension.manage` (Q14) | Lists | dimension types and values (not `required_mode`, which is `company.settings`) | Accountant cap; no level; Controller template; Admin and Master hold it; others by custom template or per-user Add |
| `plan.manage` | Reports | operating plan versions, imports and grid | Accountant cap; Accountant · Manager level; Controller template |

### 9.3 Controls and settings (all default OFF or permissive, audit-logged, on the Controls page, R36 high-impact)

| Setting | Default | Kind |
|---------|---------|------|
| `company_settings.job_budget_entry` | 'Job editors' | setting (who may enter) |
| `company_settings.require_budget_before_costs` | 0 | control |
| `dimension_type.required_mode` | 'Never' (Q10 A) | control, per dimension |
| `company_settings.warranty_cost_code_id` | NULL | setting (Q17 A) |
| `company_settings.service_quote_limit_cents` (Settings › Service; defined in area 15) | 100000 ($1,000) | setting (owner 2:45 AM). **Withdrawn 2026-11-20 (owner 3:15 AM)**: no quote limit |

---

## 10. Row version (rule g4) and audit in this area

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `project` | yes | yes |
| `project_budget` | insert-only (Q8 A) | no |
| `project_number_seq` | sequence | no |
| `cost_type`, `cost_code` | yes | yes |
| `dimension_type`, `dimension_value` | yes | yes |
| `project_dimension` | insert, update and delete by `jobs.set_dimensions` | no (the key names it; the job's `row_version` guards the save) |
| `operating_plan_version`, `operating_plan_line` | yes | yes |
| `operating_plan_import` | insert-only | no |
| `poc_snapshot` | replaced for an open period by the WIP service only | no (the job's lock and the period guard it) |
| `company_settings` (new columns) | yes | area 21 adds it to the row |

Every table above has audit triggers (area 18 section 1.2 already lists `project_budget`, `dimension_type`,
`dimension_value`, `poc_snapshot`; `cost_code` and `project` are audited today); reasons are required on: a budget
transfer, a dimension or cost code deactivation, a change to `required_mode`, `job_budget_entry` or
`require_budget_before_costs`, a manual percent complete, a plan version delete.

---

## 11. Conflicts with decisions (settled by the owner's answers, 2026-11-20 2:25 AM)

- **F1 Dimension depth.** S 11-15 3:52 PM: "unlimited depth (no cycles)". RP3 (2026-11-16): `MAX_DIMENSION_DEPTH`
  is 10 (`database.py:14`; the insert and update triggers check it). Q11. **Settled: Q11 A (nesting capped at 10
  levels).**
- **F2 Required dimensions.** C6 (chart section, 2026-11-11): required dimension per account, a control, off. JD1:
  "Require dimensions on lines without a job" is a future control, off. S 11-15 2:08 PM: per dimension, never / from
  job / always. C94's mockup default is "From job", while section 0 asks for a permissive default. The draft follows
  2:08 PM per dimension (the latest) and asks the default (Q10). **Settled: Q10 A (per dimension, default
  'Never').**
- **F3 Company plan model.** J2 (2026-11-11): `budget_version` with status Draft/Approved/Locked and `budget_line`;
  J3 rolling forecasts build on "the latest locked budget". S 11-18 3:14 and 3:16 PM: "operating plan", no approved
  or default status, never called a budget. The draft follows 11-18; J2's name and statuses and J3's "locked budget"
  wording need the owner's word that they are replaced. **Settled with Q12 A and Q13 A: the operating plan of 11-18
  stands (shared dimension sets, fiscal year + month 1-12, no statuses); J2's `budget_version` and J3's "locked
  budget" wording are replaced.**
- **F4 Forecast storage.** D10: `cost_forecast` append-only per job, cost code and **period**. Area 8 (approved):
  `job_forecast_line` (current ETC per code, no period) and insert-only revisions. Q19. **Settled: Q19 A (D10 is
  replaced by the job forecast per cost code).**
- **F5 Budget level.** A 11-15 3:52 PM item 2 and C111: "Budgets at any level; a parent with children sums them".
  RP5: postings go to active leaf codes. Area 6 asks whether estimate lines must use leaf codes. A parent row and
  child rows on one job would double count. Q6, Q7. **Settled: Q6 A (one level per branch per job) and Q7 A
  (estimate lines on lowest-level codes).**
- **F6 Posting level wording.** A 11-15 3:52 PM item 2: "postings go to the lowest level used on the line". RP5
  (later, built in `ledger.py:176`): a code with active sub-codes is refused. The draft keeps RP5. **Settled: RP5
  kept; Q7 A puts estimate lines on the same leaf codes.**
- **F7 Billing method names.** S 11-14 2:45 PM and C62: fixed price, pay applications, milestones, T&M, not billed.
  Area 6 (approved) schedule types: Progress billing, Milestones, Fixed price, Time and materials (no "Not billed"),
  and "the schedule type becomes the job's billing method at signing". Q3. **Settled: Q3 A (one list plus Not
  billed for jobs only).**
- **F8 Service job numbers.** design_decisions "Customer codes": "a service case's project_code is the parent job's
  project_code + '-S' + a 2-digit sequence". Area 15 (approved): cases are numbered `CS-0001` from
  `case_number_seq`; "Create service job" makes a job of type Service. The -S rule names neither. Q4. **Settled:
  Q4 B (a service job from a case on a known job is AC0001-001-S01; others take the customer's next number; the case
  keeps its CS- number).**
- **F9 Draft jobs.** A 11-14 and C62: a job can be saved as a draft (no costs or invoices). Area 8 Q6 C drops
  `project.status` and derives the state from the stage. A draft needs its own flag (Q1). **Settled: Q1 (owner's
  wording): no draft jobs; the unsigned lead is the draft; no flag.**
- **F10 Default accounts.** Inbox 1:15 AM: the mockup's "6000 Overhead" is a header in the Operating Expenses group
  of the construction chart (not postable, not a job cost). Q15, Q16. **Settled: Q15 A (5070) and Q16 (warranty
  work is a service job posting to 5080 by role).**
- **F11 Budget rights by role.** A 11-14: "Accounting roles (Controller, Accountant)". L7 and area 18: permissions are
  codes, never role names. Q9. **Settled: Q9 A (four choices mapped to codes; default Job editors).**
- **F12 Direct job contract value.** C62 and A 11-14: the New job screen takes contract value, retainage % and terms.
  Area 6 (approved): the `contract` row is written once at Mark signed from an estimate revision. A direct job has no
  revision. Q2. **Settled: Q2 A (a 'Direct' contract row through area 6's contract service, with the signed file).**

---

## 12. Questions for the owner: answers recorded (2026-11-20, 2:25 AM)

Owner 2026-11-20 2:25 AM: Q2, Q3, Q5-Q13, Q15 and Q17-Q20 A; Q4 B; Q1, Q14 and Q16 in the owner's wording. Each
answer is folded into the sections above.

**Q1. Draft jobs (F9).**
- A. `project.is_draft` (0/1): a draft has a number and appears in lists as Draft; every cost and invoice service
  refuses it; "Create job" activates it (logged).
- B. A "Draft" stage role before the first delivery stage, so the state derives from the stage like the rest.
- C. No drafts: Save draft keeps the form only on the page.
**Answer (owner's wording, replaces A, B and C):** no draft jobs. A job exists only from a signed contract; a lead
whose estimate isn't signed is the "draft". `project.is_draft` and every draft rule and test are dropped. Sections
1.2, 1.3, 1.5, 1.6, 2.3. Owner 2:45 AM: every job has exactly one contract row; service jobs need no signed file
(sources 'Service quote', 'Case warranty', 'Case T&M'; section 1.3). **Withdrawn 2026-11-20 (owner 3:15 AM)**: the
three sources and "no signed file". Owner 3:15 AM: every service job starts from a signed quote; `contract.source` is
'Estimate' or 'Direct'; every contract starts as Signed (section 1.3).

**Q2. Contract value on a direct job (F12).**
- A. "Create job" writes a `contract` row through area 6's contract service (no estimate revision; source 'Direct'),
  so pay apps, invoices and WIP read one contract for every job (area 6 amendment: `contract.source_revision_id`
  nullable).
- B. `project` columns (contract value, retainage %, terms) for direct jobs only; readers check two places.
**Answer: A.** New job (a direct job: migration, paper contract) writes a `contract` row through the contract service
with source 'Direct', no estimate revision and no lead; it needs the contract value, retainage, terms and the signed
file (area 6 Q10: the signed copy is always required). Area 6 amendment: the contract's revision link nullable and
`source` CHECK IN ('Estimate', 'Direct'). Sections 1.2, 1.3.

**Q3. Billing method values (F7).**
- A. One list for jobs and estimates: Progress billing (label "Pay applications" on job screens), Milestones, Fixed
  price, Time and materials, plus Not billed (jobs only); signing copies the schedule type.
- B. Two lists, mapped at signing.
**Answer: A.**

**Q4. Service job numbers (F8).**
- A. Every job, service jobs included, takes the customer's next number (AC0001-004); the case keeps its `CS-`
  number and the link; the -S rule in design_decisions is retired.
- B. A service job from a case on a known job takes that job's number + '-S' + two digits (AC0001-001-S01); others
  take the next number.
**Answer: B.** A service job created from a case on a known job is numbered from it, `<job number>-S<two digits>`
(AC0001-001-S01); other jobs take the customer's next number. The case keeps its CS- number and the link. Section
1.3 (`numbered_from_job_id`, `service_seq`, `project_service_seq`). Owner 2:45 AM: a case on a service job numbers
from the root job (AC0001-001-S03); after S99 the number widens (S100).

**Q5. Cached budget totals (area 8 F12).**
- A. Drop `original_budget_cents` and `revised_budget_cents`; every reader sums `project_budget` (indexed by job and
  code).
- B. Keep `revised_budget_cents`, updated in the same transaction as every budget row.
**Answer: A.**

**Q6. Budget level on one job (F5).**
- A. Rows on one level per branch per job: a code whose descendants have rows on that job can't take its own, and the
  reverse; a parent shows the sum of its branch.
- B. Rows at any level, and a parent's figure adds its own rows and its children's.
**Answer: A.**

**Q7. Estimate lines and leaf codes (area 6 section 3.4; F5).**
- A. Estimate cost lines use active leaf codes (as postings, RP5), so budgets from estimates land where costs post;
  hand-entered budgets follow Q6.
- B. Estimates may use any non-division code.
**Answer: A.**

**Q8. Budget rows are never changed.**
- A. Integrity triggers refuse UPDATE and DELETE on `project_budget` (corrections are new rows), as area 8 locks
  approved CO lines.
- B. A service rule only.
**Answer: A.**

**Q9. Who may enter a job's budget (F11).**
- A. The setting's four choices map to codes: Job editors (`project.manage` with project scope), Job PM (the job's
  `assigned_pm_id`), Budget code (new `job.budget.enter`, seeded per section 9.2), PM or budget code; default Job
  editors.
- B. Keep "Accounting" as the Accountant role.
**Answer: A.**

**Q10. Required dimensions default (F2).**
- A. 'Never' for every dimension (section 0: permissive by default).
- B. 'From job', as the mockup shows.
**Answer: A.**

**Q11. Dimension depth (F1).**
- A. Keep RP3's limit of 10 levels; the refusal names the limit.
- B. Unlimited: drop the depth check, keep the cycle check.
- C. Raise the limit (for example 20).
**Answer: A.**

**Q12. Plan lines and dimension combinations.**
- A. Plan lines use area 10's `dimension_set` through one shared get-or-create function (area 10 amendment: a second
  writer besides `ledger.py`), so reports join plan and actuals on the same set.
- B. Plan lines keep their own `operating_plan_line_dimension` rows; uniqueness is a service check.
**Answer: A.**

**Q13. Plan months.**
- A. `fiscal_year` plus `period_no` 1-12, so a plan can exist before its fiscal periods are created; adjustment
  periods 13 and 14 are not planned.
- B. A foreign key to `fiscal_period`; a plan only for years whose periods exist.
**Answer: A.**

**Q14. Who manages cost codes and dimensions.**
- A. Two codes, `cost_code.manage` and `dimension.manage` (section 9.2).
- B. One `lists.manage` for cost codes, cost types and dimensions.
- C. Reuse `account.manage`.
**Answer (owner's wording):** two codes, `cost_code.manage` and `dimension.manage`. Admin and Master hold them (they
hold every code); the shipped Controller template includes both; no role level gets them by default; others get them
by a custom template or a per-user Add. Area 18 amendment for placement. Section 9.2.

**Q15. Default account for General conditions (inbox 1:15 AM, a).**
- A. 5070 Indirect Job Costs (Overhead).
- B. 5060 Permits, Bonds and Job Insurance.
- C. A new account 5065 General Conditions under 5000 Job Costs.
**Answer: A.**

**Q16. How Warranty is accounted for (inbox 1:15 AM, b).**
- A. A job cost on the original job: the Warranty code defaults to 5080 Warranty Expense, and warranty work's cost
  shows on the original job's Warranty line (as S 11-18 2:14 AM).
- B. A reserve: at completion accrue Dr 5080 / Cr a new 2335 Warranty Reserve per job; later warranty costs post Dr
  2335, so the closed job's cost does not change.
- C. A period expense: 5080 with no job.
**Answer (owner's wording: "works like a service job"):** warranty work is a service job. Its costs post to the
service job on the Warranty cost code, to the account with role `warranty_expense` (5080 Warranty Expense), in the open
period; no reserve. Job cost reads add warranty service-job lines to the original job's Warranty line through the job
link (Q17 A). Sections 4.2-4.4, 7.2.

**Q17. Warranty roll-up mechanics (with Q16 A).**
- A. Warranty job lines keep the service job; job cost reads add them to the original job under the company's
  Warranty cost code (`warranty_cost_code_id`).
- B. Posting puts the original job and its Warranty code on the line directly, with the service job as a reference.
**Answer: A** (follows Q16).

**Q18. WIP scope in 2.9.**
- A. Schema now (`poc_method`, `counts_toward_pct`, the `poc_snapshot` additions); the WIP service designed and built
  with the v1.1 construction work.
- B. Design the WIP service fully in this area now.
**Answer: A.**

**Q19. D10 per-period cost forecast (F4).**
- A. D10 is replaced by area 8's `job_forecast_line` and revisions; no per-period forecast in v1 (J3 later).
- B. Keep D10 as a separate per-period table for J3.
**Answer: A.**

**Q20. How a shipped cost code finds its default account.**
- A. By role: each cost type has a default account role (Labor `job_labor` 5010, Material `job_materials` 5030,
  Subcontract `job_subcontract` 5040, Equipment `job_equipment` 5050, Other `job_overhead` 5070), the chart template
  gets those roles (and `warranty_expense` on 5080), and the shipped cost code list names a role only where it
  differs from its type.
- B. The shipped list names account numbers, resolved once against the company's chart when the list is applied.
**Answer: A.**

---

## 13. Open items (not decisions)

Amendments in approved areas (owner answers 2026-11-20 2:25 AM; the done ones carry "Amendment 2026-11-20 (owner
2:25 AM, from area 7)" lines there):
1. **Area 6: done** (sections 3.3, 9.3 and 10.2): Q2 A, the contract's revision link nullable and a 'Direct' source;
   the budget call is `job_budgets.set_original_from_signing`; the job call is `jobs.create_from_signing`; with Q7 A,
   estimate cost lines are refused on non-leaf codes.
2. **Area 8:** the `project` columns and the dropped `status` are confirmed: **done** (section 7). Still open:
   `service_type` default dimension values (C62 "starts with profit and cost center") as a `service_type_dimension`
   table, and a default `poc_method`; the transfer and CO services call section 2's functions; `job_forecast_line`
   seeding moves into `set_original`.
3. **Area 10: done** (section 4.3): with Q12 A, `dimension_set` gets a second writer (the plan service) through one
   shared function.
4. **Area 13: done** (section 2.3): `wip_current` reads `poc_snapshot.computed_at` (section 8.3; Q18 A);
   `manual_pct_complete` reads the `project.manual_*` columns placed here.
5. **Area 17: done** (section 14): `src_wip` (WIP schedule by service type); `src_jobs` fields (billing method, sales
   rep, budget figures; no draft, Q1); the plan compare reads `period_no` (Q13 A).
6. **Area 18: done** (sections 2.4.2 and 4.2): the four codes of section 9.2 with their caps, levels and templates
   (Q9 A, Q14); R36's high-impact list gains `job_budget_entry`, `require_budget_before_costs` and `required_mode`.
7. **Chart template (`templates/coa/construction.csv`):** the roles of Q20 A; the accounts are settled (Q15 A 5070,
   Q16 5080), the file changes in the baseline pass; no row carries `contract_cost` today although
   `company_settings.contract_cost_acct_id` exists.
8. **design_decisions "Customer codes": done**, no edit: Q4 B keeps the -S rule.

Raised by the answers (for the owner):
- **Q1 and service jobs: closed** (owner 2026-11-20 2:45 AM). Every service job has exactly one contract row with no
  signed file. `contract.source` adds 'Service quote', 'Case warranty' and 'Case T&M'. Schedule type per source:
  'Estimate' and 'Service quote' copy the revision's (a service quote: Fixed price or Time and materials); 'Direct'
  takes the New job's billing method (one of the four); 'Case T&M' is Time and materials; 'Case warranty' is 'Not
  billed' (added to `contract.schedule_type` for that source only). Amendment lines in areas 6, 15 and 18.
  **Withdrawn 2026-11-20 (owner 3:15 AM)**: the three sources and "no signed file". Still closed, by the 3:15 AM rule:
  every service job starts from a signed quote, `contract.source` is 'Estimate' or 'Direct', and every contract starts
  as Signed. Schedule type: 'Estimate' copies the revision's, which for a warranty or no-charge service quote is 'Not
  billed'; 'Direct' takes one of the four from New job. Amendment lines in areas 6, 15 and 18 ("owner 3:15 AM").
- **Q4 B edges: closed** (planning, accepted by the owner 2:45 AM): a case on a service job numbers from the root job
  (AC0001-001-S03, never -S01-S01); after S99 the number widens (S100).

New open items (owner 2:45 AM):
- **Online customer acceptance** of a service quote needs a customer link (connections; hosted later). Desktop v1
  records the approval by the rep (method, who, when, amount). **Withdrawn 2026-11-20 (owner 3:15 AM)**: no
  "accepted" quotes; every quote is signed and uploaded.
- **Service manager: closed (owner 3:35 AM)**: a new shipped Service manager access template (owner 3:15 AM), for
  roles Sales rep and Operations, scope All, with its codes in area 18 (section 2.4.2, the 3:35 AM line, and the
  2.4.3 row).
- **The service quote's lead: closed** (owner 3:15 AM): a quote started from a case links to the case and the customer
  and makes no lead; `estimate.case_id`, with a CHECK for exactly one of `lead_id` or `case_id` (area 6 amendment).
- **The limit check: closed** (owner 3:15 AM): the quote limit is dropped; every service quote runs the same estimate
  flow.
- **Contract status for service sources: closed** (owner 3:15 AM): every contract, project or service, starts as
  Signed, with the real signed date entered on upload, the signer's name and the signed PDF.

Handed to areas not yet drafted:
- **Areas 3, 4, 5, 9, 19:** every cost and invoice service calls the budget control and the JD1 resolver (no draft
  check, Q1); committed amounts (4, 9); the PO's inline over-budget transfer calls `add_transfer_rows` (9); T&M lines
  default Billable with the job's markup (5); `is_prevailing_wage` and WH-347 (19); the customer's job-sites list and
  tax rate from the site (5).
- **Area 16:** job custom fields per stage and service type.
- **Area 21:** entities inside one company file (which entity a job belongs to is not designed here); `row_version`
  on the new `company_settings` columns; the notification for "Enter budget".
- **Imports (backlog 4):** cost code and dimension paste lists use the Import service; dimension tables for
  `time_entry` and `staged_line` (JD1).
- **Build items for later phases (area 7):** `jobs.py`, `job_budgets.py`, `cost_codes.py`, `dimensions.py` (with the
  resolver), `operating_plans.py`, `job_cost.py`, `wip.py` (v1.1), the cost code template loader.

---

## 14. Inbox input 2026-11-22 (dated; not decided schema)

- **Contact roles on a job for outside parties** (design chat "CRM and Field gap list" item 5): architect, general
  contractor, lender, inspector and similar parties linked to a job, beyond the lead's decision-makers (Area 15).
  Not designed. A later pass proposes a job-contact link (job, contact, role from a company list, primary flag) that
  reuses `contact` rows instead of a parallel table; the role list follows the Reasons and lists pattern (Area 18).
  Generic, not solar-only.

- **Amendment 2026-11-23 (owner 7:23 PM and 7:28 PM; owner of the rule: Area 8 §12.6).** In the `project` DDL (§1):
  `target_start_on` becomes NOT NULL **(Withdrawn 2026-11-24, owner 11:58 PM 11/23, Q28 revisited: the start date is optional; planned completion is required; Area 8 §12.16)** (a job cannot be created without a start date, the first day of work on site,
  Area 8 Q28 A), and `requested_completion_on` TEXT (date or NULL) is added, copied from the lead's Requested
  completion at signing (Area 15 §12.1) **(Withdrawn 2026-11-23, owner 8:30 PM: next line)**. `target_finish_on` is dropped (lead default, owner may revise) **(Withdrawn 2026-11-23, owner 8:30 PM: next line)**: the target finish is
  derived (Area 8 §12.6).
- **Amendment 2026-11-23 (owner 8:30 PM revision; owner of the rule: Area 8 §12.10).** `target_finish_on` stays an
  editable date (NULL until the PM sets it), and every change writes a row in the new insert-only
  `project_target_history` (date, old, new, who, note). `estimated_completion_on` TEXT (date or NULL) replaces
  `requested_completion_on`, copied from the lead's Estimated completion date at signing (Area 15 §12.1).
  `target_start_on` NOT NULL stands (Q28). **(Withdrawn 2026-11-24, owner 11:58 PM 11/23, Q28 revisited: the start date is optional; planned completion is required; Area 8 §12.16)**
- **Amendment 2026-11-24 (Area 8 Q28 revisited; rule owned by Area 8 §12.16).** `project.target_start_on` is NULL
  allowed again (a job with no start shows "Not scheduled"). The required date at job creation is the planned
  completion, the baseline finish, held on the baseline (Area 8 §12.16).

- **Amendment 2026-11-24 (pointer, Area 9): committed amounts and material codes.** Job cost "committed" reads only
  **sent** POs and subcontracts (`purchase_order.committed_at`; Area 9 §6.2), less closed remainders. A material code needs
  an active leaf cost code, and a cost code cannot be deactivated while an active material code uses it (Area 9 §4).
  The PO's inline over-budget transfer calls `add_transfer_rows`.

- **Amendment 2026-11-25 (pointer, Area 16): job custom fields per stage are open again.** The owner kept job delivery-stage fields a separate set from the CRM lead fields (2:58 AM); Area 16 designs only Lead fields by service type and stage. Project custom fields stay company-wide and unscoped until that set is designed (Area 16 A16-Q8). **[Updated by the pointer below (A16-Q6): Project custom fields are dropped, not company-wide; the job-set question is now A16-Q9.]**

- **Amendment 2026-11-25 (pointer, Area 16, owner 3:47 AM, A16-Q6: custom fields are for CRM leads only): Project custom fields are dropped.** The line that `custom_fields.py:55` (Project read and write codes) is unchanged and the hand-off "job custom fields per stage and service type" are withdrawn; a job uses its built-in fields and notes (job delivery-stage fields are open: Area 16 A16-Q9).
