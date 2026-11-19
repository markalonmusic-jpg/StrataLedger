# Next step: Phase 2.9, the schema replan

Written 2026-11-18 at the end of Phase 2.7 STOP C. Overwritten at each STOP (CLAUDE.md section 8). Start a fresh
session (MR1) and read .claude/rules/workflow-standards.md: done, the review gate, fix mode.
Status: **STOP C approved by the owner (2026-11-18)**; the Codex batch 2 posting fixes ran first (owner
2026-11-18; section below). 2.9 starts in a new session.

## Done before 2.9 (2026-11-18): Codex batch 2 posting fixes

Source: `Strata_Teams\codex_reports\posting_batch2_2026-11-18.md` (review of d7a8073).
- **R21 (Low), fixed test first:** `ledger.update_entry` cancels a Pending or Approved request only when the
  entry's R15 digest (`_entry_digest`, the one `ledger_chain.entry_digest` path) differs before and after the save,
  both read inside the write transaction. A no-change save (no fields, or every field and line as it is) keeps
  the request; a change to the date, a line, a line's account, an amount, a dimension, the description or the
  reference cancels it (tests/test_ledger_approvals.py). `delete_entry` still always cancels.
- **C4/L2 (Medium), not built:** the baseline has `deferral` and `deferral_schedule_line`, but no service makes,
  schedules or posts them, so the close check waits for the deferral work (Deferred below; owner rule for this step).
- **B14:** no change (Deferred below).
- **Step review** (approve with changes): the R21 decision text now matches the code (digest change or delete
  cancels). Its "flaky" test was one parallel run that started before the test's source fix; 65/65 in parallel
  since. Not changed (note 8): the digest now runs on every save, so a draft whose stored values cannot be
  sealed (only a write outside ledger.py could make one) fails the save, as submit and post already do.
- **Mutation test of f629f2f** (update_entry only): 20 mutants, 19 killed, 0 equivalent; the survivor (the
  header UPDATE keeping the old source) is killed by tests/test_mutation_codex_batch2_extra.py.

## Step 2.9 plan: the schema replan (owner decision 2026-11-17)

- Working doc: `Strata_Teams\schema_replan_2026-11-17.md` (the planning chat's list of 21 areas, each todo /
  drafted / owner-approved). Owner rule 2026-11-18: the mockups define the features; the schema follows them.
- All held schema changes land in the two baselines in one pass, tests first. Before any baseline edit, list the
  development databases the edit blocks (CLAUDE.md section 5.2) and ask before rebuilding (rule 9).
- Build only the areas the owner has marked owner-approved in the working doc. An area still todo or drafted is
  not built; PROPOSED items are not built as final.
- Open before drafting (working doc): the design chat confirms the mockups are nearly final and renumbers
  CODE_CHANGES 16-30 (second set).

### Inputs that STOP C adds to the replan (also in the working doc as P items)

1. **Custom field columns (area 16):** `help_text`, on board card, shown from stage, and which job types use a
   field (CODE_CHANGES 27). Section 27's warnings (more than 2 fields on board cards, more than 20 active per job
   type) come with the CRM screens. Lead support and display metadata (Codex X 4, X 8).
2. **Estimate (area 6):** no estimate service and no read code exist (`estimate.create` and `estimate.approve`
   only), and `estimate` has no `project_id` (the link is `project.source_estimate_id`). `custom_fields` refuses
   every call on Estimate with one sentence until an estimate service and its read code exist.
3. **Access model (area 18):** `contacts.update_contact` (and deactivate, find_duplicates) accept either
   `customer.manage` or `vendor.manage` for every contact kind, so a vendor manager edits a customer-only contact
   and the reverse. Custom field values on contacts use the same check today. Not changed in STOP C.
4. **Area locks (area 13):** custom-field edits on posted invoices and bills must honour `fiscal_period_lock`
   (Sales / Purchases) when the rule 8 editable-documents work lands. Today they check only the closed period
   and `Lock documents after posting`.
5. **AX4 (area 18):** audit_log before/after detail and a reason. The custom field audit triggers already store
   the old and new values as JSON.
6. **RI1** (decided, not built): the replan inputs in docs/decisions_2026-11-11.md.

## Done in STOP C (2026-11-18): the custom fields service

- `modules/services/custom_fields.py` (tests/test_custom_fields.py, 220 tests): `list_fields`, `define_field`,
  `update_field`, `deactivate_field`, `reactivate_field`, `set_value`, `get_values`. FR1 as amended by
  CODE_CHANGES 27: no field packs, no `pack` or `is_builtin` columns, no seeded fields, no cap.
- **Schema:** one seed row, `('fields.manage', 'Company', 'Define custom fields', 1)` in 001_company.sql (owner
  2026-11-18), and the same entry in `permissions.py`. Sensitive, so no starter role template holds it: Admin
  (seeded with every code) and the Master only; not in AGENT_ALLOWED. docs/role_templates.md: 77 codes and a
  section 3 row. No other schema change. The dry-run rebuild found no development company files (the data
  folder is empty; the repo-root master's baseline did not change), so nothing was rebuilt.
- **Definitions:** labels are unique per record type ignoring case (`casefold`, inactive fields included), checked
  inside the write transaction (two writers: one wins). `field_key` is an ASCII slug of the label (`field` when
  none, `f_` before a digit, `_2`, `_3` on a clash) and never changes. "Remove" is `is_active = 0`; nothing in the
  module removes a definition or a value. The type changes only while no non-empty value is stored. Choices are
  `choices_json` `[{"value", "active"}]`; a used choice that is left out stays inactive, an unused one goes, and
  a re-listed one becomes active with its stored spelling. `is_required` is stored only (the record services
  enforce it later).
- **Values:** Text (at most 2000 characters; blank clears), Number (finite, not yes/no), Money (an `int` only:
  floats, text and yes/no refused), Date (`YYYY-MM-DD`, a real date), Yes/No (`bool` only), Choice (an active
  choice, matched without case). `None` clears every column (the row stays). The record must exist (an
  invoice id is not a bill). An inactive field refuses new values; its old values still read.
- **Contact bank-number names** (deferred check 2): routing, IBAN, SWIFT, BIC, ABA, BSB, IFSC, CLABE, account or
  acct number/no/#, bank account, sort code, and their joined forms are refused on Contact fields, with one
  sentence naming Melara and the bank payee (RP1).
- **Permissions (owner answers 2026-11-18):**
  - Defining: `fields.manage`; the Agent is refused, Admin included.
  - Reading values: Invoice `ar.view`; Bill `ap.view`; Project `project.view` with project scope. Contact by kind:
    a customer `ar.view` or either manager; a vendor `ap.view` or either manager; both or neither either view
    code or either manager. The Agent reads only through view codes.
  - Listing definitions: the type's read codes or `fields.manage`. Project fields under Assigned scope need
    `project_id=`.
  - Setting values: Contact either manager (as contacts.py); Invoice `invoice.create`; Bill `bill.create`; Project
    `project.manage` with scope. The Agent never sets values (a logged denial).
  - Estimate: every call refused with one sentence.
- **Posted invoices and bills:** values may change. They are in no ledger seal or chain (the chain hashes
  journal_entry, journal_line and journal_line_dimension only; audit_log has no chain). Refused while
  `company_settings.lock_documents_after_posting` is on (OFF by default), and with `PeriodClosedError` when the
  posting entry's period is closed. A draft is not posted, so its date's period does not matter.
- **Audit:** the baseline triggers write old_value and new_value for both tables, with the user; a rolled-back
  write leaves no value and no audit row (tested). No second row from the service (owner).

- **Step review of e61dec2 (approve with changes, nothing must-fix), fixed test first:** integers beyond 64 bits
  (record id, Money, Number, order) are refused with a sentence instead of an OverflowError; the closed-period and
  lock refusals are checked to write nothing; the inactive filter no longer passes an integer as a boolean (H5);
  one view code cannot tell a missing contact from one it may not read (only a reader of every kind is told it
  is missing), and `set_value` authorizes before it looks the record up; the Agent reads only through
  `ar.view`, `ap.view` and `project.view`, whatever AGENT_ALLOWED holds; an update or (de)activation that changes
  nothing writes no audit row. Not built (finding 7): a test proving the label check sits inside the write
  transaction (only the two-writer test covers it). Bank-number names are checked on Contact fields only, as planned.

- **Mutation test of e61dec2 and 67e9f56:** 151 mutants (custom_fields.py, the fields.manage registry entry and
  seed row). 124 killed by tests/test_custom_fields.py, 20 by tests/test_mutation_stop_c_extra.py (each re-checked),
  7 equivalent:
  - `_pick` without the AGENT_ALLOWED filter: `is_allowed` applies it again.
  - `_AGENT_READ` without `project.view`: it is the only Project reader, so the fallback gives the same code.
  - The missing-contact Agent skip, `group[-1]` for `group[0]`, and the group without `customer.manage`: the
    fallback is `customer.manage`, or every code in the group is held.
  - `_store_value` writing None into the type's column, and Yes/No stored as a bool: the same stored values.
  - The existing no-op update test compared only after a later deactivation; the new file checks the no-op alone.

## Commit hook

`.claude/settings.json` runs `.claude/hooks/pre_commit_pytest.py` before any `git commit`. It runs
`python -m pytest -q -n auto` (pytest-xdist, **without** `--dist loadgroup`: the clipboard tests use a file lock
instead), blocks the commit on failure or when xdist is missing, and writes the suite's last line to
`strataledger-commit-hook-last-run.txt` in the system temp folder. Timeout 900 s.

## Left for the packaging step (U1)

- Rename to Melara: the data folders (`%LOCALAPPDATA%\StrataLedger-dev`, `%PROGRAMDATA%\StrataLedger`), the
  environment variables (`STRATALEDGER_DATA_DIR`, `STRATALEDGER_ALLOW_TEST_KEYS`, `STRATALEDGER_LIVE_CLIPBOARD`),
  the logger name `strataledger`, the installer and the repo. A renamed data folder needs a move plan (rule 9).
  The key-derivation labels (`b"StrataLedger ... v1"`) never change.
- Screens and modules outside services still show "StrataLedger" (app_strata.pyw, sidebar.py,
  views_first_run.py, first_run_model.py, views_wizard.py, database.py docstrings, platform_support.py).
- After install, check that the program folder's ACL and owners pass HA8, and test with the built-in Administrator.

## Open points carried forward

- The linked-migration-file test (secrets audit LOW-4) is skipped on this Windows account; run it once with the
  right to create symbolic links (Developer Mode).
- AX3: the old development files stay in the repo root (`system_master.db`, `Backups/`).
- A read-only reader of a WAL file leaves an empty `-wal` and the `-shm` (AX1). Copy a company file only with
  `database.backup_database`.
- An add-on table cannot drop a column while its audit triggers name it (HA9). An add-on is trusted installation
  code (HA3, HA8).
- Phase 2.8: the restore service on `database.restore_database` (`company.restore`, K5's Master override, the
  Audit-ready flag); scheduled backups with E7 retention (`pre-upgrade` and `pre-restore` never pruned, AX2); after
  a recovery-code reissue, list the older master backups and offer to remove them, the choice audit-logged
  (secrets audit M1, owner 2026-11-18). PW1-PW11.
- Open question 7 (System context and Import-origin entries in `post_journal_entry`); undeposited funds vs
  matching (Phase 4).

## Deferred (unchanged)

- **Phase 4 posting services:** `clearing_lines`, `NEW_CLEARING`; `next_invoice_number`, `next_voucher_number`;
  the voids call `void_document_entry` and `release_allocations`; AR and AP in the chart CSVs. Deferral targets
  in `allocate`.
- **Phase 3 screens:** the unverified range and the close check's warning; `App.start_key_store()` after a key
  replacement; `KeyReplaced.recovery_code` shown once; `self.app.action_context()` on every post, approval,
  close, void and correction; `display_description`; log errors by passing the error object; `SaveFailedError`
  like any service error; the import review's rounding note; the AQ2 bridge follows RP6, the token rules in
  docs/design.md section 1, and AX5-AX10; MR8's "This removes: ..."; Company Settings > Add-ons; the custom
  fields screen (crm-fields.html) on this service.
- **C4 as amended by L2, with the deferral work (Codex batch 2, finding 1):** a period-close check for unposted
  deferral lines (`deferral_schedule_line.status` 'Scheduled', `amort_date` on or before the period's end) and the
  deferral subledger-to-GL tie-out. Warning by default, block when set through `period_close_check`; needs a new
  `check_code` in the baseline CHECK list and its seed row in warn mode.
- **B14 (Codex batch 2):** a received-payment void service (reopening the invoices it paid, NSF handling, using
  `payments.release_allocations`) is not built.
- **Backlog 21** (R42). **KS18:** retired installation keys' recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).
