# StrataLedger controls and analytics audit (read-only)

**Date:** 2026-11-10 · **Schema audited:** migrations 001 + 002 (branch `phase1-ledger-integrity`), i.e. the schema the real files will have once 002 is applied.
**Method:** Built a fresh company database from the migrations in a scratch folder and tried 30 things an accounting control should stop. Each probe ran in its own rolled-back transaction with foreign keys on (as `get_connection` opens them). No project file or real database was opened. Probe script: `controls_probe.py` in the session scratchpad (not committed).

**Result: 29 of 30 probes were allowed.** The one that was blocked is itself a bug (credit memos cannot be saved; C7).

The Phase 1 triggers do their job for what they cover: balance, 2+ lines, one-sided lines, closed `period_id`, and locks on posted entries. The gaps are around those rules: what a line may post *to*, what counts as a period, and every record outside `journal_entry`/`journal_line` (invoices, payments, allocations, deferrals, the audit log), which can still be changed after its ledger entry is posted.

---

## Summary

| # | Area | Finding | Severity |
|---|---|---|---|
| L1 | Ledger | A line with **no account** posts | **Critical** |
| L2 | Ledger | Lines post to **header (non-postable)** and **inactive** accounts | High |
| L3 | Ledger | Lines can exist with **no entry** (orphans) | Medium |
| P1 | Periods | A non-ISO date (`03/20/2026`) **gets past the closed-period check** | **Critical** |
| P2 | Periods | A posted entry can be **voided inside a closed period** | **Critical** |
| P3 | Periods | `period_id` need not match `entry_date`; entries post with **no period**; periods overlap or end before they start | High |
| P4 | Periods | Closed periods **reopen** with no reason, user or trail; `is_closed = 2` counts as open | High |
| R1 | Reversals | Reversals aren't checked: they can reverse a draft, reverse the same entry twice, or not mirror the amounts | High |
| A1 | Chart of accounts | An account with posted history can be **re-typed or re-coded**, which rewrites past statements | High |
| A2 | Chart of accounts | Accounts need no type; there are no statement, subtype or control-account fields; nothing is seeded | High |
| C1 | Subledgers | A **Sent invoice with a posted entry can be deleted** (AR no longer ties to the GL) | **Critical** |
| C2 | Subledgers | **Paid invoices** can be edited and moved back to Draft | **Critical** |
| C3 | Subledgers | **Posted payments** can be edited and deleted | **Critical** |
| C4 | Subledgers | An invoice's stored totals needn't match its lines | High |
| C5 | Subledgers | One journal entry can be the posting for several invoices and payments | High |
| C6 | Subledgers | Payments can be **over-allocated**, allocated negatively, or allocated to nothing | High |
| C7 | Subledgers | The UI sends `'Credit Memo'` but the schema allows only `'Credit memo'`, so **credit memos cannot be saved** | High (bug) |
| C8 | Subledgers | Customer invoice numbers are unique only per contact, so the same number can go to two customers | High |
| C9 | Subledgers | Negative amounts are allowed everywhere and there is no sign convention | Medium |
| C10 | Subledgers | Deferral schedules need not sum to the deferral; posted schedule lines are editable | Medium (service layer) |
| C11 | Subledgers | `recon_id` and the other journal_line tags have no FKs | High |
| T1 | Audit trail | `audit_log` can be **edited and deleted**, and nothing writes to it automatically | **Critical** |
| T2 | Audit trail | No posted_by / posted_at / approved_by; preparer and poster can be the same person; `created_by` is optional | High |
| T3 | Audit trail | No entry number; deleted drafts leave gaps that can't be explained | Medium |
| D1 | Data quality | Dates and timestamps are free text; 0/1 flags have no CHECK | High |
| D2 | Data quality | FX rates and tax rates are REAL; no base-currency amounts; currency defaults conflict (PHP vs USD) | Medium |
| X1 | Analytics | Dimensions exist on invoice lines but **not on journal lines** | High |
| X2 | Analytics | No indexes; every ledger query is a full scan | Medium |
| X3 | Analytics | No views, no fiscal-year fields, no signed amounts, no link from an entry back to its source document | Medium |
| X4 | Analytics | Charts of accounts aren't comparable across company files; no intercompany tagging | Medium |

---

## 1. Ledger (double entry)

**L1 — A line with no account posts.** `journal_line.account_id` is nullable, and the posting trigger never checks it. Probe: an entry with a debit to 1000 and a credit with `account_id NULL` posted. The trial balance then has a credit that belongs to no account, so the TB still "balances" by total while not balancing by account.
*Fix (schema, migration 003):* `account_id NOT NULL`, plus a posting check that every line has an account.

**L2 — Posting to header and inactive accounts.** `is_postable` and `is_active` exist but nothing reads them. Probe: both posted. Header accounts that carry balances double-count in rolled-up reports.
*Fix (schema):* the posting trigger rejects lines whose account has `is_postable = 0` or `is_active = 0`. Also add `CHECK (is_postable IN (0,1))` and the same for the other flags.

**L3 — Orphan lines.** `journal_line.entry_id` is nullable. Probe: a line with no entry was saved. These lines never post, but they sit in any `SUM` that doesn't join to `journal_entry`.
*Fix (schema):* `entry_id NOT NULL`.

## 2. Periods

**P1 — Date format bypass.** The closed-period check compares text, and nothing forces `entry_date` into ISO `YYYY-MM-DD`. Probe: March was closed, an entry dated `03/20/2026` posted, and `'03/20/2026'` doesn't sort between `'2026-03-01'` and `'2026-03-31'`. The real files already contain mixed formats: CHRM's `company_profile` has fiscal year ends `'12-31'` and `'12/31'`.
*Fix (schema):* `CHECK (entry_date = date(entry_date))` on every date column the ledger uses (entry, invoice, payment and period dates), and an equivalent CHECK for timestamps.

**P2 — Voiding in a closed period.** Phase 1 allows `is_void` 0 → 1 on a posted entry (as instructed), but doesn't check the period. Probe: the entry was posted, March was closed, then the entry was voided. If reports exclude voided entries, **a closed period's balances changed after close**, which is exactly what closing is meant to prevent. Voiding is also a correction made without a reversing entry, which is in tension with rule 8.
*Recommendation:* decide what void means. The usual control is that voiding **always creates a reversing entry dated in an open period**, and the flag only marks the pair. Reports then never need to filter on `is_void`. At minimum, the lock trigger should reject voiding when the entry's period is closed.

**P3 — Period integrity.** Each of these was allowed:
- An entry dated September posted with April's `period_id`.
- An entry posted in 2031 when no period covers that date.
- Periods overlapping, and a period ending before it starts.

Period-based and date-based reports will disagree.
*Fix (schema):*
- When posting, `period_id` is required and `entry_date` must fall inside it. Alternatively, derive `period_id` from the date and stop storing both.
- `CHECK (start_date <= end_date)`.
- A trigger that rejects overlapping periods.

**P4 — Reopening.** `UPDATE fiscal_period SET is_closed = 0` is allowed with no reason, user or time recorded. `is_closed = 2` is accepted and treated as open, because the trigger tests `= 1`.
*Fix:* `CHECK (is_closed IN (0,1))` (schema). Add `closed_at` and `closed_by`, and keep a `period_status_history` table, append-only (schema). Reopening needs a reason and a role (service layer).

## 3. Reversals

**R1 — Reversals aren't checked.** Probe: two posted reversals of an unposted entry, with amounts that didn't mirror the original.
*Fix (schema):*
- The original must be posted.
- `UNIQUE (reverses_entry_id)`, so each entry is reversed at most once.
- The reversal's lines must mirror the original's: same accounts, debits and credits swapped.
- The reversal's date must be in an open period.

## 4. Chart of accounts

**A1 — Changing history.** Probe: an Asset account with posted lines was changed to Expense and given a new code and name. Every past balance sheet and income statement changes without a single journal line changing.
*Fix (schema):* once an account has posted lines, lock `type_id`, `code` and `normal_balance`, either by trigger or through an `account_history` table. Renaming the description can stay allowed.

**A2 — Structure for statements.** `account.type_id` is nullable, so an account can belong to no statement. `account_type` has only 5 names. A fresh database contains **no** account types, periods, settings row or import sources, so the CHECK on `account_type.name` is the only thing defining them.
*Fix (schema):*
- `type_id NOT NULL`, and seed `account_type` in a migration.
- Add `statement` (BS/IS), `subtype` (current asset, fixed asset, COGS, opex, other income, …), `cash_flow_category`, and `control_type` (AR, AP, sales tax, payroll, deferral, or none).

Control accounts matter for C1–C3. **Manual journal entries to AR/AP control accounts are the most common way subledgers drift from the GL.** The posting trigger should allow lines on a control account only when `source` is the matching subledger.

## 5. Subledgers (invoices, payments, allocations, deferrals)

The journal is now locked, but the documents that create journal entries are not. So the GL is protected while the AR and AP ledgers can drift away from it.

**C1 — Delete a posted invoice.** Probe: a Sent invoice whose entry was posted was deleted, and its lines cascaded with it. The GL still shows the receivable; the AR ledger no longer does.
**C2 — Edit a Paid invoice.** Probe: lines and total changed, status set back to Draft.
**C3 — Edit or delete a posted payment.** Probe: amount changed, then the row deleted.
*Fix (schema, same pattern as F3):* once `entry_id` is set, or the status is past Draft, the invoice, its lines and the payment are locked. Status moves only forward (Draft → Sent → Paid/Void). Deleting an invoice requires Draft status. Changing an invoice after that point means a credit memo.

**C4 — Stored totals vs lines.** Probe: an invoice with `total_cents` of 10000 had lines summing to 500. The stored BIR breakdown (`vatable_sales`, `vat_exempt`, `zero_rated`, `tax`, `cwt`) has no consistency checks either.
*Fix:* compute totals in the service layer and store them only when posting. Add a schema check at Draft → Sent that `subtotal_cents` equals the sum of the lines and that `total = subtotal + tax - cwt` (confirm the BIR formula with your CPA).

**C5 — Shared entries.** Probe: one journal entry was linked as the posting of two invoices and a payment. A document and its entry need a 1:1 link.
*Fix (schema):* `UNIQUE (entry_id)` on `invoice`, `payment` and `deferral_schedule_line`, plus a back-link on the entry (see X3).

**C6 — Allocations.** Probe: 999,999 allocated from a 100 payment; a negative allocation that pointed at nothing.
*Fix:*
- Schema: `amount_applied_cents > 0`, and exactly one of `invoice_id`/`deferral_id`. That rule was moved to the service layer in Phase 1, but it's simple enough to be a CHECK.
- Service layer: the sum of a payment's allocations can't exceed the payment, and the sum on an invoice can't exceed its open balance. These can also be triggers.

**C7 — Credit memos can't be saved.** [views_billing.py:53](../modules/views_billing.py#L53) offers `"Credit Memo"`, CLAUDE.md section 4 says `'Credit Memo'`, and the CHECK in `001_company.sql` allows only `'Credit memo'`. The probe confirmed the CHECK rejects the UI value. This is a Phase 3 screen fix plus a decision on the canonical spelling. Pick one and enforce it everywhere.

**C8 — Invoice numbering.** `UNIQUE (invoice_type, contact_id, invoice_number)` is right for vendor bills, because vendors repeat numbers. For your own invoices and credit memos it lets `INV-1000` go to two customers. Because `contact_id` is nullable, two invoices with no customer can also share a number. Auditors test sales numbering for gaps and duplicates. `company_settings.next_invoice_number` also invites MAX+1-style races.
*Fix (schema):*
- A partial unique index on `invoice_number` where `invoice_type IN ('Invoice', 'Credit memo')`.
- `contact_id NOT NULL`.
- Numbers drawn from a sequence table, like the customer-code design.

**C9 — Signs.** Negative payments, quantities and prices are all accepted. With no convention, credit memos could be stored either as negative invoices or as positive credit memos, and reports will double-count or cancel them.
*Fix:* amounts are positive and the document type carries the sign. Add `CHECK (>= 0)` on money columns except where a negative value is designed in.

**C10 — Deferral schedules.** Probe: a schedule summing to 5000 on a 1200 deferral, and a Posted line edited and set back to Scheduled. This feature isn't built yet, so per the Phase 1 decision these rules belong in the service layer. Record them now: the schedule sums to `original_amount_cents`, and posted lines lock.

**C11 — Dangling tags.** `journal_line.contact_id`, `project_id`, `cost_code_id`, `deferral_id`, `batch_id` and `recon_id` have no FKs. The audit already noted this; the probe confirmed lines can point to rows that don't exist, including a reconciliation. A line can therefore show as "reconciled" against nothing, and job-cost reports can count cost against a job that doesn't exist.
*Fix (schema):* real FKs on all six, plus `invoice.batch_id` and `contract_line.change_order_id`. Once a reconciliation is complete, lock `recon_id` on its lines.

## 6. Audit trail and segregation of duties

**T1 — The audit log is optional and editable.** Probe: posting an entry wrote 0 rows to `audit_log`, and existing rows could be updated (including `logged_at`) and deleted. A log that the app has to remember to write, and anyone can edit, doesn't count as audit evidence.
*Fix (schema):*
- `audit_log` is append-only: triggers reject UPDATE and DELETE.
- Triggers write the audit rows automatically for posting, voiding, period close/reopen, and changes to accounts, invoices and payments. The service layer adds the user, since SQLite has no session user. One way is a one-row `audit_context` table the service layer sets inside each transaction.
- Optional: hash-chain the rows (each row stores a hash of the previous one) so tampering with the file is detectable.

**T2 — Who posted, who approved.** `journal_entry` has `created_by`, which is optional, and no `posted_by`, `posted_at` or `approved_by`. The probe posted with every user field empty. Auditors' first questions are who made each entry and who approved it.
*Fix:*
- Schema: `posted_by` and `posted_at` must be set in the same UPDATE that posts. Add `approved_by`, and `origin` (Human/Agent/Import/System), which the AI plan already calls for.
- Service layer, configurable: a manual entry above a threshold, or any entry in a closed period, needs approval from a second user.

**T3 — Entry numbering.** `entry_id` comes from AUTOINCREMENT, so deleted drafts leave gaps that can't be explained (the probe deleted a draft with no trace).
*Fix (schema):* a separate `entry_number` assigned **at posting** from a sequence table, so posted entries are gapless. Drafts keep their internal ID.

## 7. Data quality

**D1 — Free-text dates and flags.** Every date is TEXT with no format check. This is what causes P1, and it will break every date filter in reports. Every 0/1 flag except the few added in 002 accepts any value (the probe stored `is_closed = 2`).
*Fix (schema):* date-format CHECKs and `IN (0,1)` CHECKs, added through the same rebuild pattern as 002.

**D2 — Currency.**
- `invoice.exchange_rate` and `payment.exchange_rate` are REAL, and `tax_rate.rate` is REAL too, so the money they produce goes through float arithmetic. Rule 1 allows REAL for rates, but the cents they produce must be computed deterministically.
- Neither `journal_line` nor `invoice_line` stores a base-currency amount, so FX gains and losses and revaluation can't be computed.
- Defaults conflict: `invoice` and `payment` default to `'PHP'`, while `company_settings` and `company_profile` default to `'USD'`.

*Fix:*
- Store rates as scaled integers (tax in basis points; FX as rate × 10^6), or as exact decimal text.
- Store `amount_cents` plus `base_amount_cents` on journal lines.
- Make the documents default to the company's base currency.

## 8. Optimizing data collection for analysis

**X1 — Dimensions don't reach the GL.** `invoice_line_dimension` exists, but there is no `journal_line_dimension`. Once an invoice posts, the GL loses its Cost Center, Region and Profit Center, so segment P&L, departmental budget vs actual and margin by dimension can't be built from the ledger. `invoice_line.department_tag` is a free-text duplicate of the same idea.
*Recommendation:*
- Add `journal_line_dimension`, with the same shape and composite FK as `invoice_line_dimension`.
- Copy the dimensions onto the journal lines at posting (Phase 4).
- Drop `department_tag` once dimensions replace it.

**X2 — Indexes.** The schema has none besides the automatic unique ones. A trial balance does a full scan of `journal_line` and a temp B-tree for the GROUP BY, and filtering by project scans the whole table. Fine at today's size; at a few years of transactions every report slows down.
*Recommended starting set:*
- `journal_line (entry_id)`, `journal_line (account_id, entry_id)`, `journal_line (project_id)`, `journal_line (contact_id)`
- `journal_entry (is_posted, entry_date)`, `journal_entry (period_id)`
- `invoice (contact_id, status)`, `invoice_line (invoice_id)`
- `payment_allocation (invoice_id)`, `payment_allocation (payment_id)`
- unique `staged_transaction (batch_id, external_ref)`

**X3 — An analysis layer.**
- **Fiscal calendar:** add `fiscal_year`, `period_number`, `quarter` and `is_adjustment_period` to `fiscal_period`. Today yearly analysis means parsing period names. An adjustment period (period 13) keeps audit adjustments separate from operations.
- **Back-link to the source:** the entry links to its document only through the document's `entry_id`. Add `source_type` + `source_id` on `journal_entry`, or a `journal_entry_source` table, so drill-down from GL to document is one join and C5 is enforced. Add `'Closing'`, `'Opening balance'` and `'Reversal'` to the `source` list. Year-end close and retained-earnings roll-forward have no source type today.
- **Views** (read-only; these are also the AI agent's read tools):
  - `v_gl_detail`: one flat row per posted line with entry number, dates, period, fiscal year, account code/type/statement/subtype, signed amount (`debit - credit`, flipped by normal balance), contact, project, cost code, dimensions and source document. This is the fact table every report, export and pivot reads.
  - `v_trial_balance` and `v_account_period_balance`: opening balance, activity and closing balance per account per period.
  - Subledger tie-outs: `v_ar_open_items` and `v_ap_open_items` with aging, plus a view comparing AR/AP subledger totals with the control account balances.
  - Exception views for continuous monitoring: unbalanced drafts, lines on inactive or header accounts, posted entries with no `posted_by`, gaps in invoice or entry numbers, periods with unposted drafts at close, manual entries to control accounts.

**X4 — Comparing across companies.** Each company is its own file with its own chart of accounts. Consolidation, benchmarking and parent/child reporting (`company_registry.parent_company_id` already models the parent chain) need:
- a shared chart template, or a `reporting_account_map` from each company's accounts to a standard chart;
- an `intercompany_company_id` tag on lines that involve another company in the group, so eliminations can be found.

Reports across companies can then `ATTACH` the files read-only and union `v_gl_detail`.

---

## 9. Where each fix belongs

Under the Phase 1 decisions, ledger rules can be schema triggers, while rules for features not built yet go in the service layer.

| Schema (a migration 003 candidate) | Service layer (Phase 2+) |
|---|---|
| L1–L3, P1, P3 (date checks), P4 flags, R1, A1, A2 seed + NOT NULL, C1–C3 locks, C5 uniqueness, C6 sign and exactly-one-of, C8 index, C11 FKs, T1 append-only and auto-audit, T2 posted_by/at, T3 entry number, D1, X1 table, X2 indexes, X3 calendar and views | P2 void-as-reversal workflow, P4 reopen approval, C4 total computation, C6 allocation limits, C9 sign convention, C10 deferral rules, T2 two-person approval, D2 rate math, X4 mapping |

**Suggested order:**
1. The Critical items: L1, P1, P2, C1–C3, T1. They're small and protect what already exists.
2. Then the High items as part of the Phase 2 service layer.
3. Then the X items with Phase 4 posting, since they shape what posting writes.

## 10. Decisions needed

1. **Void:** is it a reversing entry, or a flag that reports exclude? This affects P2 and every report filter. A reversal is recommended.
2. **Credit memo spelling** (C7), and positive amounts with sign by document type vs signed amounts (C9).
3. **Customer invoice numbering:** a company-wide sequence with gapless numbers (C8)?
4. **Whether to store `period_id` at all**, or always derive it from `entry_date` (P3).
5. **Control accounts:** block manual entries to AR/AP/tax control accounts, or warn (A2)?
6. **Two-person approval for manual entries:** on by default, a threshold, or off (T2)?
7. **Base currency per company, and whether FX is in scope** before Phase 4 (D2).
8. **Whether to put the Critical fixes in a migration 003 now**, before 002 is applied to the real files, so the real files get both in one upgrade.

---

## 11. Status (updated 2026-11-10)

**Decisions recorded:**
1. Void = reversing entry.
2. `'Credit Memo'`, positive amounts.
3. Company-wide invoice and credit memo sequences, assigned at send.
4. `period_id` is set by the system and validated; periods are contiguous.
5. Manual entries to control accounts are blocked in the service layer.
6. Manual-entry approval is a company setting.
7. `base_currency` defaults to USD; no FX before Phase 4.

**Closed by migration 003** (branch `phase1-ledger-integrity`; not yet applied to the real company files): L1, P1, P2 (void by reversal), C1–C3, T1, C7 and the sign part of C9. Rerunning the probe script on a fresh version-3 database:
- **Blocked:** `null_account`, `bad_date_format`, `void_closed`, `delete_posted_invoice`, `edit_paid_invoice`, `delete_posted_payment`, `audit_tamper`, `audit_auto`, `negative_money`, and reversals without a reason.
- **Now accepted (correct):** `credit_memo_ui_value`.
- **Partly closed:** `draft_delete` is still allowed, but it now leaves an audit row. In `overallocate`, negative allocations are blocked, but allocating more than the payment is still allowed (C6, migration 004).

**Closed by migration 004** (same branch; not applied to any real file):
- **Periods:** P3 and the schema part of P4 (decision 4).
- **Ledger:** L3, T2 and T3.
- **Accounts:** A1 and A2. `control_type` uses the fine-grained values.
- **Invoices:**
  - C4, subtotal only. The total formula is left for the service layer and CPA review.
  - C5.
  - C8 and decision 3, through `invoice_series`.
  - `ledger_side`.
- **Ledger keys:** C11 and X1, plus the reconciliation locks.
- **Data quality:** D1 (dates and flags) and D2 (`base_currency`, no FX).
- **Add-ons:** the `company_addon` and `addon_schema_version` tables.

The proof on copies also found that invoices could be inserted already past Draft, skipping every leave-Draft rule. 004 now rejects that.

**Moved to the Phase 2 service layer**, with strict expected-failure tests in `tests/test_service_rules_pending.py`:
- L2 (postable and active accounts) and decision 5 (controlled accounts);
- decision 6 (when approval is required);
- the remaining reversal check (date not before the original);
- C6 (over-allocation, and exactly one target);
- the logged reason for reopening a period;
- the numbering service;
- setting `period_id` from `entry_date`.

**Still open:**
- Timestamp format: `CURRENT_TIMESTAMP` writes `YYYY-MM-DD HH:MM:SS`, while `crm_pm_design.md` uses `YYYY-MM-DDTHH:MM:SSZ`. Decide before 005.
- `contract_line.change_order_id` has no FK until the canonical change-order table is chosen.
- X2 (indexes) and X3 (views, fiscal-year fields).
- C10 and X4 (service layer).
