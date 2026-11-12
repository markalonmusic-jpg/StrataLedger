# StrataLedger: CRM and Project Management Design

Status: design draft, 2026-11-10. NOT BUILT. Nothing here changes the live
schema until a migration is written, tested on copies and approved.
The live database and migrations/*.sql remain the source of truth for what
exists today. This document records design intent for later phases.

---

## 1. Direction

- An internal-use CRM and project tool for a company's own staff.
- Main jobs: update project status, manage costs, track project profit,
  capture the timing of each stage and the speed of throughput, and do CRM
  basics (notes, collaboration, tracking how fast leads convert).
- Desktop version: no subscription. Hosted version: planned, for recurring
  revenue. Same schema and service layer in both. One database per company
  in both.
- Not a Procore clone. No external collaborators (owners, subcontractors,
  architects) and no RFIs, submittals or drawings in the first versions.

---

## 2. Core idea: one record, one lifecycle

A lead is a project from day one. One `project` record moves through one
list of stages from first contact to closed. Signing the contract is a
milestone on that path, not a boundary between two record types.

Default stages (editable per company):

| Group     | Stages |
|-----------|--------|
| Sales     | New lead, Qualified, Estimating, Proposal sent, Negotiation |
| (signing) | Contract signed: milestone, runs the signing function (section 6) |
| Delivery  | Pre-construction, Mobilization, In progress, Punch list |
| Closeout  | Substantial completion, Final billing |
| Closed    | Closed (LOCKED, never reopens) |
| Lost      | Lost, Cancelled (off-ramps from any stage; reopenable) |

After Closed, repairs are NEW records: a service case (kind = 'Service
case') linked to the closed job through parent_project_id, moving through a
separate Customer Support pipeline:

| Group   | Stages |
|---------|--------|
| Support | New request, Triage, Scheduled, In progress, Resolved |
| Closed  | Closed (LOCKED) |

A closed job is never reopened. Warranty or repair costs go to the case,
never to the closed job.

SaaS onboarding can use its own pipeline on the same record. The ongoing
subscription stays in its own tables.

---

## 3. Status of decisions

CONFIRMED by the owner:
- Internal-use tool; desktop no-subscription plus a hosted version.
- Leads and projects are one record; stages continue past signing.
- Closed projects never reopen; repairs go to a Customer Support pipeline.
- A case relates to the job (job code) that caused the service.
- Customer codes are fully automatic (no manual edit).
- Customer code format: first 2 letters of the name + a database-generated
  sequence number, zero-padded to at least 4 digits (AC0001).
- Customer code is assigned in the Create New Customer wizard on save, or at
  contract signing for a prospect, whichever comes first.
- Job number = customer code + project code (AC0001-001).

PROPOSED, waiting for confirmation (do not build as final):
- Vendor codes: 'V' + 2 letters + sequence (VAC0001). The V prefix is not
  confirmed.
- Optional service_case fields root_cause and responsible_contact_id
  (vendor/subcontractor), for back-charges.
- A case may only link to a Closed job.
- Stages are strictly linear (no overlapping stages).
- Warranty length per contract, with a company default as fallback.
- Cases can pause (blocked time) without counting against resolve time.
- The Create New Customer wizard creates customers only; prospects come
  from the CRM.
- Two sales pipelines (construction and SaaS).
- Closing checklist (section 6).
- Phase placement (section 11).

---

## 4. Tables

Conventions as in docs/accounting_schema.txt: money is integer cents,
dates are ISO text, timestamps are UTC (section 7), user references are
plain integers holding the system_master user_id (no foreign key).

### 4.1 Changed tables

contact (new fields)
  customer_code            TEXT      unique (partial index, where not null)
  vendor_code              TEXT      unique (partial index, where not null)
  customer_since           DATE
  source_id                INTEGER   FK -> lead_source.source_id (opt)
  owner_user_id            INTEGER   (opt)

project (new fields; one record from lead to close)
  kind                     TEXT      [Job, Service case]
  parent_project_id        INTEGER   FK -> project.project_id (opt)
  pipeline_id              INTEGER   FK -> pipeline.pipeline_id
  stage_id                 INTEGER   FK -> pipeline_stage.stage_id
  stage_entered_at         DATETIME
  is_blocked               BOOL
  source_id                INTEGER   FK -> lead_source.source_id (opt)
  owner_user_id            INTEGER
  expected_value_cents     INTEGER   (opt)
  expected_close_date      DATE      (opt)
  lead_created_at          DATETIME
  contract_signed_at       DATETIME  (opt)
  closed_at                DATETIME  (opt)
  lost_reason_id           INTEGER   FK -> lost_reason.reason_id (opt)
  warranty_end_date        DATE      (opt; set at closing)
  job_site_street, job_site_city, job_site_state, job_site_zip   TEXT
  target_margin_pct        REAL
  project_code             TEXT      short part only (001, or 001-S01 for a
                                     case); unique within a customer;
                                     empty until signing
  project_number           TEXT      full number (AC0001-001); stored,
                                     unique, never changes; empty until
                                     signing

pipeline
  pipeline_id              INTEGER   PK
  name                     TEXT
  applies_to               TEXT      [Job, Service case]
  is_active                BOOL

pipeline_stage
  stage_id                 INTEGER   PK
  pipeline_id              INTEGER   FK -> pipeline.pipeline_id
  name                     TEXT
  sort_order               INTEGER
  stage_group              TEXT      [Sales, Delivery, Closeout, Support,
                                      Closed, Lost]
  probability              REAL      (sales stages)
  target_days              INTEGER   (benchmark for aging and throughput)
  allows_costs             BOOL      (false before signing and when Closed)
  is_terminal              BOOL
  is_locked                BOOL      (true for Closed; Lost is NOT locked)
  is_lost                  BOOL
  is_active                BOOL

contract (new field)
  warranty_months          INTEGER   (opt override)

company_settings (new field)
  default_warranty_months  INTEGER

estimate (changed)
  project_id               now always set (the project exists from the lead
                           stage); no opportunity link

project_budget (changed)
  stage_id                 INTEGER   FK -> pipeline_stage.stage_id (opt)
                           (replaces any phase link; one cost code belongs
                           to one stage per project)

### 4.2 New tables

customer_number      seq INTEGER PK AUTOINCREMENT, contact_id INTEGER UNIQUE
                     FK -> contact, assigned_at DATETIME
vendor_number        same shape (DECIDED 2026-11-11)

person               person_id PK, contact_id FK (opt), first_name,
                     last_name, job_title, role, email, phone, mobile,
                     is_primary, is_active, created_at
lead_source          source_id PK, name, is_active
lost_reason          reason_id PK, name, is_active

project_stage_history   APPEND-ONLY
  history_id PK, project_id FK, stage_id FK, entered_at DATETIME,
  exited_at DATETIME (null while current), is_blocked BOOL,
  blocked_reason TEXT, changed_by INTEGER, note TEXT
  (Blocking or unblocking closes the current row and opens a new one with
  the same stage.)

project_stage_plan
  plan_id PK, project_id FK, stage_id FK, planned_start DATE,
  planned_end DATE, UNIQUE(project_id, stage_id)

project_status_update
  update_id PK, project_id FK, update_date DATE, overall_health,
  schedule_health, cost_health [On track, At risk, Off track],
  percent_complete REAL, summary, issues, next_steps, created_by,
  created_at

project_assignment
  assignment_id PK, project_id FK, user_id INTEGER, role, start_date,
  end_date

cost_forecast        (estimate to complete by cost code)
  forecast_id PK, project_id FK, cost_code_id FK, as_of_date DATE,
  est_cost_to_complete_cents INTEGER, note, created_by

activity             (CRM timeline: notes, calls, emails, meetings, visits)
  activity_id PK, type, subject, body, occurred_at DATETIME,
  duration_minutes, contact_id FK (opt), person_id FK (opt),
  project_id FK (opt), is_pinned, created_by, created_at
  (at least one link required)

task
  task_id PK, title, description, assigned_to INTEGER, created_by,
  due_date, status, priority, completed_at DATETIME, contact_id FK (opt),
  project_id FK (opt), created_at

comment              (threaded, on any record)
  comment_id PK, record_type, record_id, parent_comment_id FK (opt), body,
  created_by, created_at, edited_at

attachment           (files on any record; also used by the AI plan)
  attachment_id PK, record_type, record_id, file_name, file_path,
  sha256, size_bytes, uploaded_by, uploaded_at

notification
  notification_id PK, user_id INTEGER, event_type, record_type, record_id,
  message, created_at, read_at

service_case         (1:1 detail for projects where kind = 'Service case')
  project_id PK/FK -> project, category_id FK -> case_category,
  case_type [Warranty, Billable, Goodwill], priority, warranty_covered BOOL,
  reported_at DATETIME, reported_by_person_id FK -> person,
  issue_description, resolution_summary, resolved_at DATETIME
  PROPOSED optional: root_cause TEXT, responsible_contact_id FK -> contact

case_category        category_id PK, name, is_active

### 4.3 Designs that were considered and SUPERSEDED (do not create)

opportunity, opportunity_stage_history, project_phase,
project_phase_history. Their purpose is covered by the single project
record, project_stage_history and project_stage_plan.

---

## 5. Codes and numbers

Customer code
- Automatic only. First 2 letters of the name (uppercase, accents removed,
  skip a leading The/A/An, ignore digits and punctuation, pad with X) +
  seq from customer_number, zero-padded to at least 4 digits (AC0001).
- The number comes from the database: insert a row into customer_number in
  the same transaction that sets the code, and use seq. Never MAX+1.
  Keep a unique index on customer_code as a second safeguard.
- Assigned once, when a contact first becomes a customer (wizard save, or
  contract signing). Same service function for both routes. The UI never
  builds codes.
- Never changed, never reused. A coded customer can only be made inactive.
  A merged customer's code stays reserved.
- A contact with is_customer = 1 must have a customer_code (CHECK, added
  after the backfill).
- Duplicate check (name, tax_id, email) before creating a customer.
- The number may grow past 4 digits. Sort by seq, not by the code text.

Vendor code (DECIDED 2026-11-11)
- 'V' + 2-letter prefix (same rules) + seq from vendor_number, 4+ digits
  (VAC0001). Customer codes are exactly 2 letters then digits, so the
  formats cannot collide.
- Assigned once, when a contact first becomes a vendor. Imports (Ramp etc.)
  never create vendors directly: the staging approval step matches existing
  vendors and creates a new one only on approval.
- A contact can hold both a customer_code and a vendor_code.

Job and case numbers
- project_number = customer_code + '-' + project_code (AC0001-001).
- A job's project_code is the next 3-digit number for that customer, taken
  at signing inside the transaction, with UNIQUE(contact_id, project_code)
  as the backstop. It grows past 3 digits if needed.
- A case's project_code = parent job's project_code + '-S' + a 2-digit
  sequence per parent (AC0001-001-S01). A case with no parent job:
  'S' + sequence per customer (AC0001-S01).
- Leads have no number until signing; they are identified by name.
- Stored, immutable, so merges and renames never change numbers that appear
  on invoices, ledger entries and imports.

---

## 6. Signing and closing

sign_contract (one service function, one transaction)
1. Confirm the customer: choose an existing contact or create one (duplicate
   check). The contract's signing party is the customer, which may differ
   from the lead's company.
2. Assign the customer code if none (returning customers keep theirs); set
   is_customer and customer_since.
3. Set project.contact_id to the signing party; set contract_signed_at.
4. Assign project_code and project_number.
5. Create the contract and the original budget from the estimate; move the
   project to the first stage that allows costs.
6. Write an activity note and an audit entry.

close_project (PROPOSED checklist; confirm which items to require)
- Final progress billing issued.
- Retainage released or settled.
- Final percent-complete snapshot posted.
- No unapproved bills or open commitments.
Closing sets closed_at and warranty_end_date (contract.warranty_months, else
company default), then moves the project to the locked Closed stage.

create_service_case
- New project row, kind = 'Service case', customer and job site copied from
  the parent job, own pipeline (Customer Support).

---

## 7. Rules for these modules

1. No costs before signing: a ledger line tagged to a project requires the
   project's stage to have allows_costs = true.
2. Invoices (type Invoice) can only be issued to a contact that has a
   customer_code.
3. Locked (Closed) projects: no stage change, costs, invoices, change
   orders, budget or contract edits. Notes, comments and attachments are
   still allowed.
4. Lost is terminal but reopenable. Closed is not.
5. History tables are append-only. Every stage move or block change writes
   history in the same transaction, through one service function. A trigger
   safety net may be added per database.
6. All timestamps (_at fields) are UTC, ISO 8601 text
   (YYYY-MM-DDTHH:MM:SSZ). Calendar dates are plain dates.
7. comment, attachment and notification point at records by
   (record_type, record_id), checked in the service layer. Everything else
   uses real foreign keys.
8. A service case's customer must equal its parent job's customer.
9. Job cost, WIP and percent-complete reports include only jobs with
   contract_signed_at set. Service cases are reported separately.
10. Warranty and repair costs are charged to the service case, never to the
    closed job. A lifetime margin report combines them.
11. All writes go through service functions (CLAUDE.md rule 7).

---

## 8. Throughput and profit measures (views, not stored fields)

Pipeline and stage
- Time in each stage: average, median, slowest; blocked time separately.
- Stage-to-stage conversion, win rate, days from lead to signed, signed to
  closed.
- Aging: open items past their stage's target_days.
- Work in progress per stage (count and value); items completed per week or
  month.
- Sales velocity: open deals x win rate x average deal size / average cycle
  days.
- Planned vs actual days per stage (project_stage_plan vs history).

Profit
- Forecast margin = revised contract - cost to date - estimate to complete
  (sum of cost_forecast), compared with target_margin_pct.
- Budget vs actual by stage (budget lines carry stage_id).
- Lifetime margin per job = original margin - warranty cost from its cases.

Support
- Time to first response (New request to Triage), time to resolve (excluding
  paused time), backlog by stage, cases per job / category / customer,
  warranty cost per job, warranty periods about to expire.
- Customer profile view: code, name, customer since, jobs by stage, total
  contracted value, lifetime margin, open cases, last activity, next task.

---

## 9. Hosted version notes

- One database per company in hosted mode too. Same migrations and service
  layer.
- SQLite triggers are not portable. Keep business rules in the service layer;
  triggers are an optional per-database safety net.
- Sequences: customer_number and vendor_number map to identity columns in a
  hosted database.
- Desktop-to-hosted move = export and import of the same schema.
- UNDECIDED: whether desktop and hosted need to sync. If yes, add unique IDs
  to synced tables before building them.

---

## 10. Migration and backfill notes

- Existing customers and vendors: generate codes with the same rules, in
  order of creation, and list the prefix groups for review before applying.
- Existing projects: build project_number from existing project_code plus
  the customer code; report collisions and missing customers; do not guess.
- Existing projects need a pipeline and stage assigned; propose a mapping
  from the current status and let the owner approve it.
- All of this runs on copies first, with the migration runner's transaction,
  integrity check and backup rules (Phase 1).

---

## 11. Where it fits (PROPOSED)

- Phase 2 (service layer): customer_number table, customer_code field and
  the code-assignment service function.
- Phase 3 (screen alignment): the Create New Customer wizard shows the code
  (read-only; "assigned on save" for a new customer).
- After Phase 4 (posting), unscheduled order: A) pipeline, stages, history
  and the signing function; B) CRM basics and collaboration (person,
  activity, task, comment, attachment, notification); C) service cases and
  the Customer Support pipeline; D) throughput and profit views.
- AI coworker (Phase 6) uses attachment, activity and the same service
  functions.

---

## 12. Open questions

1. Vendor code format: V prefix (proposed) or plain two letters?
2. Optional service_case fields root_cause and responsible_contact_id?
3. Cases only on closed jobs?
4. Stages strictly linear, or can they overlap?
5. Warranty length: per contract with company default?
6. Can cases pause?
7. Should the New Customer wizard also be able to save a prospect?
8. Which closing checklist items are required?
9. Do desktop and hosted need to sync?
