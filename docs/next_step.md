# Next step: Phase 2.7 STOP C (custom fields service, FR1 as amended)

Written 2026-11-17 at the end of step B2. Overwritten at each STOP (CLAUDE.md section 8). Start a fresh session
(MR1) and read .claude/rules/workflow-standards.md: done, the review gate, fix mode.
Status: **step B2 is approved** (owner, 2026-11-18, with the answers below, built in the "B2 owner answers" commit).
**STOP C starts in a fresh session** once the owner approves that commit at the review gate.

## Owner answers: product name, HA8 sentence, AX9-AX10 (2026-11-18; fix mode on fc6efe0, awaiting the owner's approval)

1. The product name people see is "Melara": `config.APP_NAME`. The three service sentences that named StrataLedger
   use it (the HA8 sentence, the missing time-zone error in `clock.py`, the ledger-verify Hash reason), and so does
   `database.restore_database`'s refusal (step review). A static test (tests/test_static_rules.py,
   `test_no_service_string_names_strataledger`) refuses "strataledger" in any case in any string in
   modules/services/ or modules/database.py (fix mode); docstrings, comments and bytes are not checked, and a
   run-time join is not caught. Five identifiers keep the old name until U1 and are allowed only as the whole
   string (`OLD_NAME_IDENTIFIERS`, shrink-only): the logger names `strataledger`, `strataledger.clock`,
   `strataledger.keys`, the variable `STRATALEDGER_ALLOW_TEST_KEYS` and the add-on module prefix
   `strataledger_addon_`. The key-derivation labels (`b"StrataLedger ... v1"` in key_store, key_wrap,
   ledger_chain) are identifiers and must never change: changing one breaks every existing key and seal.
2. HA8 sentence (fix mode, replacing the first wording because M3 also counts the admin's own account): "Add-ons
   are off because the program folder's permissions allow changes by accounts other than the system and
   Administrators group. Reinstall Melara to Program Files."
3. CREATOR OWNER and CREATOR GROUP (not an earlier owner decision; ruled in fix mode): `platform_support.
   non_admin_writers` skips a CREATOR allow entry only when INHERIT_ONLY (0x08) is set; without it the entry counts.
   The owner is checked first and separately, so an owner outside SYSTEM, Administrators and TrustedInstaller
   turns add-ons off whatever the entries say. Logic unchanged; tests added for both conditions and for a user's
   file under an inherit-only CREATOR OWNER entry. HA8 now says "inherit-only CREATOR ACEs ignored (owner
   2026-11-18)". `sess_id` and `password_number_id` stay allowed.
4. AX9 and AX10 recorded (docs/decisions_2026-11-11.md, with index rows) and added to docs/CLAUDE_UI.md section 10A
   with AX5-AX8 (which were not in that file before).
5. tests/test_clipboard_lock.py under pytest-xdist: two tests asserted the shared lock was free, but another
   worker may hold it for a real clipboard test. The lock's own test now uses a private lock file, and the
   fixture records `clipboard_lock_held` on the test item, which the marked and unmarked tests check.
6. Hook counts: the commit hook kept no output on a pass, so fc6efe0's counts were not recorded. It now writes the
   suite's last line to `strataledger-commit-hook-last-run.txt` in the system temp folder on every run
   (tests/test_commit_hook.py). It runs `pytest -q -n auto` (without `--dist loadgroup`, which the hook note
   below wrongly says; loadgroup is not needed now that the clipboard tests use a lock).

**Left for the packaging step (U1):**
- Rename to Melara: the data folders (`%LOCALAPPDATA%\StrataLedger-dev`, `%PROGRAMDATA%\StrataLedger`), the
  environment variables (`STRATALEDGER_DATA_DIR`, `STRATALEDGER_ALLOW_TEST_KEYS`, `STRATALEDGER_LIVE_CLIPBOARD`),
  the logger name `strataledger`, the installer and the repo. A renamed data folder needs a move plan (rule 9).
- Screens and other modules outside services still show "StrataLedger" (app_strata.pyw, sidebar.py,
  views_first_run.py, first_run_model.py, views_wizard.py, database.py docstrings, platform_support.py): Phase 3 or U1.
- U1 checklist: after install, check that the program folder's ACL and owners pass HA8 (no files owned by the
  user, no "Object creator" ownership), and test the install with the built-in Administrator account.

## Owner answers on the review step and the KS12 tie (2026-11-18; awaiting the owner's approval)

Commit 55a0e2b, then the mutation-test commit. KS12 tie decided; HA8 M1-M3 (allow-list of SYSTEM, Administrators,
TrustedInstaller over RESOURCE_DIR and the whole add-ons tree; links refused); HA11 L2/L3; the voucher test's own wait.
- Mutation test of 55a0e2b: 132 mutants, 99 killed by existing tests, 23 by tests/test_mutation_owner_answers_extra.py
  (each re-checked), 10 equivalent: five `_SECRET_WORDS` entries and four `_SECRET_PAIRS` entries also caught by a
  run or word; `len(before) > 1` as `>= 1` (a one-word tuple is never a pair).
- For the owner: AX9 and AX10 are not in the repo or this session; please resend their text. The HA8 sentence says
  "this account" though any principal outside the allow-list now trips it. `password_number_id` is allowed (the id
  exemption refuses only values that are the secret). A real installer build is not yet tested against HA8: an
  install that leaves files owned by a user account (the "Object creator" owner policy, or the built-in
  Administrator) turns add-ons off.
- Suite: 3868 passed, 2 skipped after 55a0e2b, plus 23 mutation tests.

## Owner answers, 2026-11-18 (built in the B2 owner-answers commit)

1. Safety backups: `pre-upgrade` and `pre-restore` are never pruned. `addon-<key>` backups are pruned by E7 (7
   days, 4 weeks, 12 months; the LOW-6 fix stands, owner's choice). AX2 now says the `.sha256` file detects
   corruption only.
2. M1 goes to Phase 2.8 (below).
3. M2 became HA11: add-on migrations refuse secret-looking column names (tests/test_addon_secret_columns.py).
4. `.codex/agents` is kept. CLAUDE.md section 8: a change to a `.claude` agent updates its `.codex` copy in the same commit.
5. `fields.manage` may be added to the baseline permission seed in STOP C (below).
6. Agents and workflow:
   - The models stay in the `.claude/agents` frontmatter: step-reviewer and secrets-auditor on opus, the other
     three on sonnet. Codex cannot run Claude models, so each `.codex` copy maps its tier to
     `model_reasoning_effort` (opus to high, sonnet to medium; owner's choice).
   - mutation-tester mutates only the functions changed in the step's commits.
   - `.claude/settings.json` has a PreToolUse hook (`.claude/hooks/pre_commit_pytest.py`, tests/test_commit_hook.py).
     It runs the suite in parallel (`pytest -q -n auto --dist loadgroup`, pytest-xdist) before any `git commit`
     and blocks the commit on failure, or when xdist is missing. About 5 minutes (18 in one process); timeout 900 s.
   - Review fixes after b4ea844 (status_log 2026-11-18): secrets-audit fixes to HA11, and HA8's writable-program-
     folder check (frozen build only). Awaiting the owner's approval.
   - CLAUDE.md section 8 also says: after each STOP, Codex reviews the pushed commits read-only in its own worktree,
     and its findings come to the owner.

## Review step after b4ea844 (2026-11-18; awaiting the owner's approval)

Commits 997305c (HA11 audit fixes, parallel hook), 7aeb3f4 (HA8 ACL, SQLite redaction), 6afd131 (step-review fixes),
then the mutation-test commit. Owner questions from the step-review (not built): M1 check add-on subfolders and
files too; M2 an allow-list of admin SIDs instead of four non-admin groups; M3 count the user's own SID even when
elevated; L2/L3 HA11 misses (mypwd, acctnum, client_key, nonce) and false positives (file_hash, pass_count,
account_number, bank_account_id).

Mutation test: 145 mutants, 102 killed by the existing tests, 33 more by tests/test_mutation_b2_review_extra.py
(each re-checked), 10 equivalent:
- `_check_existing_columns` with `startswith(prefix)` instead of `_owned`: check_addon_key refuses a key whose
  prefix matches a core table, so no core table starts with `<key>_`.
- `_looks_secret` without `not _secret_word(w)` in the singular list: only `pass` ends in s, and a name with the
  word `pass` is refused by the word check already.
- `current_token` with elevation fixed to False: same result in a non-elevated session (the suite's); killing it
  needs an elevated run or a fake advapi32.
- `read_folder_acl` without `if status != 0`: reached only for a folder that exists but cannot be read; a missing
  path already raises. Needs a fake advapi32.
- `read_folder_acl` without the NULL-DACL branch: GetAclInformation then fails, and folder_open_to_non_admins
  fails closed to True, the same answer.
- `read_folder_acl` without the object-ACE branch: object ACEs exist only in Active Directory, never on folders.
- The three frees (`LocalFree` in `_sid_text` and of the descriptor, `CloseHandle` of the token): a leak, not a
  behaviour change.

## KS12 epoch-anchor tie (2026-11-18; awaiting the owner's approval)

Commits 7a704a2 (the fix) and 3a792cc (step-review fix: only the file's latest signed row decides). Owner sign-off
needed on the PROPOSED carve-out in KS12: on a tie the file's row stays when its ref_id is the mirror's key_id.
Mutation test of `_epoch_anchor`: 44 mutants, 41 killed, 3 equivalent: `ahead == 0` as `ahead >= 0` (the `ahead >
0` term returns first), and `LIMIT 1` changed to `LIMIT 2` or removed (read with fetchone under ORDER BY
checkpoint_id DESC).

**State:**
- Suite: 3675 passed, 1 skipped (after the KS12 tie step; 3440 after the owner-answers commit, 3369 after B2).
- B2 commits:
  - 785ca30 (part A);
  - 8e5979c (the build);
  - 3340b32 (step-reviewer fixes);
  - 2698385 (secrets-audit fixes);
  - the mutation-test commit that follows them.
- Everything is pushed to `origin/main`.

## Done in step B2 (2026-11-17)

- **Workflow:** `.claude/rules/workflow-standards.md` loads in every session and overrides CLAUDE.md section 8 where
  they differ. AGENTS.md points to CLAUDE.md. Codex, like Copilot, works only in its own worktree.
- **AX1:** every connection from `modules/database.py` has foreign keys on and a 5-second busy timeout. Master and
  company files are WAL: set at build, and an older file is switched (and the switch logged) when it is opened.
- **AX2:** one backup helper, `database.backup_database`, on `Connection.backup`. It includes pages still in the
  WAL, never copies `-wal`/`-shm`, and writes a `.sha256` (K5).
  - Users: the baseline runner (`pre-upgrade`), the add-on migration runner (`addon-<key>` and E7 retention through
    `prune_backups`; closes LOW-6) and `restore_database` (`pre-restore`).
  - `restore_database`: checks the checksum and the file's soundness, refuses while the company is open, makes the
    safety backup, removes leftover `-wal`/`-shm` and replaces the file.
  - The restore *service* (permission, K5 Master override, Audit-ready flag) is Phase 2.8.
- **AX3:** a source run without `STRATALEDGER_DATA_DIR` uses `%LOCALAPPDATA%\StrataLedger-dev`. The repo-root
  files were not moved (rule 9). B2 edited the company baseline, so a company file there needs a rebuild;
  the repo-root master (its baseline is unchanged) still opens if the variable points at the repo.
- **HA9:** add-on tables get audit triggers generated from `migrations/addon_audit_triggers.sql` after every
  migration statement. `addon_schema_version` has baseline audit triggers. `addons.enable` names the person
  (`tx.AuditStamp`). The guard lets only these triggers read `audit_context` and append to `audit_log`.
- **Small gaps:** a handler's `SystemExit` becomes AddonError (`KeyboardInterrupt` still propagates). The Agent
  refusal in `hooks.fire` writes a denial row after the rollback (`DeferredDenialError`, `authz.record_denial`).
- `Theme.create_scrollbar` (the DataTable known issue).
- **Decisions recorded:**
  - AX1-AX8 (AX4 queued for the replan; AX5-AX8 are AQ2 front-end rules, not built);
  - AG1-AG8 (AI v1.2, docs only);
  - HA8-HA10;
  - RI1 (replan inputs, decided, not built);
  - FR1 amended.
- **Reviews:**
  - step-reviewer on 8e5979c: findings 1-6, 8 and 9 were fixed in 3340b32. Finding 7 (.codex/agents) is for the
    owner, below.
  - secrets-auditor on 3340b32: nothing Critical or High. L1-L5 were fixed in 2698385. M1 and M2 are for the owner,
    below.
  - mutation-tester on 2698385: 250 mutants.
    - 158 are killed by the B2 test files and 7 by tests/test_service_tx.py.
    - 55 survivors were real gaps, now killed by tests/test_mutation_b2_extra.py.
    - 30 are equivalent:
      - B01, B10: sqlite3's default timeout is already 5 s.
      - B05: SQLite returns `wal` in lower case.
      - B33: `immutable=1` alone refuses writes.
      - B54: reasons are `[a-z0-9-]` only.
      - B60: restore's outer handler gives the same refusal.
      - B73: refcounting closes the check connection.
      - B84: the cleanup checks `exists()`.
      - B88: the staged copy is rollback-journal mode, so it has no sidecars.
      - B106: ATTACH is refused.
      - B113: `xWITHOUT ROWID` is not valid SQL.
      - B123, B124: SQLite accepts leading comments, and an empty statement cannot occur.
      - B137, B138, B143: speed only; `complete` forces a rebuild.
      - B140: names are plain identifiers.
      - B151: the add-on cannot create an audit-named trigger.
      - B153, B156-B161: seq edits are refused by the authorizer, and the version row recreates audit_log's
        counter.
      - B167: the sync never touches counters.
      - B171: `audit_context` is not in the snapshot.
      - B195: `close()` rolls back.
      - B204: `_actor_type` already says Agent.
      - B222: FileExistsError is an OSError.
    - New defect, fixed test first: a second audit_log counter row is now refused.

## STOP C plan: the custom fields service (FR1 as amended, owner 2026-11-17)

Rulings that replace the STOP B plan's open questions 1-5:
- CODE_CHANGES_NEEDED.md section 27 replaces the field packs and the 15-field cap (crm_design_log section 5,
  CODE_CHANGES 12.4):
  - no packs, no `pack` or `is_builtin` columns, no seeded fields, no cap;
  - section 27's warnings (more than 2 fields on board cards, more than 20 active per job type) wait for the CRM
    step.
- **No schema change in STOP C** (schema hold):
  - "Remove" makes a field inactive (`is_active = 0`) and keeps its values. The audit log is the history.
  - `help_text`, the board card, shown-from-stage and job-type visibility go to the schema replan (step 2.9).
- **Names:** field labels are unique, case-insensitive, per record type. This is a service check inside the write
  transaction.
- **Permission:**
  - A new `fields.manage`, held by the Admin and Master templates, and not in AGENT_ALLOWED.
  - The Agent reads values where it may read the record; it never defines fields.
- The baseline names stay: `custom_field_def`, `custom_field_value`, `choices_json`.
- Both deferred checks stay (below).
- docs/crm_pm_design.md was checked for field packs: it names none ("pack", "Solar" and "Roofing" do not appear), so
  nothing was removed.

### The baseline today (it wins, CLAUDE.md section 5)

- **`custom_field_def`** has these columns:
  - `record_type`: Contact, Invoice, Bill, Project or Estimate;
  - `field_key`: unique per record type;
  - `label`;
  - `data_type`: Text, Number, Money, Date, Yes/No or Choice;
  - `choices_json`, `is_required`, `is_active`, `sort_order`.
- **`custom_field_value`** has one typed column per type (`value_cents` INTEGER, `value_number` REAL, ...). At most
  one is set, and triggers match the column to the field's type.
- Both tables have audit triggers. `record_id` has no foreign key (it is polymorphic). No service exists yet.

### The service: `modules/services/custom_fields.py` (tests first)

- **`list_fields(context, record_type, *, include_inactive=False)`:** needs the record type's view permission.
- **`define_field(context, record_type, *, label, data_type, choices=None, is_required=False)`:**
  - needs `fields.manage`;
  - `field_key` is derived from the label, stable, and never changes;
  - a label that matches an existing one case-insensitively is refused, with one sentence.
- **`update_field(context, field_id, ...)`:**
  - changes the label (same uniqueness check), order, required flag or choices;
  - `data_type` changes only while no value of the old type exists (deferred check 1);
  - a used choice is deactivated in `choices_json`, never removed.
- **`deactivate_field` / `reactivate_field`:** `is_active` only. The service never deletes a definition or a value.
- **`set_value(context, record_type, record_id, field_key, value)` and `get_values(context, record_type,
  record_id)`:**
  - typed: money is integer cents (floats, strings and booleans refused, as in the ledger), dates are ISO, a Choice
    is an active choice, a number is finite;
  - clearing sets every column to NULL;
  - the record must exist;
  - an inactive field refuses new values, and its old values still read.
- **Contact bank-number check (deferred check 2):** a Contact field whose label or key looks like a bank number
  (routing, account number, IBAN, SWIFT, ...) is refused, with one sentence pointing to `bank_payee_id` (RP1).
- **Permissions for values:** setting a value uses the record's own permission (`customer.manage`,
  `invoice.create`, `bill.create`, `project.manage` with project scope, `estimate.create`). Reading uses the
  record's view permission.
- **Seed and templates:**
  - `fields.manage` is added to the baseline's permission seed (owner 2026-11-18: allowed in STOP C as a seed row
    only). It goes in the Admin and Master role templates, **not** `AGENT_ALLOWED`. The baseline edit means the
    empty development databases are rebuilt (CLAUDE.md section 5).
  - The Admin and Master role templates hold it; docs/role_templates.md is updated with tests.
- **Tests first:**
  - each type's value check, with the trigger as backstop;
  - case-insensitive uniqueness per record type, including two writers;
  - the data-type change refused while values exist;
  - the bank-number names;
  - a deactivated field keeps its values and refuses new ones;
  - permissions per record type, project scope and the Agent;
  - audit rows;
  - the static rules (rule 10, H5).

### Open questions for the owner (STOP C)

- None. The `fields.manage` seed row was answered on 2026-11-18 (above).

## Open points carried forward

- The B2 owner points (M1, M2, step-reviewer finding 7) were answered on 2026-11-18 (top of this file).
- The linked-migration-file test (secrets audit LOW-4) is skipped on this Windows account. Run it once with the
  right to create symbolic links (Developer Mode).
- AX3: the old development files stay in the repo root (`system_master.db`, `Backups/`). The new source-run data
  folder starts empty, so first run creates a Master there.
- A read-only reader of a WAL file leaves an empty `-wal` and the `-shm` beside it (AX1). Anything that copies a
  company file must use `database.backup_database`, never a plain file copy.
- An add-on table cannot drop a column while its audit triggers name it. SQLite refuses `DROP COLUMN` then, so an
  add-on rebuilds the table instead (HA9).
- An add-on is trusted installation code (HA3, HA8). The guards stop SQL mistakes, not hostile Python.
- Phase 2.8: the restore service on `database.restore_database` (`company.restore`, K5's Master override with a
  typed confirmation and a reason, the Audit-ready flag) and scheduled backups with E7 retention (the
  `pre-upgrade` and `pre-restore` safety backups stay outside pruning, AX2).
- **Phase 2.8, master backups and the recovery-code reissue (owner 2026-11-18, secrets audit M1):** a master
  backup taken before a reissue still holds the old `recovery_blob` and old password hashes. When the recovery
  code is reissued, 2.8 lists the master backups older than the reissue and offers to delete them. The person's
  choice (deleted, or kept, and which files) is audit-logged, and nothing is deleted silently. Tests first.
- Step 2.9 (schema replan): AX4 (audit_log before/after detail and a reason), RI1, and STOP C's deferred field
  columns.
- Open question 7 (System context and Import-origin entries in `post_journal_entry`); undeposited funds vs
  matching (Phase 4).

## Deferred (unchanged)

- **Phase 4 posting services:**
  - `clearing_lines`, `NEW_CLEARING`;
  - `next_invoice_number`, `next_voucher_number`;
  - the voids call `void_document_entry` and `release_allocations`;
  - AR and AP in the chart CSVs.
- Deferral targets in `allocate`.
- **Phase 3 screens:**
  - show the unverified range and the close check's warning;
  - `App.start_key_store()` after a key replacement;
  - show `KeyReplaced.recovery_code` once;
  - pass `self.app.action_context()` on every post, approval, close, void and correction;
  - `display_description`;
  - log errors by passing the error object;
  - `SaveFailedError` like any service error;
  - the import review's rounding note;
  - the AQ2 bridge follows RP6, the token rules in docs/design.md section 1, and AX5-AX8;
  - a multi-role screen showing MR8's "This removes: ...";
  - Company Settings > Add-ons.
- **Backlog 21** (R42). **KS18:** retired installation keys' recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).
