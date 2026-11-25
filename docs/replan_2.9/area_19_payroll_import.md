# Step 2.9 schema replan, area 19: Payroll import (Gusto, Rippling or a spreadsheet), job labor and month-end accrual

Status: **DRAFT 2026-11-25, awaiting owner approval.** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise**. PROPOSED items in the sources are not built as final.

Sources read (only these, searched by section, date or code):
- docs/next_step.md: "Area 19 (Payroll import; not yet drafted, planning only)" (the saved-batch, review, retry, control-total, source-link,
  T&M and download tests; "Source-file access and retention policy remain unresolved for Mark").
- `docs/decisions_2026-11-11.md`: E8 (payroll import through staging with hold and approve; `time_entry` allocates labor to jobs;
  auto-reversing month-end labor accrual), L8 (one-cent import rounding), E11 (`origin`); `docs/design_decisions.md` "Imports" (staging
  first, one human approval, `external_ref` unique per source, `import_mapping`, the open payroll-journal question).
- docs/roadmap.md "Open decisions" 1 and 2 (post the provider's own journal or reclass from a payroll clearing account; a period-end labor accrual).
- Approved areas, by section: 14 (kind 'Payroll import', additional gate, §5.1 and the digest rule), 5 and 6 (T&M uses only posted payroll
  hours at the contract's frozen rates; owner S 11-19 8:40 PM), 7 (job cost accounts 5010 and 5020, job statuses, "rule: code finds accounts by role"),
  13 (lock area 'Payroll', the payroll clearing reconciliation, the close), 12 (`import_batch` columns, `file_sha256`, F11 and BF1 for Ramp),
  18 (`payroll.view`, `payroll.import`, `import.run`, `time.approve`, the Payroll template Q20 A, reasons), 15 (lead pipeline stages), 17 (reports).
- Live mockups (read-only, StrataLedger_mockups): `payroll.html` (list, row details, states), `import-wizard.html` and `csv-import.html`
  (type "Batch payroll": fields, tips, sample rows, error wording, "done" text).
- `migrations/001_company.sql` (checked: `import_source` 'Gusto', 'Rippling', 'Ramp', 'Manual Upload'; `import_batch` and its `batch_type` 'Payroll run',
  'Labor Accrual', `batch_nature` Actual, Accrual, Reversal; `staged_transaction` and `staged_line`; `time_entry`; `import_mapping`;
  `company_settings.payroll_clearing_acct_id` and `rounding_variance_acct_id`; `contact.is_employee`; permission seeds `time.enter`, `time.approve`,
  `payroll.view`, `payroll.import`; `journal_entry.source` 'Payroll').

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | Shape | One saved **batch** per payroll run file. Rows wait in a staging table (never the ledger) until a person reviews the exact mapped rows; then **one balanced entry** posts and the job labor rows (`time_entry`) are written in the same transaction. |
| 2 | Posting model | The entry is built from the rows, as the file has gross wages and employer burden per employee and no journal: debit wages and burden (job lines carry job and cost code), credit **Payroll clearing**. Planning proposal; the provider's own journal is the other choice (Q1). |
| 3 | Review | **Always on:** one human review of the exact rows that will post. Any change after review voids the review and any approval. Area 14's 'Payroll import' row (OFF) adds an approver. |
| 4 | Duplicates | A file already imported is refused (hash); a row already imported is refused (`external_ref` per source); a retry with the same operation id returns the first result. |
| 5 | Reverse | A posted run is corrected only by a reversal (reversing entry and negative labor rows); refused when the period is locked or the hours are on an issued T&M invoice (Q5). |
| 6 | Accrual | Optional **Labor accrual** control (OFF): a month-end accrual entry with an automatic reversal on the first day of the next month; no labor rows, so it never reaches T&M billing. |
| 7 | T&M and reports | Only **posted** payroll hours, net of reversals, reach T&M billing (owner S 11-19). Wages and burden are hidden without `payroll.view`. |

---

## 1. Current state

- **Baseline:** `import_batch` (`source_id`, `batch_type`, `batch_nature`, `reverses_batch_id`, `file_name`, period dates, `total_cents`, `status` Imported, In review,
  Approved, Posted, Voided, `entry_id`); `staged_transaction` (`txn_type` has no pay line; `Labor Accrual Adjustment` exists) and `staged_line`; `time_entry` (employee `contact_id`, `project_id`,
  `cost_code_id`, `work_date`, `hours` REAL, `wage_cents`, `burden_cents`, `source_batch_id`; no source-row link, no reversal marker); `import_mapping` (kinds Category, Department, Job/Project,
  Employee, Vendor); `import_source` names. `company_settings.payroll_clearing_acct_id` exists; there is no wages, burden, overhead or accrued-payroll role.
- **Live mockups:** `payroll.html` lists runs (pay period, "Gusto · JE-000417, dated 10/31", employees, hours, wages and burden, status Posted) with the actions View, View the entry,
  Download source and Reverse, a filter All, Pending review, Posted, Reversed, and a closed-period message ("This payroll run is in September, which is closed. Ask an Admin to reopen it.").
  The import wizard type "Batch payroll" reads Pay date, Employee, Job number, Cost code, Hours, Gross wages, Employer burden, Pay period start and end; rows with no job are overhead; "62 pay lines added to a
  batch waiting for your review. Nothing is posted yet."; three error samples (an employee typo, "4o.0" is not a number, a lead without a signed contract cannot take costs).
- **Existing rules:** CLAUDE.md section 0 (import-origin batches always need one human review; second approver for imports is a control); Area 14 (Payroll import row, OFF, an additional gate, never removes
  the review); Areas 5 and 6 (T&M hours come only from posted payroll imports); Area 13 (Payroll is a lock area; payroll clearing is reconciled at close); L8 (1-cent rounding for imports).

---

## 2. Decided (owner) and carried forward

1. **Staging first, one human review, then post** (owner E8; CLAUDE.md section 0 "import-origin batches always need one human review"; design_decisions "Imports"). Always on.
2. **`time_entry` allocates labor to jobs; month-end labor accrual reverses itself** (owner E8).
3. **A re-import never creates duplicates** (design_decisions: `external_ref` unique per source; mockup text "importing the same pay run twice never creates duplicates").
4. **T&M billing uses only posted payroll import hours at the contract's frozen rates** (owner S 11-19 8:40 PM; Areas 5 and 6).
5. **L8:** an import may auto-balance a difference of exactly 1 cent to the rounding variance account; 2 cents or more is rejected. (This area never needs it: §4 rule 6.)
6. **Area 14:** 'Payroll import' is an additional approver gate, OFF by default; the mandatory review stays whether it is OFF or ON (Area 14 §5.1).
7. **Wages and burden are hidden from people without `payroll.view`** (mockup text; permission seed, sensitive).
8. **Nothing posts into a closed period; the posted entry is append-only and corrected by reversal** (integrity rules).
9. **The AI never posts, approves or imports** (rule 0; `AGENT_ALLOWED` has no payroll function).

---

## 3. Tables (planning proposals)

- **`import_batch` (payroll columns; shares Area 12's `file_sha256`, `storage_key`, `line_count`):** `control_gross_cents`, `control_burden_cents`, `control_hours` (what the file says the totals are, NULL when it has none),
  `operation_id` UNIQUE (retry), `entry_date`, `reviewed_by`, `reviewed_at`, `review_digest`, `reversed_by_batch_id`, `row_version`. `status` gains **'Reversed'**. `total_cents` stays the integer-cent total of wages plus burden.
- **`payroll_import_line` (new, staging; never part of the ledger):** `line_id`, `batch_id`, `source_row_number`, `source_row_hash`, `external_ref` (provider row id, else a hash of source, pay date, employee, job, cost code, hours, wages, burden and
  the occurrence number), `employee_text`, `contact_id`, `job_text`, `project_id`, `cost_code_text`, `cost_code_id`, `department_text`, `pay_date`, `period_start`, `period_end`, `hours`, `gross_cents`, `burden_cents`, `is_overhead`,
  `wage_acct_id`, `burden_acct_id`, `status` Valid, Error, `error_text`, `row_version`. `UNIQUE (source_id, external_ref)` is enforced across posted batches. Lines are editable only while the batch is Imported or In review.
- **`time_entry` (new columns):** `source_line_id` (the staging row, so the original file row stays linked), `reverses_time_entry_id`; **rows are never edited or deleted; a reversal inserts mirror rows with negative hours, wages and burden.** `hours` stays REAL
  (a quantity); the service compares totals in hundredths of an hour, never with float equality.
- **`import_mapping`:** `external_kind` gains **'Cost code'**; Employee maps to a contact (`is_employee` = 1), Job/Project to a job, Department to the wage and burden accounts.
- **Account roles (`company_settings`, found by role, never by number):** `labor_wages_acct_id` (chart 5010), `labor_burden_acct_id` (5020), `overhead_wages_acct_id`, `overhead_burden_acct_id`, `accrued_payroll_acct_id`; `payroll_clearing_acct_id` exists.
  A Department mapping may override the wage and burden roles for its lines.
- **Setting (control, OFF):** `payroll_accrual_enabled` (§7).
- **Not added:** timesheets, pay rates, tax tables, net pay or withholding detail, a payroll register, a provider API connector (a file or spreadsheet only in v1; a connector is a provider step).

---

## 4. Import and mapping rules (`payroll_import.py`)

1. **One call stores the file and the batch:** `import_file(context, source, file, operation_id)` stores the file through `storage.py` (H3), keeps `file_sha256`, parses into lines and returns the batch. The same hash for the same source is refused: "This file was already imported on <date> as batch <n>."
2. **Row checks (a row with an error blocks Post, never Import):** valid ISO or MM/DD/YYYY dates; hours a number greater than 0 (2 decimals); gross and burden money to the cent (burden may be blank = 0); never a float; Employee resolves to a contact with `is_employee` = 1; Job resolves to a job; Cost code resolves to a cost code of that job; a job with a status other than Mobilization, In Progress, Suspended or Completed (Closed Out) takes no cost; a **lead** takes no cost
   (mockup wording: "Garcia roof replacement is a lead (New lead stage) without a signed contract, so it cannot take costs yet."). Errors say what to do next in one sentence and offer "Did you mean ...".
3. **Mapping is remembered:** a fixed mapping (employee, job, cost code, department) is saved in `import_mapping` and applied to later files; a changed mapping re-resolves the unreviewed rows only.
4. **No job = overhead:** a row with no job number is overhead (mockup text): wage and burden go to the overhead roles, no project, no cost code. Hours of overhead rows are stored on `time_entry` with `project_id` NULL and never reach T&M.
5. **Rows already posted:** a row whose `external_ref` was posted for the same source in another batch is refused with the batch it came from; the rest of the file still imports.
6. **Control totals:** when the file has a total (rows or footer) it is read as a control; the service compares gross, burden and hours as integers (hours in hundredths). Posting needs equality; a difference of exactly 1 cent on a money total is shown as information (L8) and does not post a rounding line, since the entry is built from the rows.
7. **Period and lock check at import and again at post:** the entry date (the pay date, the date in the first column of the file; a file with several pay dates is refused: "One pay date per batch") must be in an open period; the Payroll lock area and the job's area locks are checked at Post, not only at Import.
8. **Agents and the UI never write rows;** all writes go through this service after `authorize`.

---

## 5. Review and posting

**Statuses:** Imported (file read) -> In review (a person opened the exact rows) -> Approved (reviewed; plus Area 14's approval when that row is ON) -> Posted. Voided discards an unposted batch; Reversed is a posted batch that was corrected.
The list's "Pending review" filter shows Imported, In review and Approved.

1. **Payroll and Approvals open the same saved batch id** (next_step): both pages read the batch and its rows by `batch_id`, never a copy.
2. **Review covers the exact mapped rows that will post** (always on): `mark_reviewed(batch_id, expected_digest)` stores `review_digest`, a hash over every line's `line_id`, mapped contact, job, cost code, accounts, hours, gross, burden and source row number. A change to any line, mapping or the batch after review voids the review (and any Area 14 approval) and blocks Post until the current rows are reviewed again.
3. **Post** (`post_batch(context, batch_id, operation_id)`, `payroll.import`, sensitive) runs `authorize` first, then one write transaction: recompute the digest, re-check periods, lock, jobs, mapping and control totals, call `ledger.py` for one entry (`source` 'Payroll', `origin` 'Import', dated the pay date), insert the `time_entry` rows with `source_line_id`, set `status` Posted and `entry_id`. A retry with the same `operation_id` returns the first result and creates no second entry or rows.
4. **When Area 14's 'Payroll import' row is ON,** the submit step follows the review and the entry posts on the final approval (Area 14 table); the reviewer and the approver may be different people (the separation-of-duties control, OFF, makes it required).
5. **One entry per batch,** each row two or more lines: wages and burden to their accounts (with project and cost code on job lines), the credit to payroll clearing for the batch total.
6. **Payroll clearing is cleared by the bank,** not by this area: the provider's bank debit is matched by Area 12 (bank feed or rule) to the clearing account, and Area 13's close reconciles it. This area posts no cash.

**Worked example (the wizard's four sample rows, run 10/16/2026 to 10/31/2026, pay date 10/31/2026; all amounts integer cents):**

| Employee | Job, cost code | Hours | Gross wages | Employer burden |
|----------|----------------|-------|-------------|-----------------|
| Marcus Webb | RI0001-002, 05-200 | 80.00 | 384000 ($3,840.00) | 69120 ($691.20) |
| Priya Natarajan | CA0002-001, 05-100 | 76.00 | 342000 ($3,420.00) | 61560 ($615.60) |
| Jordan Ellis | overhead | 80.00 | 296000 ($2,960.00) | 53280 ($532.80) |
| Dana Reyes | overhead | 80.00 | 415000 ($4,150.00) | 74700 ($747.00) |

Totals: hours 316.00; gross 1,437,000 ($14,370.00); burden 258,660 ($2,586.60); batch 1,695,660 ($16,956.60).

Entry dated 10/31/2026 (job lines carry project and cost code):

| Line | Debit | Credit |
|------|-------|--------|
| 5010 Direct field labor, RI0001-002, 05-200 | $3,840.00 | |
| 5020 Field payroll taxes and burden, RI0001-002, 05-200 | $691.20 | |
| 5010 Direct field labor, CA0002-001, 05-100 | $3,420.00 | |
| 5020 Field payroll taxes and burden, CA0002-001, 05-100 | $615.60 | |
| Overhead wages (Jordan Ellis, Dana Reyes: 2,960.00 + 4,150.00) | $7,110.00 | |
| Overhead payroll taxes and burden (532.80 + 747.00) | $1,279.80 | |
| Payroll clearing | | $16,956.60 |

Debits 384000 + 69120 + 342000 + 61560 + 711000 + 127980 = 1,695,660 = credits 1,695,660. Four `time_entry` rows: (Marcus: 80.00 h, 384000, 69120), (Priya: 76.00 h, 342000, 61560), and two overhead rows with no project.

**Edge cases and refusals (each with a test):**
- The file is imported again: "This file was already imported on 11/02/2026 as batch 417." Nothing is added.
- A re-exported file for the same run (new hash, same rows): every row is refused as already imported (rule 5); the batch has zero new lines.
- Marcus Webb's row is edited after review (hours 80.00 -> 82.00): the review is void; Post is blocked until the new digest is reviewed; the change is audited.
- The lock for the Payroll area covers 10/31/2026: Post is refused naming the area and date; nothing is written.
- Post is called again after the network drop with the same operation id: the original result returns; one entry, four rows.
- Hours "4o.0" in row 18: the row is an Error with "This is not a number: 4o.0"; the batch can be reviewed only after the row is fixed or the line removed (a removal is audited; the file stays).
- A pay line for a job that is Closed Out: Error; the same line for a Solar install job in its Installation delivery stage (status In Progress) is Valid.

---

## 6. Reversing, voiding and downloading the source

- **Void** (unposted batch): status Voided; lines and file are kept (the source file stays through `storage.py`); the audit log records who and why (Area 18 reasons apply only to controls, so none is required).
- **Reverse a posted run** (`payroll.import`, sensitive): creates a batch with `batch_nature` 'Reversal' and `reverses_batch_id`, posts the mirror entry through `ledger.py` dated the reversal date (today, which must be in an open period), inserts the negative `time_entry` rows (`reverses_time_entry_id`), sets the original `reversed_by_batch_id` and status Reversed. Refused when the period or area is locked (mockup wording), or when any of its hours are on an issued T&M invoice (Q5).
  **Example:** reversing run 10/16/2026 to 10/31/2026 (batch total 1,695,660) on 11/03/2026: Dr Payroll clearing 1,695,660 / Cr each of the six debit lines above; net `time_entry` hours for RI0001-002, 05-200 = 80.00 - 80.00 = 0.00.
- **Download source** returns the stored file for the selected batch to a user with `payroll.view` and writes an audit event with the user and batch (next_step). The retention rule is Q2.

---

## 7. Month-end labor accrual (optional control, OFF)

`payroll_accrual_enabled` = 0 by default (Company Settings > Controls, Admin or Master, audit-logged). When ON, a batch with `batch_type` 'Labor Accrual' and `batch_nature` 'Accrual' is built from the same file format (pay date = the accrual date, a month-end) for labor worked and not yet in a payroll run.

- **Posting:** one entry dated the accrual date: debit the same wage and burden accounts (job lines with project and cost code), credit **Accrued payroll**. The service creates, in the same transaction, a second batch with nature 'Reversal' dated the first day of the next month; if that date's period or the Payroll area is locked, the accrual is refused naming it.
- **No labor rows:** an accrual writes no `time_entry`, so accrued hours never reach T&M (owner S 11-19: posted payroll import hours only).
- **Review** applies exactly as in §5 (always on; Area 14's row is additional).
- **Example, accrual 11/30/2026 for 11/16 to 11/30 (paid 12/04):** Marcus Webb 384000 + 69120 on RI0001-002, 05-200; Priya Natarajan 342000 + 61560 on CA0002-001, 05-100.
  11/30: Dr 5010 RI0001-002 $3,840.00, Dr 5020 RI0001-002 $691.20, Dr 5010 CA0002-001 $3,420.00, Dr 5020 CA0002-001 $615.60 / Cr Accrued payroll $8,566.80 (856,680 = 384000 + 69120 + 342000 + 61560).
  12/01 reversal: Dr Accrued payroll $8,566.80 / Cr the same four lines $8,566.80. 12/04 payroll run for the same labor: Dr the four lines $8,566.80 / Cr Payroll clearing $8,566.80.
  **Job cost by month:** November +8,566.80 (accrual); December -8,566.80 (reversal) + 8,566.80 (run) = 0.00. The two-month total is 8,566.80: the real cost, counted once, in the month the work was done.

---

## 8. Reads, reports and the close

- **List (`payroll.html`):** columns Pay period, Source and entry, Employees, Hours, Wages and burden, Status; **Wages and burden are shown only with `payroll.view`**; others see hours and employees. Filters All, Pending review, Posted, Reversed (§5). Export CSV and Excel carry the same columns (Area 17 export rules).
- **Job cost:** job cost reports read the ledger lines (job and cost code); labor by employee for a job needs `payroll.view`.
- **T&M:** `posted_labor_hours(project_id, cost_code_id, from, to)` returns `time_entry` rows net of reversals with their source ids and quantities for Area 5; an accrual or an unposted batch is never returned.
- **Close (Area 13):** Payroll is a lock area; the payroll clearing reconciliation is the close subledger check; a batch in Imported, In review or Approved for the period is listed as an open item, never blocking (close-checklist blocks are an optional control).

---

## 9. Permissions, locks, row version and audit

- **Permissions (Area 18):** `import.run` uploads, maps, edits unreviewed rows and voids; `payroll.import` (sensitive) reviews, posts and reverses; `payroll.view` (sensitive) sees wages, burden and the source download; `time.approve` is not used by this area (it is for timesheets later). None is in `AGENT_ALLOWED`. The Payroll template (Area 18 Q20 A) holds `import.run`, `payroll.import`, `payroll.view`.
- **Separation of duties** (the existing Controls setting, OFF): when ON, the person who imported cannot review or post that batch.
- **Locks:** posting checks the Payroll area lock and the job areas; reversing checks the original entry's period and the reversal date's period.
- **Row version:** `import_batch` and `payroll_import_line` carry `row_version` (a stale edit is refused).
- **Audit:** every batch and line change is audited by the trigger pattern with the user; the batch's review, post, reversal and source download write audit events; the review digest is stored.

---

## 10. How it lands in the baselines and code

- **Baselines (2.9 pass, tests first):** `import_batch` columns and the 'Reversed' status; `payroll_import_line`; `time_entry` columns; the `import_mapping` kind; the five account roles and the control column (the dev databases are rebuilt).
- **Code:** `modules/services/payroll_import.py` (import, map, edit, review, post, reverse, void, download, accrual) and the shared import-batch rules it reuses; `ledger.py` stays the only journal writer; no UI or HTTP import (H1), no clock (H2: dates from the context), files through `storage.py` (H3), no SQLite-only SQL (H5).
- **Tests (named from next_step, plus these):** `test_payroll_and_approvals_open_exact_saved_batch`, `test_human_review_covers_exact_mapped_rows_that_post`, `test_payroll_post_requires_review_with_area14_approval_off`,
  `test_payroll_post_requires_review_and_area14_approval_when_configured`, `test_changed_payroll_batch_after_review_requires_new_review`, `test_payroll_retry_after_lost_confirmation_no_duplicate_rows_or_entries`,
  `test_payroll_import_rejects_invalid_dates_hours_amounts_and_unresolved_references`, `test_payroll_provider_control_totals_reconcile_to_mapped_rows`, `test_payroll_labor_rows_link_original_source_rows`,
  `test_payroll_job_cost_uses_mapped_job_and_cost_code`, `test_tm_billing_uses_only_posted_payroll_import_hours`, `test_payroll_download_returns_selected_batch_source_and_audits`,
  `test_same_file_hash_is_refused`, `test_reexported_run_adds_no_rows`, `test_payroll_entry_balances_and_credits_clearing_for_the_batch_total` (the 1,695,660 example),
  `test_overhead_rows_have_no_project_and_never_reach_tm`, `test_lead_job_cannot_take_payroll_cost`, `test_closed_out_job_takes_no_payroll_cost`, `test_multiple_pay_dates_in_one_file_are_refused`,
  `test_posting_into_a_locked_payroll_area_is_refused_and_writes_nothing`, `test_reverse_inserts_negative_time_entry_rows_and_net_hours_are_zero`, `test_reverse_refused_when_hours_are_on_an_issued_tm_invoice`,
  `test_wages_hidden_without_payroll_view`, `test_accrual_control_defaults_off`, `test_accrual_posts_and_reversal_is_created_with_it`, `test_accrual_refused_when_reversal_period_is_locked`,
  `test_accrual_writes_no_time_entry_and_never_reaches_tm`, `test_agent_cannot_import_review_post_or_reverse_payroll`, `test_payroll_import_static_has_no_ui_clock_or_sqlite_pragma`.

---

## 11. Integrity checks kept (always on)

Integer cents and balanced double entry on the one entry; the review before posting; no posting into a closed period; the posted entry append-only and corrected by reversal; the audit log; permissions enforced in the service; the agent never imports, approves or posts; the same file or row never posts twice.

---

## 12. Conflicts with decisions, the baseline or the mockups (flagged)

1. **design_decisions "Imports" prefers the provider's own journal as the cost source, hours only on `time_entry`; roadmap open decision 1.** The mockup file has gross wages and burden per employee, not a journal. Proposal: build the entry from rows (Q1).
2. **Staging tables:** design_decisions names `staged_transaction` and `staged_line`; the baseline's `txn_type` has no pay line and no hours or burden columns. Proposal: a dedicated `payroll_import_line`.
3. **Statuses:** the baseline has Imported, In review, Approved, Posted, Voided; the mockup filters Pending review, Posted, Reversed. Proposal: add 'Reversed'; "Pending review" groups three statuses.
4. **`time_entry` has no source-row link and no reversal marker;** it is immutable by proposal, so reversal inserts negative rows.
5. **No wages, burden, overhead or accrued-payroll account roles;** only `payroll_clearing_acct_id` exists (Area 7: code finds accounts by role).
6. **`import_mapping` kinds lack Cost code.**
7. **Entry date:** the mockup shows "dated 10/31" for a run ending 10/31; wages earned in one month and paid in the next fall in the pay-date month unless the accrual control is ON (planning proposal; Q3).
8. **Area 12 F11 and BF1:** Ramp card lines and the never-booked-twice rule are assigned to "area 19 or the provider step"; this area designs payroll only and the shared batch rules, and hands BF1 to the Ramp provider step (Q7).
9. **`time.approve` (Area 6 note: T&M hours "approved when the import posts")** is not used; posting is the approval of the hours (planning reading).
10. **Mockup wizard says "Wages and burden are hidden from people who do not have payroll access";** the list page shows them for all; the list must hide them (work order).
11. **Mockup "Close" button on a run row** is not a payroll action; assumed to close the row detail (work order).

---

## 13. Questions for the owner (recommended option first, with an example)

- **Q1. How is the payroll entry built?**
  (A) From the file's rows: wages and burden to expense, credit Payroll clearing (recommended: matches the mockup file and puts cost on the job and cost code).
  (B) Import the provider's own journal entry and use the rows only for hours and job allocation.
  Example: the 10/31/2026 run posts $16,956.60 to clearing under A; under B the entry would carry the provider's own lines (net pay, withholdings) and the job cost needs a separate reclass.
- **Q2. How long is the source file kept, and who may download it?**
  (A) Kept as long as the entry (never deleted); download needs `payroll.view` and is audited (recommended).
  (B) Kept until the period is closed, then removed.
  Example: gusto_payroll_10-16-2026.csv stays beside batch 417 for audit under A.
- **Q3. Is the month-end labor accrual built in v1 (control OFF)?**
  (A) Yes, as in §7 (recommended: owner E8 names it).
  (B) Later, with timesheets.
  Example: the 11/30/2026 accrual of $8,566.80 reverses on 12/01/2026.
- **Q4. When an employee in the file is not found?**
  (A) The row is an error and the Admin adds or maps the employee, then re-checks (recommended: no silent hires).
  (B) The service creates the employee from the file.
  Example: "Marcus Web" gets "Did you mean Marcus Webb?" under A.
- **Q5. Reversing a run whose hours are already on an issued T&M invoice?**
  (A) Refused naming the invoice; credit the invoice first (recommended).
  (B) Allowed; the invoice is flagged.
  Example: 80.00 hours of Marcus Webb on invoice INV-1042 block the reversal under A.
- **Q6. Job statuses that take payroll cost?**
  (A) Mobilization, In Progress, Suspended and Completed; Closed Out and leads take none (recommended).
  (B) Also Closed Out, with a warning.
  Example: "Garcia roof replacement" (lead at New lead) is refused under both.
- **Q7. Ramp and the other batch types (card, bills, reimbursements)?**
  (A) Area 19 designs the shared batch rules and payroll only; Ramp comes with its provider step in v1.1, with the BF1 test (recommended).
  (B) Design Ramp here now.
  Example: a Ramp $812.40 card charge and its bill never both post (BF1) in the provider step.

---

## 14. Open items (not decisions)

- Certified payroll (WH-347) and prevailing wage (Area 7 flag; v1.1).
- Timesheets, pay rates and a bill rate per employee (Area 6 Q26 A: none in v1).
- A provider API connector (Gusto, Rippling) instead of a file.
- Net pay, withholdings, payroll liabilities and a payroll register.
- Ramp lines and BF1 (Q7); bills, reimbursements and card batches.
- The job-charging posting for equipment by the hour (Area 11 open item) is not payroll.
