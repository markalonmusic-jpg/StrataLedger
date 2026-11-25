# Step 2.9 schema replan, area 19: Payroll import (Gusto, Rippling or a spreadsheet), job labor and month-end accrual

Status: **REVISED 2026-11-25 for the owner answers A19-Q1 to Q9, Q3b and Q7b (2:15 to 3:00 PM; section 15), awaiting owner approval; drafted in d1a406d.** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise** (text marked "Planning reading" is a planning proposal). PROPOSED items in the sources are not built as final.

Sources read (only these, searched by section, date or code):
- docs/next_step.md: "Area 19 (Payroll import; not yet drafted, planning only)" (the saved-batch, review, retry, control-total, source-link,
  T&M and download tests; "Source-file access and retention policy remain unresolved for Mark").
- `docs/decisions_2026-11-11.md`: E8 (payroll import through staging with hold and approve; `time_entry` allocates labor to jobs;
  auto-reversing month-end labor accrual), L8 (one-cent import rounding), E11 (`origin`); `docs/design_decisions.md` "Imports" (staging
  first, one human approval, `external_ref` unique per source, `import_mapping`, the open payroll-journal question).
- docs/roadmap.md "Open decisions" 1 and 2 (post the provider's own journal or reclass from a payroll clearing account; a period-end labor accrual).
- Approved areas, by section: 14 (kind 'Payroll import', additional gate, §5.1 and the digest rule), 5 and 6 (T&M uses only posted payroll
  hours at the contract's frozen rates; owner S 11-19 8:40 PM), 7 (job cost accounts 5010 and 5020, job statuses, "rule: code finds accounts by role"),
  13 (lock area 'Payroll', the payroll clearing reconciliation, the close), 12 (`import_batch` columns, `file_sha256`, F11 and BF1 for card charges),
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
| 2 | Posting model | The entry is built from the rows, as the file has gross wages and employer burden per employee and no journal: debit wages and burden (job lines carry job and cost code), credit **Payroll clearing**. **Owner A19-Q1:** from the rows, not the provider's own journal. Burden is split by who pays it (owner Q8): provider-paid burden credits Payroll clearing, separately billed burden credits Accrued burden. |
| 3 | Review | **Always on:** one human review of the exact rows that will post. Any change after review voids the review and any approval. Area 14's 'Payroll import' row (OFF) adds an approver. |
| 4 | Duplicates | A file already imported is refused (hash); a row already imported is refused (`external_ref` per source); a retry with the same operation id returns the first result. |
| 5 | Reverse | A posted run is corrected only by a reversal (reversing entry and negative labor rows); refused when the period is locked or the hours are on an issued T&M invoice (Q5). |
| 6 | Accrual | Optional **Labor accrual** control (OFF), built in v1 (owner Q3): a month-end entry that posts to the GL and to the job as a **separate accrual posting type**, never counted as job cost actuals; job reports show Actual, Accrued and Total and job profit with and without accruals; it never reaches T&M or a pay app. *Planning reading:* the same rule covers every job cost accrual (§7). |
| 7 | T&M and reports | Only **posted** payroll hours, net of reversals, reach T&M billing (owner S 11-19); a bonus with 0.00 hours adds no billable time (owner Q9). Wages and burden are hidden without `payroll.view`. |

---

## 1. Current state

- **Baseline:** `import_batch` (`source_id`, `batch_type`, `batch_nature`, `reverses_batch_id`, `file_name`, period dates, `total_cents`, `status` Imported, In review,
  Approved, Posted, Voided, `entry_id`); `staged_transaction` (`txn_type` has no pay line; `Labor Accrual Adjustment` exists) and `staged_line`; `time_entry` (employee `contact_id`, `project_id`,
  `cost_code_id`, `work_date`, `hours` REAL, `wage_cents`, `burden_cents`, `source_batch_id`; no source-row link, no reversal marker); `import_mapping` (kinds Category, Department, Job/Project,
  Employee, Vendor); `import_source` names. `company_settings.payroll_clearing_acct_id` exists; there is no wages, burden, overhead, accrued-payroll or accrued-burden role, and `journal_line` has no column that separates an accrual from an actual.
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
10. **A19-Q1 (owner, 2:15 PM):** the entry is built from the file's rows: wages and burden to expense by job and cost code (overhead rows to the overhead accounts), credit Payroll clearing; not the provider's own journal. This settles roadmap open decision 1.
11. **A19-Q2 (owner, 2:20 PM):** the source file is kept as long as the entry (never deleted); "Download source" needs `payroll.view` and every download is audited.
12. **A19-Q3 and Q3b (owner's words, 2:30 PM):** "labor accrual needs to be a different type of posting to ensure it doesnt hit the job cost as actuals and in the reports will just show as forecasted/accrued and not part of any billing payapp"; and: "GL and Job, but the accruals need to be separated from the actuals. Still need to see the job profit with the accruals, but should show with and without accruals. Same with material accruals or any job cost accruals need to be visible." (§7.)
13. **A19-Q4 (owner, 2:40 PM):** an employee not found makes the row an error ("Did you mean Marcus Webb?"); an Admin maps the name (remembered in `import_mapping`) or adds the employee, then re-checks; the batch cannot post until fixed; no employee is created from the file.
14. **A19-Q5 (owner, 2:40 PM):** reversing a posted run whose hours are on an issued T&M invoice is refused, naming the invoice ("Marcus Webb's 80.00 hours are on invoice INV-1042. Issue a credit memo first."); nothing is reversed.
15. **A19-Q6 (owner, 2:50 PM):** jobs in Mobilization, In Progress, Suspended and Completed take payroll cost; a Closed Out job's row is an error (reopen the job or code the row to overhead); leads take none.
16. **A19-Q7 and Q7b (owner, 2:50 PM):** the generic uploader is **"Card and spend import"** (Ramp, Divvy, Bill.com or any other card or spend system), its own area for v1.1 with the never-booked-twice (BF1) test; Area 19 stays payroll plus the shared batch rules. Ramp remains only an `import_source` name.
17. **A19-Q8 (owner, 3:00 PM):** burden is split by who pays it: provider-paid burden (payroll taxes the provider remits) credits Payroll clearing; burden billed separately (workers' comp, health and similar) credits an Accrued burden account, cleared when the carrier's bill is paid; job cost still gets the full burden.
18. **A19-Q9 (owner, 3:00 PM):** pay lines with 0 hours (bonus, commission) and negative rows (corrections) are allowed; a bonus posts its cost to the job with 0.00 hours; a negative correction posts negative cost and hours; T&M reads only hours, so a bonus never bills as time.

---

## 3. Tables (planning proposals)

- **`import_batch` (payroll columns; shares Area 12's `file_sha256`, `storage_key`, `line_count`):** `control_gross_cents`, `control_burden_cents`, `control_hours` (what the file says the totals are, NULL when it has none),
  `operation_id` UNIQUE (retry), `entry_date`, `reviewed_by`, `reviewed_at`, `review_digest`, `reversed_by_batch_id`, `row_version`. `status` gains **'Reversed'**. `total_cents` stays the integer-cent total of wages plus burden.
- **`payroll_import_line` (new, staging; never part of the ledger):** `line_id`, `batch_id`, `source_row_number`, `source_row_hash`, `external_ref` (provider row id, else a hash of source, pay date, employee, job, cost code, hours, wages, burden and
  the occurrence number), `employee_text`, `contact_id`, `job_text`, `project_id`, `cost_code_text`, `cost_code_id`, `department_text`, `pay_date`, `period_start`, `period_end`, `hours` (2 decimals, may be 0 or negative), `gross_cents` (may be negative), `burden_cents` (the sum of the line's burden rows, may be negative), `is_overhead`,
  `wage_acct_id`, `burden_acct_id`, `status` Valid, Error, `error_text`, `row_version`. `UNIQUE (source_id, external_ref)` is enforced across posted batches. Lines are editable only while the batch is Imported or In review.
- **`payroll_burden_type` (new) and `payroll_import_line_burden` (new, staging):** a burden type has a name and `paid_by_provider` (1 = the provider remits it, default 1; 0 = billed separately); a line's burden rows (`line_id`, `burden_type_id`, `amount_cents`) sum to its `burden_cents`. A file with one "Employer burden" column is one provider-paid burden row. A file with burden columns (for example "Workers' comp") maps each column header to a burden type through `import_mapping` (new kind 'Burden type'), with the `paid_by_provider` flag on the type (owner Q8; table shape is a planning proposal).
- **`journal_line.cost_nature` (new, planning proposal for owner Q3):** `'Actual'` (default) or `'Accrued'`, set by `ledger.py` from the posting type and never edited; job cost lines of an accrual entry and of its reversal carry `'Accrued'`.
- **`time_entry` (new columns):** `source_line_id` (the staging row, so the original file row stays linked), `reverses_time_entry_id`; **rows are never edited or deleted; a reversal inserts mirror rows with negative hours, wages and burden.** `hours` stays REAL
  (a quantity; 0 or negative allowed, owner Q9); the service compares totals in hundredths of an hour, never with float equality. A negative correction row has `reverses_time_entry_id` NULL; only a run reversal sets it.
- **`import_mapping`:** `external_kind` gains **'Cost code'**; Employee maps to a contact (`is_employee` = 1), Job/Project to a job, Department to the wage and burden accounts, Burden type to a `payroll_burden_type`.
- **Account roles (`company_settings`, found by role, never by number):** `labor_wages_acct_id` (chart 5010), `labor_burden_acct_id` (5020), `overhead_wages_acct_id`, `overhead_burden_acct_id`, `accrued_payroll_acct_id`, **`accrued_burden_acct_id`** (owner Q8: cleared when the carrier's bill is paid, Area 3); `payroll_clearing_acct_id` exists.
  A Department mapping may override the wage and burden roles for its lines.
- **Setting (control, OFF):** `payroll_accrual_enabled` (§7).
- **Not added:** timesheets, pay rates, tax tables, net pay or withholding detail, a payroll register, a provider API connector (a file or spreadsheet only in v1; a connector is a provider step).

---

## 4. Import and mapping rules (`payroll_import.py`)

1. **One call stores the file and the batch:** `import_file(context, source, file, operation_id)` stores the file through `storage.py` (H3), keeps `file_sha256`, parses into lines and returns the batch. The same hash for the same source is refused: "This file was already imported on <date> as batch <n>."
2. **Row checks (a row with an error blocks Post, never Import):** valid ISO or MM/DD/YYYY dates; hours a number with at most 2 decimals, **0 and negative allowed** (owner Q9: a bonus has 0.00 hours, a correction is negative); gross and burden money to the cent, **negative allowed** (burden may be blank = 0); never a float; a row with 0.00 hours and 0 cents is flagged as empty, not an error; Employee resolves to a contact with `is_employee` = 1 (**owner Q4:** a name not found is an error with "Did you mean ...", an Admin maps or adds the employee, and no employee is created from the file); Job resolves to a job; Cost code resolves to a cost code of that job; a job takes cost only in Mobilization, In Progress, Suspended or Completed (**owner Q6**); a **Closed Out** job's row is an error ("reopen the job or code the row to overhead"); a **lead** takes no cost
   (mockup wording: "Garcia roof replacement is a lead (New lead stage) without a signed contract, so it cannot take costs yet."). Errors say what to do next in one sentence and offer "Did you mean ...".
3. **Mapping is remembered:** a fixed mapping (employee, job, cost code, department) is saved in `import_mapping` and applied to later files; a changed mapping re-resolves the unreviewed rows only.
4. **No job = overhead:** a row with no job number is overhead (mockup text): wage and burden go to the overhead roles, no project, no cost code. Hours of overhead rows are stored on `time_entry` with `project_id` NULL and never reach T&M.
5. **Rows already posted:** a row whose `external_ref` was posted for the same source in another batch is refused with the batch it came from; the rest of the file still imports.
6. **Control totals:** when the file has a total (rows or footer) it is read as a control; the service compares gross, burden and hours as integers (hours in hundredths). **Planning proposal, owner may revise (consistent with L8):** a money control total that differs from the rows by exactly 1 cent is shown as information and **does not block Post**; a difference of 2 cents or more **blocks Post**; hours must match exactly in hundredths. No rounding line is posted: the entry is built from the rows, so it always balances, and the control total is only a check.
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
5. **One entry per batch,** each row two or more lines: wages and burden to their accounts (with project and cost code on job lines; **job cost gets the full burden**, owner Q8). The credits split by who pays: **provider-paid burden and all wages go to Payroll clearing; burden billed separately goes to Accrued burden** (owner Q8). A negative row posts the opposite side (a credit to expense, a debit to clearing).
6. **Accrued burden is cleared by the carrier's bill:** when the workers' comp or health bill is entered and paid in Area 3, its line is coded to the Accrued burden role (Dr Accrued burden / Cr Accounts payable), so the balance is the burden accrued and not yet billed. The Area 13 close lists the Accrued burden balance (planning proposal).
7. **Payroll clearing is cleared by the bank,** not by this area: the provider's bank debit is matched by Area 12 (bank feed or rule) to the clearing account, and Area 13's close reconciles it. This area posts no cash.

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

**The same run when 40,000 of the 258,660 burden is workers' comp billed by the carrier (owner Q8; planning example of the split by row):** workers' comp Marcus 12000, Priya 10000, Jordan 8000, Dana 10000 = 40,000; provider-paid burden 57120 + 51560 + 45280 + 64700 = 218,660 (= 258,660 - 40,000). Debit lines are unchanged (job cost still gets the full burden: 691.20 on Marcus and so on). Credits: Payroll clearing 1,437,000 + 218,660 = **1,655,660** ($16,556.60); Accrued burden **40,000** ($400.00). Total credits 1,655,660 + 40,000 = 1,695,660 = debits 1,695,660.

**Bonus and correction rows (owner Q9; run 11/01/2026 to 11/15/2026, pay date 11/15/2026, burden 0 on both rows):**

| Employee | Job, cost code | Hours | Gross wages |
|----------|----------------|-------|-------------|
| Priya Natarajan (bonus) | CA0002-001, 05-100 | 0.00 | 50000 ($500.00) |
| Priya Natarajan (correction of 4.00 overpaid hours at $45.00) | CA0002-001, 05-100 | -4.00 | -18000 (-$180.00) |

Entry dated 11/15/2026: Dr 5010 Direct field labor, CA0002-001, 05-100 $500.00; Cr 5010 Direct field labor, CA0002-001, 05-100 $180.00; Cr Payroll clearing $320.00 (the batch total 50000 - 18000 = 32000). Debits 50000 = credits 18000 + 32000 = 50000. `time_entry`: (0.00 h, 50000, 0) and (-4.00 h, -18000, 0). **T&M sums hours only:** the bonus adds 0.00 h and the correction -4.00 h, so net T&M hours for CA0002-001, 05-100 in this run are -4.00 and the bonus is never billed as time.

**Edge cases and refusals (each with a test):**
- The file is imported again: "This file was already imported on 11/02/2026 as batch 417." Nothing is added.
- A re-exported file for the same run (new hash, same rows): every row is refused as already imported (rule 5); the batch has zero new lines.
- Marcus Webb's row is edited after review (hours 80.00 -> 82.00): the review is void; Post is blocked until the new digest is reviewed; the change is audited.
- The lock for the Payroll area covers 10/31/2026: Post is refused naming the area and date; nothing is written.
- Post is called again after the network drop with the same operation id: the original result returns; one entry, four rows.
- Hours "4o.0" in row 18: the row is an Error with "This is not a number: 4o.0"; the batch can be reviewed only after the row is fixed or the line removed (a removal is audited; the file stays).
- A pay line for a job that is Closed Out: Error ("reopen the job or code the row to overhead", owner Q6); the same line for a Solar install job in its Installation delivery stage (status In Progress) is Valid.

---

## 6. Reversing, voiding and downloading the source

- **Void** (unposted batch): status Voided; lines and file are kept (the source file stays through `storage.py`); the audit log records who and why (Area 18 reasons apply only to controls, so none is required).
- **Reverse a posted run** (`payroll.import`, sensitive): creates a batch with `batch_nature` 'Reversal' and `reverses_batch_id`, posts the mirror entry through `ledger.py` dated the reversal date (today, which must be in an open period), inserts the negative `time_entry` rows (`reverses_time_entry_id`), sets the original `reversed_by_batch_id` and status Reversed. Refused when the period or area is locked (mockup wording), or when any of its hours are on an issued T&M invoice (**owner Q5:** "Marcus Webb's 80.00 hours are on invoice INV-1042. Issue a credit memo first."; nothing is reversed).
  **Example:** reversing run 10/16/2026 to 10/31/2026 (batch total 1,695,660; all burden provider-paid) on 11/03/2026: Dr Payroll clearing 1,695,660 / Cr each of the six debit lines above (a run with separately billed burden also debits Accrued burden for that part); net `time_entry` hours for RI0001-002, 05-200 = 80.00 - 80.00 = 0.00.
- **Download source** returns the stored file for the selected batch to a user with `payroll.view` and writes an audit event with the user and batch (next_step). The retention rule is owner Q2: the file is kept as long as the entry and is never deleted.

---

## 7. Job cost accruals: the labor accrual (optional control, OFF) and the separation rule

**Owner A19-Q3 and Q3b (words quoted in §2 item 12):** an accrual is a different type of posting, in the GL and on the job, kept apart from actuals. **Planning reading (owner may correct):** the rule applies to **every job cost accrual** (labor here; materials received not billed and subcontract work not billed in their own areas), so the posting type is shared (pointers in Areas 5, 7 and 17).

- **The posting type:** an accrual entry's job cost lines carry project, cost code and `journal_line.cost_nature` = 'Accrued' (§3). It is in the GL and the trial balance like any entry. **Job reports read two measures and a total: Actual (lines 'Actual'), Accrued (lines 'Accrued', net of reversals) and Total (both).** Job profit is shown **with and without accruals** (owner). Budget-to-actual and percent complete by cost use **Actual only** (planning proposal; §14).
- **Never billed:** accrued lines never reach T&M billing or a pay application (owner: "not part of any billing payapp"). `posted_labor_hours` reads `time_entry`, and an accrual writes none; progress billing reads Actual only.
- **The control:** `payroll_accrual_enabled` = 0 by default (Company Settings > Controls, Admin or Master, audit-logged). When ON, a batch with `batch_type` 'Labor Accrual' and `batch_nature` 'Accrual' is built from the same file format (pay date = the accrual date, a month-end) for labor worked and not yet in a payroll run. **Built in v1** (owner Q3).
- **Posting:** one entry dated the accrual date: debit the same wage and burden accounts (job lines with project, cost code, 'Accrued'), credit **Accrued payroll**. The service creates, in the same transaction, a second batch with nature 'Reversal' dated the first day of the next month, whose lines are 'Accrued' too; if that date's period or the Payroll area is locked, the accrual is refused naming it.
- **Review** applies exactly as in §5 (always on; Area 14's row is additional).
- **Example, accrual 11/30/2026 for 11/16 to 11/30 (paid 12/04):** Marcus Webb 384000 + 69120 on RI0001-002, 05-200; Priya Natarajan 342000 + 61560 on CA0002-001, 05-100.
  11/30: Dr 5010 RI0001-002 $3,840.00, Dr 5020 RI0001-002 $691.20, Dr 5010 CA0002-001 $3,420.00, Dr 5020 CA0002-001 $615.60 (all 'Accrued') / Cr Accrued payroll $8,566.80 (856,680 = 384000 + 69120 + 342000 + 61560).
  12/01 reversal: Dr Accrued payroll $8,566.80 / Cr the same four lines $8,566.80 ('Accrued'). 12/04 payroll run for the same labor: Dr the four lines $8,566.80 ('Actual') / Cr Payroll clearing $8,566.80.
  **Job RI0001-002, cost code 05-200 (labor 453,120 = 384000 + 69120):**

  | Month | Actual | Accrued | Total |
  |-------|--------|---------|-------|
  | November 2026 | $0.00 | $4,531.20 | $4,531.20 |
  | December 2026 | $4,531.20 | -$4,531.20 | $0.00 |

  Job CA0002-001, 05-100 (403,560 = 342000 + 61560) is the same pattern: November Accrued $4,035.60, December Actual $4,035.60 and Accrued -$4,035.60. 453,120 + 403,560 = 856,680.
  **Job profit for RI0001-002 in November (illustrative):** revenue billed 2,000,000 ($20,000.00), other actual job cost 900,000 ($9,000.00). **Without accruals** 2,000,000 - 900,000 = 1,100,000 ($11,000.00); **with accruals** 1,100,000 - 453,120 = 646,880 ($6,468.80). T&M and the pay application for that job read Actual only.

---

## 8. Reads, reports and the close

- **List (`payroll.html`):** columns Pay period, Source and entry, Employees, Hours, Wages and burden, Status; **Wages and burden are shown only with `payroll.view`**; others see hours and employees. Filters All, Pending review, Posted, Reversed (§5). Export CSV and Excel carry the same columns (Area 17 export rules).
- **Job cost:** job cost reports read the ledger lines (job and cost code) and show **Actual, Accrued and Total, and job profit with and without accruals** (owner Q3b; Areas 7 and 17 own the report); labor by employee for a job needs `payroll.view`.
- **T&M:** `posted_labor_hours(project_id, cost_code_id, from, to)` returns `time_entry` rows net of reversals with their source ids and quantities for Area 5; an accrual or an unposted batch is never returned, and only hours are read (a bonus row has 0.00 hours).
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

- **Baselines (2.9 pass, tests first):** `import_batch` columns and the 'Reversed' status; `payroll_import_line`; `time_entry` columns; the `import_mapping` kind; the six account roles, `payroll_burden_type` and `payroll_import_line_burden`, `journal_line.cost_nature`, and the control column (the dev databases are rebuilt).
- **Code:** `modules/services/payroll_import.py` (import, map, edit, review, post, reverse, void, download, accrual) and the shared import-batch rules it reuses; `ledger.py` stays the only journal writer; no UI or HTTP import (H1), no clock (H2: dates from the context), files through `storage.py` (H3), no SQLite-only SQL (H5).
- **Tests (named from next_step, plus these):** `test_payroll_and_approvals_open_exact_saved_batch`, `test_human_review_covers_exact_mapped_rows_that_post`, `test_payroll_post_requires_review_with_area14_approval_off`,
  `test_payroll_post_requires_review_and_area14_approval_when_configured`, `test_changed_payroll_batch_after_review_requires_new_review`, `test_payroll_retry_after_lost_confirmation_no_duplicate_rows_or_entries`,
  `test_payroll_import_rejects_invalid_dates_hours_amounts_and_unresolved_references`, `test_payroll_provider_control_totals_reconcile_to_mapped_rows`, `test_payroll_labor_rows_link_original_source_rows`,
  `test_payroll_job_cost_uses_mapped_job_and_cost_code`, `test_tm_billing_uses_only_posted_payroll_import_hours`, `test_payroll_download_returns_selected_batch_source_and_audits`,
  `test_same_file_hash_is_refused`, `test_reexported_run_adds_no_rows`, `test_payroll_entry_balances_and_credits_clearing_for_the_batch_total` (the 1,695,660 example),
  `test_overhead_rows_have_no_project_and_never_reach_tm`, `test_lead_job_cannot_take_payroll_cost`, `test_closed_out_job_takes_no_payroll_cost`, `test_multiple_pay_dates_in_one_file_are_refused`,
  `test_posting_into_a_locked_payroll_area_is_refused_and_writes_nothing`, `test_reverse_inserts_negative_time_entry_rows_and_net_hours_are_zero`, `test_reverse_refused_when_hours_are_on_an_issued_tm_invoice`,
  `test_wages_hidden_without_payroll_view`, `test_accrual_control_defaults_off`, `test_accrual_posts_and_reversal_is_created_with_it`, `test_accrual_refused_when_reversal_period_is_locked`,
  `test_accrual_writes_no_time_entry_and_never_reaches_tm`,
  `test_burden_split_by_who_pays_credits_clearing_1655660_and_accrued_burden_40000` (total 1,695,660), `test_job_cost_gets_the_full_burden_when_part_is_accrued`, `test_carrier_bill_clears_accrued_burden`,
  `test_zero_hour_bonus_row_posts_cost_with_no_hours`, `test_negative_correction_row_posts_negative_cost_and_hours` (the 50000 and -18000 example), `test_tm_hours_sum_ignores_bonus_cost`,
  `test_unresolved_employee_blocks_post_and_is_never_created`, `test_closed_out_job_row_is_an_error_and_a_completed_job_is_valid`, `test_control_total_one_cent_difference_does_not_block_and_two_cents_blocks`,
  `test_accrual_lines_carry_cost_nature_accrued_and_never_count_as_actuals`, `test_job_report_shows_actual_accrued_total_and_profit_with_and_without_accruals` (the 453,120 and 646,880 example),
  `test_accrual_never_reaches_a_pay_application`, `test_accrual_reversal_nets_accrued_to_zero_and_the_run_is_actual`, `test_source_file_is_kept_with_the_entry_and_every_download_is_audited`, `test_agent_cannot_import_review_post_or_reverse_payroll`, `test_payroll_import_static_has_no_ui_clock_or_sqlite_pragma`.

---

## 11. Integrity checks kept (always on)

Integer cents and balanced double entry on the one entry; the review before posting; no posting into a closed period; the posted entry append-only and corrected by reversal; the audit log; permissions enforced in the service; the agent never imports, approves or posts; the same file or row never posts twice.

---

## 12. Conflicts with decisions, the baseline or the mockups (flagged)

1. **design_decisions "Imports" preferred the provider's own journal as the cost source, hours only on `time_entry`; roadmap open decision 1.** **Closed by owner A19-Q1 (2:15 PM): the entry is built from the file's rows; roadmap open decision 1 is settled.** (Pointers in design_decisions and the roadmap.)
2. **Staging tables:** design_decisions names `staged_transaction` and `staged_line`; the baseline's `txn_type` has no pay line and no hours or burden columns. Proposal: a dedicated `payroll_import_line`.
3. **Statuses:** the baseline has Imported, In review, Approved, Posted, Voided; the mockup filters Pending review, Posted, Reversed. Proposal: add 'Reversed'; "Pending review" groups three statuses.
4. **`time_entry` has no source-row link and no reversal marker;** it is immutable by proposal, so reversal inserts negative rows.
5. **No wages, burden, overhead, accrued-payroll or accrued-burden account roles;** only `payroll_clearing_acct_id` exists (Area 7: code finds accounts by role).
6. **`import_mapping` kinds lack Cost code.**
7. **Entry date:** the mockup shows "dated 10/31" for a run ending 10/31; wages earned in one month and paid in the next fall in the pay-date month unless the accrual control is ON (planning proposal; Q3).
8. **Area 12 F11 and BF1:** card-charge lines and the never-booked-twice rule were assigned to "area 19 or the provider step"; **owner A19-Q7b: the feature is "Card and spend import"** (Ramp, Divvy, Bill.com or any card or spend system), its own area for v1.1 with the BF1 test. This area designs payroll and the shared batch rules only. Ramp stays an `import_source` name.
9. **`time.approve` (Area 6 note: T&M hours "approved when the import posts")** is not used; posting is the approval of the hours (planning reading).
10. **Mockup wizard says "Wages and burden are hidden from people who do not have payroll access";** the list page shows them for all; the list must hide them (work order).
11. **Mockup "Close" button on a run row** is not a payroll action; assumed to close the row detail (work order).

---
12. **`journal_line` has no accrual or actual marker;** `cost_nature` is added (owner Q3 needs the separation; the column is a planning proposal). Areas 5, 7 and 17 read it (pointers).
13. **Area 6 and Area 5 T&M text says hours come from "posted payroll imports";** accruals write no `time_entry`, so the rule holds (owner Q3).

## 13. Questions for the owner (recommended option first, with an example; **all answered 2026-11-25 2:15 to 3:00 PM, section 15**)

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
- **Q7. Card and spend import (Ramp, Divvy, Bill.com and other card or spend systems) and the other batch types?**
  (A) Area 19 designs the shared batch rules and payroll only; Card and spend import is its own v1.1 area with the BF1 test (recommended).
  (B) Design it here now.
  Example: a card charge of $812.40 and its bill never both post (BF1) in the provider step.

---

## 14. Open items (not decisions)

- Certified payroll (WH-347) and prevailing wage (Area 7 flag; v1.1).
- Timesheets, pay rates and a bill rate per employee (Area 6 Q26 A: none in v1).
- A provider API connector (Gusto, Rippling) instead of a file.
- Net pay, withholdings, payroll liabilities and a payroll register.
- **Card and spend import** (Ramp, Divvy, Bill.com or any card or spend system; its own v1.1 area) with the BF1 never-booked-twice test (owner Q7b); bills and reimbursements batches.
- Whether cost-to-cost percent complete and budget-to-actual should include accrued cost (planning proposal: Actual only; owner may revise).
- Material and subcontract accruals: the posting type is shared here (§7), their own entries belong to Areas 9 and 3.
- The job-charging posting for equipment by the hour (Area 11 open item) is not payroll.

## 15. Owner answers 2026-11-25 2:15 to 3:00 PM and the planning fixes (dated amendment; §13 stays as asked)

- **A19-Q1 A, Q2 A, Q4 A, Q5 A, Q6 A (owner):** recorded as owner rules in §2 items 10, 11, 13, 14 and 15. Q1 closes §12 conflict 1 and settles roadmap open decision 1; Q2 closes next_step's payroll retention item.
- **A19-Q3 and Q3b (owner's words, quoted in §2 item 12):** §7 is reworked: a separate accrual posting type in the GL and the job, never counted as job cost actuals; Actual, Accrued and Total, and job profit with and without accruals; never in T&M or a pay app. *Planning reading (owner may correct):* it applies to all job cost accruals, so `journal_line.cost_nature` is shared (Areas 5, 7, 17 pointers); budget-to-actual uses Actual only.
- **A19-Q7 and Q7b (owner):** the feature name is "Card and spend import" (§2 item 16, §12 item 8, §14, Area 12 pointer).
- **A19-Q8 (owner):** burden by who pays, with the 1,655,660 and 40,000 example (§5). **A19-Q9 (owner):** 0-hour and negative rows with the 50000 and -18000 example (§5, §4 rule 2).
- **Planning fixes from the review of d1a406d:** §4 rule 2 "Completed (Closed Out)" wording replaced (Closed Out takes no cost); §4 rule 6 states that 1 cent does not block Post and 2 cents or more blocks it (planning proposal, consistent with L8).
- **Still planning proposals:** the tables for burden types, `journal_line.cost_nature`, "Accrued burden" cleared by the carrier's bill, Actual-only budget-to-actual.
