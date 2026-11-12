-- Migration 3 (master): Master flag, no role CHECK, per-company role and access mode
-- (Phase 2.2a; docs/roles_permissions_design.md sections 4 and 9).
--
-- * app_user.is_master marks the one Master of the installation (universal
--   access). Existing rows with role = 'Master' are backfilled.
-- * The role CHECK is dropped so custom roles and Viewer work. The role column
--   itself stays for now: login, the sidebar's NAV_ITEMS and views_new_user.py
--   still read it. A later master migration drops it after Phase 3.
-- * At most one user may be the Master, whether by the flag or by the old role
--   text, so the two cannot disagree. A trigger gives a clear message; a
--   partial unique index is the backstop. A file that already has two
--   role = 'Master' users fails the backfill below with that message and the
--   upgrade is rolled back untouched.
-- * user_company_access gains role_code (the company role for that user, text
--   with no foreign key because roles live in the company database) and
--   access_mode ('Deny' on a child company narrows access inherited from its
--   parent).
--
-- app_user is rebuilt (SQLite cannot drop a CHECK in place). The migration
-- runner switches foreign keys OFF for the rebuild, so dropping app_user does
-- not cascade into user_company_access; foreign_key_check runs before commit.

CREATE TABLE new_app_user (
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
    is_master INTEGER NOT NULL DEFAULT 0 CHECK (is_master IN (0, 1))
);
INSERT INTO new_app_user (user_id, username, password_hash, first_name, last_name, email, role, job_title, is_active, created_at)
    SELECT user_id, username, password_hash, first_name, last_name, email, role, job_title, is_active, created_at
    FROM app_user;
DROP TABLE app_user;
ALTER TABLE new_app_user RENAME TO app_user;

CREATE UNIQUE INDEX app_user_one_master ON app_user (is_master) WHERE is_master = 1;

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

UPDATE app_user SET is_master = 1 WHERE role = 'Master';

ALTER TABLE user_company_access ADD COLUMN role_code TEXT;
ALTER TABLE user_company_access ADD COLUMN access_mode TEXT NOT NULL DEFAULT 'Grant'
    CHECK (access_mode IN ('Grant', 'Deny'));
