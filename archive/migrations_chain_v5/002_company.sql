-- Migration 2 (company): ledger integrity. See docs/schema_audit.md.
--
-- F2  project_budget.estimate_line_id references estimate_line(line_id).
-- F3  Posted journal entries are locked: they cannot be unposted, edited or
--     deleted, and their lines cannot be inserted, updated or deleted. The only
--     allowed change is is_void 0 -> 1. is_posted/is_void are NOT NULL 0/1.
-- F4  An entry cannot post into a closed fiscal period (by period_id, or by
--     entry_date falling inside a closed period).
-- F5  Posting requires 2+ lines, each with exactly one non-zero side, and
--     total debits > 0 and equal to total credits.
-- F6  Master-only tables (app_user, company_registry, user_company_access) are
--     removed. User columns (created_by, approved_by, assigned_pm_id, ...) hold
--     the system_master app_user.user_id as a plain INTEGER with no FK, since
--     SQLite cannot enforce keys across database files. audit_log stays here as
--     the company's own audit trail.
-- F7  Every money column has CHECK (typeof(col) = 'integer'); nullable money
--     columns allow NULL. Money stays in INTEGER cents (no STRICT tables).
--
-- Tables are rebuilt with the standard SQLite procedure: create new_x, copy,
-- drop x, rename new_x to x. Every definition below is the 001 definition
-- with only the changes above. The runner turns foreign keys off around this
-- script and runs foreign_key_check and integrity_check before committing.
--
-- Journal triggers reference the rebuilt tables, so they are dropped first and
-- recreated at the end. The dimension_value triggers are untouched.

DROP TRIGGER IF EXISTS journal_entry_require_balance_on_post;
DROP TRIGGER IF EXISTS journal_entry_no_direct_post;
DROP TRIGGER IF EXISTS journal_line_lock_insert_posted;
DROP TRIGGER IF EXISTS journal_line_lock_update_posted;
DROP TRIGGER IF EXISTS journal_line_lock_delete_posted;

-- audit_log
CREATE TABLE new_audit_log (

    log_id INTEGER PRIMARY KEY AUTOINCREMENT,

    logged_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    user_id INTEGER,

    table_name TEXT NOT NULL,

    record_id INTEGER NOT NULL,

    action TEXT CHECK (action IN ('Insert', 'Update', 'Delete', 'Post', 'Approve', 'Void')),

    old_value TEXT,

    new_value TEXT,

    software_version_tag TEXT,

    terminal_id TEXT
);
INSERT INTO new_audit_log (log_id, logged_at, user_id, table_name, record_id, action, old_value, new_value, software_version_tag, terminal_id)
    SELECT log_id, logged_at, user_id, table_name, record_id, action, old_value, new_value, software_version_tag, terminal_id FROM audit_log;
DROP TABLE audit_log;
ALTER TABLE new_audit_log RENAME TO audit_log;

-- bank_reconciliation
CREATE TABLE new_bank_reconciliation (

    recon_id INTEGER PRIMARY KEY AUTOINCREMENT,

    account_id INTEGER REFERENCES account(account_id),

    statement_date TEXT NOT NULL,

    statement_balance_cents INTEGER NOT NULL,

    is_complete INTEGER DEFAULT 0,
    CHECK (typeof(statement_balance_cents) = 'integer')
);
INSERT INTO new_bank_reconciliation (recon_id, account_id, statement_date, statement_balance_cents, is_complete)
    SELECT recon_id, account_id, statement_date, statement_balance_cents, is_complete FROM bank_reconciliation;
DROP TABLE bank_reconciliation;
ALTER TABLE new_bank_reconciliation RENAME TO bank_reconciliation;

-- change_order_line
CREATE TABLE new_change_order_line (

	co_line_id INTEGER PRIMARY KEY AUTOINCREMENT,

	co_id INTEGER REFERENCES change_order(co_id),

	cost_code_id INTEGER REFERENCES cost_code(cost_code_id),

	sov_line_id INTEGER REFERENCES contract_line(sov_line_id),

	description TEXT,

	revenue_change_cents INTEGER,

	cost_change_cents INTEGER,
    CHECK (revenue_change_cents IS NULL OR typeof(revenue_change_cents) = 'integer'),
    CHECK (cost_change_cents IS NULL OR typeof(cost_change_cents) = 'integer')
);
INSERT INTO new_change_order_line (co_line_id, co_id, cost_code_id, sov_line_id, description, revenue_change_cents, cost_change_cents)
    SELECT co_line_id, co_id, cost_code_id, sov_line_id, description, revenue_change_cents, cost_change_cents FROM change_order_line;
DROP TABLE change_order_line;
ALTER TABLE new_change_order_line RENAME TO change_order_line;

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
);
INSERT INTO new_contract (contract_id, project_id, contact_id, contract_number, contract_type, contract_date, start_date, completion_date, original_amount_cents, retainage_pct, payment_terms, status, document_ref, notes)
    SELECT contract_id, project_id, contact_id, contract_number, contract_type, contract_date, start_date, completion_date, original_amount_cents, retainage_pct, payment_terms, status, document_ref, notes FROM contract;
DROP TABLE contract;
ALTER TABLE new_contract RENAME TO contract;

-- contract_line
CREATE TABLE new_contract_line (

	sov_line_id INTEGER PRIMARY KEY AUTOINCREMENT,

	contract_id INTEGER REFERENCES contract(contract_id),

	line_number TEXT,

	description TEXT,

	cost_code_id INTEGER REFERENCES cost_code(cost_code_id),

	scheduled_value_cents INTEGER,

	sort_order INTEGER,

	change_order_id INTEGER,
    CHECK (scheduled_value_cents IS NULL OR typeof(scheduled_value_cents) = 'integer')
);
INSERT INTO new_contract_line (sov_line_id, contract_id, line_number, description, cost_code_id, scheduled_value_cents, sort_order, change_order_id)
    SELECT sov_line_id, contract_id, line_number, description, cost_code_id, scheduled_value_cents, sort_order, change_order_id FROM contract_line;
DROP TABLE contract_line;
ALTER TABLE new_contract_line RENAME TO contract_line;

-- crm_activity_stream
CREATE TABLE new_crm_activity_stream (

    activity_id       INTEGER PRIMARY KEY AUTOINCREMENT,

    contact_id        INTEGER NOT NULL REFERENCES contact(contact_id) ON DELETE CASCADE,

    project_id        INTEGER REFERENCES project(project_id) ON DELETE CASCADE,

    author_user_id    INTEGER NOT NULL,

    category          TEXT CHECK (category IN ('Sales Call', 'Email Exchange', 'Field Site Note', 'Active Project Issue')),

    severity          TEXT CHECK (severity IN ('Low', 'Medium', 'High')) DEFAULT 'Low',

    subject_header    TEXT NOT NULL,

    body_content      TEXT NOT NULL,

    is_resolved       INTEGER DEFAULT 0 CHECK (is_resolved IN (0, 1)), 

    opened_at         DATETIME DEFAULT CURRENT_TIMESTAMP,

    resolved_at       DATETIME, 

    resolution_seconds INTEGER DEFAULT NULL
);
INSERT INTO new_crm_activity_stream (activity_id, contact_id, project_id, author_user_id, category, severity, subject_header, body_content, is_resolved, opened_at, resolved_at, resolution_seconds)
    SELECT activity_id, contact_id, project_id, author_user_id, category, severity, subject_header, body_content, is_resolved, opened_at, resolved_at, resolution_seconds FROM crm_activity_stream;
DROP TABLE crm_activity_stream;
ALTER TABLE new_crm_activity_stream RENAME TO crm_activity_stream;

-- crm_approval_instance
CREATE TABLE new_crm_approval_instance (

    instance_id         INTEGER PRIMARY KEY AUTOINCREMENT,

    rule_id             INTEGER NOT NULL REFERENCES crm_approval_rule(rule_id),

    target_type         TEXT CHECK (target_type IN ('Contract', 'Estimate', 'Change Order')),

    target_record_id    INTEGER NOT NULL, 

    assigned_user_id    INTEGER,

    status              TEXT CHECK (status IN ('Pending', 'Approved', 'Rejected')) DEFAULT 'Pending',

    actioned_at         DATETIME,

    memo_comments       TEXT,

    security_hash       TEXT
);
INSERT INTO new_crm_approval_instance (instance_id, rule_id, target_type, target_record_id, assigned_user_id, status, actioned_at, memo_comments, security_hash)
    SELECT instance_id, rule_id, target_type, target_record_id, assigned_user_id, status, actioned_at, memo_comments, security_hash FROM crm_approval_instance;
DROP TABLE crm_approval_instance;
ALTER TABLE new_crm_approval_instance RENAME TO crm_approval_instance;

-- crm_approval_rule
CREATE TABLE new_crm_approval_rule (

    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,

    pipeline_id         INTEGER REFERENCES crm_pipeline(pipeline_id),

    rule_name           TEXT NOT NULL, 

    min_value_cents     INTEGER DEFAULT 0,

    max_value_cents     INTEGER DEFAULT 999999999,

    required_job_title  TEXT NOT NULL, -- Rules map directly to staff job titles

    sequence_step       INTEGER DEFAULT 1,
    CHECK (min_value_cents IS NULL OR typeof(min_value_cents) = 'integer'),
    CHECK (max_value_cents IS NULL OR typeof(max_value_cents) = 'integer')
);
INSERT INTO new_crm_approval_rule (rule_id, pipeline_id, rule_name, min_value_cents, max_value_cents, required_job_title, sequence_step)
    SELECT rule_id, pipeline_id, rule_name, min_value_cents, max_value_cents, required_job_title, sequence_step FROM crm_approval_rule;
DROP TABLE crm_approval_rule;
ALTER TABLE new_crm_approval_rule RENAME TO crm_approval_rule;

-- crm_change_line
CREATE TABLE new_crm_change_line (

    change_line_id            INTEGER PRIMARY KEY AUTOINCREMENT,

    change_id                 INTEGER NOT NULL REFERENCES crm_change_order(change_id) ON DELETE CASCADE,

    cost_code_id              INTEGER NOT NULL REFERENCES cost_code(cost_code_id), 

    quantity_change           REAL NOT NULL, 

    unit_cost_cents           INTEGER NOT NULL,

    extended_price_cents      INTEGER NOT NULL,
    CHECK (typeof(unit_cost_cents) = 'integer'),
    CHECK (typeof(extended_price_cents) = 'integer')
);
INSERT INTO new_crm_change_line (change_line_id, change_id, cost_code_id, quantity_change, unit_cost_cents, extended_price_cents)
    SELECT change_line_id, change_id, cost_code_id, quantity_change, unit_cost_cents, extended_price_cents FROM crm_change_line;
DROP TABLE crm_change_line;
ALTER TABLE new_crm_change_line RENAME TO crm_change_line;

-- crm_change_order
CREATE TABLE new_crm_change_order (

    change_id            INTEGER PRIMARY KEY AUTOINCREMENT,

    project_id           INTEGER NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,

    authorizing_pm_id    INTEGER NOT NULL,

    change_order_number  TEXT NOT NULL UNIQUE, -- e.g., "CO-01-PRJ-104"

    status               TEXT CHECK (status IN ('Draft', 'Submitted', 'Executed', 'Rejected')) DEFAULT 'Draft',

    reason_memo          TEXT,

    signed_at            DATETIME
);
INSERT INTO new_crm_change_order (change_id, project_id, authorizing_pm_id, change_order_number, status, reason_memo, signed_at)
    SELECT change_id, project_id, authorizing_pm_id, change_order_number, status, reason_memo, signed_at FROM crm_change_order;
DROP TABLE crm_change_order;
ALTER TABLE new_crm_change_order RENAME TO crm_change_order;

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
);
INSERT INTO new_crm_opportunity (opportunity_id, contact_id, pipeline_id, current_stage_id, deal_name, deal_value_cents, probability_pct, estimated_close, downstream_estimate_id, downstream_contract_id, created_by, created_at)
    SELECT opportunity_id, contact_id, pipeline_id, current_stage_id, deal_name, deal_value_cents, probability_pct, estimated_close, downstream_estimate_id, downstream_contract_id, created_by, created_at FROM crm_opportunity;
DROP TABLE crm_opportunity;
ALTER TABLE new_crm_opportunity RENAME TO crm_opportunity;

-- crm_stage_history
CREATE TABLE new_crm_stage_history (

    history_id       INTEGER PRIMARY KEY AUTOINCREMENT,

    opportunity_id   INTEGER NOT NULL REFERENCES crm_opportunity(opportunity_id) ON DELETE CASCADE,

    from_stage_id    INTEGER REFERENCES crm_stage(stage_id),

    to_stage_id      INTEGER NOT NULL REFERENCES crm_stage(stage_id),

    changed_by       INTEGER,

    changed_at       DATETIME DEFAULT CURRENT_TIMESTAMP,

    days_in_stage    INTEGER DEFAULT 0,

    memo             TEXT
);
INSERT INTO new_crm_stage_history (history_id, opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at, days_in_stage, memo)
    SELECT history_id, opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at, days_in_stage, memo FROM crm_stage_history;
DROP TABLE crm_stage_history;
ALTER TABLE new_crm_stage_history RENAME TO crm_stage_history;

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
);
INSERT INTO new_deferral (deferral_id, kind, advance_type, description, contact_id, invoice_id, invoice_line_id, payment_id, original_amount_cents, start_date, end_date, method, proration, deferral_account_id, recognition_account_id, project_id, cost_code_id, supersedes_id, status, cancelled_date, memo)
    SELECT deferral_id, kind, advance_type, description, contact_id, invoice_id, invoice_line_id, payment_id, original_amount_cents, start_date, end_date, method, proration, deferral_account_id, recognition_account_id, project_id, cost_code_id, supersedes_id, status, cancelled_date, memo FROM deferral;
DROP TABLE deferral;
ALTER TABLE new_deferral RENAME TO deferral;

-- deferral_schedule_line
CREATE TABLE new_deferral_schedule_line (

	schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,

	deferral_id INTEGER REFERENCES deferral(deferral_id),

	period_id INTEGER REFERENCES fiscal_period(period_id),

	amort_date TEXT NOT NULL,

	amount_cents INTEGER NOT NULL,

	status TEXT CHECK (status IN ('Scheduled', 'Posted', 'Skipped')),

	entry_id INTEGER REFERENCES journal_entry(entry_id),

	UNIQUE (deferral_id, period_id),
    CHECK (typeof(amount_cents) = 'integer')
);
INSERT INTO new_deferral_schedule_line (schedule_id, deferral_id, period_id, amort_date, amount_cents, status, entry_id)
    SELECT schedule_id, deferral_id, period_id, amort_date, amount_cents, status, entry_id FROM deferral_schedule_line;
DROP TABLE deferral_schedule_line;
ALTER TABLE new_deferral_schedule_line RENAME TO deferral_schedule_line;

-- estimate
CREATE TABLE new_estimate (

    estimate_id           INTEGER PRIMARY KEY AUTOINCREMENT,

    estimate_number       TEXT NOT NULL UNIQUE, -- e.g., "EST-2026-001"

    name                  TEXT NOT NULL,

    contact_id            INTEGER NOT NULL REFERENCES contact(contact_id),

    source_opportunity_id INTEGER REFERENCES crm_opportunity(opportunity_id),

    assigned_pm_id        INTEGER, 

    total_cost_cents      INTEGER DEFAULT 0,

    total_price_cents     INTEGER DEFAULT 0,

    status                TEXT CHECK (status IN ('Draft', 'Submitted', 'Approved', 'Won', 'Lost')) DEFAULT 'Draft',

    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (total_cost_cents IS NULL OR typeof(total_cost_cents) = 'integer'),
    CHECK (total_price_cents IS NULL OR typeof(total_price_cents) = 'integer')
);
INSERT INTO new_estimate (estimate_id, estimate_number, name, contact_id, source_opportunity_id, assigned_pm_id, total_cost_cents, total_price_cents, status, created_at)
    SELECT estimate_id, estimate_number, name, contact_id, source_opportunity_id, assigned_pm_id, total_cost_cents, total_price_cents, status, created_at FROM estimate;
DROP TABLE estimate;
ALTER TABLE new_estimate RENAME TO estimate;

-- estimate_line
CREATE TABLE new_estimate_line (

    line_id                       INTEGER PRIMARY KEY AUTOINCREMENT,

    estimate_id                   INTEGER NOT NULL REFERENCES estimate(estimate_id) ON DELETE CASCADE,

    cost_code_id                  INTEGER NOT NULL REFERENCES cost_code(cost_code_id),

    quantity                      REAL NOT NULL CHECK (quantity > 0),

    unit_of_measure               TEXT NOT NULL, -- "Bags", "Board Feet", etc.

    estimated_unit_cost_cents     INTEGER NOT NULL, 

    estimated_extended_cost_cents INTEGER NOT NULL, 

    price_to_customer_cents       INTEGER NOT NULL,
    CHECK (typeof(estimated_unit_cost_cents) = 'integer'),
    CHECK (typeof(estimated_extended_cost_cents) = 'integer'),
    CHECK (typeof(price_to_customer_cents) = 'integer')
);
INSERT INTO new_estimate_line (line_id, estimate_id, cost_code_id, quantity, unit_of_measure, estimated_unit_cost_cents, estimated_extended_cost_cents, price_to_customer_cents)
    SELECT line_id, estimate_id, cost_code_id, quantity, unit_of_measure, estimated_unit_cost_cents, estimated_extended_cost_cents, price_to_customer_cents FROM estimate_line;
DROP TABLE estimate_line;
ALTER TABLE new_estimate_line RENAME TO estimate_line;

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
);
INSERT INTO new_import_batch (batch_id, source_id, batch_type, batch_nature, reverses_batch_id, file_name, period_start, period_end, imported_at, total_cents, status, entry_id)
    SELECT batch_id, source_id, batch_type, batch_nature, reverses_batch_id, file_name, period_start, period_end, imported_at, total_cents, status, entry_id FROM import_batch;
DROP TABLE import_batch;
ALTER TABLE new_import_batch RENAME TO import_batch;

-- invoice
CREATE TABLE new_invoice (
    invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_type TEXT CHECK (invoice_type IN ('Invoice', 'Bill', 'Credit memo')),
    contact_id INTEGER REFERENCES contact(contact_id),
    project_id INTEGER REFERENCES project(project_id),
    subscription_id INTEGER REFERENCES subscription(subscription_id),
    invoice_number TEXT NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    terms TEXT CHECK (terms IN ('Due on Receipt', 'Net 15', 'Net 30', 'Net 60')) DEFAULT 'Net 30',
    status TEXT CHECK (status IN ('Draft', 'Sent', 'Paid', 'Void', 'Covered by advance')),
    currency TEXT DEFAULT 'PHP',
    exchange_rate REAL DEFAULT 1.0,
    subtotal_cents INTEGER DEFAULT 0,
    vatable_sales_cents INTEGER DEFAULT 0,
    vat_exempt_sales_cents INTEGER DEFAULT 0,
    zero_rated_sales_cents INTEGER DEFAULT 0,
    tax_cents INTEGER DEFAULT 0,
    cwt_rate REAL DEFAULT 0.0,
    cwt_amount_cents INTEGER DEFAULT 0,
    total_cents INTEGER DEFAULT 0,
    retainage_cents INTEGER DEFAULT 0,
    is_eis_transmitted INTEGER DEFAULT 0,
    entry_id INTEGER REFERENCES journal_entry(entry_id),
    batch_id INTEGER,
    external_ref TEXT,
    UNIQUE (invoice_type, contact_id, invoice_number),
    CHECK (subtotal_cents IS NULL OR typeof(subtotal_cents) = 'integer'),
    CHECK (vatable_sales_cents IS NULL OR typeof(vatable_sales_cents) = 'integer'),
    CHECK (vat_exempt_sales_cents IS NULL OR typeof(vat_exempt_sales_cents) = 'integer'),
    CHECK (zero_rated_sales_cents IS NULL OR typeof(zero_rated_sales_cents) = 'integer'),
    CHECK (tax_cents IS NULL OR typeof(tax_cents) = 'integer'),
    CHECK (cwt_amount_cents IS NULL OR typeof(cwt_amount_cents) = 'integer'),
    CHECK (total_cents IS NULL OR typeof(total_cents) = 'integer'),
    CHECK (retainage_cents IS NULL OR typeof(retainage_cents) = 'integer')
);
INSERT INTO new_invoice (invoice_id, invoice_type, contact_id, project_id, subscription_id, invoice_number, issue_date, due_date, terms, status, currency, exchange_rate, subtotal_cents, vatable_sales_cents, vat_exempt_sales_cents, zero_rated_sales_cents, tax_cents, cwt_rate, cwt_amount_cents, total_cents, retainage_cents, is_eis_transmitted, entry_id, batch_id, external_ref)
    SELECT invoice_id, invoice_type, contact_id, project_id, subscription_id, invoice_number, issue_date, due_date, terms, status, currency, exchange_rate, subtotal_cents, vatable_sales_cents, vat_exempt_sales_cents, zero_rated_sales_cents, tax_cents, cwt_rate, cwt_amount_cents, total_cents, retainage_cents, is_eis_transmitted, entry_id, batch_id, external_ref FROM invoice;
DROP TABLE invoice;
ALTER TABLE new_invoice RENAME TO invoice;

-- invoice_line
CREATE TABLE new_invoice_line (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER REFERENCES invoice(invoice_id) ON DELETE CASCADE,
    description TEXT,
    quantity REAL DEFAULT 1.0,
    unit_price_cents INTEGER DEFAULT 0,
    account_id INTEGER REFERENCES account(account_id),
    tax_rate_id INTEGER REFERENCES tax_rate(tax_rate_id),
    service_start_date TEXT,
    service_end_date TEXT,
    is_retainage_line INTEGER DEFAULT 0,
    cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
    department_tag TEXT DEFAULT NULL,
    sort_order INTEGER DEFAULT 0,
    CHECK (unit_price_cents IS NULL OR typeof(unit_price_cents) = 'integer')
);
INSERT INTO new_invoice_line (line_id, invoice_id, description, quantity, unit_price_cents, account_id, tax_rate_id, service_start_date, service_end_date, is_retainage_line, cost_code_id, department_tag, sort_order)
    SELECT line_id, invoice_id, description, quantity, unit_price_cents, account_id, tax_rate_id, service_start_date, service_end_date, is_retainage_line, cost_code_id, department_tag, sort_order FROM invoice_line;
DROP TABLE invoice_line;
ALTER TABLE new_invoice_line RENAME TO invoice_line;

-- journal_entry
CREATE TABLE new_journal_entry (

    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,

    entry_date TEXT NOT NULL,

    period_id INTEGER REFERENCES fiscal_period(period_id),

    reference TEXT,

    description TEXT,

    source TEXT CHECK (source IN ('Manual', 'Invoice', 'Bill', 'Payment', 'Adjustment', 'Payroll', 'Import', 'Deferral', 'Completion')),

    is_posted INTEGER NOT NULL DEFAULT 0 CHECK (is_posted IN (0, 1)),

    is_void INTEGER NOT NULL DEFAULT 0 CHECK (is_void IN (0, 1)),

    reverses_entry_id INTEGER REFERENCES journal_entry(entry_id),

    created_by INTEGER,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO new_journal_entry (entry_id, entry_date, period_id, reference, description, source, is_posted, is_void, reverses_entry_id, created_by, created_at)
    SELECT entry_id, entry_date, period_id, reference, description, source, is_posted, is_void, reverses_entry_id, created_by, created_at FROM journal_entry;
DROP TABLE journal_entry;
ALTER TABLE new_journal_entry RENAME TO journal_entry;

-- journal_line
CREATE TABLE new_journal_line (

    line_id INTEGER PRIMARY KEY AUTOINCREMENT,

    entry_id INTEGER REFERENCES journal_entry(entry_id),

    account_id INTEGER REFERENCES account(account_id),

    debit_cents INTEGER DEFAULT 0 CHECK (debit_cents >= 0),

    credit_cents INTEGER DEFAULT 0 CHECK (credit_cents >= 0),

    memo TEXT,

    contact_id INTEGER,

    recon_id INTEGER,

    project_id INTEGER,

    cost_code_id INTEGER,

    deferral_id INTEGER,

    batch_id INTEGER,

    is_retainage_line INTEGER DEFAULT 0,

    external_ref TEXT,

    CHECK (debit_cents = 0 OR credit_cents = 0),
    CHECK (debit_cents IS NULL OR typeof(debit_cents) = 'integer'),
    CHECK (credit_cents IS NULL OR typeof(credit_cents) = 'integer')
);
INSERT INTO new_journal_line (line_id, entry_id, account_id, debit_cents, credit_cents, memo, contact_id, recon_id, project_id, cost_code_id, deferral_id, batch_id, is_retainage_line, external_ref)
    SELECT line_id, entry_id, account_id, debit_cents, credit_cents, memo, contact_id, recon_id, project_id, cost_code_id, deferral_id, batch_id, is_retainage_line, external_ref FROM journal_line;
DROP TABLE journal_line;
ALTER TABLE new_journal_line RENAME TO journal_line;

-- payment
CREATE TABLE new_payment (

    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,

    direction TEXT CHECK (direction IN ('Received', 'Made')),

    contact_id INTEGER REFERENCES contact(contact_id),

    payment_date TEXT NOT NULL,

    amount_cents INTEGER NOT NULL,

    currency TEXT DEFAULT 'PHP',

    exchange_rate REAL DEFAULT 1.0,

    method TEXT CHECK (method IN ('Cash', 'Check', 'Bank Transfer', 'GCash', 'Maya')),

    bank_account_id INTEGER REFERENCES account(account_id),

    entry_id INTEGER REFERENCES journal_entry(entry_id),
    CHECK (typeof(amount_cents) = 'integer')
);
INSERT INTO new_payment (payment_id, direction, contact_id, payment_date, amount_cents, currency, exchange_rate, method, bank_account_id, entry_id)
    SELECT payment_id, direction, contact_id, payment_date, amount_cents, currency, exchange_rate, method, bank_account_id, entry_id FROM payment;
DROP TABLE payment;
ALTER TABLE new_payment RENAME TO payment;

-- payment_allocation
CREATE TABLE new_payment_allocation (

    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,

    payment_id INTEGER REFERENCES payment(payment_id),

    invoice_id INTEGER REFERENCES invoice(invoice_id),

    deferral_id INTEGER,

    amount_applied_cents INTEGER NOT NULL,
    CHECK (typeof(amount_applied_cents) = 'integer')
);
INSERT INTO new_payment_allocation (allocation_id, payment_id, invoice_id, deferral_id, amount_applied_cents)
    SELECT allocation_id, payment_id, invoice_id, deferral_id, amount_applied_cents FROM payment_allocation;
DROP TABLE payment_allocation;
ALTER TABLE new_payment_allocation RENAME TO payment_allocation;

-- poc_snapshot
CREATE TABLE new_poc_snapshot (

	poc_id INTEGER PRIMARY KEY AUTOINCREMENT,

	project_id INTEGER REFERENCES project(project_id),

	period_id INTEGER REFERENCES fiscal_period(period_id),

	as_of_date TEXT NOT NULL,

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

	entry_id INTEGER REFERENCES journal_entry(entry_id),

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
);
INSERT INTO new_progress_billing_application (pay_app_id, contract_id, invoice_id, application_number, period_to_date, work_completed_cents, stored_materials_cents, total_earned_cents, less_retainage_cents, net_earned_cents, less_previous_applied, amount_due_cents, status)
    SELECT pay_app_id, contract_id, invoice_id, application_number, period_to_date, work_completed_cents, stored_materials_cents, total_earned_cents, less_retainage_cents, net_earned_cents, less_previous_applied, amount_due_cents, status FROM progress_billing_application;
DROP TABLE progress_billing_application;
ALTER TABLE new_progress_billing_application RENAME TO progress_billing_application;

-- project
CREATE TABLE new_project (

    project_id            INTEGER PRIMARY KEY AUTOINCREMENT,

    project_number        TEXT NOT NULL UNIQUE, -- e.g., "PRJ-2026-104"

    name                  TEXT NOT NULL,

    contact_id            INTEGER NOT NULL REFERENCES contact(contact_id),

    source_estimate_id    INTEGER REFERENCES estimate(estimate_id),

    assigned_pm_id        INTEGER NOT NULL, 

    original_budget_cents INTEGER DEFAULT 0,

    revised_budget_cents  INTEGER DEFAULT 0, -- Forked dynamically via change logs

    status                TEXT CHECK (status IN ('Mobilization', 'In Progress', 'Suspended', 'Completed', 'Closed Out')) DEFAULT 'Mobilization',

    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (original_budget_cents IS NULL OR typeof(original_budget_cents) = 'integer'),
    CHECK (revised_budget_cents IS NULL OR typeof(revised_budget_cents) = 'integer')
);
INSERT INTO new_project (project_id, project_number, name, contact_id, source_estimate_id, assigned_pm_id, original_budget_cents, revised_budget_cents, status, created_at)
    SELECT project_id, project_number, name, contact_id, source_estimate_id, assigned_pm_id, original_budget_cents, revised_budget_cents, status, created_at FROM project;
DROP TABLE project;
ALTER TABLE new_project RENAME TO project;

-- project_budget
CREATE TABLE new_project_budget (

	budget_id INTEGER PRIMARY KEY AUTOINCREMENT,

	project_id INTEGER REFERENCES project(project_id),

	cost_code_id INTEGER REFERENCES cost_code(cost_code_id),

	estimate_line_id INTEGER REFERENCES estimate_line(line_id),

	co_line_id INTEGER REFERENCES change_order_line(co_line_id),

	budget_cents INTEGER NOT NULL,
    CHECK (typeof(budget_cents) = 'integer')
);
INSERT INTO new_project_budget (budget_id, project_id, cost_code_id, estimate_line_id, co_line_id, budget_cents)
    SELECT budget_id, project_id, cost_code_id, estimate_line_id, co_line_id, budget_cents FROM project_budget;
DROP TABLE project_budget;
ALTER TABLE new_project_budget RENAME TO project_budget;

-- purchase_order_subcontract
CREATE TABLE new_purchase_order_subcontract (

	commitment_id INTEGER PRIMARY KEY AUTOINCREMENT,

	contract_id INTEGER REFERENCES contract(contract_id),

	vendor_id INTEGER REFERENCES contact(contact_id),

	commitment_number TEXT UNIQUE NOT NULL,

	status TEXT CHECK (status IN ('Draft', 'Issued', 'Complete', 'Void')),

	original_amount_cents INTEGER NOT NULL,

	revised_amount_cents INTEGER NOT NULL,

	retainage_pct REAL DEFAULT 0.0,
    CHECK (typeof(original_amount_cents) = 'integer'),
    CHECK (typeof(revised_amount_cents) = 'integer')
);
INSERT INTO new_purchase_order_subcontract (commitment_id, contract_id, vendor_id, commitment_number, status, original_amount_cents, revised_amount_cents, retainage_pct)
    SELECT commitment_id, contract_id, vendor_id, commitment_number, status, original_amount_cents, revised_amount_cents, retainage_pct FROM purchase_order_subcontract;
DROP TABLE purchase_order_subcontract;
ALTER TABLE new_purchase_order_subcontract RENAME TO purchase_order_subcontract;

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
);
INSERT INTO new_saas_subscription (subscription_id, contact_id, plan_tier_name, base_mrr_cents, seat_quantity, per_seat_cost_cents, next_billing_cycle_date, status)
    SELECT subscription_id, contact_id, plan_tier_name, base_mrr_cents, seat_quantity, per_seat_cost_cents, next_billing_cycle_date, status FROM saas_subscription;
DROP TABLE saas_subscription;
ALTER TABLE new_saas_subscription RENAME TO saas_subscription;

-- staged_line
CREATE TABLE new_staged_line (

    stage_line_id INTEGER PRIMARY KEY AUTOINCREMENT,

    stage_id INTEGER REFERENCES staged_transaction(stage_id),

    account_id INTEGER REFERENCES account(account_id),

    project_id INTEGER,

    cost_code_id INTEGER,

    amount_cents INTEGER,

    memo TEXT,
    CHECK (amount_cents IS NULL OR typeof(amount_cents) = 'integer')
);
INSERT INTO new_staged_line (stage_line_id, stage_id, account_id, project_id, cost_code_id, amount_cents, memo)
    SELECT stage_line_id, stage_id, account_id, project_id, cost_code_id, amount_cents, memo FROM staged_line;
DROP TABLE staged_line;
ALTER TABLE new_staged_line RENAME TO staged_line;

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
);
INSERT INTO new_time_entry (time_entry_id, contact_id, project_id, cost_code_id, work_date, hours, wage_cents, burden_cents, source_batch_id, created_at)
    SELECT time_entry_id, contact_id, project_id, cost_code_id, work_date, hours, wage_cents, burden_cents, source_batch_id, created_at FROM time_entry;
DROP TABLE time_entry;
ALTER TABLE new_time_entry RENAME TO time_entry;

-- F6: master-only tables do not belong in a company file.
DROP TABLE IF EXISTS user_company_access;
DROP TABLE IF EXISTS company_registry;
DROP TABLE IF EXISTS app_user;

-- F3/F4/F5: journal triggers.

CREATE TRIGGER journal_entry_no_direct_post
BEFORE INSERT ON journal_entry
WHEN NEW.is_posted = 1
BEGIN
    SELECT RAISE(ABORT, 'Create journal entries as unposted, add balanced lines, then post');
END;

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
          AND substr(NEW.entry_date, 1, 10) BETWEEN start_date AND end_date
    ) THEN RAISE(ABORT, 'Cannot post: the entry date falls in a closed fiscal period') END;
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
END;

-- A posted entry may only be voided (is_void 0 -> 1) with every other column
-- unchanged. A test checks that this list names every journal_entry column.
CREATE TRIGGER journal_entry_lock_posted
BEFORE UPDATE ON journal_entry
WHEN OLD.is_posted = 1
BEGIN
    SELECT CASE WHEN NEW.is_posted IS NOT 1
        THEN RAISE(ABORT, 'Posted journal entries cannot be unposted; post a reversing entry') END;
    SELECT CASE WHEN NOT (
        OLD.is_void = 0 AND NEW.is_void = 1
        AND NEW.entry_id IS OLD.entry_id
        AND NEW.entry_date IS OLD.entry_date
        AND NEW.period_id IS OLD.period_id
        AND NEW.reference IS OLD.reference
        AND NEW.description IS OLD.description
        AND NEW.source IS OLD.source
        AND NEW.reverses_entry_id IS OLD.reverses_entry_id
        AND NEW.created_by IS OLD.created_by
        AND NEW.created_at IS OLD.created_at
    ) THEN RAISE(ABORT, 'Posted journal entries cannot be changed; only voiding is allowed') END;
END;

CREATE TRIGGER journal_entry_lock_delete_posted
BEFORE DELETE ON journal_entry
WHEN OLD.is_posted = 1
BEGIN
    SELECT RAISE(ABORT, 'Posted journal entries cannot be deleted; post a reversing entry');
END;

CREATE TRIGGER journal_line_lock_insert_posted
BEFORE INSERT ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id = NEW.entry_id AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER journal_line_lock_update_posted
BEFORE UPDATE ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id IN (OLD.entry_id, NEW.entry_id) AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER journal_line_lock_delete_posted
BEFORE DELETE ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id = OLD.entry_id AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;
