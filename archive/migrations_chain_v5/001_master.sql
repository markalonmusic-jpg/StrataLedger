-- Generated from accounting_librebase.db; reviewed migration 1.

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

CREATE TABLE IF NOT EXISTS user_company_access (
    user_id    INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES company_registry(company_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, company_id)
);
