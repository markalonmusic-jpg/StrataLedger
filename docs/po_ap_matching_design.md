# Purchase orders, subcontracts and PO-to-AP matching: design draft

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
Replaces the header-only `purchase_order_subcontract` table. Column names for
existing tables come from the migration report and must be confirmed against
the live schema before the migration is written.

Conventions follow CLAUDE.md: integer cents, double-entry, posted records
locked, corrections by reversing entries or credit memos, writes only through
service functions, controlled accounts fed only by their subledger service.

---

## 1. Scope

1. **Purchase orders** for materials and services (stock and job deliveries).
2. **Subcontracts**: a commitment with a schedule of values, a retainage rate
   and change orders. Subcontractor bills are matched against it.
3. **Receipts** (goods received, services accepted) for three-way matching.
4. **Bill matching** with tolerances, exceptions and approval.
5. **Commitment reporting** (committed, billed, remaining) per project and cost
   code.
6. **Retainage payable** on subcontract bills.

Not covered: Ramp / point-of-sale purchases. Those have no PO and go through
the staging and coding flow (CLAUDE.md section 6). A bill with no PO is allowed
unless policy requires one (section 6).

---

## 2. Concepts

- **Commitment:** an approved PO or subcontract. Commitments post NOTHING to the
  ledger. They are off-ledger records, like change orders. They feed the job
  cost report and the project manager's estimate to complete.
- **Revised commitment value** = original + approved PO/subcontract change
  orders. Pending ones are excluded.
- **Match:** a link from a bill line to a PO or subcontract line (and, for
  three-way, to a receipt line), with quantity, amount and variance.
- **Match types**, set per PO line (default by line type):
  - *Two-way* (PO and bill): services, subcontracts, anything with no receipt.
  - *Three-way* (PO, receipt, bill): materials and stock items.

---

## 3. Data model (PROPOSED)

**`purchase_order`**: `po_number` (series), `po_type` (Purchase, Subcontract),
`vendor_id`, `project_id` (optional on stock POs), `contract_id` (prime
contract, subcontracts), `issue_date`, `status` (Draft, Approved, Partially
Received, Received, Closed, Cancelled), `retainage_pct` (subcontracts, one rate
per subcontract), `revision_no`, approval fields, `terms`, `origin`.

**`purchase_order_line`**: `po_id`, `sort_order`, `line_type` (Item, Service,
Subcontract work), `item_id` (inventory items), `description`, `quantity`,
`uom_id`, `unit_cost`, `amount_cents`, `account_id`, `project_id`,
`cost_code_id`, `match_type` (Two-way, Three-way), `tax_rate_id`.
Subcontract lines act as the vendor's schedule of values.

**`purchase_order_change`** (+ lines): approved changes to a PO or subcontract.
Approved changes lock; fixes use a new change. Optional link to the project
change order that caused it.

**`goods_receipt`** (+ `goods_receipt_line`): `po_line_id`, `quantity`,
`received_date`, `received_by`, `location_id` (warehouse) or job-site delivery
(`project_id`), `status`. For stock items the receipt creates the inventory
movement (inventory design). Receipts may be partial.

**`bill_match`**: `invoice_line_id` (the bill line), `po_line_id`,
`receipt_line_id` (nullable), `matched_quantity`, `matched_amount_cents`,
`price_variance_cents`, `status` (Matched, Within tolerance, Exception,
Overridden), `reason`, approved_by.

**`subcontract_billing` (to-date basis, like pay applications):** a subcontractor
bill stores cumulative billed to date per subcontract line; this period is the
difference from the last approved bill. Cannot go below previous or above the
revised line value.

**Existing table changes:** `invoice_line.po_line_id` and `receipt_line_id`
(nullable); `invoice.po_id` (nullable; bills are `invoice` rows with `ledger_side = 'Purchase'`); `purchase_order_subcontract` is
dropped in the fresh rebuild.

---

## 4. Accounting

**Receipts (materials).** Two cases:
- *Stock to the warehouse:* Dr Inventory / Cr Accrued Receipts (GRNI) at receipt.
  The job is costed LATER, when the material is pulled: the pull ticket names
  the job and posts Dr Job cost / Cr Inventory (inventory design).
- *Delivered straight to the job site:* a **delivery ticket** (a goods receipt)
  is recorded in the app before the cost is job costed. It posts Dr Job cost
  (project, cost code) / Cr Accrued Receipts (GRNI), so delivered materials
  count toward percent complete. The ticket records date, who received it,
  quantity per PO line and an optional attached image of the signed ticket.
  Anyone with the receiving permission may enter it (foreman, superintendent,
  or office staff from the signed ticket). The AI Copilot may read a ticket
  photo and propose the receipt; a person confirms it.
- *No ticket:* the bill shows a missing-receipt exception. The project manager
  may approve it without a ticket (override with a reason); the cost then posts
  at the bill instead of at the ticket.
A bill clears the accrual. (Matches the inventory design; confirm the accounts
there.)

**Bill posting with a match:**
- Three-way: Dr Accrued Receipts (matched receipt amount), Dr/Cr Purchase Price
  Variance for any approved difference, Cr Accounts Payable (bill total, tax per
  normal rules).
- Two-way (services): Dr Expense / Job cost per PO line coding, Cr AP.
- Subcontract bill: Dr Subcontract cost (project, cost code), Cr AP (net),
  Cr Retainage Payable (withheld).

**Retainage payable (mirror of the receivable design).** Retainage per
subcontract bill = cumulative round-half-up(billed to date x subcontract rate)
minus prior cumulative. It is held in Retainage Payable (controlled account)
and is paid only through a retainage release document, which moves it from
Retainage Payable to AP and is then paid normally. No cost is touched.
Tie-out per subcontract: held = withheld - released, equal to the GL.

**Controlled accounts added:** Accrued Receipts (GRNI), Retainage Payable.
Entries come only from the receipt, bill and release services. Lines carry
`po_line_id` / `project_id` keys.

**Coding.** The bill inherits account, project, cost code and item from the
matched PO line. A different coding needs an override with a reason and, per
policy, approval.

---

## 5. Matching process

1. Bill entered (manual, CSV import or staged). The user picks the PO (or the
   system suggests it from vendor and references).
2. Each bill line is matched to an open PO line by line, quantity and amount.
   Open quantity/amount = PO line - already billed (and, for three-way, the
   billable quantity is limited to received - already billed).
3. Checks on each line:
   - quantity within tolerance (over-billing beyond received/ordered);
   - unit price within tolerance;
   - line amount within tolerance;
   - subcontract: cumulative billed <= revised line value (hard stop).
4. Result per line: Matched, Within tolerance (passes, variance recorded),
   or Exception.
5. **Exceptions block approval and payment** until resolved: correct the bill,
   receive the goods, issue a PO/subcontract change, or approve an override
   (with a reason; role-limited). A hard stop (subcontract over its revised
   value, no PO where policy requires one) cannot be overridden except by an
   approved change order or policy exception recorded by an authorized role.
6. Two-step entry (DECIDED): a clerk enters the bill, the project manager (or
   the role named in policy) approves it. Only a person approves a bill or an override. The AI Copilot may pre-fill a
   match or suggest the PO; it never approves.
7. A paid or posted bill is locked. Corrections use a credit memo or reversal.
8. Duplicate protection: bill number unique per vendor (existing rule), and a
   PO line cannot be billed past its open amount.

**Tolerances (DECIDED default 15%, flexible entry):** price and line amount
tolerance default to 15% (about 10% sales tax plus room), entered as a percent
and/or a dollar amount in `policy_rule`. Set at company level, overridable per
vendor and per PO. Quantity over the received/ordered amount defaults to 0%
(receipts define what is billable). Under-billing never raises an exception.
PROPOSED option "compare before tax": amounts are matched before tax and tax is
checked separately against the expected rate. With that on, a much lower
tolerance can be set, because a 15% tolerance on pre-tax amounts would let a
15% overcharge through.

---

## 6. Policy and approvals

All thresholds and requirements live in `policy_rule`, not code:
- PO required above an amount, or for named vendors/cost types.
- PO approval by amount and role (human only).
- Who may approve exceptions and overrides, up to what amount.
- Compliance holds (DECIDED, in v1): a vendor missing a required document
  (insurance certificate, lien waiver) puts bills on payment hold. v1 is a flag
  and a hold with an expiry date per document type; a person clears or
  overrides it (role-limited, logged). Document file storage is part of the AI
  document table later.

---

## 7. Reports and screens

Reports: commitments by project/cost code (original, changes, revised, billed,
remaining), open POs, received-not-invoiced (GRNI) listing tied to the GL,
unmatched bills, exception queue, subcontract status with retainage held,
price variance.

Screens (Phase 3 style, one view per file): `views_purchase_orders.py` (PO and
subcontract entry), `views_receiving.py`, and a match panel inside the bill
screen with an exception queue. Follow `docs/CLAUDE_UI.md`.

---

## 8. Tests required

Two-way and three-way happy paths; partial receipts and partial billing;
over-quantity and over-price beyond tolerance blocked; within-tolerance passes
with variance recorded; bill with no PO allowed or blocked per policy;
subcontract cumulative cap; subcontract retainage rounding with no drift over
many bills; retainage release cannot exceed held; release posts no cost;
exception blocks approval and payment; override needs reason and role; PO
change approved locks, pending excluded from revised value; receipt posts
accrual and bill clears it exactly; price variance posted; GRNI ties to the GL;
retainage payable ties to the GL; controlled accounts reject manual entries;
duplicate bill number rejected; void of a matched bill reopens the PO line;
closed period rejected; agent path cannot approve.

---

## 9. Placement

- Migration: after the CRM/PM migration (005) and the inventory migration
  (007), because receipts feed inventory and commitments feed job costing. The
  number is assigned at creation; unreleased migrations may be renumbered
  before release.
- Services built with the AP phase; screens with the screens phase; the AP/Ramp
  AI skill pack gains `propose_match`.

---

## 10. Decisions and open questions

Decided:
1. Warehouse stock is job costed at the pull ticket, which names the job.
2. Direct-to-job deliveries need a delivery ticket (receipt) before the cost is
   job costed; the PM may approve a bill without one, costing it at the bill.
3. Compliance hold (insurance / lien waiver) is in v1.
4. Price and amount tolerance default 15%, flexible entry (section 5).
5. Clerk enters, project manager approves.
6. Subcontract work is normally approved through the subcontract (the PO); where
   there is none, the bill approval by the PM is the approval.

7. A subcontractor bill with no subcontract may carry a manual retainage
   withheld amount (with a reason, by the approver). Such bills appear on an
   "approved without commitment" report.
8. Receiving permissions: warehouse staff receive inventory (stock to the
   warehouse); the foreman confirms job-site delivery tickets. Both are
   permissions in the roles and permissions design, not hardcoded roles.
9. Compliance holds block PAYMENT only, not approval. Which document types
   are required is set per vendor type in policy.
10. "Compare before tax" is ON by default: line amounts are matched before tax,
   and tax is checked separately against the expected rate. The 15% default
   tolerance stays as decided, set per company, vendor or PO. PROPOSED: the
   tax check uses its own small tolerance (rounding and rate differences).

Open:
1. Which compliance document types and expiry rules to ship as defaults?
   PROPOSED: insurance certificate and lien waiver, each with an expiry date.
2. Tax tolerance value (PROPOSED a small dollar amount or 1%).
