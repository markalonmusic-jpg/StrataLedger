# Step 2.9 schema replan, area 14: Approvals (kinds, policies, routing, inbox)

Status: **DRAFT 2026-11-24; owner answers Q1-Q7 folded 2026-11-24 10:20 PM and Q8 at 10:40 PM (§15). Owner approval pending the final QA (see next_step).** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. Everything not marked "owner" is a **planning proposal, owner may revise**. PROPOSED items from the
sources are not built as final.

Sources read (only these, searched by section):
- docs/next_step.md, "Handed to later areas" (the Area 14 lines for areas 8, 15, 6, 10, 13, 19) and the 1:48 AM
  stop; docs/roadmap.md 2.9 row (Area 14 handoff).
- Owner answers: 2026-11-24 1:48 AM (Approvers row "Schedule baseline rebuilds"; self-approval follows "Require a
  separate approver"); 2026-11-24 3:05 PM (OD-81, discount over authority); 2026-11-24 8:30 PM (the Estimate row is the OD-81 control); 2026-11-24 9:10 PM (Area 1: unapply and
  void have no approval kind; returned items are Area 12's); **2026-11-24 10:05 PM (this area: reasons, and three proposed rules, §6 to §8)**; 2026-11-24 10:20 PM (§15).
- Approved areas, by section: 2 (§1 lifecycle, §4 checks at approval), 3 (Q4 re-approval; §3.2; vendor-credit
  write-off, O3), 4 (pay app steps), 5 (§5.2, §9.1 refund and write-off permissions; line 189), 6 (§4.3, §4.4 and
  Q14/Q15; contract cancel; OD-81), 8 (§5 Change order approval; §12.19, §12.20), 11 (asset disposal; Area 13 line 216 names it), 13 (§1.4 one
  lock check; `pending_approvals` check; `controlled_entry_reviewed`), 15 (F17, open item 7), 18 (§2 access model,
  MR4 approval limits, "Which actions require a reason", `approval_action.reason`, §8.2, §8.3, §8.10).
- Area 1 (drafted, awaiting approval): §4 voids, §5 refunds and write-offs, §9.1 (9:10 PM answers).
- `migrations/001_company.sql`: `approval_policy`, `approval_step`, `approval_request`, `approval_action`,
  `approval_limit`, `document_approval_setting` (RP9), `company_settings.require_separate_approver`,
  `manual_entry_approval` and its threshold; permission seeds `*.approve`. `modules/services/approvals.py`.
- `Strata_Teams\docs\design_queue_followups_2026-11-22.md`, FU-N15 item 15 (vendor-credit write-off threshold).
- Decision codes by grep: RP9, R15, R16, R17, R21, R23, R28, MR4, MR5, OD-31, OD-81, H1-H5.

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | One mechanism | One approval mechanism for every kind of work (RP9). The only on/off switch is a row of `document_approval_setting`, all OFF by default (two named exceptions: the journal entry's `manual_entry_approval`, and the vendor-credit write-off's Company threshold, NULL = off). No second table, no per-feature control. |
| 2 | Kinds | A new lookup `approval_kind` lists the 14 existing kinds, the journal entry, and six new ones (Schedule baseline rebuild, Refund, Write-off, Deal stage move, Contract cancellation, Payroll import). All other tables point to it, so lists cannot drift. |
| 3 | Who approves | An `approval_policy` picks the route by kind, amount band and an optional condition; its `approval_step` rows say who: anyone with the permission, the job's PM, a role, named people, or a chain of steps, each with an optional backup. |
| 4 | Decisions | **Reject and Send back need a reason (OD-31). Approve takes an optional comment and always records who and when (owner 10:05 PM).** Self-approval follows "Require a separate approver" (OFF by default; marked Self-approved). Exception: the no-eligible-approver fallback (§8), never for journal entries (Q8). |
| 5 | Edits after approval | A change to amount, discount, lines or job voids the approval and needs a new one; history keeps it. Each kind lists its own approval-relevant fields (Bills keep Area 3 Q4). |
| 6 | Lock at approval | When approval is followed by a posting, the shared period-lock check runs again at approval time; a closed period refuses with the lock message and the document stays pending. |
| 7 | Approver unavailable | A deactivated approver, or one who lost the permission, is replaced by the step's backup, or by Admin; logged, never stuck. |
| 8 | Inbox | `pending_approvals` widens from journal entries to every kind: one list, filtered by kind and job. |
| 9 | Not approvals | Unapply and void of a payment have no kind (Area 1, owner 9:10 PM). Mandatory human review of import batches and the human approval of agent-origin entries are integrity rules, not settings. |

---

## 1. Current state (baseline and code)

- `document_approval_setting(document_type PK, requires_approval DEFAULT 0)`: 14 kinds (Bill, Payment, Purchase
  order, Subcontract, Pay application, Import batch, Asset disposal, Estimate, Change order, Contract, Invoice,
  Credit Memo, Vendor credit, Pay run), all seeded 0 (RP9). Its CHECK list differs from the lists in
  `approval_policy`, `approval_request` and `approval_limit`, which hold 'Journal entry' and not the last four.
  Journal entries are switched by `company_settings.manual_entry_approval` and its threshold, not by this table.
- `approval_policy` (kind, amount band, `is_active`) and `approval_step` (`step_no`, `role_code`, `required_count`;
  equal `step_no` means parallel). Only roles can approve; there is no "the job's PM", no named people, no backup.
- `approval_request` (frozen `chain_json`, status Pending / Approved / Rejected / Cancelled, `document_digest`
  required only for journal entries) and `approval_action` (decision Approve or Reject; **reason required only on
  Reject**, which already matches the 10:05 PM answer; `self_approved`; one action per user per request).
- `approvals.py`: policy match by kind and band, no overlapping bands, chain copied at submit (policy edits never
  change a request in progress), a person fills one slot (MR5), Master and Admin may fill any slot, human-origin
  only (R23), edit or delete of the document cancels its request (R21), status changes follow
  `ALLOWED_STATUS_CHANGES` (R16), separate-approver rule (R17, R28). `approvals.py` never writes `approved_by` on a
  document; the document service does, at post time, after `is_approved()`.
- `approval_limit(role_code, document_type, max_amount_cents)` (MR4); Area 18 re-keys it by level and adds template
  and per-user limits (a per-user limit needs a reason).
- `pending_approvals` is a close-checklist item and a screen that lists journal entries only (Area 13).

## 2. Decided (owner) and carried forward

- **RP9:** one switch per kind, all OFF; no `approval_rule` table (decisions file).
- **2026-11-24 1:48 AM:** every kind is a row on the Approvers page; the choices for who approves are the same for
  every row: anyone with permission, the job's project manager, a role, specific people, or a chain, with an
  optional backup. Self-approval follows "Require a separate approver" (OFF; marked Self-approved), except the no-eligible-approver fallback (§8, §15; not for journal entries, Q8).
- **2026-11-24 10:05 PM (this area):** only **Reject** and **Send back** need a reason (OD-31: a listed reason, or
  Other with at least 10 typed characters). **Approve takes an optional comment and always records who and when.**
  Area 18's reason table keeps "Reject an approval"; it gains "Send back an approval" and "Self-approve (no eligible approver)" (the fallback, §8).
- **Area 1 §3.2 and §4.1 (owner 8:55 PM, Q2 and Q7; 9:10 PM answer 1):** unapply and void of a payment need
  `payment.receive` or `payment.make` and a reason. **Confirmed by the owner (9:10 PM): unapply uses the recording
  permission and a reason, void needs only a reason; neither has an approval kind** (§15). Returned items are Area 12's (9:10 PM answer 2).
- **2026-11-24 3:05 PM (OD-81):** a discount over the rep's authority blocks Send only when the Estimate approval is
  ON (planning proposal: the "discount approval control" is read as the Estimate row, Q4); otherwise Send works with a warning (Area 6 §4.3).
- **Area 6 Q14 A / Q15 A:** `sales_authority_limit` is Area 6's table; the margin floor is a company setting; Area 14
  reads both.
- **Area 3 Q4:** a bill needs re-approval only on a vendor or total change, only with 'Bill' approval ON.
- **Integrity (never configurable):** only a person approves (R23); agent-origin entries always need a human
  approval; an import batch always needs one human review; approval rows are never edited or deleted (R16);
  every decision is audit-logged.

---

## 3. The kinds

`approval_kind` (planning proposal): `kind_code` TEXT PK (the label, e.g. 'Bill'), `owner_area` INTEGER,
`record_type` TEXT, `posts_on_approval` INTEGER (0/1: a posting follows the final approval, §6), `uses_amount`
INTEGER, `sort_order`, `row_version`. Seeded in the baseline. `document_approval_setting`, `approval_policy`,
`approval_request` and `approval_limit` replace their CHECK lists with a foreign key to it. A static test compares
the Approvers page rows with the table.

| Kind | Area | What waits | Posts on final approval | Suggested starting route (preset shown when the row is turned on) |
|------|------|-----------|-------------------------|----------------------------|
| Journal entry | 13 / 2.5 | the entry (switch: `manual_entry_approval`, threshold) | yes | existing policy; agent-origin always |
| Bill | 3 | the bill (Voucher #) | no (posting is the next step) | anyone with `bill.approve` |
| Vendor credit | 3 | the credit | no | anyone with permission |
| Purchase order | 3 / 9 | the PO | no | anyone with permission |
| Subcontract | 3 | the subcontract | no | anyone with permission |
| Payment | 1 / 2 | a payment made | yes (the payment posts when approved) | anyone with `payment.approve` |
| Pay run | 2 | the submitted run | no (posts nothing; each line posts on Date paid) | anyone with permission |
| Pay application | 4 | the sub's pay app on the owner side | no | anyone with permission |
| Invoice | 5 | the invoice before it posts | yes | the job's PM |
| Credit Memo | 5 | the credit memo before it posts | yes | anyone with permission |
| Estimate | 6 | an estimate revision (In approval) | no | the PM's supervisor role (policy) |
| Contract | 6 | a contract wording change | no | a role |
| Contract cancellation (new) | 6 | `contract.cancel` | no (the cancel runs after approval; it never posts) | a role |
| Change order | 8 | an internal PCO | no | the job's PM |
| Schedule baseline rebuild (new; page label "Schedule baseline rebuilds", Area 8 §12.20; code `Schedule baseline rebuild`, Area 18 §8.10) | 8 | a rebuild request (§12.20) | no (writes an insert-only schedule version) | a role |
| Deal stage move (new) | 15 | a lead's move into a stage the company marks "needs approval" | no | the sales manager role |
| Asset disposal | 11 | the disposal | yes | anyone with permission |
| Import batch | 19 | the second approver for imports (a control) | yes | a role |
| Payroll import (new) | 19 | an additional gate on a payroll batch | yes | a role |
| Refund (new) | 1 | a customer refund (`customer_refund`) | yes | anyone with `customer_refund.approve` |
| Write-off (new) | 1 / 3 | a customer invoice write-off, and (above its threshold) a vendor-credit write-off | yes | anyone with `invoice.write_off.approve` (vendor credit: `vendor_credit.write_off.approve`) |

Examples: with 'Bill' ON and the default route, an AP Clerk submits a $4,200.00 bill, the Controller approves it, and
the bill is posted by the next step. With 'Deal stage move' ON and "Won" marked "needs approval", the rep's move to
Contract signed waits for the sales manager.

**Not approvals (Area 1 cross-check, §3.2 and §4.1; confirmed, §2):** *Unapply* and *Void payment* are gated by their permission and
a reason, never by an approval kind. A static test asserts `approval_kind` has no row for them, and that neither
service calls `approvals.submit_for_approval`. Reversals of journal entries follow the manual-entry control and are
not a separate kind.

**Mandatory human review is not a kind row.** An import batch always needs one human review (integrity). The 'Import
batch' and 'Payroll import' rows are the configurable *additional* approver; turning them OFF never removes the
review. Mockup note for the design queue: the batch review screen and the approval inbox open the same saved batch.

## 4. Schema (planning proposals; baseline rewritten in the 2.9 pass, tests first)

- **`approval_kind`** (§3). `document_approval_setting.document_type` becomes a FK to it; `approval_kind` has 21 rows and
  `document_approval_setting` has 20 (all seeded 0); the journal entry has no setting row, because its switch is
  `manual_entry_approval` (the page shows it, bound to that setting; one switch only).
- **`approval_policy`**: keeps `name`, `min_amount_cents`, `max_amount_cents`, `is_active`; `document_type` becomes a
  FK to `approval_kind`; new `condition_code` TEXT NOT NULL DEFAULT 'None' CHECK IN ('None', 'Under margin floor',
  'Over authority limit', 'Margin floor or authority'); new `row_version`. A policy applies when the kind matches,
  the amount is in its band and its condition is true. Bands must not overlap within a (kind, condition); a policy
  with a true condition beats one with 'None'. Conditions apply only to Estimate, Change order (margin floor: Area
  8 §5) and Contract; the service refuses a condition on any other kind.
- **`approval_step`**: keeps `step_no`, `required_count`; `role_code` stays a foreign key to `role` and becomes nullable (NULL for every type but Role; People steps hold many
  people in the child table); the existing UNIQUE (policy_id, step_no, role_code) stays and a partial unique index
  on (policy_id, step_no, approver_type) WHERE approver_type <> 'Role' stops duplicate non-role steps; new `approver_type` TEXT NOT
  NULL CHECK IN ('Anyone with permission', 'Job PM', 'Role', 'People'), `backup_user_id` INTEGER NULL (a user id; no
  cross-file FK, rule 4 note). CHECK: Role needs `role_code`; People needs rows below; the others need neither.
- **`approval_step_person`** (`step_id` FK, `user_id`, PK both): the named people of a 'People' step.
- **`approval_request`**: keeps everything; `status` adds 'Sent back'; new `cancel_reason` TEXT NULL
  (CHECK: set exactly when status = 'Cancelled'; values 'Edited after approval', 'Edited while waiting', 'Withdrawn',
  'Document deleted'); `document_digest` becomes required for **every** kind (the digest covers the kind's
  approval-relevant fields, §7), not only journal entries; `chain_json` now holds, per step, the approver type, the
  role or people, the backup and `required_count` as they were at submit; new `row_version`.
- **`approval_action`**: `decision` CHECK IN ('Approve', 'Reject', 'Send back'); new `comment` TEXT NULL (Approve
  only, at most 500 characters); `reason` stays; CHECK: Reject and Send back need a non-empty reason; new `self_approval_fallback` INTEGER NOT NULL DEFAULT 0 CHECK
  (self_approval_fallback IN (0, 1)) with CHECK (self_approval_fallback = 0 OR (self_approved = 1 AND decision =
  'Approve' AND reason is non-empty)): the §8 fallback always carries a reason, and the flag tells it from an ordinary
  Self-approved action (extends the existing CHECK); `acted_at` and `user_id` stay NOT NULL (who and when, always). `approval_action.role_code` (NOT NULL) holds the acting
  role for a Role step and the token 'Job PM', 'People' or 'Anyone' for the other step types.
- **`approval_reassignment`** (insert-only, no update and no delete triggers; §8): `request_id`, `step_no`,
  `from_user_id` NULL (a role or group slot), `to_user_id`, `why` CHECK IN ('Deactivated', 'Lost permission',
  'Left the job', 'No holder'), `to_kind` CHECK IN ('Backup', 'Admin', 'Master'), `moved_at`.
- **Not new:** `sales_authority_limit` (Area 6), `approval_limit` and the user and template limits (Area 18),
  `company_settings.vendor_credit_writeoff_approval_threshold_cents` (Area 3), `require_separate_approver`.
- **Audit:** every table above is audited by the existing trigger pattern (Area 18 §1.2); `approval_action` and
  `approval_reassignment` are insert-only.
- **Inbox (derived, no table):** `approvals.pending_for(context, kind=None, project_id=None)` returns the requests
  where the user holds an open slot (§8 included), read-only (it writes nothing; route refresh is a separate call, §8), scoped by project (MR3).

## 5. Routing rules

1. **Submit.** Service `approvals.submit_for_approval(context, kind, record_type, record_id, ...)`: if the kind's row is OFF it
   writes no request, returns "not required" and the caller proceeds (logged in the document's own history, so a
   later turn-on explains old items). Otherwise it matches a policy, freezes the route in `chain_json`, stores the
   digest and the submitter, and the document moves to its waiting state. `authorize(context, SUBMIT_PERMISSION[kind])` runs first (rule 10; the map is today's
   `approvals.SUBMIT_PERMISSION`, extended to the new kinds with the document's own create or send permission). With no matching policy the default is "anyone with the
   kind's approve permission and a covering limit" (today's `DEFAULT_CHAIN`).
2. **Who may act on a step.** A person who is an approver by the step's type and who holds the kind's approve
   permission with a covering limit (MR4). 'Job PM' means the job's project manager (Area 7); a kind with no job
   uses the fallback in rule 12. Master and Admin may fill any slot (once). A person fills one slot per request
   (MR5). The request's creator and submitter may act only as rule 6 says.
3. **Approve.** Records who and when and the optional comment. When the last open slot of the last step is filled the
   request becomes Approved (rule 8 first). The document service then posts or proceeds, after `is_approved()`.
4. **Reject (reason).** Any rejection ends the request (Rejected); the document goes back to the preparer with the
   reason shown.
5. **Send back (reason) (owner 10:05 PM).** An approver returns the document to its submitter without a final no:
   the request ends as 'Sent back', the document returns to its draft state held by the **submitter** (for an
   estimate, the PM or the rep who submitted it, Area 6), the reason is shown to them, and editing and resubmitting
   makes a new request. Area 6 keeps its own append-only history (from and to status, from and to holder, reason);
   Area 14 passes the target (`approval_request.submitted_by`) and the reason. Example: the Controller sends back a
   $38,000.00 estimate revision with "Margin is under the floor; check the markup".
6. **Self-approval** follows `company_settings.require_separate_approver` (OFF by default): OFF, the creator or
   submitter may approve and the action is marked Self-approved; ON, `check_separate_approver` refuses before any
   write (applies to the Master and Admin too). **Exception (owner 10:20 PM, Q6; not for journal entries, owner 10:40 PM, Q8, §8):** when the control is ON and no other
   eligible approver exists, the submitter may approve, marked Self-approved, with a reason (OD-31); §8. An agent
   never approves, including by this fallback. No kind has a special rule except that Journal entry is excluded from the fallback (Q8) (this retires the §12.19 proposal in
   Area 8).
7. **Human only.** `approve`, `reject` and `send_back` accept a Human-origin context only (R23); `AGENT_ALLOWED`
   never lists them. An agent-origin journal entry always needs a human approval even when its row is OFF.
8. **Posting kinds** (§6 and the `posts_on_approval` column) run the lock check on the final approval.
9. **Withdraw.** The submitter may withdraw a Pending request (status Cancelled, reason 'Withdrawn'). The preparer
   needs no extra permission.
10. **One open request per record** (existing partial unique index), and **one open rebuild request per schedule**
    (Area 8 §12.19; the record is the schedule).
11. **Limits.** `check_approval_limit` (MR4) is unchanged; the highest applicable limit applies, no cap when none
    is set.
12. **Kinds with no job and a 'Job PM' step** fall to the backup, then Admin (rule in §8), and the Approvers page
    warns when a 'Job PM' route is chosen for a kind that has no job (Journal entry, Payment).
13. **Turning a row OFF with requests Pending.** Pending requests finish under their frozen route; only new
    submissions skip approval. Turning a row OFF is audit-logged with a reason (Area 18 Q15 A).
14. **Turning a row ON** never approves or blocks existing documents; it applies from the next submit; the change
    is audit-logged with a reason, as turning one OFF is. The reason is an owner decision, not a reviewer proposal: Area 18
    Q15 A ("a reason is needed for controls") and its table row "Change a company control", which names approval toggles
    and covers a change in either direction.

**Starting route versus default.** The §3 column is a preset the Approvers page offers when a row is first turned on
(presets first, section 0b). If no policy is saved, §5 rule 1's default applies: anyone holding the kind's approve
permission with a covering limit. A 'Job PM' step still needs the PM to hold the kind's approve permission and a
covering limit (MR4, Area 18 §2: approve codes are explicit grants); the page warns when the job's PM lacks it.

### 5.1 Per-kind notes

- **Estimate (Area 6).** The row 'Estimate' is the "Estimate approval" control and the "discount approval control"
  read by OD-81 (owner 8:30 PM: the Estimate row, no new switch; §15 Q4).
  Policy conditions: 'Under margin floor' reads `company_settings.estimate_margin_floor_pct`; 'Over authority
  limit' reads `sales_authority_limit` for the holder (user limit first, then the role's). A revision whose rep
  adjustment exceeds the limit goes to In approval; at or under the limit it does not. Row OFF: the PM's submit
  goes straight to Approved, logged; the discount warning still shows (OD-81).
- **Contract and Contract cancellation (Area 6).** 'Contract' routes wording changes; `contracts.cancel` creates a
  'Contract cancellation' request and stops; after approval the cancel runs in one transaction (never posts).
- **Change order (Area 8 §5).** The internal PCO approval chain, OFF by default; the customer's approval is
  separate and unchanged. Condition 'Under margin floor' as for estimates.
- **Schedule baseline rebuild (Area 8 §12.20).** The row is the only switch (`require_baseline_rebuild_approval` is
  withdrawn). Row ON: the rebuild is a request; the new version is copied from the schedule as it stands at approval
  and the approver sees the preview; nothing is written until approved; a refused request leaves the baseline
  unchanged and stays in history. Reason and history are recorded in both modes. `finish_on` never changes.
- **Deal stage move (Area 15, F17).** Warnings stay the default (S 11-15 3:30 PM). With the row ON the company marks
  which stages need approval (`service_stage.needs_approval`, default 0, Area 15 owns the column; planning
  proposal); a move into one creates a request and the lead stays where it was until approved.
- **Pay run (Area 2).** 'Submitted' exists only when the row is ON; approving runs `pay_runs.check_lines` again on
  the server (changed bills are named and removed) and posts nothing. `pay_run.approval_request_id` points here.
- **Refund and Write-off (Areas 1, 3, 5).** The permissions stay the four sensitive ones (`customer_refund.issue`,
  `customer_refund.void`, `invoice.write_off`, `invoice.write_off_reverse`) and `vendor_credit.write_off`. Rows OFF
  by default: the refund or write-off posts at once with its reason. Row ON: it waits, then posts.
  **Vendor-credit write-off threshold (N15, cross-check):** approval is needed only above
  `company_settings.vendor_credit_writeoff_approval_threshold_cents`, **NULL = off (default)**; below the threshold
  the write-off posts with the permission and its reason (at least 10 characters). The Approvers page shows the
  threshold as a field on the Write-off row ("Vendor-credit write-offs: ask for approval above $__"). A customer
  invoice write-off follows the row alone (any amount when ON). **For a vendor-credit write-off the threshold is the
  switch, and the Write-off row is not consulted for it** (row ON and threshold NULL: no approval; the page says so). See Q2.
- **Payment and Pay application.** Payment approval (a payment made) and Pay application (the owner-side or sub
  application per Area 4) keep their rows; Area 4's customer certification is **not** an approval kind (the PM's
  entry of the customer's answer, Area 4 §1).
- **Import batch and Payroll import (Area 19).** Mandatory human review stays; the rows are an additional gate. Both
  open the exact saved batch and the exact mapped rows that will post.
- **Asset disposal (Area 11, not drafted).** Planning proposal: the disposal waits only when the row is ON (next_step:
  the disposal uses Area 14's dependency only when configured). Area 11 owns the disposal record and its digest.

---

### 5.2 Tests for the decisions, send back, withdraw and write-off routing

- `test_approve_without_comment_succeeds_and_records_user_and_time`,
  `test_reject_and_send_back_without_reason_refused`,
  `test_approve_comment_over_500_characters_refused`,
  `test_send_back_returns_document_to_submitter_and_ends_request`,
  `test_withdraw_cancels_pending_with_reason`,
  `test_vendor_credit_writeoff_below_threshold_posts_above_waits_null_means_off`,
  `test_customer_writeoff_follows_the_row_alone`,
  `test_self_approval_allowed_and_marked_when_separate_approver_off`,
  `test_self_approval_refused_for_master_when_separate_approver_on_and_another_eligible_approver_exists`,
  `test_agent_context_cannot_approve_reject_or_send_back`.

### 5.2b Tests for the per-kind notes

- `test_estimate_row_off_goes_straight_to_approved_with_warning_only`,
  `test_contract_cancel_with_policy_creates_request_and_stops_until_approved`,
  `test_deal_stage_move_to_marked_stage_waits_for_approval_when_row_on`,
  `test_pay_run_approval_reruns_check_lines_and_removes_changed_bills`,
  `test_agent_origin_journal_entry_needs_human_approval_even_when_row_off`,
  `test_turning_a_row_on_or_off_needs_a_reason_and_is_audit_logged`.

### 5.3 Tests for submit, routing, limits and the policy rules

- `test_submit_with_row_off_writes_no_request_and_logs_not_required`,
  `test_submit_with_no_policy_uses_default_chain_of_anyone_with_permission_and_limit`,
  `test_submit_authorizes_with_submit_permission_before_the_write_transaction`,
  `test_job_pm_step_only_the_jobs_pm_may_approve_and_one_slot_per_person`,
  `test_one_open_request_per_record_and_one_open_rebuild_per_schedule`,
  `test_approval_limit_highest_applicable_applies_no_cap_when_none_set`,
  `test_job_pm_route_on_a_kind_with_no_job_falls_back_and_page_warns`,
  `test_row_turned_off_leaves_pending_requests_to_finish_under_frozen_route`,
  `test_row_turned_on_does_not_touch_existing_documents`,
  `test_policy_condition_refused_on_a_kind_that_cannot_have_one`,
  `test_true_condition_policy_beats_unconditional_policy`,
  `test_overlapping_bands_within_kind_and_condition_refused`,
  `test_unapply_and_void_payment_never_call_submit_for_approval`.

## 6. Period lock at approval (planning proposal; the rule is the owner's 10:05 PM message)

- A kind with `posts_on_approval` = 1 (a posting follows the final approval in the same service call), runs the
  **shared lock check** (Area 13 §1.4, `period_locks.check_open` with the area of the source document, the
  accounts its lines would hit, the date it would post at, and `action` = the document's action) **inside the final
  approver's write transaction, before the action row is written**.
- If the period has closed, or an area or account lock now applies, the approval is **refused with Area 13's one
  sentence** ("October is partly closed: <area> is locked. Ask an Admin to unlock it, or date this
  in November."); nothing is written, the request stays Pending and the document stays waiting. The approver sees
  the message; nothing is logged as a permission denial (it is not one).
- The preparer's way out is to change the date (an edit, which cancels the request per §7, then resubmit) or an
  Admin unlocks, after which the same approver approves. Earlier steps of a chain do not run the check (they post
  nothing); the final step does. **Bill, Vendor credit, Pay run, Pay application and the other kinds whose posting is a
  separate later step do not run it at approval**; the posting step runs it (below). The check also covers the Special
  cutoff (Area 13 §1.4 amendment 2026-11-21): a date on or before the cutoff refuses.
- Kinds that post nothing (Estimate, Change order, Schedule baseline rebuild, Deal stage move, Contract,
  Contract cancellation, Pay run) skip it; the lock check of their next action (Area 13 §1.4, Q7 A) still applies there.
- **A second check at posting** stays: `is_approved` is not a lock check, and the posting service calls the shared
  check again (Area 13 Q7 A static test: every function that writes `journal_line` calls it).
- Example: the Controller approves a $9,400.00 invoice dated October 28 on November 3, after October closed: refused
  with the lock sentence; the AR Clerk redates it to November 3 and resubmits; approved and posted.
- Tests: `test_final_approval_refused_in_closed_period_and_request_stays_pending`,
  `test_final_approval_refused_in_locked_area_and_names_the_area`,
  `test_final_approval_refused_on_or_before_the_special_cutoff`,
  `test_approval_in_open_period_writes_action_and_posts`,
  `test_intermediate_step_approval_does_not_run_the_lock_check`,
  `test_non_posting_kind_skips_the_lock_check`,
  `test_lock_refusal_writes_no_approval_action_and_no_denied_access_event`,
  `test_unlocked_period_lets_the_same_approver_approve_the_pending_request`.

## 7. Edits after approval (planning proposal; the rule is the owner's 10:05 PM message, Q3 and Q5 owner 10:20 PM)

- **Rule.** Changing an approved document's **amount, discount, lines or job** voids the approval and needs a new
  one. The old request becomes Cancelled with `cancel_reason` 'Edited after approval'; its actions stay in history.
  The document returns to its waiting-to-submit state. The same fields change on a **Pending** request cancel it
  ('Edited while waiting', R21 as today) and the preparer resubmits.
- **How it is detected.** Each owning service registers `approval_digest(kind, record)` over the kind's
  approval-relevant fields; the digest is stored at submit (`document_digest`, now for every kind) and compared at
  approval, at post and at Send. A mismatch voids the approval. One shared function, so no kind does its own check.
- **Per kind, the fields** (a field not listed never voids): default = amount, discount, lines, job **and, for a kind
  with `posts_on_approval` = 1, the posting date** (so a redate for a closed period, §6, cancels the request; Bill
  keeps Area 3 Q4 and is checked at its posting step). **Journal entry** is the exception: its digest is
  the full sealed form (R15), so any change to the entry voids it, a memo included.
  Exceptions that follow approved rules: **Bill** = vendor and total only (Area 3 Q4; a job or GL change with the
  same total stays approved; the approval applies only while 'Bill' approval is ON, and with it OFF the change
  shows a warning); **Estimate** = the revision's lines, price, discount, and job; a memo or note never voids;
  **Schedule baseline rebuild** = the request's dates and reason (the preview is recomputed at approval).
  See Q3 for the Bill conflict.
- **Discount (OD-81).** A discount **higher than the approved one blocks Send again**: with the Estimate row ON, the
  revision goes to In approval and Send waits; with it OFF, Send works and shows "This discount is over your
  authority (10%)." Any change to the approved fields, a **lower** amount or discount included, voids the approval (owner 10:20 PM,
  Q3). Example: a $12,000.00 change order edited to $11,500.00 needs approval again.
- **Posted documents.** Editing a posted invoice, credit memo, bill or vendor credit is a reverse-and-repost under
  the same number (rule 8). When the kind's row is ON and an approval-relevant field changes, the edit is **held as a
  pending revision by the owning service and the posted original stays posted until the revision is approved**; then
  the one transaction reverses and reposts. Storage of the pending revision is the owning area's (planning
  proposal); Area 14 supplies the gate. **Owner 10:20 PM, Q5:** the posted version stays in the ledger until the
  revision is approved, then reposts; **Reject discards the revision** (the posted version is untouched).
- Examples: the Controller approves a $12,000.00 change order for Job Maple St; the PM edits it to $11,500.00: the
  approval is voided ("Edited after approval") and the change order goes back to the PM to resubmit (Q3, a lower
  amount voids too). A posted $12,000.00 invoice whose row is ON is edited to $12,600.00: the edit is held as a
  pending revision, the posted invoice stays in the ledger, and it reposts only when the revision is approved.
- Tests: `test_changing_approved_amount_voids_approval_and_keeps_history`,
  `test_changing_discount_lines_or_job_voids_approval`,
  `test_changing_memo_or_notes_does_not_void_approval`,
  `test_edit_while_pending_cancels_request_with_reason`,
  `test_bill_job_change_with_same_total_stays_approved` (Area 3 Q4),
  `test_higher_discount_than_approved_blocks_send_when_estimate_policy_on` (OD-81),
  `test_higher_discount_warns_and_sends_when_estimate_policy_off`,
  `test_digest_required_for_every_kind_not_only_journal_entries`,
  `test_posted_document_edit_held_until_revision_approved`,
  `test_lower_amount_after_approval_still_voids_it` (Q3),
  `test_posting_date_change_voids_approval_for_posting_kinds`,
  `test_journal_entry_memo_change_voids_approval_full_digest`,
  `test_reject_of_pending_revision_discards_it_and_leaves_posted_version`,
  `test_resubmission_after_voided_approval_is_a_new_request_one_open_at_a_time`.

## 8. Approver unavailable (planning proposal; the rule is the owner's 10:05 PM message, Q6 owner 10:20 PM)

- **When it is checked.** (a) At the moment the cause happens: `users` deactivation, a role or level change, a
  permission override and a job's PM change call `approvals.reassign_for_user(conn, user_id, why)` inside their own
  write (a service rule, not a trigger, H4); (b) as a safety net, at every approve, and when the inbox screen loads through a separate write call
  `approvals.refresh_routes(context)` (authorized, one transaction); `pending_for` itself stays read-only.
- **What happens.** For each open slot of each Pending request whose frozen route names that person or role
  (through the Pending request's `chain_json`): if the approver is deactivated, or no longer holds the kind's
  approve permission with a covering limit, the slot moves to the step's **backup** (when active and eligible),
  else to **Admin** (every active Admin may act; the Master always may), else the **Master**. A row is written to
  `approval_reassignment` and to the audit log; the original frozen route is never edited.
- **Never stuck (owner 10:20 PM, Q6, not the recommended option).** When "Require a separate approver" is ON and no
  other eligible approver exists, the **submitter may approve**, marked Self-approved, **with a reason** (OD-31: a
  listed reason or Other with 10 typed characters); the reason is stored on the action and the audit log. The
  Approvers page and the close checklist still list the request as "No eligible approver" until then. **"Eligible" means** a person other than the creator and submitter who may act on the open step (the step's type,
  the kind's approve permission and a covering limit); **the Master and every active Admin count** when they qualify.
  An agent-origin
  entry still always needs a human: the fallback never lets an agent approve (R23), and an agent-origin item never
  uses the fallback: it waits for a different human (the initiating user is not its submitter). **Journal entries are
  excluded from the fallback (owner 10:40 PM, Q8):** the baseline triggers stay, and the creator of a journal entry
  can never approve it while the control is ON. Example: a one-user company with
  the control ON; the owner submits a $3,000.00 refund and approves it with the reason "Only user".
- **People who fill a role slot** are not "unavailable" when another holder of the role exists; only an empty role
  triggers the fallback.
- Examples: Dana Reyes (Controller) is deactivated while a $22,000.00 bill waits on her step; the step's backup is
  Tomas Okafor, who approves. With no backup, any active Admin approves; the page shows "Moved to Admin because Dana
  Reyes was deactivated".
- Tests: `test_deactivated_approver_step_moves_to_backup`,
  `test_no_backup_moves_to_admin_then_master`,
  `test_lost_permission_or_limit_moves_the_step`,
  `test_removed_job_pm_step_moves_to_backup_or_admin`,
  `test_reassignment_is_logged_insert_only_and_frozen_route_unchanged`,
  `test_role_with_another_holder_does_not_reassign`,
  `test_no_eligible_approver_is_listed_not_hidden`,
  `test_submitter_may_self_approve_with_reason_when_no_other_eligible_approver_and_control_on`,
  `test_self_approval_fallback_needs_a_reason_and_is_marked`,
  `test_self_approval_fallback_never_applies_to_an_agent`,
  `test_self_approval_fallback_excluded_for_journal_entries_and_triggers_still_refuse`,
  `test_self_approval_fallback_applies_to_every_other_kind`,
  `test_reassignment_runs_on_user_deactivation_and_again_on_refresh_routes`,
  `test_pending_for_writes_nothing`.

## 9. The inbox and the Approvers page

- **Inbox.** One list "Waiting for me", filtered by kind and job, with Approve (optional comment), Reject (reason)
  and Send back (reason). `pending_approvals` (Area 13's close check) counts every kind's Pending requests for the
  period. A user sees only requests they may act on, within their project scope (MR3); an Admin sees all.
- **Approvers page** (Company Settings > Controls > Approvers; Admin or Master; every change audit-logged with a
  reason, Area 18 Q15 A). A row per kind with the switch (OFF), then the route: "Anyone with permission", "The job's
  project manager", "A role", "Specific people" or "A chain" (add steps), a backup, and an amount band. The page
  warns, never blocks, when a route lets one person create and approve (Area 18 Q10 A) or when a 'Job PM' route is
  chosen for a kind with no job.
- **Reasons list.** The self-approval fallback uses the Reasons kind 'Self-approval' (Area 18's table gains "Self-approve (no eligible
  approver)"). Reject uses the Reasons kind 'Approval rejection' (a new kind Area 18 adds beside its table row "Reject an approval") and Send back uses Area 6's existing kind 'Send back'
  (no new duplicate kind); both are company-editable lists under Settings > Lists > Reasons (OD-31), stored as
  `approval_action.reason_id` and `reason_label` beside the free text for Other (Area 18 reason pattern); Other needs 10 typed characters.
- **Mockup work orders** (design queue, not written here): the Approvers rows and chain editor; the inbox with the
  optional Approve comment; the send-back dialog; the "Moved to Admin" banner; the lock-refusal message.
- Tests: `test_inbox_lists_every_kind_the_user_may_act_on`,
  `test_inbox_hides_requests_outside_project_scope`,
  `test_approvers_page_row_per_kind_matches_approval_kind`,
  `test_every_approval_toggle_defaults_off_and_is_audit_logged`,
  `test_no_approval_kind_row_for_unapply_or_void_payment`.

## 10. Decisions, permissions, reasons and audit

- **Reasons (owner 10:05 PM).** `approval_action` CHECK requires a reason on Reject and Send back only; Approve takes
  an optional `comment`; `user_id` and `acted_at` are NOT NULL on every action. Area 18's "Which actions require a
  reason" table: "Reject an approval" stays; add "Send back an approval". An Approve with a comment is **not** a
  reason-required action.
- **Permissions.** The kind's approve permission (`je.approve`, `bill.approve`, `payment.approve`, and one per
  other kind: names are Area 18's; the rest, including `customer_refund.approve`, `invoice.write_off.approve` and
  `vendor_credit.write_off.approve`, are planning proposals following `<kind>.approve`), sensitive, in no level default,
  never in `AGENT_ALLOWED` (Area 18 §2). Submitting is the document's own permission. Withdrawing needs none beyond
  being the submitter. Changing the Approvers page needs the controls permission (Admin or Master).
- **Audit.** Every request, action, reassignment, policy, step and setting change is in `audit_log`; the Approvers
  page history reads it (Area 18 Q16 A).
- **Row version** on `approval_kind`, `approval_policy` and `approval_request` (Area 21 stale-save refusal).

## 11. How it lands in the baselines and the existing code

- **Baseline (planning).** `approval_kind` (new); `document_approval_setting`, `approval_policy`, `approval_request`,
  `approval_limit` re-pointed to it; `approval_step`, `approval_request`, `approval_action` columns above;
  `approval_step_person`, `approval_reassignment` (new, insert-only triggers); seeds: 21 kinds; 20 setting rows, all OFF. Existing
  development databases are rebuilt (rule 9 note: ask before deleting any file).
- **Code.** `approvals.py` splits into `approvals.py` (submit, approve, reject, send back, withdraw, cancel on edit),
  `approval_routing.py` (policy match, step resolution, fallback) and `approval_inbox.py` (reads). `is_approval_required`
  reads `approval_kind` + the setting. `check_approval_limit` unchanged. Static tests: no approval service imports a
  UI module (H1); no clock read (H2: `context.now`); status changes only through `ALLOWED_STATUS_CHANGES` (R16).
- **New service names (proposals; none exist today):** `send_back`, `withdraw`, `refresh_routes`, `pending_for`,
  `reassign_for_user`. `submit_for_approval` keeps its name.
- **Existing tests change:** `tests/test_approvals.py` (reject-only reason rule, digest for every kind, status
  'Sent back'), `tests/test_schema_replan.py` (kind lists), the journal-entry approval tests (digest unchanged).
- **Handoffs out.** Area 1: refund and write-off services call `approvals.submit` (kinds 'Refund', 'Write-off').
  Area 2: `pay_run.approval_request_id`. Area 3: bill and vendor-credit services register their digests and the
  write-off threshold. Area 5: invoice and credit memo digests. Area 6: policy conditions, send-back target.
  Area 8: PCO, rebuild. Area 11: disposal. Area 15: `service_stage.needs_approval`. Area 19: Import batch and
  Payroll import rows. Area 13: `pending_approvals` widened and `controlled_entry_reviewed`. Area 18: the reason
  rows, the permission list, the Approvers page fields.

## 12. Conflicts with decisions or the baseline (flagged; all resolved by the owner answers of 2026-11-24 10:20 PM, or planning's call for Q2, §15)

1. **Bill re-approval (Area 3 Q4, owner-approved)** says a job or GL change with the same total stays approved;
   the 10:05 PM rule 1 says a job change voids. Treated here as a per-kind field list: Bills keep Q4 (Q3).
2. **Baseline CHECK lists differ** across the four approval tables and the setting table ('Journal entry' versus the
   last four). `approval_kind` removes the drift; the journal entry's switch stays `manual_entry_approval`.
3. **Area 3's `vendor_credit_writeoff_approval_threshold_cents`** is a Company setting; this area keeps it (no second
   switch) and shows it on the Write-off row (Q2).
4. **Area 6's "discount approval control"** (OD-81) is the Estimate row (owner 8:30 PM, §15 Q4; confirmed).
5. **Area 8 §12.19** proposed a fixed approver list and a no-self-approval rule: both already withdrawn (1:48 AM).
6. **Wording in Areas 1 and 5** calls Refund and Write-off "the existing approval kinds"; the baseline has neither,
   so they are new rows here and those lines are corrected by pointer.
7. **Area 6 sends In approval to "the rep" (Area 6 line 260)**; §5 rule 5 sends a send-back to the submitter (the PM
   or the rep who submitted). Differs when the PM submitted a rep's revision (Q7).
8. **Area 6 §4.3 says "OFF = no active policy"**; here the switch is the `document_approval_setting` row (RP9 and the
   1:48 AM answer). Row ON with no policy = the default route; a policy cannot switch an approval on by itself.
9. **Area 8 label** "Schedule baseline rebuilds" (page) versus `Schedule baseline rebuild` (code, Area 18 §8.10): both
   kept, as in §3.
10. **`approval_policy` for Journal entry** exists in the baseline but the table has no switch row for it today;
   handled as above.

## 13. Questions for the owner (recommended option first; all answered 2026-11-24 10:20 PM, §15; Q6 superseded by the owner's own answer)

- **Q1. Approval kinds: which new rows?** (A) the six new rows listed in §3, all OFF (recommended); (B) only Schedule
  baseline rebuild now, others added when their areas are built. Example under A: the Approvers page lists 21 rows.
- **Q2. Vendor-credit write-off threshold (N15).** (A) Keep Area 3's Company threshold (NULL = off), shown on the
  Write-off row; a customer write-off follows the row alone (recommended). (B) Make the threshold a policy band on
  the Write-off kind and retire the column (one place, but changes approved Area 3). Example: threshold $500.00; a
  $450.00 vendor write-off posts at once; $800.00 waits for an approver.
- **Q3. Does a *lower* amount or discount after approval still need re-approval?** (A) Yes, any change to the kind's
  approval-relevant fields voids it, except Bills, which keep Area 3 Q4 (recommended: simple and matches "changing
  ... voids"). (B) Only a change that raises the amount or discount, or changes the lines or job, voids it; a
  reduction keeps the approval. Example: a $12,000.00 approved invoice cut to $11,800.00.
- **Q4. Is OD-81's "discount approval control" the Estimate row?** (A) Yes, the same row, no new switch
  (recommended). (B) A separate switch on the Controls page. Example: with the Estimate row OFF and a 12% discount over
  a 10% limit, Send works with the warning.
- **Q5. A posted document edit under a turned-on row: hold the edit until approved?** (A) Hold it as a pending
  revision; the posted original stays until approved (recommended, nothing posts unapproved). (B) Repost at once and
  flag it "Needs approval" afterwards (simpler, weaker control).
- **Q6. When no eligible approver exists (one-person company with "Require a separate approver" ON)?** (A) Show
  "No eligible approver" to Admin and the Master and leave it pending (recommended). (B) Let the Master approve
  anyway, marked Self-approved, overriding the control (never: the control applies to the Master too).

- **Q7. Who receives a send-back from In approval: the rep or the submitter?** (A) The submitter, the PM or rep who
  submitted that revision (recommended; one rule for every kind). (B) Always the rep, as Area 6 line 260 reads.
  Example: the PM submits a revision the rep priced; the Controller sends it back; under A it goes to the PM.
- **Q8 (new, from the reviewer; ANSWERED 2026-11-24 10:40 PM: option A, §15). The journal entry's separate-approver triggers.** The baseline
  triggers `journal_entry_separate_approver_insert` and `_update` (migrations/001_company.sql, near line 3700) refuse
  an approver who is the creator whenever "Require a separate approver" is ON, so the §8 fallback cannot work for
  journal entries as the baseline stands. (A) Exclude Journal entry from the fallback and leave the triggers
  (recommended: no baseline change; a one-user company turns the control OFF or has a second person). (B) Retire the
  triggers and enforce the rule in the service (H4 prefers a service rule), so the fallback applies to journal
  entries too, with the same reason. Example under B: a one-user company's $3,000.00 manual entry approved by its
  creator with the reason "Only user". Until answered, A.

## 14. Open items (not decisions)

- Where a posted document's pending revision is stored (Areas 3 and 5, Q5).
- Notifications to approvers (Area 20's feed); this area writes none.
- `service_stage.needs_approval` placement and wording (Area 15 owns it).
- The reports that read approvals (aging of pending approvals) are Area 17's.
- Approver delegation while on leave (a date range) is out of scope; the backup covers it.
- Foreign-company or hosted multi-tenant routing is out of scope.

## 15. Owner answers 2026-11-24 10:20 PM (dated amendment; §13 and §12 stay as asked)

- **Q1 decided:** all six new kinds, all OFF.
- **Q2 (planning's call, planning proposal):** keep Area 3's Company threshold; blank (NULL) = off; shown on the
  Write-off row.
- **Q3 (owner):** any change to an approved document's amount, discount, lines or job voids the approval, even a
  lower amount ($12,000.00 change order edited to $11,500.00). **Bills keep Area 3's rule** (only a vendor or total
  change).
- **Q4:** already answered 8:30 PM: the Estimate row; no new switch.
- **Q5 (owner):** editing a posted document while its row is ON is held as a pending revision; the posted version
  stays in the ledger until approved, then reposts; Reject discards it.
- **Q6 (owner, not the recommended option):** with "Require a separate approver" ON and no other eligible approver,
  the submitter may approve, marked Self-approved, with a reason (OD-31). The fallback never lets an agent approve (planning note, owner may revise: agent-origin entries always need a human
  approver, §2 integrity, §5 rule 7 and §8; the fallback is for humans only).
- **Q7 (owner):** a send-back goes to the submitter (the PM or rep), with the reason; history records from, to and
  when. **Area 6 is amended** (pointer there).
- **Q8 (owner 10:40 PM): option A.** The two `journal_entry_separate_approver` triggers stay. **Journal entries are
  excluded from the Q6 self-approval fallback:** with "Require a separate approver" ON, the creator of a journal entry
  can never approve it; a one-person company turns the control OFF or adds a second user. The fallback applies to
  every other kind. Example: the only user's $3,000.00 manual entry cannot be self-approved while the control is ON;
  the same user's $3,000.00 refund can, with a reason. Owner rule. Tests:
  `test_self_approval_fallback_excluded_for_journal_entries_and_triggers_still_refuse`,
  `test_self_approval_fallback_applies_to_every_other_kind`.
- **Area 1 cross-check confirmed (owner 9:10 PM):** unapply uses the recording permission (`payment.receive` or
  `payment.make`); void needs only a reason; neither has an approval kind.
- **§12 conflicts resolved:** (1) Bills keep Area 3 Q4; (2) the baseline lists are replaced by `approval_kind`; (3)
  Area 3's threshold is kept; (4) the Estimate row is the OD-81 control; (5), (6) already withdrawn or corrected by
  pointer; (7) send-back goes to the submitter; (8) the setting row is the switch, a policy never switches approval
  on by itself; (9) both labels kept; (10) the journal entry's switch stays `manual_entry_approval`.

- **Amendment 2026-11-24 (pointer, Area 9): Purchase order and Subcontract rows.** One commitment record serves both
  rows; a PO with its row ON is 'Pending approval' until approved and is committed only on Send, Mark as sent or Print;
  an approved unsent PO is voided by an edit; a sent PO changes only through a change record (Area 9 §6.3). The digest is
  this area's §7 default (amount, discount, lines, job), plus the vendor (planning proposal).

- **Amendment 2026-11-25 (pointer, Area 20, owner 12:37 AM Q3): approver notices.** Area 14's routing calls Area 20's `notifications.notify` (§7) for approval
  waiting, decided, moved to the backup or Admin, and no eligible approver. Every such notice shows in the user's in-app list; email is opt-in per user and per
  kind, off by default. Area 14 owns no feed.

- **Amendment 2026-11-25 (pointer, Area 11): the 'Asset disposal' row.** Area 11 owns the disposal record (`asset_disposal`, one proceeds row per asset, `operation_id` for exact retry); with the row ON the disposal is Pending approval, `asset.approve` (sensitive) approves, the final approval runs the shared lock check again, and the digest covers the assets, date, proceeds, allocation and counterparty (Area 11 §5).

- **Amendment 2026-11-25 (pointer, Area 19 draft): 'Payroll import' row.** Area 19 reviews the exact mapped rows through a stored `review_digest` (always on); when this row is ON the entry posts on final approval, and any row, mapping or batch change after review voids the review and the approval (Area 19 §5). Planning proposal, owner may revise.
