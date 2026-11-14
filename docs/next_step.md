# Next step: Phase 2.5 Step 6 (rounding)

Written at the end of Step 5 (2026-11-13). Overwritten at each STOP (CLAUDE.md section 8).
Status: **Step 5 built, reviewed and mutation-tested. One owner question is open (R48, below).** Step 6 is not
planned yet: the next session writes its plan (plan mode) and stops for approval before any code.

**State:** suite **2561 passed, 7 deselected, 5 xfailed** (Step 5 retired the "reversal cannot predate original"
xfail). There was no baseline change, so no rebuild. The development master is empty (no users, companies or keys)
and there are no company files.

## What Step 5 built (decisions L5, R2, R4, R8, R40-R48)

All in `modules/services/ledger.py`, which is still the only writer of the journal tables.
- **One posting core,** `_seal_and_post`. Every entry is posted through it, so one transaction can post several
  entries with gapless numbers and a whole chain. `post_journal_entry` seals exactly what it sealed before.
- **Automatic reversals (L5, R47).**
  - Posting an entry with `auto_reverse_date` posts its Accrual reversal right after it, in the same transaction:
    origin System, created and posted by the poster, the original's source, no approval fields.
  - A missing or closed reversal period refuses the post before anything is numbered, and refuses submitting it
    for approval.
  - The result now also carries `reversal_entry_id` and `reversal_entry_number`, both None for an ordinary entry.
  - The R11 refusal is gone.
- **`void_entry` and `reverse_entry`** (Void and Correction).
  - Who: a person with `je.reverse`, `confirm=True` (exactly True) and a note. Import and System contexts are
    denied with a sentence; Agent is denied by `authorize`.
  - Which entries: manual, Import, Payroll and Conversion. A document's entry is refused with "void the invoice
    instead" (R40).
  - Dates: a Void defaults to the original's date and a Correction to today, and neither may be earlier than the
    original (R41).
  - No second person (R42), no approval (R8), and the A5 control is not applied again.
  - A reversal of a reversal is refused (R43).
  - An accrual with an automatic reversal can only be voided, and then both are voided, each on its own date and
    all or nothing (R4, R44).
  - Losing the race for the slot gives a sentence; any other database error goes through R35.
- **Mirrors (R45):** every line field and flag and every dimension is copied, then checked by the service. A test
  pins `journal_line`'s columns to the copied list, so a new column cannot be missed.
- **Descriptions (R46):** "Void of JE-000012: Rent" and so on. `get_entry` and `list_entries` return
  `display_description`, which shows the person's note: "Void of JE-000012: Rent (note: wrong account)".
- **`approvals.separation_required(row)`** is now the one separation rule for both modules.
- **Tests:** tests/test_ledger_reversals.py, 91 tests, written first. The refusal snapshot (tests/test_ledger_posting.py)
  now also covers `journal_line_dimension`.

## Reviews
- **step-reviewer** on 8d23ba5: approve with changes. Fixed in b5faa82:
  - (medium) reversals of period 13/14 entries. A Void dated the target's date stays in that period with no date
    warnings. Before the fix it fell into period 12, which was wrong for the Pre-adjustment basis and refused
    once period 12 was closed. This is **R48, provisional** (question 1);
  - an IntegrityError is called a race only when the slot is really taken;
  - a sentence for a reversal date with no period;
  - eight tests for the gaps it listed.
- **mutation-tester** on b5faa82: 92 mutations, 79 killed, 13 survived. Five survivors were real gaps, and each
  now has a test that kills it (checked one by one against its mutation):
  - a void by a different person (the void's `created_by` and `posted_by`);
  - a confirm that is not exactly True;
  - a malformed date that sorts after the original;
  - a pair void showing a date warning once;
  - `display_description` with no description.

  The other eight are equivalent:
  - the R48 condition without the adjustment test: an ordinary target's period always holds its date, because
    the resolver refuses anything else;
  - `!= 0` for `== 1` on `require_separate_approver`: the CHECK allows only 0 and 1;
  - the race branch's Accrual-reversal guard and query width: no Void can exist when an automatic reversal is
    inserted;
  - `_slot_taken` narrowed or removed: the unique indexes give the same sentence through the race branch;
  - the pair void's second lookup by target: an automatic reversal is always dated after its accrual.
- **secrets-auditor:** not needed. No change to auth, key storage, recovery, backups, email or feeds.

## Hand check for the owner

There is still no posting screen, so the check runs the real services on a throwaway company in a temporary
folder. From the repo root, in PowerShell:

```
$env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step5.py; Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS
```

The last line must be **"Every step behaved as decided."** These are the sentences to judge (rule 0b):

| Section | What you should see |
|---|---|
| 1 | The accrual posts as JE-000001 on 31 March, and its automatic reversal as JE-000002 on 1 April (origin System), with the description "Automatic reversal of JE-000001: March wages accrued". |
| 2 | "The automatic reversal date (2031-01-01) has no fiscal period yet; add the fiscal year or change the date." |
| 3 | No note: "Say why in the note, so the reason stays with the entry."; not confirmed: "Confirm the void first; ..."; dated too early: "A void cannot be dated before the entry it reverses (2026-03-15)."; a user without the permission is refused with the role sentence; then the void posts ("Void of JE-000003: Rent March (note: wrong account)") and the original shows void 1; voiding again: "JE-000003 is already void."; voiding the Void: "JE-000004 is a reversal; enter a new entry to change its effect." |
| 4 | A Correction dated today (20 March) leaves the original standing; voiding it afterwards: "JE-000005 has already been voided or corrected." |
| 5 | Correcting the accrual: "JE-000001 has an automatic reversal (JE-000002); void JE-000001 and both are voided together, then enter a new accrual."; voiding the automatic reversal alone: "JE-000002 is the automatic reversal of JE-000001; void JE-000001 and both are voided together."; voiding the accrual posts two Voids, on 31 March and 1 April. |
| 6 | Verification OK for 8 entries numbered 1 to 8 with no gap; the accrued wages account nets to 0.00. |

The Step 4 hand check (`tools/hand_check_step4.py`) still ends "Every step behaved as decided."

## Open question for the owner

1. **R48 (provisional; built this way):** when the entry being voided or corrected is in adjustment period 13 or
   14, a reversal dated on that entry's own date is posted in the same period, with no date warnings. That way the
   Pre-adjustment, GAAP and Tax bases each net to zero. A later date takes its month period, as usual. The
   alternative is to always use the month period (period 12 for the year end). That would show a void in the
   Pre-adjustment basis without its original, and it is refused once period 12 is closed. Proposed: keep R48 as
   built.

## Step 6, to plan next session

Rounding (R1, L8): the one-cent `is_rounding_adjustment` line on Import, Payroll and Conversion entries only, to
`rounding_variance_acct_id`; two cents or more is refused, and manual entries have zero tolerance. The entry path
is the narrow `create_document_entry` (docs/audit_readiness_design.md section 13). Read R1, L8 and section 13 by
search before planning. Then Step 7: the five xfails left (payment over-allocation, one allocation target,
reopening with a reason, numbering, period from date), plus the payment allocation gaps placed there in
docs/roadmap.md ("Baseline gaps from the 2026-11-13 design batch").

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
