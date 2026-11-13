-- StrataLedger company baseline schema, version 1.
--
-- One baseline instead of a migration chain: nothing is released and no real
-- data exists. Until the first release, schema changes edit this file directly
-- and development databases are rebuilt from it with
-- scripts/create_fresh_databases.py (CLAUDE.md section 5). At the first
-- release this file is frozen; later changes are numbered 002 and up.
--
-- Generated from the migration chain that preceded it, kept in
-- archive/migrations_chain_v5/ (git tag schema-chain-v5). The reasons behind
-- the controls are in docs/controls_audit.md. The runner records a SHA-256 of
-- this file in each database and refuses to open a file built from different
-- text (modules/database.py).


-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE account_type (

    type_id INTEGER PRIMARY KEY,

    name TEXT CHECK (name IN ('Asset', 'Liability', 'Equity', 'Revenue', 'Expense')),

    normal_balance TEXT CHECK (normal_balance IN ('D', 'C'))

);

CREATE TABLE cost_code (

    cost_code_id     INTEGER PRIMARY KEY AUTOINCREMENT,

    code             TEXT NOT NULL UNIQUE, -- e.g., "03-300" (Concrete), "06-100" (Carpentry)

    name             TEXT NOT NULL, 

    cost_type_label  TEXT NOT NULL, -- "Cement", "Lumber", "SaaS User Licensing"

    account_id       INTEGER -- Parent General Ledger Account cross-reference link

);

CREATE TABLE dimension_type (

    dimension_type_id   INTEGER PRIMARY KEY AUTOINCREMENT,

    name                TEXT NOT NULL UNIQUE, -- e.g., "Profit Center"

    description         TEXT,

    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE dimension_value (
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

CREATE TABLE file_attachment (

    file_id          INTEGER PRIMARY KEY AUTOINCREMENT,

    file_name        TEXT NOT NULL,

    file_path        TEXT NOT NULL, -- Stored localized directory reference strings

    file_size_kb     INTEGER,

    target_type      TEXT CHECK (target_type IN ('Project_Evidence', 'Change_Evidence', 'Invoice_Source')),

    target_record_id INTEGER NOT NULL, 

    uploaded_at      DATETIME DEFAULT CURRENT_TIMESTAMP

);

CREATE TABLE import_mapping (

    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_id INTEGER REFERENCES import_source(source_id),

    external_kind TEXT CHECK (external_kind IN ('Category', 'Department', 'Job/Project', 'Employee', 'Vendor')),

    external_value TEXT,

    account_id INTEGER REFERENCES account(account_id),

    project_id INTEGER,

    cost_code_id INTEGER,

    contact_id INTEGER REFERENCES contact(contact_id)

);

CREATE TABLE import_source (

    source_id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT CHECK (name IN ('Gusto', 'Rippling', 'Ramp', 'Manual Upload')),

    source_type TEXT CHECK (source_type IN ('Payroll', 'Spend'))

);

CREATE TABLE invoice_line_dimension (
    line_id INTEGER NOT NULL REFERENCES invoice_line(line_id) ON DELETE CASCADE,
    dimension_type_id INTEGER NOT NULL,
    dimension_value_id INTEGER NOT NULL,
    PRIMARY KEY (line_id, dimension_type_id),
    FOREIGN KEY (dimension_value_id, dimension_type_id)
        REFERENCES dimension_value(dimension_value_id, dimension_type_id)
        ON DELETE RESTRICT
);

CREATE TABLE tax_rate (

    tax_rate_id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL,

    rate REAL NOT NULL,

    tax_account_id INTEGER REFERENCES account(account_id)

);

CREATE TABLE "audit_log" (

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

CREATE TABLE "change_order_line" (

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

CREATE TABLE "contract_line" (

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

CREATE TABLE "estimate" (

    estimate_id           INTEGER PRIMARY KEY AUTOINCREMENT,

    estimate_number       TEXT NOT NULL UNIQUE, -- e.g., "EST-2026-001"

    name                  TEXT NOT NULL,

    contact_id            INTEGER NOT NULL REFERENCES contact(contact_id),

    assigned_pm_id        INTEGER, 

    total_cost_cents      INTEGER DEFAULT 0,

    total_price_cents     INTEGER DEFAULT 0,

    status                TEXT CHECK (status IN ('Draft', 'Submitted', 'Approved', 'Won', 'Lost')) DEFAULT 'Draft',

    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (total_cost_cents IS NULL OR typeof(total_cost_cents) = 'integer'),
    CHECK (total_price_cents IS NULL OR typeof(total_price_cents) = 'integer')
);

CREATE TABLE "estimate_line" (

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

CREATE TABLE "project" (

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

CREATE TABLE "project_budget" (

	budget_id INTEGER PRIMARY KEY AUTOINCREMENT,

	project_id INTEGER REFERENCES project(project_id),

	cost_code_id INTEGER REFERENCES cost_code(cost_code_id),

	estimate_line_id INTEGER REFERENCES estimate_line(line_id),

	co_line_id INTEGER REFERENCES change_order_line(co_line_id),

	budget_cents INTEGER NOT NULL,
    CHECK (typeof(budget_cents) = 'integer')
);

CREATE TABLE "staged_line" (

    stage_line_id INTEGER PRIMARY KEY AUTOINCREMENT,

    stage_id INTEGER REFERENCES staged_transaction(stage_id),

    account_id INTEGER REFERENCES account(account_id),

    project_id INTEGER,

    cost_code_id INTEGER,

    amount_cents INTEGER,

    memo TEXT,
    CHECK (amount_cents IS NULL OR typeof(amount_cents) = 'integer')
);

CREATE TABLE "payment_allocation" (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER REFERENCES payment(payment_id),
    invoice_id INTEGER REFERENCES invoice(invoice_id),
    deferral_id INTEGER,
    amount_applied_cents INTEGER NOT NULL,
    CHECK (typeof(amount_applied_cents) = 'integer'),
    CONSTRAINT allocation_amount_positive CHECK (amount_applied_cents > 0),
    -- 2.5: an allocation names exactly one document, an invoice or a deferral.
    CONSTRAINT allocation_one_target CHECK ((invoice_id IS NULL) <> (deferral_id IS NULL))
);

-- Who is writing. One row; the service layer sets it inside each write
-- transaction (modules/services/tx.py) and clears it before commit. The audit
-- triggers read it, so every audit row names the user. The row cannot be
-- deleted, so audit rows are always written.

CREATE TABLE audit_context (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id INTEGER,
    terminal_id TEXT,
    software_version_tag TEXT,
    set_at DATETIME
);

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

CREATE TABLE entry_number_sequence (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_number INTEGER NOT NULL DEFAULT 0 CHECK (typeof(last_number) = 'integer' AND last_number >= 0)
);

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

CREATE TABLE "fiscal_period" (
    period_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL CHECK (start_date IS date(start_date)),
    end_date TEXT NOT NULL CHECK (end_date IS date(end_date)),
    is_closed INTEGER NOT NULL DEFAULT 0 CHECK (is_closed IN (0, 1)),
    closed_at DATETIME,
    closed_by INTEGER,
    -- 2.4b: the fiscal year, the period number (1-12 months, 13 audit and 14 tax adjustments, A1, S4)
    fiscal_year_id INTEGER REFERENCES fiscal_year(year_id),
    period_number INTEGER CHECK (period_number IS NULL OR period_number BETWEEN 1 AND 14),
    is_adjustment_period INTEGER NOT NULL DEFAULT 0 CHECK (is_adjustment_period IN (0, 1)),
    CHECK (start_date <= end_date),
    CHECK ((is_adjustment_period = 1) = (COALESCE(period_number, 0) >= 13)),
    UNIQUE (fiscal_year_id, period_number)
);

-- 2.4b: fiscal years, named by the calendar year they end in (S2: Jul 2026 - Jun 2027 = FY2027).
-- Year-end locks the year; there are no closing entries (B1).
CREATE TABLE fiscal_year (
    year_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK (name GLOB 'FY[0-9][0-9][0-9][0-9]'),
    start_date TEXT NOT NULL UNIQUE CHECK (start_date IS date(start_date)),
    end_date TEXT NOT NULL UNIQUE CHECK (end_date IS date(end_date)),
    is_year_closed INTEGER NOT NULL DEFAULT 0 CHECK (is_year_closed IN (0, 1)),
    closed_at TEXT,
    closed_by INTEGER,
    CHECK (start_date < end_date),
    CHECK (is_year_closed = 0 OR (closed_at IS NOT NULL AND closed_by IS NOT NULL))
);

-- Every close and reopen of a period or a year (L7). Append-only.
CREATE TABLE period_status_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER REFERENCES fiscal_period(period_id),
    year_id INTEGER REFERENCES fiscal_year(year_id),
    action TEXT NOT NULL CHECK (action IN ('Close', 'Reopen', 'Year close', 'Year reopen')),
    via TEXT NOT NULL CHECK (via IN ('Period close', 'Books closed through', 'Year close', 'Year reopen')),
    reason TEXT,
    user_id INTEGER NOT NULL,
    acted_at TEXT NOT NULL,
    CHECK (period_id IS NOT NULL OR year_id IS NOT NULL),
    CHECK (action NOT IN ('Reopen', 'Year reopen') OR (reason IS NOT NULL AND length(trim(reason)) > 0))
);

-- Period-close checks (L2): each is a warning by default and can be made a hard block in Controls.
CREATE TABLE period_close_check (
    check_code TEXT PRIMARY KEY CHECK (check_code IN ('draft_entries', 'earlier_period_open', 'pending_approvals', 'control_overrides', 'ledger_integrity')),
    mode TEXT NOT NULL DEFAULT 'warn' CHECK (mode IN ('warn', 'block'))
);

CREATE TABLE "journal_entry" (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL CHECK (entry_date IS date(entry_date)),
    period_id INTEGER NOT NULL REFERENCES fiscal_period(period_id),
    reference TEXT,
    description TEXT,
    source TEXT CHECK (source IN ('Manual', 'Invoice', 'Bill', 'Payment', 'Adjustment', 'Payroll', 'Import', 'Deferral', 'Completion', 'Conversion')),
    is_posted INTEGER NOT NULL DEFAULT 0 CHECK (is_posted IN (0, 1)),
    is_void INTEGER NOT NULL DEFAULT 0 CHECK (is_void IN (0, 1)),
    reverses_entry_id INTEGER REFERENCES journal_entry(entry_id),
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reversal_reason TEXT CHECK (reversal_reason IN ('Void', 'Accrual reversal', 'Correction')),
    entry_number INTEGER UNIQUE CHECK (entry_number IS NULL OR entry_number > 0),
    posted_by INTEGER,
    posted_at DATETIME,
    approved_by INTEGER,
    approved_at DATETIME,
    origin TEXT NOT NULL DEFAULT 'Human' CHECK (origin IN ('Human', 'Agent', 'Import', 'System')),
    -- 2.5 (L5): the date the system posts this entry's Accrual reversal; never on a reversal itself.
    auto_reverse_date TEXT CHECK (auto_reverse_date IS date(auto_reverse_date) AND auto_reverse_date > entry_date),
    -- 2.5: why a Void or Correction was posted (reversal_reason is only the category).
    reversal_note TEXT,
    -- 2.5 step 1b: the tamper-evident chain (docs/audit_readiness_design.md section 2). Set only when posting,
    -- computed by the service; the schema checks shape and locks it, never the HMAC or the previous link.
    chain_version INTEGER CHECK (chain_version IS NULL OR chain_version = 1),
    chain_key_id INTEGER REFERENCES ledger_chain_key(key_id),
    chain_prev_hash TEXT CHECK (chain_prev_hash IS NULL OR (length(chain_prev_hash) = 64 AND chain_prev_hash NOT GLOB '*[^0-9a-f]*')),
    chain_hash TEXT CHECK (chain_hash IS NULL OR (length(chain_hash) = 64 AND chain_hash NOT GLOB '*[^0-9a-f]*')),
    CHECK (is_posted = 1 OR (chain_version IS NULL AND chain_key_id IS NULL AND chain_prev_hash IS NULL
                             AND chain_hash IS NULL)),
    CHECK (is_posted = 0 OR (chain_version IS NOT NULL AND chain_key_id IS NOT NULL AND chain_prev_hash IS NOT NULL
                             AND chain_hash IS NOT NULL)),
    CHECK ((reverses_entry_id IS NULL) = (reversal_reason IS NULL)),
    CHECK (auto_reverse_date IS NULL OR reverses_entry_id IS NULL),
    CHECK (reversal_note IS NULL OR reverses_entry_id IS NOT NULL),
    CHECK (reversal_reason IS NULL OR reversal_reason = 'Accrual reversal'
           OR length(trim(COALESCE(reversal_note, ''))) > 0),
    CHECK (is_posted = 1 OR entry_number IS NULL),
    CHECK ((approved_by IS NULL) = (approved_at IS NULL))
);

CREATE TABLE "journal_line" (
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
    -- 2.5 (A5): a manual line to a controlled account, allowed by allow_manual_control_je and flagged for close review.
    is_control_override INTEGER NOT NULL DEFAULT 0 CHECK (is_control_override IN (0, 1)),
    -- 2.5 (L8): the one-cent balancing line of an imported or converted entry.
    is_rounding_adjustment INTEGER NOT NULL DEFAULT 0 CHECK (is_rounding_adjustment IN (0, 1)),
    CHECK (debit_cents = 0 OR credit_cents = 0),
    CHECK (debit_cents IS NULL OR typeof(debit_cents) = 'integer'),
    CHECK (credit_cents IS NULL OR typeof(credit_cents) = 'integer')
);

-- 2.5 step 1b: chain keys. The key itself never lives in this file; only its fingerprint
-- (HMAC of a fixed label under the key, hex). One active key; a key is retired once and kept forever, because
-- the entries it sealed must stay verifiable.
CREATE TABLE ledger_chain_key (
    key_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE CHECK (length(fingerprint) = 64 AND fingerprint NOT GLOB '*[^0-9a-f]*'),
    created_at TEXT NOT NULL,
    created_by INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    retired_at TEXT,
    retire_reason TEXT CHECK (retire_reason IN ('Rotation', 'Key lost', 'Compromised')),
    CHECK ((is_active = 1) = (retired_at IS NULL)),
    CHECK ((retired_at IS NULL) = (retire_reason IS NULL))
);

-- 2.5 step 1b: checkpoints of the chain head (verification results, close, export, backup, restore, rotation).
-- Append-only; `mac` is an HMAC over the row so a forged "verified through N" marker is detected.
-- Step 1d (KS12): a 'Key lost' checkpoint, result 'Unverified', starts a new key epoch. It records the last entry
-- sealed with the lost key (through_entry_number, its stored hash as is), is signed by the new key (key_id) and
-- names the key retired as lost (ref_type 'ledger_chain_key', ref_id). Entries up to it cannot be verified.
CREATE TABLE ledger_checkpoint (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    created_by INTEGER,
    kind TEXT NOT NULL CHECK (kind IN ('Verify', 'Period close', 'Year close', 'Report export', 'Backup', 'Restore',
                                       'Key rotation', 'Manual', 'Key lost')),
    scope TEXT CHECK (scope IN ('Incremental', 'Full')),
    result TEXT NOT NULL CHECK (result IN ('OK', 'Broken', 'Unverified')),
    through_entry_number INTEGER NOT NULL
        CHECK (typeof(through_entry_number) = 'integer' AND through_entry_number >= 0),
    chain_hash TEXT CHECK (chain_hash IS NULL OR (length(chain_hash) = 64 AND chain_hash NOT GLOB '*[^0-9a-f]*')),
    first_broken_entry_number INTEGER,
    key_id INTEGER REFERENCES ledger_chain_key(key_id),
    ref_type TEXT,
    ref_id INTEGER,
    mac TEXT NOT NULL CHECK (length(mac) = 64 AND mac NOT GLOB '*[^0-9a-f]*'),
    CHECK ((kind = 'Verify') = (scope IS NOT NULL)),
    CHECK ((result = 'Broken') = (first_broken_entry_number IS NOT NULL)),
    CHECK ((through_entry_number = 0) = (chain_hash IS NULL)),
    CHECK ((kind = 'Key lost') = (result = 'Unverified')),
    CHECK (kind <> 'Key lost' OR (key_id IS NOT NULL AND ref_type IS NOT NULL AND ref_type = 'ledger_chain_key'
                                  AND ref_id IS NOT NULL))
);

CREATE TABLE journal_line_dimension (
    line_id INTEGER NOT NULL REFERENCES journal_line(line_id) ON DELETE CASCADE,
    dimension_type_id INTEGER NOT NULL,
    dimension_value_id INTEGER NOT NULL,
    PRIMARY KEY (line_id, dimension_type_id),
    FOREIGN KEY (dimension_value_id, dimension_type_id)
        REFERENCES dimension_value(dimension_value_id, dimension_type_id)
        ON DELETE RESTRICT
);

CREATE TABLE "account" (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type_id INTEGER NOT NULL REFERENCES account_type(type_id),
    parent_id INTEGER REFERENCES account(account_id),
    is_postable INTEGER DEFAULT 1 CHECK (is_postable IN (0, 1)),
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    is_deferral_account INTEGER DEFAULT 0 CHECK (is_deferral_account IN (0, 1)),
    control_type TEXT CHECK (control_type IN (
        'AR', 'AP', 'Retainage receivable', 'Retainage payable', 'Sales tax payable', 'Use tax payable',
        'Undeposited funds', 'GRNI', 'Inventory', 'Fixed assets', 'Loans',
        'Deferral', 'Over/under billing', 'Employee advance', 'Employee material advance')),
    -- 2.4: A3 (D or C; a contra account differs from its type) and 1.5 (tax-strategy accounts)
    subtype TEXT,
    normal_balance TEXT CHECK (normal_balance IS NULL OR normal_balance IN ('D', 'C')),
    is_tax_strategy_only INTEGER NOT NULL DEFAULT 0 CHECK (is_tax_strategy_only IN (0, 1))
);

CREATE TABLE "invoice" (
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

CREATE TABLE "invoice_line" (
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

CREATE TABLE "payment" (
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

CREATE TABLE "deferral_schedule_line" (
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

CREATE TABLE "poc_snapshot" (
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

CREATE TABLE "bank_reconciliation" (
    recon_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES account(account_id),
    statement_date TEXT NOT NULL CHECK (statement_date IS date(statement_date)),
    statement_balance_cents INTEGER NOT NULL,
    is_complete INTEGER DEFAULT 0 CHECK (is_complete IN (0, 1)),
    CHECK (typeof(statement_balance_cents) = 'integer')
);

CREATE TABLE "company_settings" (
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
, require_separate_approver INTEGER NOT NULL DEFAULT 0
    CHECK (require_separate_approver IN (0, 1)),
    -- 2.4: setup facts, controls and the system account pointers (A6)
    country TEXT CHECK (country IS NULL OR country IN ('US', 'PH')),
    timezone TEXT,
    date_format TEXT NOT NULL DEFAULT 'MM/DD/YYYY' CHECK (date_format IN ('MM/DD/YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD')),
    warn_future_days INTEGER NOT NULL DEFAULT 30 CHECK (warn_future_days >= 0),
    warn_past_days INTEGER NOT NULL DEFAULT 90 CHECK (warn_past_days >= 0),
    books_closed_through TEXT CHECK (books_closed_through IS date(books_closed_through)),
    allow_manual_control_je INTEGER NOT NULL DEFAULT 1 CHECK (allow_manual_control_je IN (0, 1)),
    adjustment_periods_enabled INTEGER NOT NULL DEFAULT 0 CHECK (adjustment_periods_enabled IN (0, 1)),
    first_fiscal_year INTEGER CHECK (first_fiscal_year IS NULL OR first_fiscal_year BETWEEN 1900 AND 2200),
    ar_acct_id INTEGER REFERENCES account(account_id),
    ap_acct_id INTEGER REFERENCES account(account_id),
    sales_tax_payable_acct_id INTEGER REFERENCES account(account_id),
    default_bank_acct_id INTEGER REFERENCES account(account_id),
    retained_earnings_acct_id INTEGER REFERENCES account(account_id),
    opening_balance_equity_acct_id INTEGER REFERENCES account(account_id),
    undeposited_funds_acct_id INTEGER REFERENCES account(account_id),
    retainage_receivable_acct_id INTEGER REFERENCES account(account_id),
    retainage_payable_acct_id INTEGER REFERENCES account(account_id),
    employee_advances_acct_id INTEGER REFERENCES account(account_id),
    prepaid_expenses_acct_id INTEGER REFERENCES account(account_id),
    grni_acct_id INTEGER REFERENCES account(account_id),
    credit_card_clearing_acct_id INTEGER REFERENCES account(account_id),
    use_tax_payable_acct_id INTEGER REFERENCES account(account_id),
    unearned_revenue_acct_id INTEGER REFERENCES account(account_id),
    customer_deposits_acct_id INTEGER REFERENCES account(account_id),
    equipment_recovery_acct_id INTEGER REFERENCES account(account_id),
    inventory_adjustments_acct_id INTEGER REFERENCES account(account_id),
    bank_charges_acct_id INTEGER REFERENCES account(account_id),
    interest_income_acct_id INTEGER REFERENCES account(account_id),
    gain_loss_disposal_acct_id INTEGER REFERENCES account(account_id),
    interest_expense_acct_id INTEGER REFERENCES account(account_id),
    rounding_variance_acct_id INTEGER REFERENCES account(account_id));

CREATE TABLE "change_order" (
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

CREATE TABLE "contact" (
    contact_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL, 
    bir_registered_name  TEXT, 
    entity_type          TEXT CHECK (entity_type IN ('Individual/Single member LLC', 'Corp', 'LLC/LLP')),
    is_customer          INTEGER DEFAULT 0, 
    is_vendor            INTEGER DEFAULT 0, 
    is_employee          INTEGER DEFAULT 0,
    email                TEXT,
    phone                TEXT,
    address              TEXT,
    tax_id               TEXT, -- Maps to EIN / TIN structures
    is_active            INTEGER DEFAULT 1
, mailing_street TEXT, mailing_city TEXT, mailing_state TEXT, mailing_zip TEXT
    -- 2.6: codes are assigned only by the contacts service (customer_number / vendor_number)
    , customer_code TEXT, vendor_code TEXT
    -- 004: ISO dates and 0/1 flags
    , CHECK (is_customer IN (0, 1))
    , CHECK (is_vendor IN (0, 1))
    , CHECK (is_employee IN (0, 1))
    , CHECK (is_active IN (0, 1))
    , CHECK (is_customer = 0 OR customer_code IS NOT NULL)
    , CHECK (is_vendor = 0 OR vendor_code IS NOT NULL)
);

CREATE UNIQUE INDEX idx_contact_customer_code ON contact (customer_code) WHERE customer_code IS NOT NULL;
CREATE UNIQUE INDEX idx_contact_vendor_code ON contact (vendor_code) WHERE vendor_code IS NOT NULL;

-- The sequence tables are the only source of code numbers (never MAX+1). AUTOINCREMENT
-- keeps a number from ever being issued twice, even if a row is removed.
CREATE TABLE customer_number (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL UNIQUE REFERENCES contact(contact_id)
);

CREATE TABLE vendor_number (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL UNIQUE REFERENCES contact(contact_id)
);

CREATE TRIGGER trg_contact_code_immutable
BEFORE UPDATE OF customer_code, vendor_code ON contact
WHEN (OLD.customer_code IS NOT NULL AND NEW.customer_code IS NOT OLD.customer_code)
  OR (OLD.vendor_code IS NOT NULL AND NEW.vendor_code IS NOT OLD.vendor_code)
BEGIN
    SELECT RAISE(ABORT, 'A customer or vendor code cannot be changed once it is set');
END;

CREATE TRIGGER trg_contact_with_code_no_delete
BEFORE DELETE ON contact
WHEN OLD.customer_code IS NOT NULL OR OLD.vendor_code IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'A contact with a customer or vendor code cannot be deleted; make it inactive instead');
END;

CREATE TABLE "contract" (
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

CREATE TABLE "deferral" (
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

CREATE TABLE "import_batch" (
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

CREATE TABLE "progress_billing_application" (
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

CREATE TABLE "saas_subscription" (
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

CREATE TABLE "saas_usage_telemetry" (
    telemetry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id  INTEGER NOT NULL REFERENCES saas_subscription(subscription_id) ON DELETE CASCADE,
    metric_type      TEXT CHECK (metric_type IN ('API_Calls', 'Storage_GB', 'AI_Tokens_Consumed')),
    units_used       INTEGER NOT NULL CHECK (units_used > 0),
    logged_at_date   TEXT NOT NULL
    -- 004: ISO dates and 0/1 flags
    , CHECK (logged_at_date IS date(logged_at_date))
);

CREATE TABLE "staged_transaction" (
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

CREATE TABLE "subscription" (
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

CREATE TABLE "time_entry" (
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

CREATE TABLE permission (
    permission_code TEXT PRIMARY KEY,
    module TEXT NOT NULL,
    description TEXT NOT NULL,
    is_sensitive INTEGER NOT NULL CHECK (is_sensitive IN (0, 1))
);

CREATE TABLE role (
    role_code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_system INTEGER NOT NULL CHECK (is_system IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    project_scope TEXT NOT NULL DEFAULT 'All' CHECK (project_scope IN ('All', 'Assigned')),
    created_at TEXT NOT NULL
);

CREATE TABLE role_permission (
    role_code TEXT NOT NULL REFERENCES role(role_code) ON DELETE CASCADE,
    permission_code TEXT NOT NULL REFERENCES permission(permission_code),
    PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE approval_limit (
    role_code TEXT NOT NULL REFERENCES role(role_code) ON DELETE CASCADE,
    document_type TEXT NOT NULL CHECK (document_type IN ('Bill', 'Journal entry', 'Payment', 'Purchase order', 'Subcontract', 'Pay application', 'Import batch', 'Asset disposal', 'Estimate', 'Change order', 'Contract')),
    max_amount_cents INTEGER NOT NULL CHECK (typeof(max_amount_cents) = 'integer' AND max_amount_cents >= 0),
    PRIMARY KEY (role_code, document_type)
);

CREATE TABLE user_project_scope (
    user_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL REFERENCES project(project_id),
    PRIMARY KEY (user_id, project_id)
);

CREATE TABLE access_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    user_id INTEGER,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('Master', 'User', 'Agent')),
    event_type TEXT NOT NULL CHECK (event_type IN ('Denied', 'Open company')),
    permission_code TEXT,
    record_type TEXT,
    record_id INTEGER,
    origin TEXT
);

CREATE TABLE approval_policy (
    policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    document_type TEXT NOT NULL CHECK (document_type IN ('Bill', 'Journal entry', 'Payment', 'Purchase order', 'Subcontract', 'Pay application', 'Import batch', 'Asset disposal', 'Estimate', 'Change order', 'Contract')),
    min_amount_cents INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(min_amount_cents) = 'integer' AND min_amount_cents >= 0),
    max_amount_cents INTEGER
        CHECK (max_amount_cents IS NULL
               OR (typeof(max_amount_cents) = 'integer' AND max_amount_cents >= min_amount_cents)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE approval_step (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL REFERENCES approval_policy(policy_id) ON DELETE CASCADE,
    step_no INTEGER NOT NULL CHECK (step_no >= 1),
    role_code TEXT NOT NULL REFERENCES role(role_code),
    required_count INTEGER NOT NULL DEFAULT 1 CHECK (required_count >= 1),
    UNIQUE (policy_id, step_no, role_code)
);

CREATE TABLE approval_request (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_type TEXT NOT NULL CHECK (document_type IN ('Bill', 'Journal entry', 'Payment', 'Purchase order', 'Subcontract', 'Pay application', 'Import batch', 'Asset disposal', 'Estimate', 'Change order', 'Contract')),
    record_type TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (typeof(amount_cents) = 'integer'),
    policy_id INTEGER REFERENCES approval_policy(policy_id),
    created_by INTEGER NOT NULL,
    project_id INTEGER REFERENCES project(project_id),
    chain_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Cancelled')),
    submitted_by INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK ((status = 'Pending') = (completed_at IS NULL))
);

CREATE TABLE approval_action (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES approval_request(request_id),
    step_no INTEGER NOT NULL,
    role_code TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('Approve', 'Reject')),
    reason TEXT,
    self_approved INTEGER NOT NULL DEFAULT 0 CHECK (self_approved IN (0, 1)),
    acted_at TEXT NOT NULL,
    UNIQUE (request_id, user_id),
    CHECK (decision = 'Approve' OR (reason IS NOT NULL AND length(trim(reason)) > 0))
);


-- ---------------------------------------------------------------------------
-- Seed rows (inserted before the audit triggers exist, so they write no audit rows)
-- ---------------------------------------------------------------------------

INSERT INTO account_type (type_id, name, normal_balance) VALUES
    (1, 'Asset', 'D'),
    (2, 'Liability', 'C'),
    (3, 'Equity', 'C'),
    (4, 'Revenue', 'C'),
    (5, 'Expense', 'D');

INSERT INTO audit_context (id) VALUES (1);

INSERT INTO entry_number_sequence (id, last_number) VALUES (1, 0);

INSERT INTO permission (permission_code, module, description, is_sensitive) VALUES
    ('company.settings', 'Company', 'Change company settings', 0),
    ('company.users.manage', 'Company', 'Create users and assign roles and access', 0),
    ('company.roles.manage', 'Company', 'Create and edit roles and approval limits', 0),
    ('company.backup', 'Company', 'Back up and export the company', 0),
    ('company.restore', 'Company', 'Restore the company from a backup', 1),
    ('company.create', 'Company', 'Create a subsidiary company', 0),
    ('period.close', 'Periods', 'Close a fiscal period', 0),
    ('period.reopen', 'Periods', 'Reopen a closed fiscal period (reason required)', 1),
    ('year.reopen', 'Periods', 'Reopen a period in a closed fiscal year (reason required)', 1),
    ('period.view', 'Periods', 'View fiscal periods', 0),
    ('je.create', 'Ledger', 'Create journal entries', 0),
    ('je.post', 'Ledger', 'Post journal entries', 0),
    ('je.approve', 'Ledger', 'Approve journal entries', 1),
    ('je.reverse', 'Ledger', 'Reverse posted journal entries', 0),
    ('account.manage', 'Ledger', 'Create and edit accounts', 0),
    ('ledger.view', 'Ledger', 'View the general ledger', 0),
    ('customer.manage', 'Customers / AR', 'Create and edit customers', 0),
    ('invoice.create', 'Customers / AR', 'Create invoices', 0),
    ('invoice.send', 'Customers / AR', 'Send (post) invoices', 0),
    ('invoice.void', 'Customers / AR', 'Void invoices', 0),
    ('payment.receive', 'Customers / AR', 'Receive customer payments', 0),
    ('credit_memo.create', 'Customers / AR', 'Create credit memos', 0),
    ('ar.view', 'Customers / AR', 'View receivables', 0),
    ('vendor.manage', 'Vendors / AP', 'Create and edit vendors', 0),
    ('bill.create', 'Vendors / AP', 'Enter vendor bills', 0),
    ('bill.approve', 'Vendors / AP', 'Approve vendor bills', 1),
    ('bill.override_match', 'Vendors / AP', 'Override a purchase order match exception', 1),
    ('bill.void', 'Vendors / AP', 'Void vendor bills', 0),
    ('payment.make', 'Vendors / AP', 'Pay vendor bills', 0),
    ('payment.approve', 'Vendors / AP', 'Approve payments', 1),
    ('payment.release_hold', 'Vendors / AP', 'Release a compliance hold on payment', 1),
    ('ap.view', 'Vendors / AP', 'View payables', 0),
    ('po.create', 'Purchasing', 'Create purchase orders', 0),
    ('po.approve', 'Purchasing', 'Approve purchase orders', 1),
    ('subcontract.approve', 'Purchasing', 'Approve subcontracts', 1),
    ('receiving.stock', 'Purchasing', 'Receive stock into the warehouse', 0),
    ('receiving.jobsite', 'Purchasing', 'Confirm delivery tickets at the job site', 0),
    ('po.view', 'Purchasing', 'View purchase orders', 0),
    ('inventory.pull', 'Inventory', 'Pull inventory to a job', 0),
    ('inventory.adjust', 'Inventory', 'Adjust inventory quantities', 0),
    ('inventory.count', 'Inventory', 'Count inventory', 0),
    ('inventory.view', 'Inventory', 'View inventory', 0),
    ('project.create', 'Projects / CRM', 'Create projects and leads', 0),
    ('project.manage', 'Projects / CRM', 'Manage projects', 0),
    ('estimate.create', 'Projects / CRM', 'Create estimates', 0),
    ('estimate.approve', 'Projects / CRM', 'Approve estimates', 1),
    ('change_order.create', 'Projects / CRM', 'Create change orders', 0),
    ('change_order.approve', 'Projects / CRM', 'Approve change orders', 1),
    ('contract.approve', 'Projects / CRM', 'Approve contracts', 1),
    ('project.view', 'Projects / CRM', 'View projects', 0),
    ('payapp.create', 'Pay applications', 'Create pay applications', 0),
    ('payapp.approve', 'Pay applications', 'Approve pay applications', 1),
    ('retainage.release', 'Pay applications', 'Release retainage', 0),
    ('asset.create', 'Fixed assets', 'Create fixed assets', 0),
    ('asset.dispose', 'Fixed assets', 'Dispose of fixed assets', 0),
    ('asset.approve', 'Fixed assets', 'Approve asset disposals', 1),
    ('depreciation.run', 'Fixed assets', 'Run depreciation', 0),
    ('asset.view', 'Fixed assets', 'View fixed assets', 0),
    ('loan.manage', 'Loans', 'Manage loans', 0),
    ('loan.view', 'Loans', 'View loans', 0),
    ('time.enter', 'Payroll / time', 'Enter time', 0),
    ('time.approve', 'Payroll / time', 'Approve time', 1),
    ('payroll.view', 'Payroll / time', 'View wages and payroll', 1),
    ('payroll.import', 'Payroll / time', 'Import payroll', 1),
    ('import.run', 'Imports', 'Run imports into staging', 0),
    ('import.approve', 'Imports', 'Approve staged import batches', 1),
    ('view.tax_ids', 'Sensitive data', 'See tax IDs unmasked', 1),
    ('view.bank_details', 'Sensitive data', 'See bank details unmasked', 1),
    ('report.financial', 'Reports', 'Run financial reports', 0),
    ('report.job_cost', 'Reports', 'Run job cost reports', 0),
    ('report.export', 'Reports', 'Export reports', 0),
    ('ai.use', 'AI', 'Open and use the AI Copilot', 0),
    ('ai.settings', 'AI', 'Change AI keys, data sharing and budget', 0),
    ('audit.view', 'Audit', 'View the audit trail', 1),
    ('ledger.verify', 'Audit', 'Verify ledger integrity', 1);

INSERT INTO role (role_code, name, is_system, is_active, project_scope, created_at)
    VALUES ('Admin', 'Admin', 1, 1, 'All', strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'));

INSERT INTO role_permission (role_code, permission_code)
    SELECT 'Admin', permission_code FROM permission;


-- ---------------------------------------------------------------------------
-- 2.4: per-document approval switches, voucher numbers, bank account details
-- ---------------------------------------------------------------------------

-- Decision 1.6: approval is OFF by default for every document type. Journal entries use
-- company_settings.manual_entry_approval as their switch, so they have no row here.
CREATE TABLE document_approval_setting (
    document_type TEXT PRIMARY KEY CHECK (document_type IN ('Bill', 'Payment', 'Purchase order', 'Subcontract', 'Pay application', 'Import batch', 'Asset disposal', 'Estimate', 'Change order', 'Contract')),
    requires_approval INTEGER NOT NULL DEFAULT 0 CHECK (requires_approval IN (0, 1))
);

INSERT INTO document_approval_setting (document_type) VALUES
    ('Bill'), ('Payment'), ('Purchase order'), ('Subcontract'), ('Pay application'),
    ('Import batch'), ('Asset disposal'), ('Estimate'), ('Change order'), ('Contract');

-- Decision 1.3: bills get a system voucher number (VCH-1001...) from their own sequence,
-- assigned at entry; gaps are allowed when drafts are deleted.
CREATE TABLE voucher_sequence (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_number INTEGER NOT NULL DEFAULT 1000 CHECK (typeof(last_number) = 'integer' AND last_number >= 1000)
);

INSERT INTO voucher_sequence (id, last_number) VALUES (1, 1000);

INSERT INTO period_close_check (check_code) VALUES ('draft_entries'), ('earlier_period_open'), ('pending_approvals'),
    ('control_overrides'), ('ledger_integrity');

-- 2.5 step 1b: a seal never repeats; one active chain key; keys and checkpoints are never removed.
CREATE UNIQUE INDEX journal_entry_chain_hash_unique ON journal_entry (chain_hash) WHERE chain_hash IS NOT NULL;
CREATE UNIQUE INDEX ledger_chain_key_one_active ON ledger_chain_key (is_active) WHERE is_active = 1;

CREATE TRIGGER ledger_chain_key_no_delete
BEFORE DELETE ON ledger_chain_key
BEGIN
    SELECT RAISE(ABORT, 'Ledger keys are never deleted; retired keys verify the entries they sealed');
END;

CREATE TRIGGER ledger_chain_key_retire_only
BEFORE UPDATE ON ledger_chain_key
WHEN NOT (OLD.is_active = 1 AND NEW.is_active = 0
          AND NEW.key_id IS OLD.key_id AND NEW.fingerprint IS OLD.fingerprint
          AND NEW.created_at IS OLD.created_at AND NEW.created_by IS OLD.created_by)
BEGIN
    SELECT RAISE(ABORT, 'A ledger key can only be retired, once; nothing else about it changes');
END;

CREATE TRIGGER ledger_checkpoint_no_update
BEFORE UPDATE ON ledger_checkpoint
BEGIN
    SELECT RAISE(ABORT, 'Ledger checkpoints cannot be changed');
END;

CREATE TRIGGER ledger_checkpoint_no_delete
BEFORE DELETE ON ledger_checkpoint
BEGIN
    SELECT RAISE(ABORT, 'Ledger checkpoints cannot be deleted');
END;

-- 2.5: an entry has at most one Void or Correction reversal and at most one Accrual reversal, so an accrual and
-- its automatic reversal can be voided as a pair (decision L5).
CREATE UNIQUE INDEX journal_entry_one_void_or_correction ON journal_entry (reverses_entry_id)
    WHERE reversal_reason IN ('Void', 'Correction');
CREATE UNIQUE INDEX journal_entry_one_accrual_reversal ON journal_entry (reverses_entry_id)
    WHERE reversal_reason = 'Accrual reversal';

-- Decision C4: full routing and account numbers live here only; they are shown masked without
-- view.bank_details, never sent to the AI and never written in full to the audit log.
CREATE TABLE bank_account (
    bank_account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL UNIQUE REFERENCES account(account_id),
    bank_name TEXT,
    routing_number TEXT,
    account_number TEXT,
    account_last4 TEXT CHECK (account_last4 IS NULL OR (length(account_last4) <= 4 AND account_last4 NOT GLOB '*[^0-9]*'))
);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX invoice_sales_number_unique ON invoice (invoice_number) WHERE ledger_side = 'Sales';

CREATE UNIQUE INDEX approval_request_one_pending
    ON approval_request (record_type, record_id) WHERE status = 'Pending';


-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------

CREATE TRIGGER dimension_value_validate_insert
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

CREATE TRIGGER dimension_value_validate_update
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

CREATE TRIGGER audit_context_no_delete
BEFORE DELETE ON audit_context
BEGIN
    SELECT RAISE(ABORT, 'audit_context row cannot be deleted');
END;

CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

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

CREATE TRIGGER fiscal_period_contiguous_insert
BEFORE INSERT ON fiscal_period
WHEN NEW.is_adjustment_period = 0 AND EXISTS (SELECT 1 FROM fiscal_period WHERE is_adjustment_period = 0)
BEGIN
    SELECT CASE WHEN NOT (
           NEW.start_date = (SELECT date(MAX(end_date), '+1 day') FROM fiscal_period WHERE is_adjustment_period = 0)
        OR NEW.end_date = (SELECT date(MIN(start_date), '-1 day') FROM fiscal_period WHERE is_adjustment_period = 0)
    ) THEN RAISE(ABORT, 'Fiscal periods must be contiguous: start the day after the last period or end the day before the first') END;
END;

-- Periods 13 and 14 are one day long: the last day of their fiscal year (A1).
CREATE TRIGGER fiscal_period_adjustment_insert
BEFORE INSERT ON fiscal_period
WHEN NEW.is_adjustment_period = 1
BEGIN
    SELECT CASE WHEN NEW.fiscal_year_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM fiscal_year WHERE year_id = NEW.fiscal_year_id
           AND end_date = NEW.start_date AND end_date = NEW.end_date)
    THEN RAISE(ABORT, 'Adjustment periods 13 and 14 are dated the last day of their fiscal year') END;
END;

-- A period of a closed fiscal year cannot be reopened; reopen the year first (L7).
CREATE TRIGGER fiscal_period_reopen_in_closed_year
BEFORE UPDATE OF is_closed ON fiscal_period
WHEN OLD.is_closed = 1 AND NEW.is_closed = 0
 AND EXISTS (SELECT 1 FROM fiscal_year WHERE year_id = NEW.fiscal_year_id AND is_year_closed = 1)
BEGIN
    SELECT RAISE(ABORT, 'This fiscal year is closed; reopen the year first');
END;

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
WHEN OLD.is_adjustment_period = 0
 AND EXISTS (SELECT 1 FROM fiscal_period WHERE is_adjustment_period = 0 AND end_date < OLD.start_date)
 AND EXISTS (SELECT 1 FROM fiscal_period WHERE is_adjustment_period = 0 AND start_date > OLD.end_date)
BEGIN
    SELECT RAISE(ABORT, 'Only the first or last period can be deleted');
END;

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

CREATE TRIGGER journal_entry_require_balance_on_post
BEFORE UPDATE OF is_posted ON journal_entry
WHEN NEW.is_posted = 1 AND OLD.is_posted = 0
BEGIN
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM fiscal_period WHERE period_id = NEW.period_id AND is_closed = 1
    ) THEN RAISE(ABORT, 'Cannot post into a closed fiscal period') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM fiscal_period
        WHERE is_closed = 1 AND is_adjustment_period = 0
          AND NEW.entry_date BETWEEN start_date AND end_date
    ) AND COALESCE((SELECT is_adjustment_period FROM fiscal_period WHERE period_id = NEW.period_id), 0) = 0
    THEN RAISE(ABORT, 'Cannot post: the entry date falls in a closed fiscal period') END;
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

-- Posted records are locked (CLAUDE.md rule 8). A posted entry cannot be
-- unposted or edited; the only allowed change is marking it void, and only
-- when a posted reversing entry with reason 'Void' exists. Corrections are
-- reversing entries, never edits or deletes.

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
        AND NEW.auto_reverse_date IS OLD.auto_reverse_date
        AND NEW.reversal_note IS OLD.reversal_note
        AND NEW.chain_version IS OLD.chain_version
        AND NEW.chain_key_id IS OLD.chain_key_id
        AND NEW.chain_prev_hash IS OLD.chain_prev_hash
        AND NEW.chain_hash IS OLD.chain_hash
    ) THEN RAISE(ABORT, 'Posted journal entries cannot be changed; void them by posting a Void reversal') END;
END;

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
        AND NEW.is_control_override IS OLD.is_control_override
        AND NEW.is_rounding_adjustment IS OLD.is_rounding_adjustment
 )
BEGIN SELECT RAISE(ABORT, 'Posted journal entries cannot be changed'); END;

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

CREATE TRIGGER account_lock_after_posting
BEFORE UPDATE OF type_id, parent_id, control_type, normal_balance ON account
WHEN (NEW.type_id IS NOT OLD.type_id
      OR NEW.parent_id IS NOT OLD.parent_id OR NEW.control_type IS NOT OLD.control_type
      OR NEW.normal_balance IS NOT OLD.normal_balance)
 AND EXISTS (SELECT 1 FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id
             WHERE l.account_id = OLD.account_id AND e.is_posted = 1)
BEGIN
    SELECT RAISE(ABORT, 'An account with posted entries keeps its type, parent, control type and normal balance; its name and number can still change');
END;

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

CREATE TRIGGER invoice_insert_as_draft
BEFORE INSERT ON invoice
WHEN NEW.status IS NOT 'Draft' OR NEW.entry_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Create invoices as Draft without a journal entry, add lines, then send');
END;

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
            'origin', NEW.origin,
            'auto_reverse_date', NEW.auto_reverse_date,
            'reversal_note', NEW.reversal_note,
            'chain_version', NEW.chain_version,
            'chain_key_id', NEW.chain_key_id,
            'chain_prev_hash', NEW.chain_prev_hash,
            'chain_hash', NEW.chain_hash),
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
            'origin', OLD.origin,
            'auto_reverse_date', OLD.auto_reverse_date,
            'reversal_note', OLD.reversal_note,
            'chain_version', OLD.chain_version,
            'chain_key_id', OLD.chain_key_id,
            'chain_prev_hash', OLD.chain_prev_hash,
            'chain_hash', OLD.chain_hash),
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
            'origin', NEW.origin,
            'auto_reverse_date', NEW.auto_reverse_date,
            'reversal_note', NEW.reversal_note,
            'chain_version', NEW.chain_version,
            'chain_key_id', NEW.chain_key_id,
            'chain_prev_hash', NEW.chain_prev_hash,
            'chain_hash', NEW.chain_hash),
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
                    'external_ref', l.external_ref,
                    'is_control_override', l.is_control_override,
                    'is_rounding_adjustment', l.is_rounding_adjustment))
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
            'origin', NEW.origin,
            'auto_reverse_date', NEW.auto_reverse_date,
            'reversal_note', NEW.reversal_note,
            'chain_version', NEW.chain_version,
            'chain_key_id', NEW.chain_key_id,
            'chain_prev_hash', NEW.chain_prev_hash,
            'chain_hash', NEW.chain_hash) END,
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
            'origin', OLD.origin,
            'auto_reverse_date', OLD.auto_reverse_date,
            'reversal_note', OLD.reversal_note,
            'chain_version', OLD.chain_version,
            'chain_key_id', OLD.chain_key_id,
            'chain_prev_hash', OLD.chain_prev_hash,
            'chain_hash', OLD.chain_hash),
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
            'closed_by', NEW.closed_by,
            'fiscal_year_id', NEW.fiscal_year_id,
            'period_number', NEW.period_number,
            'is_adjustment_period', NEW.is_adjustment_period),
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
            'closed_by', OLD.closed_by,
            'fiscal_year_id', OLD.fiscal_year_id,
            'period_number', OLD.period_number,
            'is_adjustment_period', OLD.is_adjustment_period),
        json_object(
            'period_id', NEW.period_id,
            'name', NEW.name,
            'start_date', NEW.start_date,
            'end_date', NEW.end_date,
            'is_closed', NEW.is_closed,
            'closed_at', NEW.closed_at,
            'closed_by', NEW.closed_by,
            'fiscal_year_id', NEW.fiscal_year_id,
            'period_number', NEW.period_number,
            'is_adjustment_period', NEW.is_adjustment_period),
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
            'closed_by', OLD.closed_by,
            'fiscal_year_id', OLD.fiscal_year_id,
            'period_number', OLD.period_number,
            'is_adjustment_period', OLD.is_adjustment_period),
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
            'control_type', NEW.control_type,
            'normal_balance', NEW.normal_balance,
            'subtype', NEW.subtype,
            'is_tax_strategy_only', NEW.is_tax_strategy_only),
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
            'control_type', OLD.control_type,
            'normal_balance', OLD.normal_balance,
            'subtype', OLD.subtype,
            'is_tax_strategy_only', OLD.is_tax_strategy_only),
        json_object(
            'account_id', NEW.account_id,
            'code', NEW.code,
            'name', NEW.name,
            'type_id', NEW.type_id,
            'parent_id', NEW.parent_id,
            'is_postable', NEW.is_postable,
            'is_active', NEW.is_active,
            'is_deferral_account', NEW.is_deferral_account,
            'control_type', NEW.control_type,
            'normal_balance', NEW.normal_balance,
            'subtype', NEW.subtype,
            'is_tax_strategy_only', NEW.is_tax_strategy_only),
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
            'control_type', OLD.control_type,
            'normal_balance', OLD.normal_balance,
            'subtype', OLD.subtype,
            'is_tax_strategy_only', OLD.is_tax_strategy_only),
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

CREATE TRIGGER access_event_no_update
BEFORE UPDATE ON access_event
BEGIN
    SELECT RAISE(ABORT, 'access_event is append-only');
END;

CREATE TRIGGER access_event_no_delete
BEFORE DELETE ON access_event
BEGIN
    SELECT RAISE(ABORT, 'access_event is append-only');
END;

CREATE TRIGGER approval_action_no_update
BEFORE UPDATE ON approval_action
BEGIN
    SELECT RAISE(ABORT, 'approval_action is append-only');
END;

CREATE TRIGGER approval_action_no_delete
BEFORE DELETE ON approval_action
BEGIN
    SELECT RAISE(ABORT, 'approval_action is append-only');
END;

-- Admin is protected: it is the one fixed company role and holds every
-- permission, so a company can never lock itself out. Its role row and its
-- grants cannot be changed or removed; inserts stay allowed so a later
-- change can grant Admin new permissions.

CREATE TRIGGER role_admin_no_update
BEFORE UPDATE ON role
WHEN OLD.role_code = 'Admin'
BEGIN
    SELECT RAISE(ABORT, 'The Admin role cannot be changed');
END;

CREATE TRIGGER role_admin_no_delete
BEFORE DELETE ON role
WHEN OLD.role_code = 'Admin'
BEGIN
    SELECT RAISE(ABORT, 'The Admin role cannot be deleted');
END;

CREATE TRIGGER role_permission_admin_no_delete
BEFORE DELETE ON role_permission
WHEN OLD.role_code = 'Admin'
BEGIN
    SELECT RAISE(ABORT, 'Admin permissions cannot be removed');
END;

CREATE TRIGGER role_permission_admin_no_update
BEFORE UPDATE ON role_permission
WHEN OLD.role_code = 'Admin'
BEGIN
    SELECT RAISE(ABORT, 'Admin permissions cannot be changed');
END;

CREATE TRIGGER audit_role_insert
AFTER INSERT ON role
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'role', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'role_code', NEW.role_code,
            'name', NEW.name,
            'is_system', NEW.is_system,
            'is_active', NEW.is_active,
            'project_scope', NEW.project_scope,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_role_update
AFTER UPDATE ON role
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'role', NEW.rowid,
        'Update',
        json_object(
            'role_code', OLD.role_code,
            'name', OLD.name,
            'is_system', OLD.is_system,
            'is_active', OLD.is_active,
            'project_scope', OLD.project_scope,
            'created_at', OLD.created_at),
        json_object(
            'role_code', NEW.role_code,
            'name', NEW.name,
            'is_system', NEW.is_system,
            'is_active', NEW.is_active,
            'project_scope', NEW.project_scope,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_role_delete
AFTER DELETE ON role
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'role', OLD.rowid,
        'Delete',
        json_object(
            'role_code', OLD.role_code,
            'name', OLD.name,
            'is_system', OLD.is_system,
            'is_active', OLD.is_active,
            'project_scope', OLD.project_scope,
            'created_at', OLD.created_at),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_role_permission_insert
AFTER INSERT ON role_permission
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'role_permission', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'role_code', NEW.role_code,
            'permission_code', NEW.permission_code),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_role_permission_update
AFTER UPDATE ON role_permission
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'role_permission', NEW.rowid,
        'Update',
        json_object(
            'role_code', OLD.role_code,
            'permission_code', OLD.permission_code),
        json_object(
            'role_code', NEW.role_code,
            'permission_code', NEW.permission_code),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_role_permission_delete
AFTER DELETE ON role_permission
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'role_permission', OLD.rowid,
        'Delete',
        json_object(
            'role_code', OLD.role_code,
            'permission_code', OLD.permission_code),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_limit_insert
AFTER INSERT ON approval_limit
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_limit', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'role_code', NEW.role_code,
            'document_type', NEW.document_type,
            'max_amount_cents', NEW.max_amount_cents),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_limit_update
AFTER UPDATE ON approval_limit
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_limit', NEW.rowid,
        'Update',
        json_object(
            'role_code', OLD.role_code,
            'document_type', OLD.document_type,
            'max_amount_cents', OLD.max_amount_cents),
        json_object(
            'role_code', NEW.role_code,
            'document_type', NEW.document_type,
            'max_amount_cents', NEW.max_amount_cents),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_limit_delete
AFTER DELETE ON approval_limit
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_limit', OLD.rowid,
        'Delete',
        json_object(
            'role_code', OLD.role_code,
            'document_type', OLD.document_type,
            'max_amount_cents', OLD.max_amount_cents),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_project_scope_insert
AFTER INSERT ON user_project_scope
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_project_scope', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'user_id', NEW.user_id,
            'project_id', NEW.project_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_project_scope_update
AFTER UPDATE ON user_project_scope
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_project_scope', NEW.rowid,
        'Update',
        json_object(
            'user_id', OLD.user_id,
            'project_id', OLD.project_id),
        json_object(
            'user_id', NEW.user_id,
            'project_id', NEW.project_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_project_scope_delete
AFTER DELETE ON user_project_scope
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_project_scope', OLD.rowid,
        'Delete',
        json_object(
            'user_id', OLD.user_id,
            'project_id', OLD.project_id),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_policy_insert
AFTER INSERT ON approval_policy
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_policy', NEW.policy_id,
        'Insert',
        NULL,
        json_object(
            'policy_id', NEW.policy_id,
            'name', NEW.name,
            'document_type', NEW.document_type,
            'min_amount_cents', NEW.min_amount_cents,
            'max_amount_cents', NEW.max_amount_cents,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_policy_update
AFTER UPDATE ON approval_policy
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_policy', NEW.policy_id,
        'Update',
        json_object(
            'policy_id', OLD.policy_id,
            'name', OLD.name,
            'document_type', OLD.document_type,
            'min_amount_cents', OLD.min_amount_cents,
            'max_amount_cents', OLD.max_amount_cents,
            'is_active', OLD.is_active),
        json_object(
            'policy_id', NEW.policy_id,
            'name', NEW.name,
            'document_type', NEW.document_type,
            'min_amount_cents', NEW.min_amount_cents,
            'max_amount_cents', NEW.max_amount_cents,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_policy_delete
AFTER DELETE ON approval_policy
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_policy', OLD.policy_id,
        'Delete',
        json_object(
            'policy_id', OLD.policy_id,
            'name', OLD.name,
            'document_type', OLD.document_type,
            'min_amount_cents', OLD.min_amount_cents,
            'max_amount_cents', OLD.max_amount_cents,
            'is_active', OLD.is_active),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_step_insert
AFTER INSERT ON approval_step
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_step', NEW.step_id,
        'Insert',
        NULL,
        json_object(
            'step_id', NEW.step_id,
            'policy_id', NEW.policy_id,
            'step_no', NEW.step_no,
            'role_code', NEW.role_code,
            'required_count', NEW.required_count),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_step_update
AFTER UPDATE ON approval_step
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_step', NEW.step_id,
        'Update',
        json_object(
            'step_id', OLD.step_id,
            'policy_id', OLD.policy_id,
            'step_no', OLD.step_no,
            'role_code', OLD.role_code,
            'required_count', OLD.required_count),
        json_object(
            'step_id', NEW.step_id,
            'policy_id', NEW.policy_id,
            'step_no', NEW.step_no,
            'role_code', NEW.role_code,
            'required_count', NEW.required_count),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_step_delete
AFTER DELETE ON approval_step
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_step', OLD.step_id,
        'Delete',
        json_object(
            'step_id', OLD.step_id,
            'policy_id', OLD.policy_id,
            'step_no', OLD.step_no,
            'role_code', OLD.role_code,
            'required_count', OLD.required_count),
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
            'manual_entry_approval_threshold_cents', NEW.manual_entry_approval_threshold_cents,
            'require_separate_approver', NEW.require_separate_approver,
            'country', NEW.country,
            'timezone', NEW.timezone,
            'date_format', NEW.date_format,
            'warn_future_days', NEW.warn_future_days,
            'warn_past_days', NEW.warn_past_days,
            'books_closed_through', NEW.books_closed_through,
            'allow_manual_control_je', NEW.allow_manual_control_je,
            'adjustment_periods_enabled', NEW.adjustment_periods_enabled,
            'first_fiscal_year', NEW.first_fiscal_year,
            'ar_acct_id', NEW.ar_acct_id,
            'ap_acct_id', NEW.ap_acct_id,
            'sales_tax_payable_acct_id', NEW.sales_tax_payable_acct_id,
            'default_bank_acct_id', NEW.default_bank_acct_id,
            'retained_earnings_acct_id', NEW.retained_earnings_acct_id,
            'opening_balance_equity_acct_id', NEW.opening_balance_equity_acct_id,
            'undeposited_funds_acct_id', NEW.undeposited_funds_acct_id,
            'retainage_receivable_acct_id', NEW.retainage_receivable_acct_id,
            'retainage_payable_acct_id', NEW.retainage_payable_acct_id,
            'employee_advances_acct_id', NEW.employee_advances_acct_id,
            'prepaid_expenses_acct_id', NEW.prepaid_expenses_acct_id,
            'grni_acct_id', NEW.grni_acct_id,
            'credit_card_clearing_acct_id', NEW.credit_card_clearing_acct_id,
            'use_tax_payable_acct_id', NEW.use_tax_payable_acct_id,
            'unearned_revenue_acct_id', NEW.unearned_revenue_acct_id,
            'customer_deposits_acct_id', NEW.customer_deposits_acct_id,
            'equipment_recovery_acct_id', NEW.equipment_recovery_acct_id,
            'inventory_adjustments_acct_id', NEW.inventory_adjustments_acct_id,
            'bank_charges_acct_id', NEW.bank_charges_acct_id,
            'interest_income_acct_id', NEW.interest_income_acct_id,
            'gain_loss_disposal_acct_id', NEW.gain_loss_disposal_acct_id,
            'interest_expense_acct_id', NEW.interest_expense_acct_id,
            'rounding_variance_acct_id', NEW.rounding_variance_acct_id),
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
            'manual_entry_approval_threshold_cents', OLD.manual_entry_approval_threshold_cents,
            'require_separate_approver', OLD.require_separate_approver,
            'country', OLD.country,
            'timezone', OLD.timezone,
            'date_format', OLD.date_format,
            'warn_future_days', OLD.warn_future_days,
            'warn_past_days', OLD.warn_past_days,
            'books_closed_through', OLD.books_closed_through,
            'allow_manual_control_je', OLD.allow_manual_control_je,
            'adjustment_periods_enabled', OLD.adjustment_periods_enabled,
            'first_fiscal_year', OLD.first_fiscal_year,
            'ar_acct_id', OLD.ar_acct_id,
            'ap_acct_id', OLD.ap_acct_id,
            'sales_tax_payable_acct_id', OLD.sales_tax_payable_acct_id,
            'default_bank_acct_id', OLD.default_bank_acct_id,
            'retained_earnings_acct_id', OLD.retained_earnings_acct_id,
            'opening_balance_equity_acct_id', OLD.opening_balance_equity_acct_id,
            'undeposited_funds_acct_id', OLD.undeposited_funds_acct_id,
            'retainage_receivable_acct_id', OLD.retainage_receivable_acct_id,
            'retainage_payable_acct_id', OLD.retainage_payable_acct_id,
            'employee_advances_acct_id', OLD.employee_advances_acct_id,
            'prepaid_expenses_acct_id', OLD.prepaid_expenses_acct_id,
            'grni_acct_id', OLD.grni_acct_id,
            'credit_card_clearing_acct_id', OLD.credit_card_clearing_acct_id,
            'use_tax_payable_acct_id', OLD.use_tax_payable_acct_id,
            'unearned_revenue_acct_id', OLD.unearned_revenue_acct_id,
            'customer_deposits_acct_id', OLD.customer_deposits_acct_id,
            'equipment_recovery_acct_id', OLD.equipment_recovery_acct_id,
            'inventory_adjustments_acct_id', OLD.inventory_adjustments_acct_id,
            'bank_charges_acct_id', OLD.bank_charges_acct_id,
            'interest_income_acct_id', OLD.interest_income_acct_id,
            'gain_loss_disposal_acct_id', OLD.gain_loss_disposal_acct_id,
            'interest_expense_acct_id', OLD.interest_expense_acct_id,
            'rounding_variance_acct_id', OLD.rounding_variance_acct_id),
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
            'manual_entry_approval_threshold_cents', NEW.manual_entry_approval_threshold_cents,
            'require_separate_approver', NEW.require_separate_approver,
            'country', NEW.country,
            'timezone', NEW.timezone,
            'date_format', NEW.date_format,
            'warn_future_days', NEW.warn_future_days,
            'warn_past_days', NEW.warn_past_days,
            'books_closed_through', NEW.books_closed_through,
            'allow_manual_control_je', NEW.allow_manual_control_je,
            'adjustment_periods_enabled', NEW.adjustment_periods_enabled,
            'first_fiscal_year', NEW.first_fiscal_year,
            'ar_acct_id', NEW.ar_acct_id,
            'ap_acct_id', NEW.ap_acct_id,
            'sales_tax_payable_acct_id', NEW.sales_tax_payable_acct_id,
            'default_bank_acct_id', NEW.default_bank_acct_id,
            'retained_earnings_acct_id', NEW.retained_earnings_acct_id,
            'opening_balance_equity_acct_id', NEW.opening_balance_equity_acct_id,
            'undeposited_funds_acct_id', NEW.undeposited_funds_acct_id,
            'retainage_receivable_acct_id', NEW.retainage_receivable_acct_id,
            'retainage_payable_acct_id', NEW.retainage_payable_acct_id,
            'employee_advances_acct_id', NEW.employee_advances_acct_id,
            'prepaid_expenses_acct_id', NEW.prepaid_expenses_acct_id,
            'grni_acct_id', NEW.grni_acct_id,
            'credit_card_clearing_acct_id', NEW.credit_card_clearing_acct_id,
            'use_tax_payable_acct_id', NEW.use_tax_payable_acct_id,
            'unearned_revenue_acct_id', NEW.unearned_revenue_acct_id,
            'customer_deposits_acct_id', NEW.customer_deposits_acct_id,
            'equipment_recovery_acct_id', NEW.equipment_recovery_acct_id,
            'inventory_adjustments_acct_id', NEW.inventory_adjustments_acct_id,
            'bank_charges_acct_id', NEW.bank_charges_acct_id,
            'interest_income_acct_id', NEW.interest_income_acct_id,
            'gain_loss_disposal_acct_id', NEW.gain_loss_disposal_acct_id,
            'interest_expense_acct_id', NEW.interest_expense_acct_id,
            'rounding_variance_acct_id', NEW.rounding_variance_acct_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

-- Decision 1.7 / A9: a journal entry cannot be approved by its creator when the company requires a
-- separate approver. No settings row counts as "required" (the safe default).
CREATE TRIGGER journal_entry_separate_approver_insert
BEFORE INSERT ON journal_entry
WHEN NEW.approved_by IS NOT NULL AND NEW.approved_by IS NEW.created_by
 AND COALESCE((SELECT require_separate_approver FROM company_settings WHERE id = 1), 1) = 1
BEGIN
    SELECT RAISE(ABORT, 'This company requires a different user to approve an entry');
END;

CREATE TRIGGER journal_entry_separate_approver_update
BEFORE UPDATE OF approved_by, created_by ON journal_entry
WHEN NEW.approved_by IS NOT NULL AND NEW.approved_by IS NEW.created_by
 AND COALESCE((SELECT require_separate_approver FROM company_settings WHERE id = 1), 1) = 1
BEGIN
    SELECT RAISE(ABORT, 'This company requires a different user to approve an entry');
END;

CREATE TRIGGER audit_document_approval_setting_update
AFTER UPDATE ON document_approval_setting
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'document_approval_setting', NEW.rowid,
        'Update',
        json_object('document_type', OLD.document_type, 'requires_approval', OLD.requires_approval),
        json_object('document_type', NEW.document_type, 'requires_approval', NEW.requires_approval),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

-- Only the last four digits of a bank account number are ever written to the audit log.
CREATE TRIGGER audit_bank_account_insert
AFTER INSERT ON bank_account
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_account', NEW.bank_account_id,
        'Insert',
        NULL,
        json_object('account_id', NEW.account_id, 'bank_name', NEW.bank_name, 'account_last4', NEW.account_last4),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_account_update
AFTER UPDATE ON bank_account
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_account', NEW.bank_account_id,
        'Update',
        json_object('account_id', OLD.account_id, 'bank_name', OLD.bank_name, 'account_last4', OLD.account_last4),
        json_object('account_id', NEW.account_id, 'bank_name', NEW.bank_name, 'account_last4', NEW.account_last4),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_account_delete
AFTER DELETE ON bank_account
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_account', OLD.bank_account_id,
        'Delete',
        json_object('account_id', OLD.account_id, 'bank_name', OLD.bank_name, 'account_last4', OLD.account_last4),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

-- 2.4b: history is append-only; fiscal years and the close-check modes are audited.
CREATE TRIGGER period_status_history_no_update
BEFORE UPDATE ON period_status_history
BEGIN SELECT RAISE(ABORT, 'Period history cannot be changed'); END;

CREATE TRIGGER period_status_history_no_delete
BEFORE DELETE ON period_status_history
BEGIN SELECT RAISE(ABORT, 'Period history cannot be deleted'); END;

CREATE TRIGGER audit_fiscal_year_insert
AFTER INSERT ON fiscal_year
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_year', NEW.year_id, 'Insert', NULL,
        json_object('year_id', NEW.year_id, 'name', NEW.name, 'start_date', NEW.start_date,
                    'end_date', NEW.end_date, 'is_year_closed', NEW.is_year_closed),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_year_update
AFTER UPDATE ON fiscal_year
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_year', NEW.year_id, 'Update',
        json_object('name', OLD.name, 'start_date', OLD.start_date, 'end_date', OLD.end_date,
                    'is_year_closed', OLD.is_year_closed, 'closed_at', OLD.closed_at, 'closed_by', OLD.closed_by),
        json_object('name', NEW.name, 'start_date', NEW.start_date, 'end_date', NEW.end_date,
                    'is_year_closed', NEW.is_year_closed, 'closed_at', NEW.closed_at, 'closed_by', NEW.closed_by),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_year_delete
AFTER DELETE ON fiscal_year
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_year', OLD.year_id, 'Delete',
        json_object('name', OLD.name, 'start_date', OLD.start_date, 'end_date', OLD.end_date), NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_period_close_check_update
AFTER UPDATE ON period_close_check
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'period_close_check', NEW.rowid, 'Update',
        json_object('check_code', OLD.check_code, 'mode', OLD.mode),
        json_object('check_code', NEW.check_code, 'mode', NEW.mode),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

-- 2.5 step 1b: audit rows for chain keys and checkpoints (a checkpoint's chain head is thereby in audit_log).
CREATE TRIGGER audit_ledger_chain_key_insert
AFTER INSERT ON ledger_chain_key
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'ledger_chain_key', NEW.key_id, 'Insert', NULL,
        json_object('key_id', NEW.key_id, 'fingerprint', NEW.fingerprint, 'created_at', NEW.created_at, 'created_by', NEW.created_by, 'is_active', NEW.is_active, 'retired_at', NEW.retired_at, 'retire_reason', NEW.retire_reason),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_ledger_chain_key_update
AFTER UPDATE ON ledger_chain_key
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'ledger_chain_key', NEW.key_id, 'Update',
        json_object('key_id', OLD.key_id, 'fingerprint', OLD.fingerprint, 'created_at', OLD.created_at, 'created_by', OLD.created_by, 'is_active', OLD.is_active, 'retired_at', OLD.retired_at, 'retire_reason', OLD.retire_reason),
        json_object('key_id', NEW.key_id, 'fingerprint', NEW.fingerprint, 'created_at', NEW.created_at, 'created_by', NEW.created_by, 'is_active', NEW.is_active, 'retired_at', NEW.retired_at, 'retire_reason', NEW.retire_reason),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_ledger_checkpoint_insert
AFTER INSERT ON ledger_checkpoint
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'ledger_checkpoint', NEW.checkpoint_id, 'Insert', NULL,
        json_object('checkpoint_id', NEW.checkpoint_id, 'created_at', NEW.created_at, 'created_by', NEW.created_by, 'kind', NEW.kind, 'scope', NEW.scope, 'result', NEW.result, 'through_entry_number', NEW.through_entry_number, 'chain_hash', NEW.chain_hash, 'first_broken_entry_number', NEW.first_broken_entry_number, 'key_id', NEW.key_id, 'ref_type', NEW.ref_type, 'ref_id', NEW.ref_id, 'mac', NEW.mac),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;
