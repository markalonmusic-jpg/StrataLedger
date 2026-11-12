-- Migration 3 (company): critical controls. See docs/controls_audit.md.
--
-- L1  Every journal line has an account (journal_line.account_id NOT NULL).
-- P1  Ledger and document dates are strict ISO YYYY-MM-DD:
--     CHECK (col IS date(col)) rejects '03/20/2026', '2026-3-5',
--     '2026-02-30' and date-times, which could get past the closed-period check.
-- P2 / decision 1  Void = reversing entry. A reversal names the entry it
--     reverses (reverses_entry_id, now UNIQUE) and why (reversal_reason).
--     It posts only if the original is posted and unvoided, it mirrors the
--     original exactly, and it is in an open period. Posting a 'Void'
--     reversal sets is_void = 1 on the original in the same statement; is_void
--     cannot be set any other way. is_void is only a marker: reports never
--     filter on it, because the reversal already nets the original to zero.
-- C1-C3  Non-Draft or posted invoices, their lines and line dimensions, and
--     posted payments and their allocations are locked. Invoice status moves:
--     Draft -> Sent, Sent -> Paid, Paid -> Sent, Sent -> Void (entry voided
--     first), Draft/Sent -> Covered by advance.
-- T1  audit_log is append-only and written by triggers. The user comes from
--     the one-row audit_context table, which the service layer sets inside
--     each write transaction.
-- Decision 2  invoice_type is 'Credit Memo' (existing 'Credit memo' rows are
--     converted). Document amounts are stored positive; the sign by document
--     type is applied in one place (modules/ledger_rules.py).
--
-- Same rebuild procedure as 002. All triggers on the rebuilt tables are
-- dropped first and recreated at the end.

DROP TRIGGER IF EXISTS journal_entry_no_direct_post;
DROP TRIGGER IF EXISTS journal_entry_require_balance_on_post;
DROP TRIGGER IF EXISTS journal_entry_lock_posted;
DROP TRIGGER IF EXISTS journal_entry_lock_delete_posted;
DROP TRIGGER IF EXISTS journal_line_lock_insert_posted;
DROP TRIGGER IF EXISTS journal_line_lock_update_posted;
DROP TRIGGER IF EXISTS journal_line_lock_delete_posted;

-- journal_entry: ISO entry_date; reversal link is unique and carries a reason.
CREATE TABLE new_journal_entry (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL CHECK (entry_date IS date(entry_date)),
    period_id INTEGER REFERENCES fiscal_period(period_id),
    reference TEXT,
    description TEXT,
    source TEXT CHECK (source IN ('Manual', 'Invoice', 'Bill', 'Payment', 'Adjustment', 'Payroll', 'Import', 'Deferral', 'Completion')),
    is_posted INTEGER NOT NULL DEFAULT 0 CHECK (is_posted IN (0, 1)),
    is_void INTEGER NOT NULL DEFAULT 0 CHECK (is_void IN (0, 1)),
    reverses_entry_id INTEGER UNIQUE REFERENCES journal_entry(entry_id),
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reversal_reason TEXT CHECK (reversal_reason IN ('Void', 'Accrual reversal', 'Correction')),
    CHECK ((reverses_entry_id IS NULL) = (reversal_reason IS NULL))
);
INSERT INTO new_journal_entry (entry_id, entry_date, period_id, reference, description, source, is_posted, is_void, reverses_entry_id, created_by, created_at, reversal_reason)
    SELECT entry_id, entry_date, period_id, reference, description, source, is_posted, is_void, reverses_entry_id, created_by, created_at,
           CASE WHEN reverses_entry_id IS NULL THEN NULL ELSE 'Correction' END
    FROM journal_entry;
DROP TABLE journal_entry;
ALTER TABLE new_journal_entry RENAME TO journal_entry;

-- journal_line: account required.
CREATE TABLE new_journal_line (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER REFERENCES journal_entry(entry_id),
    account_id INTEGER NOT NULL REFERENCES account(account_id),
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

-- fiscal_period: ISO dates.
CREATE TABLE new_fiscal_period (
    period_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL CHECK (start_date IS date(start_date)),
    end_date TEXT NOT NULL CHECK (end_date IS date(end_date)),
    is_closed INTEGER DEFAULT 0
);
INSERT INTO new_fiscal_period (period_id, name, start_date, end_date, is_closed)
    SELECT period_id, name, start_date, end_date, is_closed FROM fiscal_period;
DROP TABLE fiscal_period;
ALTER TABLE new_fiscal_period RENAME TO fiscal_period;

-- invoice: 'Credit Memo'; status required (Draft by default); ISO dates;
-- amounts positive.
CREATE TABLE new_invoice (
    invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_type TEXT CHECK (invoice_type IN ('Invoice', 'Bill', 'Credit Memo')),
    contact_id INTEGER REFERENCES contact(contact_id),
    project_id INTEGER REFERENCES project(project_id),
    subscription_id INTEGER REFERENCES subscription(subscription_id),
    invoice_number TEXT NOT NULL,
    issue_date TEXT NOT NULL CHECK (issue_date IS date(issue_date)),
    due_date TEXT NOT NULL CHECK (due_date IS date(due_date)),
    terms TEXT CHECK (terms IN ('Due on Receipt', 'Net 15', 'Net 30', 'Net 60')) DEFAULT 'Net 30',
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Sent', 'Paid', 'Void', 'Covered by advance')),
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
    CHECK (retainage_cents IS NULL OR typeof(retainage_cents) = 'integer'),
    CONSTRAINT invoice_amounts_positive CHECK (
        subtotal_cents >= 0 AND vatable_sales_cents >= 0 AND vat_exempt_sales_cents >= 0
        AND zero_rated_sales_cents >= 0 AND tax_cents >= 0 AND cwt_amount_cents >= 0
        AND total_cents >= 0 AND retainage_cents >= 0
    )
);
INSERT INTO new_invoice (invoice_id, invoice_type, contact_id, project_id, subscription_id, invoice_number, issue_date, due_date, terms, status, currency, exchange_rate, subtotal_cents, vatable_sales_cents, vat_exempt_sales_cents, zero_rated_sales_cents, tax_cents, cwt_rate, cwt_amount_cents, total_cents, retainage_cents, is_eis_transmitted, entry_id, batch_id, external_ref)
    SELECT invoice_id,
           CASE WHEN invoice_type = 'Credit memo' THEN 'Credit Memo' ELSE invoice_type END,
           contact_id, project_id, subscription_id, invoice_number, issue_date, due_date, terms,
           COALESCE(status, 'Draft'),
           currency, exchange_rate, subtotal_cents, vatable_sales_cents, vat_exempt_sales_cents, zero_rated_sales_cents, tax_cents, cwt_rate, cwt_amount_cents, total_cents, retainage_cents, is_eis_transmitted, entry_id, batch_id, external_ref
    FROM invoice;
DROP TABLE invoice;
ALTER TABLE new_invoice RENAME TO invoice;

-- invoice_line: amounts and quantities positive.
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
    CHECK (unit_price_cents IS NULL OR typeof(unit_price_cents) = 'integer'),
    CONSTRAINT invoice_line_amounts_positive CHECK (unit_price_cents >= 0 AND quantity >= 0)
);
INSERT INTO new_invoice_line (line_id, invoice_id, description, quantity, unit_price_cents, account_id, tax_rate_id, service_start_date, service_end_date, is_retainage_line, cost_code_id, department_tag, sort_order)
    SELECT line_id, invoice_id, description, quantity, unit_price_cents, account_id, tax_rate_id, service_start_date, service_end_date, is_retainage_line, cost_code_id, department_tag, sort_order FROM invoice_line;
DROP TABLE invoice_line;
ALTER TABLE new_invoice_line RENAME TO invoice_line;

-- payment: ISO date; amount positive.
CREATE TABLE new_payment (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT CHECK (direction IN ('Received', 'Made')),
    contact_id INTEGER REFERENCES contact(contact_id),
    payment_date TEXT NOT NULL CHECK (payment_date IS date(payment_date)),
    amount_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'PHP',
    exchange_rate REAL DEFAULT 1.0,
    method TEXT CHECK (method IN ('Cash', 'Check', 'Bank Transfer', 'GCash', 'Maya')),
    bank_account_id INTEGER REFERENCES account(account_id),
    entry_id INTEGER REFERENCES journal_entry(entry_id),
    CHECK (typeof(amount_cents) = 'integer'),
    CONSTRAINT payment_amount_positive CHECK (amount_cents > 0)
);
INSERT INTO new_payment (payment_id, direction, contact_id, payment_date, amount_cents, currency, exchange_rate, method, bank_account_id, entry_id)
    SELECT payment_id, direction, contact_id, payment_date, amount_cents, currency, exchange_rate, method, bank_account_id, entry_id FROM payment;
DROP TABLE payment;
ALTER TABLE new_payment RENAME TO payment;

-- payment_allocation: amount positive.
CREATE TABLE new_payment_allocation (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER REFERENCES payment(payment_id),
    invoice_id INTEGER REFERENCES invoice(invoice_id),
    deferral_id INTEGER,
    amount_applied_cents INTEGER NOT NULL,
    CHECK (typeof(amount_applied_cents) = 'integer'),
    CONSTRAINT allocation_amount_positive CHECK (amount_applied_cents > 0)
);
INSERT INTO new_payment_allocation (allocation_id, payment_id, invoice_id, deferral_id, amount_applied_cents)
    SELECT allocation_id, payment_id, invoice_id, deferral_id, amount_applied_cents FROM payment_allocation;
DROP TABLE payment_allocation;
ALTER TABLE new_payment_allocation RENAME TO payment_allocation;

-- T1: who is writing. One row; the service layer sets it inside each write
-- transaction. It cannot be deleted, so audit rows are always written.
CREATE TABLE audit_context (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id INTEGER,
    terminal_id TEXT,
    software_version_tag TEXT,
    set_at DATETIME
);
INSERT INTO audit_context (id) VALUES (1);

CREATE TRIGGER audit_context_no_delete
BEFORE DELETE ON audit_context
BEGIN
    SELECT RAISE(ABORT, 'audit_context row cannot be deleted');
END;

-- ---------------------------------------------------------------------------
-- Journal triggers (F3-F5 from 002, plus decision 1)
-- ---------------------------------------------------------------------------

CREATE TRIGGER journal_entry_no_direct_post
BEFORE INSERT ON journal_entry
WHEN NEW.is_posted = 1 OR NEW.is_void = 1
BEGIN
    SELECT CASE WHEN NEW.is_posted = 1
        THEN RAISE(ABORT, 'Create journal entries as unposted, add balanced lines, then post') END;
    SELECT CASE WHEN NEW.is_void = 1
        THEN RAISE(ABORT, 'is_void is set only by posting a Void reversal') END;
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
          AND NEW.entry_date BETWEEN start_date AND end_date
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
    -- Reversals: the original must be posted and unvoided, and the reversal
    -- must mirror it exactly (same accounts and tags, debits and credits swapped).
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

-- Decision 1: posting a Void reversal marks the original as void, in the same
-- statement (and so the same transaction).
CREATE TRIGGER journal_entry_void_on_reversal
AFTER UPDATE OF is_posted ON journal_entry
WHEN NEW.is_posted = 1 AND OLD.is_posted = 0 AND NEW.reversal_reason = 'Void'
BEGIN
    UPDATE journal_entry SET is_void = 1 WHERE entry_id = NEW.reverses_entry_id;
END;

-- Drafts can never be marked void; posted entries are handled by the lock below.
CREATE TRIGGER journal_entry_no_draft_void
BEFORE UPDATE OF is_void ON journal_entry
WHEN OLD.is_posted = 0 AND NEW.is_void IS NOT OLD.is_void
BEGIN
    SELECT RAISE(ABORT, 'is_void is set only by posting a Void reversal');
END;

-- A posted entry may only change by being marked void (is_void 0 -> 1), and
-- only once a posted Void reversal of it exists. Every other column must stay
-- the same. A test checks that this list names every journal_entry column.
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
    ) THEN RAISE(ABORT, 'Posted journal entries cannot be changed; void them by posting a Void reversal') END;
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

-- ---------------------------------------------------------------------------
-- C1-C3: invoices and payments
-- An invoice is locked once it leaves Draft or has a journal entry.
-- ---------------------------------------------------------------------------

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

-- On a locked invoice only status (by the flow above) and is_eis_transmitted
-- (0 -> 1, set after transmission) may change. entry_id is set only in the
-- update that moves Draft -> Sent. A test checks that every column is listed.
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
    ) THEN RAISE(ABORT, 'Sent or posted invoices cannot be changed; issue a credit memo') END;
END;

CREATE TRIGGER invoice_lock_delete
BEFORE DELETE ON invoice
WHEN OLD.status IS NOT 'Draft' OR OLD.entry_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Only Draft invoices without a journal entry can be deleted');
END;

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

CREATE TRIGGER invoice_line_lock_delete
BEFORE DELETE ON invoice_line
WHEN EXISTS (SELECT 1 FROM invoice WHERE invoice_id = OLD.invoice_id
             AND (status IS NOT 'Draft' OR entry_id IS NOT NULL))
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

CREATE TRIGGER invoice_line_dimension_lock_delete
BEFORE DELETE ON invoice_line_dimension
WHEN EXISTS (SELECT 1 FROM invoice_line AS l JOIN invoice AS i ON i.invoice_id = l.invoice_id
             WHERE l.line_id = OLD.line_id AND (i.status IS NOT 'Draft' OR i.entry_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'Lines of a Sent or posted invoice cannot be changed'); END;

-- A payment is locked once it has a journal entry. Its allocations can then be
-- added, but not changed; they can be removed only after the payment's entry
-- is voided, and nothing can be added to a voided payment.
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

CREATE TRIGGER payment_allocation_lock_update
BEFORE UPDATE ON payment_allocation
WHEN EXISTS (SELECT 1 FROM payment WHERE payment_id IN (OLD.payment_id, NEW.payment_id)
             AND entry_id IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'Allocations of a posted payment cannot be changed'); END;

CREATE TRIGGER payment_allocation_lock_delete
BEFORE DELETE ON payment_allocation
WHEN EXISTS (SELECT 1 FROM payment AS p LEFT JOIN journal_entry AS e ON e.entry_id = p.entry_id
             WHERE p.payment_id = OLD.payment_id AND p.entry_id IS NOT NULL AND e.is_void IS NOT 1)
BEGIN SELECT RAISE(ABORT, 'Allocations of a posted payment can be removed only after its entry is voided'); END;

CREATE TRIGGER payment_allocation_no_voided_payment
BEFORE INSERT ON payment_allocation
WHEN EXISTS (SELECT 1 FROM payment AS p JOIN journal_entry AS e ON e.entry_id = p.entry_id
             WHERE p.payment_id = NEW.payment_id AND e.is_void = 1)
BEGIN SELECT RAISE(ABORT, 'A voided payment cannot be allocated'); END;

-- ---------------------------------------------------------------------------
-- T1: audit trail
-- ---------------------------------------------------------------------------

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

-- Generated from the table columns; a test checks every column is covered.

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
            'reversal_reason', NEW.reversal_reason
        ),
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
            'reversal_reason', OLD.reversal_reason
        ),
        CASE WHEN OLD.is_posted = 0 AND NEW.is_posted = 1 THEN json_insert(
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
            'reversal_reason', NEW.reversal_reason
        ),
            '$.lines', json((
                SELECT json_group_array(json_object(
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
            'reversal_reason', NEW.reversal_reason
        ) END,
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
            'reversal_reason', OLD.reversal_reason
        ),
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
            'is_closed', NEW.is_closed
        ),
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
            'is_closed', OLD.is_closed
        ),
        json_object(
            'period_id', NEW.period_id,
            'name', NEW.name,
            'start_date', NEW.start_date,
            'end_date', NEW.end_date,
            'is_closed', NEW.is_closed
        ),
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
            'is_closed', OLD.is_closed
        ),
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
            'is_deferral_account', NEW.is_deferral_account
        ),
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
            'is_deferral_account', OLD.is_deferral_account
        ),
        json_object(
            'account_id', NEW.account_id,
            'code', NEW.code,
            'name', NEW.name,
            'type_id', NEW.type_id,
            'parent_id', NEW.parent_id,
            'is_postable', NEW.is_postable,
            'is_active', NEW.is_active,
            'is_deferral_account', NEW.is_deferral_account
        ),
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
            'is_deferral_account', OLD.is_deferral_account
        ),
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
            'external_ref', NEW.external_ref
        ),
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
            'external_ref', OLD.external_ref
        ),
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
            'external_ref', NEW.external_ref
        ),
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
            'external_ref', OLD.external_ref
        ),
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
            'entry_id', NEW.entry_id
        ),
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
            'entry_id', OLD.entry_id
        ),
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
            'entry_id', NEW.entry_id
        ),
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
            'entry_id', OLD.entry_id
        ),
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
            'amount_applied_cents', NEW.amount_applied_cents
        ),
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
            'amount_applied_cents', OLD.amount_applied_cents
        ),
        json_object(
            'allocation_id', NEW.allocation_id,
            'payment_id', NEW.payment_id,
            'invoice_id', NEW.invoice_id,
            'deferral_id', NEW.deferral_id,
            'amount_applied_cents', NEW.amount_applied_cents
        ),
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
            'amount_applied_cents', OLD.amount_applied_cents
        ),
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
            'payroll_clearing_acct_id', NEW.payroll_clearing_acct_id
        ),
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
            'payroll_clearing_acct_id', OLD.payroll_clearing_acct_id
        ),
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
            'payroll_clearing_acct_id', NEW.payroll_clearing_acct_id
        ),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

