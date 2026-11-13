"""The local key store (Phase 2.5 step 1c; docs/audit_readiness_design.md 2.7; KS3, KS6, KS9, KS10).

* The installation key: 32 random bytes made at first run, in the same master transaction as the Master
  (`create_installation_key`). It is never stored; the master's `installation_key` row holds its fingerprint and
  two wrapped copies: the DPAPI machine copy (made by the machine wrap the app passes in, so services never call
  the OS, H1) and the recovery copy (AES-GCM under `key_wrap.recovery_kek(code, recovery_salt)`). A DPAPI failure
  at first run leaves only the recovery copy and the key locked; the recovery copy must always be made.
* `LocalKeyProvider(master_db_path, machine_wrap)` opens the machine copy once at start-up and checks it against
  the fingerprint. `status` is 'unlocked', 'locked' (no machine copy, the machine wrap failed, or it opened to
  another key) or 'missing' (no installation key). Only an unlocked provider gives or makes keys.
* The key rows are not audited (KS9); each change writes an auth_event without the blob. Python cannot reliably
  wipe bytes from memory: the unlocked key lives in the provider for the life of the process.
"""
import hashlib
import hmac
import logging

from modules.services import key_wrap
from modules.services.errors import KeyUnavailableError, ValidationError
from modules.services.keys import KEY_STORE_LOCKED, NO_KEY_MESSAGE, KeyProvider, SecretKey
from modules.services.tx import read_connection

INSTALLATION_FINGERPRINT_LABEL = b"StrataLedger installation key fingerprint v1"
ALREADY_HAS_A_KEY = ("This installation already has a ledger key. Restore the Master with the recovery code "
                     "instead of setting up again.")

_logger = logging.getLogger("strataledger.keys")

__all__ = ["KEY_STORE_LOCKED", "NO_KEY_MESSAGE", "LocalKeyProvider", "create_installation_key",
           "installation_fingerprint", "recovery_associated_data"]


def installation_fingerprint(key):
    """HMAC-SHA256(key, label) as 64 hex characters: identifies the installation key, reveals nothing about it."""
    return hmac.new(key.use_for_aead(), INSTALLATION_FINGERPRINT_LABEL, hashlib.sha256).hexdigest()


def recovery_associated_data(fingerprint):
    return key_wrap.associated_data("installation_key", 1, "recovery", fingerprint)


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
    if conn.execute("SELECT 1 FROM installation_key WHERE id = 1").fetchone() is not None:
        raise ValidationError(ALREADY_HAS_A_KEY)
    key = key_wrap.new_secret_key()
    fingerprint = installation_fingerprint(key)
    salt = key_wrap.new_salt()
    recovery_blob = key_wrap.wrap_key(key_wrap.recovery_kek(recovery_code, salt), key,
                                      recovery_associated_data(fingerprint))
    machine_blob = _machine_copy(machine_wrap, key)
    conn.execute(
        "INSERT INTO installation_key (id, fingerprint, machine_blob, machine_wrapped_at, recovery_salt, "
        "recovery_blob, recovery_wrapped_at, created_at) VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
        (fingerprint, machine_blob, now if machine_blob else None, salt, recovery_blob, now, now))
    return machine_blob is None


class LocalKeyProvider(KeyProvider):
    """The key provider of a desktop installation: the installation key opened with DPAPI (P5: Azure Key Vault
    replaces it when hosted, with no service change)."""

    def __init__(self, master_db_path, machine_wrap):
        self._master_db_path = master_db_path
        self._machine_wrap = machine_wrap
        self._installation = None
        self.status = "missing"
        self.unlock()

    @property
    def is_unlocked(self):
        return self.status == "unlocked"

    def unlock(self):
        """Open the machine copy. Sets `status`; never raises for a locked key."""
        self._installation = None
        conn = read_connection(self._master_db_path)
        try:
            row = conn.execute("SELECT fingerprint, machine_blob FROM installation_key WHERE id = 1").fetchone()
        finally:
            conn.close()
        if row is None:
            self.status = "missing"
            return self.status
        self.status = "locked"
        if row["machine_blob"] is None or self._machine_wrap is None:
            return self.status
        try:
            key = SecretKey(self._machine_wrap.unprotect(bytes(row["machine_blob"])))
        except Exception as error:  # noqa: BLE001  (DPAPI failing here means another computer or account)
            _logger.warning("the ledger key could not be opened on this computer: %s", type(error).__name__)
            return self.status
        if not hmac.compare_digest(installation_fingerprint(key), row["fingerprint"]):
            _logger.warning("the ledger key opened on this computer is not this installation's key")
            return self.status
        self._installation = key
        self.status = "unlocked"
        return self.status

    def _require_unlocked(self, error):
        if not self.is_unlocked:
            raise error

    def get_key(self, company_id, key_id):
        self._require_unlocked(KeyUnavailableError(NO_KEY_MESSAGE))
        raise KeyUnavailableError(f"Ledger key {key_id} is not available on this computer.")

    def __repr__(self):
        return f"<LocalKeyProvider {self.status}>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("A key provider cannot be pickled or copied out of the process")

