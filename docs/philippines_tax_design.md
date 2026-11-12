# Philippines tax module: design draft

Status: DESIGN ONLY. NOT BUILT. Items marked PROPOSED are not decided.
Items marked VERIFY come from secondary sources or from memory and must be
confirmed by a Philippine accountant (and the BIR text) before anyone builds
or relies on them. This is not tax advice.

Conventions follow CLAUDE.md: integer cents, rates REAL, ISO dates, UTC
timestamps, writes through service functions, posted records locked,
corrections by reversing entries.

PACKAGING DECISION (user, 2026-11-10): everything Philippine is an ADD-ON
module that can be turned on and off per company, with its code in separate
files (section 11). Where sections 3-9 add columns to core tables, section 11
supersedes them: the fields live in add-on side tables instead.

Depends on: migration 004 (`invoice_series`, `company_settings.regime`),
migration 006 (`journal_line` source keys, controlled accounts), the
vendor/customer contact model, and `tax_rate`.

Sources used for the facts below (secondary sources, summarized):
- Grant Thornton PH, "BIR issues guidelines on electronic invoicing, retains
  31 Dec 2026 deadline" (RMC 098-2026)
- Grant Thornton PH, "Clarification on the invoicing requirements per RR No.
  7-2024 as amended by RR No. 11-2024" (RMC 77-2024)
- Mynd Solution, "BIR withholding tax compliance in accounts payable"

---

## 1. Scope and approach

Three areas, all needed (confirmed by the user): VAT, withholding tax, and
invoicing/e-invoicing. They apply only to companies whose
`company_settings.regime` = Philippines. US companies are unaffected.

The module sits on top of the general ledger. It does not change the ledger
rules. Tax amounts post to controlled tax accounts, and every tax ledger line
carries its `tax_rate_id` so tax reports are built from the ledger.

Not designed: income tax returns, percentage tax for non-VAT companies,
payroll withholding (compensation), SSS/PhilHealth/Pag-IBIG, import duties,
BIR-prescribed file formats beyond what is listed.

---

## 2. Timeline warning

Per the Grant Thornton alert on RMC 098-2026 (VERIFY), covered taxpayers must
issue electronic invoices on or before 31 December 2026, and need a Permit to
Issue (PTI) Electronic Invoice first, then EIS certification within six
months of the PTI. Covered groups include taxpayers using computerized
accounting systems or invoicing software, large taxpayers and e-commerce
sellers.

This roadmap will not have a production-ready e-invoicing feature by that
date. Any accountant selling to a covered Philippine business would need a
certified invoicing solution alongside StrataLedger until then. Product
position (PROPOSED): ship the US construction product first, mark Philippine
mode as beta without e-invoicing, and add e-invoicing later through the
adapter in section 7 (own build, or an integration with a certified provider).

---

## 3. Company and contact data

**company tax profile** (fields on `company_settings` or a `company_tax_profile`
table): `tin`, `branch_code`, `registered_name`, `registered_address`,
`vat_status` [VAT, Non-VAT], `is_withholding_agent` 0/1,
`is_top_withholding_agent` 0/1 (affects rates, VERIFY), `pti_reference`,
`pti_date`, `eis_certified_date`, `cas_registration_ref` (VERIFY whether
computerized books must be registered).

**contact**: existing `tax_id` (TIN) and `bir_registered_name`; add
`branch_code`, `vat_status` [VAT, Non-VAT, Unknown], `tax_classification`
[Individual, Corporation, Non-resident foreign], `default_atc_code` (opt).
The mailing address is the registered address unless a separate field is
added.

---

## 4. VAT

- **tax_rate** gains: `tax_kind` [Sales tax, VAT output, VAT input,
  Withholding creditable, Withholding final], `atc_code` (opt),
  `applies_to` [Sales, Purchases], `base` [Net of VAT, Gross],
  `payable_account_id`, `receivable_account_id`, `effective_from`,
  `effective_to`. Rates are data, not code.
- **invoice_line** gains: `vat_category` [VATable, Zero-rated, Exempt, Not
  subject to VAT] and `vat_cents`.
- **Sales (VAT company):** Dr AR (gross), Cr Revenue (net of VAT), Cr Output
  VAT payable. Invoice prints VATable, zero-rated and exempt sales and the VAT
  amount.
- **Purchases:** Dr Expense or asset (net), Dr Input VAT, Cr AP. Input VAT is
  recorded only when the vendor invoice shows VAT and the vendor is VAT
  registered. Input VAT on capital goods and unclaimed input VAT rules are
  VERIFY.
- **Non-VAT company:** no VAT lines; a percentage-tax option is NOT designed.
- A VAT quarter summary view: output VAT, input VAT, net payable, and the
  carry-over of excess input VAT (VERIFY the rules).
- Existing rule stays: tax is never deferred. Invoice lines on POC projects
  still carry VAT; the VAT timing for progress billings is VERIFY.

---

## 5. Withholding tax

### 5.1 When we pay (we are the withholding agent)

Per the Mynd Solution summary (VERIFY): withholding applies to the amount
excluding VAT; typical creditable (expanded) rates include 5% rentals, 5% or
10% professional fees, 2% contractors/services, and 1% goods / 2% services for
top withholding agents; final withholding applies to non-resident foreign
payments (25%, plus 12% final withholding VAT). Withholding is recorded at the
earlier of expense accrual or invoice receipt.

**invoice_line** gains: `atc_code`, `withholding_rate`,
`withholding_base_cents`, `withholding_cents`.
**invoice** gains: `withholding_total_cents`. Amount due to the vendor =
`total_cents` - `withholding_total_cents`.

Posting a bill: Dr Expense/asset (net of VAT), Dr Input VAT, Cr Withholding tax
payable (by ATC, creditable or final), Cr Accounts payable (net of
withholding). Payment pays the net amount to the vendor.

Captured for every withheld payment (from the Mynd Solution list): payee TIN,
registered name and classification, ATC, invoice details, tax base net of
VAT, rate, tax withheld, net payment, and the quarter and period.

**Remittance:** a payment to the BIR (a vendor "BIR") allocated to the
withholding payable. The tracker (section 8) shows the forms and due dates:
- 0619-E: monthly for months 1 and 2 of a quarter, due the 10th of the next
  month.
- 1601-EQ: quarterly, due the last day of the month after quarter end, filed
  with the QAP (quarterly alphalist of payees).
- 1604-E: annual, due March 1.
- Form 2307 to the payee: on payment or within 20 days after quarter end.
(all from the Mynd Solution summary; VERIFY dates and forms.)

### 5.2 When customers withhold from us

The customer pays the invoice less withholding and owes us Form 2307.
- **payment_allocation** gains `withholding_cents`: Dr Bank (cash received),
  Dr Creditable withholding tax (asset), Cr AR (full invoice).
- The creditable balance is applied against income tax (not designed).

### 5.3 Certificates

**tax_certificate**: `certificate_id`, `direction` [Issued by us, Received],
`form_type` [2307, other], `contact_id`, `period_year`, `period_quarter`,
`atc_code`, `income_payment_cents`, `tax_withheld_cents`, `certificate_number`
(opt), `due_date`, `received_date` (opt), `status` [Expected, Issued or
Received, Overdue, Not applicable], `file_hash` (opt; scanned copy through the
document table).

- Issued: created automatically from withheld bills; due 20 days after
  quarter end (VERIFY); the screen lists which payees still need one.
- Received: created as Expected when a customer short-pays by withholding;
  marked Received when the certificate arrives. The report shows creditable
  tax claimed without a certificate.
- The AI agent may read a scanned certificate and propose the match; a person
  confirms.

---

## 6. Invoicing (after the EOPT changes)

Per the Grant Thornton summaries of RR 7-2024 / RMC 77-2024 (VERIFY):
- The sales/VAT invoice is the primary document for goods and services. VAT
  sellers must issue one for every sale; non-VAT sellers when a transaction
  exceeds PHP 500 or the buyer asks (threshold adjusted every three years).
- Official receipts may remain as supplementary documents, stamped "This
  document is not valid for claim of input tax."
- A change from receipts to invoices needs a new Authority to Print (ATP),
  with a separate serial series per invoice type.
- To support the buyer's input VAT claim, the invoice shows: sales amount, VAT
  amount, registered names and TINs of seller and buyer, description, date.

Design:
- `invoice_series` (migration 004) carries the registered range and permit
  reference. Philippine mode requires them and blocks numbers outside the
  range.
- Document types: Sales Invoice (our `Invoice`), Credit Memo, and an optional
  supplementary Collection Receipt tied to a payment (own series, stamped
  text). PROPOSED; VERIFY whether a collection receipt is needed.
- The invoice print layout is a Philippine template with the required fields.
- Branch: invoices are issued per TIN and branch; the series can be tied to
  a branch code.

---

## 7. E-invoicing

Per RMC 098-2026 as summarized (VERIFY): the invoice is issued electronically
to the buyer and the sales data is transmitted or reported to the BIR in the
BIR-prescribed structured format (JSON); separate PTIs are needed for distinct
invoicing systems; during an outage, a BIR-authorized manual invoice is issued
and later replaced by an electronic invoice that references the manual one.

The BIR technical specification (field list, API, authentication) was NOT
found in these sources and must be obtained before building.

Design (PROPOSED):
- **Outbox adapter.** Posting an invoice never waits on the BIR. The service
  writes a transmission job; a separate adapter sends it and records the
  result, with retries. Ledger posting and transmission are independent.
- `invoice` gains: `eis_status` [Not required, Pending, Transmitted, Failed,
  Replaced], `eis_reference`, `eis_transmitted_at`. The existing
  `is_eis_transmitted` flag is migrated into `eis_status`.
- **eis_transmission**: `transmission_id`, `invoice_id`, `attempt_no`,
  `requested_at`, `status`, `response_code`, `response_text`,
  `payload_hash`, `payload_file` (the JSON sent), `replaced_invoice_id` (opt).
- **Outage workflow:** a manual invoice records `manual_invoice_ref`; when
  service returns, the electronic replacement carries that reference and the
  manual one is marked Replaced.
- A transmitted invoice is locked (already enforced for invoices); the
  transmission fields are the only fields that change after sending, and they
  are audit-logged.
- Company flags: `pti_reference`, `eis_certified_date`; a warning when a
  covered company issues an invoice without them.
- Desktop: the outbox needs internet and queues while offline.
- Unknown: whether StrataLedger itself must be accredited or certified as
  invoicing software, or only the taxpayer's use of it. VERIFY.

---

## 8. Tracker, reports and controls

**tax_filing** (calendar and status): `filing_id`, `return_type` [VAT
quarterly, 0619-E, 1601-EQ, 1604-E, other], `period_start`, `period_end`,
`due_date`, `status` [Not started, Prepared, Filed, Paid], `amount_cents`,
`reference_number`, `filed_date`, `payment_id` (opt). Due dates are data (a
rules table), not code. The app prepares the figures; filing happens on the
BIR portal (PROPOSED v1). Output files in BIR formats (QAP DAT) are a later
option, VERIFY the format.

**Controlled accounts:** Output VAT payable, Input VAT, Withholding tax
payable, Creditable withholding tax. Lines must come from the tax services;
manual entries are blocked. `journal_line.tax_rate_id` ties each line to a
rate.

**Reports:** VAT summary by quarter; sales and purchase listings with TINs;
withholding by ATC, payee and quarter (1601-EQ and QAP source data);
certificates issued and expected; creditable tax balance; filing calendar;
EIS status (pending, failed, replaced); invoice series usage against the
registered range; tie-out of tax accounts to the transaction detail.

---

## 9. Placement

PROPOSED migrations after loans: 011 tax foundations (tax_rate fields,
contact and company tax data, invoice line tax fields, tax_certificate,
tax_filing), 012 e-invoicing outbox. `journal_line.tax_rate_id` and the tax
control types go into the ledger-keys migration (006). Philippine mode is
inactive for companies with regime Standard.

---

## 10. Product decisions and open questions

1. Market order: US construction accountants first, Philippines second
   (PROPOSED)? Is Philippine mode part of the first release at all?
2. E-invoicing: build our own BIR transmission and seek certification, or
   integrate with a certified provider through the adapter (PROPOSED)? Needs
   the BIR technical specification either way.
3. Ship gate: a Philippine tax professional reviews VAT, withholding and
   invoicing logic before Philippine mode leaves beta (PROPOSED).
4. Does the product need to be registered or certified itself as accounting
   or invoicing software in the Philippines? VERIFY with the BIR.
5. BIR-format output files (QAP DAT) or just the figures, in version 1?
6. VAT edge cases to support first (zero-rated, exempt, capital goods,
   progress billings), all VERIFY.
7. Is corporate income tax ever in scope?

---

## 11. Add-on packaging (supersedes where it conflicts)

### 11.1 Rules
1. Core never imports an add-on. An add-on may call core service functions and
   pure helpers only through their public interface.
2. Core exposes hook points; an enabled add-on registers handlers for them.
   A disabled add-on registers nothing, so core behaves as if it did not exist.
3. Add-on tables are prefixed `ph_` and keyed to core ids. Add-on migrations
   have their own numbering (`ph_001`, `ph_002`, ...) and version in
   `addon_schema_version`. Core tables are not altered by an add-on.
4. Turning an add-on off hides its screens and stops its hooks. Its tables and
   data are never dropped. Posted documents stay locked. A warning lists
   pending work (unsent e-invoices, unfiled returns) before disabling.
5. No network calls, endpoints or credentials are written until the BIR
   specification is available. The only transport built now is a dry-run.

### 11.2 Core support (small, generic, country-neutral)
- `company_addon` (core migration): `addon_key`, `enabled`, `enabled_at`,
  `enabled_by`, `addon_version`. Replaces the `regime` setting.
- `addon_schema_version` (core migration): `addon_key`, `version`.
- A hook registry in the service layer (Phase 2): named events such as
  `invoice.before_post`, `invoice.after_post`, `bill.before_post`,
  `payment.before_allocate`, `series.before_issue`, with ordered handlers. A
  handler can reject (raise) or add data; it cannot post on its own.
- `invoice_series` registered-range fields stay in core (country-neutral);
  the add-on makes them mandatory through `series.before_issue`.
- `journal_line.tax_rate_id` and tax control types stay in core (generic).
- Cleanup (a later core migration): the legacy `invoice.is_eis_transmitted`
  moves to the add-on's side table, and the core invoice-lock exception for it
  goes away.

### 11.3 Add-on tables (replace the core-column changes in sections 3-8)
- `ph_company_profile` (TIN, branch code, registered name and address, VAT
  status, withholding-agent flags, PTI and EIS dates, CAS reference)
- `ph_contact_tax` (contact_id, branch code, VAT status, classification,
  default ATC)
- `ph_invoice_line_tax` (line_id: VAT category, VAT cents, ATC, withholding
  rate, base and amount)
- `ph_invoice_info` (invoice_id: withholding total, EIS status, reference,
  transmitted time, manual invoice reference)
- `ph_tax_certificate`, `ph_tax_filing`, `ph_eis_transmission`

### 11.4 Package layout (code in separate files)
    addons/ph_tax/
      __init__.py          manifest: key, version, minimum core schema version
      migrations/          ph_001.sql, ph_002.sql, ...
      hooks.py             registers handlers (the only file that touches hooks)
      services.py          VAT, withholding, certificates (later)
      invoice_print.py     paper invoice renderer (pure function, build now)
      templates/           ph_sales_invoice layout files, plain text and HTML
      eis_payload.py       invoice -> e-invoice JSON mapper (pure, build now,
                           DRAFT schema)
      eis_transport.py     transport interface + dry-run transport (build now)
      eis_outbox.py        queue, retries, status (after the service layer)
      reports.py           VAT, withholding, certificates (later)

### 11.5 What can be built now
Pure functions with no database and no network, unit-tested with fixed sample
data:
1. **BIR paper invoice:** `invoice_print.py` turns an invoice, seller, buyer and
   lines into a printable HTML page and a plain-text version, using layout
   files in `templates/` that can be edited without code. Required content from
   the sources: registered names, TINs and addresses of seller and buyer, date,
   description, VATable / zero-rated / exempt sales, VAT amount, total, and the
   serial number from the registered series. The authority-to-print details
   (permit number, date issued, approved range, printer) print from the series
   and profile (VERIFY exact wording and layout rules). Supplementary receipts
   carry the stamp "This document is not valid for claim of input tax."
2. **E-invoice payload:** `eis_payload.py` builds the structured JSON and
   validates completeness (names, TINs, totals equal the sum of lines). The
   schema is a labeled DRAFT until the BIR specification is obtained.
3. **Transport:** `eis_transport.py` defines the interface and a dry-run
   transport that writes the JSON to an Outbox folder. No network.

Built later, after the service layer and the hook registry: the add-on
migrations, hooks, outbox, VAT, withholding, certificates, filing tracker and
reports, and the screens.

### 11.6 Updated placement
- Core (small, generic) in the Phase 2 service layer: hook registry, add-on
  registry and add-on migration runner; `company_addon` and
  `addon_schema_version` in migration 004.
- The add-on is built in its own folder, with its own tests; its migrations
  are not numbered in the core series (supersedes migrations 011 and 012).
