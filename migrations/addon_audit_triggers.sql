-- HA9 (2026-11-17): the audit triggers the add-on migration runner gives every `<key>_` table. They match the
-- baseline's audit triggers. modules/database.py fills in __TABLE__, and __NEW__ / __OLD__ with JSON of every
-- column. This file is not a migration: the baseline runner never reads it.

CREATE TRIGGER audit___TABLE___insert
AFTER INSERT ON __TABLE__
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, '__TABLE__', NEW.rowid,
        'Insert',
        NULL,
        __NEW__,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit___TABLE___update
AFTER UPDATE ON __TABLE__
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, '__TABLE__', NEW.rowid,
        'Update',
        __OLD__,
        __NEW__,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;

CREATE TRIGGER audit___TABLE___delete
AFTER DELETE ON __TABLE__
BEGIN
    INSERT INTO audit_log (user_id, table_name, record_id, action, old_value, new_value,
                           software_version_tag, terminal_id)
    SELECT ctx.user_id, '__TABLE__', OLD.rowid,
        'Delete',
        __OLD__,
        NULL,
        ctx.software_version_tag, ctx.terminal_id
    FROM (SELECT 1) LEFT JOIN audit_context AS ctx ON ctx.id = 1;
END;
