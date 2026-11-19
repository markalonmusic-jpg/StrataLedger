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

    account_id       INTEGER, -- Parent General Ledger Account cross-reference link

    -- RP5: three levels (1 Division, 2 Code, 3 Sub-code). Level 1 has no parent; a deeper code's parent is one
    -- level up (trigger cost_code_parent_level_*). Postings go to active leaf codes (a service check).
    parent_id        INTEGER REFERENCES cost_code(cost_code_id),
    level            INTEGER NOT NULL DEFAULT 1 CHECK (level IN (1, 2, 3)),
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    CHECK ((level = 1) = (parent_id IS NULL))
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

    terminal_id TEXT,

    -- Replan: why a change was made (filled through audit_context by a later step; H4).
    reason TEXT
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
    -- RP4: the job's service type and current stage (replace the planned pipeline_stage).
    service_type_id       INTEGER REFERENCES service_type(service_type_id),
    service_stage_id      INTEGER REFERENCES service_stage(stage_id),
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
    -- Step 7 (B4, B6, CB1, RP11): the date applied (cash basis and the closed-period check use it), the credit memo
    -- applied as the source instead of a payment, who applied it, and the one-time release when the source is voided.
    applied_date TEXT NOT NULL CHECK (applied_date IS date(applied_date)),
    credit_memo_id INTEGER REFERENCES invoice(invoice_id),
    created_by INTEGER,
    created_at TEXT,
    released_at TEXT,
    released_by INTEGER,
    release_reason TEXT,
    -- R58: the zero-net application entry posted when this allocation applied an already-posted payment or credit
    -- memo; a release posts its opposite. NULL for an allocation made while the source was a draft.
    application_entry_id INTEGER UNIQUE REFERENCES journal_entry(entry_id),
    CHECK (typeof(amount_applied_cents) = 'integer'),
    CONSTRAINT allocation_amount_positive CHECK (amount_applied_cents > 0),
    -- 2.5: an allocation names exactly one document, an invoice or a deferral.
    CONSTRAINT allocation_one_target CHECK ((invoice_id IS NULL) <> (deferral_id IS NULL)),
    -- Step 7: exactly one source, a payment or a credit memo.
    CONSTRAINT allocation_one_source CHECK ((payment_id IS NULL) <> (credit_memo_id IS NULL)),
    CONSTRAINT allocation_release_complete CHECK (
        (released_at IS NULL) = (released_by IS NULL) AND (released_at IS NULL) = (release_reason IS NULL))
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

-- HA6: each applied add-on migration file's SHA-256 (line endings ignored), checked like the baseline's hash.
CREATE TABLE addon_schema_version (
    addon_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
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
    -- RP2: the entity the line belongs to (NULL = the file's own company) and its clearing group. Both are set
    -- at save or post time, frozen after posting (journal_line_lock_update_posted) and sealed by the chain.
    entity_id INTEGER REFERENCES company_entity(entity_id),
    clearing_id INTEGER,
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
    is_tax_strategy_only INTEGER NOT NULL DEFAULT 0 CHECK (is_tax_strategy_only IN (0, 1)),
    -- RP2: the account keeps open items by clearing group (AR, AP, GRNI, clearing accounts).
    track_clearing_id INTEGER NOT NULL DEFAULT 0 CHECK (track_clearing_id IN (0, 1))
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
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Sent', 'Paid', 'Void', 'Covered by advance', 'In pay run')),
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
    -- Decision 1.3: a bill's or vendor credit's internal voucher number (VCH-...), from voucher_sequence.
    voucher_number TEXT CHECK (voucher_number IS NULL OR (ledger_side = 'Purchase' AND voucher_number GLOB 'VCH-*')),
    -- Editable posted documents (docs/design.md section 4): the revision and the document it supersedes.
    revision_no INTEGER NOT NULL DEFAULT 1 CHECK (typeof(revision_no) = 'integer' AND revision_no >= 1),
    supersedes_id INTEGER REFERENCES invoice(invoice_id),
    sent_at TEXT,
    sent_to TEXT,
    void_reason TEXT,
    memo TEXT,
    is_opening INTEGER NOT NULL DEFAULT 0 CHECK (is_opening IN (0, 1)),
    payment_term_id INTEGER REFERENCES payment_term(term_id),
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
    rounding_variance_acct_id INTEGER REFERENCES account(account_id),
    -- Control (docs/design.md section 9): OFF lets a posted document be edited by reverse-and-repost.
    lock_documents_after_posting INTEGER NOT NULL DEFAULT 0 CHECK (lock_documents_after_posting IN (0, 1)));

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
    -- Replan (2026-11-16): customer type and names, tax exemption, bank payee id (RP1: no routing or account
    -- numbers are ever stored), memo and payment terms.
    , customer_type TEXT CHECK (customer_type IS NULL OR customer_type IN ('Individual', 'Business'))
    , first_name TEXT, last_name TEXT
    , tax_exempt_status TEXT NOT NULL DEFAULT 'Taxable' CHECK (tax_exempt_status IN ('Taxable', 'Exempt'))
    , exemption_reason TEXT, exemption_cert_no TEXT
    , exemption_expires_at TEXT CHECK (exemption_expires_at IS date(exemption_expires_at))
    , bank_details_on_file INTEGER NOT NULL DEFAULT 0 CHECK (bank_details_on_file IN (0, 1))
    , bank_payee_id TEXT
    , memo TEXT
    , payment_term_id INTEGER REFERENCES payment_term(term_id)
    -- 004: ISO dates and 0/1 flags
    , CHECK (is_customer IN (0, 1))
    , CHECK (is_vendor IN (0, 1))
    , CHECK (is_employee IN (0, 1))
    , CHECK (is_active IN (0, 1))
    , CHECK (is_customer = 0 OR customer_code IS NOT NULL)
    , CHECK (is_vendor = 0 OR vendor_code IS NOT NULL)
    , CHECK (tax_exempt_status = 'Exempt'
             OR (exemption_reason IS NULL AND exemption_cert_no IS NULL AND exemption_expires_at IS NULL))
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
    -- 2.5 step 4 (R15): SHA-256 of the document's canonical form when it was submitted (for a journal entry, the
    -- form ledger_chain seals). Posting refuses unless it still matches; a rejected entry is resubmitted only with
    -- a new digest. Required for journal entries; other documents add it when their services are built.
    document_digest TEXT CHECK (document_digest IS NULL
                                OR (length(document_digest) = 64 AND document_digest NOT GLOB '*[^0-9a-f]*')),
    CHECK ((status = 'Pending') = (completed_at IS NULL)),
    CHECK (record_type <> 'journal_entry' OR document_digest IS NOT NULL)
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
    ('addon.manage', 'Company', 'Turn add-ons on and off', 1),
    ('fields.manage', 'Company', 'Define custom fields', 1),
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
    document_type TEXT PRIMARY KEY CHECK (document_type IN ('Bill', 'Payment', 'Purchase order', 'Subcontract', 'Pay application', 'Import batch', 'Asset disposal', 'Estimate', 'Change order', 'Contract', 'Invoice', 'Credit Memo', 'Vendor credit', 'Pay run')),
    requires_approval INTEGER NOT NULL DEFAULT 0 CHECK (requires_approval IN (0, 1))
);

INSERT INTO document_approval_setting (document_type) VALUES
    ('Bill'), ('Payment'), ('Purchase order'), ('Subcontract'), ('Pay application'),
    ('Import batch'), ('Asset disposal'), ('Estimate'), ('Change order'), ('Contract'),
    -- RP9: every approval toggle lives here, all OFF by default (1.6).
    ('Invoice'), ('Credit Memo'), ('Vendor credit'), ('Pay run');

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
        -- Pay Run (docs/design.md section 6): an approved run locks the bill; paying it or removing it moves it on.
        OR (OLD.status = 'Sent' AND NEW.status = 'In pay run' AND OLD.invoice_type = 'Bill')
        OR (OLD.status = 'In pay run' AND NEW.status IN ('Paid', 'Sent'))
    ) THEN RAISE(ABORT, 'Invoice status move not allowed (Draft -> Sent -> Paid/Void; Paid -> Sent; Sent <-> In pay run -> Paid)') END;
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

-- RP11: allocations of a posted payment or credit memo are never deleted; voiding the source releases each
-- allocation once (released_at, released_by, release_reason), and only after the source's entry is voided.
-- Allocations of a draft source stay editable.
CREATE TRIGGER payment_allocation_lock_delete
BEFORE DELETE ON payment_allocation
WHEN EXISTS (SELECT 1 FROM payment WHERE payment_id = OLD.payment_id AND entry_id IS NOT NULL)
  OR EXISTS (SELECT 1 FROM invoice WHERE invoice_id = OLD.credit_memo_id AND entry_id IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'Allocations of a posted payment or credit memo are released, never deleted'); END;

CREATE TRIGGER payment_allocation_lock_update
BEFORE UPDATE ON payment_allocation
WHEN (EXISTS (SELECT 1 FROM payment WHERE payment_id IN (OLD.payment_id, NEW.payment_id) AND entry_id IS NOT NULL)
   OR EXISTS (SELECT 1 FROM invoice WHERE invoice_id IN (OLD.credit_memo_id, NEW.credit_memo_id)
              AND entry_id IS NOT NULL))
 AND NOT (
        OLD.released_at IS NULL AND NEW.released_at IS NOT NULL
        AND NEW.allocation_id IS OLD.allocation_id
        AND NEW.payment_id IS OLD.payment_id
        AND NEW.credit_memo_id IS OLD.credit_memo_id
        AND NEW.invoice_id IS OLD.invoice_id
        AND NEW.deferral_id IS OLD.deferral_id
        AND NEW.amount_applied_cents IS OLD.amount_applied_cents
        AND NEW.applied_date IS OLD.applied_date
        AND NEW.created_by IS OLD.created_by
        AND NEW.created_at IS OLD.created_at
        AND NEW.application_entry_id IS OLD.application_entry_id
        AND (EXISTS (SELECT 1 FROM payment AS p JOIN journal_entry AS e ON e.entry_id = p.entry_id
                     WHERE p.payment_id = OLD.payment_id AND e.is_void = 1)
          OR EXISTS (SELECT 1 FROM invoice AS i JOIN journal_entry AS e ON e.entry_id = i.entry_id
                     WHERE i.invoice_id = OLD.credit_memo_id AND e.is_void = 1))
 )
BEGIN SELECT RAISE(ABORT, 'Allocations of a posted payment or credit memo cannot be changed; void the source to release them'); END;

CREATE TRIGGER payment_allocation_no_voided_credit_memo
BEFORE INSERT ON payment_allocation
WHEN EXISTS (SELECT 1 FROM invoice AS i JOIN journal_entry AS e ON e.entry_id = i.entry_id
             WHERE i.invoice_id = NEW.credit_memo_id AND e.is_void = 1)
BEGIN SELECT RAISE(ABORT, 'A voided credit memo cannot be applied'); END;

-- R56: a sales credit memo applies to invoices, a vendor credit (a Purchase credit memo) to bills; the payments
-- service checks the side, the schema that the source is a credit memo.
CREATE TRIGGER payment_allocation_credit_memo_source_insert
BEFORE INSERT ON payment_allocation
WHEN NEW.credit_memo_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM invoice WHERE invoice_id = NEW.credit_memo_id AND invoice_type = 'Credit Memo')
BEGIN SELECT RAISE(ABORT, 'A credit memo source must be a credit memo or vendor credit'); END;

CREATE TRIGGER payment_allocation_credit_memo_source_update
BEFORE UPDATE OF credit_memo_id ON payment_allocation
WHEN NEW.credit_memo_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM invoice WHERE invoice_id = NEW.credit_memo_id AND invoice_type = 'Credit Memo')
BEGIN SELECT RAISE(ABORT, 'A credit memo source must be a credit memo or vendor credit'); END;

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
        AND NEW.entity_id IS OLD.entity_id
        AND NEW.clearing_id IS OLD.clearing_id
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
        AND NEW.voucher_number IS OLD.voucher_number
        AND NEW.revision_no IS OLD.revision_no
        AND NEW.supersedes_id IS OLD.supersedes_id
        AND NEW.memo IS OLD.memo
        AND NEW.is_opening IS OLD.is_opening
        AND NEW.payment_term_id IS OLD.payment_term_id
        -- Recorded once after the document leaves Draft: when and to whom it was sent, and why it was voided.
        AND (NEW.sent_at IS OLD.sent_at OR OLD.sent_at IS NULL)
        AND (NEW.sent_to IS OLD.sent_to OR OLD.sent_to IS NULL)
        AND (NEW.void_reason IS OLD.void_reason OR OLD.void_reason IS NULL)
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
                    'is_rounding_adjustment', l.is_rounding_adjustment,
                    'entity_id', l.entity_id,
                    'clearing_id', l.clearing_id))
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
            'subtype', NEW.subtype,
            'normal_balance', NEW.normal_balance,
            'is_tax_strategy_only', NEW.is_tax_strategy_only,
            'track_clearing_id', NEW.track_clearing_id),
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
            'subtype', OLD.subtype,
            'normal_balance', OLD.normal_balance,
            'is_tax_strategy_only', OLD.is_tax_strategy_only,
            'track_clearing_id', OLD.track_clearing_id),
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
            'subtype', NEW.subtype,
            'normal_balance', NEW.normal_balance,
            'is_tax_strategy_only', NEW.is_tax_strategy_only,
            'track_clearing_id', NEW.track_clearing_id),
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
            'subtype', OLD.subtype,
            'normal_balance', OLD.normal_balance,
            'is_tax_strategy_only', OLD.is_tax_strategy_only,
            'track_clearing_id', OLD.track_clearing_id),
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
            'sequence_number', NEW.sequence_number,
            'voucher_number', NEW.voucher_number,
            'revision_no', NEW.revision_no,
            'supersedes_id', NEW.supersedes_id,
            'sent_at', NEW.sent_at,
            'sent_to', NEW.sent_to,
            'void_reason', NEW.void_reason,
            'memo', NEW.memo,
            'is_opening', NEW.is_opening,
            'payment_term_id', NEW.payment_term_id),
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
            'sequence_number', OLD.sequence_number,
            'voucher_number', OLD.voucher_number,
            'revision_no', OLD.revision_no,
            'supersedes_id', OLD.supersedes_id,
            'sent_at', OLD.sent_at,
            'sent_to', OLD.sent_to,
            'void_reason', OLD.void_reason,
            'memo', OLD.memo,
            'is_opening', OLD.is_opening,
            'payment_term_id', OLD.payment_term_id),
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
            'sequence_number', NEW.sequence_number,
            'voucher_number', NEW.voucher_number,
            'revision_no', NEW.revision_no,
            'supersedes_id', NEW.supersedes_id,
            'sent_at', NEW.sent_at,
            'sent_to', NEW.sent_to,
            'void_reason', NEW.void_reason,
            'memo', NEW.memo,
            'is_opening', NEW.is_opening,
            'payment_term_id', NEW.payment_term_id),
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
            'sequence_number', OLD.sequence_number,
            'voucher_number', OLD.voucher_number,
            'revision_no', OLD.revision_no,
            'supersedes_id', OLD.supersedes_id,
            'sent_at', OLD.sent_at,
            'sent_to', OLD.sent_to,
            'void_reason', OLD.void_reason,
            'memo', OLD.memo,
            'is_opening', OLD.is_opening,
            'payment_term_id', OLD.payment_term_id),
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
            'amount_applied_cents', NEW.amount_applied_cents,
            'applied_date', NEW.applied_date,
            'credit_memo_id', NEW.credit_memo_id,
            'created_by', NEW.created_by,
            'created_at', NEW.created_at,
            'released_at', NEW.released_at,
            'released_by', NEW.released_by,
            'release_reason', NEW.release_reason,
            'application_entry_id', NEW.application_entry_id),
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
            'amount_applied_cents', OLD.amount_applied_cents,
            'applied_date', OLD.applied_date,
            'credit_memo_id', OLD.credit_memo_id,
            'created_by', OLD.created_by,
            'created_at', OLD.created_at,
            'released_at', OLD.released_at,
            'released_by', OLD.released_by,
            'release_reason', OLD.release_reason,
            'application_entry_id', OLD.application_entry_id),
        json_object(
            'allocation_id', NEW.allocation_id,
            'payment_id', NEW.payment_id,
            'invoice_id', NEW.invoice_id,
            'deferral_id', NEW.deferral_id,
            'amount_applied_cents', NEW.amount_applied_cents,
            'applied_date', NEW.applied_date,
            'credit_memo_id', NEW.credit_memo_id,
            'created_by', NEW.created_by,
            'created_at', NEW.created_at,
            'released_at', NEW.released_at,
            'released_by', NEW.released_by,
            'release_reason', NEW.release_reason,
            'application_entry_id', NEW.application_entry_id),
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
            'amount_applied_cents', OLD.amount_applied_cents,
            'applied_date', OLD.applied_date,
            'credit_memo_id', OLD.credit_memo_id,
            'created_by', OLD.created_by,
            'created_at', OLD.created_at,
            'released_at', OLD.released_at,
            'released_by', OLD.released_by,
            'release_reason', OLD.release_reason,
            'application_entry_id', OLD.application_entry_id),
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

-- HA9 (2026-11-17): add-on migration history is audit-logged like any table.
CREATE TRIGGER audit_addon_schema_version_insert
AFTER INSERT ON addon_schema_version
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'addon_schema_version', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'addon_key', NEW.addon_key,
            'version', NEW.version,
            'sha256', NEW.sha256),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_addon_schema_version_update
AFTER UPDATE ON addon_schema_version
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'addon_schema_version', NEW.rowid,
        'Update',
        json_object(
            'addon_key', OLD.addon_key,
            'version', OLD.version,
            'sha256', OLD.sha256),
        json_object(
            'addon_key', NEW.addon_key,
            'version', NEW.version,
            'sha256', NEW.sha256),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_addon_schema_version_delete
AFTER DELETE ON addon_schema_version
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'addon_schema_version', OLD.rowid,
        'Delete',
        json_object(
            'addon_key', OLD.addon_key,
            'version', OLD.version,
            'sha256', OLD.sha256),
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

-- 2.5 step 4 (R16): approval requests are part of the audit trail. A request is never deleted (a rejected or
-- cancelled one stays); which status changes are allowed is a service rule (H4). approval_action is
-- append-only, so only its insert is audited.
CREATE TRIGGER approval_request_no_delete
BEFORE DELETE ON approval_request
BEGIN
    SELECT RAISE(ABORT, 'approval_request rows are never deleted');
END;

CREATE TRIGGER audit_approval_request_insert
AFTER INSERT ON approval_request
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_request', NEW.request_id,
        'Insert',
        NULL,
        json_object(
            'request_id', NEW.request_id,
            'document_type', NEW.document_type,
            'record_type', NEW.record_type,
            'record_id', NEW.record_id,
            'amount_cents', NEW.amount_cents,
            'policy_id', NEW.policy_id,
            'created_by', NEW.created_by,
            'project_id', NEW.project_id,
            'chain_json', NEW.chain_json,
            'status', NEW.status,
            'submitted_by', NEW.submitted_by,
            'submitted_at', NEW.submitted_at,
            'completed_at', NEW.completed_at,
            'document_digest', NEW.document_digest),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_request_update
AFTER UPDATE ON approval_request
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_request', NEW.request_id,
        'Update',
        json_object(
            'request_id', OLD.request_id,
            'document_type', OLD.document_type,
            'record_type', OLD.record_type,
            'record_id', OLD.record_id,
            'amount_cents', OLD.amount_cents,
            'policy_id', OLD.policy_id,
            'created_by', OLD.created_by,
            'project_id', OLD.project_id,
            'chain_json', OLD.chain_json,
            'status', OLD.status,
            'submitted_by', OLD.submitted_by,
            'submitted_at', OLD.submitted_at,
            'completed_at', OLD.completed_at,
            'document_digest', OLD.document_digest),
        json_object(
            'request_id', NEW.request_id,
            'document_type', NEW.document_type,
            'record_type', NEW.record_type,
            'record_id', NEW.record_id,
            'amount_cents', NEW.amount_cents,
            'policy_id', NEW.policy_id,
            'created_by', NEW.created_by,
            'project_id', NEW.project_id,
            'chain_json', NEW.chain_json,
            'status', NEW.status,
            'submitted_by', NEW.submitted_by,
            'submitted_at', NEW.submitted_at,
            'completed_at', NEW.completed_at,
            'document_digest', NEW.document_digest),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_approval_action_insert
AFTER INSERT ON approval_action
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'approval_action', NEW.action_id,
        'Insert',
        NULL,
        json_object(
            'action_id', NEW.action_id,
            'request_id', NEW.request_id,
            'step_no', NEW.step_no,
            'role_code', NEW.role_code,
            'user_id', NEW.user_id,
            'decision', NEW.decision,
            'reason', NEW.reason,
            'self_approved', NEW.self_approved,
            'acted_at', NEW.acted_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
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
            'rounding_variance_acct_id', NEW.rounding_variance_acct_id,
            'lock_documents_after_posting', NEW.lock_documents_after_posting),
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
            'rounding_variance_acct_id', OLD.rounding_variance_acct_id,
            'lock_documents_after_posting', OLD.lock_documents_after_posting),
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
            'rounding_variance_acct_id', NEW.rounding_variance_acct_id,
            'lock_documents_after_posting', NEW.lock_documents_after_posting),
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


-- ===========================================================================
-- Consolidated replan update, STOP 1 (decisions RP1-RP11; docs/design.md section 10)
-- ===========================================================================

-- Entities in one file (rule 3): a parent's subsidiaries as entities, for consolidation. NULL entity_id on a
-- journal line means the file's own company.
CREATE TABLE company_entity (
    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_entity_id INTEGER REFERENCES company_entity(entity_id),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    is_eliminations INTEGER NOT NULL DEFAULT 0 CHECK (is_eliminations IN (0, 1)),
    created_at TEXT
);

-- RP2: open items per account are the (account_id, clearing_id) groups that do not net to zero.
CREATE INDEX idx_journal_line_account_clearing ON journal_line (account_id, clearing_id) WHERE clearing_id IS NOT NULL;

CREATE TABLE payment_term (
    term_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    days_due INTEGER NOT NULL DEFAULT 0 CHECK (typeof(days_due) = 'integer' AND days_due >= 0),
    discount_percent REAL CHECK (discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)),
    discount_days INTEGER CHECK (discount_days IS NULL OR (typeof(discount_days) = 'integer' AND discount_days >= 0)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE contact_site (
    site_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contact(contact_id),
    name TEXT NOT NULL,
    street TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    country TEXT,
    is_billing INTEGER NOT NULL DEFAULT 0 CHECK (is_billing IN (0, 1)),
    is_shipping INTEGER NOT NULL DEFAULT 0 CHECK (is_shipping IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    memo TEXT
);

CREATE UNIQUE INDEX invoice_voucher_number_unique ON invoice (voucher_number) WHERE voucher_number IS NOT NULL;

-- A period can be locked per area while the rest of the period stays open.
CREATE TABLE fiscal_period_lock (
    lock_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL REFERENCES fiscal_period(period_id),
    area TEXT NOT NULL CHECK (area IN ('Sales', 'Purchases', 'Banking', 'Payroll', 'Inventory', 'Journal')),
    is_locked INTEGER NOT NULL DEFAULT 1 CHECK (is_locked IN (0, 1)),
    locked_by INTEGER,
    locked_at TEXT,
    reason TEXT,
    UNIQUE (period_id, area)
);

CREATE TRIGGER cost_code_parent_level_insert
BEFORE INSERT ON cost_code
WHEN NEW.parent_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM cost_code WHERE cost_code_id = NEW.parent_id AND level = NEW.level - 1)
BEGIN SELECT RAISE(ABORT, 'A cost code''s parent must be one level up'); END;

CREATE TRIGGER cost_code_parent_level_update
BEFORE UPDATE OF parent_id, level ON cost_code
BEGIN
    SELECT CASE WHEN NEW.parent_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM cost_code WHERE cost_code_id = NEW.parent_id AND level = NEW.level - 1)
    THEN RAISE(ABORT, 'A cost code''s parent must be one level up') END;
    SELECT CASE WHEN NEW.level IS NOT OLD.level AND EXISTS (
        SELECT 1 FROM cost_code WHERE parent_id = NEW.cost_code_id)
    THEN RAISE(ABORT, 'A cost code with sub-codes cannot change level') END;
END;

-- RP4: service types and their stages replace pipeline_stage; triggers run in services (H4), once per event.
CREATE TABLE service_type (
    service_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE service_stage (
    stage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_type_id INTEGER NOT NULL REFERENCES service_type(service_type_id),
    phase TEXT NOT NULL CHECK (phase IN ('Sales', 'Delivery')),
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    allows_costs INTEGER NOT NULL DEFAULT 0 CHECK (allows_costs IN (0, 1)),
    allows_billing INTEGER NOT NULL DEFAULT 0 CHECK (allows_billing IN (0, 1)),
    is_closed_stage INTEGER NOT NULL DEFAULT 0 CHECK (is_closed_stage IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (service_type_id, name)
);

CREATE TABLE stage_trigger (
    trigger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage_id INTEGER NOT NULL REFERENCES service_stage(stage_id),
    event TEXT NOT NULL CHECK (event IN ('Enter', 'Leave')),
    action TEXT NOT NULL,
    config_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE stage_trigger_run (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_id INTEGER NOT NULL REFERENCES stage_trigger(trigger_id),
    record_type TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    event_key TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('Done', 'Skipped', 'Failed')),
    message TEXT,
    UNIQUE (trigger_id, record_type, record_id, event_key)
);

CREATE TRIGGER stage_trigger_run_no_update
BEFORE UPDATE ON stage_trigger_run
BEGIN SELECT RAISE(ABORT, 'Trigger runs are a permanent record'); END;

CREATE TRIGGER stage_trigger_run_no_delete
BEFORE DELETE ON stage_trigger_run
BEGIN SELECT RAISE(ABORT, 'Trigger runs are a permanent record'); END;

-- Pay Run (docs/design.md section 6): approve the run, then complete each line with the date paid and reference.
CREATE TABLE pay_run (
    pay_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_number TEXT NOT NULL UNIQUE,
    bank_account_id INTEGER NOT NULL REFERENCES bank_account(bank_account_id),
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Approved', 'Completed', 'Cancelled')),
    scheduled_date TEXT CHECK (scheduled_date IS date(scheduled_date)),
    memo TEXT,
    created_by INTEGER,
    created_at TEXT,
    approved_by INTEGER,
    approved_at TEXT
);

CREATE TABLE pay_run_line (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pay_run_id INTEGER NOT NULL REFERENCES pay_run(pay_run_id),
    invoice_id INTEGER NOT NULL REFERENCES invoice(invoice_id),
    amount_cents INTEGER NOT NULL CHECK (typeof(amount_cents) = 'integer' AND amount_cents > 0),
    status TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Paid', 'Removed')),
    date_paid TEXT CHECK (date_paid IS date(date_paid)),
    payment_ref TEXT,
    payment_id INTEGER REFERENCES payment(payment_id),
    completed_by INTEGER,
    completed_at TEXT,
    UNIQUE (pay_run_id, invoice_id),
    CHECK ((status = 'Paid') = (payment_id IS NOT NULL AND date_paid IS NOT NULL AND payment_ref IS NOT NULL))
);

CREATE TRIGGER pay_run_line_bill_insert
BEFORE INSERT ON pay_run_line
WHEN NOT EXISTS (SELECT 1 FROM invoice WHERE invoice_id = NEW.invoice_id AND invoice_type = 'Bill')
BEGIN SELECT RAISE(ABORT, 'A pay run pays bills only'); END;

CREATE TRIGGER pay_run_line_bill_update
BEFORE UPDATE OF invoice_id ON pay_run_line
WHEN NOT EXISTS (SELECT 1 FROM invoice WHERE invoice_id = NEW.invoice_id AND invoice_type = 'Bill')
BEGIN SELECT RAISE(ABORT, 'A pay run pays bills only'); END;

-- One staging table for bank and card lines from files and feeds (B11, B11a); amounts are signed
-- (+ money in, - money out). A line of a completed reconciliation cannot change.
CREATE TABLE bank_statement_line (
    statement_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id INTEGER NOT NULL REFERENCES bank_account(bank_account_id),
    source TEXT NOT NULL CHECK (source IN ('File', 'Feed', 'Manual')),
    import_batch_id INTEGER REFERENCES import_batch(batch_id),
    external_id TEXT,
    posted_date TEXT NOT NULL CHECK (posted_date IS date(posted_date)),
    description TEXT,
    amount_cents INTEGER NOT NULL CHECK (typeof(amount_cents) = 'integer'),
    status TEXT NOT NULL DEFAULT 'Unmatched' CHECK (status IN ('Unmatched', 'Matched', 'Excluded')),
    recon_id INTEGER REFERENCES bank_reconciliation(recon_id),
    created_at TEXT
);

CREATE UNIQUE INDEX bank_statement_line_external_unique
    ON bank_statement_line (bank_account_id, external_id) WHERE external_id IS NOT NULL;

CREATE TRIGGER bank_statement_line_recon_lock
BEFORE UPDATE ON bank_statement_line
WHEN EXISTS (SELECT 1 FROM bank_reconciliation
             WHERE recon_id IN (OLD.recon_id, NEW.recon_id) AND is_complete = 1)
BEGIN SELECT RAISE(ABORT, 'Lines of a completed bank reconciliation cannot change'); END;

CREATE TRIGGER bank_statement_line_recon_lock_delete
BEFORE DELETE ON bank_statement_line
WHEN EXISTS (SELECT 1 FROM bank_reconciliation WHERE recon_id = OLD.recon_id AND is_complete = 1)
BEGIN SELECT RAISE(ABORT, 'Lines of a completed bank reconciliation cannot change'); END;

-- A match is released once, never deleted, so the history shows what was matched and undone.
CREATE TABLE bank_statement_match (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_line_id INTEGER NOT NULL REFERENCES bank_statement_line(statement_line_id),
    payment_id INTEGER REFERENCES payment(payment_id),
    journal_line_id INTEGER REFERENCES journal_line(line_id),
    amount_cents INTEGER NOT NULL CHECK (typeof(amount_cents) = 'integer'),
    matched_by INTEGER,
    matched_at TEXT,
    released_at TEXT,
    released_by INTEGER,
    release_reason TEXT,
    CHECK ((payment_id IS NULL) <> (journal_line_id IS NULL)),
    CHECK ((released_at IS NULL) = (released_by IS NULL) AND (released_at IS NULL) = (release_reason IS NULL))
);

CREATE TRIGGER bank_statement_match_release_only
BEFORE UPDATE ON bank_statement_match
WHEN NOT (
        OLD.released_at IS NULL AND NEW.released_at IS NOT NULL
        AND NEW.match_id IS OLD.match_id
        AND NEW.statement_line_id IS OLD.statement_line_id
        AND NEW.payment_id IS OLD.payment_id
        AND NEW.journal_line_id IS OLD.journal_line_id
        AND NEW.amount_cents IS OLD.amount_cents
        AND NEW.matched_by IS OLD.matched_by
        AND NEW.matched_at IS OLD.matched_at
)
BEGIN SELECT RAISE(ABORT, 'A bank match cannot be changed; release it instead'); END;

CREATE TRIGGER bank_statement_match_no_delete
BEFORE DELETE ON bank_statement_match
BEGIN SELECT RAISE(ABORT, 'A bank match is released, never deleted'); END;

-- Close checklist (a block only when the control is on; is_blocking defaults to 0).
CREATE TABLE close_task (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL REFERENCES fiscal_period(period_id),
    title TEXT NOT NULL,
    area TEXT CHECK (area IS NULL OR area IN ('Sales', 'Purchases', 'Banking', 'Payroll', 'Inventory', 'Journal')),
    assignee_user_id INTEGER,
    due_date TEXT CHECK (due_date IS date(due_date)),
    status TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Done', 'Skipped')),
    is_blocking INTEGER NOT NULL DEFAULT 0 CHECK (is_blocking IN (0, 1)),
    completed_by INTEGER,
    completed_at TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE close_task_dependency (
    task_id INTEGER NOT NULL REFERENCES close_task(task_id),
    depends_on_task_id INTEGER NOT NULL REFERENCES close_task(task_id),
    PRIMARY KEY (task_id, depends_on_task_id),
    CHECK (task_id <> depends_on_task_id)
);

-- Custom fields: one typed value per field and record; the column used matches the field's type.
CREATE TABLE custom_field_def (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type TEXT NOT NULL CHECK (record_type IN ('Contact', 'Invoice', 'Bill', 'Project', 'Estimate')),
    field_key TEXT NOT NULL,
    label TEXT NOT NULL,
    data_type TEXT NOT NULL CHECK (data_type IN ('Text', 'Number', 'Money', 'Date', 'Yes/No', 'Choice')),
    choices_json TEXT,
    is_required INTEGER NOT NULL DEFAULT 0 CHECK (is_required IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (record_type, field_key)
);

CREATE TABLE custom_field_value (
    value_id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER NOT NULL REFERENCES custom_field_def(field_id),
    record_id INTEGER NOT NULL,
    value_text TEXT,
    value_number REAL,
    value_cents INTEGER CHECK (value_cents IS NULL OR typeof(value_cents) = 'integer'),
    value_date TEXT CHECK (value_date IS date(value_date)),
    value_bool INTEGER CHECK (value_bool IS NULL OR value_bool IN (0, 1)),
    UNIQUE (field_id, record_id),
    CHECK ((value_text IS NOT NULL) + (value_number IS NOT NULL) + (value_cents IS NOT NULL)
           + (value_date IS NOT NULL) + (value_bool IS NOT NULL) <= 1)
);

CREATE TRIGGER custom_field_value_type_insert
BEFORE INSERT ON custom_field_value
WHEN NOT EXISTS (
    SELECT 1 FROM custom_field_def AS d WHERE d.field_id = NEW.field_id AND (
        (NEW.value_text IS NULL AND NEW.value_number IS NULL AND NEW.value_cents IS NULL
         AND NEW.value_date IS NULL AND NEW.value_bool IS NULL)
        OR (d.data_type IN ('Text', 'Choice') AND NEW.value_text IS NOT NULL)
        OR (d.data_type = 'Number' AND NEW.value_number IS NOT NULL)
        OR (d.data_type = 'Money' AND NEW.value_cents IS NOT NULL)
        OR (d.data_type = 'Date' AND NEW.value_date IS NOT NULL)
        OR (d.data_type = 'Yes/No' AND NEW.value_bool IS NOT NULL)))
BEGIN SELECT RAISE(ABORT, 'A custom field value must use the column of its field''s type'); END;

CREATE TRIGGER custom_field_value_type_update
BEFORE UPDATE ON custom_field_value
WHEN NOT EXISTS (
    SELECT 1 FROM custom_field_def AS d WHERE d.field_id = NEW.field_id AND (
        (NEW.value_text IS NULL AND NEW.value_number IS NULL AND NEW.value_cents IS NULL
         AND NEW.value_date IS NULL AND NEW.value_bool IS NULL)
        OR (d.data_type IN ('Text', 'Choice') AND NEW.value_text IS NOT NULL)
        OR (d.data_type = 'Number' AND NEW.value_number IS NOT NULL)
        OR (d.data_type = 'Money' AND NEW.value_cents IS NOT NULL)
        OR (d.data_type = 'Date' AND NEW.value_date IS NOT NULL)
        OR (d.data_type = 'Yes/No' AND NEW.value_bool IS NOT NULL)))
BEGIN SELECT RAISE(ABORT, 'A custom field value must use the column of its field''s type'); END;

-- Per-user list settings (user ids are master ids, plain integers; section 4).
CREATE TABLE user_list_pref (
    user_id INTEGER NOT NULL,
    list_key TEXT NOT NULL,
    columns_json TEXT,
    sort_json TEXT,
    page_size INTEGER CHECK (page_size IS NULL OR (typeof(page_size) = 'integer' AND page_size > 0)),
    PRIMARY KEY (user_id, list_key)
);

CREATE TABLE saved_view (
    view_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    list_key TEXT NOT NULL,
    name TEXT NOT NULL,
    filters_json TEXT,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    UNIQUE (user_id, list_key, name)
);

CREATE TABLE alert_dismissal (
    user_id INTEGER NOT NULL,
    alert_key TEXT NOT NULL,
    dismissed_at TEXT NOT NULL,
    until_at TEXT,
    PRIMARY KEY (user_id, alert_key)
);

-- A contact's tax id and exemption certificate number reach the audit log as their last four characters only
-- (K4: tax ids are masked outside the contact record).
CREATE TRIGGER audit_contact_insert
AFTER INSERT ON contact
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'contact', NEW.contact_id,
        'Insert',
        NULL,
        json_object(
            'contact_id', NEW.contact_id,
            'name', NEW.name,
            'bir_registered_name', NEW.bir_registered_name,
            'entity_type', NEW.entity_type,
            'is_customer', NEW.is_customer,
            'is_vendor', NEW.is_vendor,
            'is_employee', NEW.is_employee,
            'email', NEW.email,
            'phone', NEW.phone,
            'address', NEW.address,
            'tax_id_last4', substr(NEW.tax_id, -4),
            'is_active', NEW.is_active,
            'mailing_street', NEW.mailing_street,
            'mailing_city', NEW.mailing_city,
            'mailing_state', NEW.mailing_state,
            'mailing_zip', NEW.mailing_zip,
            'customer_code', NEW.customer_code,
            'vendor_code', NEW.vendor_code,
            'customer_type', NEW.customer_type,
            'first_name', NEW.first_name,
            'last_name', NEW.last_name,
            'tax_exempt_status', NEW.tax_exempt_status,
            'exemption_reason', NEW.exemption_reason,
            'exemption_cert_no_last4', substr(NEW.exemption_cert_no, -4),
            'exemption_expires_at', NEW.exemption_expires_at,
            'bank_details_on_file', NEW.bank_details_on_file,
            'bank_payee_id', NEW.bank_payee_id,
            'memo', NEW.memo,
            'payment_term_id', NEW.payment_term_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_contact_update
AFTER UPDATE ON contact
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'contact', NEW.contact_id,
        'Update',
        json_object(
            'contact_id', OLD.contact_id,
            'name', OLD.name,
            'bir_registered_name', OLD.bir_registered_name,
            'entity_type', OLD.entity_type,
            'is_customer', OLD.is_customer,
            'is_vendor', OLD.is_vendor,
            'is_employee', OLD.is_employee,
            'email', OLD.email,
            'phone', OLD.phone,
            'address', OLD.address,
            'tax_id_last4', substr(OLD.tax_id, -4),
            'is_active', OLD.is_active,
            'mailing_street', OLD.mailing_street,
            'mailing_city', OLD.mailing_city,
            'mailing_state', OLD.mailing_state,
            'mailing_zip', OLD.mailing_zip,
            'customer_code', OLD.customer_code,
            'vendor_code', OLD.vendor_code,
            'customer_type', OLD.customer_type,
            'first_name', OLD.first_name,
            'last_name', OLD.last_name,
            'tax_exempt_status', OLD.tax_exempt_status,
            'exemption_reason', OLD.exemption_reason,
            'exemption_cert_no_last4', substr(OLD.exemption_cert_no, -4),
            'exemption_expires_at', OLD.exemption_expires_at,
            'bank_details_on_file', OLD.bank_details_on_file,
            'bank_payee_id', OLD.bank_payee_id,
            'memo', OLD.memo,
            'payment_term_id', OLD.payment_term_id),
        json_object(
            'contact_id', NEW.contact_id,
            'name', NEW.name,
            'bir_registered_name', NEW.bir_registered_name,
            'entity_type', NEW.entity_type,
            'is_customer', NEW.is_customer,
            'is_vendor', NEW.is_vendor,
            'is_employee', NEW.is_employee,
            'email', NEW.email,
            'phone', NEW.phone,
            'address', NEW.address,
            'tax_id_last4', substr(NEW.tax_id, -4),
            'is_active', NEW.is_active,
            'mailing_street', NEW.mailing_street,
            'mailing_city', NEW.mailing_city,
            'mailing_state', NEW.mailing_state,
            'mailing_zip', NEW.mailing_zip,
            'customer_code', NEW.customer_code,
            'vendor_code', NEW.vendor_code,
            'customer_type', NEW.customer_type,
            'first_name', NEW.first_name,
            'last_name', NEW.last_name,
            'tax_exempt_status', NEW.tax_exempt_status,
            'exemption_reason', NEW.exemption_reason,
            'exemption_cert_no_last4', substr(NEW.exemption_cert_no, -4),
            'exemption_expires_at', NEW.exemption_expires_at,
            'bank_details_on_file', NEW.bank_details_on_file,
            'bank_payee_id', NEW.bank_payee_id,
            'memo', NEW.memo,
            'payment_term_id', NEW.payment_term_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_contact_delete
AFTER DELETE ON contact
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'contact', OLD.contact_id,
        'Delete',
        json_object(
            'contact_id', OLD.contact_id,
            'name', OLD.name,
            'bir_registered_name', OLD.bir_registered_name,
            'entity_type', OLD.entity_type,
            'is_customer', OLD.is_customer,
            'is_vendor', OLD.is_vendor,
            'is_employee', OLD.is_employee,
            'email', OLD.email,
            'phone', OLD.phone,
            'address', OLD.address,
            'tax_id_last4', substr(OLD.tax_id, -4),
            'is_active', OLD.is_active,
            'mailing_street', OLD.mailing_street,
            'mailing_city', OLD.mailing_city,
            'mailing_state', OLD.mailing_state,
            'mailing_zip', OLD.mailing_zip,
            'customer_code', OLD.customer_code,
            'vendor_code', OLD.vendor_code,
            'customer_type', OLD.customer_type,
            'first_name', OLD.first_name,
            'last_name', OLD.last_name,
            'tax_exempt_status', OLD.tax_exempt_status,
            'exemption_reason', OLD.exemption_reason,
            'exemption_cert_no_last4', substr(OLD.exemption_cert_no, -4),
            'exemption_expires_at', OLD.exemption_expires_at,
            'bank_details_on_file', OLD.bank_details_on_file,
            'bank_payee_id', OLD.bank_payee_id,
            'memo', OLD.memo,
            'payment_term_id', OLD.payment_term_id),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_contact_site_insert
AFTER INSERT ON contact_site
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'contact_site', NEW.site_id,
        'Insert',
        NULL,
        json_object(
            'site_id', NEW.site_id,
            'contact_id', NEW.contact_id,
            'name', NEW.name,
            'street', NEW.street,
            'city', NEW.city,
            'state', NEW.state,
            'zip', NEW.zip,
            'country', NEW.country,
            'is_billing', NEW.is_billing,
            'is_shipping', NEW.is_shipping,
            'is_active', NEW.is_active,
            'memo', NEW.memo),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_contact_site_update
AFTER UPDATE ON contact_site
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'contact_site', NEW.site_id,
        'Update',
        json_object(
            'site_id', OLD.site_id,
            'contact_id', OLD.contact_id,
            'name', OLD.name,
            'street', OLD.street,
            'city', OLD.city,
            'state', OLD.state,
            'zip', OLD.zip,
            'country', OLD.country,
            'is_billing', OLD.is_billing,
            'is_shipping', OLD.is_shipping,
            'is_active', OLD.is_active,
            'memo', OLD.memo),
        json_object(
            'site_id', NEW.site_id,
            'contact_id', NEW.contact_id,
            'name', NEW.name,
            'street', NEW.street,
            'city', NEW.city,
            'state', NEW.state,
            'zip', NEW.zip,
            'country', NEW.country,
            'is_billing', NEW.is_billing,
            'is_shipping', NEW.is_shipping,
            'is_active', NEW.is_active,
            'memo', NEW.memo),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_contact_site_delete
AFTER DELETE ON contact_site
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'contact_site', OLD.site_id,
        'Delete',
        json_object(
            'site_id', OLD.site_id,
            'contact_id', OLD.contact_id,
            'name', OLD.name,
            'street', OLD.street,
            'city', OLD.city,
            'state', OLD.state,
            'zip', OLD.zip,
            'country', OLD.country,
            'is_billing', OLD.is_billing,
            'is_shipping', OLD.is_shipping,
            'is_active', OLD.is_active,
            'memo', OLD.memo),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_entity_insert
AFTER INSERT ON company_entity
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_entity', NEW.entity_id,
        'Insert',
        NULL,
        json_object(
            'entity_id', NEW.entity_id,
            'code', NEW.code,
            'name', NEW.name,
            'parent_entity_id', NEW.parent_entity_id,
            'is_active', NEW.is_active,
            'is_eliminations', NEW.is_eliminations,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_entity_update
AFTER UPDATE ON company_entity
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_entity', NEW.entity_id,
        'Update',
        json_object(
            'entity_id', OLD.entity_id,
            'code', OLD.code,
            'name', OLD.name,
            'parent_entity_id', OLD.parent_entity_id,
            'is_active', OLD.is_active,
            'is_eliminations', OLD.is_eliminations,
            'created_at', OLD.created_at),
        json_object(
            'entity_id', NEW.entity_id,
            'code', NEW.code,
            'name', NEW.name,
            'parent_entity_id', NEW.parent_entity_id,
            'is_active', NEW.is_active,
            'is_eliminations', NEW.is_eliminations,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_entity_delete
AFTER DELETE ON company_entity
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_entity', OLD.entity_id,
        'Delete',
        json_object(
            'entity_id', OLD.entity_id,
            'code', OLD.code,
            'name', OLD.name,
            'parent_entity_id', OLD.parent_entity_id,
            'is_active', OLD.is_active,
            'is_eliminations', OLD.is_eliminations,
            'created_at', OLD.created_at),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_period_lock_insert
AFTER INSERT ON fiscal_period_lock
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_period_lock', NEW.lock_id,
        'Insert',
        NULL,
        json_object(
            'lock_id', NEW.lock_id,
            'period_id', NEW.period_id,
            'area', NEW.area,
            'is_locked', NEW.is_locked,
            'locked_by', NEW.locked_by,
            'locked_at', NEW.locked_at,
            'reason', NEW.reason),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_period_lock_update
AFTER UPDATE ON fiscal_period_lock
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_period_lock', NEW.lock_id,
        'Update',
        json_object(
            'lock_id', OLD.lock_id,
            'period_id', OLD.period_id,
            'area', OLD.area,
            'is_locked', OLD.is_locked,
            'locked_by', OLD.locked_by,
            'locked_at', OLD.locked_at,
            'reason', OLD.reason),
        json_object(
            'lock_id', NEW.lock_id,
            'period_id', NEW.period_id,
            'area', NEW.area,
            'is_locked', NEW.is_locked,
            'locked_by', NEW.locked_by,
            'locked_at', NEW.locked_at,
            'reason', NEW.reason),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_fiscal_period_lock_delete
AFTER DELETE ON fiscal_period_lock
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'fiscal_period_lock', OLD.lock_id,
        'Delete',
        json_object(
            'lock_id', OLD.lock_id,
            'period_id', OLD.period_id,
            'area', OLD.area,
            'is_locked', OLD.is_locked,
            'locked_by', OLD.locked_by,
            'locked_at', OLD.locked_at,
            'reason', OLD.reason),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_cost_code_insert
AFTER INSERT ON cost_code
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'cost_code', NEW.cost_code_id,
        'Insert',
        NULL,
        json_object(
            'cost_code_id', NEW.cost_code_id,
            'code', NEW.code,
            'name', NEW.name,
            'cost_type_label', NEW.cost_type_label,
            'account_id', NEW.account_id,
            'parent_id', NEW.parent_id,
            'level', NEW.level,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_cost_code_update
AFTER UPDATE ON cost_code
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'cost_code', NEW.cost_code_id,
        'Update',
        json_object(
            'cost_code_id', OLD.cost_code_id,
            'code', OLD.code,
            'name', OLD.name,
            'cost_type_label', OLD.cost_type_label,
            'account_id', OLD.account_id,
            'parent_id', OLD.parent_id,
            'level', OLD.level,
            'is_active', OLD.is_active),
        json_object(
            'cost_code_id', NEW.cost_code_id,
            'code', NEW.code,
            'name', NEW.name,
            'cost_type_label', NEW.cost_type_label,
            'account_id', NEW.account_id,
            'parent_id', NEW.parent_id,
            'level', NEW.level,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_cost_code_delete
AFTER DELETE ON cost_code
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'cost_code', OLD.cost_code_id,
        'Delete',
        json_object(
            'cost_code_id', OLD.cost_code_id,
            'code', OLD.code,
            'name', OLD.name,
            'cost_type_label', OLD.cost_type_label,
            'account_id', OLD.account_id,
            'parent_id', OLD.parent_id,
            'level', OLD.level,
            'is_active', OLD.is_active),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_service_type_insert
AFTER INSERT ON service_type
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'service_type', NEW.service_type_id,
        'Insert',
        NULL,
        json_object(
            'service_type_id', NEW.service_type_id,
            'code', NEW.code,
            'name', NEW.name,
            'is_active', NEW.is_active,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_service_type_update
AFTER UPDATE ON service_type
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'service_type', NEW.service_type_id,
        'Update',
        json_object(
            'service_type_id', OLD.service_type_id,
            'code', OLD.code,
            'name', OLD.name,
            'is_active', OLD.is_active,
            'sort_order', OLD.sort_order),
        json_object(
            'service_type_id', NEW.service_type_id,
            'code', NEW.code,
            'name', NEW.name,
            'is_active', NEW.is_active,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_service_type_delete
AFTER DELETE ON service_type
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'service_type', OLD.service_type_id,
        'Delete',
        json_object(
            'service_type_id', OLD.service_type_id,
            'code', OLD.code,
            'name', OLD.name,
            'is_active', OLD.is_active,
            'sort_order', OLD.sort_order),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_service_stage_insert
AFTER INSERT ON service_stage
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'service_stage', NEW.stage_id,
        'Insert',
        NULL,
        json_object(
            'stage_id', NEW.stage_id,
            'service_type_id', NEW.service_type_id,
            'phase', NEW.phase,
            'name', NEW.name,
            'sort_order', NEW.sort_order,
            'allows_costs', NEW.allows_costs,
            'allows_billing', NEW.allows_billing,
            'is_closed_stage', NEW.is_closed_stage,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_service_stage_update
AFTER UPDATE ON service_stage
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'service_stage', NEW.stage_id,
        'Update',
        json_object(
            'stage_id', OLD.stage_id,
            'service_type_id', OLD.service_type_id,
            'phase', OLD.phase,
            'name', OLD.name,
            'sort_order', OLD.sort_order,
            'allows_costs', OLD.allows_costs,
            'allows_billing', OLD.allows_billing,
            'is_closed_stage', OLD.is_closed_stage,
            'is_active', OLD.is_active),
        json_object(
            'stage_id', NEW.stage_id,
            'service_type_id', NEW.service_type_id,
            'phase', NEW.phase,
            'name', NEW.name,
            'sort_order', NEW.sort_order,
            'allows_costs', NEW.allows_costs,
            'allows_billing', NEW.allows_billing,
            'is_closed_stage', NEW.is_closed_stage,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_service_stage_delete
AFTER DELETE ON service_stage
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'service_stage', OLD.stage_id,
        'Delete',
        json_object(
            'stage_id', OLD.stage_id,
            'service_type_id', OLD.service_type_id,
            'phase', OLD.phase,
            'name', OLD.name,
            'sort_order', OLD.sort_order,
            'allows_costs', OLD.allows_costs,
            'allows_billing', OLD.allows_billing,
            'is_closed_stage', OLD.is_closed_stage,
            'is_active', OLD.is_active),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_stage_trigger_insert
AFTER INSERT ON stage_trigger
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'stage_trigger', NEW.trigger_id,
        'Insert',
        NULL,
        json_object(
            'trigger_id', NEW.trigger_id,
            'stage_id', NEW.stage_id,
            'event', NEW.event,
            'action', NEW.action,
            'config_json', NEW.config_json,
            'is_active', NEW.is_active,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_stage_trigger_update
AFTER UPDATE ON stage_trigger
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'stage_trigger', NEW.trigger_id,
        'Update',
        json_object(
            'trigger_id', OLD.trigger_id,
            'stage_id', OLD.stage_id,
            'event', OLD.event,
            'action', OLD.action,
            'config_json', OLD.config_json,
            'is_active', OLD.is_active,
            'sort_order', OLD.sort_order),
        json_object(
            'trigger_id', NEW.trigger_id,
            'stage_id', NEW.stage_id,
            'event', NEW.event,
            'action', NEW.action,
            'config_json', NEW.config_json,
            'is_active', NEW.is_active,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_stage_trigger_delete
AFTER DELETE ON stage_trigger
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'stage_trigger', OLD.trigger_id,
        'Delete',
        json_object(
            'trigger_id', OLD.trigger_id,
            'stage_id', OLD.stage_id,
            'event', OLD.event,
            'action', OLD.action,
            'config_json', OLD.config_json,
            'is_active', OLD.is_active,
            'sort_order', OLD.sort_order),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_stage_trigger_run_insert
AFTER INSERT ON stage_trigger_run
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'stage_trigger_run', NEW.run_id,
        'Insert',
        NULL,
        json_object(
            'run_id', NEW.run_id,
            'trigger_id', NEW.trigger_id,
            'record_type', NEW.record_type,
            'record_id', NEW.record_id,
            'event_key', NEW.event_key,
            'ran_at', NEW.ran_at,
            'result', NEW.result,
            'message', NEW.message),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_pay_run_insert
AFTER INSERT ON pay_run
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'pay_run', NEW.pay_run_id,
        'Insert',
        NULL,
        json_object(
            'pay_run_id', NEW.pay_run_id,
            'run_number', NEW.run_number,
            'bank_account_id', NEW.bank_account_id,
            'status', NEW.status,
            'scheduled_date', NEW.scheduled_date,
            'memo', NEW.memo,
            'created_by', NEW.created_by,
            'created_at', NEW.created_at,
            'approved_by', NEW.approved_by,
            'approved_at', NEW.approved_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_pay_run_update
AFTER UPDATE ON pay_run
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'pay_run', NEW.pay_run_id,
        'Update',
        json_object(
            'pay_run_id', OLD.pay_run_id,
            'run_number', OLD.run_number,
            'bank_account_id', OLD.bank_account_id,
            'status', OLD.status,
            'scheduled_date', OLD.scheduled_date,
            'memo', OLD.memo,
            'created_by', OLD.created_by,
            'created_at', OLD.created_at,
            'approved_by', OLD.approved_by,
            'approved_at', OLD.approved_at),
        json_object(
            'pay_run_id', NEW.pay_run_id,
            'run_number', NEW.run_number,
            'bank_account_id', NEW.bank_account_id,
            'status', NEW.status,
            'scheduled_date', NEW.scheduled_date,
            'memo', NEW.memo,
            'created_by', NEW.created_by,
            'created_at', NEW.created_at,
            'approved_by', NEW.approved_by,
            'approved_at', NEW.approved_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_pay_run_delete
AFTER DELETE ON pay_run
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'pay_run', OLD.pay_run_id,
        'Delete',
        json_object(
            'pay_run_id', OLD.pay_run_id,
            'run_number', OLD.run_number,
            'bank_account_id', OLD.bank_account_id,
            'status', OLD.status,
            'scheduled_date', OLD.scheduled_date,
            'memo', OLD.memo,
            'created_by', OLD.created_by,
            'created_at', OLD.created_at,
            'approved_by', OLD.approved_by,
            'approved_at', OLD.approved_at),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_pay_run_line_insert
AFTER INSERT ON pay_run_line
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'pay_run_line', NEW.line_id,
        'Insert',
        NULL,
        json_object(
            'line_id', NEW.line_id,
            'pay_run_id', NEW.pay_run_id,
            'invoice_id', NEW.invoice_id,
            'amount_cents', NEW.amount_cents,
            'status', NEW.status,
            'date_paid', NEW.date_paid,
            'payment_ref', NEW.payment_ref,
            'payment_id', NEW.payment_id,
            'completed_by', NEW.completed_by,
            'completed_at', NEW.completed_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_pay_run_line_update
AFTER UPDATE ON pay_run_line
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'pay_run_line', NEW.line_id,
        'Update',
        json_object(
            'line_id', OLD.line_id,
            'pay_run_id', OLD.pay_run_id,
            'invoice_id', OLD.invoice_id,
            'amount_cents', OLD.amount_cents,
            'status', OLD.status,
            'date_paid', OLD.date_paid,
            'payment_ref', OLD.payment_ref,
            'payment_id', OLD.payment_id,
            'completed_by', OLD.completed_by,
            'completed_at', OLD.completed_at),
        json_object(
            'line_id', NEW.line_id,
            'pay_run_id', NEW.pay_run_id,
            'invoice_id', NEW.invoice_id,
            'amount_cents', NEW.amount_cents,
            'status', NEW.status,
            'date_paid', NEW.date_paid,
            'payment_ref', NEW.payment_ref,
            'payment_id', NEW.payment_id,
            'completed_by', NEW.completed_by,
            'completed_at', NEW.completed_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_pay_run_line_delete
AFTER DELETE ON pay_run_line
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'pay_run_line', OLD.line_id,
        'Delete',
        json_object(
            'line_id', OLD.line_id,
            'pay_run_id', OLD.pay_run_id,
            'invoice_id', OLD.invoice_id,
            'amount_cents', OLD.amount_cents,
            'status', OLD.status,
            'date_paid', OLD.date_paid,
            'payment_ref', OLD.payment_ref,
            'payment_id', OLD.payment_id,
            'completed_by', OLD.completed_by,
            'completed_at', OLD.completed_at),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_statement_line_insert
AFTER INSERT ON bank_statement_line
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_statement_line', NEW.statement_line_id,
        'Insert',
        NULL,
        json_object(
            'statement_line_id', NEW.statement_line_id,
            'bank_account_id', NEW.bank_account_id,
            'source', NEW.source,
            'import_batch_id', NEW.import_batch_id,
            'external_id', NEW.external_id,
            'posted_date', NEW.posted_date,
            'description', NEW.description,
            'amount_cents', NEW.amount_cents,
            'status', NEW.status,
            'recon_id', NEW.recon_id,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_statement_line_update
AFTER UPDATE ON bank_statement_line
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_statement_line', NEW.statement_line_id,
        'Update',
        json_object(
            'statement_line_id', OLD.statement_line_id,
            'bank_account_id', OLD.bank_account_id,
            'source', OLD.source,
            'import_batch_id', OLD.import_batch_id,
            'external_id', OLD.external_id,
            'posted_date', OLD.posted_date,
            'description', OLD.description,
            'amount_cents', OLD.amount_cents,
            'status', OLD.status,
            'recon_id', OLD.recon_id,
            'created_at', OLD.created_at),
        json_object(
            'statement_line_id', NEW.statement_line_id,
            'bank_account_id', NEW.bank_account_id,
            'source', NEW.source,
            'import_batch_id', NEW.import_batch_id,
            'external_id', NEW.external_id,
            'posted_date', NEW.posted_date,
            'description', NEW.description,
            'amount_cents', NEW.amount_cents,
            'status', NEW.status,
            'recon_id', NEW.recon_id,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_statement_line_delete
AFTER DELETE ON bank_statement_line
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_statement_line', OLD.statement_line_id,
        'Delete',
        json_object(
            'statement_line_id', OLD.statement_line_id,
            'bank_account_id', OLD.bank_account_id,
            'source', OLD.source,
            'import_batch_id', OLD.import_batch_id,
            'external_id', OLD.external_id,
            'posted_date', OLD.posted_date,
            'description', OLD.description,
            'amount_cents', OLD.amount_cents,
            'status', OLD.status,
            'recon_id', OLD.recon_id,
            'created_at', OLD.created_at),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_statement_match_insert
AFTER INSERT ON bank_statement_match
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_statement_match', NEW.match_id,
        'Insert',
        NULL,
        json_object(
            'match_id', NEW.match_id,
            'statement_line_id', NEW.statement_line_id,
            'payment_id', NEW.payment_id,
            'journal_line_id', NEW.journal_line_id,
            'amount_cents', NEW.amount_cents,
            'matched_by', NEW.matched_by,
            'matched_at', NEW.matched_at,
            'released_at', NEW.released_at,
            'released_by', NEW.released_by,
            'release_reason', NEW.release_reason),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_bank_statement_match_update
AFTER UPDATE ON bank_statement_match
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'bank_statement_match', NEW.match_id,
        'Update',
        json_object(
            'match_id', OLD.match_id,
            'statement_line_id', OLD.statement_line_id,
            'payment_id', OLD.payment_id,
            'journal_line_id', OLD.journal_line_id,
            'amount_cents', OLD.amount_cents,
            'matched_by', OLD.matched_by,
            'matched_at', OLD.matched_at,
            'released_at', OLD.released_at,
            'released_by', OLD.released_by,
            'release_reason', OLD.release_reason),
        json_object(
            'match_id', NEW.match_id,
            'statement_line_id', NEW.statement_line_id,
            'payment_id', NEW.payment_id,
            'journal_line_id', NEW.journal_line_id,
            'amount_cents', NEW.amount_cents,
            'matched_by', NEW.matched_by,
            'matched_at', NEW.matched_at,
            'released_at', NEW.released_at,
            'released_by', NEW.released_by,
            'release_reason', NEW.release_reason),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_close_task_insert
AFTER INSERT ON close_task
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'close_task', NEW.task_id,
        'Insert',
        NULL,
        json_object(
            'task_id', NEW.task_id,
            'period_id', NEW.period_id,
            'title', NEW.title,
            'area', NEW.area,
            'assignee_user_id', NEW.assignee_user_id,
            'due_date', NEW.due_date,
            'status', NEW.status,
            'is_blocking', NEW.is_blocking,
            'completed_by', NEW.completed_by,
            'completed_at', NEW.completed_at,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_close_task_update
AFTER UPDATE ON close_task
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'close_task', NEW.task_id,
        'Update',
        json_object(
            'task_id', OLD.task_id,
            'period_id', OLD.period_id,
            'title', OLD.title,
            'area', OLD.area,
            'assignee_user_id', OLD.assignee_user_id,
            'due_date', OLD.due_date,
            'status', OLD.status,
            'is_blocking', OLD.is_blocking,
            'completed_by', OLD.completed_by,
            'completed_at', OLD.completed_at,
            'sort_order', OLD.sort_order),
        json_object(
            'task_id', NEW.task_id,
            'period_id', NEW.period_id,
            'title', NEW.title,
            'area', NEW.area,
            'assignee_user_id', NEW.assignee_user_id,
            'due_date', NEW.due_date,
            'status', NEW.status,
            'is_blocking', NEW.is_blocking,
            'completed_by', NEW.completed_by,
            'completed_at', NEW.completed_at,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_close_task_delete
AFTER DELETE ON close_task
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'close_task', OLD.task_id,
        'Delete',
        json_object(
            'task_id', OLD.task_id,
            'period_id', OLD.period_id,
            'title', OLD.title,
            'area', OLD.area,
            'assignee_user_id', OLD.assignee_user_id,
            'due_date', OLD.due_date,
            'status', OLD.status,
            'is_blocking', OLD.is_blocking,
            'completed_by', OLD.completed_by,
            'completed_at', OLD.completed_at,
            'sort_order', OLD.sort_order),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_close_task_dependency_insert
AFTER INSERT ON close_task_dependency
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'close_task_dependency', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'task_id', NEW.task_id,
            'depends_on_task_id', NEW.depends_on_task_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_close_task_dependency_update
AFTER UPDATE ON close_task_dependency
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'close_task_dependency', NEW.rowid,
        'Update',
        json_object(
            'task_id', OLD.task_id,
            'depends_on_task_id', OLD.depends_on_task_id),
        json_object(
            'task_id', NEW.task_id,
            'depends_on_task_id', NEW.depends_on_task_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_close_task_dependency_delete
AFTER DELETE ON close_task_dependency
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'close_task_dependency', OLD.rowid,
        'Delete',
        json_object(
            'task_id', OLD.task_id,
            'depends_on_task_id', OLD.depends_on_task_id),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_term_insert
AFTER INSERT ON payment_term
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment_term', NEW.term_id,
        'Insert',
        NULL,
        json_object(
            'term_id', NEW.term_id,
            'name', NEW.name,
            'days_due', NEW.days_due,
            'discount_percent', NEW.discount_percent,
            'discount_days', NEW.discount_days,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_term_update
AFTER UPDATE ON payment_term
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment_term', NEW.term_id,
        'Update',
        json_object(
            'term_id', OLD.term_id,
            'name', OLD.name,
            'days_due', OLD.days_due,
            'discount_percent', OLD.discount_percent,
            'discount_days', OLD.discount_days,
            'is_active', OLD.is_active),
        json_object(
            'term_id', NEW.term_id,
            'name', NEW.name,
            'days_due', NEW.days_due,
            'discount_percent', NEW.discount_percent,
            'discount_days', NEW.discount_days,
            'is_active', NEW.is_active),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_payment_term_delete
AFTER DELETE ON payment_term
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'payment_term', OLD.term_id,
        'Delete',
        json_object(
            'term_id', OLD.term_id,
            'name', OLD.name,
            'days_due', OLD.days_due,
            'discount_percent', OLD.discount_percent,
            'discount_days', OLD.discount_days,
            'is_active', OLD.is_active),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_custom_field_def_insert
AFTER INSERT ON custom_field_def
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'custom_field_def', NEW.field_id,
        'Insert',
        NULL,
        json_object(
            'field_id', NEW.field_id,
            'record_type', NEW.record_type,
            'field_key', NEW.field_key,
            'label', NEW.label,
            'data_type', NEW.data_type,
            'choices_json', NEW.choices_json,
            'is_required', NEW.is_required,
            'is_active', NEW.is_active,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_custom_field_def_update
AFTER UPDATE ON custom_field_def
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'custom_field_def', NEW.field_id,
        'Update',
        json_object(
            'field_id', OLD.field_id,
            'record_type', OLD.record_type,
            'field_key', OLD.field_key,
            'label', OLD.label,
            'data_type', OLD.data_type,
            'choices_json', OLD.choices_json,
            'is_required', OLD.is_required,
            'is_active', OLD.is_active,
            'sort_order', OLD.sort_order),
        json_object(
            'field_id', NEW.field_id,
            'record_type', NEW.record_type,
            'field_key', NEW.field_key,
            'label', NEW.label,
            'data_type', NEW.data_type,
            'choices_json', NEW.choices_json,
            'is_required', NEW.is_required,
            'is_active', NEW.is_active,
            'sort_order', NEW.sort_order),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_custom_field_def_delete
AFTER DELETE ON custom_field_def
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'custom_field_def', OLD.field_id,
        'Delete',
        json_object(
            'field_id', OLD.field_id,
            'record_type', OLD.record_type,
            'field_key', OLD.field_key,
            'label', OLD.label,
            'data_type', OLD.data_type,
            'choices_json', OLD.choices_json,
            'is_required', OLD.is_required,
            'is_active', OLD.is_active,
            'sort_order', OLD.sort_order),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_custom_field_value_insert
AFTER INSERT ON custom_field_value
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'custom_field_value', NEW.value_id,
        'Insert',
        NULL,
        json_object(
            'value_id', NEW.value_id,
            'field_id', NEW.field_id,
            'record_id', NEW.record_id,
            'value_text', NEW.value_text,
            'value_number', NEW.value_number,
            'value_cents', NEW.value_cents,
            'value_date', NEW.value_date,
            'value_bool', NEW.value_bool),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_custom_field_value_update
AFTER UPDATE ON custom_field_value
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'custom_field_value', NEW.value_id,
        'Update',
        json_object(
            'value_id', OLD.value_id,
            'field_id', OLD.field_id,
            'record_id', OLD.record_id,
            'value_text', OLD.value_text,
            'value_number', OLD.value_number,
            'value_cents', OLD.value_cents,
            'value_date', OLD.value_date,
            'value_bool', OLD.value_bool),
        json_object(
            'value_id', NEW.value_id,
            'field_id', NEW.field_id,
            'record_id', NEW.record_id,
            'value_text', NEW.value_text,
            'value_number', NEW.value_number,
            'value_cents', NEW.value_cents,
            'value_date', NEW.value_date,
            'value_bool', NEW.value_bool),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_custom_field_value_delete
AFTER DELETE ON custom_field_value
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'custom_field_value', OLD.value_id,
        'Delete',
        json_object(
            'value_id', OLD.value_id,
            'field_id', OLD.field_id,
            'record_id', OLD.record_id,
            'value_text', OLD.value_text,
            'value_number', OLD.value_number,
            'value_cents', OLD.value_cents,
            'value_date', OLD.value_date,
            'value_bool', OLD.value_bool),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_list_pref_insert
AFTER INSERT ON user_list_pref
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_list_pref', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'user_id', NEW.user_id,
            'list_key', NEW.list_key,
            'columns_json', NEW.columns_json,
            'sort_json', NEW.sort_json,
            'page_size', NEW.page_size),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_list_pref_update
AFTER UPDATE ON user_list_pref
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_list_pref', NEW.rowid,
        'Update',
        json_object(
            'user_id', OLD.user_id,
            'list_key', OLD.list_key,
            'columns_json', OLD.columns_json,
            'sort_json', OLD.sort_json,
            'page_size', OLD.page_size),
        json_object(
            'user_id', NEW.user_id,
            'list_key', NEW.list_key,
            'columns_json', NEW.columns_json,
            'sort_json', NEW.sort_json,
            'page_size', NEW.page_size),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_list_pref_delete
AFTER DELETE ON user_list_pref
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_list_pref', OLD.rowid,
        'Delete',
        json_object(
            'user_id', OLD.user_id,
            'list_key', OLD.list_key,
            'columns_json', OLD.columns_json,
            'sort_json', OLD.sort_json,
            'page_size', OLD.page_size),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_saved_view_insert
AFTER INSERT ON saved_view
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'saved_view', NEW.view_id,
        'Insert',
        NULL,
        json_object(
            'view_id', NEW.view_id,
            'user_id', NEW.user_id,
            'list_key', NEW.list_key,
            'name', NEW.name,
            'filters_json', NEW.filters_json,
            'is_default', NEW.is_default),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_saved_view_update
AFTER UPDATE ON saved_view
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'saved_view', NEW.view_id,
        'Update',
        json_object(
            'view_id', OLD.view_id,
            'user_id', OLD.user_id,
            'list_key', OLD.list_key,
            'name', OLD.name,
            'filters_json', OLD.filters_json,
            'is_default', OLD.is_default),
        json_object(
            'view_id', NEW.view_id,
            'user_id', NEW.user_id,
            'list_key', NEW.list_key,
            'name', NEW.name,
            'filters_json', NEW.filters_json,
            'is_default', NEW.is_default),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_saved_view_delete
AFTER DELETE ON saved_view
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'saved_view', OLD.view_id,
        'Delete',
        json_object(
            'view_id', OLD.view_id,
            'user_id', OLD.user_id,
            'list_key', OLD.list_key,
            'name', OLD.name,
            'filters_json', OLD.filters_json,
            'is_default', OLD.is_default),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_alert_dismissal_insert
AFTER INSERT ON alert_dismissal
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'alert_dismissal', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'user_id', NEW.user_id,
            'alert_key', NEW.alert_key,
            'dismissed_at', NEW.dismissed_at,
            'until_at', NEW.until_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_alert_dismissal_update
AFTER UPDATE ON alert_dismissal
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'alert_dismissal', NEW.rowid,
        'Update',
        json_object(
            'user_id', OLD.user_id,
            'alert_key', OLD.alert_key,
            'dismissed_at', OLD.dismissed_at,
            'until_at', OLD.until_at),
        json_object(
            'user_id', NEW.user_id,
            'alert_key', NEW.alert_key,
            'dismissed_at', NEW.dismissed_at,
            'until_at', NEW.until_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_alert_dismissal_delete
AFTER DELETE ON alert_dismissal
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'alert_dismissal', OLD.rowid,
        'Delete',
        json_object(
            'user_id', OLD.user_id,
            'alert_key', OLD.alert_key,
            'dismissed_at', OLD.dismissed_at,
            'until_at', OLD.until_at),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_project_insert
AFTER INSERT ON project
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'project', NEW.project_id,
        'Insert',
        NULL,
        json_object(
            'project_id', NEW.project_id,
            'project_number', NEW.project_number,
            'name', NEW.name,
            'contact_id', NEW.contact_id,
            'source_estimate_id', NEW.source_estimate_id,
            'assigned_pm_id', NEW.assigned_pm_id,
            'original_budget_cents', NEW.original_budget_cents,
            'revised_budget_cents', NEW.revised_budget_cents,
            'status', NEW.status,
            'created_at', NEW.created_at,
            'service_type_id', NEW.service_type_id,
            'service_stage_id', NEW.service_stage_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_project_update
AFTER UPDATE ON project
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'project', NEW.project_id,
        'Update',
        json_object(
            'project_id', OLD.project_id,
            'project_number', OLD.project_number,
            'name', OLD.name,
            'contact_id', OLD.contact_id,
            'source_estimate_id', OLD.source_estimate_id,
            'assigned_pm_id', OLD.assigned_pm_id,
            'original_budget_cents', OLD.original_budget_cents,
            'revised_budget_cents', OLD.revised_budget_cents,
            'status', OLD.status,
            'created_at', OLD.created_at,
            'service_type_id', OLD.service_type_id,
            'service_stage_id', OLD.service_stage_id),
        json_object(
            'project_id', NEW.project_id,
            'project_number', NEW.project_number,
            'name', NEW.name,
            'contact_id', NEW.contact_id,
            'source_estimate_id', NEW.source_estimate_id,
            'assigned_pm_id', NEW.assigned_pm_id,
            'original_budget_cents', NEW.original_budget_cents,
            'revised_budget_cents', NEW.revised_budget_cents,
            'status', NEW.status,
            'created_at', NEW.created_at,
            'service_type_id', NEW.service_type_id,
            'service_stage_id', NEW.service_stage_id),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_project_delete
AFTER DELETE ON project
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'project', OLD.project_id,
        'Delete',
        json_object(
            'project_id', OLD.project_id,
            'project_number', OLD.project_number,
            'name', OLD.name,
            'contact_id', OLD.contact_id,
            'source_estimate_id', OLD.source_estimate_id,
            'assigned_pm_id', OLD.assigned_pm_id,
            'original_budget_cents', OLD.original_budget_cents,
            'revised_budget_cents', OLD.revised_budget_cents,
            'status', OLD.status,
            'created_at', OLD.created_at,
            'service_type_id', OLD.service_type_id,
            'service_stage_id', OLD.service_stage_id),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

-- Every foreign key column is indexed (tests/test_schema_replan.py).
-- Full indexes for the three columns that had only a partial one.
CREATE INDEX idx_bank_statement_line_bank_account_id ON bank_statement_line (bank_account_id);
CREATE INDEX idx_journal_entry_reverses_entry_id ON journal_entry (reverses_entry_id);
CREATE INDEX idx_journal_line_account_id ON journal_line (account_id);
CREATE INDEX idx_account_parent_id ON account (parent_id);
CREATE INDEX idx_account_type_id ON account (type_id);
CREATE INDEX idx_approval_request_project_id ON approval_request (project_id);
CREATE INDEX idx_approval_request_policy_id ON approval_request (policy_id);
CREATE INDEX idx_approval_step_role_code ON approval_step (role_code);
CREATE INDEX idx_bank_reconciliation_account_id ON bank_reconciliation (account_id);
CREATE INDEX idx_bank_statement_line_recon_id ON bank_statement_line (recon_id);
CREATE INDEX idx_bank_statement_line_import_batch_id ON bank_statement_line (import_batch_id);
CREATE INDEX idx_bank_statement_match_journal_line_id ON bank_statement_match (journal_line_id);
CREATE INDEX idx_bank_statement_match_payment_id ON bank_statement_match (payment_id);
CREATE INDEX idx_bank_statement_match_statement_line_id ON bank_statement_match (statement_line_id);
CREATE INDEX idx_change_order_contract_id ON change_order (contract_id);
CREATE INDEX idx_change_order_project_id ON change_order (project_id);
CREATE INDEX idx_change_order_line_sov_line_id ON change_order_line (sov_line_id);
CREATE INDEX idx_change_order_line_cost_code_id ON change_order_line (cost_code_id);
CREATE INDEX idx_change_order_line_co_id ON change_order_line (co_id);
CREATE INDEX idx_close_task_period_id ON close_task (period_id);
CREATE INDEX idx_close_task_dependency_depends_on_task_id ON close_task_dependency (depends_on_task_id);
CREATE INDEX idx_company_entity_parent_entity_id ON company_entity (parent_entity_id);
CREATE INDEX idx_company_settings_rounding_variance_acct_id ON company_settings (rounding_variance_acct_id);
CREATE INDEX idx_company_settings_interest_expense_acct_id ON company_settings (interest_expense_acct_id);
CREATE INDEX idx_company_settings_gain_loss_disposal_acct_id ON company_settings (gain_loss_disposal_acct_id);
CREATE INDEX idx_company_settings_interest_income_acct_id ON company_settings (interest_income_acct_id);
CREATE INDEX idx_company_settings_bank_charges_acct_id ON company_settings (bank_charges_acct_id);
CREATE INDEX idx_company_settings_inventory_adjustments_acct_id ON company_settings (inventory_adjustments_acct_id);
CREATE INDEX idx_company_settings_equipment_recovery_acct_id ON company_settings (equipment_recovery_acct_id);
CREATE INDEX idx_company_settings_customer_deposits_acct_id ON company_settings (customer_deposits_acct_id);
CREATE INDEX idx_company_settings_unearned_revenue_acct_id ON company_settings (unearned_revenue_acct_id);
CREATE INDEX idx_company_settings_use_tax_payable_acct_id ON company_settings (use_tax_payable_acct_id);
CREATE INDEX idx_company_settings_credit_card_clearing_acct_id ON company_settings (credit_card_clearing_acct_id);
CREATE INDEX idx_company_settings_grni_acct_id ON company_settings (grni_acct_id);
CREATE INDEX idx_company_settings_prepaid_expenses_acct_id ON company_settings (prepaid_expenses_acct_id);
CREATE INDEX idx_company_settings_employee_advances_acct_id ON company_settings (employee_advances_acct_id);
CREATE INDEX idx_company_settings_retainage_payable_acct_id ON company_settings (retainage_payable_acct_id);
CREATE INDEX idx_company_settings_retainage_receivable_acct_id ON company_settings (retainage_receivable_acct_id);
CREATE INDEX idx_company_settings_undeposited_funds_acct_id ON company_settings (undeposited_funds_acct_id);
CREATE INDEX idx_company_settings_opening_balance_equity_acct_id ON company_settings (opening_balance_equity_acct_id);
CREATE INDEX idx_company_settings_retained_earnings_acct_id ON company_settings (retained_earnings_acct_id);
CREATE INDEX idx_company_settings_default_bank_acct_id ON company_settings (default_bank_acct_id);
CREATE INDEX idx_company_settings_sales_tax_payable_acct_id ON company_settings (sales_tax_payable_acct_id);
CREATE INDEX idx_company_settings_ap_acct_id ON company_settings (ap_acct_id);
CREATE INDEX idx_company_settings_ar_acct_id ON company_settings (ar_acct_id);
CREATE INDEX idx_contact_payment_term_id ON contact (payment_term_id);
CREATE INDEX idx_contact_site_contact_id ON contact_site (contact_id);
CREATE INDEX idx_contract_contact_id ON contract (contact_id);
CREATE INDEX idx_contract_project_id ON contract (project_id);
CREATE INDEX idx_contract_line_cost_code_id ON contract_line (cost_code_id);
CREATE INDEX idx_contract_line_contract_id ON contract_line (contract_id);
CREATE INDEX idx_cost_code_parent_id ON cost_code (parent_id);
CREATE INDEX idx_deferral_supersedes_id ON deferral (supersedes_id);
CREATE INDEX idx_deferral_recognition_account_id ON deferral (recognition_account_id);
CREATE INDEX idx_deferral_deferral_account_id ON deferral (deferral_account_id);
CREATE INDEX idx_deferral_payment_id ON deferral (payment_id);
CREATE INDEX idx_deferral_invoice_line_id ON deferral (invoice_line_id);
CREATE INDEX idx_deferral_invoice_id ON deferral (invoice_id);
CREATE INDEX idx_deferral_contact_id ON deferral (contact_id);
CREATE INDEX idx_deferral_schedule_line_period_id ON deferral_schedule_line (period_id);
CREATE INDEX idx_dimension_value_parent_value_id ON dimension_value (parent_value_id);
CREATE INDEX idx_dimension_value_dimension_type_id ON dimension_value (dimension_type_id);
CREATE INDEX idx_estimate_contact_id ON estimate (contact_id);
CREATE INDEX idx_estimate_line_cost_code_id ON estimate_line (cost_code_id);
CREATE INDEX idx_estimate_line_estimate_id ON estimate_line (estimate_id);
CREATE INDEX idx_import_batch_entry_id ON import_batch (entry_id);
CREATE INDEX idx_import_batch_reverses_batch_id ON import_batch (reverses_batch_id);
CREATE INDEX idx_import_batch_source_id ON import_batch (source_id);
CREATE INDEX idx_import_mapping_contact_id ON import_mapping (contact_id);
CREATE INDEX idx_import_mapping_account_id ON import_mapping (account_id);
CREATE INDEX idx_import_mapping_source_id ON import_mapping (source_id);
CREATE INDEX idx_invoice_payment_term_id ON invoice (payment_term_id);
CREATE INDEX idx_invoice_supersedes_id ON invoice (supersedes_id);
CREATE INDEX idx_invoice_batch_id ON invoice (batch_id);
CREATE INDEX idx_invoice_subscription_id ON invoice (subscription_id);
CREATE INDEX idx_invoice_project_id ON invoice (project_id);
CREATE INDEX idx_invoice_contact_id ON invoice (contact_id);
CREATE INDEX idx_invoice_line_cost_code_id ON invoice_line (cost_code_id);
CREATE INDEX idx_invoice_line_tax_rate_id ON invoice_line (tax_rate_id);
CREATE INDEX idx_invoice_line_account_id ON invoice_line (account_id);
CREATE INDEX idx_invoice_line_invoice_id ON invoice_line (invoice_id);
CREATE INDEX idx_invoice_line_dimension_dimension_value_id ON invoice_line_dimension (dimension_value_id);
CREATE INDEX idx_invoice_line_dimension_dimension_type_id ON invoice_line_dimension (dimension_type_id);
CREATE INDEX idx_journal_entry_chain_key_id ON journal_entry (chain_key_id);
CREATE INDEX idx_journal_entry_period_id ON journal_entry (period_id);
CREATE INDEX idx_journal_line_entity_id ON journal_line (entity_id);
CREATE INDEX idx_journal_line_batch_id ON journal_line (batch_id);
CREATE INDEX idx_journal_line_deferral_id ON journal_line (deferral_id);
CREATE INDEX idx_journal_line_cost_code_id ON journal_line (cost_code_id);
CREATE INDEX idx_journal_line_project_id ON journal_line (project_id);
CREATE INDEX idx_journal_line_recon_id ON journal_line (recon_id);
CREATE INDEX idx_journal_line_contact_id ON journal_line (contact_id);
CREATE INDEX idx_journal_line_entry_id ON journal_line (entry_id);
CREATE INDEX idx_journal_line_dimension_dimension_value_id ON journal_line_dimension (dimension_value_id);
CREATE INDEX idx_journal_line_dimension_dimension_type_id ON journal_line_dimension (dimension_type_id);
CREATE INDEX idx_ledger_checkpoint_key_id ON ledger_checkpoint (key_id);
CREATE INDEX idx_pay_run_bank_account_id ON pay_run (bank_account_id);
CREATE INDEX idx_pay_run_line_payment_id ON pay_run_line (payment_id);
CREATE INDEX idx_pay_run_line_invoice_id ON pay_run_line (invoice_id);
CREATE INDEX idx_payment_bank_account_id ON payment (bank_account_id);
CREATE INDEX idx_payment_contact_id ON payment (contact_id);
CREATE INDEX idx_payment_allocation_credit_memo_id ON payment_allocation (credit_memo_id);
CREATE INDEX idx_payment_allocation_invoice_id ON payment_allocation (invoice_id);
CREATE INDEX idx_payment_allocation_payment_id ON payment_allocation (payment_id);
CREATE INDEX idx_period_status_history_year_id ON period_status_history (year_id);
CREATE INDEX idx_period_status_history_period_id ON period_status_history (period_id);
CREATE INDEX idx_poc_snapshot_period_id ON poc_snapshot (period_id);
CREATE INDEX idx_progress_billing_application_invoice_id ON progress_billing_application (invoice_id);
CREATE INDEX idx_progress_billing_application_contract_id ON progress_billing_application (contract_id);
CREATE INDEX idx_project_service_stage_id ON project (service_stage_id);
CREATE INDEX idx_project_service_type_id ON project (service_type_id);
CREATE INDEX idx_project_source_estimate_id ON project (source_estimate_id);
CREATE INDEX idx_project_contact_id ON project (contact_id);
CREATE INDEX idx_project_budget_co_line_id ON project_budget (co_line_id);
CREATE INDEX idx_project_budget_estimate_line_id ON project_budget (estimate_line_id);
CREATE INDEX idx_project_budget_cost_code_id ON project_budget (cost_code_id);
CREATE INDEX idx_project_budget_project_id ON project_budget (project_id);
CREATE INDEX idx_role_permission_permission_code ON role_permission (permission_code);
CREATE INDEX idx_saas_usage_telemetry_subscription_id ON saas_usage_telemetry (subscription_id);
CREATE INDEX idx_stage_trigger_stage_id ON stage_trigger (stage_id);
CREATE INDEX idx_staged_line_account_id ON staged_line (account_id);
CREATE INDEX idx_staged_line_stage_id ON staged_line (stage_id);
CREATE INDEX idx_staged_transaction_entry_id ON staged_transaction (entry_id);
CREATE INDEX idx_staged_transaction_payment_id ON staged_transaction (payment_id);
CREATE INDEX idx_staged_transaction_invoice_id ON staged_transaction (invoice_id);
CREATE INDEX idx_staged_transaction_matched_invoice_id ON staged_transaction (matched_invoice_id);
CREATE INDEX idx_staged_transaction_contact_id ON staged_transaction (contact_id);
CREATE INDEX idx_staged_transaction_reverses_stage_id ON staged_transaction (reverses_stage_id);
CREATE INDEX idx_staged_transaction_batch_id ON staged_transaction (batch_id);
CREATE INDEX idx_subscription_contact_id ON subscription (contact_id);
CREATE INDEX idx_tax_rate_tax_account_id ON tax_rate (tax_account_id);
CREATE INDEX idx_time_entry_source_batch_id ON time_entry (source_batch_id);
CREATE INDEX idx_time_entry_cost_code_id ON time_entry (cost_code_id);
CREATE INDEX idx_time_entry_project_id ON time_entry (project_id);
CREATE INDEX idx_time_entry_contact_id ON time_entry (contact_id);
CREATE INDEX idx_user_project_scope_project_id ON user_project_scope (project_id);
