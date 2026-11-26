# Next step: Phase 2.9, the schema replan (areas 18, 13, 12, 10, 17, 8, 15, 6, 7, 5, 4, 3, 2, 14, 9, 20, 1, 11 and 16 approved)

## Current planning stop (2026-11-25, Area 21 revised)

**Update 2026-11-25 (9:44 to 9:53 PM): A21-Q13a to Q13d recorded:** the other company's side posts on save for anyone (audit trail names the WSB user); save blocked when either company's period is closed (same for transfer, voids, credit memos); pay run records the full amount, net 400,000 only at settlement ($5,000 example); no split on PO-matched bills. The four intercompany open items are closed; remaining: 'Available after pay run' uses WSB's balance, an approval for the transfer, the OBE lock. Awaiting owner approval.

**Update 2026-11-25 (9:34 PM): A21-Q2e recorded: IC AP is 2220** (the first 22xx number free in both chart templates; Use Tax Payable stays 2210; 1210, 1800, 2800 stay). The account-number open item is closed; AP is 2010 and AR 1110 (design mockups to update). Other open items remain: who creates the mirror bill, other-company period lock, pay-run shares when paying another entity's bill, PO-matched vendors, an approval for the transfer. Awaiting owner approval.

**Update 2026-11-25 (8:35 PM): A21-Q2d recorded ("design sent to planning inbox"):** Area 21 §7 now follows the design chat's intercompany model (1800/2800 clearing at bill entry, automatic transfer to 1210/2210 at payment, split bills 50/30/20, elimination also nets 1800/2800 for unpaid bills, ICB and ICI created at the payment transfer, memo "Paid by WSB" with no AP posting, split stored per bill). Chart check: 2210 is Use Tax Payable in both templates (clash, not renumbered); AP is 2010 and AR 1110. Open: who creates the mirror bill, other-company period lock, pay-run shares when paying another entity's bill, the account numbers. Awaiting owner approval.

**Update 2026-11-25 (7:45 PM): A21-Q2c recorded:** both cross-charging cases (payment for a related entity; bill coded to a related entity), each example stating whose books hold the supplier bill (50,000 WSB/WEC); Due to/Due from from clearing accounts set per entity pair (planning reading); Area 1 and Area 3 pointers updated; Design asked to build cross-charging into bill entry (message in Strata_Teams inbox/to_design.md). Awaiting owner approval.

`docs/replan_2.9/area_21_whole_app_setup_conversion.md` revised for the owner answers A21-Q1 to Q13, Q2b and Q5b (6:50 to 8:04 PM): balance per entity; eliminations an auto-generated draft in the month-end review, posted on approval; intercompany charge (AR invoice and AP bill) created when a related entity's bill is paid (50,000 example); one opening depreciation entry per asset; no automatic OBE move (hard warning and a choice; Owner's capital 1,000,000 and Retained earnings 4,425,333 bring the example OBE to 0); two conversion methods and nothing rolled into Retained earnings unless a year end; monthly trial balances post each month's change (6,000,000 example); policy records only for new settings; `row_version` on every editable table; whole Save refused on one stale record; mid-month go-live; full setup copy; closed alerts return on content change; Export all data `company.backup`; one reassign tool. **No open owner questions; awaiting owner approval.** Pointers in Areas 1, 2, 3, 5, 7, 8, 11, 13, 16, 18 and the decisions file.

## Earlier planning stop (2026-11-25, Area 21 drafted)

`docs/replan_2.9/area_21_whole_app_setup_conversion.md` drafted (Planning readings; docs only). Contents: stale-save refusal (`row_version`, `tx.update_versioned`, `StaleVersionError`), `company_policy` records, the opening balances and conversion batch (one linked entry per item, OBE tie-out and close), the company creation wizard and switch, entities and consolidation, the calendar query and per-user alert state, and the other whole-app items (timestamps, Export all data, reassigning a deactivated user's work). Worked examples: a conversion of eight items with OBE 5,425,333, the stale save 450000 vs 475000 vs 460000, a 1,000,000 intercompany loan and its elimination. **Awaiting the owner's answers.** **Open for the owner (§14):** Q1 balance per entity, Q2 how eliminations post, Q3 opening accumulated depreciation per asset, Q4 OBE close, Q5 year-to-date on a mid-year start, Q6 migrate `company_settings` controls, Q7 which tables get `row_version`, Q8 one stale item in a multi-row Save, Q9 mid-month go-live, Q10 subsidiary copy scope, Q11 closed alerts and content change, Q12 Export all data permission, Q13 reassigning a deactivated user's work. Pointers in Areas 3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20.

## Earlier planning stop (2026-11-25, Area 19 drafted)

**Update 2026-11-25 (3:15 PM): A19-Q10 recorded (percent complete and budget-to-actual count Actual plus Accrued; 29.1% example); the all-job-cost-accruals rule is an owner rule; area set: producers Areas 19, 9, 3, readers Areas 7, 17, 5.** **Update 2026-11-25 (3:00 PM): Area 19 revised for the owner answers A19-Q1 to Q9, Q3b and Q7b; awaiting owner approval; no open owner questions.** Settled: entry from the file's rows (roadmap open decision 1), file kept as long as the entry, accrual built in v1 as a separate accrual posting type (Actual, Accrued, Total; profit with and without accruals; never in T&M or a pay app; all job cost accruals, pointers in Areas 5, 7, 17), burden split by who pays (Accrued burden), 0-hour and negative rows, "Card and spend import" as its own v1.1 area.

`docs/replan_2.9/area_19_payroll_import.md` drafted (planning proposals; docs only). One batch per payroll run through staging (`payroll_import_line`), a mandatory human review of the exact rows (digest), one balanced entry (wages and burden to expense with job and cost code, credit Payroll clearing) plus `time_entry` rows in the same transaction; a reversal inserts negative rows; an optional Labor accrual control (OFF) with an automatic reversal. Worked example: the wizard's four rows, batch 1,695,660 cents. **Awaiting the owner's approval.** **Open for the owner (§13):** Q1 entry from rows or the provider's journal, Q2 source file retention and download, Q3 accrual in v1, Q4 employee not found, Q5 reversal when hours are on a T&M invoice, Q6 job statuses that take cost, Q7 Ramp and other batch types. Pointers: Areas 5, 12, 14, 18. Area still to draft: 21.

## Earlier planning stop (2026-11-25, Area 16 drafted)

**Update 2026-11-25 11:39 AM: A16-Q7, Q8, Q9 decided (A each); no open owner questions in Area 16. **APPROVED by the owner 2026-11-25 1:18 PM (23a8b6b); 19 of 21 areas approved.** Areas 19 and 21 remain to draft.** `docs/replan_2.9/area_16_custom_fields.md` drafted; **revised for the owner answers of 2:58, 3:05, 3:09 and 3:47 AM (3:47: custom fields are for CRM leads only; Estimate, Contact, Invoice, Bill and Project have none, and Area 6 Q25 A is withdrawn; old rows are archived in `custom_field_legacy`) and earlier: a CRM custom field belongs to one service type > stage > field (the scope table is dropped), CRM lead fields only; a service type change keeps the old values hidden and is audit-logged; a User field picks any active user; no custom fields for service cases (`'Case'` removed from Area 15 Q23 A); job delivery-stage fields stay a separate set, not designed here.** Owner inputs: the 2026-11-13 request (all fields company-defined, no packs; warnings at more than 2 board-card fields and more than 20 active fields, never limits; copy fields; help text; shown from stage; remove keeps values) and FR1; Area 15 Q23 A (`'Lead'` only; `'Case'` removed by the 3:09 AM answer). Planning proposals: one `custom_field_def` table kept (no `deal_field` tables); `service_type_id` and `stage_id` on the definition (no scope table); a `'User'` type in `value_user_id`; `on_board_card`, `help_text`, `row_version`. This area posts nothing; Money fields are integer cents. **Awaiting the owner's approval.** **Open for the owner (§9):** A16-Q7 stage visibility (onward or only in the stage), A16-Q8 copy fields with no matching stage, A16-Q9 when job delivery-stage fields are designed. Pointers: Areas 3, 6, 7, 8, 13, 15, 17 and 18. Areas still to draft: 19, 21.

## Earlier planning stop (2026-11-25, Area 11 drafted)

`docs/replan_2.9/area_11_fixed_assets_depreciation_loans.md` drafted with the owner answers of 1:21 AM: straight-line and declining balance (switching to straight-line when that gives more is a planning reading), and book depreciation only, no tax schedule. Planning calls (owner may revise): loan payments are drafted as bills split into principal and interest; no entity column. The decided disposal inputs (ASSET-02, 03, 04) and Area 14's 'Asset disposal' row (OFF) are carried; every posting has a balanced worked example. **Revised for the owner answers A11-Q1 to Q4 (2:09 AM): split shown always, posting a control (OFF); a loan paid to the dealer is the dealer's bill plus a "loan funded" payment (Dr Accounts payable / Cr Loans payable, no bank line); disposal month convention is a Company setting; job charging stores the flag and rate only.** Two planning fixes: no month is charged twice (run skips disposed assets; catch-up only when the run line has not posted), and the line-of-credit example now ties. **APPROVED by the owner 2026-11-25 2:49 AM (c464cc1); 18 of 21 areas approved.** Pointers: Areas 3, 10, 13, 14 and 18. Areas still to draft: 16, 19, 21 (Area 1 drafted, awaiting approval).

## Earlier planning stop (2026-11-25, Areas 9 and 20 approved)

`docs/replan_2.9/area_20_connections_email_notifications.md` drafted; **revised 2026-11-25 for the owner answers A20-Q1 to Q4 (12:50 AM: Windows credential store; mail read every 15 minutes while the app is open; weather gets only the job site address; purged capture messages leave a content-free stub) and the 12:53 AM answer that serial tracking is in (Area 9 §8.3, per material code, OFF by default).** Owner rules (12:37 AM): every notice shows in the in-app list always, email is opt-in per user and
per kind of notice, and documents still send by email as their own action; the job-site weather forecast is OFF until an Admin turns it on (one setting, owned here;
Area 8 points to it). Planning calls (owner may revise): the notification feed lives in Area 20 (Area 21 pointed here; next_step lines 645 and 687 marked); email sends
from the company's own mailbox as live Connections shows. Also built from owner decisions already on file: CAP-04, CONN-01 to CONN-03 and OD-24 (sent events keep their
destination). Nothing in this area posts, approves or moves money. **APPROVED by the owner 2026-11-25 1:00 AM (Areas 9 and 20 together, as committed in 43e824e; Area 9 re-approved with serial tracking, §8.3); 16 of 21 areas approved.** **A20-Q1 to Q4 answered (§17); no open owner question remains in Areas 9 and 20.** Pointers: Areas 2, 3, 6, 8, 9,
14, 15 and 18. Areas still to draft: 1 (drafted), 11, 16, 19, 21.

## Earlier planning stop (2026-11-25, Area 9 approved)

`docs/replan_2.9/area_9_materials_pos_inventory.md` drafted with the owner answers of 11:05 to 11:35 PM; **revised 2026-11-24 for the owner answers to §16 Q1 to Q7 (11:30 to 11:43 PM; section 18)**. Owner rules:
units add and deactivate (never delete, no rename of a used unit; settles OD-51); stock tracking is a Company control,
OFF by default; one commitment record `po_type` Materials or Subcontract (commitment on Send, Mark as sent or Print);
free-text "to be coded" request lines; **a line with a material code takes its cost code, read-only on the line**.
Planning proposals: `unit_of_measure`, `material_code`, PO, change, receipt, `bill_match`, request, pull ticket and
stock tables; `po_matching` control (OFF, owner); costing is the owner's moving average or FIFO, picked once. **APPROVED by the owner 2026-11-25 12:31 AM; 15 of 21 areas approved.** **Q1 to Q7 answered (§18):** matching is a Company control (OFF); costing is moving average or FIFO, picked once; no free-text PO lines; a bill line is locked to its PO line's job and cost code; units can be reactivated; a recoded request line takes the material's cost code; a stock price difference splits between stock value and a new controlled "Stock price differences" role. **Not asked (§17):** Subcontract SOV lines without a material code; roll, sheet, bundle, square, pallet and lot as shipped units; "Hold bills" holds the bill before approval and routes it to the job's PM (owner 11/25); Pointers: Areas 3, 6, 7, 8,
10, 13, 14 and 18. Areas still to draft: 11, 16, 19, 20, 21.

## Earlier planning stop (2026-11-24, Area 14 approved)

`docs/replan_2.9/area_14_approvals.md` drafted with the owner answers of 10:05 PM (only Reject and Send back need a
reason; Approve takes an optional comment) and 10:20 PM (Q1-Q7). One mechanism: `approval_kind` (21 kinds, six new, all
OFF), `approval_policy` and `approval_step` (anyone with permission, the job's PM, a role, people or a chain, each with
a backup), a widened inbox. Rules: any change to amount, discount, lines or job voids an approval (Bills keep Area 3
Q4); a posted document edit is held as a pending revision (Reject discards it); the lock check runs again at the final
approval of a posting kind; an unavailable approver goes to the backup, then Admin, then the Master; with "Require a
separate approver" ON and no other eligible approver the submitter may approve with a reason (never an agent).
**APPROVED by the owner 2026-11-24 10:40 PM once the final QA (Opus reviewer and Sonnet QA) was clean; 14 of 21 areas approved.** **Q8 answered 10:40 PM (option A):** journal entries are excluded from the self-approval
fallback and the two separate-approver triggers stay. Pointers: Areas 1, 2, 3, 5,
6, 8, 13, 15 and 18. **Area 11 handoff (not drafted):** asset disposal is the 'Asset disposal' approval row (OFF);
Area 11 owns the disposal record and its approval digest. Areas still to draft: 9, 11, 16, 19, 20, 21.

## Earlier planning stop (2026-11-24, Area 1 drafted)

`docs/replan_2.9/area_1_payments_receipts.md` drafted (owner approved the outline 2026-11-24 8:55 PM, with answers Q1,
Q2, Q3, Q4, Q6, Q7 and Q8; Q5 and Q9 recommended defaults, planning proposals). It places every Area 1 input of this
file (OD-69/OD-70, the 2:55 PM unapplied-payments rule, RP11, Area 2's allocation rules, the Mark triage). Owner
rules: the user chooses where a receipt lands (Q3) and, for a stated deposit, the deposit account (Q1, narrowing the
2:55 PM answer; unplaced money posts to Unapplied customer payments); a user with the permission may unapply an
application while the payment stays posted (Q2, RP11 rewritten); payment methods are a company-editable list (Q6); no
`payment.void`, whoever records may void with a reason (Q7); optional fee on a receipt (Q4). Pointers: Areas 2, 5, 6,
10, 12 and 18 §8.12, and beside RP11 in the decisions file. **Area 1 APPROVED by the owner 2026-11-25 2:49 AM (61706a1).**
Planning proposals to confirm: the new permission `payment.unapply`, the four refund and write-off permission names,
`customer_refund`, `invoice_writeoff` and `statement_send`. Three planning agent files (`cpa-controller`, `planner`,
`reviewer` under `.claude/agents/` and `.codex/agents/`) are drafted and uncommitted, held for the owner.

## Earlier planning stop (2026-11-24, mockup audit and 2:55 PM to 8:15 PM answers folded)

Mockup code-hygiene audit items 1-15 applied as dated amendments (planning proposals unless an owner answer applies):
CLAUDE_UI.md rule 6 (money parser); docs/design.md section 1 (escaping, URLs, UTF-8, shipped secrets, packaging
allow-list); Area 17 §9.5 (exports); Area 18 §8.6 (one reason validator; "only" withdrawn for the unapplied role;
credit-hold control placement); Area 5 §4.2 (unapplied customer payments, owner 2:55 PM; write-off credit hold,
owner 7:30 PM and 8:15 PM); Area 10 §11.2 pointer; Area 6 §3.5 (OD-80) and §4.4 (OD-81); Area 13 §2.7 ("Skip this
month", owner 8:15 PM); Phase 5 conflict list below (item 10). Items 4, 6 and 14 were already covered; no change.
**Open for Mark:** whether OD-81's "discount approval control" is the Estimate approval policy (Area 6 §4.3; read
that way until answered).

## Earlier planning stop (2026-11-24, 1:48 AM answer folded)

From `Strata_Teams\docs\owner_decisions_2026-11-22.md` ("Owner answer 2026-11-24 1:48 AM"), Area 8 §12.20 and Area
18 §8.11: rebuild approval is a new Approvers row "Schedule baseline rebuilds" (PM), OFF by default, configured like
every other kind of work (anyone with permission, the job's PM, a role, specific people or a chain; optional
backup). The separate control `require_baseline_rebuild_approval` is withdrawn: approval kinds are rows of
`document_approval_setting` (RP9), so the row is the only switch. Self-approval follows "Require a separate approver"
(off = allowed, marked Self-approved). **Area 14 handoff: include the approval kind "Schedule baseline rebuilds"
when Area 14 is drafted.** No open owner questions remain in the drafted areas.

## Earlier planning stop (2026-11-24, 1:37 AM answer folded)

From `Strata_Teams\docs\owner_decisions_2026-11-22.md` ("Owner answer 2026-11-24 1:37 AM"), Area 8 §12.19 and Area
18 §8.10: the task-baseline rebuild uses the existing `job.schedule.edit` (job scope), no new permission; one new
Company control `require_baseline_rebuild_approval` (PROPOSED name, OFF by default; **Withdrawn 2026-11-24, owner
1:48 AM: the switch is the Approvers row, above**): off, the editor rebuilds alone;
on, the rebuild is a request written only on approval, never self-approved (**Withdrawn 2026-11-24: follows "Require a separate approver"**), and a refused request leaves the
baseline unchanged. Reason and history in both modes; insert-only and `finish_on` are not controllable. **STOP
question for Mark:** who may approve when the control is on (**answered 2026-11-24 1:48 AM: the Approvers page; the
proposed rule is Withdrawn**; proposed rule: Area 14's single approval mechanism,
default approvers Admin, Master and job-scoped `job.schedule.edit` holders, never the requester).

## Earlier planning stop (2026-11-24, 1:14 AM answer folded)

From `Strata_Teams\docs\owner_decisions_2026-11-22.md` ("Owner answer 2026-11-24 1:14 AM"), Area 8 §12.18: the
task-level baseline can be rebuilt from the current schedule with a required reason, as a new insert-only version
(the earlier one is kept and reads as superseded); the planned completion (`finish_on`) never changes, so Late is
unaffected; slip uses the latest version; not a control (**Withdrawn 2026-11-24, owner 1:37 AM: one approval control, OFF; §12.19**). **STOP question for Mark:** which existing permission
covers the rebuild (candidate `job.schedule.edit`; no new permission added). **Answered 2026-11-24 1:37 AM: `job.schedule.edit`.**

## Earlier planning stop (2026-11-24, 12:28 AM answers folded)

From `Strata_Teams\docs\owner_decisions_2026-11-22.md` ("Owner answers 2026-11-24 12:28 AM"), Area 8 §12.17:
task baseline dates are fixed automatically at the first schedule build and never move (rebuild with a reason: §12.18) (until then the baseline
holds only the planned completion); a failed inspection adds open tasks with an assignee plus a re-inspection, never
punch items; on the Material forecast a signed job with no start stays in the week of its planned completion, tagged
"Not scheduled", until it is scheduled.

## Earlier planning stop (2026-11-24, later): Q28 revisited and inspections folded

From `Strata_Teams\docs\owner_decisions_2026-11-22.md` ("Owner answer to Area 8 Q28, revisited", 11/23 11:58 PM;
"Owner answer to field review question 3, inspections", 11/24 12:04 AM):
- **Area 8 §12.16:** the planned completion date is required at job creation and is the baseline finish; the start
  date is optional ("Not scheduled" until entered); the three dates and Late are unchanged. Inspections are a
  company list per job type, copied to the job and editable there; tracked only (Q34 A).
- **Area 15 §12.1 and Area 7 §14:** the lead's Estimated completion date pre-fills the planned completion;
  `project.target_start_on` NULL allowed again. Earlier "start date required" lines are marked withdrawn.
- **STOP question for Mark:** when task-level baseline dates are fixed if the job has no start at signing
  (proposed, not approved: the first time the PM enters the start and the schedule is built). **Answered 2026-11-24
  12:28 AM: approved; Area 8 §12.17.**
- **Conflict flagged:** a failed inspection "adds its corrections as punch items" vs Q32 (a punch item is logged
  work, not an open task). **Resolved 2026-11-24 12:28 AM: corrections are open tasks; Area 8 §12.17.**

## Earlier planning stop (2026-11-24): Areas 2, 3, 4 and 5 approved; Area 8 Q37 folded

Owner approvals in `Strata_Teams\docs\owner_decisions_2026-11-22.md` (2026-11-23 11:25 PM to 2026-11-24 12:00 AM):

| Area | Status | Change folded |
|---|---|---|
| 2 Pay run | Approved 2026-11-23 11:40 PM | §10: a Card line credits the chosen credit card account and is left out of cash after the run and the negative-balance warning; check numbers unique per funding account across all payments, voided included |
| 3 Bills, vendor credits, terms, subcontracts, vendors | Approved as drafted 2026-11-23 11:55 PM | none |
| 4 Customer pay apps and billing cycles | Approved 2026-11-23 11:55 PM | OD-72 fix: on Reclass job each certified SOV line of the linked pay app is mapped to the new contract's SOV (refused if any line cannot be mapped); old contract's later pay apps show "moved to <job>"; new G703 includes it |
| 5 Invoices, credit memos, statements, customers | Approved again 2026-11-24 12:00 AM | §9.5 pointers only (Area 10 Q18, Q19, Q21, Q36; billed to date from postings; Area 4 SOV mapping) |
| 8 PM and schedules | (approved earlier; Q37 answered 2026-11-23 11:25 PM) | §12.15: Q37 A, an open PCO's cost is its own forecast line tagged with the field event, removed if the PCO is closed; mockup item for the job-detail Budget |

Approved: 13 of 21 areas (18, 13, 12, 10, 17, 8, 15, 6, 7, 5, 4, 3, 2). Not yet drafted or approved: Areas 1, 9, 11,
14, 16, 19, 20 and 21; their owner inputs are in the sections below. No open owner questions remain from the
drafted areas. Next action: draft the next area (Area 1, payments and receipts, holds the most handoffs: OD-69/OD-70
undo and re-apply, RP11, allocations for Area 2). The baselines change in one pass after the full replan is approved.

## Earlier planning stop (2026-11-23 late): owner answers of 3:20–4:50 PM and 8:05–10:45 PM folded

**Added 2026-11-23 (owner 10:45 PM):** Area 10 Q36 A (only expense and COGS reclasses skip approval; whole-invoice
and whole-bill job moves follow manual-entry approval when it is on; §11.9); Area 8 Q34 A (the final-billing control
is retired; §12.14), Q35 A ("Late n days" in calendar days); the PCO correction (tagging a PCO creates a field event
and no change order; a CO exists only after a PM converts it; the 3da374b default and the approved 'PCO pending'
statuses are marked withdrawn); the editable reclass/void date within open periods is a lead default. New
question: Area 8 Q37 (does an open PCO's cost show in the forecast). **Waiting for owner approval:** Areas 2 and 3
(drafts, all their questions answered), Area 4 (ready for approval) and the amended Area 5.

Folded from `Strata_Teams\docs\owner_decisions_2026-11-22.md` (OD-71 to OD-78 with the 4:10 PM revisions and the
4:12 PM correction; Area 10 Q20–Q21 at 8:05 PM; Area 8 Q29–Q32 at 8:15 PM; Q33 at 8:35 PM; 10:05 PM WIP sample).
One owner each:

| Owner | Items |
|---|---|
| Area 10 §11.7–§11.8 (approved; amendments) | Q20 B (AP line moves only when the whole bill is on one job); Q21 A + OD-71 (one date rule for reclasses and payment voids); expense-account reclass posts with no approval or hold; OD-72 B (pay app follows the invoice); OD-77 (no WIP entry; jobs-list note); Billed to date is posted billing (9:28 PM); new Q36 |
| Area 8 §12.11–§12.13 (approved; amendments) | Q29 A; Q31 (no special stage scheduling); Q32 (PCO by whoever logs, CO by a PM, no COR; no "Feeds the status update"; a punch item is logged work); Q33 A (Late vs baseline + approved CO time; target never sets Late); work-days fix of fee73a8; 10:05 PM WIP sample (no schema); new Q34, Q35 |
| Area 15 §12.1 (approved; amendment) | OD-73 to OD-76 lead import rules; control "Require approval for lead imports" (OFF) |
| Area 6 §17 (approved; amendments) | ESTIMATE-PRETAX (line Taxable/Exempt flags, summary shows the mix); OD-78 B (signed file may be a PDF or a JPG/PNG photo) |
| Area 4, Area 18 §8.8 (pointers) | OD-72 pay app follows; placement of `require_lead_import_approval` and `lead.import_approve` (PROPOSED) |
| Area 3 and Area 2 drafts | Q20 B and the one date rule in the same-gross bill reclass; void reversal date per Q21 A |

Not folded (mockups only, owned by the design-queue run): the 8:26, 8:28, 9:33, 9:42 and 9:45 PM page-width
decisions. Controls stay OFF by default; integrity rules unchanged (no posting into a closed or locked period; an
agent-origin entry still needs a human approval). Areas 2 and 3 are drafted (Q1–Q6 and Q1–Q3 answered) and wait
for owner approval with Area 4 and the amended Area 5. Questions for Mark: Area 10 Q36, Area 8 Q34–Q35 (in the areas
and the log `Strata_Teams\planning_replan_log_2026-11-22.md`).

## Earlier planning stop (2026-11-23 evening): owner answers of 6:55–8:00 PM folded

Folded from `Strata_Teams\docs\owner_decisions_2026-11-22.md` ("Owner answer to Area 10 Q18" to the end) and the
inbox message 2026-11-23 1:30 PM "schedule tree, tasks without %, and one activity table". One owner each:

| Owner | Items |
|---|---|
| Area 10 §11.5–§11.6 (approved; amendments) | Q18 (AR and revenue lines take the new job together, in Reclass job and on the Reclassify page; §2.4 exception); Q19 B (the page follows OD-69/OD-70); new Q20 (AP lines), Q21 (one date rule, OD-71) |
| Area 18 §8.7 (approved; amendment) | Q26 A (a listed reason satisfies the rule; 10 typed characters only for Other or no list); the unapplied role also posted from the page |
| Area 8 §12.5–§12.9 (approved; amendments) | work tree (`work_template_node`, `job_work_node`), tasks without %, task start and finish activities, one `activity` table (Q25, Q26 superseded); Q27 three dates (baseline locked at signing; a CO or a granted extension moves the target; `schedule_extension`); Q28 A (start date required **(start no longer required: Withdrawn 2026-11-24, Area 8 §12.16)**); Requested completion warning; new Q29–Q32 **(target, extension and Requested completion parts Withdrawn 2026-11-23, owner 8:30 PM: see below)** |
| Area 15 §12.1, Area 7 §14 (approved; amendments) | Q24: optional `lead.requested_completion_on`; lead stages on the tree; `activity` gains the field columns; `project.target_start_on` NOT NULL **(start no longer required: Withdrawn 2026-11-24, Area 8 §12.16)**, `requested_completion_on` added, `target_finish_on` dropped **(target, extension and Requested completion parts Withdrawn 2026-11-23, owner 8:30 PM: see below)** |
| Area 3 draft | Q1 A, Q2 A, Q3 (compliance hold is a control, OFF; warning by default; the draft no longer has it always on), Q4 (vendor or total only, only with approval ON), Q5 A (remainder on the last line), Q6 A |
| Area 2 draft | Q1 A, Q2 A (void reversal date follows Area 10 §2.4), Q3 A (warn only) |

**Correction folded 2026-11-23 (owner revision 8:30 PM; Area 8 §12.10, Area 15 §12.1, Area 7 §14):** baseline
set at signing, never moves; forecast = baseline + approved CO time + delays + reschedules; target = a PM-editable
date with a history log (`project_target_history`), not calculated; the lead's optional date is Estimated completion
(the job warns when the forecast is later); the Material forecast places leads in the week of their Estimated
completion, tagged Estimate. The e949ba3 text for Q27, Q24 and Q30 (calculated target, `schedule_extension`,
Requested completion) is marked withdrawn. New question: Area 8 Q33 (which date makes a job Late). Not yet folded:
the owner's 8:05 PM answers (Area 10 Q20 B, Q21 A) and 8:15 PM answers (Area 8 Q29 A, Q31, Q32).

The 8:00 PM RI0001-003 contract value ($260,000.00) is sample data only (Area 8 §12.8). Controls stay OFF by default
(new: `vendor_compliance_hold`, `require_note_on_task_start_finish`, both PROPOSED names) and the integrity rules are
unchanged. **Not folded (outside this range): OD-71 to OD-78 (owner 3:20–4:50 PM)** (folded 2026-11-23 late, above), which touch Area 10 (OD-71
date rule, OD-72 pay app follows, OD-77 no WIP entry), Area 15 (OD-73 to OD-76 lead import) and the design queue
(OD-78); Area 10 Q21 asks about OD-71. Next action: fold OD-71 to OD-78; Mark answers the new questions and approves
Areas 2, 3 and 4 and the amended Area 5. Questions for Mark: each area and the log
(`Strata_Teams\planning_replan_log_2026-11-22.md`).

## Earlier planning stop (2026-11-23 early): evening and overnight owner messages folded; Areas 2 and 3 drafted

Folded from `Strata_Teams\inbox\to_planning.md` (2026-11-22 evening to 2026-11-23 2:20 AM), with
`Strata_Teams\docs\planning_owner_features_2026-11-22.md` and OD-23 to OD-70 of `owner_decisions_2026-11-22.md`.
One owner each:

| Owner | Items |
|---|---|
| Area 10 §11 (approved; amendments) | Reclassify transactions page (OD-28 new item); Reclass job (OD-28, OD-69, OD-70; OD-68 withdrawn); Q18–Q19 |
| Area 18 §8.5–§8.6 (approved; amendments) | 10-character reasons (OD-31, markers in Areas 10, 13 and 18); roles `purchase_discounts` and `unapplied_customer_payments`; Manager cannot override the final-billing block **(control retired 2026-11-23, Area 8 Q34 A)**; Q26 |
| Area 5 §9.4 (approved; amendments) | tax rates by effective date (OD-59); invoice state after Reclass job |
| Area 8 §12 (approved; amendments) | Stage > Phase > Task and the milestone answer; 11/22 field decisions; Material forecast page; Q25–Q28 |
| Area 15 §12, Area 7 §14 (approved; inputs) | lead import, lead alerts, stage probability (owner, pending), `lead.estimated_start_on` (Q24); job contact roles |
| next_step (undrafted areas, below) | Area 1 (OD-69/OD-70 postings); Area 3 (OD-66, OD-67, vendor documents, vendor kind, waivers); Area 9 (OD-51 units list, PM creates requests, PO expected date); Area 16 (User field type, Lead scoping); Area 20 (weather connection) |

The "v1.1 field records approved" message was checked: it is fully in Area 8 §10, Area 18 §8.5 and the Area 9
entry below. Conflicts with approved text are flagged in place, not changed (Area 10 §11.2 AR refusal; Area 8 §12.1
C30 and §12.2 baseline rule). Area 3 is drafted for owner approval
(`docs/replan_2.9/area_3_bills_vendor_credits_terms_subcontracts.md`, Q1–Q6), and so is Area 2
(`docs/replan_2.9/area_2_pay_run.md`, Q1–Q3). Next action: Mark answers the questions and approves Areas 2, 3 and 4
and the amended Area 5. Questions for Mark are in each area and in the log
(`Strata_Teams\planning_replan_log_2026-11-22.md`, "Questions for Mark").

## Earlier planning stop (2026-11-22): owner decisions folded; Areas 4 and 5 ready for the owner

The owner's 2026-11-22 answers (`Strata_Teams\docs\owner_decisions_2026-11-22.md`: items 1–26, OD-01 to OD-18)
are folded into the owning areas, one owner each:

| Owner | Decisions |
|---|---|
| Area 4 §5, §7 | item 17 (Q5 roles; `payapp.adjust`) |
| Area 5 §9 | items 7 and 22; OD-07, OD-09, OD-10, OD-11, OD-15, OD-18 |
| Area 7 §1.2, §2.2 | item 25 with OD-03; item 26 with OD-02 |
| Area 10 §6 | item 21 |
| Area 17 §3.2 | OD-13 |
| Area 18 §8 | items 8, 9, 10, 11; places the four new codes |
| Areas 2, 3, 9, 20, 21 (not drafted; section below) | items 5, 6, 12–16, 18, 23; OD-04, OD-08, OD-16, OD-17 |
| Area 9 and 11 entries, Area 20 entry (below, "Handed to later areas") | items 19, 20, 24 |
| Design queue and later phases (section below; no 2.9 schema effect) | items 1–4 with OD-01; OD-05, OD-06, OD-12, OD-14 |

- **Area 5** was approved in full at 2:15 AM (shared_decisions 2026-11-22). Its §9 holds the dated amendments and
  its questions, all decided (Q11 and Q12 at 12:47 PM; Q7a, Q7b, Q7e and Q8 in round 2 at 1:56 PM: accrual-only
  sales tax, with the written-off tax report in Area 17 §4). The amended plan is ready for owner full-plan approval.
- **Area 4** is ready for owner full-plan approval: Q1–Q7 are decided (Q6 and Q7 at 12:47 PM).
- **Conflicts, now decided by the owner (12:47 PM follow-ups):** item 9 vs chart-of-accounts C3 (Area 18 Q25:
  normal balance follows the new Type); item 21 vs deferral C3 (Area 10 §6: auto-post confirmed); item 17 vs Area 4
  Q5 (Q7: adjust never edits certified amounts); OD-09 vs Area 5 §8.2 Q3 (Q11: unpaid job change by Edit, paid by
  reclass); Area 5 Q12 replaces the 11/20 tax-freeze rule (signed price is pre-tax; tax at invoicing), recorded as
  dated amendments in Areas 5, 6, 7, 8 and 15 and in the service-quote reconciliation below.
- **v1.1 field scope (owner 12:41 PM, amended 12:45 PM):** Inbox inputs in Area 8 §10 (daily log, delays,
  assignments, look-ahead, punch and inspection items, Schedule tab), Area 18 §8.5 (Field role, default tab) and
  Area 9 below (field material request).
- Next action: Mark approves Area 4 and the amended Area 5. The v1.1 wireframe questions stay open inputs for
  UX research and the owner's wireframe review. Baseline work waits for
  approval of the full replan. Log: `Strata_Teams\planning_replan_log_2026-11-22.md`.

## Owner decisions 2026-11-22 for areas not yet drafted (Decided 2026-11-22, owner)

Each line is the rule the drafting session must carry; audit IDs in brackets.

- **Area 21, Company setup and conversion:**
  - Item 5 (CSVIMP-04, OPENBAL-03, COSETUP-02, OPENBAL-04; the GLDETAIL-01/REPORT-03 conversion-date cases): the
    conversion posts on the day before the first live date, for both month-end and mid-month go-lives (Jan 1 →
    Dec 31; Mar 15 → Mar 14). Schema: `company_settings.first_live_date`; the conversion date is derived, never
    typed. Area 17 handoff recorded in Area 17 §3.2.
  - Item 6 (OPENBAL-02/03/04): a separate entry per item. There is no single summary conversion journal entry.
    Every opening balance and every open invoice or bill gets its own linked posting (source 'Conversion', linked
    to its source row). Tests: `test_conversion_posts_day_before_first_live_date`,
    `test_conversion_creates_one_linked_entry_per_item`.
- **Area 3, Bills, vendor credits, terms and subcontracts:**
  - Item 12 (APBILL-04, APBILL-01 over-limit branch, SUBPAY-04 draw-to-bill limit): Save bill and Save and new
    both warn and require a reason when a subcontract bill exceeds the remaining approved value, including approved
    change orders. Company control `subcontract_overlimit_block` (OFF by default; Area 18 §8.3) makes both refuse.
  - Item 13 (APBILL-05): a same-gross correction that moves account, job or line allocation is a reclass through
    journal entry approval, or the approval route already set for reclasses (Area 10 §2). No separate bill
    re-verification route.
  - Item 14 (VCR-01, VCR-03, PAYRUN-04, VCR-04 balance and close): a saved refund request holds its outstanding
    amount against that exact vendor credit. The hold is released on cancel and reduced as refund cash is received.
    Bills and pay runs see only the unheld remainder. Schema: a hold row per refund request (credit ID, held
    cents, released cents, status). Area 2 handoff: pay runs read the unheld remainder.
  - Item 15 (VCR-04): a vendor-credit remainder can be written off to any active expense or other-income account by
    Accountant, Admin or Master with a reason (new sensitive code `vendor_credit.write_off`, Area 18 §8.2).
    Approval is needed only above a Company threshold, `vendor_credit_writeoff_approval_threshold_cents` (NULL =
    off; Area 14 routes it). Period locks apply.
  - Item 16 (TERM-04, PAYRUN-01/02/04 discount branches): the early-payment discount applies through the deadline
    date inclusive, calculated on the bill total. If it expires before the payment is recorded, the line returns
    for review at the full amount. It posts to a new `purchase_discounts` account role, or back to the job cost
    line when the bill is job-coded. On the payment line the discount is an editable amount that defaults to the
    calculated amount (pro rata for a partial payment) and can be changed, for example to $0. Area 2 handoff: pay
    run lines carry the same editable discount. Area 18 handoff: add the `purchase_discounts` role.
  - Item 17 branches (SUBPAY-01, APBILL-05): the Area 4 §5 `payapp.adjust` rule applies.
  - OD-08 (VENDOR-05): drop the posting-preview vendor-name claim. Design fix (no schema): New bill must open as a
    blank form at every entry point; it currently opens filled from an existing bill.
  - OD-16 (G1): the New bill vendor dropdown and the Vendors page read one shared vendor source (no hard-coded
    list), so every vendor, including the nine codes, preselects from "Enter bill"; the rest of the bill stays
    blank. This is a database binding point (CODE_CHANGES_NEEDED.md, in the mockups folder).
  - OD-17 (G1): reload keeps what the user typed as an unsaved session draft; a fresh + New bill still opens blank.
    Screen behaviour; no stored draft row.
  - Added 2026-11-23 (inbox 2026-11-22 evening "two new owner features + rules"; OD-66 B): an early-payment discount
    on a job-coded bill credits that bill's job and cost code line; only bills with no job use the
    `purchase_discounts` role (Area 18 §8.6).
  - Added 2026-11-23 (same message; OD-67 B, correcting OD-26's sample numbers): a vendor-refund receipt also lowers
    the credit's open balance; usable = open credit minus held. VC-031 after a $100.00 receipt on a $350.00 request:
    open $250.00, held $250.00, usable $0.00. Second lead-default scenario: $200.00 requested and $50.00 received
    gives open $300.00, held $150.00, usable $150.00.
  - Added 2026-11-23 (design chat "CRM and Field gap list", items 6–8, with the 11/22 owner decision on item 7):
    vendor documents as stored rows (type, number or policy, issued, expiry, status, file; proposed
    `vendor_document`), required documents per vendor kind in `policy_rule`, and the decided payment hold
    (`po_ap_matching_design.md` §6 and §10 item 9: blocks payment only, role-limited override). Vendor kind is a
    `contact.vendor_kind` column (not `entity_type`, which is legal form) with the mockup values Supplier,
    Subcontractor, Service provider, Utility, Government; no separate sub ID (decided 11/22). Lien waivers are
    collected per sub pay app draw (conditional this draw, unconditional prior draw); a missing waiver warns and
    "Paid without waiver" is logged; the control "Require lien waivers before paying subs" blocks the pay run only.
    Open: waivers the contractor gives the owner were not checked (Area 4).
  - **Folded 2026-11-23 into the Area 3 draft** (`docs/replan_2.9/area_3_bills_vendor_credits_terms_subcontracts.md`,
    for owner approval; questions Q1–Q6 there). The lines above stay as the record of what was handed over.
- **Area 2, Pay run:** carries items 14 and 16 through the Area 3 lines above. **Folded 2026-11-23 into the Area 2
  draft** (`docs/replan_2.9/area_2_pay_run.md`, for owner approval; questions Q1–Q3 there, answered 2026-11-23
  7:55 PM and folded).
- **Area 1, Payments and receipts (drafted 2026-11-24: docs/replan_2.9/area_1_payments_receipts.md; added 2026-11-23; OD-69 and OD-70, inbox 2026-11-22 10:55 PM and the OD-70
  addition):** Reclass job on a part-paid invoice (Area 10 §11.2) undoes each payment application on it: the
  allocation is released (reason "Reclass job") and, in the same transaction, one entry posts on the payment's
  original job: Dr Accounts receivable / Cr Unapplied customer payments (Area 18 §8.6 role, current liability). Cash
  stays in the bank; nothing moves to Undeposited funds. Re-applying the payment reverses it: Dr Unapplied customer
  payments / Cr Accounts receivable on the invoice's job. The payment shows the OD-11 "Unapplied" badge and lists in
  the OD-56 unapplied list. Flagged: baseline RP11 (`payment_allocation` release only after the source entry is
  voided) must allow this "Reclass job" release on a still-posted payment. With reclass approval ON the undo waits
  for the approval with the RECLASS entry (Area 10 §11.2). Tests:
  `test_application_undo_posts_ar_to_unapplied_customer_payments_on_payment_job`,
  `test_reapply_reverses_unapplied_customer_payments_entry`, `test_application_undo_leaves_cash_and_deposit_unchanged`.
  **Amendment 2026-11-23 (owner 6:58 PM, Area 10 Q19 B):** the same undo runs when a job change on the Reclassify
  transactions page moves an invoice with a payment applied (Area 10 §11.5); one service function for both.
  **Amendment 2026-11-24 (owner 2:55 PM):** Area 1 posts every unapplied customer payment Cr Unapplied customer
  payments, never Cr Accounts receivable, and applying it later Dr Unapplied / Cr Accounts receivable; AR aging
  shows unapplied payments as their own line (Area 5 §4.2 and Area 18 §8.6 amendments 2026-11-24). Open for Area 1:
  whether customer deposits (Area 5 §8.5 Q9) use the same account, and today's receipt posting in `payments.py`.
- **Area 9, Materials, POs and inventory:**
  - Item 18 (PORDER-01, PORDER-04): job and cost-code commitment starts only on a successful send (or Mark as sent
    or Print). Drafts, approved-but-unsent POs and failed sends stay uncommitted. Close remainder releases the
    unreceived commitment. Area 7 handoff: commitments read only sent POs.
  - OD-04 (SR2-04): the authoritative units list is the UOM column of the Material codes table on the Inventory
    tab; unit pickers and labels use that list. Schema: `material_code.unit_of_measure` is the source; other
    `unit_of_measure` columns (for example `estimate_cost_line`) take values from it.
  - Amendment 2026-11-23 (OD-51, inbox 2026-11-22 evening "two new owner features + rules"; amends OD-04): the units
    list (ea, box, kw, cnt, ft, kit) is company-editable, so companies add their own units; "kit" is added (PO 1042
    racking kit). PO and estimate builder units pick from it. Proposed: a `unit_of_measure` list table (code, label,
    active, sort order; inactive units stay on old documents) that `material_code`, PO lines and
    `estimate_cost_line` reference. The owner named Area 9 or 21; placed in Area 9.
  - Inbox input 2026-11-23 (Material forecast page, 2:20 AM; Area 8 §12.3): `purchase_order` has only `issue_date`
    in `po_ap_matching_design.md` §3; the forecast needs `purchase_order.expected_on` with an optional per-line
    override, read for open quantity not yet received. Otherwise the page is a view only.
  - Inbox input 2026-11-22 (v1.1 field scope; owner 12:41 PM): a field material request from the job feeds the
    pull-ticket queue; stock is reserved only when the pull ticket is created. Who can create a request is open
    for the wireframe review. **Decided 2026-11-22 (owner, design chat gap list): the PM creates material
    requests.**
- **Area 20, Capture inbox:** item 23 (CAP-04): Allow sender covers that sender for that capture address only. An
  already rejected message needs a one-click Reprocess to enter review. Rejected and deleted messages are kept
  30 days, then purged (company setting `capture_rejected_retention_days`, default 30).
- **Area 20, Connections (added 2026-11-23; design chat gap list item 9; Area 8 §12.2):** the weather forecast
  stays on (owner 11/22). It reads the job site address (`project.site_*`) and is fetched over the network
  (twice a day, read-only, per the mockup); a company setting turns it on. Design the connection, its failure
  message and what the desktop app does offline.
- **Area 16, Custom fields (added 2026-11-23; design chat gap list item 4):** a custom field of type User, and Lead
  scoping of custom fields (Lead is not yet a custom-field target).

## Owner decisions 2026-11-22 for the design queue and later phases (no Phase 2.9 schema effect)

- Items 1 and 2: Materials round 2 and the Whole-app decisions brief build stages 2–4, stopping after each stage for
  independent QA only.
- Item 3: Playbook stage 3 waits for Phase 5. Phase 5 note: "propose page edits from evidence" and "Playbook text is
  sent to the AI provider" conflict with the 11/17 AI privacy rule; resolve them then.
- **Added 2026-11-24 (mockup audit item 10; no decision now):** the mockup Connections page offers "Let the
  assistant read company records", which conflicts with the 11/17 AI privacy rule: AG4 (extraction sends only the
  chosen file or pasted text), AG7 and G4 (analysis sends only locally computed figures, under the AG3 warning and
  the data-sharing opt-in). Resolve it in Phase 5 with the Playbook items above.
- Item 4 and OD-01: one more Shared Run 1 release-gate round, run after the open Shared Run 1 fixes pass.
- OD-05 (SR2-01): a calendar click selects the row and opens its details; the selection clears on reload.
- OD-06: 1280 px stays the supported minimum width; the normal header and Assistant offsets count as full-window for
  Bank rules.
- OD-12: Settings Jump to scrolls, then shows the accent focus ring on the target card for about 2 seconds, above
  the card shadow.
- OD-14 (F): the Team company menu is accepted with the layout as shown: company switcher under the logo, user
  menu (My profile / Edit layout / Sign out) at the bottom. Fix: at 1280 px with the Assistant open, page header
  buttons wrap or collapse into a ... menu. Correct the F description: the switcher stays at the top and did not
  move into the user card.

## Earlier planning stop (2026-11-21): Area 4 plan review

Mark's 2:50 AM answers close Area 4 Q1 and Q5. Read `docs/replan_2.9/area_4_owner_pay_applications_billing_cycles.md` with Q2–Q4 and billed-to-date timing. The owner-approved workflow has no separate customer-approval withdrawal action: Reject before invoice posting cancels the linked invoice draft, preserves the approved pay app version and starts the next version; after posting, use a linked reversal and a new version. The approved invoice draft carries immutable certified amounts, while all other invoice-draft fields stay editable until posting. Billing creates; the PM reviews, sends and records the customer's answer; retainage release stays with the Controller or delegated accounting approver.

(Answered 2026-11-22 by owner_decisions item 17; see Area 4 §5 and §7.) Decision brief for Mark and Area 18: Mark's policy choices still needed are the business roles allowed to adjust a draft pay app, unlock a locked pay app, and create an explicit replacement invoice draft. Area 18 owns mapping the chosen roles to permission codes, sensitivity, project scope, caps and templates. Existing seeds include `payapp.create`, sensitive `payapp.approve`, `retainage.release`, `invoice.create`, `invoice.send`, and `invoice.void`; the Controller template has `retainage.release`. The 2:50 AM decision assigns the PM to review, send and record the customer answer and keeps retainage release with the Controller/delegate.

The Area 5 handoff below still applies.

## Earlier planning stop (2026-11-20): area 5 drafted for Mark

Review `docs/replan_2.9/area_5_invoices_credit_memos_statements_customers.md` §§0–7.
Nine areas are approved. Area 5 is a draft with open questions in §7 as narrowed by §8, including dependencies on
areas 1, 4, 14 and 19. The 5:00 and 5:15 PM decisions close Q5. Area 5 §5.3 lists the four inputs still needed
from Area 4. Q2–Q4 are also closed (§8.2). Owner approval creates and claims one linked invoice draft and locks
the certified pay app. Issue/Post remains in Area 5 (§5.3). Q6–Q7 product rules are approved in §8.3.
Q1 and Q8 product rules and follow-ups are approved in §8.4. Q9 and Q10 are closed in §8.5. Review retention
duration for companies without a policy and the tax, Payments/AR, Banking, Security, Approvers and source
dependencies listed in §8.5. Area 4 retains its
§5.3 handoff, including billed-to-date timing and void/reissue effects.
Next action: Mark reviews the Area 5 plan for full plan approval. Q1–Q10 product decisions are approved.
Baseline work waits for approval of the full replan.

## Earlier planning handoff (2026-11-20): service-quote decision reconciliation

- State: planning-only reconciliation of the confirmed 2:10 PM, 2:20 PM and 2:30 PM service-quote rules into areas
  6, 7, 8, 15 and the existing area 17 report rule. Areas 5 and 14 have no Phase 2.9 plan document yet; their
  ownership boundaries and required inputs are handed off below. The internal `contract` row remains derived from
  the signed quote revision. No code, migration, baseline or test file was changed; no test, stage, commit or push was
  run. Existing unrelated working-tree changes and untracked paths remain preserved.
- Rules reconciled: one estimate links to exactly one lead or case; case problem edits sync during drafting and quote
  content freezes when printed; service type defaults the cost enterer/pricer, PM, reusable payment term and quote
  validity; cost enterer and PM stay separate with Solo/unset-controls PM defaulting to cost enterer; send-backs
  return to the estimate submitter with append-only history; signing freezes billing kind, price, terms, tax details
  and the customer-signed tax-inclusive total; signed upload records optional repair groups as Accepted or Declined
  and only required plus Accepted lines determine the signed amount; jobs and contract rows are created only on
  signed-quote upload, while a case enters In progress when cost work starts; Warranty and goodwill use separate cost
  destinations, with the `service_goodwill` System account role and separate reports; unrelated upsells are a human
  new-estimate rule with no schema enforcement.
- Amendment 2026-11-22 (tax on signed quotes; Area 5 Q12): Decided 2026-11-22 (owner; owner_decisions_2026-11-22
  "Planning-session follow-ups", 12:47 PM; Area 5 Q12), replacing the 2026-11-20 2:10 PM rule that signing freezes tax
  details and a tax-included signed total: signed quotes and estimates carry a pre-tax price, and the PDF shows an
  "Estimated tax" line; each line keeps its taxable/exempt flag; actual tax is calculated on each invoice at the
  job-site rate in effect at invoicing; the item-22 tax override (Accountant+, with a reason) applies to all lines,
  including signed-quote lines; a tax-rate change needs no change order. The customer-signed tax-inclusive total above
  is superseded; the customer signs a pre-tax price.
- Blockers/open questions: later-area implementation details remain for area 5 invoice line/tax carry-forward and
  area 14 approval routing to `approval_request`'s submitter. Area 18 now defines the configurable
  `service_goodwill` System account mapping. The four review findings are corrected in areas 6, 7, 8 and 15:
  accepted work drives the signed totals and original budget, warranty and goodwill use distinct destinations,
  and estimate cost work starts the case transition.
- Next action: planning review of the amended sections and later-area handoffs; then select the next area with the
  owner. Do not start baseline or code work until the whole replan is approved.

## Historical stop (2026-11-20): Git hook repair planning snapshot

- State: on `main`; local `core.hooksPath` is `.githooks`. The hook, settings and `CLAUDE.md` changes were already
  staged. `tests/test_commit_hook.py` now covers the tracked Git hook instead of the removed Claude PreToolUse entry;
  its focused run passed (68 tests). The `.codex/hooks.json` and `.codex/hooks/` paths remain untouched and untracked.
- Test outcome: with default `%TEMP%`, the focused ACL test failed and the full suite had 4,209 passed, 2 skipped,
  1 failed in 315.94 s. A later dedicated-basetemp attempt found `PYTEST_ADDOPTS` unset but passed a Windows path with
  backslashes. Pytest parsed them as escapes and created the test temp under the repo at
  `C:\Users\marka\StrataLedger-clean\Usersmarka.pytest-strataledger-acl`; the focused test failed its exact-mask
  assertion there (1 failed in 0.15 s). That generated directory was removed. No ACL inspection or full-suite run
  followed. The original `%TEMP%` still inherits the recorded `Modify, Synchronize` ACEs for `CodexSandboxUsers` and
  SID `S-1-5-21-3876112204-1666981215-754291341-1030728988`. The ACL test was not changed or skipped.
- Python: 3.11.9, pytest 9.2.0 and `xdist` import passed under the non-admin `marka` identity.
- Blocker/open question: the dedicated-basetemp attempt did not reach the proposed path because `PYTEST_ADDOPTS`
  consumed the Windows backslashes. No ACLs or pytest settings were changed.
- Next action: rerun with the dedicated path written with forward slashes in `PYTEST_ADDOPTS`, confirm the focused
  test directory is actually under `C:\Users\marka\.pytest-strataledger-acl`, inspect its ACL read-only, then run the
  full suite with the same option. Stop on any failure. Only after a full pass, verify the commit-launching process
  inherits the basetemp option, stage the approved paths, commit normally on `main`, verify the hook record timestamp,
  and push. **No commit or push has occurred.**
- Follow-up (2026-11-20): the forward-slash preflight resolved exactly to
  `C:/Users/marka/.pytest-strataledger-acl`; the target was absent before the run. The focused ACL test passed (1
  passed), but read-only inspection found an inherited `CodexSandboxUsers` ACE with mask `1179817` on the test
  directory, not the expected full-control mask `2032127`. The ACL gate failed, so the full suite was not run. This
  pass applies only to the dedicated basetemp and does not repair `%TEMP%`'s inherited ACEs. Blocker: investigate the
  dedicated directory's inherited ACE without changing the test or ACL. Next: planning review of the service-quote
  amendments in this step, then resume ACL diagnosis before any later commit.
- Historical service-quote amendment review (2026-11-20, before follow-up `2b98b15`): commit `1e912fa` was pushed. The step reviewer found that
  the tax-to-invoice sentence belongs only in the later-area handoff and that the estimate schema needed an explicit
  PM field. Those points are corrected locally; the report rule is also placed under area 17 section 4.4. Blocker:
  the requested single commit is already pushed, so a follow-up commit would exceed that limit and amending it would
  require a force-push. The stop applied at that review. See the current planning handoff above.

Overwritten 2026-11-20 (CLAUDE.md section 8) after the owner approved area 7. Start a fresh session (MR1) and read
.claude/rules/workflow-standards.md: done, the review gate, fix mode.

## Where 2.9 stands (owner decision 2026-11-17; docs only so far)

- Working doc: `Strata_Teams\schema_replan_2026-11-17.md` (21 areas; planning keeps its status column, so this repo
  never edits it). Owner rule 2026-11-18: the mockups define the features; the schema follows them.
- **Owner-approved: 10 of 21 areas, plus the report contracts** (area 5 added 2026-11-22 2:15 AM; area 4 is ready for approval).

  | Area | Doc | Commits |
  |------|-----|---------|
  | 18 Admin, security, audit, attachments | docs/replan_2.9/area_18_admin_security_audit.md | 6e9cdf8, 2a3b497, d38e11e; dated amendment lines from areas 13, 12, 10, 17, 8, 15, 6 and 7 (seeded codes 111; 115 with the 2026-11-22 §8 amendment) |
  | 13 Close and locks | docs/replan_2.9/area_13_close_and_locks.md | dfb26b6, dac81ec (+ amendment lines from areas 12, 10, 17 and 7) |
  | 12 Bank and reconciliation | docs/replan_2.9/area_12_bank_and_reconciliation.md | d9032ea, a837bc1, d239f32 |
  | 10 Prepaid, deferrals, reclass, period balance summary | docs/replan_2.9/area_10_prepaid_deferrals_reclass.md | 3f79eb3, 77938bc, a46501a (+ amendment line from area 7) |
  | 17 Field registry, list layouts, report builder, KPIs, measures | docs/replan_2.9/area_17_fields_layouts_reports.md | 809fb22, fded8c4 (+ amendment line from area 7) |
  | 8 PM: stages, service types, schedules, change orders, forecast | docs/replan_2.9/area_8_pm_schedules.md | 3d15762, c835d20 and the approval commit b9ff295 (+ amendment lines in area 18; amendment lines from areas 15, 6 and 7) |
  | 15 CRM: leads, activities, cases, comments, routing | docs/replan_2.9/area_15_crm.md | 2237b63, 03477c0, 3b8108b and the approval commit (+ amendment lines in areas 8 and 18; amendment lines from areas 6 and 7) |
  | 6 Estimates, contracts, pricing, T&M rates, contract templates | docs/replan_2.9/area_6_estimates_contracts.md | 2c82148, d297397, b0bea27 and the approval commit (+ amendment lines in areas 8, 15 and 18; amendment lines from area 7) |
  | 7 Jobs, budgets, cost codes and cost types, dimensions, operating plan, WIP | docs/replan_2.9/area_7_jobs_budgets_cost_codes.md | 7bab6f0, 7ebcd4f, 8b68381, d582c7e, 64519fd and the approval commit (+ amendment lines in areas 6, 8, 10, 13, 15, 17 and 18; seeded codes 111; shipped Service manager template) |
  | 5 Invoices, credit memos, statements, customers | docs/replan_2.9/area_5_invoices_credit_memos_statements_customers.md | approved by the owner 2026-11-22 2:15 AM; §9 dated amendments 2026-11-22, all questions decided; ready for full-plan approval |
  | Report builder service contracts (input to area 17; amended by it) | docs/contracts/reports.md | 3d237d3, 221b996, e869ecf, fded8c4 |

- **Todo (11):** areas 1-4, 9, 11, 14, 16, 19, 20, 21 (area 4 drafted, ready for approval); the owner chooses the next. Only owner-approved areas are built;
  an area still todo or drafted is not, and PROPOSED items are not built as final.
- All held schema changes land in the two baselines in one pass, tests first, after the replan is approved. Before any
  baseline edit, list the development databases it blocks (CLAUDE.md section 5.2) and ask before rebuilding (rule 9).
  Nothing in the baselines or code has changed for 2.9 yet.

## Next: an area chosen by the owner

Ask the owner which todo area to draft next (areas 1-5, 9, 11, 14, 16, 19, 20, 21). Draft it in
`docs/replan_2.9/area_<n>_<name>.md` in the layout of the area 13 doc (0 Summary table; per topic current state with
file:line, decided with source, proposed schema, how it lands in the baselines, effect on services and tests, tests to
write later; row version and audit; conflicts flagged; questions for the owner, multiple choice, recommended option
first; open items), from the area's row and "Inbox inputs" in the working doc. Cite "C21" style codes as sections of
`CODE_CHANGES_NEEDED.md`, not decision codes. Every area prompt lists "Checked against: <shared_decisions entry
times>" (owner 2026-11-20 12:56 AM), and the area's report repeats it. A later owner decision that replaces an
earlier one is added as a dated amendment line, and the replaced items are marked "Withdrawn <date> (owner <time>)"
beside them, never deleted (area 7 fix 3).

## Handed to later areas by the approved ones (open items, not decisions)

- **Area 1 (Payments, deposits, undeposited funds; not yet drafted [Update 2026-11-24: drafted, Area 1 §1 to §6 place every input below]; Mark triage 2026-11-21 1:45 AM — must-fix inputs):**
  - Invoice status counts only posted applications effective on or before the as-of date. Draft receipts, draft credit memos and future-dated applications never make an invoice Paid. Add `test_invoice_status_uses_only_posted_applications_as_of_date`, covering each case. `tests/test_payments.py::test_releasing_a_draft_source_allocation_posts_no_entry` (around line 381) currently expects Paid after allocating a draft source; flag that expectation as wrong and replace it in the rebuild with the non-Paid status assertion.
  - Require an operation ID on each application call; retrying the same ID returns the original result without another allocation, following the 2026-11-20 5:15 PM billing-claim retry principle. Test `test_allocation_same_operation_id_retry_returns_original_result`.
  - Store allocation release-effective date and the replacement invoice version link. Voiding a paid invoice releases its applications back to the original receipt, which stays posted. Reposting under the same number uses one stable invoice identity because `invoice_sales_number_unique` reserves a sales number on one row today. Test `test_allocation_release_records_effective_date_and_replacement_invoice_version`, `test_paid_invoice_void_releases_allocations_to_posted_receipt`, and `test_same_number_repost_uses_stable_invoice_identity_after_number_reserved`.
  - Either support the allocation deferral target end to end or remove it from the schema. Test `test_allocation_schema_targets_match_supported_allocator_targets` against the selected design.
  - Use the approved close model: Payments received or Bill payments area lock plus the affected AR or AP account locks, never the legacy Sales or Purchases areas. Test `test_payment_locks_use_payments_received_or_bill_payments_area_and_ar_ap_accounts`.
  - Build service-owned receipts, deposits and deposit lines; preserve date paid separately from date cleared; include card fees; and provide refund, write-off and statement send/posting services. Test `test_receipt_posting_runs_through_service`, `test_deposit_and_deposit_line_posting_runs_through_service`, `test_date_paid_and_date_cleared_are_distinct`, `test_card_fee_posts_through_payment_service`, `test_refund_posting_runs_through_service`, `test_writeoff_posting_runs_through_service`, and `test_statement_send_and_retention_run_through_service`. Keep the four refund/write-off authorities separate and sensitive, with refund/write-off approvals OFF by default; test `test_refund_writeoff_authorities_are_four_separate_sensitive_permissions` and `test_refund_writeoff_approval_defaults_are_off`.
  - Policy to confirm with Mark while drafting: ordinary overpayments remain unapplied credits on customer AR; only an explicitly chosen job deposit posts to Customer Deposits by account role. Test `test_ordinary_overpayment_stays_unapplied_on_customer_ar` and `test_explicit_job_deposit_uses_customer_deposits_role`.
- **Area 1/2:** payment record and receipt destination (area 12 Q20 A keeps deposits and transfers in 12); pay run
  posting shape (one bank line per payment assumed); `payment.method` values for ACH, wire and card.
- **Area 3/5:** a job per bill and invoice line (area 10 F8); the bill void calls `deferrals.void_for_bill`.
- **Area 7/8 (area 7 done, approved 2026-11-20):** job cost reads GL lines carrying a job (area 7 section 7);
  `project.manual_*` columns (area 7 section 1.3); WIP schema now, the WIP service with v1.1 (area 7 Q18 A); area 8
  reuses area 13's work week and holidays (area 13 Q14 A).
- **Area 7 (from area 17; done, approved 2026-11-20):** `operating_plan_version` and `operating_plan_line`;
  `project_budget` for the `job_budget` compare; area 17 adds `saved_report.split_by`.
- **Areas 6, 8, 15, 16 (from area 17):** the Records source tables (`lead`, stage and status history, `activity`,
  `service_case`, the lead-to-job link, the sales rep on the contract) and `custom_field_def.record_type` 'Lead'; until
  they exist those sources are not offered (Estimates and Jobs can ship first).
- **Area 9 (Materials, POs, inventory, warehouse; not yet drafted; must-fix inputs):** keep warehouse and
  direct-to-site receipt flows distinct. Receipt detail reads the saved receipt and its original posting; preview
  stays read-only and never marks a receipt or posting posted. Test
  `test_receipt_detail_reads_saved_receipt_and_original_posting`.
  - Warehouse: a pull-ticket issue reduces on-hand stock, releases the reservation and posts its own linked job-cost
    entry exactly once; a retry with the same operation ID returns the first result. Test
    `test_pull_ticket_issue_posts_stock_reservation_and_cost_once` and
    `test_pull_ticket_issue_retry_same_operation_id_no_double_post`. A matched bill posts its own ledger entry to
    clear the original receipt accrual. Test
    `test_matched_bill_posts_own_entry_clearing_original_receipt_accrual`.
  - Direct to site: a receipt posts job cost directly and links that posting to the saved receipt, without a
    warehouse pull. Test `test_direct_to_site_receipt_posts_linked_job_cost_without_warehouse_pull`.
  - Direct job receipts and pull-ticket issues/returns resolve the job-materials account by role, never by number.
    Test `test_materials_postings_resolve_job_materials_role_not_number`.
  - STOCK-03 Decided 2026-11-22 (owner; owner_decisions_2026-11-22 item 19): a return credits job cost on the
    account the original issue used, even if the mapping has changed since. Schema: each issue line stores the
    account it posted to, and the return reads that stored account. Test
    `test_stock03_return_after_mapping_change_uses_original_issue_account`.
  - Also add an item table for `reclass_line.original_item_ref` and the warehouse close checks (area 13 section 2.3).
- **Area 11 (Fixed assets and loans; not yet drafted):** build an asset register and depreciation service that
  hold each asset, its schedule and its disposal entry; asset-disposal approval type already exists in
  `migrations/001_company.sql` near line 1126 but has no service workflow. Test
  `test_asset_disposal_reads_saved_asset_schedule_and_entry`. Refuse unknown asset IDs without fallback and test a
  mixed valid/unknown selection: show the exact missing ID and block the whole disposal, leaving every selected
  asset undisposed (`test_asset_disposal_unknown_id_refused`,
  `test_asset_disposal_mixed_valid_unknown_ids_refuses_without_substitution`). Run catch-up depreciation through
  the chosen disposal date before calculating book value and gain or loss:
  `test_disposal_catch_up_depreciation_through_disposal_date`.
  Persist one durable disposal result linked to its exact disposal posting and any separate catch-up entry. Register,
  asset detail, schedule and GL use those same saved IDs; exact retry creates no duplicate disposal or posting:
  `test_disposal_exact_retry_adds_no_duplicate_posting`.
  Carry ASSET-04 into the regression queue: List and Schedule share filters and selected dates; monthly totals tie to
  posted depreciation; every posted cell opens its exact entry; include a disposal during the range and verify any
  separate catch-up entry link. Test `test_asset_schedule_monthly_totals_tie_to_gl_with_exact_entry_links_and_disposal`.
  Refuse impossible dates before posting as always-on integrity. Use Area 13's period close, the `Fixed assets and
  depreciation` posting area, and account locks for the affected entry accounts. Test
  `test_disposal_respects_period_area_and_account_locks`.
  Use Area 14's configured asset-disposal approval dependency only when approval is enabled (controls OFF by
  default); test `test_disposal_approval_uses_area14_only_when_configured`.
  Proceeds Decided 2026-11-22 (owner; owner_decisions_2026-11-22 item 20; ASSET-02/03/04): (1) a scrap disposal
  can have $0 proceeds; (2) negative proceeds are always refused, and removal costs are a separate expense; (3) a
  lump-sum sale is split per asset, and when total book value is zero the split defaults by original cost, is
  editable and must sum to the proceeds (for example, a $500 sale across two fully depreciated assets). Schema:
  one proceeds row per disposed asset (asset ID, proceeds cents >= 0, allocation basis Book value/Original
  cost/Edited). Test
  `test_disposal_accepts_zero_proceeds_for_scrapped_asset`, `test_disposal_rejects_negative_proceeds` and
  `test_disposal_positive_lump_sum_with_zero_total_book_value_requires_per_asset_allocation`.
  Reuse the prepaid schedule grid and design depreciation and loan lock areas.
- **Area 14:** `pending_approvals` beyond journal entries; the approvals the new codes need.
- **Area 21 (COMPANY-01 through COMPANY-03; planning-only):** test the round trip Westline Solar & Build →
  Westline Arizona LLC → Westline Solar & Build, including reload. Use distinct settings and report data in both
  companies; verify selected company, dashboard, Area 20 calendar settings, Area 17 report data and export header
  all follow the active `company_id`. Test `test_company_switch_roundtrip_uses_active_company_id_after_reload`.
  Failed access denial and destination preparation each leave the current company usable and write no successful-open
  event for the target: `test_company_switch_access_denial_keeps_current_company_and_logs_no_target_open`,
  `test_company_switch_destination_prepare_failure_keeps_current_company_and_logs_no_target_open`. Carry Area 18's
  rule that every user's successful open writes master `auth_event` type `Company opened` with the actual company ID:
  `test_successful_company_open_logs_actual_company_id_for_every_user`.
  When a successful switch actually closes the outgoing company, run its existing
  `ledger_verify.checkpoint_on_close` behavior; failed opens leave that company open. Test
  `test_company_switch_checkpoints_outgoing_company_only_on_actual_close`.
  Decided (owner, shared_decisions 2026-11-21 10:20 AM): when the destination company is ready, the switch continues
  if the outgoing company's checkpoint fails or is skipped; that outcome is recorded and reported separately against
  the outgoing company, and Signed is shown only when the service confirms it was saved. A failed destination open
  keeps the original company selected and usable. Also retain the open payments limits (30 and 180 days) as policy records (area 12 Q16 A),
  `row_version` and stale-save refusal on `company_settings`, area 17's general notification feed **[Amendment 2026-11-25: Area 20 §7]** and whether saved
  views can be shared.
- **Areas 12, 13 and 10 and 17 build items for later phases:** (area 17: `field_registry`, `list_prefs`,
  `report_layouts`, `report_formulas`, `report_sources`, `saved_reports`, `packs`, `report_run`, `report_records`,
  `report_combined`, `kpis`, `measures`, `report_schedules`, `report_output`, and the `perf` test.)
- **Areas 12, 13 and 10 build items:** `bank_feed.py`, `reconciliation.py`, `banking.py`,
  `period_locks.py`, `close_tasks.py`, `deferrals.py`, `reclass.py`; the static test that every journal-writing service
  calls `period_locks.check_open`.
- **Still open from STOP C:** custom field columns `help_text`, on board card, shown from stage, job types (area 16, with
  CODE_CHANGES 27); custom fields refuse Estimate until an estimate service exists (area 6); RI1 (decided, not built).
  Item 4 of the STOP C list (area locks on custom-field edits) is answered by area 13 Q6 A.
- Open question 7 (System context and Import-origin entries in `post_journal_entry`): area 10 Q7 A decides it for the
  deferral runner (origin System, no approval, no date warnings, needs `deferral.manage`); the posting work builds it.

## Handed to later areas by area 8 (open items, not decisions)

- **Area 7 (done, approved 2026-11-20; area 7 section 1.3 writes the `project` DDL, amendment line in area 8 section
  7):** the area 8 columns, `status` dropped, `project_budget.revision_id`, budget totals derived (Q5 A),
  `project.row_version`, the `job_budget` compare.
- **Area 6 (done, approved 2026-11-20; amendment lines written in area 8):** `rate_card`, `contract_milestone`, new SOV
  lines from an approved change order; still open: the contract's completion date as the schedule's contract date.
- **Area 15 (done, approved 2026-11-20; Q13 B dropped `case_job`):** reuses `crew` and `calendar_item` times for busy
  checks; defines `service_case`, the lead stage history twin and the lead-side stage role 'Lost'; the case Resolve
  prompt.
- **Areas 3, 4, 5, 9:** a warning naming the hold on costs, POs and invoices of a held job (never a refusal);
  `subcontract_id` on schedule tasks (area 4); committed amounts for the forecast figures (areas 4 and 9).
- **Area 14:** the change order approval chain (default OFF) beside the customer approval.
- **Area 16:** per-stage custom fields and job type scoping (`custom_field_def`); stage guidance is area 8's.
- **Area 20:** sending final bill requests and share-schedule emails; the email log id.
- **Area 21:** the company calendar query over tasks, milestones and `calendar_item`; `row_version` on the new
  `company_settings` columns (controls and the crew label).
- **Build items for later phases (area 8):** `job_stages.py`, `job_close.py`, `job_hold.py`, `schedule_templates.py`,
  `job_schedules.py`, `work_calendar.py`, `calendar_items.py`, `change_orders.py`, `forecast.py`.

## Handed to later areas by area 15 (open items, not decisions)

- **Area 6:** `estimate.lead_id`; `estimate.contact_id` nullable before signing; `contract.sales_rep_user_id`;
  contract signing calls into `leads.py` (the lead's Won); the Cancellation case type's "Cancel the contract".
- **Area 7 (done, approved 2026-11-20):** `project.sales_rep_user_id`; `project.source_case_id`.
- **Area 5:** the `lead_contact` hand-off at signing; the contact-person table.
- **Area 14:** approvals on sales stage moves (default OFF).
- **Area 16:** Lead custom fields by service type and stage; no custom fields for service cases (owner 3:09 AM, Area 16).
- **Area 20 (Connections; planning-only CONN-01 through CONN-03):** verify an address-only calendar setting edit
  reaches Review changes, requires a reason, Cancel discards it, Apply saves it, reload retains it and the next
  event uses that destination; validate it differs from the company's actual sending mailbox. Test
  `test_calendar_address_only_review_reason_cancel_apply_reload_and_next_event_destination` and
  `test_calendar_address_must_differ_from_actual_sending_mailbox`.
  Create, update, cancel and retry invitations with one stable event UID and the correct iCalendar sequence: create
  starts at SEQUENCE 0; each successful update or cancellation increments once; a retry does not duplicate or
  increment twice. Tests: `test_calendar_invite_create_uses_stable_uid_sequence_zero`,
  `test_calendar_invite_update_keeps_uid_and_increments_sequence`,
  `test_calendar_invite_cancel_keeps_uid_and_increments_sequence`,
  `test_calendar_invite_retry_does_not_duplicate_or_increment_sequence_twice`.
  Delivery status comes from the recorded send result, never from a saved setting alone:
  `test_calendar_delivery_status_comes_from_recorded_send_result`. Keep Download .ics available without a
  connected mailbox: `test_ics_download_fallback_available_without_connected_mailbox`. Test real mailbox test,
  reconnect and disconnect outcomes with the actual sending identity:
  `test_mailbox_test_reports_actual_sending_identity`, `test_mailbox_reconnect_records_connection_outcome`,
  `test_mailbox_disconnect_records_state_and_keeps_ics_fallback`. One-way invitations go only to the configured
  company calendar address. Decided 2026-11-22 (owner; owner_decisions_2026-11-22 item 24; CONN-03 and the
  PMSCHED-04 notification branch): events already sent keep their original destination for updates and
  cancellations; only new events use the new address. Schema: each sent event stores its destination address with
  its UID and sequence. Test `test_calendar_address_change_keeps_sent_event_destination_for_updates_and_cancels`.
  Area 8 handoff: PMSCHED-04 schedule notifications follow the same rule.
  Keep backend work behind Phase 2.9 approval.
- **Area 21:** the notification feed; `last_seen_at`; the CRM alerts. **[Amendment 2026-11-25 (planning call 12:37 AM): the notification feed and `last_seen_at` are now Area 20 §7; Area 21 keeps the calendar query and `row_version`.]**

## Handed to later areas by area 6 (open items, not decisions)

Area 6's amendment lines are already in areas 8, 15 and 18; these are the items that are not.
- **Area 7 (done, approved 2026-11-20):** `cost_type` and `cost_code.cost_type_id`; the budget from the summary by cost
  code at Mark signed; `project.sales_rep_user_id`; `project.source_revision_id`; estimate lines on leaf codes (Q7 A,
  amendment line in area 6 section 3.3).
- **Area 5:** the create-customer service and contacts at Mark signed; the draft (unposted) deposit invoice, credit side
  by role `customer_deposits`; `contract_milestone.invoice_id`; T&M monthly drafts at the contract's frozen rates and
  the near-not-to-exceed warning (with area 19); whether the T&M revenue account needs a system role. Carry only the
  required and Accepted optional quote lines, their frozen tax-rate identity/name/rate, taxable base and tax cents,
  and the signed revision's pre-tax, tax and tax-inclusive total onto the invoice. The internal contract row and
  amount stay derived from that signed quote.
- **Area 9:** `material_code`; until it exists `estimate_cost_line.material_code_id` is a plain integer.
- **Area 14:** the Estimate policy, `sales_authority_limit` routing, the Contract policies (wording changes and contract
  cancellation approval), all OFF by default. Define service-quote send-back routing to `approval_request`'s submitter
  (PM or rep); pass that target to area 6 and retain append-only from/to status, from/to holder and reason history.
- **Area 19 (Payroll import; not yet drafted, planning only):** Payroll and Approvals open the exact same saved
  batch ID, and required human review covers the exact mapped rows and source-row links that posting will consume.
  Mandatory human review stays in force whether Area 14's configured payroll approval is OFF or ON; when ON, that
  approval is an additional gate. Tests: `test_payroll_and_approvals_open_exact_saved_batch`,
  `test_human_review_covers_exact_mapped_rows_that_post`, `test_payroll_post_requires_review_with_area14_approval_off`,
  `test_payroll_post_requires_review_and_area14_approval_when_configured`.
  Any row, mapping or batch change after review invalidates that review (and any approval) and blocks posting until
  the current rows are reviewed again: `test_changed_payroll_batch_after_review_requires_new_review`.
  A retry after lost confirmation with the same operation ID returns the original result and creates no duplicate
  labor rows or ledger effects, including any applicable accrual and reversal:
  `test_payroll_retry_after_lost_confirmation_no_duplicate_rows_or_entries`.
  Use a synthetic provider file to reject invalid dates, hours, amounts and unresolved employee, job or cost-code
  references; reconcile provider control totals; preserve original source-row links; and verify job cost lands on
  the mapped job and cost code. Tests: `test_payroll_import_rejects_invalid_dates_hours_amounts_and_unresolved_references`,
  `test_payroll_provider_control_totals_reconcile_to_mapped_rows`,
  `test_payroll_labor_rows_link_original_source_rows`, `test_payroll_job_cost_uses_mapped_job_and_cost_code`.
  Only posted import hours reach v1 T&M billing at the frozen rates:
  `test_tm_billing_uses_only_posted_payroll_import_hours`.
  Download source returns the actual file for the selected batch and writes the authorized audit event:
  `test_payroll_download_returns_selected_batch_source_and_audits`. Source-file access and retention policy remain
  unresolved for Mark. **[Update 2026-11-25: closed for payroll by owner A19-Q2 (2:20 PM): the file is kept as long as the entry; download needs `payroll.view` and is audited.]** Keep backend work behind Phase 2.9 approval.
- **Area 4:** pay apps read the contract's SOV and cost codes, retainage and the deposit-remaining balance.
- **Area 16:** custom fields on Estimate (on `estimate`, Q25 A); the refusal in `custom_fields.py` is lifted with
  `estimates.py`. **Area 17:** `src_leads_estimates` field ids and the rep on the contract. **Area 20:** the proposal
  email and its log id. **Area 21:** notifications (PM assigned, Ask the rep, send back, the 3-day expiry reminder) **[Amendment 2026-11-25: now Area 20 §7]** and
  `row_version` on the new `company_settings` columns.
- **2.8 (backups):** the company logo's `storage.py` key (`company_branding.logo_storage_key`) is included in the
  company backup and restore, like attachments, and recorded in `backup_run`.
- **Build items for later phases (area 6):** `estimates.py`, `contracts.py`, `pricing.py`, `rate_cards.py`,
  `contract_templates.py`, and one PDF renderer service (the library choice is for the build step).

  Amendment 2026-11-22 (tax on signed quotes; Area 5 Q12): invoicing carries the signed pre-tax price and each line's
  taxable/exempt flag, not frozen tax-rate identity or a tax-inclusive total; tax is calculated at the job-site rate
  in effect at invoicing.

## Handed to later areas by area 7 (open items, not decisions)

Area 7's amendment lines are already in areas 6, 8, 10, 13, 15, 17 and 18; these are the items that are not
(area 7 section 13).
- **Area 8 (still open):** `service_type` default dimension values (C62 "starts with profit and cost center") as a
  `service_type_dimension` table, and a default `poc_method`; the transfer and CO services call area 7's budget
  functions; `job_forecast_line` seeding moves into `job_budgets.set_original`.
- **Chart template (`templates/coa/construction.csv`, baseline pass):** the cost type roles of Q20 A (`job_labor`
  5010, `job_materials` 5030, `job_subcontract` 5040, `job_equipment` 5050, `job_overhead` 5070) and
  `warranty_expense` on 5080; no row carries `contract_cost` today although `company_settings.contract_cost_acct_id`
  exists. The shipped cost code list `templates/cost_codes/construction.csv` is new.
- **Areas 3, 4, 5, 9, 19:** every cost and invoice service calls the budget control and the JD1 resolver (no draft
  check, Q1); committed amounts (4, 9); the PO's inline over-budget transfer calls `add_transfer_rows` (9); T&M lines
  default Billable with the job's markup (5); `is_prevailing_wage` and WH-347 (19); the customer's job-sites list and
  tax rate from the site (5).
- **Area 16:** job custom fields per stage and service type.
- **Area 21:** entities inside one company file (which entity a job belongs to is not designed in area 7);
  `row_version` on the new `company_settings` columns; the notification for "Enter budget".
- **Area 18 (done in section 4.2):** `service_goodwill` is a configurable System account role used by area 7's
  Service overhead destination; each company maps it to an account, with no account number hard-coded. Warranty and
  goodwill remain separate report destinations even if both map to the same account.
- **Imports (backlog 4):** cost code and dimension paste lists use the Import service; dimension tables for
  `time_entry` and `staged_line` (JD1).
- **Raised in the area 7 fix reports, not yet decided by the owner:** a case quote's service type and sales rep
  (no lead to copy them from; area 15's `service_job_type_id` is the default service type); a no-charge quote on a case
  with no job (no original job for the Warranty roll-up); the Service manager template's scope All with
  `project.manage`; a Service manager cannot record payments (`payment.receive` stays Accountant-only, owner 3:38 AM).
- **Build items for later phases (area 7):** `jobs.py`, `job_budgets.py`, `cost_codes.py`, `dimensions.py` (with the
  resolver), `operating_plans.py`, `job_cost.py`, `wip.py` (v1.1), the cost code template loader.

## Commit hook (owner 2026-11-19; changed in 887da07)

`.claude/settings.json` runs `.claude/hooks/pre_commit_pytest.py` before any `git commit` (timeout 1500 s).
- **Docs only:** when every staged file is under `docs/`, the hook skips the suite, prints one line, `docs only: suite
  skipped (N files)`, and writes it to `strataledger-commit-hook-last-run.txt` in the system temp folder (the same file
  that holds the suite's last line).
- **Anything else runs the full suite exactly as before** (`python -m pytest -q -n auto`, pytest-xdist, without `--dist
  loadgroup`; blocks on failure or when xdist is missing): a staged file outside `docs/` (code, tests, migrations,
  `.claude`, the hook itself), a rename into or out of `docs/` (read as delete plus add), nothing staged, a git error.
- **The hook looks before the command runs.** A commit whose own command changes the staged set (`git add ... &&
  git commit`, `-a`, `-am`, `--amend`, `--include`, `--only`, a pathspec after `--`, `git -C`) runs the suite, since the
  staged files it sees are not final. **Stage in one call and commit in the next to get the skip.** A commit message
  that mentions `git add` also runs the suite (a false alarm costs one run, never a missed one).
- Tests: tests/test_commit_hook.py (both paths, the renames in a real temp repo, the staging-command guard).

## Left for the packaging step (U1)

- Rename to Melara: the data folders (`%LOCALAPPDATA%\StrataLedger-dev`, `%PROGRAMDATA%\StrataLedger`), the
  environment variables (`STRATALEDGER_DATA_DIR`, `STRATALEDGER_ALLOW_TEST_KEYS`, `STRATALEDGER_LIVE_CLIPBOARD`),
  the logger name `strataledger`, the installer and the repo. A renamed data folder needs a move plan (rule 9).
  The key-derivation labels (`b"StrataLedger ... v1"`) never change.
- Screens and modules outside services still show "StrataLedger" (app_strata.pyw, sidebar.py,
  views_first_run.py, first_run_model.py, views_wizard.py, database.py docstrings, platform_support.py).
- After install, check that the program folder's ACL and owners pass HA8, and test with the built-in Administrator.

## Open points carried forward

- The linked-migration-file test (secrets audit LOW-4) is skipped on this Windows account; run it once with the
  right to create symbolic links (Developer Mode).
- AX3: the old development files stay in the repo root (`system_master.db`, `Backups/`).
- A read-only reader of a WAL file leaves an empty `-wal` and the `-shm` (AX1). Copy a company file only with
  `database.backup_database`.
- An add-on table cannot drop a column while its audit triggers name it (HA9). An add-on is trusted installation
  code (HA3, HA8).
- Phase 2.8: the restore service on `database.restore_database` (`company.restore`, K5's Master override, the
  Audit-ready flag); scheduled backups with E7 retention (`pre-upgrade` and `pre-restore` never pruned, AX2); after
  a recovery-code reissue, list the older master backups and offer to remove them, the choice audit-logged
  (secrets audit M1, owner 2026-11-18). PW1-PW11.
  Backups must include the company's attachments (owner 2026-11-18, area 18 Q14): a company backup without them
  is not complete; only the database-only safety copies (`pre-upgrade`, `addon-<key>`, `pre-restore`, AX2) are
  exempt. Each run is recorded in the master `backup_run` (docs/replan_2.9/area_18_admin_security_audit.md
  section 4).
  Backup retest inputs (mockup audit tracker rows BACKUP-01 to BACKUP-04):
  - **BACKUP-01:** Run a manual backup and verify the activity row and attachment coverage reflect the completed run
    after reload. Change the schedule and backup folder, then verify the saved settings after reload.
  - **BACKUP-02:** Select two backup dates and verify the source and proposed copy name follow the selected backup.
    Verify the replace confirmation identifies the real destination company.
  - **BACKUP-03:** Require a restore reason. Verify copy and replace results use the actual operation outcome, record
    the exact source backup and safety backup where applicable, and retain history after reload. Exercise a failed
    verification without modifying the target. Test restore itself remains tracked under ADMIN-11.
    Proposed, pending owner: keep the Audit-ready flag set until the replacement's sensitive audit event is reviewed,
    and a durable link from the destination operation to its safety-copy run.
  - **BACKUP-04:** Export two different sets of data groups and verify each ZIP, filename and reported count reflect
    the chosen groups.
- Undeposited funds vs matching (Phase 4): area 12 Q11 A decides it for deposits (clearing groups on the undeposited
  funds account).

## Deferred (unchanged except where an approved area now designs it)

- **Phase 4 posting services:** `clearing_lines`, `NEW_CLEARING`; `next_invoice_number`, `next_voucher_number`;
  the voids call `void_document_entry` and `release_allocations`; AR and AP in the chart CSVs. Deferral targets
  in `allocate`.
- **Phase 3 screens:** the unverified range and the close check's warning; `App.start_key_store()` after a key
  replacement; `KeyReplaced.recovery_code` shown once; `self.app.action_context()` on every post, approval,
  close, void and correction; `display_description`; log errors by passing the error object; `SaveFailedError`
  like any service error; the import review's rounding note; the AQ2 bridge follows RP6, the token rules in
  docs/design.md section 1, and AX5-AX10; MR8's "This removes: ..."; Company Settings > Add-ons; the custom
  fields screen (crm-fields.html) on this service.
- **C4 as amended by L2:** the deferral close checks are now designed (area 13 section 2.3 and area 10 section 3:
  `deferral_entries_posted`, `deferral_tie_out`, warn by default); they ship with the prepaid schedule service, not
  before. The baseline `period_close_check` CHECK list gets their codes in the 2.9 pass.
- **B14 (Codex batch 2):** a received-payment void service (reopening the invoices it paid, NSF handling, using
  `payments.release_allocations`) is not built.
- **Backlog 21** (R42). **KS18:** retired installation keys' recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).

History of what was done before 2.9 (STOP C custom fields service, Codex batch 2 posting fixes, their reviews and
mutation tests) is in docs/status_log.md (2026-11-18 entries) and the module docstrings.
