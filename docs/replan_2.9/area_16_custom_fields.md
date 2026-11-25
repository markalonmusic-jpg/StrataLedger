# Step 2.9 schema replan, area 16: Custom fields (CRM lead fields by service type and stage, User type, board cards)

Status: **DRAFT 2026-11-25, awaiting owner approval; revised for the owner answers of 2:58, 3:05 and 3:09 AM (section 2).** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise**. PROPOSED items in the sources are not built as final.

**This area posts nothing.** A custom field never writes a journal entry, never changes a posted amount and never feeds
a ledger total; the only money rule is integer cents. §5 therefore shows integer-cents examples and states that there is no
entry to balance.

Sources read (only these, searched by section, date or code):
- Owner answers 2026-11-25 2:58 AM (A16-Q1), 3:05 AM (A16-Q2, Q3) and 3:09 AM (A16-Q5, which supersedes the 3:05 AM Q5 line) in Strata_Teams `inbox/to_owner.md` (read-only).
- docs/next_step.md: "Area 16, Custom fields (added 2026-11-23; design chat gap list item 4)", "Still open from STOP C", and the Area 16 lines in the Area 8, 15, 6, 7 and 17 hand-off lists.
- Owner request 2026-11-13, `StrataLedger_mockups/CODE_CHANGES_NEEDED.md` §27, and FR1 as amended (owner 2026-11-17: no field packs, no seeded fields, no cap), quoted in `modules/services/custom_fields.py`.
- Approved areas, by section: 15 (§1.6 and Q23 A as amended here; the service type and stage model of leads), 8 (`service_type`, `service_stage`, stage requirements, `stage_requirements_block`, stage guidance), 6 (§12, Q25 A), 7, 17 (§1, Q1 A),
  13 (Q6 A), 18 (`fields.manage`, audit `event_id`, person pickers, reasons).
- `migrations/001_company.sql` (`custom_field_def`, `custom_field_value`, the two type triggers, the `fields.manage` seed), `modules/services/custom_fields.py`.
- Live mockups (read-only, StrataLedger_mockups): `crm-fields.html`, `job-type-fields.html`, `settings-index.html`, `case-settings.html`, `pm-materials-settings.html`.

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | One definition table | Keep `custom_field_def` and `custom_field_value` (no `deal_field` tables). Add `service_type_id`, `stage_id`, `help_text`, `on_board_card` and `row_version`. |
| 2 | Lead fields hang off a stage | **A CRM custom field belongs to one service type, then one stage, then the field (owner).** The definition carries `service_type_id` and `stage_id`; there is no "Applies to" list and no scope table; reuse is by Copy custom fields. |
| 3 | CRM only | **These fields are for CRM (lead) inquiry only (owner).** Job delivery-stage fields are a separate set, not designed here. |
| 4 | Record types | Add `'Lead'` only. **No custom fields for service cases (owner 3:09 AM); `'Case'` is removed from Area 15 Q23 A.** Estimate, Contact, Invoice, Bill and Project stay company-wide, unscoped. |
| 5 | Service type change | **The old type's values are kept hidden and show again if the lead is switched back; the change is audit-logged (owner).** |
| 6 | User field type | **A User field picks any active user (owner).** A new `value_user_id` column. |
| 7 | Warnings, not limits | More than 2 board-card fields, or over 20 active fields, on one service type shows a warning only (owner request 2026-11-13). |
| 8 | Controls | No new Control. Stage requirements follow Area 8's `stage_requirements_block` (default 0, warn). |

---

## 1. Current state

- **Baseline:** `custom_field_def` (`record_type` CHECK IN Contact, Invoice, Bill, Project, Estimate; `data_type` CHECK IN Text, Number, Money, Date, Yes/No, Choice; `choices_json`; `is_required`; `is_active`; `sort_order`;
  UNIQUE (`record_type`, `field_key`)) and `custom_field_value` (one typed column per type: `value_text`, `value_number`, `value_cents` with an integer CHECK, `value_date`, `value_bool`; UNIQUE (`field_id`, `record_id`); at most one column
  set; two triggers keep the column matched to the field's type). The `fields.manage` permission is seeded sensitive. There is no `help_text`, no board-card flag, no service type or stage, no User type and no `row_version`.
- **Service (`custom_fields.py`):** defining, updating, deactivating and reactivating need `fields.manage` (Admin and the Master, never the Agent); a field is never removed (inactive, values kept); labels are unique per
  record type ignoring case; `field_key` comes from the label and never changes; a Contact field whose name looks like a bank number is refused (RP1); a value is readable exactly when its record is, and set with the
  record's own edit check; a posted invoice or bill value may change unless Lock documents after posting is on or the entry's period is closed; Estimate is refused until an estimate service exists.
- **Live mockups:** `crm-fields.html` (CRM Settings > Custom fields) lists name, type (Text, Number, Money, Date, Pick list, Yes/no), **Applies to** (an "All service types" box and one box per service type), **Shown from** (a stage),
  **On board card**, Active and help text, with "Every custom field here was added by your company. Nothing is built in", the **Busy cards** warning (more than 2 custom fields on board cards for a service type), the **Many fields** warning
  (over 20 active fields, "a warning, not a limit"), Make inactive and Remove, "Saving writes one entry to the audit log", and the note that lead basics are not custom fields. `job-type-fields.html` (Service types and custom fields) lists each
  service type's stages with a Custom fields column and guidance (the owner pointed to it as the pattern: Solar install > Site survey > Roof type and Main panel rating (A); Permitting > Permit number). `case-settings.html` shows four case
  types with Default owner and Due and no custom fields section.

## 2. Decided (owner) and carried forward

- **A16-Q1 (owner 2:58 AM; his words: "these custom fields belong to one service type > Stage > Custom Field. But these custom fields are just used for CRM related inquiry."):** a CRM custom field belongs to one service type, then one
  stage, then the field, as on the Service types and custom fields page (Solar install > Site survey > Roof type). These are lead (CRM) fields only; job delivery-stage fields stay a separate set. Planning reading (owner may correct): the stage
  replaces "Shown from"; the "Applies to" list and a scope table go away; reuse is by Copy custom fields; a required field is required from its own stage (A16-Q4).
- **A16-Q2 (owner 3:05 AM):** when a lead's service type changes, the old type's values are kept hidden; they show again if the lead is switched back; the change is audit-logged. Example: a Residential solar lead with Roof type "Tile" switched to Roofing
  keeps "Tile" stored, not shown.
- **A16-Q3 (owner 3:05 AM):** a User field picks any active user (no role filter).
- **A16-Q5 (owner 3:09 AM; his words: "only have these on case types."):** no custom fields for service cases. Case types carry only Type, Default owner and Due (business days), as on the live Case settings page; no case custom fields section is added to the mockups.
  This **removes `'Case'` from Area 15 Q23 A** (Area 15 gets a pointer).
- **Owner request 2026-11-13 (C27) and FR1 (owner 2026-11-17):** all fields are company-defined, no built-in packs, no seeded fields, no cap; each field has a name, type, help text, on board card and active; every field can be added, edited, renamed,
  made inactive or removed, **removing keeps the entered values** and Make inactive is offered first; **warnings, not limits**: more than 2 fields on board cards for a service type, and more than 20 active fields on a service type; deal basics (value, expected close
  date, owner, contacts, lead source) are core columns, not fields; the lead page shows "<service type> details"; the pipeline Columns menu has "Deal basics" and "Your fields"; stage requirements ("Field filled") pick from both.
- **Owner answers carried (2026-11-18, STOP C):** defining needs `fields.manage` (Admin and the Master only); a field is never removed; a Contact field named like a bank number is refused; a value is readable exactly when its record is and set with the record's own
  edit check; a posted invoice or bill value may change unless Lock documents after posting is on or the period is closed.
- **Carried:** Area 15 Q23 A adds `'Lead'` to `record_type` (its `'Case'` is withdrawn above); Area 6 Q25 A: Estimate values attach to `estimate`; area locks on custom-field edits follow Area 13 Q6 A; Area 17 Q1 A offers every active custom field
  by its immutable `field_key`; stage requirements warn unless `company_settings.stage_requirements_block` is 1 (Area 8). The User type and Lead scoping came from the design chat gap list item 4 (2026-11-23), an input.

---

## 3. Schema (planning proposals, owner may revise)

- **`custom_field_def`** (changed):

  | Column | Change |
  |--------|--------|
  | `record_type` | CHECK gains `'Lead'` only (Area 15 Q23 A, `'Case'` withdrawn). |
  | `data_type` | CHECK gains `'User'`. The mockup's "Pick list" is the stored `'Choice'`. |
  | `service_type_id` | new, INTEGER NULL FK `service_type` (Area 8). **Set exactly when `record_type` = 'Lead'** (owner: one service type per CRM field); NULL for every other record type (service check; SQL cannot read the record type of another row). |
  | `stage_id` | new, INTEGER NULL FK `service_stage` (Area 8). **Set exactly when `service_type_id` is set;** the stage must belong to that service type (service check). The stage replaces "Shown from". |
  | `help_text` | new, TEXT NULL, CHECK NULL or length(trim) <= 200. |
  | `on_board_card` | new, INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1); the service refuses 1 unless the record type is Lead (the pipeline board). |
  | `row_version` | new, INTEGER NOT NULL DEFAULT 1 (Area 21 stale-save refusal). |

  Uniqueness: `field_key` stays UNIQUE per `record_type` (it comes from the label, with a numeric suffix on a collision, and never changes); **the label is unique per (`record_type`, `service_type_id`) ignoring case**, so "Roof type" may exist on both Solar install and
  Roofing as two definitions (service rule, checked in the write transaction; inactive fields count). Area 17's registry shows a Lead field with its service type name beside its label.
- **`custom_field_value`** (changed): new `value_user_id` INTEGER NULL (a master user id, a plain integer with no cross-file FK, like every user id in a company file); the "at most one column set" CHECK and the two type triggers gain it
  (`'User'` uses `value_user_id`). `value_cents` stays integer-checked; `value_number` stays REAL for quantities (rule 1).
- **No scope table:** the `custom_field_service_type` table of the 30aad67 draft is dropped (owner A16-Q1). **No `deal_field` tables** (C27's names are replaced by the baseline's). **No cap column. No "show in reports" flag** (Area 17 Q1 A).

## 4. Rules (`custom_fields.py`, extended)

1. **A Lead field belongs to one service type and one stage** (owner). It shows on a lead only while the lead's service type equals the field's, and **from the field's stage onward** (planning reading: the stage replaces Shown from, and the lead page groups fields under their stage).
   Before that stage the field is hidden and cannot be set; a stage move never deletes a value; moving back hides, not clears.
2. **Service type change (owner A16-Q2):** when a lead's service type changes (Area 15 allows it only while no estimate names the lead), the old type's values stay stored and are hidden; they show again if the lead is switched back; the change is audit-logged (the lead's own audit
   trigger and `lead_stage_history`, Area 15; nothing extra is written by this area).
3. **Required (planning reading, A16-Q4):** `is_required` applies from the field's own stage onward and only to leads of its service type. A save missing a required value is refused naming the field. A stage requirement "Field filled" (Area 8's stage triggers) references `field_id` and
   **warns, or blocks only when `stage_requirements_block` = 1** (default 0).
4. **User type (owner A16-Q3):** the value is the id of **any active company user** (Area 18's person pickers, 11-17 item 4), no role filter; the picker shows the current name; a user later deactivated stays on old values, shown "(inactive)", and cannot be picked for a new value. The Agent never sets a value.
5. **Copy custom fields** (`copy_fields(from_service_type_id, to_service_type_id, field_ids)`): for each chosen Lead field it **creates a new definition on the target service type** (same label, type, choices, help text, board-card flag), with the stage of the same name in the target type, else the stage with the same role;
   a field with no matching stage is skipped and listed so an Admin places it (planning proposal; A16-Q7). A label already used on the target is skipped and listed. Copy never moves values.
6. **Remove is Make inactive** (FR1): a field is never deleted; inactive fields keep values, are not offered on new records, and still resolve in saved report definitions (Area 17). Reactivating restores them.
7. **Warnings, not limits (owner request 2026-11-13):** `list_fields` returns, per service type, a "Busy cards" warning when more than 2 active Lead fields of that type have `on_board_card` = 1, and a "Many fields" warning when more than 20 are active; saving is never refused. Inactive fields do not count. Both are information, not Controls.
8. **Locks:** a value on a posted Invoice or Bill follows Area 13 Q6 A (refused when the entry's period is closed, when Lock documents after posting is on, or when the document's area is locked; no account locks); values on Contact, Project, Estimate and Lead have no posting period and are
   editable under the record's own edit check.
9. **Permissions:** defining, copying and deactivating need `fields.manage` (sensitive, Admin and the Master, none in `AGENT_ALLOWED`); a value is readable exactly when its record is (a Lead by Area 15's read check, an Estimate by Area 6's) and set with the record's own edit check; the Contact bank-number refusal stays.
10. **Audit:** every definition and value change is audited by the trigger pattern; the settings page's Save applies all pending edits in one transaction and tags the audit rows with one `event_id`, so the screen shows "one entry" while the log keeps a row per change (Area 18). A reason is not required
    (Area 18 Q15 A: reasons are for controls).
11. **Job delivery-stage fields are a separate set (owner A16-Q1) and are not designed here.** Project custom fields stay as today: company-wide, unscoped. Per-stage fields on the job page (the Custom fields column of `job-type-fields.html`) are listed as open (§10); Area 8 owns stage guidance only.

## 5. Worked examples, integer cents (no entries to balance)

- **Money field.** A Project field "Permit fee" (Money). Typing "1,250.00" stores `value_cents` 125000; typing "875.50" on another job stores 87550. The sum of the two in a report is 125000 + 87550 = 212550 cents, shown $2,125.50. "12.345", "1e3" and "$-" are refused by the shared
  money parser; the stored value is never a float (rule 1).
- **Posting.** No custom field posts: the Permit fee changes no ledger line, no job cost and no invoice total, so there is no journal entry here and nothing to balance. A static test checks that `custom_fields.py` imports neither `ledger` nor any posting service.
- **Service type, stage and the owner's pattern.** Solar install > Site survey > "Roof type" (Pick list: Tile, Shingle, Metal) and "Main panel rating (A)" (Number); Permitting > "Permit number" (Text). A Residential solar lead in "New lead" shows none of them; at "Site survey" it shows Roof type and Main panel rating; at "Permitting" it also shows Permit number.
  A Roofing lead never shows Solar install's fields; Roofing has its own "Roof type" definition.
- **Service type change (owner A16-Q2).** A lead with Roof type "Tile" is switched from Residential solar to Roofing: "Tile" stays stored and is not shown (Roofing's Roof type is a different, empty field); switching back shows "Tile" again; the change is in the audit log.
- **Warnings.** Residential solar has three active Lead fields with On board card: the list shows "More than 2 custom fields on board cards for Residential solar" and every save still works. A 21st active field shows "Over 20 active custom fields on Residential solar" and saves.
- **User field.** "Site safety lead" (User) on a Lead holds user id 41 (Dana Reyes); it shows "Dana Reyes". When Dana is deactivated it shows "Dana Reyes (inactive)"; a new lead cannot pick her; any other active user can be picked.

## 6. Tests (planning proposals)

`test_custom_field_def_keeps_one_table_for_every_record_type_and_has_no_deal_field_tables`, `test_lead_is_a_record_type_and_case_is_not`, `test_no_custom_fields_for_service_cases_and_case_types_carry_only_type_default_owner_and_due`,
`test_lead_field_requires_one_service_type_and_one_stage_and_other_record_types_have_neither`, `test_stage_must_belong_to_the_fields_service_type`, `test_no_custom_field_scope_table_exists`,
`test_lead_field_is_hidden_before_its_stage_and_value_kept_when_the_lead_moves_back`, `test_lead_does_not_show_another_service_types_fields`,
`test_service_type_change_keeps_old_values_hidden_shows_them_again_on_switch_back_and_is_audit_logged` (owner A16-Q2), `test_label_unique_per_record_type_and_service_type_ignoring_case_so_two_types_may_each_have_roof_type`,
`test_field_key_unique_per_record_type_and_never_changes`, `test_required_field_applies_only_from_its_own_stage_and_its_service_type`, `test_stage_requirement_field_filled_warns_unless_stage_requirements_block_is_on`,
`test_user_field_stores_an_active_company_user_id_in_value_user_id`, `test_user_field_has_no_role_filter_and_shows_inactive_user_on_old_values_but_refuses_them_on_new` (owner A16-Q3),
`test_custom_field_value_type_triggers_accept_value_user_id_only_for_user_fields`, `test_agent_cannot_set_a_custom_field_value`, `test_copy_fields_creates_new_definitions_on_the_target_type_with_the_same_named_stage_and_lists_skipped`,
`test_copy_fields_never_moves_values`, `test_remove_is_make_inactive_and_values_and_history_stay`, `test_inactive_field_still_resolves_in_a_saved_report_definition`,
`test_busy_cards_warning_over_2_board_card_fields_per_service_type_never_blocks_a_save`, `test_many_fields_warning_over_20_active_fields_per_service_type_never_blocks_a_save`,
`test_on_board_card_refused_for_every_record_type_but_lead`, `test_contact_field_named_like_a_bank_number_is_refused`, `test_money_field_is_integer_cents_and_refuses_more_than_two_decimals`,
`test_custom_fields_service_posts_nothing_and_imports_no_ledger`, `test_posted_invoice_value_edit_refused_when_period_closed_or_lock_documents_on_or_area_locked`,
`test_defining_needs_fields_manage_and_is_not_in_agent_allowed`, `test_settings_save_writes_one_event_id_with_a_row_per_change`, `test_custom_field_def_row_version_stale_save_is_refused`.

## 7. How it lands in the baselines and the existing code

- **Company baseline:** the `custom_field_def` columns above, the CHECK widenings (`'Lead'`, `'User'`), `custom_field_value.value_user_id`, the revised sum CHECK and both type triggers, audit triggers for the new columns. No new table. Development databases are blocked and rebuilt (CLAUDE.md section 5.2; ask first).
- **Code:** `custom_fields.py` gains the service type and stage rule, board-card, help, User type, copy and the warnings; `RECORD_TYPES` gains Lead (and Estimate) when `leads.py` and `estimates.py` exist (until then they are refused with the existing sentence). No UI, OS or HTTP imports (H1), no clock reads (H2),
  no triggers for workflow (H4), no SQLite-only SQL (H5).
- **Existing tests change:** the test that Estimate is refused becomes the test that it is allowed once `estimates.py` exists; tests that count the data types or record types.
- **Handoffs out:** Area 8 (a stage requirement "Field filled" references `field_id`), Area 15 (the lead page "<service type> details", pipeline Columns "Your fields", board cards; `'Case'` removed from Q23 A), Area 6 (estimate values stay unscoped), Area 17 (the registry shows a Lead field with its service type), Area 18 (audit `event_id`),
  Area 21 (`row_version`).

## 8. Conflicts with decisions, the baseline or the mockups (flagged)

1. **C27 names three tables (`deal_field`, `deal_field_job_type`, `deal_field_value`);** the baseline already has `custom_field_def` and `custom_field_value`. This area keeps the baseline tables and drops the scope table of the first draft (§3).
2. **C27 and the mockup say "job type" and "deal";** the approved model says service type and lead (Area 8 Q1; Area 15). Work order for the wording.
3. **The mockup's "Applies to" multi-select and "Shown from" select** (`crm-fields.html`, `pages/crm-fields.js`) contradict the owner's one service type > stage > field. Work order: replace them with a Service type pick and a Stage pick, and add Copy custom fields.
4. **No User type in the mockup** (its types are Text, Number, Money, Date, Pick list, Yes/no); the type is added from the design-chat gap list (work order).
5. **"Remove" in the mockup versus the baseline's never-deleted rule:** Remove must stay Make inactive (§4 rule 6).
6. **"Saving writes one entry to the audit log" versus row-level audit triggers:** resolved with one `event_id` per Save (§4 rule 10).
7. **Two pages, two sets:** the CRM Custom fields page (lead fields, this area) and the Service types and custom fields page (job delivery-stage fields, not designed here) look alike and share the service type > stage > field pattern; they must not share definitions (work order).
8. **Area 15 Q23 A (owner-approved) adds `'Lead'` and `'Case'`;** the owner's 3:09 AM answer removes `'Case'` (pointer in Area 15). Area 15's lines about case custom fields (§0 item and the Area 16 hand-off) are corrected by that pointer.
9. **Areas 7 and 8 said Area 16 would carry per-stage job fields** ("job custom fields per stage and service type"); the owner's answer keeps job delivery-stage fields a separate set, so those hand-offs are open again (pointers).
10. **Area 17 Q1 offered a per-field "Show in reports" flag as option B;** the owner chose A, so this area adds none.
11. **A Lead field's `field_key` must be unique per record type while two service types may reuse a label:** keys take a numeric suffix on a collision (§3); Area 17's `cf.lead.<key>` stays unique.

## 9. Questions for the owner (recommended option first, with an example)

The owner answers A16-Q1, Q2, Q3 and Q5 are in §2 (A16-Q4 follows from Q1, a planning reading). Three small points remain:

- **A16-Q6. Is a Lead field visible only from its stage onward, or only while the lead is in that stage?**
  (A) From its stage onward, so the Roof type entered at Site survey stays visible at Permitting (recommended: nothing disappears as the lead advances).
  (B) Only while the lead is in that stage.
  Example: Roof type entered at "Site survey" is still shown when the lead reaches "Permitting" under A.
- **A16-Q7. When Copy custom fields cannot find a matching stage in the target service type, what happens?**
  (A) The field is skipped and listed so an Admin places it (recommended: no field lands on a wrong stage).
  (B) It is placed on the target's first stage.
  Example: copying "Permit number" from Solar install to Roofing, which has no "Permitting" stage.
- **A16-Q8. Job delivery-stage fields.**
  (A) Design them later with the job pages, as their own set (recommended: the owner called them separate).
  (B) Design them in this area now.
  Example: "Inverter serial" collected at the Install stage of a job.

## 10. Open items (not decisions)

- Job delivery-stage custom fields (A16-Q8) and the Custom fields column of `job-type-fields.html`.
- Contact, Invoice and Bill field settings pages; per-field permissions (hiding a field from some roles).
- Conditional fields, calculated fields and formulas; attachments or multi-select choice types.
- Importing and exporting field definitions and bulk-filling a field.
- Whether a field is also offered on the lead's estimate or contract (Estimate fields stay company-wide and unscoped, Area 6 Q25 A).
