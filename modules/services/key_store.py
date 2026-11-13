"""The local key store (Phase 2.5 step 1c; docs/audit_readiness_design.md 2.7; KS3, KS6, KS9, KS10).

* The installation key: 32 random bytes made at first run, in the same master transaction as the Master
  (`create_installation_key`). It is never stored; the master's `installation_key` row holds its fingerprint and
  two wrapped copies: the DPAPI machine copy (made by the machine wrap the app passes in, so services never call
  the OS, H1) and the recovery copy (AES-GCM under `key_wrap.recovery_kek(code, recovery_salt)`). A DPAPI failure
  at first run leaves only the recovery copy and the key locked; the recovery copy must always be made.
* `LocalKeyProvider(master_db_path, machine_wrap)` opens the machine copy once at start-up and checks it against
  the fingerprint. `status` is 'unlocked', 'locked' (no machine copy, the machine wrap failed, or it opened to
  another key) or 'missing' (no installation key). Only an unlocked provider gives or makes keys.
* Company chain keys (`new_chain_key`, `store_chain_key`): random, wrapped by the installation key with AES-GCM
  in the master's `company_key`, bound to the company, purpose and fingerprint by the associated data.
  `get_key(company_id, key_id)` finds the stored key by the fingerprint of the company file's key row (KS3).
* The test switch `use_test_key_for_new_companies` makes create_company use the suite's fixed key and store
  nothing in the master; it works only while STRATALEDGER_ALLOW_TEST_KEYS is "1" (KS7).
* The key rows are not audited (KS9); each change writes an auth_event without the blob. Python cannot reliably
  wipe bytes from memory: the unlocked key lives in the provider for the life of the process.
"""
import hashlib
import hmac
import logging
import os

from modules.services import key_wrap, ledger_chain
from modules.services.errors import KeyStoreLockedError, KeyUnavailableError, ValidationError
from modules.services.keys import KEY_STORE_LOCKED, NO_KEY_MESSAGE, KeyProvider, SecretKey
from modules.services.paths import resolve_company_path
from modules.services.tx import read_connection

INSTALLATION_FINGERPRINT_LABEL = b"StrataLedger installation key fingerprint v1"
ALREADY_HAS_A_KEY = ("This installation already has a ledger key. Restore the Master with the recovery code "
                     "instead of setting up again.")

TEST_KEYS_FLAG = "STRATALEDGER_ALLOW_TEST_KEYS"
TEST_ONLY = "The test key switch is for the test suite only"
CHAIN = "chain"

_logger = logging.getLogger("strataledger.keys")
_test_new_company_key = None

__all__ = ["KEY_STORE_LOCKED", "NO_KEY_MESSAGE", "LocalKeyProvider", "company_key_associated_data",
           "create_installation_key", "installation_fingerprint", "recovery_associated_data",
           "open_machine_copy", "open_with_machine_wrap", "open_with_recovery_code",
           "rewrap_installation_key", "switched_on_test_key", "use_test_key_for_new_companies"]


def installation_fingerprint(key):
    """HMAC-SHA256(key, label) as 64 hex characters: identifies the installation key, reveals nothing about it."""
    return hmac.new(key.use_for_aead(), INSTALLATION_FINGERPRINT_LABEL, hashlib.sha256).hexdigest()


def recovery_associated_data(fingerprint):
    return key_wrap.associated_data("installation_key", 1, "recovery", fingerprint)


def company_key_associated_data(company_id, purpose, fingerprint):
    return key_wrap.associated_data("company_key", company_id, purpose, fingerprint)


# --- The test switch (KS7) ------------------------------------------------------------------------------------

def _require_test_flag():
    if os.environ.get(TEST_KEYS_FLAG) != "1":
        raise RuntimeError(TEST_ONLY)


def use_test_key_for_new_companies(key):
    """Tests only: new companies get this fixed chain key (bytes), or the real path again with None."""
    global _test_new_company_key
    _require_test_flag()
    _test_new_company_key = None if key is None else SecretKey(key)


def switched_on_test_key():
    """The switched-on test key, or None. A switch left on without the flag is refused."""
    if _test_new_company_key is None:
        return None
    _require_test_flag()
    return _test_new_company_key


def _machine_copy(machine_wrap, key):
    """The DPAPI copy, or None if there is no machine wrap or it fails (only the error type is logged)."""
    if machine_wrap is None:
        return None
    try:
        blob = machine_wrap.protect(key.use_for_aead())
    except Exception as error:  # noqa: BLE001  (any OS failure leaves the key locked, never the setup undone)
        _logger.warning("the ledger key could not be protected for this computer: %s", type(error).__name__)
        return None
    return blob if isinstance(blob, bytes) and blob else None


def create_installation_key(conn, recovery_code, machine_wrap, now):
    """Make the installation key inside the caller's master transaction. Returns True if it is locked (no DPAPI
    copy). Raises ValidationError if the installation already has one: it can never be replaced."""
    if conn.execute("SELECT 1 FROM installation_key WHERE is_active = 1").fetchone() is not None:
        raise ValidationError(ALREADY_HAS_A_KEY)
    key = key_wrap.new_secret_key()
    fingerprint = installation_fingerprint(key)
    salt = key_wrap.new_salt()
    recovery_blob = key_wrap.wrap_key(key_wrap.recovery_kek(recovery_code, salt), key,
                                      recovery_associated_data(fingerprint))
    machine_blob = _machine_copy(machine_wrap, key)
    conn.execute(
        "INSERT INTO installation_key (fingerprint, machine_blob, machine_wrapped_at, recovery_salt, "
        "recovery_blob, recovery_wrapped_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (fingerprint, machine_blob, now if machine_blob else None, salt, recovery_blob, now, now))
    return machine_blob is None


def open_machine_copy(row, machine_wrap):
    """The installation key from an installation_key row's DPAPI copy, or None (no copy, no wrap, DPAPI failed, or
    it opened to another key). Only the error type is logged."""
    if row["machine_blob"] is None or machine_wrap is None:
        return None
    try:
        key = SecretKey(machine_wrap.unprotect(bytes(row["machine_blob"])))
    except Exception as error:  # noqa: BLE001  (DPAPI failing here means another computer or account)
        _logger.warning("the ledger key could not be opened on this computer: %s", type(error).__name__)
        return None
    if not hmac.compare_digest(installation_fingerprint(key), row["fingerprint"]):
        _logger.warning("the ledger key opened on this computer is not this installation's key")
        return None
    return key


def _installation_row(conn):
    return conn.execute("SELECT fingerprint, machine_blob, recovery_salt, recovery_blob FROM installation_key "
                        "WHERE is_active = 1").fetchone()


def open_with_recovery_code(conn, code):
    """The installation key from its recovery copy, or None (no key, a wrong code, or a damaged copy)."""
    row = _installation_row(conn)
    if row is None:
        return None
    try:
        key = key_wrap.unwrap_key(key_wrap.recovery_kek(code, bytes(row["recovery_salt"])),
                                  bytes(row["recovery_blob"]), recovery_associated_data(row["fingerprint"]))
    except (KeyUnavailableError, ValueError):
        return None
    return key if hmac.compare_digest(installation_fingerprint(key), row["fingerprint"]) else None


def open_with_machine_wrap(conn, machine_wrap):
    """The installation key from its DPAPI copy on this computer, or None."""
    row = _installation_row(conn)
    return None if row is None else open_machine_copy(row, machine_wrap)


def rewrap_installation_key(conn, key, new_code, machine_wrap, now):
    """Re-wrap the installation key inside the caller's master transaction: the recovery copy with `new_code`
    (a new salt) and, when `machine_wrap` is given and works, the DPAPI copy for this computer. A failed machine
    wrap keeps the old DPAPI copy. Returns True if a DPAPI copy for this computer was written."""
    fingerprint = installation_fingerprint(key)
    salt = key_wrap.new_salt()
    blob = key_wrap.wrap_key(key_wrap.recovery_kek(new_code, salt), key, recovery_associated_data(fingerprint))
    conn.execute("UPDATE installation_key SET recovery_salt = ?, recovery_blob = ?, recovery_wrapped_at = ? "
                 "WHERE is_active = 1", (salt, blob, now))
    machine_blob = _machine_copy(machine_wrap, key)
    if machine_blob is not None:
        conn.execute("UPDATE installation_key SET machine_blob = ?, machine_wrapped_at = ? WHERE is_active = 1",
                     (machine_blob, now))
    return machine_blob is not None


class LocalKeyProvider(KeyProvider):
    """The key provider of a desktop installation: the installation key opened with DPAPI (P5: Azure Key Vault
    replaces it when hosted, with no service change)."""

    def __init__(self, master_db_path, machine_wrap):
        self._master_db_path = master_db_path
        self._machine_wrap = machine_wrap
        self._installation = None
        self._installation_id = None
        self._cache = {}
        self.status = "missing"
        self.unlock()

    @property
    def is_unlocked(self):
        return self.status == "unlocked"

    def unlock(self):
        """Open the machine copy. Sets `status`; never raises for a locked key."""
        self._installation = None
        self._installation_id = None
        self._cache = {}
        conn = read_connection(self._master_db_path)
        try:
            row = conn.execute("SELECT id, fingerprint, machine_blob FROM installation_key "
                               "WHERE is_active = 1").fetchone()
        finally:
            conn.close()
        if row is None:
            self.status = "missing"
            return self.status
        self.status = "locked"
        key = open_machine_copy(row, self._machine_wrap)
        if key is None:
            return self.status
        self._installation = key
        self._installation_id = row["id"]
        self.status = "unlocked"
        return self.status

    def _require_unlocked(self, error):
        if not self.is_unlocked:
            raise error

    def get_key(self, company_id, key_id):
        self._require_unlocked(KeyUnavailableError(NO_KEY_MESSAGE))
        unavailable = KeyUnavailableError(f"Ledger key {key_id} is not available on this computer.")
        fingerprint = self._company_fingerprint(company_id, key_id)     # read every time: the file may be replaced
        if fingerprint is None:
            raise unavailable
        cached = self._cache.get((company_id, fingerprint))
        if cached is not None:
            return cached
        conn = read_connection(self._master_db_path)
        try:
            row = conn.execute("SELECT wrapped_key FROM company_key WHERE company_id = ? AND purpose = ? "
                               "AND fingerprint = ?", (company_id, CHAIN, fingerprint)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise unavailable
        try:
            key = key_wrap.unwrap_key(self._installation, bytes(row["wrapped_key"]),
                                      company_key_associated_data(company_id, CHAIN, fingerprint))
        except KeyUnavailableError:
            raise unavailable from None
        if not hmac.compare_digest(ledger_chain.fingerprint(key.use_for_hmac()), fingerprint):
            raise unavailable
        self._cache[(company_id, fingerprint)] = key
        return key

    def _company_fingerprint(self, company_id, key_id):
        """The fingerprint of the company file's ledger_chain_key row `key_id`, or None."""
        conn = read_connection(self._master_db_path)
        try:
            registry = conn.execute("SELECT database_file_path FROM company_registry WHERE company_id = ?",
                                    (company_id,)).fetchone()
        finally:
            conn.close()
        if registry is None:
            return None
        path = resolve_company_path(registry["database_file_path"])
        if not os.path.isfile(path):
            return None
        conn = read_connection(path)
        try:
            row = conn.execute("SELECT fingerprint FROM ledger_chain_key WHERE key_id = ?", (key_id,)).fetchone()
        finally:
            conn.close()
        return row["fingerprint"] if row else None

    def new_chain_key(self):
        self._require_unlocked(KeyStoreLockedError(KEY_STORE_LOCKED))
        return SecretKey(ledger_chain.new_key())

    def store_chain_key(self, conn, company_id, key, now):
        self._require_unlocked(KeyStoreLockedError(KEY_STORE_LOCKED))
        fingerprint = ledger_chain.fingerprint(key.use_for_hmac())
        blob = key_wrap.wrap_key(self._installation, key, company_key_associated_data(company_id, CHAIN, fingerprint))
        conn.execute("INSERT INTO company_key (company_id, purpose, fingerprint, wrapped_key, installation_key_id, "
                     "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (company_id, CHAIN, fingerprint, blob, self._installation_id, now))

    def __repr__(self):
        return f"<LocalKeyProvider {self.status}>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("A key provider cannot be pickled or copied out of the process")

