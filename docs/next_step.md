# Next step: Phase 2.5 Step 4 (approvals in posting)

Written at STOP 3 of Step 1d (2026-11-13). Overwritten at each STOP (CLAUDE.md section 8).
Status: NOT PLANNED. Step 1d is done and waits for the owner's acceptance and hand check. Step 4 starts in plan
mode in a fresh session: write the plan below into a full design, ask the open questions, and stop for approval
before any code.

**State at this STOP:** HEAD is the commit that writes this file, on top of the mutation-check tests for Step 1d
and `da5e697` (the Step 1d review fixes). Suite on the committed tree: **2162 passed, 7 deselected, 12 xfailed**
(about 10 minutes). Working tree clean, `main` pushed. Development databases were rebuilt from the 1d baselines
(old master and the unregistered COMBUZZ.db are in `Backups\20261112-214913\`). The fresh master has no users
until the owner's first run.

## Step 1d as finished (for the record; details in docs/status_log.md)

- Part A: the signed `Key lost` checkpoint (`Unverified`) in the file and the master mirror; the verifier anchors
  on it, reports entries 1..N as unverified (never Broken) and verifies N+1 onwards (KS12, KS14-KS16).
- Part B: `installation_keys.py` replaces a lost installation key (Master, typed phrase NEW LEDGER KEY, password),
  keeps the history of installation keys, binds each copy to its own row (KS21) and starts a key-lost epoch in
  every registered company, archived included (KS13, KS17-KS20).
- Review fixes (da5e697) and the mutation check: 126 mutations, 109 killed at first; tests were added for the 10
  survivors that mattered and all 10 now die. Left as equivalent or defence in depth: I4 (`finish_remaining_
  companies` also checks through `remaining_companies`), I8 (the pre-write KEY_NOT_LOST check; the in-write check
  stops it), V4, V9, V12, V31, S11.

## Step 4 plan (to be designed): approvals in posting

Goal: replace R11's fail-closed refusal with the approval engine, so the entries R11 refuses today can be
submitted, approved and then posted. Strict xfails in tests/test_service_rules_pending.py that belong to this
step flip to pass (`test_manual_entry_over_threshold_needs_approval`, `test_agent_and_import_entries_always_
need_human_approval`).

**Read first (by search):** decisions A8, A9, 1.6, R3, R5, R8, R11, R2; the `approval_policy`, `approval_step`,
`approval_request` tables in `migrations/001_company.sql`; `ledger.post_journal_entry` and its R11 refusal;
`authz.py` (`AGENT_ALLOWED`: the agent never approves); section 0 of CLAUDE.md (approvals are a control, off by
default; agent- and import-origin always need a human).

Proposed scope, for the owner to confirm:
1. `approvals.py` (new service): `submit_for_approval`, `approve`, `reject`, `list_pending`; one policy per
   document type, steps in order; `authorize` before every write; the agent cannot call approve (authz).
2. Posting: an entry that needs approval (R11's list) posts only with an approved request; otherwise the refusal
   names the next action in one sentence. R3 self-approval flagged when `require_separate_approver` is off.
3. Import-origin batches need one human review (always on; second approver is a control, off by default).
4. Every approval and rejection audit-logged; approval limits and chains are later controls (listed, not built).
5. No screen in this step (Phase 3).

**Open questions for the planning chat:**
1. Does Step 4 use the existing `approval_*` tables as they are, or does the baseline need changes (one baseline
   edit with tag and archive copy, one rebuild, as in 1d)?
2. Does an edit to a draft after approval void the approval (proposed: yes, the request goes back to pending)?
3. Is rejection final for that draft, or can it be resubmitted (proposed: resubmit after an edit)?
4. Does the approval need the approver's `now` from a fresh context (known issue: the session context's `now` is
   the time the company was opened)?

Then step 5 (reversals and auto-reversals: R4 pair void, R11's reversal refusal lifted), step 6 (rounding, R1),
step 7 (billing document entries; docs/audit_readiness_design.md "When it lands").

## Carried forward from Step 1d (for Phase 3 screens and later steps)

- Every screen that shows a verification result must show the unverified range (`unverified_through`) and the
  close check's warning; the message text is already built by the service.
- `KeyReplaced` is a namedtuple: a screen reads only `.recovery_code`, shows it once and never logs or serialises
  the result; add a static test when the screen is built.
- After a replacement the app must call `App.start_key_store()` again.
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` is still the one allowed clock read in services (H2); `installation_keys` relies on it through
  `auth._Actor`.
