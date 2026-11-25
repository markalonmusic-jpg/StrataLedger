# Step 2.9 schema replan, area 1: payments and receipts

Status: **Drafted 2026-11-24 for owner approval.** The outline was approved by the owner 2026-11-24 8:55 PM (planning
chat) with the answers recorded in §1.2, §2.1, §3.2 and §4.1; the rest follows the recommended options. Docs only:
nothing here changes code, a baseline, a migration or a test. Everything below is built only in the 2.9 baseline pass,
after the whole replan is approved. Items marked PROPOSED or "planning proposal, owner may revise" are not decided.
Payments made to vendors are Area 2's pay run; this area owns what both sides share: the payment record, receipts,
applications and unapplied cash, voids, refunds, write-offs and statements (`modules/services/payments.py` and its
new neighbours).

Sources read (searched by code, date or title):
- `docs/next_step.md`: every Area 1 entry (OD-69/OD-70 undo and re-apply, the 2026-11-24 2:55 PM amendment, RP11, the
  allocation inputs for Area 2, the Mark triage of 2026-11-21 1:45 AM must-fix inputs).
- Cross-references in Area 2 (§3.2, §5, §6, §9 O2), Area 5 (§4.2, §8.5 Q9 and Q10, §9.4), Area 10 (§11.2, §11.5),
  Area 12 (§4 deposits, §10), Area 13 (§1.4 callers) and Area 18 (§8.1, §8.6, §8.7).
- `migrations/001_company.sql`: `payment` :670, `payment_allocation` :316, the RP11 triggers :1543-1570, `account`
  :569, `company_settings` roles :771-787, `bank_account` :1332; `modules/services/payments.py` (open_item,
  allocate, release_allocations, clearing_lines, `_check_period`).
- `docs/decisions_2026-11-11.md`: R56-R59, RP2, RP11, L4, B2, B4, B6 (searched by code).
- Owner answers 2026-11-24 8:55 PM (planning chat), given in the task and recorded here.

---

## 0. Summary

| # | Item | Proposal in one line | Baseline |
|---|------|----------------------|----------|
| 1 | The payment record | `payment` gains status, void fields, reference, memo, fee and a user-chosen destination; the method CHECK becomes a company-editable list table | company |
| 2 | Where a receipt lands | The user picks Undeposited funds or a bank account on each receipt; no default by method (Q3) | company |
| 3 | Unapplied cash and deposits | Money the user cannot yet place posts to Unapplied customer payments; money stated as a deposit posts to a deposit account the user chooses (Q1); applying later is Dr held account / Cr AR | company |
| 4 | Applications | Operation IDs, status as of a date from posted applications only, release fields, one service function for every release | company |
| 5 | Unapply and RP11 | A user with the permission may unapply while the payment stays posted, with a reason; RP11 is rewritten (Q2) | company |
| 6 | Voids | Whoever can record payments may void one with a reason; cleared items go through bank reconciliation; no `payment.void` (Q7) | company |
| 7 | Refunds, write-offs, statements | Service-owned postings for the rules Area 5 decided; four separate sensitive permissions, approvals OFF | company |
| 8 | Locks and permissions | Payments received and Bill payments areas plus the AR, AP and held accounts; one new permission proposed | company |

Everything is company-database only. Nothing goes in `system_master.db` except the new permission codes' seeds
(Area 18 owns the seed).

---

## 1. The payment record and receipts

### 1.1 Current state

- `payment` (`001_company.sql:670`): `direction` Received or Made, `contact_id`, `payment_date`, `amount_cents` > 0,
  `currency`, `exchange_rate` (only 1.0), `method` CHECK Cash, Check, Bank Transfer, GCash, Maya,
  `bank_account_id` REFERENCES account, `entry_id` UNIQUE. No status, void fields, reference, memo, fee or deposit
  link. No service writes a receipt today; `payments.py` only allocates and releases (R56-R59).
- `payment_allocation` and its RP11 triggers are in §3.1.
- The role accounts exist in `company_settings`: `undeposited_funds_acct_id` :771, `customer_deposits_acct_id` :780,
  `bank_charges_acct_id` :783. The Unapplied customer payments role is Area 18 §8.6 (lead account 2325).
- `payments._check_period` reads the legacy Sales and Purchases lock areas (`LOCK_AREA`, payments.py:29).
- Area 12 owns `deposit` and `deposit_line` (Dr bank / Cr the undeposited funds role); Area 2 owns payments made
  through the pay run and adds `payment.pay_run_id` and `reference` (Area 2 §3.2).

### 1.2 Decided (owner, 2026-11-24 8:55 PM)

- **Q3: the user chooses where each receipt lands**, Undeposited funds or a bank account. There is no default by
  method. Example: a $1,000.00 card payment can be put straight into Operating bank, or into Undeposited funds, as
  the user decides.
- **Q4: an optional Fee on the receipt**; the user picks the fee account, Bank charges by default (§1.4).
- **Q6: payment methods are a company-editable list**, like the units list. The core list (Cash, Check, ACH, Wire,
  Card, Bank transfer, and Paid outside for payments made) ships as the default (that default list is a planning
  proposal); companies add their own (for example GCash, Maya). The method CHECK is replaced by a list table.
- **Q8 (decided 2:55 PM):** a receipt larger than the invoices ticked posts the remainder to Unapplied customer
  payments automatically, with a notice.

### 1.3 Proposed schema (planning proposal, owner may revise)

**`payment_method`** (new): `payment_method_id` PK, `name` TEXT NOT NULL UNIQUE COLLATE NOCASE, `kind` TEXT NOT NULL
CHECK IN ('Cash', 'Check', 'ACH', 'Wire', 'Card', 'Bank transfer', 'Paid outside', 'Loan funded', 'Other'), `direction` TEXT NOT
NULL CHECK IN ('Received', 'Made', 'Both'), `requires_reference` INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1),
`is_core` INTEGER NOT NULL DEFAULT 0, `is_active` INTEGER NOT NULL DEFAULT 1, `sort_order` INTEGER NOT NULL,
`row_version`. Seed: the eight core rows (Paid outside and Loan funded are Made only; Loan funded is shipped for Area 11 §6 and not deactivatable while a loan uses it). A company-added method such as GCash is kind
'Other' and sets its own `requires_reference`. A used method is deactivated, never deleted. The kind keeps Area 2's
rules working: a Check needs a number unique across all payments, ACH and Wire need a reference, a Card line needs
the card account (Area 2 §3.2). Edited under the same permission as the other Settings > Lists pages.

**`payment`** (changed):

| Column | Change |
|--------|--------|
| `method` | replaced by `payment_method_id` INTEGER NOT NULL REFERENCES payment_method, plus `method_name` TEXT NOT NULL (the label at the time of use) |
| `status` | new, TEXT NOT NULL CHECK IN ('Draft', 'Posted', 'Voided'), service-owned |
| `reference` | TEXT (the check number, ACH or wire reference, card authorization); Area 2 adds the same column, one column only |
| `memo` | TEXT, CHECK NULL or length <= 1000 |
| `bank_account_id` | kept (REFERENCES account); it is the account the money landed in: a `bank_account` row or the Undeposited funds role account (service check), and NULL for a Loan funded payment (§9.2); Area 12 §5 (line 463) said Area 1 may change it |
| `project_id` | new, INTEGER NULL REFERENCES project: the job the money is for, when known (a deposit for RI0001-003); carried on the held line |
| `held_account_id` | new, INTEGER NULL REFERENCES account: where an unapplied part is held; NULL means the Unapplied customer payments role (§2.2) |
| `fee_cents`, `fee_account_id` | new, INTEGER NOT NULL DEFAULT 0 CHECK (>= 0 AND < `amount_cents`) and INTEGER NULL REFERENCES account (defaults to the `bank_charges` role); CHECK `(fee_cents = 0) = (fee_account_id IS NULL)` and fee only on a Received payment |
| `operation_id` | new, TEXT UNIQUE (a retried recording returns the first result, §3.3) |
| `voided_by`, `voided_at`, `void_reason`, `void_reason_id`, `void_reason_label` | new, all or none; reason rules in §4.1 |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

The currency columns stay as they are (single currency, `exchange_rate` = 1.0). Date cleared is not a column: it is
read from Area 12's `bank_line_clearing` (Area 2 §3.2), so date paid and date cleared stay distinct.

### 1.4 Receipt posting (through `ledger.create_document_entry`)

One entry per receipt, source Payment:
- **Debit** the landing account (Undeposited funds or the chosen bank account) for `amount_cents` less the fee.
- **Debit** the fee account for `fee_cents`.
- **Credit** Accounts receivable, one line per applied invoice, each carrying that invoice's clearing id (R57), for
  the applied amounts.
- **Credit** the held account for any remainder (§2), a line that opens its own clearing group.

A fee is allowed only when the landing account is a bank account: with Undeposited funds the fee must be 0 (the fee
is recorded when the money reaches the bank, Area 12). A refused receipt writes nothing.

Example: a $1,000.00 card payment of INV-0377, with a 2.9% plus $0.30 fee ($29.30), landing in Operating bank:
Dr Operating bank $970.70 / Dr Bank charges $29.30 / Cr 1110 Accounts receivable $1,000.00 (INV-0377's group).

### 1.5 Tests (planning proposal)

`test_receipt_posting_runs_through_service`, `test_receipt_destination_is_the_users_choice_with_no_default_by_method`,
`test_receipt_into_undeposited_funds_or_bank_only`, `test_card_fee_posts_through_payment_service`,
`test_fee_refused_when_landing_in_undeposited_funds`, `test_date_paid_and_date_cleared_are_distinct`,
`test_payment_method_list_is_company_editable_and_used_method_is_deactivated_not_deleted`,
`test_method_name_is_kept_as_used`, `test_refused_receipt_writes_nothing`.

---

## 2. Unapplied cash and deposits

### 2.1 Decided (owner)

- **2:55 PM 2026-11-24:** every unapplied customer payment posts Cr Unapplied customer payments (current liability,
  the OD-70 role), never Cr Accounts receivable; applying it later is Dr Unapplied / Cr Accounts receivable; AR aging
  shows unapplied payments as their own line.
- **Q1, narrowing the 2:55 PM answer (8:55 PM):** a payment the customer **explicitly said is a deposit** posts to a
  customer deposit account the **user chooses** (Dr bank / Cr Customer Deposits $20,000.00 for RI0001-003). Money the
  user **cannot yet place** (a $5,000.00 bank-feed check with no invoice) posts to Unapplied customer payments. The
  account is the user's choice on the receipt.

### 2.2 Proposed rules (planning proposal, owner may revise)

- **The receipt asks one question** about any part not applied to an invoice: "Hold this as: Not yet placed
  (Unapplied customer payments) or A deposit (choose the deposit account)". Not yet placed is the default.
- **The held account** is `payment.held_account_id`: NULL = the Unapplied role account; otherwise an active postable
  current-liability account the user picks, offered from the `customer_deposits` role account and any account the
  company marks as a customer deposit account (the account's `control_type` gains 'Customer deposits'). A control type
  'Unapplied customer payments' is added for the role account. Both control types set `track_clearing_id` = 1 so each
  held amount is its own open item per customer, and are posted only by the receipts service (the Area 18 §8.6
  controlled-account block applies to manual entries).
- **Applying later** (either kind) posts one entry, source Payment, origin System (R59: the allocation is the
  decision, no approval): Dr the held account (that amount's clearing group) / Cr Accounts receivable (the invoice's
  clearing group, job and customer). Cash does not move.
- **Applied on the receipt itself:** no separate application entry. The receipt's own entry credits AR with the
  invoice's clearing id (R57), as in §1.4.
- **Reports:** AR aging and the statement show the Unapplied balance as its own line ("Unapplied customer payments"),
  per customer; deposits show on the statement and aging as their own "Customer deposits" line (planning proposal).
  Statements keep Area 5 §4.2's "Unapplied credits and payments" section: unapplied payments plus unapplied credit
  memos, which stay AR credit lines (§3.4).
- **Overpayment and policy.** Q8 above. Only an explicit deposit goes to a deposit account; ordinary overpayment goes
  to Unapplied. Mark's policy item (next_step) is settled by Q1 and Q8.

### 2.3 Postings with worked examples

- **P1: money the user cannot yet place.** A $5,000.00 check arrives in the bank feed with no invoice: Dr Operating
  bank $5,000.00 / Cr 2325 Unapplied customer payments $5,000.00. (A check that has not been to the bank yet: Dr 1050
  Undeposited funds, and Area 12's deposit later moves it: Dr Operating bank / Cr 1050.)
- **P2: partly applied on the receipt.** A $12,000.00 check, $9,500.00 for INV-0377: Dr 1050 Undeposited funds
  $12,000.00 / Cr 1110 $9,500.00 (INV-0377's group) / Cr 2325 $2,500.00.
- **P3: applying the rest later.** The $2,500.00 to INV-0388 (job RI0001-003): Dr 2325 $2,500.00 / Cr 1110 $2,500.00
  (INV-0388's group).
- **P7: an explicit deposit.** The customer says "$20,000.00 deposit for RI0001-003" and the user picks Customer
  Deposits: Dr Operating bank $20,000.00 / Cr Customer Deposits $20,000.00 (line job RI0001-003). When the deposit
  invoice or a pay app exists it is applied: Dr Customer Deposits / Cr 1110.

### 2.4 Tests (planning proposal)

`test_unplaced_money_posts_to_unapplied_customer_payments`,
`test_explicit_deposit_posts_to_the_deposit_account_the_user_chose`,
`test_receipt_remainder_above_applied_posts_unapplied_line_with_notice`,
`test_applying_unapplied_payment_posts_dr_unapplied_cr_ar`,
`test_applying_deposit_posts_dr_deposit_account_cr_ar`,
`test_ar_aging_and_statement_show_unapplied_and_deposit_lines`,
`test_held_account_must_be_an_active_postable_current_liability`,
`test_manual_entry_to_held_accounts_is_refused_when_controlled`.

---

## 3. Applications, unapply and RP11

### 3.1 Current state

- `payment_allocation` (:316): one source (payment or credit memo), one target (invoice or deferral), amount, applied
  date, R58's `application_entry_id`, and the release columns `released_at`, `released_by`, `release_reason`, set only
  together.
- RP11 (`payment_allocation_lock_delete`, `payment_allocation_lock_update`, :1543-1570): a posted source's allocation
  is never deleted and may only be stamped released, and only after the source's entry is voided.
- `payments.allocate` and `release_allocations` implement R56-R59; `clearing_lines` posts a payment's unapplied
  remainder as an AR line that opens a new group (R57). That last behaviour is replaced by §2.
- Draft sources may allocate (row only); the posting later splits the AR side.

### 3.2 Decided (owner, 8:55 PM, Q2: a new decision)

A user **with a permission** may **Unapply** an application while the payment stays posted, with a reason (OD-31):
Dr Accounts receivable on that invoice / Cr Unapplied customer payments, and the payment can then be re-applied. No
void; the history keeps both. Reclass job and the Reclassify transactions page also release (Area 10 §11.2, §11.5).
**RP11 is rewritten accordingly**: the trigger keeps its append-only guarantees and the allowed reasons live in the
service.

### 3.3 Proposed schema (planning proposal, owner may revise)

**`payment_allocation`** (changed):

| Column | Change |
|--------|--------|
| `operation_id` | new, TEXT NOT NULL UNIQUE; a retried application returns the original result (Mark 2026-11-21 input; the 2026-11-20 5:15 PM principle) |
| `discount_cents` | new (Area 2 §3.2), INTEGER NOT NULL DEFAULT 0 CHECK (>= 0) |
| `deferral_id` | **removed**; `allocation_one_target` becomes NOT NULL on `invoice_id` (the deferral target has no allocator; Area 10 deferrals take no payments) |
| `release_kind` | new, TEXT CHECK IN ('Source voided', 'Unapplied by user', 'Reclass job', 'Reclassify page', 'Invoice voided', 'Invoice reposted'), set with the release columns |
| `release_reason_id`, `release_reason_label` | new, with `release_reason` kept: the Area 18 §8.7 pattern (a listed reason, or Other with at least 10 typed characters) |
| `release_effective_date` | new, TEXT date: the date the release counts from (as-of reads) |
| `release_entry_id` | new, INTEGER UNIQUE REFERENCES journal_entry: the Dr AR / Cr Unapplied entry that an unapply, a Reclass job, a Reclassify or an invoice void posts (NULL when the source's void reversed everything) |
| `replacement_invoice_id` | new, INTEGER NULL REFERENCES invoice: the new version, when the invoice was reposted under the same number (Area 5 owns the stable identity) |

CHECK: the release columns are all set or all NULL (as today), and `release_kind` is set with them.

### 3.4 Rules (planning proposal)

- **Status as of a date.** An invoice's Paid or Partly paid counts only **posted** applications whose applied date is
  on or before the as-of date and that were not released by then. Draft receipts, draft credit memos and future-dated
  applications never make an invoice Paid. The expectation in `tests/test_payments.py` around line 381
  (`test_releasing_a_draft_source_allocation_posts_no_entry` expects Paid after allocating a draft source) is wrong and
  is replaced in the rebuild with a not-Paid assertion.
- **One release function** (`payments.unapply`, planning proposal) is the only code that releases a live allocation.
  It runs inside the caller's transaction, checks the lock (§6), writes the opposite entry and stamps the release.
- **Unapply by the user:** `payment.unapply` (PROPOSED sensitive code, §6), reason required (Area 18 §8.7: a listed **[Withdrawn 2026-11-24 9:10 PM: uses `payment.receive` or `payment.make`; §9.1.]**
  reason such as "Applied to the wrong invoice", or Other with 10 typed characters). Posts Dr 1110 (the invoice's
  group, job and customer, reopening it) / Cr 2325 on the payment's job. Example: $2,500.00 applied to INV-0388 by
  mistake: Dr 1110 $2,500.00 / Cr 2325 $2,500.00; INV-0388 is open again; the payment shows the OD-11 "Unapplied"
  badge and can be applied to INV-0377 (P3's entry, Dr 2325 / Cr 1110).
- **Reclass job and Reclassify page (OD-69, OD-70, Area 10 Q19 B):** the same function with `release_kind` 'Reclass
  job' or 'Reclassify page' and the system reason "Reclass job"; the entry is the OD-70 entry already decided (Dr 1110
  / Cr 2325 on the payment's original job; Area 10 §11.2, the $10,000.00 RI0001-002 example).
- **Voiding a paid invoice** releases each application first (`release_kind` 'Invoice voided', Dr 1110 / Cr 2325), then
  reverses the invoice, so the payment stays posted and unapplied. **Reposting under the same number** (rule 8) does
  the same with `release_kind` 'Invoice reposted' and `replacement_invoice_id` on each released row, then re-applies.
  Both in one transaction.
- **Voiding the source** keeps today's path (§4): the receipt's entry is reversed and each application entry is voided
  (R59); `release_kind` 'Source voided', no `release_entry_id`.
- **Credit memos** (R58) are unchanged: an unapplied credit memo remains an AR credit line, not the Unapplied
  role, and its application and unapply are zero-net entries between groups, with the same reason and permission rules.
- **Locks:** §6.

### 3.5 RP11, rewritten (owner 8:55 PM; Q2)

Allocations of a posted source are never deleted. A release stamps the allocation once (the release columns above).
The database keeps only the append-only guarantees: no delete; an update on a posted source's allocation may only set
the release columns on a still-live row, and nothing else changes. **Which releases are allowed is the service's
rule (H4), not the trigger's:** the source was voided, the user unapplied it with a reason and the permission, a
Reclass job or the Reclassify page, or the invoice was voided or reposted. This replaces "only after the source's
entry is voided" in the baseline trigger and comment (`payment_allocation_lock_update`, :1571) when the
baseline is rebuilt, and supersedes RP11's closing note that a later unapply "would be a new decision": it is now
decided. Amended beside RP11 in `docs/decisions_2026-11-11.md`.

### 3.6 Tests (planning proposal)

`test_invoice_status_uses_only_posted_applications_as_of_date`,
`test_releasing_a_draft_source_allocation_posts_no_entry` (assertion changed: not Paid),
`test_allocation_same_operation_id_retry_returns_original_result`,
`test_allocation_schema_targets_match_supported_allocator_targets`,
`test_user_unapply_posts_dr_ar_cr_unapplied_and_keeps_both_rows_in_history`,
`test_user_unapply_needs_permission_and_reason`, `test_unapply_reason_under_10_characters_refused_for_other`,
`test_unapplied_payment_can_be_reapplied`, `test_reclass_job_release_allowed_while_payment_posted`,
`test_release_with_a_reason_kind_outside_the_allowed_set_is_refused`,
`test_allocation_release_records_effective_date_and_replacement_invoice_version`,
`test_paid_invoice_void_releases_allocations_to_posted_receipt`,
`test_same_number_repost_uses_stable_invoice_identity_after_number_reserved`,
`test_posted_allocation_cannot_be_deleted_or_edited_except_release_columns`,
`test_credit_memo_unapplied_remainder_stays_on_ar`.

---

## 4. Voids and returned items

### 4.1 Decided (owner, 8:55 PM, Q7)

There is **no separate void permission**: anyone who can record payments (`payment.receive` for a payment received,
`payment.make` for a payment made) may void one, with a reason: a listed reason ("Not cleared", "NSF", and others the
company adds under Settings > Lists > Reasons, kind 'Void payment') or Other with at least 10 typed characters
(OD-31). Cleared or reconciled payments are controlled through bank reconciliation (Area 12 correction first). Area 2's
proposed `payment.void` is **withdrawn**. Planning note: an NSF check that was already deposited and then returned is
a **returned item**, handled in Area 12, not a plain void.

### 4.2 Proposed rules (planning proposal)

- The void reverses the receipt's entry (Void reversal; dating per Area 10 Q21 A and OD-71: the original date if
  its period is open and not locked, otherwise the void date), voids each application entry (R59) and stamps each
  allocation 'Source voided'. A payment in a live deposit is taken out of the deposit first (Area 12). One transaction.
- Example: the $12,000.00 check of P2 is voided with the reason "Not cleared": the entry is reversed, INV-0377's group
  reopens, nothing is left unapplied.
- A voided payment cannot be applied (existing trigger `payment_allocation_no_voided_payment`).
- Tests: `test_void_payment_reverses_entry_and_releases_allocations_with_reason`,
  `test_void_payment_uses_listed_reason_or_10_character_other`,
  `test_void_cleared_payment_refused_until_bank_correction`,
  `test_void_needs_payment_receive_or_make_not_a_separate_permission`,
  `test_voided_payment_cannot_be_applied`.

---

## 5. Refunds, write-offs and statements: the services

Area 5 decided the rules (§8.5 Q9 and Q10, §4.2); this area owns the postings.

- **Refund** (`customer_refund`, planning proposal): source a payment's unapplied part, a customer deposit or an
  unapplied credit memo; checks and consumes the source's available balance in the posting transaction; applied
  amounts need an authorized release first. Posting: **Dr the source's held account** (Unapplied customer payments
  for unapplied receipts, the deposit account for deposits; for a credit memo, Accounts receivable against that
  credit, as Q9 says) **/ Cr the payout bank account**. This amends Q9's wording "AR against the specific open credit
  for receipts" (Area 5 pointer). Example: $2,500.00 of unapplied cash is refunded: Dr 2325 $2,500.00 / Cr Operating
  bank $2,500.00. A failed payout that cleared needs an Area 12 bank correction before the void (Q9 reversal).
- **Write-off** (`invoice_writeoff`, planning proposal): Dr the selected GL account / Cr Accounts receivable, partial
  up to the effective unpaid balance, no tax entry (Q10). Example: $1,200.00 against INV-0377: Dr Bad debt expense
  $1,200.00 / Cr 1110 $1,200.00. The form's "Put customer on credit hold" box (unchecked by default) sets the
  customer's hold in the same transaction (Area 5 §4.2 amendment 2026-11-24).
- **Statements** (`statement_send`, planning proposal; Area 5 §4.2 names the retained copy but no table): the exact
  rendered copy with customer, cutoff, parameters, recipient, sender, delivery time, kept under the company retention
  policy (flagged for review if none is set), written through `storage.py` (H3).
- **Four separate sensitive permissions** (Area 5 §5.2 and §9.1, Q9 and Q10; names are planning proposals):
  `customer_refund.issue`, `customer_refund.void`, `invoice.write_off`, `invoice.write_off_reverse`; each in the
  Accountant cap, Admin and the Master, none in `AGENT_ALLOWED`. Refund and write-off approvals are **OFF by default**
  (the existing approval kinds routed through Area 14).
- Tests: `test_refund_posting_runs_through_service`, `test_refund_from_unapplied_receipt_debits_unapplied_role`,
  `test_refund_from_deposit_debits_the_deposit_account`, `test_writeoff_posting_runs_through_service`,
  `test_statement_send_and_retention_run_through_service`,
  `test_refund_writeoff_authorities_are_four_separate_sensitive_permissions`,
  `test_refund_writeoff_approval_defaults_are_off`.

---

## 6. Locks, permissions, controls, row version and audit

- **Locks (Area 13 §1.4):** a receipt, application, unapply, void and refund check the **Payments received** area
  (Sales side) or **Bill payments** (Purchase side) plus every account the lines touch: AR, the bank or Undeposited
  account, the held account, the fee account. A write-off checks **Invoices and credit memos**. This replaces the
  legacy Sales and Purchases areas in `payments._check_period`; its refusal becomes `PeriodLockedError`.
  Test: `test_payment_locks_use_payments_received_or_bill_payments_area_and_ar_ap_accounts`.
- **Permissions:** `payment.receive` (record, apply, void a receipt; Accountant cap, existing) and `payment.make`
  (existing; Area 2). PROPOSED new sensitive `payment.unapply` (Accountant cap, Admin, the Master; owner may instead **[Withdrawn 2026-11-24 9:10 PM; §9.1.]**
  choose to reuse `payment.receive`) and the four of §5; none in `AGENT_ALLOWED`. The agent never records, applies,
  unapplies or voids (section 0). Area 18 places the codes and recounts the seed (§8.12 there).
- **Controls:** none new. Refund and write-off approvals and 'Payment' approval are existing `document_approval_setting`
  rows, OFF by default; separation of duties follows `require_separate_approver`.
- **Row version:** `payment`, `payment_method`, `payment_allocation` (g4); stale saves are refused.
- **Audit:** the existing audit triggers cover `payment` and `payment_allocation`; add `payment_method`,
  `customer_refund`, `invoice_writeoff`, `statement_send`; the release stamps are before/after rows (Area 18 §1).

---

## 7. How it lands in the baselines and the existing code

- **Company baseline (one pass, tests first):** `payment_method`, `customer_refund`, `invoice_writeoff`,
  `statement_send`; `payment` and `payment_allocation` changes of §1.3 and §3.3; the rewritten RP11 trigger; the two
  new `account.control_type` values; the Reasons kinds 'Void payment' and 'Unapply payment'; seeds for
  `payment_method`. Every development database is blocked and rebuilt (CLAUDE.md section 5.2; ask first).
- **Code:** `payments.py` is split: `open_item`, `clearing_lines` (now posting the remainder to the held account),
  `allocate`, a new `unapply`, `release_allocations` (void path), then new services for receipts, refunds, write-offs
  and statements. `LOCK_AREA` changes (§6). Static tests: every function that writes `journal_line` or releases an
  allocation calls the shared lock check (Area 13 Q7 A).
- **Existing tests change:** `tests/test_payments.py` (the Paid-after-draft expectation, the lock-area inserts,
  the remainder line), `tests/test_schema_replan.py` allocation checks.
- **Handoffs out:** Area 3's `vendor.default_payment_method` and Area 2's `pay_run_line.method` take their values from
  `payment_method` (pointers in Area 2; Area 3 follows when next touched); Area 12 gets the destination rule and the
  returned-item note; Area 14 routes the refund and write-off approvals.

---

## 8. Conflicts with decisions or the baseline (flagged)

- **R57/R58 versus the 2:55 PM rule.** R57's remainder line (Cr AR, new group) and `clearing_lines` become the held
  account; R58's zero-net application entry for a posted payment becomes Dr held account / Cr AR. Credit memos keep
  R58 (§3.4). Sales side only; vendor payments keep today's AP behaviour.
- **RP11.** Rewritten (§3.5); the baseline trigger and comment change in the rebuild.
- **Area 5 Q9.** Its refund debit wording ("AR against the specific open credit for receipts") is amended (Area 5
  pointer): unapplied receipts debit the Unapplied role, deposits the deposit account.
- **Area 18 §8.6.** Its role text ("posted only when ... un-applied by Reclass job") was already withdrawn 2026-11-24
  (2:55 PM); Q1 now narrows the 2:55 PM wording: a stated deposit goes to the user's deposit account.
- **Area 2.** `payment.void` and the fixed method CHECK are withdrawn (Area 2 pointers).
- **Account numbers.** The owner's text names 1200 for Accounts receivable (mockup chart); the repo template has 1110.
  The baseline follows the repo chart.

---

## 9. Open items (not decisions)

- **`payment.unapply` versus reuse of `payment.receive`:** the owner said "a user with a permission"; a new sensitive
  code is proposed. Say if the existing code should be reused.
- **Returned items (NSF after deposit):** Area 12 (not designed here).
- **Customer deposits and Area 4/6 pay apps:** how a deposit balance is credited "Less deposit applied" is Area 4's
  and Area 6's rule; this area only holds and applies it.
- **Vendor prepayments:** not covered; the Purchase side keeps today's remainder line (Area 2/3).
- **Foreign-currency receipts:** out of scope (`exchange_rate` stays 1.0).
- **Statement send:** the table's owner (Area 1 or Area 5) is for the owner to confirm.

### 9.1 Answered 2026-11-24 9:10 PM (owner; dated amendment, the §9 items above stay as asked)

- **Answered: unapply permission.** Unapply uses the same permission as recording the payment (`payment.receive` for
  customer receipts, `payment.make` for vendor payments), with a reason (OD-31). **No `payment.unapply`** (owner
  rule). The "new sensitive code is proposed" line in §9 and any `payment.unapply` mention in §3 and §6 are
  **Withdrawn** by this answer.
- **Answered: returned items (NSF after deposit).** A returned check that already cleared is a returned-item entry in
  Area 12, not a void (owner rule). The original payment and deposit stay; history links them. Area 12 section 11.1.
- **Answered (planning decision, owner may revise): `statement_send` belongs to Area 5**, which already names the
  retained copy. Area 1 does not create the table. Area 5 section 9.6.
- Still open in §9: customer deposits and pay apps (Areas 4 and 6), vendor prepayments, foreign currency.

- **Amendment 2026-11-24 (pointer, Area 14, owner 10:20 PM): Refund and Write-off are new approval kinds, not
  existing ones.** The baseline has no such rows; Area 14 §3 adds them to `approval_kind` and
  `document_approval_setting`, all OFF, with the approve permissions `customer_refund.approve` and
  `invoice.write_off.approve` (planning proposals). Confirmed (owner 9:10 PM): unapply uses the recording permission
  and a reason, void needs only a reason, and neither has an approval kind (Area 14 §3, §15). A vendor-credit
  write-off follows the Company threshold alone.

### 9.2 Amendment 2026-11-25 (Area 11 §6, owner A11-Q2): the shipped payment method 'Loan funded' (planning proposal for the mechanics, owner may revise)

A loan paid to the equipment dealer is the dealer's bill (Area 3) paid by a bank payment for any down payment plus a **"loan funded" payment** that names a loan, not a bank account (Area 11 §6).

- **Schema:** `payment_method.kind` gains 'Loan funded' (direction 'Made' only; seeded as a shipped method, `is_core` = 1, not deactivatable while a loan uses it). `payment` gains `loan_id` INTEGER NULL REFERENCES `loan`
  (Area 11 §6) with `loan_id` set exactly when the method's kind is 'Loan funded' (a service rule with a test, since SQL cannot read the method row) and `bank_account_id` becomes NULL for a Loan funded payment (service check; the column
  stays required for every other kind). A Loan funded payment has no reference and no fee.
- **Posting:** Dr Accounts payable (the bill's vendor and clearing group) / Cr Loans payable (the loan's `loan_account_id`), **no bank line**; the same payment-allocation rules apply (RP11, `operation_id` retry). It **never appears in bank
  reconciliation or the bank feed** (Area 12 reads only payments with a `bank_account_id`) and never counts in Open payments.
- **Combining:** one bill may be paid by several payments, so a bank payment and a loan funded payment can sit on the same bill. **Example:** a $130,000.00 dealer bill = $10,000.00 bank (Dr Accounts payable $10,000.00 / Cr Bank $10,000.00) + $120,000.00 loan funded
  (Dr Accounts payable $120,000.00 / Cr Loans payable $120,000.00); Accounts payable nets $0.00 and the loan starts at $120,000.00.
- **Refusals:** the method is refused for customer receipts (direction 'Received'); it is refused for a loan whose status is Paid off or Closed, for a Line of credit (**owner 2:36 AM, A1-LOC:** a line of credit pays a vendor through a draw into the bank and then a bank payment; example: a $15,000.00 bill = Draw (Dr Bank / Cr Line of credit 2510) $15,000.00 + bank payment (Dr Accounts payable / Cr Bank) $15,000.00; only an Active Term loan or Vehicle loan may be picked), for an amount above the loan's remaining unfunded
  amount (original amount less principal already funded or paid), and when the bill's vendor is not the dealer the loan names (planning proposal: the loan's `linked_asset_id` or the asset bill must match).
- **Tests (planning proposals):** `test_loan_funded_payment_posts_dr_accounts_payable_cr_loans_payable_and_no_bank_line`, `test_loan_funded_payment_never_appears_in_bank_reconciliation`, `test_loan_funded_method_refused_on_a_customer_receipt`,
  `test_loan_funded_payment_refused_for_a_paid_off_or_closed_loan`, `test_loan_funded_payment_refused_for_a_line_of_credit`, `test_line_of_credit_draw_then_bank_payment_pays_a_bill` (owner A1-LOC: a $15,000.00 bill, draw Dr Bank / Cr Line of credit 2510 $15,000.00, then bank payment Dr Accounts payable / Cr Bank $15,000.00; the bill is paid, Bank nets $0.00, 2510 is $15,000.00), `test_bank_payment_and_loan_funded_payment_on_one_bill_net_accounts_payable_to_zero` ($130,000.00 = $10,000.00 + $120,000.00),
  `test_loan_funded_payment_cannot_exceed_the_loans_unfunded_amount`, `test_loan_funded_retry_with_the_same_operation_id_posts_once`.
