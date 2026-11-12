"""Where ledger chain keys come from: the KeyProvider interface (docs/audit_readiness_design.md 2.7; P5, K1-K3).

Services ask `get_provider()` for a key and never touch key storage themselves, so the local DPAPI provider
(Phase 2.5 step 1c) and a hosted Azure Key Vault provider can replace each other without service changes.

* `NullKeyProvider` is the default: it always refuses, so nothing can be posted until a real provider is set
  (decision K3: never post without the key).
* `FixedKeyProvider` holds one constant key for the test suite. It refuses to load unless the environment
  variable STRATALEDGER_ALLOW_TEST_KEYS is "1", which only tests/conftest.py sets.
* Keys travel as `SecretKey`: its repr and str are redacted, it cannot be pickled, and its bytes are reached
  only through `use_for_hmac()`. It is never put in a ServiceContext, and errors name at most a key id.
"""
import os

from modules.services.errors import KeyUnavailableError

NO_KEY_MESSAGE = ("This computer cannot seal ledger entries right now. Ask the Master to sign in and restore the "
                  "ledger key with the recovery code.")


class SecretKey:
    """Key bytes that do not leak into logs, reprs, pickles or exception text."""

    __slots__ = ("_value",)

    def __init__(self, value):
        if not isinstance(value, bytes) or len(value) != 32:
            raise ValueError("A chain key is 32 bytes")
        self._value = value

    def use_for_hmac(self):
        return self._value

    def __repr__(self):
        return "<SecretKey redacted>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("A SecretKey cannot be pickled or copied out of the process")

    def __reduce_ex__(self, protocol):
        return self.__reduce__()


class KeyProvider:
    """The interface. `chain_key` returns the key that sealed (or will seal) under `key_id` in a company."""

    def chain_key(self, company_id, key_id):
        raise NotImplementedError


class NullKeyProvider(KeyProvider):
    """No key is available on this computer; posting is refused."""

    def chain_key(self, company_id, key_id):
        raise KeyUnavailableError(NO_KEY_MESSAGE)


class FixedKeyProvider(KeyProvider):
    """One constant key for every company and key id. Tests only."""

    def __init__(self, key_bytes):
        if os.environ.get("STRATALEDGER_ALLOW_TEST_KEYS") != "1":
            raise RuntimeError("FixedKeyProvider is for the test suite only")
        self._key = SecretKey(key_bytes)

    def chain_key(self, company_id, key_id):
        return self._key

    def __repr__(self):
        return "<FixedKeyProvider>"


_provider = NullKeyProvider()


def get_provider():
    """The provider this process uses (set once at start-up by the app in step 1c; tests swap it)."""
    return _provider


def set_provider(provider):
    global _provider
    if not isinstance(provider, KeyProvider):
        raise TypeError("Use a KeyProvider")
    _provider = provider
