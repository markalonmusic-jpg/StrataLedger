# Bank loans payable: design draft (revision 2)

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
Conventions follow CLAUDE.md: integer cents for money, rates may be REAL, ISO
text dates, booleans 0/1, UTC `_at` timestamps, all writes through service
functions, posted records locked, corrections by reversing entries, no raw SQL
writes from the UI or the AI agent.

Depends on (see docs/inventory_fixed_assets_design.md): `account.control_type`,
`journal_line` source keys, the `payment_allocation` change, the fixed asset
module, and the vendor contact (the bank is a vendor with a vendor code).

CONFIRMED by the user (2026-11-10):
- These are bank loans only.
- The schedule exists to create the payable (AP) on a chosen date, not an
  accrual. The payment is made whenever it is due; payment timing needs no
  special handling.
- The bill date can be set to the end of the month so the expense is captured.
- Closing fees are capitalized to the financed asset when there is one;
  otherwise they become their own amortized asset (rev 3).
- Lines of credit are needed (rev 3).
- Day count is flexible per bank, and variable rates are supported (rev 3).
- A loan that is past due is classified as a current liability (rev 3).

---

## 1. Scope

In: bank term loans (level payment, interest-only, balloon), including
equipment and vehicle loans and mortgages; bank lines of credit; fixed or
variable rate.
Out (PROPOSED): related-party loans, loans the company makes to others, capitalized interest on construction loans, covenants, gain or loss
on refinancing, escrow.

---

## 2. Principles

1. Each loan has a schedule. The schedule gives each AP its principal and
   interest split and drives the current/long-term classification.
2. No interest accrual entries. Expense is recognized when the bill is posted,
   so the bill date rule (section 5) decides the period.
3. The bank statement wins. A person can change the principal and interest on
   a bill; later schedule lines recalculate from the actual balance.
4. Every ledger line on a loan account carries `loan_id`. Loan accounts are
   controlled: no manual or uploaded journal entry can touch them.
5. The AI agent may propose a loan setup from the loan agreement or statement.
   It never posts or approves.
6. Business rules live in the service layer; triggers are only a backstop.

---

## 3. Tables

**loan**
- `loan_id` PK, `loan_number` (automatic, LN0001), `name`
- `lender_contact_id` -> contact (a vendor)
- `loan_type` [Term, Equipment or vehicle, Mortgage, Line of credit]
- `original_principal_cents`, `funding_date`, `first_payment_date`,
  `maturity_date`, `term_months`
- `amortization_type` [Level payment, Interest-only, Balloon, None (line of
  credit)]
- `credit_limit_cents` (line of credit only)
- `payment_cents` (the bank's stated payment; calculated if blank),
  `balloon_cents` (opt)
- `annual_rate` REAL (current rate), `rate_type` [Fixed, Variable]
- `rate_index` [None, Prime, SOFR, Other] and `margin` REAL, `rate_floor` REAL
  (opt) for variable loans; informational, the entered rate is what counts
- `day_count` [30/360, Actual/360, Actual/365, Actual/Actual] (default 30/360;
  set per bank, and can change on a rate change date)
- `classify_all_current` 0/1 (default 1 for a line of credit, else 0; set by
  a person, e.g. default or covenant breach)
- `past_due_grace_days` (default 0; see section 6)
- `closing_cost_treatment` [Capitalize to financed asset, Amortize over loan
  term] (default: capitalize if `asset_id` is set, else amortize)
- `bill_date_rule` [On due date, Last day of the due month, Last day of the
  month before the due date] (see section 5)
- Accounts: `principal_account_id` (long-term), `current_portion_account_id`,
  `interest_expense_account_id`
- `asset_id` -> fixed_asset (opt; the equipment or vehicle financed),
  `project_id` (opt)
- `status` [Draft, Active, Paid off, Refinanced], `refinanced_by_loan_id` (opt),
  `origin`, `created_by`
- A loan with posted entries can be Paid off, never deleted.

**loan_rate_change** (variable rate or any rate/day-count change):
`loan_id`, `effective_date`, `index_value` REAL (opt), `annual_rate`,
`day_count` (opt; changes the basis from that date), `note`, `entered_by`.
A back-dated change leaves Billed lines alone; unbilled lines are recalculated
in a new version and any difference shows up in the next statement amounts.

**loan_schedule_line** (one row per payment per version)
- `schedule_line_id`, `loan_id`, `version` (highest = current), `payment_no`,
  `due_date`, `bill_date`, `period_id` (of the bill date)
- `beginning_balance_cents`, `payment_cents`, `principal_cents`,
  `interest_cents`, `ending_balance_cents`
- `status` [Scheduled, Billed, Paid]
- `invoice_id` -> invoice (the bill, opt)
- `actual_principal_cents`, `actual_interest_cents` (opt; set when billed)
- Unique on (`loan_id`, `version`, `payment_no`).
- Billed and Paid lines are locked. A change (rate change, extra payment, bank
  correction) creates a NEW version for the remaining payments only.

**loan_event** (append-only): `event_id`, `loan_id`, `event_type` [Funded,
Draw, Repayment, Bill created, Extra principal, Rate change, Reclassified,
Paid off, Refinanced, Renewed], `event_date`, `amount_cents`, `entry_id`, `schedule_line_id`
(opt), `note`, `origin`, `created_by`.

**loan_classification**: `loan_id`, `as_of_date`, `total_principal_cents`,
`current_cents`, `long_term_cents`, `schedule_version`, `entry_id`. Unique on
(`loan_id`, `as_of_date`).

### Changes to existing tables
- `account.control_type`: add `Loan principal`, `Loan current portion`.
- `journal_line`: add `loan_id`, `loan_schedule_line_id` (opt), in the ledger
  line keys migration (006).
- `invoice_line`: add `loan_id`, `loan_schedule_line_id` (opt) and
  `loan_line_type` [Principal, Interest, Fee, Extra principal].
- `payment_allocation`: add `loan_id` (opt) for loan proceeds received. A row
  points to one target only (bill, deferral, refund or loan).
- `fixed_asset`: add `loan_id` (opt; closing costs that belong to a loan).
- `company_settings`: nothing new.

---

## 4. Schedule calculation

**Level payment** (30/360: monthly rate r = annual rate / 12):
`payment = P x r / (1 - (1 + r)^-n)`, exact decimal arithmetic. Each period:
`interest = round(balance x r)` to the cent (half up); `principal = payment -
interest`; `ending = balance - principal`. The last payment absorbs rounding so
the ending balance is exactly zero. Interest-only and balloon follow the same
pattern. Actual/360 and Actual/365 use actual days x rate / basis.

**Variable rate:** from each rate change date the remaining schedule is
recalculated (the payment re-amortizes over the remaining term). Billed lines
never change; a new version holds the future lines.

**Extra principal:** reduces the balance on the payment date and recalculates
the remaining schedule (keep the payment and shorten the term).

Worked example: $100,000, 6.00% fixed, 60 monthly payments, 30/360.
- Payment 1,933.28 (the last is 1,933.32).
- Payment 1: interest 500.00, principal 1,433.28, balance 98,566.72.
- Payment 2: interest 492.83, principal 1,440.45, balance 97,126.27.
- Total interest over the life: 15,996.84.

### Lines of credit

- No amortization schedule. Draws and repayments are events (`loan_event`
  with amount, entry and payment).
- **Credit limit:** a draw above the available amount (limit - balance) is
  blocked. A person can raise the limit by editing the loan with a logged note.
- **Draw:** payment Received from the bank, allocated to the loan: Dr Bank,
  Cr Loan current portion (when `classify_all_current` = 1) or Loan principal
  (termed-out line).
- **Repayment:** payment Made to the bank, allocated to the loan: Dr Loan
  current portion or principal, Cr Bank.
- **Interest:** one monthly schedule line per line of credit (interest only,
  no principal). The bill date follows the bill date rule. The system shows an
  ESTIMATE = sum of daily balance x rate / day-count basis from the draw and
  repayment events; the person enters the actual interest from the statement.
  The bill has Interest and Fee lines (unused-line fee, annual fee) and no
  principal line.
- **Availability** (limit - balance) shows in the loan register.
- **Renewal:** an event updates the maturity date and limit with a note.
- **Classification:** all current by default. A long-term (termed-out) line
  can be set to 0, then the normal 12-month rule applies. Which one is right
  is the CPA's call.

---

## 5. Creating the payable (AP)

A "Loan bills" screen lists schedule lines whose `bill_date` has arrived.
Creating the bill produces one Bill to the bank with lines:

| Bill line | Account | `loan_line_type` |
|---|---|---|
| Principal | Current portion (liability) | Principal |
| Interest | Interest expense | Interest |
| Extra principal (if any) | Current portion | Extra principal |

Posting: Dr Current portion (principal), Dr Interest expense; Cr Accounts
payable. Every line carries `loan_id` and `loan_schedule_line_id`. The schedule
line becomes Billed.

**Bill date rule (per loan).** Chosen so the expense lands in the right month:
- On due date: bill dated on the payment due date.
- Last day of the due month: bill dated at the month end of the due date's
  month.
- Last day of the month before the due date: for a payment due early in a
  month (the 1st) that covers the prior month; the expense and AP are in the
  prior month, the payment follows.
- The due date on the bill is always the real payment due date. A bill is
  never dated after its due date; if a rule would do that, the due date is
  used.
- This replaces accrual: the expense is recognized by the bill date, not by
  days elapsed. The amount is whatever the bank statement says.

**Payment:** a normal payment (direction Made) from the bank, allocated to the
bill through `payment_allocation` whenever it is paid: Dr Accounts payable,
Cr Bank. The schedule line becomes Paid when its bill is paid. If the bank
drafts the payment before a bill exists, "Bill and pay" creates both on the
payment date. A bank-feed line that matches a loan bill is matched in staging.

**Matching the statement:** a person can change principal and interest on the
loan screen (not on the generic bill screen). The actual amounts are stored on
the schedule line. If the balance differs from the schedule, a new version
recalculates the remaining lines. Loan lines are read-only on the generic bill
screen.

---

## 6. Short-term and long-term portion

**Rule:** current portion at a balance sheet date = principal due in the 12
months after that date, from the current schedule version. Long-term = balance
- current portion.
- Interest-only: current portion is zero until maturity is within 12 months.
- Balloon: the balloon counts when it is due within 12 months.
- **Past due = current:** if any bill for the loan is unpaid more than
  `past_due_grace_days` after its due date as of the balance sheet date, the
  whole balance is current. The test uses payment dates, so a payment made
  after the balance sheet date does not change the answer for that date.
- A person can also set `classify_all_current` (default, covenant breach).
  Refinancing after the balance sheet date is a CPA call, not designed.

**Posting.** Principal payments are debited to the CURRENT PORTION account. A
classification entry keeps it right:
- At funding: after Cr Loan principal (long-term) for the full amount, a
  system entry moves the principal due in the first 12 months: Dr long-term,
  Cr current portion.
- At each period end (system run): target = principal due in the next 12
  months. Entry = target - the loan's current portion balance. Dr long-term, Cr
  current portion if positive; the reverse if negative. Lines carry `loan_id`.
  A `loan_classification` row records the result.

Worked example: right after funding, current = principal in payments 1-12 =
17,680.31 and long-term = 82,319.69. After payment 12, current = 18,770.80
(payments 13-24) and the balance is 82,319.69. After payment 24, balance
63,548.89 and current 19,928.53.

Tie-out: GL principal plus current portion by `loan_id` = ending balance of the
last Billed schedule line.

---

## 7. Funding and closing fees

| Case | Debit | Credit |
|---|---|---|
| Cash proceeds | Bank | Loan principal |
| Bank pays the vendor (equipment loan) | Accounts payable (the vendor's bill) | Loan principal |
| Bank pays the vendor, asset not billed yet | Fixed asset (draft asset) | Loan principal |

- Proceeds into the bank are a payment (direction Received) from the bank,
  allocated to the loan.
- Equipment loans link to the `fixed_asset`.
- **Closing fees** (the bill line for the fee, coded by treatment):
  - **Capitalize to the financed asset** (when the loan has an `asset_id`):
    the fee is added to that asset's cost. The ledger line carries the
    asset's `asset_id`, and an asset event "Improvement" records it with the
    `loan_id`. Depreciation recalculates for the remaining months going
    forward; posted months never change. If the asset is still Draft, the
    cost is added to it directly.
  - **Amortize over the loan term** (no financed asset): the line is coded to
    an asset class named "Loan closing costs" and posts as a fixed asset
    linked to the loan (`fixed_asset.loan_id`), starting at the funding
    date, straight-line over `term_months`, with per-asset depreciation as
    usual. The class's expense account is a person's choice (amortization of
    loan costs or interest expense).
  - The person picks the treatment per fee line; the loan's default
    pre-fills it.
- If a loan is paid off or refinanced early, the screen prompts to dispose of
  the linked closing-cost asset, which writes off the remaining net book value
  through the normal disposal entry. Costs capitalized into a financed asset
  stay with that asset.
- The agent may propose the setup from the loan agreement; a person approves.

---

## 8. Other events

- **Extra principal payment:** a bill line (Extra principal) and a payment; the
  schedule recalculates.
- **Rate change (variable):** enter the rate and effective date; a new schedule
  version is created going forward.
- **Payoff:** payoff amount = balance + interest to date + fees; the loan is
  marked Paid off; unpaid schedule lines close.
- **Refinance:** pay off the old loan, fund a new one, link them with
  `refinanced_by_loan_id`. Gain or loss is NOT designed.

---

## 9. Rules

1. The schedule is generated once at activation; later changes create a new
   version for future lines only.
2. Loan accounts accept lines only from the loan service (controlled).
3. Billed and Paid schedule lines are locked.
4. Loan lines on a bill cannot be edited from the bill screen.
5. One bill per schedule line (`invoice_id` is unique).
6. The classification run covers every Active loan, once per loan and date.
7. Nothing posts into a closed period; reversals follow the ledger rules.
8. Schedule principal adds up to the original principal; a balloon is explicit.
9. A paid-off loan has a zero balance in both loan accounts.
10. Every service function that posts has a test for each posting row above.

---

## 10. Views and reports

Loan register (balance, rate, next bill, maturity), amortization schedule (per
version), balance by loan at any date, current vs long-term by loan at any
date, interest expense by loan and period, maturity ladder (principal due by
year), upcoming bills, schedule vs actual differences, tie-out to the general
ledger, unamortized closing costs by loan, loans financing each fixed asset.

---

## 11. Placement

PROPOSED migration 010 (Loans), after vendor refunds. `loan_id` on
`journal_line` and the new `control_type` values go into the ledger-keys
migration (006). Services after Phase 2; posting with the posting phase. Order:
tables and constraints, service functions, screens.

---

## 12. Decisions and open questions

Decided (user, 2026-11-10):
1. Day count is flexible per bank (set per loan, changeable by rate change).
2. Lines of credit are in scope (section 4, Lines of credit).
3. Variable rates are supported, with effective-dated rate changes.
4. Closing costs: capitalized to the financed asset, otherwise amortized as
   their own asset.
5. A past-due loan is classified as a current liability.

Still open:
1. Past-due grace days: default 0. Do you want a different default?
2. Is a line of credit usually all current for your clients, or do some have
   multi-year revolvers? (Default is current; a CPA decides the exceptions.)
3. Which expense account should "Loan closing costs" amortization use
   (interest expense or a separate amortization account)?
4. Back-dated rate changes: the difference flows through the next statement
   amounts. OK, or do you want a catch-up bill?
