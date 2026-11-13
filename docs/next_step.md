# Next step: Phase 2.5 Step 4 (approvals in posting)

Written at the Step 4 planning STOP (2026-11-13). Overwritten at each STOP (CLAUDE.md section 8).
Status: PLAN APPROVED (2026-11-13) with the owner's answers (decisions R15-R24). STOP 1 done: the company
baseline edit (tag `baseline-pre-2.5-4`, archive copy), waiting for the owner's word on the rebuild. Next: part A.

**State at STOP 1:** suite **2184 passed, 7 deselected, 12 xfailed**. The master baseline did not change; the
development master is empty (no users, companies or keys) and there are no company files.

**Owner answers (2026-11-13), built as decided:**
1. Use the existing `approval_*` tables; change the baseline only for a gap the design shows (one edit, tag,
   archive copy, one rebuild).
2. Any edit after approval cancels it (`cancel_on_edit`); the entry must be resubmitted.
3. A rejected entry can be resubmitted after an edit. Rejection needs a reason; the rejected request stays.
4. The stale-now known issue is fixed in this step: posting, approval and rejection take `now` from a fresh
   context per action (H2 holds: no clock reads in services). Removed from CLAUDE.md Known issues when done.
5. Multi-approver chains and approval limits are in scope (owner requirement).

## What approvals.py (2.2b) already does

- `is_approval_required(context, document_type)`: Journal entry follows `company_settings.manual_entry_approval`;
  other types follow `document_approval_setting` (all off by default, 1.6).
- `submit_for_approval(context, document_type, record_type, record_id, amount_cents, *, created_by, project_id)`:
  authorizes the type's submit permission (`je.create` for journal entries: the agent may submit), picks the
  policy whose band covers the amount (or the default one-approver chain), copies the chain onto the request
  (`chain_json`), one Pending request per record (partial unique index).
- `approve` / `reject(reason)`: approval limit (`check_approval_limit`), the approve permission (`je.approve`,
  not in AGENT_ALLOWED), steps in order, parallel steps, `required_count` different people, one person one slot,
  Master and Admin fill any slot once, the separate-approver rule (on: the creator is denied; off: the action is
  flagged `self_approved`, R3), every denial logged before the write, a re-check inside the write. A rejection
  needs a reason and ends the request (status Rejected, the row and its action stay).
- `cancel_on_edit(context, record_type, record_id)`: cancels a **Pending** request in its own transaction.
- `is_approved(conn, record_type, record_id)`: the newest request is Approved (the posting gate).
- Policies and limits: `create_policy` (no overlapping bands), `deactivate_policy`, `set_approval_limit`
  (`company.roles.manage`, audited tables). 34 tests in tests/test_approvals.py.

## What posting needs from it, and the gaps found

| # | Need | Today | Proposed |
|---|---|---|---|
| G1 | An edit after approval cancels the approval (answer 2) | `cancel_on_edit` cancels Pending only, so an approved draft edited afterwards would still post as approved | cancel Pending **or Approved**; `completed_at` set to the edit's `now` |
| G2 | The cancel and the edit are one change | `cancel_on_edit` opens its own transaction | an internal `cancel_in_transaction(conn, context, record_type, record_id)` called inside `ledger.update_entry` and `ledger.delete_entry`; the public function stays for other documents |
| G3 | "Resubmitted after an edit" (answer 3) and "approved = what is posted" | the request records only the amount; nothing ties it to the entry's content | a digest of the entry (the canonical header and lines, as sealed, without the posting fields) stored on the request; submit refuses a digest equal to the last Rejected request's; posting refuses unless the approved digest equals the entry now. **Needs a column (baseline gap B1).** |
| G4 | Approvals are by a human | `authorize` refuses Agent origin only; an Import or System context holding `je.approve` could approve | approve and reject refuse any origin but Human (integrity, one sentence) |
| G5 | The audit log records every change (integrity) | `approval_request` and `approval_action` have **no audit triggers**; a request row can be deleted | **baseline gap B2**: audit insert/update triggers on `approval_request`, audit insert on `approval_action`, and a no-delete trigger on `approval_request` (integrity, like `approval_action`'s append-only triggers). Allowed status changes (Pending to Approved, Rejected or Cancelled; Approved to Cancelled) live in the service (H4), with tests |
| G6 | `approved_by` / `approved_at` on the entry | approvals.py never writes them (by design) | posting writes the last approver and their `acted_at`; both are sealed (already in `ledger_chain` header fields) |

**Baseline (only if B1 and/or B2 are approved):** one edit of `migrations/001_company.sql`, previous baseline
copied to `archive/baseline_pre_2_5_4/` with tag `baseline-pre-2.5-4`, failing schema tests first, one rebuild
(`scripts/create_fresh_databases.py --apply`, after asking). B1: `approval_request.document_digest TEXT` (64 hex
CHECK, NULL allowed for document types that do not use it yet). The master baseline does not change.

## Design

### A. A fresh context per action (answer 4)
- `companies.action_context(context)`: the same identity with a new `now` and the company-local `today`, built with
  `dataclasses.replace(context, now=None, today=None)` (the clock is read only in `ServiceContext.__post_init__`,
  which H2 already exempts) and `clock.local_today` with the company time zone. No new clock read in services.
- `App.action_context()` in `app_strata.pyw` returns it for the open company. Screens never pass the stored session
  context to an action.
- Static test (tests/test_static_rules.py): in `app_strata.pyw` and `modules/views_*.py`, every call to
  `ledger.post_journal_entry`, `ledger.submit_entry_for_approval`, `approvals.approve`, `approvals.reject` and
  `periods.close_period` / `close_year` passes an `...action_context()` call as its first argument. Tests that `action_context`
  moves `now` (clock patched) and keeps the user, company, origin and read-only flag.
- CLAUDE.md: remove the stale-now known issue; status_log entry.

### B. Which entries need approval (R11 replaced, nothing lifted except through approval)
An entry needs an Approved request before it posts when any of these holds:
1. **origin Agent**: always, whatever the controls (integrity);
2. **origin Import**: always, one human review (integrity); a second approver or a chain is a control set through
   an "Import batch" policy (`required_count` 2, or two steps), off by default;
3. a manual entry (source none, Manual, Adjustment) with `manual_entry_approval` on and the debits **strictly over**
   the threshold, or no threshold set (R5; an entry equal to the threshold posts);
4. a document source (Bill, Payment, Import, Payroll) whose type has `requires_approval` on (1.6).

Document type of the request: "Import batch" for Import origin and for sources Import and Payroll; "Bill" and
"Payment" for those sources; otherwise "Journal entry". The amount is the entry's total debits. `created_by` is the
entry's creator (for an Agent entry, the human it ran as, so R3's self-approval flag follows). `project_id` is the
one project all lines share, else none.

### C. The ledger functions
- `ledger.submit_entry_for_approval(context, entry_id)`: authorizes `je.create`, runs every posting check that
  does not depend on approval (balanced, two lines, open period, accounts, controlled-account contacts, no
  reversal, no auto-reversal date), works out the document type and amount, computes the digest, then
  `approvals.submit_for_approval`. Refused for an entry that needs no approval ("This entry can be posted
  directly."), while one is Pending, and when the digest equals the last rejected one ("Change the entry before
  sending it again; it was rejected: <reason>.").
- `ledger.update_entry` and `ledger.delete_entry` cancel a Pending or Approved request in the same transaction
  (G1, G2).
- `ledger.post_journal_entry`: the R11 refusals and `APPROVAL_STEP_MESSAGE` are removed. An entry that needs
  approval posts only when, inside the posting transaction: the newest request is Approved, its digest equals the
  entry now, and its amount equals the debits. Otherwise one sentence names the next action (send for approval;
  waiting for step N of M; rejected: reason; approval cancelled by an edit, send again). On success it writes
  `approved_by` / `approved_at` (sealed). An entry with a Pending request cannot be posted directly, even when
  approval is not required.
- Posting stays Human origin only: `je.post` is not agent-allowed, and an Import or System context is still
  refused until the Imports phase builds batch posting (the reversal and auto-reversal refusals stay until step 5).

### D. AGENT_ALLOWED
A static test: no `*.approve` code and neither `je.post` nor `je.reverse` in `permissions.AGENT_ALLOWED`; an
agent-origin call to `approve` or `reject` is denied and logged before any read (already tested; kept).

### E. Pending xfails that flip (tests/test_service_rules_pending.py)
They call a proposed API (`ledger.post_entry(conn, ...)`, a `billing` module), so they are rewritten against the
real services and un-marked:
- `test_manual_entry_over_threshold_needs_approval` (R5, with the boundary: equal posts, one cent over needs it);
- `test_agent_and_import_entries_always_need_human_approval`, split as design_decisions.md says into one test for
  Agent and one for Import, both with every control off.
Expected: **12 xfailed becomes 9**.

### F. Tests first (new tests/test_ledger_approvals.py, plus the static and schema tests)
Each rule above gets a failing test before code: the four triggers for approval and their absence (a manual entry
with approval off posts directly); R5 at, one cent over and with no threshold; Agent and Import with every control
off; R3 (separation off: the run-as human approves and the action is `self_approved`; on: a different human must);
a two-step chain and a 2-of-3 step on a journal entry, posting refused until the last step; an approval limit too
low is denied; an edit after approval cancels it and posting is refused until resubmitted and approved from step
1; delete cancels; a rejected entry needs an edit before resubmission and its request stays Rejected with the
reason; posting refuses a mismatched digest or amount (tampered request); `approved_by` / `approved_at` are the
last approver's and are in the seal (verification OK; changing them is Broken); approve/reject from an Import or
System context refused; the audit log records submit, approve, reject and cancel (if B2); `action_context`.

## STOP points

1. **STOP 1 (only if B1 or B2 is approved):** schema tests first, the baseline edit, archive copy and tag, the
   rebuild (asked before `--apply`). Commit, push, report.
2. **STOP 2, part A:** `action_context` and its static test, the approvals.py changes (G1, G2, G4 and the status
   rules), CLAUDE.md known issue removed. Full suite, commit, push, report.
3. **STOP 3, part B:** the ledger wiring (C), the flipped xfails (E), decisions recorded (next free R codes, with
   index rows), docs (status_log, roadmap, file_map, the "Where we are" paragraph). Full suite, commit, push, then
   step-reviewer and mutation-tester (secrets-auditor is not needed: no auth, keys or codes change), fixes, new
   docs/next_step.md, report.

## Open questions for the owner

1. **B1 (digest column):** approve it? Without it, "resubmit only after an edit" cannot be enforced (any
   resubmission is allowed) and posting relies on `cancel_on_edit` alone to keep the approved content.
2. **B2 (audit triggers and no-delete on approval_request):** approve it? It is an integrity gap today (approvals
   are not in the audit log). The status rules would stay in the service (H4).
3. **Separation at posting:** docs/roles_permissions_design.md says that with `require_separate_approver` on, the
   creator can neither approve nor post. Posting does not check that today. Add it in Step 4 for every entry
   (proposed), only for entries that needed approval, or leave it for later?
4. **Import origin:** Step 4 approves Import-origin entries one entry at a time (document type "Import batch").
   The review of a whole batch (`import_batch`) comes with the Imports phase. Accept?
5. **Period close:** include `periods.close_period` and `close_year` in the fresh-context static test (the known issue names it)?
6. **The other stale xfails:** `test_cannot_post_to_header_or_inactive_account` (2 cases) and
   `test_manual_entry_to_controlled_account_is_blocked` test rules already built in steps 2-3 but still call the
   proposed API. The second one contradicts the decided default (manual entries to controlled accounts are allowed
   and flagged). Rewrite them in Step 4, or leave them for a later clean-up?

## Carried forward

- Phase 3 screens: show the unverified range and the close check's warning; after a key replacement call
  `App.start_key_store()` again; show `KeyReplaced.recovery_code` once.
- `auth.CodeIssued` and `auth.FirstMaster` are still namedtuples, so `_asdict()`, indexing and iteration expose
  their codes; the same fix as KeyReplaced is proposed as a small separate change.
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` remains the one allowed clock read in services (H2).
