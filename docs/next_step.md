# Next step: Phase 2.9, the schema replan (areas 18, 13, 12, 10, 17, 8, 15, 6 and 7 approved; next area chosen by the owner)

## Planning handoff (2026-11-20): service-quote decision reconciliation

- State: planning-only reconciliation of the confirmed 2:10 PM, 2:20 PM and 2:30 PM service-quote rules into areas
  6, 7, 8, 15 and the existing area 17 report rule. Areas 5 and 14 have no Phase 2.9 plan document yet; their
  ownership boundaries and required inputs are handed off below. The internal `contract` row remains derived from
  the signed quote revision. No code, migration, baseline or test file was changed; no test, stage, commit or push was
  run. Existing unrelated working-tree changes and untracked paths remain preserved.
- Rules reconciled: one estimate links to exactly one lead or case; case problem edits sync during drafting and quote
  content freezes when printed; service type defaults the cost enterer/pricer, PM, reusable payment term and quote
  validity; cost enterer and PM stay separate with Solo/unset-controls PM defaulting to cost enterer; send-backs
  return to the estimate submitter with append-only history; signing freezes billing kind, price, terms, tax details
  and the customer-signed tax-inclusive total; signed upload records optional repair groups as Accepted or Declined
  and only required plus Accepted lines determine the signed amount; jobs and contract rows are created only on
  signed-quote upload, while a case enters In progress when cost work starts; Warranty and goodwill use separate cost
  destinations, with the `service_goodwill` System account role and separate reports; unrelated upsells are a human
  new-estimate rule with no schema enforcement.
- Blockers/open questions: later-area implementation details remain for area 5 invoice line/tax carry-forward and
  area 14 approval routing to `approval_request`'s submitter. Area 18 now defines the configurable
  `service_goodwill` System account mapping. The four review findings are corrected in areas 6, 7, 8 and 15:
  accepted work drives the signed totals and original budget, warranty and goodwill use distinct destinations,
  and estimate cost work starts the case transition.
- Next action: planning review of the amended sections and later-area handoffs; then select the next area with the
  owner. Do not start baseline or code work until the whole replan is approved.

## Historical stop (2026-11-20): Git hook repair planning snapshot

- State: on `main`; local `core.hooksPath` is `.githooks`. The hook, settings and `CLAUDE.md` changes were already
  staged. `tests/test_commit_hook.py` now covers the tracked Git hook instead of the removed Claude PreToolUse entry;
  its focused run passed (68 tests). The `.codex/hooks.json` and `.codex/hooks/` paths remain untouched and untracked.
- Test outcome: with default `%TEMP%`, the focused ACL test failed and the full suite had 4,209 passed, 2 skipped,
  1 failed in 315.94 s. A later dedicated-basetemp attempt found `PYTEST_ADDOPTS` unset but passed a Windows path with
  backslashes. Pytest parsed them as escapes and created the test temp under the repo at
  `C:\Users\marka\StrataLedger-clean\Usersmarka.pytest-strataledger-acl`; the focused test failed its exact-mask
  assertion there (1 failed in 0.15 s). That generated directory was removed. No ACL inspection or full-suite run
  followed. The original `%TEMP%` still inherits the recorded `Modify, Synchronize` ACEs for `CodexSandboxUsers` and
  SID `S-1-5-21-3876112204-1666981215-754291341-1030728988`. The ACL test was not changed or skipped.
- Python: 3.11.9, pytest 9.2.0 and `xdist` import passed under the non-admin `marka` identity.
- Blocker/open question: the dedicated-basetemp attempt did not reach the proposed path because `PYTEST_ADDOPTS`
  consumed the Windows backslashes. No ACLs or pytest settings were changed.
- Next action: rerun with the dedicated path written with forward slashes in `PYTEST_ADDOPTS`, confirm the focused
  test directory is actually under `C:\Users\marka\.pytest-strataledger-acl`, inspect its ACL read-only, then run the
  full suite with the same option. Stop on any failure. Only after a full pass, verify the commit-launching process
  inherits the basetemp option, stage the approved paths, commit normally on `main`, verify the hook record timestamp,
  and push. **No commit or push has occurred.**
- Follow-up (2026-11-20): the forward-slash preflight resolved exactly to
  `C:/Users/marka/.pytest-strataledger-acl`; the target was absent before the run. The focused ACL test passed (1
  passed), but read-only inspection found an inherited `CodexSandboxUsers` ACE with mask `1179817` on the test
  directory, not the expected full-control mask `2032127`. The ACL gate failed, so the full suite was not run. This
  pass applies only to the dedicated basetemp and does not repair `%TEMP%`'s inherited ACEs. Blocker: investigate the
  dedicated directory's inherited ACE without changing the test or ACL. Next: planning review of the service-quote
  amendments in this step, then resume ACL diagnosis before any later commit.
- Historical service-quote amendment review (2026-11-20, before follow-up `2b98b15`): commit `1e912fa` was pushed. The step reviewer found that
  the tax-to-invoice sentence belongs only in the later-area handoff and that the estimate schema needed an explicit
  PM field. Those points are corrected locally; the report rule is also placed under area 17 section 4.4. Blocker:
  the requested single commit is already pushed, so a follow-up commit would exceed that limit and amending it would
  require a force-push. The stop applied at that review. See the current planning handoff above.

Overwritten 2026-11-20 (CLAUDE.md section 8) after the owner approved area 7. Start a fresh session (MR1) and read
.claude/rules/workflow-standards.md: done, the review gate, fix mode.

## Where 2.9 stands (owner decision 2026-11-17; docs only so far)

- Working doc: `Strata_Teams\schema_replan_2026-11-17.md` (21 areas; planning keeps its status column, so this repo
  never edits it). Owner rule 2026-11-18: the mockups define the features; the schema follows them.
- **Owner-approved: 9 of 21 areas, plus the report contracts.**

  | Area | Doc | Commits |
  |------|-----|---------|
  | 18 Admin, security, audit, attachments | docs/replan_2.9/area_18_admin_security_audit.md | 6e9cdf8, 2a3b497, d38e11e; dated amendment lines from areas 13, 12, 10, 17, 8, 15, 6 and 7 (seeded codes 111) |
  | 13 Close and locks | docs/replan_2.9/area_13_close_and_locks.md | dfb26b6, dac81ec (+ amendment lines from areas 12, 10, 17 and 7) |
  | 12 Bank and reconciliation | docs/replan_2.9/area_12_bank_and_reconciliation.md | d9032ea, a837bc1, d239f32 |
  | 10 Prepaid, deferrals, reclass, period balance summary | docs/replan_2.9/area_10_prepaid_deferrals_reclass.md | 3f79eb3, 77938bc, a46501a (+ amendment line from area 7) |
  | 17 Field registry, list layouts, report builder, KPIs, measures | docs/replan_2.9/area_17_fields_layouts_reports.md | 809fb22, fded8c4 (+ amendment line from area 7) |
  | 8 PM: stages, service types, schedules, change orders, forecast | docs/replan_2.9/area_8_pm_schedules.md | 3d15762, c835d20 and the approval commit b9ff295 (+ amendment lines in area 18; amendment lines from areas 15, 6 and 7) |
  | 15 CRM: leads, activities, cases, comments, routing | docs/replan_2.9/area_15_crm.md | 2237b63, 03477c0, 3b8108b and the approval commit (+ amendment lines in areas 8 and 18; amendment lines from areas 6 and 7) |
  | 6 Estimates, contracts, pricing, T&M rates, contract templates | docs/replan_2.9/area_6_estimates_contracts.md | 2c82148, d297397, b0bea27 and the approval commit (+ amendment lines in areas 8, 15 and 18; amendment lines from area 7) |
  | 7 Jobs, budgets, cost codes and cost types, dimensions, operating plan, WIP | docs/replan_2.9/area_7_jobs_budgets_cost_codes.md | 7bab6f0, 7ebcd4f, 8b68381, d582c7e, 64519fd and the approval commit (+ amendment lines in areas 6, 8, 10, 13, 15, 17 and 18; seeded codes 111; shipped Service manager template) |
  | Report builder service contracts (input to area 17; amended by it) | docs/contracts/reports.md | 3d237d3, 221b996, e869ecf, fded8c4 |

- **Todo (12):** areas 1-5, 9, 11, 14, 16, 19, 20, 21; the owner chooses the next. Only owner-approved areas are built;
  an area still todo or drafted is not, and PROPOSED items are not built as final.
- All held schema changes land in the two baselines in one pass, tests first, after the replan is approved. Before any
  baseline edit, list the development databases it blocks (CLAUDE.md section 5.2) and ask before rebuilding (rule 9).
  Nothing in the baselines or code has changed for 2.9 yet.

## Next: an area chosen by the owner

Ask the owner which todo area to draft next (areas 1-5, 9, 11, 14, 16, 19, 20, 21). Draft it in
`docs/replan_2.9/area_<n>_<name>.md` in the layout of the area 13 doc (0 Summary table; per topic current state with
file:line, decided with source, proposed schema, how it lands in the baselines, effect on services and tests, tests to
write later; row version and audit; conflicts flagged; questions for the owner, multiple choice, recommended option
first; open items), from the area's row and "Inbox inputs" in the working doc. Cite "C21" style codes as sections of
`CODE_CHANGES_NEEDED.md`, not decision codes. Every area prompt lists "Checked against: <shared_decisions entry
times>" (owner 2026-11-20 12:56 AM), and the area's report repeats it. A later owner decision that replaces an
earlier one is added as a dated amendment line, and the replaced items are marked "Withdrawn <date> (owner <time>)"
beside them, never deleted (area 7 fix 3).

## Handed to later areas by the approved ones (open items, not decisions)

- **Area 1/2:** payment record and receipt destination (area 12 Q20 A keeps deposits and transfers in 12); pay run
  posting shape (one bank line per payment assumed); `payment.method` values for ACH, wire and card.
- **Area 3/5:** a job per bill and invoice line (area 10 F8); the bill void calls `deferrals.void_for_bill`.
- **Area 7/8 (area 7 done, approved 2026-11-20):** job cost reads GL lines carrying a job (area 7 section 7);
  `project.manual_*` columns (area 7 section 1.3); WIP schema now, the WIP service with v1.1 (area 7 Q18 A); area 8
  reuses area 13's work week and holidays (area 13 Q14 A).
- **Area 7 (from area 17; done, approved 2026-11-20):** `operating_plan_version` and `operating_plan_line`;
  `project_budget` for the `job_budget` compare; area 17 adds `saved_report.split_by`.
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
- **Areas 12, 13 and 10 and 17 build items for later phases:** (area 17: `field_registry`, `list_prefs`,
  `report_layouts`, `report_formulas`, `report_sources`, `saved_reports`, `packs`, `report_run`, `report_records`,
  `report_combined`, `kpis`, `measures`, `report_schedules`, `report_output`, and the `perf` test.)
- **Areas 12, 13 and 10 build items:** `bank_feed.py`, `reconciliation.py`, `banking.py`,
  `period_locks.py`, `close_tasks.py`, `deferrals.py`, `reclass.py`; the static test that every journal-writing service
  calls `period_locks.check_open`.
- **Still open from STOP C:** custom field columns `help_text`, on board card, shown from stage, job types (area 16, with
  CODE_CHANGES 27); custom fields refuse Estimate until an estimate service exists (area 6); RI1 (decided, not built).
  Item 4 of the STOP C list (area locks on custom-field edits) is answered by area 13 Q6 A.
- Open question 7 (System context and Import-origin entries in `post_journal_entry`): area 10 Q7 A decides it for the
  deferral runner (origin System, no approval, no date warnings, needs `deferral.manage`); the posting work builds it.

## Handed to later areas by area 8 (open items, not decisions)

- **Area 7 (done, approved 2026-11-20; area 7 section 1.3 writes the `project` DDL, amendment line in area 8 section
  7):** the area 8 columns, `status` dropped, `project_budget.revision_id`, budget totals derived (Q5 A),
  `project.row_version`, the `job_budget` compare.
- **Area 6 (done, approved 2026-11-20; amendment lines written in area 8):** `rate_card`, `contract_milestone`, new SOV
  lines from an approved change order; still open: the contract's completion date as the schedule's contract date.
- **Area 15 (done, approved 2026-11-20; Q13 B dropped `case_job`):** reuses `crew` and `calendar_item` times for busy
  checks; defines `service_case`, the lead stage history twin and the lead-side stage role 'Lost'; the case Resolve
  prompt.
- **Areas 3, 4, 5, 9:** a warning naming the hold on costs, POs and invoices of a held job (never a refusal);
  `subcontract_id` on schedule tasks (area 4); committed amounts for the forecast figures (areas 4 and 9).
- **Area 14:** the change order approval chain (default OFF) beside the customer approval.
- **Area 16:** per-stage custom fields and job type scoping (`custom_field_def`); stage guidance is area 8's.
- **Area 20:** sending final bill requests and share-schedule emails; the email log id.
- **Area 21:** the company calendar query over tasks, milestones and `calendar_item`; `row_version` on the new
  `company_settings` columns (controls and the crew label).
- **Build items for later phases (area 8):** `job_stages.py`, `job_close.py`, `job_hold.py`, `schedule_templates.py`,
  `job_schedules.py`, `work_calendar.py`, `calendar_items.py`, `change_orders.py`, `forecast.py`.

## Handed to later areas by area 15 (open items, not decisions)

- **Area 6:** `estimate.lead_id`; `estimate.contact_id` nullable before signing; `contract.sales_rep_user_id`;
  contract signing calls into `leads.py` (the lead's Won); the Cancellation case type's "Cancel the contract".
- **Area 7 (done, approved 2026-11-20):** `project.sales_rep_user_id`; `project.source_case_id`.
- **Area 5:** the `lead_contact` hand-off at signing; the contact-person table.
- **Area 14:** approvals on sales stage moves (default OFF).
- **Area 16:** Lead and Case custom fields; per-service-type fields.
- **Area 20:** the `.ics` invite details; the company calendar address.
- **Area 21:** the notification feed; `last_seen_at`; the CRM alerts.

## Handed to later areas by area 6 (open items, not decisions)

Area 6's amendment lines are already in areas 8, 15 and 18; these are the items that are not.
- **Area 7 (done, approved 2026-11-20):** `cost_type` and `cost_code.cost_type_id`; the budget from the summary by cost
  code at Mark signed; `project.sales_rep_user_id`; `project.source_revision_id`; estimate lines on leaf codes (Q7 A,
  amendment line in area 6 section 3.3).
- **Area 5:** the create-customer service and contacts at Mark signed; the draft (unposted) deposit invoice, credit side
  by role `customer_deposits`; `contract_milestone.invoice_id`; T&M monthly drafts at the contract's frozen rates and
  the near-not-to-exceed warning (with area 19); whether the T&M revenue account needs a system role. Carry only the
  required and Accepted optional quote lines, their frozen tax-rate identity/name/rate, taxable base and tax cents,
  and the signed revision's pre-tax, tax and tax-inclusive total onto the invoice. The internal contract row and
  amount stay derived from that signed quote.
- **Area 9:** `material_code`; until it exists `estimate_cost_line.material_code_id` is a plain integer.
- **Area 14:** the Estimate policy, `sales_authority_limit` routing, the Contract policies (wording changes and contract
  cancellation approval), all OFF by default. Define service-quote send-back routing to `approval_request`'s submitter
  (PM or rep); pass that target to area 6 and retain append-only from/to status, from/to holder and reason history.
- **Area 19:** payroll import hours (employee, job, cost code) as the T&M time source, billed at the frozen rates.
- **Area 4:** pay apps read the contract's SOV and cost codes, retainage and the deposit-remaining balance.
- **Area 16:** custom fields on Estimate (on `estimate`, Q25 A); the refusal in `custom_fields.py` is lifted with
  `estimates.py`. **Area 17:** `src_leads_estimates` field ids and the rep on the contract. **Area 20:** the proposal
  email and its log id. **Area 21:** notifications (PM assigned, Ask the rep, send back, the 3-day expiry reminder) and
  `row_version` on the new `company_settings` columns.
- **2.8 (backups):** the company logo's `storage.py` key (`company_branding.logo_storage_key`) is included in the
  company backup and restore, like attachments, and recorded in `backup_run`.
- **Build items for later phases (area 6):** `estimates.py`, `contracts.py`, `pricing.py`, `rate_cards.py`,
  `contract_templates.py`, and one PDF renderer service (the library choice is for the build step).

## Handed to later areas by area 7 (open items, not decisions)

Area 7's amendment lines are already in areas 6, 8, 10, 13, 15, 17 and 18; these are the items that are not
(area 7 section 13).
- **Area 8 (still open):** `service_type` default dimension values (C62 "starts with profit and cost center") as a
  `service_type_dimension` table, and a default `poc_method`; the transfer and CO services call area 7's budget
  functions; `job_forecast_line` seeding moves into `job_budgets.set_original`.
- **Chart template (`templates/coa/construction.csv`, baseline pass):** the cost type roles of Q20 A (`job_labor`
  5010, `job_materials` 5030, `job_subcontract` 5040, `job_equipment` 5050, `job_overhead` 5070) and
  `warranty_expense` on 5080; no row carries `contract_cost` today although `company_settings.contract_cost_acct_id`
  exists. The shipped cost code list `templates/cost_codes/construction.csv` is new.
- **Areas 3, 4, 5, 9, 19:** every cost and invoice service calls the budget control and the JD1 resolver (no draft
  check, Q1); committed amounts (4, 9); the PO's inline over-budget transfer calls `add_transfer_rows` (9); T&M lines
  default Billable with the job's markup (5); `is_prevailing_wage` and WH-347 (19); the customer's job-sites list and
  tax rate from the site (5).
- **Area 16:** job custom fields per stage and service type.
- **Area 21:** entities inside one company file (which entity a job belongs to is not designed in area 7);
  `row_version` on the new `company_settings` columns; the notification for "Enter budget".
- **Area 18 (done in section 4.2):** `service_goodwill` is a configurable System account role used by area 7's
  Service overhead destination; each company maps it to an account, with no account number hard-coded. Warranty and
  goodwill remain separate report destinations even if both map to the same account.
- **Imports (backlog 4):** cost code and dimension paste lists use the Import service; dimension tables for
  `time_entry` and `staged_line` (JD1).
- **Raised in the area 7 fix reports, not yet decided by the owner:** a case quote's service type and sales rep
  (no lead to copy them from; area 15's `service_job_type_id` is the default service type); a no-charge quote on a case
  with no job (no original job for the Warranty roll-up); the Service manager template's scope All with
  `project.manage`; a Service manager cannot record payments (`payment.receive` stays Accountant-only, owner 3:38 AM).
- **Build items for later phases (area 7):** `jobs.py`, `job_budgets.py`, `cost_codes.py`, `dimensions.py` (with the
  resolver), `operating_plans.py`, `job_cost.py`, `wip.py` (v1.1), the cost code template loader.

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
