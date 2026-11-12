# Instructions for Claude Code: next steps after migration 003

Stay in plan mode. Show the plan and wait for approval before editing.
Do NOT commit this file (next_steps_instructions.md).

## Ground rules

- Do NOT run the apply commands for 003 on the real databases.
- Real databases hold test data and will be rebuilt fresh later by
  scripts/create_fresh_databases.py (dry-run only until approved).
- No 003_master.sql is needed; the runner fix c37f784 is enough.
- Do not touch the real .db files. Do not launch the app.

## Answers to your checks on migration 003

- Voiding an entry in a closed period by a reversal in an open period is OK.
  Reports and v_gl_detail must never filter on is_void.
- The is_eis_transmitted exception is OK if the change is audit-logged. It
  moves into the Philippines add-on later.
- Credit Memo: add invoice.ledger_side [Sales, Purchase] in migration 004
  (Invoice = Sales, Bill = Purchase, Credit Memo chosen explicitly).

## Step 1. Design docs

Move loans_design.md, inventory_fixed_assets_design.md and
philippines_tax_design.md into docs/. Commit them alone with the message
"Add inventory, fixed assets, loan and Philippines tax design docs".

## Step 2. Update CLAUDE.md (doc-only commit)

- List the design docs: CRM/PM, inventory and fixed assets, loans, Philippines
  tax, controls audit.
- New migration plan: 004 High controls, 005 CRM/PM, 006 ledger line keys and
  controlled accounts, 007 inventory, 008 fixed assets, 009 vendor refunds,
  010 loans. Philippines is an add-on, not in the core series.
- Fresh-start decision: the real databases hold test data and will be rebuilt.
- Add-on rule: country rules live in addons/<key>/. Core never imports an
  add-on. Core exposes hooks. Add-on tables are prefixed (ph_) and keyed to
  core ids. Add-on migrations have their own numbering. Disabling an add-on
  never drops data.
- Phase 2 list: hook registry, add-on registry, add-on migration runner, and
  the service-layer rules from the controls audit (postable and active
  accounts, reversal checks, payment over-allocation, period reopening with a
  logged reason).
- Phase 3 list: the app must ask before upgrading a database on launch.
- Backlog: Philippines tax module (VAT, withholding, certificates, filing
  tracker, e-invoicing) is designed, not built, and needs a Philippine tax
  professional's review.

## Step 3. Build migration 004 (failing tests first)

- The High schema fixes from the controls audit.
- Invoice numbering: an invoice_series table with series_id, document_type
  [Invoice, Credit Memo], prefix, last_number, registered_from,
  registered_to, authority_ref, valid_until, is_active. The counter updates in
  the same transaction as the number. Numbers outside a registered range are
  rejected. Numbers are assigned at send or post, never reused, and a void
  keeps its number.
- period_id is set by the system from entry_date, NOT NULL and validated.
  Periods are contiguous with no overlap. Posting with no period is rejected.
- account.control_type with the values: AR, AP, sales tax, deferral, retainage,
  over/under billing, employee advance, inventory, fixed assets, loans.
- company_settings: manual entry approval (off by default, with an optional
  threshold; the approver cannot be the creator) and base_currency
  (default USD).
- company_addon and addon_schema_version tables.
- invoice.ledger_side.
- Service-layer enforcement tests are marked expected-failure until Phase 2.

## Step 4. Philippines add-on, pure parts only

Start this only after step 3 is reviewed. No database and no network.

- addons/ph_tax/__init__.py with a manifest (key, version, minimum core
  schema version).
- invoice_print.py: builds an HTML page and a plain-text version of the paper
  invoice from template files in addons/ph_tax/templates/. Default layout is
  plain paper, with the series and permit details printed by the system. A
  pre-printed form layout comes later as another template file.
- eis_payload.py: builds the structured e-invoice JSON and validates
  completeness. Mark the schema "DRAFT" in code and in output.
- eis_transport.py: the transport interface and a dry-run transport that
  writes the JSON to an Outbox/ folder.
- All money is integer cents. Sample data only. No BIR endpoints or
  credentials. Do not touch core tables.
