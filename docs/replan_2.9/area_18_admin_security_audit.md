# Step 2.9 schema replan, area 18: admin, security, audit, attachments

Status: **Owner-approved 2026-11-19** (first draft 2026-11-18, 6e9cdf8; owner answers Q1-Q17 2026-11-18, folded
in below, 2a3b497; owner answers Q18-Q24 2026-11-19, all A, section 7). Docs only: nothing here changes
code, a baseline, a migration or a test.
Nothing is built until the owner marks area 18 owner-approved in `Strata_Teams\schema_replan_2026-11-17.md`. Every
table, column and code below is PROPOSED until then. No questions are open.

Sources read (only these, searched by date, title or code):
- `Strata_Teams\schema_replan_2026-11-17.md`, row 18 and the source keys.
- `Strata_Teams\inbox\archive\to_planning_archive_2026-11-17.md`: 2026-11-14 "admin and security rules",
  2026-11-15 "Memo and attachments on every input form", 2026-11-15 "persona audit, schema implications".
- `Strata_Teams\inbox\to_planning.md` (open): 2026-11-17 "new access model, roles × levels + job-title access
  templates + per-user tweaks" and "access templates".
- `StrataLedger_mockups\CODE_CHANGES_NEEDED.md` sections 57 and 72.
- `Strata_Teams\codex_reports\schema_gaps_vs_mockups_2026-11-18.md` item 9.
- docs/decisions_2026-11-11.md by code: AX1, AX2, AX4, E7, E11, MR1-MR9, R16, R27, R30, R35, RP1, HA11, K13,
  AQ1 (index line only; the file has no longer AQ1 entry), H4.
- `migrations/001_company.sql`, `migrations/001_master.sql`, and the services that write the tables named.
- Added for O1 (owner 2026-11-18): `Strata_Teams\ux_research_roles_access_2026-11-17.md` sections 2 and 6;
  docs/roles_permissions_design.md section 3; `modules/services/role_templates.py` (the built starter roles).

---

## 0. Summary

| # | Topic | Decided (owner 2026-11-18) | Baseline |
|---|-------|----------------------------|----------|
| 1 | Audit (AX4) | Keep the audit triggers (Q1 A). Services add `reason`, `origin`, `event`, `event_id` through `tx.py`. Redaction lives in the triggers, from one shared list with RP1 and HA11. Every business table is audited, and only derived tables are exempt (list in 1.2). The audit log keeps the last 4 of `company_settings.tax_id` (Q6 A) | both |
| 2 | Access model | Several roles per user (Q2 B), each with a level. Fixed system roles (Q3 A). Caps are their own lists, and a user's cap is the union of their roles' caps (Q4 A, C5). One job title (Q5 A). Add and Remove overrides, each with a reason (Q7 A). Seed tables in 2.4 | both |
| 3 | Memos and attachments | `memo` (max 4,000) on every form header, never printed. `attachment` replaces `file_attachment`: append-only, and a removal is marked with a reason, the file kept (Q12 A). Removing from a posted document follows the posted-document rules (Q13 A plus) | company |
| 4 | Settings history, backup runs | Settings history read from `audit_log` (Q16 A); a reason is needed for controls (Q15 A). New master `backup_run` table. 2.8 backups must include attachments (Q14 A plus) | both |

Conflicts: section 6 (C1 amended, C5 and C7 closed, C8 and C9 new).

---

## 1. Audit: before/after detail, reason, who writes it (AX4)

### 1.1 Current state

**The two audit_log tables**
- Master `audit_log`: `migrations/001_master.sql:20-45`. Columns: `log_id`, `logged_at DATETIME DEFAULT
  CURRENT_TIMESTAMP`, `user_id` (FK app_user), `table_name`, `record_id`, `action` (CHECK Insert, Update, Delete,
  Post, Approve, Void), `old_value`, `new_value`, `software_version_tag`, `terminal_id`, `reason TEXT`
  (`:43`, "Replan: ... filled through audit_context by a later step"). Index `idx_audit_log_user_id` (`:646`).
- Company `audit_log`: `migrations/001_company.sql:144-168`. The same columns, `user_id` without an FK (CLAUDE.md
  section 4), and `reason TEXT` (`:167`). The company file has **no index** on `audit_log`.
- Append-only: `audit_log_no_update` and `audit_log_no_delete` (company `:1427`, `:1433`; master `:180`, `:186`).
  `audit_context` cannot be deleted (company `:1421`, master `:174`).
- **`reason` exists in both baselines but nothing fills it.** `audit_context` has no reason column (company
  `:349-355`, master `:88-94`), and no trigger copies one.
- **No `origin` column** on either `audit_log` or `audit_context`, though E11 places `origin` on audit_log
  (conflict C2). `tx.py:3-4` says audit_context "has no `origin` column yet".
- `logged_at` comes from the database clock (`CURRENT_TIMESTAMP`, `YYYY-MM-DD HH:MM:SS` with no offset), not from
  `context.now` (conflict C3).
- The `action` CHECK lists Post, Approve and Void, but every trigger writes only Insert, Update or Delete.

**Who writes audit rows today.** Only triggers. No module runs `INSERT INTO audit_log` (grep of `modules/`: none).
`tx.AuditStamp` (`modules/services/tx.py:72-92`) sets `audit_context.user_id`, `terminal_id`,
`software_version_tag` and `set_at` inside each write transaction and clears them before COMMIT. Add-on tables get
generated triggers from `migrations/addon_audit_triggers.sql` (`modules/database.py:756-880`, HA9).

**Every audit trigger in the company baseline** (`001_company.sql`, 127 `INSERT INTO audit_log` statements). Each
writes the row's columns as JSON, `old_value` for the old row and `new_value` for the new one:

| Table | Triggers (line) | Notes |
|-------|-----------------|-------|
| journal_entry | insert 2084, update 2121, delete 2229 | Carries its `journal_line` rows as `$.lines` (`:2180-2199`), as they are when the header row changes |
| fiscal_period | 2266, 2289, 2322 | |
| account | 2345, 2371, 2410 | |
| invoice | 2436, 2486, 2573 | Includes `memo`. `invoice_line` is not in the JSON and has no trigger of its own |
| payment | 2623, 2646, 2679 | |
| payment_allocation | 2702, 2728, 2767 | |
| invoice_series | 2793, 2815, 2846 | |
| company_addon | 2868, 2886, 2909 | |
| addon_schema_version | 2928, 2944, 2963 | |
| bank_reconciliation | 2979, 2997, 3020 | |
| approval_request | insert 3059, update 3086 | R16: never deleted (trigger) |
| approval_action | insert 3127 | R16 |
| role | 3194, 3213, 3238 | |
| role_permission | 3257, 3272, 3289 | |
| approval_limit | 3304, 3320, 3339 | |
| user_project_scope | 3355, 3370, 3387 | |
| approval_policy | 3402, 3421, 3446 | |
| approval_step | 3465, 3483, 3506 | |
| company_settings | insert 3524, update 3587 | Writes `tax_id` in full (`:3537`, `:3599`, `:3650`); masked under Q6 |
| document_approval_setting | update 3718 | |
| bank_account | 3732, 3745, 3758 | Only `account_last4` (`:3730` comment) |
| fiscal_year | 3780, 3792, 3806 | |
| period_close_check | update 3817 | |
| ledger_chain_key | insert 3830, update 3841 | Fingerprint only, no key material |
| ledger_checkpoint | insert 3853 | Includes `mac` and `chain_hash` (integrity values, not secrets) |
| contact | 4200, 4242, 4313 | `tax_id_last4` only (`:4219`, `:4260`); `exemption_cert_no` left out; includes `bank_payee_id` and `memo` |
| contact_site | 4355, 4380, 4417 | |
| company_entity | 4442, 4462, 4489 | |
| fiscal_period_lock | 4509, 4529, 4556 | |
| cost_code | 4576, 4597, 4626 | |
| service_type | 4647, 4665, 4688 | |
| service_stage | 4706, 4728, 4759 | |
| stage_trigger | 4781, 4801, 4828 | |
| stage_trigger_run | insert 4848 | |
| pay_run | 4869, 4892, 4925 | |
| pay_run_line | 4948, 4971, 5004 | |
| bank_statement_line | 5027, 5051, 5086 | |
| bank_statement_match | insert 5110, update 5133 | |
| close_task | 5166, 5190, 5225 | |
| close_task_dependency | 5249, 5264, 5281 | |
| payment_term | 5296, 5315, 5340 | |
| custom_field_def | 5359, 5381, 5412 | |
| custom_field_value | 5434, 5455, 5484 | Old and new `value_text`, `value_number`, `value_cents`, `value_date`, `value_bool` as JSON |
| user_list_pref | 5505, 5523, 5546 | |
| saved_view | 5564, 5583, 5608 | |
| alert_dismissal | 5627, 5644, 5665 | |
| project | 5682, 5707, 5744 | |

**Every audit trigger in the master baseline** (`001_master.sql`): `app_user` 207, 231, 267 (`password_hash` is
never written; the update writes `password_changed` as true or false, `:264`); `user_company_access` 291, 308, 329;
`company_registry` 354, 375, 404; `chain_checkpoint` insert 472; `user_company_role` 586, 604, 627.

### 1.2 Decided (Q1 A) and proposed detail

**The triggers stay as the capture (H4 and HA9 stand; C1 amended).** They are the only thing that also records
writes from the LEGACY screens (`CONNECT_ALLOW_LIST`, `tests/test_static_rules.py:23-30`) and from add-ons (HA9).
Services supply what a trigger cannot know (the reason, the origin, the business action) through `tx.py` only (H4).

`audit_context` (both baselines), new columns:

| Column | Type | Rule |
|--------|------|------|
| `origin` | TEXT | CHECK IN ('Human', 'Agent', 'Import', 'System'), the same list as `journal_entry.origin` (`001_company.sql:463`); set from `context.origin` |
| `event` | TEXT | The service's action code, e.g. `settings.change`, `attachment.remove`, `period.reopen`. The vocabulary is a service registry, not a CHECK, so a new action needs no baseline edit |
| `event_id` | TEXT | One random id per write transaction (UUID text), so the rows of one action group together |
| `reason` | TEXT | CHECK (reason IS NULL OR length(reason) BETWEEN 1 AND 1000) |

`audit_log` (both baselines):
- Add `origin`, `event`, `event_id` (same types). Keep `reason` (already there).
- `logged_at` stays, without `DEFAULT CURRENT_TIMESTAMP`. Every trigger writes `ctx.set_at`, which `AuditStamp`
  already fills from `context.now` (`tx.py:84`). The time is then UTC ISO 8601 with an offset (CLAUDE.md section
  4) and is the same for every row of one action. Rows written with no context set, such as the baseline runner's
  build and seed rows, keep a NULL time; the audit screen shows them as "Setup".
- `action` keeps its CHECK. Insert, Update and Delete remain the row operation; services use `event` for the
  business action.
- Indexes (company; the master gets the same): `(table_name, record_id, log_id)`, `(event_id)`, `(logged_at)`.
- Every core trigger gains `logged_at, origin, event, event_id, reason` in its column list, read from `ctx`.
  `addon_audit_triggers.sql` gets the same.

**Redaction lives in the triggers, from one shared list (owner, Q1).** One reviewed list names every column whose
value never reaches `audit_log` in full. It is one Python constant (proposed: `database.REDACTED_COLUMNS`, which
replaces and extends `_ADDON_HIDDEN_COLUMNS`, `modules/database.py:547-551`). Three things read it:
1. The core triggers, which write what the list says. A schema test parses each trigger and checks it against the
   list.
2. The add-on authorizer, which reads these columns as NULL (as today).
3. The HA11 name rule, which now also runs over every column of every audited core table. A column whose name
   looks secret must be on the list (`omit` or `last 4`) or on a short reviewed allow-list (`mac`, `chain_hash`,
   `fingerprint`, `bank_payee_id` under RP1: integrity values or a payee id, not secrets).

| Column | In the audit log | Today |
|--------|------------------|-------|
| `app_user.password_hash` (master) | omitted; `password_changed` true or false | as listed |
| `bank_account.routing_number`, `account_number` | omitted; `account_last4` kept | as listed |
| `contact.tax_id` | `tax_id_last4` | as listed |
| `contact.exemption_cert_no` | omitted | as listed |
| `company_settings.tax_id` | `tax_id_last4` (Q6 A). The record keeps the full value: the 1099 payer TIN and vendor 1099s read it there | full value: changes |
| `installation_key`, `company_key`, `master_recovery`, `throttle_secret` (master) | not audited (KS9); `auth_event` records changes | as listed |

`reason` is free text, so a person could type a secret into it. It is never written to the log file (the R30
filter applies), and only holders of `audit.view` (sensitive) see it.

**Which actions require a reason.** The service refuses a missing reason with one sentence ("Enter a reason for
this change.", R27 style), and the trigger copies the reason. A CHECK cannot do this, since it cannot see the action
(H4).

| Action | Source | Also kept on the record |
|--------|--------|-------------------------|
| Change a company control (Controls page: approval toggles, `require_separate_approver`, `manual_entry_approval` and its threshold, `allow_manual_control_je`, `lock_documents_after_posting`, approval policies and steps, area and account locks, area 21's policy records) | 11-14; Q15 A | audit_log only |
| Change a user's roles or levels, a job title, an access template, a user's job title, **each per-user override (Q7 A)**, an approval limit | 11-17 item 3; C57 | `user_permission_override.reason`, `user_approval_limit.reason`; audit_log for the rest |
| Remove an attachment | 11-15; C72 | `attachment.removed_reason` |
| Reopen a period or a year | `period.reopen`, `year.reopen` | `period_status_history.reason` (`:432`) |
| Reverse a posted entry | rule 8 | `journal_entry.reversal_reason` (`:457`) |
| Void an invoice, bill, credit memo or payment | persona audit 7 | `invoice.void_reason` (`:626`); payment: area 1 |
| Reject an approval | R16 | `approval_action.reason` (`:1154`) |
| Release an allocation | step 7 | `payment_allocation.release_reason` (`:330`) |
| Set or remove a period lock | area 13 | `fiscal_period_lock.reason` (`:3918`) |
| Restore a company (K5 Master override) | AX2, 2.8 | `backup_run.reason` (section 4) |
| Edit a posted document by reverse-and-repost (rule 8) | rule 8 | the document's version history (area 5) |

Amendment 2026-11-19 (owner, area 12 Q10 A): bank reasons added to this table: exclude a bank feed line, unmatch,
undo a posted feed line, undo a reconciliation (`bank_reconciliation_event.reason`), void a deposit or a transfer
(`void_reason`); a reconciliation set to Reopened by a period reopen carries the reopen's reason
(docs/replan_2.9/area_12_bank_and_reconciliation.md section 7).

Amendment 2026-11-19 (owner, area 10 Q10 A): area 10 reasons added to this table: stop a prepaid schedule and change a
schedule (`deferral.stop_reason`; the change through the audit row), a reclass (`reclass_line.reason`, on every pair),
remove a "Related to" link, and changing the `allow_cross_type_reclass` control
(docs/replan_2.9/area_10_prepaid_deferrals_reclass.md section 7).

Amendment 2026-11-19 (owner, area 8 section 8): area 8 reasons added to this table: put a job on hold or take it off
(`project_hold_history.reason`), reopen a closed job, a Back stage move and a correction
(`project_stage_history.reason`), close a job with open checklist items, cancel a job (the cancel reason list plus a
note), reject or void a change order, a forecast finish that moves later (the delay reason), a forecast change or
budget transfer (`job_forecast_revision.reason`; required only above `forecast_reason_over_cents`, empty by
default), and changing any of the new controls. No table of area 8 is added to the derived or exempt lists: its
history and snapshot tables are insert-only and audited, `pm_prompt` and `calendar_item_notify` are audited
(docs/replan_2.9/area_8_pm_schedules.md section 8).

Amendment 2026-11-19 (owner 11:20 PM, from area 15): area 15 reasons added to this table: a Back lead move ("Moving a
lead back"), marking a lead Lost ("Lost lead"; `lead.lost_reason_id` and `lost_reason_label`), continuing past a lead
stage gate warning ("Continue anyway"), a lead stage correction, blocking a lead (`lead.blocked_reason`), reopening a
case, resolving a case (`service_case.resolution_note`), cancelling an appointment (`activity.cancel_reason`),
removing a comment (`comment.removed_reason`), and changing any area 15 CRM setting (`auto_lost_days`,
`auto_lost_warn_days`, `case_auto_close_days`, `service_job_type_id`). A reason picked from the Reasons list is
stored as `reason_id` with its `reason_label` beside it (docs/replan_2.9/area_15_crm.md section 7.3).

Amendment 2026-11-20 (owner, from area 6): area 6 reasons added to this table: send an estimate back ("Send back";
`estimate_revision_history.reason_id` and `reason_label`), decline a sent estimate ("Lost lead";
`estimate_revision.decision_reason_id` and `decision_reason_label`), abandon an unsent estimate (a note of at least 10
characters in the history row), Mark signed on an expired, unsent or unapproved estimate ("Continue anyway"), cancel a
contract ("Job cancel" plus the date received; `contract.cancel_reason_id` and `cancel_reason_label`), a T&M rate typed
on an estimate ("Rate change"; `estimate_rate_line.change_reason_id`), a contract wording override ("Contract
wording"; `estimate_section_choice.override_reason_id`), and changing an area 6 control or setting
(`allow_estimate_rate_change`, `tm_rate_source`, `company_rate_card_id`, the margin floor and target, the Estimate and
Contract approval policies). A reason from the Reasons list is stored as `reason_id` with its `reason_label`; a note
is needed only with Other (at least 10 characters) (docs/replan_2.9/area_6_estimates_contracts.md section 13).
Corrected 2026-11-20 (owner 12:50 AM, area 6 Q13 B): a short note is required on every rate change and contract-wording change; Other needs at least 10 characters.

Where a record already has its own reason column, the service writes the same text to both in one transaction.

**Rollback guarantee.** An audit row is written by a trigger in the same transaction as the change it records. A
rolled-back change leaves no audit row, and a committed change always has one, even from a writer that forgets (a
legacy screen, an add-on, a raw connection with no context: user NULL, still logged). A refusal is not a change.
Its record is `access_event` (written after the rollback, `tx.py:66-70`) or `auth_event`, both append-only.

**Every business table is audited (owner, Q1).** Each table below without an audit trigger gets insert, update and
delete triggers in the 2.9 pass ("to audit"). Only derived tables are exempt, each with its reason. A schema test
holds both lists: it fails on a table with no audit trigger that is not on the exempt list, and on an exempt-list
table that has disappeared. A new table in any area is audited in the same edit that adds it.

To audit, company file (30 tables):

| Table | Note |
|-------|------|
| `account_type` | seeded reference rows |
| `change_order`, `change_order_line` | |
| `contract`, `contract_line` | |
| `deferral`, `deferral_schedule_line` | |
| `dimension_type`, `dimension_value` | |
| `estimate`, `estimate_line` | |
| `import_batch`, `import_mapping`, `import_source`, `staged_transaction`, `staged_line` | import staging and review |
| `invoice_line`, `invoice_line_dimension` | today an invoice's lines are unaudited |
| `journal_line`, `journal_line_dimension` | Own triggers. The header's `$.lines` only shows the lines at the moment the header changes, so a draft line added later and a reconciliation update are not captured today |
| `period_status_history` | append-only already; its insert is audited for the actor and context |
| `permission` | seeded; changes only with the baseline, still logged |
| `poc_snapshot` | holds a person's estimate to complete, so it is not purely derived |
| `progress_billing_application` | area 4 may replace it |
| `project_budget` | |
| `subscription`, `saas_subscription`, `saas_usage_telemetry` | unless the area that owns them drops them |
| `tax_rate` | |
| `time_entry` | |

`file_attachment` is dropped and replaced by the audited `attachment` (section 3). Master file: every business
table is already audited; `backup_run` (section 4) is audited when added.

Exempt as derived (owner's rule):

| Table | Why |
|-------|-----|
| `customer_number`, `vendor_number` (company) | Counters. Each issued number is the code on an audited `contact` row |
| `entry_number_sequence` (company) | A counter. Each number is on an audited `journal_entry` row |
| `voucher_sequence` (company) | A counter. Each number is on an audited `invoice` row (bill) |
| `login_throttle` (master) | A cache of failed-sign-in counts, derived from the attempts `auth_event` records |

Amendment 2026-11-19 (owner, area 13 F13): `ledger_period_balance` (company) is added to this derived list; it is a
sum of posted `journal_line` rows written only by `ledger.py` (docs/replan_2.9/area_13_close_and_locks.md section 6).

Amendment 2026-11-19 (owner, area 12 Q10 A): `deposit_sequence` (company) is added to this derived list; a counter,
each number is on an audited `deposit` row (docs/replan_2.9/area_12_bank_and_reconciliation.md section 4.3).

Amendment 2026-11-19 (owner, area 10 F13): `dimension_set` and `dimension_set_member` (company) are added to this
derived list; they are the dimension combinations of posted lines, written only by `ledger.py` with
`ledger_period_balance` (docs/replan_2.9/area_10_prepaid_deferrals_reclass.md section 4).

Amendment 2026-11-19 (owner, area 17 Q4 A): `user_list_pref`, `saved_view`, `report_schedule_run` and
`report_delivery` (company) are exempt from audit, as a fourth exempt category named in the same schema test:
display-only per-user preferences (11-15 2:13 PM: UI only, not audit-logged) and report delivery event records.
`user_list_pref` and `saved_view` leave the audited list (section 1.1 rows; their six triggers, 5505-5608, are
dropped in the baseline plan). `company_list_default` stays audited (it is a company setting)
(docs/replan_2.9/area_17_fields_layouts_reports.md sections 2.4 and 11).

Not business tables, and outside the owner's two categories, so they form a third exempt category
(Q24 A; C8 closed), listed by name in the same schema test:
- The audit trail itself: `audit_log`, `audit_context` (both files), `access_event` (company), `auth_event`
  (master).
- Secret-holding tables, by KS9: `installation_key`, `company_key`, `master_recovery`, `throttle_secret` (master).
- The runner's metadata: `schema_version`, `schema_baseline` (made by `modules/database.py:140`, `:343`, not by the
  baselines).

**PostgreSQL (AQ1, H4).** `audit_context` becomes per-transaction settings (`SET LOCAL app.user_id`, `app.reason`
and so on), as H4 plans. The triggers become PL/pgSQL trigger functions. `json_object` becomes
`jsonb_build_object` and `substr(x, -4)` becomes `right(x, 4)`. `REDACTED_COLUMNS` is the one source for both
engines' triggers. Diffing before and after for screens is done in Python, never with `json_extract` in service SQL
(H5). For the hosted port, not now: generate the core triggers from column lists plus `REDACTED_COLUMNS`, as HA9
does for add-ons.

### 1.3 How it lands in the baselines

One pass with the rest of 2.9. In both files:
- four columns on `audit_context` and three on `audit_log`;
- the `logged_at` default removed, and three indexes;
- every existing audit trigger rewritten (about 140 company and 13 master statements, generated, then checked);
- the `company_settings` triggers changed to `tax_id_last4`;
- new triggers for the 30 "to audit" tables.

`addon_audit_triggers.sql` changes too. Every development database is blocked (CLAUDE.md section 5.2) and rebuilt
after asking (rule 9).

### 1.4 Effect on existing services and tests

- `tx.write_transaction(db_path, context, *, reason=None, event=None)`: `AuditStamp.begin` sets the four new
  columns and `end` clears them. No other module touches `audit_context` (H4; `tests/test_static_portability.py:219`).
- Services that already take a reason (ledger reversals, approval rejection, allocation release, period reopen)
  also pass it to `write_transaction`.
- `company_settings.update_setting` (`modules/services/company_settings.py:121`) and `set_document_approval`
  (`:130`) take `reason` and refuse a control change without it.
- `database._ADDON_HIDDEN_COLUMNS` becomes `REDACTED_COLUMNS`. `tests/test_addon_secrets.py` and
  `tests/test_addon_database.py` follow the rename.
- 35 test files read `audit_log`; the old columns keep their meaning. Tests that rely on the database's `logged_at`
  or on the exact JSON of `company_settings` (`test_company_settings.py`, `test_controls_003.py`,
  `test_controls_004.py`) need updating. Tests that count audit rows per action may see more rows once
  `journal_line` and `invoice_line` are audited (`test_ledger_*`).

### 1.5 Tests to write later

- Every audit row written inside `write_transaction` has `logged_at == context.now`, its `origin`, and one
  `event_id` shared by every row of that transaction.
- A control change without a reason is refused and nothing is saved; with a reason, the audit row carries it.
- A rolled-back write leaves no audit row; a committed one always has one, including from a raw connection with no
  context.
- `audit_context` is cleared after commit and after rollback (reason and event included).
- `audit_log` still refuses UPDATE and DELETE, in both files.
- Each trigger matches `REDACTED_COLUMNS`. No `company_settings` audit row holds the full `tax_id`, while the record
  still does. The HA11 name rule passes over every audited core column (allow-list reviewed).
- The to-audit and exempt lists: every company and master table is either audited or on the exempt list.
- A draft journal line added after the header, and a reconciliation update of a posted line, each write an audit
  row.
- Add-on triggers carry the reason and origin like core triggers (HA9).

---

## 2. Access model: roles × levels, job-title templates, per-user overrides

### 2.1 Current state

- Master: `app_user.role` (legacy free text, `001_master.sql:77`, read only by the sidebar), `app_user.job_title`
  (`:78`, free text, NOT NULL DEFAULT ''). `user_company_access(user_id, company_id, role_code, access_mode Grant
  or Deny)` (`:47-56`) is the gate (MR2). `user_company_role(user_id, company_id, role_code, granted_by,
  granted_at)` (`:577-584`) is audited (`:586`, `:604`, `:627`) and has no reason.
- Company: `permission(permission_code, module, description, is_sensitive)` (`001_company.sql:1056`), 77 codes
  seeded; `role(role_code, name, is_system, is_active, project_scope All or Assigned, created_at)` (`:1063`);
  `role_permission` (`:1072`); `approval_limit(role_code, document_type, max_amount_cents)` (`:1078`);
  `user_project_scope(user_id, project_id)` (`:1085`). Only `Admin` is seeded, with every permission
  (`:1256-1260`). Its `created_at` uses `strftime('now')`, which the PostgreSQL port must replace.
- Built starter roles (`modules/services/role_templates.py`, from docs/role_templates.md, S6): Controller,
  Accountant, AP Clerk, AR Clerk, General Manager, Project Manager, Warehouse, Foreman, Payroll, Sales, Viewer.
  The first four and Payroll, Sales and Viewer are in every company; the other four are construction-only. These
  differ from C57's list of 11 (C9).
- Rules in force: MR2 (the union of active roles; Admin allows all), MR3 (project scope), MR4 (approval limit: the
  highest), MR5 (one chain slot per person), MR8 (role changes name the rows they remove; `confirm_removal`). The
  last-Admin check is `users.py:311-330`; the Admin guards are `users.py:278`.
- Agent: `permissions.AGENT_ALLOWED` (`modules/services/permissions.py:113`) holds only non-sensitive view and
  report codes. `authz.authorize` denies anything else for `origin == 'Agent'` before any read
  (`modules/services/authz.py:132`).
- Contacts (next_step.md input 3): `contacts._either_permission` (`modules/services/contacts.py:69-80`) authorizes
  `customer.manage` if held, else `vendor.manage`, for `update_contact` (`:199`), `deactivate_contact` (`:216`) and
  `find_duplicates` (`:148`), whatever kind the contact is.

### 2.2 Decided model (owner 2026-11-18)

- **Roles (Q3 A):** the system roles are Admin, Accountant, Sales rep and Operations, all `is_system = 1`. The
  Master is `app_user.is_master`, not a role row. Companies do not create roles; access templates cover the
  variety. `company.roles.manage` becomes "Edit role levels, access templates, job titles and approval limits",
  held by Admin only (11-17, 8:31 PM).
- **Several roles per user (Q2 B):** MR2 and MR8 as built. Each of a user's `user_company_role` rows carries its
  own level. The **effective cap is the union of the caps of the user's active roles** (C5 closed).
- **Levels:** View only, Standard and Manager on Accountant, Sales rep and Operations. Admin has no level. Each
  level includes the ones below it.
- **Cap (Q4 A):** each role has its own cap list, wider than its Manager defaults, so a template can add codes the
  level does not give.
- **Job title (Q5 A):** one per user per company, each pointing to one access template.
- **Overrides (Q7 A):** Add and Remove; Remove wins over every source. **Each override needs a reason**, stored on
  the row and in the audit log.
- **Approval limits (Q8 A):** level defaults, template limits and user limits. The highest of those that come with
  the approve permission applies, with no cap on the amount (MR4 generalised).
- **Sensitive codes (Q9 A):** no level default holds a sensitive code, approve codes included. They come only from
  templates or named Add overrides, with a reason. K13 holds: `ledger.verify` comes from the Controller template,
  not the Accountant level.
- **Separation of duties (Q10 A):** a warning only, when a template or override leaves one person able to create
  and approve the same document type. `require_separate_approver` (R17), MR5 and the triggers at
  `001_company.sql:3702-3714` are unchanged; they remain controls, OFF by default.
- **Contacts (Q11 A):** authorize by the contact's side. Customer-only needs `customer.manage`, vendor-only needs
  `vendor.manage`, both sides or neither takes either. The service reads the flags first, in its own read
  connection (MR6), then authorizes. A holder of one right gets the same sentence, error and denial row for a
  missing contact and for one on the other side (MR9). `find_duplicates` returns only contacts on a side the caller
  can manage, and custom field values on contacts follow the same rule. No schema change.
- **Sessions (Q17 A):** `app_user.session_epoch`.

**Effective access (the authz rule that replaces MR2's union; for the decision log, not built):**
1. Gate as MR2: the access row decides, and Deny wins. The Master allows all, and Admin in any role allows all.
2. For each active role row: that role's level defaults (cumulative).
3. Add the job title's template and the Add overrides; subtract the Remove overrides.
4. Intersect with the union of the user's role caps. Under Q19 A, a role held at View only contributes only read
   codes to that union.
5. Apply `AGENT_ALLOWED` for Agent origin.

Inactive roles, titles and templates are skipped, with the inactive-role denial as today. Denials keep R27 and
`authz.DENIAL_REASONS`; a capped code is simply not held (`ROLE`). MR3 per code: a code is limited to assigned
projects only when every source that grants it (level row or template) has `project_scope = 'Assigned'`.

**The Agent.** It has no role, level, title or override. `AGENT_ALLOWED` is its only source, applied last. No
sensitive code is agent-allowed (`permissions.py:114-115`). Person pickers never list it. Agent-origin entries keep
their human approval (integrity, section 0).

**Person pickers (11-17 item 4).** These are service reads by permission code, not stored. Existing codes cover
`can_manage_jobs` (`project.manage`), `can_build_estimates` (`estimate.create`), `can_approve:<doc>:<limit>` (the
approve codes with the effective limit) and `can_receive_deliveries` (`receiving.jobsite`, `receiving.stock`).
Proposed new codes, to be confirmed in areas 8 and 15 and not seeded here: `lead.own`, `field.schedule`,
`case.work`.

### 2.3 Proposed schema

**Master**
- `user_company_role` gains `level TEXT CHECK (level IS NULL OR level IN ('View only', 'Standard', 'Manager'))`.
  The key stays `(user_id, company_id, role_code)` (Q2 B). "Admin has no level; the other roles have one" is a
  service rule, because role codes are company data the master cannot check.
- `user_company_access.role_code` stays only as MR2's fallback until Phase 3 removes it with `app_user.role`.
- `app_user.deactivated_at TEXT` and `deactivated_by INTEGER`: CHECK both set or both NULL, and set only while
  `is_active = 0` (C57 "Deactivated 11/14/2026 by mark").
- `app_user.temp_password_expires_at TEXT` (72 hours, C57).
- `app_user.session_epoch INTEGER NOT NULL DEFAULT 0` (Q17 A). Reset password and Sign out everywhere add 1, and a
  session started under an older epoch is signed out at its next request.
- The idle-lock minutes are a company setting in area 21's policy records.

**Company**
- `role`: seeded rows `Admin`, `Accountant`, `Sales rep`, `Operations`, all `is_system = 1`. A trigger refuses
  INSERT and DELETE of any other role (Q3 A; integrity of the fixed list). `role.project_scope` is dropped and
  moves to `role_level`. `role_permission` is kept only for Admin's "every code" rows, or dropped in favour of the
  Admin rule in authz (Q23).
- `role_level(role_code, level, project_scope)`: PK `(role_code, level)`, FK role, level CHECK as above,
  `project_scope` CHECK ('All', 'Assigned') DEFAULT 'All'. Nine seeded rows.
- `role_level_permission(role_code, level, permission_code)`: PK all three, FKs. These are the level defaults
  (table 2.4.2). A trigger refuses a sensitive code (Q9 A; backstop for the service rule).
- `role_cap_permission(role_code, permission_code)`: PK both, FKs (table 2.4.1). A trigger refuses a
  `role_level_permission` row whose code is not in the role's cap.
- `access_template(template_id PK, name TEXT NOT NULL UNIQUE, description, project_scope CHECK ('All', 'Assigned')
  NOT NULL DEFAULT 'All', is_shipped 0/1 NOT NULL, is_hidden 0/1 NOT NULL DEFAULT 0, created_at, created_by)`.
  Triggers refuse DELETE of a shipped template, and of a template a `job_title` still uses (FK, no cascade).
- `access_template_role(template_id, role_code)`: PK both. The roles a template is meant for, used by the screen to
  offer it and to warn when the user lacks one. It is not enforced beyond the cap.
- `access_template_permission(template_id, permission_code)`: PK both, FKs (table 2.4.3).
- `job_title(job_title_id PK, name TEXT NOT NULL UNIQUE, template_id NOT NULL REFERENCES access_template, is_active
  0/1, created_at, created_by)`. Master `app_user.job_title` stays a display label.
- `user_job_title(user_id PK, job_title_id NOT NULL REFERENCES job_title, assigned_by, assigned_at)`: one title per
  user per company (Q5 A).
- `user_permission_override(user_id, permission_code, effect CHECK IN ('Add', 'Remove'), reason TEXT NOT NULL CHECK
  (length(trim(reason)) > 0), granted_by INTEGER NOT NULL, granted_at TEXT NOT NULL)`: PK `(user_id,
  permission_code)` (Q7 A).
- `approval_limit` re-keyed `(role_code, level, document_type)`, plus `access_template_approval_limit(template_id,
  document_type, max_amount_cents)` and `user_approval_limit(user_id, document_type, max_amount_cents, reason NOT
  NULL, granted_by, granted_at)`. Q8 A. No limits are seeded: the Controls page asks for them when approvals are
  turned on, as today.
- `permission` gains `is_read INTEGER NOT NULL CHECK (is_read IN (0, 1))`, used for View only (Q19). Read codes:
  every `*.view`, plus `report.financial` and `report.job_cost`.
- Every new table gets audit triggers (section 1), and every write to them carries a reason.
- Indexes, for the person pickers: `user_permission_override(permission_code)`,
  `access_template_permission(permission_code)`, `role_level_permission(permission_code)`,
  `user_job_title(job_title_id)`.

Amendment 2026-11-19 (owner 11:40 PM, from area 15): Q18: `role_level` and `access_template` each gain `lead_scope`
TEXT NOT NULL CHECK (`lead_scope` IN ('All', 'Own')) DEFAULT 'All', beside `project_scope`. Own limits `lead.view` to
leads where the user is the sales rep, Unassigned leads, and leads the user takes part in. It resolves like MR3:
`lead.view` is limited to Own only when every source that grants it (level row or template) has `lead_scope =
'Own'`. Every seeded level row and shipped template keeps the default All. There is no `lead.view_all` code
(docs/replan_2.9/area_15_crm.md section 7.2).

Amendment 2026-11-20 (owner 11-14 1:30 PM, decision audit; answered 1:50 AM): deactivating a user returns their open
work in each company they can open: leads where they are sales rep, estimate revisions they hold, open cases and
activities they own, jobs where they are PM, and items waiting on their approval. It offers to reassign each item
through its owning service, with a reason, and logs it. Open work never blocks deactivation (rule 0), and the list
stays available afterwards so items can be reassigned later.

### 2.4 Seed tables (O1)

Checked by a scratch script, not project code:
- all 77 seeded codes are placed: either Admin-only or in at least one cap;
- each level's cumulative defaults sit inside its role's cap and hold no sensitive code;
- View only holds read codes only;
- each template sits inside the union of the caps of its roles.

The scratch check becomes a real test when this is built (2.6).

**Admin only (in no cap; Admin and the Master hold them):** `company.settings`, `company.users.manage`,
`company.roles.manage`, `company.create`, `company.restore` (sensitive), `addon.manage` (sensitive),
`fields.manage` (sensitive; STOP C), `ai.settings`.

#### 2.4.1 Caps (`role_cap_permission`)

| Role | Codes | Cap |
|------|-------|-----|
| Accountant | 59 | `company.backup`, `period.view`, `period.close`, `period.reopen`, `year.reopen`, `ledger.view`, `je.create`, `je.post`, `je.approve`, `je.reverse`, `account.manage`, `ar.view`, `customer.manage`, `invoice.create`, `invoice.send`, `invoice.void`, `payment.receive`, `credit_memo.create`, `ap.view`, `vendor.manage`, `bill.create`, `bill.approve`, `bill.override_match`, `bill.void`, `payment.make`, `payment.approve`, `payment.release_hold`, `po.view`, `po.create`, `po.approve`, `receiving.stock`, `inventory.view`, `inventory.count`, `inventory.adjust`, `project.view`, `payapp.create`, `payapp.approve`, `retainage.release`, `asset.view`, `asset.create`, `asset.dispose`, `asset.approve`, `depreciation.run`, `loan.view`, `loan.manage`, `time.enter`, `time.approve`, `payroll.view`, `payroll.import`, `import.run`, `import.approve`, `view.tax_ids`, `view.bank_details`, `report.financial`, `report.job_cost`, `report.export`, `ai.use`, `audit.view`, `ledger.verify` |
| Sales rep | 14 | `project.view`, `project.create`, `project.manage`, `estimate.create`, `estimate.approve`, `change_order.create`, `change_order.approve`, `contract.approve`, `ar.view`, `customer.manage`, `invoice.create`, `report.job_cost`, `report.export`, `ai.use` |
| Operations | 30 | `project.view`, `project.create`, `project.manage`, `estimate.create`, `estimate.approve`, `change_order.create`, `change_order.approve`, `contract.approve`, `po.view`, `po.create`, `po.approve`, `subcontract.approve`, `receiving.stock`, `receiving.jobsite`, `inventory.view`, `inventory.pull`, `inventory.count`, `inventory.adjust`, `payapp.create`, `payapp.approve`, `retainage.release`, `ap.view`, `bill.create`, `bill.approve`, `asset.view`, `time.enter`, `time.approve`, `report.job_cost`, `report.export`, `ai.use` |

In short: Accountant covers the books, money, payroll, sensitive data and audit. Sales rep covers leads, estimates,
contracts and customers. Operations covers jobs, purchasing, inventory, pay apps and time. Bank and tax details, the
ledger, payroll and audit are never reachable from Sales rep or Operations.

#### 2.4.2 Level defaults (`role_level_permission`, cumulative; no sensitive code)

| Role | Level | Adds | Scope |
|------|-------|------|-------|
| Accountant | View only | `period.view`, `ledger.view`, `ar.view`, `ap.view`, `po.view`, `inventory.view`, `project.view`, `asset.view`, `loan.view`, `report.financial`, `report.job_cost` | All |
| Accountant | Standard | `je.create`, `ai.use` | All |
| Accountant | Manager | `je.post`, `je.reverse`, `period.close`, `invoice.void`, `bill.void`, `account.manage`, `company.backup`, `report.export` | All |
| Sales rep | View only | `project.view`, `ar.view` | All |
| Sales rep | Standard | `project.create`, `estimate.create`, `customer.manage`, `ai.use` | All |
| Sales rep | Manager | `project.manage`, `change_order.create`, `invoice.create`, `report.job_cost`, `report.export` | All |
| Operations | View only | `project.view`, `po.view`, `inventory.view`, `asset.view` | All |
| Operations | Standard | `time.enter`, `report.job_cost`, `ai.use` | All |
| Operations | Manager | `project.manage`, `po.create`, `change_order.create`, `inventory.adjust`, `ap.view`, `report.export` | All |

The level defaults are kept small on purpose. A template adds the area work, so AP clerk and AR clerk on the same
Accountant · Standard level stay different.

Amendment 2026-11-19 (owner, area 12 Q10 A): three new codes, module Banking: `bank.feed` and `bank.reconcile` (not
sensitive) and `bank.unreconcile` (sensitive). All three go in the Accountant cap (2.4.1, 59 to 62 codes). Level
defaults (2.4.2), revised 2026-11-19 by the owner: Accountant · Standard adds both `bank.feed` and `bank.reconcile`
(Manager inherits them); `bank.unreconcile` is in no level (sensitive). Shipped templates (2.4.3), revised 2026-11-19
by the owner: the Controller template adds `bank.unreconcile` to its sensitive codes; Admin and the Master keep it;
anyone else only by that template or an Add override with a reason. None in AGENT_ALLOWED
(docs/replan_2.9/area_12_bank_and_reconciliation.md section 3.5).

Amendment 2026-11-19 (owner, area 10 Q10 A): two new codes, module Ledger, both not sensitive: `deferral.manage` and
`je.reclass`, in the Accountant cap (2.4.1, 62 to 64 codes with area 12's three). Level defaults (2.4.2): Accountant ·
Standard adds `deferral.manage`; `je.reclass` goes at the level that holds `je.post`, Accountant · Manager. Shipped
templates (2.4.3), revised 2026-11-19 by the owner: `je.reclass` follows `je.post`, so Controller and Staff accountant
(the only templates naming `je.post`) add `je.reclass` in their non-sensitive column. Neither code in AGENT_ALLOWED.
Placement check re-run in words: every code still placed; the levels stay inside the cap with no sensitive code; View
only unchanged; every template inside its roles' caps
(docs/replan_2.9/area_10_prepaid_deferrals_reclass.md section 7.1).

Amendment 2026-11-19 (owner, area 17 Q21 A, Q23 A, Q24 A): four new codes, module Reports, none sensitive: `money.view`,
`report.records`, `report.design` and `report.schedule`. Caps (2.4.1): the Accountant cap gains all four (64 to 68 codes
with areas 12 and 10); the Sales rep cap gains `money.view`, `report.records` and `report.design` (14 to 17); the
Operations cap gains the same three (30 to 33). Level defaults (2.4.2, cumulative): `money.view` at Accountant · View
only, Sales rep · Manager and Operations · Standard; `report.records` at Accountant · Standard, Sales rep · Standard and
Operations · Standard; `report.design` at Accountant · Manager, Sales rep · Manager and Operations · Manager;
`report.schedule` at Accountant · Manager. Shipped templates (2.4.3): Sales manager, Project manager and Estimator add
`money.view` in their non-sensitive column (the two union templates inherit it); Controller adds `report.schedule`.
`AGENT_ALLOWED` adds `money.view` and `report.records` only. Placement check re-run in words: every new code is in the
Accountant cap, so every code is still placed (86 seeded codes with areas 12, 10 and 17); every level default stays
inside its role's cap and holds no sensitive code; View only holds read codes only (`money.view` is one); every
template sits inside the union of its roles' caps; the Accountant templates already hold `money.view` through
Accountant · View only, and the three templates that name `report.job_cost` now hold it
(docs/replan_2.9/area_17_fields_layouts_reports.md section 10.3).

Amendment 2026-11-19 (owner, area 8 section 8; forecast codes owner 2:20 PM and planning 3:10 PM): six new codes.
`job.forecast.edit` and `job.budget.transfer` (module Projects / CRM, not sensitive); `job.schedule.edit` and
`schedule.template.manage` (Projects / CRM, not sensitive); `service_type.manage` (Projects / CRM, not sensitive, Admin
only: in no cap, like `company.settings`); `job.stage.backdate` (Projects / CRM, sensitive). Caps (2.4.1): the
Accountant cap gains `job.forecast.edit`, `job.budget.transfer` and `job.stage.backdate` (68 to 71 codes with areas
12, 10 and 17); the Operations cap gains `job.forecast.edit`, `job.budget.transfer`, `job.schedule.edit` and
`schedule.template.manage` (33 to 37); the Sales rep cap is unchanged (17), so a Sales rep can hold none of them.
Level defaults (2.4.2): unchanged; none of the six is in any level, and View only gains nothing. Shipped templates
(2.4.3): the Project manager template adds `job.forecast.edit`, `job.budget.transfer`, `job.schedule.edit` and
`schedule.template.manage` in its non-sensitive column (the Project manager + Estimator and Sales rep + Project manager
union templates inherit them); the Controller template adds `job.forecast.edit` and `job.budget.transfer` in its
non-sensitive column and `job.stage.backdate` in its sensitive column; Admin and the Master hold all six. The Sales
manager, Sales rep, Estimator, Superintendent, Warehouse lead and View only templates, and the Viewer, get none.
None of the six is in `AGENT_ALLOWED`. Placement check re-run in words: every new code is placed (five in a cap, the
sixth Admin-only), so all 92 seeded codes are placed (86 with areas 12, 10 and 17); every level default is unchanged
and so still inside its role's cap with no sensitive code; View only still holds read codes only; every template sits
inside the union of its roles' caps (the Controller template's three new codes are in the Accountant cap; the Project
manager template's four in the Operations cap; the two union templates inside the union of their roles' caps);
`job.stage.backdate` is sensitive and is in no level and no template but the Controller's
(docs/replan_2.9/area_8_pm_schedules.md section 8).

Amendment 2026-11-19 (owner 11:40 PM, from area 15): Q19 A with Q18: ten new codes, module Projects / CRM, none
sensitive: `lead.view`, `lead.create`, `lead.edit`, `lead.own`, `lead.assign`, `activity.log_for_others`,
`crm.settings`, `case.view`, `case.create`, `case.work`. No `lead.view_all`. `project.create` keeps its code with the
description "Create jobs". Caps (2.4.1): the Sales rep cap gains all ten (17 to 27 codes); the Operations cap gains
`lead.view`, `activity.log_for_others`, `case.view`, `case.create` and `case.work` (37 to 42); the Accountant cap gains
`lead.view`, `case.view`, `case.create` and `case.work` (71 to 75). Level defaults (2.4.2, cumulative): Sales rep ·
View only adds `lead.view` and `case.view`; Sales rep · Standard adds `lead.create`, `lead.edit`, `lead.own` and
`case.create`; Sales rep · Manager adds `lead.assign`, `activity.log_for_others` and `crm.settings`; Operations · View
only adds `case.view`; Operations · Standard adds `case.create` and `case.work`; Operations · Manager adds
`activity.log_for_others`; Accountant · View only adds `case.view`; Accountant · Standard adds `case.create` and
`case.work`. Operations and Accountant get `lead.view` only through a template or an Add override (their caps allow
it, their levels do not give it). Shipped templates (2.4.3): unchanged (area 15 section 7.3 places none). Admin and
the Master hold all ten. `AGENT_ALLOWED` adds `lead.view` and `case.view` only. Placement check re-run in words: every
new code is in the Sales rep cap, so all 102 seeded codes are placed (92 with areas 12, 10, 17 and 8); every level
default sits inside its role's cap and holds no sensitive code; View only gains only `lead.view` and `case.view`,
both read codes; every template is unchanged and so still inside its roles' caps
(docs/replan_2.9/area_15_crm.md section 7.3).

Amendment 2026-11-20 (owner, from area 6 Q19 A): five new codes, module Projects / CRM: `estimate.view` (the read
code STOP C found missing), `estimate.send` (send, decline and revise an estimate) and `sales.templates.manage`
(pricing templates, cost templates, contract templates and clauses, rate cards, branding), none sensitive; and
`contract.sign` (Mark signed: creates the customer, job, budget and contract) and `contract.cancel`, both sensitive.
102 seeded codes become 107 (102 + 5). The existing `estimate.create`, `estimate.approve` and `contract.approve` keep
their codes and meaning. Caps (2.4.1): the Sales rep cap gains all five (27 to 32 codes); the Operations cap gains
`estimate.view` (42 to 43); the Accountant cap gains `estimate.view` (75 to 76). Level defaults (2.4.2, cumulative):
Sales rep · View only adds `estimate.view`; Sales rep · Standard adds `estimate.send`; Sales rep · Manager adds
`sales.templates.manage`; Operations · View only adds `estimate.view`; Accountant · View only adds `estimate.view`.
`contract.sign` and `contract.cancel` are in no level (sensitive). Shipped templates (2.4.3): the Sales manager
template adds `estimate.view`, `estimate.send` and `sales.templates.manage` in its non-sensitive column and
`contract.sign` and `contract.cancel` in its sensitive column; the Sales rep template adds `estimate.view` and
`estimate.send` in its non-sensitive column and `contract.sign` in its sensitive column (it had none); the Project
manager, Estimator and Controller templates add `estimate.view` (the two union templates inherit it). Admin and the
Master hold all five. `AGENT_ALLOWED` adds `estimate.view` only. Placement check re-run in words: every new code is in
the Sales rep cap, so all 107 seeded codes are placed (102 with areas 12, 10, 17, 8 and 15); every level default sits
inside its role's cap and holds no sensitive code; View only gains only `estimate.view`, a read code; every template
sits inside the union of its roles' caps (the Sales rep and Sales manager additions in the Sales rep cap, the Project
manager and Estimator ones in the Operations cap, the Controller's in the Accountant cap)
(docs/replan_2.9/area_6_estimates_contracts.md section 12).

Amendment 2026-11-20 (owner 2:25 AM, from area 7 Q9 A and Q14): four new codes, none sensitive, none in
`AGENT_ALLOWED`: `job.budget.enter` (module Projects / CRM: the "Budget code" choice of `job_budget_entry`),
`cost_code.manage` (cost codes and cost types) and `dimension.manage` (dimension types and values; not
`required_mode`, which is `company.settings`), both in a new module Lists (area 7 section 9.2), and `plan.manage`
(module Reports: operating plan versions, imports and grid). 107 seeded codes become 111 (107 + 4). Caps (2.4.1): the
Accountant cap gains all four (76 to 80 codes); the Operations cap gains `job.budget.enter` and `cost_code.manage`
(43 to 45); the Sales rep cap is unchanged (32). Level defaults (2.4.2, cumulative): Accountant · Manager adds
`job.budget.enter` and `plan.manage`; `cost_code.manage` and `dimension.manage` are in no level (Q14). Shipped
templates (2.4.3): the Controller template adds all four in its non-sensitive column; the Project manager template
adds `job.budget.enter` (the Project manager + Estimator and Sales rep + Project manager union templates inherit it).
Admin and the Master hold all four. Anyone else gets `cost_code.manage` or `dimension.manage` only by a custom
template or a per-user Add with a reason, inside their role caps. Placement check re-run in words: every new code is
in the Accountant cap, so all 111 seeded codes are placed (107 with areas 12, 10, 17, 8, 15 and 6); every level
default sits inside its role's cap and holds no sensitive code; View only gains nothing; every template sits inside
the union of its roles' caps (the Controller's four in the Accountant cap, the Project manager's `job.budget.enter`
in the Operations cap) (docs/replan_2.9/area_7_jobs_budgets_cost_codes.md section 9.2).

Amendment 2026-11-20 (owner 3:15 AM, from area 7; replaces the 2:45 AM sources): every service job starts from a signed
quote, so the people who sign quotes need Sign contracts. `contract.sign` stays sensitive and in no level. It is
already in the shipped Sales manager and Sales rep templates' sensitive columns (area 6 amendment above), and is also
in a new shipped **Service manager** template (2.4.3). Proposed for the owner: role Sales rep; scope Assigned;
non-sensitive codes `case.view`, `case.create`, `case.work`, `estimate.view`, `estimate.create`, `estimate.send`,
`project.view`; sensitive code `contract.sign`. Every code is in the Sales rep cap (2.4.1 with the area 15 and area 6
amendments), so the template sits inside its role's cap. An Operations user gets it only with a Sales rep role as
well, because `estimate.send` and `contract.sign` are not in the Operations cap. No new code: the seeded count stays
111; shipped templates gain one. `AGENT_ALLOWED` is unchanged. The 2:45 AM `service_quote_limit_cents` setting and its
high-impact mark are withdrawn (section 4.2).

Amendment 2026-11-20 (owner 3:35 AM, from area 7): the Service manager template is wider than the 3:15 AM proposal.
For roles Sales rep and Operations (a union template, like Sales rep + Project manager, Q18); scope All. Non-sensitive
codes: the proposed `case.view`, `case.create`, `case.work`, `estimate.view`, `estimate.create`, `estimate.send`,
`project.view`; the owner's `project.manage`, `job.schedule.edit`, `job.forecast.edit`, `change_order.create`,
`invoice.create`, `report.job_cost`, `money.view`; and, to run and bill a service job, `customer.manage` (keep the
case customer's billing and site details current), `ar.view` (see what the job has billed and been paid), `po.view`
and `po.create` (order parts for the job), `receiving.jobsite` (receive parts delivered to the site),
`inventory.pull` (take parts from stock for the job) and `time.enter` (record the crew's hours on T&M service work).
Sensitive code: `contract.sign`. Every code sits inside the union of the Sales rep and Operations caps (2.4.1 with
the areas 17, 8, 15, 6 and 7 amendments). Not added, for the owner: `invoice.send` and `payment.receive` are in the
Accountant cap only, and no cap was widened; with this template a Service manager creates the invoice and someone
holding those codes sends it and records the payment. No new code: the seeded count stays 111. `AGENT_ALLOWED` is
unchanged.

Amendment 2026-11-20 (owner 3:38 AM, from area 7): `invoice.send` is added to the Operations cap and to the Service
manager template; `payment.receive` stays in the Accountant cap only. Caps (2.4.1): the Operations cap goes from 45
to 46 codes (with areas 17, 8, 15, 6 and 7); the Accountant (80) and Sales rep (32) caps are unchanged. Level
defaults (2.4.2): no level gets `invoice.send` by default. Shipped templates (2.4.3): the Service manager row adds
`invoice.send` in its non-sensitive column (22 codes plus `contract.sign`). The seeded code count is unchanged (111).
Placement check re-run in words: every level default is unchanged; every template sits inside the union of its roles'
caps (the Service manager's `invoice.send` in the Operations cap).

#### 2.4.3 Shipped access templates (`access_template`, `is_shipped = 1`; spec section 6)

| Template | For role(s) | Scope | Built from | Codes (non-sensitive) | Sensitive codes |
|----------|-------------|-------|------------|-----------------------|-----------------|
| Controller | Accountant (spec 2: also the title of an Admin) | All | built Controller | `company.backup`, `period.close`, `je.create`, `je.post`, `je.reverse`, `account.manage`, `customer.manage`, `invoice.create`, `invoice.send`, `invoice.void`, `payment.receive`, `credit_memo.create`, `vendor.manage`, `bill.create`, `bill.void`, `payment.make`, `po.create`, `receiving.stock`, `payapp.create`, `retainage.release`, `asset.create`, `asset.dispose`, `depreciation.run`, `loan.manage`, `import.run`, `report.export` | `period.reopen`, `year.reopen`, `je.approve`, `bill.approve`, `bill.override_match`, `payment.approve`, `payment.release_hold`, `po.approve`, `payapp.approve`, `asset.approve`, `import.approve`, `payroll.view`, `view.tax_ids`, `view.bank_details`, `audit.view`, `ledger.verify` |
| Staff accountant | Accountant | All | built Accountant | `period.close`, `je.create`, `je.post`, `je.reverse`, `account.manage`, `customer.manage`, `invoice.create`, `invoice.send`, `payment.receive`, `credit_memo.create`, `vendor.manage`, `bill.create`, `payment.make`, `asset.create`, `depreciation.run`, `import.run`, `report.job_cost` | none |
| AP clerk | Accountant | All | built AP Clerk | `vendor.manage`, `bill.create`, `ap.view`, `po.create`, `po.view` | none |
| AR clerk | Accountant | All | built AR Clerk | `customer.manage`, `invoice.create`, `invoice.send`, `payment.receive`, `credit_memo.create`, `ar.view` | none |
| Payroll | Accountant | All | built Payroll (Q20) | `time.enter`, `import.run`, `period.view`, `ledger.view`, `report.financial` | `time.approve`, `payroll.view`, `payroll.import` |
| Sales manager | Sales rep | All | C57 Sales manager | `project.create`, `project.manage`, `estimate.create`, `change_order.create`, `customer.manage`, `invoice.create`, `report.job_cost` | `estimate.approve`, `contract.approve` |
| Sales rep | Sales rep | All | built Sales | `project.create`, `estimate.create`, `customer.manage`, `invoice.create` | none |
| Project manager | Operations | Assigned | built Project Manager | `ap.view`, `po.view`, `po.create`, `receiving.stock`, `inventory.view`, `project.view`, `estimate.create`, `change_order.create`, `project.manage`, `payapp.create`, `time.enter`, `report.job_cost` | `bill.approve`, `po.approve`, `subcontract.approve`, `change_order.approve`, `time.approve` |
| Estimator | Operations | All | new (C57 Estimator) | `project.view`, `estimate.create`, `change_order.create`, `po.view`, `inventory.view`, `report.job_cost` | none |
| Project manager + Estimator | Operations | Assigned | union of the two | the union of Project manager and Estimator | as Project manager |
| Sales rep + Project manager | Sales rep + Operations (Q18) | Assigned | union of the two | the union of Sales rep and Project manager | as Project manager |
| Service manager (owner 2026-11-20 3:15 AM, 3:35 AM and 3:38 AM) | Sales rep + Operations | All | new | `case.view`, `case.create`, `case.work`, `estimate.view`, `estimate.create`, `estimate.send`, `project.view`, `project.manage`, `job.schedule.edit`, `job.forecast.edit`, `change_order.create`, `invoice.create`, `invoice.send`, `report.job_cost`, `money.view`, `customer.manage`, `ar.view`, `po.view`, `po.create`, `receiving.jobsite`, `inventory.pull`, `time.enter` | `contract.sign` |
| Superintendent | Operations | Assigned | built Foreman | `project.view`, `time.enter`, `receiving.jobsite`, `inventory.pull` | none |
| Warehouse lead | Operations | All | built Warehouse | `po.view`, `inventory.view`, `inventory.pull`, `inventory.count`, `inventory.adjust`, `receiving.stock` | none |
| View only (Accountant), View only (Sales rep), View only (Operations) | that role | All | Viewer | none: a label for a View only user (the level gives the read codes) | none |

What changes against the built starter roles:
- Project manager loses `report.financial`, which is not in the Operations cap.
- Viewer, as Operations · View only, loses `report.job_cost`; as Accountant · View only it keeps both reports.
- Nobody but Admin held `retainage.release` before. It is now in two caps and in the Controller template (Q22 A).
- `payroll.import` is in the Accountant cap and in the new Payroll template (Q20 A).

#### 2.4.4 Old roles mapped to the new model

C57's list of 11 (the owner's UI list; spec section 2):

| Old role | Role · level | Job title (template) |
|----------|--------------|----------------------|
| Admin | Admin | (any; the spec gives Dana "Controller") |
| Controller | Admin, or Accountant · Manager | Controller |
| Accounts payable | Accountant · Standard | AP clerk |
| Accounts receivable | Accountant · Standard | AR clerk |
| Sales manager | Sales rep · Manager | Sales manager |
| Sales rep | Sales rep · Standard | Sales rep |
| Estimator | Operations · Standard | Estimator |
| Project manager | Operations · Standard | Project manager |
| Superintendent | Operations · Standard | Superintendent |
| Warehouse lead | Operations · Standard | Warehouse lead |
| Viewer | each role held · View only | View only (role) or a company name |
| (Sales rep + Project manager, spec 2) | Sales rep · Standard **and** Operations · Standard (Q18) | Sales rep + Project manager |
| (Project manager + Estimator, spec 2) | Operations · Standard | Project manager + Estimator |

The built starter roles (`role_templates.py`), where they differ:

| Built role | Becomes |
|------------|---------|
| Accountant | Accountant · Standard + Staff accountant |
| AP Clerk, AR Clerk | as C57's Accounts payable and Accounts receivable |
| Foreman | Operations · Standard + Superintendent |
| Warehouse | Operations · Standard + Warehouse lead |
| Sales | Sales rep · Standard + Sales rep |
| General Manager | no shipped template (Q21) |
| Payroll | Accountant · Standard + Payroll template (Q20 A) |

Nothing needs migrating before the first release: `role_templates.py` and the seed are rewritten, and development
databases are rebuilt.

### 2.5 How it lands in the baselines

- Master: `user_company_role.level`, and the four `app_user` columns.
- Company: the role seed and its trigger, `role_level`, `role_level_permission`, `role_cap_permission`,
  `access_template` (with `project_scope`), `access_template_role`, `access_template_permission`, `job_title`,
  `user_job_title`, `user_permission_override`, the three approval-limit tables, `permission.is_read`, and drop
  `role.project_scope`.
- The seed rows of 2.4.
- New picker codes only after areas 8 and 15 confirm them.

### 2.6 Effect on existing services and tests

- `authz.authorize`, `authz.is_allowed`, and the MR3 and MR4 helpers follow the effective-access rule above. This
  is the largest change in the area.
- `users.grant_access`, `set_role` and `deny_access` (`users.py:120`, `:145`, `:172`) take a level and a reason.
  MR8 and the last-Admin check (`users.py:311-330`) are unchanged.
- `role_templates.py` is rewritten as the 2.4 seed. `seed_starter_roles` seeds templates, not roles.
- `contacts.update_contact`, `deactivate_contact`, `find_duplicates`, and `custom_fields` on contacts get the side
  check (Q11 A).
- Tests: `test_role_templates.py`, `test_users_access.py`, `test_roles_schema.py`, `test_ledger_approvals.py` (MR4,
  MR5), `test_custom_fields.py`, `test_create_company.py`, and every test that builds a role with `role_permission`
  rows directly need new fixtures.

### 2.7 Tests to write later

- Seed: every one of the 77 codes is Admin-only or in a cap. Levels are cumulative, inside their cap, and free of
  sensitive codes. View only holds only read codes. Every template sits inside the union of its roles' caps, and
  K13 holds (`ledger.verify` only via Controller).
- Effective access: defaults ∪ template ∪ Add, minus Remove, within the union of the user's caps; one test per
  source and per combination; Admin and the Master allow all; Deny wins.
- Two roles: a code in either cap is reachable; a code in neither is not, even through a template.
- An override without a reason is refused. A sensitive Add override writes its reason to the row and the audit
  log.
- No role can be inserted or deleted beyond the four. A shipped template can be hidden but not deleted, and a
  template in use cannot be deleted. Only Admin or the Master manage templates and job titles.
- MR3 and MR4 over levels, templates and user limits; MR5 unchanged across sources.
- The Agent ignores templates and overrides.
- Contacts: a vendor manager cannot edit a customer-only contact and gets the same sentence as for a missing id
  (MR9); a both-sides contact is editable with either right; `find_duplicates` hides the other side.
- Pickers: an inactive user, a user without access, and a capped code are not listed.

---

## 3. Memos and attachments on every form (C72; owner 2026-11-15)

### 3.1 Current state

Memo-like columns that exist (reused, not duplicated):
- `invoice.memo` (`001_company.sql:627`). It covers bills, credit memos and vendor credits, since a bill is an
  invoice with `ledger_side = 'Purchase'`. It is locked on a sent or posted invoice (`:1827`, `:1986`) and audited
  (`:2479`).
- `contact.memo` (`:835`), `contact_site.memo` (`:3905`), `pay_run.memo` (`:3998`), `deferral.memo` (`:921`),
  `journal_line.memo` (`:493`), `staged_line.memo` (`:312`), `contract.notes` (`:892`). The journal entry's memo is
  `journal_entry.description`.
- Missing on existing tables: `payment`, `estimate`, `change_order`, `project`.
- There is no customer-facing "Message on document (prints)" column (C72); that belongs to areas 5 and 6.
- The other C72 forms (purchase order, receipt, pull ticket, item, asset, loan, sub pay app, lead, deposit,
  transfer, refund, write-off) have no tables yet; their areas add them.

Attachments: `file_attachment` (`:74-89`) has `file_id`, `file_name`, `file_path`, `file_size_kb`, `target_type`
CHECK ('Project_Evidence', 'Change_Evidence', 'Invoice_Source'), `target_record_id`, and `uploaded_at DEFAULT
CURRENT_TIMESTAMP`. It has no uploader, content type, checksum or removal fields, no audit trigger and no index.
Nothing uses it (no reference in `modules/`, `tests/` or `scripts/`). `modules/services/storage.py` has no write API
for uploaded files.

### 3.2 Decided and proposed detail

**Memo.**
- One column named `memo`: `memo TEXT CHECK (memo IS NULL OR length(memo) <= 4000)`. Add it to `payment`,
  `estimate`, `change_order` and `project`, and add the CHECK to the existing `memo` columns (`invoice`, `contact`,
  `pay_run`, `deferral`). `contract.notes` stays; area 6 decides.
- Each new header table in areas 1, 4, 9, 11, 12 and 15 gets `memo` with the same CHECK. Customer-facing text is a
  separate column, `document_message` (areas 5 and 6).
- **Never printed (owner 2026-11-18).** The print and email renderer builds from an allow-list of fields per
  document, and `memo` is on none. A test renders every document type with a memo set and checks the text is
  absent.
- The memo follows the record's edit rules: the invoice memo is fixed once sent or posted and changes only through
  rule 8's reverse-and-repost; the JE description is fixed once posted.
- The row's audit trigger records old and new text; the tables still without triggers get them (section 1).

**Attachments: `attachment` replaces `file_attachment`** (dropped; nothing uses it).

| Column | Type and constraint |
|--------|---------------------|
| `attachment_id` | INTEGER PRIMARY KEY |
| `record_type` | TEXT NOT NULL CHECK IN ('Invoice', 'Bill', 'Credit memo', 'Estimate', 'Change order', 'Payment', 'Pay run', 'Journal entry', 'Project', 'Contact', 'Deferral'); each area adds its own forms |
| `record_id` | INTEGER NOT NULL (polymorphic, no FK; the service checks the record exists) |
| `file_name` | TEXT NOT NULL CHECK (length BETWEEN 1 AND 255) |
| `storage_key` | TEXT NOT NULL UNIQUE. A relative key from `storage.py` (H3), never a path: on the desktop under `DATA_DIR/Uploaded_Files/<company_code>/`, in hosted in blob storage |
| `size_bytes` | INTEGER NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 20971520) (20 MB, C72). The allowed types are a company setting (area 21) |
| `content_type` | TEXT NOT NULL |
| `sha256` | TEXT NOT NULL CHECK (64 lowercase hex) |
| `document_kind` | TEXT, NULL except for loans: CHECK IN ('Loan agreement', 'Promissory note', 'Security agreement', 'Amendment or rate change', 'Payoff letter', 'Statement', 'Other') |
| `added_by` | INTEGER NOT NULL |
| `added_at` | TEXT NOT NULL (from `context.now`) |
| `origin` | TEXT NOT NULL DEFAULT 'Human' CHECK (as section 1) |
| `removed_at`, `removed_by`, `removed_reason` | NULL until removed. CHECK all three set or all NULL, and `length(trim(removed_reason)) > 0` |

- Integrity triggers (H4, append-only backstop): DELETE is refused. UPDATE is refused unless it only sets the three
  removal columns, once, from NULL.
- Audit triggers on insert and update record metadata only, never the file's contents.
- Index `(record_type, record_id)`, for the list and the paperclip count.
- **Removed files are kept (Q12 A):** the file stays in storage and the row is marked removed. Holders of
  `audit.view` see "Removed by ... : reason".
- **Adding** is always allowed, also on a posted or locked record (11-15). It changes no accounting and needs the
  record's own create or manage code.
- **Removing (Q13 A plus the owner's rule; corrected 2026-11-21, access audit):** only a user authorized to edit
  the record may remove an attachment, and nonblank text is always required in `removed_reason`. On a posted
  document, removal is refused if its posting period is closed, its document area is locked, or
  `lock_documents_after_posting` is ON. Account-level locks do not apply because removal changes no accounts
  (Area 13 Q6 A). Explain the blocking condition in one sentence, such as "This bill's period is closed, so its
  attachments can't be removed. Reopen the period first."
- The Agent has no attachment reads or writes in v1; Phase 6 decides.

Amendment 2026-11-20 (owner, from area 6): `attachment.record_type` CHECK gains 'Contract' (files added to a signed
contract later). The sent PDF and the signed document of an estimate are 'Estimate' rows (record id the estimate),
linked by FK from `estimate_revision.sent_attachment_id` and `contract.signed_attachment_id`; the signed document is
required for Mark signed. The company logo is not an attachment (`company_branding.logo_storage_key`, through
`storage.py`) (docs/replan_2.9/area_6_estimates_contracts.md sections 7.3 and 12).

Amendment 2026-11-21 (to_planning 2026-11-21 "Area 18 attachment-removal lock wording"; Area 13 Q6 A): the removal
rule above is rewritten in place: a reason is always required; a closed period, a locked document area or
`lock_documents_after_posting` ON refuses removal from a posted document; account locks do not apply.

### 3.3 How it lands in the baselines

Company only:
- `memo` on four tables;
- the length CHECK on four existing `memo` columns;
- `file_attachment` dropped;
- `attachment` with its triggers and index.

The record-type list grows with each area's new tables in the same pass.

### 3.4 Effect on existing services and tests

None today: no service writes `file_attachment` or those `memo` columns. `test_schema_replan.py:370-372` already
expects `invoice.memo`. A later step adds `storage.put_file`, `open_file` and `exists` (H3), and an `attachments`
service that calls the planned `period_locks.check_open` with `period_id` set to the document's posting period,
`area_code` set to its area, and `account_ids=[]`. The service separately checks
`lock_documents_after_posting`; the cited `ledger._open_period` helper (`ledger.py:313-315`) checks period closure
only. Removal requires and preserves nonblank `attachment.removed_reason` text.

Amendment 2026-11-21 (to_planning 2026-11-21 "Area 18 attachment-removal lock wording"; Area 13 Q6 A): the attachments
service calls `period_locks.check_open` with `account_ids=[]` and checks `lock_documents_after_posting` separately, as
rewritten in place above.

### 3.5 Tests to write later

- A `memo` over 4,000 characters is refused (schema) with one sentence (service).
- No printed or emailed document contains its memo (every document type). Static: no `memo` in any print
  template's allow-list.
- `attachment`: DELETE is refused; a change to any column but the removal ones is refused; removal is set once;
  removal without a reason is refused; over 20 MB is refused; a bad `sha256` is refused.
- A posted record accepts a new attachment, and its journal and chain are unchanged.
- Test the three posted-document blockers independently, each with the other two clear: an active document area
  lock refuses removal; a closed posting period refuses it; and `lock_documents_after_posting` ON refuses it.
  A new company has open periods and area locks unset by default; each lock check applies when that lock is set.
  The closed-period integrity check is always enforced. `lock_documents_after_posting` is a configurable control
  and defaults OFF. The reason requirement is always on.
- With only an account lock active and the period open, area unlocked and posted-document control OFF, an
  authorized editor can remove the attachment with a reason; the account lock alone does not block it.
- In a new company with default settings (open period, no area lock, posted-document control OFF), an authorized
  editor can remove an attachment only with nonblank `removed_reason` text; refuse removal without it. A removed
  file is still in storage.
- An attachment on a missing record is refused; a user without the record's right is refused (R27).
- Audit rows carry metadata only. `storage_key` is relative (no drive letter, no `..`; `storage._safe_join`).

Amendment 2026-11-21 (to_planning 2026-11-21 "Area 18 attachment-removal lock wording"; Area 13 Q6 A): the removal
tests above are rewritten in place: each blocker alone, the account-lock-only case, and new-company defaults with the
reason required.

---

## 4. Settings change history and the master backup-run record (E7, AX2, X9)

### 4.1 Current state

- `company_settings` is one row (`001_company.sql:734-787`) holding controls and preferences. Its update trigger
  (`:3587`) writes the whole old and new row as JSON on every change, so before and after exist; a reason does not.
  `document_approval_setting` (`:3718`), `approval_policy` and `approval_step` (`:3402-3506`) and
  `fiscal_period_lock` (`:4509-4556`) are audited the same way. `company_settings.update_setting`
  (`modules/services/company_settings.py:121`) takes no reason.
- Backups: `database.backup_database(db_path, reason=...)` (`modules/database.py:179`) writes
  `Backups/<stem>_<timestamp>_<reason>.db` and `<backup>.sha256`, and returns `{path, sha256}`. `prune_backups`
  (`:234`) applies E7 retention to `addon-<key>` backups; `pre-upgrade` and `pre-restore` are never pruned (AX2).
  `restore_database` (`:275`) checks the checksum. No table records a backup run, and no backup copies the
  attachments folder.

### 4.2 Decided and proposed detail

**Settings history: read from `audit_log`, no second table (Q16 A).** A service read over the settings tables
(`company_settings`, `document_approval_setting`, `approval_policy`, `approval_step`, `fiscal_period_lock`, area
21's policy tables, and the access tables of section 2) diffs `old_value` and `new_value` in Python (H5). It returns
one line per changed setting: setting, before, after, who, when, reason. Labels come from the service registry the
Controls page uses. **A reason is required for controls and optional for preferences (Q15 A).**

**Master `backup_run`.** It lives in the master, so restoring an older company file cannot erase the record of its
own backups (the reasoning of K14).

| Column | Type and constraint |
|--------|---------------------|
| `run_id` | INTEGER PRIMARY KEY |
| `company_id` | INTEGER REFERENCES company_registry, NULL for the master file itself |
| `kind` | TEXT NOT NULL CHECK IN ('Scheduled', 'Manual', 'Pre-upgrade', 'Pre-restore', 'Add-on', 'Year-end', 'Test restore', 'Restore') |
| `reason_code` | TEXT NOT NULL. The AX2 file-name reason (`pre-upgrade`, `addon-<key>`, ...) |
| `started_at` | TEXT NOT NULL |
| `finished_at` | TEXT |
| `result` | TEXT NOT NULL CHECK IN ('Running', 'OK', 'Failed') |
| `file_name` | TEXT. The file name only, relative to the company's `Backups/` folder |
| `sha256` | TEXT CHECK (NULL or 64 hex) |
| `size_bytes` | INTEGER CHECK (NULL or ≥ 0) |
| `includes_attachments` | INTEGER NOT NULL CHECK (0, 1) (Q14, below) |
| `attachment_count` | INTEGER CHECK (NULL or ≥ 0) |
| `is_encrypted` | INTEGER NOT NULL CHECK (0, 1). The backup password is never stored, nor anything derived from it |
| `error_message` | TEXT. A plain sentence only (R35) |
| `requested_by` | INTEGER, NULL for a scheduled run |
| `origin` | TEXT NOT NULL CHECK (as section 1) |
| `source_run_id` | INTEGER REFERENCES backup_run. For a test restore or a restore: the backup used |
| `reason` | TEXT. Required by the service for a restore (K5) |
| `pruned_at`, `pruned_by` | NULL until E7 pruning removes the file; then set once, and the row stays |

- CHECKs:
  - `result = 'OK'` needs `finished_at`, `file_name` and `sha256`; a test restore needs `source_run_id` instead.
  - `result = 'Failed'` needs `error_message`.
  - `kind IN ('Pre-upgrade', 'Pre-restore')` needs `pruned_at IS NULL` (AX2).
  - `kind IN ('Scheduled', 'Manual', 'Year-end')` with `company_id` set and `result = 'OK'` needs
    `includes_attachments = 1` (Q14).
- **Attachments (Q14 A plus the owner's rule):** 2.8 builds the copy, and a company backup without the
  attachments is not complete. The safety copies that only guard a schema or add-on change or a restore
  (`Pre-upgrade`, `Add-on`, `Pre-restore`) copy the database only (AX2), because those changes never touch
  attachment files. Recorded in docs/next_step.md under the 2.8 items.
- Triggers: no DELETE. UPDATE may only move a `Running` row to `OK` or `Failed` once, and set the prune columns
  once (the `installation_key_retire_only` pattern, `001_master.sql:525`). Audit triggers on insert and update.
- Indexes: `(company_id, started_at)`, and `(result)` for the "need attention" item.
- Writer: the 2.8 backup service, around `database.backup_database`. The helper stays a database-layer function
  without master access. Recorded in the master only.

Amendment 2026-11-20 (owner 11-18 2:00 PM, decision audit; answered 1:50 AM): the settings registry marks each
setting, control and policy record as high-impact (who approves, how posting works, what a workflow does) or
low-impact. A high-impact change is saved in two calls. `settings.preview_change(context, key, new_value)` is
read-only and returns scope, affected roles and people, existing and new work with counts and links, and dependencies
and conflicts. `settings.apply_change(context, key, new_value, row_version)` re-runs the preview's checks and writes
the setting and its AX4 audit row in one transaction. A low-impact setting saves in one call and is still logged.
Areas 8 and 15 use the same pair for stages and triggers.

Amendment 2026-11-20 (owner 2:25 AM, from area 7): the settings registry marks `company_settings.job_budget_entry`,
`company_settings.require_budget_before_costs` and each `dimension_type.required_mode` as high-impact (preview and
apply); each change needs `company.settings` and a reason and is audit-logged (area 7 section 9.3).

Amendment 2026-11-20 (owner 2:20 PM, service quote rules): add the configurable System account role
`service_goodwill`, stored as `company_settings.service_goodwill_acct_id` INTEGER NULL REFERENCES account. A company
may map it to the same GL account as `warranty_expense` (for example 5080), but the role remains distinct and area
7's `cost_destination` remains 'Service overhead' rather than 'Warranty line'. Services resolve goodwill costs by
the role, never by an account number; area 17 reports Warranty and goodwill separately by `cost_destination` even
when both roles resolve to the same account.

**Withdrawn 2026-11-20 (owner 3:15 AM)**: the quote limit is dropped, so the setting and its high-impact mark are
withdrawn (section 2.4.2, the 3:15 AM line): Amendment 2026-11-20 (owner 2:45 AM, from area 7): `company_settings.service_quote_limit_cents` (Settings › Service,
area 15) is changed with `company.settings` and a reason and is audit-logged; the registry marks it high-impact,
since it decides which flow billable service work takes. No new permission code: Case warranty and Case T&M jobs use
`case.work` and `project.create` (area 15), the quote uses `estimate.create`, `estimate.send` and `estimate.approve`,
and recording the customer's acceptance uses `contract.sign` (area 6).

Amendment 2026-11-20 (owner 11-19 2:58 PM and planning 3:12 PM, decision audit; answered 1:50 AM): every user's
company open writes an `auth_event` of type 'Company opened' with `company_id` in the master. Today only the Master's
opens are logged, and only inside the company file. The Companies page reads the latest event per company without
opening any file. The Users page reads last sign-in from `auth_event` and "Must change password" from
`app_user.temp_password_expires_at`.

### 4.3 How it lands in the baselines

Master: `backup_run` with its triggers and indexes. Company: section 1 plus
`company_settings.service_goodwill_acct_id` REFERENCES account for the `service_goodwill` System account role. The
2.8 services write the backup table; the System Accounts settings service configures the account mapping.

### 4.4 Effect on existing services and tests

- `company_settings.update_setting` and `set_document_approval` take `reason` (required for controls). Callers:
  Phase 3 screens; tests `test_company_settings.py`, `test_controls_003.py`, `test_controls_004.py`.
- `database.backup_database`, `prune_backups` and `restore_database` are unchanged in 2.9.
  `test_master_schema.py` gains the table.

### 4.5 Tests to write later

- Settings history: one line per changed setting with before, after, who, when and reason; nothing for a no-change
  update; no SQLite JSON functions in service SQL (H5).
- A control change without a reason is refused; a preference change without one is accepted.
- System Accounts offers `service_goodwill`; saving a company-selected account and reading the role returns that
  account. Mapping `service_goodwill` and `warranty_expense` to the same account is allowed, while a Warranty job and
  a goodwill job retain distinct `cost_destination` values and remain separate in area 17's reports. No service
  resolves goodwill by a hard-coded account number.
- `backup_run`:
  - DELETE is refused, and a finished row cannot change.
  - `Running` moves to `OK` or `Failed` only once, and prune is set once.
  - An OK row needs its file, sha256 and finish time; a failed row needs a sentence.
  - `Pre-upgrade` and `Pre-restore` rows cannot be pruned.
  - An OK scheduled, manual or year-end company backup must include attachments.
- `error_message` never holds a path or exception text (R35). No column holds a backup password or a value derived
  from it (the HA11 name rule over master columns).
- Restoring an older company file leaves the master's backup history whole.

---

## 5. Open items (not decisions)

- **O1 closed:** the seed tables are in 2.4; the codes that could not be placed are questions Q20-Q22.
- **O2** C57's matrix rows (Money, Accounting, People, Data, Settings, Field) become level and template rows; the
  Users page groups the codes by module (docs/roles_permissions_design.md section 3). This is for the design chat's
  C57 revision (C4).
- **O3** The persona audit's who-and-when columns (item 2) overlap with section 1; area 21 decides.
- **O4** "Export all data" (persona audit 14): `company.backup` and `report.export` exist; area 21 decides whether
  a new code is needed.
- **O5** Lead assignment rules (11-17 item 5) belong to area 15.
- **O6 closed (2026-11-21, access audit):** the posted document's area lock applies together with period close
  and `lock_documents_after_posting`; account-level locks do not apply to attachment removal. Area 13's
  `next_step.md` input 4 makes the same no-account-lock distinction for custom-field edits.

---

## 6. Conflicts with decisions

- **C1 (amended by Q1 A):** AX4 is built with the audit triggers; H4 and HA9 stand. The task text "written by
  services, not triggers" is superseded. Services supply the reason, origin and action through `tx.py`.
- **C2 E11 vs the baseline (kept):** E11 (`docs/decisions_2026-11-11.md:605`) puts `origin` on `audit_log`; neither
  baseline has it. Section 1 adds it.
- **C3 Timestamp rule vs `logged_at` (kept):** CLAUDE.md section 4 and H2 vs `CURRENT_TIMESTAMP`. Section 1 fixes
  `audit_log`. The other tables (`file_attachment.uploaded_at`, dropped here; `company_registry.created_at`;
  `app_user.created_at`; the Admin role seed's `strftime('now')`) go to area 21.
- **C4 CODE_CHANGES 57 vs the 11-17 access model:** the owner has asked the design chat to revise C57. Until then,
  section 2 follows 11-17.
- **C5 closed by Q2 B:** a user's cap is the union of their roles' caps.
- **C6 K13 wording (kept):** K13 names "Controller (starter template)". Under 11-17 Controller is a job-title
  template (2.4.3, which holds `ledger.verify`), so K13's wording needs a later amendment; the rule itself holds.
- **C7 closed by Q6 A:** the audit log keeps the last 4; the record keeps the full TIN.
- **C8 (new) the owner's exemption rule vs KS9 and the audit tables.** The owner said to exempt only derived or
  cache tables. These tables are neither, and are not business tables:
  - the audit trail itself: `audit_log`, `audit_context`, `access_event`, `auth_event`;
  - the secret-holding tables KS9 keeps unaudited on purpose, so wrapped keys never reach the log:
    `installation_key`, `company_key`, `master_recovery`, `throttle_secret`;
  - the runner's `schema_version` and `schema_baseline`.

  Listed separately in 1.2. **Closed by Q24 A (2026-11-19):** a third exempt category, listed by name in the
  same schema test.
- **C9 (new) spec section 2 vs Q2 B, and the two old-role lists. Closed by Q18 A (2026-11-19):** the user holds
  both roles.
  - Spec section 2 gives Priya one role (Sales rep · Standard) with a template that holds Project manager codes.
    Under the caps, those codes are outside the Sales rep cap, so they work only if she also holds Operations
    (Q18).
  - The "11 old roles" are two different lists: C57's and the built starter roles (`role_templates.py`, S6). 2.4.4
    maps both.

---

## 7. Questions for the owner

Answers recorded 2026-11-18 (Q1-Q17) and 2026-11-19 (Q18-Q24, all A).

**Q1. Who writes audit rows (AX4)?** A. Keep the triggers; services add reason, origin and action through `tx.py`.
B. Services write every row. C. Both.
- **Answer: A.** Redaction rules live in the triggers too, from one shared list with RP1 and HA11. Every business
  table is audited; the tables without a trigger are listed "to audit", and only derived or cache tables are
  exempt, each with a reason, checked by a schema test. C1 amended: H4 and HA9 stand.

**Q2. How many roles may a user hold in one company?** A. One role. B. Several roles.
- **Answer: B.** MR2 and MR8 as built; the effective cap is the union of the user's role caps (C5).

**Q3. Can a company create its own roles?** A. No; templates cover the variety. B. Yes.
- **Answer: A.**

**Q4. What is a role's cap?** A. Its own list, wider than the Manager defaults. B. The Manager defaults.
- **Answer: A.**

**Q5. Job titles per user per company?** A. One. B. Several.
- **Answer: A.**

**Q6. `company_settings.tax_id` in the audit log?** A. Last 4 only. B. In full.
- **Answer: A.** The audit log keeps the last 4. The record keeps the full value (the 1099 payer TIN and vendor
  1099s read it there).

**Q7. Per-user overrides?** A. Add and Remove; Remove wins. B. Add only.
- **Answer: A**, and a reason is required for each override.

**Q8. Approval limits?** A. Level, template and user limits; the highest applies; no cap on the amount. B. A plus a
cap. C. User only.
- **Answer: A.**

**Q9. Sensitive codes and levels?** A. No level default holds a sensitive code; templates or named overrides only,
with a reason. B. Manager levels hold the approve codes.
- **Answer: A.**

**Q10. Separation-of-duties check on templates and overrides?** A. A warning only. B. A new blocking control.
- **Answer: A.**

**Q11. Contacts "either manager" check?** A. By the contact's side, with MR9's same sentence. B. Both-sides contacts
need both rights. C. Keep today's check.
- **Answer: A.**

**Q12. A removed attachment's file?** A. Kept in storage, marked removed. B. Deleted from storage.
- **Answer: A.**

**Q13. Who may remove an attachment?** A. Whoever may edit the record, with a reason. B. Admin or the Master only.
C. A new code.
- **Answer: A**, plus: the reason is always required. For a posted document, Area 13 Q6 A applies verbatim:
  "A. Closed period, `lock_documents_after_posting`, and the document's area lock; account locks do not apply."
  Store the required nonblank text in `attachment.removed_reason`.

Amendment 2026-11-21 (to_planning 2026-11-21 "Area 18 attachment-removal lock wording"; Area 13 Q6 A): the Q13 answer
above is rewritten in place to quote Area 13 Q6 A and require the reason.

**Q14. Attachments and backups?** A. Decide in 2.8. B. Each backup zips the attachments.
- **Answer: A**, plus: 2.8 must include attachments; a backup without them is not complete. Added to
  docs/next_step.md under the 2.8 items.

**Q15. Which settings changes need a reason?** A. Controls only. B. Every change.
- **Answer: A.**

**Q16. Where is settings history stored?** A. Read from `audit_log`. B. A `setting_change` table.
- **Answer: A.**

**Q17. Session invalidation?** A. `app_user.session_epoch`, added now. B. Defer to hosted.
- **Answer: A.**

**Q18. A multi-access template that spans two roles' caps (Sales rep + Project manager)**
- A. **Recommended:** the user holds both roles (Sales rep · Standard and Operations · Standard). With Q2 B this
  keeps each cap narrow, and the template stays inside the union.
- B. Widen the Sales rep cap to hold the Project manager codes, matching spec section 2's single role.
- **Answer: A** (owner 2026-11-19). C9 closed.

**Q19. Does View only limit what a template or override can add?**
- A. **Recommended:** yes. A role held at View only contributes only read codes (`permission.is_read`) to the cap
  union, so a View only user never edits ("Viewer sees no editing actions", persona audit 1).
- B. No. The level sets only the defaults, and a template can add edit rights.
- **Answer: A** (owner 2026-11-19).

**Q20. Payroll (built starter role; `payroll.import` is in no template)**
- A. **Recommended:** add a shipped "Payroll" template for Accountant: `time.enter`, `time.approve`, `import.run`,
  `payroll.view`, `payroll.import`, `period.view`, `ledger.view`, `report.financial`.
- B. No template; Admin grants `payroll.import` by override.
- **Answer: A** (owner 2026-11-19).

**Q21. General Manager (built construction role, not in spec section 6)**
- A. **Recommended:** no template. A general manager is Sales rep · Manager plus Operations · Manager, with the
  Project manager template (scope set to All by the company) or Admin.
- B. Add a shipped "General manager" template spanning Sales rep and Operations: the built role's codes inside
  those caps (its ledger, period and AP views need Accountant · View only as well).
- **Answer: A** (owner 2026-11-19).

**Q22. `retainage.release` (in the Accountant and Operations caps, in no template)**
- A. **Recommended:** add it to the Controller template.
- B. Leave it to Admin or a named override.
- **Answer: A** (owner 2026-11-19).

**Q23. Admin's permissions**
- A. **Recommended:** keep `role_permission` only for Admin's rows ("every code", as seeded today) so authz and the
  seed stay as built.
- B. Drop `role_permission`; authz treats Admin as allow-all (MR2 already does).
- **Answer: A** (owner 2026-11-19).

**Q24. The tables that are neither business nor derived (C8)**
- A. **Recommended:** a third exempt category, "the audit trail itself, KS9 secret tables and runner metadata",
  listed by name in the same schema test.
- B. Audit them too, except the KS9 secret tables (they would log wrapped keys).
- **Answer: A** (owner 2026-11-19). C8 closed.

## 8. Owner decisions, 2026-11-22 (dated amendments)

Source: `Strata_Teams\docs\owner_decisions_2026-11-22.md` items 8–11 (COA-01, COA-02, COA-04; SYSACCT-04 with the
SYSACCT-01/03 branches), plus the permission placements that items 15, 17, 21 and 22 need. This area is approved;
nothing above is rewritten, and conflicts are flagged here.

### 8.1 Chart of accounts and system accounts (Decided 2026-11-22, owner)

- **Amendment 2026-11-22: drawer Save (item 8, COA-01).** One refused field fails the whole Save and nothing
  saves. The account service validates every field before its write transaction and raises one typed error naming
  each refused field. The drawer stays open, names the refused field and keeps the user's other edits typed in.
  Test: `test_account_save_one_refused_field_saves_nothing_and_names_field`.
- **Amendment 2026-11-22: Account Type changes (item 9, COA-02).** QuickBooks-style. Type can change with a warning,
  even after postings. The change is refused for system-role accounts; for accounts whose postings require their
  current type (bank or cash used on checks, deposits or payments, and AR or AP); and where the new type mismatches
  the parent's or a child's. Every change is audit-logged. Company control `lock_account_type_after_posting`
  (`company_settings`, INTEGER 0/1, DEFAULT 0, OFF) locks Type after the first posting; it is listed on the
  Controls page, and each change is audit-logged. Existing code `account.manage`; no new permission. Area 13
  already expects a type change to show as a close-snapshot difference (Area 13 §6 tests). **Conflict flagged:**
  chart-of-accounts decision C3 (docs/decisions_2026-11-11.md section C) says "Type and normal balance locked after
  posting". Item 9 and Q25 (decided 2026-11-22) replace that lock for Type and normal balance; the decisions
  file is not edited here. Tests: `test_account_type_change_after_posting_warns_and_logs`,
  `test_account_type_change_refused_for_system_role_bank_ar_ap_and_parent_mismatch`,
  `test_lock_account_type_after_posting_control_refuses_when_on`.
- **Amendment 2026-11-22: deactivation with a balance (item 10, COA-04).** Allowed with a warning that shows the
  balance. New postings to the inactive account are refused, and it stays on reports until its balance is zero.
  Company control `require_zero_balance_to_deactivate` (`company_settings`, INTEGER 0/1, DEFAULT 0, OFF) requires a
  zero balance first; it is listed on the Controls page and logged. A system-role account stays refused at any
  balance (COA-04 retest). Schema: existing `account.is_active`; report queries include an inactive account while
  its balance is nonzero. Tests: `test_deactivate_account_with_balance_warns_and_blocks_new_postings`,
  `test_inactive_account_with_balance_stays_on_reports_until_zero`,
  `test_require_zero_balance_control_refuses_deactivation_when_on`.
- **Amendment 2026-11-22: system account role reassignment (item 11; SYSACCT-04, SYSACCT-01/03 branches).**
  Prospective only. An Admin (`company.settings`, Admin-only) can reassign a role with a reason, and the change is
  audit-logged through §4 settings history. New postings use the new account. Open items, payments, settlements and
  reversals keep using the original account until settled. Schema effect: every posted document version and open
  item stores the control account it posted to (for example the AR account on an invoice version and the AP
  account on a bill version), and settlement and reversal read that stored account, never the current role.
  Handoffs: Area 5 (invoice versions), Area 3 (bills, vendor credits), Area 1 (receipts and payments), Area 2 (pay
  runs). Tests: `test_role_reassignment_requires_admin_and_reason`,
  `test_new_postings_use_reassigned_account`, `test_open_items_settle_and_reverse_on_original_account`.

### 8.2 New permission codes (amends §2.4)

| Code | Owner | Placement |
|------|-------|-----------|
| `payapp.adjust` | Area 4 §5 (item 17) | Sensitive; Accountant cap; Admin and the Master |
| `invoice.tax_override` | Area 5 §9 (item 22) | Sensitive; Accountant cap; Admin and the Master |
| `je.recurring_autopost` | Area 10 §6 (item 21) | Sensitive; Accountant cap; Admin and the Master |
| `vendor_credit.write_off` | Area 3, next_step (item 15) | Sensitive; Accountant cap; Admin and the Master |

All four are sensitive, so they sit in no level default (2.4.2). Job-title templates and per-user tweaks grant them.
The shipped Controller template adds all four in its sensitive column; no other shipped template gains them until
the owner says so. None is in `AGENT_ALLOWED`. The seeded code count goes from 111 to 115; the scratch check in 2.4
re-runs on the new counts when built.

### 8.3 New Company controls from 2026-11-22 (all OFF by default, Controls page, every change logged)

`lock_account_type_after_posting` and `require_zero_balance_to_deactivate` (§8.1); `subcontract_overlimit_block`
and `vendor_credit_writeoff_approval_threshold_cents` (NULL = off) for Area 3 (next_step). Area 20's
`capture_rejected_retention_days` (default 30) is a company setting, not a control.

### 8.4 Owner answer

**Q25. Normal balance when Type changes after posting (item 9 vs C3). Decided 2026-11-22 (owner; owner_decisions_2026-11-22 "Planning-session follow-ups", 12:47 PM):** the
normal balance follows the new Type, with a warning and an audit-log entry. This replaces C3's lock (chart of
accounts, docs/decisions_2026-11-11.md section C). `lock_account_type_after_posting` can still lock Type after the
first posting. Posted lines are unchanged; reports read the account's current normal balance. Test:
`test_type_change_after_posting_moves_normal_balance_with_warning_and_audit`.

### 8.5 Inbox inputs 2026-11-22 (v1.1 field scope; owner 12:41 PM and 12:45 PM)

Not decided schema. A Field role with a nav of about five items (proposal: Today, My jobs, Deliveries, Pull
tickets, Capture), set through the 11/17 access model (roles, levels, job titles); it follows field planning in
build order. Default job tab by role: operations roles (PM, field, operations) open the job on the Schedule
tab, finance roles keep the overview. Area 8's proposed `block_final_billing_with_open_punch_items` control
(OFF) joins §8.3 when that area's v1.1 pass is approved. Permission codes for daily logs, delays, punch items
and field material requests are placed here once the wireframes are approved.
