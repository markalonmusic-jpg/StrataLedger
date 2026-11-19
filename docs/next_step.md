# Next step: Phase 2.9, the schema replan

Written 2026-11-18 at the end of Phase 2.7 STOP C. Overwritten at each STOP (CLAUDE.md section 8). Start a fresh
session (MR1) and read .claude/rules/workflow-standards.md: done, the review gate, fix mode.
Status: **STOP C is awaiting the owner's approval** (review gate). Do not start 2.9 until it is approved.

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

- `modules/services/custom_fields.py` (tests/test_custom_fields.py, 202 tests): `list_fields`, `define_field`,
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
- **Backlog 21** (R42). **KS18:** retired installation keys' recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).
