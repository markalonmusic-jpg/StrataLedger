"""Opening a company: the only way a session gets a ServiceContext."""
import os

import modules.database as database
from modules.services import auth, authz
from modules.services.context import ServiceContext
from modules.services.errors import NotFoundError
from modules.services.paths import resolve_company_path
from modules.services.tx import read_connection


def open_company(session, company_id):
    """Check access, open the company file through the baseline guard, and return its context.

    1. The session's user is re-read (inactive: denied; password reset: must change first).
    2. The registry path is resolved under config.BASE_PROJECT_DIR; a path outside it
       is refused (ValidationError) and a missing file is never created (NotFoundError).
    3. The file goes through database.ensure_company_database: a stale or chain-built
       file raises SchemaUpgradeBlockedError and is left unchanged.
    4. Access: the Master, or the nearest Grant row with an active role
       (check_company_access; a denial is logged in the company's access_event).
    5. The Master's open is recorded as an 'Open company' access_event.
    """
    auth.active_user(session)
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT database_file_path FROM company_registry WHERE company_id = ?",
                           (company_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise NotFoundError(f"No such company: {company_id}")
    path = resolve_company_path(row["database_file_path"])
    if not os.path.isfile(path):
        raise NotFoundError("The company file is missing")
    database.ensure_company_database(path)  # pre-release: a no-op for current files, blocks stale ones
    context = ServiceContext(user_id=session.user_id, company_id=company_id, origin="Human",
                             company_db_path=path, master_db_path=session.master_db_path)
    authz.check_company_access(context)
    authz.record_company_open(context)
    return context
