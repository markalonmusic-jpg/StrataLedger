"""Transaction helpers: the only way services touch a company database.

write_transaction sets audit_context so the audit triggers in the baseline know
who is writing. audit_context has no `origin` column yet (it comes with the AI
support schema work), so origin is validated on the context but not stored here.

Services call authorize() BEFORE opening a write transaction (rule 10, static
test): a denial is then logged in its own transaction and never waits on, or is
rolled back with, the caller's.
"""
import socket
from contextlib import contextmanager

import config
import modules.database as database
from modules.services.errors import PermissionDeniedError


@contextmanager
def write_transaction(db_path, context):
    """Yield a connection inside BEGIN IMMEDIATE with audit_context set.

    Commits on success (after clearing audit_context so a user never leaks into
    a later write), rolls back everything, including the audit_context change,
    on any exception, and always closes the connection. A read-only context (Auditor) cannot open a write
    on its company file; it may still record in the master (a verification result, design section 6).
    """
    if getattr(context, "read_only", False) and str(db_path) == str(context.company_db_path):
        raise PermissionDeniedError("This company is open read-only.")
    conn = database.get_connection(db_path)
    try:
        conn.isolation_level = None  # explicit transaction control
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE audit_context SET user_id = ?, terminal_id = ?, "
                "software_version_tag = ?, set_at = ? WHERE id = 1",
                (context.user_id, socket.gethostname(), config.APP_VERSION, context.now),
            )
            yield conn
            conn.execute(
                "UPDATE audit_context SET user_id = NULL, terminal_id = NULL, "
                "software_version_tag = NULL WHERE id = 1"
            )
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def read_connection(db_path):
    """Return a read-only connection. The caller closes it."""
    return database.get_readonly_connection(db_path)
