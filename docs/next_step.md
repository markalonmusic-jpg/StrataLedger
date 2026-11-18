# Next step: Phase 2.7 STOP C (custom fields service, FR1), plan only

Written 2026-11-17 at STOP B. Overwritten at each STOP (CLAUDE.md section 8). Start a fresh session (MR1).
Status: **Phase 2.7 STOP B (hooks, add-ons, add-on migrations) is done**: built, reviewed, audited and
mutation-checked. STOP C is **planned only**: FR1 says it is built only after the owner approves this plan.

**State:** full suite 3262 passed, 1 skipped (the linked-file test needs the right to create symbolic links), 7 deselected. Commits 3c961c3 (build), 1b5f723 (review fixes), 9b2f1f1 (audit fixes) and the STOP commit (mutation tests), all pushed to origin/main; tag `baseline-pre-2.7-b` marks the baseline before the sha256 column.

## Done in STOP B (2026-11-17)

- **Owner answers:**
  - MR8 is confirmed, with an addition. `grant_access`, `set_role` and `deny_access` take `confirm_removal`.
    Without it, a change that would remove role rows raises `ConfirmationRequiredError` ("This removes:
    <roles>. Confirm to continue."; `removed_roles`), after every other refusal. They return
    `{'removed_roles'}`, and the delete trigger audit-logs each removed row.
  - MR9 closes LOW-A. In `allocate`, someone with one payment right gets one sentence, one error type and one
    denial row for a missing id and for an id on the other side (`payments.ONE_SIDE_ONLY`).
- **Baseline (HA5, HA6):**
  - `addon_schema_version.sha256` (NOT NULL, 64 lower-case hex characters).
  - The `addon.manage` seed: sensitive, held by Admin; the Master holds every permission.
  - Old baseline saved in archive/baseline_pre_2_7_b (tag `baseline-pre-2.7-b`); development master rebuilt
    (`Companies/` was empty; the old master is in `Backups/`).
- **`modules/database.py`:**
  - `check_addon_key`: 2-31 lower-case letters and digits; no key whose `<key>_` prefix matches a core table,
    and `sqlite` is reserved.
  - `addon_write_guard`: the SQLite authorizer (HA2).
  - `apply_addon_migrations` (HA4, HA6).
- **`modules/services/hooks.py`:** `EVENTS`, `HookApi.on`, and `fire` inside the caller's transaction; HA7 has the
  details.
- **`modules/services/addons.py`:**
  - `discover` and `load`, only from RESOURCE_DIR/addons, read through `storage.py`.
  - `list_addons`, `enable` and `disable` (`addon.manage`).
  - `prepare_company`, called by `open_company`.
- **`ledger._seal_and_post`** fires `entry.posted` for every posted entry, and `entry.voided` for a Void.
- **Reviews:** step-reviewer approved with changes (fixed in 1b5f723); secrets-auditor found nothing Critical or High (MEDIUM-1 and LOW-2 to LOW-5 fixed in 9b2f1f1, LOW-6 open below); mutation-tester on 9b2f1f1: 262 mutants, 155 killed, the rest equivalent or now covered by tests/test_mutation_stop_b_extra.py (59 tests). Those tests found one bug, fixed: the migration guard refused SQLite's automatic index for a UNIQUE or text PRIMARY KEY column on an add-on table.

## STOP C plan: the custom fields service ("Field Registry", FR1)

Sources, read-only:
- C:\Users\marka\Strata_Teams\crm_design_log.md, sections 2-7. Section 5 gives the field packs (Solar,
  Roofing, Home improvement), the 15-field cap and typed storage.
- C:\Users\marka\StrataLedger_mockups\CODE_CHANGES_NEEDED.md, section 12, especially 12.4 (the proposed
  `field_definition` / `field_option` / `field_value` shape) and 12.10 (`pipeline.manage` covers fields).
- The baseline's `custom_field_def` / `custom_field_value` (migrations/001_company.sql, "Custom fields").
- The two checks deferred from STOP 1:
  - a field's `data_type` does not change while values of the old type exist;
  - a Contact field whose label or key looks like a bank number (routing, account number, IBAN, SWIFT, ...) is
    refused, with one sentence pointing to `bank_payee_id` (RP1).

### What the baseline has today (the baseline wins, CLAUDE.md section 5)

- `custom_field_def` has these columns:
  - `record_type`: Contact, Invoice, Bill, Project or Estimate;
  - `field_key`, unique per record type;
  - `label`;
  - `data_type`: Text, Number, Money, Date, Yes/No or Choice;
  - `choices_json`, `is_required`, `is_active` and `sort_order`.
- `custom_field_value` holds one typed column per type: `value_cents` is INTEGER, `value_number` is REAL. At most
  one column is set, and two triggers match the column to the field's type.
- Both tables have audit triggers. `record_id` has no foreign key (it is polymorphic).
- No service exists. Nothing reads or writes these tables.

### Differences between 12.4 and the baseline (report, do not change either without the owner)

| 12.4 proposes | Baseline today | Proposal for STOP C |
|---|---|---|
| `field_definition` / `field_option` / `field_value` | `custom_field_def` / `choices_json` / `custom_field_value` | Keep the baseline names; add columns only where a rule needs one |
| `pack` (Solar, Roofing, Home improvement, Custom) and a stable `key` (`solar.system_kw`) | `field_key` only | Add `pack` (NULL = custom) and `is_builtin`; a pack key carries its pack prefix |
| `help_text`, `on_board_card`, `is_hidden`, `shown_from_stage_id`, `applies_to_job_types` | none of these | `help_text` and `is_hidden` now; `on_board_card`, the stage and the job types wait for the CRM step (there are no `job_type` or pipeline tables, only `service_type` / `service_stage`) |
| `field_option` rows | `choices_json` | Keep `choices_json` (a list of {key, label, is_active}); a used option is deactivated, never removed |
| Value history in `project_change_history` | that table does not exist; the audit triggers log every change | The audit log is the history for now |
| `field_value.project_id` | `record_id` + the field's `record_type` | Keep it; the service checks that the record exists |

### Proposed service: `modules/services/custom_fields.py` (tests first)

- **`list_fields(context, record_type, *, include_hidden=False)`**, for screens and requirement pickers. It needs
  the record type's view permission.
- **`define_field(context, record_type, *, label, data_type, choices=None, help_text=None, is_required=False)`.**
  It derives `field_key` from the label; the key is stable and never changes.
- **`update_field(context, field_id, ...)`.** It changes the label, help text, order, required flag or choices.
  `data_type` changes only while no value of the old type exists (deferred check 1).
- **`hide_field` / `show_field`.** "Removing" a field hides it and its values stay. Built-in pack fields can be
  hidden, never deleted. The service never deletes a definition.
- **`set_value(context, record_type, record_id, field_key, value)`** and **`get_values(context, record_type,
  record_id)`.**
  - Values are typed: money is integer cents (floats, strings and booleans are refused, like ledger amounts),
    dates are ISO, a Choice is one of the active choices, a number is finite.
  - Clearing a value sets every column to NULL.
  - The record must exist.
- **Rules:**
  - At most 15 custom fields per company, counted over every record type (crm_design_log section 5: "per
    company"). Pack fields do not count. Hidden fields still count (owner to confirm; see the questions).
  - The cap is checked in the service inside the write transaction, so two Admins cannot pass it at once.
  - A Contact field whose label or key looks like a bank number is refused, with one sentence pointing to
    `bank_payee_id` (deferred check 2).
  - Field packs are seeded rows with stable keys (`solar.system_kw`, `roofing.squares`, ...). They are added
    when a company turns a pack on, not at company creation, and their keys never change.
- **Permissions:**
  - Defining, updating and hiding a field needs a new code: `fields.manage` (non-sensitive, Company module,
    Full level), or the planned `pipeline.manage` (12.10). Owner to choose; see the questions.
  - Setting a value uses the record's own permission (`customer.manage`, `invoice.create`, `bill.create`,
    `project.manage` with project scope, `estimate.create`).
  - An agent may read values where it may read the record, and never define fields. A value written by an agent
    is a draft change like the rest of its work.
- **Schema (a baseline edit, so the owner lifts the schema hold):** `custom_field_def.pack`, `is_builtin`,
  `help_text` and `is_hidden` (or reuse `is_active` for hidden). Failing tests come first, then the empty
  development databases are rebuilt.
- **Tests first:**
  - each type's value check, with money as integer cents and the trigger as backstop;
  - the cap at 15, with two writers;
  - the data-type change refused while values exist;
  - the bank-number names;
  - a built-in field cannot be deleted, a hidden field keeps its values;
  - permissions for each record type, project scope and the Agent;
  - the audit rows;
  - the static rules (rule 10, H5).

### Open questions for the owner (STOP C)

1. **Field packs, built in or not?** crm_design_log.md section 27 (2026-11-13) is titled "Deal fields are all
   company-defined; no built-in field packs". That seems to replace section 5's built-in packs and FR1's "field
   packs as seeded data". It was not read: the task limited the sources to sections 2-7 and 12. Should STOP C
   follow section 27 (no packs; every field company-defined), or FR1 and section 5? If section 27 wins, does the
   15-field cap still apply?
2. **The cap:** does it count hidden fields, and is it 15 per company across every record type, or 15 per record
   type?
3. **Permission:** a new `fields.manage`, or `pipeline.manage` from 12.10 (which also covers pipeline
   settings that do not exist yet)?
4. **Schema:** keep the baseline names (`custom_field_def`, `choices_json`) rather than 12.4's
   (`field_definition`, `field_option`)? This plan assumes yes.
5. **Stage and job-type visibility** (`shown_from_stage_id`, `applies_to_job_types`, `on_board_card`): wait for
   the CRM step? This plan assumes yes.

## Open points carried forward

- **Owner approval of the STOP C plan above** (FR1: nothing is built until then), and the conflict noted in it:
  crm_design_log section 27 is outside the sections read, so whether it overrides section 5's field packs is open.
- The linked-migration-file test (secrets audit LOW-4) is skipped on this Windows account; run it once with the
  right to create symbolic links (Developer Mode) to see it pass.
- The development master was rebuilt with no Master user (the old file is in Backups/20261117-143536); first run
  creates one.
- Open question 7 (System context and Import-origin entries in `post_journal_entry`); undeposited funds vs
  matching (Phase 4).
- **STOP B notes for the owner:**
  - An add-on is trusted code shipped in the installation (HA3 is the trust boundary). The authorizer limits
    what its SQL can write through the caller's connection; it cannot stop Python code in an add-on from opening
    files or its own connection.
  - An add-on table may not reference a core table (step-reviewer finding 1: a cascade would run the add-on's
    triggers unguarded, and a plain reference would block core deletes). An add-on that needs a link stores the id
    without a foreign key. Confirm, or name the links you want allowed.
  - Add-on data and `addon_schema_version` rows are not audit-logged (no audit triggers on add-on tables; the
    migration runner and handlers write them). Is add-on data inside "the audit log records every change"?
  - Secrets audit LOW-6: an add-on migration at company open makes a full plain copy of the company in `Backups/`
    (the baseline runner does the same), without `company.backup`, retention or a checkpoint. Keep it, or move
    the backup to Phase 2.8/backups work?
  - Not fixed (low): a handler raising `SystemExit` or `KeyboardInterrupt` is not turned into AddonError (the
    transaction still rolls back); `fire` refuses an Agent with no denial row (no Agent path posts today).

## Deferred (unchanged from STOP A)

- **Phase 4 posting services:**
  - `clearing_lines` and `NEW_CLEARING`;
  - `next_invoice_number` and `next_voucher_number`;
  - the voids call `void_document_entry` and `release_allocations`;
  - AR and AP in the chart CSVs.
- Deferral targets in `allocate`.
- **Phase 3 screens:**
  - show the unverified range and the close check's warning;
  - call `App.start_key_store()` after a key replacement;
  - show `KeyReplaced.recovery_code` once;
  - pass `self.app.action_context()` on every post, approval, close, void and correction;
  - show `display_description`;
  - log errors by passing the error object;
  - show `SaveFailedError` like any service error;
  - the import review shows the rounding note;
  - the AQ2 bridge follows RP6 and the token rules in docs/design.md section 1;
  - a screen for several roles per user, which shows MR8's "This removes: ..." before it confirms;
  - Company Settings > Add-ons over `addons.list_addons` / `enable` / `disable`.
- **Backlog 21:** "voids and corrections need a second person" (R42). **KS18:** retired installation keys'
  recovery copies.
- `auth._now()` remains the one allowed clock read in services (H2).
