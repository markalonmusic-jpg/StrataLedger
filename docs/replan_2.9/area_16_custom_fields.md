# Step 2.9 schema replan, area 16: Custom fields (CRM lead fields by service type and stage, User type, board cards)

Status: **Owner-approved 2026-11-25 1:18 PM (23a8b6b); drafted 2026-11-25; revised for the owner answers of 2:58, 3:05, 3:09, 3:47 AM and 11:39 AM (section 2); no open owner questions.** Docs only: nothing here changes code, a baseline, a migration
or a test. Every table, column, code and check below would be built only in the 2.9 baseline pass, after the replan
is approved. **Only the lines marked "owner" are owner rules.** Everything else is a **planning proposal, owner may
revise**. PROPOSED items in the sources are not built as final.

**This area posts nothing.** A custom field never writes a journal entry, never changes a posted amount and never feeds
a ledger total; the only money rule is integer cents. §5 therefore shows integer-cents examples and states that there is no
entry to balance.

Sources read (only these, searched by section, date or code):
- Owner answers 2026-11-25 2:58 AM (A16-Q1), 3:05 AM (A16-Q2, Q3), 3:09 AM (A16-Q5, superseding the 3:05 AM Q5 line) and 3:47 AM (A16-Q6, leads only) in Strata_Teams `inbox/to_owner.md` (read-only).
- docs/next_step.md: "Area 16, Custom fields (added 2026-11-23; design chat gap list item 4)", "Still open from STOP C", and the Area 16 lines in the Area 8, 15, 6, 7 and 17 hand-off lists.
- Owner request 2026-11-13, `StrataLedger_mockups/CODE_CHANGES_NEEDED.md` §27, and FR1 as amended (owner 2026-11-17), quoted in `modules/services/custom_fields.py`.
- Approved areas, by section: 15 (§1.6 and Q23 A as amended; the service type and stage model of leads), 8 (`service_type`, `service_stage`, stage requirements, `stage_requirements_block`), 6 (§12, Q25 A, withdrawn here), 7, 13 (Q6 A, the custom-field part moot here),
  17 (§1, Q1 A), 18 (`fields.manage`, audit `event_id`, person pickers, reasons).
- `migrations/001_company.sql` (`custom_field_def`, `custom_field_value`, the two type triggers, the `fields.manage` seed), `modules/services/custom_fields.py`.
- Live mockups (read-only, StrataLedger_mockups): `crm-fields.html`, `job-type-fields.html`, `settings-index.html`, `case-settings.html`, `pm-materials-settings.html`.

---

## 0. Summary

| # | Item | Proposal in one line |
|---|------|----------------------|
| 1 | Leads only | **Custom fields are for CRM leads only (owner 3:47 AM).** `record_type` allows `'Lead'` only. Estimate, Contact, Invoice, Bill and Project use their built-in fields and notes. |
| 2 | One definition table | Keep `custom_field_def` and `custom_field_value` (no `deal_field` tables). Add `service_type_id`, `stage_id`, `help_text`, `on_board_card` and `row_version`. |
| 3 | Lead fields hang off a stage | **A CRM custom field belongs to one service type, then one stage, then the field (owner).** No "Applies to" list and no scope table; reuse is by Copy custom fields. |
| 4 | Service type change | **The old type's values are kept hidden and show again if the lead is switched back; the change is audit-logged (owner).** |
| 5 | User field type | **A User field picks any active user (owner).** A new `value_user_id` column. |
| 6 | No case or job fields | **No custom fields for service cases (owner).** Job delivery-stage fields are a separate set, not designed here. |
| 7 | Warnings, not limits | More than 2 board-card fields, or over 20 active fields, on one service type shows a warning only (owner request 2026-11-13). |
| 8 | Controls | No new Control. Stage requirements follow Area 8's `stage_requirements_block` (default 0, warn). |
| 9 | Old rows | Existing Contact, Invoice, Bill, Project and Estimate definitions and values are kept, read-only, in an archive; none is deleted (migration note, §7). |

---

## 1. Current state

- **Baseline:** `custom_field_def` (`record_type` CHECK IN Contact, Invoice, Bill, Project, Estimate; `data_type` CHECK IN Text, Number, Money, Date, Yes/No, Choice; `choices_json`; `is_required`; `is_active`; `sort_order`;
  UNIQUE (`record_type`, `field_key`)) and `custom_field_value` (one typed column per type: `value_text`, `value_number`, `value_cents` with an integer CHECK, `value_date`, `value_bool`; UNIQUE (`field_id`, `record_id`); at most one column
  set; two triggers keep the column matched to the field's type). The `fields.manage` permission is seeded sensitive. There is no `help_text`, no board-card flag, no service type or stage, no User type and no `row_version`.
- **Service (`custom_fields.py`, Phase 2.7 STOP C):** supports Contact, Invoice, Bill and Project (Estimate refused). Defining needs `fields.manage` (Admin and the Master, never the Agent); a field is never removed (inactive, values kept); labels are unique per
  record type ignoring case; `field_key` comes from the label and never changes; a Contact field named like a bank number is refused (RP1); a value is readable exactly when its record is and set with the record's own edit check; a posted invoice or bill value may change unless
  Lock documents after posting is on or the entry's period is closed. All of this except the definition rules and `field_key` is built for record types this draft withdraws (§2).
- **Live mockups:** `crm-fields.html` (CRM Settings > Custom fields) lists name, type (Text, Number, Money, Date, Pick list, Yes/no), **Applies to** (an "All service types" box and one box per service type), **Shown from** (a stage), **On board card**, Active and help text,
  with "Every custom field here was added by your company. Nothing is built in", the **Busy cards** warning (more than 2 custom fields on board cards for a service type), the **Many fields** warning (over 20 active fields, "a warning, not a limit"), Make inactive and Remove,
  "Saving writes one entry to the audit log", and the note that lead basics are not custom fields. `job-type-fields.html` (Service types and custom fields) lists each service type's stages with a Custom fields column and guidance (the owner's pattern: Solar install > Site survey > Roof type
  and Main panel rating (A); Permitting > Permit number). `case-settings.html` shows four case types with Default owner and Due and no custom fields section.

## 2. Decided (owner) and carried forward

- **A16-Q6 (owner 3:47 AM):** custom fields are for CRM leads only. The company-wide custom fields on Estimate, Contact, Invoice, Bill and Project are dropped; those records use their built-in fields and notes. Example: no "PO reference" custom field on Bills.
  Planning reading (owner may correct): this **withdraws Area 6 Q25 A** (Estimate values attach to `estimate`) and every other area's custom-field hook for those five record types (pointers in Areas 6, 7, 8, 13, 15, 17 and 18); existing baseline rows are archived, not deleted (§7).
- **A16-Q1 (owner 2:58 AM; his words: "these custom fields belong to one service type > Stage > Custom Field. But these custom fields are just used for CRM related inquiry."):** a CRM custom field belongs to one service type, then one stage, then the field,
  as on the Service types and custom fields page (Solar install > Site survey > Roof type). Job delivery-stage fields stay a separate set. Planning reading (owner may correct): the stage replaces "Shown from"; the "Applies to" list and a scope table go away; reuse is by Copy custom fields;
  a required field is required from its own stage (A16-Q4).
- **A16-Q2 (owner 3:05 AM):** when a lead's service type changes, the old type's values are kept hidden; they show again if the lead is switched back; the change is audit-logged. Example: a Residential solar lead with Roof type "Tile" switched to Roofing keeps "Tile" stored, not shown.
- **A16-Q3 (owner 3:05 AM):** a User field picks any active user (no role filter).
- **A16-Q5 (owner 3:09 AM; his words: "only have these on case types."):** no custom fields for service cases. Case types carry only Type, Default owner and Due (business days), as on the live Case settings page. `'Case'` is removed from Area 15 Q23 A (pointer in Area 15).
- **Owner request 2026-11-13 (C27) and FR1 (owner 2026-11-17):** all fields are company-defined, no built-in packs, no seeded fields, no cap; each field has a name, type, help text, on board card and active; every field can be added, edited, renamed, made inactive or removed, **removing keeps the entered values**
  and Make inactive is offered first; **warnings, not limits**: more than 2 fields on board cards for a service type, and more than 20 active fields on a service type; deal basics (value, expected close date, owner, contacts, lead source) are core columns, not fields; the lead page shows
  "<service type> details"; the pipeline Columns menu has "Deal basics" and "Your fields"; stage requirements ("Field filled") pick from both.
- **Owner answers carried (2026-11-18, STOP C), now for leads only:** defining needs `fields.manage` (Admin and the Master only); a field is never removed; a value is readable exactly when its lead is and set with the lead's own edit check.
- **Carried:** Area 15 Q23 A adds `'Lead'` to `record_type` (its `'Case'` withdrawn); area 17 Q1 A offers every active custom field by its immutable `field_key`; stage requirements warn unless `company_settings.stage_requirements_block` is 1 (Area 8). The User type came from the design chat gap list item 4 (2026-11-23), an input.

---

## 3. Schema (planning proposals, owner may revise)

- **`custom_field_def`** (changed):

  | Column | Change |
  |--------|--------|
  | `record_type` | CHECK IN ('Lead') **only** (owner A16-Q6; the five old values are removed). The column stays so a later record type is a CHECK change, not a rebuild. |
  | `data_type` | CHECK gains `'User'`. The mockup's "Pick list" is the stored `'Choice'`. |
  | `service_type_id` | new, INTEGER NOT NULL FK `service_type` (Area 8): the one service type the field belongs to (owner). |
  | `stage_id` | new, INTEGER NOT NULL FK `service_stage` (Area 8): the one stage; it must belong to `service_type_id` (service check). The stage replaces "Shown from". |
  | `help_text` | new, TEXT NULL, CHECK NULL or length(trim) <= 200. |
  | `on_board_card` | new, INTEGER NOT NULL DEFAULT 0 CHECK IN (0, 1) (the pipeline board). |
  | `row_version` | new, INTEGER NOT NULL DEFAULT 1 (Area 21 stale-save refusal). |

  Uniqueness: `field_key` stays UNIQUE per `record_type` (from the label, with a numeric suffix on a collision, never changing); **the label is unique per `service_type_id` ignoring case**, so "Roof type" may exist on both Solar install and Roofing as two definitions (service rule, checked in the write
  transaction; inactive fields count). Area 17's registry shows a Lead field with its service type name beside its label.
- **`custom_field_value`** (changed): new `value_user_id` INTEGER NULL (a master user id, a plain integer with no cross-file FK, like every user id in a company file); the "at most one column set" CHECK and the two type triggers gain it (`'User'` uses `value_user_id`). `record_id` is the lead id.
  `value_cents` stays integer-checked; `value_number` stays REAL for quantities (rule 1).
- **`custom_field_legacy`** (new, insert-only, §7): the archive of definitions and values that existed for the five withdrawn record types.
- **No scope table, no `deal_field` tables, no cap column, no "show in reports" flag** (Area 17 Q1 A).

## 4. Rules (`custom_fields.py`, reduced to leads)

1. **A Lead field belongs to one service type and one stage** (owner). It shows on a lead only while the lead's service type equals the field's, and **from the field's stage onward** (owner A16-Q7), visible and editable at later stages; the lead page groups fields under their stage. Before that stage the field is hidden and cannot be set;
   a stage move never deletes a value; moving back hides, not clears.
2. **Service type change (owner A16-Q2):** when a lead's service type changes (Area 15 allows it only while no estimate names the lead), the old type's values stay stored and hidden and show again if the lead is switched back; the change is audit-logged by the lead's own audit trigger and
   `lead_stage_history` (Area 15); nothing extra is written by this area.
3. **Required (planning reading, A16-Q4):** `is_required` applies from the field's own stage onward and only to leads of its service type; a save missing a required value is refused naming the field. A stage requirement "Field filled" (Area 8's stage triggers) references `field_id` and
   **warns, or blocks only when `stage_requirements_block` = 1** (default 0).
4. **User type (owner A16-Q3):** the value is the id of **any active company user** (Area 18's person pickers, 11-17 item 4), no role filter; the picker shows the current name; a user later deactivated stays on old values, shown "(inactive)", and cannot be picked for a new value. The Agent never sets a value.
5. **Copy custom fields** (`copy_fields(from_service_type_id, to_service_type_id, field_ids)`): creates a new definition on the target service type for each chosen field (same label, type, choices, help text, board-card flag), on the stage with the same name in the target type, else the same role;
   a field with no matching stage, or whose label the target already uses, is skipped and listed as "not copied: no <stage> stage on <type>" (owner A16-Q8). Copy never moves values.
6. **Remove is Make inactive** (FR1): a field is never deleted; inactive fields keep values, are not offered on new leads, and still resolve in saved report definitions (Area 17). Reactivating restores them.
7. **Warnings, not limits (owner request 2026-11-13):** `list_fields` returns, per service type, a "Busy cards" warning when more than 2 active fields have `on_board_card` = 1, and a "Many fields" warning when more than 20 are active; saving is never refused. Inactive fields do not count. Both are information, not Controls.
8. **Leads only (owner A16-Q6):** the service refuses to define or set a field for any record type but Lead. There is no custom field on Estimate, Contact, Invoice, Bill or Project; the posted-document lock rule, the Contact bank-number refusal and the per-record-type permission mapping of the Phase 2.7 service are retired with them
   (a Lead field is a free text or choice label, and RP1's rule that bank numbers are never stored still applies: a Lead field named like a bank number is refused, planning proposal).
9. **Permissions:** defining, copying and deactivating need `fields.manage` (sensitive, Admin and the Master, none in `AGENT_ALLOWED`); a value is readable exactly when its lead is (Area 15's lead read check) and set with the lead's own edit check.
10. **Audit:** every definition and value change is audited by the trigger pattern; the settings page's Save applies all pending edits in one transaction and tags the audit rows with one `event_id`, so the screen shows "one entry" while the log keeps a row per change (Area 18). A reason is not required
    (Area 18 Q15 A: reasons are for controls).
11. **Job delivery-stage fields are a separate set (owner A16-Q1) and are not designed here** (owner A16-Q9: designed later with the job pages; jobs get no company-wide custom fields).

## 5. Worked examples, integer cents (no entries to balance)

- **Money field.** A Solar install lead field "Site survey fee quoted" (Money) at the lead stage "Site assessed". Typing "350.00" stores `value_cents` 35000; on another lead "1,250.50" stores 125050. Their sum in a report is 35000 + 125050 = 160050 cents, shown $1,600.50.
  "12.345", "1e3" and "$-" are refused by the shared money parser; the stored value is never a float (rule 1).
- **Posting.** No custom field posts: the fee changes no ledger line, no estimate total, no invoice and no job cost, so there is no journal entry here and nothing to balance. A static test checks that `custom_fields.py` imports neither `ledger` nor any posting service.
- **Service type, stage and the owner's pattern.** Solar install > lead stage "Site assessed" > "Roof type" (Pick list: Tile, Shingle, Metal) and "Main panel rating (A)" (Number); "Proposal reviewed" > "Proposal notes" (Text). A Residential solar lead in "New lead" shows none of them; at "Site assessed" it shows Roof type and Main panel rating; at "Proposal reviewed" it still shows Roof type and Main panel rating (owner A16-Q7) and also Proposal notes, grouped under their stages.
  A Roofing lead never shows Solar install's fields; Roofing has its own "Roof type" definition.
- **Service type change (owner A16-Q2).** A lead with Roof type "Tile" is switched from Residential solar to Roofing: "Tile" stays stored and is not shown (Roofing's Roof type is a different, empty field); switching back shows "Tile" again; the change is in the audit log.
- **Copy with no matching stage (owner A16-Q8).** Copying "Permit fee" (Money, stage "Site assessed") from Solar install to Roofing, which has no "Site assessed" stage, creates nothing and lists "Permit fee: not copied: no Site assessed stage on Roofing"; fields whose stage exists are copied.
- **Not a custom field.** A Bill needs a "PO reference": it uses the bill's built-in fields and notes; no custom field exists on a Bill (owner A16-Q6).
- **Warnings.** Residential solar has three active fields with On board card: the list shows "More than 2 custom fields on board cards for Residential solar" and every save still works. A 21st active field shows "Over 20 active custom fields on Residential solar" and saves.
- **User field.** "Site safety lead" (User) on a lead holds user id 41 (Dana Reyes); it shows "Dana Reyes". When Dana is deactivated it shows "Dana Reyes (inactive)"; a new lead cannot pick her; any other active user can be picked.

## 6. Tests (planning proposals)

`test_custom_field_record_type_is_lead_only` (owner A16-Q6), `test_no_custom_field_can_be_defined_or_set_for_estimate_contact_invoice_bill_or_project`, `test_custom_field_def_keeps_one_table_and_has_no_deal_field_or_scope_tables`,
`test_no_custom_fields_for_service_cases_and_case_types_carry_only_type_default_owner_and_due`, `test_lead_field_requires_one_service_type_and_one_stage_and_the_stage_must_belong_to_it`,
`test_lead_field_is_hidden_before_its_stage_and_value_kept_when_the_lead_moves_back`, `test_lead_does_not_show_another_service_types_fields`,
`test_service_type_change_keeps_old_values_hidden_shows_them_again_on_switch_back_and_is_audit_logged` (owner A16-Q2), `test_label_unique_per_service_type_ignoring_case_so_two_types_may_each_have_roof_type`,
`test_field_key_unique_per_record_type_and_never_changes`, `test_required_field_applies_only_from_its_own_stage_and_its_service_type`, `test_stage_requirement_field_filled_warns_unless_stage_requirements_block_is_on`,
`test_user_field_stores_an_active_company_user_id_in_value_user_id`, `test_user_field_has_no_role_filter_and_shows_inactive_user_on_old_values_but_refuses_them_on_new` (owner A16-Q3),
`test_custom_field_value_type_triggers_accept_value_user_id_only_for_user_fields`, `test_agent_cannot_set_a_custom_field_value`, `test_lead_field_value_follows_the_leads_read_and_edit_check`, `test_copy_fields_creates_new_definitions_on_the_target_type_with_the_same_named_stage_and_lists_skipped`,
`test_copy_fields_never_moves_values`, `test_remove_is_make_inactive_and_values_and_history_stay`, `test_inactive_field_still_resolves_in_a_saved_report_definition`,
`test_busy_cards_warning_over_2_board_card_fields_per_service_type_never_blocks_a_save`, `test_many_fields_warning_over_20_active_fields_per_service_type_never_blocks_a_save`,
`test_lead_field_named_like_a_bank_number_is_refused`, `test_money_field_is_integer_cents_and_refuses_more_than_two_decimals`, `test_custom_fields_service_posts_nothing_and_imports_no_ledger`,
`test_defining_needs_fields_manage_and_is_not_in_agent_allowed`, `test_settings_save_writes_one_event_id_with_a_row_per_change`, `test_custom_field_def_row_version_stale_save_is_refused`,
`test_legacy_custom_field_rows_are_archived_not_deleted` (§7).

## 7. How it lands in the baselines and the existing code; migration note

- **Company baseline:** the `custom_field_def` columns and CHECKs above (`record_type` Lead only, `'User'`, `service_type_id`, `stage_id`), `custom_field_value.value_user_id`, the revised sum CHECK and both type triggers, `custom_field_legacy`, audit triggers for the new columns. Development databases are rebuilt (CLAUDE.md section 5.2;
  ask first), so before the first release no migration runs: dev rows on the five withdrawn record types simply do not exist in the rebuilt file.
- **Migration note (planning reading, owner may correct): rows are made inactive and kept, never deleted.** If a company file that already holds `custom_field_def` or `custom_field_value` rows for Contact, Invoice, Bill, Project or Estimate must be upgraded (the first numbered migration after release, or an import of an older file), the migration
  copies every such definition (record type, key, label, type, choices, required, sort) and every value (record type, record id, key, the typed value as text, its type) into the insert-only `custom_field_legacy` table, marks the source definitions inactive, and only then lets the CHECK narrow; nothing is deleted and nothing is written to the
  audit log's old values. The archive is read-only, shown nowhere on the screens but available to reports through an Admin export, and keeps the audit history that already exists. `custom_field_legacy` is the only home for those rows.
- **Code:** `custom_fields.py` shrinks to Lead: `RECORD_TYPES` becomes `("Lead",)` when `leads.py` exists (until then every call is refused with the existing sentence); the Contact, Invoice, Bill and Project read and edit-code mapping, `_check_posted` and the Contact bank-number check are removed; the service gains the service type and stage rule, board-card, help, User type, copy and the
  warnings. No UI, OS or HTTP imports (H1), no clock reads (H2), no triggers for workflow (H4), no SQLite-only SQL (H5).
- **Existing tests change:** `tests/test_custom_fields.py` loses its Contact, Invoice, Bill, Project and posted-document cases and gains the Lead cases above; the test that Estimate is refused is deleted; tests that count data types or record types are updated.
- **Handoffs removed:** Area 6 Q25 A (Estimate values), the Phase 2.7 `custom_fields._check_posted` hook in Area 13 (§1.4 table row and Q6 A's custom-field half), Area 7's Project read and write codes line for custom fields, Area 8's Project custom fields line, Area 17's registry coverage of Contact, Invoice, Bill, Project and Estimate fields, Area 18's contact custom-field rule.
- **Handoffs out:** Area 8 (a stage requirement "Field filled" references `field_id`), Area 15 (the lead page "<service type> details", pipeline Columns "Your fields", board cards), Area 17 (the registry shows only `cf.lead.<key>`), Area 18 (audit `event_id`), Area 21 (`row_version`).

## 8. Conflicts with decisions, the baseline or the mockups (flagged)

1. **Area 6 Q25 A (owner-approved) puts Estimate custom fields on `estimate`;** the owner's 3:47 AM answer withdraws it (pointer in Area 6). Area 6's other custom-field lines (§12, the refusal in `custom_fields.py`, hand-off item 9) are withdrawn with it.
2. **The Phase 2.7 service and its tests (STOP C) cover Contact, Invoice, Bill and Project;** they are retired (§7). Area 13's `custom_fields._check_posted` hook and Q6 A's custom-field half become moot (the attachment-removal half stays).
3. **C27 names three tables (`deal_field`, `deal_field_job_type`, `deal_field_value`);** the baseline already has `custom_field_def` and `custom_field_value`. This area keeps them and drops the scope table of the first draft (§3).
4. **C27 and the mockup say "job type" and "deal";** the approved model says service type and lead (Area 8 Q1; Area 15). Work order for the wording.
5. **The mockup's "Applies to" multi-select and "Shown from" select** (`crm-fields.html`, `pages/crm-fields.js`) contradict the owner's one service type > stage > field. Work order: a Service type pick and a Stage pick, and a Copy custom fields button.
6. **No User type in the mockup;** the type is added from the design-chat gap list (work order). **"Remove" in the mockup versus never-deleted:** Remove must stay Make inactive (§4 rule 6).
7. **"Saving writes one entry to the audit log" versus row-level audit triggers:** resolved with one `event_id` per Save (§4 rule 10).
8. **Two pages, two sets:** the CRM Custom fields page (lead fields, this area) and the Service types and custom fields page (job delivery-stage fields, not designed here) share the service type > stage > field pattern but must not share definitions (work order).
9. **Area 15 Q23 A (owner-approved) adds `'Lead'` and `'Case'`;** `'Case'` is removed (owner 3:09 AM).
10. **Areas 7 and 8 said Area 16 would carry per-stage job fields;** the owner kept them a separate set, so those hand-offs are open again (pointers).
11. **Area 17 Q1 offered a per-field "Show in reports" flag as option B;** the owner chose A, so this area adds none; the registry now covers Lead fields only.
12. **Any other mockup page that shows custom fields on a customer, invoice, bill, job or estimate** (the intake and detail pages) must drop them (work order); the live mockups were not searched for every such page in this draft.

## 9. Questions for the owner

**No open owner questions.** Decided 2026-11-25 11:39 AM (§2): A16-Q7 (A), A16-Q8 (A), A16-Q9 (A). A16-Q4 stays a planning reading.

## 10. Open items (not decisions)

- Job delivery-stage custom fields (owner A16-Q9: later, with the job pages) and the Custom fields column of `job-type-fields.html`.
- Notes and built-in fields for Estimate, Contact, Invoice, Bill and Project: not designed here (the owner said they use their built-in fields and notes).
- Conditional fields, calculated fields and formulas; attachments or multi-select choice types.
- Importing and exporting field definitions and bulk-filling a field.
- An Admin export of `custom_field_legacy` and its retention.

## 11. Owner answers 2026-11-25 11:39 AM (dated amendment; §9 questions are decided)

- **A16-Q7 (owner, A):** a lead field shows from its stage onward, visible and editable at later stages, grouped under its stage. Example: Roof type on "Site assessed" is still shown at "Proposal reviewed".
- **A16-Q8 (owner, A):** Copy custom fields skips a field with no matching stage and lists it as "not copied: no <stage> stage on <type>". Example: "Permit fee" on "Site assessed" is not copied to Roofing.
- **A16-Q9 (owner, A):** job delivery-stage fields stay their own set, designed later with the job pages; jobs get no company-wide custom fields (A16-Q6 stands).
- Examples in §5 now use lead pipeline stages, not job stages. A16-Q4 stays a planning reading.

- **Amendment 2026-11-25 (pointer, Area 21 draft; Planning reading, owner may correct): row version.** `row_version` and the stale-save refusal are Area 21 §3 (`tx.update_versioned`, `StaleVersionError`, mapped to `conflict`; insert-only tables exempt). A Custom fields Save that changes several fields refuses the whole Save when one is stale (Area 21 §3, Q8 open).
