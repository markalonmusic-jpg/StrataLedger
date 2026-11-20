# Next step: Phase 2.9, the schema replan (areas 18, 13, 12 and 10 approved; next is area 17)

Overwritten 2026-11-19 (CLAUDE.md section 8) after the owner approved areas 13, 12 and 10. Start a fresh session (MR1)
and read .claude/rules/workflow-standards.md: done, the review gate, fix mode.

## Where 2.9 stands (owner decision 2026-11-17; docs only so far)

- Working doc: `Strata_Teams\schema_replan_2026-11-17.md` (21 areas; planning keeps its status column, so this repo
  never edits it). Owner rule 2026-11-18: the mockups define the features; the schema follows them.
- **Owner-approved: 4 of 21 areas, plus the report contracts.**

  | Area | Doc | Commits |
  |------|-----|---------|
  | 18 Admin, security, audit, attachments | docs/replan_2.9/area_18_admin_security_audit.md | 6e9cdf8, 2a3b497, d38e11e; dated amendment lines from areas 13, 12 and 10 |
  | 13 Close and locks | docs/replan_2.9/area_13_close_and_locks.md | dfb26b6, dac81ec (+ two amendment lines) |
  | 12 Bank and reconciliation | docs/replan_2.9/area_12_bank_and_reconciliation.md | d9032ea, a837bc1, d239f32 |
  | 10 Prepaid, deferrals, reclass, period balance summary | docs/replan_2.9/area_10_prepaid_deferrals_reclass.md | 3f79eb3, 77938bc, a46501a |
  | Report builder service contracts (input to area 17) | docs/contracts/reports.md | 3d237d3, 221b996, e869ecf |

- **Todo (16):** areas 1-9, 11, 14, 15, 16, 19, 20, 21, and area 17 (next). Only owner-approved areas are built; an area
  still todo or drafted is not, and PROPOSED items are not built as final.
- All held schema changes land in the two baselines in one pass, tests first, after the replan is approved. Before any
  baseline edit, list the development databases it blocks (CLAUDE.md section 5.2) and ask before rebuilding (rule 9).
  Nothing in the baselines or code has changed for 2.9 yet.

## Next: area 17, field registry, list layouts, report builder

Draft `docs/replan_2.9/area_17_report_builder.md` in the layout of the area 13 doc (0 Summary table; per topic current
state with file:line, decided with source, proposed schema, how it lands in the baselines, effect on services and tests,
tests to write later; row version and audit; conflicts flagged; questions for the owner, multiple choice, recommended
option first; open items). Sources: the area 17 row of the working doc (A 11-15 field registry, list layout preferences,
report builder and consolidation; C 92, 100, 156; S 11-18 3:19 and 3:22 PM; `money.view` for Records money fields).

What the approved areas already hand to area 17 (do not redesign; reference them):
- docs/contracts/reports.md section 12 lists the schema needs: layouts and items, formula tokens, charts, Records
  parts, saved reports and packs, **KPIs (`kpi`, `kpi_value`, frozen in the close transaction)**, schedules and
  deliveries, non-financial measures, the operating plan (area 7), combined runs (no new table), Records source
  tables from areas 6, 8 and 15, and the cash flow category and company Accrual/Cash default (item 18).
- Area 13 section 4.5: the close inserts `kpi_value` rows in the same transaction as the snapshot; typed measures are
  refused in a closed period and derived ones skipped (area 13 Q19 A). Area 13 section 4.4 defines ending cash (area 12
  Q12 A: every `bank_account` kind except Credit card, plus undeposited funds), the cash set the cash flow report uses.
- Area 10 section 4: `ledger_period_balance`, `dimension_set`, `dimension_set_member`, written only in
  `ledger._seal_and_post` (`ledger.py:927`); area 17 only reads them. Area 10 section 2: `reclass_line` for "As
  reclassed" (contracts 4.4).
- Area 18 amendments: the Q8 report codes and `money.view` placement, derived-table exempt list.

## Handed to later areas by the approved ones (open items, not decisions)

- **Area 1/2:** payment record and receipt destination (area 12 Q20 A keeps deposits and transfers in 12); pay run
  posting shape (one bank line per payment assumed); `payment.method` values for ACH, wire and card.
- **Area 3/5:** a job per bill and invoice line (area 10 F8); the bill void calls `deferrals.void_for_bill`.
- **Area 7/8:** job cost reads GL lines carrying a job (deferred cost as recognized); `project.manual_*` columns for the
  manual % complete close check; WIP recalculation; area 8 reuses area 13's work week and holidays (area 13 Q14 A).
- **Area 9:** an item table for `reclass_line.original_item_ref`; the warehouse close checks (area 13 section 2.3).
- **Area 11:** reuses the prepaid schedule grid; depreciation and loan lock areas.
- **Area 14:** `pending_approvals` beyond journal entries; the approvals the new codes need.
- **Area 21:** `row_version` on `company_settings` and the stale-save refusal; the open payments limits (30 and 180
  days) as policy records (area 12 Q16 A).
- **Areas 12, 13, 10 build items for later phases:** `bank_feed.py`, `reconciliation.py`, `banking.py`,
  `period_locks.py`, `close_tasks.py`, `deferrals.py`, `reclass.py`; the static test that every journal-writing service
  calls `period_locks.check_open`.
- **Still open from STOP C:** custom field columns `help_text`, on board card, shown from stage, job types (area 16, with
  CODE_CHANGES 27); custom fields refuse Estimate until an estimate service exists (area 6); RI1 (decided, not built).
  Item 4 of the STOP C list (area locks on custom-field edits) is answered by area 13 Q6 A.
- Open question 7 (System context and Import-origin entries in `post_journal_entry`): area 10 Q7 A decides it for the
  deferral runner (origin System, no approval, no date warnings, needs `deferral.manage`); the posting work builds it.

## Commit hook (owner 2026-11-19; changed in 887da07)

`.claude/settings.json` runs `.claude/hooks/pre_commit_pytest.py` before any `git commit` (timeout 1500 s).
- **Docs only:** when every staged file is under `docs/`, the hook skips the suite, prints one line, `docs only: suite
  skipped (N files)`, and writes it to `strataledger-commit-hook-last-run.txt` in the system temp folder (the same file
  that holds the suite's last line).
- **Anything else runs the full suite exactly as before** (`python -m pytest -q -n auto`, pytest-xdist, without `--dist
  loadgroup`; blocks on failure or when xdist is missing): a staged file outside `docs/` (code, tests, migrations,
  `.claude`, the hook itself), a rename into or out of `docs/` (read as delete plus add), nothing staged, a git error.
- **The hook looks before the command runs.** A commit whose own command changes the staged set (`git add ... &&
  git commit`, `-a`, `-am`, `--amend`, `--include`, `--only`, a pathspec after `--`, `git -C`) runs the suite, since the
  staged files it sees are not final. **Stage in one call and commit in the next to get the skip.** A commit message
  that mentions `git add` also runs the suite (a false alarm costs one run, never a missed one).
- Tests: tests/test_commit_hook.py (both paths, the renames in a real temp repo, the staging-command guard).

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
  Backups must include the company's attachments (owner 2026-11-18, area 18 Q14): a company backup without them
  is not complete; only the database-only safety copies (`pre-upgrade`, `addon-<key>`, `pre-restore`, AX2) are
  exempt. Each run is recorded in the master `backup_run` (docs/replan_2.9/area_18_admin_security_audit.md
  section 4).
- Undeposited funds vs matching (Phase 4): area 12 Q11 A decides it for deposits (clearing groups on the undeposited
  funds account).

## Deferred (unchanged except where an approved area now designs it)

- **Phase 4 posting services:** `clearing_lines`, `NEW_CLEARING`; `next_invoice_number`, `next_voucher_number`;
  the voids call `void_document_entry` and `release_allocations`; AR and AP in the chart CSVs. Deferral targets
  in `allocate`.
- **Phase 3 screens:** the unverified range and the close check's warning; `App.start_key_store()` after a key
  replacement; `KeyReplaced.recovery_code` shown once; `self.app.action_context()` on every post, approval,
  close, void and correction; `display_description`; log errors by passing the error object; `SaveFailedError`
  like any service error; the import review's rounding note; the AQ2 bridge follows RP6, the token rules in
  docs/design.md section 1, and AX5-AX10; MR8's "This removes: ..."; Company Settings > Add-ons; the custom
  fields screen (crm-fields.html) on this service.
- **C4 as amended by L2:** the deferral close checks are now designed (area 13 section 2.3 and area 10 section 3:
  `deferral_entries_posted`, `deferral_tie_out`, warn by default); they ship with the prepaid schedule service, not
  before. The baseline `period_close_check` CHECK list gets their codes in the 2.9 pass.
- **B14 (Codex batch 2):** a received-payment void service (reopening the invoices it paid, NSF handling, using
  `payments.release_allocations`) is not built.
- **Backlog 21** (R42). **KS18:** retired installation keys' recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).

History of what was done before 2.9 (STOP C custom fields service, Codex batch 2 posting fixes, their reviews and
mutation tests) is in docs/status_log.md (2026-11-18 entries) and the module docstrings.
