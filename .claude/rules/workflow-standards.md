# Workflow standards: done, review gate, fix before moving on

Applies to every session and agent (owner rule, 2026-11-17). Subagents report to the main session, which
applies the gate. Where this file and CLAUDE.md section 8 differ, this file wins.

## 1. Definition of done
- Matches the task, the decisions it cites (AX1-AX8 and others) and, for a screen, the approved mockup. No
  unapproved scope: anything extra is listed as a proposal, not built. PROPOSED items are not built as final.
- `python -m pytest -q` passes in full; edge cases have tests; no SQL or business logic in UI code (rules 7, 11).
- Ends with a summary of 5 lines or fewer: what changed, files touched, test result, known risks.

## 2. Review gate (stop and check)
- Never start the next step, STOP or phase on your own.
- Show a short checklist: (a) how to check the change by hand or by running it, (b) the pytest result line,
  (c) `git status` and `git diff --stat` showing no unrelated files changed.
- Wait for the owner's explicit "Approved" before any further work.

## 3. Fix mode (before moving on)
- When the owner flags an issue or a test fails: stop forward work, find the root cause, fix only the broken
  behaviour (test first), re-run the full suite, then show the review gate again.
- No symptom patches, skipped or loosened tests, or work on dependent tasks until the fix is approved.
- A bug pattern seen twice gets a one-line prevention rule below (here rather than in CLAUDE.md, MR7).

## Prevention rules
- (none yet)
