# Step 2.9 schema replan, area 6: estimates, contracts, pricing, T&M rates, contract templates

Status: **Owner-approved 2026-11-20 (2c82148, answers d297397, b0bea27)** (first draft 2026-11-20, 2c82148; owner answers 2026-11-20 folded in below,
section 15: all A except Q11 (Mark signed, owner's wording), Q12 B, Q13 B and Q21 B; amendment lines written in
area 8 sections 1.3, 4.3 and 5.3, area 15 sections 1.3 and 7.3, and area 18 sections 1.2, 2.4 and 3.2). Docs only: nothing here changes code, a baseline, a migration or a test. No questions are open.
Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan is
approved. PROPOSED items from the sources are not built as final. Amendments this area needs in approved areas 8,
15 and 18 are written there as dated amendment lines (owner 2026-11-20); area 17's is an open item (section 16).

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`: row 6, the source keys, and the "Inbox inputs" for "15 and 6", "6, 8
  (amendment), 15 and 18" and "6, 8, 5 and 19"; rows 7, 9 and 14 for the boundaries.
- `Strata_Teams\shared_decisions.md` 2026-11-19: 12:52 PM (account numbers follow the repo chart), 8:35 PM and 8:34 PM
  (T&M rates and the manual override per row), 8:40 PM (T&M time source and the rate-change control), 8:42 PM
  (service type holds the default payment schedule), 8:50 PM (lead stage warnings), 8:58 PM and 9:28 PM (estimate
  flow), 9:44 PM (which markups can be edited), 9:48 PM (margin % and Reasons), 9:58 PM and 10:10 PM (field event to
  PCO to CO; two ways in), 10:22 PM (change order terms template), 11:20 PM (planning's provisional records).
- `Strata_Teams\inbox\to_ux_research.md`: planning 2026-11-19 "T&M rate cards, schedules and billing" (8:42 PM
  answer) and "provisional records and calls for estimate flow, Reasons, field event → PCO → CO" (11:20 PM); the
  2026-11-15 design entries "routing setting and Send to picker" (C120) and "contract builder" (C121).
- `Strata_Teams\inbox\to_planning.md`: 2026-11-18 "lead expected value comes from the sent estimate"; 2026-11-19
  "time-and-materials rate cards and schedules" (8:35 PM) and "estimate flow needs records and data calls" (9:28 PM).
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md` (the row's A sources): 2026-11-14 "estimate =
  contract (owner): data and service rules"; 2026-11-15 "contract editor, data and services" (10:35 PM); 2026-11-16
  "estimate payment schedule and AIA billing" (3:22 PM) and "schema needs from today's mockup rounds (CODE_CHANGES
  125-130)".
- `Strata_Teams\ux_research_contract_editor_2026-11-15.md` (whole; owner decisions 10:35 PM).
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 22, 24, 76, 102, 105, 121, 122 (the contract-builder and
  "one price" items), 123 (payment schedule per service type), 124 (payment schedule and contract editor), 125,
  126-129, 130 (payment schedule only).
- docs/next_step.md "Handed to later areas" (areas 8, 15, 17 and STOP C items for area 6).
- docs/replan_2.9/area_8_pm_schedules.md sections 1.3, 5.3 (and its amendments), 5.4 and open items 4 and 13;
  area_15_crm.md sections 0, 1.4-1.6, 3.3, 7 (Reasons) and 9 (boundaries) and open item 2; area_18 sections 1.2
  (reasons), 2.4 (codes) and 3 (attachments); area_17 via next_step.md.
- docs/decisions_2026-11-11.md by code: D5, D8, D9, RI1; docs/design_decisions.md "CRM and project lifecycle" and
  "Customer codes".
- `migrations/001_company.sql` (estimate, contract, cost code, project, budget, change order, approval, settings
  tables), `templates/coa/construction.csv` (roles), `modules/services/permissions.py`, `sequences.py`,
  `custom_fields.py`, `chart_templates.py`.

---

## 0. Summary

| # | Topic | Proposal in one line | Baseline |
|---|-------|----------------------|----------|
| 1 | Estimate and revisions | `estimate` (one per deal and option: number EST-, lead, service type, sales rep, customer link) and `estimate_revision` (Rev n: status, holder, valid-until, payment schedule, pricing, customer block, sent and signed facts). A sent revision is frozen; editing makes Rev n+1 | company |
| 2 | Hand-off and history | Status plus `holder_user_id` on the revision; seven working states from the 11:20 PM record plus Sent, Declined, Expired, Signed, Superseded, Cancelled; insert-only `estimate_revision_history` with reasons from `reason_option` | company |
| 3 | Cost lines and pricing | One `estimate_cost_line` (kind Material or Other; cost code always set; material code from area 9). Price from the service type's `pricing_template` (markup per cost type, fixed or editable); the rep's extra markup or discount on the revision. Summary by cost code derived, never stored; it becomes the job budget at signing. `cost_template` for saved line sets | company |
| 4 | Approval and authority | "Estimate approval" is area 14's `approval_policy` row for 'Estimate', OFF by default (11:20 PM, RI1, D9). Off: the PM's submit goes straight to Approved, logged. Rep limits are policy records, OFF, read only when the control is on. Margin floor and target warn only | company |
| 5 | Payment schedule and SOV | On the revision: schedule type (Progress billing, Milestones, Fixed price, Time and materials), deposit, retainage, not-to-exceed; `estimate_milestone` rows; SOV lines with their cost codes. Defaults come from the service type (area 8 amendment). Copied to the contract at signing | company |
| 6 | T&M rates | `rate_card` and `rate_card_line`; `company_settings.tm_rate_source` and the company card; the control "Estimates may change their rates" ON (permissive) by default; `estimate_rate_line` frozen on the revision and `contract_rate_line` at signing; a row typed by hand keeps its source rate and a reason | company |
| 7 | Contract templates | `contract_template` (kind Contract or Change order terms), insert-only published `contract_template_version` with `contract_template_section` rows, a `contract_clause` library; per-revision section choices and wording overrides; control "Contract wording changes need approval" OFF | company |
| 8 | Send, decline, expire, revise | Send freezes the revision, stores the rendered PDF as an attachment, calls `leads.take_expected_value`; Declined with a reason; Expired by a daily run or by area 15's auto-lost; Revise copies to Rev n+1 | company |
| 9 | Signing | One "Mark signed" action (`contracts.mark_signed`, Q11): signed document required, no per-signer record, customer via area 5, job via area 7, budget from the summary, contract row, SOV, milestones, frozen rates, a draft (unposted) deposit invoice via area 5, the lead to Contract signed and Won via area 15 | company |
| 10 | Contract record and change orders | Keep `contract`, written once at Mark signed as the signed agreement (Q1 A), number from its own CT- series (Q21 B); revised amount derived from SOV lines, CO lines add SOV lines (area 8's approval calls area 6); `sales_rep_user_id` kept as the rep at signing | company |
| 11 | Cancellation (C105) | `contracts.cancel`: reason (kind 'Job cancel'), date received, case link; never posts; approval OFF by default; job Closed as Cancelled (area 8), revision Cancelled | company |
| 12 | Permissions | Keep `estimate.create`, `estimate.approve`, `contract.approve`; add `estimate.view`, `estimate.send`, `contract.sign`, `contract.cancel`, `sales.templates.manage` (Q19 A) | master (codes) |
| 13 | Row version and audit | `row_version` on every editable table; history and published versions insert-only with integrity triggers; every table audited | company |

Boundaries (flagged, not designed here): `cost_type` and `cost_code.cost_type_id` are area 7's (the 11:20 PM record
decided them; area 6 only reads a cost code's type); `material_code` is area 9's (C129); customer creation and the
deposit and T&M invoices are area 5's; the job, its budget rows and `project.sales_rep_user_id` are area 7's; stages,
schedules and change orders are area 8's; approval routing and policy records are area 14's; the notification feed
is area 21's; sending email is area 20's.

---

## 1. Estimate and revisions

### 1.1 Current state

- `estimate` (`001_company.sql:209`): `estimate_number` TEXT NOT NULL UNIQUE, `name`, `contact_id` NOT NULL FK contact
  (`:217`), `assigned_pm_id`, `total_cost_cents`, `total_price_cents`, `status` CHECK IN ('Draft', 'Submitted',
  'Approved', 'Won', 'Lost') (`:225`), `created_at` DEFAULT CURRENT_TIMESTAMP. No revision, lead, service type, sales
  rep, valid-until or payment schedule; no `row_version`.
- `estimate_line` (`:232`): `estimate_id` ON DELETE CASCADE, `cost_code_id` NOT NULL, `quantity` REAL > 0,
  `unit_of_measure`, `estimated_unit_cost_cents`, `estimated_extended_cost_cents`, `price_to_customer_cents`.
- `project.source_estimate_id` FK estimate (`:264`); `project_budget.estimate_line_id` FK estimate_line (`:290`).
- No service reads or writes either table. `custom_fields.py:21` and `:48` refuse record type Estimate "until an
  estimate service exists" (STOP C). `permissions.py:67-68` has `estimate.create` and `estimate.approve` (sensitive);
  `approval_policy.document_type` already lists 'Estimate' and 'Contract' (`:1103`).

### 1.2 Decided

| Decision | Source |
|----------|--------|
| The estimate is the contract: one document per revision carries the cost build-up and the contract content; prior revisions are immutable; editing after sent makes a new revision | A 11-14 "estimate = contract"; contract editor 2026-11-15 |
| Estimate number from the Estimates series (EST-) and a version (v1, v2); options on a lead (Option A) each with their own status | C125 |
| A lead's proposal is its latest sent revision; the lead's expected value is taken from that revision's contract total at send | A 11-18 "lead expected value"; area 15 section 1.4 (Q4 A, Q5 A) |
| The rep starts the estimate from the lead (3-step wizard: Customer, Job, Who enters costs); the rep may skip the PM; Solo always does | S 11-19 8:58 PM items 1-2 |
| The PM enters costs only; the price comes from the service type's pricing template; the rep may add markup or discount on the final step | S 11-19 8:58 PM item 4 |
| One estimate page: header (status, lead, service type, sales rep, who entered costs, approver, valid until), Customer price, Payment schedule, Proposal cards, then tabs Costs · Contract · Approval and history; editing costs after approval sends it back to approval (if on) | S 11-19 9:28 PM item 3 |
| Customer on the estimate: link an existing customer or "create on signing" (null = create from the estimate's customer fields); the picker works until signing | C126, C127, C129 |
| Signing passes the lead's addresses, contacts and signer to area 5; the estimate copies `lead.sales_rep_user_id` | area 15 section 9 (hand-off) |
| `estimate.lead_id` added; `estimate.contact_id` nullable before signing | area 15 open item 2 |
| `estimate.lead_id` is NOT NULL; the wizard's first step picks an existing lead or creates one in the same transaction (a repeat customer's lead is made inside the wizard, no separate lead form first); a lead made there gets the service type chosen at wizard step 2 (Job) | owner 2026-11-20, Q4 |

### 1.3 Proposed schema

**`estimate`** (replaced; one row per deal and option):

| Column | Type and constraint |
|--------|---------------------|
| `estimate_id` | INTEGER PRIMARY KEY |
| `estimate_number` | TEXT NOT NULL UNIQUE; from `sequences.py`, series EST- (unique, gaps allowed; not a registered gapless series) |
| `lead_id` | INTEGER NOT NULL REFERENCES lead (Q4 A: the wizard creates the lead in the same transaction when there is none, through area 15's `leads.create`) |
| `option_label` | TEXT NULL (for example "Option A"); UNIQUE (`lead_id`, `option_label`) |
| `service_type_id` | INTEGER NOT NULL REFERENCES service_type; copied from the lead at creation; changes only with the lead's (area 15: a lead's service type is locked once an estimate names it) |
| `customer_contact_id` | INTEGER NULL REFERENCES contact; NULL = create the customer at signing; the service checks a linked contact has a customer code |
| `sales_rep_user_id` | INTEGER NULL (plain integer, user in the master); copied from `lead.sales_rep_user_id` at creation, follows the lead until signing |
| `current_revision_id` | INTEGER NULL REFERENCES estimate_revision (the newest revision; set by the service) |
| `memo` | TEXT CHECK (length <= 4000) (area 18 memo rule) |
| `created_by`, `created_at` | INTEGER NOT NULL, TEXT NOT NULL (from `context.now`) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

The old `name`, `contact_id`, `assigned_pm_id`, `total_*`, `status` and `created_at` DEFAULT are dropped: the name is
the lead's, totals are per revision, status is per revision (Q5 A).

**`estimate_revision`** (new; Rev 1, 2, ...):

| Column | Type and constraint |
|--------|---------------------|
| `revision_id` | INTEGER PRIMARY KEY |
| `estimate_id` | INTEGER NOT NULL REFERENCES estimate |
| `revision_no` | INTEGER NOT NULL CHECK (>= 1); UNIQUE (`estimate_id`, `revision_no`) |
| `status` | TEXT NOT NULL CHECK IN ('With rep', 'With PM', 'In approval', 'Sent back', 'Approved', 'Ready to send', 'Sent', 'Declined', 'Expired', 'Signed', 'Superseded', 'Cancelled') (section 2) |
| `holder_user_id` | INTEGER NULL; NOT NULL while the status is a working state (CHECK) |
| `costs_by_user_id` | INTEGER NULL (who entered costs; the default job PM at signing, A 11-14) |
| `costs_due_on` | TEXT NULL CHECK date (the PM's due date) |
| `valid_until` | TEXT NULL CHECK date; required to send (service) |
| `pricing_template_id` | INTEGER NULL REFERENCES pricing_template (the template applied) |
| `rep_markup_pct`, `rep_discount_pct` | REAL NULL CHECK (0-100) (the rep's adjustment, section 3; Q7 A) |
| `rep_discount_cents` | INTEGER NULL CHECK (>= 0) (a typed lump-sum contract total is stored as this discount; Q7 A) |
| `schedule_type`, deposit, retainage, `not_to_exceed_cents` | section 5 |
| `contract_template_version_id` | INTEGER NULL REFERENCES contract_template_version (section 7) |
| `show_line_detail` | INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1) (C76: totals only by default) |
| Customer block | `customer_legal_name`, `billing_line1`, `billing_line2`, `billing_city`, `billing_region`, `billing_postal`, `billing_country`, and the same seven for `site_`; TEXT NULL; filled from the lead or linked customer at creation, editable until sent (Q8 below covers wording, not these) |
| `cost_total_cents`, `contract_total_cents` | INTEGER NULL; written by the service only at send (frozen figures the lead, reports and signing read); NULL while working (the page shows computed figures) |
| `sent_at`, `sent_by`, `sent_method`, `sent_to` | NULL until sent; `sent_method` CHECK IN ('Email', 'Download', 'Print', 'Marked sent'); `sent_to` TEXT (addresses) |
| `sent_attachment_id` | INTEGER NULL REFERENCES attachment (the rendered PDF kept unchanged, contract editor item 3) |
| `decided_at`, `decided_by`, `decision_reason_id`, `decision_reason_label` | Declined, Expired or Cancelled facts; `decision_reason_id` FK reason_option ON DELETE RESTRICT |
| `memo` | TEXT CHECK (length <= 4000) |
| `created_by`, `created_at`, `row_version` | as above |

CHECKs: the six working states ('With rep', 'With PM', 'In approval', 'Sent back', 'Approved', 'Ready to send')
need `sent_at` NULL; 'Sent', 'Declined', 'Expired', 'Signed' and 'Superseded' need it set; 'Cancelled' allows either
(an abandoned draft or a cancelled signed contract); the sent columns all set or all NULL; `contract_total_cents` and `cost_total_cents` set exactly when sent.

Partial unique index: one open (unsent) revision per estimate, UNIQUE (`estimate_id`) WHERE `sent_at` IS NULL AND
`status` NOT IN ('Superseded', 'Cancelled').

**Integrity trigger (H4, rule "sent revisions are immutable", A 11-14):** once `sent_at` is set, an UPDATE may change
only `status`, `holder_user_id` (to NULL), the decision columns, `memo` and `row_version`; the child rows of a sent
revision (cost lines, milestones, SOV lines, rate lines, section choices) refuse INSERT, UPDATE and DELETE. This is
the same kind of lock as area 8's approved change order lines; workflow (who may send, when) stays in the service.

### 1.4 Effect on existing services and tests

- No service exists. `estimates.py` (new): create from a lead, revise, read (`estimate.view`), save costs, apply a
  pricing template, set the rep's adjustment, hand off, send, decline, `mark_expired`, `run_expiry`.
- `custom_fields.py` keeps refusing Estimate until `estimates.py` exists; then the refusal is removed and its test
  replaced (open item 9).
- `sequences.py` gains the EST- series and the CT- contract series (Q21 B).

### 1.5 Tests to write later

- Creating an estimate from a lead copies service type and sales rep; an estimate without a lead is refused (Q4 A).
- The wizard with "new lead" writes the lead (service type from step 2) and the estimate in one transaction; a
  failure in either leaves neither.
- Two open revisions on one estimate are refused (partial unique index).
- After send, an UPDATE of a sent revision's price columns and any change to its child rows is refused by the
  trigger; status, decision columns and memo still change.
- Revise copies every child row to Rev n+1 and marks Rev n Superseded only when Rev n+1 is sent (Rev n stays the
  signable sent copy until then; section 8).
- `estimate_number` comes from the series; two estimates in two transactions never share a number.

---

## 2. Hand-off states and history

### 2.1 Current state

`estimate.status` is the only state (`:225`). No holder and no history. The approvals tables (`approval_request`,
`:1124`) exist for the routed approval.

### 2.2 Decided

| Decision | Source |
|----------|--------|
| States: With rep, With PM, In approval, Sent back, Approved, Ready to send, Sent; hand-off is a status plus a holder with insert-only history (from/to status, from/to holder, reason id + label for send back, who, when) | S 11-19 11:20 PM; to_ux_research 11:20 PM item 3 |
| Estimate approval OFF: the PM goes from costs straight to Approved (logged) and In approval is never used; ON: area 14 routes it | S 11-19 11:20 PM |
| Send back needs a reason from the Reasons list (kind Send back); "Other" needs at least 10 characters | S 11-19 9:48 PM; area 15 section 7 |
| The PM can "Ask the rep" and "Send back to the rep with a reason"; the approver approves or sends back with a reason | S 11-19 8:58 PM items 3 and 5 |
| Declined with a reason (the lead moves to Lost on confirm); Expired when valid-until passes | contract editor section 4 |

### 2.3 Proposed schema and rules

**Moves** (`estimates.hand_off`; each writes the revision and one history row in one transaction):

| From | To | Who | Holder after |
|------|----|-----|--------------|
| (create) | With rep | `estimate.create` | the rep |
| With rep, Sent back | With PM | the holder | the chosen PM (Send to picker) |
| With rep (rep enters costs), With PM | Approved (control OFF) or In approval (control ON) | the holder | the rep (Approved) or area 14's approver (In approval) |
| With PM | Sent back | the holder, reason (kind Send back) | the rep |
| In approval | Approved or Sent back | the approver (`estimate.approve`), reason to send back | the rep |
| Approved | Ready to send | the rep, when the send checklist passes (Q6 A) | the rep |
| Approved, Ready to send | With PM, In approval | costs edited (control ON: back to In approval; OFF: stays, logged) | as above |
| Ready to send | Sent | `estimate.send` (section 8) | NULL |
| Sent | Declined, Expired, Signed | section 8 and 9 | NULL |
| any unsent | Cancelled | the estimate is abandoned (reason) | NULL |
| Sent | Superseded | when a later revision is sent | NULL |

**`estimate_revision_history`** (new, insert-only):

| Column | Type and constraint |
|--------|---------------------|
| `history_id` | INTEGER PRIMARY KEY |
| `revision_id` | INTEGER NOT NULL REFERENCES estimate_revision |
| `from_status`, `to_status` | TEXT (`from_status` NULL on the first row); `to_status` CHECK as the revision |
| `from_holder_user_id`, `to_holder_user_id` | INTEGER NULL |
| `reason_id`, `reason_label` | FK reason_option ON DELETE RESTRICT, and the label at the time (area 15 fix a) |
| `note` | TEXT NULL (Ask the rep, approver's note) |
| `changed_by`, `changed_at` | INTEGER NOT NULL, TEXT NOT NULL (`context.now`) |
| `origin` | TEXT NOT NULL DEFAULT 'Human' CHECK IN ('Human', 'System') (System: expiry run, auto-lost) |

Integrity triggers: no UPDATE, no DELETE (append-only history, like `lead_stage_history`). The Approval and history
tab reads this table plus area 14's approval actions and the audit rows for wording and rate changes.

### 2.4 Tests to write later

- Every allowed move writes exactly one history row; a move not in the table is refused with one sentence.
- Send back without a reason is refused; "Other" under 10 characters is refused.
- With the control OFF, submit from With PM lands on Approved and never on In approval; with it ON, it lands on In
  approval and an `approval_request` row exists.
- Only the holder (or `estimate.approve` for In approval) can move a working revision; the UI hiding is not relied on.
- UPDATE and DELETE on `estimate_revision_history` are refused.

---

## 3. Cost lines, pricing templates, cost templates

### 3.1 Current state

- `estimate_line` (`:232`): one kind, cost code required, no material code, no markup column, no price override.
- `cost_code` (`:30`): `cost_type_label` TEXT NOT NULL (`:38`, free text such as "Cement"), `account_id` (default GL
  account). No `cost_type` table. No `material_code`, `pricing_template` or `cost_template` table.

### 3.2 Decided

| Decision | Source |
|----------|--------|
| Estimate cost lines are one table with kind Material or Other; Material lines carry the material code and take the cost code from it (editable per line, C129); Other lines carry a cost code; quantity, unit cost, markup | S 11-19 11:20 PM; C129 |
| The summary by cost code (cost code, cost type, total cost) is derived and becomes the job budget at signing | S 11-19 9:28 PM item 1; 11:20 PM |
| `cost_type` is a company list (shipped five: Labor, Material, Equipment, Subcontract, Other); every cost code has one; a used type cannot be deleted | S 11-19 11:20 PM (area 7's table) |
| Pricing templates per service type hold a markup per cost type with an editable flag; fixed lines show the R37 locked style "Set by the <template> pricing template" | S 11-19 9:44 PM, 11:20 PM |
| Lines show Markup and Margin % (margin = (price − cost) / price), overall margin on the Total row | S 11-19 9:48 PM item 1 |
| Price from markup, markup from price: price = cost × (1 + markup); a typed price is kept as the line's price; changing cost, quantity or markup recomputes it | C125 |
| Cost templates: name, service type, lines of both kinds (material lines keep their material code) | C125, C129 |
| Services do all money arithmetic (rule e); the page shows the figures the service returns | to_ux_research 11:20 PM |

### 3.3 Proposed schema

**`estimate_cost_line`** (replaces `estimate_line`):

| Column | Type and constraint |
|--------|---------------------|
| `line_id` | INTEGER PRIMARY KEY |
| `revision_id` | INTEGER NOT NULL REFERENCES estimate_revision |
| `kind` | TEXT NOT NULL CHECK IN ('Material', 'Other') |
| `material_code_id` | INTEGER NULL; plain integer until area 9 adds `material_code`, then FK in the same baseline pass; CHECK set exactly when `kind = 'Material'` |
| `cost_code_id` | INTEGER NOT NULL REFERENCES cost_code (Material: from the material code, editable) |
| `description` | TEXT NOT NULL |
| `quantity` | REAL NOT NULL CHECK (> 0) |
| `unit` | TEXT NOT NULL |
| `unit_cost_cents` | INTEGER NOT NULL CHECK (integer, >= 0) |
| `cost_cents` | INTEGER NOT NULL (= round(quantity × unit cost), written by the service) |
| `markup_pct` | REAL NOT NULL DEFAULT 0 CHECK (>= -100) |
| `price_override_cents` | INTEGER NULL (a typed price; NULL = from markup) |
| `price_cents` | INTEGER NOT NULL (written by the service) |
| `sort_order` | INTEGER NOT NULL |
| `row_version` | INTEGER NOT NULL DEFAULT 1 |

The cost type is not stored: it is the cost code's (area 7), so a line and the summary always agree. Margin is
derived. Index (`revision_id`, `sort_order`).

**`pricing_template`** (new): `pricing_template_id` PK, `name` TEXT NOT NULL UNIQUE COLLATE NOCASE, `is_active`,
`row_version`. **`pricing_template_line`**: `pricing_template_id` FK, `cost_type_id` FK cost_type (area 7),
`markup_pct` REAL NOT NULL, `markup_editable` INTEGER NOT NULL DEFAULT 1 CHECK IN (0, 1), PRIMARY KEY
(`pricing_template_id`, `cost_type_id`), `row_version`. A cost type with no row in the template means markup 0,
editable. The service type names its template (`service_type.pricing_template_id`, area 8 amendment, open item 3);
several types may share one.

Rules (`estimates.py`, `pricing.py`): applying a template sets each line's `markup_pct` from its cost type; on a fixed
line the service refuses a different `markup_pct` or a `price_override_cents` ("This markup is set by the <name>
pricing template."). "Markup on every line" (C76) skips fixed lines and says how many it skipped. The rep's
adjustment is applied to the total, not to the lines; the contract total is the sum of line prices × (1 + rep
markup) minus the discount, in integer cents, with the rounding rule stated once in `money.py`.

**`cost_template`** (new): `cost_template_id` PK, `name` NOT NULL, `service_type_id` NULL FK, `is_active`,
`row_version`; **`cost_template_line`**: same columns as `estimate_cost_line` without `revision_id`, prices and
override (cost side only), plus `cost_template_id` FK. "Insert template" appends copies; a template never links to
the estimate after insert.

**Summary by cost code** (derived, no table): per revision, cost code, its cost type, sum of cost, sum of price.
Signing writes the job's budget rows from it through area 7's budget service (section 9).

### 3.4 Boundary with area 7 and area 9

Area 6 needs from area 7: `cost_type` (company list, five shipped, `is_shipped`, `is_active`, `sort_order`), and
`cost_code.cost_type_id` NOT NULL replacing the free-text `cost_type_label` (`:38`). Area 7 decides migration of the
label, the leaf-only rule for estimate lines (RP5: postings go to active leaf codes; estimates should follow) and
`project_budget`'s columns. Area 6 needs from area 9: `material_code` (C129: code MAT-, description, vendor, SKU,
unit, default cost code, standard unit cost, optional inventory item). Until area 9 exists the Material kind cannot
be offered (the column stays a plain integer, open item 5).

### 3.5 Tests to write later

- `cost_cents` and `price_cents` are integer cents and match `money.py`'s rounding; a typed price survives a
  re-read and is cleared by Reset.
- A fixed-markup line refuses a markup change and a price override; Markup on every line skips it and reports it.
- A Material line without a material code, or an Other line with one, is refused (CHECK).
- The summary groups by cost code and sums to the revision's cost and price totals exactly.
- Inserting a cost template appends lines; editing the template later does not change the estimate.

---

## 4. Approval, authority and margin

### 4.1 Current state

`approval_policy` and `approval_request` (`:1103`, `:1124`) list document types 'Estimate' and 'Contract'.
`company_settings.require_separate_approver` (default 0) is read by the journal entry trigger only (`:3705`). No
authority limits, margin floor or target.

### 4.2 Decided

| Decision | Source |
|----------|--------|
| Estimate approval is a control, OFF by default; rep markup and discount limits are policy records, OFF, effective only when the control is on | S 11-19 11:20 PM; RI1; D9; C122 leftovers ("Estimates approval default is Off") |
| The rep can add markup or discount; past their authority it goes back to approval | S 11-19 8:58 PM item 4 |
| Margin floor and target colour the summary (amber under target, red under floor); Send warns, without stopping, under the floor when approval is off | C76, C125 |
| Editing costs after approval sends it back to approval (if on) | S 11-19 9:28 PM item 3 |

### 4.3 Proposed

- The control is area 14's `approval_policy` row for document type 'Estimate' (no new switch, no second approval
  mechanism). OFF = no active policy. The Controls page lists it (section 0 of CLAUDE.md).
- **Authority limits** (Q14 A): `sales_authority_limit` (new): `limit_id` PK, `scope` CHECK IN ('Role', 'User'),
  `role_code` TEXT NULL, `user_id` INTEGER NULL (CHECK exactly one by scope), `max_discount_pct` REAL NULL,
  `max_extra_markup_pct` REAL NULL, `is_active` DEFAULT 0, `row_version`; read only when the Estimate policy is
  active. A revision whose rep adjustment exceeds the holder's limit goes to In approval; under the limit it stays.
- **Margin floor and target** (Q15 A): `company_settings.estimate_margin_floor_pct` REAL NULL DEFAULT 20 and
  `estimate_margin_target_pct` REAL NULL DEFAULT 22; warnings only (a NULL turns the colour off). With the control
  ON a policy condition "under the margin floor" is area 14's (C76's rule), not a column here.
- **Self-approval** follows the company's separation-of-duties control (Q3 A): with `require_separate_approver` OFF a
  pricer may approve their own revision, marked Self-approved; ON, it is refused.

### 4.4 Tests to write later

- With no active Estimate policy, no `approval_request` is ever written and the rep's adjustment is not limited.
- With the policy and a limit active, a discount over the limit routes to In approval; at the limit it does not.
- Under the floor with the control off: Send returns a warning and succeeds.
- Self-approval is allowed and marked when `require_separate_approver` is 0; refused when it is 1.

---

## 5. Payment schedule and schedule of values

### 5.1 Current state

- `contract` (`:878`): `contract_type` CHECK IN ('Fixed price', 'Cost-plus', 'Time and materials', 'Unit price'),
  `original_amount_cents`, `retainage_pct` REAL (`:888`), `payment_terms` TEXT.
- `contract_line` (`:189`) is the SOV: `sov_line_id`, `contract_id`, `line_number`, `description`, one
  `cost_code_id`, `scheduled_value_cents`, `sort_order`, `change_order_id` INTEGER without FK (`:205`).
- No deposit, milestone or estimate-side schedule. `service_type` (`:3940`) holds no defaults.

### 5.2 Decided

| Decision | Source |
|----------|--------|
| Schedule type: Progress billing (AIA pay apps), Milestones, Fixed price (bill on completion), Time and materials; default from the service type; becomes the job's billing method at signing | A 11-16 3:22 PM item 1; S 11-19 8:42 PM |
| Deposit with progress billing is credited pro rata on each pay app ("Less deposit applied") until used; the SOV stays the full contract sum; the pay app service needs a deposit-remaining balance per job | A 11-16 3:22 PM item 2 (account: customer deposits role, 2320 in the repo chart, S 11-19 12:52 PM) |
| SOV lines start as one per cost code; can be renamed, merged and split; the SOV total equals the contract price; each SOV line keeps its cost codes; stored per revision; carried to the job at signing | A 11-16 3:22 PM item 3 |
| Milestones: name, share, billed when; add up to 100% with the deposit; the last payment takes the rounding | S 11-19 8:42 PM item 1; C122 ("one price") |
| Service types › Defaults holds the full default payment schedule; a new estimate copies it; the hint says "Default from the service type" or "Changed from the service type default" | S 11-19 8:42 PM items 1-2 |
| With a not-to-exceed amount, deposit and retainage use it; without one, a T&M deposit is a fixed amount | S 11-19 8:35 PM item 3 |
| Signing creates the billing schedule and a draft deposit invoice (not posted) | contract editor; A 11-15 10:35 PM item 7 |
| A schedule milestone may link to a payment-schedule milestone (area 8 `job_schedule_task.payment_milestone_id`, FK added by area 6) | area 8 section 4.3, open item 4 |

### 5.3 Proposed schema

On **`estimate_revision`**: `schedule_type` TEXT NOT NULL CHECK IN ('Progress billing', 'Milestones', 'Fixed price',
'Time and materials'); `deposit_pct` REAL NULL CHECK (0-100); `deposit_cents` INTEGER NULL (CHECK not both set);
`retainage_pct` REAL NULL CHECK (0-100); `not_to_exceed_cents` INTEGER NULL CHECK (> 0) (T&M only, CHECK).

**`estimate_milestone`** (new; Milestones only): `milestone_id` PK, `revision_id` FK, `sort_order`, `name` NOT NULL,
`share_pct` REAL NOT NULL CHECK (> 0 AND <= 100), `billed_when` TEXT NOT NULL (free text "Equipment delivered"),
`row_version`. The service checks deposit + shares = 100 before send; amounts are derived from the contract total
(last row takes the rounding).

**`estimate_sov_line`** (new; Progress billing): `sov_line_id` PK, `revision_id` FK, `sort_order`, `description`,
`scheduled_value_cents` INTEGER NOT NULL, `row_version`; **`estimate_sov_line_cost_code`** (`sov_line_id`,
`cost_code_id`) PRIMARY KEY both (Q16 A: a merged line keeps several cost codes; a cost code sits on one SOV line of
a revision, UNIQUE (`revision_id` via the line, `cost_code_id`) checked by the service). The service rebuilds the
default lines from the summary until the rep edits them, and checks the SOV total equals the contract total before
send (a price change spreads in proportion, remainder on the last line, C125).

**Service type defaults** (area 8 amendment, open item 3): `service_type.default_schedule_type`,
`default_deposit_pct`, `default_retainage_pct`, `pricing_template_id`, `contract_template_id`,
`co_terms_template_id`, and `service_type_milestone` (rows as `estimate_milestone` with `service_type_id`); no
cancellation period (Q12 B: it is on the template version, section 7.3). `service_type.rate_card_id` (area 8)
becomes a nullable FK to `rate_card`; NULL falls back to the company card.

**At signing** (section 9) the contract gets copies: `contract.schedule_type` (replacing `contract_type`, Q20 A),
deposit, retainage, not-to-exceed; `contract_milestone` (new: `contract_milestone_id` PK, `contract_id` FK,
`sort_order`, `name`, `share_pct`, `amount_cents` INTEGER NOT NULL, `billed_when`, `invoice_id` NULL FK invoice
(area 5 sets it when billed), `row_version`), which is the FK target of area 8's `payment_milestone_id`;
`contract_line` rows from the SOV with **`contract_line_cost_code`** (`sov_line_id`, `cost_code_id`) replacing the
single `contract_line.cost_code_id` (Q16 A). `contract_line.change_order_id` becomes an FK to `change_order`.

### 5.4 Tests to write later

- Send is refused (one sentence naming what is short or over) when deposit + milestones ≠ 100% or SOV total ≠
  contract total.
- Milestone amounts sum exactly to the contract total; the last takes the rounding.
- A new estimate copies the service type's defaults; changing them on the estimate leaves the service type unchanged.
- With not-to-exceed, the deposit base is the NTE; without it, a T&M deposit must be a fixed amount (CHECK).
- Signing copies milestones and SOV lines with their cost codes; area 8's task can link to a `contract_milestone`.

---

## 6. Time-and-materials rates

### 6.1 Current state

No rate tables. `time_entry` (`:1039`) has `wage_cents` and `burden_cents`, no bill rate. Area 8 added
`service_type.rate_card_id` as a plain integer until this area adds `rate_card` (area 8 open item 13).

### 6.2 Decided

| Decision | Source |
|----------|--------|
| Each company chooses where T&M rates come from: one company rate card, a rate schedule per service type (falls back to the company card), or the estimate's own cost lines (cost × markup) | S 11-19 8:35 PM item 1 |
| A rate schedule: labor per role or trade with the unit (person-hour, crew-hour, day), equipment rates, materials at cost plus %, subcontracts at cost plus % | S 11-19 8:35 PM item 2 |
| "Estimates may change their rates" is a control ON (permissive) by default; each change needs a reason and is logged; a company can turn it off | S 11-19 8:40 PM |
| Any T&M row's unit and rate can be typed by hand; the row shows "Changed from <source rate and unit>" with Reset; reason required, logged; locked rows show R37 with the reason | S 11-19 8:34 PM |
| Rates are copied onto the estimate when it is created and frozen onto the contract at signing; later card changes never touch them; not-to-exceed on estimate and contract | to_ux_research 8:42 PM |
| T&M time in v1 comes from payroll import hours (employee, job, cost code), approved when the import posts (area 19); timesheets later | S 11-19 8:40 PM |
| Discounts and price overrides never change the rates | S 11-19 8:35 PM item 3 |

### 6.3 Proposed schema

**`rate_card`** (new): `rate_card_id` PK, `name` NOT NULL UNIQUE COLLATE NOCASE, `effective_from` TEXT NULL CHECK
date, `effective_to` TEXT NULL CHECK date (CHECK from <= to), `is_active`, `row_version`.

**`rate_card_line`** (new): `line_id` PK, `rate_card_id` FK, `kind` CHECK IN ('Labor', 'Equipment', 'Material',
'Subcontract'), `label` TEXT NOT NULL (role, trade or equipment; Material and Subcontract one row each), `unit`
TEXT NULL CHECK IN ('Person-hour', 'Crew-hour', 'Day') (Labor and Equipment: required), `rate_cents` INTEGER NULL
(Labor and Equipment: required), `markup_pct` REAL NULL (Material and Subcontract: required), `sort_order`,
`row_version`; UNIQUE (`rate_card_id`, `kind`, `label`, `unit`).

**`company_settings`** (new columns): `tm_rate_source` TEXT NOT NULL DEFAULT 'Company card' CHECK IN ('Company
card', 'Service type', 'Estimate'); `company_rate_card_id` INTEGER NULL FK rate_card; `allow_estimate_rate_change`
INTEGER NOT NULL DEFAULT 1 CHECK IN (0, 1) (a control, ON by default as the owner decided, listed on the Controls page
and logged).

**`estimate_rate_line`** (new; T&M revisions): `rate_line_id` PK, `revision_id` FK, `kind`, `label`, `unit`,
`rate_cents`, `markup_pct` (as `rate_card_line`), `source` CHECK IN ('Company card', 'Service type', 'Estimate'),
`source_rate_card_line_id` INTEGER NULL FK, `source_unit`, `source_rate_cents`, `source_markup_pct` (what Reset
returns to), `change_reason_id` FK reason_option (kind 'Rate change') ON DELETE RESTRICT, `change_reason_label`,
`change_note` TEXT NULL (Q13 B, owner 12:50 AM: a reason and a short note are both required when the row differs from
its source; with Other the note is at least 10 characters), `changed_by`, `changed_at`, `sort_order`, `row_version`. With source 'Estimate' the rows are built from the cost lines (cost ×
markup) and have no card line.

**`contract_rate_line`** (new): the same columns with `contract_id` in place of `revision_id`, written once at
signing, insert-only (integrity trigger: no UPDATE, no DELETE; the frozen copy area 5's T&M draft reads).

Rules: with `allow_estimate_rate_change` = 0 the service refuses a row that differs from its source ("Rates on
estimates are locked to the rate card in Controls."); the effective card is the one whose dates cover the
revision's creation date (`context.today`). The T&M monthly draft and the near-NTE warning are area 5's, from
posted payroll hours (area 19) at the contract's frozen rates.

### 6.4 Tests to write later

- Source Service type with no card on the type falls back to the company card.
- Typing a rate keeps the source columns; Reset restores them; a change without a reason, or with a reason but no
  note, is refused; with Other the note must be at least 10 characters.
- With the control off, a changed row is refused; with it on, the change is audit-logged with the reason.
- A card edit after signing changes neither the estimate's nor the contract's rate lines; UPDATE on
  `contract_rate_line` is refused.

---

## 7. Contract templates and wording

### 7.1 Current state

No template tables. `contract.document_ref` and `contract.notes` (`:878`) are free text. `file_attachment` (`:74`)
is replaced by area 18's `attachment`.

### 7.2 Decided

| Decision | Source |
|----------|--------|
| Templates per service type with versions; Publish makes a new version; sent and signed contracts keep the version they were sent with; each service type uses one published template | C121; contract editor section 5 |
| Sections with title, text, "Show this section" condition, "Reps may turn it off", "Reps may change the wording" (off for locked legal sections) | contract editor sections 3 and 5; C121 |
| Limited rich text (bold, italic, underline, H2/H3, lists, table block, page break, field keys); a clause library whose edits offer to update every template using it, each as a new draft version | C122, C123, contract editor section 5 |
| A rep may change one deal's wording; changes are marked against the template (Compare, Reset, a required one-line reason) and logged; "Contract wording changes need approval" is a Sales control, OFF by default | contract editor owner decision 4 and section 3 |
| Several signers per contract (name, email, title, order) print on the contract; the company signer from Company settings. Superseded in part by Q11 (owner 2026-11-20): signers are not recorded one by one | contract editor sections 2 and 4; C125; Q11 |
| Email template (subject, body, fields), cover page with letter, body text size 10/11/12 pt, header with logo slot and company cells | contract editor section 5; C125 |
| One PDF renderer for preview, download, send and print, with exact cents; a field resolver reads the lead or customer, the estimate and company settings (no SQL in the template) | contract editor item 5; C121; C122 |
| A change order has a terms template (kind "Change order terms"), default from the service type; the PM picks it, the rep may change it before sending; publishing a new version does not change COs already sent | S 11-19 10:22 PM |

### 7.3 Proposed schema

**`contract_template`** (new): `template_id` PK, `name` NOT NULL UNIQUE COLLATE NOCASE, `kind` CHECK IN ('Contract',
'Change order terms'), `is_active`, `row_version`.

**`contract_template_version`** (new): `version_id` PK, `template_id` FK, `version_no` INTEGER NOT NULL, UNIQUE
(`template_id`, `version_no`), `status` CHECK IN ('Draft', 'Published', 'Retired'), `body_pt` INTEGER NOT NULL
DEFAULT 11 CHECK IN (10, 11, 12), `header_show_logo` 0/1, `header_cells` TEXT (JSON of the company cells as
published), `cover_letter` TEXT NULL, `email_subject` TEXT, `email_body` TEXT, `version_note` TEXT, `published_at`,
`published_by`, `cancellation_period_days` INTEGER NULL CHECK (NULL or >= 0) (Q12 B; kind Contract only; the
template's "cancellation period" field and C105's cancellation-period line read it), `row_version`. Partial unique
index: one Draft per template.

**`contract_template_section`** (new; Q9 A): `section_id` PK, `version_id` FK, `section_key` TEXT NOT NULL (stable
across versions, used by overrides and Compare), UNIQUE (`version_id`, `section_key`), `sort_order`, `title`,
`body` TEXT (limited rich text with field keys; the allowed tags are checked by the service), `block_kind` CHECK IN
('Text', 'Line items and price', 'Payment schedule', 'Signatures'), `show_when` TEXT NULL (one of the condition keys
the resolver knows), `reps_may_turn_off` 0/1, `reps_may_edit` 0/1, `clause_id` NULL FK contract_clause.

**`contract_clause`** (new): `clause_id` PK, `title` NOT NULL, `body`, `is_active`, `row_version`.

**Integrity trigger (H4; Q23 A):** a Published or Retired version and its sections refuse UPDATE (except `status`
Published → Retired) and DELETE: a sent document's terms must stay reproducible. A Draft is editable.

**Per revision:** **`estimate_section_choice`** (new): `revision_id` FK, `section_key`, PRIMARY KEY both;
`is_shown` 0/1 (only when the section allows it), `override_body` TEXT NULL (CHECK only when `reps_may_edit`, by
the service), `override_reason_id` FK reason_option (kind 'Contract wording') ON DELETE RESTRICT,
`override_reason_label`, `override_note` (Q13 B, owner 12:50 AM: a reason and a short note are both required with an
override; with Other the note is at least 10 characters), `changed_by`, `changed_at`, `row_version`. **`estimate_signer`** (new): `signer_id` PK,
`revision_id` FK, `sort_order`, `name` NOT NULL, `email`, `title`, `lead_contact_id` NULL (area 15), `row_version`.
Signers are names that print on the contract and receive the email; no per-signer signature is recorded (Q11).

**Change order terms:** area 8's `change_order` gains `terms_template_version_id` FK contract_template_version
(kind Change order terms), set when priced, changeable until sent (area 8 amendment, open item 3).

**Wording approval control:** `approval_policy` for document type 'Contract' with the condition "wording changed"
(area 14), OFF by default. When on and any section has an override, Send becomes Submit for approval.

**Branding** (Q22 A): `company_branding` (new, one row): `logo_storage_key` TEXT NULL (through `storage.py`, H3; C125),
`logo_content_type`, `logo_size_bytes` (PNG, SVG or JPG up to 2 MB, checked by the service; not an `attachment` row,
so no record type is needed), `accent_color` TEXT (stored as data, not a Theme value: it prints on documents),
`footer_text`, `show_page_numbers`, `signer_name`, `signer_email`, `signer_phone`, `signer_block`, `row_version`.
Invoices, statements and pay app prints reuse it through the one letterhead (areas 4 and 5). The logo's `storage.py`
key is included in the 2.8 backups and restore, like attachments (open item 16).

### 7.4 Tests to write later

- Publishing a draft makes it read-only (trigger) and a new Draft can be started; a sent revision still renders
  with the version it was sent with after a newer version is published.
- An override on a section with `reps_may_edit` 0 is refused; an override without a reason, or with a reason but no
  note, is refused; with Other the note must be at least 10 characters.
- Turning off a section that does not allow it is refused.
- The renderer output for preview and send is byte-identical for the same inputs; cents are exact (no rounding to
  dollars, C2 of the contract editor brief).
- Branding logo over 2 MB or of another type is refused.

---

## 8. Send, decline, expire, revise

### 8.1 Decided

| Decision | Source |
|----------|--------|
| Sending records method and date; the rendered PDF is kept unchanged as an attachment with sent_at, sent_to, sent_by; revisions compare against it | A 11-14; A 11-15 10:35 PM item 3 |
| The email is shown and editable before sending (to every signer, cc the rep); Download PDF and Print also mark it sent | contract editor section 4; C102 |
| A pre-send checklist: customer legal name, billing and site address, signer name and email are required; Send stays disabled until complete | C102; contract editor section 2 |
| The send writes the lead's expected value (`leads.take_expected_value`) in the same transaction | area 15 section 1.4 |
| Expired: valid-until passed (reminder 3 days before); auto-lost calls `estimates.mark_expired`; signing an expired, unsent or unapproved estimate warns and needs a reason (blocking follows the stage-gate setting) | contract editor section 4; area 15 section 1.5; S 11-19 8:50 PM |
| Declined with a reason; the lead moves to Lost on confirm | contract editor section 4 |
| Revise makes Rev n+1; "What changed since Rev n" (price, schedule, sections, wording); re-approval only when the rule is crossed again | A 11-14; contract editor section 4 |

### 8.2 Proposed rules (`estimates.py`)

- `send(context, revision_id, method, email, row_version)`: `authorize(context, 'estimate.send', ...)`; checks the
  checklist, the 100% and SOV checks, a published template version, at least one signer with an email (for
  Email); renders once, stores the PDF through `storage.py` as an `attachment` (area 18) and sets
  `sent_attachment_id`; writes the frozen totals; status Sent; the previous sent revision of the same estimate, if
  any, becomes Superseded; calls `leads.take_expected_value(context, lead_id, revision_id, contract_total_cents)`.
  Email goes through area 20's company mailbox; Download and Print write the same record. Margin under the floor
  with the control off returns a warning with the success (rule 0).
- `decline(context, revision_id, reason_id, note, row_version)`: Sent → Declined, reason kind 'Lost lead' (the lead's
  Lost reason); the lead move to Lost is area 15's `lead_stages` call in the same transaction when the user confirms
  (the page asks; the service takes a flag).
- `mark_expired(context, revision_id)` (called by area 15's auto-lost and by `run_expiry`) and `run_expiry(context)`
  (origin System; Sent revisions whose `valid_until` < `context.today` become Expired; idempotent; Q24 A). Expired is not
  final: signing an Expired revision is allowed with a "Continue anyway" reason (S 11-19 8:50 PM), and blocking
  follows `stage_requirements_block`. The 3-day reminder is a notification (area 21).
- `revise(context, estimate_id)`: copies the newest revision's children into Rev n+1 (status With rep, holder the
  rep); the compare is derived from the two revisions (no stored diff).

### 8.3 Tests to write later

- Send with a missing required customer field is refused with the field's name; nothing is written.
- Send stores one attachment, sets the frozen totals and calls `take_expected_value` once (lead updated in the same
  transaction; a failure rolls both back).
- Sending Rev 2 marks Rev 1 Superseded; Rev 1's attachment and figures are unchanged.
- `run_expiry` twice in a day changes nothing the second time; it never touches a Signed or Declined revision.
- Decline needs a reason; with "move the lead to Lost" the lead and the revision change in one transaction.

---

## 9. Signing

### 9.1 Current state

No signing service. The CRM decision (`design_decisions.md` "CRM and project lifecycle") says signing runs one
service function: confirm the customer, assign the customer code, assign the job number, create the contract and the
original budget. D9: `sign_contract()` locks the revision and creates budget and SOV.

### 9.2 Decided

| Decision | Source |
|----------|--------|
| Signing requires the uploaded signed PDF, signer and date; then creates customer (new or existing), job number, budget locked from the cost lines, SOV and milestones from the payment schedule, default PM = estimator | A 11-14; C102; contract editor C6 |
| Signing also creates a draft deposit invoice (not posted) from the payment schedule | A 11-15 10:35 PM item 7; contract editor section 4 |
| A contract's new customer uses the customer service and validation (area 5) | S 11-18 4:36 PM (row 5) |
| Customer codes are assigned once: in the Create New Customer wizard or at signing, by the same service | design_decisions "Customer codes" |
| Signing moves the lead to Contract signed (via Signed), sets Won and `lead.project_id`; `contract.sales_rep_user_id` keeps the rep at signing; `project.sales_rep_user_id` is copied from the lead | area 15 section 9; S 11-19 11:20 PM |
| The summary by cost code becomes the job budget at signing and freezes the estimate | S 11-19 11:20 PM |
| One "Mark signed" action plus the uploaded signed document; no digital signature field, no per-signer record, no partial signing; the job is created at Mark signed; the 8:50 PM checks stay (warning plus reason; blocks only with the stage gate on); the summary by cost code becomes the job budget; the rep is copied to `project.sales_rep_user_id` and `contract.sales_rep_user_id` (replaces the contract editor's "1 of 2 signed") | owner 2026-11-20, Q11 |
| Automation never posts (rule 0) | CLAUDE.md section 0 |

### 9.3 Proposed rules (`contracts.py`)

- `mark_signed(context, revision_id, signed_attachment_id, customer_input, job_input, continue_reason, row_version)`
  (Q11): `authorize(context, 'contract.sign', ...)` first. Allowed on a Sent revision; an Expired, unsent or
  unapproved one returns the S 11-19 8:50 PM warning and needs a "Continue anyway" reason (`reason_option`), and is
  refused only when `stage_requirements_block` is on (area 8). Then, in one write transaction:
  1. The signed document attachment exists on this estimate (required, Q10 A).
  2. Customer: `estimate.customer_contact_id` set → that customer; NULL → area 5's create-customer service with the
     revision's customer block and the lead's contacts (code assigned there).
  3. Job: area 7's job service (number, service type, PM = `costs_by_user_id` unless changed,
     `project.sales_rep_user_id` from the estimate's rep, `source_revision_id`, first Delivery stage, default
     schedule template, area 8).
  4. Budget: one row per cost code of the summary by cost code, through area 7's budget service.
  5. `contract` row (section 10) with `contract_number` from the CT- series (Q21 B), `sales_rep_user_id` (the same
     rep, kept as the rep at signing), copies of the schedule, `contract_line` + cost codes, `contract_milestone`,
     `contract_rate_line`.
  6. Draft deposit invoice through area 5's invoice service (not posted; credit side by role `customer_deposits`,
     never by account number).
  7. Revision status Signed (one history row); other open or sent revisions and the lead's other options become
     Superseded (Q18 A); `estimate.customer_contact_id` set.
  8. `leads.mark_signed(context, lead_id, project_id)` (area 15: stage Contract signed, Won, `project_id`).
  Any refusal rolls everything back. Nothing posts. Signer names print on the contract only; nothing is recorded per
  signer.

### 9.4 Tests to write later

- Mark signed without the signed document is refused.
- Mark signed on an Expired, unsent or unapproved revision without a Continue anyway reason is refused; with the
  reason it succeeds when the stage gate is off and is refused when it is on.
- The job's and the contract's `sales_rep_user_id` both equal the estimate's rep after Mark signed.
- Signing a prospect creates exactly one customer with a code and one job; a linked customer gets no new contact.
- Budget rows equal the summary by cost code; the contract's original amount equals the revision's frozen total.
- The deposit invoice is a draft with no `journal_entry`; its amount follows the schedule (NTE base for T&M).
- A failure in any step (for example the customer validation) leaves no job, contract, budget or lead change.
- Signing one option marks the lead's other options Superseded.

---

## 10. The contract record and change orders

### 10.1 Current state

`contract` (`:878`) exists with `project_id`, `contact_id`, `contract_number` UNIQUE, `contract_type`, dates,
`original_amount_cents`, `retainage_pct`, `payment_terms`, `status` CHECK IN ('Draft', 'Executed', 'Complete',
'Terminated'), `document_ref`, `notes`. Area 8's `change_order.contract_id` (`:794`) and
`progress_billing_application.contract_id` (`:948`) point at it. Area 8 left `contract.status` to area 6.

### 10.2 Proposed (Q1 A)

**`contract`** (replaced): `contract_id` PK; `project_id` NOT NULL UNIQUE FK project; `customer_contact_id` NOT NULL
FK contact; `revision_id` NOT NULL UNIQUE FK estimate_revision; `contract_number` NOT NULL UNIQUE (Q21 B: its own
CT- series, assigned at Mark signed); `schedule_type` (Q20 A, replaces `contract_type`); `signed_on` (replaces `contract_date`),
`start_date`, `completion_date` (area 8 reads it as the schedule's contract date); `original_amount_cents` NOT NULL;
`deposit_pct`/`deposit_cents`, `retainage_pct`, `not_to_exceed_cents`; `payment_terms`; `sales_rep_user_id`
INTEGER NULL (written once at signing, area 15 hand-off); `template_version_id` FK; `signed_attachment_id` NOT NULL
FK attachment; `recorded_by`, `recorded_at`; `status` CHECK IN ('Signed', 'Cancelled', 'Completed'); cancellation
columns (section 11); `memo` (replaces `notes`, area 18 memo rule); `row_version`. `document_ref` is dropped (the
attachment replaces it).

- The revised contract amount is derived: the sum of `contract_line.scheduled_value_cents` (original lines plus the
  lines approved change orders add). No stored revised column.
- Area 8's change order approval calls `contracts.add_change_order_lines(context, contract_id, change_order_id,
  lines)` in its transaction: new `contract_line` rows with `change_order_id` set and their cost codes (area 8
  section 5.3 item 1). CO pricing reads the same pricing template rules (section 3.3).
- `Completed` is set by area 8's job close (outcome Completed); `Cancelled` by section 11.
- The Contracts list is a read over sent revisions and contracts (no separate list table).

### 10.3 Tests to write later

- A second contract for the same job or the same revision is refused (UNIQUE).
- After a CO approval the derived revised amount equals the original plus the CO's revenue change.
- Changing `sales_rep_user_id` on the contract is refused after signing (service; the job's rep is the editable one).

---

## 11. Contract cancellation (C105)

### 11.1 Decided

C105 (owner item 12, answers 4-6): contract-cancel opened from Contracts, the job's More menu and a cancellation
case; Reason (required), Date received, Case link; a cancellation-period line (information only; read from the
contract's template version, Q12 B, not the job type);
money on the job with guided actions that each post on their own screen; the screen never posts; approval
"Contract cancellations" OFF by default (when on, Submit for approval and the job stays open until approved);
result: job Cancelled, estimate Cancelled (not Lost), customer and code kept, case gets a note. Area 15's
Cancellation case type offers "Cancel the contract". Area 8: job Closed with outcome Cancelled and a reason of kind
'Job cancel'.

### 11.2 Proposed

`contract` columns: `cancelled_on` TEXT NULL CHECK date, `cancel_received_on` TEXT NULL CHECK date,
`cancel_reason_id` FK reason_option (kind 'Job cancel') ON DELETE RESTRICT, `cancel_reason_label`,
`cancel_case_id` INTEGER NULL FK service_case (area 15); CHECK all set together with status Cancelled (the case
optional). `contracts.cancel(context, contract_id, reason_id, received_on, case_id, row_version)`:
`authorize(context, 'contract.cancel', ...)`; with the 'Contract' cancellation policy active (area 14) it creates
the approval request and stops; otherwise in one transaction: contract Cancelled, revision Cancelled, area 8's
`job_close` with outcome Cancelled and the same reason, a case comment (area 15). Never posts, never voids.

### 11.3 Tests to write later

- Cancel without a reason is refused; with the approval policy on, nothing changes until approved.
- The job closes as Cancelled with the reason label copied; the customer and code are unchanged; no journal entry.

---

## 12. Permissions, Records sources, custom fields, attachments

- **Codes** (Q19 A; area 18 amendment, open item 6): keep `estimate.create` (start, hold and edit the revision you
  hold), `estimate.approve` (sensitive; approve when the control is on), `contract.approve` (sensitive; wording and
  cancellation approvals when on). Add `estimate.view` (the read code STOP C found missing), `estimate.send` (send,
  decline, revise), `contract.sign` (sensitive: creates customer, job, budget), `contract.cancel` (sensitive),
  `sales.templates.manage` (pricing templates, cost templates, contract templates and clauses, rate cards, branding).
  Five new codes, so 102 seeded codes become 107 (102 + 5; area 18 amendment in its section 2.4). `crm.settings`
  (area 15) stays for CRM lists.
- **Records sources** (area 17): `src_leads_estimates` reads `estimate`, `estimate_revision` (sent figures) and the
  history; the money fields follow `money.view`.
- **Custom fields** (area 16 / STOP C): values attach to `estimate` (shared by its revisions, Q25 A); the refusal in
  `custom_fields.py` is lifted when `estimates.py` ships.
- **Attachments** (area 18): the sent PDF and the signed PDF are `attachment` rows with `record_type` 'Estimate'
  (record id the estimate) and linked from the revision and contract by FK; area 18's list gains 'Contract' for files
  added on the contract later (area 18 amendment, section 3.2). The logo is not an attachment (section 7.3).

---

## 13. Row version (rule g4) and audit in this area

| Table | Editable? | `row_version` |
|-------|-----------|---------------|
| `estimate`, `estimate_revision` (working), `estimate_cost_line`, `estimate_milestone`, `estimate_sov_line`, `estimate_rate_line`, `estimate_section_choice`, `estimate_signer` | yes (until sent) | yes |
| `pricing_template`, `pricing_template_line`, `cost_template`, `cost_template_line`, `rate_card`, `rate_card_line`, `contract_template`, `contract_template_version` (Draft), `contract_clause`, `company_branding`, `sales_authority_limit` | yes | yes |
| `contract`, `contract_milestone` | a few columns (cancellation, completion, invoice link, memo) | yes |
| `estimate_sov_line_cost_code`, `contract_line_cost_code` | insert and delete only | no (a delete names both ids) |
| `contract_line` | insert by signing and CO approval only | no |
| `estimate_revision_history`, `contract_rate_line` | insert-only | no |
| `company_settings` (new columns) | yes | area 21 adds it to the row |

Every new table gets audit triggers (area 18). Integrity triggers in this area guard only what must never change:
sent revisions and their children (section 1.3), published template versions (section 7.3), the history and the
frozen contract rates (insert-only). No trigger enforces a workflow rule (H4). Reasons required (area 18's table,
amendment in its section 1.2): send back (kind Send back), decline (Lost lead), cancel a contract (Job cancel), a
T&M rate change (Rate change, Q13 B), a wording change (Contract wording, Q13 B), Mark signed on an expired, unsent or
unapproved revision (Continue anyway), abandoning an unsent estimate (a note of at least 10 characters in the history
row), and changing an area 6 control or setting.

---

## 14. Conflicts with decisions (resolved by the owner's answers, 2026-11-20)

- **F1 A contract record or not.** A 11-14: "No separate contract record; Contracts becomes a view of sent and
  signed estimates." But the baseline has `contract` (`:878`) with area 8's `change_order.contract_id` and the pay
  app's `contract_id`; C121 asks `contract.template_id`; S 11-19 11:20 PM asks `contract.sales_rep_user_id`. **Resolved by Q1 A.**
- **F2 Approval default.** A 11-14 and C76: "Only under the margin floor or over the rep's discount authority
  (DEFAULT, owner's choice)". S 11-19 11:20 PM, RI1, D9 and C122's leftovers: OFF by default. The later decisions
  agree with section 0. **Resolved by Q2 A.**
- **F3 Self-approval.** C22 makes "the estimator cannot approve their own estimate" an integrity rule; A 11-14 and C76
  say the pricer can't approve their own. CLAUDE.md section 0 lists separation of duties as a control, OFF. **Resolved by Q3 A.**
- **F4 State names.** C22 (Requested · Estimating · Sales review · Margin approval · Ready to send · Sent · Signed),
  C76 (Requested · Estimating · With sales · Approval · Ready to send · Sent · Signed), C125 (Draft, Requested, In
  approval, Ready to send, Sent, Declined, Signed) and S 11-19 11:20 PM (With rep, With PM, In approval, Sent back,
  Approved, Ready to send, Sent). The latest is used; Approved and Ready to send overlap (both are "with the rep,
  priced"). **Resolved by Q6 A.**
- **F5 Price override and rep adjustment.** C125: `contract_total_cents` override with "Price override: ($1,896.17)"
  and Reset; S 11-19 8:58 PM: the rep adds markup or discount within authority. Two ways to change one price. **Resolved by Q7 A.**
- **F6 Where scope and wording live.** C128 (11-16 2:13 PM): scope, inclusions and exclusions only in the template,
  dropped from the estimate; A 11-14: the revision carries scope, inclusions and exclusions; the contract editor
  (11-15, owner decision 4): a Scope step with "Use the service type's default" and per-deal wording overrides. **Resolved by Q8 A.**
- **F7 Template body shape.** C121 and C122: `contract_template_section` rows; C124: "the template body stored as one
  rich-text document" where H2 blocks carry show_when. Per-section overrides, locks and Compare need a stable section
  identity. **Resolved by Q9 A.**
- **F8 Signed copy required.** A 11-14, C102 and the contract editor (C6): attaching the signed PDF is required. C9
  lists "Require the signed contract file before signing" as a PROPOSED control OFF (area 15 F10 passed this here).
  **Resolved by Q10 A.**
- **F9 Cancellation period.** C105: a "Cancellation period (days)" field on each job type (service type); C121: the
  template settings hold "cancellation period" and the template offers it as a contract field. **Resolved by Q12 B.**
- **F10 Estimate requests and routing.** C120 (11-15): a setting "Estimate requests go to an estimator" (OFF; ON
  makes the estimator required) and C125's `estimate_request` table; S 11-19 8:58 PM: the wizard's third step lets
  the rep send to a PM or enter costs, and "the rep may skip the PM". The C120 re-test is still open in
  to_ux_research. **Resolved by Q17 A.**
- **F11 Contract type and status lists.** The baseline `contract_type` ('Fixed price', 'Cost-plus', 'Time and
  materials', 'Unit price') differs from the schedule types of A 11-16 and S 11-19 8:42 PM ('Progress billing',
  'Milestones', 'Fixed price', 'Time and materials'); `contract.status` ('Draft', 'Executed', 'Complete',
  'Terminated') has no Cancelled, while C105 cancels contracts. **Resolved by Q20 A.**
- **F12 T&M bill rates.** D8 (v1.1): bill rates per role or employee on `time_entry.bill_rate_cents`, material markup.
  S 11-19 8:35 PM and the 8:42 PM answer: rates frozen onto the contract from a rate card or the estimate; time from
  payroll import. Two places for a bill rate. **Resolved by Q26 A.**
- **F13 Options and the primary revision.** D9: "only the primary revision" can be signed; C125: a lead lists every
  version and option (v1, v2, Option A), each with its own status. Which option is signable and what happens to the
  others is not decided. **Resolved by Q18 A.**
- **F14 Customer at contract sent.** C24 (11-13) proposed creating the customer when the contract is marked sent (a
  PROPOSED control); C76 merged contracts into the estimate, and the customer-code decision and S 11-18 4:36 PM keep
  creation at signing. Not built (PROPOSED); noted only.
- **F15 Deposit account number.** A 11-16 3:22 PM names "2350 Customer deposits"; the repo chart has 2320 (S 11-19
  12:52 PM). Code finds it by role `customer_deposits`, so no number is written anywhere. Noted only.
- **F16 Markup on every line.** C76's "Markup on every line + Apply" predates the 9:44 PM fixed/editable rule. This
  draft skips fixed lines and reports them (section 3.3); the owner may prefer Apply to be disabled when any line is
  fixed. Noted; no question.

---

## 15. Questions for the owner: answers recorded (2026-11-20)

Owner 2026-11-20: every question A except Q11 (the owner's wording below), Q12 B, Q13 B and Q21 B. Each answer is
folded into the sections above.

**Q1. The contract record.** (F1)
- A. Keep `contract`, written once at signing as the signed agreement (snapshot of the schedule, SOV, milestones,
  rates, the rep at signing); CO lines and pay apps hang off it; the Contracts list reads sent revisions and
  contracts.
- B. No contract table (11-14 literally): the signed revision is the contract; `change_order` and pay apps point at
  the revision.
- C. Keep `contract`, created at first send and updated until signing.
**Answer: A.**

**Q2. Estimate approval default.** (F2)
- A. OFF (11:20 PM, RI1, D9): no approval unless a company turns on the Estimate policy.
- B. ON by default "only under the margin floor or over discount authority" (C76).
**Answer: A.**

**Q3. Approving your own estimate.** (F3)
- A. It follows the separation-of-duties control (OFF by default: allowed and marked Self-approved; ON: refused).
- B. Always refused, an integrity rule (C22).
**Answer: A.**

**Q4. Must an estimate have a lead?**
- A. Yes, `estimate.lead_id` NOT NULL: every estimate starts from a lead (a repeat customer gets a Repeat customer
  lead, area 15); Solo too.
- B. No: an office or Solo estimate may exist without a lead (the lead's calls are skipped).
**Answer: A** (owner's wording). `estimate.lead_id` stays NOT NULL. The wizard's first step picks an existing lead or
creates one in the same transaction, so a repeat customer's lead is made inside the wizard and no separate lead form
comes first. A lead made in the wizard gets the service type chosen at wizard step 2 (Job), in the same transaction
(S 11-19 8:42 PM: service type required on every lead). Sections 1.2, 1.3 and 1.5; area 15 amendment (section 1.3).

**Q5. Where status and holder live.**
- A. On the revision (each revision has its own hand-off and history; the estimate shows the newest).
- B. On the estimate (one hand-off across revisions).
**Answer: A.**

**Q6. Approved and Ready to send.** (F4)
- A. Keep both: Approved = priced and approved (or PM one-click when the control is off), back with the rep; Ready to
  send = the rep has checked price, payment schedule and proposal and the send checklist passes.
- B. Merge them into "Ready to send" (approval lands there directly).
**Answer: A.**

**Q7. Changing the customer price.** (F5)
- A. The rep's adjustment only: extra markup % or a discount (% or amount); typing a lump-sum contract total is
  stored as a discount amount and shows "Price override: ($...)" with Reset; authority reads the implied %.
- B. Keep C125's separate contract-total override beside the rep's markup and discount.
- C. Only the lump-sum override (no markup or discount fields).
**Answer: A.**

**Q8. Scope, inclusions and exclusions.** (F6)
- A. They are template sections; the deal changes them with the per-section wording override (marked, reason,
  logged); no separate estimate columns (C128 plus the contract editor).
- B. Columns on the revision prefilled from the service type, inserted into the template by field keys.
**Answer: A.**

**Q9. Template body.** (F7)
- A. Section rows with a stable `section_key` (needed for overrides, locks, Compare and conditions); the editor shows
  them as one flowing document.
- B. One rich-text document per version (C124), with section identity inside the document.
**Answer: A.**

**Q10. The signed copy.** (F8)
- A. Always required to sign, not a control (owner decisions 11-14 and 11-15).
- B. A control "Require the signed contract file before signing", OFF by default (C9).
**Answer: A.**

**Q11. Several signers.**
- A. Record signers one at a time ("1 of 2 signed"); the job is created when the last one is recorded.
- B. One Record signature for all signers at once; partial signing is not stored.
**Answer (owner's wording, replaces A and B):** there is no digital signature field. Signing is one "Mark signed"
action plus the uploaded signed document. Signer names may still print on the contract, but signers are not recorded
one by one, there is no partial signing, and the job is created at Mark signed. Mark signed keeps the S 11-19 8:50 PM
checks (an expired, unsent or unapproved estimate: warning plus reason; blocks only when the stage gate is on). At
Mark signed the summary by cost code becomes the job budget and the rep is copied to `project.sales_rep_user_id` and
`contract.sales_rep_user_id`. Sections 7.3, 9.2-9.4.

**Q12. Cancellation period.** (F9)
- A. On the service type (`cancellation_period_days`, C105); the template's "cancellation period" field reads it.
- B. On the template version (C121); the service type does not hold it.
**Answer: B.** The cancellation period is on the contract template version (`cancellation_period_days`); the service
type does not hold it. Sections 5.3, 7.3, 11.

**Q13. Reasons for rate changes and wording changes.**
- A. A required one-line text (at least 10 characters), stored with the change and in the audit row.
- B. Pick from new Reasons kinds 'Rate change' and 'Contract wording' (area 15 amendment), with Other + text.
**Answer: B**, amended by the owner at 12:50 AM: the reason is picked from the `reason_option` kinds 'Rate change' and
'Contract wording' (stored as `reason_id` + `reason_label`), and a short note is required on every rate change and
every contract-wording change, not only when Other is picked; with Other the note is at least 10 characters. Stored
with the change and in the audit row. Sections 6.3, 7.3; area 15 amendment (section 7.3).

**Q14. Rep authority limits.**
- A. `sales_authority_limit` policy records defined here (per role or user, OFF), read by area 14's routing when the
  Estimate policy is on.
- B. Left wholly to area 14 (area 6 stores only the adjustment on the revision).
**Answer: A.**

**Q15. Margin floor and target.**
- A. Company settings 20% and 22% by default, warnings and colours only, a blank value turns them off.
- B. Empty by default (no colours until a company sets them).
**Answer: A.**

**Q16. SOV lines and cost codes.**
- A. A link table: a merged SOV line keeps several cost codes; each cost code sits on one SOV line.
- B. One cost code per SOV line (today's `contract_line.cost_code_id`); merging is not allowed.
**Answer: A.**

**Q17. Estimate requests.** (F10)
- A. No setting and no `estimate_request` table: the wizard's "Who enters costs" step (send to a PM with a due date,
  or enter costs myself) is the request; holder and history record it.
- B. Keep C120's control "Estimate requests go to an estimator" (OFF); ON hides "enter costs myself" for reps.
**Answer: A.**

**Q18. Options on one lead.** (F13)
- A. Each option is its own `estimate` with `option_label`; any sent option can be signed; signing one marks the
  lead's other options Superseded.
- B. Options are revisions of one estimate; only the newest sent revision can be signed (D9 "primary").
**Answer: A.**

**Q19. Permission codes.**
- A. Add `estimate.view`, `estimate.send`, `contract.sign` (sensitive), `contract.cancel` (sensitive),
  `sales.templates.manage`; keep the three existing codes (102 to 107).
- B. Add only `estimate.view` and `contract.sign`; sending is `estimate.create`, cancelling is `contract.approve`,
  templates are `crm.settings` (102 to 104).
**Answer: A.**

**Q20. Contract type and status.** (F11)
- A. Replace `contract_type` with `schedule_type` (the four schedule types) and `status` with ('Signed', 'Cancelled',
  'Completed').
- B. Keep `contract_type` as a separate legal kind beside `schedule_type`; status adds 'Cancelled' to today's list.
**Answer: A.**

**Q21. Contract number.**
- A. The estimate number (one number per deal; the contract row repeats it).
- B. Its own series (CT-), assigned at signing.
**Answer: B.** Contracts have their own series, CT-, from `sequences.py`, assigned at Mark signed. Sections 1.4, 10.2.

**Q22. Branding (logo, signer, footer).**
- A. `company_branding` (one row) defined here, since contracts are the first document to use it; invoices,
  statements and pay apps reuse it.
- B. Left to area 21 (whole-app); area 6 reads it.
**Answer: A.**

**Q23. Published template versions.**
- A. Read-only by an integrity trigger (a sent contract's terms stay reproducible).
- B. Read-only by the service only.
**Answer: A.**

**Q24. Expired.**
- A. A stored status set by the daily `run_expiry` and by `mark_expired`; signing an Expired revision needs a
  Continue anyway reason.
- B. Derived from `valid_until` only (no stored status); area 15's `mark_expired` call is removed.
**Answer: A.**

**Q25. Custom fields on estimates.**
- A. On `estimate` (shared by all revisions).
- B. On each revision (frozen at send with the rest).
**Answer: A.**

**Q26. T&M bill rates.** (F12)
- A. The contract's frozen rate lines are the only bill rates; `time_entry.bill_rate_cents` (D8) is not built, and
  area 19/5 bill payroll hours at those rates.
- B. Keep D8's per-employee bill rate on time entries as an override of the contract rate.
**Answer: A.**

---

## 16. Open items (not decisions)

1. **Area 7:** `cost_type` (company list, five shipped) and `cost_code.cost_type_id` NOT NULL replacing
   `cost_type_label` (`:38`); `project.sales_rep_user_id`; `project.source_estimate_id` becomes `source_revision_id`
   (FK estimate_revision); `project_budget.estimate_line_id` (`:290`) is dropped or replaced by a revision link
   (budget rows come from the summary by cost code, not per line); whether estimate lines must use leaf codes.
2. **Area 5:** the create-customer service called by signing (with the revision's customer block and the lead's
   contacts); the draft deposit invoice (credit by role `customer_deposits`); T&M monthly drafts from the frozen
   rates and the near-NTE warning; `contract_milestone.invoice_id`; the T&M revenue account (4040 has no system role
   in `templates/coa/construction.csv`; area 5 decides whether it needs one).
3. **Area 8 (amendment lines written 2026-11-20, sections 1.3, 4.3 and 5.3):** `service_type` gains
   `default_schedule_type`, `default_deposit_pct`, `default_deposit_cents`, `default_retainage_pct`,
   `pricing_template_id`, `contract_template_id`, `co_terms_template_id` and the child table `service_type_milestone`
   (no cancellation period, Q12 B); `service_type.rate_card_id`
   becomes an FK to `rate_card`; `job_schedule_task.payment_milestone_id` becomes an FK to `contract_milestone`;
   `change_order` gains `terms_template_version_id`; CO pricing lines follow the pricing template (markup per cost
   type, fixed or editable, margin %), which area 8's `change_order_line` must carry; the CO approval calls
   `contracts.add_change_order_lines`.
4. **Area 15 (amendment lines written 2026-11-20, sections 1.3 and 7.3):** the wizard creates a lead in the
   estimate's transaction with the step 2 service type (Q4); `reason_option.kind` gains 'Rate change' and 'Contract
   wording' (Q13 B). Unchanged: `lead.expected_value_revision_id` becomes an FK to `estimate_revision` (foreseen
   there); `leads.take_expected_value` (send), `leads.mark_signed` (Mark signed) and the Lost move on decline.
5. **Area 9:** `material_code` (C129); until it exists, `estimate_cost_line.material_code_id` is a plain integer and
   the Material kind is not offered.
6. **Area 18 (amendment lines written 2026-11-20, sections 1.2, 2.4 and 3.2):** the five codes of Q19 A (102 to
   107) with caps, level defaults and templates; the reasons rows of section 13; `attachment.record_type` gains
   'Contract'.
7. **Area 14:** the Estimate policy (and its condition "under the margin floor or over authority"), the Contract
   policy for wording changes and for cancellations, reading `sales_authority_limit`; area 14's document type list
   keeps 'Estimate' and 'Contract'.
8. **Area 17:** `src_leads_estimates` field ids over `estimate` and `estimate_revision`; the sales rep on the
   contract for `src_rep_contract_payments`.
9. **Area 16 / STOP C:** custom fields on Estimate (Q25); the refusal in `custom_fields.py` and its test are replaced
   when `estimates.py` ships.
10. **Area 20:** sending the proposal email (company mailbox), the email log id on the revision, Cc the rep.
11. **Area 21:** notifications (PM assigned with due date, Ask the rep, send back, approval, the 3-day expiry
    reminder); `row_version` on the new `company_settings` columns.
12. **Area 4:** pay apps read the contract's SOV and its cost codes, the retainage, and the deposit-remaining balance
    per job (A 11-16 3:22 PM item 2).
13. **Area 19:** payroll import hours (employee, job, cost code) as the T&M time source.
14. **The PDF renderer:** one service (`documents.py` or similar) for preview, download, send and print; the library
    choice and H1 (no UI imports in services) are for the build step, not the schema.
15. **Batch D mock data:** the data-layer calls in to_ux_research 11:20 PM stay valid as names; `data.signEstimate`
    becomes `markSigned(id, signedFileId, continueReason, rowVersion)` (Q11; no per-signer call), and
    `setRepAdjustment` carries a discount amount (Q7 A).
16. **2.8 backups and restore:** the company logo's `storage.py` key (`company_branding.logo_storage_key`) is included
    in the company backup and restore, like attachments (area 18 Q14: a company backup without them is not complete),
    and recorded in `backup_run`.
