"""Authentication: the first Master, login, throttling, password change and Master recovery.

CLAUDE.md rule 13 and docs/roles_permissions_design.md section 9.

* Passwords are hashed by modules/services/passwords.py; a stored value that is
  not in its format never verifies (no plaintext fallback).
* Every login failure gives the same message. An unknown username still runs
  one scrypt verification against a dummy hash, so it takes as long.
* Throttling is keyed by the username typed (unknown names included): from the
  LOCK_AFTER-th consecutive failure the key is locked for
  BASE_LOCK_SECONDS * 2^(failures - LOCK_AFTER), capped at MAX_LOCK_SECONDS.
  While locked, attempts are refused without checking the password and do not
  extend the lock. A success clears the key. Master recovery is throttled the
  same way under RECOVERY_KEY.
* auth_event and the log file record who and what, never a password, hash or code.
* A session whose password was reset (must_change_password) may only call
  change_password; every other service raises PasswordChangeRequiredError.

Login and the first Master cannot be permission-checked (there is no user yet,
or the user is proving who they are); they are excluded from the rule-10 static
test by name.
"""
import logging
import math
import os
import re
import sqlite3
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import modules.database as database
from modules.services import key_store, passwords
from modules.services.errors import (
    AuthenticationError, KeyStoreLockedError, LoginThrottledError, PasswordChangeRequiredError,
    PermissionDeniedError, ValidationError,
)
from modules.services.tx import read_connection, write_transaction

LOCK_AFTER = 5
BASE_LOCK_SECONDS = 30
MAX_LOCK_SECONDS = 900
RECOVERY_KEY = "#recovery"  # '#' is not allowed in usernames, so this key never collides with one
USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")
INVALID_LOGIN = "Invalid username or password"

_logger = logging.getLogger("strataledger")
_dummy_hash = None


@dataclass(frozen=True)
class Session:
    """Who logged in. Plain data: services re-read the user from the master on every call."""
    user_id: int
    username: str
    first_name: str
    is_master: bool
    legacy_role: str  # app_user.role, read only by the sidebar until Phase 3
    must_change_password: bool
    master_db_path: str


class _HoldsACode:
    """A result that carries a recovery code: its repr and str show `<redacted>` in place of the code, and it
    cannot be pickled or copied, so a log line, a traceback or a test failure never prints the code."""
    __slots__ = ()

    def __repr__(self):
        shown = ", ".join(f"{name}=<redacted>" if name == "recovery_code" else f"{name}={value!r}"
                          for name, value in zip(self._fields, self))
        return f"{type(self).__name__}({shown})"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError(f"A {type(self).__name__} holds a recovery code and cannot be pickled or copied")

    def __reduce_ex__(self, protocol):
        return self.__reduce__()

    def __copy__(self):
        return self.__reduce__()

    def __deepcopy__(self, memo):
        return self.__reduce__()


class FirstMaster(_HoldsACode, namedtuple("FirstMaster", "user_id recovery_code ledger_key_locked",
                                          defaults=(False,))):
    __slots__ = ()


class CodeIssued(_HoldsACode, namedtuple("CodeIssued", "recovery_code ledger_key_restored message")):
    """A new Master recovery code (recover_master, change_master_password, issue_recovery_code).
    `ledger_key_restored` is False when the installation key could not be re-wrapped for this computer; `message`
    then says why."""
    __slots__ = ()

LEDGER_KEY_NOT_RESTORED = ("The new recovery code is saved, but the ledger key could not be restored: neither its "
                           "recovery copy nor this computer's copy opens. Nothing can be posted on this "
                           "installation until the ledger key is replaced; keep the new code and ask for help.")
LEDGER_KEY_LOCKED_HERE = ("The Master password was reset, but this computer could not protect the ledger key, so "
                          "it stays locked here. Keep the new recovery code and try again on this computer.")
NEW_CODE_NEEDS_KEY = ("A new recovery code cannot be issued while the ledger key is locked on this computer. "
                      "Restore it with the current recovery code first.")


class _Actor(namedtuple("_Actor", "user_id now")):
    """All write_transaction needs for audit_context. Authentication runs before any context exists,
    so the actor takes its time from auth._now() (the one allow-listed clock read in this file)."""

    def __new__(cls, user_id):
        return super().__new__(cls, user_id, _iso(_now()))


def _now():
    return datetime.now(timezone.utc)


def _iso(moment):
    return moment.isoformat(timespec="seconds")


# --- Input checks ------------------------------------------------------------------------

def check_username(username):
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        raise ValidationError("Usernames are 3 to 64 letters, digits or . _ @ -")


def check_person(first_name, last_name, email):
    if not str(first_name or "").strip() or not str(last_name or "").strip():
        raise ValidationError("First and last name are required")
    email = str(email or "").strip()
    if "@" not in email or " " in email or email.startswith("@") or email.endswith("@"):
        raise ValidationError("Enter a valid email address")


# --- First run: is there a Master yet? (decision S10) -------------------------------------------

def inspect_master(master_db_path):
    """Look at the master file without changing it: (state, error type or None).

    'missing' (no file, or an empty one), 'no_users' (a valid master with nobody in it: setup is needed),
    'ready' (at least one user), or 'unreadable' (not a database, from an older or different baseline,
    or damaged). The error type is the exception class name for 'unreadable', never its text.
    """
    path = os.fspath(master_db_path)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return "missing", None
    try:
        database.check_master_database(path)
        conn = database.get_readonly_connection(path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0]
        finally:
            conn.close()
    except (database.SchemaUpgradeBlockedError, sqlite3.Error) as error:
        return "unreadable", type(error).__name__
    return ("ready" if count else "no_users"), None


def master_setup_state(master_db_path):
    return inspect_master(master_db_path)[0]


# --- First Master and recovery ---------------------------------------------------------------

def create_first_master(master_db_path, username, password, first_name, last_name, email, *, machine_wrap=None):
    """Create the installation's Master. Only while the master database has no users.

    Returns FirstMaster(user_id, recovery_code, ledger_key_locked). The recovery code is shown to the
    caller once; only its scrypt hash is stored, and it is never logged.

    The installation key is made in the same transaction (Step 1c, key_store.create_installation_key), wrapped
    with the recovery code and with `machine_wrap` (the app passes platform_support.DPAPI; services never call
    the OS). Without a machine copy the Master is still created and `ledger_key_locked` is True.
    """
    check_username(username)
    passwords.check_password_policy(password)
    check_person(first_name, last_name, email)
    database.ensure_master_database(master_db_path)
    password_hash = passwords.hash_password(password)
    code = passwords.generate_recovery_code()
    code_hash = passwords.hash_recovery_code(code)
    with write_transaction(master_db_path, _Actor(None)) as conn:
        if conn.execute("SELECT 1 FROM app_user LIMIT 1").fetchone() is not None:
            raise ValidationError("The first Master can only be created while there are no users")
        user_id = conn.execute(
            "INSERT INTO app_user (username, password_hash, first_name, last_name, email, role, is_master) "
            "VALUES (?, ?, ?, ?, ?, 'Master', 1) RETURNING user_id",
            (username, password_hash, first_name.strip(), last_name.strip(), email.strip()),
        ).fetchone()[0]
        conn.execute("INSERT INTO master_recovery (id, code_hash, created_at) VALUES (1, ?, ?) "
                     "ON CONFLICT (id) DO UPDATE SET code_hash = excluded.code_hash, created_at = excluded.created_at",
                     (code_hash, _iso(_now())))
        _insert_event(conn, "First Master created", username=username, user_id=user_id, actor_user_id=user_id)
        locked = key_store.create_installation_key(conn, code, machine_wrap, _iso(_now()))
        _insert_event(conn, "Installation key created", user_id=user_id, actor_user_id=user_id)
    _logger.info("first Master created: user=%s", user_id)
    return FirstMaster(user_id, code, locked)


def recover_master(master_db_path, code, new_password, *, machine_wrap=None):
    """Set a new Master password with the one-time recovery code. Returns CodeIssued with the NEW code.

    In the same transaction the installation key is opened with the old code and re-wrapped: its recovery copy
    with the new code and, through `machine_wrap` (the app passes platform_support.DPAPI), its DPAPI copy for this
    computer, which restores a key that is locked here (KS5). If the code is valid but its copy does not open, the
    password is still reset and the result says the ledger key could not be restored.
    """
    passwords.check_password_policy(new_password)
    _check_throttle(master_db_path, RECOVERY_KEY)
    conn = read_connection(master_db_path)
    try:
        stored = conn.execute("SELECT code_hash FROM master_recovery WHERE id = 1").fetchone()
        master = conn.execute("SELECT user_id, username FROM app_user WHERE is_master = 1").fetchone()
    finally:
        conn.close()
    valid = passwords.verify_recovery_code(code, stored["code_hash"] if stored else _dummy())
    if not (valid and stored and master):
        _record_failure(master_db_path, RECOVERY_KEY, "Recovery failed", username=None, user_id=None)
        raise AuthenticationError("The recovery code is not valid")
    new_code = passwords.generate_recovery_code()
    with write_transaction(master_db_path, _Actor(master["user_id"])) as conn:
        conn.execute("UPDATE app_user SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
                     (passwords.hash_password(new_password), master["user_id"]))
        opened, here = _replace_code(conn, master["user_id"], code, new_code, machine_wrap)
        conn.execute("DELETE FROM login_throttle WHERE throttle_key IN (?, ?)", (RECOVERY_KEY, master["username"]))
        _insert_event(conn, "Master recovered", username=master["username"], user_id=master["user_id"],
                      actor_user_id=master["user_id"])
    _logger.warning("Master password recovered with the recovery code: user=%s", master["user_id"])
    if not opened:
        return CodeIssued(new_code, False, LEDGER_KEY_NOT_RESTORED)
    if not here:
        return CodeIssued(new_code, False, LEDGER_KEY_LOCKED_HERE)
    return CodeIssued(new_code, True, None)


def change_master_password(session, current_password, code, new_password, *, machine_wrap=None):
    """The Master's password change (PW9): the current password AND the recovery code. Issues a new code at once
    and re-wraps the installation key's recovery copy with it, in the same transaction (opened with the old code,
    or with this computer's DPAPI copy through `machine_wrap` if the code's copy is damaged). Returns CodeIssued."""
    require_master(session, "master.change_password")
    passwords.check_password_policy(new_password)
    row = _verify_own_password(session, current_password)
    if current_password == new_password:
        raise ValidationError("Choose a password different from the current one")
    _verify_master_code(session.master_db_path, code)
    new_code = passwords.generate_recovery_code()
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        conn.execute("UPDATE app_user SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
                     (passwords.hash_password(new_password), session.user_id))
        opened, _here = _replace_code(conn, session.user_id, code, new_code, machine_wrap)
        _insert_event(conn, "Recovery code issued", username=row["username"], user_id=session.user_id,
                      actor_user_id=session.user_id)
        _insert_event(conn, "Password changed", username=row["username"], user_id=session.user_id,
                      actor_user_id=session.user_id)
    return CodeIssued(new_code, True, None) if opened else CodeIssued(new_code, False, LEDGER_KEY_NOT_RESTORED)


def issue_recovery_code(session, password, *, machine_wrap=None):
    """A new Master recovery code after the password is entered again (backlog 11), for a code lost while this
    computer can still open the ledger key: the DPAPI copy (through `machine_wrap`) opens the installation key and
    its recovery copy is re-wrapped with the new code. Refused while the key is locked here, because a new code
    must always open the key. Returns CodeIssued."""
    require_master(session, "master.recovery_code")
    row = _verify_own_password(session, password)
    new_code = passwords.generate_recovery_code()
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        key = key_store.open_with_machine_wrap(conn, machine_wrap)
        if key is None:
            raise KeyStoreLockedError(NEW_CODE_NEEDS_KEY)
        key_store.rewrap_installation_key(conn, key, new_code, None, _iso(_now()))
        _set_code_hash(conn, new_code)
        _insert_event(conn, "Installation key rewrapped", user_id=session.user_id, actor_user_id=session.user_id)
        _insert_event(conn, "Recovery code issued", username=row["username"], user_id=session.user_id,
                      actor_user_id=session.user_id)
    _logger.warning("a new Master recovery code was issued: user=%s", session.user_id)
    return CodeIssued(new_code, True, None)


def _set_code_hash(conn, new_code):
    conn.execute("UPDATE master_recovery SET code_hash = ?, created_at = ? WHERE id = 1",
                 (passwords.hash_recovery_code(new_code), _iso(_now())))


def _replace_code(conn, user_id, old_code, new_code, machine_wrap):
    """Inside the caller's master transaction: open the installation key with the old code (or, if that copy is
    damaged, with this computer's DPAPI copy through `machine_wrap`), re-wrap it with the new code (and for this
    computer when `machine_wrap` is given), and store the new code's hash. Returns (opened, protected_here)."""
    key = key_store.open_with_recovery_code(conn, old_code)
    if key is None:
        key = key_store.open_with_machine_wrap(conn, machine_wrap)
        if key is not None:
            _logger.warning("the ledger key's recovery copy did not open; it was rebuilt from this computer's copy")
    here = False
    if key is not None:
        here = key_store.rewrap_installation_key(conn, key, new_code, machine_wrap, _iso(_now()))
        _insert_event(conn, "Installation key rewrapped", user_id=user_id, actor_user_id=user_id)
    else:
        _logger.error("the Master recovery code is valid but neither copy of the ledger key opened")
    _set_code_hash(conn, new_code)
    return key is not None, here


def _verify_own_password(session, password):
    """The session user's row if `password` is theirs; otherwise a throttled failure and AuthenticationError."""
    _check_throttle(session.master_db_path, session.username)
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT username, is_active, password_hash FROM app_user WHERE user_id = ?",
                           (session.user_id,)).fetchone()
    finally:
        conn.close()
    verified = passwords.verify_password(password, row["password_hash"] if row else _dummy())
    if row is None or row["is_active"] != 1 or not verified:
        _record_failure(session.master_db_path, session.username, "Login failed", username=session.username,
                        user_id=session.user_id)
        raise AuthenticationError("The current password is not correct")
    return row


def _verify_master_code(master_db_path, code):
    """Check the Master recovery code (throttled under RECOVERY_KEY); AuthenticationError if it is not valid."""
    _check_throttle(master_db_path, RECOVERY_KEY)
    conn = read_connection(master_db_path)
    try:
        stored = conn.execute("SELECT code_hash FROM master_recovery WHERE id = 1").fetchone()
    finally:
        conn.close()
    valid = passwords.verify_recovery_code(code, stored["code_hash"] if stored else _dummy())
    if not (valid and stored):
        _record_failure(master_db_path, RECOVERY_KEY, "Recovery failed", username=None, user_id=None)
        raise AuthenticationError("The recovery code is not valid")


# --- Login and password change ----------------------------------------------------------------

def login(master_db_path, username, password):
    """Return a Session, or raise AuthenticationError / LoginThrottledError."""
    username = str(username or "").strip()
    _check_throttle(master_db_path, username)
    conn = read_connection(master_db_path)
    try:
        row = conn.execute(
            "SELECT user_id, username, first_name, is_master, role, is_active, must_change_password, password_hash "
            "FROM app_user WHERE username = ?", (username,),
        ).fetchone()
    finally:
        conn.close()
    verified = passwords.verify_password(password, row["password_hash"] if row else _dummy())
    if row is None or not verified or row["is_active"] != 1:
        _record_failure(master_db_path, username, "Login failed", username=username,
                        user_id=row["user_id"] if row else None)
        raise AuthenticationError(INVALID_LOGIN)
    rehash = passwords.needs_rehash(row["password_hash"])

    def succeed(conn):
        conn.execute("DELETE FROM login_throttle WHERE throttle_key = ?", (username,))
        _insert_event(conn, "Login", username=username, user_id=row["user_id"])
        if rehash:
            conn.execute("UPDATE app_user SET password_hash = ? WHERE user_id = ?",
                         (passwords.hash_password(password), row["user_id"]))
    _auth_write(master_db_path, succeed, actor_user_id=row["user_id"])
    return Session(user_id=row["user_id"], username=row["username"], first_name=row["first_name"],
                   is_master=row["is_master"] == 1, legacy_role=row["role"],
                   must_change_password=row["must_change_password"] == 1, master_db_path=str(master_db_path))


def change_password(session, old_password, new_password):
    """Change one's own password (the old one must verify). Clears must_change_password."""
    passwords.check_password_policy(new_password)
    _check_throttle(session.master_db_path, session.username)
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT username, is_active, password_hash FROM app_user WHERE user_id = ?",
                           (session.user_id,)).fetchone()
    finally:
        conn.close()
    verified = passwords.verify_password(old_password, row["password_hash"] if row else _dummy())
    if row is None or row["is_active"] != 1 or not verified:
        _record_failure(session.master_db_path, session.username, "Login failed", username=session.username,
                        user_id=session.user_id)
        raise AuthenticationError("The current password is not correct")
    if old_password == new_password:
        raise ValidationError("Choose a password different from the current one")
    with write_transaction(session.master_db_path, _Actor(session.user_id)) as conn:
        conn.execute("UPDATE app_user SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
                     (passwords.hash_password(new_password), session.user_id))
        _insert_event(conn, "Password changed", username=row["username"], user_id=session.user_id,
                      actor_user_id=session.user_id)


# --- Helpers for the other services -----------------------------------------------------------------

def active_user(session):
    """Re-read the session's user. Inactive or missing: PermissionDeniedError; reset: PasswordChangeRequiredError."""
    conn = read_connection(session.master_db_path)
    try:
        row = conn.execute("SELECT user_id, username, is_active, is_master, must_change_password FROM app_user "
                           "WHERE user_id = ?", (session.user_id,)).fetchone()
    finally:
        conn.close()
    if row is None or row["is_active"] != 1:
        raise PermissionDeniedError("Not permitted")
    if row["must_change_password"] == 1:
        raise PasswordChangeRequiredError("Change your password before continuing")
    return row


def require_master(session, permission_code="master"):
    """Allow only the Master; otherwise log a denial to auth_event and raise PermissionDeniedError."""
    user = active_user(session)
    if user["is_master"] != 1:
        _deny_master(session, permission_code)
    return user


def _deny_master(session, permission_code):
    """Log an installation-level denial (no company file applies) and raise."""
    _auth_write(session.master_db_path, lambda conn: _insert_event(
        conn, "Denied", username=session.username, user_id=session.user_id, actor_user_id=session.user_id,
        permission_code=permission_code))
    raise PermissionDeniedError(f"Not permitted: {permission_code}")


# --- internals -----------------------------------------------------------------------------------

def _dummy():
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = passwords.hash_password(passwords.generate_recovery_code())
    return _dummy_hash


def _insert_event(conn, event_type, *, username=None, user_id=None, actor_user_id=None, permission_code=None,
                  company_id=None):
    conn.execute(
        "INSERT INTO auth_event (occurred_at, event_type, username, user_id, actor_user_id, permission_code, "
        "company_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_iso(_now()), event_type, username, user_id, actor_user_id, permission_code, company_id),
    )


def _auth_write(master_db_path, work, actor_user_id=None):
    """Run work(conn) in one short master transaction (throttle rows and auth_event).

    Goes through write_transaction, so audit_context is set (to actor_user_id, or no one) and
    cleared there and nowhere else (H4). Excluded from the rule-10 static test by name: it
    records authentication itself.
    """
    with write_transaction(master_db_path, _Actor(actor_user_id)) as conn:
        work(conn)


def _check_throttle(master_db_path, key):
    conn = read_connection(master_db_path)
    try:
        row = conn.execute("SELECT locked_until FROM login_throttle WHERE throttle_key = ?", (key,)).fetchone()
    finally:
        conn.close()
    if row is None or not row["locked_until"]:
        return
    remaining = (datetime.fromisoformat(row["locked_until"]) - _now()).total_seconds()
    if remaining > 0:
        raise LoginThrottledError(math.ceil(remaining))


def _lock_seconds(failures):
    if failures < LOCK_AFTER:
        return 0
    return min(BASE_LOCK_SECONDS * 2 ** (failures - LOCK_AFTER), MAX_LOCK_SECONDS)


def _record_failure(master_db_path, key, event_type, *, username, user_id):
    def work(conn):
        row = conn.execute("SELECT failed_count FROM login_throttle WHERE throttle_key = ?", (key,)).fetchone()
        failures = (row["failed_count"] if row else 0) + 1
        now = _now()
        seconds = _lock_seconds(failures)
        locked_until = _iso(now + timedelta(seconds=seconds)) if seconds else None
        conn.execute(
            "INSERT INTO login_throttle (throttle_key, failed_count, last_failed_at, locked_until) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (throttle_key) DO UPDATE SET failed_count = excluded.failed_count, "
            "last_failed_at = excluded.last_failed_at, locked_until = excluded.locked_until",
            (key, failures, _iso(now), locked_until),
        )
        _insert_event(conn, event_type, username=username, user_id=user_id)
        if seconds:
            _insert_event(conn, "Locked", username=username, user_id=user_id)
        _logger.warning("%s: username=%s failures=%d lock_seconds=%d", event_type, username, failures, seconds)
    _auth_write(master_db_path, work)
