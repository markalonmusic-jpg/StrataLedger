# Next step: Phase 2.9, the schema replan (areas 18, 13, 12, 10 and 17 approved; next is area 8)

Overwritten 2026-11-19 (CLAUDE.md section 8) after the owner approved area 17. Start a fresh session (MR1) and read
.claude/rules/workflow-standards.md: done, the review gate, fix mode.

## Where 2.9 stands (owner decision 2026-11-17; docs only so far)

- Working doc: `Strata_Teams\schema_replan_2026-11-17.md` (21 areas; planning keeps its status column, so this repo
  never edits it). Owner rule 2026-11-18: the mockups define the features; the schema follows them.
- **Owner-approved: 5 of 21 areas, plus the report contracts.**

  | Area | Doc | Commits |
  |------|-----|---------|
  | 18 Admin, security, audit, attachments | docs/replan_2.9/area_18_admin_security_audit.md | 6e9cdf8, 2a3b497, d38e11e; dated amendment lines from areas 13, 12, 10 and 17 |
  | 13 Close and locks | docs/replan_2.9/area_13_close_and_locks.md | dfb26b6, dac81ec (+ amendment lines from areas 12, 10 and 17) |
  | 12 Bank and reconciliation | docs/replan_2.9/area_12_bank_and_reconciliation.md | d9032ea, a837bc1, d239f32 |
  | 10 Prepaid, deferrals, reclass, period balance summary | docs/replan_2.9/area_10_prepaid_deferrals_reclass.md | 3f79eb3, 77938bc, a46501a |
  | 17 Field registry, list layouts, report builder, KPIs, measures | docs/replan_2.9/area_17_fields_layouts_reports.md | 809fb22, fded8c4 |
  | Report builder service contracts (input to area 17; amended by it) | docs/contracts/reports.md | 3d237d3, 221b996, e869ecf, fded8c4 |

- **Todo (16):** areas 1-9, 11, 14, 15, 16, 19, 20, 21; area 8 is next. Only owner-approved areas are built; an area
  still todo or drafted is not, and PROPOSED items are not built as final.
- All held schema changes land in the two baselines in one pass, tests first, after the replan is approved. Before any
  baseline edit, list the development databases it blocks (CLAUDE.md section 5.2) and ask before rebuilding (rule 9).
  Nothing in the baselines or code has changed for 2.9 yet.

## Next: area 8, PM: stages, service types, schedules, change orders

Draft `docs/replan_2.9/area_8_pm_stages_schedules.md` in the layout of the area 13 doc (0 Summary table; per topic
current state with file:line, decided with source, proposed schema, how it lands in the baselines, effect on services
and tests, tests to write later; row version and audit; conflicts flagged; questions for the owner, multiple choice,
recommended option first; open items). Sources: the area 8 row of the working doc (A 11-13 stage history effective
date, 11-15 PM flow, service types; C 21, 28, 29, 34, 108, 109, 26 and 30 (11-17); X 5: project site, target dates,
stage and status history entries, never overwrite; S 11-18 2:31 PM job Closed = Completed or Cancelled with a reason
list and stage; stages and fields per job type) and its "Inbox inputs": 2026-11-13 controller_review construction PM
items; 2026-11-17 schedule items link to a phase and the job calendar (4:19 PM), schedule data model and services (5:35
PM), schedule baseline lock, thresholds, billing link and customer view (5:46 PM), schedule terms (5:58 PM); and the
schedule hierarchy entry shared with area 3 (schedule in 8; holds, pay-when-paid and sub retainage in 3).

What the approved areas already hand to area 8 (reference, do not redesign):
- Area 13: the company work week and holidays (`company_settings.work_week`, `company_holiday`, area 13 Q14 A) are
  reused by the schedule; close tasks from the PM role (estimates to complete, completed-job review) and the checks
  `wip_current`, `manual_pct_complete`, `estimates_to_complete_updated`, `completed_job_review` need area 8's
  `project.manual_*` columns, stage and Completed state (area 13 section 2.3).
- Area 17: the Records sources `src_jobs`, `src_job_stages` (time in stage from append-only stage history),
  `src_jobs_cancelled` (stage and reason) and `src_cases` need the project, stage history and cancellation reason
  tables from area 8 (service cases from area 15); `custom_field_def` job type scoping (with area 16); `from_jobs`
  measures read `project.completed_on` and `cf.project.*`; the split-by columns use `job`, `job_type` and `pm`.
- Area 10: job cost shows a deferred line's cost as recognized; WIP and job cost read GL lines carrying the job.

## Handed to later areas by the approved ones (open items, not decisions)

- **Area 1/2:** payment record and receipt destination (area 12 Q20 A keeps deposits and transfers in 12); pay run
  posting shape (one bank line per payment assumed); `payment.method` values for ACH, wire and card.
- **Area 3/5:** a job per bill and invoice line (area 10 F8); the bill void calls `deferrals.void_for_bill`.
- **Area 7/8:** job cost reads GL lines carrying a job (deferred cost as recognized); `project.manual_*` columns for the
  manual % complete close check; WIP recalculation; area 8 reuses area 13's work week and holidays (area 13 Q14 A).
- **Area 7 (from area 17):** `operating_plan_version` and `operating_plan_line` (a saved report's plan compare points at
  the version); `project_budget` for the `job_budget` compare; area 17 adds `saved_report.split_by`.
- **Areas 6, 8, 15, 16 (from area 17):** the Records source tables (`lead`, stage and status history, `activity`,
  `service_case`, the lead-to-job link, the sales rep on the contract) and `custom_field_def.record_type` 'Lead'; until
  they exist those sources are not offered (Estimates and Jobs can ship first).
- **Area 9:** an item table for `reclass_line.original_item_ref`; the warehouse close checks (area 13 section 2.3).
- **Area 11:** reuses the prepaid schedule grid; depreciation and loan lock areas.
- **Area 14:** `pending_approvals` beyond journal entries; the approvals the new codes need.
- **Area 21:** `row_version` on `company_settings` and the stale-save refusal; the open payments limits (30 and 180
  days) as policy records (area 12 Q16 A).
  Also from area 17: a general notification feed (a delivered report is unread while `report_delivery.read_at` is
  empty) and whether saved views can be shared.
- **Areas 12, 13, 10 and 17 build items for later phases:** (area 17: `field_registry`, `list_prefs`, `report_layouts`,
  `report_formulas`, `report_sources`, `saved_reports`, `packs`, `report_run`, `report_records`, `report_combined`,
  `kpis`, `measures`, `report_schedules`, `report_output`, and the `perf` test.)
- **Areas 12, 13 and 10 build items:** `bank_feed.py`, `reconciliation.py`, `banking.py`,
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
