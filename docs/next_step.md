# Next step: Phase 2.7 STOP C (custom fields service, FR1 as amended)

Written 2026-11-17 at the end of step B2. Overwritten at each STOP (CLAUDE.md section 8). Start a fresh session
(MR1) and read .claude/rules/workflow-standards.md: done, the review gate, fix mode.
Status: **step B2 is done** and waits at the review gate. **STOP C is approved to build once the owner approves
B2** (owner, 2026-11-17).

**State:** B2_STATE

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
  files were not moved (rule 9); set the variable to the repo folder to keep using them.
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
- **Reviews:** B2_REVIEWS

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
  - `fields.manage` would be added to the baseline's permission seed. That is a baseline edit, and STOP C's rule is
    "no schema change", so **ask the owner first** (see the open question).
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

### Open question for the owner (STOP C)

1. `fields.manage` needs one row in the baseline's permission seed (`addon.manage` was added the same way at STOP
   B). That means a baseline edit and a rebuild of the empty development databases. Is that allowed under the
   schema hold, or should the permission wait for step 2.9?

## Open points carried forward

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
  typed confirmation and a reason, the Audit-ready flag) and scheduled backups with E7 retention for every reason.
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
