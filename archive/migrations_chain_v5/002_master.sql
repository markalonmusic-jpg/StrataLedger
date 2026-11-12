-- Migration 2 (master): finish the system_master.db upgrade (F8).
--
-- A legacy app_user / company_registry survives 001 (CREATE TABLE IF NOT EXISTS)
-- with nullable names, no role CHECK, role DEFAULT 'Admin', and an
-- ON DELETE NO ACTION parent link. Both are rebuilt here to the 001
-- definitions. Rows are copied as they are; missing names become ''. A role
-- outside the allowed list fails the CHECK and blocks the whole upgrade.
--
-- company_profile is a company table and does not belong in the master
-- database (CLAUDE.md section 2). The legacy file holds one placeholder row
-- naming the master itself; it is dropped (kept in the pre-upgrade backup).

DROP TRIGGER IF EXISTS app_user_default_created_at;

CREATE TABLE new_app_user (
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
INSERT INTO new_app_user (user_id, username, password_hash, first_name, last_name, email, role, job_title, is_active, created_at)
    SELECT user_id, username, password_hash, COALESCE(first_name, ''), COALESCE(last_name, ''),
           COALESCE(email, ''), role, COALESCE(job_title, ''), is_active, created_at
    FROM app_user;
DROP TABLE app_user;
ALTER TABLE new_app_user RENAME TO app_user;

CREATE TABLE new_company_registry (
    company_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code        TEXT NOT NULL UNIQUE,
    legal_name          TEXT NOT NULL,
    database_file_path  TEXT NOT NULL,
    parent_company_id   INTEGER DEFAULT NULL,
    is_active           INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_company_id) REFERENCES company_registry(company_id) ON DELETE SET NULL
);
INSERT INTO new_company_registry (company_id, company_code, legal_name, database_file_path, parent_company_id, is_active, created_at)
    SELECT company_id, company_code, legal_name, database_file_path, parent_company_id, is_active, created_at
    FROM company_registry;
DROP TABLE company_registry;
ALTER TABLE new_company_registry RENAME TO company_registry;

DROP TABLE IF EXISTS company_profile;
