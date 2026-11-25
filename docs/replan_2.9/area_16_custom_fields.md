# Step 2.9 schema replan, area 16: Custom fields (scoping, stages, board cards, User type)

Status: **DRAFT 2026-11-25, awaiting owner approval.** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise**. PROPOSED items in the sources are not built as final.

**This area posts nothing.** A custom field never writes a journal entry, never changes a posted amount and never feeds
a ledger total; the only money rule is integer cents. §5 therefore shows integer-cents examples and states that there is no
entry to balance.

Sources read (only these, searched by section, date or code):
- docs/next_step.md: "Area 16, Custom fields (added 2026-11-23; design chat gap list item 4)", "Still open from STOP C" (custom field
  columns `help_text`, on board card, shown from stage, job types), and the Area 16 lines in the Area 8, 15, 6, 7 and 17 hand-off lists.
- Owner request 2026-11-13, `StrataLedger_mockups/CODE_CHANGES_NEEDED.md` §27 ("Deal fields are all company-defined; no built-in field
  packs"), and FR1 as amended (owner 2026-11-17: no field packs, no seeded fields, no cap), quoted in `modules/services/custom_fields.py`.
- Approved areas, by section: 15 (§1.6 and Q23 A: `'Lead'` and `'Case'` in `record_type`; the scoping columns are Area 16's), 8 (per-stage custom
  fields stay here; stage `guidance` is Area 8's; `stage_requirements_block`; stage requirements), 6 (§12 and Q25 A: Estimate values attach to
  `estimate`), 7 (job custom fields per stage and service type), 17 (§1 the field registry joins custom fields by `field_key`; Q1 A), 13 (Q6 A: area locks on
  custom-field edits), 18 (`fields.manage`, audit `event_id`, reasons).
- `migrations/001_company.sql` (`custom_field_def`, `custom_field_value`, the two type triggers, the `fields.manage` seed, the audit triggers),
  `modules/services/custom_fields.py` (read for the rules it already enforces).
- Live mockups (read-only, StrataLedger_mockups): `crm-fields.html` (CRM Settings > Custom fields), `job-type-fields.html` (service types, stages and
  fields), `settings-index.html`, `case-settings.html`, `pm-materials-settings.html`.

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | One definition table | Keep `custom_field_def` and `custom_field_value` (no `deal_field` tables). Add `help_text`, `on_board_card` and `row_version` to the definition. |
| 2 | Record types | Add `'Lead'` and `'Case'` (Area 15 Q23 A); lift the Estimate refusal (Area 6 Q25 A). Contact, Invoice, Bill and Project stay. |
| 3 | Scope by service type | A new child table says which service types a field applies to, and from which stage it shows, per type. No rows = all service types. |
| 4 | User field type | A new data type `'User'` stores a company user id in its own typed column. |
| 5 | Warnings, not limits | More than 2 board-card fields, or more than 20 active fields, on one service type shows a warning only (owner request 2026-11-13). |
| 6 | Nothing built in | No field packs, no seeded fields, no cap (FR1). Remove is Make inactive: values and history stay. |
| 7 | Controls | No new Control. Stage requirements follow Area 8's `stage_requirements_block` (default 0, warn). |

---

## 1. Current state

- **Baseline:** `custom_field_def` (`record_type` CHECK IN Contact, Invoice, Bill, Project, Estimate; `data_type` CHECK IN Text, Number, Money, Date, Yes/No, Choice; `choices_json`;
  `is_required`; `is_active`; `sort_order`; UNIQUE (`record_type`, `field_key`)) and `custom_field_value` (one typed column per type: `value_text`, `value_number`, `value_cents` with an integer CHECK,
  `value_date`, `value_bool`; UNIQUE (`field_id`, `record_id`); at most one column set; two triggers keep the column matched to the field's type). The `fields.manage` permission is seeded sensitive.
  There is no `help_text`, no board-card flag, no service type scope, no stage, no User type and no `row_version`.
- **Service (`custom_fields.py`):** defining, updating, deactivating and reactivating need `fields.manage` (Admin and the Master, never the Agent); a field is never removed (inactive, values kept); labels are unique per
  record type ignoring case, checked in the write transaction; `field_key` comes from the label and never changes; a Contact field whose name looks like a bank number is refused (RP1); a value is readable exactly when its record
  is, and set with the record's own edit check; a posted invoice or bill value may change unless Lock documents after posting is on or the entry's period is closed; Estimate is refused until an estimate service exists. The audit
  triggers keep old and new values.
- **Live mockups:** `crm-fields.html` is the CRM Settings > Custom fields list: name, type (Text, Number, Money, Date, Pick list, Yes/no), **Applies to** (an "All service types" box and one box per type), **Shown from** (the first stage where the
  field appears on the lead), **On board card**, Active, help text; the line "Every custom field here was added by your company. Nothing is built in"; two warnings (**Busy cards**: more than 2 custom fields on board cards for a service
  type; **Many fields**: over 20 active fields, "a warning, not a limit"); Make inactive and Remove; "Saving writes one entry to the audit log"; and the note that lead basics (value, expected close date, sales rep, contacts,
  lead source) are not custom fields. `job-type-fields.html` lists each service type's stages with a **Custom fields** column and guidance; `settings-index.html` points Service types to "defaults, payment schedule and custom
  fields".

## 2. Decided (owner) and carried forward

- **Owner request 2026-11-13 (C27) and FR1 as amended (owner 2026-11-17):** one list of fields per company, all company-defined; no built-in field packs, no seeded fields, no cap. Each field has a name, type, applies to
  (all service types or chosen ones), shown from stage, on board card, active, and help text. Every field can be added, edited, renamed, made inactive or removed; **removing keeps the entered values** and "Make inactive"
  is offered first; "Copy fields to another service type" helps set up a new type; **warnings, not limits**: more than 2 fields on board cards for a service type, and more than 20 active fields on a service type
  (the old hard limit of 15 is gone); field names are unique per company (here, per record type, ignoring case); deal basics (value, expected close date, owner, contacts, lead source) are core columns, not fields; the lead page
  shows "<service type> details" with the fields that apply; the pipeline Columns menu has "Deal basics" and "Your fields"; stage requirements ("Field filled") pick from both.
- **Owner answers carried (2026-11-18, STOP C):** defining needs `fields.manage` (Admin and the Master only); labels are unique per record type ignoring case; a field is never removed; a Contact field named like a bank number is
  refused; a value is readable exactly when its record is and set with the record's own edit check; a posted invoice or bill value may change unless Lock documents after posting is on or the period is closed.
- **Area 15 Q23 A (owner-approved):** `'Lead'` and `'Case'` join `custom_field_def.record_type`; the scoping columns are this area's. **Area 6 Q25 A:** Estimate values attach to `estimate`, shared by its revisions.
- **Design chat gap list item 4 (2026-11-23), an input, not an owner rule:** a custom field of type User, and Lead scoping.
- **Carried:** area locks on custom-field edits are answered by Area 13 Q6 A (closed period, `lock_documents_after_posting` and the document's area lock; no account locks); Area 17 Q1 A: every active custom field of a covered record type is
  offered in the field registry by its immutable `field_key`, and an inactive field still resolves in saved definitions; stage requirements warn unless `company_settings.stage_requirements_block` is 1 (Area 8).

---

## 3. Schema (planning proposals, owner may revise)

- **`custom_field_def`** (changed):

  | Column | Change |
  |--------|--------|
  | `record_type` | CHECK gains `'Lead'` and `'Case'` (Area 15 Q23 A). |
  | `data_type` | CHECK gains `'User'`. The mockup's "Pick list" is the stored `'Choice'`. |
  | `help_text` | new, TEXT NULL, CHECK NULL or length(trim) <= 200. |
  | `on_board_card` | new, INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1); the service refuses 1 unless the record type is Lead or Project (the two board types). |
  | `row_version` | new, INTEGER NOT NULL DEFAULT 1 (Area 21 stale-save refusal). |

- **`custom_field_service_type`** (new; the scope): `field_id` FK `custom_field_def`; `service_type_id` FK `service_type` (Area 8); `shown_from_stage_id` INTEGER NULL FK `service_stage` (NULL = shown from the first stage);
  PK (`field_id`, `service_type_id`). **No rows means the field applies to all service types.** Service checks: rows are allowed only for record types Lead, Project and Estimate (the types that carry a service type; Estimate through its
  lead or job); `shown_from_stage_id` must be a stage of that service type. Stage is per row because stages belong to one service type.
- **`custom_field_value`** (changed): new `value_user_id` INTEGER NULL (a master user id, a plain integer with no cross-file FK, like every user id in a company file); the "at most one column set" CHECK and the two type triggers
  gain it (`'User'` uses `value_user_id`). `value_cents` stays an integer-checked column; `value_number` stays REAL for quantities (rule 1).
- **No `deal_field`, `deal_field_job_type` or `deal_field_value` tables** (C27's names are replaced by the baseline's): there is one definition table for every record type.
- **Not new:** no "show in reports" flag (Area 17 Q1 A offers every active field); no cap or limit column.

## 4. Rules (`custom_fields.py`, extended)

1. **Applies to a record:** a field applies when it has no scope rows, or the record's service type has a scope row. A lead, job or estimate with another service type does not show it.
2. **Shown from stage:** a field shows on a record once its stage is at or after the scope row's `shown_from_stage_id` (by the service type's stage order); before that it is hidden and cannot be set. A stage move
   never deletes a value. Moving a record back, or to a service type where the field does not apply, **hides** the value without clearing it; it shows again when it applies (planning proposal; A16-Q2).
3. **Required:** `is_required` applies only to records the field applies to, and only once the record has reached the shown-from stage (planning proposal; A16-Q4). A save missing a required value is refused naming the field.
   A stage requirement "Field filled" (Area 8's stage triggers) references `field_id` and **warns, or blocks only when `stage_requirements_block` = 1** (default 0).
4. **User type:** the value is the id of an active company user with access to the company (Area 18's person pickers, 11-17 item 4); the picker shows the user's current name; a user who is later deactivated stays on old values,
   shown "(inactive)", and cannot be picked for a new value. The Agent never sets a value.
5. **Copy fields** (`copy_fields(from_service_type_id, to_service_type_id, field_ids)`): adds a scope row for the target service type to each chosen field (a field already scoped "all" is left alone); it never creates a
   duplicate definition (labels are unique per record type). `shown_from_stage_id` maps to the target type's stage with the same role, otherwise NULL.
6. **Remove is Make inactive** (FR1): a field is never deleted; inactive fields keep values, are not offered on new records, and still resolve in saved report definitions (Area 17). Reactivating restores them.
7. **Warnings, not limits (owner request 2026-11-13):** `list_fields` returns, per service type, a "Busy cards" warning when more than 2 active fields have `on_board_card` = 1, and a "Many fields" warning when more than 20
   fields are active; saving is never refused. Inactive fields do not count. The two warnings are information, not Controls.
8. **Locks:** a value on a posted Invoice or Bill follows Area 13 Q6 A (refused when the entry's period is closed, when Lock documents after posting is on, or when the document's area is locked; no account locks); values on
   Contact, Project, Estimate, Lead and Case have no posting period and are editable under the record's own edit check.
9. **Permissions:** defining, scoping, copying and deactivating need `fields.manage` (sensitive, Admin and the Master, none in `AGENT_ALLOWED`); a value is readable exactly when its record is (Lead and Case by Area 15's read checks,
   Estimate by Area 6's) and set with the record's own edit check; the existing Contact bank-number refusal stays.
10. **Audit:** every definition, scope and value change is audited by the trigger pattern; the settings page's Save applies all pending edits in one transaction and tags the audit rows with one `event_id`, so the screen shows
    "one entry" while the log keeps a row per change (Area 18). A reason is not required (Area 18 Q15 A: reasons are for controls).

## 5. Worked examples, integer cents (no entries to balance)

- **Money field.** A Project field "Permit fee" (Money). Typing "1,250.00" stores `value_cents` 125000; typing "875.50" on another job stores 87550. The sum of the two values in a report is 125000 + 87550 = 212550 cents, shown $2,125.50.
  "12.345", "1e3" and "$-" are refused by the shared money parser; the stored value is never a float (rule 1).
- **Posting.** No custom field posts: the Permit fee changes no ledger line, no job cost and no invoice total, so there is no journal entry here and nothing to balance. A static test checks that `custom_fields.py` imports
  neither `ledger` nor any posting service.
- **Scope and stage.** "Roof pitch" (Number) applies to Roofing only, shown from the stage "Site assessed". A Roofing lead in "Qualified" does not show it; when the lead moves to "Site assessed" it shows empty; a Residential solar lead never shows it.
  If the field is required, a Roofing lead can leave "Qualified" without it but is refused saving the move to "Proposal reviewed" without it (A16-Q4).
- **Warnings.** Residential solar has three active fields with On board card: the list shows "More than 2 custom fields on board cards for Residential solar" and every save still works. Adding a 21st active field shows "Over 20 active custom fields on
  Residential solar" and saves.
- **User field.** "Site safety lead" (User) on a Project holds user id 41 (Dana Reyes); the job shows "Dana Reyes". When Dana is deactivated the job shows "Dana Reyes (inactive)"; a new job cannot pick her.

## 6. Tests (planning proposals)

`test_custom_field_def_keeps_one_table_for_every_record_type_and_has_no_deal_field_tables`, `test_lead_and_case_are_record_types_and_estimate_refusal_is_lifted_with_its_service`,
`test_field_with_no_scope_rows_applies_to_all_service_types`, `test_field_scoped_to_roofing_is_not_shown_on_a_residential_solar_lead`,
`test_scope_rows_refused_for_contact_invoice_bill_and_case_record_types`, `test_shown_from_stage_must_belong_to_the_scope_rows_service_type`,
`test_field_hidden_before_its_stage_and_value_kept_when_the_record_moves_back`, `test_value_kept_hidden_when_the_record_moves_to_a_service_type_where_it_does_not_apply`,
`test_required_field_applies_only_from_its_shown_from_stage`, `test_stage_requirement_field_filled_warns_unless_stage_requirements_block_is_on`,
`test_user_field_stores_an_active_company_user_id_in_value_user_id`, `test_user_field_shows_inactive_user_on_old_values_and_refuses_them_on_new`,
`test_custom_field_value_type_triggers_accept_value_user_id_only_for_user_fields`, `test_agent_cannot_set_a_custom_field_value`,
`test_copy_fields_adds_scope_rows_and_never_duplicates_a_definition`, `test_remove_is_make_inactive_and_values_and_history_stay`,
`test_inactive_field_still_resolves_in_a_saved_report_definition`, `test_busy_cards_warning_over_2_board_card_fields_never_blocks_a_save`,
`test_many_fields_warning_over_20_active_fields_never_blocks_a_save`, `test_on_board_card_refused_for_record_types_without_a_board`,
`test_field_label_unique_per_record_type_ignoring_case_and_field_key_never_changes`, `test_contact_field_named_like_a_bank_number_is_refused`,
`test_money_field_is_integer_cents_and_refuses_more_than_two_decimals`, `test_custom_fields_service_posts_nothing_and_imports_no_ledger`,
`test_posted_invoice_value_edit_refused_when_period_closed_or_lock_documents_on_or_area_locked`, `test_defining_needs_fields_manage_and_is_not_in_agent_allowed`,
`test_settings_save_writes_one_event_id_with_a_row_per_change`, `test_custom_field_def_row_version_stale_save_is_refused`.

## 7. How it lands in the baselines and the existing code

- **Company baseline:** the `custom_field_def` columns above, the CHECK widenings, `custom_field_service_type`, `custom_field_value.value_user_id`, the revised sum CHECK and both type triggers, audit triggers for the new table and columns.
  Development databases are blocked and rebuilt (CLAUDE.md section 5.2; ask first).
- **Code:** `custom_fields.py` gains scope, stage, board-card, help, User type, copy and the warnings; `RECORD_TYPES` gains Lead, Case and Estimate when `leads.py`, `cases.py` and `estimates.py` exist (until then they are refused with
  the existing sentence). No UI, OS or HTTP imports (H1), no clock reads (H2), no triggers for workflow (H4), no SQLite-only SQL (H5).
- **Existing tests change:** the test that Estimate is refused becomes the test that it is allowed once `estimates.py` exists; tests that count the data types or record types.
- **Handoffs out:** Area 8 (stage requirement "Field filled" references `field_id`; the Custom fields column on `job-type-fields.html`), Area 15 (the lead page "<service type> details", pipeline Columns "Your fields", board cards),
  Area 6 (estimate values), Area 17 (the registry reads the new fields; nothing to add), Area 18 (the audit `event_id`), Area 21 (`row_version`).

## 8. Conflicts with decisions, the baseline or the mockups (flagged)

1. **C27 names three tables (`deal_field`, `deal_field_job_type`, `deal_field_value`);** the baseline already has `custom_field_def` and `custom_field_value`, and Area 15 Q23 A adds Lead and Case to them. This area keeps the baseline tables (§3).
2. **C27 and the mockup say "job type" and "deal";** the approved model says service type and lead (Area 8 Q1; Area 15). The mockup page title "Job types" and C27's "job type" wording are work orders.
3. **"Applies to" in the mockup is already a multi-select** (an "All service types" box and one per type), and C27 says "chosen job types"; the schema matches it (§3). A16-Q1 still asks whether to keep that model; no mockup change is needed.
4. **No User type in the mockup** (its types are Text, Number, Money, Date, Pick list, Yes/no); the type is added from the design-chat gap list (work order).
5. **"Remove" in the mockup versus the baseline's never-deleted rule:** Remove must stay Make inactive (§4 rule 6).
6. **"Saving writes one entry to the audit log" versus row-level audit triggers:** resolved with one `event_id` per Save (§4 rule 10).
7. **The mockup's Custom fields page covers leads only;** `job-type-fields.html` shows a per-stage fields column for jobs and `pm-materials-settings.html` a "Service types and custom fields" link. Both must read this one definition table (work order); Contact, Invoice and Bill fields keep their existing settings entry.
8. **Area 17 Q1 offered a per-field "Show in reports" flag as option B;** the owner chose A (every active field offered), so this area adds no such flag.
9. **Case fields have no scoping here:** a case has a case type, not a service type; Area 15's case types are not a scope in this draft (open item).

## 9. Questions for the owner (recommended option first, with an example)

- **A16-Q1. Can one field apply to several service types?**
  (A) Yes, a field has one scope row per service type it applies to, each with its own shown-from stage (recommended: one definition, no duplicates).
  (B) One service type per field; a field used by two types is defined twice.
  Example: "Roof pitch" applies to Roofing and Home improvement, shown from "Site assessed" and "Estimate sent".
- **A16-Q2. When a lead moves to a service type where a field does not apply, what happens to its value?**
  (A) It is kept hidden and shows again if the lead moves back (recommended: nothing is lost).
  (B) It is cleared on the move.
  Example: a Roofing lead with Roof pitch 6 moves to Solar; moving it back shows 6 again under A.
- **A16-Q3. Who can be picked in a User field?**
  (A) Any active company user (recommended: simple).
  (B) Only users holding a chosen role, set on the field.
  Example: "Site safety lead" lists every active user under A, only Foremen under B.
- **A16-Q4. Does "Required" apply from the start or from the field's shown-from stage?**
  (A) From its shown-from stage (recommended: a field hidden at an early stage cannot block it).
  (B) From the start, whatever the stage.
  Example: "Roof pitch" required, shown from "Site assessed": under A a lead can be Qualified without it.
- **A16-Q5. Should case custom fields be scoped by case type now?**
  (A) No: every case field applies to all cases (recommended: Area 15's case types are a short list and cases are simple).
  (B) Yes, scope by case type with a second scope table.
  Example: "Warranty claim number" on Warranty cases only.

## 10. Open items (not decisions)

- Case scoping by case type (A16-Q5) and Contact, Invoice and Bill field settings pages.
- Per-field permissions (hiding a field from some roles) are not designed.
- Conditional fields (show B only when A has a value), calculated fields and formulas are out of scope.
- Importing and exporting field definitions and bulk-filling a field.
- A field type for attachments or multi-select choices.
