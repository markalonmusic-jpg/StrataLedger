# Step 2.9 schema replan, area 8: PM stages, service types, schedules, change orders, forecast

Status: **Owner-approved 2026-11-19** (first draft 2026-11-19, 3d15762; owner answers Q1-Q24 and the 8:40 PM
`rate_card_id` addition folded in below, section 10, c835d20; the on-hold rule of section 3.1 recorded with the
approval; amendment lines in area 18 sections 1.2 and 2.4). Planning has marked area 8 owner-approved in
`Strata_Teams\schema_replan_2026-11-17.md`. Docs only: nothing here changes code, a
baseline, a migration or a test. Every table, column, code and check below is built only in the 2.9 baseline pass,
after the replan is approved. PROPOSED items from the sources are not built as final. No questions are open.

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`: row 8 and its "Inbox inputs" for area 8, "8 and 3" (the schedule part
  only) and "15 and 8" (service jobs from cases).
- `Strata_Teams\inbox\to_planning.md` and `inbox\archive\to_planning_done.md`: 2026-11-13 controller_review
  "construction PM items"; 2026-11-15 "PM flow" (3:19 PM) and "Service types with their own stages" (3:30 PM);
  2026-11-17 "schedule items link to a phase" (4:19 PM), "schedule hierarchy" (owner), "schedule data model and
  services" (5:35 PM), "schedule baseline lock, thresholds, billing link, customer view" (5:46 PM), "schedule terms"
  (5:58 PM); 2026-11-18 "job close outcome, cancel stage, job type stages and custom fields" and "service jobs
  created from cases"; 2026-11-19 "forecast snapshots and who can change a job forecast" (2:20 PM).
- `Strata_Teams\ux_research_schedule_flow_2026-11-17.md` section 7 (and sections 4 and 9-11 where section 7 points).
- `Strata_Teams\inbox\archive\to_ux_research_done.md`: 2026-11-19 "forecast snapshots, many companies on desktop,
  open-by-someone lock" (planning 3:10 PM), part A only.
- `Strata_Teams\shared_decisions.md`: 2026-11-18 2:31 PM (two entries: job Closed outcome, job stages from the job
  type), 2026-11-19 2:20 PM (forecast), and the 2026-11-15 to 2026-11-17 schedule entries they cite.
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md`: sections 21, 28, 29, 34, 108, 109 (first numbering) and 26, 30
  (the second set, 2026-11-17). **Citation rule (planning correction, 2026-11-19):** "C21", "C34" and the like in
  this doc are section numbers of `CODE_CHANGES_NEEDED.md` (the working doc's source key "C"), not decision codes;
  `docs/decisions_2026-11-11.md` has no C-codes. Where two sections share a number, "(11-17)" marks the second set.
- `Strata_Teams\codex_reports\schema_gaps_vs_mockups_2026-11-18.md` item 5 (the line only).
- `Strata_Teams\shared_decisions.md` 2026-11-19 8:40 PM "T&M time source" and 8:42 PM (service type defaults) for
  `service_type.rate_card_id`.
- Approved areas: 13 (`work_week`, `company_holiday`, close tasks and checks, section 2.3), 17 (Records sources,
  `job_budget` compare, `from_jobs` measures), 18 (permissions, reasons, templates), 10 (job cost as recognized).
- `migrations/001_company.sql` (project, project_budget, change_order, change_order_line, contract, poc_snapshot,
  service_type, service_stage, stage_trigger, stage_trigger_run) and `modules/services/permissions.py`.

---

## 0. Summary

| # | Item | Proposal in one line | Baseline |
|---|------|----------------------|----------|
| 1 | Service types, stages, stage history | One `service_type` list for leads and jobs (Q1). Stages gain a role (bookends, Complete, Closed), target days, skip flag, guidance. New append-only `project_stage_history` with effective date, direction, reason, correction links (C34). Stages are deactivated, never deleted. Edits apply through the R36 review panel, no draft/publish set (Q3) | company |
| 2 | Job close | `Closed` is one stage with an outcome Completed or Cancelled (Q2). Cancel reasons are a company list. `project` gains `close_outcome`, `cancel_reason_id`, `cancel_note`, `cancelled_at_stage_id`, `completed_on`, `closed_on`, `closed_at`. The cancelled-at stage is set by the service. Close and cancel are history rows too, so reports never lose a reopened job's earlier outcome | company |
| 3 | Other job columns | Job site and target dates (Q9), manual % complete with who and why (area 13 check), billing type and warranty link (area 15), final bill requests, PM prompts (stage move, bill next milestone). `project.status` is dropped; an on-hold flag with an append-only hold history replaces its "Suspended" (Q6 C) | company |
| 4 | Schedules | Templates (version > phase > item), job schedule copied from a version, baselines (set_at/set_by, new versions only from a change order), updates with delay reasons, calendar items, crews. Status is computed, lookahead is a view. Work days use area 13's work week and holidays | company |
| 5 | Change orders | Existing `change_order` and lines grow reason, send, reject and approval-proof fields, markup per line, and a `field_event` table. Approving writes the budget lines (`project_budget.co_line_id`) and, with days, a new baseline version. Approved lines are locked **("with days, a new baseline version": Withdrawn 2026-11-23 (owner 7:20 PM): a CO's days move the target finish, §12.6. "Target" Withdrawn 2026-11-23 (owner 8:30 PM): a CO's days move the forecast, §12.10.)** | company |
| 6 | Forecast | `job_forecast_line` holds the current estimate to complete (ETC) per cost code. Every forecast change or budget transfer first writes an insert-only revision (header, eight figures per cost code, totals). Codes `job.forecast.edit` and `job.budget.transfer` | company |
| 7 | Boundary with area 7 | Area 7 owns the job record, budgets and cost codes; area 8 owns lifecycle, schedule, change orders, forecast. Table in section 7 | both |
| 8 | Controls, labels and permissions | New controls and the crew label setting, all permissive by default; new codes `job.schedule.edit`, `schedule.template.manage`, `service_type.manage`, `job.stage.backdate`, and the two forecast codes (section 8) | company |

Master file: no change.

---

## 1. Service types, stages and stage history

**Amendment 2026-11-23 (owner 7:10 PM):** `service_stage` as the stage list is replaced by the work tree's
level-2 nodes; stage roles, history and triggers point at nodes (§12.5). The rules below stand; their tables move.

### 1.1 Current state

- `service_type` (`001_company.sql:3940`: code, name, is_active, sort_order) and `service_stage` (`:3948`: type, phase
  Sales or Delivery, name, sort_order, `allows_costs`, `allows_billing`, `is_closed_stage`, is_active, UNIQUE per
  type and name), `stage_trigger` (`:3961`: stage, event Enter or Leave, action TEXT, `config_json`, sort_order) and
  `stage_trigger_run` (`:3971`, insert-only by triggers, one run per trigger, record and `event_key`). Audit triggers
  exist for all four (`:4647-4848`). RP4 made them replace the old `pipeline_stage`.
- `project.service_type_id` and `project.service_stage_id` (`:276-277`) hold the current stage. There is **no stage
  history**, no service module in `modules/services/`, and `project.status` (`:272`) is a separate CHECK list
  (Mobilization, In Progress, Suspended, Completed, Closed Out) that has no tie to the stage.
- Tests: `tests/test_schema_replan.py:516-545` (insert, uniqueness, FKs, audit coverage map at `:734`). Nothing calls
  stages from a service.
- Custom fields on a Project already work (`custom_fields.py`); scoping them to a service type or stage is area 16.

### 1.2 Decided

| Decision | Source |
|----------|--------|
| "Job types" are "Service types" everywhere; no Solar or Construction pipeline; each type has its own sales and delivery stages | S 11-15 3:30 PM; C109 |
| Fixed bookends Contract signed (end of sales, start of delivery) and Closed; stages are ordered, with target days and "can skip" | C109 |
| Stages carry triggers (events, conditions, ordered actions); automation never posts, approves or moves money; documents are drafts; requirements warn unless the control "Stage requirements block" is on; every run is logged and idempotent | A 11-15 3:30 PM; C109; rule 0 |
| A deleted stage with jobs asks where to move them | C109 |
| Stage history is append-only; each row has effective date, recorded time and user, from and to stage, direction (Forward, Back, Skip), reason (required for Back), correction flag and link; rows never updated or deleted; current stage and days in stage derive from the latest row | C34 (integrity, always on) |
| Effective date not in the future and not earlier than the row that put the job in its current stage; a mistaken move is fixed by a correction row, both stay | C34 |
| Time in stage, conversion and cycle days come from effective dates in history, never from the current stage or edit time; a correction removes the mistaken interval | C34 |
| The same table and rules apply to delivery stages on jobs ("one project, one history") | C34 |
| Job stages are not fixed: each type has its own, each stage can have custom fields and a guidance line | S 11-18 2:31 PM |
| Job calendar items have an optional stage | A 11-18 |
| A task tagged with a delivery stage prompts the PM to move the stage; the stage moves only on a person's click | S 11-17 5:35 PM |
| "Ready to install" style requirements (install date, crew, materials ordered) warn by default | A 11-15 3:19 PM item 5, replaced by C109 |
| Reports and boards group by service type; time in stage is a Records source (`src_job_stages`) | C109; area 17 |

Decided by Q4 A (the source, C34, proposed it ON at 7 days with permission `pipeline.backdate`): the control is
`stage_backdate_days`, empty by default, with the permission `job.stage.backdate` (conflict F4).

### 1.3 Proposed schema

**`service_type`** (existing): add `description` TEXT, `default_schedule_template_id` INTEGER REFERENCES
`schedule_template` (section 4; the service type names a default template that is pre-selected at signing, S 11-17
5:35 PM), `rate_card_id` INTEGER NULL (owner 2026-11-19 8:40 PM, T&M time source: none means the company rate
card; a plain integer until area 6 adds the `rate_card` tables, then a foreign key in the same baseline pass, like
open item 4), `row_version`.

Amendment 2026-11-20 (owner, from area 6): `service_type` also holds the estimate and contract defaults (S 11-19
8:42 PM "service type holds the default payment schedule"; docs/replan_2.9/area_6_estimates_contracts.md section 5.3):
`contract_template_id` INTEGER NULL REFERENCES `contract_template` (kind Contract), `pricing_template_id` INTEGER NULL
REFERENCES `pricing_template`, `co_terms_template_id` INTEGER NULL REFERENCES `contract_template` (kind Change order
terms; the service checks the kind), and the default payment schedule: `default_schedule_type` TEXT NULL CHECK (NULL
or IN ('Progress billing', 'Milestones', 'Fixed price', 'Time and materials')), `default_deposit_pct` REAL NULL CHECK
(NULL or 0-100), `default_deposit_cents` INTEGER NULL CHECK (NULL or >= 0; CHECK not both deposit columns set),
`default_retainage_pct` REAL NULL CHECK (NULL or 0-100), plus the child table `service_type_milestone`
(`milestone_id` PK, `service_type_id` FK, `sort_order`, `name` NOT NULL, `share_pct` REAL NOT NULL CHECK (> 0 AND <=
100), `billed_when` TEXT NOT NULL, `row_version`; the service checks deposit + shares = 100). `rate_card_id` is a
nullable FK to area 6's `rate_card`; NULL falls back to the company rate card (`company_settings.company_rate_card_id`).
A new estimate copies these defaults and may change them. The cancellation period is not on the service type (area 6
Q12 B: it is on the contract template version). Audited like the table; edits need `service_type.manage`.

Amendment 2026-11-20 (owner 2:10 PM, service quote rules): the service type also defaults who prices the estimate,
the PM, payment terms using the existing payment-term model, and quote-validity days. Copy these defaults onto the
estimate revision.

Amendment 2026-11-20 (owner 5:00 PM): Due on completion with no deposit is the shipped setting on the sample
service types. The configured service-type payment schedule takes precedence and is copied onto the estimate
revision for a service quote (area 6 §5.3).

Amendment 2026-11-20 (service-quote decision reconciliation): define these service-type defaults explicitly as
`default_cost_enterer_user_id`, `default_pm_user_id`, `default_payment_term_id` (FK to the existing `payment_term`),
and `default_quote_validity_days` (> 0), alongside its existing `pricing_template_id`. Estimate creation copies
them to the revision (`costs_by_user_id`, `assigned_pm_id`, payment-term id and frozen term fields, and
`quote_validity_days`); when there is one Solo user or separation controls are not set up, PM defaults to cost
enterer. No duplicate payment-term model is introduced.

**`service_stage`** (existing): replace `is_closed_stage` by `stage_role` TEXT NOT NULL DEFAULT 'Normal' CHECK IN
('Normal', 'Contract signed', 'Complete', 'Closed'); add `target_days` INTEGER CHECK (NULL or >= 0), `can_skip`
INTEGER NOT NULL DEFAULT 0, `guidance` TEXT CHECK (NULL or length <= 500), `row_version`. A job's stage must be a
Delivery stage of its own service type (service check). Exactly one 'Contract signed' and one 'Closed' per type, and
the bookends cannot be removed or moved out of order: a service rule (H4), not a trigger. The off-ramps Lost and
Cancelled of C109 are not stage roles for jobs (conflict F2); area 15 adds the lead-side role value 'Lost' to this
same CHECK when it is drafted. Stages are never deleted: removing one sets `is_active = 0` after the service has
moved every job in it (each move is a history row, `via` = 'Stage removed'); the foreign keys from history
(RESTRICT) are the backstop.

**Per-stage custom fields** stay with area 16 (`custom_field_def` gets the service type scope and "shown from
stage"). Area 8 owns only the stage `guidance`.

**`stage_trigger`** (existing) widened to the C109 trigger model, schema only (the engine is a later phase):
- `event` CHECK IN ('Enter', 'Leave', 'DaysInStage', 'FieldChange', 'DateReached', 'LinkedRecord');
- add `days` INTEGER (for DaysInStage), `condition_json` TEXT (the "Only if" list), `field_ref` TEXT;
- `action` stays free text checked by the service against a registry of action names (Create task, Notify, Send
  email, Require field, Require file, Draft PO, Draft milestone invoice, Start pay app, Request final bills, Draft
  change order, Move stage, Assign, Set date, Set probability). Several actions on one event are several rows in
  `sort_order`. "Require" actions warn unless `company_settings.stage_requirements_block` is 1.
- `stage_trigger_run` unchanged (idempotent by `event_key`, insert-only).
- Triggers act from the moment a change is applied (Q3), as a System actor on behalf of the rule owner; they never
  call a posting service (rule 0).

**`project_stage_history`** (new, insert-only; one row per move):

| Column | Type | Notes |
|--------|------|-------|
| `history_id` | INTEGER PK | |
| `project_id` | INTEGER NOT NULL | FK project |
| `from_stage_id` | INTEGER | FK service_stage; NULL on the first row |
| `to_stage_id` | INTEGER NOT NULL | FK service_stage |
| `effective_date` | TEXT NOT NULL | CHECK `= date(...)`; the date the move happened (C34) |
| `recorded_at` | TEXT NOT NULL | UTC ISO 8601 with offset; `recorded_by` INTEGER NOT NULL |
| `direction` | TEXT NOT NULL | CHECK IN ('Start', 'Forward', 'Back', 'Skip') |
| `reason` | TEXT | CHECK (NULL or length 1-1000); required for Back and for a correction (service) |
| `via` | TEXT NOT NULL | CHECK IN ('Job created', 'Manual', 'Schedule prompt', 'Trigger', 'Close', 'Reopen', 'Stage removed') |
| `is_correction`, `corrects_history_id` | INTEGER, INTEGER | CHECK `(is_correction = 1) = (corrects_history_id IS NOT NULL)`; self FK |
| `close_outcome`, `cancel_reason_id` | TEXT, INTEGER | only on the row that moves into the Closed stage (section 2); the project columns are the current copy |

Integrity triggers `project_stage_history_no_update` and `_no_delete` (the pattern of `stage_trigger_run`).
Everything else is the service (H4). Indexes: (`project_id`, `history_id`), (`to_stage_id`, `effective_date`).
Audit trigger on insert only (no updates exist).

Rules the service enforces (`job_stages.py`; permission `project.manage`, project scope): the effective date is not
after today (`context.today`, H2) and not earlier than the effective date of the row that put the job in its current
stage (equal is allowed, so a correction can carry the mistaken row's date and the wrong interval has zero length);
a Skip needs `can_skip`; a Back needs a reason; moving into Closed goes through the close dialog (section 2);
`project.service_stage_id` is updated in the same transaction as the history row; days in stage = today minus the
latest row's effective date. A stage's entry and exit requirements warn, or block when
`stage_requirements_block` is 1; a block is refused with the sentence naming what is missing.

**Controls (new, both permissive by default, Company Settings > Controls, audit-logged with a reason):**
`company_settings.stage_requirements_block` INTEGER NOT NULL DEFAULT 0; `company_settings.stage_backdate_days`
INTEGER NULL CHECK (NULL or >= 0) (NULL = no limit; Q4). When a limit is set, a move dated further back needs
`job.stage.backdate`, and a backdated row is shown with its recorded time.

### 1.4 How it lands in the baselines

`001_company.sql` only. Edits the four existing tables (columns above; `service_stage.is_closed_stage` removed, its
one use is `tests/test_schema_replan.py:521`), adds `project_stage_history` and its triggers, adds the audit
triggers for new columns (the audit JSON lists are rebuilt from the table, area 18), and adds two `company_settings`
columns (area 21 adds `row_version` to that row). Seeds: the five starter service types of C109 (Residential solar,
Commercial solar, Roofing, Home improvement, Construction general) with their stages and triggers, as shipped rows
the company can edit. A new `project` row writes its first history row in the job-creation service (area 7's
`create_job` calls `job_stages.start`).

### 1.5 Effect on existing services and tests

- No service reads or writes these tables today, so no service changes. `custom_fields.py` keeps working.
- `tests/test_schema_replan.py:516-545` and the audit map at `:734` change: the `is_closed_stage` insert becomes
  `stage_role='Closed'`; the map gains the new table.
- `project.status` is dropped (Q6 C, section 3.1); no code reads it.

### 1.6 Tests to write later

- History: the update and delete triggers refuse; the correction CHECK; an effective date in the future, an earlier
  date than the current stage's row, a Back without a reason, a Skip on a stage without `can_skip` are refused by
  the service; a correction with the mistaken row's date leaves zero time in the wrong stage; `service_stage_id`
  always equals the latest row's `to_stage_id`; a stage with jobs is not deactivated until they are moved.
- Controls: `stage_requirements_block` 0 warns and moves, 1 refuses; `stage_backdate_days` NULL never asks for
  `job.stage.backdate`, 7 refuses an eight-day backdate without it and shows "Backdated; recorded ..." in history.
- Reports: time in stage computed from history for a past range is the same after a later move (C34 "always the
  same answer").
- Every new column is in the audit triggers; a Viewer can read history and cannot move a stage.

---

## 2. Job close: Completed or Cancelled, cancel reasons

### 2.1 Current state

`project.status` has 'Completed' and 'Closed Out' (`001_company.sql:272`); no outcome, no reason, no date. `contract.status`
(`:890`) has Complete and Terminated. Area 13's checks `manual_pct_complete`, `estimates_to_complete_updated` and
`completed_job_review` (area 13 section 2.3) name "Completed job", which nothing in the baseline can say.

### 2.2 Decided

| Decision | Source |
|----------|--------|
| The path's last step "Closed" opens a dialog: Completed or Cancelled; both are closed jobs, shown "Closed · Completed" or "Closed · Cancelled" | S 11-18 2:31 PM |
| Cancelled needs a reason from a company list (editable in job settings) and an optional note; the stage the job was in is saved automatically ("Cancelled at: Install") | S 11-18 2:31 PM |
| Completed runs the existing job close checklist | S 11-18 2:31 PM |
| Columns on the job: `close_outcome` (completed or cancelled), `cancel_reason_id`, `cancel_note`, `cancelled_at_stage_id` (set by the service from the current stage), `closed_at` | A 11-18 item 1 |
| Done when closing as cancelled without a reason is rejected by the service | A 11-18 |
| Reports: cancellations by stage and by reason | A 11-18 item 4; area 17 `src_jobs_cancelled` |
| A "Complete" state set by the PM between the last delivery stage and Closed; costs can still post while complete; closing needs final billing issued (the checklist warns, rule 0) | A 11-15 3:19 PM item 1; C108/C109 ("Mark job complete") |
| Closeout checklist: all subs have a final pay app, final lien waivers (when the waiver control is on), no receipts waiting for a bill; open items warn, never stop the close | C108 |
| Final bill requests: a logged request per vendor or sub per job (date, open POs, receipts not billed), reminders after 3 / 7 / 14 days or none, emailed from the company mailbox, subs also asked for the final unconditional lien waiver | C108 |
| Area 13 check `completed_job_review` per Completed job (keep open or close out) | area 13 |

### 2.3 Proposed schema

**`project`** (area 7 owns the table definition; area 8 asks for these columns, section 7): `close_outcome` TEXT
CHECK (NULL or IN ('Completed', 'Cancelled')), `cancel_reason_id` INTEGER REFERENCES `job_cancel_reason`,
`cancel_note` TEXT, `cancelled_at_stage_id` INTEGER REFERENCES `service_stage`, `completed_on` TEXT (the effective
date the job entered its Complete-role stage; area 17's `from_jobs` measures read it), `closed_on` TEXT (effective
date of the move into Closed), `closed_at` TEXT (UTC, when recorded). Dates CHECK `IS date(...)`.
No CHECK ties the cancel fields to the outcome: "a reason is required" is a service rule (H4); the service also
clears all of them on a reopen (Q5).

**`job_cancel_reason`** (new, company list): `reason_id` PK, `name` TEXT NOT NULL UNIQUE, `is_active`, `sort_order`,
`is_shipped` (hide yes, delete no, as area 18's templates), `row_version`. Seeds: Customer backed out, Financing,
Permit denied, Other. A reason that was used is never deleted (FK RESTRICT).

Amendment 2026-11-19 (owner 11:20 PM, from area 15): `job_cancel_reason` is not built; it becomes the kind 'Job
cancel' of area 15's one `reason_option` table (area 15 Q16 A), seeded with the same four reasons.
`project.cancel_reason_id` and the closing history row's `cancel_reason_id` reference `reason_option` (ON DELETE
RESTRICT: a used reason is hidden, never deleted), each with a `cancel_reason_label` TEXT beside it, the label at the
time of use, written by the service (area 15 section 7.3, "Stored reasons")
(docs/replan_2.9/area_15_crm.md sections 7.3 and 10).

**Closing writes a `project_stage_history` row** into the Closed stage carrying `close_outcome` and
`cancel_reason_id`, plus `reason` when the job closes with open checklist items. So `src_jobs_cancelled` reads
history and never loses an earlier cancellation of a job that was reopened and later closed again; the `project`
columns are the current copy.

**`final_bill_request`** (new): `request_id` PK, `project_id` NOT NULL FK, `contact_id` NOT NULL FK (vendor or
sub), `requested_at`, `requested_by`, `remind_after_days` INTEGER CHECK (NULL or IN (3, 7, 14)), `last_reminded_at`,
`status` CHECK IN ('Open', 'Answered', 'Cancelled'), `open_items_json` TEXT (the open POs and receipts not billed
at the time, a frozen copy), `email_ref` TEXT (the sent-mail log id from area 20; no FK until area 20), `row_version`.
Never deleted by the service. Sending is a connection (area 20); the schema only records the request.

**Close service** (`job_close.py`; `project.manage`, project scope; refuses nothing on period locks because it posts nothing): Completed
needs the Complete-role stage first or goes through it in one step (`via` = 'Close'); Cancelled needs a reason.
Neither posts to the ledger. Costs and billing after Closed are refused by the stage's `allows_costs` /
`allows_billing` flags (service check on bill, invoice and pay app creation; those services are areas 3-5).

### 2.4 How it lands, effects, tests

- Lands in `001_company.sql`: the seven `project` columns (written into the `project` DDL by area 7 in the same
  pass), `job_cancel_reason`, `final_bill_request`, seeds. `contract.status` stays as is (area 6).
- Effects: `project.status` is dropped; the stage and outcome replace it (Q6 C). No code reads `project.status` today
  (searched `modules/`, `tests/`, `scripts/`).
- Tests to write later: cancel without reason refused; `cancelled_at_stage_id` taken from the current stage (a
  caller-supplied value is ignored); history row carries outcome and reason; reopen clears the project columns and
  keeps the history; a Cancelled job appears in `src_jobs_cancelled` by stage and reason from history; closing with
  open checklist items needs a reason and warns, blocks only when `stage_requirements_block` = 1; final bill request
  stores the frozen open items and a reminder uses `context.today`.

---

## 3. Other job columns and prompts

### 3.1 Current state and what is asked

| Need | Source | Today | Proposal |
|------|--------|-------|----------|
| Job site, target dates | X 5 | none (`contact.address` only; the contract has `start_date`, `completion_date`) | Q9 A: `project.site_street`, `site_city`, `site_state`, `site_zip`, `target_start_on`, `target_finish_on`, copied from the contract at creation, editable, every change in the audit log (no overwrite without history) **(`target_finish_on` as an editable copy: Withdrawn 2026-11-23 (owner 7:20 PM): the target finish is derived, §12.6 (this withdrawal Withdrawn 2026-11-23, owner 8:30 PM: `target_finish_on` is editable again, with history, §12.10); `target_start_on` is required, Q28, §12.6 **(start no longer required: Withdrawn 2026-11-24, Area 8 §12.16)**)** |
| Manual % complete, with who and why | area 13 check `manual_pct_complete` | none | `project.manual_pct_complete` REAL CHECK (NULL or 0-100), `manual_pct_reason` TEXT, `manual_pct_by` INTEGER, `manual_pct_at` TEXT. NULL = cost-to-cost (rule: schedule % is never used for revenue, C28) |
| Status | baseline | `project.status` | Q6 C: drop `project.status`. "Open", "Complete" (stage role Complete, not closed) and "Closed · Completed/Cancelled" derive from the stage and outcome. Add `project.on_hold` INTEGER NOT NULL DEFAULT 0 CHECK (0, 1) (the current copy) and the append-only `project_hold_history` below |
| Warranty and service jobs | A 11-18 | none | `project.billing_type` TEXT NOT NULL DEFAULT 'Billable' CHECK IN ('Billable', 'Warranty'); `warranty_for_job_id` INTEGER REFERENCES project; `source_case_id` INTEGER (FK added by area 15, which defines `service_case`; the link table `case_job(case_id, job_id)` is area 15's). Editable until the first cost posts (service rule); a Warranty job cannot be invoiced; its costs roll up to the original job's warranty line (area 7/10 job cost) |
| PM prompts (stage move, bill next milestone) | S 11-17 5:35 and 5:46 PM | none | `pm_prompt` below |

Corrected 2026-11-20 (consistency scan F4): The case link is `project.source_case_id` (FK to area 15's `service_case`); there is no `case_job` table. Job-cancel and delay reasons use area 15's `reason_option`, kinds 'Job cancel' and 'Delay'; `job_cancel_reason` and `delay_reason` are not built.

Withdrawn 2026-11-20 (service-quote decision reconciliation): the proposed `project.billing_type` field in this row
is superseded by area 7's separate `billing_method` and `cost_destination` columns and their CHECK-valid combinations.
The Warranty-line and service-overhead destinations, original-job requirement, and reporting split are defined by
area 7 section 1.3 and area 17 section 4.4.

**`project_hold_history`** (new, insert-only; owner Q6 C): `hold_history_id` PK, `project_id` NOT NULL FK,
`from_on_hold` INTEGER NOT NULL, `to_on_hold` INTEGER NOT NULL (both 0/1; CHECK `from_on_hold <> to_on_hold`),
`reason` TEXT NOT NULL CHECK (length 1-1000), `changed_by` INTEGER NOT NULL, `changed_at` TEXT NOT NULL (UTC ISO 8601
with an offset). Integrity triggers refuse update and delete (the pattern of `project_stage_history`); audit trigger
on insert. The hold service (`job_hold.py`, `project.manage`, project scope) writes the history row and sets
`project.on_hold` in one transaction; putting a job on hold and taking it off both need a reason (the service refuses
a missing one with one sentence); a Closed job cannot be put on hold; the flag is shown beside the derived state
("Open, on hold"). **On-hold rule (owner 2026-11-19, with the approval of area 8):** on hold is a label and warnings
only. It shows on the job everywhere (job header, lists, boards, reports, the company calendar), and it pauses the PM
prompts (`pm_prompt` rows are not created or shown for a held job) and the "schedule not updated" and other
schedule needs-attention alerts. Costs, purchase orders and billing are still allowed, each with a warning naming the
hold. **No posting or document is refused because of a hold**; no stage move, schedule update or change order is
refused either. The check is a warning in the services that create costs, POs and invoices (areas 3-5, 9), which read
`project.on_hold`; it is not a control and has no setting. Area 17's `src_jobs` offers the flag, and the history gives
time on hold.

**`pm_prompt`** (new; stores prompts so "Not now keeps it for 3 days" and "one prompt per job and stage" hold):
`prompt_id` PK, `project_id` NOT NULL FK, `kind` CHECK IN ('Move stage', 'Bill next milestone'), `ref_type` TEXT NOT
NULL, `ref_id` INTEGER NOT NULL (the task or stage), `created_at`, `snoozed_until` TEXT, `resolved_at`,
`resolved_by`, `resolution` CHECK (NULL or IN ('Done', 'Dismissed')), UNIQUE (`project_id`, `kind`, `ref_type`,
`ref_id`), `row_version`. A prompt never changes a stage or creates an invoice; a person does (rule 0). The "all
linked jobs complete, flag the case for Resolve" prompt (A 11-18 item 4) is a case flag in area 15, not here.

### 3.2 How it lands, effects, tests

Lands in `001_company.sql` with the `project` columns (area 7 writes the DDL) and `pm_prompt`. No existing service
or test uses these. Tests to write later: a held job shows the flag, creates no `pm_prompt` and raises no schedule alert, and a cost, PO or
invoice on it is allowed with a warning that names the hold (nothing refused); a Warranty job refuses an invoice; edits to `billing_method` and `cost_destination` are refused after the first posted cost. Warranty requires an original job. Goodwill uses the configurable `service_goodwill` System account mapping; manual % outside 0-100 refused and listed by the area 13 check with who and why; one prompt per
job and stage even when the first actual start is applied twice; snooze hides for 3 days using `context.today`.

---

## 4. Schedules

### 4.1 Current state

Nothing exists: no schedule table, no `work_week` or holiday table (area 13 adds both), no crew table, no date math.
The only fragments are `contract.start_date` and `completion_date` (`:885-886`) and `change_order.days_added`
(`:803`). The Gantt mockup (job-detail, schedule-templates, job-calendar) is the spec.

### 4.2 Decided

| Decision | Source |
|----------|--------|
| Hierarchy Phase > Task; a milestone is a single-date item in a phase; a calendar item links to a task or straight to a phase (`phase_id` required, `task_id` optional) **Withdrawn 2026-11-23 (owner 1:54 AM): the hierarchy is Stage > Phase > Task; the stage comes from the phase; §12.1** | A 11-17 (hierarchy), S 11-17 5:13 PM |
| Terms: phase, task, milestone, predecessor (type FS or SS, lag in work days), baseline (`set_at`, `set_by`), calendar item (was schedule item), lookahead (1-6 weeks, a view only), delay reason | A 11-17 5:58 PM |
| Template > version > phases (ordered) > items (task or milestone, ordered): work days (tasks), an optional predecessor, an optional delivery stage tag, an optional default assignee type; loop check on save; templates are independent of service type; a service type may name a default **"Templates are independent of service type" and the optional delivery stage tag: Withdrawn 2026-11-23 (owner 1:54 AM): a template belongs to a service type and each phase to one of its stages; §12.1** | A 5:35 PM; S 11-17 5:35 PM; C30 (supersedes C29) |
| A saved template makes a new version; jobs already scheduled keep theirs ("Applies to new jobs only") | flow A1; to_design R36 note |
| Job schedule: a copy of one template version, plus planned (baseline), forecast and actual start and finish, % complete, assignee (crew, or vendor or subcontract), notes **(% complete on a task: Withdrawn 2026-11-23 (owner 7:10 PM): tasks are Not started, In progress or Done, §12.5)** | A 5:35 PM item 2 |
| Baselines are versioned; each new version references the change order that created it | A 5:35 PM |
| No baseline until the PM clicks Set baseline or applies the first update, whichever is first; store `locked_at`/`locked_by` (now `set_at`/`set_by`); versions after that come only from a change order; a gold reminder after 14 days **(Withdrawn 2026-11-23 (owner 7:20 PM, Q27): the baseline is the signed contract's dates, set at signing, one version, never moved; §12.6)** | A 5:46 PM item 1; flow section 9 |
| Calendar items: job, phase (required), task (optional), date, optional time, description, who, notify; they never change task dates; optional stage | A 5:35 PM item 3; A 11-18 |
| Updates: one record per Apply (who, when, per-item old and new, reason); a reason is required when a forecast finish moves later; reasons Weather, Material late, Inspection or permit, Owner or customer, Subcontractor, Crew availability, Design change, Other plus note | A 5:35 PM item 4 |
| Date math uses the work week and company holidays; linked moves are returned as a preview and saved only on Apply; stage prompts on the first actual start or finish of a tagged item; no automatic date or stage change | A 5:35 PM item 5 |
| Status is computed: Done, Late, At risk, On track, Not started; thresholds default At risk 1-5 work days, Late over 5; a company setting, logged | A 5:35 and 5:46 PM |
| Optional link from a schedule milestone to a payment-schedule milestone; when done the system prompts; a person creates the draft invoice | A 5:46 PM item 3 |
| Share schedule: a one-page list of milestones with forecast dates only | A 5:46 PM item 4 |
| Crews: id, name, trade tag, active; no members; assignable to tasks and appointments | A 5:55 PM |
| Both schedule baselines and dates: "planned dates read-only once the baseline is set; a task added after baseline shows 'Added after baseline'" | flow B2 |
| One calendar query across sources (job tasks, milestones, calendar items, activities, close tasks), filtered by permission | A 6:03 PM (query is area 21; this area supplies the date columns and indexes) |
| Gantt, bar dragging, critical path, FF and SF links: Later (D4) | flow section 0 |

### 4.3 Proposed schema

**Crews** (new here because the schedule needs them first; area 15 reuses the table for appointments):
`crew(crew_id PK, name TEXT NOT NULL UNIQUE, trade_tag TEXT, is_active, row_version)` (Q13 A: defined here, reused
by area 15). The word is a company setting: `company_settings.crew_label_singular` TEXT NOT NULL DEFAULT 'Crew' and
`crew_label_plural` TEXT NOT NULL DEFAULT 'Crews', each CHECK length 1-40. Every screen, report and export label
that says Crew or Crews reads them (a service returns the labels with the lists; report and export column headers
read them through area 17's field registry labels). Table and column names stay `crew`; a label change is an
ordinary audited `company_settings` change (not a control).

**Templates:**
- `schedule_template(template_id PK, name UNIQUE NOT NULL, description, is_shipped, is_active, row_version)`.
- `schedule_template_version(version_id PK, template_id FK, version_no INTEGER NOT NULL, saved_at, saved_by, note,
  UNIQUE (template_id, version_no))`.
- `schedule_template_phase(phase_id PK, version_id FK, name NOT NULL, sort_order)`.
- `schedule_template_item(item_id PK, phase_id FK, kind CHECK IN ('Task', 'Milestone'), name NOT NULL, sort_order,
  work_days INTEGER, pred_item_id INTEGER REFERENCES schedule_template_item, pred_type CHECK (NULL or IN ('FS',
  'SS')), lag_work_days INTEGER NOT NULL DEFAULT 0, stage_id INTEGER REFERENCES service_stage, assignee_type CHECK
  (NULL or IN ('Crew', 'Subcontractor', 'Supplier')), notes)`; CHECK `(kind = 'Task') = (work_days IS NOT NULL)`,
  CHECK `work_days IS NULL OR work_days >= 1`, CHECK `(pred_item_id IS NULL) = (pred_type IS NULL)`.
- Version, phase and item rows are insert-only (Q15): editing a template copies the whole version as the next one.
  The loop check (no self link, no cycle) and "the predecessor is in the same version" are service checks on save.
- The template's Work week and Holidays selectors in the mockup show the company's (area 13; Q11).

**Job schedule** (one per job; every job has one, Blank included, Q14):
- `job_schedule(schedule_id PK, project_id UNIQUE NOT NULL FK, source_template_id FK NULL, source_version_id FK
  NULL, start_date NOT NULL, created_at, created_by, baseline_set_at TEXT, baseline_set_by INTEGER,
  last_updated_at TEXT, last_updated_by INTEGER, row_version)`; CHECK `(baseline_set_at IS NULL) = (baseline_set_by
  IS NULL)`. "Baseline set" is `baseline_set_at IS NOT NULL`.
- `job_schedule_phase(phase_id PK, schedule_id FK, name NOT NULL, sort_order, row_version)`. A phase's dates are
  computed from its tasks; a phase has none of its own.
- `job_schedule_task(task_id PK, schedule_id FK, phase_id FK, kind CHECK IN ('Task', 'Milestone'), name NOT NULL,
  sort_order, work_days, pred_task_id REFERENCES job_schedule_task, pred_type, lag_work_days, stage_id FK
  service_stage, forecast_start, forecast_finish, actual_start, actual_finish, pct_complete INTEGER CHECK (0-100),
  crew_id FK crew, vendor_id FK contact, subcontract_id INTEGER (FK added by area 4), notes,
  payment_milestone_id INTEGER (FK added by area 6; milestones only), source_item_id FK schedule_template_item,
  row_version)`. Same shape CHECKs as the template item; CHECK at most one of `crew_id`, `vendor_id` is set.
  Milestones use `forecast_finish` and `actual_finish` only. **No planned columns on the task:** planned dates are
  the lines of the newest baseline. Before the baseline is set, planned equals forecast.
  **Withdrawn 2026-11-23 (owner 7:10 PM and 7:20 PM): `phase_id`, `stage_id`, `kind`, `name`, `sort_order` and
  `pct_complete` move to or come from the work tree (§12.5); "before the baseline is set" no longer happens (the
  baseline is set at signing, §12.6).**

  Amendment 2026-11-20 (owner, from area 6): `payment_milestone_id` is INTEGER NULL REFERENCES area 6's
  `contract_milestone` (the job's payment-schedule milestone copied at Mark signed;
  docs/replan_2.9/area_6_estimates_contracts.md section 5.3); the service checks the milestone belongs to the
  task's job's contract.
  The stage tag is copied from the template item by stage name into the job's service type (NULL when the job's
  type has no stage of that name).
- `job_schedule_baseline(baseline_id PK, schedule_id FK, version_no INTEGER NOT NULL, set_at, set_by,
  change_order_id INTEGER REFERENCES change_order, days_added INTEGER NOT NULL DEFAULT 0, note, UNIQUE (schedule_id,
  version_no))`; CHECK `(version_no = 1) = (change_order_id IS NULL)`. **Withdrawn 2026-11-23 (owner 7:20 PM, Q27: baseline locked at signing; a CO or a granted extension moves the target): §12.6. "Moves the target" Withdrawn 2026-11-23 (owner 8:30 PM): a CO moves the forecast, §12.10.**
- `job_schedule_baseline_task(baseline_id FK, task_id FK, planned_start, planned_finish, days_added INTEGER NOT NULL
  DEFAULT 0, PRIMARY KEY (baseline_id, task_id))`. A task with no line in the newest baseline is "Added after
  baseline". Baseline and baseline task rows are insert-only (integrity: a baseline is the record the schedule was
  held to).
- `schedule_update(update_id PK, schedule_id FK, applied_at, applied_by, finish_before, finish_after, note)` and
  `schedule_update_line(line_id PK, update_id FK, task_id FK, old/new for pct_complete **(Withdrawn 2026-11-23 (owner 7:10 PM): §12.5)**, actual_start,
  actual_finish, forecast_start, forecast_finish, delay_reason_id FK NULL, delay_note TEXT, moved_by_link INTEGER
  NOT NULL DEFAULT 0)`. One update per Apply; insert-only. Structural edits of the planning pass (add or move a
  task, re-link, assign, change work days) are not updates; their history is the audit log, which the panel
  History reads.
- `delay_reason(reason_id PK, name UNIQUE NOT NULL, is_shipped, is_active, sort_order, requires_note, row_version)`,
  seeded with the eight owner reasons, Other requiring a note (Q10).

Amendment 2026-11-19 (owner 11:20 PM, from area 15): `delay_reason` is not built; it becomes the kind 'Delay' of area
15's `reason_option` table (area 15 Q16 A), seeded with the same eight reasons (Other `requires_note`).
`schedule_update_line.delay_reason_id` references `reason_option` (ON DELETE RESTRICT), with a `delay_reason_label`
TEXT beside it, the label at the time of use, written by the service (docs/replan_2.9/area_15_crm.md section 7.3).

**Calendar items** (renamed from schedule items):
**`calendar_item`: Withdrawn 2026-11-23 (owner 7:10 PM): a calendar item is an `activity` row of type Calendar
item pointing to a work-tree node, §12.5.**
`calendar_item(item_id PK, project_id NOT NULL FK, phase_id NOT NULL FK job_schedule_phase, task_id FK NULL,
stage_id FK NULL, item_date NOT NULL, start_time TEXT (HH:MM), length_minutes INTEGER, description NOT NULL,
user_id FK NULL, crew_id FK NULL, contact_id FK NULL, row_version)`; CHECK at most one of the three "who" columns;
`calendar_item_notify(item_id FK, user_id, PK both)`. Indexes on (`item_date`), (`project_id`, `item_date`). Calendar
items never write task dates. Busy checks for users and crews (area 15) read `start_time`, `length_minutes`.

**Controls (new, permissive defaults):** **(Amendment 2026-11-24: plus the Company control `require_baseline_rebuild_approval`, OFF by default; §12.19, Area 18 §8.10.)** **(Withdrawn 2026-11-24, owner 1:48 AM: no separate control; the on/off switch is the Approvers row "Schedule baseline rebuilds"; Area 8 §12.20)** `company_settings.schedule_at_risk_days` INTEGER NOT NULL DEFAULT 1,
`schedule_late_days` INTEGER NOT NULL DEFAULT 5 (Late when more than this), `schedule_pct_behind_points` INTEGER NOT
NULL DEFAULT 20, `baseline_reminder_days` INTEGER NOT NULL DEFAULT 14 **(Withdrawn 2026-11-23 (owner 7:20 PM): §12.6)**; CHECKs `>= 0`. Each change logged with a
reason (area 18).

**Services** (`schedule_templates.py`, `job_schedules.py`, `work_calendar.py`, `calendar_items.py`; no UI, no clock
reads):
- `work_calendar`: `add_work_days(date, n)`, `count_work_days(a, b)`, `next_work_day(date)` over
  `company_settings.work_week` and `company_holiday` (area 13). Pure functions of the context's settings.
- `build_schedule(project, template_version, start_date)`: copies the version, computes dates from the start date,
  work days, predecessors and the work week; Blank creates the phase "Project" holding the milestones "Contract
  signed" and "Substantial completion" (Q14). Warns (never blocks) when the forecast finish is after
  `contract.completion_date`.
- `preview_update` returns old and new for every moved task including linked moves; `apply_update(schedule_id,
  changes, row_version)` saves, writes the `schedule_update` rows, and sets the baseline first when it is not set
  (Q12) **("sets the baseline first": Withdrawn 2026-11-23, §12.6)**, then creates `pm_prompt` rows for tagged tasks on a first actual start or finish. A forecast finish moving
  later needs a `delay_reason_id` (and note for Other); earlier needs none.
- `set_baseline` **(Withdrawn 2026-11-23 (owner 7:20 PM): §12.6)**: sets `baseline_set_at/by`, writes baseline v1 from the forecast dates. Planned dates are read-only
  afterwards; the service refuses edits of planned dates and only a change order approval writes a new baseline
  (section 5). **Withdrawn 2026-11-23 (owner 7:20 PM, Q27: baseline locked at signing; a CO or a granted extension moves the target): §12.6. "Moves the target" Withdrawn 2026-11-23 (owner 8:30 PM): a CO moves the forecast, §12.10.**
- Status is computed in one function (Done, Late, At risk, On track, Not started; a phase takes its worst task; the
  job compares forecast finish with the contract date); never stored. Lookahead and Gantt/Calendar choice are
  per-user preferences (area 17's list preferences), not schedule data. Share schedule renders milestones and
  forecast dates only; emailing goes through area 20.
- Permissions (section 8): templates `schedule.template.manage`; edits `job.schedule.edit` (project scope);
  a Viewer reads.

### 4.4 How it lands, effects, tests

- Lands in `001_company.sql`: 14 new tables (crew, 4 template tables, `job_schedule`, phase, task, baseline,
  baseline task, update, update line, delay reason, calendar item, notify), the `service_type` default-template
  column, four `company_settings` columns, seeds (delay reasons, three starter templates: Residential solar,
  Commercial solar, Roofing, flagged shipped).
- Effects: area 13's work week and holidays are read only. No existing service or test changes.
- Tests to write later: loop and self link refused; a milestone with work days refused; template save creates
  version n+1 and a job built from v3 is unchanged by v4; build_schedule dates match hand-counted work days across a
  holiday and a weekend; linked FS and SS moves with lag; preview changes nothing until apply; a later forecast
  finish without a reason refused; first Apply sets the baseline from the pre-update dates; after the baseline,
  planned edits refused; a task added later is "Added after baseline"; status thresholds read the settings and a
  change is audit-logged; calendar items never move a task; stage prompt created once; a Viewer sees no edit path.

---

## 5. Change orders and their effect on the budget

### 5.1 Current state

- `change_order` (`001_company.sql:791`): `status` CHECK IN ('Draft', 'Submitted', 'Approved', 'Rejected', 'Void'),
  `co_number`, `description`, submitted, approved and effective dates, `approved_by_name`, `approval_ref`,
  `days_added`. `change_order_line` (`:170`): cost code, `sov_line_id`, `revenue_change_cents`, `cost_change_cents`.
  `project_budget.co_line_id` (`:292`) already points at a CO line. No audit trigger on change orders, no service.
- Permissions exist: `change_order.create`, `change_order.approve` (sensitive), the approval document type "Change
  order" (`permissions.py:69-70,156,172`).
- Baseline CHECKs: the cents columns check integer type.

### 5.2 Decided

| Decision | Source |
|----------|--------|
| A change event raised from site (photo, note, optional signature) is not priced; the PM turns it into a CO or closes it with a reason | C21 |
| A draft CO has a reason (hidden condition, owner request, design change, code requirement), schedule impact in days, lines by cost code with cost, markup and price, photos carried over, send to customer by PDF email; drafts can be changed or deleted | C21 |
| Pending customer: follow-up reminders, record rejection with a reason, record approval | C21 |
| Recording approval needs approved-by and date and proof (signed CO or email); before confirming it shows the effect: revised contract, revised budget by cost code, forecast margin, the new SOV line | C21 |
| Approved COs lock; fixes use a new CO; nothing posts to the ledger | C21 |
| Approval changes the budget by cost code and the contract; the estimate to complete does not move by itself (the cost was already forecast) | C21 sample |
| A CO with a time extension gets an "Extend schedule" step: pick tasks and work days per task; on approval baseline v2 is created and linked to the CO **("baseline v2": Withdrawn 2026-11-23 (owner 7:20 PM): approval moves the target finish, §12.6; "target" Withdrawn 2026-11-23 (owner 8:30 PM): approval moves the forecast, §12.10)** | flow B5; A 5:35 PM |
| "Proceeding at risk" (work done before signature) is a flag | C21 PROPOSED, not built |
| PCO, change events and T&M tickets ahead of formal COs | controller 11-13 item 3: recommended, not decided (open item 3) |

### 5.3 Proposed schema

**`change_order`** (existing): keep the status values; the mockup's "Pending customer" is the label of `Submitted`
(F11). Add `reason` TEXT CHECK (NULL or IN ('Hidden condition', 'Owner request', 'Design change', 'Code
requirement')), `field_event_id` INTEGER REFERENCES `field_event`, `sent_at`, `sent_by`, `follow_up_on` TEXT (ISO
date, the next reminder), `rejected_date` TEXT, `rejection_reason` TEXT, `approval_recorded_by` INTEGER,
`approval_recorded_at` TEXT, `row_version`. `approved_by_name` is the customer signer, `approval_ref` the proof
reference, and the proof file is an `attachment` (area 18); the service refuses to record approval without one of
the two. `days_added` stays the schedule impact. CO numbers come from `sequences.py` (not a registered gapless
series; drafts may be deleted). Price and cost totals are sums of lines, never stored.

**`change_order_line`** (existing): add `markup_pct` REAL (an entry aid; `revenue_change_cents` is the stored
price, rounded by the company rounding rule) and `row_version`.

Amendment 2026-11-20 (owner, from area 6; S 11-19 9:44 PM, 10:10 PM and 10:22 PM): the terms template and pricing
on change orders. `change_order` gains `terms_template_version_id` INTEGER NULL REFERENCES area 6's
`contract_template_version` (kind Change order terms), defaulting from `service_type.co_terms_template_id`; the PM
picks it on the pricing screen and the sales rep may change it until Submitted; a published version is fixed, so a
sent CO keeps its terms. `change_order` also gains `pricing_template_id` INTEGER NULL REFERENCES `pricing_template`
(from the service type when priced). On `change_order_line`, `markup_pct` comes from that template by the line's cost
code's cost type (area 7); a fixed (non-editable) markup refuses a different `markup_pct` ("This markup is set by the
<name> pricing template."); Margin % is derived, never stored. Customer approval (section 5.3 item 1) calls area 6's
`contracts.add_change_order_lines(context, contract_id, change_order_id, lines)` in the same transaction, which adds
the SOV lines; `change_order_line.sov_line_id` names the SOV line it raised (docs/replan_2.9/area_6_estimates_contracts.md
sections 3.3 and 10.2).

**`field_event`** (new): `field_event_id` PK, `event_number` TEXT NOT NULL UNIQUE (FE-0008), `project_id` NOT NULL FK,
`raised_at`, `raised_by`, `occurred_on`, `note` NOT NULL, `customer_signed_name` TEXT, `status` CHECK IN ('Open',
'Converted', 'Closed'), `co_id` FK NULL, `closed_reason`, `closed_at`, `closed_by`, `row_version`. Photos and the
field signature are attachments (area 18); converting copies the attachment rows to the CO (same stored file;
confirm with area 18, open item 6).

**Integrity backstop (Q17):** triggers refuse insert, update and delete of `change_order_line` rows whose header is
Approved, and refuse any update of an Approved header except nothing (an approved CO is final; fixing needs a new
CO, so Void applies to Draft and Submitted only). Budget and contract totals derive from approved lines, so this
is the same kind of lock as posted `journal_line` rows.

Note 2026-11-20 (owner 12:05 AM): **(Withdrawn 2026-11-23, owner 10:45 PM: no 'PCO pending' status; a PCO is a field event; §12.14, Q37)** Superseded by the 2026-11-19 amendment: Void from any open state (PCO pending,
Draft, With sales rep, Submitted); Approved and Rejected stay final.

**Approval service** (`change_orders.py`; `change_order.create` to draft and send, `change_order.approve` to record
customer approval; the internal approval chain, when a company turns on "Change order approval", is area 14's
single mechanism, default OFF):
1. In one transaction: status to Approved, `approval_recorded_*`, one `project_budget` row per line with a cost
   change (`co_line_id` set, `budget_cents` = the cost change) written through area 7's budget service (Q18), the
   contract revised amount by the contract service (area 6: new SOV lines from the CO lines), a forecast revision of
   kind 'Change order' (Q16), and, when `days_added` > 0, the "Extend schedule" input.
2. Extending the schedule writes `job_schedule_baseline` v(n+1) with `change_order_id`, `days_added`, and one
   baseline task line per task with its work days added; forecast dates do not move on their own (a person applies
   an update). When the baseline was never set, approval sets it first from the then-current forecast. Approval is
   allowed without extending (a warning only, rule 0). **Withdrawn 2026-11-23 (owner 7:20 PM, Q27: baseline locked at signing; a CO or a granted extension moves the target): §12.6. "Moves the target" Withdrawn 2026-11-23 (owner 8:30 PM): a CO moves the forecast, §12.10.**
3. Nothing posts to the ledger.
Void and Reject write the reason; Reject needs `rejection_reason`.

Amendment 2026-11-19 (owner 11:20 PM, from area 15):
- `change_order.reason` and its CHECK list are replaced by `reason_id` (FK `reason_option`, kind 'Change order', ON
  DELETE RESTRICT) and `reason_label` TEXT (the label at the time of use, written by the service). The four reasons
  are seeded as that kind, and the kind's rows carry the `billable_to_customer` flag
  (docs/replan_2.9/area_15_crm.md section 7.3).
- `field_event` gets cost lines: `field_event_line`, kind Material (with `material_code_id`) or Other (with
  `cost_code_id`). The summary by cost code is derived, never stored. A field event can still close with a reason
  without a CO.
- PCO and CO are one `change_order` record **(Withdrawn 2026-11-23, owner 10:45 PM: a PCO is a field event; a CO record exists only after a PM converts it; §12.14)**. `change_order.status` CHECK IN ('PCO pending', 'PCO rejected', 'Draft'
  (priced), 'With sales rep', 'Submitted' (label "Sent to customer"), 'Approved', 'Rejected', 'Void'); Void is
  allowed from any open state. New insert-only `change_order_status_history` (from status, to status, who, when,
  `reason_id`, `reason_label`) with no-update and no-delete triggers.
- Internal PCO approval is the "Change order approval" control, OFF by default (area 14). When off, the PM approves
  with one click (logged). When on, the approver approves or rejects with a reason.
- Moving to PCO pending **(Withdrawn 2026-11-23, owner 10:45 PM: a PCO is a field event; a CO record exists only after a PM converts it; §12.14)** writes a `job_forecast_revision` of kind 'PCO' and `job_forecast_line` rows tagged
  `change_order_id`, so pending PCO cost is its own line by cost code (section 6.3 amendment). PCO rejected or Void
  writes a revision that removes them. Customer approval writes the budget and contract rows as already approved
  and leaves the ETC unchanged. The revised budget never moves before customer approval.

Amendment 2026-11-20 (owner 11-19 9:58 PM, decision audit; answered 1:50 AM): `field_event` gains `reason_id`
INTEGER NOT NULL (FK `reason_option`, kind 'Change order', ON DELETE RESTRICT) and `reason_label` TEXT NOT NULL (the
label at the time of use); `expected_days_impact` INTEGER NULL CHECK (NULL or >= 0); `pricer_user_id` INTEGER NOT
NULL once saved (a master user id, plain integer, no FK, since users live in the master file), defaulting to the
job's PM, and the person logging the event can change it (an R25 pick from users who hold `change_order.create` on
the job); and `price_due_on` TEXT NULL (a date, optional). Saving the field event writes one notification to the
pricer (area 21 feed). Converting it copies `expected_days_impact` into `change_order.days_added` as the starting
value.

Amendment 2026-11-20 (owner 11-14 12:40 PM, decision audit; answered 1:50 AM): a change order whose margin is under
`company_settings.estimate_margin_floor_pct` (area 6 s4.3) shows an R27 Check alert on the pricing screen, and its
send (to Submitted) returns a warning and succeeds. It never refuses (rule 0). With "Change order approval" ON, the
under-floor condition is area 14's policy condition, the same as for estimates.

Amendment 2026-11-20 (owner 11-19 10:10 PM, decision audit; answered 1:50 AM, Q2 A): an office change order is
created with `field_event_id` NULL and enters PCO pending once its costs are entered **(Withdrawn 2026-11-23, owner 10:45 PM: a PCO is a field event; a CO record exists only after a PM converts it; §12.14)**. From there it follows the same
statuses, forecast revision (kind 'PCO') and "Change order approval" step as the field-event path.

Amendment 2026-11-22 (tax on signed quotes; Area 5 Q12): change order prices are pre-tax, and a tax-rate change needs
no change order because tax is calculated on each invoice.

### 5.4 How it lands, effects, tests

- Lands in `001_company.sql`: the new columns, `field_event`, the lock triggers, audit triggers for the three tables,
  `change_order` series in `sequences`. `change_order_line.sov_line_id` and contract effects follow area 6.
- Effects: no service exists. `permissions.py` keeps `change_order.create` and `.approve`; the approvals document
  type "Change order" keeps its mapping (area 14 decides the chain).
- Tests to write later: approve without proof or signer refused; approval writes budget rows whose sum equals the
  cost change and a revised budget per cost code that matches the preview; an approved line cannot be edited or
  deleted (trigger); a Rejected CO needs a reason; converting a field event copies photos and links `co_id`; a CO
  with days extends the schedule to baseline v2 linked to the CO **(Withdrawn 2026-11-23 (owner 7:20 PM): §12.6)** and "Compare to v1" still reads v1; approval does
  not change `job_forecast_line.etc_cents`; nothing posts (journal tables unchanged).

---

## 6. Forecast changes and insert-only revision snapshots

### 6.1 Current state

`project_budget` holds amounts by cost code (`001_company.sql:282`, budget_cents, estimate line, CO line). Nothing
holds an estimate to complete by cost code: `poc_snapshot.est_cost_to_complete_cents` (`:697`) is one number per
job and period. `project.revised_budget_cents` (`:270`) is a cached total "forked via change logs". No forecast
table, history or service. Area 13's `wip_current` and `estimates_to_complete_updated` checks need a record of ETC
changes and their dates.

### 6.2 Decided

| Decision | Source |
|----------|--------|
| PMs update the estimate to complete on the job's Budget tab ("Update forecast"); each change is kept; a change over the threshold needs a note | S 11-16 2:02 PM (note threshold not given) |
| Forecast history lives under Budget (or Schedule when there is no Budget tab) | C26 (11-17) |
| Each forecast change keeps a read-only snapshot of the job's whole budget table as it stood just before the change: per cost code original budget, approved CO cost, revised budget, committed, cost to date, ETC, forecast at completion, variance, plus totals | A 11-19 2:20 PM item 1 |
| Storage is copies, not a rebuild: committed and cost to date keep moving. Each change writes, in the same transaction and before the change, an insert-only revision header (job, revision number, changed by, changed at UTC, reason, kind ETC update or budget transfer) plus one line per cost code with the eight figures in cents and the totals; triggers refuse update and delete; audited | planning 3:10 PM part A.1 |
| Data layer: `getForecastHistory(jobId)`, `getForecastRevision(revisionId)`, `updateForecast(jobId, lines, reason, rowVersion)`, `transferBudget(jobId, fromCode, toCode, amount, reason, rowVersion)`, each returning the new revision or a conflict | planning 3:10 PM A.2 |
| Only Project manager, Controller, Admin and Master update the forecast or transfer budget; Sales rep and Viewer read only; codes `job.forecast.edit` and `job.budget.transfer`, seeded to the Project manager and Controller templates (L7: codes, never role names); an amendment line in area 18 is written when area 8 is drafted | planning 3:10 PM A.3; S 11-19 2:20 PM |
| The snapshot opens in a full-width top drawer with the touched cost code marked, who, when and the note | S 11-19 2:20 PM |

### 6.3 Proposed schema

**`job_forecast_line`** (new; the current ETC): `project_id` NOT NULL FK, `cost_code_id` NOT NULL FK, `etc_cents`
INTEGER NOT NULL CHECK (typeof integer and `>= 0`), `updated_at`, `updated_by`, PRIMARY KEY (`project_id`,
`cost_code_id`). Seeded when a job's budget is first set (ETC = the budget for that code, service). No
`row_version` (Q20).

**`job_forecast_revision`** (new, insert-only; the state **before** one change):
`revision_id` PK, `project_id` NOT NULL FK, `revision_no` INTEGER NOT NULL (UNIQUE with project, 1, 2, ...),
`kind` TEXT NOT NULL CHECK IN ('ETC update', 'Budget transfer', 'Change order') (the last only if Q16 A),
`changed_by` INTEGER NOT NULL, `changed_at` TEXT NOT NULL (UTC), `reason` TEXT CHECK (NULL or length 1-1000), and
the totals as integer cents NOT NULL: `total_original_cents`, `total_co_cents`, `total_revised_cents`,
`total_committed_cents`, `total_cost_to_date_cents`, `total_etc_cents`, `total_fac_cents`, `total_variance_cents`.

**`job_forecast_revision_line`** (new, insert-only): `revision_id` FK, `cost_code_id` FK, the eight figures
`original_cents`, `co_cents`, `revised_cents`, `committed_cents`, `cost_to_date_cents`, `etc_cents`, `fac_cents`,
`variance_cents` (INTEGER NOT NULL, typeof integer), `is_touched` INTEGER NOT NULL DEFAULT 0 (the code or codes the
change names; a transfer touches two), PRIMARY KEY (`revision_id`, `cost_code_id`). CHECKs: `fac_cents =
cost_to_date_cents + etc_cents` and `variance_cents = revised_cents - fac_cents` (positive means under budget).
Triggers `*_no_update` and `*_no_delete` on header and lines (integrity, as `stage_trigger_run`). Audit trigger on
insert. The header totals equalling the sum of the lines is a service invariant tested later.

**Figures.** original = `project_budget` rows from the estimate; co = rows from approved CO lines; revised =
all `project_budget` rows for the code (original + CO + transfers, so a transfer shows in revised but not in the
other two); committed = open commitments (open PO lines and unbilled subcontract amounts; sources in areas 4 and 9,
the function returns 0 until those areas are approved, open item 2); cost to date = GL lines carrying the job and
the cost code, as recognized (area 10: a deferred line counts only as recognized); ETC from `job_forecast_line`.

**Services** (`forecast.py`; project scope):
- `update_forecast(context, project_id, lines, reason, expected_revision_no)` needs `job.forecast.edit`.
  In one write transaction: refuse when `expected_revision_no` is not the latest revision number (a conflict,
  returning the live data); insert the revision header and lines (the state before the change; `is_touched` on the
  changed codes); then update `job_forecast_line`.
- `transfer_budget(context, project_id, from_code, to_code, amount_cents, reason, expected_revision_no)` needs
  `job.budget.transfer`: same revision first, then two `project_budget` rows (minus on the source, plus on the
  target) with `revision_id` set (Q18). A transfer never changes the job total (service rule), and amount > 0.
- `get_forecast_history`, `get_forecast_revision`: need `project.view` plus `money.view` (area 18) because the
  figures are money; a Sales rep gets neither edit code and reads the budget only as their template allows.
- The forecast reason threshold is a control `company_settings.forecast_reason_over_cents` INTEGER NULL (Q19).
- WIP: the ETC as of a past date D is the "before" figure of the first revision after D (or the live line when
  none), so a past period's WIP can be recomputed exactly. `poc_snapshot.est_cost_to_complete_cents` stays the
  period's stored result. Area 13's `wip_current` compares the WIP entry's date with the newest revision's
  `changed_at`; `estimates_to_complete_updated` checks that every open job has a revision in the period (or a
  recorded "no change", open item 7).

Amendment 2026-11-19 (owner 11:20 PM, from area 15): `job_forecast_revision.kind` CHECK adds 'PCO'. **(Tagging by
`change_order_id`: Withdrawn 2026-11-23, owner 10:45 PM; Q37, §12.14.)**
`job_forecast_line` gains `change_order_id` INTEGER NULL (FK `change_order`), so a pending PCO's cost is its own line
by cost code. Moving a change order to PCO pending writes a revision of kind 'PCO' and the tagged lines; PCO rejected
or Void writes a revision that removes them; customer approval leaves the ETC unchanged, and the revised budget never
moves before customer approval (section 5.3 amendment). **(Withdrawn 2026-11-23, owner 10:45 PM: no 'PCO pending' status; a PCO is a field event; §12.14, Q37)**

Amendment 2026-11-20 (owner 12:05 AM, from area 15): `job_forecast_line` gains `change_order_id` INTEGER NULL (FK
`change_order`). The key (`project_id`, `cost_code_id`) is replaced by two partial unique indexes: UNIQUE
(`project_id`, `cost_code_id`) WHERE `change_order_id` IS NULL, and UNIQUE (`project_id`, `cost_code_id`,
`change_order_id`) WHERE `change_order_id` IS NOT NULL. `job_forecast_revision_line` gets the same: `change_order_id`
INTEGER NULL (FK `change_order`), and its key (`revision_id`, `cost_code_id`) is replaced by UNIQUE (`revision_id`,
`cost_code_id`) WHERE `change_order_id` IS NULL and UNIQUE (`revision_id`, `cost_code_id`, `change_order_id`) WHERE
`change_order_id` IS NOT NULL. Revision lines copy `change_order_id` from the forecast lines they snapshot.

### 6.4 How it lands, effects, tests

- Lands in `001_company.sql`: three tables, six triggers, audit triggers, the company setting, and the two
  permission codes (registry, area 18 amendment, section 8). `project_budget.revision_id` is asked of area 7.
- Effects: `permissions.py` registry gains two codes and the per-template lists; `tests/test_permissions_registry.py`
  and `tests/test_roles_schema.py` count codes (77 today per area 18) and change in the registry step.
- Tests to write later: every change writes exactly one revision first and the revision equals the table as it
  stood; update and delete refused on revisions; a stale `expected_revision_no` returns a conflict and changes
  nothing; a Sales rep and a Viewer are refused both calls; transfer total unchanged and the two touched lines
  marked; `fac = cost + etc` and variance CHECKs bite; a later cost posting does not alter an old revision; WIP as
  of a past date equals the old ETC; the history list reads the same after more changes.

---

## 7. The boundary with area 7 (jobs, budgets, cost codes)

| Owned by area 7 | Owned by area 8 |
|-----------------|-----------------|
| The `project` DDL as a whole: number, name, customer, PM, estimate link, dimensions mapping (J1), job creation service, original budget entry and budget rights | The columns on `project` listed in sections 1-3 (stage, close, site and target dates, manual %, billing type), which area 7 writes into the DDL; the services that change them (`job_stages.py`, `job_close.py`) |
| `project_budget` (original lines by cost code and manual budgets), `cost_code`, `project.revised_budget_cents` (derive or cache, F12), job cost and job reports | Change orders and field events; the CO approval service, which calls area 7's budget service to add the CO lines |
| `operating_plan_version` and the `job_budget` compare (area 17 reads `project_budget`) | `job_forecast_line`, revisions and their services; the transfer service, which calls area 7's budget service for the two rows |
| Job cost as recognized (area 10) and committed amounts via areas 4 and 9 | The forecast "committed" figure reads them through a function; WIP's ETC reads `job_forecast_line` |
| Job custom fields (area 16) | Service types, stages, stage history, triggers; job schedules and calendar items |

Asked of area 7 (listed so nothing is lost): `project_budget.revision_id` (nullable FK, Q18); `project.status`
dropped and `project.on_hold` added (Q6 C); cached `revised_budget_cents` (F12); the project's `row_version` (rule g); the seven close columns,
four site columns, two target dates, manual % columns, `billing_method`, `cost_destination`, `warranty_for_job_id`,
`source_case_id`.

Amendment 2026-11-20 (owner 2:25 AM, from area 7): area 7 section 1.3 writes the full `project` DDL with every column
asked above. Confirmed: `project.status` is dropped and `project.on_hold` added (Q6 C); `original_budget_cents` and
`revised_budget_cents` are dropped and every reader sums `project_budget` (area 7 Q5 A; F12 here);
`project_budget.revision_id` is a nullable FK (Q18). There is no draft flag: no draft jobs exist (area 7 Q1). A
Warranty uses `billing_method = 'Not billed'` and `cost_destination = 'Warranty line'`. It requires
`warranty_for_job_id` to name the original job. Costs post to the account mapped to `warranty_expense` in the open
period with no reserve and roll up to the original job's Warranty line. Goodwill uses 'Not billed' and 'Service
overhead', has no original job and resolves its account through `service_goodwill` (areas 7 §1.3 and 18 §4.2).

---

## 8. Controls, permissions, row version and audit

**New controls** (Company Settings > Controls; each default permissive, change logged with a reason, shown on the
Controls page): `stage_requirements_block` (0), `stage_backdate_days` (NULL), `schedule_at_risk_days` (1),
`schedule_late_days` (5), `schedule_pct_behind_points` (20), `baseline_reminder_days` (14) **(Withdrawn 2026-11-23 (owner 7:20 PM): §12.6)**,
`forecast_reason_over_cents` (NULL). They are `company_settings` columns now; area 21's scoped policy records may
move them. The crew label (`crew_label_singular`, `crew_label_plural`, default 'Crew' and 'Crews', section 4.3) is a
label setting, not a control.

**New permission codes** (placed by the amendment line now in area 18 section 2.4, dated 2026-11-19; none in
`AGENT_ALLOWED`; template names are area 18's shipped templates):

| Code | Meaning | Sensitive | Seeded to |
|------|---------|-----------|-----------|
| `job.forecast.edit` | Update the estimate to complete | no | Project manager and Controller templates, Admin, Master |
| `job.budget.transfer` | Move budget between cost codes | no | Project manager and Controller templates, Admin, Master |
| `job.schedule.edit` | Edit a job's schedule and calendar items (project scope) | no | Project manager template, Admin, Master; others read via `project.view` |
| `schedule.template.manage` | Create and edit schedule templates and crews ("PM settings") | no | Project manager template, Admin, Master |
| `service_type.manage` | Edit service types, stages, triggers and cancel reasons | no | Admin and Master only (in no cap) |
| `job.stage.backdate` | Date a stage move earlier than the control allows | yes | Controller template (sensitive column), Admin, Master |

Placement (area 18 section 2.4): the forecast and transfer codes and `job.stage.backdate` are in the Accountant cap
(so the Controller template holds them); the forecast and transfer codes and the two schedule codes are in the
Operations cap (so the Project manager template holds them). None is in the Sales rep cap, in a Sales rep level
default, or in View only. Existing `project.manage` covers moving stages, putting a job on hold, closing and
cancelling; `change_order.create` and `change_order.approve` keep their meaning.

**Row version (rule g4) and audit:**

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `service_type`, `service_stage`, `stage_trigger`, `job_cancel_reason`, `delay_reason`, `crew` | yes | yes |
| `schedule_template` | yes | yes |
| `schedule_template_version`, `_phase`, `_item` | insert-only (Q15) | no |
| `job_schedule`, `job_schedule_phase`, `job_schedule_task`, `calendar_item` | yes | yes |
| `job_schedule_baseline`, `_baseline_task`, `schedule_update`, `schedule_update_line` | insert-only | no |
| `change_order`, `change_order_line`, `field_event`, `pm_prompt`, `final_bill_request` | yes (CO lines locked once Approved) | yes |
| `project_stage_history`, `project_hold_history`, `stage_trigger_run` | insert-only | no |
| `job_forecast_line` | yes | no, token is the revision number (Q20) |
| `job_forecast_revision`, `job_forecast_revision_line` | insert-only | no |
| `calendar_item_notify` | insert and delete | no |

Corrected 2026-11-20 (consistency scan F4): Replace `job_cancel_reason` and `delay_reason` in this matrix with area 15's editable `reason_option` (kinds 'Job cancel' and 'Delay'), which has `row_version`; neither separate reason table is built. The job's case link is `project.source_case_id`, with no `case_job` table.

Every new table gets audit triggers (area 18). Reasons required (area 18's table gains these rows, amendment 2026-11-19): put a job on hold or take it off
(`project_hold_history.reason`), reopen a closed
job, a Back move, a correction, close with open checklist items, cancel (the reason list plus note), a forecast
change or transfer (per Q19), a CO rejection or void, a later forecast finish (delay reason), a control change.
No table in this area is derived or exempt from audit (`pm_prompt`, `calendar_item_notify` and the history tables
are audited; none is a per-user display preference), so area 18's derived and exempt lists are unchanged. Integrity
triggers in this area guard append-only and insert-only rows and the approved-CO lock; no trigger enforces
a workflow rule (H4).

---

## 9. Conflicts with decisions (all resolved by the owner's answers, 2026-11-19)

- **F1 Job type or service type.** S 11-15 3:30 PM renames job types to service types with one list for leads and
  jobs (RP4 built `service_type`). The 11-18 "job type stages" message and the mockup tab "Job types and custom
  fields" still say job types and name `job_type_stages`. This draft uses one `service_type` list; Q1. **Resolved: Q1 A: one `service_type` list.**

- **F2 Cancelled as off-ramp or outcome.** C109 lists fixed off-ramps Lost and Cancelled beside the Closed
  bookend; S 11-18 2:31 PM makes Cancelled an outcome of the Closed step with a reason. This draft follows the
  newer one; Lost stays a lead-side concept. Q2. **Resolved: Q2 A: Cancelled is an outcome of Closed; Lost is leads only.**

- **F3 Draft and publish or review panel.** C109 has "Unpublished changes: Review, Discard, Publish" for stages and
  triggers; the 11-18 R36 panel ("Review changes ... Apply / Cancel", which names service types and schedule
  templates) replaces it. Q3. **Resolved: Q3 A: changes apply through the R36 panel, no draft set.**

- **F4 Backdate lock default.** C34 proposes the control ON at 7 days; CLAUDE.md section 0 says controls start OFF
  or permissive. Q4. **Resolved: Q4 A: `stage_backdate_days`, empty by default.**

- **F5 Baseline timing and template scope.** C28 (baseline at signing) and C29 (one template per job type) were
  replaced by A 5:46 PM (Set baseline or first update) and C30 (independent templates, default per service type).
  The draft follows the newer; code and tests must cite the newer entries. **Resolved: Q12 A (baseline from the first update) and Q15 A (immutable template versions); the newer entries stand, and code and tests cite them.**

- **F6 Names.** A 4:19 PM ("a phase is a Gantt row", "Group") was replaced by the Phase > Task hierarchy; "schedule
  item" became "calendar item" (A 5:58 PM); "Lock baseline" became "Set baseline". Columns use the newer terms; the
  sources 11-17 4:19 PM item 1 and flow section 4 still show the older ones. **Resolved: Q14 A (every job has a schedule, Blank is one phase); the newer terms stand, no separate question.**

- **F7 Work week on the template.** The mockup shows Work week and Holidays selectors on each template; area 13 Q14 A
  makes one company work week and holiday list, and the task says to use them. Q11. **Resolved: Q11 A: the company's work week and holidays.**

- **F8 "Complete" as a state.** C108/C109 and A 11-15 make Complete a stage-like state before Closed; the baseline's
  `project.status` has Completed and Closed Out; the controller review (item 5) proposes a two-step close,
  "Financially complete" (late costs allowed with a reason during a holdback window) before Closed, not decided.
  Q6, Q7. **Resolved: Q6 C (no `project.status`; Open, Complete, Closed · outcome derive, plus an on-hold flag with history), Q7 A (Complete is a stage role) and Q8 A (no two-step close now).**

- **F9 Forecast reason.** S 11-16 says only a change over a threshold needs a note (no amount given); the 3:10 PM
  design has a `reason` on every revision. Q19. **Resolved: Q19 A: `forecast_reason_over_cents`, empty by default.**

- **F10 Optimistic token.** Rule g4 puts `row_version` on every editable table; the forecast calls take a
  `rowVersion` for a whole job's lines, which no single row carries. Q20. **Resolved: Q20 A: the latest revision number is the token.**

- **F11 Change order labels.** C21 statuses (Field event, Draft, Pending customer, Approved, Rejected) differ from
  the baseline CHECK (Draft, Submitted, Approved, Rejected, Void). The draft keeps the DB values and treats "Pending
  customer" as the label of Submitted and "Field event" as a `field_event` row. **Resolved: Q16 A and Q17 A: DB values kept, labels differ, approved lines locked, approval writes a revision.**

- **F12 Cached budget.** `project.revised_budget_cents` (`:270`) is a stored total that area 7 may derive instead; if
  it stays, every CO approval and transfer must update it in the same transaction. Area 7's call. **Resolved: Q18 A (one budget table); the cached `revised_budget_cents` stays area 7's call (section 7).**

- **F13 Delay reason is required.** A 5:35 PM item 4 requires a reason when a forecast finish moves later. CLAUDE.md
  section 0 asks that a check that could be optional be a setting. It is an owner decision, so the draft keeps it
  required and says so here. **Resolved: Q10 A: a seeded company table of reasons; a later finish still needs one, as the owner decided.**

- **F14 Proposed codes.** C29's `settings.schedule` and C34's `pipeline.backdate` are PROPOSED; the owner's words are
  "PM settings", "Edit job schedules" and (C34) a manager or Admin. The codes in section 8 are proposals. **Resolved: Q4 A and the placement in section 8 and area 18's amendment: `job.stage.backdate` and the other codes are named there.**

- **F15 Lead and job stage history.** C34 says "deal" and "one project, one history"; X 5 and area 17 name a job
  history, while area 15 will need a lead history. This draft makes a job-only table; Q21. **Resolved: Q21 A: `project_stage_history` is for jobs; area 15 builds its own twin.**

- **F16 Calendar items carry both a phase and a stage.** A 11-17 requires `phase_id`; A 11-18 adds an optional
  `stage_id`. Both are kept; the stage field is a tag, the phase is the parent. **Resolved: Q14 A: both kept, the phase is the parent and the stage a tag.** **Withdrawn 2026-11-23 (owner 1:54 AM): the stage is the parent of the phase; the calendar item's own stage tag is Q26 in §12.1.**

---

## 10. Questions for the owner: answers recorded (2026-11-19)

The owner answered A to Q1-Q5, Q7-Q12 and Q14-Q24, C to Q6, and A with an added label setting to Q13. Each question is
shown as asked, with the answer under it. The design in sections 0-8 follows the answers. One addition from the owner
(2026-11-19 8:40 PM) follows Q24.

Q1. **One list for leads and jobs?** A (recommended): one `service_type` list; the job's settings tab is the same
list shown with delivery stages (F1). B: a separate `job_type` list with its own stages for jobs.
**Answer: A.**

Q2. **Cancelled.** A (recommended): Cancelled is an outcome of the Closed stage, with a reason; Lost is leads only (F2).
B: Cancelled is also a separate off-ramp stage on the path.
**Answer: A.**

Q3. **Editing stages and triggers.** A (recommended): changes apply through the R36 Review changes panel and are
audit-logged; no draft set. B: keep a draft set with Publish and Discard (needs a version table for stages and
triggers).
**Answer: A.**

Q4. **Backdating a stage move.** A (recommended): control `stage_backdate_days`, empty by default (anyone can
backdate; always recorded and shown). B: default 7 days, earlier dates need `job.stage.backdate` (C34 as proposed).
**Answer: A.**

Q5. **Reopening a Closed job.** A (recommended): allowed by a Back move out of Closed with a reason (`project.manage`),
clears the close columns, history keeps the outcome. B: Closed is final; a new job or a correction is the only way.
**Answer: A.**

Q6. **`project.status`.** A (recommended): drop it; "Open", "Complete" and "Closed · outcome" derive from the stage
and outcome; no on-hold state. B: keep `status` and add a status history table (X 5 "status history"). C: drop it
but add an `on_hold` flag with history.
**Answer: C. Drop `project.status`; Open, Complete and Closed · outcome derive from the stage and outcome. Add an on-hold flag on the job with an append-only on-hold history (from, to, reason, by, at); putting a job on hold or taking it off needs a reason. Built as `project.on_hold` and `project_hold_history` (section 3.1).**

Q7. **Complete.** A (recommended): a stage role `Complete` between the last delivery stage and Closed; `completed_on`
is the effective date of the move into it. B: a separate PM flag on the job.
**Answer: A.**

Q8. **Two-step close "Financially complete" (controller item 5).** A (recommended): not now; Complete already allows
costs and the checklist warns. B: build a holdback window with a reason for late costs before Closed.
**Answer: A.**

Q9. **Job site and target dates (X 5).** A (recommended): columns on `project`, copied from the contract, editable,
changes in the audit log. B: link to a site record from the customer (area 5). C: no columns, read the contract's
dates and the contact address.
**Answer: A.**

Q10. **Delay reasons.** A (recommended): a company table seeded with the eight reasons (add, hide, never delete a
shipped one). B: a fixed CHECK list.
**Answer: A.**

Q11. **Work week and holidays on schedules.** A (recommended): the company's (area 13); the template selectors show
them read only. B: each template can override.
**Answer: A.**

Q12. **Baseline set by the first update.** A (recommended): baseline v1 is the forecast dates just before that
update's changes. B: the dates after the update.
**Answer: A.** **Withdrawn 2026-11-23 (owner 7:20 PM, Q27: baseline locked at signing; a CO or a granted extension moves the target): §12.6. "Moves the target" Withdrawn 2026-11-23 (owner 8:30 PM): a CO moves the forecast, §12.10.**

Q13. **Crews table.** A (recommended): defined here (`crew`) and reused by area 15. B: wait for area 15.
**Answer: A, plus a label: the crew table is defined here and reused by area 15; a company setting holds the crew name, singular and plural (default "Crew" / "Crews"), used by every screen, report and export label (section 4.3).**

Q14. **Blank schedule.** A (recommended): every job has a schedule; Blank is one phase "Project" with the two
milestones. B: a job may have no schedule and no calendar items.
**Answer: A.**

Q15. **Template versions immutable by trigger.** A (recommended): version, phase and item rows are insert-only.
B: plain rows kept by the service only.
**Answer: A.**

Q16. **Change order approval and forecast history.** A (recommended): approval writes a revision of kind 'Change
order' (the budget table as it stood before). B: only ETC updates and transfers write revisions.
**Answer: A.**

Q17. **Approved CO lines locked in the database.** A (recommended): backstop triggers refuse changes to an approved
CO's lines and header. B: the service only.
**Answer: A.**

Q18. **Where a budget transfer lives.** A (recommended): two `project_budget` rows with a `revision_id`, so every
reader sums one table. B: a separate `job_budget_transfer` table that readers must add.
**Answer: A.**

Q19. **Reason on a forecast change.** A (recommended): `forecast_reason_over_cents` empty by default (a reason is
always offered, never forced); the owner can set a threshold. B: default 0 (every change needs a reason). C: always
required, no setting.
**Answer: A.**

Q20. **Stale-save token for the forecast calls.** A (recommended): the latest revision number the page saw.
B: a `row_version` on `project`, which also changes on unrelated edits. C: a `row_version` on every
`job_forecast_line`, and every line sent with its own.
**Answer: A.**

Q21. **Lead history.** A (recommended): `project_stage_history` is for jobs; area 15 builds its own twin with the same
rules. B: one shared table with a record type.
**Answer: A.**

Q22. **Monthly PM forecast sign-off (controller item 7).** A (recommended): not now; area 13's close checks cover the
PM task. B: add a `job_forecast_signoff` (job, period, signed by, at).
**Answer: A.**

Q23. **PM prompts.** A (recommended): store them in `pm_prompt` (snooze, one per job and stage). B: derive them each
time, with no snooze.
**Answer: A.**

Q24. **Final bill requests.** A (recommended): the table now, sending later with area 20. B: leave the whole item for
areas 3 and 9.
**Answer: A.**

Addition (owner 2026-11-19 8:40 PM, `shared_decisions` "T&M time source"): `service_type.rate_card_id` (nullable; none
means the company rate card). The `rate_card` tables belong to area 6; until it adds them the column is a plain
integer (section 1.3).

---

Inbox inputs 2026-11-22 (v1.1 field scope; owner 12:41 PM, amended 12:45 PM; to_planning 2026-11-22 "v1.1 field
records approved"; to_ux_research same date). Inputs for the v1.1 pass, not decided schema; wireframes first. Keep
everything generic: crew types, weather, delay causes and punch/inspection categories are company lists. (1) Daily
log: one per job per day with crew and sub entries and hours, weather (company list), work done, linked photos
(attached as files on the desktop) and delays. (2) Delay log: cause (company list), days, source (weather, owner,
vendor, other), linked to the daily log and to the change order that grants a time extension (§5). (3) Assignments:
crew and subs on schedule phases and calendar items, with a cross-job "who's where tomorrow" board. (4) Look-ahead: a
2–3 week view of existing phases only; baseline and slip unchanged; no new baseline. (5) Punch and inspection items:
job, type (company list), assignee, status, pass/fail and photo; a Company control
`block_final_billing_with_open_punch_items` (OFF by default) blocks Final billing while items are open **(Withdrawn 2026-11-23, owner 10:45 PM, Q34 A: the control is retired; Area 8 §12.14)** (Area 5 and
Area 4 handoff). (6) Field material request: Area 9 (next_step). Job page (12:45 PM): operations roles (PM, field,
operations) open the job on the existing Schedule tab; finance roles keep the overview; default tab by role comes from
the Area 18 access model. Nothing phone-related until the cloud version (phone capture, photo location, offline sync,
phone app, voice-to-text). (Decided 2026-11-22 by the owner except "which inspections are standard": §12.2; answered 2026-11-24, §12.16.) Open for the wireframe review: whether the daily log replaces or feeds the status update;
who can create a material request; which inspections are standard; whether a delay suggests a time-extension change
order.

## 11. Open items (not decisions)

1. Controller items not decided and not drafted: cost type on budgets and actuals (area 7), subcontracts, lien
   waivers and compliance holds (area 4), T&M tickets and PCOs beyond the field event (item 3), the flag to exclude
   uninstalled materials from cost-to-cost progress (`poc_snapshot.excluded_cost_cents` exists, area 10), prevailing
   wage and certified payroll, SOV to cost code mapping (`contract_line.cost_code_id` exists), the profit fade
   report. They need decision items before v1.1 is designed.
2. "Committed" in the forecast figures needs the PO and subcontract tables (areas 9 and 4); returns 0 until then.
3. `crew` and the activity "who" columns are shared with area 15; names may move when it is drafted.
4. The payment-schedule milestone table (area 6), the subcontract table (area 4) and `service_case` (area 15) are
   referenced by plain integer columns until they exist; their foreign keys are added in the same baseline pass.
5. Import schedule (CSV or Microsoft Project XML, C28) is a service that must follow the import-origin rule; not
   designed here.
6. Area 18: confirm attachments can be copied from a field event to a CO and that "proof of approval" is an
   attachment kind. The amendment line for the codes and reasons is written (area 18 section 2.4, 2026-11-19).
7. Whether "no change this month" for the `estimates_to_complete_updated` check needs its own record or a revision
   with no changed lines; settled when area 13's check is built.
8. Area 21: the company calendar query reads job tasks, milestones and `calendar_item` **(Withdrawn 2026-11-23 (owner 7:10 PM): §12.5)**; the needs-attention items
   (schedule not updated in 7 days, milestone missed) are computed.
9. The variance sign (positive means under budget) and the committed definition are to be confirmed against the
   mockup's budget table when design batch D is built.
10. Area 17 `src_job_stages`, `src_jobs`, `src_jobs_cancelled` read `project_stage_history` and `project`; `src_cases`
    needs area 15. `custom_field_def` job type scoping and "shown from stage" are area 16's.
11. WIP recalculation and the monthly WIP service remain area 7/10; this area supplies ETC by date.
12. (Closed 2026-11-19, owner.) What an on-hold job does: a label and warnings only, no posting refused; the rule is in
    section 3.1.
13. `rate_card` and its tables (area 6) and the foreign key from `service_type.rate_card_id`.
14. The warning on costs, POs and billing for a held job is built by the services of areas 3, 4, 5 and 9 (they read
    `project.on_hold`); the wording names the hold and its reason. Tests belong to those services.

---

## 12. Owner decisions 2026-11-22 and 2026-11-23 (dated amendments)

This area is approved: nothing above is rewritten; replaced text is marked "Withdrawn" beside it, and conflicts are
flagged here.

### 12.1 Schedule hierarchy is Stage > Phase > Task (Decided 2026-11-23, owner 1:54 AM and 1:58 AM)

Source: inbox 2026-11-23 1:54 AM "schedule hierarchy is Stage > Phase > Task (owner)", with the owner's 1:58 AM answer.

- **Amendment 2026-11-23.** A job's work is organised as **Stage > Phase > Task**. Stage = the job type's stages
  (`service_stage`, §1), from contract signed through closeout, including the administrative stages before and after
  construction. A **milestone is a special task that marks the completion of a phase or a stage.** This replaces §4.2
  "Hierarchy Phase > Task" and F16 / Q14 A ("the phase is the parent and the stage a tag"), both marked withdrawn.
- **Amendment 2026-11-23 (1:58 AM answer).** Reaching a stage-completion milestone does **not** move the stage. It
  prompts the PM to click "Mark <stage> complete", and the current stage on the stage path turns gold to show its
  milestone is reached. No new column: the state is read from the stage's completion milestone (`actual_finish` set)
  while the job is still in that stage. The stage moves only through §1's stage-history service, as approved.
- **Schema effects (consequences of the decision, built in the 2.9 pass):**
  1. `job_schedule_phase` and `schedule_template_phase` gain `stage_id` INTEGER NOT NULL REFERENCES `service_stage`. **Withdrawn 2026-11-23 (owner 7:10 PM, work tree): §12.5.**
  2. Milestones stay `kind = 'Milestone'` and record what they complete: `completes` TEXT CHECK IN ('Phase',
     'Stage'), NULL for an ordinary task; a stage-completion milestone sits in a phase of that stage. At most one
     stage-completion milestone per stage per job schedule (service rule). **`completes`: Withdrawn 2026-11-23 (owner 7:10 PM): a milestone row names the node it closes, `closes_node_id`, §12.5.**
  3. Schedule templates belong to a service type: `schedule_template.service_type_id` NOT NULL, because their phases
     point at that type's stages. **Conflict flagged:** this reverses C30 ("templates are independent of service
     type"; the §4.2 row is marked withdrawn). A service type still names its default template (§4.2), now one of its
     own. **The C30 reversal is confirmed by the owner 2026-11-23 (7:10 PM: one template per job type); §12.5.**
  4. The optional `stage_id` tag on `job_schedule_task`, `schedule_template_item` and `calendar_item` is Q25 and Q26
     below. **Answered 2026-11-23 (owner 7:10 PM): no stage tag anywhere; the stage is the ancestor in the tree,
     §12.5.**
  5. Sample data (design run, no schema): the mockup Gantt groups (Pre-construction / Installation / Closeout) hold
     items named like stages (Site survey, Permitting); the mockups regroup them under stages.
- Tests: `test_phase_requires_stage_of_jobs_service_type`,
  `test_template_belongs_to_service_type_and_phases_to_its_stages`,
  `test_stage_completion_milestone_prompts_pm_and_does_not_move_stage`,
  `test_stage_milestone_reached_state_reads_actual_finish_while_in_stage`,
  `test_one_stage_completion_milestone_per_stage`.

### 12.2 v1.1 field records: owner decisions of 2026-11-22 (design chat gap list)

Source: inbox 2026-11-22 "from design chat: CRM and Field gap list ... with 11/22 owner decisions". These settle the
§10 inbox-input questions except one. The field records stay inputs (not decided schema) until the wireframes are
approved.

- **The daily log feeds the status update** **(Withdrawn 2026-11-23, owner 8:15 PM, Q32: the daily log's "Feeds the
  status update" section is removed; §12.11)** (it does not replace it): submitted daily log lines are offered to the
  next status update.
- **The PM creates material requests** (Area 9 entry in next_step).
- **A time extension does not need a change order, but may have one.** The delay log's change-order link stays
  optional. **Conflict flagged:** §4.2 says baseline versions after the first come only from a change order
  ("Baselines are versioned; each new version references the change order"). Q27 below asks what a time extension
  without a change order moves. **Decided 2026-11-23 (owner 7:20 PM, Q27): §12.6.**
- **Delay log Action column** opens the field event / change order wizard ("File new event" is the existing
  "+ Field event", §5). Screen only.
- **The weather forecast stays on.** The daily log and look-ahead read the forecast for the job site address
  (`project.site_*`, Q9 A). A company setting turns it on; fetching it is a network connection, handed to Area 20.
- **Crew on site** is one searchable picker over crews (internal, no vendor code; §4 crews) and subcontractors
  (vendors, shown with their vendor code). Crews are not held as vendors. When the field records are designed, a
  daily-log crew line names either a `crew_id` or a vendor `contact_id` (exactly one).
- **A Manager cannot override the final-billing block** (`block_final_billing_with_open_punch_items`, OFF by
  default): Area 18 §8.5 amendment. **(Withdrawn 2026-11-23, owner 10:45 PM, Q34 A: the control is retired; Area 8 §12.14)**
- **Still open for the wireframe review:** which inspections are standard. **(Answered 2026-11-24, owner 12:04 AM: a
  company list per job type; §12.16.)**
- The Field role and its nav (about five items) from the 12:41 PM message are owned by Area 18 §8.5.

### 12.3 Material forecast page (owner request, inbox 2026-11-23 2:20 AM)

A view only, no new table (mockup `field-material-forecast.html`, Operations menu > All jobs). It reads the first
task start of each job schedule (`job_schedule_task` forecast dates), `project.target_start_on` (Q9 A), the Material
`estimate_cost_line` rows of the accepted revision (signed jobs) or the latest sent revision (leads, only with the
"include sent estimates" filter; Area 6), stock available (on hand less reserved; Area 9) and open PO quantity by
expected date (Area 9). Rule shown on the page: surplus or deficit = available now + open PO quantity expected by the
start date - needed by earlier starts in the view - needed on the date. Gaps handed on: `lead.estimated_start_on`
(Area 15 §12 input; **Withdrawn 2026-11-23 (owner 7:28 PM, Area 15 Q24): leads get a Requested completion date, not
a start; lead demand placement is Q30, §12.9; "Requested completion" Withdrawn 2026-11-23 (owner 8:30 PM):
Estimated completion, §12.10**) and `purchase_order.expected_on` with an optional per-line override (Area 9, next_step). The owner
asks that every job carry an estimated start date: Q28. **(Withdrawn 2026-11-24, owner 11:58 PM 11/23, Q28 revisited: the start date is optional; planned completion is required; Area 8 §12.16)**

### 12.4 Questions for Mark (recommended option first)

- **Q25. The stage tag on tasks and template items (hierarchy item 2).** **Superseded 2026-11-23 (owner 7:10 PM): the
  work tree, §12.5. Options A and B Withdrawn 2026-11-23.**
  A (recommended): drop `job_schedule_task.stage_id` and `schedule_template_item.stage_id`; a task's stage is its
  phase's stage. Example: task "Permitting" in phase "Permits" under stage "Pre-construction" reads Pre-construction.
  B: keep the column, filled by the service from the phase and read-only.
- **Q26. The stage on calendar items (hierarchy item 5).** **Superseded 2026-11-23 (owner 7:10 PM): a calendar item is an
  activity pointing to a tree node, §12.5. Options A and B Withdrawn 2026-11-23.**
  A (recommended): drop `calendar_item.stage_id`; the stage comes from the required phase. The drawer shows Stage,
  then Phase filtered by stage. Example: an inspection item on phase "Electrical" shows stage "Installation".
  B: keep an optional stage tag that may differ from the phase's stage.
- **Q27. A time extension without a change order (11/22 decision vs §4.2).** **Answered 2026-11-23 (owner 7:20 PM):
  three dates; option A ("baseline only by CO") Withdrawn 2026-11-23. §12.6.**
  A (recommended): it moves the forecast finish and the job's `target_finish_on` (reason from the delay, logged); the
  baseline still changes only through a change order, so schedule variance shows the slip. Example: 3 rain days
  move the target finish from 12/04 to 12/09; the baseline finish stays 12/04. **Withdrawn 2026-11-23 (owner 8:30 PM): §12.10.**
  B: it creates a new baseline version without a change order, with a reason and the delay link.
- **Q28. Every job carries an estimated start date (material forecast).** **Answered 2026-11-23 (owner 7:23 PM): A.
  §12.6.** **Revisited 2026-11-24 (owner 11:58 PM 11/23): A Withdrawn; planned completion required, start optional;
  §12.16.**
  A (recommended): `project.target_start_on` becomes required when a job is created, copied from the contract's start
  date (Q9 A) or typed on New job, editable and logged. Example: a New job without a lead must enter a start date.
  Cross-area: the column is in Area 7's `project` DDL (approved, §1 table); A adds an amendment line there.
  B: it stays optional; the forecast lists jobs with no start date under "No start date".

### 12.5 One work tree and one activity table (Decided 2026-11-23, owner)

Source: inbox 2026-11-23 1:30 PM "from design chat: schedule tree, tasks without %, and one activity table" (items
1–3 decided in the design chat 12:39–1:27 PM; item 4 written up as a proposal) and the owner's restatement in
`owner_decisions_2026-11-22.md`, "Owner answer to Area 8 Q25 and Q26" (7:10 PM), which decides item 4's core (one
activity table, each row pointing to a tree node). This replaces §12.1's schema effects 1, 2 and 4 (marked
withdrawn there) and Q25/Q26. §12.1's milestone prompt (the stage turns gold; the PM clicks "Mark <stage>
complete"; the stage never moves by itself) stands.

**Decided.**
- **Four levels: Contract stage > Stage > Phase > Task.** Contract stages are pre-templated: **Sales,
  Pre-construction, Construction, Post-construction**. Stages are the job type's stages; phases group tasks; tasks
  are the smallest unit. A **milestone** is a task row flagged as one; it marks the completion of a phase or a stage.
- **One self-referencing tree table per side**: `work_template_node` (the job type's template) and `job_work_node`
  (copied per job at contract signing). Each row has parent, level, name, order and the milestone flag. **Level
  names are a company setting** (default Contract stage / Stage / Phase / Task). One template per job type
  (Solar, Reroof, Remodel and General seeded), which confirms the C30 reversal flagged in §12.1.
- **Leads use the same tree:** the Sales contract stage holds the sales stages, so a lead and a job still share one
  pipeline (Area 15 §1.4).
- **Tasks have no %.** A task is Not started, In progress (actual start set) or Done (actual finish set).
  `pct_complete` comes off the task and off `schedule_update_line`. Phase, stage and contract stage % complete are
  computed from the tasks under them, **weighted by working days** (forecast start to finish on the company work
  week, Q11 A; milestones and activities excluded), shown with "n of m tasks". `schedule_pct_behind_points`
  compares at phase level. Revenue % complete (cost-to-cost, C28) is unaffected.
- **Task start and finish create activities.** Setting a task's actual start or finish creates a Work started or
  Work completed activity linked to the task node, the crew or vendor and the date, and asks for a note. The note
  is optional; a Company control `require_note_on_task_start_finish` (PROPOSED name, **OFF by default**, Controls
  page, logged) requires it. The dates stay on the task; a later correction logs a correction activity.
- **Things that happen are rows in one `activity` table** with a type, each pointing to a node in the tree:
  calendar items, punch items, delays, extra work, notes, completions. The Gantt keeps its own schedule table
  (forecast and actual dates, predecessors), whose tasks link to their place in the tree. The Gantt and stages stay
  in the tree; Punch list, Delay log, Field events, Daily log, job calendar and the Schedule view (renamed from
  Look-ahead) are views, not tables. One entry point, "+ Log", with the type as the first field.

**Proposed schema (built in the 2.9 pass).**
- `work_template_node(node_id PK, version_id NOT NULL FK schedule_template_version, parent_id NULL FK
  work_template_node, level INTEGER NOT NULL CHECK 1-4, name NOT NULL, sort_order, is_milestone INTEGER NOT NULL
  DEFAULT 0 CHECK (0, 1), closes_node_id NULL FK work_template_node, work_days, pred_node_id NULL FK, pred_type CHECK
  (NULL or IN ('FS', 'SS')), lag_work_days NOT NULL DEFAULT 0, default_crew_id, default_vendor_id, target_days,
  guidance, can_skip, stage_role)`. CHECKs: `parent_id IS NULL` exactly when `level = 1`; only level 4 has
  `work_days`, a predecessor and a default assignee; only a milestone has `closes_node_id`; `stage_role` (the
  approved `service_stage.stage_role` values plus 'Lost', Area 15 §1.4) and `can_skip` only on level 2. The service
  checks that a parent is one level up, that a milestone closes one of its own ancestors (phase or stage), and that
  there are no loops (H4: rules in the service, not triggers). Template versions stay immutable (Q15 A).
- `job_work_node`: the same shape plus `project_id` NOT NULL, `source_node_id` FK work_template_node and
  `row_version`; copied from the accepted template version at signing.
- `job_schedule_task` stays as the Gantt's table, one row per level-4 node: `node_id` INTEGER NOT NULL UNIQUE FK
  job_work_node, forecast and actual start and finish, predecessor, lag, crew, vendor or subcontract,
  `payment_milestone_id` (milestones), notes, `row_version`. It loses `phase_id`, `stage_id`, `kind`, `name`,
  `sort_order` and `pct_complete` (from the node, or gone). Baseline task lines and update lines keep pointing at
  `task_id`.
- **Dropped:** `schedule_template_phase`, `schedule_template_item`, `job_schedule_phase`, `calendar_item` and
  `calendar_item_notify` (attendees are `activity_attendee`), and **`service_stage` as the stage list**: the stage
  is a level-2 node. Consequences, built in the same pass: `project.service_stage_id` becomes
  `current_stage_node_id` FK job_work_node; `project_stage_history` from/to point at `job_work_node`; `stage_trigger`
  points at the template's level-2 node; a lead's stage and `lead_stage_history` point at the Sales level-2 nodes of
  the job type's template (Area 15 amendment, §12.5 is the owner). `schedule_template` gains `service_type_id` NOT
  NULL UNIQUE (one per type), and `service_type.default_schedule_template_id` is withdrawn with it (lead default).
- `company_settings.work_level1_name` to `work_level4_name` TEXT NOT NULL with the defaults above.
- **`activity` (Area 15 §2.3 table) gains:** `work_node_id` INTEGER FK job_work_node (a phase or task; required for
  field types, service rule), `related_activity_id` FK activity (cause and effect: punch, then delay, then extra
  work), `vendor_contact_id`, and `verified_at`/`verified_by` (status Open, Done, then Verified; both or neither, and
  only after done). `activity_type` gains behaviour flags beside `is_appointment`: `needs_verify`,
  `blocks_final_billing` **(Withdrawn 2026-11-23, owner 10:45 PM, Q34 A: the control is retired; Area 8 §12.14)** (read only while the Company control `block_final_billing_with_open_punch_items` is ON,
  default OFF, §12.2), `moves_forecast` (a Delay writes a `schedule_update` on the task it affects; the baseline is
  unchanged) and `can_become_change_order` (Extra work). Seeded field types: Calendar item, Inspection, Punch, Delay,
  Extra work, Note, Work started, Work completed (sales types unchanged). Type-specific fields sit in small 1:1
  tables: `punch_detail` (priority, from inspection), `delay_detail` (cause from `reason_option` kind 'Delay' with
  the new "Rework / punch", working days lost, notice to owner) and `extra_work_detail` (customer signed, time
  extension, change order link). Activity photos are attachments (Area 18 §3).
- **Default stages per job type (seeded, from the 1:30 PM message):** Solar: Pre-construction = Site survey,
  Design & engineering, Permitting, Ready to install; Construction = Installation, Inspection; Post-construction =
  Interconnection / PTO, Complete, Final billing. Reroof and remodel: Pre-construction = Pre-construction,
  Mobilization; Construction = In progress, Punch list; Post-construction = (Substantial completion,) Complete,
  Final billing. "Contract signed" closes Sales; Closed ends Post-construction. Companies can move any stage.
  Roll-ups read the tree with a recursive query (standard SQL `WITH RECURSIVE`, H5).
- §10's v1.1 field records (punch and inspection items, the delay log, field events of the field plan) are these
  activity types, not separate tables. `field_event` (§5, numbered FE-####, with cost lines and the CO link) is
  Q32.

**Lead defaults (owner may revise).** Work-days weighting is a one-line switch to task count. Stage identity across
template versions: each level-2 node carries a stable `stage_key` copied to new versions, so leads and stage
triggers on an older version still resolve. The mockups `job-calendar.html` (own form with Stage) and the unused
calendar drawer in `pages/job-detail.ops.js` are design queue items, not schema.

Tests: `test_work_tree_parent_is_one_level_up_and_level1_has_no_parent`,
`test_only_task_rows_carry_dates_work_days_and_predecessors`,
`test_milestone_closes_one_of_its_own_ancestors`, `test_job_work_tree_copied_from_template_at_signing`,
`test_one_schedule_task_per_task_node`, `test_task_status_from_actual_start_and_finish_without_pct`,
`test_phase_and_stage_pct_rollup_weighted_by_working_days_excludes_milestones`,
`test_task_start_and_finish_create_activities_and_note_required_only_with_control`,
`test_field_activity_points_to_phase_or_task_node`, `test_delay_activity_writes_schedule_update_not_baseline`,
`test_level_names_follow_company_setting`, `test_lead_stage_points_at_sales_node_of_job_type_template`.

### 12.6 Three schedule dates, the start date and Requested completion (Decided 2026-11-23, owner)

**Revised 2026-11-23 (owner 8:30 PM): the target, forecast, extension, status and Requested completion text below is
withdrawn and replaced by §12.10; the baseline and Q28 parts stand.**

Source: `owner_decisions_2026-11-22.md`, "Owner answer to Area 8 Q27" (7:20 PM), "... Q28" (7:23 PM) and "Owner
answer to Area 15 Q24" (7:28 PM).

- **Amendment 2026-11-23 (Q27).** A job keeps **three** schedule dates:
  - **Baseline:** the dates on the signed contract, **locked at signing**; later estimate edits do not change it.
    One baseline per job, never versioned **(Refined 2026-11-24, owner 1:14 AM: the task baseline can be rebuilt with a required reason, as a new version; §12.18)**. `job_schedule_baseline` keeps one row per schedule (version 1,
    `change_order_id` NULL), written at signing with its task lines from the schedule built then; insert-only, as
    approved. The Set baseline button, the first-update rule (Q12) and the `baseline_reminder_days` setting are
    withdrawn.
  - **Target finish** **(Withdrawn 2026-11-23, owner 8:30 PM: the target is a PM-editable date, §12.10)**: the date owed to the customer now = baseline finish + the work days of approved change
    orders + extensions the customer granted. A granted extension is recorded with a reason. Derived in one
    function, never typed, and shown with its parts ("Baseline 3/20 + 5 granted rain work days = 3/27"). **Withdrawn 2026-11-23 (owner 8:30 PM): §12.10.**
  - **Forecast:** the predicted real finish from the schedule tasks; a reschedule on the job calendar or the Gantt
    updates it. It includes delays the customer has not agreed to. **Revised 2026-11-23 (owner 8:30 PM): forecast =
    baseline + approved CO time + delays + reschedules, §12.10.**
  - Example: baseline 3/20; the customer grants 5 work days for rain, so the target is 3/27; the crew is behind, so the
    forecast is 3/31, late against the target. **Withdrawn 2026-11-23 (owner 8:30 PM): §12.10.**
- **New record (proposed): `schedule_extension`** (`extension_id` PK, `project_id` NOT NULL, `work_days` INTEGER
  NOT NULL CHECK > 0, `granted_on` date, `reason_id` FK `reason_option` kind 'Delay' with its label, `reason_text`
  (10 typed characters only for Other, Area 18 §8.7), optional `granted_by_contact_id` and `delay_activity_id`,
  `recorded_by`, `recorded_at`, and `voided_at`/`voided_by`/`void_reason`). Insert-only except the void columns. An
  extension that comes with a change order is the CO's `days_added`, not a second row (the 11/22 rule "may have a
  CO" without counting it twice). Permission: `job.schedule.edit` (project scope). **Withdrawn 2026-11-23 (owner 8:30 PM): a granted extension is a $0 change order with days; §12.10.**
- **Change order approval** with days moves the target finish (by `days_added`); it no longer writes baseline
  v(n+1) (§5 step 2 marked withdrawn). The "Extend schedule" step stays as the PM's choice of which tasks move in the
  forecast. **Withdrawn 2026-11-23 (owner 8:30 PM): §12.10.**
- **Status** **(Withdrawn 2026-11-23, owner 8:30 PM: Q33, §12.10)** compares the forecast finish with the target finish (Late, At risk, On track by the existing
  `schedule_at_risk_days` and `schedule_late_days`), and the target with the baseline shows the granted slip.
  `project.target_finish_on` as an editable copy is withdrawn (§3.1 row) and dropped (lead default, owner may revise). **Withdrawn 2026-11-23 (owner 8:30 PM): §12.10.**
- **Amendment 2026-11-23 (Q28 A).** **(Withdrawn 2026-11-24, owner 11:58 PM 11/23, Q28 revisited: the start date is optional; planned completion is required; Area 8 §12.16)** `project.target_start_on` is **required when the job is created** (at contract
  signing): no job without a start date (an owner decision, not a control), so the baseline and forecast can be built. "Start" means the first day of
  work on site, the first task of the Construction contract stage **("first task of the Construction contract stage"
  Withdrawn 2026-11-23, owner 8:15 PM, Q31: no stage is special; §12.11)** (owner 7:28 PM), not the signing date. Example:
  North field array signs 12/1; the PM enters a start of 1/5. Q31 asks how the build places Pre-construction tasks.
  **(Answered 2026-11-23, owner 8:15 PM: §12.11.)**
- **Requested completion (Area 15 Q24, owner 7:28 PM).** The lead's optional Requested completion (Area 15 §12.1)
  is copied at signing to `project.requested_completion_on` (TEXT date, NULL allowed, editable, logged). The job
  shows a **warning** (never a block) when the forecast finish is after it. Example: requested completion 12/31,
  forecast 1/9: the job shows the warning. **Withdrawn 2026-11-23 (owner 8:30 PM): Estimated completion, §12.10.**
- **Area 7 amendment lines (same pass):** **(Withdrawn 2026-11-24, owner 11:58 PM 11/23, Q28 revisited: the start date is optional; planned completion is required; Area 8 §12.16)** `project.target_start_on` NOT NULL and the new
  `project.requested_completion_on` are recorded in Area 7 §14 (the `project` DDL). **(`requested_completion_on`
  Withdrawn 2026-11-23 (owner 8:30 PM): §12.10.)**
- Tests: `test_baseline_set_at_signing_from_contract_dates_and_never_versioned`, **(task baseline: rebuild with a reason, §12.18)**
  `test_target_finish_is_baseline_plus_approved_co_days_plus_granted_extensions`,
  `test_extension_with_change_order_counts_once`, `test_reschedule_moves_forecast_not_target_or_baseline`,
  `test_status_compares_forecast_with_target`, `test_job_creation_refused_without_start_date`,
  `test_requested_completion_copied_at_signing_and_warns_when_forecast_later`. **Withdrawn 2026-11-23 (owner 8:30 PM):
  the target, extension, status and requested-completion tests; replacements in §12.10.**

### 12.7 Conflicts with earlier decisions (flagged; the owner's 11/23 answers win)

- **Baseline timing:** Q27 returns to C28 ("baseline at signing"), replacing A 5:46 PM and Q12 A (Set baseline or
  first update; F5 above). Code and tests cite the 11/23 answer.
- **Change order days:** §5's baseline v(n+1) on approval (flow B5) is replaced by the target finish. **"Target"
  Withdrawn 2026-11-23 (owner 8:30 PM): replaced by the forecast, §12.10.**
- **C30:** confirmed reversed (one template per job type).
- **`service_stage`:** approved Areas 8 §1 and 15 §1.4 build on it (stage roles, history, triggers, lead stages);
  the tree replaces it as the stage list (consequences in §12.5). Area 15 gets an amendment line pointing here.
- **`field_event`:** the design chat's proposal also replaces it with an activity type, but §5's approved
  `field_event` carries a number, cost lines and the CO link. Not changed: Q32.

### 12.8 Inbox note with no schema effect

- **RI0001-003's contract value is $260,000.00 everywhere** (owner 8:00 PM): sample data and mockups only.

### 12.9 Questions for Mark (recommended option first)

- **Q29. Does the Gantt keep its own schedule list, separate from the work tree?** **Answered 2026-11-23 (owner 8:15 PM):
  A. §12.11.** (The 1:30 PM design-chat
  write-up put task dates in the tree; your 7:10 PM answer said the Gantt keeps its own schedule.)
  A (recommended): yes, as you restated: the tree says what the work is (stage, phase, task, milestone) and the
  Gantt schedule holds each task's dates, predecessor and crew. Example: task "Set inverters" sits under phase
  "Electrical" in the tree; its forecast 2/10–2/12 and its crew are on the Gantt.
  B: one list only: each task's dates, predecessor and crew are kept on the tree itself.
- **Q30. Where a lead's sent estimate sits on the Material forecast now that leads have no start date.** **Answered
  2026-11-23 (owner 8:15 PM, revised 8:30 PM): the week of the lead's Estimated completion, tagged Estimate; options A
  and B Withdrawn 2026-11-23. §12.10.**
  A (recommended): with "include sent estimates" on, lead demand shows in a "Leads, not scheduled" band with its
  Requested completion, not netted against dated stock. Example: a lead needing 40 panels by 3/31 shows in the band.
  B: place it on `expected_close_date` as a stand-in start, labelled "estimated". **(A and B Withdrawn 2026-11-23, owner
  8:15 PM and 8:30 PM: §12.10.)**
- **Q31. How the build places Pre-construction tasks now that the start date is the first day on site.** **Answered
  2026-11-23 (owner 8:15 PM): no Pre-construction rule; options A and B Withdrawn 2026-11-23. §12.11.**
  A (recommended): the first Construction task is anchored on the start date; Pre-construction tasks are scheduled
  forward from the signing date, and the build warns when they would finish after the start. Example: signed 12/1,
  start 1/5, permitting needs 30 work days: "Pre-construction ends 1/12, after the start date 1/5."
  B: back-schedule Pre-construction from the start date so it ends the day before.
- **Q32. Does a field event keep its own number and cost lines?** **Answered 2026-11-23 (owner 8:15 PM) with the PCO
  rule; options A and B Withdrawn 2026-11-23; the number and cost lines are a lead default. §12.11.**
  A (recommended): yes: a field event (FE-#### number, cost lines, link to the change order, as approved in §5)
  stays its own record; logging Extra work on the job creates or links to one. Example: Extra work "Add 2 panels"
  logged on 2/10 becomes FE-0009 with its cost lines.
  B: Extra work is only an activity; the number and cost lines move onto the activity.

### 12.10 Owner revision 2026-11-23 8:30 PM: schedule dates and lead timing (Decided 2026-11-23, owner)

Source: `owner_decisions_2026-11-22.md`, "OWNER REVISION 2026-11-23 8:30 PM ... schedule dates and lead timing". It
replaces the 7:20 PM Q27 answer, the 7:28 PM Area 15 Q24 answer and the 8:15 PM Q30 placement, as folded in
e949ba3 (§12.6, §12.9 and Area 15 §12.1; that text is marked withdrawn, not deleted). Q28 (start date required **(Withdrawn 2026-11-24, owner 11:58 PM 11/23, Q28 revisited: the start date is optional; planned completion is required; Area 8 §12.16)**)
stands.

- **Baseline:** the planned dates set at signing. It never moves (as §12.6: one row, never versioned) **(Refined 2026-11-24, owner 1:14 AM: the task baseline can be rebuilt with a required reason, as a new version; §12.18)**.
- **Forecast = baseline + all approved change-order time + delays + reschedules.** Approving a change order with
  days moves the forecast through the "Extend schedule" step (the PM picks the tasks the days go to; §5 step 1). A
  Delay activity (`moves_forecast`, §12.5) and a reschedule on the job calendar or the Gantt move it too. None of
  them moves the baseline.
- **Target:** a date the PM types, an internal target for when things move around. It is never calculated.
  `project.target_finish_on` is **restored** as an editable date (NULL until the PM sets it; lead default, owner may
  revise). Every change is kept in a new insert-only history record, **`project_target_history`** (`history_id`
  PK, `project_id` NOT NULL, `changed_at`, `old_target_on`, `new_target_on`, `changed_by`, `note`; the note is
  optional, lead default). Permission: `job.schedule.edit` (project scope).
- **A time extension the customer grants is a $0 change order with days** (the owner's example). The proposed
  `schedule_extension` record is withdrawn.
- Example: baseline 3/20; the customer grants 5 rain days as a $0 CO with +5 days and the crew loses 4 more days, so
  the forecast is 3/29. The PM sets the target to 3/25 to push the crew; a later change to 3/27 is logged with who,
  when and the note.
- **Status** (Late, At risk, On track): which date it compares with is Q33.
- **Estimated completion (Area 15 Q24 revised).** The lead's optional Estimated completion (Area 15 §12.1) is
  copied at signing to `project.estimated_completion_on` (TEXT date or NULL, editable, logged), replacing
  `project.requested_completion_on`. The job **warns** (never blocks) when its forecast finish is later. There is no
  lead estimated start.
- **Material forecast (Q30 revised).** With the filter "Signed plus estimates sent", a lead's quantities show in
  the **week of its Estimated completion**, tagged "Estimate", alongside signed jobs; with "Contracts signed only"
  they are hidden. Example: 40 panels, estimated completion 3/31: shown in the 3/31 week. A lead with no Estimated
  completion shows in an "Estimate, no date" row (lead default, owner may revise).
- **Mockup changes needed (design queue, no schema):** the job-detail Schedule tab text ("changes only through an
  approved change order with a time extension") and a Target field with its history; field-material-forecast's
  "at the lead's estimated start date".
- **Name (owner 8:22 PM, "Owner naming"):** the lead field's label, column and report heading is **"Estimated
  completion date"**; it replaces "Estimated completion" in this section (column `estimated_completion_on`).
- Area 7 §14 and Area 15 §12.1 carry the matching amendment lines.
- Tests: `test_forecast_is_baseline_plus_approved_co_days_delays_and_reschedules`,
  `test_co_approval_moves_forecast_not_baseline`, `test_target_is_editable_and_every_change_writes_history`,
  `test_target_history_is_insert_only`, `test_estimated_completion_copied_at_signing_and_warns_when_forecast_later`,
  `test_material_forecast_places_lead_in_week_of_estimated_completion_tagged_estimate`.

**Q33. Which date makes a job Late?** **Answered 2026-11-23 (owner 8:35 PM): A. §12.11.**
A (recommended): the forecast compared with the date owed to the customer (the baseline plus approved change-order
time); the target shows separately as "n days behind target". Example (day counts in calendar days) **("calendar
  days" Withdrawn 2026-11-23, owner 8:35 PM: change-order time is work days; §12.11)**: baseline Fri
3/20 + a 5-work-day CO = owed Fri 3/27; forecast 3/29 shows Late by 2 days; target 3/25 shows "4 days behind target".
B: the forecast compared with the target. Example: the same job shows Late by 4 days.
C: the forecast compared with the baseline. Example: the same job shows Late by 9 days.

### 12.11 Owner answers 2026-11-23 8:15 PM and 8:35 PM (Q29, Q31, Q32, Q33; Decided 2026-11-23, owner)

Source: `owner_decisions_2026-11-22.md`, "Owner answers to Area 8 Q29 to Q32" (8:15 PM; its Q30 is replaced by the
8:30 PM revision, §12.10) and "Owner answer to Area 8 Q33" (8:35 PM, with the planning-chat review note on work
days).

- **Q29 A.** The Gantt keeps its own schedule list (planned and forecast dates, predecessors, crew), apart from the
  work tree; each Gantt task links to its tree node. This is the §12.5 shape (`job_schedule_task.node_id`), now
  decided. Example: tree Electrical > "Set inverters"; its dates 2/10–2/12 and crew are on the Gantt.
- **Q31: no special stage scheduling.** Stages and tasks are a customizable parent/child tree ("Preconstruction is
  not a fixed thing"), so no stage gets its own scheduling rule. Each task is placed by its own Gantt dates and
  predecessors. The build keeps the approved rule (dates from the start date, work days, predecessors and the work
  week). Lead default, owner may revise: the job start date (Q28, required **(Withdrawn 2026-11-24, owner 11:58 PM 11/23, Q28 revisited: the start date is optional; planned completion is required; Area 8 §12.16)**) anchors the first task with no
  predecessor, whatever its stage.
- **Q32: PCO, then CO by a PM; no COR.** Whoever logs a Delay or Extra work activity may tag it as a PCO (potential
  change order; the live daily log's "Create PCO"), and a PM converts the PCO into a change order. There is no
  change order request (COR) step; §5's statuses already have none ('With sales rep' and 'Sent to customer' are
  steps of the change order itself). Lead defaults, owner may revise: tagging creates the §5 `field_event`
  (FE-#### number, cost lines) and its `change_order` in 'PCO pending', linked from `delay_detail` or
  `extra_work_detail` (`change_order_id`) **("and its `change_order` in 'PCO pending'" and the `change_order_id` link:
  Withdrawn 2026-11-23, owner 10:45 PM: no CO record until a PM converts; §12.14)**; creating the PCO needs only the right to log the activity, converting
  it needs `change_order.create` (the PM, project scope); the "Change order approval" control stays OFF by default.
- **Q32: the daily log's "Feeds the status update" section is removed** (the §12.2 bullet is marked withdrawn). The
  live `field-daily-log.html` no longer has it.
- **Q32: a punch item is an activity**: work done out of schedule on the day, not an open task, including the Task
  list's punch item row. A Punch activity is logged as done on its date (`done_at` set when saved); it has no Open
  state, so `needs_verify` and `blocks_final_billing` do not apply to the Punch type. What the approved (now retired, §12.14) final-billing
  control then reads is Q34.
- **Q33 A.** A job is **Late** when its forecast finish is after the date owed to the customer = baseline +
  approved change-order time. The PM's target shows separately as "n days behind target" and **never** sets Late.
  The §12.6 Status bullet (forecast vs target) stays withdrawn.
- **Work days (fee73a8 fix).** Change-order time is in **work days**, like the Gantt (company work week, Q11 A).
  Example: baseline Fri 3/20/2026 + an approved CO of 5 work days = owed Fri 3/27 (5 calendar days would be 3/25);
  target 3/25; forecast 3/29: "Late 2 days" and "4 days behind target" (the owner's figures). The unit of the "Late
  n days" count is Q35.
- Tests: `test_gantt_task_links_to_its_tree_node`, `test_build_places_tasks_by_dates_and_predecessors_only`,
  `test_delay_or_extra_work_tagged_pco_creates_field_event_and_pco_pending`,
  `test_pm_converts_pco_to_change_order_without_cor_step`, `test_punch_activity_is_logged_done_with_no_open_state`,
  `test_late_compares_forecast_with_baseline_plus_approved_co_work_days`,
  `test_target_shows_days_behind_and_never_sets_late`.

### 12.12 Inbox note with no schema effect (10:05 PM)

- **The 10/31 WIP sample** (owner 10:05 PM): RI0001-003 shows earned $13,000.00, billed $0.00, under-billed
  $13,000.00, matching posted billing. Sample data only, owned by the design-queue run; no schema effect. It agrees
  with the owner's 9:28 PM rule that Billed to date is always actual posted billing, never the WIP report.

### 12.13 Questions for Mark (recommended option first)

- **Q34. What the final-billing control checks now that a punch item is logged work.** **Answered 2026-11-23 (owner
  10:45 PM): A. §12.14.** The 11/22 control
  `block_final_billing_with_open_punch_items` (OFF by default; a Manager cannot override it, Area 18 §8.5) reads open
  punch items, which no longer exist.
  A (recommended): retire the control and the Area 18 §8.5 override note; final progress billing is never blocked
  and the retainage release waits for the Complete stage, as the live mockups say. Example (live
  `field-final-billing.html`): SU0004-004 is in Punch list; the page shows "Final progress billing · Not blocked" and
  "Punch items and the closeout items below don't block it."
  B: keep the control, OFF by default, but have it read the schedule tasks under the job's punch-list stage that are
  not Done.
- **Q35. The unit of "Late n days" and "n days behind target".** **Answered 2026-11-23 (owner 10:45 PM): A. §12.14.**
  A (recommended): calendar days, as in your Q33 example (owed Fri 3/27, forecast Sun 3/29 = "Late 2 days");
  change-order time and task lengths stay in work days. Example (live `pages/ops-menu.js` job chips): RI0001-002
  "14 days late".
  B: work days: the same job reads "Late 0 days" (3/28 and 3/29 are a weekend).

### 12.14 Owner answers 2026-11-23 10:45 PM (Q34, Q35, PCO correction; Decided 2026-11-23, owner)

Source: `owner_decisions_2026-11-22.md`, "Owner answers to Area 10 Q36 and Area 8 Q34, Q35" (10:45 PM), with the
planning chat's review of the 3da374b lead defaults.

- **Q34 A: the 11/22 final-billing control is retired.** `block_final_billing_with_open_punch_items` is not built
  (marked withdrawn in §10, §12.2, §12.5 and Area 18 §8.5). Final progress billing is never blocked; the retainage
  release opens when the job reaches Complete; punch and closeout items are tracked only, as the live
  `field-final-billing.html` shows. `activity_type.blocks_final_billing` is dropped with it.
- **Q35 A: "Late n days" and "n days behind target" count calendar days** (the live "14 days late"). Change-order
  days and task durations stay in work days. Example: owed Fri 3/27, forecast Mon 3/30 = "Late 3 days".
- **PCO correction (replaces the §12.11 lead default, marked withdrawn there):** tagging a Delay or Extra work
  activity as a PCO creates **no** change order. The PCO is the tagged `field_event` (FE-#### number and cost lines,
  status Open, §5). A `change_order` record exists only after a PM converts the PCO (`field_event.status`
  'Converted', `co_id` set); the CO then starts in 'Draft'. Nothing pending reaches the change order lists, the
  revised contract or the budgets. The activity links to the field event (`delay_detail.field_event_id`,
  `extra_work_detail.field_event_id`).
- **Effects on approved §5 (marked withdrawn there):** `change_order.status` loses 'PCO pending' and 'PCO rejected';
  the PCO state lives on `field_event` (Open, then Converted or Closed with a reason). An office change order with no
  field event starts as a CO in 'Draft' (lead default, owner may revise). The "Change order approval" control (OFF by
  default) applies to the change order after conversion. Whether a PCO's cost still shows in the cost forecast is
  Q37.
- Tests: `test_final_billing_is_never_blocked_by_punch_items`, `test_late_days_count_calendar_days`,
  `test_tagging_pco_creates_field_event_and_no_change_order`,
  `test_pm_conversion_creates_change_order_in_draft_and_marks_field_event_converted`,
  `test_open_pco_is_absent_from_co_lists_revised_contract_and_budget`.

**Q37. Does an open PCO's cost show in the job's cost forecast before a PM converts it?** **Answered 2026-11-23 (owner
11:25 PM): A. §12.15.**
A (recommended): yes, as its own forecast line by cost code tagged with the field event (`job_forecast_line.
field_event_id` in place of `change_order_id`); it never reaches the budget, the revised contract or the CO lists.
Example (live `field-daily-log.html`): a delay on "Panels, sections 3 and 4" with "Create PCO" shows its cost as a
"PCO" line in the forecast until it is converted or closed.
B: no: the forecast shows nothing until the PM converts the PCO into a change order.

### 12.15 Owner answer 2026-11-23 11:25 PM (Q37 A; Decided 2026-11-23, owner)

- **Amendment 2026-11-23 (Q37 A).** An open (unconverted) PCO's cost shows in the job's cost forecast at once, as its
  own line tagged with the field event: `job_forecast_line.field_event_id` INTEGER NULL REFERENCES field_event (in
  place of the withdrawn `change_order_id` tagging), so forecast margin drops now. It never reaches the budget, the
  revised contract or the CO lists until a PM converts it; on conversion the line moves to the change order's
  forecast lines; if the PCO is closed without converting, a forecast revision removes the line. Example: extra work
  "Add 2 panels", $1,800.00, tagged PCO FE-0009: forecast cost +$1,800.00 "PCO FE-0009".
- **Mockup item (design queue, no schema):** the job-detail Budget / forecast needs the PCO forecast line; the live
  daily log has "Create PCO" but no PCO cost line yet.
- Tests: `test_open_pco_cost_shows_as_forecast_line_tagged_with_field_event`,
  `test_open_pco_never_reaches_budget_revised_contract_or_co_lists`,
  `test_closed_pco_removes_its_forecast_line`.

### 12.16 Owner answers 2026-11-23 11:58 PM and 2026-11-24 12:04 AM (Q28 revisited; inspections)

Source: `owner_decisions_2026-11-22.md`, "Owner answer to Area 8 Q28, revisited" (replaces Q28 A, 7:23 PM) and
"Owner answer to field review question 3, inspections". Appended; the earlier Q28 text is marked withdrawn where it
says the start date is required.

- **Amendment 2026-11-24 (Q28 revised: completion only).** When a job is created at signing, the **planned
  completion date is required** and becomes the **baseline finish**: the date owed to the customer, so Late (Q33) =
  forecast finish after that date plus approved change-order time. Proposed: the baseline row written at signing,
  `job_schedule_baseline`, gains `finish_on` TEXT NOT NULL (the planned completion); its task lines come later
  (STOP question below; **answered 2026-11-24 12:28 AM: fixed at the first schedule build, §12.17**). `project.target_start_on` is **no longer required** (NULL allowed again); a job with no
  start shows **"Not scheduled"** until the PM enters one. The planned completion is pre-filled from the lead's
  Estimated completion date (Area 15) and can be changed before signing; after signing it never moves (the baseline
  rule).
- **Unchanged:** the three dates of §12.10 (baseline set at signing and never moves; forecast = baseline + approved
  CO time + delays + reschedules; target = the PM's editable date with history) and Late (Q33 A, calendar days,
  Q35 A).
- Example: North field array signs 12/1. Planned completion 3/20 is required (pre-filled from the lead). Start is
  left blank, so the job shows "Not scheduled" until the PM enters 1/5.
- **Lead default, owner may revise:** a job with no start appears on the Material forecast (§12.3) in a "Not
  scheduled" row, not netted by date. **Withdrawn 2026-11-24 (owner 12:28 AM): the job stays in the week of its
  planned completion, tagged "Not scheduled"; §12.17.**
- **Mockup notes (design queue, no schema):** job-new.html's "Target finish" collides with the three-date naming
  (Target is the PM's internal date); the signing field is named for the baseline, proposed "Planned completion"
  (owner may revise). sign-contract.html has no date field, so where the required date is entered at signing needs a
  mockup item.
- **Inspections (field review question 3, owner 12:04 AM): a company list per job type.** Each job type has its own
  editable list of standard inspections; a new job copies its job type's list, and the PM can add or remove
  inspections on that job without changing the company list. No fixed built-in list. Proposed for the v1.1 field
  pass (inputs, not decided schema): a per-job-type list (job type, name, order) and a per-job copy (job, name,
  source item, added or removed by the PM); each inspection is recorded as an Inspection activity (§12.5) with pass
  or fail. Example: Roofing starts with deck and nailing, final roofing and manufacturer warranty inspections; on
  SU0004-004 the PM adds "Electrical inspection (RTU reconnect)" for that job only.
- **Tracked only (Q34 A):** inspections and punch items never block final billing; the retainage release opens at
  Complete. Nothing on the closeout checklist gates.
- Tests: `test_job_creation_requires_planned_completion_as_baseline_finish`,
  `test_job_without_start_date_shows_not_scheduled`,
  `test_planned_completion_prefilled_from_lead_estimated_completion`,
  `test_late_compares_forecast_with_planned_completion_plus_co_work_days`,
  `test_new_job_copies_job_type_inspection_list_and_pm_edits_only_the_job`.

**STOP question for Mark (not decided): when are task-level baseline dates fixed if the job has no start at
signing?** **Answered 2026-11-24 (owner 12:28 AM): the proposal is approved; §12.17.** Task baseline lines need a start date to compute. Proposed (not approved): they are fixed the first time
the PM enters the start and the schedule is built. Until then the baseline holds only the planned completion.

**Conflict flagged (not changed):** **Resolved 2026-11-24 (owner 12:28 AM): corrections are open tasks, never punch
items; the 12:04 AM "Unchanged" line is Withdrawn 2026-11-24; §12.17.** The 12:04 AM note says a failed inspection adds its corrections as punch items
plus a re-inspection (live field-punch.html), while Q32 (8:15 PM) says a punch item is logged work done that day,
not an open task (§12.11). Corrections waiting to be done are open work; how they are held is for Mark.

### 12.17 Owner answers 2026-11-24 12:28 AM (baseline timing, inspection corrections, Material forecast)

Source: `owner_decisions_2026-11-22.md`, "Owner answers 2026-11-24 12:28 AM". The planning chat accepted cc61de2:
`job_schedule_baseline.finish_on` and the label "Planned completion" stand as lead defaults.

- **Amendment 2026-11-24: task baseline dates are fixed at the first schedule build.** The baseline finish (planned
  completion) is fixed at signing. The task-level baseline dates (`job_schedule_baseline_task` lines) are written
  automatically the first time the PM enters the start date and the schedule is built, and never move after that **(Refined 2026-11-24, owner 1:14 AM: the task baseline can be rebuilt with a required reason, as a new version; §12.18)**
  (insert-only, as approved). Later edits move the forecast only. Until then the baseline holds only `finish_on`. If
  that first schedule ends after the planned completion, the job is Late at once (forecast after the baseline
  finish; Q33, Q35). Example: North field array signs 12/1, planned completion 3/20; on 12/15 the PM enters start
  1/5 and the schedule is built; "Set inverters 2/10 to 2/12" is locked as baseline that day; **(task baseline: rebuild with a reason, §12.18)** the first schedule ends
  3/27, so the job shows "Late 7 days" at once.
- **Amendment 2026-11-24: corrections after a failed inspection are open tasks, never punch items.** A failed
  inspection adds each correction as an **open task** on the Task list, with an assignee, plus a re-inspection to
  schedule. Nothing is created as a punch item; punch items stay logged work done out of schedule on the day
  (§12.11). The 12:04 AM "Unchanged" line ("a failed one adds its corrections as punch items") is Withdrawn
  2026-11-24 (owner 12:28 AM). Example: the electrical inspection fails 11/10; "Re-terminate RTU feeder" becomes an
  open task assigned to Brightline Electric, and a re-inspection is added.
- **Amendment 2026-11-24: Material forecast, signed job with no start.** It stays in the **week of its planned
  completion**, tagged **"Not scheduled"**, and moves to its real task weeks once the PM schedules it. There is no
  separate row (the §12.16 lead default is withdrawn). This keeps a lead's materials in the weekly view across
  signing: a lead sits in the week of its Estimated completion tagged "Estimate" (§12.10). Example: a lead needing 40
  panels, estimated completion 3/31, shows in the 3/31 week tagged "Estimate"; it signs with planned completion 3/31
  and no start, so the 40 panels stay in the 3/31 week, tagged "Not scheduled"; once scheduled they move to the weeks
  of their tasks.
- **Mockup items (design queue, no schema):** field-punch.html help text ("adds the corrections as punch items") and
  field-final-billing.html ("1 correction open (P-015, Brightline Electric)") must show the correction as a task,
  not a punch item with a P- number.
- Tests: `test_task_baseline_written_once_at_first_schedule_build`,
  `test_task_baseline_unchanged_by_later_schedule_edits`,
  `test_job_with_no_start_has_baseline_finish_only`,
  `test_first_schedule_ending_after_planned_completion_is_late_at_once`,
  `test_failed_inspection_creates_open_tasks_with_assignee_and_reinspection`,
  `test_failed_inspection_creates_no_punch_item`,
  `test_material_forecast_lead_in_estimated_completion_week_tagged_estimate`,
  `test_material_forecast_signed_unscheduled_job_in_planned_completion_week_tagged_not_scheduled`,
  `test_material_forecast_scheduled_job_moves_to_task_weeks`.

### 12.18 Owner answer 2026-11-24 1:14 AM (task baseline rebuild; refines §12.17)

Source: `owner_decisions_2026-11-22.md`, "Owner answer 2026-11-24 1:14 AM". The planning chat accepted 8532272.

- **Amendment 2026-11-24: the task-level baseline can be rebuilt from the current schedule, with a required
  reason** (the Area 18 Q26 rule, §8.7: a listed reason, or at least 10 typed characters). Task baselines never move
  on their own or by ordinary schedule edits (§12.17); only a logged rebuild changes them.
- **Insert-only is kept.** A rebuild inserts a new `job_schedule_baseline` row (`version_no` + 1, `set_at`/`set_by` =
  when and who, new `rebuild_reason` TEXT and `rebuild_reason_id` FK `reason_option`, the label at the time of use)
  with a full set of `job_schedule_baseline_task` lines copied from the current schedule. The earlier version is
  never updated or deleted; it reads as **superseded** because a later version exists (derived, so no row is
  changed). Proposed CHECK: `(version_no = 1) = (rebuild_reason IS NULL AND rebuild_reason_id IS NULL)` (the
  approved `change_order_id` version rule stays withdrawn, §12.6).
- **`finish_on` (planned completion) never changes on a rebuild:** the new version carries the same value (service
  check against version 1), so Late (Q33, Q35) is unaffected.
- **Task slip is measured against the latest task baseline version.** Reports can show that a rebuild happened (who,
  when, reason) and compare with an earlier version on request.
- **Not a control and no setting.** **Withdrawn 2026-11-24 (owner 1:37 AM): one approval control, OFF by default;
  §12.19.**
- Example: on 12/15 the PM types start 1/5 instead of 1/15 and the task baseline locks. On 12/16 the PM rebuilds it
  with the reason "Start date typed wrong": task baselines shift 10 work days, planned completion 3/20 is unchanged,
  and the history shows version 1, the PM and the time.
- Tests: `test_baseline_rebuild_requires_reason`, `test_baseline_rebuild_keeps_earlier_version`,
  `test_baseline_rebuild_leaves_finish_on_unchanged`,
  `test_ordinary_schedule_edits_never_change_task_baseline`,
  `test_task_slip_uses_latest_baseline_version`.

**STOP question for Mark (not decided): which existing permission covers the rebuild?** **Answered 2026-11-24
(owner 1:37 AM): `job.schedule.edit`; §12.19.** No new permission is added.
The candidate is `job.schedule.edit` ("Edit a job's schedule and calendar items", project scope; §8: Project manager
template, Admin, Master), which matches "whoever can manage the job's schedule". Not chosen until Mark confirms.

### 12.19 Owner answer 2026-11-24 1:37 AM (rebuild permission and approval control; refines §12.18)

Source: `owner_decisions_2026-11-22.md`, "Owner answer 2026-11-24 1:37 AM". The planning chat accepted 910a9aa.

- **Amendment 2026-11-24: permission.** A task-baseline rebuild needs the existing `job.schedule.edit` (job scope;
  Project manager, Admin and Master by default, §8). No new permission. Without it the rebuild is refused.
- **Amendment 2026-11-24: one Company control, OFF by default:** **(Withdrawn 2026-11-24, owner 1:48 AM: no separate control; the on/off switch is the Approvers row "Schedule baseline rebuilds"; Area 8 §12.20)** PROPOSED name `require_baseline_rebuild_approval`
  ("Require approval to rebuild a schedule baseline"), Admin or Master, Controls page, every change audit-logged;
  listed in Area 18 §8.10.
  - **OFF (default):** the schedule editor rebuilds alone; the new baseline version is written at once (§12.18).
  - **ON:** the rebuild is a **request**. Nothing is written to `job_schedule_baseline` or
    `job_schedule_baseline_task` until it is approved; on approval the service inserts the new version. The
    requester cannot approve their own request. **(Withdrawn 2026-11-24, owner 1:48 AM: self-approval follows "Require a separate approver"; §12.20)** A refused request leaves the baseline unchanged and stays in the
    history (who asked, when, the reason, who refused, when).
  - Lead defaults, owner may revise: the request is held in the single approval mechanism (`approval_request`,
    Area 14) rather than a new table; at most one open rebuild request per schedule; the new version is copied from
    the schedule as it stands at approval, and the approval screen shows that preview.
- **Reason and history are recorded in both modes** (the Area 18 Q26 reason rule).
- **Not controllable (integrity):** baseline rows stay insert-only, and `finish_on` (planned completion) never
  changes on a rebuild, with the control on or off. Late (Q33) is unaffected either way.
- Examples: control off, the PM fixes a wrong start date with the reason "Start date typed wrong" and the new version
  is written at once, logged with her name; control on, the PM requests the same rebuild, an Admin approves it, and
  only then is the new version written; if refused, the baseline is unchanged and the request stays in the history.
- Tests: `test_baseline_rebuild_allowed_with_job_schedule_edit`,
  `test_baseline_rebuild_refused_without_job_schedule_edit`,
  `test_baseline_rebuild_control_off_writes_version_at_once`,
  `test_baseline_rebuild_control_on_writes_nothing_until_approved`,
  `test_baseline_rebuild_self_approval_refused` **(Withdrawn 2026-11-24, owner 1:48 AM: self-approval follows "Require a separate approver"; §12.20)**,
  `test_refused_baseline_rebuild_leaves_baseline_unchanged_and_stays_in_history`,
  `test_require_baseline_rebuild_approval_defaults_off` **(Withdrawn 2026-11-24, owner 1:48 AM: no separate control; the on/off switch is the Approvers row "Schedule baseline rebuilds"; Area 8 §12.20)**.

**STOP question for Mark (not decided): who may approve a rebuild when the control is on?** **Answered 2026-11-24
(owner 1:48 AM): configured on the Approvers page like every other kind of work; the proposed default list below is
Withdrawn 2026-11-24; §12.20.** The rule I would use:
the existing approval setup, the single approval mechanism of Area 14 (as for "Change order approval", §5), with a
new approval type "Schedule baseline rebuild" whose default approvers are Admin and Master, plus any holder of
`job.schedule.edit` on that job, never the requester. Why: it reuses the one approval mechanism instead of a new
path, it matches your example (an Admin approves), and the job-scoped editors are the people who already manage that
schedule. Not chosen until Mark confirms; Area 14 is not drafted yet.

### 12.20 Owner answer 2026-11-24 1:48 AM (rebuild approval is an Approvers row; refines §12.19)

Source: `owner_decisions_2026-11-22.md`, "Owner answer 2026-11-24 1:48 AM". The planning chat accepted 0d86bc3 with
these changes; the §12.19 lead defaults stand (the pending rebuild is held in the shared approvals record; at most one
open rebuild request per job schedule; the new version is copied from the schedule as it stands at approval, with a
preview for the approver).

- **Amendment 2026-11-24: a new approval kind, "Schedule baseline rebuilds" (PM), OFF by default.** It is a row on the
  Approvers page like every other kind of work. When an Admin or the Master turns it on, they pick who approves with
  the same choices as any other row: anyone with permission, the job's project manager, a role, specific people, or a
  chain, with an optional backup (live approvers.html). No fixed approver list: the proposed default list in §12.19
  (Admin, Master and `job.schedule.edit` holders) is Withdrawn 2026-11-24. Example: the row is on and set to "A role:
  Controller"; PM Tomas Okafor requests a rebuild with the reason "Start date typed wrong"; Dana Reyes approves; the
  new baseline version is written then.
- **One switch only (point 3 check).** The plan models every approval kind as a **row** of the approvals setup, not
  as its own Company control: the baseline's `document_approval_setting` (`document_type` CHECK list with
  `requires_approval` DEFAULT 0; "RP9: every approval toggle lives here, all OFF by default") holds Bill, Change
  order, Pay run and the others, and the Approvers page sets who approves (`approval_policy`, `approval_step`; Area
  14). So the separate control `require_baseline_rebuild_approval` (§12.19, Area 18 §8.3 and §8.10) is **withdrawn**,
  and the switch is the new row: `document_approval_setting.document_type` gains 'Schedule baseline rebuild', seeded
  with `requires_approval` = 0. Row off: the schedule editor rebuilds alone and the version is written at once; row
  on: the rebuild is a request written only on approval; a refused request leaves the baseline unchanged and stays
  in the history.
- **Amendment 2026-11-24: self-approval follows the existing company control "Require a separate approver"**
  (`company_settings.require_separate_approver`, OFF by default): when it is off, a person may approve their own
  rebuild and it is marked Self-approved; when it is on, it goes to another approver. The rebuild has no special
  rule; §12.19's "the requester cannot approve their own request" and its test are withdrawn. Example: the row is set
  to "The job's project manager" and "Require a separate approver" is off: the PM's own rebuild is approved by her
  and marked Self-approved.
- **Unchanged (always on):** the permission (`job.schedule.edit`, job scope); the reason and the history in both
  modes; baseline rows insert-only; `finish_on` (planned completion) never changes on a rebuild; Late (Q33)
  unaffected.
- **Area 14 handoff:** the approval kind "Schedule baseline rebuilds" must be included when Area 14 is drafted
  (next_step).
- Tests: `test_schedule_baseline_rebuild_approval_row_defaults_off`,
  `test_rebuild_with_approval_row_off_writes_version_at_once`,
  `test_rebuild_with_approval_row_on_writes_nothing_until_approved`,
  `test_rebuild_self_approval_allowed_and_marked_when_separate_approver_off`,
  `test_rebuild_self_approval_refused_when_separate_approver_on`,
  `test_no_separate_rebuild_control_exists`.

- **Amendment 2026-11-24 (pointer, Area 14): Area 14 handoffs done.** The Approvers row has the page label "Schedule
  baseline rebuilds" and the code `Schedule baseline rebuild` (Area 14 §3); Change order approval is the 'Change
  order' row with the margin-floor condition; self-approval follows "Require a separate approver" with the Area 14 §8
  fallback (refused only while another eligible approver exists, so the test above reads
  `test_rebuild_self_approval_refused_when_separate_approver_on_and_another_eligible_approver_exists`); at most one open rebuild request per schedule (Area 14 §5 rule 10).

- **Amendment 2026-11-24 (pointer, Area 9): the Material forecast inputs (§12.3).** Open PO quantity by date reads
  `purchase_order.expected_on` with the optional per-line override on sent POs (Area 9 §6.1, §6.2); stock available is on
  hand less reserved and is 0 when stock tracking is OFF (Area 9 §5, §8.2). Field material requests are raised by the PM
  (Area 9 §8.1).
