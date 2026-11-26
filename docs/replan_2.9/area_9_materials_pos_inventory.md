# Step 2.9 schema replan, area 9: Materials, units, purchase orders, subcontracts and inventory

Status: **DRAFT 2026-11-24, awaiting owner approval; revised 2026-11-24 for the owner answers of 11:30 to 11:43 PM to §16 (section 18).** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise**. PROPOSED items in the sources are not built as final.

Sources read (only these, searched by section, date or code):
- Owner answers 2026-11-24 11:05, 11:15, 11:25, 11:30 and 11:35 PM on the Area 9 outline (commit e7bd1bd) and the
  answers headed 11:35 PM+, 11:40, 11:43, 11:45, 11:50, 11:55 PM and 12:00 AM on the draft 8e90b0d, §16 Q1 to Q7
  (Strata_Teams `inbox/to_owner.md`, read-only; the entry times were estimated and corrected there, the answers
  are unchanged).
- docs/next_step.md: "Area 9, Materials, POs and inventory" (item 18, OD-04, OD-51, the 2:20 AM forecast input, the
  12:41 PM field request input), "Area 9 (Materials, POs, inventory, warehouse; must-fix inputs)", Area 11's handoff
  line, "Area 14" lines.
- docs/po_ap_matching_design.md (all; DESIGN ONLY, items marked decided are used as decided) and the "Purchase
  orders and PO-to-AP matching" summary in docs/design_decisions.md.
- Approved areas, by section: 3 (§4.3 subcontract boundary, O1, `invoice_line` FKs, retainage, waivers, over-limit),
  6 (§3.4, cost lines, OD-80), 7 (commitments read-only, cost types, leaf-only cost codes, Q20), 8 (§12.3 forecast),
  10 (`original_item_ref`), 13 (§1.4 lock check, §2.3 checks `received_not_billed_aged`, `material_advances_open`,
  `stock_count`), 14 (rows 'Purchase order' and 'Subcontract', §7 digests), 18 (roles, permissions, system account
  roles, §8.6), 17 (reports).
- `migrations/001_company.sql`: `cost_code`, `estimate_cost_line.unit_of_measure`, `company_settings` account roles
  (`grni_acct_id`, `retainage_payable_acct_id`, `inventory_adjustments_acct_id`), permission seeds `po.*`,
  `subcontract.approve`, `receiving.*`, `inventory.*`, `document_approval_setting`.
- Live mockups (read-only, StrataLedger_mockups): `units.html`, `pages/units.js`, `ui/sl-lists.js` (the 10 default
  units, MAT-101 to MAT-105), `design_log.md` 2026-11-24 (MAT-105), `inventory.html`, `inventory-item.html`,
  `pages/inventory.js` (64 items, units, SKUs, average cost).
- Decision codes by grep: OD-04, OD-51, OD-80, STOCK-03, C129, RP5, H1-H5, R-rules cited below.

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | Units | A company-editable `unit_of_measure` list in the company file: **add and deactivate, never delete, never rename a used unit (owner)**. Deactivated units are hidden from new picks and shown on every document that used them. |
| 2 | Material codes | `material_code` (MAT-nnn, service-assigned): description, vendor, vendor SKU, our SKU, unit, **a cost code that drives every line (owner)**, a **default unit cost** used only to price POs and estimates, optional stocked flag. A stocked item IS a material code (one list, planning proposal). |
| 3 | Stock tracking | A Company control, **OFF by default (owner)**. Off: materials are charged straight to the job, no stock pages, pull tickets or `stock_count` close task. |
| 4 | One commitment record | `purchase_order` with `po_type` Materials or Subcontract **(owner)**: one approval row set (Area 14), one commitment rule (starts on Send, Mark as sent or Print), one matching rule. Subcontracts add a retainage rate, lien waivers and a schedule of values, with their own number series. |
| 5 | Receipts and accounting | Warehouse receipts (Dr Inventory / Cr GRNI) and job-site delivery tickets (Dr Job cost / Cr GRNI), both at actual PO cost: **no purchase price variance on receipt (owner)**. A bill clears the accrual; a price difference on stock splits between stock value and a new "Stock price differences" expense account **(owner; made a controlled account by planning reading)**. Commitments post nothing. |
| 6 | Field requests | A PM raises a material request; a line may be free text "to be coded" **(owner)**; purchasing codes it before it can go on a PO. Stock is reserved only when a pull ticket is created. |
| 7 | Cost code rule | **A line that uses a material code takes that code's cost code, read-only on the line (owner).** Free-text lines pick their own. Saved lines never change when a material code is re-pointed. |
| 8 | Matching | **A Company control, OFF by default (owner)**; ON compares each bill with its PO and receipt (15% price and amount before tax, quantity exact); over tolerance needs an override and an OD-31 reason. **A bill line matched to a PO line takes the PO line's job and cost code, locked (owner).** |
| 9 | Costing | **Each company picks moving average or FIFO once, locked after the first stock history (owner)**; no LIFO, no standard cost. |
| 10 | Reads | Open quantity by expected date (Area 8 forecast), commitments read only sent POs (Area 7), received-not-billed and stock tie to the GL. |

---

## 1. Current state

- **Baseline:** no purchase order, receipt, stock or material tables exist. `purchase_order_subcontract` is mentioned
  in the PO design as header-only and dropped in the fresh rebuild. `document_approval_setting` has 'Purchase order'
  and 'Subcontract' rows (OFF). Permission seeds exist: `po.create`, `po.approve` (sensitive), `subcontract.approve`
  (sensitive), `po.view`, `receiving.stock`, `receiving.jobsite`, `inventory.pull`, `inventory.adjust`,
  `inventory.count`, `inventory.view`. `company_settings` has `grni_acct_id`, `retainage_payable_acct_id` and
  `inventory_adjustments_acct_id`, but no inventory asset role, no stock price differences role and no job-materials role
  (Area 7 Q20 names `job_materials`, 5030).
- **Units:** `estimate_cost_line.unit_of_measure` is free text (a comment suggests "Bags", "Board Feet"); there is no
  units table. The live mockup `units.html` keeps ten built-in units plus units a company adds in browser storage
  (`localStorage` key `sl-units`), refuses duplicates ignoring case, caps a unit at 10 characters and has no delete,
  rename or deactivate. That page is a prototype lead default, not an owner rule (owner 11:05 PM).
- **Material codes:** the mockup list holds MAT-101 to MAT-105 and others in `ui/sl-lists.js` (code, description,
  vendor, SKU, unit, cost code, unit cost in cents); MAT-105 is "Racking rail kit, 14 ft", Sunbelt Panel Supply,
  SPS-RK14, unit kit, cost code 03-100, $300.00 (PO 1042). Area 6 §3.4 waits for `material_code` and keeps
  `estimate_cost_line.material_code_id` a plain integer until then.

## 2. Decided (owner) and carried forward

- **Units (owner 11:05 PM):** add and deactivate. A unit is never deleted; a unit used on a document is never renamed.
  A deactivated unit is hidden from new picks (material codes, PO lines, estimate lines) and still shows on every
  document that used it. Example: "cnt" is retired; PO 1042 and older estimates still show it; a new PO line cannot
  pick it. This settles OD-51. Units live in the company file, never in browser storage.
- **Stock tracking (owner 11:15 PM):** a Company control, OFF by default. Off: materials are charged straight to the
  job; no stock pages, pull tickets or `stock_count` close task. On: adds stock, pull tickets and `stock_count`.
- **Subcontracts (owner 11:25 PM):** one commitment record with two types, Materials and Subcontract; the same
  approval, commitment and PO-to-AP matching rules; a commitment starts on Send, Mark as sent or Print.
- **Field requests (owner 11:30 PM):** a PM may request an item with no material code as a free-text "to be coded"
  line, with its job and cost code; purchasing creates or picks the material code before that line can go on a PO.
- **Cost code (owner 11:35 PM):** "cost code is driven by the material code, the cost code should autofill the cost
  code unchangeable on the line level." A line that uses a material code (PO, estimate, material request) takes that
  code's cost code and cannot change it; to cost an item elsewhere, use or create a material code with that cost code.
- **PO matching (owner 11:30 PM):** a Company control, OFF by default, as on live Settings > ERP ("Match bills to purchase
  orders"). ON: each bill is compared with its PO and receipt; a difference over the tolerance (live: 15%, price and
  amount before tax; quantity always exact) needs an override and a reason (OD-31). Example: a $4,200.00 PO billed at
  $4,900.00 (16.7% over) needs an override only with the control ON. This replaces the PO design's "matching ON for
  everyone".
- **Costing (owner, answer headed 11:45 PM):** each company picks its stock costing method once, moving average or
  FIFO, in company setup or when stock tracking is first turned on; locked once the first stock item has history; both
  built and tested; no LIFO, no standard cost. Examples: average, 10 inverters at $2,150.00 + 6 at $2,230.00 = 16 at
  $2,180.00 and each pull charges $2,180.00; FIFO, the next 10 pulled cost $2,150.00 each, then $2,230.00.
- **Every PO line needs a material code (owner, answer headed 11:50 PM; scope "every Materials PO line" is a planning reading, Subcontract lines §6.1):** no free-text lines on a PO; a one-off item, freight
  or rental needs a material code first, and the line takes that code's cost code (locked). Example: "Crane hire, 1 day"
  $1,800.00 needs a material code.
- **Bill lines (owner, answer headed 11:55 PM; "cost code is coming from the material code, so 1 it's going to come from the
  PO"):** a bill line matched to a PO line takes the PO line's job and cost code and AP cannot change it on the bill;
  price-difference, freight and tax rows on that bill go to the same job and cost code. Example: PO 1042, MAT-105,
  03-100, $300.00, billed at $310.00: the bill line and its $10.00 difference both post to 03-100.
- **Units (owner, answer headed 12:00 AM):** a deactivated unit can be reactivated; it shows in new picks again and
  history records who did it and when.
- **Request line recoded (owner 11:40 PM):** when purchasing codes a free-text request line with a material on a different cost
  code, the line takes the material's cost code and the PM is told; the request shows both ("PM picked 16-100, now 16-200")
  and history keeps the PM's original pick.
- **Price difference on stock (owner 11:43 PM):** a bill's price difference on stock already received splits: the part for
  units still on hand changes stock value; the part for units already used posts to a "Stock price differences"
  expense account; job costs already charged do not change. Example: 100 rails at $30.00 ($3,000.00); 60 pulled, 40 on
  hand; bill at $32.00 ($3,200.00): $80.00 (40 x $2.00) raises stock value and $120.00 (60 x $2.00) posts to Stock price
  differences. On a job PO the difference posts to the PO line's job and cost code.
- **Carried forward (earlier owner or approved decisions):** commitment starts only on a successful send, Mark as sent
  or Print; drafts, approved-but-unsent POs and failed sends stay uncommitted; Close remainder releases the unreceived
  commitment (item 18, PORDER-01 and 04). A warehouse issue is job costed at the pull ticket; direct-to-site
  deliveries need a delivery ticket (po design §10 items 1, 2, 8). Stock is reserved only when the pull ticket is
  created, and the PM creates material requests (owner 2026-11-22 12:41 PM and design chat). A return credits job cost
  on the account the original issue used (STOCK-03). Commitments post nothing to the ledger. Only a person approves
  a PO or an override; the AI never approves.

---

## 3. Units

- **`unit_of_measure`** (planning proposal): `unit_id` PK; `code` TEXT NOT NULL, a unique index on lower(trim(`code`)) (no SQLite-only collation, H5), CHECK length
  1 to 10 after trim (lead defaults, owner may revise: 10-character maximum, duplicates refused ignoring case);
  `is_active` INTEGER NOT NULL DEFAULT 1; `is_shipped` INTEGER; `sort_order` INTEGER; `row_version`.
- **Shipped defaults (lead defaults, owner may revise):** ea, ft, kW, hr, ls, box, cnt, day, sf, kit (the mockup's
  ten), in that order; company units are listed after them. The "kW" spelling is a lead default. **OD-51's text lists
  six units with "kw"; this draft uses the live ten and "kW" (conflict flagged, §15).**
- **Foreign keys:** `material_code.unit_id`, `purchase_order_line.unit_id`, `estimate_cost_line.unit_id` (replacing the
  free text `unit_of_measure`), `material_request_line.unit_id`; receipts and pull tickets read the line's unit.
  OD-04's rule that the UOM column of the Material codes table is the authoritative list is **replaced** by this table
  (OD-51 amended it; the owner's 11:05 PM answer settles it).
- **Services** (`units.py`): `add_unit`, `deactivate_unit` and `reactivate_unit` (owner: a deactivated unit can be turned back on; the audit log records
  who and when, for deactivating too). Rules: add refuses a
  blank, over-long or duplicate code (the sentence names the existing unit); deactivate keeps the row and hides it
  from every picker (`list_active_units`); a pick query for a new line filters `is_active = 1`, while any document
  read joins the unit regardless of `is_active`. **There is no delete and no rename of a used unit:** renaming is
  allowed only for a unit no document row references, which the service checks in one query; a no-delete trigger on
  `unit_of_measure` follows the existing "never deleted" pattern (an integrity rule like `approval_request`'s, so a
  trigger and not a service rule is allowed under H4, as in Area 7).
- **Permission:** the permission that edits other Settings > Lists (Area 18 names it; one proposed code
  `list.manage` if none exists). Units are not a Control; the change is audit-logged, with no reason required
  (Area 18 Q15 A: reasons are for controls).
- **Migration of existing text units** (rebuild of dev databases only; no released data): each distinct text unit in
  `estimate_cost_line` becomes a company unit in the same pass; the script trims, merges units that differ only by
  case, and reports any unit over 10 characters for a manual pick instead of truncating it.
- **Mockup work order (design queue, not written here):** `units.html` gains Deactivate and Show inactive; units move
  from `localStorage` to the company file; pickers hide inactive units but still show them on saved documents.
- Tests (planning proposals): `test_add_unit_refuses_blank_over_10_characters_and_duplicate_ignoring_case`,
  `test_deactivated_unit_hidden_from_new_picks_but_shown_on_existing_documents`,
  `test_unit_is_never_deleted`, `test_deactivated_unit_can_be_reactivated_and_audit_records_who_and_when`, `test_used_unit_cannot_be_renamed`, `test_unused_unit_can_be_renamed`,
  `test_shipped_units_seeded_in_order_with_kW_spelling`,
  `test_units_come_from_company_file_not_browser_storage` (a static test: no `localStorage` units in the shipped
  front end), `test_estimate_cost_line_unit_is_a_foreign_key`.

## 4. Material codes

- **`material_code`:** `material_id` PK; `code` TEXT NOT NULL UNIQUE (service-assigned, 'MAT-' plus at least three
  digits, never reused, never renumbered, like vendor and customer codes); `description` NOT NULL; `vendor_id` NULL
  (preferred vendor); `vendor_sku` NULL; `item_sku` NULL (planning proposal: our own SKU, unique when set; the live inventory page's PNL-440,
  against the vendor's SPS-440-BLK); `reorder_point` REAL NULL (the live inventory page; planning proposal); `is_service`
  INTEGER NOT NULL DEFAULT 0 (planning proposal: a service code such as crane hire has no receipt, so its PO lines are two-way); `unit_id` NOT NULL; **`cost_code_id` NOT NULL (an active leaf cost code, RP5)**;
  `default_unit_cost_cents` INTEGER NOT NULL CHECK >= 0 (integer cents, rule 1; **renamed from "standard unit cost": it only
  prices new PO and estimate lines and is never a stock or posting cost**, planning reading of the 11:45 PM answer); `is_stocked` INTEGER NOT NULL DEFAULT
  0 (meaningful only while stock tracking is ON); `is_active` DEFAULT 1; `row_version`. Area 6's "default cost code"
  (C129, §3.4) is **replaced** by this driving cost code (owner 11:35 PM); a pointer goes to Area 6.
- **Rules:** create and edit need `po.create` or the Purchasing permission Area 18 assigns; a code cannot be deleted,
  only made inactive (inactive codes stay on old documents, as units do); changing a code's unit is refused once any
  saved line uses it (the line's unit is the saved unit); changing a code's cost code is allowed and **does not change
  any saved line** (planning reading). A cost code cannot be deactivated or made a non-leaf while an active
  material code points to it: the service names the codes (planning proposal; follows RP5's leaf rule).
- **MAT-105:** "Racking rail kit, 14 ft", Sunbelt Panel Supply, SPS-RK14, kit, 03-100 (Panels and racking),
  30,000 cents. On every PO, estimate and request line it takes 03-100 and cannot change it.
- **Item table for Area 10:** `reclass_line.original_item_ref` becomes `original_material_id` (FK to
  `material_code`, NULL for a non-material line) in the same pass (Area 10 handoff).
- **Tests:** `test_material_code_number_service_assigned_never_reused`,
  `test_material_code_requires_active_leaf_cost_code`,
  `test_material_code_cost_code_change_does_not_change_saved_lines`,
  `test_material_code_unit_change_refused_once_used`,
  `test_cost_code_with_active_material_code_cannot_be_deactivated`,
  `test_material_code_is_never_deleted_only_inactive`, `test_default_unit_cost_is_integer_cents_and_prices_lines_only`,
  `test_stocked_item_is_a_material_code_not_a_separate_item_table`, `test_item_sku_unique_when_set`.

## 5. Stock tracking control

- **Control** `company_settings.stock_tracking` INTEGER NOT NULL DEFAULT 0 (**owner: OFF by default**); Controls page
  (Admin or Master, audit-logged with a reason, Area 18 Q15 A). The existing mockup control "Require pull tickets to
  take stock" (OFF) is `company_settings.require_pull_tickets` INTEGER NOT NULL DEFAULT 0 and **applies only while
  stock tracking is ON** (planning reading 11:15 PM); with tracking OFF it is not shown.
- **OFF:** a material code's `is_stocked` is ignored; receipts are job-site delivery tickets only (Dr Job cost / Cr
  GRNI) or no receipt at all (two-way); no stock location, no stock page, no pull ticket, no reservation, no
  `stock_count` check.
- **ON:** `is_stocked` material codes receive to a location (Dr Inventory / Cr GRNI), are issued by pull ticket (Dr Job
  cost / Cr Inventory) and appear in stock counts. Turning it ON never changes posted entries; turning it OFF with
  stock on hand is refused until on-hand is zero or an Admin posts a count adjustment to zero (planning proposal).
- **Sample company (planning reading, owner may correct):** has it ON: 64 items = GL 1310 Inventory $214,850.00; the live inventory
  pages stay as they are. **Reconciliation with the live mockups (read-only check, planning proposal: one list):** a
  stocked item IS a material code with stock tracking on; there is no separate item table, so the 64 inventory items are 64
  stocked material codes. Today the mockups disagree: the inventory page shows 5 of its 64 items (PNL-440, INV-12K,
  RAIL-14, WIRE-10-500, EMT-1-10) and `pages/inventory.js` links those five to material codes by an internal SKU, while the
  shared list `SL_LISTS.materials` holds 18 codes (12 in the page's own fallback list); the other 59 items have no
  material code, and their internal SKU differs from the vendor SKU (hence `item_sku` in §4). **The New inventory item
  unit picker lists each, roll, box, ft, sheet, bundle, square, pallet, kit and lot, which is not the ten-unit list**
  (ea, ft, kW, hr, ls, box, cnt, day, sf, kit): only ft, box and kit match, "each" is shown for "ea", and roll, sheet,
  bundle, square, pallet and lot are not defaults. Planning proposal: the picker reads the company's active units; the
  sample company adds roll, sheet, bundle, square, pallet and lot as its own units (or the owner adds them to the shipped
  defaults, §17). Design-queue work order: give the 59 items material codes and a unit from the list.
- **Costing method (owner):** `company_settings.stock_costing_method` CHECK IN ('Moving average', 'FIFO'), set in company
  setup or when tracking is first turned on, **moving average pre-selected** (planning reading; the mockups show
  "Costing: Average cost"); **locked once any `stock_movement` exists** (the service refuses a change; "once the first stock
  item has history"). No LIFO, no standard cost.
- Tests: `test_stock_costing_method_picked_once_and_locked_after_first_movement`,
  `test_costing_method_offers_only_moving_average_and_fifo`, `test_moving_average_preselected`,
  `test_stock_tracking_defaults_off_and_audit_logged_with_reason`,
  `test_stock_off_has_no_pull_ticket_stock_page_or_stock_count_check`,
  `test_require_pull_tickets_only_applies_when_tracking_on`,
  `test_stock_turned_off_with_stock_on_hand_refused`, `test_stock_on_adds_stock_count_close_check`.

## 6. Purchase orders and subcontracts: one commitment record

### 6.1 Header and lines

- **`purchase_order`:** `po_id`; `po_number` (see the "Number series" bullet below); **`po_type` CHECK IN ('Materials', 'Subcontract') (owner)**;
  `vendor_id` NOT NULL; `project_id` NULL (NULL only for a stocked-materials PO, so required while stock tracking is OFF); `contract_id` NULL (subcontract's
  prime contract, Area 4); `issue_date`; **`expected_on` NULL (Area 8 §12.3)**; `status` CHECK IN ('Draft', 'Pending
  approval', 'Approved', 'Sent', 'Partially received', 'Received', 'Closed', 'Cancelled'); **`committed_at` NULL
  (set when the status first becomes 'Sent')**; `sent_method` CHECK IN ('Email', 'Printed', 'Marked as sent'),
  `sent_by`, `sent_at`; `retainage_pct` REAL NULL (Subcontract only, one rate per subcontract: R29's rule, Area 3);
  `revision_no`; `approval_request_id` NULL; `terms`; `closed_at`, `close_reason_code` and `close_reason_text` (Close remainder); `origin`;
  `row_version`. (The design doc's value 'Purchase' becomes 'Materials' (owner 11:25 PM); its status list gains
  'Pending approval' and 'Sent' to match item 18.)
- **`purchase_order_line`:** `po_line_id`; `po_id`; `line_no`; `line_type` CHECK IN ('Item', 'Subcontract
  work'); `material_id` NULL (**NOT NULL on every Materials PO line, owner**; NULL on a Subcontract work line); `description`; `quantity` REAL; `unit_id`; `unit_cost_cents`; `amount_cents` (service:
  round-half-up of quantity x unit cost, the same rule as every other service); `project_id`; **`cost_code_id` NOT
  NULL**; `account_id` (the cost code's `account_id`, which Area 7 fills from its cost type's default role, or Inventory for a
  stocked line when tracking is ON); `expected_on` NULL (per-line override); `match_type` CHECK IN ('Two-way', 'Three-way') (Three-way for a stocked or delivered material; Two-way for a service code and a subcontract line); `tax_rate_id`;
  `request_line_id` NULL; `scheduled_value_cents` (Subcontract work lines: the SOV, a subcontract line's value);
  `row_version`. Service-type lines (freight, rental, crane hire) are Item lines on a material code with `is_service` = 1 (owner: they
  need a material code). **Planning proposal, not asked: a Subcontract SOV line carries a cost code and no material code**
  (example SC-014 line 1, 01-500, $24,000.00). CHECK (`line_type` = 'Item') = (`material_id` IS NOT NULL); the service refuses a
  line whose type does not match the PO's `po_type`.
- **`purchase_order_change` and `purchase_order_change_line`:** approved changes to a PO or subcontract: `change_no`,
  `status` ('Draft', 'Pending approval', 'Approved', 'Rejected'), `amount_delta_cents`, optional `change_order_id`
  (the project change order, Area 8); **revised commitment = original + approved changes**; pending ones are excluded;
  an approved change locks; a fix is a new change (po design §3). Approval uses the 'Purchase order' or 'Subcontract'
  row (Area 14).
- **Subcontract extras (planning reading, 11:25 PM):** `retainage_pct`, the SOV (`scheduled_value_cents` per line),
  lien waivers (Area 3's `lien_waiver`, ON by default for subcontracts, OFF for suppliers via
  `contact.requires_lien_waivers`, as on live), draws (Area 3's `sub_draw`), and `subcontract_id` FKs in Area 3 point to
  `purchase_order` where `po_type` = 'Subcontract'. A subcontract has no receipts (two-way matching).
- **Number series (planning reading):** `po_number_sequence` per type; PO numbers like 1042, subcontracts like SC-014; a
  number is assigned at first save, never reused, gaps allowed for deleted drafts (the voucher rule, decision 1.3).

### 6.2 Commitment (owner and item 18)

- A PO or subcontract commits (job and cost code) **only on a successful Send, Mark as sent or Print**; `committed_at`
  and `sent_method` are set in the same transaction as the status change. A failed send writes nothing and leaves the
  status. Drafts, 'Pending approval' and 'Approved' (unsent) POs are uncommitted. Close remainder releases the
  unreceived commitment: `closed_at`, a reason from the Reasons list (for example "Job cancelled") or Other with at least 10 typed
  characters (Area 18 §8.7, Q26 A; the CHECK is conditional: `close_reason_code <> 'Other' OR length(trim(close_reason_text))
  >= 10`), status 'Closed'; received and billed
  amounts stay.
- Commitments post nothing to the ledger. **Committed** for a job and cost code = revised commitment of sent
  POs, less closed remainders; **open quantity** = ordered - received, by `expected_on` (the line's override, else the
  header's). Area 7's job cost reads only sent POs (handoff); Area 8's forecast reads open quantity by expected date
  and stock available (on hand less reserved; 0 when stock tracking is OFF) (§12.3).
- **Tie-outs (integrity checks, always on):** committed = sum of revised line amounts of sent POs less releases;
  received-not-billed (GRNI) equals the GL balance of `grni_acct_id`; stock valuation equals GL Inventory (§7, §9).

### 6.3 Approval and edits (Area 14)

- The 'Purchase order' and 'Subcontract' rows are Area 14's, OFF by default; a PO with its row ON goes 'Pending
  approval' on submit and cannot be sent until Approved; with it OFF a PO goes Draft to Sent. Permissions: `po.create`,
  `po.approve` (sensitive), `subcontract.approve` (sensitive), `po.view`. Digest fields: Area 14 §7's default (amount, discount, lines, job) applies; planning proposal for Area 14
  to adopt: the vendor is also in the digest, and the memo, the terms and `expected_on` are not.
  Editing an approved PO before it is sent voids the approval; editing a **sent** PO is a change (6.1), never an edit.
- The PO's inline "over budget" transfer calls Area 7's `add_transfer_rows` (Area 7 handoff).
- Tests: `test_po_type_materials_and_subcontract_share_commitment_rule`,
  `test_commitment_starts_only_on_successful_send_mark_as_sent_or_print`,
  `test_draft_approved_unsent_and_failed_send_stay_uncommitted`,
  `test_close_remainder_releases_unreceived_commitment_with_reason`,
  `test_revised_commitment_excludes_pending_changes`, `test_approved_po_change_is_locked_fix_is_new_change`,
  `test_open_quantity_by_expected_date_uses_line_override_else_header`,
  `test_commitment_reads_only_sent_pos_for_job_cost`,
  `test_po_number_series_separate_for_materials_and_subcontracts_never_reused`,
  `test_subcontract_has_retainage_sov_and_lien_waiver_default_on_and_supplier_default_off`,
  `test_po_approval_row_off_goes_draft_to_sent_row_on_waits`,
  `test_agent_context_cannot_approve_a_po_or_a_po_change`, `test_po_without_project_refused_when_stock_tracking_off`,
  `test_editing_approved_unsent_po_voids_approval`, `test_materials_po_line_requires_a_material_code`,
  `test_free_text_po_line_refused`, `test_subcontract_line_has_a_cost_code_and_no_material_code`,
  `test_service_item_line_uses_a_service_material_code_two_way`, `test_sent_po_is_changed_only_by_a_change_record`,
  `test_commitment_total_ties_to_sent_po_lines`.

## 7. Receipts and accounting

- **`goods_receipt`:** `receipt_id`; `receipt_no`; `po_id`; `kind` CHECK IN ('Warehouse', 'Job site');
  `location_id` NULL (Warehouse only, tracking ON); `project_id` NULL (Job site); `received_on`; `received_by`;
  `delivery_ticket_attachment_id` NULL (Area 18 attachments); `status` ('Posted', 'Voided'); `entry_id` UNIQUE;
  `operation_id` UNIQUE (a retry with the same ID returns the first result); `row_version`.
  **`goods_receipt_line`:** `po_line_id`, `quantity` REAL, `unit_cost_cents` (the PO line's: stock and job cost are at actual PO cost, with no purchase
  price variance on receipt), `amount_cents`.
  Partial receipts allowed. A receipt past the open PO quantity follows `po_matching` (§9): a warning when OFF, refused beyond the quantity tolerance (0%) when ON.
- **Postings (materials, po design §4):** warehouse (tracking ON, stocked code): **Dr Inventory / Cr GRNI** at the PO
  cost; job-site delivery: **Dr Job cost (project, cost code) / Cr GRNI**, so delivered materials count toward percent
  complete. Receipt detail reads the saved receipt and its original posting; a preview is read-only and never marks a
  receipt posted (must-fix input). Posted receipts are never edited: a mistake is voided by reversal.
- **A matched bill clears the accrual with its own entry** (Area 3 owns the bill; this area supplies the match and the accrual):
  Dr GRNI (the received amount), Cr Accounts payable (the bill total), and **the price difference** (billed less received):
  *job PO or job-site receipt:* to the PO line's job and cost code, with the bill's freight and tax rows (owner Q4, Q7);
  *warehouse stock (tracking ON):* split by units, **the part for units still on hand to Inventory (stock value) and the part for units
  already used to Stock price differences (owner Q7)**; a bill below the receipt reverses the same split. Under **FIFO** the
  on-hand units are what is left of that receipt's own cost layer; under **moving average** they are the item's quantity on hand when
  the bill posts, **capped at the quantity this bill covers** (planning reading): on-hand part = difference per unit x min(quantity on hand,
  billed quantity). Planning proposal: the on-hand part is rounded half-up and the used part is the remainder, so the two always sum to
  the difference. Example of the cap: 50 older units on hand plus this receipt's 100, with 60 pulled, leaves 90 on hand; a bill covering 100 units caps the
  on-hand part at 90 units and the used part takes the other 10 (never more units than the bill covers). Example: 100 rails at $30.00 received, 60 pulled, bill at $32.00: Dr GRNI $3,000.00, Dr Inventory $80.00, Dr
  Stock price differences $120.00, Cr Accounts payable $3,200.00; the jobs that pulled the 60 rails keep $30.00. No ticket: **only while `po_matching` is ON** (planning proposal; CLAUDE.md section 0) the bill shows a missing-receipt exception and the PM
  may approve it without a ticket with a reason (a listed reason, or Other with 10 typed characters), and the cost then posts at the bill (po design §4);
  with matching OFF the bill is approved and costs at the bill with no exception.
- **New system account roles** (Area 18 §8.6 amendment, planning proposals): `inventory_acct_id` (asset, GL 1310 in the
  sample), and `stock_price_differences_acct_id` (expense, owner Q7; "controlled account" is a planning reading) replacing the earlier purchase price variance role
  (**Withdrawn 2026-11-24, owner 11:45 and 11:43 PM**) (`job_materials`, 5030, is Area 7 Q20's cost-type default role, not new). `grni_acct_id`,
  `retainage_payable_acct_id` and `inventory_adjustments_acct_id` exist. Resolved by role, never by number
  (must-fix input).
- **Controlled accounts (po design §4):** GRNI, Inventory and Stock price differences (and Retainage payable, Area 3) are fed only by the receipt,
  bill, release, issue and count services. A manual entry to them follows the existing controlled-account control
  (`allow_manual_control_je`, a permissive default, Controls page, Area 18); tests below.
- **Locks:** a receipt, an issue and a return call the shared lock check (Area 13 §1.4) with the area 'Inventory and
  receipts' (Area 13 §1 area list) and the accounts hit; static test: every function that writes `journal_line`
  from this area calls it.
- Tests: `test_warehouse_receipt_posts_dr_inventory_cr_grni_at_po_cost`,
  `test_job_site_receipt_posts_dr_job_cost_cr_grni_at_po_cost`,
  `test_receipt_detail_reads_saved_receipt_and_original_posting`,
  `test_receipt_preview_is_read_only_and_marks_nothing_posted`,
  `test_receipt_retry_with_same_operation_id_returns_first_result`,
  `test_matched_bill_posts_own_entry_clearing_original_receipt_accrual` (must-fix input),
  `test_direct_to_site_receipt_posts_linked_job_cost_without_warehouse_pull` (must-fix input),
  `test_grni_ties_to_gl`, `test_receipt_over_open_quantity_warns_when_matching_off_refused_when_on`,
  `test_materials_postings_resolve_job_materials_role_not_number` (must-fix input), `test_receipt_respects_period_area_and_account_locks`,
  `test_no_ticket_bill_posts_cost_at_bill_with_pm_reason`,
  `test_receipt_posts_at_po_cost_with_no_price_variance_account`,
  `test_bill_price_difference_splits_between_stock_value_and_stock_price_differences` (100 rails, 60 pulled, $80.00 and $120.00),
  `test_price_difference_split_under_fifo_uses_the_receipts_remaining_layer`,
  `test_price_difference_split_under_average_uses_quantity_on_hand_at_bill_posting`,
  `test_price_difference_on_hand_part_is_capped_at_the_billed_quantity`,
  `test_missing_receipt_exception_only_while_po_matching_on`,
  `test_bill_match_override_reason_check_is_conditional`,
  `test_fifo_layer_remaining_value_stays_whole_cents_after_a_price_difference`,
  `test_price_difference_split_sums_to_the_difference_with_remainder_in_used_part`,
  `test_jobs_already_charged_are_not_changed_by_a_price_difference`,
  `test_job_po_price_difference_freight_and_tax_post_to_the_po_lines_job_and_cost_code`,
  `test_manual_entry_to_grni_or_inventory_follows_the_controlled_account_control`.

## 8. Requests, pull tickets and stock

### 8.1 Material requests (owner 11:30 PM; PM creates, owner 2026-11-22)

- **`material_request`:** `request_id`; `request_no`; `project_id` NOT NULL; `requested_by` (a PM, or a holder of
  `material_request.create`, planning proposal); `needed_on`; `status` ('Draft', 'Submitted', 'Filled', 'Cancelled');
  `note`; `row_version`. **`material_request_line`:** `material_id` NULL; `free_text` NULL; `quantity`; `unit_id`;
  **`cost_code_id` NOT NULL**; `coded_material_id` NULL; `original_cost_code_id` NULL; `status` ('Open', 'To be coded', 'Ordered', 'Issued',
  'Cancelled'). CHECK exactly one of `material_id` or `free_text`.
- **Rules:** a line with a material code takes that code's cost code, read-only (owner). **A free-text line** carries a
  job and a cost code the PM picks (owner); purchasing creates or picks a material code (`code_line`) before the line
  can go on a PO (owner); coding it sets `coded_material_id` and, per the cost code rule, the line then takes that
  code's cost code **and the PM is told (owner 11:40 PM)**: the request shows both ("PM picked 16-100, now 16-200"), and
  `original_cost_code_id` (NULL until a re-code) keeps the PM's pick in history. A request posts nothing and reserves nothing. With tracking ON a request feeds the pull ticket
  queue; with it OFF it feeds the purchasing queue for a PO.
- Tests: `test_pm_may_raise_a_request_with_a_free_text_to_be_coded_line`,
  `test_free_text_line_cannot_go_on_a_po_until_coded`, `test_request_line_with_material_takes_its_cost_code_read_only`,
  `test_request_posts_nothing_and_reserves_nothing`,
  `test_coding_a_free_text_line_to_a_different_cost_code_moves_it_shows_both_and_keeps_the_original`,
  `test_pm_is_notified_when_purchasing_changes_a_request_lines_cost_code`.

### 8.2 Pull tickets and stock (tracking ON only)

- **`stock_location`** (`location_id`, `name`, `is_active`). **`stock_movement`** (insert-only; `movement_id`,
  `material_id`, `location_id`, `quantity_delta` REAL, `unit_cost_cents`, `value_delta_cents` (signed integer cents), `kind` CHECK IN ('Receipt', 'Issue', 'Return',
  'Adjustment', 'Count', 'Price difference'), `source_type`, `source_id`, `entry_id`, `account_id` (the account the movement posted to),
  `operation_id` UNIQUE, `created_at`, `created_by`): **on hand = SUM(`quantity_delta`)**, derived; there is no stored
  quantity column to drift. **Reservation** (`stock_reservation`: ticket line, quantity, status Open/Released) exists
  **only from the moment a pull ticket is created (owner 2026-11-22)**.
- **`pull_ticket`** (`ticket_no`, `project_id`, `request_id` NULL, `status` CHECK IN ('Reserved', 'Issued', 'Cancelled'),
  `issued_by`, `issued_at`) and **`pull_ticket_line`** (`material_id`, `quantity`, `unit_cost_cents` at issue,
  `cost_code_id` from the material code, `posted_account_id`, `entry_id`). An issue reduces on-hand, releases the
  reservation and posts **its own linked entry exactly once: Dr Job cost / Cr Inventory**; a retry with the same
  operation ID returns the first result. A return credits job cost on the account the original issue stored, even if
  the mapping has changed (STOCK-03). `inventory.pull` issues, `inventory.count` counts, `inventory.adjust`
  adjusts (posting to `inventory_adjustments_acct_id`), `receiving.stock` receives to the warehouse,
  `receiving.jobsite` confirms job-site tickets.
- **Costing (owner: moving average or FIFO, picked once, §5):** both value stock at **actual cost**; the stock value is
  `SUM(value_delta_cents)` and ties to GL Inventory. *Moving average:* the issue cost is value on hand / quantity on hand at the
  time (example 10 @ $2,150.00 + 6 @ $2,230.00 = 16 @ $2,180.00); the last unit issued takes the remaining value so nothing is
  left over. *FIFO:* each receipt is its own layer, `stock_cost_layer` (`layer_id`, `material_id`, `receipt_line_id`,
  `received_quantity`, `remaining_quantity`, `unit_cost_cents`, `remaining_value_cents` (integer cents, so a price difference is never a fraction of a cent); per material, not per location, planning proposal); issues consume the oldest layer first (the
  next 10 cost $2,150.00 each, then $2,230.00); a return restores the layer it came from (STOCK-03's account rule still applies).
  A bill price difference (§7) raises or lowers the remaining layer or the on-hand value. The `stock_count` check compares counted to on-hand.
- Tests: `test_reservation_exists_only_after_a_pull_ticket_is_created`,
  `test_pull_ticket_issue_posts_stock_reservation_and_cost_once`,
  `test_pull_ticket_issue_retry_same_operation_id_no_double_post`,
  `test_stock03_return_after_mapping_change_uses_original_issue_account`,
  `test_on_hand_is_derived_from_movements_and_an_issue_beyond_on_hand_is_refused`,
  `test_stock_valuation_ties_to_gl_inventory`,
  `test_moving_average_issue_cost_is_2180_after_10_at_2150_and_6_at_2230`,
  `test_fifo_issues_oldest_layer_first_2150_then_2230`, `test_fifo_return_restores_its_layer`,
  `test_last_unit_issued_takes_the_remaining_value_under_average`, `test_count_adjustment_posts_to_inventory_adjustments_role`,
  `test_pull_ticket_requires_inventory_pull_permission`.

### 8.3 Serial numbers (owner 12:53 AM, 2026-11-25; reopens Area 20's conflict)

- **Owner rule:** serial tracking is in the plan, **per material code, OFF by default**; a material code can be set to track serial numbers **only when stock tracking is on**.
  Serials are **recorded at receipt, picked at pull, and kept on the job's record for warranty.** Example: inverter SN 4471-A pulled to RI0001-002 shows on that job's
  record. Live already has the New inventory item form's "Track serial numbers" (recorded at receipt, checked at pull) and the String inverter 12 kW with 14 serials.
- **`material_code.track_serials`** INTEGER NOT NULL DEFAULT 0 (the service refuses 1 while `stock_tracking` is OFF, and refuses a change once the code has stock movements; planning proposal).
- **`stock_serial`** (planning proposal): `serial_id`; `material_id`; `serial_no` TEXT NOT NULL (trimmed, UNIQUE per material ignoring case); `receipt_line_id` (where it came in);
  `location_id` NULL; `status` CHECK IN ('In stock', 'Pulled', 'Returned to stock', 'Scrapped'); `pull_ticket_line_id` NULL; **`project_id` NULL (set when pulled, kept for warranty after the
  ticket closes)**; `pulled_at`; `row_version`. **`stock_serial_history`** (insert-only): `serial_id`, `event` (Received, Pulled, Returned, Adjusted), `source_type`, `source_id`, `project_id`, `at`, `by`.
- **Rules (planning proposals unless the owner words above):** a receipt line for a tracked code needs one serial per unit received, entered or confirmed by a person; a pull ticket line for a tracked
  code names the serials taken, the count equals the quantity, and each must be In stock at that location (checked at pull); a return puts the serial back In stock and the history keeps the job; a serial
  pulled to a job shows on the job's record and its warranty view (Area 8's warranty job link); no serial is ever deleted. Serials never change cost: the issue cost still follows moving average or FIFO (§8.2).
  Typed serials may arrive from a capture draft (Area 20 §5); reading them from a label photo is Phase 6.
- Tests: `test_track_serials_defaults_off_and_requires_stock_tracking_on`, `test_tracked_receipt_needs_one_serial_per_unit`, `test_serial_unique_per_material_ignoring_case`,
  `test_pull_checks_each_serial_is_in_stock_at_the_location_and_count_equals_quantity`, `test_pulled_serial_shows_on_the_jobs_record_for_warranty`,
  `test_return_restores_the_serial_and_history_keeps_the_job`, `test_serial_is_never_deleted`, `test_track_serials_cannot_change_once_the_code_has_movements`,
  `test_serial_pull_cost_follows_the_costing_method`.

## 9. Matching and tolerances (owner: a Company control, OFF by default; po design §5)

- **`bill_match`:** `invoice_line_id`, `po_line_id`, `receipt_line_id` NULL, `matched_quantity`, `matched_amount_cents`,
  `price_difference_cents`, `status` ('Matched', 'Within tolerance', 'Exception', 'Overridden'), `reason_code` and `reason_text` (a listed reason, or Other
  with 10 typed characters, for an override; the CHECK is conditional like §6.2's: `reason_code <> 'Other' OR length(trim(reason_text)) >= 10`, required when `status` = 'Overridden'), `overridden_by`. Area 3's `invoice_line.po_line_id` and `receipt_line_id` point here.
- **Two-way** (services, subcontracts): PO and bill. **Three-way** (materials): PO, receipt, bill; billable quantity is
  received - already billed. A subcontract's cumulative billed is checked against its revised line value by Area 3's control `subcontract_overlimit_block`
  (OFF by default: a reason is required when over; ON refuses).
- **Tolerances (owner, as live: 15% price and amount before tax, quantity always exact; po design §5 and §10):** price and amount **15%**, quantity **0%**, **compare
  before tax ON** with a separate tax check (a small tolerance, PROPOSED in the doc, kept open); under-billing never
  raises an exception. Each is a percent and/or a dollar amount (po design §5). Stored as company settings (the baseline has no `policy_rule` table): `match_price_tolerance_pct`,
  `match_amount_tolerance_pct`, `match_quantity_tolerance_pct`, `match_compare_before_tax`, with a per-vendor override (columns on `contact`) and a per-PO override (columns on `purchase_order`).
- **Control (owner 11:30 PM):** **`company_settings.po_matching`** INTEGER NOT NULL DEFAULT 0, shown on live Settings > ERP as "Match bills
  to purchase orders"; CLAUDE.md section 0 lists it as a configurable control, permissive by default. OFF: the match is information
  only and the bill goes ahead. ON: each bill is compared with its PO and receipt and a difference over the tolerance needs an
  override and an OD-31 reason (a listed reason, or Other with 10 typed characters) before it is approved. **"Hold bills that do not
  match the receipt"** stays its own control, `company_settings.hold_unmatched_bills` DEFAULT 0, and **applies only while matching is ON**
  (live Settings > ERP text, confirmed by the owner 2026-11-25): **it holds the bill before approval**: a bill whose quantity or price differs from the receipt
  goes to the job's project manager instead of going to approval with a warning; it does not hold payment. Both controls are OFF by default. This replaces the po design's "matching ON for everyone".
- **Limits follow the same control (planning proposal):** with `po_matching` OFF a bill past a PO line's open amount
  or a receipt past the open quantity shows a warning and is allowed; with it ON both are exceptions that block beyond
  the tolerance (quantity 0%, price and amount 15%). A subcontract's cap follows Area 3's `subcontract_overlimit_block`. A
  duplicate bill number per vendor stays Area 3's warning. Only the arithmetic, the tie-outs and the locks are integrity.
- Tests: `test_two_way_and_three_way_matching_happy_paths`, `test_partial_receipt_and_partial_billing`,
  `test_within_tolerance_passes_with_variance_recorded`, `test_over_price_beyond_tolerance_is_an_exception`,
  `test_matching_control_off_never_blocks_approval_or_payment`,
  `test_4200_po_billed_4900_needs_override_only_when_matching_on`,
  `test_hold_unmatched_bills_defaults_off_and_applies_only_with_matching_on`,
  `test_hold_unmatched_bills_sends_a_mismatched_bill_to_the_jobs_pm_before_approval_not_to_payment_hold`,
  `test_matching_control_on_blocks_until_resolved`, `test_override_needs_reason_and_role`,
  `test_void_of_a_matched_bill_reopens_the_po_line`, `test_bill_price_difference_is_recorded_on_the_match`,
  `test_compare_before_tax_checks_tax_separately`, `test_po_line_billed_past_open_amount_warns_when_off_blocks_when_on`,
  `test_subcontract_cap_follows_area3_overlimit_control`, `test_matching_reasons_use_a_pick_list_or_10_typed_characters_for_other`.

## 10. The cost code rule: check against OD-80, Area 6 and others (owner 11:35 PM)

- **Rule:** a line with a material code takes that code's `cost_code_id`; the cost code is **read-only on that line** on
  every PO line, estimate cost line and request line. The service refuses any line save where `material_id` is set and
  `cost_code_id` differs from the code's (service rule with a test; a cross-table CHECK is not possible in SQL, H4). The
  line stores the cost code it took, so **re-pointing a material code never changes a saved line** (planning reading).
  Free-text lines pick their own (planning reading). No new Control: it is not optional.
- **OD-80 (fixed pricing-template markup by cost code type):** compatible. The line's cost code type, and so the fixed
  markup, now follows from the material code's cost code; MAT-202 at a fixed 28.2% is unchanged. Nothing to change.
- **Area 6 estimate cost lines:** Area 6 §3.4 and C129 call the material code's cost code a **default**, and line 49
  says "cost code always set". This area replaces "default" with the driving cost code; the column stays NOT NULL;
  `estimate_cost_line.material_code_id` becomes the FK. **Conflict flagged:** Area 6's cost templates (`cost_template_line`)
  carry their own cost code for Material lines; a template Material line must now take the material code's cost code
  (the template column becomes derived for Material lines). Area 6 gets a pointer.
- **Area 7 (cost types, leaf-only):** compatible; a material code needs an active leaf cost code (RP5), so the budget and
  postings always find a postable code. Budget transfer rows (`add_transfer_rows`) are unaffected.
- **Bill lines (owner 11:55 PM, replaces the earlier draft's "override with a reason"):** a bill line matched to a PO line takes
  the PO line's `project_id` and `cost_code_id` and **AP cannot change them on the bill**; price-difference, freight and tax rows
  on the bill post to the same job and cost code. A bill line with no PO match is unchanged (Area 3 codes it, a cost code
  required with a job). The po design §4 "override with a reason" paragraph is **superseded** (amendment appended there). Planning
  reading (owner may correct): a wrong cost code is fixed on the PO before billing, or by reclass after posting (Area 10), with history
  kept. Areas 3 and 10 hold no "bill line may recode" text (checked); the only source is the po design's coding paragraph.
- **Area 14 digests:** a line's cost code is part of the 'Purchase order' and estimate digests only through the material
  (a material change voids an approval; a cost code change on a material code does not).
- **Mockup work order (design queue, not written here):** the PO page, the estimate builder and the material request
  show the cost code as read-only with a short "Set by the material code" note once a material is picked; free-text
  lines keep the picker; the shared `SL_LISTS.materials` rows already carry one cost code each.
- Tests: `test_line_with_material_code_autofills_its_cost_code_on_po_estimate_and_request`,
  `test_line_with_material_code_refuses_a_different_cost_code`,
  `test_free_text_request_line_picks_its_own_cost_code`,
  `test_bill_line_matched_to_a_po_line_takes_its_job_and_cost_code_locked`,
  `test_bill_line_with_no_po_match_is_coded_by_ap`,
  `test_wrong_cost_code_is_fixed_on_the_po_before_billing_or_by_reclass_after_posting`,
  `test_changing_a_material_codes_cost_code_leaves_saved_lines_unchanged`,
  `test_fixed_markup_follows_cost_code_type_of_the_material_codes_cost_code` (OD-80),
  `test_template_material_line_takes_the_material_codes_cost_code`.

## 11. Reads, close checks and reports

- **Close checks (Area 13 §2.3):** `received_not_billed_aged` (receipts not billed after 30 days; Warehouse role task),
  `material_advances_open` (see open items) and `stock_count` (**only when stock tracking is ON**, owner). Each is
  warn or block per Area 13's per-check modes; this area writes the queries.
- **Reports (Area 17 owns the screens):** commitments by project and cost code (original, changes, revised, billed,
  remaining), open POs, received-not-invoiced listing tied to GRNI, unmatched bills, exception queue, subcontract status
  with retainage held, price differences, stock on hand and valuation (tracking ON), the Material forecast page inputs.
- **Tests:** `test_received_not_billed_aged_flags_receipts_over_30_days`,
  `test_stock_count_check_absent_when_tracking_off`, `test_commitments_report_ties_to_sent_pos`,
  `test_material_advances_open_check_stays_design_only_until_its_meaning_is_settled` (the check has no query until §17's item is decided),

## 12. Locks, permissions, row version and audit

- **Locks:** Area 13 §1.4 on every posting; a sent PO has no posting; a receipt's period and the area lock apply.
- **Permissions:** existing codes are kept (§1). New (planning proposals, none in `AGENT_ALLOWED`; Area 18's seeded permission count of 115 grows by these): `material_request.create`
  (PM), `list.manage` (units, if none exists), `material_code.manage` (or `po.create`; Area 18 decides). The AI may read
  a delivery ticket photo and propose a receipt; a person confirms it; it never approves or posts (po design §4).
- **Row version** on `purchase_order`, `purchase_order_line`, `purchase_order_change`, `goods_receipt`, `material_code`,
  `material_request`, `unit_of_measure` (Area 21 stale-save refusal). **Audit:** every table is audited by the trigger
  pattern; `stock_movement` and `purchase_order_change` approved rows are insert-only. Tests: `test_material_request_create_needs_its_permission`,
  `test_unit_edit_needs_the_lists_permission`, `test_material_code_manage_needs_its_permission`, `test_stale_row_version_save_is_refused_on_po_and_material_code`.

## 13. How it lands in the baselines and code

- **Baseline (planning):** new tables: `unit_of_measure`, `material_code`, `purchase_order`, `purchase_order_line`,
  `purchase_order_change`, `purchase_order_change_line`, `goods_receipt`, `goods_receipt_line`, `bill_match`,
  `material_request`, `material_request_line`, `stock_location`, `stock_movement`, `stock_reservation`, `pull_ticket`,
  `pull_ticket_line`, `stock_cost_layer`, `stock_serial`, `stock_serial_history`, `po_number_sequence`; `company_settings` gains `stock_tracking`, `require_pull_tickets`,
  `po_matching`, `hold_unmatched_bills`, `stock_costing_method`, the tolerance columns (with per-vendor override columns on `contact` and per-PO override columns on `purchase_order`),
  `inventory_acct_id`, `stock_price_differences_acct_id` (`job_materials` is a cost-type default role from Area 7 Q20, not a `company_settings`
  column);
  `estimate_cost_line.unit_id` and the `material_code_id` FK replace the free text and the plain integer; Area 3's FKs
  (`po_line_id`, `receipt_line_id`, `subcontract_line_id`) are added; `reclass_line.original_material_id`; `material_code.item_sku`, `reorder_point`, `is_service`, `track_serials`.
- **Code:** new services `units.py`, `material_codes.py`, `purchase_orders.py` (create, send, close remainder, change),
  `receipts.py`, `matching.py`, `material_requests.py`, `stock.py`, `pull_tickets.py`; no UI or HTTP imports (H1), no
  clock reads (H2), file attachments through `storage.py` (H3). Static tests: every function that writes `journal_line`
  calls the shared lock check; no `localStorage` units; workflow rules in services, not triggers (H4).
- **Existing tests change:** estimate tests that insert a free-text unit; any test seeding `estimate_cost_line` with a
  material code integer.
- **Handoffs out:** Area 3 (FKs and `bill_match`); Area 6 (driving cost code, units FK, material kind enabled);
  Area 7 (committed reads sent POs); Area 8 (open quantity by `expected_on`, stock available); Area 10
  (`original_material_id`); Area 13 (three checks); Area 14 (digests, rows); Area 17 (reports); Area 18 (new roles and
  permissions); Area 21 (row versions, setup of units and material codes); Area 20 (notifications for late
  deliveries, not designed here).

## 14. Integrity checks kept (always on)

Integer cents; GRNI and stock valuation tie to the GL and commitments tie to the sent PO lines (they post nothing); a posted receipt, issue or return is never
edited (reversal only); a reservation exists only from a pull ticket; no cost code change on a coded line; a deactivated
unit or material code is never deleted; every posting passes the period, area and account locks; a retry with the same
operation ID never double posts; the AI never approves, posts or moves money.

## 15. Conflicts with decisions, the baseline or the mockups (flagged)

1. **OD-51 lists six units with "kw"**; the live mockup and the owner's lead defaults have ten and "kW" (§3). The ten and
   "kW" are used.
2. **OD-04 (UOM column authoritative) versus OD-51 and the owner's 11:05 PM answer:** replaced by the `unit_of_measure`
   table (§3).
3. **Mockup units page is add-only and keeps units in the browser;** the owner rule is add and deactivate in the company
   file (§3). Work order, not a plan conflict.
4. **Area 6 "default cost code" (C129) versus the owner's driving cost code:** Area 6 line 312 says the material's cost
   code is "editable per line, C129", the direct opposite of the owner's rule; it is superseded by pointer; and Area 6 cost templates carry a cost
   code on Material lines (§10).
5. **PO design says exceptions block approval and payment (decided) versus CLAUDE.md section 0 (matching and tolerances
   are configurable, permissive by default).** Resolved by the owner: a Company control, OFF (Q1, §18).
6. **PO design value 'Purchase' versus the owner's 'Materials';** and the design's status list lacks 'Sent' (§6.1).
7. **po design §4 lets a bill line override the coding;** superseded by the owner's answer: a bill line matched to a PO line is locked to the
   PO line's job and cost code (§10, Q4).
8. **Sample company counts:** 64 inventory items against 18 shared material codes and 5 linked rows; reconciled by the one-list proposal (§5).
9. **The "Require pull tickets to take stock" control** is cited as existing, but only the mockups show it; the
   baseline has no such column (§5).
10. **No `policy_rule` table in the baseline** (Area 3 line 178); tolerances are company settings here (§9).
11. **po design §4 posts a Purchase Price Variance account on bills;** the owner's costing answers have no variance on receipt and a
    stock-price-differences split instead (§7). The role `purchase_price_variance_acct_id` is not created.
12. **Live `purchase-orders.html` says lines are "items from the materials list or free text";** the owner's rule removes free text
    (work order for the design queue).
13. **Live inventory "New item" unit picker** (each, roll, box, ft, sheet, bundle, square, pallet, kit, lot) is not the ten-unit list (§5).
14. **Area 6 §3.4 and C129 call the field "standard unit cost";** renamed "default unit cost" here, used only to price lines (pointer).

## 16. Questions for the owner (recommended option first, with an example; **all answered 2026-11-24 11:30 to 11:43 PM, §18**)

- **Q1. PO matching default.** (A) A control, OFF by default: the match and variance show but never block; ON makes
  exceptions block approval and payment (recommended; follows CLAUDE.md section 0). (B) ON for every company, as the PO
  design decided. Example: a $4,200.00 bill against a $4,000.00 PO line with a 15% tolerance: both pass; a $5,000.00
  bill is an exception either way, and it blocks approval and payment only under ON.
- **Q2. Stock costing method (tracking ON).** (A) Moving average (recommended: simple, one cost per item). (B) FIFO
  layers. Example: 10 kits at $300.00 then 10 at $330.00; an issue of 5 costs $315.00 each under A, $300.00 under B.
- **Q3. Free-text lines typed straight onto a PO (live allows them).** (A) Keep them allowed, with their own cost code
  (recommended; Service and Subcontract work lines have no material). (B) Every Item line needs a material code.
  Example: "Delivery fee" on a PO.
- **Q4. Does the cost code lock reach a bill line matched to a PO line?** (A) No: bills keep the override with a reason
  (recommended; the owner's words name PO, estimate and request). (B) Yes, bill lines take the PO line's cost code too.
  Example: a $2,000.00 bill line for MAT-105 posted to a different job cost code.
- **Q5. Can a deactivated unit be reactivated?** (A) Yes, by the same permission (recommended; nothing is lost).
  (B) No, add a new unit instead. Example: "cnt" retired, then needed again.
- **Q6. A free-text request line is coded with a material whose cost code differs from the one the PM picked.**
  (A) The line takes the material's cost code and shows both to the requester (recommended; one rule). (B) Purchasing
  must pick a material with the PM's cost code, or ask the PM to change the request.
  Example: the PM picks 03-100 for "10 ft conduit"; purchasing codes it MAT-310 with 05-100.

- **Q7. Where does a bill's price difference post for a job-site delivery?** (A) To the job's cost line, so job cost equals
  the actual bill; warehouse receipts post it to Purchase price variance (recommended). (B) Always to Purchase price
  variance. Example: a delivered rail kit was received at $300.00 and billed at $318.00: under A the job shows $318.00 and
  under B the job shows $300.00 and $18.00 sits in variance.

## 17. Open items (not decisions)

- Whether a deactivated **material code** can be reactivated (units can, owner; material codes follow the same rule, planning proposal).
- `material_advances_open` (the check's meaning: advance payments to a vendor for materials not yet received) is a
  close-checklist item with no design yet; list it with Area 3's vendor prepayments.
- **Not asked:** whether Subcontract SOV lines also need a material code (planning proposal: a cost code and no material code, §6.1).
- **Not asked:** whether roll, sheet, bundle, square, pallet and lot join the shipped unit defaults (§5; today they would be the
  sample company's own units).
- The 59 sample inventory items without material codes (design-queue work order, §5).
- Returns to vendor and purchase credits for stock items; scrap and write-down of stock beyond count adjustments.
- Multi-location transfers between warehouses; lot tracking; barcode scanning (out of scope). Serial tracking is in (§8.3).
- Notifications for late or short deliveries: Area 20.
- Foreign currency, tax on use (the `use_tax_payable_acct_id` role exists), and Ramp or card purchases without a PO.
- Compliance document defaults (insurance certificate and lien waiver) and the tax tolerance value: the PO design's open
  items, kept open.

## 18. Owner answers 2026-11-24 11:30 to 11:43 PM to §16 (dated amendment; §16 stays as asked)

Source: Strata_Teams `inbox/to_owner.md`, entries headed 11:35 PM+, 11:45, 11:50, 11:55 PM, 12:00 AM, 11:40 and 11:43 PM (the times were
estimated and corrected there: the answers were given between 11:30 and 11:43 PM; the answers are unchanged).

- **Q1 matching (owner):** a Company control, OFF by default; ON compares each bill with its PO and receipt (15% price and amount before tax,
  quantity exact), over tolerance needs an override and an OD-31 reason; "Hold bills that do not match the receipt" stays its own
  control, OFF, only with matching ON; it holds the bill before approval and routes it to the job's project manager (live Settings > ERP text, owner 2026-11-25), not payment. §9.
- **Q2 costing (owner):** moving average or FIFO, picked once, locked after the first stock history; no LIFO, no standard cost;
  moving average pre-selected (planning reading); both are actual cost, no purchase price variance on receipt; "standard unit cost"
  renamed "default unit cost". §5, §7, §8.2.
- **Q3 (owner):** every PO line needs a material code, no free text; Subcontract SOV lines carry a cost code and no material code
  (planning proposal, not asked). §6.1.
- **Q4 (owner):** a bill line matched to a PO line takes the PO line's job and cost code, locked; price-difference, freight and tax
  rows go to the same job and cost code; the "override with a reason" is removed. §10.
- **Q5 (owner):** a deactivated unit can be reactivated; history records who and when. §3.
- **Q6 (owner):** a recoded request line takes the material's cost code, shows both, the PM is notified, history keeps the original. §8.1.
- **Q7 (owner):** a price difference on received stock splits between stock value (units on hand) and the new controlled "Stock price
  differences" role (units used); job PO differences go to the PO line's job and cost code. §7.
- **Item list reconciliation (planning proposal, owner may revise):** one list; a stocked item is a material code (§4, §5).

- **Amendment 2026-11-25 (pointer, Area 20): notices and the capture inbox.** The "request line recoded" and "late or short delivery" notices are
  seeded kinds in Area 20's feed (§7; in-app always, email opt-in per kind). Capture-inbox delivery tickets and pull tickets become Area 9 drafts only
  through `goods_receipt` and `pull_ticket` services after one human confirmation; serials are tracked per material code (§8.3); reading them from a pallet label stays Phase 6.

## 19. Amendment 2026-11-25 12:53 AM (owner; serial tracking reopens the Area 20 report)

Serial tracking is in: per material code, OFF by default, only while stock tracking is on; recorded at receipt, picked at pull, kept on the job's record for warranty (§8.3). This replaces
the "serial tracking out of scope" lines in §17 and in the Area 20 pointer above. Example: inverter SN 4471-A pulled to RI0001-002 shows on that job.

- **Amendment 2026-11-25 (pointer, Area 19; owner A19-Q3b): material accruals are visible as Accrued.** A job-site delivery ticket's Dr Job cost / Cr GRNI carries `journal_line.cost_nature` 'Accrued' until the matched bill's own entry posts the actual (the owner: material accruals "need to be visible", separate from actuals). Planning proposal for the mechanics, owner may revise: Area 9 is the producer of material accruals.

- **Amendment 2026-11-25 (pointer, Area 21 draft; Planning reading, owner may correct): row version and setup.** `row_version` and the stale-save refusal are Area 21 §3 (`tx.update_versioned`, `StaleVersionError`, mapped to `conflict`; insert-only tables exempt). Setup of units and material codes is a setup task in Area 21 §6.
