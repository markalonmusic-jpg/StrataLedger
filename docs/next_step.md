# Next step: owner's hand check of Step 6, then Phase 2.5 Step 7

Written 2026-11-14, at the STOP after Step 6. Overwritten at each STOP (CLAUDE.md section 8).
Status: **Step 6 is done and committed. Step 7 has not been planned in detail or started.**

**State:** suite **2740 passed, 7 deselected, 5 xfailed**. The baseline did not change, so no rebuild is needed. The development master is
empty and there are no company files.

## Done: Step 6 (rounding and document entries; L8, R1, R49-R55)

- **R48 check.** `periods.reopen_period` (step 2.4b) reopens period 13 or 14 with a confirmed, logged reason;
  when the whole year is closed it asks for `reopen_year` first. A test reopens each and then the void posts
  (tests/test_ledger_reversals.py). The sentence "reopen it with a reason, or date the void in the next fiscal
  year" offers only what exists, so it stands.
- **R49** (your answer 1). The 1-cent line is written when the draft is saved and worked out again on every
  save. Posting checks it again (R53).
- **R50** (answer 2). `create_entry` and `update_entry` take manual sources only (none, Manual, Adjustment), for
  every origin. The Import and System tests moved to `create_document_entry`.
- **R51** (answer 3). A difference of 2 cents or more on an Import, Payroll or Conversion entry is refused when
  the importer saves it. Nothing is saved, and the sentence names the entry, its source rows and the difference.
- **R52.** A 1-cent entry with no usable rounding account is refused when saved, with what to do.
- **R53.** Posting refuses:
  - a rounding line on another source;
  - two rounding lines;
  - a line that is not exactly 1 cent;
  - a line not on the current rounding account.
- **R54.** `ledger.create_document_entry`, `ServiceContext.as_system()`/`as_import()` (an Agent cannot use them)
  and the static caller test.
- **R55 (PROVISIONAL, please confirm).** The step-reviewer found that a System context could save and post an
  Import or Payroll entry with no human review. Section 0's integrity rule says import batches always need one, so:
  - Import and Payroll entries are saved only with origin Import;
  - a document's draft (Invoice, Bill, Payment, Deferral, Completion) is changed or deleted only through its
    document ("This entry was made by an invoice; change the invoice instead.").
- **Reviews:**
  - step-reviewer on 513aedc: approve with changes, fixed in 0695522.
  - mutation-tester: 53 mutants, 48 killed. The 5 survivors were all in how the rounding line is written and
    recognised. Each now has a test that kills it:
    - lines sent back as read, for all three sources;
    - the rounding line copies nothing from the other lines;
    - a line that looks like the rounding line but differs in memo, contact, project or account is kept as a
      person's line.
  - secrets-auditor: not needed.

## Hand check (for the owner)

In PowerShell, from the repo root:

    $env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step6.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS

It builds a throwaway installation in a temporary folder and never touches the real databases. Read each
numbered block against this list. The last line should say "Every step behaved as decided."

1. No rounding account: the payroll file is refused whole, naming PR-0412 (rows 4-5) and the 0.01.
2. With 8020 set: PR-0411 has no rounding line. PR-0412 has "8020 Rounding Variance: Cr 0.01  Rounding
   (1 cent)" as its last line.
3. A file with PR-0414 off by 0.02 is refused whole: "...so nothing was saved. Correct the amounts and import it
   again."
4. These are all refused, each with its own sentence:
   - a person labelling a manual entry as Payroll;
   - an agent acting as the importer;
   - payroll saved and posted as the system.
5. A manual entry 1 cent off is refused at posting (zero tolerance).
6. The reviewer approves PR-0412 and the clerk posts it as JE-000001 with no new approval.
7. Its void (JE-000002) mirrors all three lines, the rounding line included.
8. Verification OK, numbers 1 to 2 with no gap. The rounding account is back to 0.00.

## Open questions for the owner

1. **R55.** Confirm it, or say what should change. It is the only Step 6 decision not taken from your answers.

## Then Step 7 (plan to be written for approval)

- The five strict xfails left in tests/test_service_rules_pending.py:
  - payment over-allocation;
  - one allocation target;
  - reopening with a reason (check first which part `reopen_period` already covers);
  - numbering;
  - period from date.
- The payment allocation gaps placed there in docs/roadmap.md ("Baseline gaps from the 2026-11-13 design
  batch"), including `payment_allocation` and the `allocation_one_target` CHECK (B6).
- The billing caller of `create_document_entry` (its row in the static caller table).

## Carried forward

- Phase 3 screens:
  - show the unverified range and the close check's warning;
  - after a key replacement, call `App.start_key_store()` again;
  - show `KeyReplaced.recovery_code` once;
  - every post, approval, close, void and correction passes `self.app.action_context()` (the static test
    enforces it for posts, approvals and closes; extend it to void and reverse when the screen is built);
  - show `display_description` for entries;
  - log an error by passing the error object, never its text (R30, static test);
  - show `SaveFailedError` like any service error (its sentence only);
  - the import review screen shows the rounding line's note (L8 "info flag"); `get_entry` returns the flag.
- Backlog 21: the control "voids and corrections need a second person" (R42), off by default, listed on the
  Audit-ready page. Not built.
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` remains the one allowed clock read in services (H2).
