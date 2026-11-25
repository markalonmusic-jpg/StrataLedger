# Step 2.9 schema replan, area 2: pay run

Status: **Approved by the owner 2026-11-23 11:40 PM (planning chat), as of commit c0780e2, with two fixes recorded in §10.**
Drafted 2026-11-23; owner answers to Q1–Q3 (2026-11-23 7:55 PM) folded the same day. Docs only: nothing here changes code, a baseline, a migration or a
test. Everything below is built only in the 2.9 baseline pass, after the whole replan is approved. Items marked
PROPOSED are not decided. Bills, vendor credits, terms, holds, waivers and vendors are Area 3
(`area_3_bills_vendor_credits_terms_subcontracts.md`); this area is how they are paid.

Sources read (searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`: row 2 and its sources; "Inbox inputs" for Area 2 (PAYRUN-01 to
  PAYRUN-04) and the Area 3 inputs that hand to Area 2 (VENDOR-02 payment method, TERM-04, VCR reservation).
- `Strata_Teams\docs\owner_decisions_2026-11-22.md`: items 14, 16; OD-19, OD-24, OD-25, OD-26, OD-66, OD-67.
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 53, 71 and 148 (inputs; later decisions win: 53 is
  superseded by 71 and the 2026-11-18 10:03 PM decision).
- `docs/next_step.md` Area 2 line (items 14 and 16 through Area 3), now pointing here.
- Approved areas: Area 1 inputs in next_step (allocations, operation IDs, locks); Area 12 (Date cleared, open
  payments, unmatch); Area 13 §1.4 (Bill payments); Area 18 §§2, 8.1 (item 11 stored control account), 8.6.
- `migrations/001_company.sql`: `pay_run` :3992, `pay_run_line` :4005 with its two triggers, `payment` :670,
  `payment_allocation` :316, `bank_account` :1332, `document_approval_setting` :1269 ('Pay run', 'Payment'),
  permissions `payment.make`, `payment.approve` (sensitive) :1208–1209. `payments.py` allocates sources to targets;
  there is no pay run service.

**Checked against: shared_decisions 2026-11-14 12:05 PM (payments model: Date paid and Date cleared), 2:55 PM (pay
run: bank details on file, cash after the run, remittances), 11:15 PM (flat list and Voucher #), 11:25 PM (layout),
11:44 PM (lifecycle: approval posts nothing; each line posts on Date paid; stuck runs; ACH not debited); 2026-11-15
12:03 AM (reached from Bills); 2026-11-17 10:44 AM (holds and the waiver gate), 12:10 PM (who may hold); 2026-11-18
9:18 PM and 9:20 PM (unmatch), 10:03 PM (the pay run is the only way to pay bills), 10:24 PM (OK to pay);
2026-11-20 5:15 PM (single active claim and retry). Latest entry read: 2026-11-22 2:25 AM. Owner answers in
`owner_decisions_2026-11-22.md`: Area 2 Q1–Q3, 2026-11-23 7:55 PM; Area 3 Q3, 7:40 PM.**

---

## 0. Summary

| # | Item | Proposal in one line | Baseline |
|---|------|----------------------|----------|
| 1 | Run and lifecycle | Draft → (Submitted, when approval is on) → Approved (bills "In pay run") → Completed, or Cancelled; return to draft with a reason; approval posts nothing | company |
| 2 | Lines, credits and discounts | a line per bill with apply, editable discount and credit uses; vendor credits as their own linked rows; cash = apply − discount − credits; one open line per bill | company |
| 3 | Recording | each line (or a batch) records Date paid and the method's reference; that is when the payment posts, Dr AP (the bill's stored AP account) / Cr the funding bank (a Card line: the chosen card account, §10) / Cr discount; retry-safe | company |
| 4 | Checks at approval and recording | holds, approval, compliance (a warning; a hold only with its control ON), waivers, usable credit, already paid or in another run, locks; changed bills are removed and named; a negative funding balance warns only (Q3) | company |
| 5 | After recording | remittance, Date cleared from the bank feed, void of a recorded payment (bills payable again, Q2), stuck-run and ACH-not-debited alerts | company |

---

## 1. Run and lifecycle

### 1.1 Current state

`pay_run` (`:3992`): `run_number` UNIQUE, `bank_account_id` NOT NULL (FK `bank_account`), `status` IN ('Draft',
'Approved', 'Completed', 'Cancelled'), `scheduled_date`, `memo`, created and approved who/when. No submitted state,
no return-to-draft or cancel reason, no row version. `document_approval_setting` has 'Pay run' (OFF).

### 1.2 Decided

| Decision | Source |
|----------|--------|
| Bills are paid only through a pay run; Pay bill opens a draft run filtered to that bill's vendor with only that bill ticked at its open amount (other bills and credits listed unticked); Bills > Pay run opens an unfiltered batch | S 11-18 10:03 PM |
| Approving posts nothing; the chosen bills show "In pay run" with the run date and are locked to the run until recorded or taken out | S 11-14 11:44 PM; C71 |
| "Approve run" is the button when release approval is off; "Submit run for approval" when it is on | S 11-14 2:55 PM; C71 |
| Return to draft and Cancel run each ask for a reason; the bills return to Approved; logged | C71 |
| Unfinished runs warn after N days (default 3) and can be cancelled or returned to draft | S 11-14 11:44 PM |
| The run shows cash after this run and cash available after everything open (Card lines excluded, §10 fix 1) | S 11-14 2:55 PM; C71 |
| Pay run layout B: the first row has no empty slot; Date cleared moves up into row 1 | OD-19 B (screen only) |

### 1.3 Proposed schema

`pay_run` changes:

| Column | Change |
|--------|--------|
| `run_number` | 'PR-####' from a new `pay_run_sequence` (one row, like `voucher_sequence`); gaps allowed (lead default) |
| `status` | CHECK IN ('Draft', 'Submitted', 'Approved', 'Completed', 'Cancelled'); 'Submitted' only when 'Pay run' approval is ON (Area 14 routes it; `approval_request_id` INTEGER) |
| `bank_account_id` | kept: the funding account; every line posts its bank credit to it (PAYRUN-02) |
| `due_within_days`, `vendor_filter_id`, `job_filter_id` | the saved filters (PAYRUN-03: choices survive filter changes) |
| `returned_reason`, `cancelled_reason` | TEXT, length(trim) >= 10 when set (OD-31); with `*_by`, `*_at` |
| `completed_at` | set when the last open line is recorded or taken out |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

`company_settings.pay_run_stuck_days` INTEGER NOT NULL DEFAULT 3 (a setting, not a control).

### 1.4 Tests

`test_payrun_approval_posts_no_ledger_entries`, `test_payrun_pay_bill_entry_opens_vendor_filtered_draft_with_one_bill`,
`test_payrun_submit_only_when_payrun_approval_on`, `test_payrun_return_to_draft_and_cancel_need_reason_and_free_bills`,
`test_payrun_stuck_after_setting_days_raises_attention`, `test_payrun_number_from_sequence`.

---

## 2. Lines, vendor credits and discounts

### 2.1 Current state

`pay_run_line` (`:4005`): `invoice_id` NOT NULL (a bill, enforced by two triggers), `amount_cents` > 0, `status` IN
('Open', 'Paid', 'Removed'), `date_paid`, `payment_ref`, `payment_id`, completed who/when, UNIQUE (`pay_run_id`,
`invoice_id`), and a CHECK that 'Paid' has a payment, date and reference. No discount, no credit link, no rule that
a bill is in only one open run.

### 2.2 Decided

| Decision | Source |
|----------|--------|
| A flat bill list (Vendor · Voucher # · Bill # · Job · Due · Original · Open · Apply); ticking fills Apply with the open balance (payable now when retainage is held), editable for a partial payment | S 11-14 11:15 PM; C71 |
| Vendor credits are their own rows; credit applications stay separate from cash: a $100.00 bill can be settled by $80.00 cash plus a $20.00 credit, $0.00 left, $80.00 out of the bank | PAYRUN-04 (inbox input) |
| A refund request's hold: bills and pay runs see only the unheld remainder; usable = open credit − held | item 14; OD-67 B |
| The early-payment discount on the line is an editable amount, defaulting to the calculated amount (pro rata for a partial payment), changeable to $0 | item 16 |
| Compare the pay run's Date paid with the discount deadline (inclusive); if it has expired by recording, the line returns for review at the full amount | OD-24 A; item 16 |
| Total to pay is net of the discount | OD-25 A |
| Held bills show a lock instead of a checkbox and cannot be paid; a bill already in a run links to that run | S 11-18 10:03 PM; C71 |

### 2.3 Proposed schema

**`pay_run_line`** (one per bill in the run):

| Column | Type and constraint |
|--------|---------------------|
| `apply_cents` | renamed from `amount_cents`: the reduction of the bill's open balance; INTEGER > 0; ≤ the bill's open payable-now balance (service, at save and again at recording) |
| `discount_cents` | INTEGER NOT NULL DEFAULT 0 CHECK (>= 0 AND <= `apply_cents`); defaults to the calculated discount (Area 3 §5.3), editable |
| `discount_calculated_cents` | INTEGER NOT NULL DEFAULT 0 (what the term gave; kept beside the edited amount for review) |
| `status` | CHECK IN ('Open', 'Needs review', 'Paid', 'Removed'); 'Needs review' when the discount expired before recording (item 16) |
| `removed_reason` | TEXT, length(trim) >= 10 when status is 'Removed' |
| `method` | TEXT CHECK IN ('Check', 'ACH', 'Wire', 'Card', 'Paid outside'); defaults from the vendor's `default_payment_method` (Area 3 §1.3), else the run's default; ACH and Wire only when the vendor has bank details on file (C71) |
| `payment_ref` | kept: the check number or ACH/wire reference, required by method at recording (PAYRUN-04) |
| `operation_id` | TEXT UNIQUE (set at recording; a retry with the same ID returns the first result, S 11-20 5:15 PM) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

Indexes: a partial unique index on (`invoice_id`) WHERE `status` IN ('Open', 'Needs review'), so a bill is ticked in
at most one run that is not completed or cancelled, Draft runs included (the Pay bill entry links to that run,
S 11-18 10:03 PM); the existing UNIQUE (`pay_run_id`, `invoice_id`). The bill shows "In pay run" only while the run
is Approved (Area 3 §3.3). Return to draft keeps the lines Open in the Draft run (the bills show Approved again);
Cancel run sets every Open or Needs review line to 'Removed' with the run's cancel reason, freeing the bills.

**`pay_run_credit`** (a vendor credit used on a bill in the run; PAYRUN-04):

| Column | Type and constraint |
|--------|---------------------|
| `credit_use_id` | INTEGER PRIMARY KEY |
| `pay_run_line_id` | INTEGER NOT NULL REFERENCES pay_run_line (the bill it settles) |
| `credit_invoice_id` | INTEGER NOT NULL REFERENCES invoice (a purchase credit memo of the same vendor; service check) |
| `amount_cents` | INTEGER NOT NULL > 0; ≤ the credit's usable amount (open − held, Area 3 §6.3), checked again in the recording transaction |
| `allocation_id` | INTEGER UNIQUE REFERENCES payment_allocation (set at recording: the zero-cash credit application) |

Cash for a line = `apply_cents` − `discount_cents` − Σ its `pay_run_credit.amount_cents`; the service refuses a
negative cash amount (a credit larger than the bill is split across bills instead). The run's Total to pay is the sum
of cash (OD-25).

### 2.4 Tests

`test_payrun_rows_validate_amount_sign_open_balance_and_vendor_before_total`,
`test_payrun_partial_and_unticked_choices_survive_due_date_filter_changes`,
`test_payrun_selected_rows_outside_due_date_filter_are_disclosed_before_approval`,
`test_payrun_vendor_credit_selection_links_separately_and_nets_cash` ($100.00 bill = $80.00 cash + $20.00 credit),
`test_payrun_sees_only_usable_credit_open_minus_held` (VC-031 usable $0.00 at ($250.00) open),
`test_payrun_bill_in_one_open_run_only`, `test_payrun_discount_defaults_pro_rata_and_is_editable_to_zero`,
`test_payrun_total_to_pay_is_net_of_discount_and_credits`.

---

## 3. Recording a line: the payment posts

### 3.1 Decided

- Each line is completed, singly or in a batch, by entering Date paid and the ACH reference or check number; that is
  when the payment posts (Date paid = posting date and period). Date cleared comes later from the bank feed
  (S 11-14 11:44 PM, 12:05 PM). Recorded lines are read-only and link to their payment (C71).
- The posting preview for a discounted line: AP debit (full amount), bank credit (net), Purchase discounts credit
  (discount) (OD-25 A); for a job-coded bill the discount credits the bill's job cost line instead (OD-66 B).
- Settlement uses the account the bill posted to (Area 18 §8.1, item 11), never the current role.

### 3.2 Proposed rules

- **One payment per recording group (Q1 A, Decided 2026-11-23, owner 7:55 PM).** Lines of the same vendor
  recorded together with the same Date paid, method and reference make one `payment` row (one check stub listing
  the bills, one bank line to match) with one allocation per bill; lines recorded separately make separate payments.
  Example: 3 bills paid 11/28 by check #1042 are one $9,600.00 payment. `payment` gains `pay_run_id` INTEGER REFERENCES pay_run and `reference`
  TEXT; Date cleared is not a `payment` column: it is read from Area 12's `bank_line_clearing` on the payment's bank
  journal line (Area 12 Q1 A). `method` CHECK extends to ('Check', 'ACH', 'Wire', 'Card',
  'Paid outside', 'Cash', 'Bank Transfer', 'GCash', 'Maya') (the last three kept for the PH add-on). **(Refined 2026-11-24, owner 2026-11-24 8:55 PM, Q6: the CHECK is replaced by the company-editable `payment_method` list; Area 1 §1.3)**
- **Posting (one entry per payment, through `ledger.create_document_entry`):** Dr each bill's stored AP account,
  vendor and clearing group for cash plus discount (`apply_cents` less the line's credit uses); Cr the run's funding
  bank account (cash) **(for a Card line: the chosen credit card account, §10 fix 1, owner 11:40 PM)**; Cr the discount (Area 3 §5.3: the job cost line or `purchase_discounts`). Example: a $1,000.00
  bill with a $20.00 discount and a $100.00 credit: Dr AP $900.00, Cr bank $880.00, Cr discount $20.00, and the
  credit's $100.00 application settles the rest. Allocations: the payment's `payment_allocation` row carries the
  cash ($880.00) in `amount_applied_cents` and the discount in a new `discount_cents` column ($20.00, INTEGER NOT
  NULL DEFAULT 0, >= 0), posted in the payment's own entry; the credit's allocation carries $100.00. A bill's open
  balance = total − Σ (applied + discount) − Σ credit applications, from posted allocations (Area 1 rules). Credit uses post their zero-cash applications through
  `payments.allocate` (source = the credit memo, target = the bill) in the same transaction (R58 application
  entries). All lines of the group post, or none.
- **Method references:** Check needs a check number unique per funding account among recorded, not voided payments
  **("among recorded, not voided" Withdrawn 2026-11-23, owner 11:40 PM: unique across all payments, voided included;
  §10 fix 2)** (error state "check number already used", C71); ACH and Wire need a reference; Card needs the card account
  reference; Paid outside needs a note (at least 10 characters). Checks can be numbered up from a starting number
  for a batch (C71).
- **Retry:** recording with the same `operation_id` returns the first result and posts nothing more (PAYRUN-01).
- **Bill status** after recording: Paid when the open balance is zero, otherwise Partly paid, from posted
  allocations effective on or before the as-of date (Area 1 input).
- **Completion message** is built from the saved results ("6 of 8 completed · $5,360.00 still to record"), never
  from the screen (PAYRUN-01).

### 3.3 Tests

`test_payrun_record_ready_line_posts_payment_on_date_paid_and_leaves_other_pending`,
`test_payrun_reload_and_retry_do_not_duplicate_payment_or_posting`, `test_payrun_completion_message_comes_from_saved_results`,
`test_payrun_date_paid_and_date_cleared_are_distinct`,
`test_payrun_funding_account_drives_cash_estimate_preview_and_posted_bank_credit` (1010 and 1020),
`test_payrun_requires_real_date_paid_and_method_specific_reference`, `test_payrun_check_number_unique_per_funding_account`,
`test_payrun_group_of_same_vendor_lines_makes_one_payment_with_one_allocation_per_bill`,
`test_payrun_discount_posts_to_job_cost_line_or_purchase_discounts`,
`test_payrun_settles_on_bill_stored_ap_account_after_role_reassignment`.

---

## 4. Checks at approval and at recording

Decided: approval re-reads every bill in the run on the server and refuses or removes changed ones, never trusting
the client list; a changed bill is listed with who, what and when ("VCH-1022 was held at 3:14 PM on 11/17/2026 by
Dana Reyes (Dispute: …); it will be taken out of this run."), the totals are worked out again, and Approve is
disabled when no bills are left (C148, re-test passed 11/17). Recording rechecks bill eligibility and Area 13's
locks (PAYRUN-04).

One function, `pay_runs.check_lines(conn, run, as_of)`, runs at approval and again inside each recording
transaction. A line fails when its bill:
- is not Approved (OK to pay = approved and not held, S 11-18 10:24 PM), or is held (`bill_hold` open, Area 3 §3.3);
- has a compliance hold with no override for that bill, **only while `vendor_compliance_hold` is ON** (Area 3 §2.2,
  §2.3; Q3 there, Decided 2026-11-23, owner 7:40 PM). With it OFF (the default) a missing or expired document shows
  "Missing documents: <list>" on the line and the line pays;
- fails the waiver gate when `require_lien_waivers_before_paying` is ON (Area 3 §4.3; also checked when the line is
  added, so the bill cannot be ticked); with it OFF a missing waiver warns and an audit event "Paid without waiver"
  is written on recording (no reason asked);
- is already paid, voided, or in another open run;
- would be paid above its open payable-now balance, or uses more credit than is usable;
- or when the Date paid period or the "Bill payments" area or an AP or bank account it touches is locked (Area 13
  §1.4; refused, never moved to another date).

At approval a failed line is taken out (status 'Removed', reason written by the service, logged) and named; at
recording a failed line is refused with the one-sentence reason and the other lines of a batch are not posted with
it (the group is all or nothing, §3.2). An expired discount at recording sets 'Needs review' (item 16) instead.

**Funding balance (Q3 A, Decided 2026-11-23, owner 7:55 PM):** a run that would take the funding account below
zero shows a warning only and can still be approved and recorded; there is no refuse control. Example: Operating
holds $20,000.00 and the run is $26,500.00: "This run leaves Operating at -$6,500.00." (Card lines are not counted,
§10 fix 1.) Test:
`test_payrun_negative_funding_balance_warns_and_still_approves`.

Tests: `test_payrun_recording_rechecks_bill_eligibility_and_area13_locks`,
`test_payrun_approval_rereads_bills_and_removes_changed_ones_with_who_what_when`,
`test_payrun_held_or_unapproved_bill_is_refused`, `test_payrun_compliance_hold_refused_without_override_when_control_on`,
`test_payrun_missing_documents_warn_and_pay_when_control_off`,
`test_payrun_waiver_gate_only_when_control_on_and_logs_paid_without_waiver`,
`test_payrun_discount_expired_at_recording_returns_line_for_review_full_amount` (deadline day passes; one day later
returns).

---

## 5. After recording

- **Remittance:** after a line is recorded: Save PDF, Print, Mark as sent; email only when a mailbox is set up
  (Area 20; S 11-14 2:55 PM).
- **Date cleared** is written by the bank feed match or reconciliation (Area 12); a cleared payment can be unmatched
  there (S 11-18 9:18/9:20 PM). Completed ACH payments with no bank debit after 5 bank days are flagged in Open
  payments (S 11-14 11:44 PM; Area 12's module).
- **Taking a line out before recording:** "Take selected out of the run" with a reason; the bill returns to
  Approved (C71).
- **Voiding a recorded payment** (bank rejection, lost check; Q2 A, Decided 2026-11-23, owner 7:55 PM): with a
  reason (at least 10 typed characters, or a listed reason, Area 18 §8.7), the payment's entry is reversed (Dr bank /
  Cr AP, and the discount credit reversed with it), its allocations and credit uses are released, and its bills
  return to unpaid: Approved, or Open when 'Bill' approval is off, ready for a later pay run. They do **not** go
  back into the original run, which keeps the voided line in its history. **Reversal date (Area 10 Q21 A with OD-71,
  decided 2026-11-23 8:05 PM; Area 10 §11.7):** the original Date paid when its period is open and not locked,
  otherwise today (the void date); the user may change it, never into a closed or locked period. A payment matched to a bank line is unmatched first in Area 12 (lead default, owner
  may revise). Example: check #1042 lost in the mail and voided: its 3 bills are payable again.
- **Bank file:** the bank's ACH or positive-pay upload cannot be a NACHA file, because no bank account numbers are
  stored (RP1; S 11-14 2:55 PM left the format to planning). Proposal: a CSV pay list keyed by each vendor's
  `bank_payee_id` for the bank's own payee-based upload, plus a positive-pay check list; files go through
  `storage.py` and are kept with their hash. The exact column layout waits for a bank's sample (O1).

Tests: `test_payrun_take_out_needs_reason_and_returns_bill_to_approved`,
`test_void_recorded_payment_reverses_and_returns_bills_to_approved_not_to_run`,
`test_void_reversal_date_follows_area10_date_rule_and_never_a_locked_period`,
`test_payrun_bank_file_uses_payee_ids_and_stores_no_account_numbers`.

## 6. Locks, permissions, controls, row version and audit

- **Locks:** "Bill payments" area and every account a payment line touches (Area 13 §1.4 table: "pay run (area 2) |
  Bill payments | every line"), at recording and at void.
- **Permissions:** `payment.make` (build, approve when 'Pay run' approval is OFF, record, take out), `payment.approve`
  (sensitive; approve a submitted run when approval is ON; with separation of duties on, not the submitter),
  `ap.view`. PROPOSED: `payment.void` (void a recorded payment; sensitive) **(Withdrawn 2026-11-24, owner 2026-11-24 8:55 PM, Q7: no separate void permission; Area 1 §4)**, placed by an Area 18 amendment when
  approved. None is in `AGENT_ALLOWED`: the agent never approves or records (CLAUDE.md section 0).
- **Controls:** 'Pay run' approval (existing toggle, OFF); `require_lien_waivers_before_paying` and
  `vendor_compliance_hold` (Area 3, both OFF); no funding-balance control (Q3);
  `pay_run_stuck_days` is a setting.
- **Reasons:** at least 10 characters (OD-31).
- **Row version:** `pay_run`, `pay_run_line`; stale saves refused.
- **Audit:** insert and update triggers exist for `pay_run` and `pay_run_line` (`:4869`, `:4948`); add
  `pay_run_credit`, with Area 18 §1 before/after detail.

## 7. Conflicts with decisions or the baseline (flagged)

- **F1** `pay_run_line.amount_cents > 0` on bills only: kept for bills (as `apply_cents`); credits move to
  `pay_run_credit` rather than negative lines (PAYRUN-04 asks Area 2 to define this).
- **F2** `payment.method` CHECK lacks ACH, Wire, Card and Paid outside (§3.2).
- **F3** C53's `pay_run_vendor` (one payment per vendor per run) is superseded by C71's per-line recording; Q1
  decides how lines group into payments.
- **F4** C53's "Mark released by bank" posting is superseded by S 11-14 11:44 PM (each line posts on Date paid).

## 8. Questions for Mark (business rules only; recommended option first)

- **Q1. How recorded lines become payments.** **Answered 2026-11-23 (owner 7:55 PM): A (§3.2).**
  A (recommended): lines of one vendor recorded together with the same Date paid, method and reference are one
  payment (one check or bank debit) applied to each bill; lines recorded separately are separate payments. Example:
  three Pacific Coast Electric bills recorded with check 10452 on 11/20 make one $5,360.00 payment.
  B: every bill line is its own payment, even on one check.
- **Q2. Voiding a recorded payment from a run.** **Answered 2026-11-23 (owner 7:55 PM): A; reversal date aligned with
  Area 10 §2.4 (§5).**
  A (recommended): void with a reason (at least 10 characters): a reversing entry on the void date (open period),
  its allocations are released, and its bills return to Approved, not into the run; the run keeps the voided line in
  its history. Example: check 10452 is lost; voiding it reopens the three bills for the next run.
  B: voiding puts the bills back into the same run as open lines.
- **Q3. Funding account would go below zero.** **Answered 2026-11-23 (owner 7:55 PM): A, warn only (§4).**
  A (recommended): warn only: "1010 after this run" shows the negative amount in red and approval asks to confirm;
  never blocked. Example: 1010 holds $4,200.00 and the run is $5,360.00.
  B: add a Company control (OFF) that refuses approval when the book balance after the run is below zero.

## 9. Open items (not decisions)

- **O1 (Area 20 or the bank connection):** the bank's payee-ID upload layout and the positive-pay format.
- **O2 (Area 1):** **(Answered 2026-11-24: Area 1 §3 and §1.4; a card fee is an optional fee on a receipt only, payments made carry none.)** shared allocation rules (operation IDs, posted-only status as of a date, release fields) used by
  §3.2; card fees if a card payment carries one.
- **O3 (Area 12):** Open payments (uncleared and unmatched) and the 5-bank-day ACH flag.
- **O4 (Area 14):** routing for a submitted run and separation of duties.
- **O5 (Area 17):** cash requirements and the pay run register reports.

## 10. Owner approval 2026-11-23 11:40 PM: two fixes (dated amendments)

Source: `Strata_Teams\docs\owner_decisions_2026-11-22.md`, "Owner approval of Area 2, pay run".

- **Fix 1, card posting (Amendment 2026-11-23).** A line recorded with method **Card** credits the chosen **credit
  card account** (a liability; a card `bank_account` row, Area 12), not the run's funding bank account. The line
  names it in a new `pay_run_line.card_account_id` INTEGER REFERENCES bank_account (required when `method` = 'Card'
  and NULL otherwise, CHECK; the service checks it is a card account), copied to the payment. Card lines are
  excluded from "cash after this run" and from the negative-funding-balance warning (§4). Example: a $500.00 bill
  paid by card: Dr AP $500.00 / Cr 2100 card account $500.00; Operating unchanged. The lock check (Area 13 §1.4)
  covers the card account the line touches. Tests: `test_card_line_credits_chosen_card_account_not_funding_bank`,
  `test_card_lines_excluded_from_cash_after_run_and_negative_balance_warning`,
  `test_card_line_requires_card_account`.
- **Fix 2, check numbers are never reused (Amendment 2026-11-23).** A check number is unique per funding account
  across **all** payments, voided ones included: a UNIQUE index on (`bank_account_id`, `check_number`) for
  method 'Check'. A voided check stays in the register; the reissue takes the next number. Example: #1042 voided
  (lost in the mail), so the reissue is #1043. Replaces §3.2's "unique among recorded, not voided payments" (marked
  withdrawn there). Test: `test_check_number_unique_per_funding_account_including_voided`.

## 11. Pointers from Area 1 (2026-11-24, owner 2026-11-24 8:55 PM; pointers only)

- **Voiding a recorded payment (§5):** no `payment.void` (Withdrawn above); whoever holds `payment.make` may void with
  a reason (a listed reason such as "Not cleared" or "NSF", or Other with 10 typed characters). A cleared or
  reconciled payment goes through Area 12's bank correction first (the §5 sentence on unmatching stands). The reversal
  date rule stays Area 10's. Area 1 §4.
- **Method list (§2.3, §3.2):** `pay_run_line.method` and `payment.method` take their values from the
  `payment_method` list table (kinds Check, ACH, Wire, Card, Paid outside, Cash, Bank transfer, Other); a method's
  kind keeps §3.2's reference rules (a Check number unique across all payments, an ACH or Wire reference, the Card
  account). Area 3's `vendor.default_payment_method` follows the same list. Area 1 §1.3.
- **Shared columns (§3.2):** `payment.reference` and `payment.pay_run_id` are one column each, listed in Area 1 §1.3;
  `payment_allocation` gains `discount_cents` (§3.2), `operation_id` and the release fields (Area 1 §3.3).
- **Locks:** unchanged; Bill payments and every account a line touches (Area 1 §6).

- **Amendment 2026-11-24 (pointer, Area 14): O4 answered.** The 'Pay run' row routes the submitted run through the
  one approval mechanism (Area 14 §3, §5.1): `pay_run.approval_request_id` points to `approval_request`; approving
  runs `pay_runs.check_lines` again; approval posts nothing, so the period-lock check at approval does not apply to
  it (Area 14 §6). Separation of duties follows "Require a separate approver" (OFF), with the Area 14 §8 fallback.

- **Amendment 2026-11-25 (pointer, Area 20): remittance email.** After a line is recorded, the email goes through the company mailbox and is
  logged in `email_log` (kind 'Document', Area 20 §4); with no mailbox the remittance keeps Save PDF, Print and Mark as sent. A document
  email is its own action and never depends on a notice preference (owner 12:37 AM, Q3).
