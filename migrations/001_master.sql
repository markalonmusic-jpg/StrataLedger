-- StrataLedger master baseline schema, version 1.
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

CREATE TABLE audit_log (

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

CREATE TABLE user_company_access (

    user_id    INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,

    company_id INTEGER NOT NULL REFERENCES company_registry(company_id) ON DELETE CASCADE, role_code TEXT, access_mode TEXT NOT NULL DEFAULT 'Grant'
    CHECK (access_mode IN ('Grant', 'Deny')),

    PRIMARY KEY (user_id, company_id)

);

CREATE TABLE "company_registry" (
    company_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code        TEXT NOT NULL UNIQUE,
    legal_name          TEXT NOT NULL,
    database_file_path  TEXT NOT NULL,
    parent_company_id   INTEGER DEFAULT NULL,
    is_active           INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_archived         INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),
    FOREIGN KEY (parent_company_id) REFERENCES company_registry(company_id) ON DELETE SET NULL
);

CREATE TABLE "app_user" (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT,
    job_title TEXT NOT NULL DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_master INTEGER NOT NULL DEFAULT 0 CHECK (is_master IN (0, 1)),
    must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1))
);

-- Who is writing. One row; the service layer sets it inside each write
-- transaction (modules/services/tx.py) and clears it before commit. The audit
-- triggers read it, so every audit row names the user.
CREATE TABLE audit_context (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id INTEGER,
    terminal_id TEXT,
    software_version_tag TEXT,
    set_at DATETIME
);

-- Login throttling (modules/services/auth.py). Keyed by the username typed, so
-- unknown usernames are throttled exactly like real ones. Not audited.
CREATE TABLE login_throttle (
    throttle_key TEXT PRIMARY KEY,
    failed_count INTEGER NOT NULL CHECK (failed_count >= 0),
    last_failed_at TEXT,
    locked_until TEXT
);

-- Authentication events. Append-only. Never holds a password, hash or code.
CREATE TABLE auth_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('Login', 'Login failed', 'Locked', 'Password changed',
        'Password reset', 'First Master created', 'Master recovered', 'Recovery failed', 'Denied', 'Company exported')),
    username TEXT,
    user_id INTEGER,
    actor_user_id INTEGER,
    permission_code TEXT
);

-- The Master's one-time recovery code, stored only as a scrypt hash. One row.
-- Not audited, so the hash never reaches audit_log.
CREATE TABLE master_recovery (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    code_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO audit_context (id) VALUES (1);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX app_user_one_master ON app_user (is_master) WHERE is_master = 1;


-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------

-- One Master per installation (docs/roles_permissions_design.md section 9).
-- The Master is the owner with universal access. The flag and the old role
-- text must not disagree, so at most one user may have is_master = 1 OR
-- role = 'Master'. The trigger gives a clear message; the partial unique
-- index app_user_one_master is the backstop.

CREATE TRIGGER app_user_one_master_insert
BEFORE INSERT ON app_user
WHEN (NEW.is_master = 1 OR NEW.role = 'Master')
     AND EXISTS (SELECT 1 FROM app_user WHERE is_master = 1 OR role = 'Master')
BEGIN
    SELECT RAISE(ABORT, 'Only one Master user is allowed per installation');
END;

CREATE TRIGGER app_user_one_master_update
BEFORE UPDATE ON app_user
WHEN (NEW.is_master = 1 OR NEW.role = 'Master')
     AND EXISTS (SELECT 1 FROM app_user
                 WHERE user_id <> NEW.user_id AND (is_master = 1 OR role = 'Master'))
BEGIN
    SELECT RAISE(ABORT, 'Only one Master user is allowed per installation');
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

CREATE TRIGGER auth_event_no_update
BEFORE UPDATE ON auth_event
BEGIN
    SELECT RAISE(ABORT, 'auth_event is append-only');
END;

CREATE TRIGGER auth_event_no_delete
BEFORE DELETE ON auth_event
BEGIN
    SELECT RAISE(ABORT, 'auth_event is append-only');
END;

-- Master audit (Phase 2.3). password_hash is NEVER written to audit_log: the
-- app_user triggers list every other column, and an update records only
-- whether the password changed ("password_changed": 1).
CREATE TRIGGER audit_app_user_insert
AFTER INSERT ON app_user
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'app_user', NEW.user_id,
        'Insert',
        NULL,
        json_object(
            'user_id', NEW.user_id,
            'username', NEW.username,
            'first_name', NEW.first_name,
            'last_name', NEW.last_name,
            'email', NEW.email,
            'role', NEW.role,
            'job_title', NEW.job_title,
            'is_active', NEW.is_active,
            'created_at', NEW.created_at,
            'is_master', NEW.is_master,
            'must_change_password', NEW.must_change_password),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_app_user_update
AFTER UPDATE ON app_user
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'app_user', NEW.user_id,
        'Update',
        json_object(
            'user_id', OLD.user_id,
            'username', OLD.username,
            'first_name', OLD.first_name,
            'last_name', OLD.last_name,
            'email', OLD.email,
            'role', OLD.role,
            'job_title', OLD.job_title,
            'is_active', OLD.is_active,
            'created_at', OLD.created_at,
            'is_master', OLD.is_master,
            'must_change_password', OLD.must_change_password),
        json_object(
            'user_id', NEW.user_id,
            'username', NEW.username,
            'first_name', NEW.first_name,
            'last_name', NEW.last_name,
            'email', NEW.email,
            'role', NEW.role,
            'job_title', NEW.job_title,
            'is_active', NEW.is_active,
            'created_at', NEW.created_at,
            'is_master', NEW.is_master,
            'must_change_password', NEW.must_change_password,
            'password_changed', NEW.password_hash IS NOT OLD.password_hash),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_app_user_delete
AFTER DELETE ON app_user
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'app_user', OLD.user_id,
        'Delete',
        json_object(
            'user_id', OLD.user_id,
            'username', OLD.username,
            'first_name', OLD.first_name,
            'last_name', OLD.last_name,
            'email', OLD.email,
            'role', OLD.role,
            'job_title', OLD.job_title,
            'is_active', OLD.is_active,
            'created_at', OLD.created_at,
            'is_master', OLD.is_master,
            'must_change_password', OLD.must_change_password),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_company_access_insert
AFTER INSERT ON user_company_access
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_company_access', NEW.rowid,
        'Insert',
        NULL,
        json_object(
            'user_id', NEW.user_id,
            'company_id', NEW.company_id,
            'role_code', NEW.role_code,
            'access_mode', NEW.access_mode),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_company_access_update
AFTER UPDATE ON user_company_access
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_company_access', NEW.rowid,
        'Update',
        json_object(
            'user_id', OLD.user_id,
            'company_id', OLD.company_id,
            'role_code', OLD.role_code,
            'access_mode', OLD.access_mode),
        json_object(
            'user_id', NEW.user_id,
            'company_id', NEW.company_id,
            'role_code', NEW.role_code,
            'access_mode', NEW.access_mode),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_user_company_access_delete
AFTER DELETE ON user_company_access
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'user_company_access', OLD.rowid,
        'Delete',
        json_object(
            'user_id', OLD.user_id,
            'company_id', OLD.company_id,
            'role_code', OLD.role_code,
            'access_mode', OLD.access_mode),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

-- Decision S1: a company code never changes (the company file is named after it).
CREATE TRIGGER company_code_immutable
BEFORE UPDATE OF company_code ON company_registry
WHEN NEW.company_code IS NOT OLD.company_code
BEGIN
    SELECT RAISE(ABORT, 'A company code cannot be changed');
END;

CREATE TRIGGER audit_company_registry_insert
AFTER INSERT ON company_registry
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_registry', NEW.company_id,
        'Insert',
        NULL,
        json_object(
            'company_id', NEW.company_id,
            'company_code', NEW.company_code,
            'legal_name', NEW.legal_name,
            'database_file_path', NEW.database_file_path,
            'parent_company_id', NEW.parent_company_id,
            'is_active', NEW.is_active,
            'is_archived', NEW.is_archived,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_registry_update
AFTER UPDATE ON company_registry
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_registry', NEW.company_id,
        'Update',
        json_object(
            'company_id', OLD.company_id,
            'company_code', OLD.company_code,
            'legal_name', OLD.legal_name,
            'database_file_path', OLD.database_file_path,
            'parent_company_id', OLD.parent_company_id,
            'is_active', OLD.is_active,
            'is_archived', OLD.is_archived,
            'created_at', OLD.created_at),
        json_object(
            'company_id', NEW.company_id,
            'company_code', NEW.company_code,
            'legal_name', NEW.legal_name,
            'database_file_path', NEW.database_file_path,
            'parent_company_id', NEW.parent_company_id,
            'is_active', NEW.is_active,
            'is_archived', NEW.is_archived,
            'created_at', NEW.created_at),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit_company_registry_delete
AFTER DELETE ON company_registry
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'company_registry', OLD.company_id,
        'Delete',
        json_object(
            'company_id', OLD.company_id,
            'company_code', OLD.company_code,
            'legal_name', OLD.legal_name,
            'database_file_path', OLD.database_file_path,
            'parent_company_id', OLD.parent_company_id,
            'is_active', OLD.is_active,
            'is_archived', OLD.is_archived,
            'created_at', OLD.created_at),
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

-- Phase 2.5 step 3b: a mirror of every ledger checkpoint, kept outside the company file, so restoring an older
-- copy of a company cannot erase what this computer saw (docs/audit_readiness_design.md 3). A read-only
-- (Auditor) verification is recorded here only. Same fields and MAC as the company's ledger_checkpoint;
-- key_id refers to the company file's ledger_chain_key. Append-only.
CREATE TABLE chain_checkpoint (
    mirror_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES company_registry(company_id),
    company_checkpoint_id INTEGER,
    recorded_from TEXT NOT NULL CHECK (recorded_from IN ('Company file', 'Read-only')),
    created_at TEXT NOT NULL,
    created_by INTEGER,
    kind TEXT NOT NULL CHECK (kind IN ('Verify', 'Period close', 'Year close', 'Report export', 'Backup', 'Restore',
                                       'Key rotation', 'Manual')),
    scope TEXT CHECK (scope IN ('Incremental', 'Full')),
    result TEXT NOT NULL CHECK (result IN ('OK', 'Broken')),
    through_entry_number INTEGER NOT NULL
        CHECK (typeof(through_entry_number) = 'integer' AND through_entry_number >= 0),
    chain_hash TEXT CHECK (chain_hash IS NULL OR (length(chain_hash) = 64 AND chain_hash NOT GLOB '*[^0-9a-f]*')),
    first_broken_entry_number INTEGER,
    key_id INTEGER,
    ref_type TEXT,
    ref_id INTEGER,
    mac TEXT NOT NULL CHECK (length(mac) = 64 AND mac NOT GLOB '*[^0-9a-f]*'),
    CHECK ((recorded_from = 'Company file') = (company_checkpoint_id IS NOT NULL)),
    CHECK ((kind = 'Verify') = (scope IS NOT NULL)),
    CHECK ((result = 'Broken') = (first_broken_entry_number IS NOT NULL)),
    CHECK ((through_entry_number = 0) = (chain_hash IS NULL))
);

CREATE INDEX chain_checkpoint_company ON chain_checkpoint (company_id, result, mirror_id);

CREATE TRIGGER chain_checkpoint_no_update
BEFORE UPDATE ON chain_checkpoint
BEGIN
    SELECT RAISE(ABORT, 'Ledger checkpoints cannot be changed');
END;

CREATE TRIGGER chain_checkpoint_no_delete
BEFORE DELETE ON chain_checkpoint
BEGIN
    SELECT RAISE(ABORT, 'Ledger checkpoints cannot be deleted');
END;

CREATE TRIGGER audit_chain_checkpoint_insert
AFTER INSERT ON chain_checkpoint
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, 'chain_checkpoint', NEW.mirror_id, 'Insert', NULL,
        json_object('mirror_id', NEW.mirror_id, 'company_id', NEW.company_id, 'company_checkpoint_id', NEW.company_checkpoint_id, 'recorded_from', NEW.recorded_from, 'created_at', NEW.created_at, 'created_by', NEW.created_by, 'kind', NEW.kind, 'scope', NEW.scope, 'result', NEW.result, 'through_entry_number', NEW.through_entry_number, 'chain_hash', NEW.chain_hash, 'first_broken_entry_number', NEW.first_broken_entry_number, 'key_id', NEW.key_id, 'ref_type', NEW.ref_type, 'ref_id', NEW.ref_id, 'mac', NEW.mac),
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;
