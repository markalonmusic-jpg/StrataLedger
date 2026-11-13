"""Replacing a lost installation key (Phase 2.5 step 1d part B; docs/audit_readiness_design.md 2.7; KS13, KS17,
KS19-KS21).

The installation key is lost when this computer's DPAPI copy does not open it and the recovery code is lost too
(or both copies are damaged). Then no company key can be opened, so nothing can be posted. The Master can make a
new installation key:

1. `replacement_preview(session, machine_wrap=)`: Master only, read only. Whether the key still opens here, and
   every company in the registry (archived included, KS19) that will get a new key epoch, so the screen shows the
   count the service will use (KS17).
2. `replace_installation_key(session, password, confirm_text=, machine_wrap=)`, in order: the Master check (rule
   10, before anything else); the typed phrase `NEW LEDGER KEY` (checked before the password, so a mistyped phrase
   never counts as a failed sign-in); the Master's password (throttled like a sign-in); refused while the DPAPI
   copy still opens (KEY_NOT_LOST). Then ONE master transaction: the old key retired ('Key lost'), a new one with a
   NEW recovery code (also the new master_recovery hash) and this computer's DPAPI copy (refused, and nothing
   saved, if this computer cannot protect it), and the 'Installation key replaced' and 'Recovery code issued'
   events. The process's key provider then holds the new key (the app also calls App.start_key_store() again).
   Then each company enters a key-lost epoch (ledger_keys.start_new_key_epoch). That part is not atomic across
   files: each company is reported 'done' or 'failed' with one sentence, and the code is shown once (the result
   redacts it everywhere else, like auth.CodeIssued).
3. `remaining_companies(session)` finds the companies left behind (their active ledger key is not wrapped by the
   active installation key) and `finish_remaining_companies(session)` starts their epochs.

The old installation key row keeps its recovery copy (a found code could still open old blobs later, KS18; not
used in 1d). Old company_key rows are kept and never opened.
"""
import logging
import os
from collections import namedtuple

from modules.services import auth, key_store, keys, ledger_keys, passwords
from modules.services.errors import KeyStoreLockedError, ServiceError, ValidationError
from modules.services.paths import resolve_company_path
from modules.services.tx import read_connection, write_transaction

CONFIRM_PHRASE = "NEW LEDGER KEY"
PERMISSION = "master.replace_installation_key"
KEY_NOT_LOST = "The ledger key is still available on this computer, so it is not lost."
NO_INSTALLATION_KEY = "This installation has no ledger key yet, so there is nothing to replace."
WRONG_PHRASE = f"Type {CONFIRM_PHRASE} exactly as shown to make a new ledger key."
NEW_KEY_NOT_PROTECTED = ("This computer could not protect a new ledger key, so nothing was changed. Try again, or "
                         "ask for help if it keeps failing.")
COMPANY_NOT_FINISHED = ("A new ledger key could not be started for this company; use Finish the remaining "
                        "companies to try again.")
COMPANY_FILE_MISSING = "The company file is missing."

_logger = logging.getLogger("strataledger.keys")


class KeyReplaced(auth._HoldsACode, namedtuple("KeyReplaced", "recovery_code companies message")):
    """A new installation key: the new recovery code (shown once), one {'company_id', 'company_code', 'status'
    ('done' or 'failed'), 'message'} per company, and a one-sentence summary. Redacted and not copyable."""
    __slots__ = ()


def _registry(master_db_path):
    conn = read_connection(master_db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT company_id, company_code, legal_name, is_archived, database_file_path FROM company_registry "
            "ORDER BY company_id")]
    finally:
        conn.close()


def _key_opens_here(master_db_path, machine_wrap):
    """None when there is no installation key, else whether its DPAPI copy opens on this computer."""
    conn = read_connection(master_db_path)
    try:
        if conn.execute("SELECT 1 FROM installation_key WHERE is_active = 1").fetchone() is None:
            return None
        return key_store.open_with_machine_wrap(conn, machine_wrap) is not None
    finally:
        conn.close()


def _company_count(n):
    return f"{n} {'company' if n == 1 else 'companies'}"


def replacement_preview(session, *, machine_wrap=None):
    """What replacing the installation key would do (Master only, writes nothing): {'key_available_here',
    'company_count', 'companies': [{'company_id', 'company_code', 'legal_name', 'is_archived'}], 'message'}."""
    auth.require_master(session, PERMISSION)
    opens = _key_opens_here(session.master_db_path, machine_wrap)
    listed = [{"company_id": c["company_id"], "company_code": c["company_code"], "legal_name": c["legal_name"],
               "is_archived": c["is_archived"] == 1} for c in _registry(session.master_db_path)]
    if opens is None:
        message = NO_INSTALLATION_KEY
    elif opens:
        message = KEY_NOT_LOST
    else:
        message = (f"Every company's ledger history up to today will no longer be verifiable: "
                   f"{_company_count(len(listed))} will get a new ledger key. Type {CONFIRM_PHRASE} to continue.")
    return {"key_available_here": bool(opens), "company_count": len(listed), "companies": listed, "message": message}


def replace_installation_key(session, password, *, confirm_text, machine_wrap):
    """Replace a lost installation key and start a new key epoch in every company (see the module docstring).
    Returns KeyReplaced."""
    auth.require_master(session, PERMISSION)
    if not isinstance(confirm_text, str) or confirm_text != CONFIRM_PHRASE:
        raise ValidationError(WRONG_PHRASE)
    row = auth._verify_own_password(session, password)
    opens = _key_opens_here(session.master_db_path, machine_wrap)
    if opens is None:
        raise ValidationError(NO_INSTALLATION_KEY)
    if opens:
        raise ValidationError(KEY_NOT_LOST)
    new_code = passwords.generate_recovery_code()
    actor = auth._Actor(session.user_id)
    with write_transaction(session.master_db_path, actor) as conn:
        if key_store.open_with_machine_wrap(conn, machine_wrap) is not None:     # re-checked inside the write
            raise ValidationError(KEY_NOT_LOST)
        if key_store.replace_installation_key(conn, new_code, machine_wrap, actor.now):
            raise KeyStoreLockedError(NEW_KEY_NOT_PROTECTED)                  # rolls the whole change back
        auth._set_code_hash(conn, new_code)
        auth._insert_event(conn, "Installation key replaced", user_id=session.user_id, actor_user_id=session.user_id)
        auth._insert_event(conn, "Recovery code issued", username=row["username"], user_id=session.user_id,
                           actor_user_id=session.user_id)
    _logger.warning("the installation key was replaced: user=%s", session.user_id)
    keys.set_provider(key_store.LocalKeyProvider(session.master_db_path, machine_wrap))
    results = [_start_epoch(session, company) for company in _registry(session.master_db_path)]
    return KeyReplaced(new_code, results, _summary(results))


def _start_epoch(session, company):
    """One company's new key epoch; never raises. A typed service error's sentence is shown as is; anything else
    is logged (type only) and reported as COMPANY_NOT_FINISHED."""
    outcome = {"company_id": company["company_id"], "company_code": company["company_code"]}
    if not os.path.isfile(resolve_company_path(company["database_file_path"])):
        return {**outcome, "status": "failed", "message": COMPANY_FILE_MISSING}
    try:
        result = ledger_keys.start_new_key_epoch(session, company["company_id"],
                                                 confirm_company_code=company["company_code"])
    except ServiceError as error:
        _logger.warning("no new ledger key for company_id=%s: %s", company["company_id"], type(error).__name__)
        return {**outcome, "status": "failed", "message": str(error)}
    except Exception as error:              # noqa: BLE001  (reported per company; the installation key is replaced)
        _logger.error("no new ledger key for company_id=%s: %s", company["company_id"], type(error).__name__)
        return {**outcome, "status": "failed", "message": COMPANY_NOT_FINISHED}
    message = result["message"]
    if result.get("checkpoint_error"):
        message += " " + result["checkpoint_error"]
    return {**outcome, "status": "done", "message": message}


def _summary(results):
    failed = [r for r in results if r["status"] == "failed"]
    done = len(results) - len(failed)
    text = (f"A new ledger key was made and {_company_count(done)} started a new ledger key. Save the new recovery "
            "code now; it is shown only once.")
    if failed:
        text += (f" {_company_count(len(failed))} could not be finished; use Finish the remaining companies once "
                 "the problem is fixed.")
    return text


def _left_behind(master_db_path, company):
    """True if the company's active ledger key is not wrapped by the active installation key (or its file cannot
    be read)."""
    path = resolve_company_path(company["database_file_path"])
    if not os.path.isfile(path):
        return True
    conn = read_connection(path)
    try:
        active = conn.execute("SELECT fingerprint FROM ledger_chain_key WHERE is_active = 1").fetchone()
    finally:
        conn.close()
    if active is None:
        return True
    conn = read_connection(master_db_path)
    try:
        return conn.execute(
            "SELECT 1 FROM company_key AS k JOIN installation_key AS i ON i.id = k.installation_key_id "
            "WHERE i.is_active = 1 AND k.company_id = ? AND k.purpose = 'chain' AND k.fingerprint = ?",
            (company["company_id"], active["fingerprint"])).fetchone() is None
    finally:
        conn.close()


def remaining_companies(session):
    """The companies left behind by a replacement (Master only): [{'company_id', 'company_code', 'legal_name',
    'is_archived'}]."""
    auth.require_master(session, PERMISSION)
    return [{"company_id": c["company_id"], "company_code": c["company_code"], "legal_name": c["legal_name"],
             "is_archived": c["is_archived"] == 1}
            for c in _registry(session.master_db_path) if _left_behind(session.master_db_path, c)]


def finish_remaining_companies(session):
    """Start the new key epoch in every company left behind (Master only). Returns one result per company, as in
    KeyReplaced.companies; an empty list when none is left."""
    auth.require_master(session, PERMISSION)
    left = {c["company_id"] for c in remaining_companies(session)}
    return [_start_epoch(session, c) for c in _registry(session.master_db_path) if c["company_id"] in left]
