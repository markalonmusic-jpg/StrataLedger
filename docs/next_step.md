# Next step: the consolidated baseline update, then Phase 2.5 Step 7 (plans for the owner's approval)

Written 2026-11-14 at the STOP after R55; updated 2026-11-15 with the owner's architecture and design rulings
(AQ1, AQ2, docs/design.md). Overwritten at each STOP (CLAUDE.md section 8).
Status: **R55 is final and committed. The 2026-11-15 rulings are recorded in CLAUDE.md and docs/design.md
(docs only). Neither the baseline update nor Step 7 is started; no code is written.**

**State:** suite **2745 passed, 7 deselected, 5 xfailed**. The baseline did not change, so no rebuild is needed.

## Order (owner, 2026-11-15; docs/roadmap.md "Target architecture and the consolidated baseline update")

1. **One consolidated pre-release baseline update** of `migrations/001_company.sql` and `001_master.sql`.
2. **Step 7** on the new baseline (plan below): `sequences.next_invoice_number` and `services/payments.py`
   allocations, closing the 5 xfails.

## Plan outline: the consolidated baseline update

To be detailed into a column-by-column plan and approved before any edit.
- Failing schema tests first, one test file per area (or the existing schema test file for that table).
- Save the current baselines to `archive/baseline_pre_<tag>/` with a git tag, as earlier steps did.
- One edit of both baselines, one rebuild (`python scripts/create_fresh_databases.py --apply`); the master and
  company development files hold no real data.
- Contents (docs/design.md section 10): `company_entity` and `journal_line.entity_id`; `journal_line.clearing_id`
  and the open-item account marker; document versions and the `Lock documents after posting` setting;
  `bank_statement_line` and its matches; pay run tables, `In pay run` and `contact.bank_payee_id`; service types,
  stages and triggers; estimate signing with the signed PDF; 3-level cost codes; dimension depth; Step 7's
  `payment_allocation` columns (part 3 below, including open questions 1 and 3).
- Existing tests that change with it: the dimension depth tests (tests/test_database.py,
  `MAX_DIMENSION_DEPTH = 3`) if the cap goes; the chain canonical form and its vectors
  (tests/data/ledger_chain_vectors.json) if `clearing_id` and `entity_id` are sealed.
- Needs the owner first: docs/design.md section 11 questions 1-4 and 7 (B9 vs `bank_payee_id`, `clearing_id`
  and the chain, dimension depth, service types vs `pipeline_stage`, cost code levels).

## Done this session: R55 final (owner, 2026-11-14, Conversion added)

- Conversion entries join Import and Payroll: `create_document_entry` saves them only with origin Import, so they
  always need one human review. post=True is refused for them, as R18 refuses it for Import origin. A System
  context is refused with "A conversion entry is saved by its importer (origin Import), so a person reviews it
  before it posts; save it as an import and send it for review."
- Typed opening balances (a future wizard, not built) use the same path: source Conversion, origin Import
  (`as_import`). The person who entered them may review them unless separation of duties is on (OFF by default).
  With it on, someone else approves and someone other than the creator posts (R17, R28).
- Tests: tests/test_ledger_rounding.py, section "R55 final". The static caller table needed no new row
  (`services/conversion.py` already may pass "Conversion"). The hand check script has no Conversion block, so it is
  unchanged.
- Reviews: 
  - step-reviewer: approve with changes, all fixed in 394c3a2: the post-on-save result is checked again (entry
    number, posted, chain verifies), the two separation denials are matched by their sentence, and the R54 body,
    audit design section 13, the ledger docstring and the status log are in step.
  - mutation-tester on 394c3a2: 16 mutants, 15 killed. The survivor ("A import entry") is killed by the exact
    sentence per source in `test_an_import_or_payroll_entry_comes_only_from_an_importer` (STOP commit).
  - secrets-auditor: not needed.
  - Reviewer note, behaviour from before this change (not changed): the R53 tests post an approved
    Import-origin entry with a System context; `post_journal_entry` refuses only an Import-origin context, while
    the ledger docstring says "Only a person posts an Import-origin entry". Open question 7.

## Step 7 plan

Step 7 closes Phase 2.5. It has four parts. Parts 1 and 2 need no baseline change; part 3 does.

### Part 1. The five strict xfails (tests/test_service_rules_pending.py)

Each xfail was written before the service layer, against a PROPOSED API (`conn`, `user_id=`). As in Step 4 (R25),
each is rewritten against the real service and its marker removed, or moved to the file that already covers it.

| xfail | What already exists | Step 7 work |
|---|---|---|
| Reopening a period needs a logged reason | **Covered.** `periods.reopen_period` needs `period.reopen`, confirm=True and a non-blank reason; the reason goes to `period_status_history`, which cannot be updated or deleted (tests/test_period_close.py, `test_reopen_needs_confirm_and_a_reason`, plus the year and "books closed through" variants). | Delete the xfail. The history rows already cannot be updated or deleted (tests/test_period_close.py around line 373). The xfail looks for the reason in `audit_log` on `fiscal_period`; the real design keeps it in `period_status_history`, which is the better record. No code. |
| Period set from the entry date | **Covered.** `ledger.create_entry` resolves `period_id` from `entry_date` (`periods.resolve_entry_period`; tests/test_ledger_drafts.py around line 284). | Delete the xfail. No code. |
| Numbering assigns the next number | Partly. The baseline has `invoice_series` (Invoice, Credit Memo), the gapless trigger `invoice_leave_draft` and R6 (the first send with no series creates "INV-" / "CM-"; not with `ph_tax`). No service assigns it. | Build the number assignment only: `sequences.next_invoice_number(conn, context, document_type)` inside the caller's write transaction (R6 default series, registered range and `valid_until` checked, gapless, `ph_tax` refuses a missing series). `billing.send_invoice` (posting the invoice) stays in Phase 4; the xfail is rewritten against the new function. |
| A payment cannot be over-allocated | No service. | Part 3. |
| An allocation names exactly one target | The `allocation_one_target` CHECK exists (tests/test_schema_ledger_2_5.py). No service. | Part 3: the service refuses it with a sentence before the CHECK is reached. |

### Part 2. The billing caller of create_document_entry

`DOCUMENT_ENTRY_CALLERS` lets `services/billing.py` pass "Invoice" and "Payment", and `services/payments.py` pass
"Payment". Two modules may make payment entries. Proposal: payments are made only by `services/payments.py`, so the
billing row shrinks to `{"Invoice"}` (allow-lists only shrink). Allocation itself writes no journal entry (the
payment's entry already moved AR or AP; an allocation is the subledger link), so Step 7 calls
`create_document_entry` from nowhere new. The test for the shrink is the static test itself.

### Part 3. Payment allocation (R7, B2, B4, B6, B14; roadmap "Baseline gaps", Step 7)

New module `services/payments.py` with `allocate(context, ...)` and `release_allocations(conn, context, ...)`
(called by a payment void later). Shape per rule 10: validate, `authorize`, then the write transaction.

**Baseline change (made in the consolidated baseline update above, not as a separate edit; it blocks every
existing development database until it is rebuilt with `scripts/create_fresh_databases.py --apply`):**
`payment_allocation` gains
- `applied_date TEXT NOT NULL` (B4, CB1: cash basis recognizes revenue on the date applied; the closed-period check
  uses it);
- `credit_memo_id INTEGER REFERENCES invoice(invoice_id)`: the credit memo applied (B6), with a CHECK that exactly
  one source is set, `payment_id` or `credit_memo_id` (`payment_id` is already nullable);
- `created_by` and `created_at` (who applied it; services set them, H2);
- possibly `released_at`, `released_by`, `release_reason` (see open question 3).
The `allocation_one_target` CHECK stays as it is (invoice or deferral): a credit memo is a source, not a target,
so B6 needs no new target. The loan target waits for the loans step (roadmap). The change is written with failing
schema tests first (tests/test_schema_ledger_2_5.py).

**Rules the service enforces (tests first; these are integrity point 4 of the payments message):**
1. Never more than the document's open amount (total minus retainage minus live allocations, B2) and never more
   than the source's unapplied amount (the payment's amount, or the credit memo's total, minus its live
   allocations). The first xfail.
2. Exactly one target (the second xfail) and exactly one source, each refused with a sentence.
3. Same contact only; a Received payment or a sales credit memo to a Sales invoice; a Made payment or a vendor
   credit to a Bill (R7 opened the vendor side).
4. The target and the source are posted and not void; the target is not Draft, Void or Paid.
5. `applied_date` is on or after both the source's and the target's dates and in an open period (the closed-period
   integrity rule). A credit-only application carries its own date.
6. The invoice is marked Paid when its net due reaches zero (B2), in the same transaction.
7. Allocations of a posted source are never edited or deleted (the triggers exist for payments; they extend to
   credit memos); voiding the payment or credit memo releases its allocations and reopens the invoices (B14,
   "reversing a payment reverses its allocations"). The void itself is Phase 4; Step 7 builds and tests the
   release function and its trigger guard.
8. Permissions: a new `payment.allocate` (or the existing receive/pay permission; open question 4); Agent never
   (the AI does not move money, section 0).

### Part 4. Close Phase 2.5

Roadmap 2.5 marked done, status log entry, the hand check script for Step 7, step-reviewer, mutation-tester.

## The payments schema message (2026-11-14, product_consultant, forwarded from ux_audit)

Checked against migrations/001_company.sql. "Later" names the step in docs/roadmap.md.

| Item | Baseline today | Where |
|---|---|---|
| `date_paid` on every payment (the posting date) | **Already there** as `payment.payment_date` (NOT NULL, a date). Rename only if the owner wants the UI word in the schema. | Already in the baseline |
| `date_cleared` (nullable; set on match or tick, cleared on unmatch, logged) | Not there. Reconciliation today marks `journal_line.recon_id`. | Later: Phase 4 bank reconciliation and feeds (baseline change then) |
| Many-to-many matching of feed lines and payments ("partly cleared") | Not there (`bank_statement_line` and a match table do not exist; already listed as Phase 4 gaps). | Later: Phase 4 |
| A feed line with no payment creates the payment on match | Not there. | Later: Phase 4 (an Import-origin payment through `create_document_entry`) |
| Pay Bills single-vendor; Pay Run adds "Approved to pay" (posts nothing) | `invoice.status` has no "Approved to pay"; no run table. | Later: the bills and payments screens (Phase 3/4); open question 2 |
| Open payments (date_cleared null) and two settings (open too long 30 days, stale check 180 days) | Not there (needs `date_cleared`; the two settings are not in `company_settings`). | Later: Phase 4, with `date_cleared` |
| Credit memos as negative invoices, CM-### gapless at posting, integer primary key | **Mostly there.** `invoice.invoice_type` has 'Credit Memo', `invoice_series.document_type` has 'Credit Memo', R6 gives "CM-", numbers are gapless at leaving Draft, the key is an integer. Difference: amounts are stored positive (`invoice_amounts_positive`), the type gives the sign. Report, not changed (section 5.3). | Already in the baseline; the number assignment is built in Step 7 part 1 |
| Vendor credits as negative bills, numbered the same way | **Conflict.** A Purchase-side 'Credit Memo' row is allowed, but a CHECK forbids a series on the Purchase side and decision 1.3 gives bills voucher numbers with gaps allowed, not a gapless series. | Owner decision (open question 5); later: bills step |
| Receive Payment / Pay Bills list invoices, credit memos and unapplied payments; allocation rows link payment to invoice and credit memo to invoice | Partly: `payment_allocation` links a payment to an invoice or deferral; no credit-memo source and no apply date. | **Step 7 (baseline change, part 3)** |
| A $0.00 payment that only applies credits | **Refused today** by `payment_amount_positive` (`amount_cents > 0`). | Step 7 if the owner keeps the $0.00 payment record (open question 1); not needed if a credit-only application is allocation rows with their own date |
| Unapplied amounts stay on the payment, applied through the same rows | **There by derivation**: unapplied = `payment.amount_cents` minus its allocations. Needs `applied_date` to apply later. | Step 7 (the `applied_date` column) |
| Undeposited funds vs matching | `company_settings.undeposited_funds_acct_id` and the 'Undeposited funds' control type exist (decision 1.2, B3: optional). | Open question 6 |

**Its six integrity points:**
1. Unmatching or unticking an item in a finished reconciliation reopens it with a reason. Later (Phase 4; today
   `journal_line_recon_lock` refuses any change to a completed reconciliation, and B10 allows undoing only the
   latest).
2. `date_cleared` does not change the period, can be set in a closed period, and is logged. Later (Phase 4).
3. A payment created from a feed line is Import origin; the human match is its review; the assistant proposes,
   never confirms. Later (Phase 4). R18/R55 already give the path: origin Import always needs one review.
4. Allocations: never over the open amount or the payment and credits; same customer or vendor; reversing a
   payment reverses its allocations; a credit-only application has its own date and passes the closed-period
   check. **Step 7 must enforce all of these** (part 3, rules 1, 3, 5 and 7).
5. Cash basis: a credit memo applied with no cash. A report rule (Phase 4 reports). Step 7 only keeps what the
   report needs: the source kind and `applied_date` on each allocation.
6. Vendor credits keep the vendor's own number in a separate field. Already there: `invoice.invoice_number` (unique
   per vendor) is the vendor's number; the internal number is open question 5. Later (bills step).

## Open questions for the owner

1. **$0.00 payments.** Keep a $0.00 payment record for a credit-only application (the baseline CHECK becomes
   `amount_cents >= 0`, and a $0.00 payment posts no entry), or record a credit-only application as allocation rows
   from the credit memo with their own date and show it on screen as a $0.00 payment (no CHECK change)?
   Recommendation: the second; one less record that posts nothing.
2. **Which Pay screen is multi-vendor** (Pay Bills single-vendor vs a multi-vendor Pay Run). The 2026-11-15
   design describes a two-step Pay Run across approved bills (docs/design.md section 6); confirm that this
   answers it. Not needed for Step 7.
3. **Releasing allocations.** Today the baseline lets a voided payment's allocation rows be deleted (logged). Keep
   that, or keep the rows and mark them released (who, when, why), so the history shows what was applied and
   undone? Recommendation: mark them released; corrections stay visible. Decides two or three columns in the
   Step 7 baseline change.
4. **Permission for allocating.** Reuse the receive/pay permissions (the ux_research note lists "Receive payments"
   and "Pay bills" as team permissions) or add `payment.allocate`?
5. **Vendor credit numbering.** Decision 1.3 gives bills voucher numbers with gaps allowed; the message asks for a
   gapless internal series for vendor credits like CM-###. Which wins? Not needed for Step 7.
6. **Undeposited funds vs matching.** Not decided here. Not needed for Step 7.
7. **Who may post a reviewed import.** Should `post_journal_entry` also refuse a System context for an
   Import-origin entry, so that only a Human context posts it, as the ledger docstring says? Today only an
   Import context is refused. Small, and it could go into Step 7 with a test.

**Note on questions 2 and 6:** C:\Users\marka\Strata_Teams\inbox\to_planning.md holds two later messages
(2026-11-14, from ux_research) that say the owner decided both: keep Undeposited funds for checks and cash (ACH,
wire and card post straight to the bank), and a multi-vendor Pay Run with a release approval. The task for this
session said they are not decided, so they stay open here. Please confirm which is current.

## Carried forward

- Phase 3 screens:
  - show the unverified range and the close check's warning;
  - after a key replacement, call `App.start_key_store()` again;
  - show `KeyReplaced.recovery_code` once;
  - every post, approval, close, void and correction passes `self.app.action_context()` (the static test
    enforces it for posts, approvals and closes; extend it to void and reverse when the screen is built);
  - show `display_description` for entries;
  - log an error by passing the error object, never its text (R30, static test);
  - show `SaveFailedError` like any service error (its sentence only);
  - the import review screen shows the rounding line's note (L8 "info flag"); `get_entry` returns the flag.
- Backlog 21: the control "voids and corrections need a second person" (R42), off by default, listed on the
  Audit-ready page. Not built.
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` remains the one allowed clock read in services (H2).
- Bills have no column for their VCH voucher number (decision 1.3; `voucher_sequence` exists). Noticed while
  checking the message; for the bills step.
