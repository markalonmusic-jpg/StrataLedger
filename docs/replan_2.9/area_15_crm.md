# Step 2.9 schema replan, area 15: CRM (leads, activities, cases, comments, routing)

Status: **Owner-approved 2026-11-20 (2237b63, answers 03477c0, 3b8108b)** (first draft 2026-11-19, 2237b63; owner
answers 2026-11-19 11:40 PM and the 11:20 PM required fixes folded in below, section 10; open item 13 closed
2026-11-20 12:05 AM; amendment lines in area 8 sections 2.3, 4.3, 5.3 and 6.3 and
area 18 sections 1.2, 2.3 and 2.4). Docs only: nothing here changes code, a baseline, a migration or a test.
Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan is
approved. PROPOSED items from the sources are not built as final.

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`: row 15 and its "Inbox inputs" for areas 15, "15 and 6" and "15 and 8".
- `Strata_Teams\inbox\to_planning.md` (these six are still there, marked done, not yet moved to
  `inbox\archive\to_planning_done.md`): 2026-11-17 "CRM follow-ups, appointments, invites" (5:51 PM), "activity
  model, activity types, crews" (5:55 PM), "lead "owner" is "Sales rep"" (8:12 PM); 2026-11-18 "service case status
  history and milestone dates", "lead billing address, service type lock, auto-lost, win-back", "lead contacts
  captured on the intake form", "lead expected value comes from the sent estimate", "service jobs created from
  cases"; and 2026-11-18 "company calendar address gets every item" (area 20's, read for the invite rule).
- `Strata_Teams\inbox\archive\to_planning_done.md`: 2026-11-18 "customer created at contract signing uses the
  customer validation".
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md` (the row's A sources): 2026-11-13 "carry CRM
  decisions into the design doc"; 2026-11-14 "CRM, rules"; 2026-11-15 "CRM flow gaps that need service rules"
  (2:34 PM) and "Owner answers on CRM cases and cancellation" (2:41 PM).
- `Strata_Teams\ux_research_crm_followups_2026-11-17.md` (all; section 5 replaces section 4).
- `Strata_Teams\shared_decisions.md`: 2026-11-13 "CRM Solo and Team states"; 2026-11-14 "CRM"; 2026-11-15 "service
  types, stages and triggers", "routing estimates and routed items"; 2026-11-17 "CRM follow-ups and appointments",
  "Activities, activity types, crews", "Sales rep, not Owner", "roles, access levels, job titles; R25 person
  pickers; lead assignment rules"; 2026-11-18 "R33 stage path", "a lead's proposal is its estimate", "service case
  statuses, dates and status actions", "case stage path and service jobs from cases", "one company calendar address
  gets every calendar item" (11:45 AM), "lead details, service type lock, auto-lost, win-back leads", "Custom
  fields is the name", "the contract's new customer uses the customer form's fields and rules" (4:36 PM);
  2026-11-19 "service type holds the default payment schedule; every lead intake asks for the service type"
  (8:42 PM), "lead stages warn when no estimate was sent" (8:50 PM), "estimate flow" (8:58 PM), "margin % on cost
  lines; one customizable Reasons list" (9:48 PM).
- `Strata_Teams\StrataLedger_planning_log_2026-11-12.md` section 3b, the 16:10 feasibility answers (desktop team
  features between turns on one PC; real time is hosted).
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md`, sections 9, 10, 12, 13, 20, 27, 31, 103, 104 and 120 (first
  numbering). **Citation rule:** "C9", "C104" and the like below are section numbers of `CODE_CHANGES_NEEDED.md`,
  not decision codes. `docs/decisions_2026-11-11.md` has no C-codes.
- `Strata_Teams\codex_reports\schema_gaps_vs_mockups_2026-11-18.md` item 4 (X 4).
- docs/next_step.md, "Handed to later areas by area 8" (the area 15 items) and "by the approved ones".
- Approved areas: 8 (`service_type`, `service_stage.stage_role`, `project_stage_history` rules, `crew` and the crew
  label, `calendar_item`, `project.source_case_id`, `billing_method`, `cost_destination`, `warranty_for_job_id`, Q2, Q5, Q21), 13 (work
  week, holidays, the calendar query inputs, section 3), 17 and docs/contracts/reports.md (`src_leads`,
  `src_leads_estimates`, `src_activities`, `src_cases`, `src_lead_job_invoices`, `src_rep_contract_payments`; section
  5.4 row limits; section 12 items 16-17), 18 (access model, caps, level defaults, the "which actions require a
  reason" table, `attachment`, `AGENT_ALLOWED`, proposed codes `lead.own` and `case.work`, O5).
- docs/design_decisions.md "CRM and project lifecycle" and docs/crm_pm_design.md sections 2 and 4 (read for the
  conflicts in section 9 only); docs/decisions_2026-11-11.md by code: RP4, RP9, H2, H4.
- `migrations/001_company.sql` (estimate, project, contact, contact_site, permission seeds, company_settings,
  file_attachment, service_type, service_stage, stage_trigger, custom_field_def); `modules/services/permissions.py`,
  `custom_fields.py`, `contacts.py`; `modules/views_dashboard.py`; `tests/test_schema_replan.py`.

---

## 0. Summary

| # | Item | Proposal in one line | Baseline |
|---|------|----------------------|----------|
| 1 | Leads | A new `lead` record, separate from the job (Q1; conflict F1), linked to the job it becomes at signing. Service type required and locked once an estimate exists; Sales rep; job site and billing addresses (structured, "same as job site"); lead source list; win-back link. Expected value typed only until an estimate revision is sent, then written by the send and read-only | company |
| 2 | Lead stages and history | Lead stages are the service type's Sales stages (one shared list, area 8 Q1), plus a `Lost` stage role; Won is the Contract signed bookend, reached only by signing (Q3). New append-only `lead_stage_history`, the twin of `project_stage_history` with the same rules (area 8 Q21 A), plus gate warnings continued with a reason | company |
| 3 | Lead contacts | `lead_contact`: one required Primary and one optional Second decision-maker (name, phone and/or email, preferred channel), editable while the lead is open, logged; handed to the customer at signing (area 5) | company |
| 4 | Auto-lost and win-back | A System run closes a lead as Lost N days after its latest sent estimate with no signed contract (`auto_lost_days`, default 14, 0 = off; conflict F5), warns at N−3, and asks area 6 to mark the estimate Expired. "Recreate lead" makes a new lead linked both ways, source Win-back | company |
| 5 | Activities | One `activity` record for planned and done work: type, due date and optional time, length, owner, attendees (users), contacts taking part, location, crew, links to lead, customer, case (and job, Q7), done_at/done_by, cancelled. A lead's next activity is its earliest open one (derived). Company `activity_type` list, seeded generic. Busy check is a warning across activities, calendar items and crews | company |
| 6 | Service cases | `service_case` with type, channel, priority, owner (always a user, Q12 B), due, statuses Open, In progress, Waiting on customer, Resolved, Closed; milestone dates never overwritten; append-only `case_status_history`; allowed transitions in the service; auto-close after `case_auto_close_days` (default 7); follow-up cases by `parent_case_id`. `case_type` list with a default owner user and due days | company |
| 7 | Service jobs from cases | A case moves to In progress when estimate cost work starts. Signed-quote upload creates the service job and contract row without triggering the initial case transition. Declined or expired quotes leave the case open. Read jobs by `project.source_case_id` (FK and index here, Q13 B). When all linked jobs complete, show a Resolve prompt (derived, never automatic). | company |
| 8 | Comments | `comment` on leads, jobs, estimates and cases, internal only, never printed; `comment_mention`; notifications to the people mentioned plus the record's owner (area 21 feed) | company |
| 9 | Routing and assignment | `lead_assignment_rule` per service type (Round-robin with a stored next-up pointer, Fixed user, Unassigned) and its members; skip inactive users and users without `lead.own`; a hand pick wins; logged | company |
| 10 | Boundaries | Area 5 creates the customer at signing; area 6 owns estimates, revisions, sending, signing and expiry; areas 7/8 own the job; area 16 custom-field scoping; area 17 report sources; area 20 sends .ics; area 21 the calendar query and notification feed (section 6) | n/a |
| 11 | Controls, settings, permissions | Settings `auto_lost_days`, `auto_lost_warn_days`, `case_auto_close_days`; no new control that refuses anything by default; ten new codes `lead.*`, `activity.log_for_others`, `crm.settings`, `case.*` (Q19 A, no `lead.view_all`); lead visibility by `lead_scope` ('All', 'Own') on `role_level` and `access_template`, resolved like MR3 (Q18); one `reason_option` list for every reason dropdown, area 8's lists folded in (Q16 A), each stored reason with its `reason_label` (section 7) | company |
| 12 | Sales rep on the job | `project.sales_rep_user_id` copied from the lead at signing, editable with history; `contract.sales_rep_user_id` keeps the rep at signing; a change order's "Forward to sales rep" reads the project's (section 6) | company |

Master file: no change. This area posts nothing and names no account.

---

## 1. Leads

### 1.1 Current state

- **There is no lead record** (X 4). The baseline has `project` (`001_company.sql:254`) with `project_number TEXT NOT
  NULL UNIQUE` (`:258`), `contact_id INTEGER NOT NULL` (`:262`) and `assigned_pm_id INTEGER NOT NULL` (`:266`), so a
  project row needs a job number, a customer and a PM before it exists; none of these is known for a new lead.
  `project.service_type_id` and `service_stage_id` (`:276-277`) hold a current stage with no history.
- `estimate` (`:209`) has `contact_id INTEGER NOT NULL` (`:217`), no lead link, no revision, no sent date, and
  `status` CHECK Draft, Submitted, Approved, Won, Lost (`:225`). Area 6 replans it.
- `contact` (`:810`) holds customers and vendors with one-line `address` plus `mailing_*` columns; `contact_site`
  (`:3893`) holds structured addresses per contact (billing, shipping flags). Neither has a person (contact person)
  table; area 5 owns that.
- `service_type` (`:3940`) and `service_stage` (`:3948`, phase Sales or Delivery) exist; area 8 replaces
  `is_closed_stage` by `stage_role` and handed area 15 the lead-side role `Lost`.
- `custom_field_def.record_type` (`:4119`) allows Contact, Invoice, Bill, Project, Estimate; `custom_fields.py:39`
  offers four of them and refuses Estimate (`:76-82`). No `Lead`.
- Permissions: `project.create` "Create projects and leads" (`permissions.py:65`, seeded at `001_company.sql:1222`),
  `project.manage`, `project.view`. No lead code.
- Code: no service, view model or test touches leads. `modules/views_dashboard.py:62` shows hard-coded sample text
  ("INBOUND LEAD ... ASSIGN SALES REP"), a legacy screen with no data behind it.

### 1.2 Decided

| Decision | Source |
|----------|--------|
| The person who works a lead is the "Sales rep" in every label, CSV header, report and export; the column name is free; assignment rules keep their logic | A 11-17 8:12 PM; S 11-17 8:12 PM |
| A lead has name, phone or email, job site address, billing address ("Same as job site" by default) and service type, shown in its header card and changed with Edit (R31) | S 11-18 12:20 PM; A 11-18 item 1 |
| Service type is required on every lead intake form (New lead and Customer intake); it sets the lead's stages and the estimate, contract, schedule and payment-schedule defaults | S 11-19 8:42 PM |
| Service type can be changed until the first estimate exists; then the service refuses: "Locked: an estimate was made from this service type." | S 11-18 12:20 PM; A 11-18 item 2 |
| A new lead saves one required primary contact (first and last name, phone and/or email, preferred channel) and an optional second decision-maker; editable while the lead is open; changes logged | A 11-18 "lead contacts" |
| No proposal table or proposal fields (amount, date reviewed, expiry) on a lead; the proposal is the latest sent estimate revision | A 11-18 "expected value" item 1; S 11-18 2:02 AM |
| Expected value is stored and editable only while no estimate revision is sent; once one is sent it equals that revision's contract total, read-only (R29); each newly sent revision updates it and writes a lead history row; pipeline, forecast and reports read that one value | A 11-18 items 2-3; S 11-18 2:02 AM |
| The lead's Estimates card shows the latest sent revision's total, sent date and valid-until (expiry warning), read-only | S 11-18 2:02 AM |
| A lead can be tied to an existing customer at creation (Repeat customer) or at signing; the customer record and code are created only when the contract is signed, never at Mark sent; a signed repeat lead gets the next job number under that customer | A 11-14 "CRM, rules"; S 11-14; S 11-13 3:46 PM U6 |
| A new customer at signing goes through the New customer service and validation; billing and job site addresses are structured (street, city, state, ZIP); the signer becomes the customer's primary contact; signing fails with the field errors and creates nothing | A 11-18 "customer created at contract signing"; S 11-18 4:36 PM |
| Lead stages and job stages use one shared path (R33). Clicking a stage only previews it; "Mark <stage> complete" moves forward; "Mark as current stage" skips ahead or goes back. The last step is Closed: Won or Lost, a reason required for Lost | S 11-18 1:58 AM |
| Moving a lead into Proposal reviewed or later with no sent estimate warns and needs a reason; every way forward runs the same checks; blocking follows the stage-gate setting (off = warn); a continue-anyway reason comes from the Reasons list (Other + at least 10 characters) | S 11-19 8:50 PM |
| Stage history is append-only; time in stage comes from it; lead history is its own twin of `project_stage_history` with the same rules | C10; area 8 Q21 A; C34 via area 8 |
| One service type list for leads and jobs; stages are deactivated, never deleted; stage edits go through the R36 review panel, no draft set | area 8 Q1 A, Q3 A |
| Daily job: Lost when the latest sent estimate is N days old with no signed contract (company setting, default 14, 0 = off); reason "No signature in N days (automatic)"; the estimate becomes Expired; warning at N−3 to the sales rep; a new sent revision restarts the clock | A 11-18 item 3; S 11-18 12:20 PM |
| Win-back: "Recreate lead" on a lost lead makes a new lead linked both ways, customer and addresses copied, source "Win-back"; the lost lead stays lost; reports count win-backs and their win rate (`recreated_from_lead_id`) | A 11-18 item 4; S 11-18 12:20 PM |
| Company-defined lead fields are "Custom fields", per service type | S 11-18 12:26 PM; C27 |
| Deal basics are core columns, not custom fields: value, expected close date, sales rep, contacts, lead source | C27 |
| Lost reasons come from Settings > Lists > Reasons (kinds include Lost lead, Moving a lead back, Continue anyway); shipped reasons can be hidden, not deleted once used | S 11-19 9:48 PM |
| Solo (one active user) and Team (two or more) are computed from the active-user count, never stored; Solo hides team parts, services still enforce permissions | S 11-13; C13.1 |
| Commissions stay out | A 11-13 crm_design; C10 |

### 1.3 Proposed schema

**`lead`** (new; one row per lead; Q1 A):

| Column | Type | Notes |
|--------|------|-------|
| `lead_id` | INTEGER PK | |
| `lead_number` | TEXT NOT NULL UNIQUE | `L-0001` from `lead_number_seq` (Q20; the sequence-table pattern of `customer_number`, never MAX+1) |
| `name` | TEXT NOT NULL | CHECK length 1-200 ("Patel residence") |
| `service_type_id` | INTEGER NOT NULL | FK service_type; locked once an estimate exists (service) |
| `stage_id` | INTEGER NOT NULL | FK service_stage; current copy of the latest history row (1.4) |
| `sales_rep_user_id` | INTEGER | NULL = Unassigned; a user holding `lead.own` (service; R25) |
| `lead_source_id` | INTEGER | FK lead_source; NULL allowed on import |
| `customer_contact_id` | INTEGER | FK contact; set for a Repeat customer or at signing |
| `expected_value_cents` | INTEGER | CHECK NULL or integer >= 0 |
| `expected_value_revision_id` | INTEGER | the sent estimate revision it was taken from; plain integer until area 6 adds the revision table, then FK. While set, direct edits are refused (Q5 A) |
| `expected_close_date` | TEXT | CHECK `IS date(...)` |
| `site_street`, `site_city`, `site_state`, `site_zip` | TEXT | job site address, structured (S 11-18 4:36 PM) |
| `billing_same_as_site` | INTEGER NOT NULL DEFAULT 1 | CHECK IN (0, 1) |
| `billing_street`, `billing_city`, `billing_state`, `billing_zip` | TEXT | CHECK all NULL when `billing_same_as_site = 1` |
| `close_outcome` | TEXT | CHECK NULL or IN ('Won', 'Lost'); the current copy of the closing history row |
| `lost_reason_id` | INTEGER | FK reason_option ON DELETE RESTRICT (Q16 A; kind Lost lead); CHECK set only when `close_outcome = 'Lost'` |
| `lost_reason_label` | TEXT | the reason's label at the time of use, written by the service (fix a, section 7.3); CHECK set iff `lost_reason_id` is set |
| `lost_note` | TEXT | CHECK NULL or length <= 1000 |
| `lost_at_stage_id` | INTEGER | FK service_stage; set by the service from history |
| `closed_on` | TEXT | CHECK date; CHECK `(close_outcome IS NULL) = (closed_on IS NULL)` |
| `is_auto_lost` | INTEGER NOT NULL DEFAULT 0 | CHECK IN (0, 1); CHECK 1 only with `close_outcome = 'Lost'` |
| `recreated_from_lead_id` | INTEGER UNIQUE | self FK; the win-back link ("Recreated as" is the reverse lookup); UNIQUE so a lost lead is recreated once |
| `project_id` | INTEGER UNIQUE | FK project; the job created at signing (the lead → job link of X 4 and `src_lead_job_invoices`); CHECK set only when `close_outcome = 'Won'` |
| `is_blocked`, `blocked_reason` | INTEGER, TEXT | R33 "Mark blocked" (Q22 A); CHECK `blocked_reason` set iff `is_blocked = 1` |
| `memo` | TEXT | CHECK NULL or length <= 4000 (area 18 memo rule), never printed |
| `created_at`, `created_by` | TEXT NOT NULL, INTEGER NOT NULL | UTC ISO 8601 with offset (H2: from the context) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 | rule g4 |

Indexes: (`sales_rep_user_id`, `close_outcome`), (`service_type_id`, `stage_id`), (`customer_contact_id`),
(`created_at`). No phone, email or name columns of the person: those are on `lead_contact` (the lead's "phone or
email" is its Primary contact's).

Service rules (`leads.py`, H4; none of these is a trigger):
- `stage_id` is a stage of the lead's own service type with phase Sales (roles Normal or Lost), or that type's
  Contract signed bookend, which only the signing service (area 6) can set.
- `service_type_id` changes only while no estimate names the lead (`estimate.lead_id`, area 6). A change moves the
  lead to the new type's first Sales stage, as one history row (`via` 'Service type changed').
- Expected value: while `expected_value_revision_id` is NULL, `lead.edit` may set `expected_value_cents`. Area 6's
  send service calls `leads.take_expected_value(context, lead_id, revision_id, total_cents)` in the send transaction:
  it writes both columns, and the audit row (event 'Estimate sent', before and after) is the lead history row the
  owner asked for (Q4 A). The pipeline, the forecast and `src_leads` read `expected_value_cents` only. No page
  computes it (rule e).
- Billing address: when `billing_same_as_site = 1` every reader returns the site address as the billing address;
  the copy into the customer at signing is area 5's.

Amendment 2026-11-20 (owner, from area 6 Q4): each estimate links to exactly one of `lead_id` or `case_id`. The lead estimate wizard picks an existing lead or creates one in the same transaction: `leads.create` is called inside the estimate service's
write transaction (one `authorize` for `lead.create`, then the estimate's own check), so a repeat customer's lead is
made inside the wizard and no separate lead form comes first. A lead made there gets the service type chosen at
wizard step 2 (Job), in the same transaction (S 11-19 8:42 PM: service type required on every lead), with its
Primary contact from step 1 and the first Sales stage of that type; a failure rolls back both
(docs/replan_2.9/area_6_estimates_contracts.md section 1.3).

**`lead_contact`** (new; Q6 A):
`lead_contact(lead_contact_id PK, lead_id NOT NULL FK lead, role TEXT NOT NULL CHECK IN ('Primary', 'Second'),
first_name TEXT NOT NULL, last_name TEXT NOT NULL, phone TEXT, email TEXT, preferred_channel TEXT NOT NULL CHECK IN
('Call', 'Text', 'Email'), row_version)`; UNIQUE (`lead_id`, `role`); CHECK `phone IS NOT NULL OR email IS NOT
NULL`; CHECK `preferred_channel <> 'Email' OR email IS NOT NULL`, likewise Call and Text need a phone. "Exactly one
Primary per lead" is the service's (the lead and its Primary are written in one transaction). Edits are refused once
the lead is closed. At signing, area 5's customer service receives the Primary (and the signer), not this table.

**`lead_source`** (new): `lead_source(source_id PK, name TEXT NOT NULL UNIQUE COLLATE NOCASE, is_shipped INTEGER
NOT NULL DEFAULT 0, is_active, sort_order, row_version)`. Seeded: Referral, Website, Phone call, Walk-in, Repeat
customer, Win-back (shipped). The shipped `Win-back` row cannot be renamed or hidden (service), because the win-back
report reads it; the others can be renamed and hidden; a used source is never deleted. C12.5's `category`,
`monthly_cost_cents` and `partner_contact_id` are design proposals, not built (open item 3).

**`lead_number_seq`** (new): `(seq INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL UNIQUE FK lead)`,
the existing sequence-table pattern. Unique, gaps allowed (Q20).

Corrected 2026-11-20 (consistency scan F5): This is a per-lead counter advanced by `sequences.py` inside the lead-creation transaction; no other code updates it, `lead_number_seq_no_delete` refuses deletion, and it has no `row_version`.

### 1.4 Lead stages and `lead_stage_history`

**Stage roles.** Area 8's `service_stage.stage_role` CHECK gains `'Lost'` (area 8 handed this over): each service
type gets one seeded Sales-phase stage with role Lost, named "Closed · Lost" (renamable, never removable, a service
rule like the other bookends). A lead reaches Won only when the signing service puts it in the type's Contract
signed stage (Q3 A); R33's Closed dialog offers Won (which opens Sign contract) or Lost (reason from the list).
Lead status for lists and reports is derived: Open (role Normal), Won (Contract signed), Lost (role Lost).

**`lead_stage_history`** (new, insert-only, the twin of area 8's `project_stage_history`, column for column where
they mean the same):

| Column | Type | Notes |
|--------|------|-------|
| `history_id` | INTEGER PK | |
| `lead_id` | INTEGER NOT NULL | FK lead |
| `from_stage_id` | INTEGER | FK service_stage; NULL on the first row |
| `to_stage_id` | INTEGER NOT NULL | FK service_stage |
| `effective_date` | TEXT NOT NULL | CHECK `= date(...)` |
| `recorded_at`, `recorded_by` | TEXT NOT NULL, INTEGER | `recorded_by` NULL only for origin System (auto-lost); CHECK |
| `direction` | TEXT NOT NULL | CHECK IN ('Start', 'Forward', 'Back', 'Skip') |
| `reason_id`, `reason_label`, `reason` | INTEGER, TEXT, TEXT | `reason_id` FK reason_option (RESTRICT); `reason_label` the label at the time of use, set iff `reason_id` is set (fix a); `reason` CHECK NULL or length 1-1000. Back needs a "Moving a lead back" reason; Lost needs a "Lost lead" reason; a correction needs text; "Other" needs at least 10 characters (service) |
| `warnings_continued` | TEXT | CHECK NULL or length <= 2000; the gate warnings shown and continued past (S 11-19 8:50 PM), with `continue_reason_id` INTEGER FK reason_option (kind Continue anyway, RESTRICT), `continue_reason_label` TEXT beside it (fix a) and the text in `reason` |
| `via` | TEXT NOT NULL | CHECK IN ('Lead created', 'Manual', 'Trigger', 'Auto-lost', 'Signed', 'Service type changed', 'Stage removed', 'Blocked', 'Unblocked') |
| `origin` | TEXT NOT NULL DEFAULT 'User' | CHECK IN ('User', 'System', 'Import'); CHECK `(origin = 'System') = (recorded_by IS NULL)` |
| `is_correction`, `corrects_history_id` | INTEGER, INTEGER | CHECK `(is_correction = 1) = (corrects_history_id IS NOT NULL)`; self FK |
| `close_outcome` | TEXT | CHECK NULL or IN ('Won', 'Lost'); only on the row into Contract signed or Lost |

Integrity triggers `lead_stage_history_no_update` and `_no_delete` (the `stage_trigger_run` pattern). Indexes
(`lead_id`, `history_id`), (`to_stage_id`, `effective_date`). Audit trigger on insert only.

The same rules as area 8 section 1.3, enforced by `lead_stages.py` (permission `lead.edit`, row limits of section
7): effective date not after `context.today` (H2) and not earlier than the row that put the lead in its current
stage; Skip needs `can_skip`; Back needs a reason; `lead.stage_id`, `close_outcome`, `lost_*` and `closed_on` are
written in the same transaction as the history row; days in stage = today minus the latest row's effective date;
`stage_requirements_block` (area 8) decides warn or refuse for gates; `stage_backdate_days` and `job.stage.backdate`
apply to leads too (one rule, area 8 Q4 A; open item 6). Block and unblock are rows with the same from and to stage
(`via` Blocked or Unblocked; Q22 A), so blocked days are measurable. Lost is final except by a correction row
(Q2 A); a correction of a Lost row puts the lead back in the stage it was lost from and clears the lost columns.

The lead gate checks of S 11-19 8:50 PM (no sent estimate before Proposal reviewed; sign on an expired, unsent or
unapproved estimate) are stage requirements of the existing trigger model (area 8 `stage_trigger`, a 'Require'
action) plus one built-in check in `lead_stages.py` that reads area 6's sent-revision status. No new table.

### 1.5 Auto-lost and win-back

- `company_settings.auto_lost_days` INTEGER NOT NULL DEFAULT 14 CHECK (0-365; 0 = off) and `auto_lost_warn_days`
  INTEGER NOT NULL DEFAULT 3 CHECK (0 to `auto_lost_days`). Changed by `crm.settings` with a reason, audit-logged.
  The default of 14 is the owner's (F5, Q15).
- `leads.run_auto_lost(context)`: origin System, run at app open and on the desktop schedule while open (as area 8's
  time-based triggers, A 11-15 3:30 PM item 5), hosted on a schedule. For each open lead whose latest sent revision
  is older than `auto_lost_days` (by `context.today`) and has no signed contract: one history row (`via`
  'Auto-lost', `origin` System, reason the shipped Lost lead reason "No signature in N days (automatic)" with N
  filled in), `is_auto_lost = 1`, and area 6's `estimates.mark_expired` in the same transaction. Idempotent (a lead
  already closed is skipped). It never posts, approves or moves money (rule 0).
- The N−3 warning is derived (no column): the lead shows the R27 box and the run writes one notification to the
  sales rep per lead and revision (area 21's feed; open item 1), keyed so it is written once.
- `leads.recreate(context, lost_lead_id)`: only from a Lost lead; a new lead with `recreated_from_lead_id`, the
  customer, addresses, contacts and service type copied, source Win-back, first stage; the lost lead is unchanged.
  Reports: win-backs are leads with `recreated_from_lead_id` set; win rate as for any lead set.

### 1.6 How it lands in the baselines

`001_company.sql` only: tables `lead`, `lead_contact`, `lead_source`, `lead_number_seq`, `lead_stage_history` and
its two integrity triggers; audit triggers for each; the value `'Lost'` in area 8's `stage_role` CHECK and one Lost
stage per seeded service type; three `company_settings` columns (1.5 and 3.4); `lead_source` seeds; the shipped
reasons of section 7.3. `custom_field_def.record_type` CHECK gains `'Lead'` and `'Case'` (Q23 A; the scoping columns
are area 16's). Area 6 adds `estimate.lead_id` (FK lead) and the revision table that `expected_value_revision_id`
points to (open item 2).

### 1.7 Effect on existing services and tests

- No service reads or writes leads today, so nothing breaks. `custom_fields.py` keeps `RECORD_TYPES` as it is and
  refuses `Lead` and `Case` with the Estimate-style sentence until `leads.py` and `cases.py` exist (the baseline
  CHECK allows them first, as it does Estimate).
- `permissions.py:65`: `project.create` becomes "Create jobs" when the `lead.*` codes arrive (section 7.1); the
  registry and the seeded rows change together (`tests/test_permissions_registry.py`).
- `tests/test_schema_replan.py`: `AUDITED_TABLES_REPLAN` (`:731`) gains every new table; the `service_stage` tests
  (`:516-545`) gain a Lost-role row.
- `modules/views_dashboard.py:62` stays legacy sample text until Phase 3.

### 1.8 Tests to write later

- `lead`: CHECKs (billing columns NULL when same as site; lost columns only when Lost; `project_id` only when Won;
  auto-lost only when Lost; `closed_on` with outcome); `lead_number` from the sequence, never reused.
Corrected 2026-11-20 (consistency scan F5): Tests to write later: two leads created in a row receive consecutive numbers; deleting a `lead_number_seq` row is refused.
- Service type lock: changing it with no estimate writes a 'Service type changed' row; with one estimate it is
  refused with the exact sentence.
- Expected value: editable before a sent revision; after `take_expected_value` an edit is refused, the value equals
  the revision total, and the audit row shows before and after; a second sent revision updates it again.
- `lead_contact`: no phone and no email refused; preferred Email without an email refused; a second Primary refused
  (UNIQUE); edits on a closed lead refused.
- History: the update and delete triggers refuse; every area 8 history test repeated for leads (future date,
  earlier than current, Back without reason, Skip without `can_skip`, correction with zero interval); a Lost move
  without a Lost lead reason refused; "Other" with 9 characters refused; a stage of another service type refused;
  only the signing service reaches Contract signed.
- Gates: with `stage_requirements_block` 0 a move to Proposal reviewed without a sent estimate returns the warning
  and saves with a continue reason in `warnings_continued`; with 1 it is refused.
- Auto-lost: day 13 nothing, day 11 (N−3) one notification and only one after a second run, day 14 Lost with the
  automatic reason and the estimate Expired, in one transaction; `auto_lost_days = 0` never closes; a new sent
  revision restarts the count; a run with a clock read fails the static H2 test.
- Win-back: only from Lost; copies; the lost lead unchanged; a second recreate refused (UNIQUE).

---

## 2. Activities and activity types

### 2.1 Current state

No activity, follow-up, task or appointment table; no reminder. Area 8 (approved) defines `crew` and
`calendar_item` (with `user_id`, `crew_id`, `contact_id`, `start_time`, `length_minutes`) and says the busy check for
users and crews is area 15's. The baseline has `alert_dismissal` (audited, `tests/test_schema_replan.py:736`) for
closed alert strips.

### 2.2 Decided

| Decision | Source |
|----------|--------|
| The CRM word is **Activity**; page "Activities" (tabs Overdue, Today, This week, Later, Done; List, Week, Month); a lead shows its "Next activity"; planned and done are one record ("Mark done" logs a planned one, "Log an activity" records a past one); replaces "Next step" and "Follow-up" | S 11-17 5:55 PM; ux_research section 5.1 |
| Fields: type, due (date, optional time), length if an appointment, owner, attendees, invited contacts, location, linked lead/customer/case, done_at and done_by, notes; a lead's next activity is its earliest open one | A 11-17 5:55 PM item 1 |
| Activity types are company-defined: name, icon, is_appointment, default_length, counts_as_contact, active; seeded generic (Call, Email, Text, Meeting, Site visit, Task) | A 11-17 5:55 PM item 2; ux_research 5.2 |
| An appointment has a start, a length (default from its type, editable) and a location (default the lead's site address); attendees are company people; it shows on each attendee's calendar, the PM Job calendar and PM home | A 11-17 5:51 PM item 1; ux_research 3.2-3.3 |
| Busy check across a user's appointments and timed schedule items, and per crew; a warning only (rule 0) | A 11-17 5:51 PM item 2; 5:55 PM item 3 |
| Crews: name, trade tag, active, no members; assignable to schedule tasks and appointments | A 11-17 5:55 PM item 3; area 8 Q13 A |
| Every calendar item, appointments included, goes as an .ics invite to one company calendar address only; individuals get no invites; attendees and a link are written in the event details; one way | S 11-18 11:45 AM (replaces the 11-17 attendee invites) |
| Desktop reminders show in the app at next login; emails go out only while the app runs; hosted sends on time | A 11-17 5:51 PM item 4; S 11-17 |
| Mark done asks for the next activity; a lead with none shows a gold notice | ux_research 3.1 |
| Alerts create activities (speed to lead, proposal follow-up, stale digest) | ux_research section 1 and 5.1 |
| Status update is an activity type (Overall; on jobs also Schedule and Budget; shared with the customer; photos); it does not count as contact | C31 (but see F12) |
| Team: "Logged for" behind "Logging this for someone else?"; the person who entered it is always the signed-in user | C13.4; C12.6, C12.10 |
| Desktop team features (mentions, routing, notifications) work between turns on one PC; real time is hosted | planning log 3b 16:10 |

### 2.3 Proposed schema

**`activity_type`** (new): `activity_type(type_id PK, name TEXT NOT NULL UNIQUE COLLATE NOCASE, icon_key TEXT NOT
NULL, is_appointment INTEGER NOT NULL DEFAULT 0, default_length_minutes INTEGER, counts_as_contact INTEGER NOT NULL
DEFAULT 1, is_shipped, is_active, sort_order, row_version)`. CHECK `default_length_minutes` NULL unless
`is_appointment = 1`, and 5-1440 when set. `icon_key` is a key from a fixed icon set the front end draws (H6: no
visual value in the database). Seeds: Call, Email, Text (contact, not appointment), Meeting (appointment, 60),
Site visit (appointment, 60), Task (not contact, not appointment). Shipped types can be renamed and deactivated,
never deleted once used.

**`activity`** (new):

| Column | Type | Notes |
|--------|------|-------|
| `activity_id` | INTEGER PK | |
| `type_id` | INTEGER NOT NULL | FK activity_type |
| `subject` | TEXT NOT NULL | CHECK length 1-200 ("Follow up on the sent estimate") |
| `notes` | TEXT | CHECK NULL or length <= 4000 |
| `due_date` | TEXT | CHECK `IS date(...)`; NULL for a logged-only activity |
| `start_time` | TEXT | 'HH:MM' local company time (`company_settings.timezone`); CHECK needs `due_date` |
| `length_minutes` | INTEGER | CHECK NULL or 5-1440; needs `start_time` |
| `owner_user_id` | INTEGER NOT NULL | who it is assigned to ("Logged for"); default the lead's sales rep or the case owner |
| `location` | TEXT | CHECK NULL or length <= 300; default the lead's site address (service) |
| `crew_id` | INTEGER | FK crew (area 8) |
| `lead_id`, `customer_contact_id`, `case_id`, `project_id` | INTEGER | FKs lead, contact, service_case, project; CHECK at least one set; `project_id` per Q7 A |
| `done_at`, `done_by` | TEXT, INTEGER | when it happened (UTC with offset, not after `context.now`) and who did it; CHECK both or neither |
| `outcome` | TEXT | CHECK NULL or length <= 1000; the "what happened" text |
| `cancelled_at`, `cancelled_by`, `cancel_reason` | TEXT, INTEGER, TEXT | CHECK all set or all NULL; CHECK not both done and cancelled |
| `remind_minutes_before` | INTEGER | CHECK NULL or 0-10080; needs `start_time` or `due_date` (Q11 A) |
| `origin` | TEXT NOT NULL DEFAULT 'User' | CHECK IN ('User', 'Alert', 'Trigger', 'System', 'Import') |
| `alert_key` | TEXT | the alert or trigger event that made it, so a rerun does not add a second (partial UNIQUE where NOT NULL) |
| `overall_health`, `schedule_health`, `budget_health`, `shared_with_customer` | TEXT, TEXT, TEXT, INTEGER | only for a status update (Q8 A); CHECK IN ('On track', 'At risk', 'Off track') or NULL |
| `created_at`, `created_by` | TEXT NOT NULL, INTEGER NOT NULL | the signed-in user who entered it, always |
| `row_version` | INTEGER NOT NULL DEFAULT 1 | the .ics SEQUENCE too (open item 5) |

Status is derived: Open (neither done nor cancelled), Done, Cancelled. Indexes: partial (`lead_id`, `due_date`,
`start_time`) WHERE open; (`owner_user_id`, `due_date`); (`due_date`) for the calendar; (`case_id`), (`project_id`).

**`activity_attendee`** (new): `(activity_id FK, user_id INTEGER, PRIMARY KEY both)`, insert and delete only.
The owner is not repeated here; the service treats owner plus attendees as the people on it.

**`activity_contact`** (new; Q9 A): `(activity_contact_id PK, activity_id NOT NULL FK, lead_contact_id FK
lead_contact, contact_id FK contact)`; CHECK exactly one of the two. The customer people taking part, written into
the event details; nobody is sent an invite (S 11-18 11:45 AM; conflict F4). When area 5 adds a contact-person table,
`contact_id` may become a person id (open item 4).

**Rules (`activities.py`, H4):**
- Next activity of a lead = the open activity with the lowest (`due_date`, `start_time` with no time last,
  `activity_id`), and "none" when there is none. Derived in one read, never stored (C12.6's
  `next_step_activity_id` is superseded, F8).
- An appointment type needs `due_date` and `start_time`; length defaults from the type. Any type may have a time
  (a call at 10:00), but only `is_appointment` types take a length, attendees, contacts, crew and location
  (service), matching the 5:55 PM "is an appointment (it has a time, attendees and a location)".
- Owner and attendees are users with company access; another person as owner needs `activity.log_for_others`.
- Mark done: sets `done_at`/`done_by`, and the service returns "What's next?" for the caller; nothing forces a next
  activity. "Counts as contact" stops speed-to-lead and resets "stale" (C31).
- Every create, reschedule (date, time, length, location, attendees) and cancel of an appointment raises the
  calendar event for area 20 (update with SEQUENCE = `row_version`, CANCEL on cancel), only while
  `company_calendar_on` (area 20). With no mailbox, the reply offers a downloadable .ics (A 11-17 5:51 PM item 3).
- **Busy check** (`activities.busy_for(context, users, crew_id, date, start, length, exclude_activity_id)`): returns
  warnings, never refuses. It reads open appointments where the person is owner or attendee or the crew matches,
  area 8 `calendar_item` rows by `user_id`/`crew_id` with `start_time` and `length_minutes`, and (Q10 A) a crew on a
  `job_schedule_task` counts as busy all day on each of that task's work days. Each warning is one sentence naming
  the clash ("Tomas Okafor has a site visit at RI0001-003 10:00–11:00").
- Reminders (Q11 A): desktop shows due reminders in the app at the next sign-in and while open, and emails them only
  while the app runs; hosted sends on time. The reminder is a notification in area 21's feed, keyed per activity and
  `row_version`, so it is written once.
- Calendar read for area 21 and the Activities Week/Month views: `activities.calendar_rows(context, date_from,
  date_to, people, crews)` returns date, time, length, title, link, attendees, crew and location, with the row limits
  of section 7.2 applied in the service.

### 2.4 Lands, effects, tests

- Lands in `001_company.sql`: `activity_type` (seeded), `activity`, `activity_attendee`, `activity_contact`, audit
  triggers on each. Area 18's `attachment.record_type` CHECK gains 'Activity' (photos on a status update, C31) and
  'Lead' and 'Case' (lead-new attachments, C104 case attachments).
- No existing service changes.
- Tests: the CHECKs (time needs a date, length needs a time, done pair, cancel triple, not both done and cancelled,
  at least one link, health only with values from the list); next activity ordering with mixed timed and untimed
  rows and ties; an alert rerun adds no second activity (`alert_key`); busy check finds a clash with an attendee's
  appointment, a calendar item and a crew task day, and saving still succeeds; a non-appointment type refuses
  attendees; `log_for_others` needed for another owner; reminders written once per version; the calendar read hides
  a lead the viewer may not see.

---

## 3. Service cases

### 3.1 Current state

Nothing. docs/crm_pm_design.md section 4.2 sketches `service_case` as a 1:1 detail of a `project` of kind 'Service
case'; the owner's 11-18 decisions replace that shape (conflict F3). Area 8 adds `project.source_case_id` as a plain
integer and leaves `service_case`, `case_job` (not built, Q13 B) and the Resolve prompt to this area. `src_cases` (reports contract)
reads `service_case` and its status history.

### 3.2 Decided

| Decision | Source |
|----------|--------|
| Case fields: customer, optional job, type, channel (received via), priority, owner (user or team), due, status, resolution, comments, attachments; audit-logged | A 11-15 2:34 PM item 4; C104 |
| Types: Complaint, Service or warranty, Billing question, Cancellation request. Default owner by type: Complaint and Service to the job's PM (Operations with no job), Billing to Accounting, Cancellation to the sales rep. Default due in business days: 2, 5, 3, 1, set in CRM settings; owner and due stay editable | A 11-15 2:41 PM; C104 |
| Statuses Open, In progress, Waiting on customer, Resolved, Closed; changed only through actions, never a dropdown; Resolve needs a resolution note; Reopen needs a reason; a closed case offers only "Create follow-up case" | S 11-18 2:08 AM |
| Allowed transitions: Open → In progress / Waiting / Resolved; In progress → Waiting / Resolved; Waiting → In progress / Resolved; Resolved → In progress (Reopen) / Closed; Closed is final, a follow-up links by `parent_case_id` | A 11-18 "case status history" item 3 |
| `case_status_history(case_id, from_status, to_status, changed_at, changed_by, note)`, append-only, no updates or deletes | A 11-18 item 1; S 11-18 2:08 AM |
| `opened_at`, `first_resolved_at` (set once), `last_resolved_at` (each Resolve), `closed_at`, `reopen_count` (+1 each Reopen); nothing is cleared | A 11-18 item 2 |
| Auto-close Resolved cases after the company setting (default 7 days), `changed_by` = System | A 11-18 item 4; S 11-18 2:08 AM |
| Days to resolve = calendar days opened → last resolved, waiting included | A 11-18 item 5 |
| Cases show the R33 path, display only | S 11-18 2:14 AM |
| Service quotes from cases | Estimate cost work moves an Open case to In progress. Signed-quote upload creates the job and contract. Decline or expiry leaves the case open. Read linked jobs by `project.source_case_id` (Q13 B). When all linked jobs complete, show a Resolve prompt. | Owner 2026-11-20, 2:10 PM |
| "Create service job" makes a job of type Service for the same customer and site | S 11-18 2:14 AM |
| Cases tab on customer and job; job header "2 open cases"; homes show "Cases due today" (overdue included) | C104 |
| Contract cancellation: reason, date received, case link; never auto-posts; approval OFF by default | A 11-15 items 5 and 2:41 PM; C105 (area 6) |

### 3.3 Proposed schema

**`case_type`** (new; Q12 B): `case_type(case_type_id PK, name TEXT NOT NULL UNIQUE COLLATE NOCASE, kind TEXT NOT
NULL CHECK IN ('Complaint', 'Service', 'Billing', 'Cancellation', 'Other'), default_owner TEXT NOT NULL CHECK IN ('Job
PM', 'Sales rep', 'User'), default_owner_user_id INTEGER NULL, default_due_business_days INTEGER CHECK (NULL or
0-60), is_shipped, is_active, sort_order, row_version)`; CHECK `default_owner_user_id` NULL unless `default_owner =
'User'`. No role queue (Q12 B). Seeds: Complaint: Job PM, 2; Service or warranty: Job PM, 5; Billing question: User,
3; Cancellation request: Sales rep, 1. `kind` drives fixed behaviour (Cancellation offers "Cancel the contract",
area 6), so the names can change.

**Default owner user (open item 13, owner 2026-11-20 12:05 AM):** `default_owner_user_id` names a user (a plain
integer: the user table is in the master and a company file has no cross-file FK, CLAUDE.md section 4; the service
checks the user exists). It is empty in every shipped type and set in CRM settings (`crm.settings`). Creating a case
fills the owner from the type's default (the job's PM, the sales rep, or `default_owner_user_id`). When that gives no
user, or the user is inactive, the person logging the case picks the owner. The service refuses a case with no owner
("Choose who owns this case.").

**`service_case`** (new):

| Column | Type | Notes |
|--------|------|-------|
| `case_id` | INTEGER PK | |
| `case_number` | TEXT NOT NULL UNIQUE | `CS-0001` from `case_number_seq` (Q20) |
| `customer_contact_id` | INTEGER NOT NULL | FK contact (a customer with a code; service) |
| `project_id` | INTEGER | FK project, the job it is about (optional) |
| `lead_id` | INTEGER | FK lead, for a case raised before signing (rare; optional) |
| `case_type_id` | INTEGER NOT NULL | FK case_type |
| `channel` | TEXT NOT NULL | CHECK IN ('Phone', 'Email', 'Text', 'In person', 'Website', 'Other') |
| `priority` | TEXT NOT NULL DEFAULT 'Normal' | CHECK IN ('Low', 'Normal', 'High', 'Urgent') |
| `description` | TEXT NOT NULL | CHECK length 1-4000 |
| `owner_user_id` | INTEGER NOT NULL | Q12 B: always a user holding `case.work` (service; R25 picker); no role queue |
| `due_date` | TEXT | CHECK date; default from the type in business days (area 13's work week and holidays) |
| `status` | TEXT NOT NULL DEFAULT 'Open' | CHECK IN ('Open', 'In progress', 'Waiting on customer', 'Resolved', 'Closed') |
| `resolution_note` | TEXT | CHECK NULL or length 1-4000; required by Resolve (service) |
| `opened_at` | TEXT NOT NULL | UTC with offset |
| `first_resolved_at`, `last_resolved_at` | TEXT | CHECK both NULL or both set; CHECK `first_resolved_at <= last_resolved_at` |
| `closed_at` | TEXT | CHECK `(status = 'Closed') = (closed_at IS NOT NULL)` |
| `reopen_count` | INTEGER NOT NULL DEFAULT 0 | CHECK >= 0; CHECK `reopen_count = 0 OR first_resolved_at IS NOT NULL` |
| `parent_case_id` | INTEGER | self FK (follow-up case) |
| `created_by` | INTEGER NOT NULL | |
| `row_version` | INTEGER NOT NULL DEFAULT 1 | |

CHECKs describe a row's shape only. "Resolved and Closed need `last_resolved_at`" is a CHECK too (`status NOT IN
('Resolved', 'Closed') OR last_resolved_at IS NOT NULL`). Transitions are the service's (H4).

**`case_status_history`** (new, insert-only): `(history_id PK, case_id NOT NULL FK, from_status TEXT (NULL on the
first row), to_status TEXT NOT NULL, changed_at TEXT NOT NULL, changed_by INTEGER, origin TEXT NOT NULL CHECK IN
('User', 'System'), note TEXT CHECK NULL or length 1-4000, via TEXT NOT NULL CHECK IN ('Opened', 'Action',
'Estimate cost work started', 'Auto-close'))`; both status columns CHECK IN the five statuses; CHECK `(origin = 'System') =
(changed_by IS NULL)`. Triggers `case_status_history_no_update` and `_no_delete`. Index (`case_id`, `history_id`).

**Case to job link (Q13 B):** no `case_job` table. `project.source_case_id` (area 8's column) gets its FK to
`service_case` and an index in the same pass (area 8 open item 4). A case's jobs are the projects with that
`source_case_id`, read through the index; there is one link, so no test is needed to keep two in step.

**`case_number_seq`** (new), the sequence pattern.

Corrected 2026-11-20 (consistency scan F5): This is a per-case counter advanced by `sequences.py` inside the case-creation transaction; no other code updates it, `case_number_seq_no_delete` refuses deletion, and it has no `row_version`.

**Settings:** `company_settings.case_auto_close_days` INTEGER NOT NULL DEFAULT 7 CHECK (0-90; 0 = off; Q15).
`company_settings.service_job_type_id` INTEGER FK service_type, the default for "Create service job" (Q14 A;
seeded to a shipped "Service" type with its own short delivery stages).

### 3.4 Rules (`cases.py`, `case_jobs.py`; H4)

- One status function `cases.change_status(context, case_id, action, note, reason)`: the five-status transition table
  above; Resolve sets `last_resolved_at` and, the first time, `first_resolved_at`; Reopen (Resolved → In progress)
  needs a reason and adds 1 to `reopen_count`; Close sets `closed_at`; Closed refuses every action. Each call writes
  one history row and the case row in one transaction, after `authorize(context, 'case.work', ...)`.
- On both create and edit, the case save service verifies that any selected job belongs to the selected customer
  (`project.contact_id` matches `service_case.customer_contact_id`). It validates due dates as real calendar dates and
  requires the selected owner to be an active eligible user holding `case.work`. Run these checks inside the create
  or edit transaction before any `service_case` or `case_status_history` write.
- Opening writes the first row (NULL → Open, `via` Opened). Owner and due default from the type: Job PM gives the
  job's PM, Sales rep the job's or lead's sales rep, User the type's user; the owner is always a user (Q12 B); when
  the default gives none or an inactive user, the person logging the case picks the owner (open item 13, closed).
- `cases.run_auto_close(context)`: origin System; measure the configured elapsed calendar days from the latest
  `last_resolved_at`. At the first scheduled check at or after the threshold, close a Resolved case (`via`
  Auto-close); zero means off. The run is idempotent and uses the same schedule as auto-lost.
- Starting estimate cost work moves an Open case to In progress through `cases.change_status`. Signed-quote upload creates the service job and derived contract row. Decline or expiry leaves the case open.

  **Withdrawn 2026-11-20 (owner 3:15 AM)** (see the 3:15 AM line below): Amendment 2026-11-20 (owner 2:45 AM, from area 7): "Create service job" makes a 'Case warranty' job (Warranty, Not
  billed, value 0) or a 'Case T&M' job (billable repairs under the quote limit, at company rates frozen onto the
  contract, optional not-to-exceed), each with its one contract row and no signed file, through area 7's
  `jobs.create_service_job`. Billable work over the limit starts a Service quote instead (area 6's estimate flow with
  service terms); its job is created when the quote is accepted. New setting `company_settings.service_quote_limit_cents`
  INTEGER NOT NULL DEFAULT 100000 CHECK (>= 0) (Settings › Service; $1,000), changed with `company.settings` and a
  reason, audit-logged. How the limit is applied to a Case T&M job, and the quote's lead, are area 7 open items
  (section 13).

  Amendment 2026-11-20 (owner 3:15 AM, from area 7; replaces the 2:45 AM sources): there are no direct case jobs.
  "Create service job" starts a service quote from the case: an estimate with `case_id`, the case's customer and no
  lead (area 6 section 1.3 amendment), in the same estimate flow with service terms, for billable, warranty or
  no-charge, and T&M work alike; there is no quote limit and no `service_quote_limit_cents`. Starting the quote needs
  `case.work` and `estimate.create`. The service job is created only when the rep uploads the signed quote with Mark
  signed (area 6 section 9.3), which also moves an Open case to In progress (`via` 'Service job created').

Withdrawn 2026-11-20 (owner 2:10 PM): the preceding automatic transition to In progress on signed-quote upload is
replaced by the cost-work-start rule below; signed-quote upload still creates the service job and its contract row.

Amendment 2026-11-20 (owner 2:10 PM, service quote rules): starting cost work moves the case to In progress. A
declined or expired quote leaves the case open (Waiting on customer, or Resolve with a note).
- Resolve prompt (derived, never stored, never automatic): a case not Resolved or Closed with at least one job whose
  `source_case_id` is the case, and every such job in a Complete or Closed stage role (area 8). Area 8's job stage
  service, when a job with a `source_case_id` reaches Complete, writes one notification to the case owner (area 21
  feed).
- Days to resolve and the open-case counts are computed in the service and the reports layer, never in a page, and
  without SQLite-only date functions (H5).

Amendment 2026-11-21 (to_planning 2026-11-21 "Area 15 CRM intake audit follow-up"): case create and edit check that
the job belongs to the case's customer, that due dates are real calendar dates and that the owner is active and holds
`case.work`, before any write. Amendment 2026-11-22 (shared_decisions 2026-11-22 2:25 AM "service case auto-close can
be turned off", owner confirmed): auto-close counts from the latest Resolve, default 7 days (Case settings); 0 turns
it off and those cases are closed by hand.

### 3.5 Lands, effects, tests

- Lands in `001_company.sql`: `case_type` (seeded), `service_case`, `case_status_history`, `case_number_seq`, their
  integrity and audit triggers, two `company_settings` columns, the FK and index on `project.source_case_id` (no
  `case_job`, Q13 B), the shipped Service type.
- No existing service changes. Area 17's `src_cases` can be offered once `cases.py` exists.
- Tests: every allowed transition passes and every other one is refused with one sentence; Resolve without a note
  and Reopen without a reason refused; `first_resolved_at` set once across Resolve, Reopen, Resolve; `reopen_count`
  counts; nothing is cleared; history update and delete refused; a Closed case refuses every action and offers only a
  follow-up with `parent_case_id`. The first scheduled auto-close check at or after the configured elapsed time
  from the latest Resolve closes the case (day 7, not day 6 at the default), with origin System and `changed_by`
  NULL. `case_auto_close_days = 0` never closes. Creating a service job writes `source_case_id` and the In progress
  row in one transaction and rolls both back on a job validation error. A second job on the same case works and the
  case's job list (read by `source_case_id`) shows both; a case with no owner is refused (NOT NULL and the service
  sentence); the Resolve prompt appears only when every job of the case is complete; days to resolve includes
  waiting time.
- `test_case_due_date_rejects_impossible_calendar_dates`: case create and edit reject dates that are not real
  calendar dates, such as February 31.
- `test_case_owner_must_be_active_and_eligible`: create and edit require a selected owner who is active and holds
  `case.work`; refuse an inactive or ineligible owner.
- `test_case_job_customer_mismatch_writes_no_case_or_history`: on both create and edit, reject a selected job whose
  customer differs from the selected case customer. Create writes no case or history; edit leaves the case and its
  history unchanged.

Amendment 2026-11-21 (to_planning 2026-11-21 "Area 15 CRM intake audit follow-up"): the due-date, eligible-owner and
customer/job mismatch tests above. Amendment 2026-11-22 (shared_decisions 2026-11-22 2:25 AM "service case auto-close
can be turned off", owner confirmed): the auto-close test counts from the latest Resolve, closes at day 7 and not day
6 at the default, and 0 never closes.

Corrected 2026-11-20 (consistency scan F5): Tests to write later: two cases created in a row receive consecutive numbers; deleting a `case_number_seq` row is refused.

Withdrawn 2026-11-20 (owner 2:10 PM): the section 3.5 test requiring service-job creation to move the case to In
progress in the same transaction is superseded; tests must instead cover the case transition when cost work starts.

Amendment 2026-11-20 (service-quote decision reconciliation): cases become In progress when cost work starts, not
when a job or quote is created. Signed-quote upload creates the service job and its internal contract row; a
declined or expired quote leaves the case open (Waiting on customer, or Resolve with a note). Tests to write later
must verify each transition separately, including that job/contract creation happens only on signed-quote upload.

---

## 4. Comments and mentions

### 4.1 Current state and decided

Nothing in the baseline (crm_pm_design.md 4.2 sketches `comment` and `notification`, not built). Decided: internal
comments with @mentions on leads, jobs, estimates and cases, never printed or sent to customers (A 11-15 2:34 PM
item 3; C103); notifications only to the people mentioned plus the record's owner when someone else comments (A 11-15
2:41 PM; C103); a "Mentions" card on the homes (C103). "Owner" here is the sales rep on a lead and an estimate, the
PM on a job, the case owner on a case (F15).

### 4.2 Proposed schema

- `comment(comment_id PK, record_type TEXT NOT NULL CHECK IN ('Lead', 'Project', 'Estimate', 'Case'), record_id
  INTEGER NOT NULL, body TEXT NOT NULL CHECK length 1-4000, created_at, created_by, edited_at, removed_at,
  removed_by, removed_reason, row_version)`; CHECK the three removed columns all set or all NULL. Index
  (`record_type`, `record_id`, `comment_id`). No thread column (C103 shows none).
- `comment_mention(comment_id FK, user_id INTEGER, PRIMARY KEY both)`, insert-only.
- Rules (`comments.py`): commenting needs the read permission of the record (`lead.view` with its row limits,
  `project.view` with project scope, the estimate read code of area 6, `case.view`), no separate code. Mentioned
  users are those the picker offers (R25: active, with access to this company and the record's read permission).
  Q17 A: the author may edit (`edited_at` shown as "Edited"; the earlier text stays in the audit log) and remove (a
  reason, the row kept and hidden). Notifications go to area 21's feed. Print, PDF and every customer-facing
  document never read this table (a static test).
- Tests: a comment on a lead the user cannot see is refused; mentions notify exactly the mentioned plus the owner
  (not the author); edit by someone else refused; removal needs a reason and keeps the row; the print and send
  services do not import `comments`.

---

## 5. Routing and assignment

### 5.1 Current state and decided

Nothing in the baseline. Decided: lead assignment rules per service type in Settings > Routing (round-robin between
chosen reps with a stored next-up pointer, one fixed rep, or unassigned), managed by Admins and Sales rep ·
Manager; skip inactive or away users; a hand-picked rep always wins; changes logged (A 11-17 8:17 PM item 5, area
18 O5; S 11-17 8:17 PM). Everything routed to another user lets the sender choose from people who can act on it,
with the Approvers default suggested, and the choice logged; "Estimate requests go to an estimator" is a control,
OFF (S 11-15 8:36 PM; C120). Leads import uses the rule when Sales rep is blank (C12.9). C12.2's ZIP territories,
"by job type" and "creator" rules are superseded by the 11-17 owner rule (F16).

### 5.2 Proposed schema and rules

- `lead_assignment_rule(service_type_id PK FK service_type, mode TEXT NOT NULL DEFAULT 'Unassigned' CHECK IN
  ('Round-robin', 'Fixed user', 'Unassigned'), fixed_user_id INTEGER, next_up_user_id INTEGER, row_version)`; CHECK
  `fixed_user_id` set iff mode is Fixed user. A service type with no row is Unassigned (the default: no automatic
  assignment unless a company sets it).
- `lead_assignment_member(service_type_id FK lead_assignment_rule, user_id INTEGER, sort_order INTEGER NOT NULL,
  PRIMARY KEY both)`, insert and delete only.
- `leads.assign_new(context, lead)`, inside the lead-create transaction: a hand pick wins; else Fixed user; else
  Round-robin from `next_up_user_id` in `sort_order`, skipping users who are inactive, lack company access or
  `lead.own`, or are away (Q21 A), then the pointer moves to the next member in the same transaction; with nobody
  eligible the lead stays Unassigned and the reply says why in one sentence. Reassigning a lead's sales rep later
  needs `lead.assign` (or `lead.edit` on one's own lead to hand it on, Q18), logged by the audit trigger.
- Q21 A: `user_away(away_id PK, user_id INTEGER NOT NULL, from_date TEXT NOT NULL, to_date TEXT NOT NULL, note,
  row_version)`, CHECK `from_date <= to_date`; set by the user or an Admin; read by round-robin and shown in pickers
  ("Away until …"). Per company, not in the master.
- Case owner routing is the `case_type` defaults (section 3.3). Estimate request routing (`estimate_requests_routed`,
  `routed_to_user_id`, `route_note`) belongs to areas 6 and 14 (C120).
- Tests: round-robin over three members with one inactive and one away gives the expected order and pointer; a hand
  pick does not move the pointer; Fixed user who has lost `lead.own` leaves the lead Unassigned with the sentence;
  member insert and delete audited; a rule change by a Sales rep · Standard refused.

---

## 6. Boundaries with other areas

| Area | Owns | Area 15 asks or provides |
|------|------|--------------------------|
| 5 Customers | The customer create service and validation, the contact-person table, structured customer addresses | Signing (area 6) passes the lead's site and billing address, Primary contact and signer to area 5's service; on success `lead.customer_contact_id` is set. A Repeat customer lead links an existing customer at creation. Leads never create customers |
| 6 Estimates and contracts | `estimate` replan, revisions, sending, approval, signing, Expired, cancellation, the sales rep on the estimate and contract | Adds `estimate.lead_id` and makes `estimate.contact_id` nullable before signing (today NOT NULL, `:217`); the send calls `leads.take_expected_value`; `mark_expired` is called by auto-lost; signing moves the lead to Contract signed (`via` Signed), sets `close_outcome` Won and `lead.project_id`; the estimate copies `lead.sales_rep_user_id` (for `src_rep_contract_payments`). The lead-side gate reads "has a sent revision" and "is approved, unexpired" from area 6. **Hand-off (fix b, owner 11:20 PM):** area 6 adds `contract.sales_rep_user_id` INTEGER, written once by the signing service from `lead.sales_rep_user_id` and kept as the rep at signing (not changed when the job's rep changes); in the same signing transaction it copies the same value to `project.sales_rep_user_id` (area 7's column) |
| 7/8 Jobs | The job record, its stages, `billing_method`, `cost_destination`, `warranty_for_job_id`, `source_case_id` column, `crew`, `calendar_item` | Area 15 adds the FK and index on `source_case_id` (no `case_job`, Q13 B), the stage role 'Lost', reuses `crew` and `calendar_item` times for the busy check. The job page timeline shows the job's activities and, through `lead.project_id`, the lead's sales history (C31's "one continuous record" as a view, F1). **Hand-off (fix b, owner 11:20 PM):** area 7 adds `project.sales_rep_user_id` INTEGER (NULL when the lead had no sales rep), copied from `lead.sales_rep_user_id` at signing and editable afterwards with history (the audit log's before and after rows, no new table); area 8's change order "Forward to sales rep" ('With sales rep') reads `project.sales_rep_user_id` |
| 14 Approvals | `pending_approvals`, approval chains | C13.5 sales approvals (`deal_stage_move`) are not designed here (open item 7) |
| 16 Custom fields | Scoping by service type and stage, board-card, help text | Area 15 adds `'Lead'` and `'Case'` to `record_type` (Q23 A) |
| 17 Reports | Records sources | Supplies the base tables of `src_leads`, `src_leads_estimates` (with area 6), `src_activities`, `src_cases`, `src_lead_job_invoices`; field ids `lead.sales_rep`, `lead.status` (derived), `lead.days_in_stage`, `lead.source`, `lead.created_on`. Row limits of section 7.2 are what report section 5.4 applies |
| 20 Connections | SMTP, the company calendar address, .ics sending, the email log | Activities raise create, update (SEQUENCE = `row_version`) and cancel events; area 20 decides the UID and sends |
| 21 Whole-app | The company calendar query, the notification feed, `row_version` on `company_settings` | Provides `activities.calendar_rows`; writes notifications (mentions, reminders, auto-lost warning, Resolve prompt, assignment) to area 21's feed |

---

## 7. Controls, settings and permissions

### 7.1 Settings and controls

| Setting | Default | Kind | Who changes it |
|---------|---------|------|----------------|
| `auto_lost_days` | 14 (owner; 0 = off) | automation setting (F5) | `crm.settings`, reason, logged |
| `auto_lost_warn_days` | 3 | setting | `crm.settings` |
| `case_auto_close_days` | 7 (owner; 0 = off) | automation setting (F5) | `crm.settings`, reason, logged |
| `service_job_type_id` | the shipped Service type | default | `crm.settings` |
| `stage_requirements_block`, `stage_backdate_days` | area 8's (0, NULL) | controls, reused for leads | area 8 |

No new control that refuses anything is added; everything that could block (gates) uses area 8's existing control,
OFF by default. Integrity rules here, always on: history tables append-only (triggers); a closed case is final;
Lost is final except a correction; automation never posts, approves or moves money; comments are never printed.

### 7.2 Row limits (rule e: in services, never pages)

Q18 (owner's choice, area 18's scope mechanism): `role_level` and `access_template` gain `lead_scope` TEXT NOT NULL
CHECK IN ('All', 'Own') DEFAULT 'All', beside `project_scope`. A user with `lead.view` at scope All sees every lead;
at scope Own they see leads where they are the sales rep, Unassigned leads, and leads they take part in (they own or
attend one of its activities). It resolves like MR3: `lead.view` is limited to Own only when every source that grants
it (level row or template) has `lead_scope = 'Own'`. There is no `lead.view_all` code. Every seeded row keeps the
default All; a company sets Own per level or template. Activities follow their linked record's visibility, plus
the user's own activities. Cases: `case.view` sees all cases (cases are customer service, not sales territory);
job-linked cases also need project scope (MR3) for job details. Report sources apply the same limits (reports
contract 5.4). In Solo nothing is hidden.

### 7.3 Permission codes (Q19 A with Q18: ten codes; placed by the amendment line in area 18 section 2.4, 2026-11-19)

| Code | Meaning | Sensitive | Cap (area 18 2.4.1) | Level default |
|------|---------|-----------|---------------------|---------------|
| `lead.view` | Read leads, limited by `lead_scope` (section 7.2) | no | Sales rep, Operations, Accountant | Sales rep · View only |
| `lead.create` | Create leads (also import) | no | Sales rep | Sales rep · Standard |
| `lead.edit` | Edit, move stages, mark Lost, recreate, log activities on leads you can see | no | Sales rep | Sales rep · Standard |
| `lead.own` | Can be a lead's sales rep (R25 picker) | no | Sales rep | Sales rep · Standard |
| `lead.assign` | Reassign any lead's sales rep; edit lead assignment rules | no | Sales rep | Sales rep · Manager |
| `activity.log_for_others` | Create or reassign an activity for another user | no | Sales rep, Operations | Sales rep · Manager, Operations · Manager |
| `crm.settings` | Activity types, lead sources, case types, auto-lost and auto-close days, the service job type | no | Sales rep | Sales rep · Manager |
| `case.view` | Read cases | no | all three | each role's View only |
| `case.create` | Log a case | no | all three | each role's Standard |
| `case.work` | Be a case owner; change status; create a service job (with `project.create`) | no | Operations, Accountant, Sales rep | Operations · Standard, Accountant · Standard |

`project.create` keeps its code with the description "Create jobs". Admin and the Master get every code. Operations
and Accountant see leads only through a template or `lead.view` (their caps allow it, their levels do not give it).
Activities on jobs and cases need the record's own write code (`project.manage` or `case.work`) or `lead.edit`.

**`AGENT_ALLOWED`** (Q19 A with Q18): add `lead.view` and `case.view` only, following the list's own rule
("every *.view code that is not sensitive", `permissions.py:115`); no write code. Agent-origin activities or cases are
not possible.

**Reasons required** (area 18's table gains these rows, amendment 2026-11-19 in its section 1.2): a Back lead move (Moving a lead
back), Lost (Lost lead), continuing past a gate warning (Continue anyway), a lead stage correction, blocking a lead,
Reopen a case, Resolve (the resolution note), cancel an appointment (`activity.cancel_reason`), remove a comment
(`comment.removed_reason`), and changing any section 7.1 setting.

**Reasons list (Q16 A):** one `reason_option(reason_id PK, kind TEXT NOT NULL CHECK IN ('Lost lead', 'Moving a lead
back', 'Continue anyway', 'Send back', 'Change order', 'Write-off', 'Job cancel', 'Delay'), name TEXT NOT NULL,
is_shipped, is_active, sort_order, is_other INTEGER NOT NULL DEFAULT 0, billable_to_customer INTEGER (Change order
only), requires_note INTEGER NOT NULL DEFAULT 0, row_version)`, UNIQUE (`kind`, `name`); "Other" rows need at least
10 characters of text (service). Shipped rows for the three CRM kinds, including "No signature in N days
(automatic)" (kind Lost lead, shipped, hidden from manual pickers). Area 8's `job_cancel_reason` and `delay_reason`
and the `change_order.reason` CHECK list fold in as kinds 'Job cancel', 'Delay' and 'Change order' (Q16 A, owner
11:20 PM; amendment lines in area 8 sections 2.3, 4.3 and 5.3), so those two tables are not built.

**Stored reasons (fix a, owner 11:20 PM):** every column that stores a `reason_id` has a `reason_label` TEXT beside
it, the reason's label at the time of use, written by the service in the same transaction (so renaming a reason
never rewrites history or reports). Every FK to `reason_option` is ON DELETE RESTRICT: a used reason cannot be
deleted, only hidden (`is_active = 0`). In this area: `lead.lost_reason_label`, `lead_stage_history.reason_label`
and `continue_reason_label`.

Amendment 2026-11-20 (owner, from area 6 Q13 B): `reason_option.kind` CHECK gains 'Rate change' (a T&M rate typed
on an estimate, `estimate_rate_line.change_reason_id`) and 'Contract wording' (a section wording override on one
deal, `estimate_section_choice.override_reason_id`), each with `reason_label` beside it. The 9:48 PM rule applies: a
note is needed only when Other is picked (at least 10 characters). Shipped rows: 'Rate change': "Agreed with the
customer", "Other"; 'Contract wording': "Requested by the customer", "Other" (Admins rename, add and hide as for
every kind) (docs/replan_2.9/area_6_estimates_contracts.md sections 6.3 and 7.3).
Corrected 2026-11-20 (owner 12:50 AM, area 6 Q13 B): a short note is required on every rate change and contract-wording change; Other needs at least 10 characters.

---

## 8. Row version (rule g4) and audit in this area

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `lead`, `lead_contact`, `lead_source`, `activity_type`, `activity`, `case_type`, `service_case`, `comment`, `lead_assignment_rule`, `user_away`, `reason_option` | yes | yes |
| `lead_stage_history`, `case_status_history`, `comment_mention` | insert-only | no |
| `activity_attendee`, `activity_contact`, `lead_assignment_member` | insert and delete | no (a delete names its key) |
| `lead_number_seq`, `case_number_seq` | insert-only sequences | no |
| `company_settings` (new columns) | yes | area 21 adds it to the row |

Corrected 2026-11-20 (consistency scan F5): `lead_number_seq` and `case_number_seq` are counters, advanced only by `sequences.py` inside their record's creation transaction; `lead_number_seq_no_delete` and `case_number_seq_no_delete` refuse row deletion, and neither table has a `row_version`.

Every new table gets audit triggers (area 18), including the history and link tables (insert only). None is derived
or a per-user display preference, so area 18's exempt list is unchanged. Integrity triggers in this area guard
insert-only rows only (`lead_stage_history`, `case_status_history`, `comment_mention`); stage rules, case
transitions, assignment and every workflow rule live in services (H4). Every write calls `authorize` before its write
transaction (rule 10); every date and time comes from the context (H2).

Corrected 2026-11-20 (consistency scan F5): `lead_number_seq_no_delete` and `case_number_seq_no_delete` also refuse DELETE; the sequence counters are advanced only by `sequences.py` inside their record-creation transactions, not by user-facing edits.

---

## 9. Conflicts with decisions (answers recorded 2026-11-19)

- **F1 Lead is a project from day one.** docs/design_decisions.md "CRM and project lifecycle" ("A lead is a project
  from day one ... no separate opportunity table"), docs/crm_pm_design.md section 2 and C31 ("lead and job are one
  record") against later approved work: area 8 Q21 A (a lead stage history twin), area 8's rule that a job's stage
  is a Delivery stage, the reports contract's `src_leads` with base `lead` and the "lead → job link" (section 12
  item 16), and the baseline's `project.project_number`, `contact_id`, `assigned_pm_id` NOT NULL. This draft makes
  `lead` its own table and keeps C31's single timeline on screen through `lead.project_id`. **Answered: Q1 A.**
- **F2 Lost leads reopen.** design_decisions says "Lost leads can be reopened"; S 11-18 12:20 PM says "The lost
  lead stays lost" and offers Recreate lead. **Answered: Q2 A.**
- **F3 Service case shape.** design_decisions and crm_pm_design.md 4.2 make a case a `project` of kind 'Service
  case' with warranty cost "charged to the case, never to the closed job"; S 11-18 2:14 AM and the 11-18 inbox
  message make it its own record that creates service jobs, with warranty costs reported against the original job's
  warranty line. This draft follows 11-18 (and area 8's approved `warranty_for_job_id`).
  **Answered: Q13 B, Q14 A.**
- **F4 Invites to attendees and contacts.** A 11-17 5:51 PM item 3 and the task text ("invited contacts") send
  invites to the customer and attendees; S 11-18 11:45 AM replaces that: only the company calendar address gets
  invites. This draft stores the contacts taking part and sends nothing to them. **Answered: Q9 A.**
- **F5 Defaults that act on records.** Section 0 asks that configurable behaviour be OFF or permissive by default;
  the owner set auto-lost to 14 days and case auto-close to 7 days, both on. They change no money and are not
  controls that refuse anything, but they do move records automatically. **Answered: Q15 A.**
- **F6 One Reasons list vs area 8's tables.** S 11-19 9:48 PM: every reason dropdown reads one Reasons page with a
  tab per kind. Area 8 (approved) defines `job_cancel_reason` and `delay_reason` as separate tables. Folding them in
  changes an approved area. **Settled: Q16 A (owner 11:20 PM).** One `reason_option` table with a kind per use;
  area 8's `job_cancel_reason`, `delay_reason` and the `change_order.reason` CHECK list fold in as kinds, by the
  dated amendment lines in area 8 sections 2.3, 4.3 and 5.3.
- **F7 Superseded CRM schema proposals.** C10 and C12 propose `pipeline`, `pipeline_stage`, `pipeline_draft`,
  `stage_requirement`, stored probability, `project.is_blocked`, `probability_override`, `payment_method`,
  `assignment_territory`, `saved_list_view`, `alert_setting` and a business-hours calendar. RP4, area 8 Q3 A (no
  draft set), area 13 (work week and holidays), area 17 (`saved_view`, list prefs) and the 11-17 assignment rule
  supersede most of them; the rest are design proposals (C9 "PROPOSED") and are not built (open item 3).
- **F8 Proposal fields and the next-step pointer.** C12.6 proposes `proposal_amount_cents`, `proposal_reviewed_on`,
  `proposal_expires_on` and `next_step_activity_id`; S 11-18 2:02 AM and S 11-17 5:55 PM replace them (no proposal
  fields; next activity derived). Not built.
- **F9 `case_job` and `project.source_case_id` say the same thing twice** when a job can only come from one case
  (A 11-18 names both). **Settled: Q13 B.** `case_job` is dropped; only `project.source_case_id` (FK, indexed)
  links a job to its case, and a case's jobs are read by it. The double link and its schema test are removed.
- **F10 C9 "Require the signed contract file before signing" is listed as a PROPOSED control OFF**, while A 11-14
  and A 11-15 item 2 make the signed copy required. Area 6's to settle; noted because the lead's Won depends on it.
- **F11 Case owner "user or team".** A 11-15 item 4 says owner (user or team); there is no team table, and R25
  pickers list users. **Answered: Q12 B** (always a user; open item 13, closed 2026-11-20, for a default that gives
  no user).
- **F12 Status updates.** C31 makes Status update an activity type with health fields; S 11-17 5:55 PM makes
  activity types company-defined and generic, with no health fields. **Answered: Q8 A.**
- **F13 Activities on jobs.** A 11-17 5:55 PM names links to lead, customer and case; C31 and C103 give the job page
  an Activity tab with the full button row. **Answered: Q7 A.**
- **F14 Field name for the sales rep.** The reports contract uses field id `lead.sales_rep`; this draft's column is
  `sales_rep_user_id`. Not a conflict (the owner allowed any column name; the field registry maps it).
- **F15 "Record owner" in mention notifications** (A 11-15 2:41 PM) is read as the sales rep (lead, estimate), PM
  (job) and case owner (case), after the 11-17 8:12 PM rename.
- **F16 Assignment rule modes.** C12.2 lists Manual, Round-robin, By job type, By ZIP, Creator, with territories;
  the 11-17 owner rule has round-robin, fixed user, unassigned per service type. This draft follows 11-17.
- **F17 Sales approvals on stage moves.** C13.5 proposes `deal_stage_move` approvals in Team; S 11-15 3:30 PM
  makes requirements warnings by default and RP9 keeps one approval mechanism. Not built here (open item 7).

---

## 10. Questions for the owner: answers recorded (2026-11-19)

The owner answered on 2026-11-19 at 11:40 PM: A to Q1-Q11, Q14-Q17 and Q19-Q23; B to Q12 and Q13; for Q18 the
owner's own choice, which replaces A and B; Q16 A and the two required fixes (section 7.3 "Stored reasons" and
section 6, the sales rep on the job) were given at 11:20 PM. Each question is shown as asked, with the answer under
it. The design in sections 0-8 follows the answers.

Q1. **Lead record (F1).** A (recommended): a separate `lead` table; signing creates the job and links it
(`lead.project_id`); the job page shows the lead's sales history. B: a lead is a `project` row from day one (the
older decision), which needs `project_number`, customer and PM made nullable until signing and one history table for
both.
**Answer: A.**

Q2. **Lost (F2).** A (recommended): Lost is final; a mistaken Lost is undone only by a correction row with a reason;
a later return is a win-back lead. B: Lost can be reopened by a Back move with a "Moving a lead back" reason.
**Answer: A.**

Q3. **Won.** A (recommended): Won only through signing (the Closed dialog's Won opens Sign contract), so every Won
lead has a job. B: Won can be marked by hand without a signed contract (no job, no customer).
**Answer: A.**

Q4. **Lead history beyond stages.** A (recommended): the lead's History tab reads `lead_stage_history` plus the
audit log's before/after rows for the lead (expected value from a sent revision, sales rep, contacts), like settings
history (area 18 Q16 A). B: a separate append-only `lead_change_history` table.
**Answer: A.**

Q5. **Expected value.** A (recommended): stored on the lead; the estimate send writes the value and the revision id
in its transaction; direct edits refused while a revision id is set. B: never stored after a send; every read looks
up the latest sent revision.
**Answer: A.**

Q6. **Lead contacts.** A (recommended): `lead_contact` (Primary, Second) on the lead, handed to area 5 at signing.
B: write them straight into area 5's contact-person table, linked to the lead.
**Answer: A.**

Q7. **Activities on jobs (F13).** A (recommended): `activity.project_id` too, so jobs log calls, notes and status
updates. B: lead, customer and case only; the job page shows only its lead's and cases' activities.
**Answer: A.**

Q8. **Status updates (F12).** A (recommended): health columns on `activity`, used only by a shipped, non-removable
"Status update" type the company can rename. B: no status updates in the CRM; area 7/8 decides them for jobs.
C: no health fields; status update is plain text.
**Answer: A.**

Q9. **Contacts on an appointment (F4).** A (recommended): stored and written into the event details; no invite to
any person, only the company calendar address (11-18 11:45 AM). B: also email each invited contact an .ics.
**Answer: A.**

Q10. **Crew busy check.** A (recommended): a crew on a schedule task is busy all day on each of the task's work days,
plus timed calendar items and appointments. B: only timed calendar items and appointments.
**Answer: A.**

Q11. **Reminders.** A (recommended): an optional `remind_minutes_before` per activity, delivered as decided
(desktop at next sign-in and while open; hosted on time). B: no per-activity reminder; only overdue lists and CRM
alerts.
**Answer: A.**

Q12. **Case owner (F11).** A (recommended): a user or a role queue (for example "Accountant" for billing questions),
exactly one. B: always a user; the type's default picks a user.
**Answer: B.** A case owner is always a user (`owner_user_id` NOT NULL); the case type's default picks a user; no
role queue (section 3.3). **Open item 13 answered (owner 2026-11-20, 12:05 AM):** `case_type.default_owner_user_id`
INTEGER NULL, empty in shipped types, set in CRM settings (`crm.settings`); creating a case fills the owner from it;
when it is empty or the user is inactive, the person logging the case picks the owner; the service refuses a case
with no owner. Open item 13 is closed.

Q13. **Case and job link (F9).** A (recommended): both, as the owner wrote: `case_job` lists a case's jobs and
`project.source_case_id` is the job's back link, written together and checked by a test. B: only
`project.source_case_id`; a case's jobs are found by it.
**Answer: B.** `case_job` is dropped; only `project.source_case_id` (FK, indexed); a case's jobs are read by it. F9's
double link and its test are removed.

Q14. **Service job's type.** A (recommended): the Create service job form picks a service type, defaulting to a
company setting seeded with a shipped "Service" type. B: always one fixed shipped "Service" type.
**Answer: A.**

Q15. **Automatic defaults (F5).** A (recommended): keep the owner's defaults, auto-lost 14 days and case auto-close
7 days, each 0 = off, changes logged with a reason. B: ship both at 0 (off) under section 0.
**Answer: A.** Case auto-close is measured from the latest Resolve and runs at the first scheduled check at or after
the configured elapsed time; zero disables auto-close. At the default, the day-seven-not-day-six test checks the
threshold behavior.

Amendment 2026-11-22 (shared_decisions 2026-11-22 2:25 AM "service case auto-close can be turned off", owner
confirmed): the Q15 answer text above is extended in place: default 7 days counted from the latest Resolve; 0 turns
auto-close off and those cases are closed by hand.

Q16. **Reasons list (F6).** A (recommended): one `reason_option` table with a kind per tab; an amendment line folds
area 8's `job_cancel_reason` and `delay_reason` in as kinds. B: one table for the new kinds only; area 8's two
tables stay. C: a table per kind.
**Answer: A** (owner 11:20 PM). One `reason_option` table with a kind per use; area 8's `job_cancel_reason`,
`delay_reason` and the `change_order.reason` CHECK list fold in as kinds (amendment lines in area 8). Every stored
`reason_id` has a `reason_label` beside it; a used reason is hidden, never deleted (FK RESTRICT).

Q17. **Editing comments.** A (recommended): the author edits (shown "Edited", old text in the audit log) and removes
with a reason (row kept, hidden). B: comments are append-only; a correction is a new comment.
**Answer: A.**

Q18. **Who sees which leads.** A (recommended): `lead.view` sees own, unassigned and leads one takes part in;
`lead.view_all` (Sales rep · Manager) sees all; companies widen it with a template. B: every holder of a lead code
sees all leads.
**Answer: the owner's choice, replacing A and B.** Lead visibility uses area 18's scope mechanism: `lead_scope` CHECK
('All', 'Own') DEFAULT 'All' on `role_level` and `access_template`. Own = leads where the user is the sales rep,
Unassigned leads, and leads the user takes part in. Resolved like MR3: Own only when every source granting
`lead.view` says Own. `lead.view_all` is dropped everywhere (section 7.2).

Q19. **Permission codes.** A (recommended): the eleven new codes of section 7.3, `project.create` renamed "Create
jobs", and the three view codes added to `AGENT_ALLOWED`. B: reuse `project.create`, `project.manage` and
`project.view` for leads and add only the case codes. C: as A, but no CRM code in `AGENT_ALLOWED` yet.
**Answer: A, with Q18.** Ten codes (`lead.view`, `lead.create`, `lead.edit`, `lead.own`, `lead.assign`,
`activity.log_for_others`, `crm.settings`, `case.view`, `case.create`, `case.work`); `project.create` described
"Create jobs"; `AGENT_ALLOWED` adds `lead.view` and `case.view` only (section 7.3).

Q20. **Numbers.** A (recommended): `L-0001` for leads and `CS-0001` for cases, from sequence tables, unique, gaps
allowed. B: other formats (say which).
**Answer: A.**

Q21. **Away users in round-robin.** A (recommended): a `user_away` table (dates and note) set by the user or an
Admin, read by round-robin and pickers. B: skip only inactive users now; away comes later.
**Answer: A.**

Q22. **Blocked leads (R33 "Mark blocked").** A (recommended): `lead.is_blocked` and a reason, each block and unblock
a history row, so blocked days are counted apart. B: not now.
**Answer: A.**

Q23. **Custom fields on leads and cases.** A (recommended): add `'Lead'` and `'Case'` to
`custom_field_def.record_type` now, refused by the service until the record services exist. B: `'Lead'` only.
**Answer: A.**

---

## 11. Open items (not decisions)

1. Area 21's notification feed: mentions, reminders, the auto-lost warning, the Resolve prompt and assignments write
   to it; its table, read state and Solo behaviour are area 21's. C13.3's "Since you were last here" and
   `app_user.last_seen_at` are for area 21 too.
2. Area 6: `estimate.lead_id`, a nullable `estimate.contact_id` before signing, the revision table and its sent
   date, contract total and valid-until, `mark_expired`, the sales rep on the estimate and contract, the signing
   service's calls into `leads.py`, and contract cancellation (C105) with the Cancellation case type.
3. Not built (design proposals): lead source category, monthly cost and partner (C12.5); competitors, payment
   method, `decision_makers_confirmed`, probability per stage and overrides (C9, C10, C12.2); pipeline snapshots;
   duplicate check on quick-add (C9 / CRM-02) remains pending Mark's confirmation; area 5's `find_duplicates` may
   serve it. Also open: consent, retention and data-subject requests (C9, hosted only); "Do not contact" (C9).
4. Area 5's contact-person table: `activity_contact.contact_id` and the signer as primary contact point at it when it
   exists.
5. Area 20: the .ics UID form per activity, SEQUENCE from `row_version`, the email log id, and the "Download .ics"
   reply when no mailbox is set.
6. Whether `stage_backdate_days` should apply to leads as written for jobs, or leads get their own value (assumed one
   value).
7. Area 14: sales approvals on stage moves (C13.5, `deal_stage_move`) and contract cancellation approval
   (A 11-15, OFF).
8. Area 16: per-service-type custom fields on leads, "shown from stage", board-card flag, the warnings at more than
   2 card fields or 20 active fields (C27).
9. CRM alerts (speed to lead, proposal follow-up, stale digest; C12.7): their settings and the business-hours
   arithmetic (area 13's work week; no business hours table exists). Create-activity runs use `alert_key`. Needs a
   short design pass before batch F.
10. Leads import (C12.9): an import type under the import-origin rule (one human review), using the assignment
    rule; not designed here.
11. Saved views on Activities and Leads use area 17's `saved_view`/list prefs; nothing new here.
12. The job page's single timeline (C31) is a read across `activity` (job, its lead, its cases) and the two stage
    histories; built in Phase 3 from the services above.
13. Closed (owner 2026-11-20, 12:05 AM): `case_type.default_owner_user_id` INTEGER NULL, empty in shipped types, set
    in CRM settings (`crm.settings`); creating a case fills the owner from it; when it is empty or the user is
    inactive, the person logging the case picks the owner; the service refuses a case with no owner (section 3.3;
    recorded under Q12 in section 10).

Amendment 2026-11-21 (to_planning 2026-11-21 "Area 15 CRM intake audit follow-up"): item 3's quick-add duplicate check
(CRM-02) stays pending Mark's confirmation; cover an email match with a different phone and the inverse phone match.
