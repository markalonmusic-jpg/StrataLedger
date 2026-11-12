-- Migration 5 (company): roles, permissions, approval limits and approval chains
-- (Phase 2.2a; docs/roles_permissions_design.md sections 3-6 and 5A).
--
-- User ids in this file (user_project_scope, approval_action, access_event)
-- are master-database ids stored as plain integers: SQLite cannot enforce a
-- foreign key across database files (CLAUDE.md section 9 item 4).
--
-- What is NOT enforced here, on purpose:
--  * A role that is still in use cannot be deleted. "In use" means a user has
--    it in user_company_access.role_code, which lives in the master database,
--    so the check is a service rule (Phase 2.2b). Inside this database a role
--    used by an approval step cannot be deleted (foreign key).
--  * Approval bands for one document type must not overlap, and a person fills
--    at most one slot in a chain. Both are service rules with tests (2.2b).
--  * Starter role templates (Controller, Accountant, ...) are seeded by the
--    company creation service (2.4). Only Admin is seeded here.

-- ---------------------------------------------------------------------------
-- Permission registry. The Python registry (modules/services/permissions.py,
-- 2.2b) is the source of truth; a test compares the two.
-- ---------------------------------------------------------------------------

CREATE TABLE permission (
    permission_code TEXT PRIMARY KEY,
    module TEXT NOT NULL,
    description TEXT NOT NULL,
    is_sensitive INTEGER NOT NULL CHECK (is_sensitive IN (0, 1))
);

INSERT INTO permission (permission_code, module, description, is_sensitive) VALUES
    ('company.settings', 'Company', 'Change company settings', 0),
    ('company.users.manage', 'Company', 'Create users and assign roles and access', 0),
    ('company.roles.manage', 'Company', 'Create and edit roles and approval limits', 0),
    ('company.backup', 'Company', 'Back up and export the company', 0),
    ('company.restore', 'Company', 'Restore the company from a backup', 1),
    ('period.close', 'Periods', 'Close a fiscal period', 0),
    ('period.reopen', 'Periods', 'Reopen a closed fiscal period (reason required)', 1),
    ('period.view', 'Periods', 'View fiscal periods', 0),
    ('je.create', 'Ledger', 'Create journal entries', 0),
    ('je.post', 'Ledger', 'Post journal entries', 0),
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
    ('project.view', 'Projects / CRM', 'View projects', 0),
    ('payapp.create', 'Pay applications', 'Create pay applications', 0),
    ('payapp.approve', 'Pay applications', 'Approve pay applications', 1),
    ('retainage.release', 'Pay applications', 'Release retainage', 0),
    ('asset.create', 'Fixed assets', 'Create fixed assets', 0),
    ('asset.dispose', 'Fixed assets', 'Dispose of fixed assets', 0),
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
    ('audit.view', 'Audit', 'View the audit trail', 1);

-- ---------------------------------------------------------------------------
-- Roles. Admin is the only fixed company role (it holds every permission and
-- is protected below). Master is a user-level flag in the master database.
-- ---------------------------------------------------------------------------

CREATE TABLE role (
    role_code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_system INTEGER NOT NULL CHECK (is_system IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    project_scope TEXT NOT NULL DEFAULT 'All' CHECK (project_scope IN ('All', 'Assigned')),
    created_at TEXT NOT NULL
);

INSERT INTO role (role_code, name, is_system, is_active, project_scope, created_at)
    VALUES ('Admin', 'Admin', 1, 1, 'All', strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'));

CREATE TABLE role_permission (
    role_code TEXT NOT NULL REFERENCES role(role_code) ON DELETE CASCADE,
    permission_code TEXT NOT NULL REFERENCES permission(permission_code),
    PRIMARY KEY (role_code, permission_code)
);

INSERT INTO role_permission (role_code, permission_code)
    SELECT 'Admin', permission_code FROM permission;

CREATE TABLE approval_limit (
    role_code TEXT NOT NULL REFERENCES role(role_code) ON DELETE CASCADE,
    document_type TEXT NOT NULL CHECK (document_type IN ('Bill', 'Journal entry', 'Payment', 'Purchase order', 'Subcontract', 'Pay application', 'Import batch', 'Asset disposal')),
    max_amount_cents INTEGER NOT NULL CHECK (typeof(max_amount_cents) = 'integer' AND max_amount_cents >= 0),
    PRIMARY KEY (role_code, document_type)
);

-- user_id is a master-database user id (no foreign key).
CREATE TABLE user_project_scope (
    user_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL REFERENCES project(project_id),
    PRIMARY KEY (user_id, project_id)
);

-- Denied attempts and Master company opens. Append-only. It never stores
-- field values, only who, what kind of event, which permission and record.
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

-- Separation of duties is chosen at company setup (design section 5). The safe
-- setting is the default, including for companies upgraded from version 4.
ALTER TABLE company_settings ADD COLUMN require_separate_approver INTEGER NOT NULL DEFAULT 1
    CHECK (require_separate_approver IN (0, 1));

-- ---------------------------------------------------------------------------
-- Multiple approvers (design section 5A). These tables replace
-- crm_approval_rule / crm_approval_instance, which the CRM / project
-- lifecycle migration drops.
-- ---------------------------------------------------------------------------

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

-- Steps with the same step_no are parallel. required_count different people
-- holding the role must approve each step.
CREATE TABLE approval_step (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL REFERENCES approval_policy(policy_id) ON DELETE CASCADE,
    step_no INTEGER NOT NULL CHECK (step_no >= 1),
    role_code TEXT NOT NULL REFERENCES role(role_code),
    required_count INTEGER NOT NULL DEFAULT 1 CHECK (required_count >= 1),
    UNIQUE (policy_id, step_no, role_code)
);

-- policy_id NULL = the default single approval. chain_json is the chain copied
-- at submit time, so editing a policy never changes a request in progress.
CREATE TABLE approval_request (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_type TEXT NOT NULL CHECK (document_type IN ('Bill', 'Journal entry', 'Payment', 'Purchase order', 'Subcontract', 'Pay application', 'Import batch', 'Asset disposal', 'Estimate', 'Change order', 'Contract')),
    record_type TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (typeof(amount_cents) = 'integer'),
    policy_id INTEGER REFERENCES approval_policy(policy_id),
    chain_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Cancelled')),
    submitted_by INTEGER,
    submitted_at TEXT,
    completed_at TEXT
);

CREATE UNIQUE INDEX approval_request_one_pending
    ON approval_request (record_type, record_id) WHERE status = 'Pending';

-- user_id is a master-database user id (no foreign key). One action per person
-- per request: a person fills at most one slot in the whole chain.
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

-- ---------------------------------------------------------------------------
-- Admin is protected. Inserts stay allowed so later migrations can grant Admin
-- new permissions.
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- Audit triggers (same pattern as 003/004). Created after the seed rows so the
-- migration itself writes no audit rows. company_settings gets a new column,
-- so its insert and update triggers are regenerated to cover it.
-- ---------------------------------------------------------------------------

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

DROP TRIGGER audit_company_settings_insert;
DROP TRIGGER audit_company_settings_update;

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
            'require_separate_approver', NEW.require_separate_approver),
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
            'require_separate_approver', OLD.require_separate_approver),
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
            'require_separate_approver', NEW.require_separate_approver),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;
