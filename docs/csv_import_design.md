# Batch CSV import and the CSV upload page: design draft

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
This revises the submitted CSV import specification so that it fits the rest
of the design (staging, numbering, controls, add-ons). The changes from the
submitted spec are listed in section 12.

Conventions follow CLAUDE.md: integer cents, ISO text dates, UTC timestamps,
all writes through service functions, posted records locked, no raw SQL writes
from the UI or the AI agent, no print() error handling.

---

## 1. Scope

Version 1 import types:
1. Chart of accounts
2. Customers (contacts)
3. Vendors (contacts)  [added; bills need vendors]
4. Invoices (customer invoices with lines)
5. Bills (vendor bills with lines)

Later types, added through the same registry, belong to the opening-balance and
conversion design (not yet designed): opening trial balance, open AR, open AP,
fixed assets register, loans, inventory on hand, open jobs.

---

## 2. Architecture

- **Import type registry.** Each import type is a small plug-in with: a column
  definition, a parser, a validator, and a committer. The page and the AI
  Copilot only know the registry. Add-ons (for example the Philippines tax
  add-on) can register extra columns or types; the core importer does not know
  them by name.
- **Files (one view per file):**
  - `modules/views_csv_import.py`: the page. No SQL. No business rules.
  - the import service (location decided in the Phase 2 plan, next to the other
    services): parsing, mapping, validation, duplicate checks, batch commit.
    Never imports Tkinter.
- **No duplicated rules.** The importer calls the same service functions and
  validators the normal screens use (create contact, create account, create
  draft invoice, customer-code assignment). It never reimplements a rule and
  never writes SQL of its own.
- **Built-in templates are CSV files.** A chart of accounts template for a new
  company (for example "Construction contractor") is just a CSV loaded through
  the same importer.

---

## 3. The page: five steps

1. **Choose the type.** A list of import types, each with "Download sample CSV"
   (UTF-8, valid headers, two example rows).
2. **Choose the file and read options.** File picker; encoding (default UTF-8,
   accepts a BOM); delimiter (comma or semicolon, auto-detected, shown); header
   row yes/no. The date format is NOT chosen per file: it is the company's
   date format (section 4). Decimal and thousands separators follow the
   company number format.
3. **Map columns.** Each required column is matched to a file column; the page
   suggests a mapping from the headers. The mapping can be saved by name and
   reused.
4. **Preview and validate.** A grid with a status for every row (Ready, Warning,
   Error) and a message. Filters: All, Errors, Warnings. A summary panel: rows,
   groups (invoices or bills), errors, warnings, and the control total in
   money. Unknown customers or vendors are shown with actions: map to an
   existing contact, or create (with the duplicate check).
5. **Commit.** All or nothing. The button is disabled while any error
   remains; nothing is written until the file has zero errors. The error list
   is shown on screen and can be downloaded as a CSV (row number, column,
   message, and the original row values) so the file can be fixed and
   uploaded again. Warnings do not block. Result screen: what was created,
   with links.

Layout of the page: a step bar on top, the options or grid in the centre, the
summary panel on the right, buttons at the bottom (Back, Download sample,
Download exceptions, Commit).

---

## 4. Parsing rules

- **Money:** parse with `decimal.Decimal`, never float. Accept `1,234.56`,
  `$1,234.56`, `(1,234.56)` and trailing minus as negatives where the type
  allows negatives; convert to integer cents. A unit price with more than two
  decimals is rejected unless the file also gives the line amount (materials
  priced at a fraction of a cent need an explicit amount); the line amount
  must equal quantity x price rounded half up.
- **Dates:** the company has ONE date format, chosen at company setup
  (`company_settings.date_format`: YYYY-MM-DD, MM/DD/YYYY or DD/MM/YYYY). It
  is used everywhere dates are shown, typed, imported, exported and printed.
  The importer accepts that format, and also strict ISO `YYYY-MM-DD` (which is
  never ambiguous). Anything else is an error. Values are validated as real
  dates and stored as strict ISO. The setting can be changed by an Admin
  (audit-logged); it only changes how dates appear.
- **Numbers:** PROPOSED the same way: one company number format (decimal and
  thousands separators) chosen at setup, used for import and display.
- **Text:** trimmed; embedded newlines kept in description fields; leading
  `=`, `+`, `-`, `@` are stored as plain text (and escaped in any CSV the app
  exports).
- **Limits:** PROPOSED 50,000 rows and 20 MB per file; larger files are
  rejected with a message.
- **Errors** carry a row number, a column and a plain-language message, and are
  never printed to the console.

---

## 5. The five import types

**5.1 Chart of accounts.** Columns: `code`, `name`, `account_type`
(Asset, Liability, Equity, Revenue, Expense), `parent_code` (opt),
`is_postable` (0/1), `control_type` (opt; only the allowed values).
Rules: insert only (duplicate codes rejected, existing accounts are never
changed by import); parent must exist earlier in the file or in the company;
type is required. A `control_type` can be set on a new account only; the file
cannot add or remove it on an account that already has history.

**5.2 Customers.** Columns: `name`, `entity_type` (values must match the live
`contact.entity_type` list), `email`, `phone`, `tax_id`, `mailing_street`,
`mailing_city`, `mailing_state`, `mailing_zip`. Rules: duplicate check on name,
tax_id and email (collisions shown in the grid, never silently merged);
`customer_code` assigned by the standard customer-code service function when the
row is committed.

**5.3 Vendors.** Same columns as customers. Vendor code assigned by the vendor
code service function (the `V` prefix is CONFIRMED: V + 2-letter prefix + at
least 4 digits, for example VAC0001).

**5.4 Invoices.** Columns: `customer_name` or `customer_code`, `invoice_ref`,
`issue_date`, `due_date`, `terms` (opt), `project_number` (opt),
`line_description`, `account_code`, `quantity`, `unit_price`, `tax_rate` (opt).
- Rows are grouped into one invoice by (`customer`, `invoice_ref`,
  `issue_date`). `invoice_ref` is any text that ties the rows together; it is
  NOT the invoice number.
- Invoice numbers are assigned by the numbering series when the invoice is
  sent or posted, never at import, never at Draft. A file-supplied number is
  honored only in opening-balance mode (section 7).
- Validated with the normal rules: customer has a customer code, accounts are
  active and postable (not control accounts), the project's stage allows
  billing, the period is open, dates are valid.

**5.5 Bills.** Columns: `vendor_name` or `vendor_code`, `bill_number`
(vendor's number, required), `issue_date`, `due_date`, `project_number` (opt),
`cost_code` (opt), `line_description`, `account_code`, `quantity`,
`unit_price`. Grouped by (`vendor`, `bill_number`, `issue_date`). Vendor bill
number must be unique per vendor (existing rule). Accounts must be postable and
not control accounts; a project tag requires `allows_costs = 1`.

---

## 6. Control rules

1. **Nothing posts from a CSV.** Chart of accounts and contacts are master
   data: a person commits them after the preview, through the service
   functions. Invoices and bills are committed as Draft documents in an
   `import_batch` with `source = 'Manual Upload'`; a person reviews and posts
   them through the normal posting path. The importer never posts.
2. **One transaction per commit.** All-or-nothing, `BEGIN IMMEDIATE`, through
   `database.get_connection()`, with `audit_context` set to the committing
   user's id and `origin`. There is no partial import: if any row has an
   error, no row is written.
3. **Idempotency.**
   - File level: the SHA-256 of the file is stored on the `import_batch`;
     importing the same file twice for the same type is blocked (with an
     override that requires a reason, logged).
   - Row level: `external_ref` = SHA-256 of the import type plus the
     normalized key fields (not the row number), with an occurrence counter
     for genuinely identical lines in one document. Re-sorting a file does not
     change the hashes.
4. **Batch record:** `import_batch` stores file name, file hash, type, mapping
   used, row counts, `total_cents`, `imported_at` (UTC), `imported_by`,
   `approved_by`, `origin`.
5. **Unknown contacts** are resolved in the preview (map or create); they are
   never auto-created at commit.
6. **No silent changes:** the commit shows exactly what will be created.

---

## 7. Mode: new transactions vs opening balances

The importer asks which mode applies to Invoices and Bills.
- **New transactions (default):** normal posting rules; dates must fall in an
  open period; numbers are assigned by the series.
- **Opening balances (conversion):** for open items from a previous system.
  This mode needs the conversion workflow (not designed): it posts against
  opening balance accounts, honors the file's invoice numbers, and is locked
  after finalization. Until that design exists, the option is hidden and the
  importer rejects invoices dated before the company's go-live date.

---

## 8. AI Copilot

1. The user attaches or names a CSV in the Copilot panel.
2. The agent can: read the headers, infer the type, suggest the mapping, and
   run a dry-run validation **in memory**. Nothing is written to the database
   by a dry run.
3. **Privacy:** sending file contents to the AI provider requires the explicit
   opt-in setting. Without it, the agent works from the column headers only
   (PROPOSED) or not at all, and the mapping is done locally by the
   deterministic header matcher.
4. The agent opens the import page with the parsed preview. A human clicks
   Commit. The batch records `origin = 'Agent'` and `approved_by` = the human.
5. The agent never commits, saves, approves or posts, and never runs raw SQL.

---

## 9. Add-ons

A country add-on can register extra columns (for example Philippine TIN, branch
code and VAT category) and extra validators for the existing types. The values
are stored in the add-on's own tables through the add-on's service. If the
add-on is off, those columns are not offered.

---

## 10. Tests required (before the page is built)

Per import type: valid file, missing required column, wrong date format, a date not in the company format or ISO, negative where not allowed, more than two decimals,
amount mismatch, duplicate codes, unknown parent, unknown customer or vendor,
duplicate contact collision, inactive or control account, project that does
not allow billing or costs, closed period, multi-line grouping, same file
imported twice, re-sorted file, BOM and semicolon delimiter, oversized file,
error list download with no rows written, rollback on a failure mid-commit,
audit context recorded, the agent path never writes without a human commit,
and the privacy opt-in respected.

---

## 11. Phase placement

- Phase 2 (service layer): the registry, parsers, validators and committers
  for the five types, with the tests above. Chart of accounts first, because
  company creation uses it to load a template.
- Phase 3 (screens): `modules/views_csv_import.py`, the sidebar entry under
  Imports/Tools, and the Copilot upload command.
- Later: conversion types, after the opening-balance design.

---

## 12. Changes from the submitted spec

1. Dates: one company-wide date format chosen at company setup (US and
   Philippine files differ); strict ISO is always accepted; storage is ISO.
2. Invoice numbers are not assigned at import; they follow the numbering series
   at send or post. `invoice_number` became `invoice_ref` for grouping.
3. Staging vs Draft is decided: master data commits after preview; invoices and
   bills are Draft documents in an import batch.
4. A Vendors import was added (vendor code `V` prefix confirmed).
5. Idempotency uses a file hash plus key-field hashes, not row index.
6. Historical open items are routed to the conversion design, not this page.
7. Added: import type registry, saved mappings, parsing options, money rules,
   limits, a downloadable error list, add-on columns, and the AI privacy
   opt-in. Imports are all or nothing.
8. The importer reuses service validators instead of its own rules.
9. COA import cannot flip `control_type` on accounts that have history.

---

## 13. Open questions

1. Row and size limits (PROPOSED 50,000 rows, 20 MB)?
2. Should saved column mappings be per company, per user, or global?
3. Company number format (decimal and thousands separators): chosen at setup
   like the date format (PROPOSED)?
