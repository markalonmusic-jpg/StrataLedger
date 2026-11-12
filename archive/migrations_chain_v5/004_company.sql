-- Migration 4 (company): High controls. See docs/controls_audit.md (sections
-- 10-11) and the decisions recorded there.
--
-- Periods (decision 4, P3, P4): journal_entry.period_id is NOT NULL and must
--     be the period that contains entry_date (the service sets it). Periods
--     are contiguous with no overlap; only outer edges of the range move, and
--     only while unused; closing records closed_at/closed_by. Reopening with
--     a logged reason is enforced in the service layer.
-- Posting (T2, T3): who created and posted the entry and when; a gapless
--     entry_number from entry_number_sequence; approval columns (the approver
--     cannot be the creator; when approval is required is decided by the
--     service layer, decision 6); origin [Human, Agent, Import, System].
-- Chart of accounts (A1, A2, decision 5): the five account types are seeded;
--     type_id is required; control_type marks controlled accounts (blocking
--     manual entries to them is service-layer); an account with posted
--     entries keeps its code, type, parent and control type.
-- Invoices (C4, C5, C8, decision 3): ledger_side [Sales, Purchase]; sales
--     invoices and credit memos take the next number of an active registered
--     invoice_series when they leave Draft (prefix + 6 digits), never reused
--     or changed; purchase documents keep manual numbers; leaving Draft needs
--     a contact and a subtotal equal to the lines; one journal entry belongs
--     to one source document.
-- Ledger keys (C11, X1): journal_line tags are real foreign keys; lines of a
--     completed bank reconciliation are locked; journal_line_dimension.
-- Data quality (D1, D2, decisions 6-7): ISO checks on every date column and
--     0/1 checks on every flag; company_settings.base_currency (default USD)
--     and the manual-entry approval setting; no FX before Phase 4.
-- Add-ons: company_addon and addon_schema_version (no cascades, so
--     disabling an add-on never drops data).
--
-- Same rebuild procedure as 002/003. Triggers on rebuilt tables are dropped
-- first and recreated at the end; unchanged 003 triggers are recreated
-- verbatim.

DROP TRIGGER IF EXISTS audit_account_delete;
DROP TRIGGER IF EXISTS audit_account_insert;
DROP TRIGGER IF EXISTS audit_account_update;
DROP TRIGGER IF EXISTS audit_company_settings_insert;
DROP TRIGGER IF EXISTS audit_company_settings_update;
DROP TRIGGER IF EXISTS audit_fiscal_period_delete;
DROP TRIGGER IF EXISTS audit_fiscal_period_insert;
DROP TRIGGER IF EXISTS audit_fiscal_period_update;
DROP TRIGGER IF EXISTS audit_invoice_delete;
DROP TRIGGER IF EXISTS audit_invoice_insert;
DROP TRIGGER IF EXISTS audit_invoice_update;
DROP TRIGGER IF EXISTS audit_journal_entry_delete;
DROP TRIGGER IF EXISTS audit_journal_entry_insert;
DROP TRIGGER IF EXISTS audit_journal_entry_update;
DROP TRIGGER IF EXISTS audit_payment_allocation_delete;
DROP TRIGGER IF EXISTS audit_payment_allocation_insert;
DROP TRIGGER IF EXISTS audit_payment_allocation_update;
DROP TRIGGER IF EXISTS audit_payment_delete;
DROP TRIGGER IF EXISTS audit_payment_insert;
DROP TRIGGER IF EXISTS audit_payment_update;
DROP TRIGGER IF EXISTS invoice_line_dimension_lock_delete;
DROP TRIGGER IF EXISTS invoice_line_dimension_lock_insert;
DROP TRIGGER IF EXISTS invoice_line_dimension_lock_update;
DROP TRIGGER IF EXISTS invoice_line_lock_delete;
DROP TRIGGER IF EXISTS invoice_line_lock_insert;
DROP TRIGGER IF EXISTS invoice_line_lock_update;
DROP TRIGGER IF EXISTS invoice_lock;
DROP TRIGGER IF EXISTS invoice_lock_delete;
DROP TRIGGER IF EXISTS invoice_status_flow;
DROP TRIGGER IF EXISTS journal_entry_lock_delete_posted;
DROP TRIGGER IF EXISTS journal_entry_lock_posted;
DROP TRIGGER IF EXISTS journal_entry_no_direct_post;
DROP TRIGGER IF EXISTS journal_entry_no_draft_void;
DROP TRIGGER IF EXISTS journal_entry_require_balance_on_post;
DROP TRIGGER IF EXISTS journal_entry_void_on_reversal;
DROP TRIGGER IF EXISTS journal_line_lock_delete_posted;
DROP TRIGGER IF EXISTS journal_line_lock_insert_posted;
DROP TRIGGER IF EXISTS journal_line_lock_update_posted;
DROP TRIGGER IF EXISTS payment_allocation_lock_delete;
DROP TRIGGER IF EXISTS payment_allocation_lock_update;
DROP TRIGGER IF EXISTS payment_allocation_no_voided_payment;
DROP TRIGGER IF EXISTS payment_lock;
DROP TRIGGER IF EXISTS payment_lock_delete;

-- ---------------------------------------------------------------------------
-- New tables
-- ---------------------------------------------------------------------------

-- Decision 3: numbered series for sales invoices and sales credit memos. The
-- service takes the next number by moving last_number up by exactly one and
-- writing that number on the document in the same transaction.
CREATE TABLE invoice_series (
    series_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_type TEXT NOT NULL CHECK (document_type IN ('Invoice', 'Credit Memo')),
    prefix TEXT NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0 CHECK (typeof(last_number) = 'integer' AND last_number >= 0),
    registered_from INTEGER CHECK (registered_from IS NULL OR registered_from > 0),
    registered_to INTEGER,
    authority_ref TEXT,
    valid_until TEXT CHECK (valid_until IS date(valid_until)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    CHECK ((registered_from IS NULL) = (registered_to IS NULL)),
    CHECK (registered_from IS NULL OR registered_from <= registered_to),
    CHECK (registered_to IS NULL OR last_number <= registered_to),
    CHECK (registered_from IS NULL OR last_number >= registered_from - 1)
);

-- T3: posted journal entries are numbered without gaps from this counter.
CREATE TABLE entry_number_sequence (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_number INTEGER NOT NULL DEFAULT 0 CHECK (typeof(last_number) = 'integer' AND last_number >= 0)
);

-- Add-ons (docs/philippines_tax_design.md section 11). No foreign keys or
-- cascades, so disabling or removing an add-on can never drop data.
CREATE TABLE company_addon (
    addon_key TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    enabled_at DATETIME,
    enabled_by INTEGER,
    addon_version TEXT
);

CREATE TABLE addon_schema_version (
    addon_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    PRIMARY KEY (addon_key, version)
);

-- A2: the five account types every chart needs (kept if already present).
INSERT INTO account_type (name, normal_balance)
    SELECT column1, column2
    FROM (VALUES ('Asset', 'D'), ('Liability', 'C'), ('Equity', 'C'), ('Revenue', 'C'), ('Expense', 'D'))
    WHERE NOT EXISTS (SELECT 1 FROM account_type WHERE name = column1);

-- ---------------------------------------------------------------------------
-- Rebuilt tables (the version-3 definition plus only the changes noted)
-- ---------------------------------------------------------------------------

-- fiscal_period: is_closed 0/1 NOT NULL; start <= end; who closed it and when.
-- Contiguity, date locks and closing details are enforced by triggers below.
CREATE TABLE new_fiscal_period (
    period_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL CHECK (start_date IS date(start_date)),
    end_date TEXT NOT NULL CHECK (end_date IS date(end_date)),
    is_closed INTEGER NOT NULL DEFAULT 0 CHECK (is_closed IN (0, 1)),
    closed_at DATETIME,
    closed_by INTEGER,
    CHECK (start_date <= end_date)
);
INSERT INTO new_fiscal_period (period_id, name, start_date, end_date, is_closed)
    SELECT period_id, name, start_date, end_date, COALESCE(is_closed, 0) FROM fiscal_period;
DROP TABLE fiscal_period;
ALTER TABLE new_fiscal_period RENAME TO fiscal_period;

-- journal_entry: period_id NOT NULL (the service sets it from entry_date and
-- a trigger validates it); posting number, who posted and when; approval;
-- origin. Existing entries get the period covering their date, and posted
-- ones are numbered in entry order.
CREATE TABLE new_journal_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL CHECK (entry_date IS date(entry_date)),
    period_id INTEGER NOT NULL REFERENCES fiscal_period(period_id),
    reference TEXT,
    description TEXT,
    source TEXT CHECK (source IN ('Manual', 'Invoice', 'Bill', 'Payment', 'Adjustment', 'Payroll', 'Import', 'Deferral', 'Completion')),
    is_posted INTEGER NOT NULL DEFAULT 0 CHECK (is_posted IN (0, 1)),
    is_void INTEGER NOT NULL DEFAULT 0 CHECK (is_void IN (0, 1)),
    reverses_entry_id INTEGER UNIQUE REFERENCES journal_entry(entry_id),
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reversal_reason TEXT CHECK (reversal_reason IN ('Void', 'Accrual reversal', 'Correction')),
    entry_number INTEGER UNIQUE CHECK (entry_number IS NULL OR entry_number > 0),
    posted_by INTEGER,
    posted_at DATETIME,
    approved_by INTEGER,
    approved_at DATETIME,
    origin TEXT NOT NULL DEFAULT 'Human' CHECK (origin IN ('Human', 'Agent', 'Import', 'System')),
    CHECK ((reverses_entry_id IS NULL) = (reversal_reason IS NULL)),
    CHECK (is_posted = 1 OR entry_number IS NULL),
    CHECK ((approved_by IS NULL) = (approved_at IS NULL)),
    CHECK (approved_by IS NULL OR approved_by IS NOT created_by)
);
INSERT INTO new_journal_entry (entry_id, entry_date, period_id, reference, description, source, is_posted, is_void, reverses_entry_id, created_by, created_at, reversal_reason, entry_number)
    SELECT entry_id, entry_date,
           COALESCE(period_id, (SELECT p.period_id FROM fiscal_period AS p
                                WHERE journal_entry.entry_date BETWEEN p.start_date AND p.end_date)),
           reference, description, source, is_posted, is_void, reverses_entry_id, created_by, created_at, reversal_reason,
           CASE WHEN is_posted = 1 THEN ROW_NUMBER() OVER (PARTITION BY is_posted ORDER BY entry_id) END
    FROM journal_entry;
DROP TABLE journal_entry;
ALTER TABLE new_journal_entry RENAME TO journal_entry;

INSERT INTO entry_number_sequence (id, last_number)
    SELECT 1, COUNT(*) FROM journal_entry WHERE is_posted = 1;

-- Existing data must already satisfy the period rule; otherwise the upgrade
-- is blocked (CHECK failure) and the file is left unchanged.
CREATE TABLE migration_004_check (
    every_entry_period_contains_its_date INTEGER CHECK (every_entry_period_contains_its_date = 1)
);
INSERT INTO migration_004_check
    SELECT NOT EXISTS (
        SELECT 1 FROM journal_entry AS e JOIN fiscal_period AS p ON p.period_id = e.period_id
        WHERE e.entry_date NOT BETWEEN p.start_date AND p.end_date
    );
DROP TABLE migration_004_check;

-- journal_line: entry required (L3); every tag is a real foreign key (C11).
CREATE TABLE new_journal_line (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES journal_entry(entry_id),
    account_id INTEGER NOT NULL REFERENCES account(account_id),
    debit_cents INTEGER DEFAULT 0 CHECK (debit_cents >= 0),
    credit_cents INTEGER DEFAULT 0 CHECK (credit_cents >= 0),
    memo TEXT,
    contact_id INTEGER REFERENCES contact(contact_id),
    recon_id INTEGER REFERENCES bank_reconciliation(recon_id),
    project_id INTEGER REFERENCES project(project_id),
    cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
    deferral_id INTEGER REFERENCES deferral(deferral_id),
    batch_id INTEGER REFERENCES import_batch(batch_id),
    is_retainage_line INTEGER DEFAULT 0 CHECK (is_retainage_line IN (0, 1)),
    external_ref TEXT,
    CHECK (debit_cents = 0 OR credit_cents = 0),
    CHECK (debit_cents IS NULL OR typeof(debit_cents) = 'integer'),
    CHECK (credit_cents IS NULL OR typeof(credit_cents) = 'integer')
);
INSERT INTO new_journal_line (line_id, entry_id, account_id, debit_cents, credit_cents, memo, contact_id, recon_id, project_id, cost_code_id, deferral_id, batch_id, is_retainage_line, external_ref)
    SELECT line_id, entry_id, account_id, debit_cents, credit_cents, memo, contact_id, recon_id, project_id, cost_code_id, deferral_id, batch_id, is_retainage_line, external_ref FROM journal_line;
DROP TABLE journal_line;
ALTER TABLE new_journal_line RENAME TO journal_line;

-- X1: dimensions on journal lines (same shape as invoice_line_dimension).
CREATE TABLE journal_line_dimension (
    line_id INTEGER NOT NULL REFERENCES journal_line(line_id) ON DELETE CASCADE,
    dimension_type_id INTEGER NOT NULL,
    dimension_value_id INTEGER NOT NULL,
    PRIMARY KEY (line_id, dimension_type_id),
    FOREIGN KEY (dimension_value_id, dimension_type_id)
        REFERENCES dimension_value(dimension_value_id, dimension_type_id)
        ON DELETE RESTRICT
);

-- account: type required (A2); 0/1 flags; control_type (decision 5).
CREATE TABLE new_account (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type_id INTEGER NOT NULL REFERENCES account_type(type_id),
    parent_id INTEGER REFERENCES account(account_id),
    is_postable INTEGER DEFAULT 1 CHECK (is_postable IN (0, 1)),
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    is_deferral_account INTEGER DEFAULT 0 CHECK (is_deferral_account IN (0, 1)),
    control_type TEXT CHECK (control_type IN (
        'AR', 'AP', 'Sales tax', 'Deferral', 'Retainage', 'Over/under billing',
        'Employee advance', 'Employee material advance', 'Inventory',
        'Fixed asset cost', 'Accumulated depreciation', 'Depreciation expense', 'Equipment cost recovery',
        'Loan principal', 'Loan current portion'))
);
INSERT INTO new_account (account_id, code, name, type_id, parent_id, is_postable, is_active, is_deferral_account)
    SELECT account_id, code, name, type_id, parent_id, is_postable, is_active, is_deferral_account FROM account;
DROP TABLE account;
ALTER TABLE new_account RENAME TO account;

-- invoice: type required; ledger_side; series numbering; manual numbers only
-- on the purchase side; one entry per document (C5); batch is a real key;
-- no FX before Phase 4 (currency NULL = base currency, rate 1).
CREATE TABLE new_invoice (
    invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_type TEXT NOT NULL CHECK (invoice_type IN ('Invoice', 'Bill', 'Credit Memo')),
    contact_id INTEGER REFERENCES contact(contact_id),
    project_id INTEGER REFERENCES project(project_id),
    subscription_id INTEGER REFERENCES subscription(subscription_id),
    invoice_number TEXT,
    issue_date TEXT NOT NULL CHECK (issue_date IS date(issue_date)),
    due_date TEXT NOT NULL CHECK (due_date IS date(due_date)),
    terms TEXT CHECK (terms IN ('Due on Receipt', 'Net 15', 'Net 30', 'Net 60')) DEFAULT 'Net 30',
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Sent', 'Paid', 'Void', 'Covered by advance')),
    currency TEXT,
    exchange_rate REAL DEFAULT 1.0 CHECK (exchange_rate IS NULL OR exchange_rate = 1.0),
    subtotal_cents INTEGER DEFAULT 0,
    vatable_sales_cents INTEGER DEFAULT 0,
    vat_exempt_sales_cents INTEGER DEFAULT 0,
    zero_rated_sales_cents INTEGER DEFAULT 0,
    tax_cents INTEGER DEFAULT 0,
    cwt_rate REAL DEFAULT 0.0,
    cwt_amount_cents INTEGER DEFAULT 0,
    total_cents INTEGER DEFAULT 0,
    retainage_cents INTEGER DEFAULT 0,
    is_eis_transmitted INTEGER DEFAULT 0 CHECK (is_eis_transmitted IN (0, 1)),
    entry_id INTEGER UNIQUE REFERENCES journal_entry(entry_id),
    batch_id INTEGER REFERENCES import_batch(batch_id),
    external_ref TEXT,
    ledger_side TEXT NOT NULL CHECK (ledger_side IN ('Sales', 'Purchase')),
    series_id INTEGER REFERENCES invoice_series(series_id),
    sequence_number INTEGER CHECK (sequence_number IS NULL OR sequence_number > 0),
    UNIQUE (invoice_type, contact_id, invoice_number),
    UNIQUE (series_id, sequence_number),
    CHECK ((invoice_type = 'Invoice' AND ledger_side = 'Sales')
        OR (invoice_type = 'Bill' AND ledger_side = 'Purchase')
        OR invoice_type = 'Credit Memo'),
    CHECK (status <> 'Draft' OR sequence_number IS NULL),
    CHECK (ledger_side = 'Sales' OR (series_id IS NULL AND sequence_number IS NULL)),
    CHECK (subtotal_cents IS NULL OR typeof(subtotal_cents) = 'integer'),
    CHECK (vatable_sales_cents IS NULL OR typeof(vatable_sales_cents) = 'integer'),
    CHECK (vat_exempt_sales_cents IS NULL OR typeof(vat_exempt_sales_cents) = 'integer'),
    CHECK (zero_rated_sales_cents IS NULL OR typeof(zero_rated_sales_cents) = 'integer'),
    CHECK (tax_cents IS NULL OR typeof(tax_cents) = 'integer'),
    CHECK (cwt_amount_cents IS NULL OR typeof(cwt_amount_cents) = 'integer'),
    CHECK (total_cents IS NULL OR typeof(total_cents) = 'integer'),
    CHECK (retainage_cents IS NULL OR typeof(retainage_cents) = 'integer'),
    CONSTRAINT invoice_amounts_positive CHECK (
        subtotal_cents >= 0 AND vatable_sales_cents >= 0 AND vat_exempt_sales_cents >= 0
        AND zero_rated_sales_cents >= 0 AND tax_cents >= 0 AND cwt_amount_cents >= 0
        AND total_cents >= 0 AND retainage_cents >= 0
    )
);
INSERT INTO new_invoice (invoice_id, invoice_type, contact_id, project_id, subscription_id, invoice_number, issue_date, due_date, terms, status, currency, exchange_rate, subtotal_cents, vatable_sales_cents, vat_exempt_sales_cents, zero_rated_sales_cents, tax_cents, cwt_rate, cwt_amount_cents, total_cents, retainage_cents, is_eis_transmitted, entry_id, batch_id, external_ref, ledger_side)
    SELECT invoice_id, invoice_type, contact_id, project_id, subscription_id, invoice_number, issue_date, due_date, terms, status, currency, exchange_rate, subtotal_cents, vatable_sales_cents, vat_exempt_sales_cents, zero_rated_sales_cents, tax_cents, cwt_rate, cwt_amount_cents, total_cents, retainage_cents, is_eis_transmitted, entry_id, batch_id, external_ref,
           CASE WHEN invoice_type = 'Bill' THEN 'Purchase' ELSE 'Sales' END
    FROM invoice;
DROP TABLE invoice;
ALTER TABLE new_invoice RENAME TO invoice;

-- Sales-side numbers are unique across the company (C8, decision 3).
CREATE UNIQUE INDEX invoice_sales_number_unique ON invoice (invoice_number) WHERE ledger_side = 'Sales';

-- invoice_line: ISO service dates; 0/1 flag.
CREATE TABLE new_invoice_line (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    description TEXT,
    quantity REAL DEFAULT 1.0,
    unit_price_cents INTEGER DEFAULT 0,
    account_id INTEGER REFERENCES account(account_id),
    tax_rate_id INTEGER REFERENCES tax_rate(tax_rate_id),
    service_start_date TEXT CHECK (service_start_date IS date(service_start_date)),
    service_end_date TEXT CHECK (service_end_date IS date(service_end_date)),
    is_retainage_line INTEGER DEFAULT 0 CHECK (is_retainage_line IN (0, 1)),
    cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
    department_tag TEXT DEFAULT NULL,
    sort_order INTEGER DEFAULT 0,
    CHECK (unit_price_cents IS NULL OR typeof(unit_price_cents) = 'integer'),
    CONSTRAINT invoice_line_amounts_positive CHECK (unit_price_cents >= 0 AND quantity >= 0)
);
INSERT INTO new_invoice_line (line_id, invoice_id, description, quantity, unit_price_cents, account_id, tax_rate_id, service_start_date, service_end_date, is_retainage_line, cost_code_id, department_tag, sort_order)
    SELECT line_id, invoice_id, description, quantity, unit_price_cents, account_id, tax_rate_id, service_start_date, service_end_date, is_retainage_line, cost_code_id, department_tag, sort_order FROM invoice_line;
DROP TABLE invoice_line;
ALTER TABLE new_invoice_line RENAME TO invoice_line;

-- payment: one entry per document; no FX before Phase 4.
CREATE TABLE new_payment (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT CHECK (direction IN ('Received', 'Made')),
    contact_id INTEGER REFERENCES contact(contact_id),
    payment_date TEXT NOT NULL CHECK (payment_date IS date(payment_date)),
    amount_cents INTEGER NOT NULL,
    currency TEXT,
    exchange_rate REAL DEFAULT 1.0 CHECK (exchange_rate IS NULL OR exchange_rate = 1.0),
    method TEXT CHECK (method IN ('Cash', 'Check', 'Bank Transfer', 'GCash', 'Maya')),
    bank_account_id INTEGER REFERENCES account(account_id),
    entry_id INTEGER UNIQUE REFERENCES journal_entry(entry_id),
    CHECK (typeof(amount_cents) = 'integer'),
    CONSTRAINT payment_amount_positive CHECK (amount_cents > 0)
);
INSERT INTO new_payment (payment_id, direction, contact_id, payment_date, amount_cents, currency, exchange_rate, method, bank_account_id, entry_id)
    SELECT payment_id, direction, contact_id, payment_date, amount_cents, currency, exchange_rate, method, bank_account_id, entry_id FROM payment;
DROP TABLE payment;
ALTER TABLE new_payment RENAME TO payment;

-- deferral_schedule_line: ISO date; one entry per document.
CREATE TABLE new_deferral_schedule_line (
    schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    deferral_id INTEGER REFERENCES deferral(deferral_id),
    period_id INTEGER REFERENCES fiscal_period(period_id),
    amort_date TEXT NOT NULL CHECK (amort_date IS date(amort_date)),
    amount_cents INTEGER NOT NULL,
    status TEXT CHECK (status IN ('Scheduled', 'Posted', 'Skipped')),
    entry_id INTEGER UNIQUE REFERENCES journal_entry(entry_id),
    UNIQUE (deferral_id, period_id),
    CHECK (typeof(amount_cents) = 'integer')
);
INSERT INTO new_deferral_schedule_line (schedule_id, deferral_id, period_id, amort_date, amount_cents, status, entry_id)
    SELECT schedule_id, deferral_id, period_id, amort_date, amount_cents, status, entry_id FROM deferral_schedule_line;
DROP TABLE deferral_schedule_line;
ALTER TABLE new_deferral_schedule_line RENAME TO deferral_schedule_line;

-- poc_snapshot: ISO date; one entry per document.
CREATE TABLE new_poc_snapshot (
    poc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES project(project_id),
    period_id INTEGER REFERENCES fiscal_period(period_id),
    as_of_date TEXT NOT NULL CHECK (as_of_date IS date(as_of_date)),
    cost_to_date_cents INTEGER NOT NULL,
    excluded_cost_cents INTEGER NOT NULL,
    est_cost_to_complete_cents INTEGER NOT NULL,
    revised_contract_cents INTEGER NOT NULL,
    pct_complete REAL NOT NULL,
    earned_revenue_to_date_cents INTEGER NOT NULL,
    revenue_this_period_cents INTEGER NOT NULL,
    billed_to_date_cents INTEGER NOT NULL,
    over_under_billing_cents INTEGER NOT NULL,
    est_gross_profit_cents INTEGER NOT NULL,
    entry_id INTEGER UNIQUE REFERENCES journal_entry(entry_id),
    UNIQUE (project_id, period_id),
    CHECK (typeof(cost_to_date_cents) = 'integer'),
    CHECK (typeof(excluded_cost_cents) = 'integer'),
    CHECK (typeof(est_cost_to_complete_cents) = 'integer'),
    CHECK (typeof(revised_contract_cents) = 'integer'),
    CHECK (typeof(earned_revenue_to_date_cents) = 'integer'),
    CHECK (typeof(revenue_this_period_cents) = 'integer'),
    CHECK (typeof(billed_to_date_cents) = 'integer'),
    CHECK (typeof(over_under_billing_cents) = 'integer'),
    CHECK (typeof(est_gross_profit_cents) = 'integer')
);
INSERT INTO new_poc_snapshot (poc_id, project_id, period_id, as_of_date, cost_to_date_cents, excluded_cost_cents, est_cost_to_complete_cents, revised_contract_cents, pct_complete, earned_revenue_to_date_cents, revenue_this_period_cents, billed_to_date_cents, over_under_billing_cents, est_gross_profit_cents, entry_id)
    SELECT poc_id, project_id, period_id, as_of_date, cost_to_date_cents, excluded_cost_cents, est_cost_to_complete_cents, revised_contract_cents, pct_complete, earned_revenue_to_date_cents, revenue_this_period_cents, billed_to_date_cents, over_under_billing_cents, est_gross_profit_cents, entry_id FROM poc_snapshot;
DROP TABLE poc_snapshot;
ALTER TABLE new_poc_snapshot RENAME TO poc_snapshot;

-- bank_reconciliation: ISO date; 0/1 flag. Locking is by trigger below.
CREATE TABLE new_bank_reconciliation (
    recon_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES account(account_id),
    statement_date TEXT NOT NULL CHECK (statement_date IS date(statement_date)),
    statement_balance_cents INTEGER NOT NULL,
    is_complete INTEGER DEFAULT 0 CHECK (is_complete IN (0, 1)),
    CHECK (typeof(statement_balance_cents) = 'integer')
);
INSERT INTO new_bank_reconciliation (recon_id, account_id, statement_date, statement_balance_cents, is_complete)
    SELECT recon_id, account_id, statement_date, statement_balance_cents, is_complete FROM bank_reconciliation;
DROP TABLE bank_reconciliation;
ALTER TABLE new_bank_reconciliation RENAME TO bank_reconciliation;

-- company_settings: base currency required (decision 7); manual-entry
-- approval setting (decision 6). The service layer enforces the approval.
CREATE TABLE new_company_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    company_name TEXT NOT NULL,
    fiscal_year_start TEXT NOT NULL,
    base_currency TEXT NOT NULL DEFAULT 'USD',
    tax_id TEXT,
    branch_code TEXT DEFAULT '00000',
    tax_type TEXT,
    cas_permit_number TEXT,
    next_invoice_number INTEGER DEFAULT 1000,
    contract_revenue_acct_id INTEGER,
    contract_cost_acct_id INTEGER,
    underbilled_acct_id INTEGER,
    overbilled_acct_id INTEGER,
    payroll_clearing_acct_id INTEGER,
    manual_entry_approval INTEGER NOT NULL DEFAULT 0 CHECK (manual_entry_approval IN (0, 1)),
    manual_entry_approval_threshold_cents INTEGER CHECK (
        manual_entry_approval_threshold_cents IS NULL
        OR (typeof(manual_entry_approval_threshold_cents) = 'integer' AND manual_entry_approval_threshold_cents >= 0))
);
INSERT INTO new_company_settings (id, company_name, fiscal_year_start, base_currency, tax_id, branch_code, tax_type, cas_permit_number, next_invoice_number, contract_revenue_acct_id, contract_cost_acct_id, underbilled_acct_id, overbilled_acct_id, payroll_clearing_acct_id)
    SELECT id, company_name, fiscal_year_start, COALESCE(base_currency, 'USD'), tax_id, branch_code, tax_type, cas_permit_number, next_invoice_number, contract_revenue_acct_id, contract_cost_acct_id, underbilled_acct_id, overbilled_acct_id, payroll_clearing_acct_id FROM company_settings;
DROP TABLE company_settings;
ALTER TABLE new_company_settings RENAME TO company_settings;

-- ---------------------------------------------------------------------------
-- Date and flag checks only (D1); duplicate tables get constraint-only changes
-- ---------------------------------------------------------------------------

-- change_order
CREATE TABLE new_change_order (
	co_id INTEGER PRIMARY KEY AUTOINCREMENT,
	project_id INTEGER REFERENCES project(project_id),
	contract_id INTEGER REFERENCES contract(contract_id),
	co_number TEXT NOT NULL,
	description TEXT,
	status TEXT CHECK (status IN ('Draft', 'Submitted', 'Approved', 'Rejected', 'Void')),
	submitted_date TEXT,
	approved_date TEXT,
	effective_date TEXT,
	approved_by_name TEXT,
	approval_ref TEXT,
	days_added INTEGER
    -- 004: ISO dates and 0/1 flags
    , CHECK (submitted_date IS date(submitted_date))
    , CHECK (approved_date IS date(approved_date))
    , CHECK (effective_date IS date(effective_date))
);
INSERT INTO new_change_order (co_id, project_id, contract_id, co_number, description, status, submitted_date, approved_date, effective_date, approved_by_name, approval_ref, days_added)
    SELECT co_id, project_id, contract_id, co_number, description, status, submitted_date, approved_date, effective_date, approved_by_name, approval_ref, days_added FROM change_order;
DROP TABLE change_order;
ALTER TABLE new_change_order RENAME TO change_order;

-- contact
CREATE TABLE new_contact (
    contact_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL, 
    bir_registered_name  TEXT, 
    entity_type          TEXT CHECK (entity_type IN ('Individual/Single member LLC', 'Corp', 'LLC/LLP')),
    is_customer          INTEGER DEFAULT 1, 
    is_vendor            INTEGER DEFAULT 0, 
    is_employee          INTEGER DEFAULT 0,
    email                TEXT,
    phone                TEXT,
    address              TEXT,
    tax_id               TEXT, -- Maps to EIN / TIN structures
    is_active            INTEGER DEFAULT 1
, mailing_street TEXT, mailing_city TEXT, mailing_state TEXT, mailing_zip TEXT
    -- 004: ISO dates and 0/1 flags
    , CHECK (is_customer IN (0, 1))
    , CHECK (is_vendor IN (0, 1))
    , CHECK (is_employee IN (0, 1))
    , CHECK (is_active IN (0, 1))
);
INSERT INTO new_contact (contact_id, name, bir_registered_name, entity_type, is_customer, is_vendor, is_employee, email, phone, address, tax_id, is_active, mailing_street, mailing_city, mailing_state, mailing_zip)
    SELECT contact_id, name, bir_registered_name, entity_type, is_customer, is_vendor, is_employee, email, phone, address, tax_id, is_active, mailing_street, mailing_city, mailing_state, mailing_zip FROM contact;
DROP TABLE contact;
ALTER TABLE new_contact RENAME TO contact;

-- contract
CREATE TABLE new_contract (
	contract_id INTEGER PRIMARY KEY AUTOINCREMENT,
	project_id INTEGER REFERENCES project(project_id),
	contact_id INTEGER REFERENCES contact(contact_id),
	contract_number TEXT NOT NULL UNIQUE,
	contract_type TEXT CHECK (contract_type IN ('Fixed price', 'Cost-plus', 'Time and materials', 'Unit price')),
	contract_date TEXT,
	start_date TEXT,
	completion_date TEXT,
	original_amount_cents INTEGER,
	retainage_pct REAL,
	payment_terms TEXT,
	status TEXT CHECK (status IN ('Draft', 'Executed', 'Complete', 'Terminated')),
	document_ref TEXT,
	notes TEXT,
    CHECK (original_amount_cents IS NULL OR typeof(original_amount_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (contract_date IS date(contract_date))
    , CHECK (start_date IS date(start_date))
    , CHECK (completion_date IS date(completion_date))
);
INSERT INTO new_contract (contract_id, project_id, contact_id, contract_number, contract_type, contract_date, start_date, completion_date, original_amount_cents, retainage_pct, payment_terms, status, document_ref, notes)
    SELECT contract_id, project_id, contact_id, contract_number, contract_type, contract_date, start_date, completion_date, original_amount_cents, retainage_pct, payment_terms, status, document_ref, notes FROM contract;
DROP TABLE contract;
ALTER TABLE new_contract RENAME TO contract;

-- crm_opportunity
CREATE TABLE new_crm_opportunity (
    opportunity_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id             INTEGER NOT NULL REFERENCES contact(contact_id) ON DELETE CASCADE,
    pipeline_id            INTEGER NOT NULL REFERENCES crm_pipeline(pipeline_id),
    current_stage_id       INTEGER NOT NULL REFERENCES crm_stage(stage_id),
    deal_name              TEXT NOT NULL,
    deal_value_cents       INTEGER DEFAULT 0 CHECK (deal_value_cents >= 0),
    probability_pct        REAL DEFAULT 10.0 CHECK (probability_pct >= 0.0 AND probability_pct <= 100.0),
    estimated_close        TEXT, -- String date alignment tracking: YYYY-MM-DD
    downstream_estimate_id INTEGER, 
    downstream_contract_id INTEGER, 
    created_by             INTEGER,
    created_at             DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (deal_value_cents IS NULL OR typeof(deal_value_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (estimated_close IS date(estimated_close))
);
INSERT INTO new_crm_opportunity (opportunity_id, contact_id, pipeline_id, current_stage_id, deal_name, deal_value_cents, probability_pct, estimated_close, downstream_estimate_id, downstream_contract_id, created_by, created_at)
    SELECT opportunity_id, contact_id, pipeline_id, current_stage_id, deal_name, deal_value_cents, probability_pct, estimated_close, downstream_estimate_id, downstream_contract_id, created_by, created_at FROM crm_opportunity;
DROP TABLE crm_opportunity;
ALTER TABLE new_crm_opportunity RENAME TO crm_opportunity;

-- deferral
CREATE TABLE new_deferral (
	deferral_id INTEGER PRIMARY KEY AUTOINCREMENT,
	kind TEXT CHECK (kind IN ('Expense', 'Revenue')),
	advance_type TEXT CHECK (advance_type IN ('Billed in advance', 'Paid in advance')),
	description TEXT,
	contact_id INTEGER REFERENCES contact(contact_id),
	invoice_id INTEGER REFERENCES invoice(invoice_id),
	invoice_line_id INTEGER REFERENCES invoice_line(line_id),
	payment_id INTEGER REFERENCES payment(payment_id),
	original_amount_cents INTEGER NOT NULL,
	start_date TEXT NOT NULL,
	end_date TEXT NOT NULL,
	method TEXT CHECK (method IN ('Straight-line', 'Manual')),
	proration TEXT CHECK (proration IN ('Full month', 'Half month', 'Daily')),
	deferral_account_id INTEGER REFERENCES account(account_id),
	recognition_account_id INTEGER REFERENCES account(account_id),
	project_id INTEGER,
	cost_code_id INTEGER,
	supersedes_id INTEGER REFERENCES deferral(deferral_id),
	status TEXT CHECK (status IN ('Draft', 'Active', 'Fully amortized', 'Cancelled')),
	cancelled_date TEXT,
	memo TEXT,
    CHECK (typeof(original_amount_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (start_date IS date(start_date))
    , CHECK (end_date IS date(end_date))
    , CHECK (cancelled_date IS date(cancelled_date))
);
INSERT INTO new_deferral (deferral_id, kind, advance_type, description, contact_id, invoice_id, invoice_line_id, payment_id, original_amount_cents, start_date, end_date, method, proration, deferral_account_id, recognition_account_id, project_id, cost_code_id, supersedes_id, status, cancelled_date, memo)
    SELECT deferral_id, kind, advance_type, description, contact_id, invoice_id, invoice_line_id, payment_id, original_amount_cents, start_date, end_date, method, proration, deferral_account_id, recognition_account_id, project_id, cost_code_id, supersedes_id, status, cancelled_date, memo FROM deferral;
DROP TABLE deferral;
ALTER TABLE new_deferral RENAME TO deferral;

-- import_batch
CREATE TABLE new_import_batch (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES import_source(source_id),
    batch_type TEXT CHECK (batch_type IN ('Payroll run', 'Card transactions', 'Bills', 'Reimbursements', 'Labor Accrual')),
    batch_nature TEXT CHECK (batch_nature IN ('Actual', 'Accrual', 'Reversal')) DEFAULT 'Actual',
    reverses_batch_id INTEGER REFERENCES import_batch(batch_id),
    file_name TEXT,
    period_start TEXT,
    period_end TEXT,
    imported_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_cents INTEGER,
    status TEXT CHECK (status IN ('Imported', 'In review', 'Approved', 'Posted', 'Voided')),
    entry_id INTEGER REFERENCES journal_entry(entry_id),
    CHECK (total_cents IS NULL OR typeof(total_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (period_start IS date(period_start))
    , CHECK (period_end IS date(period_end))
);
INSERT INTO new_import_batch (batch_id, source_id, batch_type, batch_nature, reverses_batch_id, file_name, period_start, period_end, imported_at, total_cents, status, entry_id)
    SELECT batch_id, source_id, batch_type, batch_nature, reverses_batch_id, file_name, period_start, period_end, imported_at, total_cents, status, entry_id FROM import_batch;
DROP TABLE import_batch;
ALTER TABLE new_import_batch RENAME TO import_batch;

-- progress_billing_application
CREATE TABLE new_progress_billing_application (
	pay_app_id INTEGER PRIMARY KEY AUTOINCREMENT,
	contract_id INTEGER REFERENCES contract(contract_id),
	invoice_id INTEGER REFERENCES invoice(invoice_id),
	application_number INTEGER NOT NULL,
	period_to_date TEXT NOT NULL,
	work_completed_cents INTEGER NOT NULL,
	stored_materials_cents INTEGER NOT NULL,
	total_earned_cents INTEGER NOT NULL,
	less_retainage_cents INTEGER NOT NULL,
	net_earned_cents INTEGER NOT NULL,
	less_previous_applied INTEGER NOT NULL,
	amount_due_cents INTEGER NOT NULL,
	status TEXT CHECK (status IN ('Draft', 'Submitted', 'Approved', 'Paid')),
    CHECK (typeof(work_completed_cents) = 'integer'),
    CHECK (typeof(stored_materials_cents) = 'integer'),
    CHECK (typeof(total_earned_cents) = 'integer'),
    CHECK (typeof(less_retainage_cents) = 'integer'),
    CHECK (typeof(net_earned_cents) = 'integer'),
    CHECK (typeof(less_previous_applied) = 'integer'),
    CHECK (typeof(amount_due_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (period_to_date IS date(period_to_date))
);
INSERT INTO new_progress_billing_application (pay_app_id, contract_id, invoice_id, application_number, period_to_date, work_completed_cents, stored_materials_cents, total_earned_cents, less_retainage_cents, net_earned_cents, less_previous_applied, amount_due_cents, status)
    SELECT pay_app_id, contract_id, invoice_id, application_number, period_to_date, work_completed_cents, stored_materials_cents, total_earned_cents, less_retainage_cents, net_earned_cents, less_previous_applied, amount_due_cents, status FROM progress_billing_application;
DROP TABLE progress_billing_application;
ALTER TABLE new_progress_billing_application RENAME TO progress_billing_application;

-- saas_subscription
CREATE TABLE new_saas_subscription (
    subscription_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id              INTEGER NOT NULL UNIQUE REFERENCES contact(contact_id) ON DELETE CASCADE,
    plan_tier_name          TEXT NOT NULL, 
    base_mrr_cents          INTEGER DEFAULT 0 CHECK (base_mrr_cents >= 0), 
    seat_quantity           INTEGER DEFAULT 1,
    per_seat_cost_cents     INTEGER DEFAULT 0,
    next_billing_cycle_date TEXT NOT NULL, 
    status                  TEXT CHECK (status IN ('Trial', 'Active', 'Past_Due', 'Contracted', 'Churned')) DEFAULT 'Trial',
    CHECK (base_mrr_cents IS NULL OR typeof(base_mrr_cents) = 'integer'),
    CHECK (per_seat_cost_cents IS NULL OR typeof(per_seat_cost_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (next_billing_cycle_date IS date(next_billing_cycle_date))
);
INSERT INTO new_saas_subscription (subscription_id, contact_id, plan_tier_name, base_mrr_cents, seat_quantity, per_seat_cost_cents, next_billing_cycle_date, status)
    SELECT subscription_id, contact_id, plan_tier_name, base_mrr_cents, seat_quantity, per_seat_cost_cents, next_billing_cycle_date, status FROM saas_subscription;
DROP TABLE saas_subscription;
ALTER TABLE new_saas_subscription RENAME TO saas_subscription;

-- saas_usage_telemetry
CREATE TABLE new_saas_usage_telemetry (
    telemetry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id  INTEGER NOT NULL REFERENCES saas_subscription(subscription_id) ON DELETE CASCADE,
    metric_type      TEXT CHECK (metric_type IN ('API_Calls', 'Storage_GB', 'AI_Tokens_Consumed')),
    units_used       INTEGER NOT NULL CHECK (units_used > 0),
    logged_at_date   TEXT NOT NULL
    -- 004: ISO dates and 0/1 flags
    , CHECK (logged_at_date IS date(logged_at_date))
);
INSERT INTO new_saas_usage_telemetry (telemetry_id, subscription_id, metric_type, units_used, logged_at_date)
    SELECT telemetry_id, subscription_id, metric_type, units_used, logged_at_date FROM saas_usage_telemetry;
DROP TABLE saas_usage_telemetry;
ALTER TABLE new_saas_usage_telemetry RENAME TO saas_usage_telemetry;

-- staged_transaction
CREATE TABLE new_staged_transaction (
    stage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER REFERENCES import_batch(batch_id),
    external_ref TEXT,
    related_external_ref TEXT,
    txn_type TEXT CHECK (txn_type IN ('Card purchase', 'Bill', 'Bill payment', 'Reimbursement', 'Statement payment', 'Refund', 'Labor Accrual Adjustment')),
    entry_nature TEXT CHECK (entry_nature IN ('Actual', 'Accrual', 'Reversal')) DEFAULT 'Actual',
    reverses_stage_id INTEGER REFERENCES staged_transaction(stage_id),
    txn_date TEXT,
    vendor_name TEXT,
    description TEXT,
    amount_cents INTEGER,
    contact_id INTEGER REFERENCES contact(contact_id),
    matched_invoice_id INTEGER REFERENCES invoice(invoice_id),
    status TEXT CHECK (status IN ('New', 'Coded', 'Matched', 'Approved', 'Posted', 'Rejected')),
    approved_by INTEGER,
    approved_at DATETIME,
    invoice_id INTEGER REFERENCES invoice(invoice_id),
    payment_id INTEGER REFERENCES payment(payment_id),
    entry_id INTEGER REFERENCES journal_entry(entry_id),
    CHECK (amount_cents IS NULL OR typeof(amount_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (txn_date IS date(txn_date))
);
INSERT INTO new_staged_transaction (stage_id, batch_id, external_ref, related_external_ref, txn_type, entry_nature, reverses_stage_id, txn_date, vendor_name, description, amount_cents, contact_id, matched_invoice_id, status, approved_by, approved_at, invoice_id, payment_id, entry_id)
    SELECT stage_id, batch_id, external_ref, related_external_ref, txn_type, entry_nature, reverses_stage_id, txn_date, vendor_name, description, amount_cents, contact_id, matched_invoice_id, status, approved_by, approved_at, invoice_id, payment_id, entry_id FROM staged_transaction;
DROP TABLE staged_transaction;
ALTER TABLE new_staged_transaction RENAME TO staged_transaction;

-- subscription
CREATE TABLE new_subscription (
    subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contact(contact_id),
    plan_name TEXT NOT NULL,
    mrr_cents INTEGER DEFAULT 0,
    arr_cents INTEGER DEFAULT 0,
    status TEXT CHECK (status IN ('Active', 'Paused', 'Churned')),
    start_date TEXT NOT NULL,
    end_date TEXT,
    CHECK (mrr_cents IS NULL OR typeof(mrr_cents) = 'integer'),
    CHECK (arr_cents IS NULL OR typeof(arr_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (start_date IS date(start_date))
    , CHECK (end_date IS date(end_date))
);
INSERT INTO new_subscription (subscription_id, contact_id, plan_name, mrr_cents, arr_cents, status, start_date, end_date)
    SELECT subscription_id, contact_id, plan_name, mrr_cents, arr_cents, status, start_date, end_date FROM subscription;
DROP TABLE subscription;
ALTER TABLE new_subscription RENAME TO subscription;

-- time_entry
CREATE TABLE new_time_entry (
    time_entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contact(contact_id),
    project_id INTEGER REFERENCES project(project_id),
    cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
    work_date TEXT NOT NULL,
    hours REAL NOT NULL,
    wage_cents INTEGER NOT NULL,
    burden_cents INTEGER NOT NULL,
    source_batch_id INTEGER REFERENCES import_batch(batch_id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (typeof(wage_cents) = 'integer'),
    CHECK (typeof(burden_cents) = 'integer')
    -- 004: ISO dates and 0/1 flags
    , CHECK (work_date IS date(work_date))
);
INSERT INTO new_time_entry (time_entry_id, contact_id, project_id, cost_code_id, work_date, hours, wage_cents, burden_cents, source_batch_id, created_at)
    SELECT time_entry_id, contact_id, project_id, cost_code_id, work_date, hours, wage_cents, burden_cents, source_batch_id, created_at FROM time_entry;
DROP TABLE time_entry;
ALTER TABLE new_time_entry RENAME TO time_entry;

-- ---------------------------------------------------------------------------
-- 003 triggers recreated unchanged
-- ---------------------------------------------------------------------------

CREATE TRIGGER invoice_line_dimension_lock_delete
BEFORE DELETE ON invoice_line_dimension
WHEN EXISTS (SELECT 1 FROM invoice_line AS l JOIN invoice AS i ON i.invoice_id = l.invoice_id
             WHERE l.line_id = OLD.line_id AND (i.status IS NOT 'Draft' OR i.entry_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'Lines of a Sent or posted invoice cannot be changed'); END;

CREATE TRIGGER invoice_line_dimension_lock_insert
BEFORE INSERT ON invoice_line_dimension
WHEN EXISTS (SELECT 1 FROM invoice_line AS l JOIN invoice AS i ON i.invoice_id = l.invoice_id
             WHERE l.line_id = NEW.line_id AND (i.status IS NOT 'Draft' OR i.entry_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'Lines of a Sent or posted invoice cannot be changed'); END;

CREATE TRIGGER invoice_line_dimension_lock_update
BEFORE UPDATE ON invoice_line_dimension
WHEN EXISTS (SELECT 1 FROM invoice_line AS l JOIN invoice AS i ON i.invoice_id = l.invoice_id
             WHERE l.line_id IN (OLD.line_id, NEW.line_id) AND (i.status IS NOT 'Draft' OR i.entry_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'Lines of a Sent or posted invoice cannot be changed'); END;

CREATE TRIGGER invoice_line_lock_delete
BEFORE DELETE ON invoice_line
WHEN EXISTS (SELECT 1 FROM invoice WHERE invoice_id = OLD.invoice_id
             AND (status IS NOT 'Draft' OR entry_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'Lines of a Sent or posted invoice cannot be changed'); END;

CREATE TRIGGER invoice_line_lock_insert
BEFORE INSERT ON invoice_line
WHEN EXISTS (SELECT 1 FROM invoice WHERE invoice_id = NEW.invoice_id
             AND (status IS NOT 'Draft' OR entry_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'Lines of a Sent or posted invoice cannot be changed'); END;

CREATE TRIGGER invoice_line_lock_update
BEFORE UPDATE ON invoice_line
WHEN EXISTS (SELECT 1 FROM invoice WHERE invoice_id IN (OLD.invoice_id, NEW.invoice_id)
             AND (status IS NOT 'Draft' OR entry_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'Lines of a Sent or posted invoice cannot be changed'); END;

CREATE TRIGGER invoice_lock_delete
BEFORE DELETE ON invoice
WHEN OLD.status IS NOT 'Draft' OR OLD.entry_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Only Draft invoices without a journal entry can be deleted');
END;

CREATE TRIGGER invoice_status_flow
BEFORE UPDATE OF status ON invoice
WHEN NEW.status IS NOT OLD.status
BEGIN
    SELECT CASE WHEN NOT (
           (OLD.status = 'Draft' AND NEW.status IN ('Sent', 'Covered by advance'))
        OR (OLD.status = 'Sent' AND NEW.status IN ('Paid', 'Void', 'Covered by advance'))
        OR (OLD.status = 'Paid' AND NEW.status = 'Sent')
    ) THEN RAISE(ABORT, 'Invoice status move not allowed (Draft -> Sent -> Paid/Void; Paid -> Sent)') END;
    SELECT CASE WHEN NEW.status = 'Void' AND OLD.entry_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM journal_entry WHERE entry_id = OLD.entry_id AND is_void = 1
    ) THEN RAISE(ABORT, 'Void the invoice journal entry (post a Void reversal) before voiding the invoice') END;
END;

CREATE TRIGGER journal_entry_lock_delete_posted
BEFORE DELETE ON journal_entry
WHEN OLD.is_posted = 1
BEGIN
    SELECT RAISE(ABORT, 'Posted journal entries cannot be deleted; post a reversing entry');
END;

CREATE TRIGGER journal_entry_no_direct_post
BEFORE INSERT ON journal_entry
WHEN NEW.is_posted = 1 OR NEW.is_void = 1
BEGIN
    SELECT CASE WHEN NEW.is_posted = 1
        THEN RAISE(ABORT, 'Create journal entries as unposted, add balanced lines, then post') END;
    SELECT CASE WHEN NEW.is_void = 1
        THEN RAISE(ABORT, 'is_void is set only by posting a Void reversal') END;
END;

CREATE TRIGGER journal_entry_no_draft_void
BEFORE UPDATE OF is_void ON journal_entry
WHEN OLD.is_posted = 0 AND NEW.is_void IS NOT OLD.is_void
BEGIN
    SELECT RAISE(ABORT, 'is_void is set only by posting a Void reversal');
END;

CREATE TRIGGER journal_entry_void_on_reversal
AFTER UPDATE OF is_posted ON journal_entry
WHEN NEW.is_posted = 1 AND OLD.is_posted = 0 AND NEW.reversal_reason = 'Void'
BEGIN
    UPDATE journal_entry SET is_void = 1 WHERE entry_id = NEW.reverses_entry_id;
END;

CREATE TRIGGER journal_line_lock_delete_posted
BEFORE DELETE ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id = OLD.entry_id AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER journal_line_lock_insert_posted
BEFORE INSERT ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id = NEW.entry_id AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER payment_allocation_lock_delete
BEFORE DELETE ON payment_allocation
WHEN EXISTS (SELECT 1 FROM payment AS p LEFT JOIN journal_entry AS e ON e.entry_id = p.entry_id
             WHERE p.payment_id = OLD.payment_id AND p.entry_id IS NOT NULL AND e.is_void IS NOT 1)
BEGIN SELECT RAISE(ABORT, 'Allocations of a posted payment can be removed only after its entry is voided'); END;

CREATE TRIGGER payment_allocation_lock_update
BEFORE UPDATE ON payment_allocation
WHEN EXISTS (SELECT 1 FROM payment WHERE payment_id IN (OLD.payment_id, NEW.payment_id)
             AND entry_id IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'Allocations of a posted payment cannot be changed'); END;

CREATE TRIGGER payment_allocation_no_voided_payment
BEFORE INSERT ON payment_allocation
WHEN EXISTS (SELECT 1 FROM payment AS p JOIN journal_entry AS e ON e.entry_id = p.entry_id
             WHERE p.payment_id = NEW.payment_id AND e.is_void = 1)
BEGIN SELECT RAISE(ABORT, 'A voided payment cannot be allocated'); END;

CREATE TRIGGER payment_lock
BEFORE UPDATE ON payment
WHEN OLD.entry_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Posted payments cannot be changed; void the payment entry instead');
END;

CREATE TRIGGER payment_lock_delete
BEFORE DELETE ON payment
WHEN OLD.entry_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Posted payments cannot be deleted; void the payment entry instead');
END;

-- ---------------------------------------------------------------------------
-- Periods (decision 4)
-- ---------------------------------------------------------------------------

-- Periods are contiguous with no overlap: a new period starts the day after
-- the last one ends, or ends the day before the first one starts.
CREATE TRIGGER fiscal_period_contiguous_insert
BEFORE INSERT ON fiscal_period
WHEN EXISTS (SELECT 1 FROM fiscal_period)
BEGIN
    SELECT CASE WHEN NOT (
           NEW.start_date = (SELECT date(MAX(end_date), '+1 day') FROM fiscal_period)
        OR NEW.end_date = (SELECT date(MIN(start_date), '-1 day') FROM fiscal_period)
    ) THEN RAISE(ABORT, 'Fiscal periods must be contiguous: start the day after the last period or end the day before the first') END;
END;

-- A closed period records who closed it and when.
CREATE TRIGGER fiscal_period_close_insert
BEFORE INSERT ON fiscal_period
WHEN NEW.is_closed = 1 AND (NEW.closed_at IS NULL OR NEW.closed_by IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'Closing a period records closed_at and closed_by');
END;

CREATE TRIGGER fiscal_period_close_update
BEFORE UPDATE OF is_closed ON fiscal_period
WHEN OLD.is_closed = 0 AND NEW.is_closed = 1 AND (NEW.closed_at IS NULL OR NEW.closed_by IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'Closing a period records closed_at and closed_by');
END;

-- Only the outer edges of the period range can move, and only while no entry
-- uses the period.
CREATE TRIGGER fiscal_period_dates_update
BEFORE UPDATE OF start_date, end_date ON fiscal_period
WHEN NEW.start_date IS NOT OLD.start_date OR NEW.end_date IS NOT OLD.end_date
BEGIN
    SELECT CASE WHEN EXISTS (SELECT 1 FROM journal_entry WHERE period_id = OLD.period_id)
        THEN RAISE(ABORT, 'Fiscal period dates cannot change once entries use the period') END;
    SELECT CASE WHEN NEW.start_date IS NOT OLD.start_date
                 AND EXISTS (SELECT 1 FROM fiscal_period WHERE end_date < OLD.start_date)
        THEN RAISE(ABORT, 'Only the start of the first period can move') END;
    SELECT CASE WHEN NEW.end_date IS NOT OLD.end_date
                 AND EXISTS (SELECT 1 FROM fiscal_period WHERE start_date > OLD.end_date)
        THEN RAISE(ABORT, 'Only the end of the last period can move') END;
END;

CREATE TRIGGER fiscal_period_delete
BEFORE DELETE ON fiscal_period
WHEN EXISTS (SELECT 1 FROM fiscal_period WHERE end_date < OLD.start_date)
 AND EXISTS (SELECT 1 FROM fiscal_period WHERE start_date > OLD.end_date)
BEGIN
    SELECT RAISE(ABORT, 'Only the first or last period can be deleted');
END;

-- period_id is the period that contains entry_date (set by the service).
CREATE TRIGGER journal_entry_period_matches_insert
BEFORE INSERT ON journal_entry
WHEN NOT EXISTS (SELECT 1 FROM fiscal_period
                 WHERE period_id = NEW.period_id AND NEW.entry_date BETWEEN start_date AND end_date)
BEGIN
    SELECT RAISE(ABORT, 'period_id must be the fiscal period that contains entry_date');
END;

CREATE TRIGGER journal_entry_period_matches_update
BEFORE UPDATE OF entry_date, period_id ON journal_entry
WHEN NOT EXISTS (SELECT 1 FROM fiscal_period
                 WHERE period_id = NEW.period_id AND NEW.entry_date BETWEEN start_date AND end_date)
BEGIN
    SELECT RAISE(ABORT, 'period_id must be the fiscal period that contains entry_date');
END;

-- ---------------------------------------------------------------------------
-- Posting (003 rules, plus who/when and the gapless entry number)
-- ---------------------------------------------------------------------------

CREATE TRIGGER journal_entry_require_balance_on_post
BEFORE UPDATE OF is_posted ON journal_entry
WHEN NEW.is_posted = 1 AND OLD.is_posted = 0
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM fiscal_period WHERE period_id = NEW.period_id AND is_closed = 1
    ) THEN RAISE(ABORT, 'Cannot post into a closed fiscal period') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM fiscal_period
        WHERE is_closed = 1
          AND NEW.entry_date BETWEEN start_date AND end_date
    ) THEN RAISE(ABORT, 'Cannot post: the entry date falls in a closed fiscal period') END;
    SELECT CASE WHEN NEW.created_by IS NULL OR NEW.posted_by IS NULL
                  OR NEW.posted_at IS NULL OR datetime(NEW.posted_at) IS NULL
        THEN RAISE(ABORT, 'Posting records who created the entry, who posted it and when') END;
    SELECT CASE WHEN NEW.entry_number IS NOT (SELECT last_number FROM entry_number_sequence WHERE id = 1)
        THEN RAISE(ABORT, 'A posted entry takes the next entry number from entry_number_sequence') END;
    SELECT CASE WHEN (
        SELECT COUNT(*) FROM journal_line WHERE entry_id = NEW.entry_id
    ) < 2 THEN RAISE(ABORT, 'A journal entry needs at least two lines to post') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM journal_line
        WHERE entry_id = NEW.entry_id
          AND ((debit_cents > 0 AND credit_cents = 0)
               OR (debit_cents = 0 AND credit_cents > 0)) IS NOT 1
    ) THEN RAISE(ABORT, 'Every journal line must have exactly one non-zero side') END;
    SELECT CASE WHEN
        (SELECT COALESCE(SUM(debit_cents), 0) FROM journal_line WHERE entry_id = NEW.entry_id) <= 0
        OR (SELECT COALESCE(SUM(debit_cents), 0) FROM journal_line WHERE entry_id = NEW.entry_id)
           != (SELECT COALESCE(SUM(credit_cents), 0) FROM journal_line WHERE entry_id = NEW.entry_id)
    THEN RAISE(ABORT, 'Journal entry must balance before posting') END;
    SELECT CASE WHEN NEW.reverses_entry_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM journal_entry
        WHERE entry_id = NEW.reverses_entry_id AND is_posted = 1 AND is_void = 0
    ) THEN RAISE(ABORT, 'A reversal can only reverse a posted, unvoided entry') END;
    SELECT CASE WHEN NEW.reverses_entry_id IS NOT NULL AND (
        EXISTS (
            SELECT account_id, contact_id, project_id, cost_code_id, deferral_id,
                   SUM(credit_cents), SUM(debit_cents)
            FROM journal_line WHERE entry_id = NEW.reverses_entry_id
            GROUP BY account_id, contact_id, project_id, cost_code_id, deferral_id
            EXCEPT
            SELECT account_id, contact_id, project_id, cost_code_id, deferral_id,
                   SUM(debit_cents), SUM(credit_cents)
            FROM journal_line WHERE entry_id = NEW.entry_id
            GROUP BY account_id, contact_id, project_id, cost_code_id, deferral_id
        )
        OR EXISTS (
            SELECT account_id, contact_id, project_id, cost_code_id, deferral_id,
                   SUM(debit_cents), SUM(credit_cents)
            FROM journal_line WHERE entry_id = NEW.entry_id
            GROUP BY account_id, contact_id, project_id, cost_code_id, deferral_id
            EXCEPT
            SELECT account_id, contact_id, project_id, cost_code_id, deferral_id,
                   SUM(credit_cents), SUM(debit_cents)
            FROM journal_line WHERE entry_id = NEW.reverses_entry_id
            GROUP BY account_id, contact_id, project_id, cost_code_id, deferral_id
        )
    ) THEN RAISE(ABORT, 'A reversal must mirror the original entry exactly') END;
END;

-- The counter moves forward by exactly one, and only after its current
-- number has been used, so posted entry numbers have no gaps.
CREATE TRIGGER entry_number_sequence_step
BEFORE UPDATE ON entry_number_sequence
BEGIN
    SELECT CASE WHEN NEW.id IS NOT OLD.id OR NEW.last_number IS NOT OLD.last_number + 1
        THEN RAISE(ABORT, 'The entry number counter only moves forward by one') END;
    SELECT CASE WHEN OLD.last_number IS NOT (SELECT COALESCE(MAX(entry_number), 0) FROM journal_entry)
        THEN RAISE(ABORT, 'The current entry number has not been used yet') END;
END;

CREATE TRIGGER entry_number_sequence_no_delete
BEFORE DELETE ON entry_number_sequence
BEGIN
    SELECT RAISE(ABORT, 'The entry number counter cannot be deleted');
END;

-- A posted entry may only change by being marked void (is_void 0 -> 1), and
-- only once a posted Void reversal of it exists. A test checks that this list
-- names every journal_entry column.
CREATE TRIGGER journal_entry_lock_posted
BEFORE UPDATE ON journal_entry
WHEN OLD.is_posted = 1
BEGIN
    SELECT CASE WHEN NEW.is_posted IS NOT 1
        THEN RAISE(ABORT, 'Posted journal entries cannot be unposted; post a reversing entry') END;
    SELECT CASE WHEN NOT (
        OLD.is_void = 0 AND NEW.is_void = 1
        AND EXISTS (
            SELECT 1 FROM journal_entry AS reversal
            WHERE reversal.reverses_entry_id = OLD.entry_id
              AND reversal.reversal_reason = 'Void'
              AND reversal.is_posted = 1
        )
        AND NEW.entry_id IS OLD.entry_id
        AND NEW.entry_date IS OLD.entry_date
        AND NEW.period_id IS OLD.period_id
        AND NEW.reference IS OLD.reference
        AND NEW.description IS OLD.description
        AND NEW.source IS OLD.source
        AND NEW.reverses_entry_id IS OLD.reverses_entry_id
        AND NEW.reversal_reason IS OLD.reversal_reason
        AND NEW.created_by IS OLD.created_by
        AND NEW.created_at IS OLD.created_at
        AND NEW.entry_number IS OLD.entry_number
        AND NEW.posted_by IS OLD.posted_by
        AND NEW.posted_at IS OLD.posted_at
        AND NEW.approved_by IS OLD.approved_by
        AND NEW.approved_at IS OLD.approved_at
        AND NEW.origin IS OLD.origin
    ) THEN RAISE(ABORT, 'Posted journal entries cannot be changed; void them by posting a Void reversal') END;
END;

-- Lines of a posted entry are locked, except that recon_id may be set or
-- cleared (bank reconciliation) while the reconciliation is open. A test
-- checks that this list names every journal_line column.
CREATE TRIGGER journal_line_lock_update_posted
BEFORE UPDATE ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id IN (OLD.entry_id, NEW.entry_id) AND is_posted = 1)
 AND NOT (
        NEW.recon_id IS NOT OLD.recon_id
        AND NEW.line_id IS OLD.line_id
        AND NEW.entry_id IS OLD.entry_id
        AND NEW.account_id IS OLD.account_id
        AND NEW.debit_cents IS OLD.debit_cents
        AND NEW.credit_cents IS OLD.credit_cents
        AND NEW.memo IS OLD.memo
        AND NEW.contact_id IS OLD.contact_id
        AND NEW.project_id IS OLD.project_id
        AND NEW.cost_code_id IS OLD.cost_code_id
        AND NEW.deferral_id IS OLD.deferral_id
        AND NEW.batch_id IS OLD.batch_id
        AND NEW.is_retainage_line IS OLD.is_retainage_line
        AND NEW.external_ref IS OLD.external_ref
 )
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

-- ---------------------------------------------------------------------------
-- Bank reconciliation (C11)
-- ---------------------------------------------------------------------------

CREATE TRIGGER journal_line_recon_lock
BEFORE UPDATE OF recon_id ON journal_line
WHEN NEW.recon_id IS NOT OLD.recon_id
 AND EXISTS (SELECT 1 FROM bank_reconciliation
             WHERE recon_id IN (OLD.recon_id, NEW.recon_id) AND is_complete = 1)
BEGIN
    SELECT RAISE(ABORT, 'Lines of a completed bank reconciliation cannot change');
END;

CREATE TRIGGER bank_reconciliation_lock
BEFORE UPDATE ON bank_reconciliation
WHEN OLD.is_complete = 1
BEGIN
    SELECT RAISE(ABORT, 'A completed bank reconciliation cannot be changed');
END;

CREATE TRIGGER bank_reconciliation_lock_delete
BEFORE DELETE ON bank_reconciliation
WHEN OLD.is_complete = 1
BEGIN
    SELECT RAISE(ABORT, 'A completed bank reconciliation cannot be deleted');
END;

-- ---------------------------------------------------------------------------
-- Journal line dimensions (X1): locked once the entry is posted
-- ---------------------------------------------------------------------------

CREATE TRIGGER journal_line_dimension_lock_insert
BEFORE INSERT ON journal_line_dimension
WHEN EXISTS (SELECT 1 FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id
             WHERE l.line_id = NEW.line_id AND e.is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER journal_line_dimension_lock_update
BEFORE UPDATE ON journal_line_dimension
WHEN EXISTS (SELECT 1 FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id
             WHERE l.line_id IN (OLD.line_id, NEW.line_id) AND e.is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER journal_line_dimension_lock_delete
BEFORE DELETE ON journal_line_dimension
WHEN EXISTS (SELECT 1 FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id
             WHERE l.line_id = OLD.line_id AND e.is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

-- ---------------------------------------------------------------------------
-- Chart of accounts (A1)
-- ---------------------------------------------------------------------------

CREATE TRIGGER account_lock_after_posting
BEFORE UPDATE OF code, type_id, parent_id, control_type ON account
WHEN (NEW.code IS NOT OLD.code OR NEW.type_id IS NOT OLD.type_id
      OR NEW.parent_id IS NOT OLD.parent_id OR NEW.control_type IS NOT OLD.control_type)
 AND EXISTS (SELECT 1 FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id
             WHERE l.account_id = OLD.account_id AND e.is_posted = 1)
BEGIN
    SELECT RAISE(ABORT, 'An account with posted entries keeps its code, type, parent and control type; it can only be renamed');
END;

-- ---------------------------------------------------------------------------
-- Invoice series and numbering (decision 3, C8)
-- ---------------------------------------------------------------------------

CREATE TRIGGER invoice_series_step
BEFORE UPDATE OF last_number ON invoice_series
WHEN NEW.last_number IS NOT OLD.last_number AND NEW.last_number IS NOT OLD.last_number + 1
BEGIN
    SELECT RAISE(ABORT, 'An invoice series counter only moves forward by one');
END;

CREATE TRIGGER invoice_series_lock_after_use
BEFORE UPDATE ON invoice_series
WHEN EXISTS (SELECT 1 FROM invoice WHERE series_id = OLD.series_id)
 AND NOT (
        NEW.series_id IS OLD.series_id
        AND NEW.document_type IS OLD.document_type
        AND NEW.prefix IS OLD.prefix
        AND NEW.registered_from IS OLD.registered_from
        AND NEW.registered_to IS OLD.registered_to
        AND NEW.authority_ref IS OLD.authority_ref
        AND NEW.valid_until IS OLD.valid_until
 )
BEGIN
    SELECT RAISE(ABORT, 'A used invoice series keeps its type, prefix, range and authority; start a new series instead');
END;

-- Invoices start as plain Drafts, so the leave-Draft rules below cannot be
-- skipped by inserting a document that is already Sent, Paid or posted.
CREATE TRIGGER invoice_insert_as_draft
BEFORE INSERT ON invoice
WHEN NEW.status IS NOT 'Draft' OR NEW.entry_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Create invoices as Draft without a journal entry, add lines, then send');
END;

-- Leaving Draft: a contact, a number, a subtotal that matches the lines and,
-- on the sales side, the next number of an active registered series.
CREATE TRIGGER invoice_leave_draft
BEFORE UPDATE OF status ON invoice
WHEN OLD.status = 'Draft' AND NEW.status IS NOT 'Draft'
BEGIN
    SELECT CASE WHEN NEW.contact_id IS NULL
        THEN RAISE(ABORT, 'An invoice needs a contact before it leaves Draft') END;
    SELECT CASE WHEN NEW.invoice_number IS NULL
        THEN RAISE(ABORT, 'An invoice needs a number before it leaves Draft') END;
    SELECT CASE WHEN NEW.subtotal_cents IS NOT (
        SELECT COALESCE(SUM(CAST(ROUND(COALESCE(quantity, 0) * COALESCE(unit_price_cents, 0)) AS INTEGER)), 0)
        FROM invoice_line WHERE invoice_id = NEW.invoice_id
    ) THEN RAISE(ABORT, 'subtotal_cents must equal the sum of the invoice lines') END;
    SELECT CASE WHEN NEW.ledger_side = 'Sales' AND NOT EXISTS (
        SELECT 1 FROM invoice_series AS s
        WHERE s.series_id = NEW.series_id
          AND s.is_active = 1
          AND s.document_type = NEW.invoice_type
          AND s.last_number = NEW.sequence_number
          AND (s.registered_from IS NULL OR NEW.sequence_number BETWEEN s.registered_from AND s.registered_to)
          AND (s.valid_until IS NULL OR NEW.issue_date <= s.valid_until)
          AND NEW.invoice_number = s.prefix || printf('%06d', NEW.sequence_number)
    ) THEN RAISE(ABORT, 'Sales documents take the next number of an active, registered invoice series when they leave Draft') END;
END;

-- On a locked invoice only status (by invoice_status_flow) and
-- is_eis_transmitted (0 -> 1, audit-logged) may change. entry_id is set only
-- in the update that moves Draft -> Sent. A test checks every column is listed.
CREATE TRIGGER invoice_lock
BEFORE UPDATE ON invoice
BEGIN
    SELECT CASE WHEN NEW.entry_id IS NOT OLD.entry_id AND NOT (
        OLD.entry_id IS NULL AND OLD.status = 'Draft' AND NEW.status = 'Sent'
    ) THEN RAISE(ABORT, 'Invoice entry_id is set only when the invoice moves from Draft to Sent') END;
    SELECT CASE WHEN (OLD.status IS NOT 'Draft' OR OLD.entry_id IS NOT NULL) AND NOT (
        NEW.invoice_id IS OLD.invoice_id
        AND NEW.invoice_type IS OLD.invoice_type
        AND NEW.contact_id IS OLD.contact_id
        AND NEW.project_id IS OLD.project_id
        AND NEW.subscription_id IS OLD.subscription_id
        AND NEW.invoice_number IS OLD.invoice_number
        AND NEW.issue_date IS OLD.issue_date
        AND NEW.due_date IS OLD.due_date
        AND NEW.terms IS OLD.terms
        AND NEW.currency IS OLD.currency
        AND NEW.exchange_rate IS OLD.exchange_rate
        AND NEW.subtotal_cents IS OLD.subtotal_cents
        AND NEW.vatable_sales_cents IS OLD.vatable_sales_cents
        AND NEW.vat_exempt_sales_cents IS OLD.vat_exempt_sales_cents
        AND NEW.zero_rated_sales_cents IS OLD.zero_rated_sales_cents
        AND NEW.tax_cents IS OLD.tax_cents
        AND NEW.cwt_rate IS OLD.cwt_rate
        AND NEW.cwt_amount_cents IS OLD.cwt_amount_cents
        AND NEW.total_cents IS OLD.total_cents
        AND NEW.retainage_cents IS OLD.retainage_cents
        AND (NEW.is_eis_transmitted IS OLD.is_eis_transmitted
             OR (OLD.is_eis_transmitted = 0 AND NEW.is_eis_transmitted = 1))
        AND NEW.entry_id IS OLD.entry_id
        AND NEW.batch_id IS OLD.batch_id
        AND NEW.external_ref IS OLD.external_ref
        AND NEW.ledger_side IS OLD.ledger_side
        AND NEW.series_id IS OLD.series_id
        AND NEW.sequence_number IS OLD.sequence_number
    ) THEN RAISE(ABORT, 'Sent or posted invoices cannot be changed; issue a credit memo') END;
END;

-- ---------------------------------------------------------------------------
-- C5: a journal entry belongs to one source document
-- ---------------------------------------------------------------------------

CREATE TRIGGER invoice_one_document_per_entry_insert
BEFORE INSERT ON invoice
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM payment WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM deferral_schedule_line WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM poc_snapshot WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

CREATE TRIGGER invoice_one_document_per_entry_update
BEFORE UPDATE OF entry_id ON invoice
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM payment WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM deferral_schedule_line WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM poc_snapshot WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

CREATE TRIGGER payment_one_document_per_entry_insert
BEFORE INSERT ON payment
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM invoice WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM deferral_schedule_line WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM poc_snapshot WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

CREATE TRIGGER payment_one_document_per_entry_update
BEFORE UPDATE OF entry_id ON payment
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM invoice WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM deferral_schedule_line WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM poc_snapshot WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

CREATE TRIGGER deferral_schedule_line_one_document_per_entry_insert
BEFORE INSERT ON deferral_schedule_line
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM invoice WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM payment WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM poc_snapshot WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

CREATE TRIGGER deferral_schedule_line_one_document_per_entry_update
BEFORE UPDATE OF entry_id ON deferral_schedule_line
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM invoice WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM payment WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM poc_snapshot WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

CREATE TRIGGER poc_snapshot_one_document_per_entry_insert
BEFORE INSERT ON poc_snapshot
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM invoice WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM payment WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM deferral_schedule_line WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

CREATE TRIGGER poc_snapshot_one_document_per_entry_update
BEFORE UPDATE OF entry_id ON poc_snapshot
WHEN NEW.entry_id IS NOT NULL AND (
       EXISTS (SELECT 1 FROM invoice WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM payment WHERE entry_id = NEW.entry_id)
    OR EXISTS (SELECT 1 FROM deferral_schedule_line WHERE entry_id = NEW.entry_id)
)
BEGIN
    SELECT RAISE(ABORT, 'A journal entry belongs to one source document');
END;

-- ---------------------------------------------------------------------------
-- T1: audit triggers, regenerated for the new columns and tables.
-- Generated from the table columns; a test checks every column is covered.
-- ---------------------------------------------------------------------------

CREATE TRIGGER audit_journal_entry_insert
AFTER INSERT ON journal_entry
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'journal_entry', NEW.entry_id,
        'Insert',
        NULL,
        json_object(
            'entry_id', NEW.entry_id,
            'entry_date', NEW.entry_date,
            'period_id', NEW.period_id,
            'reference', NEW.reference,
            'description', NEW.description,
            'source', NEW.source,
            'is_posted', NEW.is_posted,
            'is_void', NEW.is_void,
            'reverses_entry_id', NEW.reverses_entry_id,
            'created_by', NEW.created_by,
            'created_at', NEW.created_at,
            'reversal_reason', NEW.reversal_reason,
            'entry_number', NEW.entry_number,
            'posted_by', NEW.posted_by,
            'posted_at', NEW.posted_at,
            'approved_by', NEW.approved_by,
            'approved_at', NEW.approved_at,
            'origin', NEW.origin),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_journal_entry_update
AFTER UPDATE ON journal_entry
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'journal_entry', NEW.entry_id,
        CASE WHEN OLD.is_posted = 0 AND NEW.is_posted = 1 THEN 'Post'
             WHEN OLD.is_void = 0 AND NEW.is_void = 1 THEN 'Void'
             ELSE 'Update' END,
        json_object(
            'entry_id', OLD.entry_id,
            'entry_date', OLD.entry_date,
            'period_id', OLD.period_id,
            'reference', OLD.reference,
            'description', OLD.description,
            'source', OLD.source,
            'is_posted', OLD.is_posted,
            'is_void', OLD.is_void,
            'reverses_entry_id', OLD.reverses_entry_id,
            'created_by', OLD.created_by,
            'created_at', OLD.created_at,
            'reversal_reason', OLD.reversal_reason,
            'entry_number', OLD.entry_number,
            'posted_by', OLD.posted_by,
            'posted_at', OLD.posted_at,
            'approved_by', OLD.approved_by,
            'approved_at', OLD.approved_at,
            'origin', OLD.origin),
        CASE WHEN OLD.is_posted = 0 AND NEW.is_posted = 1 THEN json_insert(json_object(
            'entry_id', NEW.entry_id,
            'entry_date', NEW.entry_date,
            'period_id', NEW.period_id,
            'reference', NEW.reference,
            'description', NEW.description,
            'source', NEW.source,
            'is_posted', NEW.is_posted,
            'is_void', NEW.is_void,
            'reverses_entry_id', NEW.reverses_entry_id,
            'created_by', NEW.created_by,
            'created_at', NEW.created_at,
            'reversal_reason', NEW.reversal_reason,
            'entry_number', NEW.entry_number,
            'posted_by', NEW.posted_by,
            'posted_at', NEW.posted_at,
            'approved_by', NEW.approved_by,
            'approved_at', NEW.approved_at,
            'origin', NEW.origin),
            '$.lines', json((SELECT json_group_array(json_object(
                    'line_id', l.line_id,
                    'entry_id', l.entry_id,
                    'account_id', l.account_id,
                    'debit_cents', l.debit_cents,
                    'credit_cents', l.credit_cents,
                    'memo', l.memo,
                    'contact_id', l.contact_id,
                    'recon_id', l.recon_id,
                    'project_id', l.project_id,
                    'cost_code_id', l.cost_code_id,
                    'deferral_id', l.deferral_id,
                    'batch_id', l.batch_id,
                    'is_retainage_line', l.is_retainage_line,
                    'external_ref', l.external_ref))
                FROM journal_line AS l WHERE l.entry_id = NEW.entry_id)))
        ELSE json_object(
            'entry_id', NEW.entry_id,
            'entry_date', NEW.entry_date,
            'period_id', NEW.period_id,
            'reference', NEW.reference,
            'description', NEW.description,
            'source', NEW.source,
            'is_posted', NEW.is_posted,
            'is_void', NEW.is_void,
            'reverses_entry_id', NEW.reverses_entry_id,
            'created_by', NEW.created_by,
            'created_at', NEW.created_at,
            'reversal_reason', NEW.reversal_reason,
            'entry_number', NEW.entry_number,
            'posted_by', NEW.posted_by,
            'posted_at', NEW.posted_at,
            'approved_by', NEW.approved_by,
            'approved_at', NEW.approved_at,
            'origin', NEW.origin) END,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_journal_entry_delete
AFTER DELETE ON journal_entry
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'journal_entry', OLD.entry_id,
        'Delete',
        json_object(
            'entry_id', OLD.entry_id,
            'entry_date', OLD.entry_date,
            'period_id', OLD.period_id,
            'reference', OLD.reference,
            'description', OLD.description,
            'source', OLD.source,
            'is_posted', OLD.is_posted,
            'is_void', OLD.is_void,
            'reverses_entry_id', OLD.reverses_entry_id,
            'created_by', OLD.created_by,
            'created_at', OLD.created_at,
            'reversal_reason', OLD.reversal_reason,
            'entry_number', OLD.entry_number,
            'posted_by', OLD.posted_by,
            'posted_at', OLD.posted_at,
            'approved_by', OLD.approved_by,
            'approved_at', OLD.approved_at,
            'origin', OLD.origin),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_period_insert
AFTER INSERT ON fiscal_period
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_period', NEW.period_id,
        'Insert',
        NULL,
        json_object(
            'period_id', NEW.period_id,
            'name', NEW.name,
            'start_date', NEW.start_date,
            'end_date', NEW.end_date,
            'is_closed', NEW.is_closed,
            'closed_at', NEW.closed_at,
            'closed_by', NEW.closed_by),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_period_update
AFTER UPDATE ON fiscal_period
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_period', NEW.period_id,
        'Update',
        json_object(
            'period_id', OLD.period_id,
            'name', OLD.name,
            'start_date', OLD.start_date,
            'end_date', OLD.end_date,
            'is_closed', OLD.is_closed,
            'closed_at', OLD.closed_at,
            'closed_by', OLD.closed_by),
        json_object(
            'period_id', NEW.period_id,
            'name', NEW.name,
            'start_date', NEW.start_date,
            'end_date', NEW.end_date,
            'is_closed', NEW.is_closed,
            'closed_at', NEW.closed_at,
            'closed_by', NEW.closed_by),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_period_delete
AFTER DELETE ON fiscal_period
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_period', OLD.period_id,
        'Delete',
        json_object(
            'period_id', OLD.period_id,
            'name', OLD.name,
            'start_date', OLD.start_date,
            'end_date', OLD.end_date,
            'is_closed', OLD.is_closed,
            'closed_at', OLD.closed_at,
            'closed_by', OLD.closed_by),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_account_insert
AFTER INSERT ON account
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'account', NEW.account_id,
        'Insert',
        NULL,
        json_object(
            'account_id', NEW.account_id,
            'code', NEW.code,
            'name', NEW.name,
            'type_id', NEW.type_id,
            'parent_id', NEW.parent_id,
            'is_postable', NEW.is_postable,
            'is_active', NEW.is_active,
            'is_deferral_account', NEW.is_deferral_account,
            'control_type', NEW.control_type),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_account_update
AFTER UPDATE ON account
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'account', NEW.account_id,
        'Update',
        json_object(
            'account_id', OLD.account_id,
            'code', OLD.code,
            'name', OLD.name,
            'type_id', OLD.type_id,
            'parent_id', OLD.parent_id,
            'is_postable', OLD.is_postable,
            'is_active', OLD.is_active,
            'is_deferral_account', OLD.is_deferral_account,
            'control_type', OLD.control_type),
        json_object(
            'account_id', NEW.account_id,
            'code', NEW.code,
            'name', NEW.name,
            'type_id', NEW.type_id,
            'parent_id', NEW.parent_id,
            'is_postable', NEW.is_postable,
            'is_active', NEW.is_active,
            'is_deferral_account', NEW.is_deferral_account,
            'control_type', NEW.control_type),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_account_delete
AFTER DELETE ON account
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'account', OLD.account_id,
        'Delete',
        json_object(
            'account_id', OLD.account_id,
            'code', OLD.code,
            'name', OLD.name,
            'type_id', OLD.type_id,
            'parent_id', OLD.parent_id,
            'is_postable', OLD.is_postable,
            'is_active', OLD.is_active,
            'is_deferral_account', OLD.is_deferral_account,
            'control_type', OLD.control_type),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_invoice_insert
AFTER INSERT ON invoice
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'invoice', NEW.invoice_id,
        'Insert',
        NULL,
        json_object(
            'invoice_id', NEW.invoice_id,
            'invoice_type', NEW.invoice_type,
            'contact_id', NEW.contact_id,
            'project_id', NEW.project_id,
            'subscription_id', NEW.subscription_id,
            'invoice_number', NEW.invoice_number,
            'issue_date', NEW.issue_date,
            'due_date', NEW.due_date,
            'terms', NEW.terms,
            'status', NEW.status,
            'currency', NEW.currency,
            'exchange_rate', NEW.exchange_rate,
            'subtotal_cents', NEW.subtotal_cents,
            'vatable_sales_cents', NEW.vatable_sales_cents,
            'vat_exempt_sales_cents', NEW.vat_exempt_sales_cents,
            'zero_rated_sales_cents', NEW.zero_rated_sales_cents,
            'tax_cents', NEW.tax_cents,
            'cwt_rate', NEW.cwt_rate,
            'cwt_amount_cents', NEW.cwt_amount_cents,
            'total_cents', NEW.total_cents,
            'retainage_cents', NEW.retainage_cents,
            'is_eis_transmitted', NEW.is_eis_transmitted,
            'entry_id', NEW.entry_id,
            'batch_id', NEW.batch_id,
            'external_ref', NEW.external_ref,
            'ledger_side', NEW.ledger_side,
            'series_id', NEW.series_id,
            'sequence_number', NEW.sequence_number),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_invoice_update
AFTER UPDATE ON invoice
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'invoice', NEW.invoice_id,
        'Update',
        json_object(
            'invoice_id', OLD.invoice_id,
            'invoice_type', OLD.invoice_type,
            'contact_id', OLD.contact_id,
            'project_id', OLD.project_id,
            'subscription_id', OLD.subscription_id,
            'invoice_number', OLD.invoice_number,
            'issue_date', OLD.issue_date,
            'due_date', OLD.due_date,
            'terms', OLD.terms,
            'status', OLD.status,
            'currency', OLD.currency,
            'exchange_rate', OLD.exchange_rate,
            'subtotal_cents', OLD.subtotal_cents,
            'vatable_sales_cents', OLD.vatable_sales_cents,
            'vat_exempt_sales_cents', OLD.vat_exempt_sales_cents,
            'zero_rated_sales_cents', OLD.zero_rated_sales_cents,
            'tax_cents', OLD.tax_cents,
            'cwt_rate', OLD.cwt_rate,
            'cwt_amount_cents', OLD.cwt_amount_cents,
            'total_cents', OLD.total_cents,
            'retainage_cents', OLD.retainage_cents,
            'is_eis_transmitted', OLD.is_eis_transmitted,
            'entry_id', OLD.entry_id,
            'batch_id', OLD.batch_id,
            'external_ref', OLD.external_ref,
            'ledger_side', OLD.ledger_side,
            'series_id', OLD.series_id,
            'sequence_number', OLD.sequence_number),
        json_object(
            'invoice_id', NEW.invoice_id,
            'invoice_type', NEW.invoice_type,
            'contact_id', NEW.contact_id,
            'project_id', NEW.project_id,
            'subscription_id', NEW.subscription_id,
            'invoice_number', NEW.invoice_number,
            'issue_date', NEW.issue_date,
            'due_date', NEW.due_date,
            'terms', NEW.terms,
            'status', NEW.status,
            'currency', NEW.currency,
            'exchange_rate', NEW.exchange_rate,
            'subtotal_cents', NEW.subtotal_cents,
            'vatable_sales_cents', NEW.vatable_sales_cents,
            'vat_exempt_sales_cents', NEW.vat_exempt_sales_cents,
            'zero_rated_sales_cents', NEW.zero_rated_sales_cents,
            'tax_cents', NEW.tax_cents,
            'cwt_rate', NEW.cwt_rate,
            'cwt_amount_cents', NEW.cwt_amount_cents,
            'total_cents', NEW.total_cents,
            'retainage_cents', NEW.retainage_cents,
            'is_eis_transmitted', NEW.is_eis_transmitted,
            'entry_id', NEW.entry_id,
            'batch_id', NEW.batch_id,
            'external_ref', NEW.external_ref,
            'ledger_side', NEW.ledger_side,
            'series_id', NEW.series_id,
            'sequence_number', NEW.sequence_number),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_invoice_delete
AFTER DELETE ON invoice
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'invoice', OLD.invoice_id,
        'Delete',
        json_object(
            'invoice_id', OLD.invoice_id,
            'invoice_type', OLD.invoice_type,
            'contact_id', OLD.contact_id,
            'project_id', OLD.project_id,
            'subscription_id', OLD.subscription_id,
            'invoice_number', OLD.invoice_number,
            'issue_date', OLD.issue_date,
            'due_date', OLD.due_date,
            'terms', OLD.terms,
            'status', OLD.status,
            'currency', OLD.currency,
            'exchange_rate', OLD.exchange_rate,
            'subtotal_cents', OLD.subtotal_cents,
            'vatable_sales_cents', OLD.vatable_sales_cents,
            'vat_exempt_sales_cents', OLD.vat_exempt_sales_cents,
            'zero_rated_sales_cents', OLD.zero_rated_sales_cents,
            'tax_cents', OLD.tax_cents,
            'cwt_rate', OLD.cwt_rate,
            'cwt_amount_cents', OLD.cwt_amount_cents,
            'total_cents', OLD.total_cents,
            'retainage_cents', OLD.retainage_cents,
            'is_eis_transmitted', OLD.is_eis_transmitted,
            'entry_id', OLD.entry_id,
            'batch_id', OLD.batch_id,
            'external_ref', OLD.external_ref,
            'ledger_side', OLD.ledger_side,
            'series_id', OLD.series_id,
            'sequence_number', OLD.sequence_number),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_insert
AFTER INSERT ON payment
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment', NEW.payment_id,
        'Insert',
        NULL,
        json_object(
            'payment_id', NEW.payment_id,
            'direction', NEW.direction,
            'contact_id', NEW.contact_id,
            'payment_date', NEW.payment_date,
            'amount_cents', NEW.amount_cents,
            'currency', NEW.currency,
            'exchange_rate', NEW.exchange_rate,
            'method', NEW.method,
            'bank_account_id', NEW.bank_account_id,
            'entry_id', NEW.entry_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_update
AFTER UPDATE ON payment
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment', NEW.payment_id,
        'Update',
        json_object(
            'payment_id', OLD.payment_id,
            'direction', OLD.direction,
            'contact_id', OLD.contact_id,
            'payment_date', OLD.payment_date,
            'amount_cents', OLD.amount_cents,
            'currency', OLD.currency,
            'exchange_rate', OLD.exchange_rate,
            'method', OLD.method,
            'bank_account_id', OLD.bank_account_id,
            'entry_id', OLD.entry_id),
        json_object(
            'payment_id', NEW.payment_id,
            'direction', NEW.direction,
            'contact_id', NEW.contact_id,
            'payment_date', NEW.payment_date,
            'amount_cents', NEW.amount_cents,
            'currency', NEW.currency,
            'exchange_rate', NEW.exchange_rate,
            'method', NEW.method,
            'bank_account_id', NEW.bank_account_id,
            'entry_id', NEW.entry_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_delete
AFTER DELETE ON payment
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment', OLD.payment_id,
        'Delete',
        json_object(
            'payment_id', OLD.payment_id,
            'direction', OLD.direction,
            'contact_id', OLD.contact_id,
            'payment_date', OLD.payment_date,
            'amount_cents', OLD.amount_cents,
            'currency', OLD.currency,
            'exchange_rate', OLD.exchange_rate,
            'method', OLD.method,
            'bank_account_id', OLD.bank_account_id,
            'entry_id', OLD.entry_id),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_allocation_insert
AFTER INSERT ON payment_allocation
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment_allocation', NEW.allocation_id,
        'Insert',
        NULL,
        json_object(
            'allocation_id', NEW.allocation_id,
            'payment_id', NEW.payment_id,
            'invoice_id', NEW.invoice_id,
            'deferral_id', NEW.deferral_id,
            'amount_applied_cents', NEW.amount_applied_cents),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_allocation_update
AFTER UPDATE ON payment_allocation
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment_allocation', NEW.allocation_id,
        'Update',
        json_object(
            'allocation_id', OLD.allocation_id,
            'payment_id', OLD.payment_id,
            'invoice_id', OLD.invoice_id,
            'deferral_id', OLD.deferral_id,
            'amount_applied_cents', OLD.amount_applied_cents),
        json_object(
            'allocation_id', NEW.allocation_id,
            'payment_id', NEW.payment_id,
            'invoice_id', NEW.invoice_id,
            'deferral_id', NEW.deferral_id,
            'amount_applied_cents', NEW.amount_applied_cents),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_allocation_delete
AFTER DELETE ON payment_allocation
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment_allocation', OLD.allocation_id,
        'Delete',
        json_object(
            'allocation_id', OLD.allocation_id,
            'payment_id', OLD.payment_id,
            'invoice_id', OLD.invoice_id,
            'deferral_id', OLD.deferral_id,
            'amount_applied_cents', OLD.amount_applied_cents),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_settings_insert
AFTER INSERT ON company_settings
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_settings', NEW.id,
        'Insert',
        NULL,
        json_object(
            'id', NEW.id,
            'company_name', NEW.company_name,
            'fiscal_year_start', NEW.fiscal_year_start,
            'base_currency', NEW.base_currency,
            'tax_id', NEW.tax_id,
            'branch_code', NEW.branch_code,
            'tax_type', NEW.tax_type,
            'cas_permit_number', NEW.cas_permit_number,
            'next_invoice_number', NEW.next_invoice_number,
            'contract_revenue_acct_id', NEW.contract_revenue_acct_id,
            'contract_cost_acct_id', NEW.contract_cost_acct_id,
            'underbilled_acct_id', NEW.underbilled_acct_id,
            'overbilled_acct_id', NEW.overbilled_acct_id,
            'payroll_clearing_acct_id', NEW.payroll_clearing_acct_id,
            'manual_entry_approval', NEW.manual_entry_approval,
            'manual_entry_approval_threshold_cents', NEW.manual_entry_approval_threshold_cents),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_settings_update
AFTER UPDATE ON company_settings
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_settings', NEW.id,
        'Update',
        json_object(
            'id', OLD.id,
            'company_name', OLD.company_name,
            'fiscal_year_start', OLD.fiscal_year_start,
            'base_currency', OLD.base_currency,
            'tax_id', OLD.tax_id,
            'branch_code', OLD.branch_code,
            'tax_type', OLD.tax_type,
            'cas_permit_number', OLD.cas_permit_number,
            'next_invoice_number', OLD.next_invoice_number,
            'contract_revenue_acct_id', OLD.contract_revenue_acct_id,
            'contract_cost_acct_id', OLD.contract_cost_acct_id,
            'underbilled_acct_id', OLD.underbilled_acct_id,
            'overbilled_acct_id', OLD.overbilled_acct_id,
            'payroll_clearing_acct_id', OLD.payroll_clearing_acct_id,
            'manual_entry_approval', OLD.manual_entry_approval,
            'manual_entry_approval_threshold_cents', OLD.manual_entry_approval_threshold_cents),
        json_object(
            'id', NEW.id,
            'company_name', NEW.company_name,
            'fiscal_year_start', NEW.fiscal_year_start,
            'base_currency', NEW.base_currency,
            'tax_id', NEW.tax_id,
            'branch_code', NEW.branch_code,
            'tax_type', NEW.tax_type,
            'cas_permit_number', NEW.cas_permit_number,
            'next_invoice_number', NEW.next_invoice_number,
            'contract_revenue_acct_id', NEW.contract_revenue_acct_id,
            'contract_cost_acct_id', NEW.contract_cost_acct_id,
            'underbilled_acct_id', NEW.underbilled_acct_id,
            'overbilled_acct_id', NEW.overbilled_acct_id,
            'payroll_clearing_acct_id', NEW.payroll_clearing_acct_id,
            'manual_entry_approval', NEW.manual_entry_approval,
            'manual_entry_approval_threshold_cents', NEW.manual_entry_approval_threshold_cents),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_invoice_series_insert
AFTER INSERT ON invoice_series
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'invoice_series', NEW.series_id,
        'Insert',
        NULL,
        json_object(
            'series_id', NEW.series_id,
            'document_type', NEW.document_type,
            'prefix', NEW.prefix,
            'last_number', NEW.last_number,
            'registered_from', NEW.registered_from,
            'registered_to', NEW.registered_to,
            'authority_ref', NEW.authority_ref,
            'valid_until', NEW.valid_until,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_invoice_series_update
AFTER UPDATE ON invoice_series
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'invoice_series', NEW.series_id,
        'Update',
        json_object(
            'series_id', OLD.series_id,
            'document_type', OLD.document_type,
            'prefix', OLD.prefix,
            'last_number', OLD.last_number,
            'registered_from', OLD.registered_from,
            'registered_to', OLD.registered_to,
            'authority_ref', OLD.authority_ref,
            'valid_until', OLD.valid_until,
            'is_active', OLD.is_active),
        json_object(
            'series_id', NEW.series_id,
            'document_type', NEW.document_type,
            'prefix', NEW.prefix,
            'last_number', NEW.last_number,
            'registered_from', NEW.registered_from,
            'registered_to', NEW.registered_to,
            'authority_ref', NEW.authority_ref,
            'valid_until', NEW.valid_until,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_invoice_series_delete
AFTER DELETE ON invoice_series
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'invoice_series', OLD.series_id,
        'Delete',
        json_object(
            'series_id', OLD.series_id,
            'document_type', OLD.document_type,
            'prefix', OLD.prefix,
            'last_number', OLD.last_number,
            'registered_from', OLD.registered_from,
            'registered_to', OLD.registered_to,
            'authority_ref', OLD.authority_ref,
            'valid_until', OLD.valid_until,
            'is_active', OLD.is_active),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_addon_insert
AFTER INSERT ON company_addon
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_addon', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'addon_key', NEW.addon_key,
            'enabled', NEW.enabled,
            'enabled_at', NEW.enabled_at,
            'enabled_by', NEW.enabled_by,
            'addon_version', NEW.addon_version),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_addon_update
AFTER UPDATE ON company_addon
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_addon', NEW.rowid,
        'Update',
        json_object(
            'addon_key', OLD.addon_key,
            'enabled', OLD.enabled,
            'enabled_at', OLD.enabled_at,
            'enabled_by', OLD.enabled_by,
            'addon_version', OLD.addon_version),
        json_object(
            'addon_key', NEW.addon_key,
            'enabled', NEW.enabled,
            'enabled_at', NEW.enabled_at,
            'enabled_by', NEW.enabled_by,
            'addon_version', NEW.addon_version),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_addon_delete
AFTER DELETE ON company_addon
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_addon', OLD.rowid,
        'Delete',
        json_object(
            'addon_key', OLD.addon_key,
            'enabled', OLD.enabled,
            'enabled_at', OLD.enabled_at,
            'enabled_by', OLD.enabled_by,
            'addon_version', OLD.addon_version),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_reconciliation_insert
AFTER INSERT ON bank_reconciliation
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_reconciliation', NEW.recon_id,
        'Insert',
        NULL,
        json_object(
            'recon_id', NEW.recon_id,
            'account_id', NEW.account_id,
            'statement_date', NEW.statement_date,
            'statement_balance_cents', NEW.statement_balance_cents,
            'is_complete', NEW.is_complete),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_reconciliation_update
AFTER UPDATE ON bank_reconciliation
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_reconciliation', NEW.recon_id,
        'Update',
        json_object(
            'recon_id', OLD.recon_id,
            'account_id', OLD.account_id,
            'statement_date', OLD.statement_date,
            'statement_balance_cents', OLD.statement_balance_cents,
            'is_complete', OLD.is_complete),
        json_object(
            'recon_id', NEW.recon_id,
            'account_id', NEW.account_id,
            'statement_date', NEW.statement_date,
            'statement_balance_cents', NEW.statement_balance_cents,
            'is_complete', NEW.is_complete),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_reconciliation_delete
AFTER DELETE ON bank_reconciliation
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_reconciliation', OLD.recon_id,
        'Delete',
        json_object(
            'recon_id', OLD.recon_id,
            'account_id', OLD.account_id,
            'statement_date', OLD.statement_date,
            'statement_balance_cents', OLD.statement_balance_cents,
            'is_complete', OLD.is_complete),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;
