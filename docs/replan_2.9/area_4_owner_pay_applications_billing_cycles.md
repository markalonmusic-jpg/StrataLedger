# Area 4 — Customer pay applications and billing cycles

Phase 2.9 schema replan draft, 2026-11-21. Owner review pending. “Customer pay app” is the UI label.

## 0. Summary

One numbered pay app per contract billing cycle, with revision history, certified SOV amounts and a stable invoice claim. Certification locks the pay app and creates one linked draft. Area 5 issues or sends and posts it. Billed-to-date follows effective postings and reversals. The owner approved the deposit and retainage rules in §3.

## 1. Current baseline and sources

- `migrations/001_company.sql:948` defines `progress_billing_application` with contract and invoice links, application number, period end, aggregate work, stored materials, retainage and due amounts, and Draft/Submitted/Approved/Paid statuses. It has no normalized revision, certified SOV line, deposit allocation or release history. The invoice and contract indexes are at :5878–5879. Existing pay app permission seeds are :1230–1231.
- Area 6 §§5.3 and 10.2 own the signed schedule, contract lines and cost-code links. Area 5 §5.3 owns invoice issue and calls out the required Area 4 inputs. Area 13 §§1–2 define Billing and invoice area locks.
- Mockup snapshot `Strata_Teams/outputs/shared_run1_retest_2026-11-20_v3/current`: `billing-cycle.html:3–6` redirects to the Pay applications list. The job's Pay apps tab is the job-level workspace. `payapp-detail.html:53–68` shows work, stored materials, retainage and change-order context. Treat mockup states as illustrations where later decisions supersede them.
- `shared_decisions.md:576–591` covers the job workspace, sub cut-off, one cycle per AP bill and holds; :691–693 covers re-hold and sub retainage; :1025–1028 covers locked bills. :561 confirms pro rata deposit credit while retaining the full SOV. :1655–1660 confirms claim and rounding rules. :1663–1673 covers release on the pay app, cost-based amounts, and optional internal review. :1756–1761 confirms draft-only certification. The later clarification supersedes the explicit “and posts” wording at :1665. The 8:20 PM rule supersedes the older separate-document-only retainage rule.

## 2. Cycle, revisions and certification

### 2.1 Confirmed workflow

The cross-job list is Pay applications. The job tab holds the monthly workspace and editable sub cut-off. Each approved eligible AP bill can belong to one customer cycle, without splitting. Include a source only when its accounting effective date is on or before the inclusive cut-off; allow the PM to move an eligible bill to the next cycle. Keep cycle membership distinct from payment holds. A locked pay app blocks bill edit and send-back until the authorized unlock workflow permits correction. Certified history stays immutable. A cut-off determines what the calculation can include; certification freezes what it actually included.

Propose a stable application ID and a number unique per contract. Each revision snapshots the period, cut-off, signed contract version, SOV lines, and each source entry and amount used in its calculation. Include approved change-order SOV changes effective for that revision. Show cost-to-date divided by budget as the suggested percent complete, with posted bills, stock pull tickets and labor whose accounting effective dates are on or before the cut-off, and expandable source rows. If budget is missing or zero, show the posted costs and explain that the system cannot suggest a percent complete; an authorized user must enter an amount or percentage with a reason before submission. Store calculated and adjusted amounts separately. Adjustments and prospective retainage rate changes require reasons. PM enters stored materials. When previously billed stored materials are installed, link the transfer to the original stored-material line, reduce its stored balance and increase installed work by the same amount; the transfer adds zero to cumulative earned value. Show any new billable work separately. Record the entries and amounts actually used on each revision. A late posting or correction that changes a sent application goes through a new revision. Certified revisions remain immutable; later corrections use the applicable correction workflow.

Create a draft, or submit it for internal review when the optional control is on. Keep the control OFF by default. Printing, downloading or emailing the issued preview marks it Sent under the owner decision. Return creates a new revision with prior sent copies preserved. Optional internal review and customer approval are distinct actions.

### 2.2 Area 5 contract

The billing event is recording customer approval of the identified sent revision with certification actor/date and approved SOV amounts. In one transaction, lock that revision, reserve the Area 5 billing claim keyed by stable pay app ID, and create one linked invoice draft. Preserve the certified revision ID on the claim. An exact retry returns the linked draft or the canceled outcome under §4. A conflicting revision or certification attempt fails without another draft. Certification writes zero ledger entries. The authorized Area 5 Issue/Post or Send action assigns the invoice number and posts.

Pass certified SOV and signed source-line IDs, gross current work and stored material deltas, current retainage withheld, releases by source, deposit principal applied by source, and pre-tax invoice components to Area 5. Supply effective dates and signed tax references. Area 5 computes invoice tax using its frozen tax, advance and last-cent rules. Keep certified amounts separate from net AR due and posted invoice state.

## 3. Deposit and retainage

### 3.1 Pro rata deposit (Q2 approved 2026-11-21)

Use cumulative eligible pre-tax progress before retainage, releases and deposit deductions divided by the
signed eligible SOV base for the deposit obligation. Apply that proportion to funded deposit principal.
An issued deposit invoice alone does not fund it. Exclude tax and retainage releases. Subtract effective
prior applications from the cumulative rounded target and cap this application at both remaining funded
principal and the eligible amount on the current bill. Apply the rounding remainder on the final eligible
bill and show any principal that cannot be applied as unapplied. A zero eligible base has no calculable share.

A signed change affects the basis only if it expressly changes the obligation or eligible scope. Use the new
basis prospectively and preserve earlier billed records. Flag for review any change that would require
undoing an effective prior application.

Expose obligation ID, eligible base, cumulative target, this bill's principal and remaining principal. Reserve draft application amounts against concurrent use. Proposed remaining balance is funded principal less effective posted applications and refunds, with pending reservations shown separately. A void restores availability only on its effective reversal. Area 5 deducts previously charged advance tax only for the applied principal under the signed treatment.

### 3.2 Retainage releases (Q3 approved 2026-11-21)

Allow part or all of retainage already posted and still held to be released as a distinct pay app line.
Current-cycle withholding becomes available only after posting. The user selects original held sources and
the amount from each. Record a stable release ID, source splits and reason. Preserve IDs across retries and
reissue and claim them with the enclosing invoice. Effective posted withholding less effective posted
releases defines held balance, with pending reservations tracked separately. Validate available held amounts
atomically. A prospective rate change applies to newly earned work starting with its first eligible pay app.
Preserve prior withholding.

## 4. Billed-to-date and draft cancellation (owner-approved 2026-11-21)

| Event | Claim and certification | Effective billed-to-date and ledger |
|---|---|---|
| Approve or retry | Claim once, lock certified revision, link or reuse draft | Draft reserves amounts. No billed increment and no ledger entry. |
| Issue/Post or Send | Keep same claim and certified source | On successful posting, add the invoice's certified progress components once at posting effective date. Consume deposit and retainage reservations as effective amounts. |
| Cancel unposted draft | Record the reason and canceled outcome in claim history, end the active claim, release reservations and keep certification locked. Approval retry returns the canceled outcome. An authorized user can explicitly claim a replacement draft for the same certified event, subject to one active claim. | Zero ledger effect and zero billed-to-date change. |
| Void posted invoice | Preserve certification, invoice and claim history. Release or restore balances on the effective reversal date. | Area 5 posts a linked reversing entry in the same transaction. Subtract original posted components effective on that date. Earlier as-of totals remain intact. |
| Explicit reissue | Link replacement to voided invoice, reclaim same certified event and release IDs. Enforce one active claim. | Draft adds zero. Replacement posting adds its components at its own effective date. No overlap with reversed amounts. |

Derive billed-to-date by SOV line from effective invoice posting and reversal events. Keep gross progress (including stored material movements under Q4), withheld and released retainage, deposit applied, pre-tax net billed and tax separately. A release changes retainage and due amounts without billing the underlying work twice. Payment affects collection and holds, while billing totals follow invoices. A permitted same-number repost reverses the previous effect and adds the replacement in one transaction under the same identity. Certified source amounts stay frozen. Confirm permissible invoice-only changes in Q5.

Apply the confirmed re-hold rule on return, posted void or payment reversal for released bills still outside pay runs and unpaid. Log and notify the PM. Keep actual cash receipts, AP holds, waivers and pay run behavior in their owning services.

## 5. Proposed company schema and service boundaries

- Record deposit obligation funding separately from invoice issue, with signed eligible basis versions and
  effective dates. Store application source, principal and reservation separately from advance tax references.
  Link each retainage split to the original posted withholding, and retain rate-change effective scope.

- Preserve each claim attempt and outcome under the same certified billing event. In the Area 5 claim
  transaction, record cancellation with its reason and release draft reservations while retaining the certified
  revision and lock. An explicit replacement gets a new linked attempt. Enforce one active claim per event.
- Link effective billed component changes to the posted Area 5 invoice version and ledger entry. A void records
  the original components with opposite sign and links the reversing entry and its effective date. A replacement
  contributes only on posting. Certification, draft creation and cancellation generate no posted effects.

- Extend or replace the baseline header with stable contract/application identity and revision pointer. Add revision, SOV line, source allocation, cycle membership, event history and retainage release header/splits. Store each revision's source entry IDs, accounting effective dates, and included amounts. Record stored-material transfers against the original stored-material line with equal stored-balance decrease and installed-work increase, and zero cumulative earned-value delta; keep new billable work as a separate source. Amounts are integer cents. Add unique contract/application number and revision sequence, one active cycle per AP bill, and stable release/source keys. Store cutoff and effective dates separately from actor timestamps. Guard concurrent draft edits with row versions. Audit mutable business records. Freeze certified facts and append status and correction events.
- Area 4 computes and certifies; stores source provenance and deposit/retained balance components. Area 5 owns the shared invoice claim and posts/reverses via the ledger service (`ledger.py:1030`). Proposed in-transaction posting/reversal interface carries stable claim ID, invoice/version and entry IDs, effective date and source component deltas. Fail atomically if a posted effect cannot be linked or reconciled. Area 6 owns signed terms; Area 7 owns cost and budgets; Areas 3/9/19 supply stable AP, stock and labor source contracts; Area 1 owns receipts and payment-release events.
- Start with `payapp.create` and sensitive `payapp.approve` plus project scope. Area 18 owns send, adjust, unlock, release, certification and replacement permission placement where existing permissions are insufficient. Area 14 owns optional review routing. Internal approval cannot bypass customer certification or posting authorization. Require reasons for adjustments, rate/release changes and correction actions. Honor Area 13 Billing locks and Area 5 invoice and period checks on effective posting and reversal dates. No accounting changes in the master baseline.

## 6. Planned tests

1. Cost and stored-material calculations tie to certified source lines. The inclusive cut-off uses each source's accounting effective date and excludes later-effective activity even if entered earlier. A revision records each included source entry and amount; a late posting or correction that changes a sent application requires a new revision, and certified revisions remain immutable. One AP bill joins one cycle. Moving it and locked bill editing follow permissions and audit.
2. Missing or zero budget shows posted costs and explains why no percent-complete suggestion is available. Require an authorized user's amount or percentage and reason before submission. Review OFF allows the normal flow. Review ON routes. Sent and returned revisions preserve history. Certified facts remain immutable.
3. A stored-material transfer links to the original stored-material line, reduces stored balance and increases installed work equally, adds zero cumulative earned value, and keeps new billable work separate. Approval and concurrent retry produce one claim, one linked invoice draft, a locked certified revision and zero ledger entries. Draft failure rolls back the claim and lock. Authorized issue posts once.
4. An issued unfunded deposit contributes zero. Funded pro rata applications exclude tax and retainage releases,
   subtract effective prior applications and respect both bill and principal caps and concurrent reservations.
   Verify final rounding, unapplied principal and prospective signed changes with a review flag for any required
   undo. Partial retainage release selects original posted held sources and records stable splits and reason.
   Reject release of unposted current withholding. The first eligible pay app uses the new rate for newly earned
   work, preserving prior withholding.
5. Draft cancellation records a reason and preserves claim history, ends the active claim, releases reservations
   and keeps certification locked. Retry returns canceled. Only explicit authorized replacement may claim the
   certified event again, with one active claim even on concurrent attempts. Approval, draft creation and
   cancellation leave the ledger and billed-to-date unchanged. A posted void requires a linked reversing entry,
   subtracts the original components at its effective date and preserves earlier as-of totals. Reissue counts
   only on successful posting. A failure rolls back ledger and source effects together.
6. Return, void and payment reversal re-hold only eligible bills and log and notify. Lock and permission failures leave document and balance state unchanged.

## 7. Owner questions

1. **Cancellation closed (§4).** Any separate decertification workflow and its authority remain open.
2. **Closed (§3.1).** Apply funded principal pro rata against eligible signed SOV, with prospective changes only.
3. **Closed (§3.2).** Release only posted held retainage, with stable source splits and prospective rate changes.
4. **Closed (Q4, 2026-11-21).** Use inclusive accounting-effective-date cut-offs with revision-level source evidence; late postings or corrections that change a sent application require a new revision. Missing/zero budget requires a reasoned authorized manual amount or percentage. Stored-material installation is a linked equal transfer with zero cumulative earned-value change; new work is separate.
5. **Billed-to-date timing closed.** Decide which invoice-only fields may change while certified billing facts stay frozen, and which roles may adjust a pay app or create an explicit replacement draft. Area 18 owns exact permission placement for adjust, release, unlock, certification, and replacement actions.

Review gate: keep the plan unstaged. Implementation waits for owner decisions and source contracts.
