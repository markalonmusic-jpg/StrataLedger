-- Generated from accounting_librebase.db; reviewed migration 1.

CREATE TABLE IF NOT EXISTS account (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type_id INTEGER REFERENCES account_type(type_id),
    parent_id INTEGER REFERENCES account(account_id),
    is_postable INTEGER DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    is_deferral_account INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS account_type (
    type_id INTEGER PRIMARY KEY,
    name TEXT CHECK (name IN ('Asset', 'Liability', 'Equity', 'Revenue', 'Expense')),
    normal_balance TEXT CHECK (normal_balance IN ('D', 'C'))
);

CREATE TABLE IF NOT EXISTS app_user (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT CHECK (role IN ('Master', 'Admin', 'Accountant', 'HR', 'AP', 'AR', 'Sales', 'Marketing', 'PM', 'Warehouse')),
    job_title TEXT NOT NULL DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES app_user(user_id),
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT CHECK (action IN ('Insert', 'Update', 'Delete', 'Post', 'Approve', 'Void')),
    old_value TEXT,
    new_value TEXT,
    software_version_tag TEXT,
    terminal_id TEXT
);

CREATE TABLE IF NOT EXISTS bank_reconciliation (
    recon_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES account(account_id),
    statement_date TEXT NOT NULL,
    statement_balance_cents INTEGER NOT NULL,
    is_complete INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS change_order (
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
);

CREATE TABLE IF NOT EXISTS change_order_line (
	co_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
	co_id INTEGER REFERENCES change_order(co_id),
	cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
	sov_line_id INTEGER REFERENCES contract_line(sov_line_id),
	description TEXT,
	revenue_change_cents INTEGER,
	cost_change_cents INTEGER
);

CREATE TABLE IF NOT EXISTS company_profile (
                company_id INTEGER PRIMARY KEY AUTOINCREMENT,
                legal_name TEXT,
                company_code TEXT,
                fiscal_year_end TEXT,
                currency TEXT DEFAULT 'USD'
            );

CREATE TABLE IF NOT EXISTS company_registry (
    company_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code        TEXT NOT NULL UNIQUE,      
    legal_name          TEXT NOT NULL,
    database_file_path  TEXT NOT NULL,             
    parent_company_id   INTEGER DEFAULT NULL,      -- 🌲 PARENT NODE LINK: Maps parent corporate chains
    is_active           INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_company_id) REFERENCES company_registry(company_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS "company_settings" (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    company_name TEXT NOT NULL,
                    fiscal_year_start TEXT NOT NULL, 
                    base_currency TEXT DEFAULT 'USD', 
                    tax_id TEXT, 
                    branch_code TEXT DEFAULT '00000',
                    tax_type TEXT, 
                    cas_permit_number TEXT,
                    next_invoice_number INTEGER DEFAULT 1000,
                    contract_revenue_acct_id INTEGER,
                    contract_cost_acct_id INTEGER,
                    underbilled_acct_id INTEGER,
                    overbilled_acct_id INTEGER,
                    payroll_clearing_acct_id INTEGER
                );

CREATE TABLE IF NOT EXISTS contact (
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
, mailing_street TEXT, mailing_city TEXT, mailing_state TEXT, mailing_zip TEXT);

CREATE TABLE IF NOT EXISTS contract (
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
	notes TEXT
);

CREATE TABLE IF NOT EXISTS contract_line (
	sov_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
	contract_id INTEGER REFERENCES contract(contract_id),
	line_number TEXT,
	description TEXT,
	cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
	scheduled_value_cents INTEGER,
	sort_order INTEGER,
	change_order_id INTEGER
);

CREATE TABLE IF NOT EXISTS cost_code (
    cost_code_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    code             TEXT NOT NULL UNIQUE, -- e.g., "03-300" (Concrete), "06-100" (Carpentry)
    name             TEXT NOT NULL, 
    cost_type_label  TEXT NOT NULL, -- "Cement", "Lumber", "SaaS User Licensing"
    account_id       INTEGER -- Parent General Ledger Account cross-reference link
);

CREATE TABLE IF NOT EXISTS crm_activity_stream (
    activity_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id        INTEGER NOT NULL REFERENCES contact(contact_id) ON DELETE CASCADE,
    project_id        INTEGER REFERENCES project(project_id) ON DELETE CASCADE,
    author_user_id    INTEGER NOT NULL REFERENCES app_user(user_id),
    category          TEXT CHECK (category IN ('Sales Call', 'Email Exchange', 'Field Site Note', 'Active Project Issue')),
    severity          TEXT CHECK (severity IN ('Low', 'Medium', 'High')) DEFAULT 'Low',
    subject_header    TEXT NOT NULL,
    body_content      TEXT NOT NULL,
    is_resolved       INTEGER DEFAULT 0 CHECK (is_resolved IN (0, 1)), 
    opened_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at       DATETIME, 
    resolution_seconds INTEGER DEFAULT NULL 
);

CREATE TABLE IF NOT EXISTS crm_approval_instance (
    instance_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id             INTEGER NOT NULL REFERENCES crm_approval_rule(rule_id),
    target_type         TEXT CHECK (target_type IN ('Contract', 'Estimate', 'Change Order')),
    target_record_id    INTEGER NOT NULL, 
    assigned_user_id    INTEGER REFERENCES app_user(user_id),
    status              TEXT CHECK (status IN ('Pending', 'Approved', 'Rejected')) DEFAULT 'Pending',
    actioned_at         DATETIME,
    memo_comments       TEXT,
    security_hash       TEXT 
);

CREATE TABLE IF NOT EXISTS crm_approval_rule (
    rule_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id         INTEGER REFERENCES crm_pipeline(pipeline_id),
    rule_name           TEXT NOT NULL, 
    min_value_cents     INTEGER DEFAULT 0,
    max_value_cents     INTEGER DEFAULT 999999999,
    required_job_title  TEXT NOT NULL, -- Rules map directly to staff job titles
    sequence_step       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS crm_change_line (
    change_line_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    change_id                 INTEGER NOT NULL REFERENCES crm_change_order(change_id) ON DELETE CASCADE,
    cost_code_id              INTEGER NOT NULL REFERENCES cost_code(cost_code_id), 
    quantity_change           REAL NOT NULL, 
    unit_cost_cents           INTEGER NOT NULL,
    extended_price_cents      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS crm_change_order (
    change_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id           INTEGER NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    authorizing_pm_id    INTEGER NOT NULL REFERENCES app_user(user_id),
    change_order_number  TEXT NOT NULL UNIQUE, -- e.g., "CO-01-PRJ-104"
    status               TEXT CHECK (status IN ('Draft', 'Submitted', 'Executed', 'Rejected')) DEFAULT 'Draft',
    reason_memo          TEXT,
    signed_at            DATETIME
);

CREATE TABLE IF NOT EXISTS crm_opportunity (
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
    created_by             INTEGER REFERENCES app_user(user_id),
    created_at             DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm_pipeline (
    pipeline_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL, -- e.g., "SaaS Sales Cycle" or "Construction Bids"
    description      TEXT
);

CREATE TABLE IF NOT EXISTS crm_stage (
    stage_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id      INTEGER NOT NULL REFERENCES crm_pipeline(pipeline_id) ON DELETE CASCADE,
    name             TEXT NOT NULL, -- e.g., "Bid Submitted", "Trial / POC"
    sequence_order   INTEGER NOT NULL,
    is_closed_won    INTEGER DEFAULT 0 CHECK (is_closed_won IN (0, 1)),
    is_closed_lost   INTEGER DEFAULT 0 CHECK (is_closed_lost IN (0, 1)),
    ai_trigger_event TEXT, -- Automation hook targets for your AI Assistant
    UNIQUE (pipeline_id, sequence_order)
);

CREATE TABLE IF NOT EXISTS crm_stage_history (
    history_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id   INTEGER NOT NULL REFERENCES crm_opportunity(opportunity_id) ON DELETE CASCADE,
    from_stage_id    INTEGER REFERENCES crm_stage(stage_id),
    to_stage_id      INTEGER NOT NULL REFERENCES crm_stage(stage_id),
    changed_by       INTEGER REFERENCES app_user(user_id),
    changed_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    days_in_stage    INTEGER DEFAULT 0,
    memo             TEXT
);

CREATE TABLE IF NOT EXISTS deferral (
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
	memo TEXT
);

CREATE TABLE IF NOT EXISTS deferral_schedule_line (
	schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
	deferral_id INTEGER REFERENCES deferral(deferral_id),
	period_id INTEGER REFERENCES fiscal_period(period_id),
	amort_date TEXT NOT NULL,
	amount_cents INTEGER NOT NULL,
	status TEXT CHECK (status IN ('Scheduled', 'Posted', 'Skipped')),
	entry_id INTEGER REFERENCES journal_entry(entry_id),
	UNIQUE (deferral_id, period_id)
);

CREATE TABLE IF NOT EXISTS dimension_type (
    dimension_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE, -- e.g., "Profit Center"
    description         TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dimension_value (
    dimension_value_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension_type_id INTEGER NOT NULL REFERENCES dimension_type(dimension_type_id) ON DELETE CASCADE,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_value_id INTEGER DEFAULT NULL,
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_value_id) REFERENCES dimension_value(dimension_value_id) ON DELETE SET NULL,
    UNIQUE (dimension_value_id, dimension_type_id)
);

CREATE TABLE IF NOT EXISTS estimate (
    estimate_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_number       TEXT NOT NULL UNIQUE, -- e.g., "EST-2026-001"
    name                  TEXT NOT NULL,
    contact_id            INTEGER NOT NULL REFERENCES contact(contact_id),
    source_opportunity_id INTEGER REFERENCES crm_opportunity(opportunity_id),
    assigned_pm_id        INTEGER REFERENCES app_user(user_id), 
    total_cost_cents      INTEGER DEFAULT 0,
    total_price_cents     INTEGER DEFAULT 0,
    status                TEXT CHECK (status IN ('Draft', 'Submitted', 'Approved', 'Won', 'Lost')) DEFAULT 'Draft',
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS estimate_line (
    line_id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_id                   INTEGER NOT NULL REFERENCES estimate(estimate_id) ON DELETE CASCADE,
    cost_code_id                  INTEGER NOT NULL REFERENCES cost_code(cost_code_id),
    quantity                      REAL NOT NULL CHECK (quantity > 0),
    unit_of_measure               TEXT NOT NULL, -- "Bags", "Board Feet", etc.
    estimated_unit_cost_cents     INTEGER NOT NULL, 
    estimated_extended_cost_cents INTEGER NOT NULL, 
    price_to_customer_cents       INTEGER NOT NULL  
);

CREATE TABLE IF NOT EXISTS file_attachment (
    file_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name        TEXT NOT NULL,
    file_path        TEXT NOT NULL, -- Stored localized directory reference strings
    file_size_kb     INTEGER,
    target_type      TEXT CHECK (target_type IN ('Project_Evidence', 'Change_Evidence', 'Invoice_Source')),
    target_record_id INTEGER NOT NULL, 
    uploaded_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fiscal_period (
    period_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    is_closed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_batch (
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
    entry_id INTEGER REFERENCES journal_entry(entry_id)
);

CREATE TABLE IF NOT EXISTS import_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES import_source(source_id),
    external_kind TEXT CHECK (external_kind IN ('Category', 'Department', 'Job/Project', 'Employee', 'Vendor')),
    external_value TEXT,
    account_id INTEGER REFERENCES account(account_id),
    project_id INTEGER,
    cost_code_id INTEGER,
    contact_id INTEGER REFERENCES contact(contact_id)
);

CREATE TABLE IF NOT EXISTS import_source (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT CHECK (name IN ('Gusto', 'Rippling', 'Ramp', 'Manual Upload')),
    source_type TEXT CHECK (source_type IN ('Payroll', 'Spend'))
);

CREATE TABLE IF NOT EXISTS invoice (
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
    UNIQUE (invoice_type, contact_id, invoice_number)
);

CREATE TABLE IF NOT EXISTS invoice_line (
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
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invoice_line_dimension (
    line_id INTEGER NOT NULL REFERENCES invoice_line(line_id) ON DELETE CASCADE,
    dimension_type_id INTEGER NOT NULL,
    dimension_value_id INTEGER NOT NULL,
    PRIMARY KEY (line_id, dimension_type_id),
    FOREIGN KEY (dimension_value_id, dimension_type_id)
        REFERENCES dimension_value(dimension_value_id, dimension_type_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS journal_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    period_id INTEGER REFERENCES fiscal_period(period_id),
    reference TEXT,
    description TEXT,
    source TEXT CHECK (source IN ('Manual', 'Invoice', 'Bill', 'Payment', 'Adjustment', 'Payroll', 'Import', 'Deferral', 'Completion')),
    is_posted INTEGER DEFAULT 0,
    is_void INTEGER DEFAULT 0,
    reverses_entry_id INTEGER REFERENCES journal_entry(entry_id),
    created_by INTEGER REFERENCES app_user(user_id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journal_line (
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
    CHECK (debit_cents = 0 OR credit_cents = 0)
);

CREATE TABLE IF NOT EXISTS payment (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT CHECK (direction IN ('Received', 'Made')),
    contact_id INTEGER REFERENCES contact(contact_id),
    payment_date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'PHP',
    exchange_rate REAL DEFAULT 1.0,
    method TEXT CHECK (method IN ('Cash', 'Check', 'Bank Transfer', 'GCash', 'Maya')),
    bank_account_id INTEGER REFERENCES account(account_id),
    entry_id INTEGER REFERENCES journal_entry(entry_id)
);

CREATE TABLE IF NOT EXISTS payment_allocation (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER REFERENCES payment(payment_id),
    invoice_id INTEGER REFERENCES invoice(invoice_id),
    deferral_id INTEGER,
    amount_applied_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS poc_snapshot (
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
	UNIQUE (project_id, period_id)
);

CREATE TABLE IF NOT EXISTS progress_billing_application (
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
	status TEXT CHECK (status IN ('Draft', 'Submitted', 'Approved', 'Paid'))
);

CREATE TABLE IF NOT EXISTS project (
    project_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_number        TEXT NOT NULL UNIQUE, -- e.g., "PRJ-2026-104"
    name                  TEXT NOT NULL,
    contact_id            INTEGER NOT NULL REFERENCES contact(contact_id),
    source_estimate_id    INTEGER REFERENCES estimate(estimate_id),
    assigned_pm_id        INTEGER NOT NULL REFERENCES app_user(user_id), 
    original_budget_cents INTEGER DEFAULT 0,
    revised_budget_cents  INTEGER DEFAULT 0, -- Forked dynamically via change logs
    status                TEXT CHECK (status IN ('Mobilization', 'In Progress', 'Suspended', 'Completed', 'Closed Out')) DEFAULT 'Mobilization',
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_budget (
	budget_id INTEGER PRIMARY KEY AUTOINCREMENT,
	project_id INTEGER REFERENCES project(project_id),
	cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
	estimate_line_id INTEGER REFERENCES estimate_line(estimate_line_id),
	co_line_id INTEGER REFERENCES change_order_line(co_line_id),
	budget_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_order_subcontract (
	commitment_id INTEGER PRIMARY KEY AUTOINCREMENT,
	contract_id INTEGER REFERENCES contract(contract_id),
	vendor_id INTEGER REFERENCES contact(contact_id),
	commitment_number TEXT UNIQUE NOT NULL,
	status TEXT CHECK (status IN ('Draft', 'Issued', 'Complete', 'Void')),
	original_amount_cents INTEGER NOT NULL,
	revised_amount_cents INTEGER NOT NULL,
	retainage_pct REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS saas_subscription (
    subscription_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id              INTEGER NOT NULL UNIQUE REFERENCES contact(contact_id) ON DELETE CASCADE,
    plan_tier_name          TEXT NOT NULL, 
    base_mrr_cents          INTEGER DEFAULT 0 CHECK (base_mrr_cents >= 0), 
    seat_quantity           INTEGER DEFAULT 1,
    per_seat_cost_cents     INTEGER DEFAULT 0,
    next_billing_cycle_date TEXT NOT NULL, 
    status                  TEXT CHECK (status IN ('Trial', 'Active', 'Past_Due', 'Contracted', 'Churned')) DEFAULT 'Trial'
);

CREATE TABLE IF NOT EXISTS saas_usage_telemetry (
    telemetry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id  INTEGER NOT NULL REFERENCES saas_subscription(subscription_id) ON DELETE CASCADE,
    metric_type      TEXT CHECK (metric_type IN ('API_Calls', 'Storage_GB', 'AI_Tokens_Consumed')),
    units_used       INTEGER NOT NULL CHECK (units_used > 0),
    logged_at_date   TEXT NOT NULL 
);

CREATE TABLE IF NOT EXISTS staged_line (
    stage_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage_id INTEGER REFERENCES staged_transaction(stage_id),
    account_id INTEGER REFERENCES account(account_id),
    project_id INTEGER,
    cost_code_id INTEGER,
    amount_cents INTEGER,
    memo TEXT
);

CREATE TABLE IF NOT EXISTS staged_transaction (
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
    approved_by INTEGER REFERENCES app_user(user_id),
    approved_at DATETIME,
    invoice_id INTEGER REFERENCES invoice(invoice_id),
    payment_id INTEGER REFERENCES payment(payment_id),
    entry_id INTEGER REFERENCES journal_entry(entry_id)
);

CREATE TABLE IF NOT EXISTS subscription (
    subscription_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contact(contact_id),
    plan_name TEXT NOT NULL,
    mrr_cents INTEGER DEFAULT 0,
    arr_cents INTEGER DEFAULT 0,
    status TEXT CHECK (status IN ('Active', 'Paused', 'Churned')),
    start_date TEXT NOT NULL,
    end_date TEXT
);

CREATE TABLE IF NOT EXISTS tax_rate (
    tax_rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rate REAL NOT NULL,
    tax_account_id INTEGER REFERENCES account(account_id)
);

CREATE TABLE IF NOT EXISTS user_company_access (
    user_id    INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES company_registry(company_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, company_id)
);

CREATE TRIGGER IF NOT EXISTS dimension_value_validate_insert
BEFORE INSERT ON dimension_value
BEGIN
    SELECT CASE WHEN NEW.parent_value_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM dimension_value
        WHERE dimension_value_id = NEW.parent_value_id
          AND dimension_type_id = NEW.dimension_type_id
    ) THEN RAISE(ABORT, 'Parent dimension value must have the same dimension type') END;
    SELECT CASE WHEN NEW.parent_value_id IS NOT NULL AND (WITH RECURSIVE ancestors(value_id, parent_value_id, depth) AS (
    SELECT dimension_value_id, parent_value_id, 1 FROM dimension_value
    WHERE dimension_value_id = NEW.parent_value_id
    UNION ALL
    SELECT parent.dimension_value_id, parent.parent_value_id, ancestors.depth + 1
    FROM dimension_value AS parent JOIN ancestors
      ON parent.dimension_value_id = ancestors.parent_value_id
    WHERE ancestors.depth < __MAX_DIMENSION_DEPTH__
)
SELECT COALESCE(MAX(depth), 0) + 1 FROM ancestors) > __MAX_DIMENSION_DEPTH__
        THEN RAISE(ABORT, 'Dimension depth limit exceeded') END;
END;

CREATE TRIGGER IF NOT EXISTS dimension_value_validate_update
BEFORE UPDATE OF parent_value_id, dimension_type_id ON dimension_value
BEGIN
    SELECT CASE WHEN NEW.parent_value_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM dimension_value
        WHERE dimension_value_id = NEW.parent_value_id
          AND dimension_type_id = NEW.dimension_type_id
    ) THEN RAISE(ABORT, 'Parent dimension value must have the same dimension type') END;
    SELECT CASE WHEN NEW.parent_value_id = NEW.dimension_value_id
        THEN RAISE(ABORT, 'A dimension value cannot parent itself') END;
    SELECT CASE WHEN NEW.parent_value_id IS NOT NULL AND EXISTS (
        WITH RECURSIVE ancestors(value_id, parent_value_id) AS (
            SELECT dimension_value_id, parent_value_id FROM dimension_value
            WHERE dimension_value_id = NEW.parent_value_id
            UNION ALL
            SELECT parent.dimension_value_id, parent.parent_value_id
            FROM dimension_value AS parent JOIN ancestors
              ON parent.dimension_value_id = ancestors.parent_value_id
        ) SELECT 1 FROM ancestors WHERE value_id = NEW.dimension_value_id
    ) THEN RAISE(ABORT, 'Dimension hierarchy cannot contain a cycle') END;
    SELECT CASE WHEN (WITH RECURSIVE ancestors(value_id, parent_value_id, depth) AS (
    SELECT dimension_value_id, parent_value_id, 1 FROM dimension_value
    WHERE dimension_value_id = NEW.parent_value_id
    UNION ALL
    SELECT parent.dimension_value_id, parent.parent_value_id, ancestors.depth + 1
    FROM dimension_value AS parent JOIN ancestors
      ON parent.dimension_value_id = ancestors.parent_value_id
    WHERE ancestors.depth < __MAX_DIMENSION_DEPTH__
)
SELECT COALESCE(MAX(depth), 0) + 1 FROM ancestors) + (WITH RECURSIVE descendants(value_id, depth, path) AS (
    SELECT dimension_value_id, 1, printf('/%d/', dimension_value_id)
    FROM dimension_value WHERE parent_value_id = NEW.dimension_value_id
    UNION ALL
    SELECT child.dimension_value_id, descendants.depth + 1,
           descendants.path || child.dimension_value_id || '/'
    FROM dimension_value AS child JOIN descendants
      ON child.parent_value_id = descendants.value_id
    WHERE instr(descendants.path, printf('/%d/', child.dimension_value_id)) = 0
      AND descendants.depth < __MAX_DIMENSION_DEPTH__
)
SELECT COALESCE(MAX(depth), 0) FROM descendants) > __MAX_DIMENSION_DEPTH__
        THEN RAISE(ABORT, 'Dimension depth limit exceeded') END;
END;
CREATE TRIGGER IF NOT EXISTS journal_entry_require_balance_on_post
BEFORE UPDATE OF is_posted ON journal_entry
WHEN NEW.is_posted = 1 AND OLD.is_posted = 0
BEGIN
    SELECT CASE WHEN
        (SELECT COUNT(*) FROM journal_line WHERE entry_id = NEW.entry_id) = 0
        OR (SELECT COALESCE(SUM(debit_cents), 0) FROM journal_line WHERE entry_id = NEW.entry_id)
           != (SELECT COALESCE(SUM(credit_cents), 0) FROM journal_line WHERE entry_id = NEW.entry_id)
    THEN RAISE(ABORT, 'Journal entry must balance before posting') END;
END;

CREATE TRIGGER IF NOT EXISTS journal_entry_no_direct_post
BEFORE INSERT ON journal_entry
WHEN NEW.is_posted = 1
BEGIN
    SELECT RAISE(ABORT, 'Create journal entries as unposted, add balanced lines, then post');
END;

CREATE TRIGGER IF NOT EXISTS journal_line_lock_insert_posted
BEFORE INSERT ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id = NEW.entry_id AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER IF NOT EXISTS journal_line_lock_update_posted
BEFORE UPDATE ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id IN (OLD.entry_id, NEW.entry_id) AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

CREATE TRIGGER IF NOT EXISTS journal_line_lock_delete_posted
BEFORE DELETE ON journal_line
WHEN EXISTS (SELECT 1 FROM journal_entry WHERE entry_id = OLD.entry_id AND is_posted = 1)
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;
CREATE TABLE IF NOT EXISTS time_entry (
    time_entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contact(contact_id),
    project_id INTEGER REFERENCES project(project_id),
    cost_code_id INTEGER REFERENCES cost_code(cost_code_id),
    work_date TEXT NOT NULL,
    hours REAL NOT NULL,
    wage_cents INTEGER NOT NULL,
    burden_cents INTEGER NOT NULL,
    source_batch_id INTEGER REFERENCES import_batch(batch_id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
