# Next step: Phase 2.5 Step 5 (reversals and automatic reversals)

Written at the end of the Step 4 follow-up 4 (2026-11-13). Overwritten at each STOP (CLAUDE.md section 8).
Status: **Step 4 and four rounds of owner follow-ups (R27-R31, R32-R36, R37-R38, R39) done; the owner accepted the hand check.**
Step 5 is not planned yet: the next session writes its plan (plan mode) and stops for approval before any code.

**State:** suite **2466 passed, 7 deselected, 6 xfailed**. HEAD: the R39 commit. The development master was
rebuilt from the edited baseline (it gained `throttle_secret`, R32); it is empty (no users, companies or keys) and
there are no company files. The previous empty master is in Backups\.

## Follow-up 4 (owner answer to the follow-up-3 question, R39)

- **R39:** with separation on, the limit refusal's "ask" target leaves out the creator and submitter: "another
  Admin" when one of them is an Admin and another active Admin exists; "an Admin" when neither is an Admin
  (unchanged wording); else "the Master" if the Master is neither; else, with no role holder left, the whole
  refusal is "No one else in this company can approve it; add another approver, or turn off separation of duties
  in Settings > Controls." `authz._admin_target` and `authz._ask_target` build it; `_who_can_approve` became
  `_roles_that_can_approve` (names only). Tests in tests/test_refusal_messages.py (R39 section), written first.
- The hand check (`STRATALEDGER_ALLOW_TEST_KEYS=1 python tools/hand_check_step4.py`) still ends "Every step behaved
  as decided."

## Follow-up 3 (owner answers to the three follow-up-2 questions, R37-R38)

- **R37:** with require_separate_approver on (or no settings row), the approval-limit refusal does not count the
  request's creator or submitter as holding a role that could approve; if no one is left it says to ask an Admin.
  Approve and reject both. `approvals.separation_on(context)` is the shared read; `authz.check_approval_limit`
  takes `not_counted`.
- **R38:** every logger is `strataledger` or under it; `modules/font_loader.py` is `strataledger.fonts`. A static
  test in tests/test_app_logging.py scans every `getLogger` call in app_strata.pyw and modules/.
- **Backlog 19** (docs/roadmap.md): support bundles redact absolute paths and the Windows profile name from the
  logs before they leave the computer. No code now.
- **step-reviewer:** approve with changes. Fixed: a test for the reject path (it bites: removing the exclusion
  from reject turns it red), and the logger scan now also sees a bare `getLogger(...)`. Left as notes:
  - `_not_counted` reads company_settings on every approve or reject, before authorize (not protected data;
    `_load_request` already reads first; rule 10's write order holds);
  - `ledger._separation_on(settings)` and `approvals.separation_on(context)` both treat a missing row as on;
    they could be merged when Step 5 touches ledger;
  - question 1 below.

## Follow-up 2 (owner answers to the four questions, R32-R36)

- **R32 (question 1):** a failed sign-in never writes the typed username. The log says `user=<id>` or
  `user=unknown username`; `auth_event` keeps the user id only (no username) for `Login failed` / `Locked`. The
  throttle key is `auth.throttle_key(secret, name)`, HMAC-SHA256 of the stripped, case-folded name under the
  master's `throttle_secret` (32 random bytes, made on the first failure). Case variants share one lock. The
  limit is written into the decision: the secret is in the same file.
- **R33 (question 2):** `app_strata.pyw` calls `start_logging()` before the window (`DATA_DIR\Logs\strataledger.log`,
  1 MB x 5, R30 filter). If it cannot open, the app starts and says so once. The CLAUDE.md known issue is gone.
- **R34 (question 3):** a limit refusal names only roles that an active user (not the Master) holds in the
  company, by the nearest access row; otherwise "ask an Admin".
- **R35 (question 4):** a database error in any service write is rolled back, logged with its details and shown
  as "Something went wrong saving this; nothing was saved. The details are in the log." (`SaveFailedError`, no
  cause attached).
- **R36 (question 4):** a user without access is told only that, before any wrong-file check.
- Not changed: the Windows `getpass` note (use `--no-prompt` from tools, R31).

To see R32 by hand: sign in with a password typed into the username box five times, then look at
`Logs\strataledger.log` and the master's `auth_event` and `login_throttle`: the text you typed is in none of them.

Reviews of follow-up 2:
- **step-reviewer:** approve with changes. Fixed:
  - the R36 reorder wrote the denial row into the unchecked (wrong) company file. Now the file is still compared
    first; a wrong file gets only the log line, with the no-access sentence when the user has no access;
  - "Ann" and "ann" could be two accounts sharing one throttle counter, so a sign-in as one reset the other's
    lock. New usernames must now be unique ignoring case.

  Left as notes:
  - a missing secret row disables existing locks (needs the master file in hand, which is R32's limit; commented);
  - question 1 below.
- **secrets-auditor:** no Critical or High. Fixed:
  - (Medium) a password typed into the username box stayed forever as an HMAC that is cheap to guess against
    with the master file in hand. Rows idle for a day are now purged, and the R32 limit is reworded;
  - the secret is a `SecretKey`;
  - the R35 log line no longer prints an earlier error it interrupted (it may quote typed text);
  - tests for the upper-case marker, the typed password, the secret's hex and a temporary password when the save
    fails.

  Left as notes: questions 2 and 3 below.

## Hand check for the owner (Step 4 and R27-R31)

There is no posting screen yet, so the check runs the real services on a throwaway company in a temporary folder
(never the real databases) and prints what a person would see. From the repo root, in PowerShell:

```
$env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step4.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS
```

The variable lets this one run use the test suite's fixed chain key (`keys.FixedKeyProvider` refuses without it;
without it the script prints one line and does nothing). The last line must be **"Every step behaved as decided."**
Read the sentences on the way; these are the ones to judge (rule 0b). No sentence shows a permission code (R27).
The test world names each role by its code, so a sentence reads "the APPROVER role"; a real company shows the
role's name.

| Section | What you should see |
|---|---|
| 1 | Every control off: "This entry can be posted directly; it does not need approval." and the entry posts. |
| 2 | Threshold 1,000.00: 1,000.00 posts; 1,000.01 is refused "...send it for approval first."; "already waiting"; "waiting for approval (step 1 of 1)"; after Anna approves it posts with `approved_by` = Anna and `approved_at` = her approval time (15:30). |
| 3 | Two steps: Carl approving first is told "Step 1 of 2 must be approved first by someone in the APPROVER role; you can approve step 2 once it is complete."; after Anna, posting says "step 2 of 2"; Carl completes it. |
| 4 | An edit after approval: "The approval was cancelled because the entry was changed; send it for approval again."; the new request starts at step 1 (Carl gets the step-order sentence again). |
| 5 | Reject with no reason: "Give a reason for rejecting it, so the preparer knows what to fix."; posting says "This entry was rejected (Wrong account); change it and..."; sending it again unchanged, or after re-saving the same lines, is refused; after a real change it can be sent. |
| 6 | Agent and Import entries with every control off: refused until approved; "Only a person can approve or reject..." and "the denial log names je.approve (the sentence above does not)" (R29); the agent posting: "The AI assistant cannot post entries; a person posts the entry after it is approved."; "An imported entry is posted by a person after review..."; a person posts both. |
| 7 | Separation on: "This company needs a different person to post an entry you created; ask a colleague to post it."; another clerk posts it. The Admin sends the clerk's entry for approval and may not approve it: "...approve the entry you sent for approval; ask a colleague to approve it." (R28); Anna and Carl approve and clerk2 posts. |
| 8 | Verification OK; changing one approver breaks the chain at that entry. |
| 9 | The audit log holds the approval requests and actions; denials are logged. |
| 10 | A fresh context has the current time, not the time the company was opened. |

R30 and R31 are not in the script. R30 is covered by tests/test_rejection_logging.py, which logs a marked reason
every way a screen might and checks that the log file never holds it. To see R31:
`python scripts/create_fresh_databases.py --apply --no-prompt` rebuilds the development databases without the
first-Master question (it is a real rebuild: run the dry run first, as always).

## What this follow-up built (owner answers 1-5 to the Step 4 questions)

- **R27 (answer 3):** no refusal a person sees shows a permission code; the code is only in the denial log.
  `authz.denial_message` builds the default sentence from the denial's reason (role, project scope, no access,
  inactive role or user, archived or missing company, wrong file, agent). Approval sentences give the step order,
  the role that can approve, and for a limit the roles whose limit covers the amount, or an Admin. Master-only
  actions, user management, a read-only company and acting twice on a request have their own sentences. A user
  without access to a company is told only that, not whether it exists or is archived. Static scans in
  tests/test_refusal_messages.py check refusal calls, module-level sentences and `*_message` returns for
  code-shaped words. The pattern needs two letters on each side of the dot, so "1,000.00" and "e.g." pass. The
  allow-list holds two entries, `.db` and `.sql` file names.
- **R28 (answer 1):** with separation on, neither the creator nor the submitter may approve or reject. With it
  off, the submitter's approval is flagged `self_approved` like the creator's, so it stops counting at posting
  once separation is turned on.
- **R29 (answer 2):** the "only a person" denial reads the request first; its `access_event` row names the
  approve permission. It is still denied before any write.
- **R30 (answer 4):** rejection reasons never reach the log file.
  - Mechanism: `ServiceError(..., log_message=...)` with `errors.log_text`, and `logging_setup.LogMessageFilter` on
    the file handler. The filter cleans error objects in the message, the arguments and the traceback, and
    follows causes, contexts (also after `from None`) and exception groups.
  - Static tests: one forbids logging an error's text (f-strings, `str()`, `repr()`, `.args`, formatting,
    `format_exc()`) or a reason. Another requires `log_message=` wherever `reason_text(` builds a sentence.
- **R31 (answer 5):** `create_fresh_databases.py --no-prompt`; input that ends early ends with "No answer was
  read; no Master was created." and exit code 0.
- New `modules/services/money.py` (amounts in sentences; the ledger uses it too).

## Reviews

- **step-reviewer:** approve with changes; permission decisions unchanged apart from R28. Fixed:
  - the log filter missed a chain cut with `from None` and errors quoting a hidden one; logging an error's text
    is now banned by a static test;
  - the R27 scan's blind spots (module-level sentences, `*_message` returns, the deny calls' message
    arguments);
  - the agent sentence was used for an allowed code the user's role lacks;
  - three sentences without a next step (password reset, read-only company, already acted);
  - the two UI-model tests that still built "Not permitted" errors.

  Left as a hint: `_who_can_approve` names a role even when nobody holds it (question 3 below).
- **secrets-auditor:** no Critical or High findings. Fixed:
  - the same filter gaps, plus exception groups and reasons with quotes or newlines;
  - the R30 static test now covers attribute calls and every `reason_text(` use;
  - the denial no longer tells a user without access whether a company exists or is archived;
  - the Master gets "restore it ... first" for an archived company.

  Open: questions 1 and 2 below.
- **mutation-tester:** 116 mutations, 88 killed, 28 survived. Tests were added for the 20 real gaps; 19 of them
  were re-run against their mutation and are killed:
  - the Master and a missing company;
  - a missing role;
  - `deny` with no code;
  - Admin never listed;
  - a limit equal to the amount;
  - the default creator sentence;
  - already acted, in planning and in the transaction;
  - step 2 named after step 1;
  - only the unfilled role named;
  - role names and their order;
  - three roles;
  - dict arguments, `__cause__`, exception groups, a cycle of linked errors and a trailing newline in the log filter.

  The 20th (a later step open to any role) cannot happen: a policy step must name a role.

  Equivalent survivors:
  - "do this" for an unknown code (unreachable);
  - "aeiou" (no document type starts with o or u);
  - `> 1` / `> 2` roles (same text for two);
  - the later-step scan starting at the first open step, and `<=` on later steps (unreachable);
  - the order of the three redaction forms (the reason is removed either way).

## Open questions for the owner

None. The follow-up-3 question was answered (R39).

## Step 5, to plan next session

Reversals and automatic reversals (the refusals in `ledger._postable` for `reverses_entry_id` and
`auto_reverse_date`, R11's remainder), then step 6 (rounding) and step 7 (the remaining six xfails in
tests/test_service_rules_pending.py: reversal date, payment over-allocation, one allocation target, reopening
with a reason, numbering, period from date). Read docs/decisions_2026-11-11.md by code (grep) and the reversal
parts of docs/design_decisions.md before planning. New refusals follow R27 (the static scan enforces it) and any
sentence quoting typed text carries a `log_message` (R30).

## Carried forward

- Phase 3 screens:
  - show the unverified range and the close check's warning;
  - after a key replacement, call `App.start_key_store()` again;
  - show `KeyReplaced.recovery_code` once;
  - every post, approval and close passes `self.app.action_context()` (the static test enforces it);
  - log an error by passing the error object, never its text (R30, static test).
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` remains the one allowed clock read in services (H2).
- Phase 3 screens show `SaveFailedError` like any service error (its sentence only) and never log typed text.
