# Inventory and fixed assets: design draft (revision 2)

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
Conventions follow CLAUDE.md: integer cents for money (`*_cents`), quantities
and hours may be REAL, ISO text dates, booleans 0/1, UTC `_at` timestamps,
all writes through service functions, posted records locked, corrections by
reversing entries, no raw SQL writes from the UI or the AI agent.

CONFIRMED by the user (2026-11-10):
- Depreciation expense must trace to the specific asset in the ledger. It is
  never a manual or lump-sum journal entry.
- Inventory is designed for construction cost accounting (job-centric), not
  for retail stock.
- (rev 3) Average, FIFO and specific-cost methods are all available, chosen
  per item.
- (rev 3) Materials delivered to a job are expensed to the job and count
  toward percent complete.
- (rev 3) Stock pulled without a job number becomes an employee material
  advance, cleared by a cost report to job numbers.
- (rev 3) Stock can also be bought at the point of sale (Home Depot, card).
- (rev 3) Trucks and equipment are depreciated assets. No tax depreciation
  in the app.
- (rev 3) Capitalization rules live in an external rule book. A bill line
  coded to an asset account posts as an asset. A policy_rule table holds the
  rules for people and the AI agent.
- (rev 3) Item codes and asset tags are manual. The AI may suggest; a person
  can override.
- (rev 4) Returns to the warehouse have their own entry screen, coded to job
  numbers, which reduces job cost at the cost originally charged.
- (rev 4) Lot AND serial tracking are fully supported by the schema.
- (rev 4) Charging equipment and trucks to jobs by the hour is a designed
  option (4.4), off by default.
- (rev 4) Vendor credits can be turned into a refund request that is billed
  to the vendor and settled with cash received (section 6B).
- (rev 4) An employee's open material advance can be expensed, collected, or
  allocated to jobs at month end; finance chooses (3.7).

Everything else is PROPOSED. The live schema wins on naming: check
`journal_line` and `invoice_line` in the database before building.

---

## 1. Principles

1. Each subledger ties out to the general ledger, per asset and per item, not
   only in total. Tie-outs are views plus a period-close check.
2. Subledger movements are append-only. A mistake is fixed by a reversing
   movement or entry, never an edit or delete.
3. Closed periods block new movements and new depreciation.
4. Controlled accounts (section 2) accept lines only from their subledger.
   A person cannot type a journal entry into them, and a journal file
   cannot be imported into them.
5. Every ledger line that comes from a subledger carries a real foreign key
   back to the source row. The ledger is traceable in both directions.
6. Job costs carry project and cost code at the ledger line, not only on the
   invoice header.
7. The AI agent may propose receipts, counts, assets and disposals. It never
   posts or approves them (origin / actor_type fields apply).
8. Business rules live in the service layer so the hosted version can reuse
   them. Triggers are only a backstop.

---

## 2. Ledger changes shared by both areas

**journal_line: new optional columns** (real foreign keys; added by table
rebuild after the subledger tables exist, since SQLite allows the circular
reference)
- `project_id` -> project, `cost_code_id` -> cost_code
- `quantity` REAL, `uom_id` -> unit_of_measure (opt; for job unit costs)
- `asset_id` -> fixed_asset
- `depreciation_line_id` -> depreciation_line
- `inventory_movement_id` -> inventory_movement
- `equipment_usage_id` -> equipment_usage (PROPOSED, see 4.4)
- Only one of `depreciation_line_id`, `inventory_movement_id`,
  `equipment_usage_id` may be set on a line.

**account: new `control_type`** [None, Inventory, Employee material advance,
Fixed asset cost, Accumulated depreciation, Depreciation expense, Equipment
cost recovery].

**Posting rule for controlled accounts** (service layer, with a test per row;
a trigger backstop is PROPOSED):

| control_type | Line must carry | Entry origin |
|---|---|---|
| Inventory | `inventory_movement_id` | System |
| Employee material advance | `inventory_movement_id` | System |
| Fixed asset cost | `asset_id` | System |
| Accumulated depreciation | `asset_id` and `depreciation_line_id` | System |
| Depreciation expense | `asset_id` and `depreciation_line_id` | System |
| Equipment cost recovery | `equipment_usage_id` | System |

- The manual journal entry screen does not list controlled accounts. The
  posting function rejects them if they arrive anyway (including from an
  import or the AI agent).
- A reversing entry copies the source keys, so a reversal still traces to the
  same asset or movement.
- Accounts used for the other side of a bill (accounts payable, cash) are
  not controlled.

---

## 3. Inventory (construction cost accounting)

### 3.1 How construction uses material

1. **Direct to job.** Material bought for one job. Cost goes to the job on
   the bill, with the quantity kept for unit-cost reporting. No stock
   balance. This is the most common case.
2. **Stocked.** Bought for general use, held in a shop, yard or truck, then
   issued to jobs. Stock is an asset until it is issued.
3. **Pulled from stock for a job.** The person pulling gives the warehouse
   manager the job number and cost code. Cost is expensed to the job when it
   leaves the warehouse (delivery) and counts toward percent complete
   (confirmed). There is no "job site inventory" balance: material at a job
   is already job cost. Leftovers come back as a Return from project or move
   to another job as a Job transfer.
4. **Pulled without a job number.** Not allowed to sit unassigned. It is
   booked as an employee material advance (3.6) against the person, and
   cleared by a cost report that assigns it to job numbers. "Truck inventory"
   is the open advance balance, by employee and item.
5. **Bought at the point of sale** (Home Depot, company card). The purchase
   arrives through Ramp staging. The approver codes each line as one of: Job
   cost (Direct to job), Stock receipt, Employee advance, Expense, or Fixed
   asset. The AI may propose; a person approves.

Every issue or direct purchase for a job needs `project_id` and
`cost_code_id`. Nothing is charged to a job without them.

### 3.2 New tables

**unit_of_measure**: `uom_id`, `code` (EA, LF, SF, CY, BOX), `name`.
One UOM per item in v1; conversions deferred.

**item**
- `item_id` PK, `item_code` unique, `name`, `description`
- `item_type` [Stock, Non-stock, Service]
- `uom_id`
- `costing_method` [Average, FIFO, Specific] (defaults to the company
  setting; locked once the item has movements)
- `tracking_type` [None, Lot, Serial] (default None; see 3.10)
- `inventory_account_id` (Stock; an Inventory control account)
- `default_cost_code_id` -> cost_code (the material cost code on a job)
- `waste_pct` REAL (opt; used by estimates and takeoff only)
- `reorder_point` REAL (opt), `is_active`
- Cost of goods sold is not on the item. A job issue charges the cost
  code's account. COGS applies only when stock is sold over the counter
  (rare for a contractor; `cogs_account_id` and `income_account_id` are
  optional).
- Items with movements can be made inactive, never deleted.

**location**: `location_id`, `name`, `kind` [Warehouse, Yard], `is_active`.
Only places the company owns stock count as locations. Trucks and job sites
are not locations (see 3.1 and 3.6).

**item_balance**: `item_id`, `location_id` (unique together), `qty_on_hand`
REAL, `value_cents`. Maintained in the same transaction as each movement.
Average cost = value / quantity; the last unit absorbs rounding.

**inventory_lot** (a batch of identical units received under one batch
number)
- `lot_id`, `item_id`, `lot_number` (unique with `item_id`), `manufacturer_lot`
  (opt), `vendor_contact_id` (opt), `received_date`, `expiry_date` (opt),
  `notes`, `is_active`

**inventory_serial** (one unique unit)
- `serial_id`, `item_id`, `serial_number` (unique with `item_id`), `lot_id`
  (opt), `status` [In stock, Issued to job, With employee, Returned to vendor,
  Scrapped], `current_location_id` (opt), `current_project_id` (opt),
  `current_contact_id` (opt; employee), `unit_cost_cents`, `warranty_end_date`
  (opt), `asset_id` -> fixed_asset (opt; when the serialized unit is a
  capitalized tool or equipment)

**inventory_movement_tracking** (which lots and serials a movement touched)
- `movement_id`, `lot_id` (opt), `serial_id` (opt), `quantity` REAL
- Rules: a Serial item has quantity 1 per row and a whole-number movement
  quantity; a Lot item's rows add up to the movement quantity; an item with
  `tracking_type` None has no rows.

**inventory_cost_layer** (one row per receipt; used by all three methods)
- `layer_id`, `item_id`, `location_id`, `receipt_movement_id`,
  `received_date`, `qty_received`, `qty_remaining`, `unit_cost_cents`
- `lot_id`, `serial_id` (opt; set when the item is tracked)
- Average: cost comes from `item_balance`; layers are still kept.
- FIFO: issues consume the oldest layer with quantity remaining.
- Specific: the person (or the serial/lot) picks the layer.

**inventory_layer_consumption** (append-only): `movement_id`, `layer_id`,
`quantity`, `cost_cents`. Every issue records which layers it used, so a
return can be credited at the cost that was actually charged.

**inventory_movement** (append-only; the material subledger)
- `movement_id` PK, `item_id`, `movement_date`, `period_id`
- `movement_type`:
  - Receipt (bill for stock; Dr Inventory)
  - Direct to job (bill straight to a job; no stock)
  - Issue to project (stock leaves for a job)
  - Issue to employee (stock leaves with no job number; creates an advance)
  - Advance clearing (cost report assigns advance stock to a job)
  - Advance return (employee returns advance stock to the warehouse)
  - Return from project (job returns stock)
  - Job transfer (move cost from one job to another)
  - Transfer out / Transfer in (between locations)
  - Return to vendor
  - Adjustment (count variance)
  - Waste (scrap charged to a job or overhead)
  - Opening balance (conversion from another system)
- `quantity` REAL (positive; type gives direction)
- `unit_cost_cents`, `total_cost_cents`
- `location_id` (opt), `to_location_id` (opt)
- `project_id`, `cost_code_id` (required for job types)
- `to_project_id` (Job transfer only)
- `contact_id` -> contact (opt; the employee for advance movements)
- `invoice_line_id` (opt; source bill line), `count_line_id` (opt)
- `reverses_movement_id` (opt)
- `entry_id` -> journal_entry
- `origin` [Human, Agent, Import, System], `created_by` (plain integer)

**material_allocation** (reserve stock for a job from the estimate or takeoff)
- `allocation_id`, `project_id`, `cost_code_id`, `item_id`, `qty_planned`,
  `qty_issued` (maintained), `estimate_line_id` (opt), `status` [Open, Closed]

**inventory_count / inventory_count_line**: header `count_id`, `location_id`,
`count_date`, `status` [Draft, Approved, Posted], `approved_by`, `entry_id`;
line `item_id`, `counted_qty`, `system_qty`, `variance_qty`,
`variance_cost_cents`. A human approves; variances post as Adjustments.

### 3.3 Changes to existing tables

- `invoice_line`: add `item_id` (opt), `quantity` already exists, add
  `project_id` (opt), `cost_code_id` (opt), `location_id` (opt).
- `estimate_line` and `project_budget`: add `item_id` (opt), `quantity` and
  `uom_id`, so budget quantity can be compared with actual quantity.
- `company_settings`: `inventory_costing_method` (default for new items:
  Average, Fifo or Specific), `allow_negative_inventory` (default 0),
  `advance_review_days` (PROPOSED; advances older than this are flagged).

### 3.4 Posting rules

| Event | Debit | Credit |
|---|---|---|
| Receipt to stock | Inventory | Accounts payable |
| Direct to job | Job cost (cost code account) | Accounts payable |
| Issue to project | Job cost (cost code account) | Inventory, at average cost |
| Return from project | Inventory | Job cost, at the ORIGINAL issue cost |
| Job transfer | Job cost, receiving job | Job cost, sending job |
| Waste | Job cost (waste cost code) or overhead | Inventory |
| Count shortage / overage | Inventory adjustment / Inventory | Inventory / adjustment |
| Return to vendor | Accounts payable | Inventory |
| Issue to employee (no job) | Employee material advance | Inventory |
| Advance clearing (cost report) | Job cost (cost code account) | Employee material advance |
| Advance return | Inventory | Employee material advance |
| Point-of-sale purchase coded to an employee | Employee material advance | Accounts payable or card |
| Over-the-counter sale | Cost of goods sold | Inventory |

- Job cost lines carry `project_id`, `cost_code_id`, `quantity` and `uom_id`.
- Issues leave stock at average cost; they never use the latest bill price.
- A return from a job uses the cost of the movement it reverses, so the job
  is credited what it was charged.
- Negative stock is blocked unless `allow_negative_inventory` is 1.
- A project can only receive movements when its current stage allows costs
  (`allows_costs`, per the CRM design) and it is not Closed or locked.
  A warranty issue goes to the service case, never to the closed job.
- Invoice lines on POC or completed-contract projects create no COGS entry;
  revenue follows the contract.
- Freight on a bill is coded to the job or an expense line; landed-cost
  allocation to items is deferred.

### 3.5 Rules

1. One movement = one balanced journal entry in the same transaction.
2. Movements need an open period and a project allowed to take costs.
3. Receipts update average cost: new value = old value + receipt cost, new
   quantity = old quantity + received quantity.
4. Location transfers write two movements and no entry when both locations
   share the same inventory account.
5. Tie-out: sum of `item_balance.value_cents` = GL balance of Inventory
   control accounts. Tie-out for jobs: cost by project and cost code from
   movements = ledger lines with the same project and cost code.
6. A closing project must have no stock left in its Job site locations
   (return it to stock or transfer it to another job first). This is a
   proposed item in the close checklist.
7. Material issued to a job counts toward percent complete (confirmed). The
   existing `cost_code.counts_toward_progress` flag stays, so a cost code can
   still be excluded later if a CPA requires it (uninstalled material is a
   known cost-to-cost review point).

### 3.6 Employee material advances (truck inventory)

- Stock that leaves the warehouse without a job number is an advance against
  the person who took it (`contact_id`, quantity, cost). It is an asset of
  the company (a receivable from the employee), not job cost and not
  inventory.
- The advance is tracked by item and employee (quantity and cost), so the
  open balance is the "truck inventory". It does not need a truck location.
- **material_cost_report**: `report_id`, `contact_id` (employee), `report_date`,
  `status` [Draft, Submitted, Approved, Posted], `approved_by`, `entry_id`.
  **material_cost_report_line**: `report_id`, `item_id`, `quantity`,
  `project_id`, `cost_code_id`. Posting writes Advance clearing movements
  that charge the jobs and reduce the advance. Leftovers are returned with an
  Advance return.
- Approval is by a person. The AI may draft a report from receipts or
  notes but never approves or posts.
- Projects must allow costs (`allows_costs`) and not be Closed.
- Review: the open-advance report lists balance, age and the oldest pull per
  employee. Items older than `advance_review_days` are flagged. Payroll
  deduction for unreturned material is NOT designed.
- Tie-out: advance quantity and cost by employee = GL balance of the
  Employee material advance accounts.

### 3.7 Open advances at separation or month end

Finance decides what happens to an advance an employee has not cleared.
Nothing is automatic; a person approves.

**advance_disposition**: `disposition_id`, `contact_id` (employee),
`disposition_date`, `method` [Expense, Collect from employee, Allocate to
jobs], `amount_cents`, `status` [Draft, Approved, Posted], `approved_by`,
`entry_id`, `reason`, `origin`.

| Method | Debit | Credit |
|---|---|---|
| Expense | Unreturned material expense (overhead) | Employee material advance |
| Collect from employee | Employee receivable | Employee material advance |
| Allocate to jobs | Job cost per project (cost code) | Employee material advance |

- **Collect from employee:** moves the balance to an employee receivable.
  Cash back, or a payroll deduction, is handled outside the app by finance
  and recorded as a normal receipt against the receivable. A payroll
  deduction import is NOT designed.
- **Allocate to jobs (month end):** **advance_allocation_line**
  (`disposition_id`, `project_id`, `cost_code_id`, `amount_cents`, `basis`).
  The basis is each eligible project's share of REVISED CONTRACT VALUE
  (original contract plus approved change orders); the last project absorbs
  rounding. Eligible projects are those given the PM status "Completed" in
  the month. "Completed" is a Closeout-group stage that still allows costs:
  the job stays open for late vendor bills and is not locked until it is
  Closed. A Closed project cannot take the charge. If no project qualifies in
  the month, the balance stays open and is flagged.
- The month-end review screen lists every open advance with age, employee
  status and a suggested method from `policy_rule`. A person approves each
  one or approves all.
- A separated employee's balance is flagged. If finance does nothing, it
  stays open and appears on the open-advance report; it is never silently
  expensed.
- Movements: Advance write-off (to expense), Advance clearing (to jobs).
  Quantities are relieved with the amount.

### 3.8 Returns to the warehouse (entry screen)

A fast, keyboard-driven screen for the warehouse manager. One session can
hold many lines and many jobs.

**Header:** return date, returned by (employee), warehouse location, return
slip number (automatic).

**Line:** item (search or scan), quantity, **job number and cost code**
(required unless the return is from an employee advance), lot or serial (if
the item is tracked), reason [Unused, Wrong item, Over-ordered, Job
cancelled, Defective, Other], condition [Resalable, Damaged].

**What the screen shows and enforces:**
- After the job and item are chosen, it lists what was issued to that job:
  quantity issued, already returned, still returnable, and the cost per unit.
  The cost is read-only. It is the cost the job was charged, taken from the
  layers the issue consumed.
- Quantity cannot exceed what is still returnable on that job and item.
  Lot and serial must be among those issued to that job.
- Source can be Job (Return from project, credits the job) or Employee
  advance (Advance return, no job needed, credits the advance).
- Resalable returns go back into stock at the original cost. Damaged
  returns are not restocked; they are charged to the Waste movement for
  the job or overhead account the finance team sets.
- A preview shows the job cost reduction before saving.
- The entry date is the return date (open period). Past periods are never
  reopened.
- A return to a Closed job is blocked. Jobs stay open after the PM marks them
  Completed (see section 6), so this should not come up.
- Printable return slip; the project manager sees the credit on the job.
- The AI agent may draft a return from a photo or note; only a person saves.

### 3.9 Buying at the point of sale (job costing suggestions)

Job coding at the register is the hard part, so do not require it there.
Ranked from most to least useful:
1. **Capture by cardholder, code later.** Every card purchase defaults to an
   employee advance for that cardholder. The job is assigned on the weekly
   material cost report. Perfect coding at the register is not needed.
2. **Ask for the job where it is cheap.** Where the store or card program
   lets the buyer add a job or PO name at checkout (many commercial accounts
   do), or a note in the card app, use it. The receipt then carries the job
   number for the AI to read. Verify what Ramp and the store support.
3. **AI proposes the job.** The agent reads the receipt lines and suggests a
   job from the employee's assigned active projects and past coding, with a
   confidence and rationale. A person approves in staging. Splits across
   several jobs use `staged_line`.
4. **Job-specific cards or limits** for large or single-job buys, so those
   purchases arrive already tied to a job.
5. **Weekly cadence.** The cost report is due weekly; open advances are
   flagged after `advance_review_days`.
6. **Small consumables pool.** Items under a threshold (screws, tape) are
   coded to a supplies pool and allocated to completed projects at month end
   with the same allocation tool as 3.7.

### 3.10 Lot and serial tracking

- Each tracked item is set to Lot or Serial in `tracking_type`. Untracked
  items are unaffected.
- Every receipt of a tracked item creates its lots or serials (and the
  cost layer for each). Every issue, return, transfer, advance and vendor
  return names the lot or serial it touched in `inventory_movement_tracking`.
- A serial can be in one place at a time. Its `status` and current
  location, job or employee are updated by the same service function that
  writes the movement.
- Specific costing uses the lot or serial's own layer. FIFO can be first
  expiry first out (FEFO) for items with an expiry date (PROPOSED option).
- A serialized unit can be linked to a fixed asset (tools, generators) so
  warranty, location and depreciation share one record.
- Traceability reports: where was lot X used (jobs, dates), which jobs have
  serial Y, units on hand by lot, items expiring soon, warranty ending soon.
- Service cases can look up the serials and lots installed on the parent job.

### 3.11 Views

Job material cost by project and cost code (with quantity and unit cost),
budget vs actual quantity by item, material issued and returned by job,
stock on hand and value, stock staged on job sites, reorder list, valuation
tie-out, shrinkage by count.

---

## 4. Fixed assets

### 4.1 New tables

**asset_class**: `class_id`, `name`, `asset_account_id`,
`accum_depr_account_id`, `depr_expense_account_id` (each a controlled
account), `default_life_months`, `default_method`, `default_salvage_pct`,
`charge_to_jobs` 0/1 (PROPOSED, see 4.4).

**fixed_asset**
- `asset_id` PK, `asset_tag` unique (auto; PROPOSED 'FA' + 4+ digit sequence
  from an `asset_number` table, same method as customer codes)
- `name`, `class_id`, `description`, `serial_number`, `vendor_contact_id` (opt)
- `acquisition_date`, `in_service_date`
- `cost_cents`, `salvage_cents`
- `opening_accum_depr_cents`, `opening_date` (conversion only; see below)
- `source_line_id` -> invoice_line (opt; the bill line that bought it)
- `location` TEXT, `assigned_to_contact_id` (opt)
- `status` [Draft, In service, Fully depreciated, Disposed]
- `disposal_date`, `disposal_proceeds_cents`, `disposal_entry_id` (opt)

**asset_book**: `asset_id`, `book_type` (only 'Book' in v1; no tax
depreciation), `method` [Straight-line, Double-declining balance],
`life_months`, `salvage_cents`, `convention` [Full month] (mid-month is a
later option), `switch_to_straight_line` 0/1 (default 1; Double-declining
only), `expected_annual_hours` REAL (opt; used for equipment hourly rates).

**Depreciation methods (both built in v1)**
- **Straight-line:** (cost - salvage) / life, spread evenly by month; the last
  period absorbs rounding.
- **Double-declining balance (PROPOSED mechanics):** the annual amount for a
  fiscal year is the net book value at the start of that year x 2 / life in
  years; each month in that year takes 1/12 of it. The first year is
  prorated by full months in service. Depreciation never goes below salvage.
  With `switch_to_straight_line` on, the schedule changes to straight-line
  over the remaining life in the first year where that gives a larger amount
  (the standard approach). The last period absorbs rounding.
- A schedule is computed by a service function from the book row, so future
  annual depreciation can be read before it is posted. Only posted months are
  stored as `depreciation_line`. Changing cost or life (an improvement)
  recalculates the remaining months going forward; posted months are never
  changed.
- The method is chosen by the person when the asset is put in service, on
  the fixed asset screen. The default is Straight-line (about 90% of assets).
  The method is locked once any depreciation is posted. Tax depreciation is
  done outside the books and is not part of this design.

**asset_event** (append-only): `event_id`, `asset_id`, `event_type`
[Acquired, Opening balance, Placed in service, Improvement, Transfer,
Impairment, Disposed], `event_date`, `amount_cents`, `entry_id`, `note`,
`origin`, `created_by`.

**depreciation_run**: `run_id`, `period_id` (unique), `status` [Draft,
Posted], `entry_id`, `approved_by`, `posted_at`.

**depreciation_line** (the expense record for ONE asset in ONE period)
- `depreciation_line_id` PK, `asset_id`, `book_type`, `period_id`, `run_id`
- `amount_cents`, `accum_after_cents`, `net_book_value_after_cents`
- Unique on (asset_id, book_type, period_id)

### 4.2 How depreciation reaches the ledger

- A run creates one `journal_entry` per period, but never a lump sum. For
  every `depreciation_line` it posts two ledger lines:
  - Debit the class depreciation expense account, with `asset_id` and
    `depreciation_line_id`.
  - Credit the class accumulated depreciation account, with the same keys.
- The general ledger therefore shows depreciation by asset. Total
  depreciation by class is a sum of lines, not a typed number.
- The entry has `origin = System`. The depreciation expense and accumulated
  depreciation accounts reject any line that does not carry the keys
  (section 2). A manual or uploaded journal entry cannot touch them.
- Reversing a run writes reversing lines that copy the same `asset_id` and
  `depreciation_line_id`.
- Per-asset tie-out: ledger accumulated depreciation by `asset_id` =
  `opening_accum_depr_cents` + sum of its depreciation lines. Any difference
  is flagged at period close.
- Depreciation in the ledger is traceable to asset class, location, vendor,
  in-service date and (if allocated, see 4.4) job.

### 4.3 Other posting rules

| Event | Debit | Credit |
|---|---|---|
| Purchase | Asset account (with `asset_id`) | Accounts payable or cash |
| Improvement | Asset account (with `asset_id`) | Accounts payable or cash |
| Opening balance (conversion) | Asset account; accumulated depreciation is credited | Opening equity (system account) |
| Depreciation run | Depreciation expense (with `asset_id`) | Accumulated depreciation (with `asset_id`) |
| Disposal | Cash, accumulated depreciation, loss | Asset account, gain |

- A bill line coded to an asset-class account posts as an asset. The posting
  function creates the fixed asset in the same transaction (status Draft, not
  in service) and the ledger line carries its `asset_id`. The bill is never
  blocked. A person completes the asset later (class, in-service date, life);
  nothing depreciates until then, and a report lists Draft assets.
- Nothing depreciates until the asset is In service.
- Disposal posts depreciation up to the disposal date first (full month in
  the month of disposal, PROPOSED), then removes cost and accumulated
  depreciation and books gain or loss against proceeds.
- Opening balances: assets already owned when the company converts are loaded
  as assets with `opening_accum_depr_cents`; the opening entry is posted by
  a service function, with `asset_id` on every line. No lump-sum opening JE.
- No threshold is hard-coded. Capitalization rules come from the company's
  own rule book and are stored in `policy_rule` (section 6A).

### 4.4 Charging equipment and trucks to jobs by the hour (OPTION, off by default)

Switched on by `company_settings.equipment_charging_enabled` and, per class,
`asset_class.charge_to_jobs`. When off, depreciation stays overhead.

**equipment_rate** (effective-dated)
- `rate_id`, `asset_id` (opt) or `class_id` (opt) (an asset rate wins over a
  class rate), `rate_cents` per hour, `includes_operator` 0/1,
  `effective_from`, `effective_to` (opt)
- `rate_basis` [Depreciation per hour, Fixed]. For Depreciation per hour:
  rate = annual book depreciation for the fiscal year / expected annual hours
  (`fixed_asset.expected_annual_hours`, falling back to the class default),
  rounded to cents. The rate is stored on the row at the time it is
  calculated.
- A "Recalculate equipment rates" action (run by a person at the start of each
  fiscal year, or after a cost, life or hours change) writes a new
  effective-dated rate row. It never changes an old row. With double-declining
  depreciation the rate falls each year.
- The rate covers depreciation only. Fuel, repairs and insurance are not in
  it (an optional add-on per hour is a later option).

**equipment_usage** (one row per asset per job per day)
- `usage_id`, `asset_id`, `project_id`, `cost_code_id` (an Equipment code),
  `usage_date`, `period_id`, `hours` REAL, `rate_cents` (copied from the rate
  in effect), `amount_cents` (hours x rate, rounded to cents)
- `operator_contact_id` (opt), `source` [Manual, Timesheet, Import]
- `status` [Draft, Approved, Posted], `approved_by`, `entry_id`,
  `reverses_usage_id` (opt), `origin`, `created_by`

**Posting** (per usage row, carrying `equipment_usage_id` and `asset_id`):
- Debit job cost (cost code account, with project and cost code).
- Credit Equipment cost recovery (a contra-expense account).
- Depreciation expense is unchanged. The company-wide expense is the same;
  recovery moves it onto jobs.

**Rules**
1. The asset must be In service and not Disposed on the usage date, and its
   class must allow job charging.
2. Hours per asset per day cannot exceed 24 across all jobs.
3. The project must allow costs and not be Closed.
4. A rate is copied onto the usage row; later rate changes never alter
   posted usage.
5. Posted usage is locked; corrections are reversing rows.
6. Charges count toward percent complete unless the cost code is excluded.

**Views:** recovery vs depreciation vs maintenance by asset (under- or
over-recovered), hours by asset and job, utilization, truck cost per job.
Billing equipment to customers (time and materials with billing rates) is NOT
designed.

### 4.5 Rules

1. A depreciation run covers one open period and posts one entry.
2. Posted depreciation lines are locked. A mistake is fixed by a reversing
   run or in the next period.
3. An asset with posted depreciation can only be Disposed, never deleted.
4. Depreciation never exceeds cost minus salvage.
5. Cost and depreciation ledger lines always carry the asset key.
6. Straight-line and double-declining balance are both built in v1; there
   is no tax book and no units-of-production method.
7. Every service function that posts is covered by a test for each row of the
   controlled-account table.

### 4.6 Views

Asset register, depreciation by asset and period (from ledger lines),
depreciation schedule (past and future), net book value by class and asset,
disposals with gain/loss, assets nearing fully depreciated, per-asset tie-out
to the ledger, equipment recovery vs depreciation (if B).

---

## 5. Placement and effort

- Test data only today, so the schema can be rebuilt. New tables arrive as
  numbered migrations after 003 (PROPOSED: 004 CRM/PM, 005 ledger line keys
  and controlled accounts, 006 inventory with lots, serials, advances and
  returns, 007 fixed assets with equipment charging, 008 vendor refunds),
  each with failing tests first.
- Migration 005 is the dependency for 006, 007 and 008: the ledger line columns
  and `account.control_type`.
- Services (receive, issue, return, transfer, count, depreciate, dispose)
  come after Phase 2. Posting for inventory and depreciation comes with the
  double-entry posting phase.
- Order inside each area: tables and constraints, service functions, screens.
- Not designed: purchase orders and receiving without a bill (GRNI),
  subcontract commitments, pay applications, landed cost, lot/serial
  tracking, assemblies/kits, UOM conversions, time-and-materials billing
  with markup, equipment hours from telematics.

---

## 6. Interaction with other designs

- CRM/PM: no job costs before signing (`allows_costs`); Closed projects
  never take movements; warranty material goes to the service case.
- POC: cost to date = ledger job cost lines for the project on cost codes
  flagged `counts_toward_progress`.
- Completed vs Closed: the PM marks a job Completed (Closeout group; still
  open for costs, such as late vendor bills). A month-end review with the
  PMs decides, for each Completed job, either Keep open or Close out. Only
  Close out locks the job (after the closing checklist). Closed jobs take no
  movements, returns, usage or allocations.
- Staging/AI: a bill or Ramp line for a Stock item or an asset-class account
  is staged with the item or asset proposed; a person approves before posting.
- Deferrals: unaffected.

---

## 6A. Policy rules (for people and the AI agent)

Capitalization and coding rules come from the company's own rule book
(for example "expense anything under X unless it is a vehicle"). They are
entered by a person and stored so the posting screens and the AI agent can
use them.

**policy_rule**
- `rule_id`, `rule_type` [Capitalization, Coding, Inventory vs expense,
  Approval, Other]
- `scope_type` [Company, Account, Asset class, Vendor, Cost code, Item] and
  `scope_id` (opt)
- `title`, `rule_text` (the rule in the company's words)
- `threshold_cents` (opt; a structured amount for rules that have one)
- `effective_from`, `effective_to`, `is_active`
- `created_by`, `created_at`

How it is used:
- Deterministic checks run first. A rule with `threshold_cents` and a scope
  can flag a line (for example an asset-class line under the threshold)
  without any AI.
- The AI agent reads active rules as context, applies them in its
  suggestion, and cites the rule in the suggestion's rationale.
- Rules only propose. A person can always override; the override and the
  rule it overrode are logged. The rules never block a posting by themselves.
- Rules are edited by a person only, never by the agent.

---

## 6B. Vendor credits and refunds

Sources of a vendor credit: a vendor credit memo, an advance payment larger
than the bill, a return to vendor, an overpayment. Today the credit sits as a
debit balance in accounts payable. This design turns it into something finance
can collect.

**vendor_refund**
- `refund_id`, `refund_number` (automatic), `contact_id` (the vendor)
- `request_date`, `amount_cents`, `received_cents` (maintained)
- `status` [Draft, Requested, Partly received, Received, Applied to bills,
  Written off, Cancelled]
- `source_invoice_id` (opt; the credit memo or bill), `source_deferral_id`
  (opt; the advance), `reference`, `notes`, `requested_by`, `entry_id`

**Flow**
1. **Vendor Credits screen:** lists vendors with credit balances and their
   sources. Select the credits to chase.
2. **Request refund** (a "bill to the vendor" for the balance): creates a
   `vendor_refund`, prints or emails a request statement. Posting moves the
   amount out of accounts payable into **Vendor refunds receivable**
   (Dr Vendor refunds receivable, Cr Accounts payable), so payables show the
   true amount owed.
3. **Receive cash:** a payment with direction Received from the vendor,
   allocated to the refund (`payment_allocation.refund_id`). Dr Cash,
   Cr Vendor refunds receivable. Partial receipts keep the status Partly
   received.
4. **Alternative:** apply the credit to a later bill instead (status Applied
   to bills; reverses the reclass).
5. **Write-off:** a person approves the remaining balance to an expense or
   variance account with a reason. Logged.

**Rules**
- This is NOT a customer invoice, so the vendor does not need a customer
  code. Invoices to contacts still require a customer code.
- A payment allocation points to an invoice or bill, a deferral, or a
  refund, never more than one on the same row.
- Receipts and write-offs are locked once posted; fixes are reversing entries.
- A vendor with an open refund is flagged on the vendor screen and on new
  payments to them (a person may net them).
- The advance-payment mismatch below produces a vendor credit by this path.

**Views:** open vendor credits by vendor and age, refund requests outstanding,
cash received against refunds, write-offs.

---

## 7. Decisions and open questions

Decided (user, 2026-11-10): the items marked (rev 3) and (rev 4) above, plus:
1. Costing: all methods available (Average, FIFO, Specific), per item.
2. Stock can be bought at the point of sale (card); coded at approval.
3. Pulled stock needs a job number; otherwise an employee advance.
4. Delivered material is expensed to the job and counts toward progress.
5. Trucks and equipment are depreciated assets; no tax depreciation.
6. Capitalization rules come from an external rule book (policy_rule).
7. Item codes and asset tags are manual; the AI may suggest.
8. A bill with an asset-class line posts as an asset (never blocked).
9. Returns have their own screen, charged back to job numbers.
10. Lot and serial tracking are both supported.
11. Equipment and trucks can be charged to jobs by the hour (option).
12. Vendor credits become refund requests with cash received against them.
13. Open employee advances: finance chooses expense, collect, or month-end
    allocation to jobs.

Also decided (2026-11-10, later): month-end advance allocation is by share of
revised contract value, across projects with the PM status "Completed" that
month; equipment rate = annual book depreciation / expected annual hours;
depreciation methods are straight-line and double-declining balance.

Also decided (2026-11-10, final round): returns to a Closed job are simply
blocked; Completed does not mean Closed; the depreciation method
(Straight-line or Double-declining) is chosen per asset when it is put in
service; tax depreciation is outside the books.

Still open:
1. Default depreciation convention beyond full month (mid-month later?).
2. Payroll deduction import for collected advances (not designed).
3. PM side: add "Completed" (Closeout group, `allows_costs` = 1, not locked)
   before "Closed", and a month-end PM review screen (Keep open / Close out)
   to docs/crm_pm_design.md.

### Advance-payment mismatch (settled)

A "paid in advance" deferral starts with a payment; the bill arrives later and
attaches with no new ledger entry.

- Bill larger than the payment (paid 12,000; bill 12,400): the payment covers
  12,000 and the bill keeps 400 open as a normal payable.
- Bill smaller than the payment (paid 12,000; bill 11,600): the bill is
  covered and 400 becomes a vendor credit, handled by section 6B (refund
  request, apply to a later bill, or write-off).
- No variance account by default; a person may write off a difference with a
  reason, which is logged.
- Until resolved, the bill shows "Partly covered by advance".
