# Next step: Phase 2.5 Step 1d (key-lost checkpoint and a new installation key)

Written at the STOP after Step 1c was accepted (2026-11-12). Overwritten at each STOP (CLAUDE.md section 8).
Status: PLAN APPROVED (2026-11-12), not started. The owner starts it in a fresh session. The seven open questions
below are answered as proposed, with the owner's additions to Q1-Q3; record all seven as decisions KS12 and up
(with index rows) when building.

**State at this STOP:** HEAD is the commit that records the approval in this file, on top of `c191c1f` (the
plan) and `ebf8e98` (docs: decisions index, audit design trim). Last code commit `e725506`. Suite on the committed tree: **2033 passed, 7 deselected,
12 xfailed** (about 10 minutes). Working tree clean, `main` pushed.

**Read first (by search, not whole files):** docs/audit_readiness_design.md 2.6 (verification rules), 2.7
("Key lost", "Decided for Step 1d", "Installation key rules", "Rotation") and section 3; decisions K14-K16,
K18, KS5, KS6, KS8-KS10; `modules/services/ledger_verify.py` (`_check`, `_record`, `record_key_checkpoint`);
`modules/services/ledger_keys.py` (`start_new_key_epoch`, `_switch_keys`); `modules/services/key_store.py`.

## Owner decisions this step builds (2026-11-12)

1. **Key-lost checkpoint.** A key-lost epoch writes a signed checkpoint recording that the history before it
   cannot be verified. The verifier reports that range as Unverified (key lost), never Broken, and verifies the
   new epoch from its first entry.
2. **Lost installation key.** The Master can create a new installation key (password plus a typed
   confirmation, a recorded event). Every company then enters a key-lost epoch automatically. Data stays
   readable; posting continues under new keys.
3. Both baseline changes in one edit: the previous baselines are saved to archive/ with a tag, and the
   databases are rebuilt once.

## Proposed design

### A. The key-lost checkpoint (company baseline and master mirror)
- `ledger_checkpoint.kind` gains `'Key lost'`; `result` gains `'Unverified'`, with
  `CHECK ((kind = 'Key lost') = (result = 'Unverified'))`. The same two changes go on the master's
  `chain_checkpoint`. The other CHECKs stay (an Unverified row has no `first_broken_entry_number`).
- The row: `through_entry_number` = N, the last entry sealed before the epoch (0 when none);
  `chain_hash` = the stored hash of entry N, recorded as is and not verified; `key_id` = the NEW key, which
  signs the MAC; `ref_type` `ledger_chain_key`, `ref_id` = the key retired as `Key lost`; scope NULL.
- `start_new_key_epoch` writes the checkpoint in the SAME company-file transaction that retires the old key
  and activates the new one, so an epoch can never exist without its checkpoint. The master mirror is written
  afterwards. If the mirror fails, the epoch is not undone; the result says so in one sentence, as with
  `KEY_CHECKPOINT_NOT_SAVED`. This means `_switch_keys` needs a hook for the extra insert, or the epoch gets
  its own switch.
- **Verifier** (`ledger_verify._check`):
  - The latest valid `Key lost` checkpoint (file, plus the master mirror) is the epoch anchor E, through N.
  - Before trusting E: its MAC must check under its `key_id`; `ref_id` must be retired with reason `Key lost`;
    and the stored hash at N must equal E's `chain_hash`. A failure is Broken (`Marker` or `Hash`), never
    Unverified.
  - Entries 1..N are not hashed. Verification starts at N+1 with `prev` = E's `chain_hash`. Incremental and
    full both do this; incremental may start later, at an OK checkpoint after E.
  - Anchors and checkpoints made before E (signed with keys that may be lost) are ignored for the MAC and
    truncation checks. E and everything after it are checked as today. The void cross-check and the counter
    check still cover the whole ledger.
  - Result: status `OK` (or `Broken` or `Unavailable` for the new epoch, as today), plus
    `unverified_through` = N and `unverified_reason` = `Key lost`, both None when there is no epoch. The
    message names the range: "Entries JE-000001 to JE-000N cannot be verified because their key was lost;
    entries after it were verified." It contains no hash or key, and it is never empty when
    `unverified_through` is set (Q1).
  - Every verification result shown on a screen, report or export shows the unverified range next to it (Q1).
  - A Verify checkpoint recorded after an epoch is OK through the head and means "verified from N+1".
- Only the latest epoch counts: a second epoch moves N forward.
- `rotate_chain_key` after an epoch: the full check is now OK with an unverified range, so rotation signs its
  `Key rotation` checkpoint again. The "Unavailable, no checkpoint" path stays only for a key missing with no
  epoch.
- The close check `ledger_integrity` treats an unverified range as a warning in every mode (it is not
  tampering); the verified part follows the check's mode (L2). See question 2.
- The note "history before JE-N cannot be verified (key lost)" has no expiry. It stays, permanently, on every
  close report and export that covers those periods, and on the Audit-ready page (Q2). This replaces "until the
  next year close" in audit design 2.7 ("Key lost").

### B. A new installation key (master baseline)
- `installation_key` becomes append-only history with one active row, the same pattern as
  `ledger_chain_key`:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT` (drop `CHECK (id = 1)`);
  - `is_active`, `retired_at`, `retire_reason CHECK (retire_reason IN ('Key lost'))`;
  - a partial unique index for one active row;
  - triggers: `installation_key_no_delete` stays; `installation_key_same_key` stays for id, fingerprint and
    created_at; a new trigger allows a retired row to change nothing and allows an active row only to be
    re-wrapped or retired.
  - A retired row keeps its fingerprint and recovery copy (the copy is kept: a later found code could still
    open old blobs, see question 4).
- `company_key` gains `installation_key_id INTEGER NOT NULL REFERENCES installation_key(id)`: the key that
  wrapped it. The provider unwraps only rows wrapped by the active installation key and treats the others as
  unavailable (KeyUnavailableError, never a crash). Rows stay append-only.
- `auth_event.event_type` gains `'Installation key replaced'`.
- **Service** (proposed `auth.replace_installation_key(session, password, *, confirm_text, machine_wrap)`):
  - Master only (`require_master`) before anything else, then the password check and the typed confirmation
    (see question 3).
  - Refused while the installation key opens on this computer (DPAPI copy opens): "The ledger key is still
    available on this computer, so it is not lost."
  - When the key is locked (no DPAPI copy), it goes ahead only on the typed confirmation that the recovery code
    is lost. The confirmation is the phrase `NEW LEDGER KEY` (Q3).
  - The confirmation screen says every company's history up to today will no longer be verifiable, and shows how
    many companies will get a new key epoch (Q3). A read service (for example
    `installation_keys.replacement_preview(session)`, Master only) returns that count, so the screen and the
    service agree on it.
  - In one master transaction: retire the old row (`Key lost`), insert the new key with a NEW recovery code
    (shown once, like PW9; it also replaces the `master_recovery` hash) and this computer's DPAPI copy, and
    write the `Installation key replaced` event.
  - Then, for every company in the registry: `start_new_key_epoch` (new chain key wrapped by the new
    installation key, old key retired as `Key lost`, the Key lost checkpoint).
  - The per-company part is not atomic across files. The result lists every company as done or failed with a
    one-sentence reason.
  - A company left behind is found later by a check, since its active key has no `company_key` row wrapped by
    the active installation key. `start_new_key_epoch` (already Master-only, code typed) finishes it, or the
    replace service offers "Finish the remaining companies".
  - Returns a `CodeIssued`-style result, redacted, not picklable.
  - After success the app calls `App.start_key_store()` again, so the provider holds the new key.

### C. Baseline procedure (one edit, one rebuild)
1. Tag the commit before the edit `baseline-pre-2.5-1d` and push the tag.
2. Copy `migrations/001_company.sql` and `001_master.sql` to `archive/baseline_pre_2_5_1d/`, with a README
   naming the commit and the tag.
3. Write the failing tests (below), then edit both baselines in one commit.
4. Rebuild the development databases with `python scripts/create_fresh_databases.py --apply`. Before that, run
   the dry run and show the owner the files it will move to Backups/ (rule 9: ask before rewriting a
   database). This is the step's one rebuild.

## Files to change
- `migrations/001_company.sql` (`ledger_checkpoint` kind and result).
- `migrations/001_master.sql` (`chain_checkpoint` kind and result; `installation_key` history; `company_key`
  gains `installation_key_id`; `auth_event` gains the new type).
- `modules/services/ledger_verify.py`: epoch anchor, `unverified_through`, the message, the Key lost
  checkpoint writer, the close check wording.
- `modules/services/ledger_keys.py`: the epoch writes its checkpoint atomically; rotation after an epoch.
- `modules/services/key_store.py`: the active installation key row, `installation_key_id` on stored keys,
  creating a replacement key, skipping blobs wrapped by a retired key.
- `modules/services/auth.py`: `replace_installation_key` and its result type (or a new `installation_keys.py`
  service, if auth grows too large).
- `scripts/create_fresh_databases.py`: only if the first-run key row shape changes its inserts.
- Tests (below).
- Docs:
  - audit design 2.6, 2.7 (including the Q2 change to "until the next year close"), 3 (kinds), 8 (the
    Audit-ready line) and 11 (test plan);
  - decisions: new codes for this step's answers, each with an index row;
  - roadmap, status_log, file_map;
  - CLAUDE.md "Where we are";
  - next_step.md.

## Tests to write first (each must fail before its code or baseline edit)
- **Schema** (`tests/test_schema_ledger_chain.py`, `tests/test_master_key_tables.py`, `tests/test_master_schema.py`):
  - kind `Key lost` exactly when result is `Unverified`, in both the file and the mirror;
  - one active installation key; a retired row cannot change or come back;
  - `company_key.installation_key_id` is required and references a real row;
  - the new auth_event type.
- **Key lost checkpoint** (new `tests/test_key_lost_checkpoint.py`):
  - the epoch writes one Key lost / Unverified checkpoint (file and mirror) with N, the hash at N, the new key
    and the retired key's id;
  - no epoch exists without its checkpoint (forced failure inside the transaction leaves the old key active);
  - a failed mirror keeps the epoch and says so.
- **Verifier** (`tests/test_ledger_verify.py` or the new file):
  - after an epoch, full and incremental are OK with `unverified_through` = N and never Broken;
  - entries after N are verified, and a changed entry after N is Broken at that entry;
  - a changed entry 1..N is not reported (documented limit, with a test);
  - a changed hash at N, a forged or unsigned Key lost row, or a Key lost row naming an active key is Broken;
  - two epochs: only the latest counts;
  - an older OK checkpoint signed with the lost key no longer makes the result Unavailable;
  - the message has no hash or key, and is never empty when `unverified_through` is set (Q1; parametrized over
    full, incremental, the close check and the rotation result);
  - the close check warns, never blocks, on the unverified range.
- **Rotation after an epoch**: signs its checkpoint again (update `tests/test_key_rotation.py`).
- **Replace installation key** (new `tests/test_installation_key_replace.py`):
  - refusals: a non-Master is refused first; a wrong password and a wrong confirmation write nothing
    (snapshot of the master and every company file); refused while the DPAPI copy opens;
  - success:
    - the old row is retired;
    - the new key row and a new recovery code (the old code no longer opens anything, the new one does);
    - the event is recorded;
    - every company is in a new epoch with a Key lost checkpoint, and posting works for each;
    - old `company_key` rows are kept and are not opened;
  - partial failure: one company file missing is reported, and finishing it later works;
  - the result redacts the code;
  - the preview's company count matches the companies that get an epoch (archived included, Q5);
  - no key or code in logs, `audit_log`, `auth_event` or exceptions (extend `tests/test_key_secrets.py`).
- Static rules stay green (rule 10 order in the new service; no new allow-list entries).

## STOP points
1. After the baseline edit, the schema tests and the rebuild: report the baseline diff, the archive copy,
   the tag and the counts.
2. After part A (Key lost checkpoint, verifier, rotation after an epoch): commit, push, report.
3. After part B (replace installation key): commit, push, then run step-reviewer, secrets-auditor and
   mutation-tester. Report each agent's findings and what was fixed, then write the next docs/next_step.md.

## Questions (answered 2026-11-12: approved as proposed, with the owner's additions marked "Owner")
1. **Overall status after an epoch:** `OK` with `unverified_through`, or a fourth status such as "Partly
   verified"? *Proposed:* `OK` plus `unverified_through`, so close checks, rotation and the K16 rules keep
   their meaning, and the screen shows the unverified range next to the result.
   **Owner:** every verification result shown on a screen, report or export shows the unverified range next to
   it; a test proves the message is never empty when `unverified_through` is set.
2. **Close check and Audit-ready mode:** does an unverified range block a close when `ledger_integrity` is
   set to block? *Proposed:* no; it is always a warning (it is not tampering). Audit-ready mode shows "history
   before JE-N cannot be verified" until the next year close, as the design already says.
   **Owner:** no expiry. The note stays permanently on every close report and export that covers those periods
   (not "until the next year close").
3. **Typed confirmation for a new installation key:** what is typed? *Proposed:* the phrase `NEW LEDGER KEY`,
   after a screen that says every company's history up to today will no longer be verifiable.
   **Owner:** the confirmation screen also shows how many companies will get a new key epoch.
4. **A lost key found again** (an old master backup, a found recovery code): may the verifier use it to verify
   the old range? *Proposed:* not in 1d. The range stays Unverified; restoring keys is part of the backup and
   key-bundle work (backlog 16).
5. **Archived companies** when the installation key is replaced: do they get an epoch too (the file is written
   though archived)? *Proposed:* yes, every company in the registry, archived included, so none is left with a
   key that can never open; the result lists them.
6. **Where the replace service lives:** `auth.py` (it changes the recovery code) or a new
   `installation_keys.py`? *Proposed:* a new module that calls auth's password and code helpers, so auth.py does
   not grow further.
7. **Decision codes:** record this step's answers as KS12 and up (KS index rows added)? *Proposed:* yes.
