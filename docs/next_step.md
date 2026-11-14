# Next step: Phase 2.5 Step 5 (reversals and automatic reversals)

Written at the STOP after the R39 review and the design batch (2026-11-13). Overwritten at each STOP (CLAUDE.md
section 8). Status: **plan written, waiting for the owner's approval. No Step 5 code exists.**

**State:** suite **2471 passed, 7 deselected, 6 xfailed** (the R39 review added five tests). The development
master is empty (no users, companies or keys), and there are no company files. Step 5 needs no baseline change,
so no rebuild, unless the owner answers question 6 with "yes".

## Done since the last STOP

- **R39 review** (step-reviewer on d141718): approve with changes, and the changes were tests only. Five tests were
  added to tests/test_refusal_messages.py: no Admin in the company asks the Master; an inactive Master is not
  asked; reject leaves out the Admin creator; a missing settings row; two role holders with the Master. Each was
  proven against a mutant of authz.py or approvals.py (5 of 5 killed). One note was left as is: an Admin
  inherited from a parent company is not tested for R39 (it reuses `_access_role`, which is tested elsewhere).
- **Design batch:** five docs-only commits, then the owner accepted every proposed answer (CM3, BF1, EX1) and the
  Ramp double-booking test requirement. Every baseline gap is placed under its step in docs/roadmap.md ("Baseline
  gaps from the 2026-11-13 design batch"). **Step 5 needs none of them.** It keeps the accrual link that CB1 uses
  (`auto_reverse_date` on the original; `reversal_reason = 'Accrual reversal'` and `reverses_entry_id` on the
  reversal; the reversal keeps its original's `source`).

## Step 5 plan (for approval)

### What is built already (the starting point)
- **Baseline:**
  - `journal_entry` columns: `reverses_entry_id`, `reversal_reason` (Void, Accrual reversal, Correction),
    `reversal_note` (required and non-blank for Void and Correction), and `auto_reverse_date` (after the entry
    date, never on a reversal).
  - Two slot indexes (R4): one Void-or-Correction reversal per entry and one Accrual reversal per entry.
  - The posting trigger refuses a reversal of an unposted or voided entry, and one that does not mirror its
    original by account, contact, project, cost code and deferral. It does not compare dimensions or memos.
  - `journal_entry_void_on_reversal` sets `is_void` on the original when a Void reversal posts; the posted-entry
    lock allows only that change.
  - All the reversal fields, `auto_reverse_date` included, are hashed by the chain and covered by the approval
    digest (R15).
- **Code:**
  - `ledger._postable` refuses a draft with `reverses_entry_id` and a draft with `auto_reverse_date` (R11's
    remainder).
  - `update_entry` refuses reversal drafts.
  - Drafts may already carry `auto_reverse_date`, checked to be later than the entry date.
  - `je.reverse` exists (Ledger, not sensitive) and is seeded at the Standard level. It is not in
    `AGENT_ALLOWED`.
- **The pending xfail** `test_reversal_cannot_predate_original` in tests/test_service_rules_pending.py was listed
  for step 7. It belongs to this step, so Step 5 rewrites it against the real service (R25) and removes it from
  the pending file (6 xfails become 5).

### What Step 5 builds (all in `modules/services/ledger.py`, the only writer of the journal tables)

1. **One internal posting core**, `_post_in_transaction(conn, context, entry_id, ...)`, split out of
   `post_journal_entry`. It numbers the entry, takes the chain head, seals and writes, inside the caller's
   transaction. `post_journal_entry`, the reversal actions and the automatic reversal all use it, so the numbering
   stays gapless (L4) and the chain has no hole however many entries one transaction posts.
2. **Automatic reversals (L5, R2, R11).** Posting an entry with `auto_reverse_date` posts the original, then in
   the same transaction creates and posts its reversal:
   * dated `auto_reverse_date`, with `reversal_reason = 'Accrual reversal'` and `reverses_entry_id` set to the
     original;
   * the original's source, origin `System` (the narrow ledger path in audit design 13), and `created_by` and
     `posted_by` set to the person who posted;
   * no approval fields and no `confirm` (R2). The original's approval covers it, because the digest includes the
     date.

   The reversal date's period must exist and be open. If not, the whole post is refused before anything is
   numbered: "The automatic reversal date (2027-01-01) has no open period; open it or change the date." (The
   wording distinguishes a missing period from a closed one.) The R11 refusal for `auto_reverse_date` is removed.
3. **`void_entry(context, entry_id, *, note, entry_date=None, confirm=False, acknowledge_date_warnings=False)`.**
   Posts a Void reversal and marks the original void. The order of checks:
   1. authorize `je.reverse` (rule 10; Agent is already refused there);
   2. Human origin only;
   3. `confirm=True` (R2);
   4. a non-blank note (R9);
   5. the target is posted and not void;
   6. the slot is free;
   7. the date is not before the original's (the xfail) and its period is open.

   Then mirror lines (debit and credit swapped; account, contact, project, cost code, deferral, batch, retainage
   flag, external ref, memo and the control-override and rounding flags copied; dimensions copied verbatim, never
   re-resolved, JD1), posted through the core. The voided original's period and the void's period are both
   checked. Date warnings (L6, R12) apply as for a Human post.
4. **`reverse_entry(context, entry_id, *, note, entry_date=None, confirm=False, acknowledge_date_warnings=False)`**:
   the same as `void_entry` with `reversal_reason = 'Correction'`. The original is not marked void. The person then
   enters the corrected entry as a normal draft.
5. **Pair void (R4).** `void_entry` on an entry that has an Accrual reversal voids both in one transaction: a Void of
   the original and a Void of its automatic reversal. If either period is closed, nothing is written: "JE-000012
   and its automatic reversal JE-000013 must both be voided, and February 2027 is closed; reopen it first." Voiding
   the automatic reversal on its own is refused with a sentence that names the original.
6. **Reversals are exempt** from manual-entry approval (R8), and from the A5 "manual entries to controlled accounts
   off" refusal. The flags are copied, so a reversal of a flagged line is flagged too.
7. **Unique-index races:** a second void or correction of the same entry, when two people act at once, becomes
   "JE-000012 has already been voided or corrected." rather than a database error.
8. **Clean-up carried from the R37 review:** `ledger._separation_on(settings)` and `approvals.separation_on(context)`
   share one rule (a missing row is on). Step 5 makes the ledger call the approvals helper's logic (one function
   that takes a settings row), so there is one definition.
9. **Refusals** follow R27 (no permission codes; the static scan enforces it). The note is typed text and is never
   quoted in a refusal, so no `log_message` is needed. Any sentence that quotes one gets `log_message` (R30).

### Tests first (new `tests/test_ledger_reversals.py`; the xfail rewritten)
- **Automatic reversal:**
  - posting gives two entries numbered N and N+1, both sealed;
  - the reversal mirrors the original line by line, dimensions included;
  - fields: Accrual reversal, System origin, the poster as creator and poster, the same source, no approval
    fields;
  - the full verification is OK;
  - refused, with nothing numbered, when the reversal period is missing or closed;
  - an Agent-origin accrual still needs approval, and once approved both post;
  - the approval digest changes when `auto_reverse_date` changes (R21 cancels the approval).
- **Void and Correction:**
  - confirm, the note, `je.reverse`, Agent, Import and System refused;
  - refused for a draft, a voided entry, a date before the original, and a closed period;
  - mirror exactness, dimensions included;
  - Void marks `is_void` and Correction does not;
  - the shared slot: a void after a correction, and a correction after a void, are both refused;
  - the race sentence;
  - date warnings and acknowledge;
  - exempt from threshold approval and from the A5 control;
  - flags copied.
- **Pair void:** both voided; all or nothing when either period is closed; the automatic reversal cannot be voided
  on its own.
- **Verification and audit:**
  - after every reversal kind the full verification is OK;
  - tampering with a reversal's line breaks the chain there;
  - `audit_log` holds every insert and the void flag;
  - CB1's identification holds (the original with `auto_reverse_date` and its Accrual reversal can be found by
    query).
- **Static:** `ledger.py` stays the only writer of the journal tables; the R27 scan passes; the rule 10 order
  holds for the new services.
- **The rewritten xfail:** a Void dated before the original is refused (moved into the new file; the pending file
  loses it).

### Files
- `modules/services/ledger.py` (the core split, auto reversal, `void_entry`, `reverse_entry`, pair void, races,
  separation helper)
- `modules/services/approvals.py` (the shared separation rule, item 8)
- `tests/test_ledger_reversals.py` (new)
- `tests/test_service_rules_pending.py` (one xfail removed)
- `tests/ledger_helpers.py` (only if a helper is needed)
- `tools/hand_check_step5.py` (new, like the Step 4 one, on a throwaway company)
- Docs: the decisions record (codes for the owner's answers below), CLAUDE.md "Where we are", docs/roadmap.md,
  docs/status_log.md and docs/next_step.md.
- **No baseline change** (unless question 6).

### Order, reviews and stop
Tests first (red), then the code, then the full suite. Then step-reviewer, and mutation-tester on the committed
step. secrets-auditor is not needed: no auth, key storage or secret handling changes; posting already uses the
chain key. Then commit and push, write next_step.md, and STOP.

## Questions for the owner (proposed answers first)

1. **Which entries may a person void or correct?** Proposed: manual sources (none, Manual, Adjustment) and
   Import, Payroll and Conversion entries. Entries from documents (Invoice, Bill, Payment, Deferral, Completion)
   are refused with "This entry belongs to invoice INV-1001; void the invoice instead." Those documents' own void
   services (Phase 4; B14 for payments) will call the narrow ledger path.
2. **The Void's date:** proposed: it defaults to the original's date and may be any later date in an open period,
   never earlier. In a pair void, each Void is dated on its own target's date, as R4's "either period closed"
   implies. A Correction defaults to today and may be any date on or after the original's.
3. **Separation of duties (R17) for a reversal:** a reversal is created and posted by one person in one action,
   so R17 ("the creator cannot post it") would always refuse it when separation is on. Proposed: void and
   correction need no second person, because they are audited and reversible by a new entry; they only need
   `je.reverse`. The alternative is that with separation on, a reversal becomes a draft that another person posts.
4. **Reversing a reversal:** proposed: refused for every kind ("JE-000015 is a reversal; enter a new entry to
   change its effect."), so an undo is never undone by the same mechanism.
5. **A Correction of an accrual that has an automatic reversal:** proposed: refused ("void JE-000012 and its
   automatic reversal together, then enter a new accrual"), because a correction plus the standing automatic
   reversal would double-count.
6. **Dimensions in the mirror check:** the baseline's posting trigger does not compare dimensions. Proposed: the
   service checks them and a test proves it, with no baseline change now (H4: the service rule plus a test). The
   alternative is to extend the trigger, which means one baseline edit and a rebuild.
7. **The automatic reversal's description and reference:** proposed: description "Automatic reversal of
   JE-000012: <original description>", the original's reference; a Void gets "Void of JE-000012: ..." and a
   Correction gets "Correction of JE-000012: ...".

## Then
Step 6 (rounding, R1, L8) and Step 7 (the five xfails left: payment over-allocation, one allocation target,
reopening with a reason, numbering, period from date; plus the payment allocation gaps placed there), then 2.7,
2.8 and Phase 3.

## Carried forward

- Phase 3 screens:
  - show the unverified range and the close check's warning;
  - after a key replacement, call `App.start_key_store()` again;
  - show `KeyReplaced.recovery_code` once;
  - every post, approval and close passes `self.app.action_context()` (the static test enforces it); the void and
    reverse actions do too;
  - log an error by passing the error object, never its text (R30, static test);
  - show `SaveFailedError` like any service error (its sentence only) and never log typed text.
- Whether retired installation keys keep their recovery copies is decided with KS18's key restore (backlog 16).
- `auth._now()` remains the one allowed clock read in services (H2).
- The hand check for Step 4 still runs: `$env:STRATALEDGER_ALLOW_TEST_KEYS = "1"; python tools/hand_check_step4.py;
  Remove-Item Env:STRATALEDGER_ALLOW_TEST_KEYS` ends "Every step behaved as decided."
