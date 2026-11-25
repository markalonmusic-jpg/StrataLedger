# Step 2.9 schema replan, area 3: bills, vendor credits, payment terms, subcontract bills and vendors

Status: **Approved as drafted by the owner 2026-11-23 11:55 PM (planning chat), as of commit c0780e2.** Drafted
2026-11-23; owner answers to Q1–Q6 (2026-11-23 7:32–7:48 PM) folded the same day. Docs only: nothing here changes code, a baseline, a migration or a
test. Every table, column, code and check below is built only in the 2.9 baseline pass, after the whole replan is
approved. Items marked PROPOSED are not decided. The pay run itself is Area 2 (`area_2_pay_run.md`); this area owns
what a bill, a vendor credit, a term and a vendor are, and what a pay run may read from them.

Sources read (searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`: row 3 and its sources; "Inbox inputs" for Area 3 (APBILL-01 to
  APBILL-05, VENDOR-01 to VENDOR-04, VCR-01 to VCR-04, TERM-01 to TERM-04) and "Area 8 and 3" (holds after reversals,
  pay-when-paid limit, sub retainage); the Area 4 SUBPAY-01 to SUBPAY-04 inputs where they touch bills.
- `Strata_Teams\docs\owner_decisions_2026-11-22.md`: items 12–17; OD-08, OD-16, OD-17, OD-21, OD-26, OD-36 to
  OD-40, OD-50, OD-66, OD-67.
- `Strata_Teams\inbox\to_planning.md`: 2026-11-22 "from design chat: CRM and Field gap list" (items 6–8) and the
  2026-11-22 evening "two new owner features + rules" (OD-66, OD-67, OD-31).
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 43, 53, 71, 144, 148, 169 (as inputs; the decisions win).
- `docs/po_ap_matching_design.md` §§3, 4, 6, 10; `docs/next_step.md` "Owner decisions 2026-11-22 for areas not yet
  drafted" (Area 3 list, now pointing here) and the Area 3/5 handoff from Area 10 (F8).
- Approved areas this one must fit: Area 4 (draft, ready for approval) §§2, 4, 5; Area 5 §§2, 8.2, 9; Area 10 §§1,
  2, 11; Area 13 §1.4; Area 18 §§2, 3, 8.
- `migrations/001_company.sql`: `invoice` :590, `invoice_line` :652, `payment` :670, `payment_allocation` :316,
  `contact` :810, `vendor_number` :858, permission seeds :1203–1211, `document_approval_setting` :1269,
  `voucher_sequence` :1282, `payment_term` :3884, `pay_run` :3992, `pay_run_line` :4005, `company_settings`
  roles :765–787. Services: `contacts.py` (codes), `payments.py` (allocation), `ledger.py:516` and `:1030` (document
  entry and void). There is no bill service today.

**Checked against: shared_decisions 2026-11-14 12:05 PM (payments model), 2:30 PM (approvals: duplicates), 2:40 PM
(bills), 3:05 PM (editing posted documents), 3:10 PM (vendors layout), 11:15 PM (Voucher #); 2026-11-17 10:44 AM
(holds, billing cycles, lien waivers), 12:10 PM (who may hold), 4:16 PM (locked pay apps), 5:13 PM (re-hold,
pay-when-paid limit, sub retainage); 2026-11-18 10:50 AM (a locked pay app locks its bills), 10:03 PM (one way to pay
bills), 10:24 PM (bill approval), 11:55 PM (prepaid bills); 2026-11-19 12:52 PM (account numbers follow the repo
chart); 2026-11-20 5:15 PM (single active claim and retry). Latest entry read: 2026-11-22 2:25 AM. Owner answers
in `owner_decisions_2026-11-22.md`: Area 3 Q1–Q6, 2026-11-23 7:32 PM, 7:40 PM, 7:44 PM and 7:48 PM.**

Decisions are cited as "Decided <date> (owner)" with their source. Lead defaults (prototype details) are marked
"lead default, owner may revise"; they are not questions.

---

## 0. Summary

| # | Item | Proposal in one line | Baseline |
|---|------|----------------------|----------|
| 1 | Vendors and the shared vendor source | `contact` gains `vendor_kind`, vendor defaults (terms, account, method, job required, 1099) and `requires_lien_waivers`; one vendor list read by Vendors and New bill (OD-16); inactive vendors kept in history, not offered on new bills | company |
| 2 | Vendor documents and the compliance hold | `vendor_document` rows (type, number, issued, expires, status, file) and `vendor_kind_document` (what each kind needs); a missing or expired required document **warns** on the vendor, the bill and the pay run; only with the compliance-hold control ON (OFF by default) does it hold payment (Q3, decided 2026-11-23) | company |
| 3 | Bills | Purchase side of Area 5's stable document and version model; Voucher # at first save; job per line (Q1); duplicate warns with a reason; one approval record; re-approval only on a vendor or total change with approval ON (Q4); holds with history; same-number edit, same-gross reclass (item 13) | company |
| 4 | Subcontract bills, retainage, draws and waivers | bill line links to the subcontract line; over-limit warns with a reason, control refuses (item 12); retainage withheld to Retainage payable; draw and waiver rows; release bill starts held; locked pay app locks its bills | company |
| 5 | Payment terms and early-payment discounts | `payment_term` validated and frozen on each bill version; discount through the deadline inclusive on the bill total; posts to the bill's job cost line, or `purchase_discounts` with no job (item 16, OD-66) | company |
| 6 | Vendor credits and refund requests | typed purchase credit with its own `VC-###` series at posting; refund request holds its outstanding amount against that credit; a receipt lowers the open balance (OD-67); write-off with a reason (item 15) | company |
| 7 | Locks, permissions, controls, row version and audit | Area 13's "Bills and vendor credits" area; four PROPOSED codes; six controls, all OFF (two already in Area 18 §8.3, four pending its amendment); every typed reason at least 10 characters (OD-31; a listed reason needs none, Area 18 §8.7) | company and master |

---

## 1. Vendors and the shared vendor source

### 1.1 Current state

- `contact` (`:810`) holds customers and vendors: `is_vendor`, `vendor_code` (assigned only by `contacts.py` from
  `vendor_number`, immutable by `trg_contact_code_immutable`), `entity_type` (legal form), `tax_id`,
  `bank_details_on_file`, `bank_payee_id` (RP1: no bank numbers), `payment_term_id`, `memo`, `is_active`.
- `contacts.py` creates vendors and assigns codes; it does not expose `payment_term_id` (VENDOR-02) and has no
  default account, payment method, job requirement, 1099 or kind.
- There is no vendor list service: the mockup's New bill had a hard-coded option list (OD-16).

### 1.2 Decided

| Decision | Source |
|----------|--------|
| The Vendors list and the New bill vendor dropdown read **one shared vendor source**, no hard-coded list; every vendor on the Vendors list, including the nine codes, preselects from "Enter bill"; the rest of the bill stays blank. A database binding point | OD-16 (G1), owner 2026-11-22 |
| 14 sample vendors: the 12 visible ones plus Cascade Ready-Mix VCA0014 (Active). Granite Ridge Scaffold stays hidden and is not offered on New bill | OD-36 A |
| An unknown `?vendor=` code opens a blank bill with no vendor | OD-50 1A + 2A |
| Vendor kind is one value stored as `contact.vendor_kind` (not `entity_type`, which is legal form), with the mockup values Supplier, Subcontractor, Service provider, Utility, Government. No separate sub ID | design chat gap list item 7, decided 2026-11-22 (owner) |
| Subcontract vendors require lien waivers by default; suppliers don't | S 11-17 10:44 AM |
| The vendor profile shows no bank account numbers, only "bank details on file with our bank" | S 11-14 3:10 PM; RP1 |
| Vendor codes are service-assigned and unique; renaming keeps the code; duplicate creation needs explicit confirmation; inactive vendors stay in history and are excluded from new-bill selection | VENDOR-01, VENDOR-04 (inbox inputs) |
| An inactive vendor's open bills stay payable, with a "Vendor inactive" note on the bill and the pay run line; no new bills or POs for an inactive vendor. Example: a supplier made inactive while owed $3,200.00 can still be paid the $3,200.00 | Q6 A, Decided 2026-11-23 (owner 7:48 PM) |

### 1.3 Proposed schema

`contact` gains (all NULL for a non-vendor; the service refuses them there):

| Column | Type and constraint |
|--------|---------------------|
| `vendor_kind` | TEXT CHECK (`vendor_kind` IS NULL OR IN ('Supplier', 'Subcontractor', 'Service provider', 'Utility', 'Government')); CHECK (`is_vendor` = 1 OR `vendor_kind` IS NULL); required by the service on a vendor |
| `default_expense_account_id` | INTEGER REFERENCES account (bill line default) |
| `default_payment_method` | TEXT CHECK IN ('Check', 'ACH', 'Wire', 'Card', 'Paid outside') (Area 2 reads it; ACH and Wire only when `bank_details_on_file` = 1, service rule) |
| `job_required_on_bills` | INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1) (enforced when a bill is saved: every expense line needs a job) |
| `is_1099` | INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1); `form_1099_box` TEXT (default 'NEC-1' when `is_1099` = 1; the 1099 report is Area 17's) |
| `requires_lien_waivers` | INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1); the service defaults it to 1 when `vendor_kind` = 'Subcontractor' (S 11-17 10:44 AM) |
| `legal_name` | TEXT (1099 and remittance name; `bir_registered_name` stays for the PH add-on) |
| `row_version` | INTEGER NOT NULL DEFAULT 1 (rule g4) |

- `payment_term_id` (exists) becomes readable and writable through `contacts.py` (VENDOR-02).
- The shared vendor source is a read service, `vendors.list_vendors(context, *, active_only, kind=None, query=None)`,
  used by Vendors, New bill, the pay run and PO screens. New bill passes `active_only=True`, so an inactive vendor
  (Granite Ridge Scaffold in the samples) is never offered (OD-36), while history, reports and open documents still
  resolve it. Lookup by code (`?vendor=VCA0014`) returns the vendor or "not found"; not found opens a blank bill
  with no vendor and no error (OD-50).
- Defaults copy at entry only: a saved bill keeps its own terms, account and method when the vendor's defaults
  change later (VENDOR-02).
- Precedence on a new bill line (lead default, owner may revise): PO or subcontract line coding, then the vendor's
  default account, then blank.

### 1.4 How it lands, effects, tests

- Company baseline: the `contact` columns and checks; audit triggers already cover `contact` (Area 18 §1 adds the
  before/after detail).
- Services: `contacts.py` gains the vendor fields and validates them before its write transaction; a new
  `vendors.py` read module (protected read, `ap.view` or `vendor.manage`). No SQL in screens.
- Tests to write later: `test_vendor_list_is_one_source_for_vendors_and_new_bill`,
  `test_new_bill_vendor_picker_excludes_inactive_vendor`, `test_unknown_vendor_code_opens_blank_bill_without_error`,
  `test_vendor_kind_values_and_non_vendor_refused`, `test_subcontractor_kind_defaults_requires_lien_waivers`,
  `test_vendor_setup_fields_round_trip_through_owner_and_consumer`, `test_vendor_defaults_carry_forward_to_new_bill`,
  `test_saved_bill_values_survive_later_vendor_default_changes`,
  `test_vendor_same_name_prefix_gets_distinct_service_assigned_codes_and_exact_contact_ids`,
  `test_vendor_edit_reload_records_audit_history_and_rename_preserves_code`,
  `test_vendor_duplicate_match_name_tax_id_email_including_inactive_contacts`,
  `test_vendor_duplicate_results_link_exact_contacts_and_mask_tax_id_by_permission`,
  `test_vendor_duplicate_creation_requires_explicit_confirmation`,
  `test_inactive_vendor_remains_in_history_and_is_excluded_from_new_bill_selection`,
  `test_vendor_exact_id_open_edit_and_unknown_id_refusal`,
  `test_vendor_documents_tab_shows_only_exact_vendor_links_after_reload`.

---

## 2. Vendor documents and the compliance hold

### 2.1 Current state

No document rows. `payment.release_hold` (sensitive, `:1210`) is seeded with nothing behind it.
`po_ap_matching_design.md` §6 and §10 item 9 decide the hold: a vendor missing a required document puts bills on
payment hold, which blocks payment only, not approval; a person clears or overrides it (role-limited, logged).

### 2.2 Decided

- Compliance holds are in v1 and block **payment only** (`po_ap_matching_design.md` §10 items 3 and 9). **"Always on"
  reading Withdrawn 2026-11-23 (owner 7:40 PM, Q3): the hold applies only when its control is ON; next bullet.**
- **Q3, Decided 2026-11-23 (owner 7:40 PM): warn by default; the compliance hold is an optional control**
  (decisions_2026-11-11 section 0 lists compliance holds as a control, OFF by default; B8; the 11/23 field rule
  "warn, don't block"). Default: a missing or expired required document shows a **warning** on the vendor, the bill
  and the pay run, and the bill can still be paid. A company may turn on the Company control
  `vendor_compliance_hold` (PROPOSED name; Admin or Master, Controls page, audit-logged, **OFF by default**); only
  then is the bill held from payment (never from approval), and holders of `payment.release_hold` may override it
  per bill with a typed reason (at least 10 characters), audit-logged. Example: a sub's workers' comp expired 11/1;
  with the control off, the $18,500.00 draw in Friday's pay run shows the warning and pays.
- Which documents are required is set per vendor type (§10 item 9), editable per company. **Q2 A, Decided
  2026-11-23 (owner 7:32 PM):** Subcontractor: general liability, workers' comp, licence, W-9; Service provider:
  general liability, W-9; Supplier: W-9; Utility and Government: none. Missing or expired means a warning, or a hold
  with the Q3 control ON (owner 7:40 PM correction of the Q2 record). Example: a roofing sub whose workers' comp
  expired 11/1 shows the warning on its bills.
- The mockup's Required documents table (vendor-new, vendor-detail) and the 30-day "need attention" list are the
  screen (design chat gap list item 6; CODE_CHANGES 169).

### 2.3 Proposed schema

**`vendor_document`** (one row per document held for a vendor):

| Column | Type and constraint |
|--------|---------------------|
| `vendor_document_id` | INTEGER PRIMARY KEY |
| `contact_id` | INTEGER NOT NULL REFERENCES contact (a vendor; service check) |
| `doc_type` | TEXT NOT NULL CHECK IN ('Insurance GL', 'Workers comp', 'Licence', 'W-9', 'Other') |
| `doc_label` | TEXT (required when `doc_type` = 'Other') |
| `number_or_policy` | TEXT |
| `issued_on`, `expires_on` | TEXT dates (`IS date(...)`); `expires_on` NULL for a W-9 |
| `attachment_id` | INTEGER REFERENCES the Area 18 §3 attachment row (file through `storage.py`, with hash) |
| `received_without_file_reason` | TEXT; CHECK (`attachment_id` IS NOT NULL OR length(trim(received_without_file_reason)) >= 10) |
| `superseded_by_id` | INTEGER REFERENCES vendor_document (a renewal adds a new row; the old one stays) |
| `created_by`, `created_at`, `row_version` | as rule g4 |

Status is derived, never stored: **On file** (current row, not expired), **Expiring** (expires within 30 days, the
"need attention" item), **Expired**, **Missing** (required for the kind and no current row).

**`vendor_kind_document`** (what each kind needs; a company setting, edited on the Controls page, every change
logged): `vendor_kind` TEXT, `doc_type` TEXT, `is_required` INTEGER 0/1; PRIMARY KEY (`vendor_kind`, `doc_type`).
The baseline seeds the Q2 defaults. (Lead default, owner may revise: a small table now; Area 21's scoped policy
records (X 6) may absorb it later. The baseline has no `policy_rule` table.)

**Compliance warning and hold (Q3).** Derived at the moment of payment, not stored as a flag. A bill from a vendor
with a Missing or Expired required document:
- with `vendor_compliance_hold` **OFF** (default): shows "Missing documents: <list>" on the vendor, the bill and the
  pay run line, and can be added to a pay run and recorded; recording writes an audit event "Paid with missing
  documents" (no reason asked; lead default, owner may revise, like Area 2's "Paid without waiver");
- with it **ON**: cannot be added to a pay run or recorded (Area 2 rechecks at approval and at recording) unless an
  override row exists for that bill.
An override is a stored row, **`bill_compliance_override`** (`invoice_id`, `vendor_document_type`, `reason` CHECK
length(trim) >= 10, `overridden_by`, `overridden_at`), insert-only, by a holder of `payment.release_hold`, and is
used only while the control is ON. It covers that bill only.

### 2.4 Lands, effects, tests

- Company baseline: both tables, the override table, audit triggers, the seed rows.
- Services: `vendors.py` writes documents (permission `vendor.manage`); the compliance check is one function the bill
  and pay-run services call (`vendors.compliance_status(conn, contact_id, invoice_id, as_of)`, returning OK, Warn
  or Hold from the control).
- Tests: `test_vendor_document_status_derived_on_file_expiring_expired_missing`,
  `test_expiring_document_raises_attention_30_days_ahead`,
  `test_missing_required_document_warns_and_pays_when_control_off`,
  `test_missing_required_document_holds_payment_not_approval_when_control_on`,
  `test_compliance_control_defaults_off_and_change_is_audit_logged`,
  `test_compliance_override_needs_permission_and_10_character_reason_and_covers_one_bill`,
  `test_renewal_adds_row_and_keeps_superseded_document`, `test_required_documents_follow_vendor_kind_setting`.

---

## 3. Bills

### 3.1 Current state

- Bills are `invoice` rows (`invoice_type` 'Bill', `ledger_side` 'Purchase') with `voucher_number` (GLOB 'VCH-*'),
  `revision_no` and `supersedes_id`, legacy `terms` CHECK (four fixed values, TERM-03), `status` including 'In pay
  run', `retainage_cents`, positive-amount checks and `UNIQUE (invoice_type, contact_id, invoice_number)`.
- `invoice_line` (`:652`) has account, cost code, tax rate and a retainage marker, **no line job** (Area 10 F8).
- `voucher_sequence` (`:1282`) starts at 1000; `document_approval_setting` has 'Bill' and 'Vendor credit' (OFF).
- No bill service. `ledger.create_document_entry` (`:516`) and `void_document_entry` (`:1030`) post and reverse a
  document's entry.

### 3.2 Decided

| Decision | Source |
|----------|--------|
| Every bill has a read-only Voucher # (VCH-1001...), assigned at first save, unique, gaps allowed | S 11-14 11:15 PM; decision 1.3 |
| A duplicate vendor and bill number can't be saved without "This is a different bill" plus a reason; it then goes to Approvals flagged; never approved in one click or in bulk | S 11-14 2:40 PM, 2:30 PM; L (duplicate warns + control) |
| Bill lines carry a cost code (required with a job) and a Billable flag with markup | S 11-14 2:40 PM |
| A bill is job-coded per **line**. Example: one $12,000.00 panel bill: line 1 $8,000.00 RI0001-002, line 2 $4,000.00 RI0001-003 | Q1 A, Decided 2026-11-23 (owner 7:32 PM) |
| An approved bill needs re-approval only when its **vendor or total** changes, and only while 'Bill' approval (the control) is ON; with it OFF the same change shows a warning and the bill stays approved. A due-date change never triggers re-approval. A job or GL change with the same total stays the same-gross reclass (item 13), no re-approval. Example: approval ON, $12,000.00 changed to $12,400.00 goes back to approval; approval OFF, a warning only | Q4, Decided 2026-11-23 (owner 7:44 PM; replaces option A, which included the due date) |
| Approval is one word, **Approve**; after it the bill is **Approved** and payment **OK to pay**; a warning (PO/receipt difference, possible duplicate) needs "Approve anyway" with a reason; one approval record everywhere | S 11-18 10:24 PM |
| Any bill can be held with a reason (Pay when paid, Waiting on cash, Dispute, Other); release any time, no reason needed; every hold and release recorded; the job's PM or anyone with bill-payment permission | S 11-17 10:44 AM, 12:10 PM |
| Resubmitting a sent-back bill may change the vendor, with a warning, logged "Vendor A → B", back to Needs review | S 11-17 12:10 PM |
| Posted bills and vendor credits are editable by default: one reversal and a new posting under the same number, every version kept; blocked in closed or locked periods, below the amount paid, in a submitted pay run, or while `Lock documents after posting` is ON | S 11-14 3:05 PM; CLAUDE.md rule 8 |
| A same-gross correction that moves account, job or line allocation without changing the total is a **reclass** through journal entry approval, or the route already set for reclasses; no separate bill re-verification route | item 13 (APBILL-05), owner 2026-11-22 |
| New bill opens blank at every entry point (OD-08, OD-21); Reload keeps the typed values as an unsaved session draft for the tab session only; Back/Forward and links open blank; Save, Save and new and Cancel discard it (OD-17, OD-37); the posting-preview vendor-name claim is dropped (OD-08, VENDOR-05) | owner 2026-11-22 |
| A prepaid bill line can be deferred ("Defer expense"), with a separate schedule entry | S 11-18 11:55 PM; Area 10 §1 |

### 3.3 Proposed schema

**Identity and versions.** Bills reuse Area 5's stable document identity and immutable posted versions (§2.3 and
8.2 Q2 there) on the purchase side: one bill identity, one Voucher #, one vendor bill number, versions linked to
their ledger entries, reversal and replacement links. Each posted version stores the AP account it posted to
(Area 18 §8.1, item 11), and settlement and reversal read that stored account. Area 5 and this area share the
versioning, lock checks and reversal logic; Voucher # and the vendor's bill number are the purchase-side numbers
(no sales series).

**Changes to `invoice` (bill rows):**
- Drop `UNIQUE (invoice_type, contact_id, invoice_number)` for bills (it refuses what the decision allows, APBILL-03);
  keep a non-unique index (`contact_id`, `invoice_number`) for the duplicate check. The Sales side keeps its series
  uniqueness.
- `duplicate_reason` TEXT (CHECK length(trim) >= 10 when set) and `duplicate_of_id` INTEGER REFERENCES invoice:
  set when the user confirmed "This is a different bill"; the approval queue shows the flag.
- `terms` (legacy fixed list) is dropped; the bill version freezes `payment_term_id` plus `due_days`,
  `discount_percent`, `discount_days` and the computed `due_date` and `discount_deadline` (§5).
- `review_status` TEXT NOT NULL DEFAULT 'Needs review' CHECK IN ('Needs review', 'Work verified', 'Sent back',
  'Resubmitted', 'Approved') ('Work verified' only where the company turns on the PM verification step, S 11-18
  10:24 PM). The approval itself stays in `approval_request` when 'Bill' approval is ON (Area 14); with it OFF,
  Approve writes the approver and time on the bill (`approved_by`, `approved_at`).
- `status` keeps 'Draft', 'Paid', 'Void'; 'In pay run' is derived (not stored) from an open Area 2 line in an
  **Approved** run, so the list, the drawer and the pay run cannot disagree; a bill ticked in a Draft run shows
  Approved with a link to that draft. (Lead default, owner may revise.)
- `subcontract_id` INTEGER (FK once the subcontract table exists, §4) and `over_limit_reason` TEXT (§4).
- `row_version` INTEGER NOT NULL DEFAULT 1.

**`invoice_line` (bill lines):** `project_id` INTEGER REFERENCES project (a job per line, Area 10 F8; the header
job is the default for new lines; Q1), `is_billable` INTEGER 0/1 and `markup_percent` REAL (T&M; Area 5 pulls them
once), `po_line_id`, `receipt_line_id` and `subcontract_line_id` (FKs when Area 9 and §4 add the tables),
`retainage_withheld_cents` INTEGER (§4). A cost code is required on a line with a job (service rule, existing
`ledger._check_cost_codes`).

**`bill_hold`** (one row per hold; insert-only except the release columns; S 11-17):

| Column | Type and constraint |
|--------|---------------------|
| `hold_id` | INTEGER PRIMARY KEY |
| `invoice_id` | INTEGER NOT NULL REFERENCES invoice (a bill) |
| `reason_code` | TEXT NOT NULL CHECK IN ('Pay when paid', 'Waiting on cash', 'Dispute', 'Other') |
| `reason_text` | TEXT; CHECK (`reason_code` <> 'Other' OR length(trim(reason_text)) >= 10) |
| `linked_invoice_id` | INTEGER REFERENCES invoice (the customer invoice a pay-when-paid hold waits on; shows "customer paid $X of $Y") |
| `origin` | TEXT NOT NULL CHECK IN ('Manual', 'Re-hold after reversal', 'Retainage release') |
| `held_by`, `held_at` | NOT NULL |
| `released_by`, `released_at` | NULL until released; both set or both NULL; no reason needed (S 11-17 10:44 AM) |

A partial unique index allows one open hold per bill (`invoice_id` WHERE `released_at` IS NULL). A held bill
cannot be added to a pay run (Area 2).

**Re-hold after reversals (S 11-17 5:13 PM; Area 4 §4).** When an owner pay app is returned, its invoice is voided or
a customer payment on it is reversed, its released bills that are not in a pay run or paid get a new `bill_hold`
('Pay when paid', origin 'Re-hold after reversal'), logged, and the PM is notified. Paid bills and bills in a pay run
are not touched. Area 4 triggers it; this area's service writes the rows.

**Pay-when-paid time limit (S 11-17 5:13 PM).** `company_settings.pay_when_paid_limit_days` INTEGER NULL (NULL = off),
on the Controls page: a hold warns 7 days before and on the date; it never releases a hold.

### 3.4 Same-number edit and same-gross correction

- **Edit (rule 8, R31).** One transaction: `ledger.void_document_entry` on the posted version and
  `ledger.create_document_entry` for the new one, under the same Voucher # and bill number, with a reason (at least
  10 characters) and version history. Refused: closed or locked period or area (Area 13 on both posting dates),
  `lock_documents_after_posting` ON, the new total below the amount paid, the bill in a pay run (Area 2), or in a
  locked owner pay app ("Locked in pay app #<n>. An approver unlocks the pay app first.", S 11-18 10:50 AM). If
  either posting fails, both roll back (APBILL-05). Re-approval follows Q4 (§3.2): only a vendor or total change,
  only with 'Bill' approval ON; otherwise the edit posts with the warning "This bill was approved at <amount>; the
  change is logged."
- **Same-gross correction (item 13).** When the total is unchanged and only account, job or line allocation moves,
  the bill service posts a reclass (Area 10 §2, one pair per moved line; the AP line takes the new job too when the
  whole bill is on one job, otherwise it is untouched: Area 10 Q20 B, decided 2026-11-23) instead of a reversal and
  repost. A reclass whose lines are all expense accounts posts with no approval and no hold (owner 8:05 PM, Area 10
  §11.7); any other reclass follows the approval route set for reclasses. The bill keeps its version; it shows
  "Reclassed". The edit dialog routes to it automatically. The same guards as Edit apply: refused while the bill is
  in a pay run or in a locked owner pay app (a job or cost-code move changes that pay app's cost basis; Area 4 needs
  a new revision, so an approver unlocks it first). The reclass date follows Area 10's one date rule (§11.7, Q21 A
  with OD-71, decided 2026-11-23): the bill line's date when its period is open and unlocked, otherwise today,
  changeable but never into a closed or locked period; Area 13 checks that date. Permission: `je.reclass` (Area 10 §7.1) in addition to the bill edit
  code.

### 3.5 Lands, effects, tests

- Company baseline: the column changes on `invoice` and `invoice_line`, `bill_hold`, `pay_when_paid_limit_days`,
  triggers that keep holds insert-only, audit triggers.
- Services: a new `bills.py` (create, save, approve, hold, release, send back, resubmit, edit, void), calling
  `authorize` first, `period_locks.check_open` (Area 13) and the ledger helpers; the bill void calls
  `deferrals.void_for_bill` in its transaction (Area 10).
- Tests: `test_apbill01_save_creates_one_durable_bill_with_voucher_vendor_job_subcontract_and_amounts`,
  `test_apbill01_bills_detail_and_required_approval_resolve_same_bill_after_reload`,
  `test_apbill01_save_and_new_clears_only_after_success`,
  `test_apbill02_impossible_dates_and_malformed_amounts_are_refused`,
  `test_apbill02_due_date_quantity_rate_tax_retainage_and_saved_cents`,
  `test_apbill03_same_invoice_number_for_two_vendors_resolves_by_exact_voucher`,
  `test_apbill03_vendor_scoped_lookup_returns_exact_bill`, `test_apbill03_missing_or_ambiguous_bill_reference_is_explicit`,
  `test_duplicate_bill_number_needs_different_bill_reason_and_flags_approval`,
  `test_voucher_number_assigned_at_first_save_unique_gaps_allowed`,
  `test_bill_approval_state_is_one_record_across_list_approvals_page_and_drawer`,
  `test_approve_anyway_requires_reason_for_warning`, `test_bill_hold_and_release_are_recorded_with_history`,
  `test_held_bill_cannot_join_pay_run`, `test_rehold_after_owner_payapp_return_void_or_payment_reversal`,
  `test_pay_when_paid_limit_warns_and_never_releases`,
  `test_apbill05_same_gross_correction_posts_reclass_through_reclass_route`,
  `test_apbill05_rule8_required_approval_blocks_reversal_and_replacement`,
  `test_apbill05_rule8_reason_reversal_replacement_and_version_history`,
  `test_apbill05_area13_locks_apply_to_both_postings`, `test_apbill05_failure_of_either_posting_rolls_back_both`,
  `test_apbill05_locked_pay_app_pay_run_and_payment_guards_remain`, `test_bill_version_stores_ap_account_it_posted_to`,
  `test_bill_line_with_job_requires_cost_code`, `test_vendor_job_required_refuses_line_without_job`,
  `test_edit_changing_vendor_or_total_needs_reapproval_only_with_bill_approval_on`,
  `test_edit_changing_vendor_or_total_with_approval_off_warns_and_stays_approved`,
  `test_due_date_change_never_triggers_reapproval`, `test_inactive_vendor_open_bill_stays_payable_with_note`.
- Screen behaviour only (no schema; tests in the screen phase): New bill blank at every entry point; the
  tab-session draft on Reload (OD-17, OD-37).

---

## 4. Subcontract bills, retainage, draws and lien waivers

### 4.1 Current state

No subcontract, draw or waiver table; `subcontract.approve` is seeded (`:1214`). `po_ap_matching_design.md`
§3 proposes the subcontract as a `purchase_order` with `po_type` 'Subcontract', its lines as the vendor's schedule
of values, `purchase_order_change` for changes, and `subcontract_billing` on a to-date basis.
`company_settings.retainage_payable_acct_id` exists (2020 Retainage Payable in the repo chart).

### 4.2 Decided

| Decision | Source |
|----------|--------|
| Over-limit subcontract bill: Save bill and Save and new both warn and require a reason; Company control (OFF) makes both refuse. The limit is the remaining approved value including approved change orders | item 12 (APBILL-04, SUBPAY-04) |
| Compare the **gross** amount. SC-014 sample: $9,600.00 = no warning, $9,600.01 = over; CO-1 approved $5,000.00 counts ($14,600.00 left), CO-2 not approved $3,000.00 does not | OD-38 A |
| The banner ends "Enter a reason to save anyway."; a required "Reason for exceeding the subcontract" field (at least 10 characters); Save is refused with "Enter a reason." while blank; the reason is saved on the bill and in the audit log; Save and new saves and opens a blank bill | OD-39 A |
| Settings > ERP settings checkbox "Refuse subcontract bills over the remaining approved value", OFF; refusal "This bill is over what is left on the subcontract. Add an approved change order first." | OD-40 A |
| Sub pay apps split into payable now and retainage held (Retainage payable) | S 11-14 2:40 PM |
| Sub retainage release follows pay when paid: the release bill starts held, linked to the owner's retainage invoice; the PM or anyone with bill-payment permission releases it | S 11-17 5:13 PM |
| Lien waivers warn by default. "Require lien waivers before paying subs" (OFF) blocks only adding the bill to a pay run until this draw's conditional and the prior paid draw's unconditional waiver are in. Attaching a file marks it received; received without a file needs a reason | S 11-17 10:44 AM; SUBPAY-02 (owner 2026-11-19) |
| A billed (locked) owner pay app blocks Send back and Edit on its bills; fixes go through a vendor credit or a Dispute hold, or an approver unlocks the pay app first | S 11-17 4:16 PM; S 11-18 10:50 AM |
| A bill counts in one owner billing cycle only, joins by date against the cut-off, and the PM may move it to the next | S 11-17 10:44 AM; Area 4 §2.1 |
| Pay app adjust, unlock or replace: Accountant, Admin and Master with a reason (`payapp.adjust`); a PM can request it; job titles and templates can grant it; all logged | item 17; Area 4 §5 and Q5–Q7 |
| A sub bill with no subcontract may carry a manual retainage withheld amount (with a reason, by the approver) and appears on an "approved without commitment" report | `po_ap_matching_design.md` §10 item 7 |

### 4.3 Proposed schema

- **Subcontract and its lines:** this area uses the PO design's subcontract (`purchase_order` with `po_type`
  'Subcontract', its lines as the schedule of values, approved `purchase_order_change` rows). Area 9 builds those
  tables with POs. **Ownership flagged:** row 4's X 3 lists "subcontract and sub SOV, sub pay-app lines, waivers"
  under Area 4, whose draft covers the customer side only. This draft takes the AP side (draws, retainage withheld,
  waivers, the over-limit check) and leaves the commitment header and lines to Area 9 (O1 in §10).
- **Remaining approved value** (computed, not stored): per subcontract, original value + approved change orders −
  gross billed on posted bills (all versions' effective totals). The check runs in the bill save transaction on the
  gross amount (OD-38) for Save bill and Save and new alike.
- `invoice.over_limit_reason` TEXT (CHECK length(trim) >= 10 when set); the service requires it when over and
  `subcontract_overlimit_block` is OFF, and refuses when it is ON (OD-40 text).
- **`company_settings.subcontract_overlimit_block`** INTEGER NOT NULL DEFAULT 0 (Area 18 §8.3; Controls page, logged).
- **Draws (`sub_draw`)**: one row per sub pay app period per subcontract, linked to the bill it creates (`invoice_id`
  UNIQUE), with `draw_no` (unique per subcontract), period end, and **`sub_draw_line`** per subcontract line:
  `billed_to_date_cents`, `this_period_cents` (= to date − prior approved; refused below 0 or above the revised line,
  SUBPAY-04), `retainage_rate` (read-only from the subcontract, R29), `retainage_withheld_cents`. Rounding: cumulative
  round-half-up (to-date × rate) minus prior cumulative (`po_ap_matching_design.md` §4). Send back on an unlocked
  cycle saves a reason and removes the draw from that cycle (SUBPAY-01).
- **Bill posting with retainage:** Dr job cost (line job and cost code) gross; Cr AP net; Cr Retainage payable
  withheld. A **retainage release bill** moves an amount from Retainage payable to AP, touches no cost, starts with a
  `bill_hold` ('Pay when paid', origin 'Retainage release', `linked_invoice_id` = the owner's retainage invoice),
  and cannot release more than held per subcontract (held = withheld − released, equal to the GL).
- **`lien_waiver`**: `draw_id` FK sub_draw, `waiver_type` CHECK IN ('Conditional', 'Unconditional'), `covers_draw_id`
  (the unconditional waiver covers the prior paid draw), `attachment_id` (Area 18 §3), `received_without_file_reason`
  (length >= 10 when no file), `received_by`, `received_at`. With the control OFF a bill paid while a waiver is
  missing is logged "Paid without waiver" by Area 2 at recording (an audit event; no reason, as the mockup and S
  11-17 10:44 AM have it). With the control ON the gate refuses adding the bill to a pay run; Area 2 runs the same
  check when a line is added, at approval and at recording (Area 2 §4).
- **`company_settings.require_lien_waivers_before_paying`** INTEGER NOT NULL DEFAULT 0 (Controls page, logged);
  applies to vendors with `requires_lien_waivers` = 1.
- Retainage on bills the contractor **gives** the owner (owner-side waivers) is not covered (design chat item 8;
  Area 4, O2).

### 4.4 Lands, effects, tests

- Company baseline: `sub_draw`, `sub_draw_line`, `lien_waiver`, the two controls, the bill columns; FKs to the
  subcontract tables in the same pass as Area 9.
- Services: `bills.py` (over-limit check, retainage split, release bill), `sub_draws.py`; both refuse an edit while
  the owner pay app that holds the bill is locked, and honour `payapp.adjust` through Area 4's unlock.
- Tests: `test_apbill04_remaining_approved_value_case_for_both_save_actions`,
  `test_apbill04_one_cent_over_warns_and_requires_reason_for_both_save_actions`,
  `test_apbill04_overlimit_block_control_refuses_both_save_actions`,
  `test_apbill04_retry_succeeds_after_approved_change_order_increases_limit`,
  `test_overlimit_compares_gross_and_ignores_unapproved_change_order`,
  `test_overlimit_reason_saved_on_bill_and_audit_log`, `test_subpay04_sc014_5997_percent_negative_draw_is_refused`,
  `test_subpay04_manual_negative_720_is_refused`, `test_subpay04_exact_cumulative_floor_and_valid_positive_draw`,
  `test_subpay01_edited_draw_gross_retainage_and_net_match_linked_bill_after_reload`,
  `test_subpay01_send_back_saves_reason_removes_exact_cycle_membership_and_reloads_consistent_status`,
  `test_subpay01_locked_cycle_refuses_send_back`, `test_sub_retainage_rounding_has_no_drift_over_many_draws`,
  `test_retainage_release_bill_starts_held_and_links_owner_retainage_invoice`,
  `test_retainage_release_cannot_exceed_held_and_posts_no_cost`,
  `test_subpay02_file_linked_to_exact_draw_marks_waiver_received_and_shows_file_row`,
  `test_subpay02_received_without_file_requires_reason`, `test_lien_waiver_warning_default_and_configured_payrun_gate`,
  `test_locked_owner_payapp_blocks_bill_edit_and_send_back`, `test_payapp_adjust_unlock_lets_bill_edit_with_reason`.

---

## 5. Payment terms and early-payment discounts

### 5.1 Current state

`payment_term` (`:3884`): `name` UNIQUE, `days_due` ≥ 0 integer, `discount_percent` 0–100 REAL, `discount_days`
integer, `is_active`. `invoice.payment_term_id` and `contact.payment_term_id` exist; the legacy `invoice.terms` list
is separate (TERM-03). No row version, no audit detail of term edits.

### 5.2 Decided

| Decision | Source |
|----------|--------|
| The discount applies through the deadline date **inclusive**, calculated on the bill total | item 16 (TERM-04) |
| If it expires before the payment is recorded, the line returns for review at the full amount | item 16 |
| It posts to the `purchase_discounts` role, **or back to the job cost line when the bill is job-coded**; only bills with no job use Purchase discounts (e.g. SPS-88214, $368.40 off RI0001-002's cost) | item 16; OD-66 B; Area 18 §8.6 |
| On the payment line the discount is an editable amount, defaulting to the calculated amount (pro rata for a partial payment), and can be changed, e.g. to $0 | item 16 (owner addition) |
| Compare the pay run's Date paid with the deadline | OD-24 A |
| Total to pay is net of the discount; the preview shows AP debit (full), bank credit (net), Purchase discounts or job cost credit (discount) | OD-25 A; OD-66 B |

### 5.3 Proposed schema and rules

- `payment_term` gains `row_version`; deactivation keeps history (TERM-01); duplicate names are refused ignoring case
  (service; no `COLLATE NOCASE`, H5); fractional or negative days and percentages over 100 are refused (TERM-02,
  existing CHECKs plus the service).
- The bill version freezes `payment_term_id`, `due_days`, `discount_percent`, `discount_days`, `due_date` and
  `discount_deadline` (= bill date + discount days). A later edit of the term changes no saved bill (TERM-03).
- Calculated discount = round-half-up(bill total × percent); for a partial payment, pro rata: round-half-up(discount ×
  paid ÷ total), with the last payment taking the remainder (lead default, owner may revise). Area 2 stores the
  editable amount on the pay run line.
- Posting of the discount: Dr AP (full applied amount) / Cr bank (net) / Cr the discount: for a job-coded bill, one
  credit per job-coded line on that line's account, job and cost code, split pro rata by line amount with the
  rounding remainder on the last line (Q5 A, Decided 2026-11-23, owner 7:48 PM; example: 2% = $240.00 on a
  $12,000.00 bill: the $8,000.00 RI0001-002 line's cost falls $160.00 and the $4,000.00 RI0001-003 line's
  $80.00); otherwise Cr
  `purchase_discounts`.
- Tests: `test_term_exact_id_create_view_edit_deactivate_and_audit_after_reload`,
  `test_term_usage_counts_and_new_document_picker_follow_active_state_after_reload`,
  `test_historical_documents_retain_saved_terms_and_due_dates`,
  `test_term_due_days_discount_percent_and_discount_days_round_trip_separately`,
  `test_term_zero_days_allowed_and_fractional_or_negative_days_refused`,
  `test_term_percentage_over_100_and_duplicate_name_refused`,
  `test_standard_45_day_vendor_default_uses_stored_days_for_due_date`,
  `test_bill_due_date_and_agreed_terms_stay_fixed_after_term_definition_changes`,
  `test_discount_deadline_is_inclusive_across_bill_detail_pay_run_and_preview`,
  `test_discount_expired_one_day_later_matches_bill_detail_pay_run_and_preview`,
  `test_discount_on_job_coded_bill_credits_job_cost_line`, `test_discount_on_bill_without_job_uses_purchase_discounts`,
  `test_partial_payment_discount_defaults_pro_rata_and_is_editable_to_zero`,
  `test_job_coded_discount_split_pro_rata_by_line_remainder_on_last_line`.

---

## 6. Vendor credits and refund requests

### 6.1 Current state

A vendor credit is an `invoice` row with `invoice_type` 'Credit Memo' and `ledger_side` 'Purchase' (positive
amounts, typed); `payment_allocation` already takes a credit memo as a source (`credit_memo_id`). No `VC-` series,
no refund request, no hold.

### 6.2 Decided

| Decision | Source |
|----------|--------|
| Vendor credits are numbered `VC-###` in their own series, assigned at posting; shown as negative on lists | S 11-14 2:40 PM; VCR-02 (owner-approved series) |
| A saved refund request holds its outstanding amount against that exact credit; released on cancel, reduced as refund cash is received; bills and pay runs see only the unheld remainder | item 14 (VCR-01, VCR-03, PAYRUN-04, VCR-04) |
| A refund receipt also lowers the credit's **open balance**; usable = open credit − held. VC-031: $350.00 requested, $100.00 received → open $250.00, held $250.00, usable $0.00; second sample $200.00 requested, $50.00 received → open $300.00, held $150.00, usable $150.00 | OD-67 B (corrects OD-26's numbers) |
| A remainder can be written off to any active expense or other-income account by Accountant, Admin or Master, with a reason; approval only above a Company threshold (OFF); period locks apply | item 15 (VCR-04) |

### 6.3 Proposed schema

- Vendor credits stay typed purchase credit memos (`invoice_type` 'Credit Memo', `ledger_side` 'Purchase'); the
  mockup's "negative bill" wording is display only (VCR-02). A `VC` series row in the shared sequence pattern assigns
  the number at posting (gaps not allowed, like CM-### in Area 5 §9.1).
- **`vendor_refund_request`**: `request_id`, `contact_id` NOT NULL, `credit_invoice_id` NOT NULL (the exact credit),
  `requested_cents` INTEGER > 0, `expected_on`, `status` CHECK IN ('Requested', 'Partly received', 'Closed',
  'Cancelled', 'Written off'), `reason` (length >= 10), `created_by`, `created_at`, `cancelled_by`, `cancelled_at`,
  `cancel_reason`, `row_version`. Saving posts nothing (the credit already sits as a debit in AP).
- **`vendor_credit_hold`** (item 14): one row per request: `request_id` UNIQUE, `credit_invoice_id`, `held_cents`
  (= requested), `released_cents` (grows on cancel), `status` CHECK IN ('Active', 'Released', 'Consumed'). Held now
  = requested − received − released.
- **`vendor_refund_receipt`**: `request_id`, `received_on`, `amount_cents` > 0, `deposit_account_id` (bank, or
  Undeposited funds for a check), `reference`, `entry_id` UNIQUE; posts Dr bank / Cr AP on the credit's own AP
  account and clearing group (VCR-03). Refused above the request's outstanding amount or the credit's open balance
  (VCR-04). Retry with the same operation ID returns the first receipt (S 11-20 5:15 PM).
- **Balances (derived):** open credit = credit total − applications to bills − refunds received − written off;
  held = Σ active holds' outstanding; **usable = open − held** (OD-67). The pay run and bill allocation read usable,
  checked again in the write transaction so competing writes never consume more than the credit.
- **`vendor_credit_write_off`**: `credit_invoice_id`, `amount_cents` (≤ open − held), `account_id` (active expense
  or other income), `reason` (length >= 10), `entry_id` UNIQUE (Dr the chosen expense or other-income account / Cr AP on the
  credit's stored AP account and clearing group: the credit is a debit balance in AP, so writing off the rest is a
  loss), `approval_request_id`
  (only when the amount is over `company_settings.vendor_credit_writeoff_approval_threshold_cents`, NULL = off;
  Area 14 routes it). Permission `vendor_credit.write_off` (Area 18 §8.2). The linked posting is created before
  the balance or the request status changes.
- Tests: `test_vcr01_request_saves_exact_vendor_and_credit_without_posting`,
  `test_vcr01_partial_receipt_reload_and_remainder_recording`,
  `test_vcr01_receipts_link_exact_credit_and_ap_clearing_group`,
  `test_vcr01_receipt_retry_does_not_duplicate_receipt_or_posting`,
  `test_vcr02_purchase_credit_memo_type_survives_entry_selection_allocation_and_reversal`,
  `test_vcr02_vc_series_assigned_at_posting_gapless`,
  `test_vcr03_vendor_change_clears_incompatible_credit_and_refreshes_choices`,
  `test_vcr03_receipt_amount_and_destination_match_preview_and_posting`,
  `test_vcr04_rejects_impossible_dates_closed_or_locked_periods_and_excess_receipts`,
  `test_vcr04_write_off_requires_reason_and_eligible_selected_account`,
  `test_vcr04_write_off_posts_linked_entry_before_balance_and_request_change`,
  `test_vcr04_write_off_over_threshold_needs_approval_when_set`,
  `test_vcr_request_hold_prevents_competing_bill_or_pay_run_consumption`,
  `test_refund_receipt_lowers_open_balance_and_usable_is_open_minus_held` (VC-031: 250/250/0; second: 300/150/150),
  `test_cancel_releases_hold`.

---

## 7. Locks, permissions, controls, row version and audit

- **Locks (Area 13 §1.4):** bills, vendor credits, retainage release bills and write-offs check the "Bills and
  vendor credits" area and every account their lines touch; refund receipts check "Bill payments" and the AP and
  bank lines. Area 13 §1.4's caller table has no row for refund receipts or write-offs yet: these two rows are
  PROPOSED for an Area 13 amendment line when this area is approved. Edits check both posting dates. Custom field values and attachment removal on a posted bill check the
  area only (Q6 A there).
- **Permissions:** existing `vendor.manage`, `bill.create`, `bill.approve` (sensitive), `bill.override_match`,
  `bill.void`, `payment.release_hold` (sensitive; compliance overrides), `ap.view`, `subcontract.approve`,
  `payapp.adjust` (Area 4), `vendor_credit.write_off` (Area 18 §8.2). New (PROPOSED, placed by an Area 18 amendment
  when approved): `bill.hold` (place and release holds; the job's PM gets it by project scope, and every
  `payment.make` holder has it, S 11-17 12:10 PM), `bill.edit_posted` (same-number edit; not sensitive),
  `vendor_document.manage` and `vendor_refund.manage`. None is in `AGENT_ALLOWED`; the agent may draft a bill for
  human approval only (CLAUDE.md section 0).
- **Controls (all OFF, Controls page, every change logged):** `vendor_compliance_hold` (PROPOSED name, Q3),
  `subcontract_overlimit_block`,
  `require_lien_waivers_before_paying`, `pay_when_paid_limit_days` (NULL), `vendor_credit_writeoff_approval_threshold_cents`
  (NULL), the existing 'Bill' and 'Vendor credit' approval toggles, `lock_documents_after_posting`, and the
  duplicate-bill block (L, owner 2026-11-17 16:05: "warns, with a control to block"; PROPOSED name
  `block_duplicate_bills`, OFF: with it ON a same-vendor duplicate bill number is refused instead of warned).
- **Reasons:** every typed reason here is at least 10 characters after trimming (OD-31; Area 18 §8.6); a reason
  picked from a list (a bill hold's Pay when paid, Waiting on cash or Dispute) needs no typed text (Area 18 §8.7).
- **Row version (rule g4):** `contact`, `invoice` (bill rows), `bill_hold`, `vendor_document`, `vendor_refund_request`,
  `sub_draw`, `payment_term` carry `row_version`; services refuse stale saves.
- **Audit:** every table above has insert/update audit triggers with before/after detail (Area 18 §1); holds,
  waivers, overrides, receipts and write-offs are insert-only.

## 8. Conflicts with decisions or the baseline (flagged, not resolved here)

- **F1 Duplicate bills vs the baseline.** `UNIQUE (invoice_type, contact_id, invoice_number)` refuses a same-vendor
  duplicate that S 11-14 2:40 PM allows with a reason (APBILL-03). Proposal: drop it for bills (§3.3).
- **F2 Subcontract ownership.** Row 4's X 3 lists subcontracts, sub SOV, sub pay-app lines and waivers under Area 4;
  Area 4's draft covers only customer pay apps. This draft takes the AP side and leaves the commitment tables to
  Area 9 (O1).
- **F3 Legacy `invoice.terms`.** The fixed four-value CHECK conflicts with company terms (TERM-03); proposal: drop it
  and freeze term values on the version (§5.3).
- **F4 `payment.method` CHECK** (`:670`: Cash, Check, Bank Transfer, GCash, Maya) lacks ACH, Wire, Card and Paid
  outside; Area 2 proposes the change.
- **F5 Item 13 vs Area 10 §2.4:** the same-gross correction is a reclass, which never moves the AP line (refused
  there); consistent, since the total and vendor do not change. **Updated 2026-11-23 (owner 8:05 PM, Area 10 Q20 B): a
  job change on a bill wholly on one job moves the AP line too (Area 10 §11.7).**
- **F6 Re-hold trigger:** S 11-17 5:13 PM puts the re-hold in AP; Area 4 §4 applies the rule. This draft writes the
  rows when Area 4's service calls it.

## 9. Questions for Mark (business rules only; recommended option first)

- **Q1. A job per bill line, or one job per bill?** **Answered 2026-11-23 (owner 7:32 PM): A (§3.2).**
  A (recommended): each bill line carries its own job (the header job is the default for new lines), as Area 10 F8
  expects. Example: one supplier bill for wire used on RI0001-002 and SU0004-004 is entered once with two job lines.
  B: one job per bill, like invoices (OD-09); a two-job supplier bill is entered as two bills.
- **Q2. Which documents each vendor kind needs by default (compliance hold).** **Answered 2026-11-23 (owner 7:32 PM):
  A; "can be approved but not paid" applies only with the Q3 control ON (§2.2).**
  A (recommended): Subcontractor: GL insurance, workers' comp, licence, W-9; Service provider: GL insurance, W-9;
  Supplier: W-9; Utility and Government: none. Companies edit the list. Example: a new Subcontractor with no workers'
  comp certificate shows "Missing" and its bills can be approved but not paid.
  B: only GL insurance and the lien waiver, as `po_ap_matching_design.md` proposed.
- **Q3. Who may override a compliance hold on one bill?** **Answered 2026-11-23 (owner 7:40 PM): warn by default; the
  hold is a control, OFF; with it ON, `payment.release_hold` holders override per bill with a typed reason (§2.2).**
  A (recommended): holders of `payment.release_hold` (Admin and the Master by default; grantable by job title), per
  bill, with a reason of at least 10 characters, logged. Example: Dana Reyes (Admin) pays VCH-1022 while the renewed
  GL certificate is on its way.
  B: Admin and the Master only, never grantable.
- **Q4. Editing a posted, approved bill when Bill approval is ON.** **Answered 2026-11-23 (owner 7:44 PM): vendor or
  total only, only with approval ON, else a warning; option A's due date Withdrawn 2026-11-23 (§3.2).**
  A (recommended): the new version needs approval again when the total, vendor or due date changes; a same-gross
  allocation change follows item 13's reclass route instead. Example: raising VCH-1015 from $2,400.00 to $2,460.00
  sends it back to Approvals; moving a line from cost code 03-100 to 03-200 posts a reclass.
  B: every edit of an approved bill needs approval again.
- **Q5. Discount on a job-coded bill with several lines (OD-66).** **Answered 2026-11-23 (owner 7:48 PM): A, with the
  remainder on the last line ("largest line" below Withdrawn 2026-11-23) (§5.3).**
  A (recommended): the discount is split across the bill's job-coded lines in proportion to their amounts, the
  rounding remainder on the largest line. Example: a $368.40 discount on a bill with $10,000.00 on cost code 03-100
  and $8,420.00 on 03-200 credits $200.00 and $168.40.
  B: the whole discount credits the first job-coded line.
- **Q6. Paying an inactive vendor's open bills.** **Answered 2026-11-23 (owner 7:48 PM): A (§1.2).**
  A (recommended): inactive only stops new bills and POs; open bills and credits stay payable and refundable.
  Example: Granite Ridge Scaffold is made inactive with one approved bill still open; the pay run still offers it.
  B: inactive also blocks payment until the vendor is reactivated.

## 10. Open items (not decisions)

- **O1 (Area 9):** the subcontract header, lines and change orders (`purchase_order` with `po_type` 'Subcontract' in
  `po_ap_matching_design.md` §3) and `po_line_id` / `receipt_line_id` targets; the FKs in §3.3 and §4.3 wait for them.
- **O2 (Area 4):** lien waivers the contractor gives the owner were not checked (design chat item 8).
- **O3 (Area 14):** routing for 'Bill' and 'Vendor credit' approval, duplicate review, and the write-off threshold.
- **O4 (Area 17):** the 1099 report (`is_1099`, `form_1099_box`, reclass grouping follows the original vendor), the
  "approved without commitment" report, and the vendor-document attention list.
- **O5 (Area 18):** placement of the four PROPOSED codes in §7; §8.3 already lists `subcontract_overlimit_block` and
  the write-off threshold, and an amendment adds `require_lien_waivers_before_paying`, `pay_when_paid_limit_days`
  and the PROPOSED `block_duplicate_bills` and `vendor_compliance_hold`; attachments as the document file.
- **O6 (Area 20):** remittance email after payment and the vendor document request email.
- **O7 (mockups, no schema):** the CODE_CHANGES 43 `vendor_bank_account` with encrypted numbers is superseded by RP1
  (no bank numbers stored); `bank_payee_id` stays.

- **Amendment 2026-11-24 (pointer, Area 14): O3 answered.** Bills keep Q4 (re-approval only on a vendor or total
  change, only with 'Bill' approval ON; Area 14 §7); every other kind voids on any change to amount, discount, lines
  or job. The vendor-credit write-off threshold stays here (NULL = off) and is the only switch for vendor-credit
  write-offs; the Write-off row is not consulted (Area 14 §5.1, Q2). Area 14 adds no duplicate-review approval: the
  duplicate warning with a reason stands. 'Bill' and 'Vendor credit' post in a separate step, which runs the lock
  check; the approval itself does not.

- **Amendment 2026-11-24 (pointer, Area 9, owner 11:25 PM): O1 answered.** A subcontract is a `purchase_order` with
  `po_type` 'Subcontract' (header, lines as the SOV, `purchase_order_change` rows), with its own number series (SC-014)
  apart from material POs; Area 9 §6 builds those tables and `bill_match` (§9), so this area's `po_line_id`,
  `receipt_line_id` and `subcontract_line_id` FKs point there in the same baseline pass. The over-limit check stays this
  area's control `subcontract_overlimit_block` (OFF by default); Area 9 does not make it integrity.

- **Amendment 2026-11-24 (pointer, Area 9, owner 11:55 PM): a bill line matched to a PO line is locked to the PO line.** It takes
  the PO line's job and cost code (which came from the material code) and AP cannot change them on the bill; the bill's
  price-difference, freight and tax rows post to the same job and cost code. A bill line with no PO match is coded here as before
  (a cost code is required with a job). No "bill line may recode" text exists in this area (checked). A wrong code is fixed on the
  PO before billing or by reclass after posting (Area 10; planning reading, owner may correct). Matching is a Company control, OFF by default (Area 9 §9).

- **Amendment 2026-11-25 (pointer, Area 20): O6 answered.** The remittance email and the vendor document request email are sent by Area 20's
  `emails` service and logged in `email_log` (§4); the request has no table of its own (its record is the `email_log` row, document type
  'vendor document request'). Capture-inbox drafts create vendor bills and vendor documents only through this area's services and only after one
  human confirmation (Area 20 §5).

- **Amendment 2026-11-25 (pointer, Area 11): loan payments and asset purchases are bills.** Each loan payment is drafted as a bill to the lender (principal to the loan account, interest to the interest account; Area 11 §6) by `loan_bills.run`; a bill line coded to the fixed-assets account creates or links a `fixed_asset` (§3) with the line amount as its cost; proceeds from a sale or trade-in come back through Area 5's invoice and a vendor credit here (§5).
