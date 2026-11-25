# Step 2.9 schema replan, area 5: invoices, credit memos, statements and customers

Status: **Approved again by the owner 2026-11-24 12:00 AM (planning chat) after the refresh in §9.5, no new rules.**
Earlier: **Approved in full by the owner, 2026-11-22 2:15 AM** (shared_decisions 2026-11-22 "invoicing plan approved"). Later findings are dated Amendment lines. The 2026-11-22 owner decisions are folded in §9; every question is decided, and the amended plan is ready for owner full-plan approval. Drafted 2026-11-20 for the single approved 2.9 pass.

Evidence: `docs/design.md:17` (AQ1/AQ2), `:62` (open items), `:83` (posted edits); `Strata_Teams/schema_replan_2026-11-17.md:26` and `:92`; `shared_decisions.md:76` (payments), `:180` and `:550` (posted edits), `:1174` (customers), `:1510` (reasons), `:1617`, `:1629`, `:1637` (owner 2:10, 2:20 and 2:30 PM); `inbox/to_planning.md:503` (quote handoff). Mockup references below are to the shared run 1 v3 review snapshot under `Strata_Teams/outputs/shared_run1_retest_2026-11-20_v3/current`.

## 0. Summary

| Topic | Confirmed outcome | Baseline |
|---|---|---|
| Customers | Same validation at intake and signing | Company |
| Sales documents | Stable document number, immutable posted history, corrections by reversal and replacement | Company |
| Contract billing | Read signed terms and accepted work. Keep pay applications in area 4 | Company |
| Receivables | Allocations and clearing drive balances and statements | Company |
| Controls | Service authorization, locks, reason and audit history | Company |

## 1. Customers

### 1.1 Current state

`migrations/001_company.sql:810` defines shared contacts with separate customer/vendor identity and exemption fields. `:3884` defines payment terms; `:3893` defines contact sites. `modules/services/contacts.py:148` checks duplicates and masks tax IDs; `:162` creates contacts. Compare `customer-intake.html:25` and the owner checklist at shared decisions :1174.

### 1.2 Decided

Individual requires first and last name; Business requires business name. The shared intake checks email, phone, structured billing address and same-as-billing or separate job site. Site supplies the tax default. Terms default through company settings (Net 30 in the decision). Tax status is Taxable or Exempt with certificate and expiry for Exempt. Assign the customer code at actual creation. Signing a new customer uses the same validation and numbering as intake. Signing for an existing customer links that record. Area 15 hands over lead contacts and signer information; case quotes already link to their customer.

### 1.3 Proposed schema and service rules

Use reusable contact-person records linked to the customer. Each complete customer has one designated primary
contact. Keep billing details on the customer and reusable job sites on the existing site records. Apply §8
completeness checks when creating a sales document or signing an estimate. If signing creates a customer,
save the signer's name, email and phone as the primary contact in the same transaction. An existing customer's
designated primary contact stays in place at signing. Record the signer on the signed revision. Changing the
primary requires an explicit customer edit by an authorized user. Issued versions retain their rendered billing facts.

Share a transaction-scoped validation/create operation between intake and area 6 Mark signed. Follow area 18 authorization before opening the write transaction. Allocate the customer code inside the transaction. If validation, duplicate resolution, job creation or contract creation fails, leave no partial customer, contract or job. Keep exemption data under the area 18 masking and audit rules.

## 2. Invoices, credit memos and versions

### 2.1 Current state

`001_company.sql:590` holds Invoice, Bill and Credit Memo in a shared header with Sales/Purchase side, ledger entry, series, revision number, supersedes link and positive amount checks. `:652` has quantity, unit price, tax reference, cost code and retainage marker, with no line job or frozen tax rate/base/amount. `:1439–1482` and `:1917–1996` protect issued rows and state transitions. Header audit exists at `:2436`, `:2486` and `:2573`; area 18 §1 adds line and dimension audit. See `invoice.html:97–98`, `credit-memo.html:49`, and shared decisions :1213 for invoice-specific Receive payment.

### 2.2 Decided

Drafts are editable. Posting assigns the sales series number in the same transaction as the ledger post. Sales credits are negative in receivables and have their own gapless series at posting. Credits can stand alone or apply to invoices. Posted edits are allowed by default and require a reason, one atomic reversal and replacement under the same document number, and retention of both versions. Refuse edits under the document lock, period/area lock, below paid amount or on a submitted pay app. Preserve the posted journal and its lines. Voids are reversals with a reason and preserved history.

### 2.3 Proposed schema and services

Apply the approved identity, issuing, job and allocation rules in §8.2. Keep the original application and
record any change in clearing linkage with an effective date. Invoice void needs a target-side release
operation. The current source-side helper in `payments.py:311` expects a voided payment or credit memo.

Keep series and number uniqueness on the stable document identity and revision uniqueness within that identity. Each posted version points to its ledger entry and retains issue and due dates, terms, recipient facts, signed totals, lines and dimensions. Record reversal and replacement links. Derive settlement from postings and allocations, and retain sent facts for the issued version. Sales line attribution can inherit the single invoice job.

The invoice and credit services share numbering, issuing, versioning, lock checks and reversal logic. Credit validation and the credit series remain separate. Revalidate authorization, row version, locks and allocations in the write transaction. The ledger service writes journal data. Payments/AR handles application and release under §8.2.

## 3. Billing sources and tax

### 3.1 Confirmed source rules

Area 6 §§5.3, 6.3, 9.3 and 10.2 own signed pricing, terms, contract lines and frozen rates. Area 7 §§1.3 and 4.3 own job classification. Source actions prepare drafts; automation does not post. A job on hold supplies the area 8 warning. For Warranty and No charge (goodwill), do not produce a customer invoice, including automatic deposit drafts, unless a later approved workflow expressly authorizes one. Warranty requires an original job; goodwill uses the company mapping for `service_goodwill`. Neither cost destination determines a customer charge.

| Source | Area 5 draft boundary |
|---|---|
| Fixed price | Bill on completion from signed scope and price under area 6's schedule model. |
| Milestones | Draft from the contract milestone and link the document; preserve the schedule amounts. See area 6 §5.3. |
| Progress | Area 4 owns approved owner pay app, SOV, retainage and deposit draw. Area 5 consumes its billable result, returns the invoice link and preserves source identity. A billed application remains locked. `payapp-detail.html:53–66` shows the retainage/source context. |
| Deposit | Area 6 requests an unposted draft for a billable signed schedule with a deposit. Use the company customer-deposits role. Apply to the first milestone or pro rata to progress bills. See §3.2 for tax and §5.3 for the Area 4 inputs. |
| T&M | Draft eligible posted work at signed rates under §8.3. Warn near the signed pre-tax NTE and block issue above it. |

### 3.2 Proposed source and tax model

Area 6 owns signed quote tax facts. The contract original/customer price is pre-tax. The signed revision retains frozen tax and tax-inclusive signed total separately. Required lines and Accepted optional groups alone contribute to all three and to the original budget. Undecided choices block signing; a signed-total mismatch is refused at upload. Area 5 reads the signed revision and the selection rows without mutating either.

Persist auditable provenance from each quote-derived invoice version and line to its signed revision and accepted/required source lines. Copy tax-rate identity, label and rate, taxable base and frozen tax amount. Carry the signed terms into the draft. Keep staged amounts distinct from the signed totals.

Apply §8.1 when drafting or posting staged bills. Credit collected sales tax to the sales tax payable account found by role. Output VAT is a liability, with input VAT on purchases recorded as an asset and netted against output VAT. A deposit invoice carries no tax by default. Bill frozen tax with work on milestones and progress bills. For a tax code configured to tax the advance, deduct the previously charged tax on the deposit portion applied to each later bill. Track applied principal and previously charged tax separately.

Reserve one active invoice claim per deposit obligation, contract milestone, pay app or retainage release event in the draft transaction. A same-number repost keeps the same claim. A void preserves claim history, and a replacement requires explicit reissue linked to the voided invoice. For each signed line, subtract effective prior billed amounts from the cumulative rounded target. The last bill of that amount takes its remainder. Check cumulative pre-tax and tax separately against the signed quote at completion.
A billed pre-tax or tax mismatch warns and requires a reason to continue. Once the reason is recorded, the mismatch alone does not block an otherwise valid posting.

For independent invoices, apply §8.3 for per-line rounding, frozen issue tax and exemption validation. Keep VAT,
withholding and EIS separate from U.S. sales tax. Tax review still owns uncovered effective dates, standalone
credits, refunds without a linked adjustment, signed-tax correction and mapping frozen tax to actual T&M quantities.

Amendment 2026-11-22 (tax on signed quotes). Decided 2026-11-22 (owner; owner_decisions_2026-11-22 "Planning-session
follow-ups", 12:47 PM; Area 5 Q12), replacing the 2026-11-20 2:10 PM rule that signing freezes tax details and a
tax-included signed total: signed quotes and estimates carry a pre-tax price, and the PDF shows an "Estimated tax"
line; each line keeps its taxable/exempt flag; actual tax is calculated on each invoice at the job-site rate in effect
at invoicing; the item-22 tax override (Accountant+, with a reason) applies to all lines, including signed-quote
lines; a tax-rate change needs no change order. Superseded in §3.2, not deleted: the signed revision's frozen tax and
tax-inclusive signed total; copying tax-rate identity, label, rate, taxable base and frozen tax from the signed
revision; and the separate cumulative tax check against the signed quote with its warn-and-reason path. Now
quote-derived invoice lines carry the signed pre-tax price and each line's taxable/exempt flag; tax is calculated per
line at the job-site rate in effect on the invoice date and frozen on the issued invoice version (frozen issue tax,
§8.3, still applies to every invoice). The cumulative check compares pre-tax only. Deposit and tax-on-the-advance
rules are unchanged: the advance tax is the tax charged on the deposit invoice.

## 4. Statements, allocations, refunds and write-offs

### 4.1 Current state and decided

`001_company.sql:316` defines allocations, `:670` payments; `payments.py:36`, `:255`, `:311`, `:341` provide open item, allocate, release and clearing helpers. AR/AP always track open items. Apply receipts and credits through allocation rows; unapplied amounts remain available. A zero-cash application can apply credits; it must not fabricate a bank receipt. A noncash credit application is ignored for cash-basis payment reporting per shared decisions :88. Date paid determines payment period; bank match or reconciliation supplies date cleared. Area 12 owns the bank match and deposit/transfer model. Customer deposits can be refunded per shared decisions :134.

Mockups: `customers.html:12` opens batch statements from selected customers; `statement.html` supplies the statement view; `customer-refund.html:42` exposes unapplied source funds; `write-off.html:42` shows bad debt; `credit-memo.html:49` exposes unapplied credit. These are workflow inputs, not GL posting specifications.

### 4.2 Proposed read and write boundaries

Use the selected company-local calendar date as the inclusive statement cutoff. Derive balances from posted
activity, applications and reversals effective through that date, including application releases through their
effective dates. Later activity leaves earlier as-of balances intact. Show open invoices first, then
“Unapplied credits and payments,” then “Net balance.” Preserve drill-through and batch access checks.

Retain the exact rendered copy of each sent statement with the customer, cutoff, parameters, recipient,
sender and delivery time. The sent copy supports retrieval independent of later data or template changes.
Apply the company document retention policy. If none is configured, retain the copy and flag its duration for review.

Refunds and write-offs follow the approved source, posting and reversal rules in §8.5. Retain source, amount,
effective date, reason, posting entry and reversal links. Enforce available credit or unpaid balance atomically.

- **Amendment 2026-11-24 (owner 2:55 PM): unapplied customer payments.** Every unapplied customer payment posts Cr
  Unapplied customer payments (the Area 18 §8.6 role, current liability), never Cr Accounts receivable: a receipt with
  nothing applied, or the part of a receipt above what it pays, posts Dr bank or Undeposited funds / Cr Unapplied
  customer payments; applying it later posts Dr Unapplied customer payments / Cr Accounts receivable on the invoice's
  job. AR aging shows unapplied payments as their own line (statements already show "Unapplied credits and payments",
  above). Planning proposal, owner may revise: example, a $5,000.00 receipt with nothing applied posts Dr Undeposited
  funds / Cr 2325 $5,000.00; applying it to INV-0377 posts Dr 2325 / Cr 1110 $5,000.00. Area 1 owns the receipt
  postings (next_step). Open for Area 1: whether customer deposits (§8.5 Q9) use the same account; today's receipt
  posting in the baseline and `payments.py` is checked then. Tests (planning proposal, owner may revise):
  `test_unapplied_receipt_posts_to_unapplied_customer_payments_not_ar`,
  `test_applying_unapplied_payment_posts_dr_unapplied_cr_ar`, `test_ar_aging_shows_unapplied_payments_line`.
- **Amendment 2026-11-24 (owner 7:30 PM and 8:15 PM): customer credit hold from a write-off.** The write-off form has
  a checkbox "Put customer on credit hold", **unchecked by default**. When checked, the same transaction puts the
  customer on credit hold, audit-logged. A credit hold **warns by default**: new invoices and estimates show
  "<customer> is on credit hold" and can still be saved. A Company control, **OFF by default** (Controls page, Admin
  or Master, audit-logged; Area 18 §8.3), makes the hold block new estimates, invoices and sales orders until it is
  released. Planning proposal, owner may revise: fields `contact.is_credit_hold` INTEGER NOT NULL DEFAULT 0 CHECK IN
  (0, 1) and `credit_hold_reason` (OD-31 rule); control name `block_sales_on_credit_hold`. Tests (planning proposal, owner may revise):
  `test_write_off_credit_hold_unchecked_by_default`,
  `test_write_off_with_credit_hold_sets_customer_hold_in_same_transaction`,
  `test_credit_hold_warns_and_saves_when_control_off`,
  `test_credit_hold_blocks_estimates_invoices_and_sales_orders_when_control_on`.

## 5. Controls, cross-area boundaries and landing

Use `ar.view`, `customer.manage`, `invoice.create`, `invoice.send`, `invoice.void`, `credit_memo.create` and Accountant-only `payment.receive` as the existing permission inputs (`001_company.sql:1196–1201`; area 18 §§2.4, 4). Keep send/post, receive and refund authority separate. Area 14 owns approval policies, default OFF, and approval lifecycle. Do not infer new permission codes or approval thresholds. Use the shared Reasons list (area 15 §7.3 and owner decision :1510) with the stored label and reason details for history. Apply area 13 §§1–2 to invoice/credit, payment and Billing actions, including reversal and replacement dates. Keep period integrity always on. Apply row versions to mutable drafts and customer/settings rows and retain immutable posted versions and audit records. Area 18 owns attachment kinds, sensitive field policy and history format.

| Area | Contract with area 5 |
|---|---|
| 4 | Owner pay app calculation, certified figures, billed lock and linkage. Area 4 plan is pending. |
| 6 | Shared customer creation at signing; signed revision, accepted lines, terms, tax and source schedule. |
| 7 / 8 | Job/cost attribution, billing method and destination, hold warning and milestone prompts. |
| 10 | Deferral/unearned revenue and reclass stay area 10; settle line linkage and deposit interaction. See area 10 §§1.3–1.7 and 2. |
| 12 / 1 | Bank activity, reconciliation and deposits in area 12 §§1–5; receipt posting, allocation and release contract with area 1. |
| 13 | Global and area locks, reopen permissions and posting prechecks. |
| 14 | Approval routing, thresholds and reapproval policy. |
| 15 | Customer contacts at signing, lead/job attribution and case linkage. |
| 17 | AR drill-through and lead/job/invoice sources, shared report access and historical cutoffs. No invented account-number filters. |
| 18 | Permission registry, reasons/audit, redaction and attachments. |

### 5.1 Baseline landing and service effects

After approval, plan company-baseline changes for customer/site and terms, sales identity and versions, line
source and tax snapshots, billing links, allocations, refunds and write-offs. Apply §§8.3 and 8.5. The remaining
implementation dependencies are the tax, payment, bank, approval, permission and source contracts in those sections
and the Area 4 inputs in §5.3. Plan foreign keys, customer/date and source indexes, and audit history. Reconcile the
existing locks and number constraints with immutable versions and keep purchase and registered series behavior.

Build list: customer intake service accepts customer type, individual names, job sites, primary contact, payment terms and exemption evidence. The service owns the duplicate check using normalized name, tax ID and email, allocates the required `customer_code`, validates entity-type values against the baseline, and returns tax IDs masked for edit-screen reads. Keep customer persistence out of subscription tables.
Billing sources need a durable source-to-invoice link with idempotent retry. Follow the 2026-11-20 5:15 PM shared decision: one active invoice claim per billing event is reserved with draft creation; retry reuses the active claim, a void preserves claim history, and replacement requires explicit linked reissue.
### 5.2 Tests to write later

- Recording owner approval claims one linked invoice draft and locks the certified pay app. A retry reuses
  that draft. Approval posts no ledger entry. An authorized Issue/Post or Send posts through Area 5.

- Refund each eligible source with its approved offset. Reject over-refunds, allocations still applied and concurrent
  double use. Settling a tax-adjusted credit produces no second tax adjustment.
- Require separate bank correction authority and completed correction for failed cleared payouts. Preserve original
  match/reconciliation history, restore source availability only at reversal effectiveness, and record actual cash returns separately.
- Verify that **GL account** is required and that the picker and posting validation enforce §8.5. Accept an active,
  postable bad debt allowance, direct write-off expense and contra-revenue account. Refuse a blank selection,
  inactive or nonpostable accounts, the AR control account, a bank account and a cash account. Verify that the
  entry debits the selected account, credits invoice AR and saves the choice. Check that partial write-offs
  respect the effective unpaid balance and create no tax entry. Verify that a full linked reversal uses the
  account saved on the original posting and follows the effective date rules. A replacement is a new write-off.
- Enforce all four sensitive permissions independently, reasons and the 10-character “Other” minimum. Verify approvals
  default OFF and route when enabled under Area 14 policy.

- Signing for an existing customer preserves its primary and stores the signer on the signed revision. Only an
  authorized explicit customer edit changes the primary. Sent statement copies follow company retention policy.
  With no policy configured, keep the copy and surface the duration for review.

- A complete customer has exactly one designated primary contact. Additional reusable people and job sites
  remain available. Exercise the 4:58 PM completeness gate at document creation and signing, and verify that
  new-customer signing saves all three signer fields as primary in the same transaction.
- Include postings, applications and reversals effective on the company-local cutoff date, and exclude later
  activity even if it has already been entered when the statement runs. Verify the three sections in order.
  Retrieve the original sent bytes and all delivery metadata after customer data and templates change.

- T&M rejects unapproved, unposted and unsupported inputs and counts a receipt/vendor bill cost once.
  A new rate or revision and a price-only credit leave billed quantity consumed. Verify repost preservation,
  effective-dated void and quantity correction, reasoned draft adjustment, and concurrent claims.
- NTE warns near the ceiling and blocks excess pre-tax issue. Partial billing fits the remaining capacity.
  A posted credit restores only its effective pre-tax reduction against the same ceiling.
- Independent invoice tax sums rounded line amounts and freezes issue facts. Missing or expired exemption
  evidence blocks exempt issue. An unresolved effective-date rule goes to tax review. Linked credits cap
  tax cumulatively, cash settlement of a credit preserves its tax adjustment, and signed-tax conflicts hold issue.

- Issue without sending, issue through Send, and retry delivery. Issue allocates one number and posts once.
  A failed Issue rolls back both. Credit memos use signed AR totals and their own gapless series.
- A same-number repost retains the old version, original receipt and valid allocations. Verify the paid floor,
  customer and job restrictions, one-job line inheritance, submitted pay app restriction and document lock.
- Repost checks the original invoice period. An explicitly dated clearing correction can post in an open
  period while the original application period stays closed. Refuse any new entry that fails its locks and
  verify balances as of dates before and after correction.
- A confirmed paid invoice void either reverses and releases together or rolls back both. The original receipt
  stays posted with the released amount unapplied. Zero-cash credit application creates no bank receipt.

- Intake/signing parity, duplicate and exemption validation, code assigned once, atomic signing rollback.
- Draft/post, series uniqueness and posting rollback, credit sign, line audit and optimistic concurrency.
- Same-number reversal/repost retains old facts; failures leave balances unchanged; all lock, paid-floor and submitted-pay-app cases.
- Signed quote stays immutable after catalog or certificate changes; declined lines excluded, undecided and mismatched totals refused; fixed, milestone, progress, deposit and T&M source replay guarded; Warranty and goodwill generate no draft.
- Deposit tax defaults to zero and the milestone or progress bill charges frozen tax. With tax on the advance,
  later bills deduct the previously charged tax on the applied portion exactly once. Tax resolves to the payable
  role and stays out of revenue. Verify output VAT and the separate input VAT asset for the VAT path.
- Concurrent draft attempts and retries for the same event share one active claim. Same-number repost keeps it.
  Void keeps history, and only explicit linked reissue can replace it. Partial releases use distinct Area 4 IDs.
- Across staged bills, the last bill takes the signed line remainder. Verify cumulative pre-tax and tax separately,
  including deposit offsets and reversed bills. Verify the mismatch warning and required reason, then verify
  that a recorded reason allows an otherwise valid posting to proceed.
- Allocations reject over-application and cross-customer use. Zero-cash credit application has no bank movement.
  As-of statements tie to AR.
- Print and report permissions and job scopes, reason snapshots and redaction, archived/voided document visibility.

**Billing/customer audit regressions (also carry these named cases into the single consolidated test plan when it is assembled):**
- `test_invoice_preview_and_save_share_service_calculation_for_blank_quantity` — preview and save use the same service calculation for blank quantity input.
- `test_invoice_preview_and_save_share_service_calculation_for_half_unit_lines` — preview and save produce the same result for half-unit lines.
- `test_invoice_missing_account_is_refused` — refuse invoice lines without a required account.
- `test_invoice_zero_price_is_refused` and `test_invoice_nonfinite_price_is_refused` — refuse zero and non-finite prices.
- `test_invoice_tax_rounds_per_line` — round tax per line before totaling.
- `test_invoice_invalid_calendar_date_is_rejected` — reject an impossible date such as 02/31.
- `test_invoice_expired_exemption_evidence_does_not_zero_tax` — expired exemption evidence cannot silently produce $0 tax.
- `test_customer_name_validation_runs_on_save` and `test_customer_exemption_expiry_validation_runs_on_save` — enforce both required customer-name and exemption-expiry rules.
- `test_invoice_save_changes_runs_shared_validator` — Save changes uses the same validation path as the other save action.
- `test_invoice_customer_change_revalidates_existing_lines` — changing customer cannot retain incompatible old lines without revalidation.
- `test_sales_invoice_rejects_multiple_jobs_in_v1` — a sales invoice has one job; lines may inherit that job.
- `test_payapp_approval_copy_says_invoice_draft_not_posted` — approval copy states that it creates a linked draft, not a posted invoice.
- `test_posted_invoice_edit_guard_uses_paid_amount_floor` — allow a permitted edit when the replacement total remains at least the amount paid; reject a lower total.
- `test_customer_save_never_touches_subscriptions` — customer saves do not read or write subscription records.
- `test_customer_service_allocates_required_customer_code` — service creation allocates the schema-required code.
- `test_customer_entity_type_matches_schema_values` — service values and persisted entity types match the baseline constraints.
- `test_customer_edit_reads_tax_id_masked_through_service` — edit reads only the service-masked tax ID.
- `test_customer_save_database_error_shows_error_without_navigation` — a database failure shows an error and keeps the user on the form.

Amendment 2026-11-22 (tax on signed quotes; §9.3 Q12): the §5.2 cases that say a milestone or progress bill charges
frozen tax now charge tax calculated at invoicing; add
`test_quote_derived_invoice_tax_uses_job_site_rate_at_invoice_date` and
`test_tax_override_applies_to_signed_quote_lines`.

### 5.3 Explicit handoff to Area 4 (pay apps and retainage)

| Area 4 decision | Area 5 needs |
|---|---|
| Certified pay app billing event (confirmed) | Recording owner approval creates one linked invoice draft, reserves the billing claim and locks the certified pay app atomically. A retry reuses the linked draft. Area 4 supplies the stable pay app ID, certified revision ID and approved SOV line amounts. An authorized user issues or sends through Area 5's normal posting flow. Source: `shared_decisions.md:1668–1673` (owner, 8:30 PM), clarified by Mark's Area 4/5 approval. |
| Pro rata deposit basis | Eligible base and rounding rule, the deposit obligation ID, amount to apply on this bill and the remaining principal balance. Area 5 uses these to apply any tax already charged on the advance. |
| Partial retainage release IDs | A stable ID per authorized release, its retained source lines and released amounts, and the remaining amount available to release. |
| Billed-to-date timing, voids and reissues | Area 4 owns when billed-to-date changes, which certified amounts and deposit or retainage balances are restored, and how the replacement carries the original source identity without counting both invoices. |

## 6. Conflicts

F1. Baseline header uniqueness conflicts with same-number revisions. Stable identity holds number uniqueness (§8.2).
F2. Baseline stores credit magnitudes and forbids zero-value payments. Use signed AR totals and a credit application without a bank receipt (§8.2).
F3. Sales lines may inherit the invoice job. Frozen quote tax still needs snapshots (§3.2).
F4. Baseline status mixes posting, delivery and settlement. First Issue/Post posts the version. Delivery uses that version, and settlement derives from open items.
F5. Area 6's deposit draft applies only to billable signed schedules that call for a deposit. Warranty and goodwill generate no invoice. The 5:15 PM decision settles tax timing, claim lifecycle and rounding. Area 4 still supplies the event and balance inputs in §5.3.
F6. Section 8.5 records the approved per-write-off **GL account** picker, account exclusions and refund offsets.
It also lists the remaining tax and cross-area implementation dependencies.

## 7. Owner questions

1. **Closed (§8.4).** Preserve the existing primary at signing and save signer details on the signed revision.
2. **Closed (§8.2).** Stable identity, immutable versions, signed AR totals, and atomic numbering and posting.
3. **Closed (§8.2).** One job per sales invoice in v1. Lines may inherit it.
4. **Closed (§8.2).** Preserve valid allocations on repost. Payments/AR owns zero-cash applications. Paid invoice voids reverse and release atomically.
5. **Closed.** Owner decisions at 5:00 and 5:15 PM settle schedule precedence, tax timing, source claims and final remainder (§§8–8.1). Area 4 dependencies are in §5.3.
6. **Product rules approved (§8.3).** Source-area identity and duplicate-cost contracts remain prerequisites.
7. **Product rules approved (§8.3).** Confirm tax effective dates for uncovered transactions and tax treatment for
   standalone credits and refunds without a linked adjustment. Confirm the correction workflow for signed tax
   conflicts and any unresolved mapping of frozen signed tax facts to actual T&M quantities.
8. **Policy approved (§8.4).** Review retention duration where the company has no configured policy.
9. **Closed (§8.5).** Refund sources, offsets and bank correction before failed-payout void are approved.
10. **Closed (§8.5).** The per-write-off **GL account** picker and exclusions, partial posting, full reversal,
    permissions and approval defaults are approved.

## 8. Owner corrections, 2026-11-20 at 4:58 PM

These corrections govern the corresponding sections and narrow the questions in §7. The shared decision log
already records 1a and 8a at lines 1642–1648.

- **1a (§1).** New sales documents and estimate signing require customer type, legal name, email, full structured
  billing address (street, city, state, ZIP), and tax status. Exempt customers require the certificate and expiry.
  Save the signer's name, email and phone as the customer's primary contact. Incomplete legacy/imported records
  remain viewable only. Section 8.4 clarifies the contact model and the open existing-customer question.
- **2a (§§2, 5).** Posted invoice and credit memo edits require the posted-edits permission and a reason, reverse
  and repost under the same number, and retain both versions. The company lock defaults OFF and disables these
  edits when enabled. Posted journal entries are always reverse-only. Q10 retains permission placement.
- **5a (§3.1).** Apply the deposit to the first milestone or credit it pro rata on each progress pay app until used
  (“Less deposit applied”). Base deposit and retainage on the NTE when present. Create the deposit invoice as a
  draft after signing when the signed billable schedule has a deposit. The sample service types ship with Due on
  completion and no deposit. The configured service-type schedule takes precedence and the estimate revision
  copies it (owner, 5:00 PM).
- **6a (§3).** Before signing, permit per-row T&M rate overrides under “Estimates may change their rates,” ON by
  default. Show “Changed from <source>” and Reset, require a reason and log the change. At signing freeze the rates.
  Changing signed terms, including raising the NTE, requires a newly signed and uploaded revision. Section 8.3
  settles Q6. Source owners still need to define stable IDs, eligible posted quantities and duplicate-cost rules.
- **7a (§3.2).** Use tax detail frozen on the signed revision in quote-derived invoices. The customer signs the
  tax-inclusive total. Q7 remains open for tax mechanics outside that confirmed carry-forward.
- **8a (§4.2).** Statements show open invoices and their total, then a separate “Unapplied credits and payments”
  section, then “Net balance.” Keep credits out of invoice rows. The Customers list continues to show the net
  balance. Section 8.4 records the cutoff and sent-copy rules.
- **10a (§§4–5).** Write-off, refund and credit reasons come from Settings › Lists › Reasons. “Other” requires text.
  Company › Approvers configures write-off and refund approvals, OFF by default. The Service goodwill account role
  remains separate from warranty and from the per-write-off **GL account** selection. See §8.5 for posting and authority.

**Q5 default precedence closed (owner, 5:00 PM).** Shared decisions :1651 and planning inbox :595 confirm the
sample defaults and configured schedule precedence.

Amendment 2026-11-22 (tax on signed quotes; §9.3 Q12): correction 7a above is superseded. Quote-derived invoices no
longer use tax frozen on the signed revision; the customer signs a pre-tax price.

### 8.1 Q5 billing answers (owner, 5:15 PM)

Checked against: shared_decisions 2026-11-20 5:15 PM

These answers settle the Q5 choices in §§3 and 7.

1. Credit collected sales tax to the sales tax payable account resolved by role. Collected tax is a liability.
   Output VAT follows the same principle, with input VAT on purchases recorded as an asset and netted against
   output VAT.
2. By default the deposit invoice carries no tax. As work is billed, each milestone or progress bill uses the
   frozen signed tax detail. A tax code may specify “tax on the advance” where required. Later bills deduct
   the tax already charged on the applied advance so the signed tax total ties out. Each company confirms its
   treatment with its tax adviser.
3. Reserve one active invoice claim per billing event in the draft's transaction. Key the claim to the deposit
   obligation, contract milestone, stable pay app, or retainage release event. Same-number repost keeps the
   claim on the invoice identity. A void retains claim history. An explicit reissue linked to the voided invoice
   is required for a replacement.
4. For each signed line, subtract the amount already billed from the cumulative rounded target. The last bill
   of each signed amount absorbs its remainder. At completion, reconcile cumulative pre-tax and tax amounts
   separately to the signed quote, accounting for deposit applications and reversals.
   A billed pre-tax or tax mismatch warns and requires a reason to continue. Once the reason is recorded, the mismatch alone does not block an otherwise valid posting.

Area 4 dependencies are listed in §5.3.

Amendment 2026-11-22 (tax on signed quotes; §9.3 Q12): in §8.1 above, milestone and progress bills charge tax
calculated at invoicing, not frozen signed tax detail.

### 8.2 Owner-approved Q2–Q4 (2026-11-20)

- **Q2.** One stable document identity and permanent number, immutable posted versions linked to their
  ledger entries, and signed AR totals. An authorized user may issue without sending. First Issue/Post
  assigns the number and posts atomically. Send may initiate posting, and retries deliver the issued
  version. Share numbering, versioning, lock checks and reversal logic between invoices and credit memos.
  Keep credit-specific validation and the separate gapless credit series.
- **Q3.** One job per sales invoice in v1. Lines may inherit the invoice job. Keep the customer and job
  restrictions once payment is applied, the paid floor, and the submitted pay app edit block.
- **Q4.** Preserve valid allocations and original payment and application history on same-number repost.
  Payments/AR owns zero-cash credit applications without creating a bank receipt. A linked clearing correction
  may use an explicitly chosen open effective date without reopening the original application period. The
  original invoice period must pass the repost check and every new entry must pass its applicable locks.
  Preserve earlier as-of balances. A confirmed paid invoice void atomically reverses the invoice and
  releases its applications. The original receipt remains posted and becomes unapplied. Refunds stay separate.

The owner confirmed the pay app draft and Issue/Post boundary in §5.3. Billed-to-date remains an Area 4 decision.

Stop for Mark's review. Resolve the remaining questions before treating the proposals as approved.

### 8.3 Owner-approved Q6–Q7 (2026-11-20)

**Q6 — T&M billing**

- Use posted payroll imports for v1 labor. Nonlabor can use approved, posted stock issues and approved, posted
  billable job cost lines for direct materials, equipment, subcontract and other costs covered by signed terms.
  A receipt and vendor bill representing one cost supply one billable source. Exclude a source type until its
  owning area defines a stable transaction ID and the applicable duplicate-cost rule.
- Track remaining billable quantity by source transaction. Retain the signed rate line as pricing evidence.
  Rate changes and newly signed revisions leave previously billed quantities consumed. Same-number repost
  preserves the claim. Void restores eligible quantity when the reversal takes effect.
- Draft adjustments require a reason, source link and compliance with signed terms. Correct posted quantities
  through a linked correction or credit. Restore only quantities explicitly reversed by an effective correction.
  A price-only credit leaves billed quantity unchanged.
- Warn near the signed NTE and block issue above it. Compare proposed charges plus cumulative effective pre-tax
  charges to the signed pre-tax ceiling. A posted credit restores capacity only by its pre-tax reduction against
  that ceiling. Offer partial billing within capacity. Raising the ceiling requires a newly signed and uploaded revision.

**Q7 — Invoice tax**

- On independent invoices, round tax per line to cents and sum those amounts as the v1 default. Freeze the basis,
  rate and amount at issue. Validate exemption on the applicable tax effective date. Flag transactions without an
  approved date rule for tax review. Missing or expired evidence blocks exempt issue until corrected or the user
  explicitly changes the tax treatment.
- Linked credits use the original invoice line's frozen tax facts and cap cumulative tax credited at the original
  tax. A cash refund settling an existing credit consumes it without a second tax adjustment. Standalone credits
  and refunds without a linked tax adjustment require separate tax review.
- Preserve frozen signed tax for quote-derived invoices. Surface conflicts with current tax facts before issue and
  hold for review. A change to signed amounts requires a newly signed revision or an approved correction workflow.
  Keep Q5 tax timing and final-cent reconciliation.

**Schema and cross-area handoff.** T&M claims link to the stable source transaction independently of signed
revision and rate line. Retain quantity, unit, signed pricing evidence, correction links and effective dates.
Track effective pre-tax charges and credit reductions against the signed ceiling. Areas 7/9 and the owning
purchasing and costing areas supply source IDs, posted/approved billable state, quantities and receipt-to-bill
duplicate-cost identity. Area 19 supplies posted payroll source IDs and quantities. Area 6 supplies frozen rate,
revision and ceiling identity. Tax versions retain line basis, rate, amount and applicable effective date.
Linked credits point to original issued lines and refunds settling them point to the credit to preserve one tax
adjustment. Area 4 retains the existing §5.3 handoff.

Amendment 2026-11-22 (tax on signed quotes; §9.3 Q12): the §8.3 rule to preserve frozen signed tax for quote-derived
invoices is superseded; frozen issue tax on each issued invoice version stays.

### 8.4 Owner-approved Q1 and Q8 (2026-11-20)

- **Q1.** Reusable contact people with one designated primary per complete customer. Customer billing details
  and reusable job sites stay on their existing records. Apply the 4:58 PM completeness rules at new sales
  document creation and estimate signing. For a customer created at signing, the signer's name, email and phone
  become the primary contact. Existing customers keep their designated primary. Save the signer on the signed
  revision. Only an authorized, explicit customer edit changes the primary.
- **Q8.** Use an inclusive company-local cutoff date for posted activity, applications and reversals. Later
  activity leaves historical balances intact. Use the three-section layout in §4.2. Keep exact sent copies and
  customer, cutoff, parameters, recipient, sender and delivery time. Apply company document retention policy.
  If absent, retain the copy and flag its duration for review.

### 8.5 Owner-approved Q9–Q10 (2026-11-20)

- **Q9.** Allow refunds from available customer deposits, unapplied receipts and unapplied issued credit memos.
  Link the source and check and consume its available balance in the posting transaction. Applied amounts require
  authorized release or correction first. Debit Customer Deposits liability for deposits or AR against the specific
  open credit for receipts and credit memos. Credit the payout bank account. Settling an already tax-adjusted
  credit memo consumes the credit without another tax adjustment.
- **Q9 reversal.** For a failed payout that was cleared or reconciled, require an authorized Area 12 bank correction
  before void. Preserve match and reconciliation history. Reverse on an allowed effective date and restore source
  availability as of that date. Cash paid and later returned is a separate linked bank event.
- **Q10 (owner clarification, 2026-11-21 at 1:35 AM).** The Write off form requires an explicit **GL account**
  selection for each write-off. Any active, postable account is eligible except the AR control account and bank
  or cash accounts. Eligible examples include a bad debt allowance, direct write-off expense and contra-revenue
  account. Allow partial write-offs up to the effective unpaid invoice balance. Debit the selected GL account
  and credit AR against the invoice. Record the invoice, amount, selected account, effective date, reason and
  posting entry. Reverse each write-off in full on an allowed date through a linked entry that uses the account
  saved on the original posting. For a different amount, post a new write-off against the remaining balance.
  The write-off creates no tax adjustment.
- **Authority.** Require distinct sensitive permissions for refund posting, refund reversal, write-off posting
  and write-off reversal. Bank correction authority is separate. Use Settings › Lists › Reasons and require at
  least 10 characters for “Other.” Optional refund and write-off approvals in Company › Approvers default OFF.

Remaining dependencies by owner:

- **Tax review / Area 5:** uncovered effective dates, standalone credits and refunds without a linked tax adjustment,
  any tax recovery on write-offs, and signed-tax correction and T&M tax mapping.
- **Area 1 / Payments and AR:** source balances, release/correction and allocation contracts for refund posting.
- **Area 12 / Banking:** authorized correction and reconciliation history, plus linked actual bank returns.
- **Area 18 / Security:** name and place the four sensitive permissions. Each write-off uses the GL account
  selected under Q10.
- **Area 14 / Approvers:** refund and write-off routing and reversal approval policy.
- **Area 4 / Pay apps:** retain §5.3. **Areas 7/9, purchasing/costing, 19 and 6:** retain the T&M source and signed terms handoff in §8.3.

Amendment 2026-11-22 (owner_decisions_2026-11-22 "Planning-session questions, round 2", 1:56 PM): the tax review
dependencies above and §7 items 7 and 8 are decided in §9.3 (Q7a, Q7b, Q7e and Q8; Q7c and Q7d closed by Q12). Sales
tax is accrual-only.

## 9. Owner decisions, 2026-11-22 (dated amendments)

Source: `Strata_Teams\docs\owner_decisions_2026-11-22.md` (items 7 and 22; OD-07, OD-09, OD-10, OD-11, OD-15 and
OD-18). The plan was approved in full at 2:15 AM (shared_decisions 2026-11-22 "invoicing plan approved"). As that
decision requires, later findings are recorded here as dated Amendment lines; none replaces approved text without a
flag. Every §9.3 question is decided (2026-11-22), so the amended plan is ready for owner full-plan approval.

### 9.1 Decided 2026-11-22 (owner)

- **Amendment 2026-11-22: posted invoice edit (OD-18, G2; amends §2.2 and 8 2a without changing them).** A posted
  invoice opens view-only. It becomes editable only after the user presses **Edit**, and only then is **Add a line**
  available. Edit shows a warning that saving will reverse the previous invoice and repost the new one. Save adds
  the line and persists it through the approved same-number reversal and repost. Tax is recalculated and frozen
  again on the new version, and the one-job refusal still applies. Edit is unavailable while the Company
  `lock_documents_after_posting` control is ON or the period is locked. The approved paid floor, area lock and
  submitted-pay-app refusals still apply. Schema: none new; the version history, reason and reversal links of §2.3
  and 8.2 Q2 carry it. Tests: `test_posted_invoice_opens_view_only_until_edit`,
  `test_posted_invoice_edit_add_line_reverses_and_reposts_same_number`,
  `test_posted_invoice_edit_recalculates_and_refreezes_tax`,
  `test_posted_invoice_edit_unavailable_when_document_lock_or_period_locked`.
- **Amendment 2026-11-22: one job per invoice (OD-09, G2; narrows §8.2 Q3).** A saved invoice keeps its job.
  Adding a line for another job is refused with "One job per invoice — start a new invoice". Fixture acceptance
  for this guard is limited to RI0001-002. Test: `test_saved_invoice_refuses_line_for_another_job` (extends
  `test_sales_invoice_rejects_multiple_jobs_in_v1`). Job changes follow §9.3 Q11 (decided).
- **Amendment 2026-11-22: active tax code override (item 22; TAXSET-04 invoice tax authorization branch).**
  Accountant, Admin or Master, or a user whose job title grants it, can override the rate on one invoice with a
  reason. The override is logged and frozen with that invoice version. The tax code and its rate history are
  unchanged. Schema: on the invoice version, `tax_override_rate` (REAL percent, NULL when not overridden),
  `tax_override_reason` (TEXT, nonblank when the rate is set), `tax_override_by` and `tax_override_at` (all set or
  all NULL; CHECK). Each affected line keeps its tax-code identity and freezes the overridden rate and amount.
  Permission: new code `invoice.tax_override` in the Accountant cap, held by Admin and the Master, grantable by job
  title and template (Area 18 §8.2, which amends §2.4); not in `AGENT_ALLOWED`. No Company control. Tests:
  `test_invoice_tax_override_requires_permission_and_reason`, `test_invoice_tax_override_frozen_with_version`,
  `test_invoice_tax_override_leaves_tax_code_unchanged`. Under §9.3 Q12 (decided) the override and the OD-18
  recalculation apply to all lines, including signed-quote lines.
- **Amendment 2026-11-22: document numbering (item 7; DOCNUM-02).** Company settings shows the journal entry
  sequence read-only (for example "Next: JE-000432" (Amended 2026-11-24: journal entry example renumbered to the L4 format; no rule or amount changed.)); `ledger.py` keeps sole ownership of journal numbers. Add the
  credit memo series in the format `CM-###` (the separate gapless credit series of §8.2 Q2) and keep the existing
  Settings wording. Schema: the credit memo series row and its `CM-` prefix in the shared sequence pattern; no new
  table. Test: `test_credit_memo_series_assigns_cm_numbers_gapless`,
  `test_company_settings_shows_next_journal_number_read_only`.
- **Amendment 2026-11-22: customer intake and refund reason (OD-07; ARREF-04).** A valid preselected default
  (Net 30) counts as a complete terms section at customer intake. Refund reasons live in Settings › Lists › Reasons
  under the refund category; "Other" requires a free-text reason (the approved §8.5 reasons rule already sets 10 characters for "Other"). Test:
  `test_customer_intake_default_terms_count_as_complete`, `test_refund_reason_other_requires_text`.
- **Amendment 2026-11-22: refund customer change (OD-10).** Clearing the customer on a refund blanks the amount and
  clears the applied lines. Test:
  `test_refund_clearing_customer_blanks_amount_and_applied_lines`.
- **Amendment 2026-11-22: write-off amount (OD-15, H, S7; option B; consistent with §8.5 Q10).** Picking or
  re-picking an invoice fills the amount with that invoice's open balance; the user can edit it down. A fixed
  $7,700.00 is not an approved value. Test: `test_write_off_amount_defaults_to_selected_invoice_open_balance`.
- **Amendment 2026-11-22: unapplied payment (OD-11).** A cleared payment with no matched documents shows a visible
  "Unapplied" badge. Its drawer says "No invoices or bills applied" and has an **Apply** button, and the payment
  also lists in the open-payments module. Unapplied status is derived from allocations; no stored flag. Test:
  `test_cleared_payment_without_allocations_shows_unapplied_and_lists_in_open_payments`.

### 9.2 Handoffs

- **Area 18:** place `invoice.tax_override`; Company settings shows the journal sequence read-only.
- **Areas 1 and 12:** the OD-11 badge reads Area 1 allocations; the open-payments module is Area 12's (Q16 A limits).
- **Area 4:** `payapp.adjust` on the linked pay app draft (Area 4 §5 amendment); certified amounts follow Area 4 Q7.
- **Area 3:** the OD-11 wording covers bills ("No invoices or bills applied") for AP payments.

### 9.3 Questions (recommended option first; decided ones marked)

Questions 7 and 8 restate §7 items 7 and 8. All are decided: Q11 and Q12 at 12:47 PM (Q7c and Q7d close with Q12), and Q7a, Q7b, Q7e and Q8 in round 2 (1:56 PM). Nothing in this plan is open.

- **Q7a. Tax rate for a date with no rate on file. Decided 2026-11-22 (owner; owner_decisions_2026-11-22
  "Planning-session questions, round 2", 1:56 PM): option A.** Issue is refused with "No tax rate is set for this
  date; add one in Sales tax setup". Example: an invoice dated 2026-01-05 when the code's first rate starts
  2026-02-01. Test: `test_invoice_issue_refused_when_no_tax_rate_for_date`.
- **Q7b. Standalone credit or refund. Decided 2026-11-22 (owner; owner_decisions_2026-11-22 "Planning-session
  questions, round 2", 1:56 PM): option A.** A standalone credit or refund makes no tax adjustment by default; linking
  it to an original invoice line reverses that line's tax (capped as §8.3 linked credits are). Tests:
  `test_standalone_credit_or_refund_makes_no_tax_adjustment`,
  `test_credit_linked_to_invoice_line_reverses_that_line_tax`.
- **Q7c. Signed-tax correction. Closed 2026-11-22 by Q12:** signed quotes carry a pre-tax price, so there is
  no signed tax to correct; a job-site rate change is handled on the invoice (rate at invoicing, or the
  item-22 override).
- **Q7d. T&M tax on actual quantities. Closed 2026-11-22 by Q12:** tax is calculated on each invoice at the
  job-site rate in effect at invoicing, on the actual taxable amount.
- **Q7e. Sales tax basis and write-offs. Decided 2026-11-22 (owner; owner_decisions_2026-11-22 "Planning-session
  questions, round 2", 1:56 PM):** sales tax is reported on an accrual basis only, owed on the invoice date; there is
  no Cash/Accrual setting. A write-off posts its full amount to the write-off account selected under §8.5 Q10 (bad
  debt), with no automatic tax split (§8.5 Q10 stands). A report lists the sales tax inside written-off invoices so
  the filer can claim the bad-debt deduction; Area 17 owns it (Area 17 §4 amendment). Schema: no tax-basis setting;
  the report reads the write-off records and the invoice versions' frozen tax. Tests:
  `test_sales_tax_owed_on_invoice_date_accrual_only`, `test_write_off_posts_full_amount_without_tax_split`.
- **Q8. Sent statement retention with no company policy. Decided 2026-11-22 (owner; owner_decisions_2026-11-22
  "Planning-session questions, round 2", 1:56 PM): option A.** Keep sent statements 7 years, then flag them for
  review; never auto-delete. Schema: the sent-statement copy stores `retention_review_on` (sent date plus 7 years)
  when the company has no policy. Test: `test_sent_statement_kept_seven_years_then_flagged_never_deleted`.
- **Q11. Changing the job (OD-09 vs §8.2 Q3). Decided 2026-11-22 (owner; owner_decisions_2026-11-22 "Planning-session follow-ups", 12:47 PM):** an unpaid invoice can
  move to another job through Edit (same-number reverse and repost), with all lines moving together. Once a
  payment is applied, a later job change is made with a reclass entry (Area 10 §2), not an invoice edit.
  OD-09 still refuses mixing jobs on one invoice. Tests: `test_unpaid_invoice_job_change_moves_all_lines_via_repost`,
  `test_paid_invoice_job_change_refused_and_offers_reclass`.
- **Q12. Tax on signed quotes. Decided 2026-11-22 (owner; owner_decisions_2026-11-22 "Planning-session follow-ups", 12:47 PM); a change to approved text:** signed quotes
  and estimates carry a pre-tax price, and the PDF shows an "Estimated tax" line. Each line keeps its
  taxable/exempt flag. Actual tax is calculated on each invoice at the job-site rate in effect at invoicing.
  The item-22 override (Accountant+, with a reason) applies to all lines, including signed-quote lines; no
  change order is needed for a tax-rate change. This replaces the 2026-11-20 rule that signing freezes tax
  details and a tax-included signed total; dated amendments mark each superseded statement in §§3.2, 5.2,
  8 (7a), 8.1 and 8.3 here and in Areas 6, 7, 8 and 15 and the next_step service-quote reconciliation.
  Dependencies flagged: the signed amount (pre-tax), lead expected value (Area 15), WIP over/under billing
  (Area 7) and the Hughes regression figures (Area 6 §9.2). The original budget comes from cost and is
  unaffected.

### 9.4 Owner decisions 2026-11-22 evening (dated amendments)

Source: `Strata_Teams\docs\owner_decisions_2026-11-22.md` OD-28, OD-69 and OD-70; OD-59 from the inbox 2026-11-22 evening
message and `docs\planning_owner_features_2026-11-22.md` (its text is not in owner_decisions); inbox 2026-11-22 evening
"two new owner features + rules" and 10:55 PM "correction to the reclass rule". Nothing above is rewritten.

- **Amendment 2026-11-22: tax rates by effective date (OD-59).** A tax rate carries an effective-from date and the
  invoice date picks the rate. Schema: the baseline `tax_rate` (`migrations/001_company.sql:132`: name, rate,
  account only) gains a rate history, `tax_rate_version` (`tax_rate_id` FK, `rate` REAL percent, `effective_from`
  TEXT date NOT NULL, `created_by`, `created_at`; UNIQUE (`tax_rate_id`, `effective_from`); insert-only, a later row
  replaces an earlier one from its date). The invoice version freezes the rate it used (the §3.2 frozen tax), so a
  later rate row never changes a posted invoice. (The owner's rule is the first sentence; the table shape is planning's proposal.) This is the rule Q7a relies on: no row on or before the invoice date
  refuses issue. Area 17's written-off tax report reads the frozen tax. Tests:
  `test_invoice_date_picks_tax_rate_in_effect`, `test_new_tax_rate_row_leaves_posted_invoice_tax_unchanged`.
- **Amendment 2026-11-22: Reclass job on a posted invoice (OD-28, OD-69, OD-70; amends Q11's "a later job change is
  made with a reclass entry").** The invoice's ... menu offers Reclass job (new job and a reason of at least 10
  characters). It moves the whole invoice (revenue, receivable and retainage) in one RECLASS entry (Area 10 §11.2),
  and undoes every payment application on it: each payment becomes unapplied on its own date and deposit (OD-11
  badge; OD-56 unapplied list on Receive payment) and the invoice shows its full open balance on the new job.
  OD-28's "leaves the invoice and its payment untouched" is withdrawn for the payment part (owner 10:55 PM, OD-69).
  Invoice number, version and posted lines are unchanged; the invoice's job reads the latest effective reclass. The
  undo and re-apply postings (Dr AR / Cr Unapplied customer payments, and back) are Area 1's; the role is Area 18
  §8.6. The receivable move depends on Area 10 Q18 (open; it conflicts with Area 10 §2.4 until answered), and Q19 (open)
  decides the Reclassify page case. Tests:
  `test_reclass_job_unapplies_payments_and_shows_full_open_balance_on_new_job`,
  `test_reclassed_invoice_keeps_number_and_version`.
- **Handoff to Area 1:** application undo by Reclass job writes an allocation release (the baseline release fields,
  `payment_allocation.released_*`) with reason "Reclass job" and posts the OD-70 entry in the same transaction;
  re-applying is a new allocation that reverses it. **Flagged:** baseline RP11 allows a release only after the
  payment's entry is voided; Area 1 amends RP11 for the "Reclass job" release while the payment stays posted.

### 9.5 Refresh 2026-11-24 (owner approval 12:00 AM; pointers only, no new rules)

- **Amendment 2026-11-24 (pointer): Area 10 Q18 and Q19 decided** (2026-11-23): on a job reclass of an invoice both
  the AR and the revenue lines take the new job, and the Reclassify page follows OD-69/OD-70 (Area 10 §11.5).
- **Amendment 2026-11-24 (pointer): one date rule** for reclasses and payment voids (Area 10 Q21 A with OD-71,
  §11.7).
- **Amendment 2026-11-24 (pointer): invoice job moves follow manual-entry approval** when that control is on (Area
  10 Q36 A, §11.9).
- **Amendment 2026-11-24 (pointer): Billed to date is actual posted billing only**, never the WIP report (owner
  9:28 PM; Area 10 §11.7).
- **Amendment 2026-11-24 (pointer): the linked pay app's certified SOV lines are mapped to the new contract** on
  Reclass job (Area 4, owner 11:55 PM amendment).
