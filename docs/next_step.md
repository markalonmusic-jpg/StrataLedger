# Next step: Phase 2.5 Step 5 (reversals and automatic reversals)

Written at the end of Step 4 (2026-11-13). Overwritten at each STOP (CLAUDE.md section 8).
Status: **Step 4 done, waiting for the owner's hand check.** Step 5 is not planned yet: the next session writes
its plan (plan mode) and stops for approval before any code.

**State at the end of Step 4:** suite **2294 passed, 7 deselected, 6 xfailed**. HEAD: the commit that adds this file (after 9ed6f83).
The development master is empty (no users, companies or keys) and there are no company files.

## Hand check for the owner (Step 4)

There is no posting screen yet, so the check runs the real services on a throwaway company in a temporary folder
(never the real databases) and prints what a person would see. From the repo root, in PowerShell:

```
$env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step4.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS
```

The variable lets this one run use the test suite's fixed chain key (`keys.FixedKeyProvider` refuses without it;
without it the script prints one line and does nothing). The last line must be **"Every step behaved as decided."**
Read the sentences on the way; these are the ones to judge (rule 0b):

| Section | What you should see |
|---|---|
| 1 | Every control off: "This entry can be posted directly; it does not need approval." and the entry posts. |
| 2 | Threshold 1,000.00: 1,000.00 posts; 1,000.01 is refused "...send it for approval first."; "already waiting"; "waiting for approval (step 1 of 1)"; after Anna approves it posts with `approved_by` = Anna and `approved_at` = her approval time (15:30). |
| 3 | Two steps: Carl cannot approve first; after Anna, posting says "step 2 of 2"; Carl completes it. |
| 4 | An edit after approval: "The approval was cancelled because the entry was changed; send it for approval again."; the new request starts at step 1. |
| 5 | Reject needs a reason; posting says "This entry was rejected (Wrong account); change it and..."; sending it again unchanged, or after re-saving the same lines, is refused; after a real change it can be sent. |
| 6 | Agent and Import entries with every control off: refused until approved; "Only a person can approve or reject..."; the agent cannot post ("Not permitted: je.post"); "An imported entry is posted by a person after review..."; a person posts both. |
| 7 | Separation on: "This company needs a different person to post an entry you created; ask a colleague to post it."; another clerk posts it. |
| 8 | Verification OK; changing one approver breaks the chain at that entry. |
| 9 | The audit log holds the approval requests and actions; denials are logged. |
| 10 | A fresh context has the current time, not the time the company was opened. |

## What Step 4 built (R15-R26)

- **Part A (0b00935):** `companies.action_context` / `App.action_context` (R19) and a static test that screens,
  `app_strata.pyw` and `*_model.py` pass `action_context()` to post, submit, approve, reject, the closes and the
  close checkpoint; approvals: edits cancel Pending or Approved (R21), `cancel_in_transaction`, only a person
  approves or rejects (R23), `ALLOWED_STATUS_CHANGES` (R16).
- **Part B (431f2e2):** `ledger.submit_entry_for_approval` and the posting gate (R15, R17, R20, R24),
  `ledger_chain.entry_digest`, `approvals.request_state`, edits and deletes cancel in their own transaction, the
  close checkpoint with a fresh context (R26), six pending xfails rewritten (R25; 12 xfailed became 6).
- **Review fixes (9ed6f83):** closing never blocks; submit reads, digests and inserts in one write transaction;
  re-saving the same lines is not a change; a creator's approval made while separation was off stops counting when
  it is turned on (no dead end); the Import-context post is a logged denial; clearer sentences.
- **Mutation fixes (this commit):** 12 tests for real survivors, each now killed; `tools/hand_check_step4.py`.

**Corrected plan wording:** the Step 4 plan said "an Import or System context is still refused" at posting. Only
Import is refused (R18). System contexts post document entries as they did before Step 4 (without `confirm`), and
R17 applies to them too. The reviewer read it the same way.

## Reviews

- **step-reviewer:** approve with changes. Fixed: closing could be blocked by a non-service error; the
  separation dead end; the submit race; the line re-save loophole in R22; message wording; test gaps (rollback of
  the edit with its cancel, refused submits, approval tables in the `refused()` snapshot, `*_model.py` in the
  R19 checker). It also noted that a creator's approval in an earlier step was not caught after separation was
  turned on: now caught (any self-approved action stops counting).
- **secrets-auditor:** no Critical, High or Medium findings; no key material in logs, messages or rows. Fixed:
  a DEBUG-log test for the chain key over the whole approval flow; the denial row's user and actor are asserted;
  the Import-context post is logged; closing catches every error. Left as is (question 2 below): the "only a
  person" denial records no permission code.
- **mutation-tester:** 112 mutations, 88 killed, 24 survived. Tests added for the 12 real gaps (separation off
  posts and stays "already approved"; no settings row counts as separation on; two projects give no project;
  Payroll follows the Import batch switch; dimensions are in the digest, unit and ledger level; `approved_at` is
  the last approval's; a self-approval in an earlier step stops counting; the changed-while-sending refusal;
  `App.action_context` without a company; the checker refuses a lookalike call). Each was re-run against its
  mutation and is killed. Equivalent or defence in depth (not tested): the project passed to the submit
  permission (no submit permission is project-scoped today: `je.create`, `bill.create`, `payment.make`,
  `import.run` are not in `PROJECT_SCOPED`); `debits <= 0` (unreachable after `check_lines`); line order in the
  digest (same order at submit and post); `is_posted` in `POSTING_FIELDS` (always 0 on a draft); first or last
  rejection reason (one rejection ends a request); `approved_by` from any last action and `self_approved`
  counting rejections (read only when Approved); `_record` writing the status directly (already checked Pending);
  `_change_status`'s rowcount and `AND status = ?` guards (race only); `_live_requests` first or last (at most one
  live request without hand-edited SQL).

## Open questions for the owner

1. **Submitter and approver:** separation compares the approver with the entry's creator only. User B can submit
   A's draft and then approve it (with separation on, B is not the creator). Should the submitter also be barred
   from approving when separation is on?
2. **The "only a person" denial** is logged before any read of the request, so its `access_event` row has no
   permission code (user, origin, actor, record are there). Keep it, or read the request first so the row names
   `je.approve` / `import.approve`?
3. **Older sentences not yet rule 0b:** an approver who cannot fill the open step, or is over their limit, sees
   "Not permitted: je.approve"; a missing reason says "A reason is required to reject" (no next step). These
   predate Step 4. Fix them now as a small change, or with the approval screens in Phase 3?
4. **Rejection reasons** appear in refusal sentences and so can reach the log file (rule 12). They are what a
   person typed, not secrets. Keep, or log a fixed sentence and show the reason only on screen?

## Step 5, to plan next session

Reversals and automatic reversals (the refusals in `ledger._postable` for `reverses_entry_id` and
`auto_reverse_date`, R11's remainder), then step 6 (rounding) and step 7 (the remaining six xfails in
tests/test_service_rules_pending.py: reversal date, payment over-allocation, one allocation target, reopening
with a reason, numbering, period from date). Read docs/decisions_2026-11-11.md by code (grep) and the reversal
parts of docs/design_decisions.md before planning.

## Carried forward

- Phase 3 screens: show the unverified range and the close check's warning; after a key replacement call
  `App.start_key_store()` again; show `KeyReplaced.recovery_code` once; every post, approval and close passes
  `self.app.action_context()` (the static test enforces it).
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` remains the one allowed clock read in services (H2).
- `scripts/create_fresh_databases.py --apply` ends with an EOFError in a non-interactive shell (its first-Master
  prompt); the rebuild itself completes. Small fix if wanted: skip the prompt when stdin is not a terminal.
