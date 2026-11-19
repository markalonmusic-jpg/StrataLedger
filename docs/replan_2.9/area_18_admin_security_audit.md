# Step 2.9 schema replan, area 18: admin, security, audit, attachments

Status: **drafted** (2026-11-18). Docs only: nothing here changes code, a baseline, a migration or a test.
Nothing here is built until the owner marks area 18 owner-approved in `Strata_Teams\schema_replan_2026-11-17.md`.
Every table, column and code below is PROPOSED.

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

Not read, though the sources point to them: `ux_research_roles_access_2026-11-17.md` (the access spec, sections 2
and 6), `ux_research_admin_security_2026-11-14.md`, docs/roles_permissions_design.md. The old-role mapping and the
shipped templates depend on the access spec (open item O1).

---

## 0. Summary

| # | Topic | Proposal in one line | Baseline |
|---|-------|----------------------|----------|
| 1 | Audit (AX4) | Keep the row-level audit triggers. Add `reason`, `origin`, `event`, `event_id` to the context and the log, filled only through `tx.py`. Take `logged_at` from the context. Mask `company_settings.tax_id` | both |
| 2 | Access model | Fixed roles with a level, company job titles with access templates, per-user overrides (add or remove), capped by the role. Contacts check by the contact's side | both |
| 3 | Memos and attachments | One `memo` column (max 4,000) on every form's header. `file_attachment` is replaced by `attachment` (append-only, removal marked with a reason, file kept) | company |
| 4 | Settings history, backup runs | Settings history is read from `audit_log` (no second table); a reason is needed for controls. New master `backup_run` table | both |

Conflicts with decisions, flagged and left open: section 6.

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
- `logged_at` comes from the database clock (`CURRENT_TIMESTAMP`, `YYYY-MM-DD HH:MM:SS` with no offset), not
  from `context.now`. That breaks the CLAUDE.md section 4 rule (`_at` columns are UTC ISO 8601 with an offset)
  and keeps a clock read in the database, which H2 forbids in services (conflict C3).
- The `action` CHECK lists Post, Approve and Void, but every trigger writes only Insert, Update or Delete. The
  business action (post, approve, void, reopen) is visible only from the column diff.

**Who writes audit rows today.** Only triggers. No module runs `INSERT INTO audit_log` (grep of `modules/`: none).
`tx.AuditStamp` (`modules/services/tx.py:72-92`) sets `audit_context.user_id`, `terminal_id`,
`software_version_tag` and `set_at` inside each write transaction and clears them before COMMIT. Add-on tables get
generated triggers from `migrations/addon_audit_triggers.sql` (`modules/database.py:756-880`, HA9).

**Every audit trigger in the company baseline** (`001_company.sql`, 127 `INSERT INTO audit_log` statements).
Each writes the row's columns as JSON, `old_value` for the old row and `new_value` for the new one:

| Table | Triggers (line) | Notes |
|-------|-----------------|-------|
| journal_entry | insert 2084, update 2121, delete 2229 | Carries its `journal_line` rows as `$.lines` (`:2180-2199`) |
| fiscal_period | 2266, 2289, 2322 | |
| account | 2345, 2371, 2410 | |
| invoice | 2436, 2486, 2573 | Includes `memo`. **`invoice_line` is not in the JSON and has no trigger of its own** |
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
| company_settings | insert 3524, update 3587 | **Writes `tax_id` in full** (`:3537`, `:3599`, `:3650`) |
| document_approval_setting | update 3718 | |
| bank_account | 3732, 3745, 3758 | Only `account_last4` (`:3730` comment) |
| fiscal_year | 3780, 3792, 3806 | |
| period_close_check | update 3817 | |
| ledger_chain_key | insert 3830, update 3841 | Fingerprint only, no key material |
| ledger_checkpoint | insert 3853 | Includes `mac` and `chain_hash` (integrity values, not secrets) |
| contact | 4200, 4242, 4313 | `tax_id_last4` only (`:4219`, `:4260`); includes `bank_payee_id` and `memo` |
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
`company_registry` 354, 375, 404; `chain_checkpoint` insert 472; `user_company_role` 586, 604, 627. Not audited,
on purpose: `master_recovery`, `installation_key`, `company_key`, `throttle_secret`, `login_throttle` (KS9;
`auth_event` records their changes instead).

**Company tables with no audit trigger** (no AFTER trigger at all): `estimate`, `estimate_line`, `contract`,
`contract_line`, `change_order`, `change_order_line`, `invoice_line`, `invoice_line_dimension`,
`journal_line_dimension`, `deferral`, `deferral_schedule_line`, `project_budget`, `time_entry`, `tax_rate`,
`dimension_type`, `dimension_value`, `file_attachment`, `import_batch`, `import_mapping`, `import_source`,
`staged_transaction`, `staged_line`, `progress_billing_application`, `poc_snapshot`, `subscription`,
`saas_subscription`, `saas_usage_telemetry`, `customer_number`, `vendor_number`, `voucher_sequence`,
`entry_number_sequence`. Some are counters or append-only logs of their own (`access_event` `:3039`/`:3045`,
`period_status_history` `:3773`/`:3777`). The rest are tables no service writes yet; each area that builds one
adds its triggers (rule below).

### 1.2 Proposal

**Recommended (option A in question Q1): keep the triggers as the capture, add the context to them.** H4 lets the
audit trail keep a database-level backstop, and the triggers are the only thing that also records writes from
the LEGACY screens (`CONNECT_ALLOW_LIST`, `tests/test_static_rules.py:23-30`) and from add-ons (HA9). Services
supply what a trigger cannot know (the reason, the origin, the business action), through `tx.py` only (H4).
Option B (services write every audit row and the core triggers are dropped) is what the task text calls AX4;
see conflict C1.

`audit_context` (both baselines), new columns:

| Column | Type | Rule |
|--------|------|------|
| `origin` | TEXT | CHECK IN ('Human', 'Agent', 'Import', 'System'), the same list as `journal_entry.origin` (`001_company.sql:463`); set from `context.origin` |
| `event` | TEXT | The service's action code, e.g. `settings.change`, `attachment.remove`, `period.reopen` (vocabulary in a service registry, not a CHECK, so a new action needs no baseline edit) |
| `event_id` | TEXT | One random id per write transaction (UUID text), so the rows of one action group together |
| `reason` | TEXT | CHECK (reason IS NULL OR length(reason) BETWEEN 1 AND 1000) |

`audit_log` (both baselines):
- Add `origin`, `event`, `event_id` (same types). Keep `reason` (already there).
- `logged_at` stays, without `DEFAULT CURRENT_TIMESTAMP`. Every trigger writes `ctx.set_at` (which `AuditStamp`
  already fills from `context.now`, `tx.py:84`), so the time is UTC ISO 8601 with an offset (CLAUDE.md section 4)
  and is the same for every row of one action. CHECK `logged_at IS NOT NULL` is not added, because the baseline
  runner's build and the add-on runner write rows before any context exists. Those rows keep a NULL time, which
  the audit screen shows as "Setup".
- `action` keeps its CHECK. Insert, Update and Delete stay the row operation; Post, Approve and Void stay
  allowed, but services use `event` for the business action.
- Indexes (company; the master gets the same): `(table_name, record_id, log_id)` for the record history,
  `(event_id)`, `(logged_at)`. Plain B-tree, portable.
- Every core trigger gains `logged_at, origin, event, event_id, reason` in its column list, read from `ctx`.
  `addon_audit_triggers.sql` gets the same, so add-on rows carry the reason too.

**Which actions require a reason.** The service refuses with one sentence when it is missing ("Enter a reason for
this change.", R27 style); the trigger copies it. A CHECK cannot do this, since it cannot see the action (H4).

| Action | Source | Where the reason is also kept |
|--------|--------|-------------------------------|
| Change a company control (Controls page: approval toggles, `require_separate_approver`, `manual_entry_approval` and its threshold, `allow_manual_control_je`, `lock_documents_after_posting`, approval policies and steps, area and account locks, the policy records of area 21) | 11-14 admin rules | audit_log only |
| Change a role's level defaults, a job title, an access template, a user's role, level, job title or override | 11-17 access model item 3; C57 | audit_log only |
| Remove an attachment | 11-15; C72 | `attachment.removed_reason` |
| Reopen a period or a year | `period.reopen`, `year.reopen` seeds (`001_company.sql`, "reason required") | `period_status_history.reason` (`:432`) |
| Reverse a posted entry | rule 8 | `journal_entry.reversal_reason` (`:457`) |
| Void an invoice, bill, credit memo or payment | persona audit 7 | `invoice.void_reason` (`:626`); payment: area 1 |
| Reject an approval | R16 | `approval_action.reason` (`:1154`) |
| Release an allocation | step 7 | `payment_allocation.release_reason` (`:330`) |
| Set or remove a period lock | area 13 | `fiscal_period_lock.reason` (`:3918`) |
| Restore a company (K5 Master override) | AX2, 2.8 | `backup_run` (section 4) |
| Edit a posted document by reverse-and-repost (rule 8) | rule 8 | the document's version history (area 5) |

Where a record already has its own reason column, the service writes the same text to both in the same
transaction. The record shows it, and the log keeps it after a later change. Optional for every other write: a
service may pass a reason, and the trigger stores it.

**Rollback guarantee (either option).** An audit row is written in the same transaction as the change it records:
a rolled-back change leaves no audit row, and a committed change always has one. With option A the database
guarantees it, even for a writer that forgets (a legacy screen, an add-on). With option B only the services and a
test that every write path writes its row can guarantee it. A refusal is not a change. Its record is
`access_event` (written after the rollback, `tx.py:66-70`) or `auth_event`, both append-only.

**Secrets never enter before/after (RP1, HA11).**
- Already safe: `password_hash` (master `:264`), bank numbers (`account_last4`), contact `tax_id` (last 4), key
  tables (not audited), `bank_payee_id` (a payee id, not a bank number, RP1).
- **To fix: `company_settings.tax_id` is written in full** (`:3537`, `:3599`, `:3650`), though `view.tax_ids` is
  sensitive and `_ADDON_HIDDEN_COLUMNS` hides the same column from add-ons (`modules/database.py:547-551`).
  Proposal: `tax_id_last4` like contact (question Q6).
- New rule: a static schema test applies HA11's secret-name rule (the same splitter and word list as the add-on
  runner) to every JSON key of every core audit trigger, in both baselines. A key that looks secret fails unless
  it is on a short reviewed allow-list (`mac`, `chain_hash`, `fingerprint`: integrity values, not secrets).
- `reason` is free text, so a person could type a secret into it. It is never written to the log file (R30
  already covers rejection reasons; the same filter applies). It is shown only to holders of `audit.view`
  (sensitive, `001_company.sql`, Audit module).
- Custom field values: STOP C refuses bank-number names on Contact fields only. Area 16 decides whether the same
  name check covers every record type, since every value reaches the log.

**PostgreSQL (AQ1, H4).** `audit_context` becomes per-transaction settings (`SET LOCAL app.user_id`, `app.reason`
and so on), as H4 already plans. The triggers become one PL/pgSQL trigger function per table (or one generic
function using `to_jsonb(OLD)` with a column allow-list). `json_object` becomes `jsonb_build_object`, and the
partial `substr(tax_id, -4)` becomes `right(tax_id, 4)`. The diffing of before/after for screens is done in
Python, never with `json_extract` in service SQL (H5). Proposal for the hosted port, not for now: generate the
core triggers from a column list, as HA9 does for add-ons, so the SQLite and PostgreSQL triggers come from one
source.

**Rule for new tables (all areas).** Every table a service writes gets insert, update and delete audit triggers in
the same baseline edit that adds it, or a one-line comment saying why not (a counter, an append-only log of its
own, a secret). A schema test lists the unaudited tables and fails on one that is not on the reviewed list.

### 1.3 How it lands in the baselines

One pass with the rest of 2.9. In both files: four columns on `audit_context`, three on `audit_log`, the
`logged_at` default removed, three indexes, every audit trigger rewritten (about 140 company and 13 master
statements; mechanical, so it is generated and then checked). `addon_audit_triggers.sql` changes too. That
changes `addon_schema_version.sha256` for nothing built yet (HA6), but the template's hash is part of the runner's
check, so the runner's tests need it. Every development database is blocked (CLAUDE.md section 5.2) and rebuilt
after asking (rule 9).

### 1.4 Effect on existing services and tests

- `tx.write_transaction(db_path, context, *, reason=None, event=None)`: `AuditStamp.begin` sets the four new
  columns and `end` clears them. No other module touches `audit_context` (H4; `test_static_portability.py`
  already checks this).
- `ServiceContext` already carries `origin` and `now`; nothing new.
- Services that already take a reason (`ledger` reversals, approvals rejection, `payments` release, period
  reopen) pass it to `write_transaction` too.
- `company_settings.update_setting` (`modules/services/company_settings.py:121`) and `set_document_approval`
  (`:130`) take `reason` and refuse without it for a control (section 4).
- Tests that read `audit_log` (35 test files, for example `test_company_settings.py`, `test_custom_fields.py`,
  `test_users_access.py`, `test_addon_audit.py`) keep working: the old columns keep their meaning. Tests that
  assert `logged_at` is set by the database, or count columns, need updating. The HA9 template tests change with
  the template.

### 1.5 Tests to write later

- Every audit row written inside `write_transaction` has `logged_at == context.now`, its `origin`, and one
  `event_id` shared by every row of that transaction.
- A control change without a reason is refused and nothing is saved; with one, the audit row carries it.
- A rolled-back write leaves no audit row (triggers fire, then the rollback removes them); a committed one always
  has one, including a write from a raw connection that has no context set (user NULL, still logged).
- `audit_context` is cleared after commit and after rollback (reason and event included).
- `audit_log` still refuses UPDATE and DELETE, in both files.
- Schema test: every core audit trigger's JSON keys pass the HA11 secret-name rule (reviewed allow-list).
- `company_settings` audit rows contain no full `tax_id`.
- Schema test: the list of company tables without audit triggers equals the reviewed list.
- Add-on triggers carry the reason and origin like core triggers (HA9).

---

## 2. Access model: roles × levels, job-title templates, per-user overrides

### 2.1 Current state

- Master: `app_user.role` (legacy free text, `001_master.sql:77`, read only by the sidebar), `app_user.job_title`
  (`:78`, free text, NOT NULL DEFAULT ''). `user_company_access(user_id, company_id, role_code, access_mode Grant
  or Deny)` (`:47-56`) is the gate (MR2). `user_company_role(user_id, company_id, role_code, granted_by,
  granted_at)` (`:577-584`), audited (`:586`, `:604`, `:627`), with no reason.
- Company: `permission(permission_code, module, description, is_sensitive)` (`001_company.sql:1056`);
  `role(role_code, name, is_system, is_active, project_scope All or Assigned, created_at)` (`:1063`);
  `role_permission` (`:1072`); `approval_limit(role_code, document_type, max_amount_cents)` (`:1078`);
  `user_project_scope(user_id, project_id)` (`:1085`). Only `Admin` is seeded, with every permission
  (`:1256-1260`). Its `created_at` uses `strftime('now')` in the baseline, which the PostgreSQL port must replace.
  Starter roles come from `modules/services/role_templates.py`.
- Rules in force: MR2 (the union of active roles; Admin allows all), MR3 (project scope), MR4 (approval limit: the
  highest), MR5 (one chain slot per person), MR8 (role changes name the rows they remove; `confirm_removal`).
  The last-Admin check is in `users.py:311-330`. The Admin guards are in `users.py:278`.
- Agent: `permissions.AGENT_ALLOWED` (`modules/services/permissions.py:113`) holds non-sensitive view and report
  codes only; `authz.authorize` denies anything else for `origin == 'Agent'` before any read
  (`modules/services/authz.py:132`).
- Sensitive codes (`is_sensitive = 1`): every approve code, `company.restore`, `addon.manage`, `fields.manage`,
  `period.reopen`, `year.reopen`, `payroll.view`, `payroll.import`, `import.approve`, `time.approve`,
  `view.tax_ids`, `view.bank_details`, `audit.view`, `ledger.verify`, `bill.override_match`,
  `payment.release_hold`. K13: `ledger.verify` is held only where granted by name (Admin, the Controller starter
  template, a later Auditor role, the Master); not the Accountant.
- Contacts (next_step.md input 3): `contacts._either_permission` (`modules/services/contacts.py:69-80`) authorizes
  `customer.manage` if held, else `vendor.manage`, for `update_contact` (`:199`), `deactivate_contact` (`:216`)
  and `find_duplicates` (`:148`), whatever kind the contact is. A vendor manager can edit a customer-only contact,
  and the reverse. Custom field values on contacts use the same check (STOP C).

### 2.2 What the sources ask for, and how they differ

- 11-14 (archive) and C57: one role list of 11 roles (Admin, Controller, Accounts payable, Accounts receivable,
  Sales manager, Sales rep, Estimator, Project manager, Superintendent, Warehouse lead, Viewer), a user's roles
  united, a role × permission matrix on the Users page, a reason for each change.
- 11-17 (open): **replaces the 11-14 matrix.** 5 roles (Master, Admin, Accountant, Sales rep, Operations); levels
  View only, Standard and Manager on the last three; job titles per company, each with an access template (a
  permission set that may span areas); per-user overrides on top. Effective access = role/level defaults ∪
  template ∪ overrides, **capped by the role**; Master and Admin get everything. Every change needs a reason.
  Person pickers query by permission. Lead assignment rules per service type (area 15). The 11 old roles are
  mapped by spec section 2. 11-17 (8:31 PM): only Admins and the Master manage templates and job titles; shipped
  templates can be hidden, not deleted; a template in use cannot be deleted until its users move.
- CODE_CHANGES 57 still describes the 11-role list (conflict C4).

### 2.3 Proposal

Where things live: the gate and the role assignment stay in the master (MR2; a user's access is installation
data). Job titles, templates and overrides are company configuration and go in the company file, beside `role`
and `role_permission`, so they travel with the company file and its backups (rule 3 allows this: they are not
accounting tables, but they are per company). User ids are plain integers there (CLAUDE.md section 4).

**Master**
- `user_company_role` gains `level TEXT` CHECK (level IS NULL OR level IN ('View only', 'Standard',
  'Manager')). The rule "Admin has no level, Accountant / Sales rep / Operations have one" is a service rule,
  because role codes are company data the master cannot check. If question Q2 picks one role per user per company,
  the primary key becomes `(user_id, company_id)`, MR8's "replace the rows" becomes "replace the row", and the
  union of roles (MR2) shrinks to one role plus a template. Otherwise the key stays.
- `user_company_access.role_code` stays only as MR2's fallback until Phase 3 removes it with `app_user.role`
  (Known issues). Not touched now.
- Offboarding and sign-in (C57, 11-14): `app_user.deactivated_at TEXT`, `deactivated_by INTEGER` (the screen's
  "Deactivated 11/14/2026 by mark"; CHECK both set or both NULL, and set only while `is_active = 0`);
  `app_user.temp_password_expires_at TEXT` (72 hours, C57; NULL when not a temporary password);
  `app_user.session_epoch INTEGER NOT NULL DEFAULT 0` (Reset password and Sign out everywhere add 1, and a session
  that started under an older epoch is signed out at its next request; the hosted edition needs this, and on the
  desktop it ends a second open window). The idle-lock minutes are a company setting (area 21's policy records).

**Company**
- `role`: the system roles are seeded as rows: `Admin`, `Accountant`, `Sales rep`, `Operations` (`is_system = 1`).
  The Master is not a role (`app_user.is_master`). Whether companies may still create custom roles: question Q3
  (recommended: no; templates take that job).
- `role_level(role_code, level, project_scope)`: PK `(role_code, level)`, FK role, level CHECK as above,
  `project_scope` CHECK ('All', 'Assigned'). MR3's scope moves from `role` to the level. `role.project_scope` is
  dropped.
- `role_level_permission(role_code, level, permission_code)`: PK all three, FK `role_level` and `permission`.
  These are the defaults.
- `role_cap_permission(role_code, permission_code)`: PK both. This is the cap: no template or override can give a
  user of this role a code outside it. Admin has no rows, because Admin holds everything (MR2). Question Q4: is
  the cap its own list, or the Manager level's defaults?
- `job_title(job_title_id PK, name TEXT NOT NULL UNIQUE, template_id INTEGER REFERENCES access_template, is_active
  0/1, created_at, created_by)`. `app_user.job_title` (master) stays a display label. The access link is the
  company's `user_job_title`.
- `access_template(template_id PK, name TEXT NOT NULL UNIQUE, description, is_shipped 0/1 NOT NULL, is_hidden 0/1
  NOT NULL DEFAULT 0, created_at, created_by)`. Triggers (integrity: shipped rows never deleted) refuse DELETE of a
  shipped template, and DELETE of a template that a `user_job_title` or `job_title` row still uses (the FK does it
  too: no ON DELETE CASCADE).
- `access_template_permission(template_id, permission_code)`: PK both, FKs.
- `user_job_title(user_id, job_title_id)`: PK `user_id` (one title per user per company; question Q5),
  FK job_title, `assigned_by`, `assigned_at`.
- `user_permission_override(user_id, permission_code, effect TEXT CHECK (effect IN ('Add', 'Remove')), granted_by
  INTEGER NOT NULL, granted_at TEXT NOT NULL)`: PK `(user_id, permission_code)`. Remove beats Add from any source,
  which is useful for separation of duties (question Q7).
- `approval_limit`: keyed by `(role_code, level, document_type)` instead of `(role_code, document_type)`, plus
  `access_template_approval_limit(template_id, document_type, max_amount_cents)` and
  `user_approval_limit(user_id, document_type, max_amount_cents, granted_by, granted_at)`. MR4 becomes: the
  highest limit among the sources that also grant the approve permission. The cap on limits: question Q8.
- Every new table gets audit triggers (section 1). Every write to them passes a reason (11-17 item 3).
- Indexes: `user_permission_override(permission_code)`, `access_template_permission(permission_code)`,
  `role_level_permission(permission_code)`, `user_job_title(job_title_id)`. These serve the person pickers ("who
  can do X").

**Effective access (the authz rule that replaces MR2's union, written here for the decision log, not built):**
gate as MR2 (access row, Deny wins; the Master allows all; Admin allows all) → role and level rows → defaults ∪
template ∪ Add overrides, minus Remove overrides, intersected with the role's cap → `AGENT_ALLOWED` for Agent
origin. Inactive role, title or template: skipped (the inactive-role denial as today). Denials keep R27 (no code
in a sentence) and the reasons `authz.DENIAL_REASONS`; a new reason `capped` is not needed, because a capped code
is simply not held (`ROLE`).

**Sensitive codes (K13, fields.manage, ledger.verify).** No level default ever holds a sensitive code (schema test
on the seed rows). A sensitive code comes only from a template or a named Add override, and adding one requires a
reason. Shipped templates may hold them, for example a Controller template with `ledger.verify` (K13).
`fields.manage` stays Admin-only by default, as STOP C seeded it. The cap must include a sensitive code for a
template to grant it, so the Accountant's cap decides whether an Accountant can ever verify the ledger (K13 says
not by default; question Q9). Note: every approve code is sensitive today, so under this rule a Manager level
cannot approve unless a template grants it. That is part of Q9.

**Separation of duties.** Unchanged and still a control (OFF by default, section 0): `require_separate_approver`
(R17), MR5 (one chain slot per person), the triggers at `001_company.sql:3702-3714`. New, as a warning only: saving
a template or an override that leaves one user holding both a document's create and approve codes shows "This
person could enter and approve the same bill." That is informational, not a block; it becomes a block only if the
owner adds a control for it (question Q10).

**The Agent.** The Agent is not a user and has no role, level, title or override. `AGENT_ALLOWED` stays the only
source of its codes, applied after everything else. No sensitive code is ever agent-allowed (existing comment,
`permissions.py:114-115`). Person pickers never list the Agent. Agent-origin entries keep their human approval
(integrity rule, section 0).

**Contacts: the "either manager" check (next_step.md input 3).** Proposal: authorize by the contact's side,
following MR6 and MR9:
- customer only: `customer.manage`; vendor only: `vendor.manage`; both flags, or neither (a plain contact or a
  lead's contact): either one.
- The service reads the contact's flags before `authorize` (in its own read connection, as MR6 does for
  allocations), then authorizes. A holder of only one right gets the same sentence, error type and denial row for
  a missing contact and for one on the other side (MR9), so ids cannot be probed.
- `find_duplicates` returns only contacts on a side the caller can manage. Custom field values on contacts use
  the same rule.
- No schema change (the flags `is_customer` and `is_vendor` exist). Alternative: question Q11.

**Person pickers (11-17 item 4).** The listed capabilities (`can_own_leads`, `can_manage_jobs`,
`can_build_estimates`, `can_run_field_schedule`, `can_approve:<doc>:<limit>`, `can_receive_deliveries`,
`can_work_cases`) are permission codes, not a second mechanism. Existing codes cover some (`project.manage`,
`estimate.create`, the approve codes with `approval_limit`, `receiving.jobsite` and `receiving.stock`). New codes
proposed, to be confirmed in areas 8 and 15: `lead.own`, `field.schedule`, `case.work`. A picker is a service
read: users with company access, active, holding the code by the effective-access rule. It is not stored.

**Migration of the 11 old roles (11-17 item 6).** Needs spec section 2 (open item O1). Until the first release
nothing needs migrating: the role templates in `role_templates.py` and the seed are rewritten, and development
databases are rebuilt.

### 2.4 How it lands in the baselines

Master: `user_company_role.level`; the `app_user` columns. Company: the seeded system roles, `role_level`,
`role_level_permission`, `role_cap_permission`, `job_title`, `access_template` (+ shipped seed rows, spec section
6), `access_template_permission`, `user_job_title`, `user_permission_override`, the approval-limit tables; drop
`role.project_scope`; new permission codes only once areas 8 and 15 confirm them. All in the one 2.9 pass.

### 2.5 Effect on existing services and tests

- `authz.authorize`, `authz.is_allowed`, the MR3 and MR4 helpers: the new effective-access rule. This is the
  largest change in the area, and every permission test path runs through it.
- `users.grant_access`, `set_role`, `deny_access` (`users.py:120`, `:145`, `:172`): take a level and a reason;
  MR8's removal confirmation stays. The last-Admin check (`users.py:311-330`) is unchanged.
- `role_templates.py` is rewritten as level defaults plus shipped access templates.
- `contacts.update_contact`, `deactivate_contact`, `find_duplicates`, and `custom_fields` on contacts: the
  side check.
- Tests: `test_users_access.py`, `test_roles_schema.py`, `test_ledger_approvals.py` (MR4, MR5),
  `test_custom_fields.py` (contacts and the `fields.manage` holders) and every test that builds a role with
  `role_permission` rows directly need new fixtures. The static rules are unchanged.

### 2.6 Tests to write later

- Effective access: defaults ∪ template ∪ Add, minus Remove, within the cap; one test per source and per
  combination; Admin and the Master allow all; Deny wins.
- A template or override cannot give a code outside the role's cap (saving refuses, and authz ignores a stored
  one).
- No level default holds a sensitive code (seed test). A sensitive Add override without a reason is refused.
- Shipped template: hide works, delete is refused. A template in use cannot be deleted (trigger and service).
- Only Admin or the Master manage templates and job titles.
- MR3 and MR4 rewritten over levels, templates and user limits; MR5 unchanged across sources.
- The Agent ignores templates and overrides; an override cannot add a code to the Agent.
- Contacts: a vendor manager cannot edit a customer-only contact and gets the same sentence as for a missing id
  (MR9); a both-sides contact is editable with either right; `find_duplicates` hides the other side.
- Pickers: an inactive user, a user without access, and a capped code are not listed.
- Every role, level, title, template or override change writes an audit row with a reason.

---

## 3. Memos and attachments on every form (R16 of the UI rules, C72; owner 2026-11-15)

### 3.1 Current state

Memo-like columns that exist (to reuse, not duplicate, as the 11-15 message asks):
- `invoice.memo` (`001_company.sql:627`), which covers bills, credit memos and vendor credits, since a bill is an
  invoice with `ledger_side = 'Purchase'`. It is locked on a sent or posted invoice (`:1827`, `:1986`) and audited
  (`:2479`).
- `contact.memo` (`:835`), `contact_site.memo` (`:3905`), `pay_run.memo` (`:3998`), `deferral.memo` (`:921`),
  `journal_line.memo` (`:493`), `staged_line.memo` (`:312`), `contract.notes` (`:892`). The journal entry's memo is
  `journal_entry.description` (C72: it stays the entry description).
- Missing on existing tables: `payment`, `estimate`, `change_order`, `project`.
- There is no customer-facing "Message on document (prints)" column on `invoice` or `estimate` (C72). That belongs
  to areas 5 and 6.
- The other forms in C72 (purchase order, receipt, pull ticket, item, asset, loan, sub pay app, lead, deposit,
  transfer, refund, write-off) have no tables yet. Their areas (1, 4, 9, 11, 12, 15) add them.

Attachments: `file_attachment` (`:74-89`): `file_id`, `file_name`, `file_path` ("localized directory reference"),
`file_size_kb`, `target_type` CHECK ('Project_Evidence', 'Change_Evidence', 'Invoice_Source'),
`target_record_id`, `uploaded_at DEFAULT CURRENT_TIMESTAMP`. No uploader, content type, checksum or removal fields;
no audit trigger; no index. **Nothing uses it**: no reference in `modules/`, `tests/` or `scripts/`.
`modules/services/storage.py` has resource reads and `data_path` (`:106`), but no write API for uploaded files.

### 3.2 Proposal

**Memo.** One column named `memo` (the existing name) on every form's header table: `memo TEXT CHECK (memo IS NULL
OR length(memo) <= 4000)`.
- Add it to `payment`, `estimate`, `change_order` and `project`, and add the CHECK to the existing `memo` columns
  (`invoice`, `contact`, `pay_run`, `deferral`).
- `contract.notes` stays (area 6 decides whether it is the contract's memo).
- Each new header table in other areas gets `memo` with the same CHECK. That is a rule for areas 1, 4, 9, 11, 12
  and 15, listed here so they do not invent `internal_memo` or `notes`.
- The customer-facing text is a separate column, `document_message`, on customer documents (areas 5 and 6). The
  name is proposed here so both areas use one.
- **Never printed (owner 2026-11-18).** The print and email renderer builds from an allow-list of fields per
  document, and `memo` is on none. A test renders every document type with a memo set and asserts the text is
  absent. No schema can enforce this; it is a service and template rule.
- The memo follows the record's edit rules: the invoice memo is fixed once sent or posted (existing trigger) and
  changes only through rule 8's reverse-and-repost. The JE description is fixed once posted.
- Audit: the memo is a column, so the row's audit trigger records its old and new text. Tables still without
  triggers (`estimate`, `change_order`) get them under section 1's rule.

**Attachments.** `file_attachment` is replaced by `attachment`. Nothing uses the old table, so it is dropped rather
than altered.

| Column | Type and constraint |
|--------|---------------------|
| `attachment_id` | INTEGER PRIMARY KEY |
| `record_type` | TEXT NOT NULL CHECK IN (the form list of C72 that exists in this baseline: 'Invoice', 'Bill', 'Credit memo', 'Estimate', 'Change order', 'Payment', 'Pay run', 'Journal entry', 'Project', 'Contact', 'Deferral'; each area adds its own) |
| `record_id` | INTEGER NOT NULL (polymorphic, no FK; the service checks the record exists) |
| `file_name` | TEXT NOT NULL CHECK (length BETWEEN 1 AND 255) |
| `storage_key` | TEXT NOT NULL UNIQUE. A relative key from `storage.py` (H3), never a path. On the desktop it maps under `DATA_DIR/Uploaded_Files/<company_code>/`, and in hosted to blob storage |
| `size_bytes` | INTEGER NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 20971520) (20 MB, C72). The company's allowed types and any lower size limit are a company setting (area 21) |
| `content_type` | TEXT NOT NULL |
| `sha256` | TEXT NOT NULL CHECK (64 lowercase hex), so a later read detects a changed file |
| `document_kind` | TEXT, NULL except for loans: CHECK IN ('Loan agreement', 'Promissory note', 'Security agreement', 'Amendment or rate change', 'Payoff letter', 'Statement', 'Other') (C72) |
| `added_by` | INTEGER NOT NULL |
| `added_at` | TEXT NOT NULL (from `context.now`) |
| `origin` | TEXT NOT NULL DEFAULT 'Human' CHECK (as section 1) |
| `removed_at`, `removed_by`, `removed_reason` | NULL until removed; CHECK all three set or all NULL; CHECK `removed_reason` length ≥ 1 |

- Integrity triggers (H4: append-only backstop): DELETE refused; UPDATE refused unless it only sets the three
  removal columns, once, from NULL. A posted or locked record still takes new attachments; that changes no
  accounting (11-15).
- Audit triggers on insert and update: metadata only, never the file's contents.
- Index: `(record_type, record_id)`. It serves the list and the paperclip count. The count query filters
  `removed_at IS NULL`; a partial index works in both SQLite and PostgreSQL if needed.
- Removal keeps the file in storage, marked removed (the 11-15 recommendation; question Q12). The record shows
  "Removed by ... : reason" to `audit.view` holders.
- Permission: adding needs the record's own create or manage code; removing needs the same and a reason
  (question Q13).
- The Agent: no attachment reads or writes in v1 (outside `AGENT_ALLOWED`; Phase 6 decides).

### 3.3 How it lands in the baselines

Company only: `memo` on four tables, the length CHECK on four existing `memo` columns, `file_attachment` dropped,
`attachment` with its triggers and index. The record-type list grows with each area's new tables in the same pass.

### 3.4 Effect on existing services and tests

None today: no service writes `file_attachment` or those `memo` columns. `test_schema_replan.py:370-372` already
expects `invoice.memo`. A later step adds `storage.put_file`, `storage.open_file` and `storage.exists` (H3), and an
`attachments` service. Backups: AX2 copies the database only, so the attachments folder is outside every backup
today (question Q14).

### 3.5 Tests to write later

- `memo` longer than 4,000 characters is refused (schema) with one sentence (service).
- No printed or emailed document contains its memo (every document type).
- The invoice memo cannot change once sent or posted (existing trigger, re-asserted for bills).
- `attachment`: DELETE refused; changing any column but the removal ones refused; removal is set once; removal
  without a reason refused; size over 20 MB refused; a bad `sha256` refused.
- A posted or locked record accepts a new attachment, and its journal and chain are unchanged.
- An attachment on a missing record is refused; a user without the record's right is refused (R27 sentence).
- Audit rows carry metadata only. `storage_key` is relative (no drive letter, no `..`; storage.py `_safe_join`).
- Static: no `memo` field in any print template's allow-list.

---

## 4. Settings change history and the master backup-run record (E7, AX2, X9)

### 4.1 Current state

- Settings: `company_settings` is one row (`001_company.sql:734-787`), with controls and preferences side by side.
  Its update trigger (`:3587`) writes the whole old and new row as JSON on every change. So before and after
  exist now; the reason and an easy per-setting view do not. `document_approval_setting` (`:3718`),
  `approval_policy` and `approval_step` (`:3402-3506`) and `fiscal_period_lock` (`:4509-4556`) are audited the
  same way. `company_settings.update_setting` (`modules/services/company_settings.py:121`) takes no reason.
- X6 (area 21) asks not to keep growing the singleton row; the policy records come from area 21.
- Backups: `database.backup_database(db_path, reason=...)` (`modules/database.py:179`) writes
  `Backups/<stem>_<timestamp>_<reason>.db` and `<backup>.sha256`, and returns `{path, sha256}`.
  `prune_backups` (`:234`) applies E7 retention to `addon-<key>` backups. `pre-upgrade` and `pre-restore` are never
  pruned (AX2, owner 2026-11-18). `restore_database` (`:275`) checks the checksum. **No table records a backup
  run**: the backup screen's history would have to read the folder. The `.sha256` file detects corruption, not
  tampering (AX2). 11-14 asks for scheduled (daily at sign-out, keep 30), manual, test-restore and year-end archive
  backups, encrypted with a backup password, with failure as a "need attention" item. E7 says keep 7 daily, 4
  weekly, 12 monthly.

### 4.2 Proposal

**Settings history: no second table.** The history screen is a service read over `audit_log` for the settings
tables (`company_settings`, `document_approval_setting`, `approval_policy`, `approval_step`, `fiscal_period_lock`,
the area 21 policy tables, the access tables of section 2). It diffs `old_value` and `new_value` in Python (H5)
and returns one line per changed setting: setting, before, after, who, when, reason. The labels come from a service
registry of setting names (the same one the Controls page uses). Section 1 supplies the reason, the origin and the
`event_id`. A reason is required for a control (section 1's list) and optional for a preference such as the date
format or time zone (question Q15). Alternative: a `setting_change` table written by the service (question Q16;
not recommended: two records of one change).

**Master `backup_run`** (in the master, so restoring an older company file cannot erase the record of its own
backups, the same reasoning as K14's checkpoint mirror):

| Column | Type and constraint |
|--------|---------------------|
| `run_id` | INTEGER PRIMARY KEY |
| `company_id` | INTEGER REFERENCES company_registry, NULL for the master file itself |
| `kind` | TEXT NOT NULL CHECK IN ('Scheduled', 'Manual', 'Pre-upgrade', 'Pre-restore', 'Add-on', 'Year-end', 'Test restore', 'Restore') |
| `reason_code` | TEXT NOT NULL. The AX2 file-name reason (`pre-upgrade`, `addon-<key>`, ...), so a row and a file match |
| `started_at` | TEXT NOT NULL |
| `finished_at` | TEXT |
| `result` | TEXT NOT NULL CHECK IN ('Running', 'OK', 'Failed') |
| `file_name` | TEXT. The backup's file name only, relative to the company's `Backups/` folder (no absolute path: H3, hosted) |
| `sha256` | TEXT CHECK (NULL or 64 hex) |
| `size_bytes` | INTEGER CHECK (NULL or ≥ 0) |
| `is_encrypted` | INTEGER NOT NULL CHECK (0, 1). The backup password itself is never stored, and nor is a hash of it |
| `error_message` | TEXT. A plain sentence only (R35: the details go to the log file, not here) |
| `requested_by` | INTEGER, NULL for a scheduled run |
| `origin` | TEXT NOT NULL CHECK (as section 1) |
| `source_run_id` | INTEGER REFERENCES backup_run. For a test restore or a restore: the backup it used |
| `reason` | TEXT. Required by the service for a restore (K5's Master override) and for a deletion offer (next_step 2.8) |
| `pruned_at`, `pruned_by` | NULL until E7 pruning removes the file; then set once (the row stays) |

- CHECKs: `result = 'OK'` needs `finished_at`, `file_name` and `sha256` (except for a test restore, which needs
  `source_run_id`); `result = 'Failed'` needs `error_message`; `kind IN ('Pre-upgrade', 'Pre-restore')` needs
  `pruned_at IS NULL` (never pruned, AX2).
- Triggers: no DELETE. UPDATE may only move a `Running` row to `OK` or `Failed` once, and set the prune columns
  once. Every other column is immutable (the `installation_key_retire_only` pattern, `001_master.sql:525`). Audit
  triggers on insert and update.
- Index: `(company_id, started_at)`, and `(result)` for the "need attention" item.
- A failed run is a row, so the home screen's "need attention" item is a query, not a file scan.
- Writer: the 2.8 backup service, around `database.backup_database`. The helper stays free of master access, a
  database-layer function that knows no context. The baseline runner's `pre-upgrade` backup (after the first
  release) is recorded by the `ensure_*` caller once the master is open. Recorded in the master only, never in the
  company file.
- Hosted: the same table in the hosted master database; `file_name` becomes a storage key.

### 4.3 How it lands in the baselines

Master: `backup_run` with triggers and indexes (section 1's audit columns apply). Company: nothing more than
section 1. The 2.8 services write it; 2.9 only adds the table.

### 4.4 Effect on existing services and tests

- `company_settings.update_setting` and `set_document_approval` take `reason` (required for controls). Callers:
  the settings screens (Phase 3) and `test_company_settings.py`, `test_controls_003.py`, `test_controls_004.py`.
- `database.backup_database`, `prune_backups`, `restore_database`: unchanged. `test_master_schema.py` gains the
  table.

### 4.5 Tests to write later

- Settings history: one line per changed setting with before, after, who, when and reason; no line for an update
  that changed nothing; the labels come from the registry; no SQLite JSON functions in the service SQL (static
  rule H5).
- A control change without a reason is refused; a preference change without one is accepted (if Q15 = A).
- `backup_run`: DELETE refused; a finished row cannot change; `Running` → `OK` or `Failed` only once; an OK row
  needs file, sha256 and finish time; a failed row needs a sentence; `Pre-upgrade` and `Pre-restore` rows cannot
  be marked pruned; prune is set once.
- `error_message` never holds a path or exception text (R35).
- No column holds a backup password or a value derived from it (HA11 name rule over the master's columns).
- Restoring an older company file leaves the master's backup history whole.

---

## 5. Open items (not decisions)

- **O1** The access spec (`ux_research_roles_access_2026-11-17.md`, section 2 role mapping, section 6 shipped
  templates) is needed before section 2's seed rows can be written. It is not read in this draft, by the task's
  source list.
- **O2** C57's permission matrix rows (Money, Accounting, People, Data, Settings, Field) map to codes in
  docs/roles_permissions_design.md section 3 (not read). Under the 11-17 model they become template and level
  rows instead of a role × permission grid.
- **O3** The persona audit's who-and-when columns (item 2: `created_by`, `created_at`, `updated_by`, `updated_at`
  on invoice, payment, contact, change_order, contract) overlap with section 1: "Entered by" can be read from the
  first audit row. Area 21 decides whether the record carries them too.
- **O4** "Export all data" (persona audit 14) needs an export permission. `company.backup` ("Back up and export the
  company") and `report.export` exist; area 21 decides whether a new code is needed.
- **O5** Lead assignment rules (11-17 item 5) belong to area 15.

---

## 6. Conflicts with decisions (flagged, not resolved)

- **C1 AX4 wording vs H4 and HA9.** The task says audit rows are "written by services, not triggers (AX4)".
  AX4's text (docs/decisions_2026-11-11.md:1658) says only "before/after detail and a reason field". H4 (`:846`)
  keeps triggers for "the audit trail" as a database backstop, and HA9 makes add-on audit triggers. This draft
  recommends keeping the triggers (Q1). If the owner picks services-only, H4 and HA9 need amending.
- **C2 E11 vs the baseline.** E11 (`:605`) says `origin` lives on `audit_log`; neither baseline has it. Section 1
  adds it.
- **C3 Timestamp rule vs `audit_log.logged_at`.** CLAUDE.md section 4 says `_at` columns written by services are
  UTC ISO with an offset, and H2 says no clock reads in services. `logged_at` uses `CURRENT_TIMESTAMP`. The same
  applies to `file_attachment.uploaded_at`, `company_registry.created_at` and `app_user.created_at`. Section 1
  fixes audit_log only; the rest belong to area 21.
- **C4 CODE_CHANGES 57 vs the 11-17 access model.** C57 lists 11 roles and a role × permission matrix; 11-17 says
  it replaces that matrix. C57 is not yet updated, so the design chat should revise it.
- **C5 MR2 union vs the 11-17 cap.** MR2 unites roles. 11-17 adds a cap per role. If a user may hold two roles
  (Q2 B), the cap of a union needs a rule (the union of caps is recommended under that option).
- **C6 K13 vs level defaults.** K13 names "Controller (starter template)" as a holder of `ledger.verify`. Under
  11-17 Controller is a job title with a template, not a role. That is consistent, but K13's wording needs a later
  amendment.
- **C7 HA11 vs `company_settings.tax_id`.** HA11 treats TIN as a secret word for add-ons, and the add-on
  authorizer hides the column, yet the core trigger logs it in full (Q6).

---

## 7. Questions for the owner

Recommended option first in each.

**Q1. Who writes audit rows (AX4)?**
- A. **Recommended:** keep the row triggers. Services add the reason, origin and action through `tx.py`. Every
  write is logged, even one a service forgets.
- B. Services write every audit row and the core triggers are dropped. One Python place for redaction, nothing to
  port, but a missed write path is unlogged. H4 and HA9 need amending.
- C. Both: services write an action row with the reason, and the triggers keep the column detail.

**Q2. How many roles may a user hold in one company?**
- A. **Recommended:** one role with one level, plus one job title and overrides. This is simpler, and the cap is
  clear. MR2's union and MR8 shrink accordingly.
- B. Several roles, as MR2 and the persona audit's "gets all of them" allow. The cap is the union of their caps.

**Q3. Can a company create its own roles under the new model?**
- A. **Recommended:** no. The four system roles are fixed; custom templates cover the variety.
- B. Yes, a custom role with its own levels and cap.

**Q4. What is a role's cap?**
- A. **Recommended:** its own list (`role_cap_permission`), wider than the Manager defaults, so a template can add
  codes the level does not give.
- B. The Manager level's defaults: nothing beyond them can be added.

**Q5. How many job titles per user per company?**
- A. **Recommended:** one.
- B. Several, with their templates united.

**Q6. `company_settings.tax_id` in the audit log**
- A. **Recommended:** last 4 only, like contacts.
- B. In full (the company's own ID prints on its invoices), readable by `audit.view` holders.

**Q7. Per-user overrides**
- A. **Recommended:** Add and Remove; Remove wins over every source.
- B. Add only.

**Q8. Approval limits under the new model**
- A. **Recommended:** level defaults, template limits and user limits. The highest of those that come with the
  approve permission applies, with no cap on the amount.
- B. As A, plus a cap per role and document type.
- C. Limits on the user only.

**Q9. Sensitive codes and levels**
- A. **Recommended:** no level default holds a sensitive code (approve codes included). They come only from
  templates or named overrides, with a reason.
- B. Manager levels may hold the approve codes by default; the other sensitive codes as in A.

**Q10. Separation-of-duties check on templates and overrides**
- A. **Recommended:** a warning only.
- B. A new control (OFF by default) that blocks one person from holding create and approve for the same document
  type.

**Q11. Contacts "either manager" check**
- A. **Recommended:** by the contact's side: customer-only needs `customer.manage`, vendor-only needs
  `vendor.manage`, both sides or neither takes either. MR9's same sentence for one-right holders.
- B. Both-sides contacts need both rights.
- C. Keep either right for every contact (today's behaviour).

**Q12. A removed attachment's file**
- A. **Recommended:** kept in storage and marked removed.
- B. Deleted from storage; the row stays.

**Q13. Who may remove an attachment?**
- A. **Recommended:** whoever may edit the record, with a reason.
- B. Only Admins or the Master.
- C. A new sensitive code `attachment.remove`.

**Q14. Attachments and backups**
- A. **Recommended:** decide in 2.8. A backup copies the database only today (AX2), so files need their own copy
  plan.
- B. Each backup also zips the company's attachments folder.

**Q15. Which settings changes need a reason?**
- A. **Recommended:** controls only (the 11-14 rule); preferences optional.
- B. Every settings change.

**Q16. Where settings history is stored**
- A. **Recommended:** read from `audit_log`, with no second table.
- B. A `setting_change` table written by the service.

**Q17. Session invalidation (Sign out everywhere, Reset password)**
- A. **Recommended:** `app_user.session_epoch`, added now.
- B. Defer to the hosted edition; the desktop has one session per window.
