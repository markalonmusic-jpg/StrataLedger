# CSV and Excel export design (DESIGN, NOT BUILT)

**Date:** 2026-11-13 · **Status:** design, not built. No report code exists yet (no report service, no
report screen), so this design defines the export layer that the reports will use. Open questions are in
section 14 with proposed answers.

**Goal (the owner's top accountant request):** one click exports any report or ledger drill-down to a real
`.xlsx` with live formulas and clean columns; CSV export for lists; bulk CSV and XLSX upload with clear row
errors.

**Inputs read:** docs/csv_import_design.md; F6 (saved column layouts); G1-G7 (report presets; `report.export`
is blocked for the AI); H3 (storage); A1 (report basis); A2 (company date format); CB1 and CF1; J4 (Excel FP&A
export); docs/roles_permissions_design.md (masked fields, report permissions, project scope); audit design
section 3 (the `Report export` checkpoint and the export footer hook); `modules/services/permissions.py`;
`modules/services/storage.py`; requirements.txt and requirements-dev.txt.

**What is installed today:** no spreadsheet library. requirements.txt holds `customtkinter`, `tzdata` and
`cryptography`; requirements-dev.txt adds `pytest` and `pyinstaller==6.22.3`. The permission `report.export`
exists and is not in `AGENT_ALLOWED`.

---

## 1. The export service (`modules/services/export.py`)

    def run_export(context, definition_key, filters, fmt, *, confirm_large=False) -> ExportResult

* **Steps:** validate the definition and filters; `authorize(context, "report.export")` and then the
  definition's own read permission, with the project if it is job-scoped (G7, rule 10); refuse `origin =
  'Agent'` (section 7); count the rows and apply the guard (section 7); build the rows; write the file; write
  the audit row and the `Report export` checkpoint; return the result.
* **Definitions** (one registry, shared by reports and lists): each one says which read service produces its
  rows, which permission it needs, its filters, and its columns. A **ColumnSpec** has `key`, `header`, `type`
  (`date`, `money`, `integer`, `quantity`, `percent`, `text`, `code`), `width`, `total` (`none`, `sum`), and
  `masked_by` (the sensitive permission that unmasks it, or none). The report services return **rows of plain
  values** (money in integer cents, dates as ISO text) plus **row kinds** (`Detail`, `Subtotal`, `Total`,
  `Opening`) and group keys. They never return spreadsheet formulas.
* **Writers:** `export_xlsx.py` and `export_csv.py`. They are pure functions from (columns, rows, parameters) to
  a byte stream and know nothing about the database. They have no Tk code (H1) and no clock: the run time comes
  from the context (H2).
* **Output** goes through `storage.py` (H3) to `Exports/<company code>/<file name>` in the data folder, which is
  the same place `export_company` writes. `storage.py` needs a streaming write (`open_data_for_write(relative)`
  returning a binary stream) for large files; today it only has `write_data(relative, content)` (section 14, Q2).
* **File names:** `<company code> <report name> <period or as-of date> <run date>.xlsx`, with characters that
  Windows does not allow replaced, and `(2)`, `(3)` added rather than overwriting a file.
* **ExportResult:** relative path, format, row count, SHA-256 of the file, the checkpoint string, and warnings
  (for example the unverified range, KS14).

---

## 2. Excel layout

Every workbook has two visible sheets, **Report** and **Parameters**, in that order.

**The Report sheet:**
* **One header row** (row 1). No title rows above it: the title is in the print header and on Parameters.
* **No merged cells**, and **no blank spacer rows** inside the data. Grouping is shown by a `Row type` column
  (`Detail`, `Subtotal`, `Total`, `Opening`) and a group column (for example `Section`), so filtering `Row type
  = Detail` always gives clean data for a pivot table.
* **Frozen header** (`freeze_panes` at row 2; the first column too when it holds codes), **autofilter** over the
  header and data, **print titles** (`repeat_rows` for row 1), landscape when the sheet has more than 6 columns,
  fit to one page wide, and the page footer "Page n of m · <company> · <basis>".
* **Column types** set with a column format (`set_column`) and, for every cell, the matching write call:

| Type | Written as | Format |
|---|---|---|
| `date` | an Excel date (serial number) | the company date format (A2): `mm/dd/yyyy`, `dd/mm/yyyy` or `yyyy-mm-dd` |
| `money` | a number in **dollars** | `#,##0.00;(#,##0.00);"-"` (negatives in parentheses, zero as a dash) |
| `integer` | a number | `0` |
| `quantity`, `percent` | a number | `#,##0.####`, `0.00%` |
| `text` | a string (`write_string`, never `write`) | General |
| `code` | a string (`write_string`) | Text (`@`) |

* **Where cents become dollars:** in one function only, `export_xlsx._dollars(cents: int) -> float`, which
  returns `cents / 100`. Python's integer-by-integer division gives the double nearest to the exact decimal
  value, so every amount below $10 trillion (15 significant digits) shows and copies back exactly. Nothing
  upstream of the writer ever holds dollars, and nothing does arithmetic on the float. The CSV writer never makes
  a float at all (section 5).
* **Codes and ids are text** so leading zeros survive: account codes, contact and job codes, entry numbers
  (`JE-000123`), invoice and check numbers, cost codes, ZIP codes, the last four digits of bank accounts, and any
  external reference.
* **Masked values** are written as the masked text (for example `•••• 1234`), never the real value, and never in
  a hidden cell (section 7).

**The Parameters sheet** (two columns, Name and Value, all text): company name and code; report name and
preset; **basis**: the A1 basis (Pre-adjustment, GAAP, Tax or Management) **and** Accrual or Cash (CB1); date
range or as-of date; comparison; every filter in words (accounts, dimensions, jobs, contacts); run at (UTC and
company time); run by (name and user id); app version; **the ledger checkpoint** (the full `SL1-...` string, audit
design 3) and the verification result, with the **unverified range** sentence when there is one (KS14, KS15);
the row count; and "Values are as of the run time; formulas recalculate in Excel."

---

## 3. Live formulas

* **Data rows are values.** Subtotals, totals, running balances, variance columns and check lines are
  **formulas** over the data range.
* **Formulas with cached values.** Each formula is written with its result (calculated in Python from integer
  cents and then turned into dollars once), so previewers that do not calculate (the Excel viewer, PDF
  converters, mobile previews, email attachments) show the right number, not 0. The writer must therefore support
  cached formula results.
* **The writer library: XlsxWriter** (checked 2026-11-13 on PyPI and its documentation): version 3.3.1 released
  28 Oct 2026, BSD-2-Clause licence, Python 3.8 or later, "uses standard libraries only" (no dependencies).
  `write_formula(row, col, formula, cell_format, value)` takes the cached result as `value`; without it, the file
  stores 0, and "applications that don't have a facility to calculate formulas will only display the 0 results."
  It never calculates formulas itself. Its `constant_memory` mode keeps about one row in memory (rows must be
  written in order; `add_table` and merged cells do not work, and this design uses neither). Formulas must be
  written in English with comma separators, and newer functions need the `_xlfn.` prefix; this design uses only
  `SUM`, `SUBTOTAL`, `ROUND` and arithmetic.
  * **Workbook options:** `strings_to_formulas: False`, `strings_to_numbers: False` and `strings_to_urls: False`.
    The defaults turn any string starting with `=` into a formula (documented), which would undo section 6. The
    writer also calls `write_string`, `write_number` and `write_formula` explicitly, never `write`.
  * **openpyxl** is used only for reading uploads (section 9): version 3.1.5 (28 Jun 2024), MIT licence.
    `load_workbook(data_only=True)` returns "the value stored the last time Excel read the sheet". Its docs
    recommend `defusedxml` against XML attacks.
  * **Confirm before building:** pin exact versions at least two weeks old (3.3.0 or 3.3.1 for XlsxWriter);
    whether openpyxl needs `et_xmlfile` (the pages read do not say) and the licence of anything it pulls in; add
    `defusedxml` (its licence too); a `tools/check_frozen_xlsx.py` like `tools/check_frozen_crypto.py`, which
    builds a PyInstaller 6.22.3 one-file app that writes a formula workbook and reads it back, and records the size
    it adds; and the third-party notices in the installer. Both libraries are pure Python, so no PyInstaller
    problem is expected, but this is not verified.
* **Formula rules:**
  * Subtotals and totals use `SUBTOTAL(9, range)`, never `SUM`, so a total skips the subtotals inside its range
    and still works when the user filters.
  * Each money formula is wrapped in `ROUND(..., 2)`, so Excel's own result equals the cached value to the cent.
  * A running balance is `=ROUND(prev + debit - credit, 2)`, starting from an `Opening` row whose balance is a
    value.
  * A variance is `=ROUND(current - prior, 2)`; a variance % is `=IF(prior=0, "", (current - prior) / ABS(prior))`.
  * A check line (for example "Debits minus credits" on the trial balance, or CF1's check against cash-basis net
    income) is a formula that should be 0, with conditional formatting when it is not.
  * Formulas use A1 references within the Report sheet only, never another file.
* **Where formulas cannot drive the numbers** (the values come from the report service, and the reason is on the
  Parameters sheet):
  * **AR and AP aging buckets:** the bucket is chosen by date rules (due date, terms, partial payments, B2
    retainage), so each bucket cell is a value; only the row and bucket totals are formulas.
  * **Cash basis (CB1):** the paid-share proration and the removal of non-cash entries happen in the service;
    the rows are values, and the totals are formulas.
  * **Cash flow (CF1):** the lines come from the cash flow categories; the sections, net change and beginning plus
    change equal ending are formulas, and the tie-out to the bank balances is a value plus a check formula.
  * **Balance sheet retained earnings:** calculated in reports (B1, no closing entries), so it is a value row,
    marked "calculated".
  * **Masked columns:** never part of a formula.
  * Anything above the row guard written in `constant_memory` mode still gets formulas, because they reference
    rows already written.

---

## 4. Report coverage, v1.0

| Report | Columns | Grouping (`Row type`) | Formulas |
|---|---|---|---|
| **Trial balance** | Account code (code), Account name, Type, Debit, Credit; per comparison period another Debit/Credit pair | Detail per account; one Total | Debit and Credit totals (SUBTOTAL); the check "Debits minus credits" |
| **Profit and loss** | Section (Revenue, Cost of sales, Expenses, Other), Account code, Account name, one money column per period, Variance, Variance % | Detail per account; Subtotal per section; Total rows for Gross profit and Net income | Section subtotals; gross profit and net income from the subtotals; variance and variance % |
| **Balance sheet** | Section (Assets, Liabilities, Equity), Sub-section, Account code, Account name, As-of amount, comparison amounts | Detail; Subtotal per sub-section and section; Total | Subtotals; "Liabilities and equity"; the check "Assets minus liabilities and equity"; retained earnings is a value (section 3) |
| **Cash flow statement (CF1)** | Section (Operating, Investing, Financing, Other balance-sheet movements), Category, Amount per period | Detail per category; Subtotal per section; Total net change; Opening and ending cash | Section subtotals; net change; beginning plus net change; the check against cash-basis net income; Unclassified as its own Detail row |
| **GL detail / ledger drill-down** | Account code, Account name, Date, Entry number (code), Source, Reference, Contact, Job, Memo, Debit, Credit, Balance, dimension columns | Opening row per account; Detail per line; Subtotal per account | Running balance; account subtotals; grand totals |
| **AR aging and AP aging** | Contact code, Contact name, Document number, Date, Due date, Current, 1-30, 31-60, 61-90, Over 90, Retainage, Unapplied credits (B4), Total | Detail per document; Subtotal per contact; Total | Row total across buckets; contact subtotals; grand total (bucket cells are values) |
| **Bank reconciliation report** | Section (Statement balance, Deposits in transit, Outstanding checks, Other items), Date, Reference, Payee, Amount | Detail; Subtotal per section; Total | Adjusted bank balance; book balance; the check "difference" that must be 0 |
| **Journal entry list** | Entry number (code), Date, Period, Source, Origin, Reference, Description, Account code, Account name, Debit, Credit, Posted by, Approved by, Status | Detail per line; Subtotal per entry; Total | Entry subtotals; totals; the per-entry check "debits minus credits" |

Each report's columns, filters and saved layout follow G1-G2 (presets store the definition, never numbers).
"Export" always exports exactly what is on screen: the same basis, filters, columns and sort.

---

## 5. CSV

* **Encoding:** UTF-8 with a BOM, so Excel on Windows opens accented names correctly.
* **Separator:** comma; **line ends:** CRLF; **quoting:** RFC 4180 (fields with a comma, quote, CR or LF are
  quoted, and quotes are doubled); **one header row** with the same headers as the Excel export.
* **Money:** plain decimals in dollars, no thousands separators and no currency sign, with a minus sign for
  negatives, made from integer cents with integer arithmetic (`-1234.56` from `-123456`), never through a float.
* **Dates:** ISO 8601 `YYYY-MM-DD`, not the company display format. A CSV has no column types, so a date like
  `03/04/2026` means 3 April or 4 March depending on the computer that opens it. Excel may also rewrite it in
  the local format when the file is saved, and the next import would then misread it. ISO is never ambiguous,
  sorts correctly as text, and the importer always accepts it (csv_import_design.md section 4).
* **Timestamps:** ISO 8601 UTC with `Z`.
* **Codes and ids** are written as they are; Excel may drop leading zeros when it opens a CSV, which is why the
  Excel export is the default for people and the CSV is for systems.
* **No totals rows** in a CSV: data only. Totals belong to the Excel export.
* **Masked values** as in section 2.

---

## 6. Spreadsheet formula injection

**Rule:** a **text** cell whose value starts with `=`, `+`, `-`, `@`, a tab (U+0009) or a carriage return
(U+000D) is neutralized. The full-width forms `＝` (U+FF1D), `＋` (U+FF0B), `－` (U+FF0D) and `＠` (U+FF20) are
treated the same way, as a precaution.
* **CSV:** a single apostrophe `'` is put in front of the value (and the field is quoted). Spreadsheet apps show
  the text and do not run it.
* **XLSX:** the value is written with `write_string` (a string cell can never be a formula) **and** with the cell's
  "quote prefix" style, so the cell stays text even if a user later edits it. The cell shows the original text,
  with no apostrophe added to the value. **Confirm before building:** the XlsxWriter format property for the quote
  prefix (`set_quote_prefix`, not in the pages read).
* Only text and code cells are affected. Money and numbers are number cells, so a negative amount is never
  changed.
* **Import side:** when the importer reads a text cell that starts with an apostrophe followed by one of the
  characters above, it removes that one apostrophe, so an exported file comes back exactly as it was (section 8).
  Stored text is never changed: neutralizing happens only on the way out.
* **Tests:** section 12.

---

## 7. Security

* **Permissions:** `report.export` **and** the report's own permission (`report.financial`, `report.job_cost`,
  `ar.view`, `ap.view`, `ledger.view` and so on). The report runs under the user's own permissions (G7): project
  scope limits job-scoped reports (`report.job_cost` is project-scoped), and masked fields stay masked (wages need
  `payroll.view`, tax IDs `view.tax_ids`, bank details `view.bank_details`) through the one shared masking helper
  (roles design). A masked value is never written to a hidden column, a comment, a formula or the Parameters
  sheet.
* **The AI can never export:** `report.export` is not in `AGENT_ALLOWED` (G7, already true), and `run_export`
  refuses `origin = 'Agent'` before anything else, with a test. The AI can run a report, but not export it.
* **Audit entry for every export:** who, the report key, the filters (as stored in a preset: words and ids, never
  values from the rows), the basis, the format, the row count, the file name and its SHA-256, and the checkpoint.
  Never any data. The baseline has no table for this; proposed: an append-only `export_event` table in the company
  file, with an audit trigger like the others (section 13). A denied export is logged through `authorize`'s
  denial path as today.
* **The `Report export` checkpoint** (a kind already in the baseline) is written for every export of a ledger
  report, and its string is printed on the Parameters sheet (audit design 3, "the export design adds the footer
  hook").
* **Row-count guard:** the service counts the rows before building them.
  * Excel: above **250,000 rows**, refused: "This export has 412,380 rows, more than Excel handles well; narrow the
    date range, or export as CSV." Excel's own hard limit is 1,048,576 rows per sheet.
  * Above **50,000 rows**, the screen asks first ("This export has 84,000 rows and may take a minute. Export?"),
    and the service needs `confirm_large=True`.
  * **Streaming for large ledgers:** GL detail and the journal entry list read in pages (keyset on `entry_number`,
    `line_id`), never all at once. The XLSX writer uses `constant_memory` mode and the CSV writer writes row by row
    to the storage stream. The export runs in the background with progress and a Cancel button (like the
    verification in backlog 14). A cancelled export deletes its partial file and writes no audit row.

---

## 8. Round trip and import templates

* **Same layout as the importer:** journal entries, bills, invoices, budgets and contacts export with exactly the
  columns, headers and order their import type accepts (csv_import_design.md section 5), in CSV and XLSX. A file
  exported and imported unchanged produces the same rows. Saved column layouts (F6) apply in both directions.
* **Not yet import types:** csv_import_design.md section 1 has chart of accounts, customers, vendors, invoices and
  bills. **Journal entries and budgets are not import types yet**; they need their import type definitions (budget
  columns from J2) before their round trip can be built.
* **Blank import templates:** for every import type, a downloadable `.xlsx` with:
  * a **Template** sheet: the header row, one sample row and typed columns (codes as text, dates as dates, money as
    numbers);
  * a **Data dictionary** sheet: each column's name, required or optional, type, allowed values (for example
    `account_type`), an example, and a one-sentence note;
  * plus the CSV version (UTF-8 BOM, the header and the sample row), which is the "Download sample CSV" that
    csv_import_design.md section 3 already describes.

---

## 9. Import: what is added to csv_import_design.md

**Already covered there (not restated):** the five-step page, column mapping saved by name, parsing rules for
money, dates, text and limits (section 4), all-or-nothing commit (section 6.2), the downloadable error list with
row number, column, message and the original values (section 3 step 5), file and row idempotency (6.3), and
nothing posting from an import (6.1).

**Added by this design:**
* **XLSX upload** as well as CSV: the first sheet, or a sheet the user picks when there is more than one.
  * The header is the first non-empty row.
  * Read with openpyxl in `read_only` and `data_only` mode, so **values, never formulas**: a formula cell gives the
    value Excel saved.
  * A formula cell with no saved value is a row error: "Row 12, Amount: this cell has a formula with no saved
    result; open the file in Excel, save it, and upload it again."
  * Excel date cells are accepted as dates (no date-format question). Number cells go through `str()` to
    `Decimal`, never float arithmetic.
  * Hidden rows and sheets are read like visible ones, and the preview says how many were hidden.
  * Safety: `defusedxml` installed; the file's total uncompressed size and its number of entries are checked
    before opening (a zip-bomb guard, with the same 20 MB file limit as CSV); macros (`.xlsm`) and old `.xls`
    files are refused with a sentence that says to save as `.xlsx` or `.csv`.
* **The leading-apostrophe rule** of section 6.
* **A one-sentence fix for every error**, added as its own column ("Fix") next to the message: for example
  "Account 6100 does not exist; add it to the chart of accounts or correct the code."
* **The error report in XLSX** as well as CSV: the original columns, then Row number, Column, Value, Message and
  Fix. Codes are text, and the error rows sort in file order.
* **The value** of the failing cell, as the user typed it, in the error report.

---

## 10. Screens (described, not built; docs/CLAUDE_UI.md, 0b)

* **Report screens:** the toolbar's right side has **Export** (a split button: "Excel" by default, "CSV" in its
  menu) and **Save as preset** (G2). Export is hidden for users without `report.export` (the service still
  checks). It exports what is on screen.
* **List screens** (contacts, accounts, invoices, bills, journal entries): Export in the list toolbar, with CSV
  and Excel; for types that can be imported, a menu item "Download import template".
* **Drill-down:** every drill-down view (a report line's entries) has the same Export button.
* **Success:** a non-blocking message: "Exported 1,284 rows to ACME Profit and loss Oct 2026.xlsx." with **Open
  file** and **Open folder**, plus the unverified range sentence when there is one.
* **Failures** (one sentence each, saying what to do):
  * no permission: "You do not have permission to export reports; ask an Admin.";
  * too many rows: section 7;
  * file in use: "The file is open in another program; close it and try again.";
  * disk full or not writable: "The export could not be saved; check that there is free space in the data
    folder.";
  * anything else: the R35 sentence ("Something went wrong saving this; nothing was saved. The details are in the
    log.").

---

## 11. Hook only: the Excel FP&A model (J4, J5)

The FP&A export with an actuals refresh and the AI reforecast is designed later. This design must leave room for
it:
* **Stable named ranges** (workbook-level `define_name`, for example `SL_Actuals`, `SL_Periods`, `SL_Accounts`),
  whose names never change between versions, so a user's model can refer to them and a refresh can replace the
  data under them.
* **A hidden data sheet** (`_sl_data`, hidden, not "very hidden", so an accountant can unhide it) holding the flat
  actuals (account code, period, dimension codes, amount in dollars) that the named ranges point to.
* **A version cell** on the Parameters sheet (`export_format_version`), so a refresh knows the layout.
* The writer builds every workbook through one `WorkbookPlan` object (sheets, ranges and names), so the FP&A export
  can add sheets without a second writer.

---

## 12. Test plan (tests first, in the build phase)

* **Formula injection:** every trigger character (including tab, CR and the full-width forms) at the start of a
  contact name, memo and description produces a neutralized CSV field and a string cell with the quote prefix; a
  negative money value is unchanged; a re-import gives back the original text.
* **Leading zeros:** account `0100`, ZIP `02134`, check `000457` and entry `JE-000001` survive in XLSX (string
  cells, text format) and CSV.
* **Cents to dollars:** every amount from -$99,999,999,999.99 to $99,999,999,999.99 at the edges, and 10,000 random
  ones, written and read back, equal `cents / 100` exactly; the CSV text equals the integer-arithmetic string; no
  float is used on the CSV path (a test feeds a cents value whose float form would be wrong in the last digit).
* **BOM and encoding:** a CSV starts with `EF BB BF`, uses CRLF, and round-trips `Ñ`, `é`, `—` and CJK text.
* **Masked fields absent:** a user without `view.tax_ids`, `view.bank_details` or `payroll.view` exports a report;
  a scan of every cell, the shared strings, the defined names, the comments and the Parameters sheet finds no
  unmasked value.
* **Audit entry without data:** every export writes one `export_event` with counts and the file hash; a test
  checks that no row value appears in it.
* **Permission denied:** without `report.export`, or without the report's own permission, or a job outside the
  user's scope: refused before any read, and the denial logged; an Agent context refused.
* **Round trip:** invoices, bills, contacts, journal entries and budgets exported and imported give identical rows
  (once JE and budget import types exist).
* **No merged cells and one header row:** the XLSX has no `mergeCell` element, nothing above the header, and no
  empty row inside the data.
* **Formulas match recomputed values:** for each v1.0 report, every formula's cached value equals the service's
  total in cents divided by 100, and recalculating the workbook (LibreOffice headless in a developer tool, not in
  the suite) gives the same values.
* **Large export guard:** above the limit refused with the sentence; above the confirm threshold refused without
  `confirm_large`; a 300,000-row CSV streams with flat memory.
* **Import (section 9):** XLSX values not formulas; a formula with no saved value is an error with its sentence;
  `.xlsm` and `.xls` refused; a zip bomb refused; the error report has the row number, column, value, message and
  fix.

---

## 13. Phase placement and baseline gaps

* **v1.0:** the export service and both writers; the v1.0 reports in section 4 as each report is built (backlog
  6); list exports; XLSX upload and the error report additions; the import templates for the existing import types;
  the `export_event` table; the row guard and streaming.
* **v1.1:** construction reports (WIP schedule, job cost by cost code, pay application and retainage reports, POC)
  with the same writers; journal entry and budget round trips once their import types exist, if not done in v1.0.
* **Deferred:** the FP&A model export with actuals refresh and the AI reforecast (J4, J5; section 11); PDF export;
  scheduled or emailed exports.

**Baseline and code gaps (report only; nothing changed):**
* No `export_event` table (or another place to record exports without data).
* `storage.py` has no streaming write.
* No spreadsheet library in requirements.txt (XlsxWriter and openpyxl, with `defusedxml`, to be added after the
  licence and PyInstaller check in section 3).
* Journal entries and budgets are not import types in csv_import_design.md.
* No company number format setting (csv_import_design.md question 3 is still PROPOSED); exports use `.` as the
  decimal point in CSV regardless, and Excel number formats are locale-independent.

---

## 14. Open questions, with proposed answers

1. **Which writer library?** Proposed: XlsxWriter to write (cached formula results, constant memory, no
   dependencies) and openpyxl only to read uploads. openpyxl cannot write cached formula results.
2. **Where do exports go?** Proposed: `Exports/<company code>/` in the data folder through `storage.py` (H3), with
   Open file and Open folder, plus "Save a copy as..." on the success message for another folder (the screen picks
   the path, and storage copies the file). Hosted: object storage and a download link.
3. **Row limits:** proposed 250,000 rows for Excel (refuse above), a confirmation above 50,000, and CSV
   unlimited but streamed.
4. **Subtotals with `SUBTOTAL(9, …)` rather than `SUM`?** Proposed yes (filters and nested totals work).
5. **Excel dates in the company format, CSV in ISO?** Proposed yes (sections 2 and 5).
6. **Do all exports write a `Report export` checkpoint, or only ledger reports?** Proposed: only reports built from
   the journal (TB, P&L, balance sheet, cash flow, GL detail, JE list, bank rec); lists (contacts, accounts) do
   not.
7. **Who holds `report.export`?** Today it is the Reports "Full" level in docs/role_templates.md, and the Auditor
   starter role (K9) is not a template yet. Proposed: the Auditor gets it when its template is added (auditors
   work in Excel); Viewer stays without it.
8. **Full-width trigger characters:** proposed neutralized too (section 6), as a precaution.
