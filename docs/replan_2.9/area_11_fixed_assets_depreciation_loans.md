# Step 2.9 schema replan, area 11: Fixed assets, depreciation, disposals and loans

Status: **Owner-approved 2026-11-25 2:49 AM (c464cc1); drafted 2026-11-25; revised for the owner answers A11-Q1 to Q4 (2:09 AM) and two planning fixes, section 15.** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise**. PROPOSED items in the sources are not built as final.

Sources read (only these, searched by section, date or code):
- Owner answers 2026-11-25 1:21 AM (Strata_Teams `inbox/to_owner.md`, read-only): Q1 methods, Q2 book depreciation only; the planning calls
  Q3 (loans) and Q4 (no entity column).
- docs/next_step.md: "Area 11 (Fixed assets and loans; not yet drafted)" (ASSET-02, ASSET-03, ASSET-04, the 2026-11-22 owner decisions on
  proceeds and disposals, the Area 14 dependency), and the Area 11 handoff lines in the Area 14 and Area 9 stops.
- Approved areas, by section: 10 (§1.3 and §1.4 the schedule model, "Area 11 reuses the schedule grid"), 13 (§1 area list: Fixed assets and
  depreciation, Loans; §1.4 the shared lock check; §2.3 `depreciation_run`), 14 (kind 'Asset disposal', §6 lock at approval, §7 digests),
  3 (bills, vendor, retainage not used here; Area 3 owns the bill a loan payment or an asset purchase becomes), 2 (pay run pays those bills),
  18 (system account roles, reasons, permissions, attachments), 17 (reports), 21 (row version).
- Live mockups (read-only, StrataLedger_mockups): `assets.html`, `asset-detail.html`, `asset-dispose.html`, `loans.html`, `loan.html`.
- `docs/decisions_2026-11-11.md` (S7 a new subsidiary copies the parent, E5 consolidated reports; the cash-flow lines that put fixed assets
  in investing and loans in financing), `migrations/001_company.sql` (checked: no asset, depreciation or loan table; permission seeds
  `asset.create`, `asset.dispose`, `asset.approve` (sensitive), `asset.view`, `loan.manage`, `loan.view`; `company_settings.gain_loss_disposal_acct_id`,
  `equipment_recovery_acct_id`; 'Asset disposal' in the approval lists).

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | Assets | A `fixed_asset` register with a class list, cost, salvage, in-service date, life, **straight-line or declining balance (owner)**, and its three accounts. The acquisition posts through the bill (Area 3); depreciation starts the month the asset is placed in service. |
| 2 | Depreciation | **Book only, one posting schedule per asset (owner). No tax schedule, no Section 179, bonus or MACRS tables.** One monthly run posts one entry; each asset has schedule lines in the Area 10 grid pattern. |
| 3 | Disposal | One disposal record, one proceeds row per asset (owner ASSET-02/03/04), catch-up depreciation first, then one disposal entry; Reverse disposal undoes it. Approval is Area 14's 'Asset disposal' row (OFF). |
| 4 | Loans | Term loan, line of credit and vehicle loan with a payment schedule; **each payment is drafted as a bill split into principal and interest** (planning call). Balance ties to GL 2500 or 2510. |
| 5 | Current and long-term | Shown from the schedule always; posting a month-end reclass is a Company control, OFF by default (planning proposal). |
| 6 | Entity | No entity column: each subsidiary is its own company database (S7; E5 consolidates by account code) (planning call). |
| 7 | Close and locks | The `depreciation_run` close check ships here; depreciation, disposals and loans are lock areas. |

---

## 1. Current state

- **Baseline:** no asset, depreciation, disposal or loan table. Permission seeds exist (`asset.create`, `asset.dispose`, `asset.approve` sensitive,
  `asset.view`, `loan.manage`, `loan.view`). `company_settings` has `gain_loss_disposal_acct_id` and `equipment_recovery_acct_id`; there is no
  fixed-asset, accumulated-depreciation, depreciation-expense or loan-account role (the mockup maps GL 1500, 1550, 2500, 2510 and 7100). 'Asset
  disposal' is in the approval kind lists (Area 14 makes it a row, owner Area 11).
- **Live mockups:** `assets.html` lists assets (class, in service, cost, accumulated depreciation, net book value, method) with tie-outs to GL 1500 and 1550
  and "October depreciation is 2026-00419" (an entry link). The New asset form has name, class (Vehicles, Equipment, Tools, Office), cost, in service,
  method (Straight-line, Declining balance), useful life, and **Charge to jobs by the hour**. `asset-detail.html` shows the scheduled postings (posted
  "automatically on the last day of each open month"), "Skipped: 2026-11 locked, Post now dates it 12/01/2026", the GL impact and a Clearing ID (AST-S03) for an asset
  bought on a bill ("Posts when the bill is approved"). `asset-dispose.html` has disposal date (must be in an open period), how (Sold, Traded in, Scrapped, Lost or stolen,
  Donated, Insurance claim), sold to or traded to, proceeds to (bank, Accounts receivable creating an invoice to the buyer, or the vendor's bill as a trade-in credit), a lump
  sum split by book value with each line editable, "Depreciation for the disposal month is taken in full (company setting: Disposal month convention, Full month)", a posting
  preview and approval by the Controller. `loans.html` and `loan.html` show the loan types, a 60-payment schedule with interest, principal and balance, bills drafted
  N days before the due date, extra principal, pay off, a line of credit with Record draw and Repay principal, the current and long-term split, and tie-outs to GL 2500
  and 2510. Interest goes to 7100.

## 2. Decided (owner) and carried forward

- **Methods (owner 1:21 AM, Q1):** straight-line and declining balance, as the live New asset form offers. Example: a $48,000.00 truck over 5 years: straight-line
  $800.00 a month; double-declining balance year 1 $19,200.00 (40%). Planning reading (owner may revise): declining balance switches to straight-line when that
  gives more.
- **Book only (owner 1:21 AM, Q2):** the app posts one book schedule per asset; tax depreciation (Section 179, bonus, MACRS) stays with the CPA's tax software.
- **Planning calls (owner may revise):** loans post their payments split into principal and interest, each payment drafted as a bill (Q3); assets belong to their company's
  database, so no entity column (Q4).
- **Disposal inputs already decided (owner 2026-11-22, ASSET-02, ASSET-03, ASSET-04 and the next_step list):** the disposal reads the saved asset schedule and entry; unknown
  asset IDs are refused with no fallback, and a mixed valid and unknown selection blocks the whole disposal naming the missing ID, leaving every selected asset undisposed;
  catch-up depreciation runs through the chosen disposal date before book value and gain or loss are worked out; one durable disposal result is persisted, linked to its exact
  disposal posting and any separate catch-up entry, and an exact retry creates no duplicate; impossible dates are refused before posting (integrity, always on); a scrap disposal
  can have $0 proceeds; negative proceeds are always refused, and removal costs are a separate expense; a lump sum split across assets is editable and must sum to the proceeds
  (for example $500 across two fully depreciated assets), with one proceeds row per disposed asset (asset ID, proceeds cents >= 0, allocation basis Book value, Original cost or
  Edited); a positive lump sum with zero total book value requires a per-asset allocation. Period close, the "Fixed assets and depreciation" posting area and account locks apply.
  Disposal approval uses Area 14's 'Asset disposal' row only when configured (OFF by default). ASSET-04: the List and Schedule share filters and selected dates; monthly totals tie
  to posted depreciation; every posted cell opens its exact entry; a disposal during the range is verified with any separate catch-up entry link.
- **Carried forward:** Area 10's schedule grid pattern is reused (a posted line is never edited, only Reversed; the last line takes the rounding); schedules run while the app is open
  with the owner signed in, and missed runs catch up once at the next sign-in; the AI never posts or approves; depreciation and loans are Area 13 lock areas.

---

## 3. Assets

- **`asset_class`** (company list; planning proposal): `class_id`, `name` (shipped: Vehicles, Heavy equipment, Equipment, Tools, Office), `default_life_months`,
  `asset_account_id`, `accumulated_account_id`, `expense_account_id`, `is_active`, `row_version`. An asset takes its three accounts from its class and may override them. The accounts
  resolve by role from the chart template, never by number; new system roles: `fixed_assets_acct_id`, `accumulated_depreciation_acct_id`, `depreciation_expense_acct_id` (Area 18 §8.1).
- **`fixed_asset`:** `asset_id`; `asset_no` (service-assigned, 'FA-0015', never reused); `name`; `class_id`; `status` CHECK IN ('Not in service', 'In service', 'Disposed');
  `cost_cents` INTEGER CHECK >= 0 (rule 1); `salvage_cents` CHECK >= 0 and <= `cost_cents`; `in_service_on`; `life_months` CHECK BETWEEN 1 AND 600;
  `method` CHECK IN ('Straight-line', 'Declining balance') (owner); `declining_factor_pct` REAL NULL (200 = double; required for Declining balance); `asset_account_id`,
  `accumulated_account_id`, `expense_account_id`; `acquisition_invoice_line_id` NULL (the bill line, Area 3); `clearing_id` TEXT NULL (the live "AST-S03"); `serial_text` NULL; `assigned_to_user_id`
  NULL; `charge_to_jobs_by_hour` INTEGER NOT NULL DEFAULT 0 and `hourly_rate_cents` NULL (stored here; the job-charging posting through `equipment_recovery_acct_id` is not designed here, §14);
  `disposal_id` NULL; `row_version`.
- **Rules:** cost and the acquisition posting come from the bill (Area 3): a bill line coded to the fixed-assets account creates or links an asset 'Not in service' and the cost is the
  line amount; depreciation starts the month the asset is placed in service and **the in-service month is taken in full** (live: a truck placed in service 03/15/2024 has 32 months of
  depreciation at 10/31/2026). Cost, life, method, in-service date and salvage change only until the first depreciation line posts; afterwards a change is refused and the fix is a
  correction or a disposal (posted lines are never edited). An asset in a posted disposal cannot be edited. Import assets (live "Import assets") uses the same service and needs the
  opening accumulated depreciation, which posts as one opening entry (planning proposal, Area 21's import).
- **No entity column (planning call, Q4):** a subsidiary is its own company database (S7); consolidated reports combine them by account code (E5).
- **Permissions:** `asset.create` creates and edits, `asset.view` reads, `asset.dispose` disposes, `asset.approve` (sensitive) approves a disposal; none in `AGENT_ALLOWED`.
- Tests (planning proposals): `test_asset_cost_and_salvage_are_integer_cents`, `test_asset_cost_comes_from_the_bill_line_not_a_typed_amount`,
  `test_depreciation_starts_the_in_service_month_taken_in_full`, `test_asset_terms_cannot_change_after_first_depreciation_posts`,
  `test_asset_number_is_service_assigned_and_never_reused`, `test_asset_requires_a_declining_factor_only_for_declining_balance`,
  `test_no_tax_depreciation_table_exists` (owner Q2), `test_asset_accounts_resolve_by_role_not_number`, `test_asset_has_no_entity_column`.

## 4. Depreciation

- **Straight-line (owner):** monthly charge from cumulative rounding, as Area 10 does: the cumulative charge after month *n* is round-half-up((cost - salvage) x *n* / life months); each month is that
  minus the prior cumulative, so the lines always sum to cost minus salvage with the last line taking the remainder. Live check: truck T-04, cost $58,400.00, life 60 months, no salvage, 32 months through
  October 2026: $58,400.00 x 32 / 60 = $31,146.67 accumulated.
- **Declining balance (owner; the switch is a planning reading):** each month charges round-half-up(the book value at the start of the asset year x (declining factor / life in years) / 12), where
  the asset year runs from the in-service month; never below salvage. **It switches to straight-line over the remaining months when that gives more.** Example (the owner's truck): $48,000.00, 5 years, factor
  200%: rate 40%; year 1 $1,600.00 a month = $19,200.00; year 2 book value $28,800.00 x 40% / 12 = $960.00 a month = $11,520.00; year 3 $6,912.00; at the start of year 4 the book value is
  $10,368.00: declining balance gives $345.60 a month, straight-line over the remaining 24 months gives $432.00, so it switches: years 4 and 5 are $5,184.00 each. The five years sum to $48,000.00.
- **`asset_schedule_line`** (the Area 10 `deferral_schedule_line` pattern; planning proposal): `line_id`; `asset_id`; `sequence`; `scheduled_date` (the period end); `posted_date` (the scheduled date, or the first open day
  for a catch-up); `period_id` NULL until posted; `amount_cents` CHECK > 0; `status` CHECK IN ('Scheduled', 'Posted', 'Caught up', 'Blocked', 'Reversed', 'Replaced'); `run_id` NULL; `entry_id`;
  `reversal_entry_id`; `blocked_reason`; `row_version`; UNIQUE (`asset_id`, `sequence`) WHERE `status` <> 'Replaced'. A Posted or Caught up line never changes except to Reversed (a trigger backs it, integrity).
  The live lines of an asset sum to cost minus salvage. The schedule is generated when the asset goes in service and regenerated (old lines Replaced) only before the first posting.
- **`depreciation_run`** (one per period; planning proposal): `run_id`; `period_id` UNIQUE; `entry_id` UNIQUE (the one entry of that month); `ran_at`; `ran_by`; `origin` CHECK IN ('Scheduled', 'Post now').
  Live: "October depreciation is 2026-00419", an entry link (the live number format predates L4: work order).
- **Posting (monthly run, `depreciation.py`):** runs on the last day of each open month, while the app is open with the owner signed in, and catches up once at the next sign-in (Area 10 Contracts Q2 A). Locked period:
  the line is Blocked with the lock sentence; "Post now" dates it the first open day (live: 12/01/2026) (Area 13 §1.4). One entry per run, one debit and one credit line per asset (keys `asset_id` on the lines).
  **Rule (planning fix):** the run skips assets Disposed on or before the run date, and a disposal's catch-up (§5) posts only when that month's run line for the asset has not posted; so a month is never charged twice.
  **Example, the November 2026 run** (all three assets still in service at the run, so no disposal has posted before it): Excavator E-02 $84,000.00 / 60 months = $1,400.00; truck T-04 $973.33 (33rd month: $58,400.00 x 33 / 60 = $32,120.00 less $31,146.67); scissor lift L-01 $22,500.00 / 60 = $375.00.

  | Account | Debit | Credit |
  |---|---|---|
  | Depreciation expense (role) | $2,748.33 | |
  | Accumulated depreciation, GL 1550 (role) | | $2,748.33 |

  (per asset lines: Excavator $1,400.00, Truck $973.33, Lift $375.00; the debits equal the credits.)
- **Close check `depreciation_run` (Area 13 §2.3, ships here):** passes when every In service asset has a Posted or Caught up line for the period; fails otherwise with the asset names; the checklist button is "Go to Run depreciation".
- **Locks:** area 'Fixed assets and depreciation' plus the accounts hit (Area 13 §1.4); a static test: every function that writes `journal_line` from this area calls the shared check.
- Tests: `test_straight_line_cumulative_rounding_sums_to_cost_less_salvage_and_last_month_takes_remainder`, `test_truck_t04_32_months_accumulates_31146_67`,
  `test_declining_balance_year_one_is_19200_for_the_48000_truck`, `test_declining_balance_switches_to_straight_line_when_that_gives_more`,
  `test_declining_balance_never_goes_below_salvage`, `test_monthly_run_posts_one_entry_with_a_line_per_asset_and_balances`,
  `test_run_in_a_locked_month_blocks_the_line_and_post_now_dates_the_first_open_day`, `test_missed_runs_catch_up_once_at_next_sign_in`,
  `test_posted_schedule_line_never_changes_except_to_reversed`, `test_depreciation_run_check_fails_until_every_in_service_asset_has_a_line`,
  `test_asset_schedule_monthly_totals_tie_to_gl_with_exact_entry_links_and_disposal` (ASSET-04), `test_depreciation_respects_period_area_and_account_locks`.

## 5. Disposals

- **`asset_disposal`:** `disposal_id`; `disposal_no`; `disposal_on` (must be in an open period; impossible dates refused before posting, owner); `how` CHECK IN ('Sold', 'Traded in', 'Scrapped', 'Lost or stolen', 'Donated', 'Insurance claim');
  `counterparty_contact_id` NULL (sold to or traded to); `proceeds_to` CHECK IN ('Bank account', 'Accounts receivable', 'Vendor bill credit'); `bank_account_id` NULL; `total_proceeds_cents` CHECK >= 0 (owner: negative refused); `allocation_basis`
  CHECK IN ('Book value', 'Original cost', 'Edited'); `status` CHECK IN ('Draft', 'Pending approval', 'Posted', 'Reversed'); `entry_id` UNIQUE NULL (the disposal entry); `catch_up_entry_id` UNIQUE NULL; `reversal_entry_id` NULL;
  `reverse_reason_code` / `reverse_reason_text` (OD-31, conditional CHECK); `approval_request_id` NULL; `operation_id` UNIQUE (an exact retry returns the first result and posts nothing twice); `row_version`.
  **`asset_disposal_line`:** `disposal_id`; `asset_id` (UNIQUE among non-Reversed disposals); `proceeds_cents` CHECK >= 0; `cost_cents`, `accumulated_cents`, `book_value_cents`, `gain_loss_cents` (frozen at posting).
  Company setting `disposal_month_convention` CHECK IN ('Full month', 'No depreciation in the disposal month') DEFAULT 'Full month' (live: "taken in full", A11-Q3 in §13).
- **Rules:** (1) **Unknown or already-disposed asset IDs are refused, naming the first missing one, and the whole disposal is blocked** (no fallback, no substitution). (2) **Catch-up depreciation runs through the disposal date first, only if that month's run line has not already posted (otherwise nothing is added, never a second charge),** as its own
  entry (`catch_up_entry_id`), only if the convention takes the month; book value, gain and loss are worked out after it. (3) **Allocation:** a lump sum is split by Book value, Original cost or typed lines (Edited); the lines must sum to the total
  proceeds to the cent (the last line takes the rounding); **a positive lump sum with zero total book value requires a per-asset allocation**: it cannot split by book value, so it defaults to Original cost and is editable (next_step). (4) Scrap may have $0 proceeds; **removal costs are a separate
  expense** (a bill), never netted into proceeds. (5) The disposal posts one entry and persists one durable result linked to it and to the catch-up entry; asset status becomes Disposed and its remaining schedule lines are Replaced (not posted).
  (6) **Reverse disposal** (`asset.dispose`, a reason): reverses the disposal entry (dated by the void rules, never into a closed period), puts the asset back In service and restores its remaining schedule lines; the catch-up depreciation stays (it was correct).
  (7) Proceeds to **Accounts receivable** or a **vendor bill credit** are created through Area 5's and Area 3's services (an invoice to the buyer, a vendor credit), each with one line crediting a new clearing role `asset_disposal_clearing_acct_id` that the disposal entry debits, so each
  subledger document stays its own (planning proposal; §14).
- **Approval (Area 14):** the 'Asset disposal' row is OFF by default; ON: the disposal is Pending approval, `asset.approve` (sensitive) approves, the final approval runs the shared lock check again (the kind posts on approval, Area 14 §6), and the digest covers the assets, date, proceeds, allocation and counterparty.
- **Postings, with real amounts (all balanced).** The three examples assume the disposal posts **before** the November run (the run then skips these assets, so the catch-up is the only November charge; the §4 run example assumes no disposal has posted, and if these two disposals post first that run would be the excavator's $1,400.00 only).
  1. **Sale at a gain.** Truck T-04 sold 11/30/2026 for $30,000.00 to the bank (cost $58,400.00; accumulated after the November catch-up $32,120.00; book value $26,280.00; gain $3,720.00).
     Catch-up entry: Dr Depreciation expense $973.33 / Cr Accumulated depreciation $973.33. Disposal entry:

     | Account | Debit | Credit |
     |---|---|---|
     | Bank (1010) | $30,000.00 | |
     | Accumulated depreciation (1550) | $32,120.00 | |
     | Fixed assets (1500) | | $58,400.00 |
     | Gain on disposal (role) | | $3,720.00 |

     Debits $62,120.00 = credits $62,120.00.

     **Same sale under "No depreciation in the disposal month" (owner A11-Q3):** no catch-up; accumulated depreciation stays $31,146.67; book value $27,253.33; gain $2,746.67. Entry: Dr Bank $30,000.00, Dr Accumulated depreciation $31,146.67 / Cr Fixed assets $58,400.00, Cr Gain on disposal $2,746.67 (debits $61,146.67 = credits $61,146.67).
  2. **Scrap at $0 with a removal cost.** Scissor lift L-01 scrapped 11/30/2026 (cost $22,500.00; $375.00 November catch-up; accumulated $4,125.00; book value $18,375.00). Disposal entry: Dr Accumulated depreciation $4,125.00, Dr Loss on disposal $18,375.00 / Cr Fixed assets $22,500.00
     (debits $22,500.00 = credits $22,500.00). The $200.00 hauling charge is its own bill: Dr Removal expense $200.00 / Cr Accounts payable $200.00, not part of the disposal.
  3. **Lump sum across assets.** Two fully depreciated assets, A (cost $5,000.00) and B (cost $3,000.00), sold together for $500.00: book value is zero, so the split is by Original cost: A $312.50, B $187.50 (sum $500.00). Entry: Dr Bank $500.00, Dr Accumulated depreciation $8,000.00 / Cr Fixed assets $8,000.00,
     Cr Gain on disposal $500.00 (debits $8,500.00 = credits $8,500.00); the gain splits $312.50 and $187.50 on the two disposal lines.
- **Locks:** period, area 'Fixed assets and depreciation' and the accounts hit (Area 13 §1.4); the approval step repeats it.
- Tests: `test_asset_disposal_reads_saved_asset_schedule_and_entry`, `test_asset_disposal_unknown_id_refused`, `test_asset_disposal_mixed_valid_unknown_ids_refuses_without_substitution`, `test_disposal_catch_up_depreciation_through_disposal_date`,
  `test_disposal_exact_retry_adds_no_duplicate_posting`, `test_disposal_accepts_zero_proceeds_for_scrapped_asset`, `test_disposal_rejects_negative_proceeds`,
  `test_disposal_positive_lump_sum_with_zero_total_book_value_requires_per_asset_allocation`, `test_lump_sum_split_sums_to_proceeds_with_rounding_in_the_last_line`,
  `test_disposal_respects_period_area_and_account_locks`, `test_disposal_approval_uses_area14_only_when_configured`, `test_disposal_impossible_date_refused_before_posting`,
  `test_sale_at_a_gain_posts_the_balanced_entry_30000_32120_58400_3720`, `test_scrap_posts_loss_18375_and_removal_cost_is_a_separate_bill`, `test_reverse_disposal_restores_asset_and_schedule_and_keeps_catch_up`,
  `test_disposal_month_convention_default_is_full_month`, `test_no_depreciation_in_the_disposal_month_gain_is_2746_67`, `test_catch_up_is_skipped_when_the_month_run_already_posted`, `test_run_skips_disposed_assets`, `test_disposal_proceeds_to_ar_creates_an_invoice_through_area5_and_clears_the_clearing_role`.

## 6. Loans

- **`loan`:** `loan_id`; `name`; `loan_type` CHECK IN ('Term loan', 'Line of credit', 'Vehicle loan'); `lender_contact_id` (a vendor, the bills' payee); `original_amount_cents` (the limit for a line of credit); `annual_rate_pct` REAL; `term_months` (NULL for a line of credit);
  `loan_date`; `first_payment_on`; `payment_cents` (computed, stored); `money_went_to` CHECK IN ('Deposited to a bank account', 'Paid to the dealer'); `deposit_bank_account_id` NULL; `linked_asset_id` NULL ("Add as fixed asset"); `bill_lead_days` CHECK IN (0, 5, 10, 15) DEFAULT 10 (live: 10);
  `pay_from_bank_account_id`; `loan_account_id` (2500 Loans payable, or 2510 Line of credit); `interest_account_id` (7100); `status` CHECK IN ('Active', 'Paid off', 'Closed'); `row_version`. Attachments (the loan agreement, note and amendments, each typed) through Area 18 (target 'Loan').
- **`loan_schedule_line`** (the same pattern as the asset schedule): `loan_id`; `payment_no`; `due_on`; `kind` CHECK IN ('Payment', 'Interest'); `payment_cents`; `interest_cents`; `principal_cents`; `extra_principal_cents`; `balance_after_cents`; `status` CHECK IN ('Scheduled', 'Bill drafted', 'Billed', 'Paid', 'Replaced');
  `invoice_id` NULL (the bill, Area 3); UNIQUE (`loan_id`, `payment_no`) WHERE `status` <> 'Replaced'; `row_version`. Interest = round-half-up(balance x annual rate / 12); principal = payment minus interest; **the last payment takes the remainder**.
- **`loan_draw`** (line of credit; insert-only): `loan_id`; `kind` CHECK IN ('Draw', 'Repayment'); `amount_cents` > 0; `occurred_on`; `bank_account_id`; `entry_id` UNIQUE; `operation_id` UNIQUE. Available = limit minus balance (live: $250,000.00 limit, $65,000.00 balance, $185,000.00 available). A line of credit has monthly **interest bills** (kind 'Interest'): balance x annual rate / 12
  on the month-end balance (planning proposal; daily accrual is open).
- **Each payment is drafted as a bill (planning call):** `loan_bills.run` (while the app is open, like the deferral runner) drafts the bill `bill_lead_days` before the due date through Area 3's bill service, to the lender, one line to the loan account (principal) and one to the interest account (interest);
  "Create bill now" drafts it early. The bill is only a draft; approval and posting follow Area 3 and Area 14's 'Bill' row. The loan's balance is the original amount less the principal on **posted** payment bills (plus draws, less repayments), and ties to the GL.
- **Postings, with real amounts (all balanced).**
  1. **Loan payment split.** Equipment loan, $120,000.00, 7.25%, 60 months, payment $2,390.32. Payment 21 (due 11/30/2026) on a balance of $84,300.00: interest $84,300.00 x 7.25% / 12 = $509.31; principal $1,881.01; balance after $82,418.99. The drafted bill, once approved: 

     | Account | Debit | Credit |
     |---|---|---|
     | Loans payable (2500) | $1,881.01 | |
     | Interest expense (7100) | $509.31 | |
     | Accounts payable (Cascade Valley Bank) | | $2,390.32 |

     The pay run then pays the bill (Dr Accounts payable / Cr Bank $2,390.32).
  2. **Extra principal (live payment 20).** Payment $2,390.32 plus $410.84 extra: interest $523.08, scheduled principal $1,867.24, extra $410.84; the bill is Dr Loans payable $2,278.08 (= $1,867.24 + $410.84), Dr Interest expense $523.08 / Cr Accounts payable $2,801.16; balance after $84,300.00. The remaining schedule lines are Replaced and recomputed
     from the new balance with the same payment (planning proposal).
  3. **Line of credit** (limit $250,000.00; **interest uses the month-end balance**). The balance is $50,000.00 on 11/01/2026. Record draw 11/10/2026 $15,000.00: Dr Bank $15,000.00 / Cr Line of credit (2510) $15,000.00; the month-end balance is $65,000.00 (available $185,000.00). November interest bill: $65,000.00 x 8.50% / 12 = $460.42: Dr Interest expense $460.42 / Cr Accounts payable $460.42.
     Repay principal 12/05/2026 $10,000.00: Dr Line of credit $10,000.00 / Cr Bank $10,000.00; the 12/31/2026 balance is $55,000.00 and the December interest is $55,000.00 x 8.50% / 12 = $389.58 (Dr Interest expense $389.58 / Cr Accounts payable $389.58).
  4. **Current and long-term reclass (§7).**
- **Origination (planning proposal for the bank-deposit case; the dealer case is owner A11-Q2, in this bullet):** deposited to a bank account: Dr Bank / Cr Loans payable (or Line of credit) for the amount, one entry from the loan service (source 'Loan'). **Paid to the dealer (owner A11-Q2):** the dealer's bill is entered as usual (Area 3), which creates the asset with its cost from the bill line; it is paid by a bank payment for any down payment plus a **"loan funded" payment**: Dr Accounts payable / Cr Loans payable, with no bank line (the Area 2 and Area 1 payment method list gains a shipped method 'Loan funded' that names a loan, not a bank account).
  **Example:** a $130,000.00 dealer bill = $10,000.00 down (Dr Accounts payable $10,000.00 / Cr Bank $10,000.00) + $120,000.00 loan funded (Dr Accounts payable $120,000.00 / Cr Loans payable (2500) $120,000.00); the bill posted Dr Fixed assets $130,000.00 / Cr Accounts payable $130,000.00, so Accounts payable nets to $0.00 and the loan starts at $120,000.00. There is no "Dr Fixed assets / Cr Loans payable" origination.
- **Pay off and close:** Pay off drafts a final bill for the remaining principal plus interest to the pay-off date (the amount the lender states, typed and checked against the schedule); a loan closes only at a $0.00 balance (live: "Pay it off first: the balance must be $0.00"); closed loans keep their history.
- **Locks and permissions:** area 'Loans' and the accounts hit (Area 13 §1.4); `loan.manage`, `loan.view` (existing); none in `AGENT_ALLOWED`; every change audit-logged.
- Tests: `test_loan_payment_interest_is_rate_over_12_of_balance_rounded_half_up_and_last_payment_takes_the_remainder`, `test_equipment_loan_payment_21_splits_509_31_interest_1881_01_principal`,
  `test_loan_payment_bill_is_drafted_the_lead_days_before_due_and_posts_nothing_until_approved`, `test_loan_bill_lines_post_principal_to_the_loan_account_and_interest_to_the_interest_account`,
  `test_extra_principal_recomputes_the_remaining_schedule_with_replaced_lines`, `test_line_of_credit_draw_and_repayment_post_to_2510_and_available_is_limit_less_balance`,
  `test_line_of_credit_interest_bill_is_balance_rate_over_12`, `test_loan_balance_ties_to_gl_loan_account`, `test_loan_cannot_close_until_balance_is_zero`,
  `test_loan_respects_the_loans_lock_area_and_account_locks`, `test_loan_draw_retry_with_same_operation_id_posts_once`, `test_loan_funded_payment_posts_dr_accounts_payable_cr_loans_payable_and_no_bank_line` (owner A11-Q2),
  `test_dealer_bill_with_down_payment_and_loan_funded_payment_leaves_accounts_payable_at_zero`, `test_no_origination_entry_debits_fixed_assets_directly`,
  `test_line_of_credit_interest_uses_the_month_end_balance` (the $65,000.00 then $55,000.00 sequence), `test_loan_run_drafts_bills_only_while_the_app_is_open_and_catches_up_once`.

## 7. Current and long-term split

- **Shown always (no posting):** the loan page and the balance sheet notes read the split from the schedule: the principal due in the next 12 months is the current part and the rest is long-term (live: balance $84,300.00 = current $23,337.45 + long-term $60,962.55).
- **Posted reclass is a Company control, OFF by default (owner A11-Q1):** `company_settings.loan_current_portion_reclass` DEFAULT 0 and a new role `loan_current_portion_acct_id` (Current portion of long-term debt, a liability; the chart template has one). ON: a month-end entry moves the change in the current part from Loans
  payable to that role (source 'Loan', one per loan per month, only the change after the first). **Example, first ON entry at 10/31/2026:** Dr Loans payable (2500) $23,337.45 / Cr Current portion of long-term debt $23,337.45. The loan tie-out then compares the balance with GL 2500 plus the current-portion role.
  The live loan page ties the balance to GL 2500 alone (work order: it must add the current-portion role when the control is ON). A line of credit has no scheduled principal, so it has no current part unless the lender states one (open).
- Tests: `test_loan_current_part_is_next_12_months_principal_from_the_schedule`, `test_current_portion_reclass_control_defaults_off_and_logs_a_reason`, `test_reclass_off_posts_nothing_and_balance_sheet_split_is_presentation_only`,
  `test_reclass_on_posts_only_the_change_each_month`, `test_loan_tie_out_adds_the_current_portion_role_when_reclass_is_on`.

## 8. Reads, reports and the close

- **Close checks (Area 13 §2.3):** `depreciation_run` (§4); a loans check (every bill due within the lead days is drafted) is a planning proposal, warn only.
- **Reports (Area 17 owns the screens; this area gives the sources):** the fixed-asset register (cost, accumulated depreciation, net book value) tying to GL 1500 and 1550; the depreciation schedule by month; the disposal list with gain and loss; the loan schedule, balance and current and long-term split; the cash flow lines
  (fixed assets investing, loans financing; the cash-flow statement decisions in docs/decisions_2026-11-11.md).
- **Tie-outs (integrity, always on):** asset cost = GL fixed assets; accumulated depreciation = GL accumulated depreciation; each loan balance = its GL account (plus the current-portion role when the reclass control is ON).
- Tests: `test_asset_cost_ties_to_gl_1500_and_accumulated_to_gl_1550`, `test_register_and_schedule_share_filters_and_dates`, `test_loans_close_check_warns_when_a_bill_is_not_drafted`.

## 9. Permissions, locks, row version and audit

- **Permissions:** existing `asset.create`, `asset.dispose`, `asset.approve` (sensitive), `asset.view`, `loan.manage`, `loan.view`; none in `AGENT_ALLOWED`. New (planning proposals): none; Post now uses `asset.create`.
- **Locks:** Area 13 §1.4 on every posting (depreciation, disposals, catch-up, reversals, loan entries); a draft bill is not a posting.
- **Row version** (Area 21): `fixed_asset`, `asset_class`, `asset_schedule_line`, `asset_disposal`, `loan`, `loan_schedule_line`. **Audit:** every table is audited by the trigger pattern; `depreciation_run` and `loan_draw` are insert-only; posted schedule lines are backstopped by a trigger.
- Tests: `test_asset_and_loan_permissions_are_not_in_agent_allowed`, `test_asset_approve_is_sensitive`.

## 10. How it lands in the baselines and code

- **Baseline (planning):** new tables `asset_class`, `fixed_asset`, `asset_schedule_line`, `depreciation_run`, `asset_disposal`, `asset_disposal_line`, `loan`, `loan_schedule_line`, `loan_draw`; `journal_line` gains a nullable `asset_id` key; `company_settings` gains
  `disposal_month_convention`, `loan_current_portion_reclass`, `fixed_assets_acct_id`, `accumulated_depreciation_acct_id`, `depreciation_expense_acct_id`, `loan_current_portion_acct_id`, `asset_disposal_clearing_acct_id`; `file_attachment.target_type` gains 'Loan' (Area 18 §3); the Area 3 bill line gains the link
  from `fixed_asset.acquisition_invoice_line_id`.
- **Code:** services `assets.py`, `depreciation.py`, `asset_disposals.py`, `loans.py`, `loan_bills.py`; no UI or HTTP imports (H1), no clock reads (H2: `context.now`), workflow rules in services (H4), no SQLite-only SQL (H5). Static tests: every function that writes `journal_line` calls the shared lock check;
  no tax depreciation table or column exists; nothing here calls the AI.
- **Existing tests change:** none known (no tables today).
- **Handoffs out:** Area 3 (the bill that becomes an asset and the loan payment bills); Area 5 and Area 3 (the proceeds invoice and trade-in credit); Area 13 (the `depreciation_run` check, the Loans lock area); Area 14 (the 'Asset disposal' digest); Area 17 (reports); Area 18 (system account roles, §8.1; attachment target);
  Area 21 (row versions, opening balances and import of assets and loans).

## 11. Integrity checks kept (always on)

Integer cents; balanced entries; a posted depreciation line is never edited; a disposal is refused for unknown or already-disposed assets, negative proceeds and impossible dates; catch-up depreciation precedes gain or loss; an exact retry never double posts; period, area and account locks apply; asset cost and accumulated depreciation tie to the GL;
loan balances tie to the GL; no tax depreciation is stored; the AI never posts or approves.

## 12. Conflicts with decisions, the baseline or the mockups (flagged)

1. **Loan tie-out versus the current-portion reclass:** live ties the balance to GL 2500 alone; with the optional reclass ON it must add the current-portion role (§7, work order).
2. **The live journal entry number "2026-00419"** predates the L4 format JE-000NNN (work order).
3. **Disposal month (resolved, owner A11-Q3):** live takes the month in full; the Company setting offers Full month (default) and No depreciation in the disposal month.
4. **Proceeds to AR or a vendor credit** (live creates an invoice or uses the vendor's bill): this area routes them through Area 5 and Area 3 with a clearing role (§5).
5. **The baseline has no asset or loan account roles;** the mockups map GL 1500, 1550, 2500, 2510 and 7100 (roles resolve from the chart template).
6. **Area 14's 'Asset disposal' row** exists; the digest and the lock-at-approval rule are applied here (§5).
7. **"Charge to jobs by the hour"** (live New asset form) has a posting (`equipment_recovery_acct_id`) that no approved area designs; stored here only (§14).

## 13. Questions for the owner (recommended option first, with an example; **all answered 2026-11-25 2:09 AM, section 15**)

- **A11-Q1. Is the current and long-term split posted or shown only?** (A) Shown from the schedule always; a Company control posts a month-end reclass, OFF by default (recommended: graduated controls). (B) Always post it monthly. Example: $23,337.45 moves from Loans payable to Current portion of long-term debt at 10/31/2026 only with the control ON.
- **A11-Q2. A loan paid directly to the equipment seller.** (A) **[REMOVED by the owner answer, §15]** one origination entry with no seller bill (not chosen). (B) Enter the seller's bill in Area 3 and pay it with a "loan funded" payment. Example: the $120,000.00 excavator loan paid to the dealer.
- **A11-Q3. Disposal month conventions.** (A) Ship Full month (live default) and No depreciation in the disposal month (recommended). (B) Full month only. Example: truck sold 11/30/2026: November's $973.33 is taken under Full month and skipped under the other.
- **A11-Q4. "Charge to jobs by the hour".** (A) Store the flag and hourly rate on the asset now; the job-charging posting is designed with the job cost areas later (recommended). (B) Design the posting here. Example: excavator $85.00 an hour x 6 hours = $510.00 charged to the job, credited to equipment recovery.

## 14. Open items (not decisions)

- The mechanics of the proceeds clearing role for a sale on account or a trade-in credit (§5). (A loan paid to the dealer is settled: owner A11-Q2.)
- **Job charging for equipment by the hour** (the `equipment_recovery_acct_id` posting) stays open for job costing (owner A11-Q4: store the flag and hourly rate only).
- Daily-accrual interest on a line of credit; a payoff quote from the lender; prepayment penalties and loan closing costs (the chart has a Loan Closing Costs account).
- Leases, capitalized interest, partial disposals (selling part of an asset), asset revaluation and impairment: not covered.
- Mid-month in-service conventions (the live convention is the full in-service month).
- Opening balances and the import of existing assets and loans: Area 21.

## 15. Owner answers 2026-11-25 2:09 AM and two planning fixes (dated amendment; §13 stays as asked)

- **A11-Q1 (owner):** the current and long-term split is shown from the schedule always; a posted month-end reclass is a Company control, OFF by default (§7).
- **A11-Q2 (owner):** a loan paid to the dealer is the dealer's bill entered as usual (it creates the asset, cost from the bill line), paid by a bank payment for any down payment plus a "loan funded" payment, Dr Accounts payable / Cr Loans payable.
  Example: $130,000.00 bill = $10,000.00 down + $120,000.00 loan funded. The "Dr Fixed assets / Cr Loans payable" option is removed (§6). A test checks the loan-funded payment posts no bank line.
- **A11-Q3 (owner):** a Company setting with Full month (default, live) and No depreciation in the disposal month. The truck example: Full month gain $3,720.00; the other $2,746.67 (§5).
- **A11-Q4 (owner):** store the flag and hourly rate only; the job-charging posting stays open for job costing (§14).
- **Planning fix 1:** the November run and the November catch-up could charge the same month twice. Rule (§4, §5): the run skips assets disposed on or before the run date; a catch-up posts only when that month's run line has not posted; the disposal examples assume the disposal posts before the run. Tests added.
- **Planning fix 2:** the line-of-credit example now runs $50,000.00 + $15,000.00 draw = $65,000.00 month-end (interest $460.42), then a $10,000.00 repayment = $55,000.00 (December interest $389.58); interest uses the month-end balance (§6).

- **Amendment 2026-11-25 (pointer, Area 21 draft; Planning reading, owner may correct): opening assets and loans.** Opening assets and loans enter through the conversion batch (Area 21 §5); the opening accumulated depreciation posts as one entry per asset because owner item 6 forbids a summary entry (changes the 'one opening entry' proposal, Area 21 Q3 open). `row_version` and the stale-save refusal are Area 21 §3 (`tx.update_versioned`, `StaleVersionError`, mapped to `conflict`; insert-only tables exempt).

- **Amendment 2026-11-25 (pointer, Area 21 revision; owner A21-Q3): [Updated: replaces the "posts as one opening entry" proposal at line 93 and the pointer above, which said Q3 open.]** Opening accumulated depreciation posts as one entry per asset, linked to the asset; example: the truck, cost 5,840,000, its own entry Dr OBE / Cr Accumulated depreciation 3,114,667 (book value 2,725,333).
