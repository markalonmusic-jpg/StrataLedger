# Next step: Phase 2.5 Step 6 (rounding)

Written 2026-11-14, at the STOP after R48 was made final. Overwritten at each STOP (CLAUDE.md section 8).
Status: **the Step 6 plan below is waiting for the owner's approval. No Step 6 code has been written.**

**State:** suite **2565 passed, 7 deselected, 5 xfailed**. The baseline did not change, so no rebuild is needed.
The development master is empty and there are no company files.

## Done this session: R48 is final

- The owner accepted R48 as built. A Void or Correction dated the same day as its target, when the target is in
  period 13 or 14, is posted in that same period.
- When that period is closed, the reversal is refused with the next step and is never moved to another period:
  "FY2026-13 is closed; reopen it with a reason, or date the void in the next fiscal year." The service had
  already refused it. Only the sentence is new.
- A pair void (R4) cannot take a date, so its sentence still says to reopen the period.
- Tests (tests/test_ledger_reversals.py):
  - a Void and a Correction into a closed period 13 are refused and write nothing, with period 12 open;
  - a Void dated in the next year still works;
  - a pair void with period 13 closed writes nothing.

## Step 6 plan (rounding: L8, R1, docs/audit_readiness_design.md section 13)

**The rule, already decided:**
- Only entries from three sources may carry a rounding line: Import (CSV), Payroll and Conversion.
- An entry from one of those sources that is out of balance by exactly 1 cent gets one line of 1 cent to
  `company_settings.rounding_variance_acct_id`, with `is_rounding_adjustment = 1`.
- 2 cents or more is refused. Manual entries have zero tolerance (posting already refuses any imbalance).

**Proposed build** (the decision codes R49 and up are proposed and waiting for approval):

1. **`ledger.create_document_entry(conn, context, *, source, entry_date, lines, description=None,
   reference=None, post=False)`**, as section 13 describes it:
   - it runs inside the caller's write transaction and does not authorize;
   - the context's origin must be System or Import;
   - its lines go through `check_lines`;
   - with `post=True`, it posts through `_seal_and_post` in the same transaction. An Import-origin entry still
     needs its approval, so it cannot be posted this way (R18).
   - `ServiceContext.as_system()` and `as_import()` return a copy of the context with that origin and the same
     `user_id`.
2. **Rounding happens when the draft is saved, not when it is posted (R49, Q1).** One helper, `_rounding_line`,
   is called by `create_document_entry`. It is also called by `update_entry` when the draft's source is one of
   the three: the old rounding line is removed and the difference is worked out again.
   - The approver sees the line, and the R15 digest covers it, so approving and then posting needs no
     re-approval.
   - If debits are higher, the 1 cent is a credit; otherwise it is a debit.
   - The line has the memo "Rounding (1 cent)", no contact, project or dimensions, and is the entry's last line.
3. **2 cents or more (R50).** Rule 2 lets an unbalanced draft be saved, so the draft is saved without a rounding
   line. Submit and post refuse it with this sentence: "This entry is out of balance by 0.02; only a 1-cent
   rounding difference is balanced automatically. Correct the amounts and import it again."
4. **No rounding account (R51).** If the setting is empty, or its account is inactive, not postable or has child
   accounts (C2), the entry is refused when it is saved: "Choose a rounding account in Company Settings >
   Accounts, or correct the 1-cent difference."
5. **Posting checks the flag again (R52, integrity).** At posting, an entry may hold at most one
   `is_rounding_adjustment` line. That line must be 1 cent, on the rounding account, and the entry's source must
   be one of the three. Anything else is refused before a number is taken.
   - Reversals keep their original's source and copy the flag (R45), so a Void of an imported entry with a
     rounding line passes.
   - Callers still cannot set the flag: it is not in `LINE_FIELDS`.
6. **Results.** `create_document_entry` returns `rounding_cents` (0, 1 or -1). `get_entry` already returns the
   line with its flag, so the import review screen can show the note (the "info flag" in L8).
7. **Who may call it (static test, section 13).** An AST scan of `modules/` names the only modules that may call
   `create_document_entry`, `as_system` or `as_import`, and the literal sources each may pass. The table is in
   section 13. Today only `ledger.py` calls it; the other rows wait for their modules.
8. **Is `create_entry` limited to manual sources now? (Q2.)** Section 13 says `create_entry` takes only manual
   sources once `create_document_entry` exists. The roadmap places that with billing in Step 7. Proposed:
   do it in Step 6.
   - Then there is one path for document and import entries, and rounding cannot be bypassed.
   - Tests that make Import entries through `create_entry` move to `create_document_entry`. These include
     test_a_person_voids_an_imported_entry and the Step 4 Import approval tests.
   - Step 7 then only adds the billing caller.

**Tests first** (tests/test_ledger_rounding.py, plus the static test in tests/test_static_rules.py):
- each of the three sources:
  - 1 cent each way gives one line on the right side, flagged;
  - 0 cents gives no line;
  - 2 cents saves the draft, and posting refuses it with the sentence;
- manual entries:
  - 1 cent off is refused at posting;
  - a Human or Agent context cannot reach `create_document_entry`;
- the rounding account is missing, inactive or a parent;
- `update_entry` works the rounding out again (1 cent to 0, 0 to 1, 1 cent to the other side);
- the digest covers the line: approve, then post with no re-approval;
- the posting check refuses each of these with the flag forced in the database:
  - two rounding lines;
  - a 2-cent line;
  - a line on the wrong account;
  - a manual entry with the flag;
- a Void of a rounded Import entry mirrors the line and verifies;
- the chain verifies after rounded entries are posted;
- the static caller test: a temporary module outside the table, or a non-literal source, makes it fail.

**Files:**
- modules/services/ledger.py
- modules/services/context.py
- tests/test_ledger_rounding.py (new)
- tests/test_static_rules.py
- the tests that move to `create_document_entry` (Q2)
- docs/decisions_2026-11-11.md (R49 and up, with index rows)
- docs/audit_readiness_design.md section 13 (when it lands)
- docs/roadmap.md, docs/status_log.md and this file

No baseline change: the column, the setting and the template account (8020 Rounding Variance) already exist.

**Reviews:** step-reviewer, then mutation-tester on the commit. secrets-auditor is not needed.

## Open questions for the owner (Step 6)

1. **Q1. When is the rounding line written?** Proposed: when the draft is saved, so the approver sees it and the
   approval covers it. The alternative is to add it at posting. That would change an approved Import entry after
   its approval, so every approval would have to be done again.
2. **Q2. Limit `create_entry` to manual sources in Step 6?** Proposed: yes. The alternative is to wait for
   Step 7, as section 13 says. Until then an Import or System context could save an Import entry through
   `create_entry`. That entry would never be rounded, and posting would refuse its 1 cent.
3. **Q3. A difference of 2 cents or more.** Proposed: the draft is saved and posting refuses it (rule 2). The
   alternative is to refuse it already when the importer saves the entry, which would stop a bad file earlier.
   That alternative breaks rule 2 for these three sources only.

## Then Step 7

- The five xfails left: payment over-allocation, one allocation target, reopening with a reason, numbering and
  period from date.
- The payment allocation gaps placed there in docs/roadmap.md ("Baseline gaps from the 2026-11-13 design
  batch").
- "Reopening with a reason" is the next step that the R48 sentence names.

## Carried forward

- Phase 3 screens:
  - show the unverified range and the close check's warning;
  - after a key replacement, call `App.start_key_store()` again;
  - show `KeyReplaced.recovery_code` once;
  - every post, approval, close, void and correction passes `self.app.action_context()` (the static test
    enforces it for posts, approvals and closes; extend it to void and reverse when the screen is built);
  - show `display_description` for entries;
  - log an error by passing the error object, never its text (R30, static test);
  - show `SaveFailedError` like any service error (its sentence only).
- Backlog 21: the control "voids and corrections need a second person" (R42), off by default, listed on the
  Audit-ready page. Not built.
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` remains the one allowed clock read in services (H2).
