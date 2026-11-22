# Step 2.9 schema replan, area 10: prepaid, deferrals, reclass, period balance summary

Status: **Owner-approved 2026-11-19** (first draft 2026-11-19, 3f79eb3; owner answers Q1-Q19 2026-11-19, all A, Q2 and
Q10 with the owner's detail, folded in below, 77938bc; `je.reclass` added to the Controller and Staff accountant
templates, a46501a; section 9). Docs only: nothing here changes code, a baseline, a migration or a test. Planning has
marked area 10 owner-approved in `Strata_Teams\schema_replan_2026-11-17.md`. Every table, column, code and check below
is built only in the 2.9 baseline pass. No questions are open. The amendments to areas 13 and 18 are dated lines in
those docs (section 10).

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`, row 10 and the source keys.
- `Strata_Teams\inbox\to_planning.md`: 2026-11-18 "prepaid bills, deferral schedules and auto-posting" (11:55 PM);
  2026-11-19 "reclass entries that keep the original line's details" (12:40 AM).
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md`: 2026-11-14 "Journal entries, owner decisions",
  "Clearing ID on journal lines"; 2026-11-16 "clearing from journal entries" (3:41 PM).
- `Strata_Teams\shared_decisions.md`: 2026-11-18 11:55 PM (prepaid bills); 2026-11-19 12:03 AM (period schedule
  grid), 12:40 AM (reclass), 12:45 AM (reclass, prepaid and money.view clarifications), 1:21 AM (prepaid void and job
  cost).
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 8 and 131 (the journal entry and clearing parts).
- docs/decisions_2026-11-11.md by code: C1-C5, L2, B1, B13, R41, R47, R48, R57, R60, RP2, RP8, A5; docs/design_decisions.md
  "Deferrals"; CLAUDE.md rule 8.
- docs/replan_2.9/area_13_close_and_locks.md sections 1.4, 2.3, 4 and 6 and its answers (section 9).
- docs/replan_2.9/area_12_bank_and_reconciliation.md section 6 (lock checks) and section 3.5 (permission style).
- docs/replan_2.9/area_18_admin_security_audit.md (permissions, reasons, exempt lists).
- docs/contracts/reports.md sections 4.4 ("As reclassed"), 4.6 and 12 items 12-13, and its Q1 and Q2 answers.
- `migrations/001_company.sql` (deferral, schedule, journal and bill tables); `modules/services/ledger.py`;
  `templates/coa/construction.csv` (numbers as examples only).

---

## 0. Summary

| # | Topic | Proposal in one line | Baseline |
|---|-------|----------------------|----------|
| 1 | Prepaid schedules | One deferral subledger (kept). `deferral` becomes the schedule of one bill line (Spread over N months or One date; Active / Finished / Stopped), `deferral_schedule_line` its entries (Scheduled / Posted / Caught up / Blocked / Replaced / Reversed). Entries post on their date while the app is open; closed-period amounts are caught up in the first open period; voiding the bill reverses everything in one transaction; job cost follows the GL | company |
| 2 | Reclass | `journal_entry.source` 'Reclass'; one line pair per original line; the original's ids and details in an insert-only `reclass_line`; refused on AR, AP, open-item, bank and card accounts; dated the original's date when open, else in the current open period; "As reclassed" from the reclass date on (contracts 4.4) | company |
| 3 | Deferral close checks | `deferral_entries_posted` reads the schedule lines due in the period; `deferral_tie_out` compares the subledger's open balance with the GL of the deferral accounts at period end; warn by default (L2) | company |
| 4 | Period balance summary | `ledger_period_balance` plus `dimension_set` / `dimension_set_member`, written only in `ledger._seal_and_post`; tie-out check and rebuild tool (area 13 section 6, Q21 A, Q22 A) | company |
| 5 | Lock checks | Every entry here calls `period_locks.check_open` with the Journal entries area (area 13 Q5 A); a bill's own posting and its void use Bills and vendor credits | company |
| 6 | Journal entries and Clearing ID | Built in 2.5 (reverse-only, R47, R57, R60); this area adds only the informational "Related to" link (Q18 A) | company |
| 7 | Permissions | `deferral.manage` at Accountant · Standard; `je.reclass` at Accountant · Manager (the level that holds `je.post`); neither in AGENT_ALLOWED (Q10 A; area 18 amended) | company |

Master file: no change.

---

## 1. Prepaid and deferral schedules

### 1.1 Current state

- **One subledger exists** (docs/design_decisions.md "Deferrals": one subledger, `kind` Expense or Revenue,
  `advance_type` Billed in advance or Paid in advance; a schedule line per period, the last absorbs rounding; the
  subledger ties to the GL; sales tax never deferred; POC and completed-contract invoice lines never deferred).
- `deferral` (`migrations/001_company.sql:900-927`): `kind`, `advance_type`, `contact_id`, `invoice_id`,
  `invoice_line_id`, `payment_id`, `original_amount_cents`, `start_date`, `end_date`, `method` ('Straight-line',
  'Manual'), `proration` ('Full month', 'Half month', 'Daily'), `deferral_account_id`, `recognition_account_id`,
  `project_id` and `cost_code_id` **with no foreign keys**, `supersedes_id`, `status` ('Draft', 'Active', 'Fully
  amortized', 'Cancelled'), `cancelled_date`, `memo`. No dimensions, no stop reason, no link to the entry that moved
  the cost to prepaid, no `row_version`, no created by/at.
- `deferral_schedule_line` (`:685-695`): `deferral_id`, `period_id`, `amort_date`, `amount_cents`, `status`
  ('Scheduled', 'Posted', 'Skipped'), `entry_id` UNIQUE; UNIQUE (`deferral_id`, `period_id`). One entry belongs to
  one source document (`*_one_document_per_entry_*` triggers, `:1996-2061`).
- Elsewhere: `journal_line.deferral_id` (`:498`); `account.is_deferral_account` (`:577`) and control type
  'Deferral' (`:581`); `payment_allocation.deferral_id` (`:320`, one target per allocation `:336-337`);
  `journal_entry.source` has 'Deferral' (`:451`); roles `prepaid_expenses_acct_id` (`:775`) and
  `unearned_revenue_acct_id` (`:779`) (construction examples 1400 and 2310, both control type Deferral).
- **No service** makes, schedules, posts or reverses a deferral (next_step.md "C4/L2 not built"). Area 18 lists
  both tables as "to audit" (no audit triggers today).
- **Bill lines have no job:** `invoice_line` (`:652-668`) has `account_id`, `cost_code_id` and dimensions
  (`invoice_line_dimension`) but no `project_id`; the job is on the header (`invoice.project_id`).
- No approval document type for deferrals (`approval_policy.document_type`, `:1106`).

### 1.2 Decided

- **Defer expense** on a bill line (S 11-18 11:55 PM; to_planning 11-18): prepaid account (default the prepaid
  role), start month, spread evenly over N months or recognize all on one later date; the dialog previews the
  schedule. The line's cost goes to the prepaid account; each entry moves its amount from prepaid to the line's
  expense account keeping the line's job and dimensions. Amounts sum exactly to the line (rounding on the last).
- Entries auto-post on their dates (period end) as system journal entries linked to the bill and the schedule;
  upcoming entries show on the Close checklist; nothing posts into a closed period.
- Change schedule rewrites upcoming entries only; Recognize the rest now posts the remainder today; Stop leaves the
  remainder in prepaid; all logged.
- On a **posted** bill, Defer posts a separate entry moving the cost to prepaid, dated in an open period; the bill's
  posted entry never changes. Amounts whose dates fall in a closed period are caught up in the first open period
  and marked "caught up". Nothing is dated into a closed period (S 11-19 12:45 AM).
- **Void** (S 11-19 1:21 AM): voiding a bill with a deferred line reverses, in one transaction, its posted recognition
  entries and its prepaid entry (dated by the void rules, never into a closed period); the schedule becomes
  Stopped. **Job cost** shows a deferred line's cost as recognized, following the GL entries that carry the job.
- **Schedule grid** (S 11-19 12:03 AM): Prepaid schedules get a List | Schedule view: one row per schedule, Cost, To
  date, Remaining, one column per month; posted months solid, upcoming lighter; each month's total equals that
  month's expense in the GL; each cell links to its entry.
- C4 as amended by L2 and S 12:45 AM: the deferral close check ships with the prepaid schedule service.
- Contracts Q2 A: schedules run while the app is open with the owner signed in to that company; missed runs catch
  up once at the next sign-in.
- C1 (early cancellation: recognize the remainder now, or reclass to a refund receivable or payable); C2 (billed-in-
  advance subscription lines create revenue deferrals); C5 (full-month proration by default, 15th cut-off; daily per
  deferral).

### 1.3 Proposed schema

**`deferral`** (kept as the one subledger; one row is one schedule):

| Column | Change |
|--------|--------|
| `kind`, `advance_type` | kept; v1 builds Expense / Billed in advance from a bill line (Q1 A) |
| `invoice_id`, `invoice_line_id` | NOT NULL for a bill-line schedule (CHECK by kind and advance type); partial unique index (`invoice_line_id`) WHERE `status` IN ('Active', 'Finished') (one live schedule per line) |
| `method` | CHECK IN ('Spread', 'One date') (the 11-18 dialog; replaces Straight-line / Manual, Q4 A) |
| `months` | INTEGER, CHECK (`method` = 'Spread') = (`months` BETWEEN 1 AND 120) |
| `start_date` | the first day of the start month; `end_date` the last entry's date |
| `proration` | dropped (Q4 A) |
| `original_amount_cents` | the deferred line amount, CHECK > 0 and integer |
| `deferral_account_id` | NOT NULL (the prepaid account; must have `is_deferral_account = 1`, service check) |
| `recognition_account_id` | NOT NULL (the line's expense account) |
| `project_id`, `cost_code_id` | gain foreign keys to `project` and `cost_code` |
| `prepaid_entry_id` | INTEGER UNIQUE REFERENCES journal_entry (the separate entry on a posted bill; NULL when the bill's own posting sent the line to prepaid, Q2 A) |
| `status` | CHECK IN ('Active', 'Finished', 'Stopped') (replaces Draft / Fully amortized / Cancelled; F3) |
| `stopped_by`, `stopped_at`, `stop_reason` | set together when Stopped (by a person or by a void); reason 1-1000 characters |
| `created_by`, `created_at` | NOT NULL |
| `supersedes_id`, `cancelled_date`, `payment_id` | `supersedes_id` dropped (Change schedule keeps one row, section 1.5); `cancelled_date` dropped (Stopped columns); `payment_id` kept for Paid in advance (later) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 (g4) |

**`deferral_dimension`** (`deferral_id`, `dimension_type_id`, `dimension_value_id`; PK the first two; FK as
`journal_line_dimension`): copied from the bill line at Defer, copied verbatim onto every recognition line (JD1).

**`deferral_schedule_line`** (kept; columns changed):

| Column | Change |
|--------|--------|
| `scheduled_date` | renamed from `amort_date`: the planned date (a period end) |
| `posted_date` | TEXT, set when posted: the scheduled date, or the first open period's date for a catch-up |
| `period_id` | the period it posted in (NULL until posted); UNIQUE (`deferral_id`, `period_id`) is dropped, because a catch-up puts several planned months in one period |
| `amount_cents` | CHECK > 0 and integer |
| `status` | CHECK IN ('Scheduled', 'Posted', 'Caught up', 'Blocked', 'Replaced', 'Reversed') |
| `entry_id` | FK to journal_entry, set on posting and retained on reversal. Recognize the rest may share one entry across lines of the same schedule. |
| `reversal_entry_id` | FK to journal_entry, set on void. Lines sharing a recognition entry share its reversal. |
| `blocked_reason` | TEXT (the lock sentence, while Blocked) |
| `sequence` | INTEGER NOT NULL (1..N); UNIQUE (`deferral_id`, `sequence`) WHERE `status` <> 'Replaced' |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

- Amounts: the live lines (not Replaced) of a schedule sum to `original_amount_cents`; the last line takes the
  rounding (service rule, tested; H4).
- A Posted or Caught up line never changes except to Reversed (with `reversal_entry_id`), backed by a trigger
  (integrity: a posted schedule line is part of the ledger trail; H4 allows integrity backstops).
- The one-document-per-entry triggers stay; the prepaid entry is the schedule's own document (a deferral row), so
  `deferral.prepaid_entry_id` joins that trigger set.

Amendment 2026-11-21 (Area 10 audit, DEF-01): remove per-line uniqueness on both entry links. Enforce one owning
schedule per recognition entry and one reversal per original recognition entry. The one-document-per-entry
checks treat linked schedule lines as one document and still refuse reuse by another schedule or document.

**`journal_entry.source`**: 'Deferral' (kept) for recognition and catch-up; 'Deferral' also for the prepaid entry,
told apart by `deferral.prepaid_entry_id`.

### 1.4 How it posts

- **Defer on an unposted bill (Q2 A, owner's words):** an unposted bill has no GL impact, so marking a line Defer only
  sets up the schedule. When the bill posts, that line posts straight to the prepaid account: one entry, no expense
  first. The line's job and dimensions stay on the schedule (and reach the GL on each recognition), not on the
  prepaid line.
- **Defer on a posted bill:** a separate entry, Dr prepaid / Cr the line's expense account carrying the line's job,
  cost code and dimensions (so job cost drops by the deferred amount), dated the bill date when its period is open
  and not locked, else the first day of the current open period (Q3 A).
- **Each recognition:** Dr the expense account with the line's job, cost code and dimensions / Cr prepaid, dated the
  scheduled date, source Deferral, linked through `deferral_schedule_line.entry_id` and `journal_line.deferral_id`.
- **The runner** (`deferrals.post_due(context)`): called by the app on company open and on its timer while open
  (contracts Q2 A; H2: `today` from the context). It posts every Scheduled or Blocked line whose scheduled date is on
  or before `context.today`:
  - period open and not locked: Posted on its date;
  - period closed: Caught up, posted on the first day of the first open period (a catch-up may hold several
    months, one entry per schedule line) (Q5 A);
  - period open but locked for Journal entries or for the prepaid or expense account: Blocked with the lock
    sentence, retried on the next run; once that period closes it is caught up like any closed one (Q6 A).
  Origin System, posted through `ledger.py` with no approval (Q7 A; open question 7 in next_step.md).
- **Recognize the rest now:** posts the remaining Scheduled lines as one entry dated `context.today` (lines become
  Posted with that date and share its entry ID; the schedule becomes Finished). The entry amount is the sum
  of the linked lines. Save the entry and the line updates in one transaction.
- **Stop:** no entry; Scheduled lines become Replaced; the remainder stays in prepaid; reason required (Q19 A: a
  refund is a vendor credit through its own service).
- **Void the bill (1:21 AM):** one transaction: void the bill's entry (void rules), void every Posted or Caught up
  recognition entry once by distinct entry ID, and void the prepaid entry (`ledger.void_document_entry`, R41:
  never before the original; an open period; R48: refused, never moved). Mark all lines linked to each reversed
  recognition entry Reversed together with the same reversal ID, the Scheduled ones Replaced, and the schedule Stopped
  with the void's reason. Any refusal refuses the whole void.
- **Rule 8 edit of a posted bill** with an Active schedule: refused with one sentence until the schedule is Stopped
  or Finished (Q9 A).
- **Job cost** reads GL lines carrying a job, so a deferred line counts only as recognized (1:21 AM).

Planned DEF-01 test: Recognize the rest for several remaining lines and verify their shared posting carries
the sum of their amounts. Void the bill and verify one reversal for that shared posting, all linked lines
Reversed with the same reversal ID, and all changes rolled back if any required reversal is refused.

### 1.5 Change schedule

Rewrites only the Scheduled and Blocked lines: they become Replaced and new Scheduled lines are added after the last
posted one, summing to the remainder. The schedule row keeps its id (no `supersedes_id`). Logged with the old and
new plan (audit triggers).

### 1.6 Unearned revenue

The same tables hold revenue deferrals (`kind` Revenue, the unearned revenue role, an invoice line), as the design
decision says. Q1 A: the schema allows them now; the service builds only expense (prepaid) schedules in this pass;
revenue deferrals come with billed-in-advance invoicing (C2).

### 1.7 Lands, effects, tests

- Company baseline: the column changes, `deferral_dimension`, the schedule-line trigger, audit triggers for
  `deferral`, `deferral_schedule_line`, `deferral_dimension` (area 18 lists the first two as to audit). Every
  development database is blocked and rebuilt (CLAUDE.md 5.2; list them and ask first, rule 9).
- New module `deferrals.py`: `preview`, `defer_line`, `change_schedule`, `recognize_rest`, `stop`, `post_due`,
  `list_schedules`, `schedule_grid` (the 12:03 AM view; reads only), and `void_for_bill` called inside the bill
  service's void. `ledger.py` gains nothing but the summary hook (section 4).
- No existing service or test changes (none touch deferrals). `tests/test_schema_replan.py` tests that name the
  deferral tables, if any, follow the column renames.
- Tests to write later: a 3-month spread of $1,000.00 is 333.33, 333.33, 333.34; One date posts once; amounts always
  sum to the line; Defer on a posted bill leaves the bill's entry untouched; the runner posts on time, catches up a
  closed month into the first open period (one entry per line, marked Caught up), blocks in a locked month and
  retries, and posts nothing twice when run twice (idempotent); Recognize the rest posts the remainder today; Stop
  leaves the remainder in prepaid; voiding the bill reverses every posted entry and the prepaid entry in one
  transaction, never into a closed period, and a refused reversal leaves everything as it was; a rule 8 edit is
  refused while Active; job cost for a month equals the GL lines with that job; the grid's month totals equal the GL
  expense for those months; sales tax and POC lines cannot be deferred.

---

## 2. Reclass

### 2.1 Current state

`journal_entry.source` (`:451`) has no 'Reclass'. No reclass table or service. Posted lines are frozen
(`journal_line_lock_update_posted`, `:1817`), so the original document is never changed by construction (rule 8).

### 2.2 Decided

- S 11-19 12:40 AM and to_planning 11-19: a Reclassify tool over transaction lines; change account, job and/or
  dimensions; amounts, names and dates never change; same account type only unless an Admin allows it; a reason is
  required. Each reclass posts a journal entry (source Reclass) with one line pair per original line (Cr old, Dr
  new), never netted; each pair carries the original's vendor or customer, date, memo, item and job, the original
  document and line ids, and the reason. The original is never changed.
- Date: the original line's date when its period is open; otherwise the first day of the current open period;
  never into a closed period.
- Rules: job reclass updates job cost; 1099 and sales tax follow the original's name and tax code; reversing a
  reclass restores the earlier view; logged.
- S 11-19 12:45 AM: "As reclassed" applies from the reclass entry's date on, so closed figures and the close
  snapshot never change; reclass is refused on clearing accounts (AR, AP; RP2) and on bank and card accounts.
- Contracts 4.4 and Q1 A: amounts equal the GL in both views; "As reclassed" changes only detail rows; chains follow
  to the latest reclass in range; grouping uses the original's details.

### 2.3 Proposed schema

**`journal_entry.source`** gains 'Reclass'.

**`reclass_line`** (Q11 A; one row per reclass journal line, written in the posting transaction):

| Column | Type and constraint |
|--------|---------------------|
| `journal_line_id` | INTEGER PRIMARY KEY REFERENCES journal_line (the reclass line) |
| `pair_no` | INTEGER NOT NULL (pairs the Cr "out" and Dr "in" lines of one original line) |
| `side` | TEXT NOT NULL CHECK IN ('Out', 'In') |
| `original_journal_line_id` | INTEGER NOT NULL REFERENCES journal_line (the line being moved: the original, or the latest In line of an earlier reclass) |
| `root_journal_line_id` | INTEGER NOT NULL REFERENCES journal_line (the first original, for chains) |
| `source_doc_type`, `source_doc_id`, `source_doc_line_id` | the original document and line (invoice, bill, JE, payment; B13 style) |
| `original_contact_id` | INTEGER REFERENCES contact |
| `original_date` | TEXT NOT NULL |
| `original_memo` | TEXT |
| `original_item_ref` | TEXT (the item until area 9 adds an item table; then a FK) |
| `original_project_id` | INTEGER REFERENCES project |
| `original_tax_rate_id` | INTEGER REFERENCES tax_rate (1099 and sales tax follow the original) |
| `reason` | TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 1000) |

- UNIQUE (`journal_line_id`); UNIQUE (`original_journal_line_id`) WHERE `side` = 'Out' AND the reclass entry is not
  reversed (service rule): a line is moved once; a later reclass moves the latest In line.
- Insert-only: triggers refuse UPDATE and DELETE (integrity of the posted trail; H4 allows it).
- Index (`root_journal_line_id`) for "As reclassed" chains; (`source_doc_type`, `source_doc_id`) for the document's
  "Reclassed" tag.

**Control** (section 0 of CLAUDE.md): `company_settings.allow_cross_type_reclass` INTEGER NOT NULL DEFAULT 0, on
the Controls page, audited with a reason (Q15 A).

### 2.4 Service rules (`reclass.py`)

- Whole lines only (amounts never change). The From line must be posted, not void, not already moved (or the latest
  In line of a chain).
- Refused accounts, both sides (Q12 A): every account with `track_clearing_id = 1` (AR, AP and any other open-item
  account, RP2, R60), every account with a `bank_account` row (bank and card, area 12), and the deferral accounts
  (`is_deferral_account = 1`), which move only through schedules (Q17 A). One sentence names the account and what to
  use instead ("AR lines are corrected through the invoice or a credit memo.").
- Same account type unless `allow_cross_type_reclass` is on.
- Date: the original line's date when its period is open **and not locked**; when its period is closed, the first
  day of the current open period (Q14 A: the period holding `context.today`, if open; else the earliest open period
  after the original's); when its period is open but locked, refused with the lock sentence (Q13 A, R48).
- Each pair copies the original line's contact, job, cost code and dimensions onto the In line except what is being
  changed; the Out line mirrors the original exactly.
- Posting goes through `ledger.py` like a manual entry (approval rules for manual entries apply, Q16 A); permission
  `je.reclass` (Q10 A, section 7.1).
- Reversing a reclass entry is an ordinary reversal (`ledger.reverse_entry`); the restored view follows from the
  reversal, and the line may be reclassed again.

### 2.5 Lands, effects, tests

- Company baseline: the source value, `reclass_line` with its triggers and audit triggers, the control column, the
  permission row.
- `ledger.py`: `create_document_entry` and `_seal_and_post` take the reclass rows in the same transaction (the only
  writer, rule 7). The report service (area 17) reads `reclass_line` for "As reclassed".
- Tests to write later: one pair per line, never netted; amounts and names unchanged; refused on AR, AP, a tracked
  account, a bank account, a card account and the prepaid account, and across types unless the control is on (and
  the control change is audited); dated the original's date in an open period, in the current open period when the
  original's is closed, refused when the original's period is locked; a closed period's report and its close
  snapshot are unchanged after a reclass dated later; a chain of two reclasses shows once under the latest account;
  reversing the second restores the first; job cost moves with a job reclass; 1099 grouping follows the original's
  vendor; the Agent cannot reclass.

---

QA handoff, DEF-03 (2026-11-21): use the source-linked reclass flow. Verify one exact Out/In pair per posted
source line, with the amount unchanged, the Out line mirroring the source and the In line changing only
the selected coding. Exercise account eligibility on both sides. Under Q16, verify the manual-entry approval
rules hold posting until required approval is satisfied. Under Q13–Q14, verify an open but locked source
period refuses the reclass and a closed source period uses the first day of the approved open period in §2.4.
These checks are planned for implementation after the Phase 2.9 gate.

## 3. Deferral close checks (area 13 section 2.3)

Both ship with `deferrals.py` (C4 as amended by L2 and S 12:45 AM); warn by default; can block (L2).

- **`deferral_entries_posted`** (step Costs): for the period being closed, every `deferral_schedule_line` of an
  Active schedule whose `scheduled_date` is on or before the period end is Posted or Caught up (or Replaced). It
  fails listing Scheduled and Blocked lines (schedule, bill, amount, the lock sentence for Blocked). It also lists, as
  information, lines Caught up into this period from earlier months (S 11-18 11:55 PM: caught-up entries show).
- **`deferral_tie_out`** (step Reconciliations): at the period end, for each deferral account (`is_deferral_account
  = 1`; the prepaid and unearned revenue roles in the construction chart), the GL balance equals the subledger's
  open balance. Include deferred additions, recognition and reversals only when their effective posting dates
  are on or before that period end, regardless of the schedule's current status. Use the bill's prepaid posting
  for a deferral set up before bill posting, or the separate prepaid entry for a posted bill. Count a shared
  recognition or reversal once at its full posted amount. A difference names the account and the amount.
  Accounts are found by `is_deferral_account` and roles, never by number (area 13 F11).
- Both read only; neither posts. "Run due entries now" on the checklist calls `deferrals.post_due`.

Tests to write later: each check passes, fails and warns vs blocks; a manual JE to the prepaid account (allowed by
`allow_manual_control_je`) makes the tie-out fail; a caught-up line is listed as information only.

Amendment 2026-11-21 (Area 10 audit, DEF-02): start with $1,000 prepaid at January 31. In separate cases,
finish the schedule by recognizing the remainder in February or void the bill with February-effective
reversals. Rerun January and verify the subledger and GL still show $1,000. Verify February reflects its
own recognition or reversal events.

---

## 4. Period balance summary (with area 17; area 13 section 6)

### 4.1 Decided

Contracts section 12 item 12 and 4.6; area 13 section 6 with its answers: `ledger_period_balance` (`period_id`,
`account_id`, `entity_id`, `project_id`, `cost_code_id`, `dimension_set_id`, `debit_cents`, `credit_cents`,
`line_count`) written only by `ledger.py` in the posting transaction, increment-only; nullable keys with a unique
expression index on `COALESCE(key, 0)` (area 13 Q21 A); tie-out check `period_balance_tie_out` (warn, L2) and a
rebuild tool in `tools/` plus an audited service wrapper needing `ledger.verify` (Q22 A); on area 18's derived exempt
list (F13); the close snapshot reads `journal_line`, not the summary (area 13 Q18 A); `dimension_set` and
`dimension_set_member`; index `journal_entry (period_id, is_posted)`.

### 4.2 Proposed schema

- **`dimension_set`** (`dimension_set_id` INTEGER PRIMARY KEY, `fingerprint` TEXT NOT NULL UNIQUE: the sorted
  `type:value` pairs) and **`dimension_set_member`** (`dimension_set_id`, `dimension_type_id`,
  `dimension_value_id`; PK the first two). Insert-only (a set never changes); derived, so exempt from audit with the
  summary (an amendment to area 18, F13 of this doc).
- **`ledger_period_balance`** as above; `debit_cents`, `credit_cents` integer and >= 0; `line_count` > 0; CHECK
  typeof integer. Unique index on (`period_id`, `account_id`, `COALESCE(entity_id, 0)`, `COALESCE(project_id, 0)`,
  `COALESCE(cost_code_id, 0)`, `COALESCE(dimension_set_id, 0)`).
- Index `journal_entry (period_id, is_posted)`.

### 4.3 Writer

One hook in `ledger._seal_and_post` (`ledger.py:927`), the single path every post, void, reversal, auto-reversal,
document posting, deferral entry and reclass goes through (`:572`, `:905`, `:912`, `:1051`, `:1153`): after the
entry is sealed and marked posted, group its lines by key, look up or add the dimension set, and upsert
(`INSERT ... ON CONFLICT ... DO UPDATE`, H5) in the same transaction. A static test allows no other writer of the
three tables.

Amendment 2026-11-20 (owner 2:25 AM, from area 7 Q12 A): `dimension_set` and `dimension_set_member` get a second
writer, the operating plan service (area 7 section 6.3), for `operating_plan_line.dimension_set_id`, so reports join
plan and actuals on the same set. Both writers call one shared get-or-create function (look up the fingerprint;
insert the set and its members when absent) inside their own write transaction; sets stay insert-only.
`ledger_period_balance` keeps its single writer; the static test allows the plan service as the one other writer of
the two set tables.

### 4.4 Lands, effects, tests

- Company baseline: the three tables and indexes; no audit triggers (exempt). Area 17 reads them.
- `ledger.py` gains the hook; every existing posting test still passes, and a shared fixture checks the summary
  equals `journal_line` after each one.
- Tests to write later: as area 13 section 6.3, plus: a deferral entry, a catch-up and a reclass each update the
  summary; two lines with the same dimensions share one set; a void lands in the void's period.

---

## 5. Lock checks this area makes (area 13 section 1.4)

All through `period_locks.check_open` inside the write transaction. Accounts by role and flag, never by number.

| Action | Period checked | Area | Accounts checked |
|--------|----------------|------|------------------|
| Defer on an unposted bill (the bill's posting) | the bill's date | Bills and vendor credits | every line |
| Defer on a posted bill (prepaid entry) | its date (Q3 A) | Journal entries (area 13 Q5 A) | prepaid and expense |
| Recognition entry (runner) | its scheduled date; closed: caught up; locked: Blocked (Q5 A, Q6 A) | Journal entries | prepaid and expense |
| Catch-up entry | the first open period's date | Journal entries | prepaid and expense |
| Recognize the rest now | `context.today` | Journal entries | prepaid and expense |
| Change schedule, Stop | none (no GL) | — | — |
| Void a bill with a schedule | each reversal's date (void rules) | Bills and vendor credits for the bill; Journal entries for the prepaid and recognition reversals | every line of each reversal |
| Reclass | the reclass date (section 2.4) | Journal entries | both lines of each pair |
| Reverse a reclass | the reversal date | Journal entries | every line |
| Summary write | none (inside a post already checked) | — | — |

Refused means refused, never moved (R48), except the runner's documented catch-up of closed months (decided
12:45 AM). The area 13 static test covers `deferrals.py` and `reclass.py`.

---

## 6. Journal entries and Clearing ID (the rest of row 10)

- **Built in 2.5:** posted entries reverse-only, one Reverse with a date and a reason (`ledger.reverse_entry`,
  `void_entry`, `:1107-1117`); auto-reversal (L5, R47) mirroring clearing ids; `clearing_id` opened and joined at post
  (R57, R60), sealed in the chain (RP2, RP8). Partial clearing and the open-amount refusal are R57/R60 rules.
- **Added here:** the informational "Related to" link (11-16 item 5, C131): `journal_line_related` (`journal_line_id`,
  `related_type`, `related_id`, `added_by`, `added_at`; PK the first three), allowed on posted lines because it
  changes no balance, audited, removable with a reason (Q18 A).
- **Not decided, not built:** C8's recurring templates, renamed pages and exports are PROPOSED in the mockup notes;
  C3 decides one `recurring_template`; that belongs to the recurring work, not this pass.

### Planned JE-01–JE-05 UI and service integration retests

- **JE-01 — Draft, post and sealed entry:** Save, reload and edit the same balanced draft. Post it once, then verify
  the list and detail resolve to the same saved entry, service-assigned number, actual actors and sealed posting.
  A refused post leaves the draft available to edit. Tests: `test_je01_draft_save_reload_edit_and_post_once`,
  `test_je01_list_and_detail_show_same_saved_entry_and_actual_actors`,
  `test_je01_refused_post_keeps_editable_draft`.
- **JE-02 — Money and counterparty:** Reject `12abc` and amounts with more than two decimal places before conversion
  to cents. Verify a selected counterparty remains on the existing line-level `contact_id` through draft, post and
  reload, alongside the original memo. Tests: `test_je02_rejects_malformed_or_overprecision_amount_before_cents`,
  `test_je02_contact_id_and_original_memo_survive_draft_post_reload`.
- **JE-03 — Exact entry identity:** Open two known entries by exact identity, then try an unknown entry number. The
  unknown route shows a missing-record message and offers no actions. Tests:
  `test_je03_known_entries_open_by_exact_identity`, `test_je03_unknown_entry_number_has_no_record_or_actions`.
- **JE-04 — Posting gates and accrual reversal:** Cover required approval, the separate-approver setting,
  control-account rules and date-warning acknowledgement where applicable. Verify a successful accrual and its linked
  automatic reversal after reload. If the reversal period is closed or missing, both postings fail atomically and no
  entry number is assigned. Tests: `test_je04_required_approval_and_separate_approver_gate`,
  `test_je04_control_account_rules_and_date_warning_acknowledgement`,
  `test_je04_accrual_and_linked_reversal_survive_reload`,
  `test_je04_closed_or_missing_reversal_period_refuses_pair_without_entry_number`.
- **JE-05 — Reverse, Void and Correct:** From both list and detail, retest **Reverse → Void / Correct** through the
  existing ledger services. Verify the saved reason, links in both directions, distinct Void and Correct effects,
  and refusal of a second reversal. For an eligible standalone entry, **Correct** leaves the original posted, posts
  its linked correction reversal and opens the exact new editable draft. Verify that draft reopens after reload and
  has no ledger effect before posting. The existing Python correction service returns the reversal only; leave
  workflow draft creation and failure handling for implementation design. **Void** posts the linked reversal, marks
  the original void and creates no replacement draft. Cover a standalone Void dated into an eligible later period
  and an all-or-nothing accrual pair on its original dates. Apply Area 13's planned area and account lock checks to
  the dates on which the new lines post. Tests: `test_je05_reverse_void_correct_from_list_and_detail`,
  `test_je05_reversal_reason_and_bidirectional_links_persist`,
  `test_je05_void_and_correct_have_distinct_effects`, `test_je05_second_reversal_is_refused`,
  `test_je05_correct_from_list_opens_linked_editable_draft`,
  `test_je05_correct_from_detail_opens_linked_editable_draft`,
  `test_je05_correct_draft_reopens_after_reload_without_ledger_effect`,
  `test_je05_void_from_list_and_detail_creates_no_replacement_draft`,
  `test_je05_standalone_void_posts_in_eligible_later_period`,
  `test_je05_accrual_pair_void_is_all_or_nothing_on_original_dates`,
  `test_je05_new_lines_respect_area13_area_and_account_locks_on_posting_dates`.

These are planned UI and service integration checks; keep the existing queue and phase ordering unchanged.

Amendment 2026-11-22 (owner_decisions_2026-11-22 item 21; RECURJE-04 with the RECURJE-01/02 branches): Repeat
monthly creates drafts by default. Accountant, Admin or Master, holding the new sensitive code
`je.recurring_autopost` (Area 18 §8.2), can switch a template to auto-post with a reason, and the switch is logged.
Auto-post still obeys period locks, approvals and required fields; a blocked run stays a draft and raises an alert
(the Area 21 notification feed). Schema for the recurring work (§6 note above; not this pass's tables):
`recurring_template.posting_mode` CHECK IN ('Draft', 'Auto-post') DEFAULT 'Draft', with `posting_mode_reason`,
`posting_mode_changed_by` and `posting_mode_changed_at` set together; each run records its outcome ('Draft
created', 'Posted', 'Blocked'), `blocked_reason` and the linked entry. No Company control. Confirmed by the owner 2026-11-22 (12:47 PM follow-ups): this extends decision C3 (docs/decisions_2026-11-11.md, "Deferrals, subscriptions, recurring") says the template
"generates drafts"; drafts stay the default and auto-post is opt-in. Tests:
`test_recurring_journal_defaults_to_draft`, `test_recurring_autopost_requires_permission_and_reason`,
`test_recurring_autopost_blocked_by_lock_or_approval_stays_draft_and_alerts`.

---

## 7. Row version (rule g4) and audit

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `deferral` | status, plan | yes |
| `deferral_schedule_line` | Scheduled and Blocked lines | yes |
| `deferral_dimension` | written with the schedule | no |
| `reclass_line` | insert-only | no |
| `journal_line_related` | insert and remove | no |
| `dimension_set`, `dimension_set_member`, `ledger_period_balance` | derived | no |

- Audit triggers on `deferral`, `deferral_schedule_line`, `deferral_dimension`, `reclass_line`,
  `journal_line_related` (area 18 section 1). The three summary tables are exempt as derived.
- Reasons required: stop a schedule, change a schedule (Q8 A), reclass (on every pair), remove a Related to link, the
  cross-type control change. Area 18's reasons table lists them through its dated amendment (Q10 A, F13).
- Integrity backstops here guard only posted or insert-only data (posted schedule lines, `reclass_line`, the
  one-document-per-entry rule). Schedule states, amounts summing to the line, the runner's rules and the reclass
  account rules are service rules with tests (H4).


### 7.1 Permissions (Q10 A, with the owner's change)

| Code | Module | Sensitive | Used by |
|------|--------|-----------|---------|
| `deferral.manage` | Ledger | no | defer a line, change a schedule, recognize the rest, stop, run due entries (the runner needs a signed-in user who holds it, Q7 A) |
| `je.reclass` | Ledger | no | post a reclass entry; reversing one uses `je.reverse` as any entry |

Placement in area 18's seed tables (owner 2026-11-19; area 18 carries the dated amendment):
- **Caps (2.4.1):** both in the Accountant cap only (62 → 64 codes with area 12's three).
- **Level defaults (2.4.2):** Accountant · Standard adds `deferral.manage`. `je.reclass` goes at the level that holds
  `je.post`, which is **Accountant · Manager** (area 18 2.4.2: Manager adds `je.post`, `je.reverse`, ...). So in
  practice it is Manager; it is tied to `je.post`'s level, so if that level moves, `je.reclass` moves with it.
- **Templates (owner 2026-11-19: `je.reclass` follows `je.post` in the shipped templates too):** every shipped template
  that names `je.post` adds `je.reclass` in the same (non-sensitive) column. In area 18 section 2.4.3 those are
  **Controller** and **Staff accountant**, both for the Accountant role; no other shipped template names `je.post`.
  `deferral.manage` is added to no template.
- **AGENT_ALLOWED:** neither.
- **Area 18 section 2.4 placement check, re-run in words (2026-11-19):** every code is still placed (both new codes are
  in the Accountant cap; area 12's three and the rest are unchanged); Accountant · Standard and Manager's cumulative
  defaults stay inside the Accountant cap and hold no sensitive code (both new codes are not sensitive); View only
  still holds read codes only; every template still sits inside the union of its roles' caps (Controller and Staff
  accountant are Accountant templates and `je.reclass` is in the Accountant cap), and their non-sensitive column
  holds no sensitive code. No rule fails (re-run after the template change, 2026-11-19).

---

## 8. Conflicts with decisions (all resolved by the owner's answers, 2026-11-19)

- **F1 Blocked or caught up.** to_planning 11-18 item 3 (Blocked; reopen or move the date) vs S 11-19 12:45 AM (caught
  up in the first open period). **Resolved by Q5 A:** closed-period amounts are caught up automatically and marked
  Caught up; Blocked is kept only for an open but locked period (Q6 A).
- **F2 Proration.** C5 and the baseline's Full month / Half month / Daily vs the 11-18 dialog. **Resolved by Q4 A:**
  monthly entries at each period end (Spread or One date); `proration` dropped.
- **F3 Vocabulary.** Baseline method and status values vs the decided ones. **Resolved as drafted (no question):**
  Spread / One date and Active / Finished / Stopped.
- **F4 Paid in advance.** The design decision's payment-first flow vs the 11-18 bill flow. **Resolved by Q1 A:** bill
  flow now; `payment_id` and revenue kept for later.
- **F5 Early cancellation.** C1's refund-receivable option vs 11-18's Stop. **Resolved by Q19 A:** Stop leaves the
  remainder in prepaid; a refund is a vendor credit.
- **F6 "An Admin allows it".** **Resolved by Q15 A:** a control `allow_cross_type_reclass`, OFF by default, on the
  Controls page, changed with a reason.
- **F7 Which accounts refuse reclass.** **Resolved by Q12 A and Q17 A:** every `track_clearing_id` account, every
  bank and card account, and the deferral accounts.
- **F8 Bill line job.** **Resolved as drafted (no question):** area 3 or 5 adds a line job; until then the schedule
  takes the header's job (section 10).
- **F9 Prepaid is a controlled account.** **Resolved by Q17 A:** deferral accounts refuse reclass; system deferral
  entries are not manual.
- **F10 System posting.** **Resolved by Q7 A:** the runner posts while the app is open, origin System, under the
  signed-in user (who must hold `deferral.manage`), with no approval and no date warnings. This also answers open
  question 7 for deferral entries.
- **F11 Area 13's tie-out wording.** **Resolved (owner 2026-11-19):** area 13 section 2.3 carries a dated amendment
  line: `deferral_tie_out` finds the prepaid and unearned revenue accounts by flag and role, not by number.
- **F12 Contracts item 13.** **Resolved as drafted (no question):** `reclass_line` also stores the tax code and the
  root line; the contracts doc is unchanged.
- **F13 Area 18 amendments.** **Resolved by Q10 A and the owner's amendment (2026-11-19):** area 18 carries dated
  amendment lines for the two codes (section 7.1), the reasons (section 7) and `dimension_set` /
  `dimension_set_member` on the derived exempt list.

---

## 9. Questions for the owner: answers recorded (2026-11-19)

All nineteen answered A, one by one; Q2 and Q10 with the owner's detail. The options as asked are kept in 9.1.

| Q | Answer | Where it lands |
|---|--------|----------------|
| Q1 Revenue and paid in advance | schema keeps both; expense schedules from bill lines only now | 1.3, 1.6 |
| Q2 Unposted bill | **A, owner's words:** no GL impact until posting; Defer only sets up the schedule; at posting the line goes straight to prepaid (one entry, no expense first) | 1.4 |
| Q3 Prepaid entry date | bill date if open and not locked, else first day of the current open period | 1.4 |
| Q4 Proration | monthly only; `proration` dropped | 1.3 |
| Q5 Closed period | caught up automatically, marked Caught up | 1.4, 3 |
| Q6 Locked period | Blocked and retried; caught up once closed | 1.4, 5 |
| Q7 Runner | while the app is open, origin System, no approval, needs `deferral.manage` | 1.4 |
| Q8 Approval and reasons | no approval type; reasons for Change and Stop | 7 |
| Q9 Rule 8 edit | refused while a schedule is Active | 1.4 |
| Q10 Permissions | **A with the owner's change:** `deferral.manage` at Accountant · Standard; `je.reclass` at the level holding `je.post` (Accountant · Manager); neither in AGENT_ALLOWED | 7.1 |
| Q11 Reclass details | insert-only `reclass_line` | 2.3 |
| Q12 Refused accounts | tracked, bank, card and deferral accounts | 2.4 |
| Q13 Locked original period | refused with the lock sentence | 2.4 |
| Q14 Current open period | the period holding today if open, else the earliest open after the original | 2.4 |
| Q15 Cross-type | control, OFF by default | 2.3 |
| Q16 Reclass approval | manual-entry approval rules apply | 2.4 |
| Q17 Deferral accounts | refuse reclass | 2.4 |
| Q18 Related to | `journal_line_related` now | 6 |
| Q19 Early cancellation | Stop leaves the remainder; refund by vendor credit | 1.4 |

### 9.1 The questions as asked

**Q1. Revenue deferrals and Paid in advance in this pass.** (F4)
- A. The schema keeps both kinds and `payment_id`; the service builds expense schedules from bill lines only; revenue
  and paid-in-advance come with billed-in-advance invoicing (C2).
- B. Build revenue deferrals from invoice lines now too.
- C. Drop the revenue and payment columns; add them back later.

**Q2. Deferring a line on an unposted bill.**
- A. The bill's own posting sends the line to prepaid; no separate entry.
- B. Always post the bill normally, then a separate prepaid entry.

**Q3. Date of the prepaid entry on a posted bill.**
- A. The bill date when its period is open and not locked; else the first day of the current open period.
- B. Always `today`.

**Q4. Proration.** (F2)
- A. Monthly entries at each period end only (Spread over N months, or One date); `proration` dropped; C5's options
  come back with revenue deferrals if needed.
- B. Keep Full month / Half month / Daily for Spread.

**Q5. A scheduled amount whose period is closed.** (F1)
- A. Caught up automatically by the runner in the first open period, marked Caught up, listed on the checklist.
- B. Blocked until a person catches it up or reopens the period.

**Q6. A scheduled amount whose period is open but locked** (Journal entries area, or the prepaid or expense account).
- A. Blocked with the lock sentence and retried each run; caught up once the period closes.
- B. Treated as closed: caught up into the next open period at once.

**Q7. How the runner posts.** (F10)
- A. While the app is open (contracts Q2 A), origin System, under the signed-in user's context, through `ledger.py`
  with no approval and no date warnings; it needs the user to hold `deferral.manage` (or it waits).
- B. Only when a person clicks "Post due entries".

**Q8. Approval and reasons for Defer, Change and Recognize the rest.**
- A. No approval type; Change and Stop need a reason; Defer and Recognize the rest are logged without one.
- B. A new Approvers type "Prepaid schedules" (OFF by default).
- C. A reason on every action.

**Q9. Rule 8 edit of a posted bill with an Active schedule.**
- A. Refused until the schedule is Stopped or Finished, with one sentence.
- B. The repost carries the schedule and rewrites its upcoming lines.

**Q10. Permissions.** (F13)
- A. New `deferral.manage` (not sensitive: defer, change, recognize the rest, stop, run due entries) and `je.reclass`
  (not sensitive), both in the Accountant cap; Accountant · Standard adds `deferral.manage`, Accountant · Manager adds
  `je.reclass`; neither in AGENT_ALLOWED; area 18 amended.
- B. Reuse `bill.create` for deferrals and `je.create` + `je.post` for reclass.

**Q11. Where the reclass details live.**
- A. An insert-only `reclass_line` side table written in the posting transaction (the chain and `journal_line` stay as
  they are).
- B. Columns on `journal_line`, added to chain v1 (RP8 allows it before release).

**Q12. Accounts that refuse reclass.** (F7)
- A. Every account with `track_clearing_id = 1` (AR, AP and other open-item accounts), every bank and card account,
  and the deferral accounts (Q17).
- B. Only the AR and AP control accounts and bank and card accounts.

**Q13. Reclass of a line whose period is open but locked.**
- A. Refused with the lock sentence (R48); unlock first.
- B. Dated into the current open period, like a closed one.

**Q14. "The current open period".**
- A. The period holding `context.today` when open; else the earliest open period after the original's.
- B. Always the earliest open period.

**Q15. Cross-type reclass.** (F6)
- A. A control `allow_cross_type_reclass`, OFF by default, on the Controls page, changed with a reason.
- B. Allowed per reclass by an Admin with a reason, no setting.

**Q16. Approval of reclass entries.**
- A. The manual-entry approval rules apply (a reclass is a journal entry).
- B. Never needs approval.

**Q17. Reclass of deferral accounts.** (F9)
- A. Refused; prepaid and unearned revenue move only through schedules, so the tie-out holds.
- B. Allowed under `allow_manual_control_je`.

**Q18. "Related to" on journal lines** (C131).
- A. Add `journal_line_related` now (informational, audited, allowed on posted lines).
- B. Later, with the journal entry screen.

**Q19. Early cancellation.** (F5)
- A. Follow 11-18: Stop leaves the remainder in prepaid; Recognize the rest now is separate; a refund is a vendor
  credit through its own service.
- B. Add C1's "move the remainder to a refund receivable" action to Stop.

---

## 10. Open items (not decisions)

- Area 3 or 5: a job per bill line (F8); bill void service calls `deferrals.void_for_bill` in its transaction.
- Area 7 or 8: job cost reads GL lines carrying a job (deferred cost as recognized).
- Area 9: an item table for `reclass_line.original_item_ref`.
- Area 13: the two deferral checks' text points here; section 2.3 carries the dated by-role amendment (F11).
- Area 17: reads `ledger_period_balance`, `dimension_set` and `reclass_line` for "As reclassed".
- Area 18: the permission rows and placement, the reasons rows and the derived exempt rows are dated amendments
  there (Q10 A, F13), including `je.reclass` in the Controller and Staff accountant templates (owner 2026-11-19).
- Open question 7 (System origin in `post_journal_entry`) is decided by Q7 or in the posting work.
- Area 11 reuses the schedule grid for fixed assets.
