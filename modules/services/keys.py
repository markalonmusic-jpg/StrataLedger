"""Where ledger chain keys come from: the KeyProvider interface (docs/audit_readiness_design.md 2.7; P5, K1-K3).

Services ask `get_provider()` for a key and never touch key storage themselves, so the local DPAPI provider
(Phase 2.5 step 1c) and a hosted Azure Key Vault provider can replace each other without service changes.

* `NullKeyProvider` is the default: it always refuses, so nothing can be posted until a real provider is set
  (decision K3: never post without the key).
* `FixedKeyProvider` holds one constant key for the test suite. It refuses to load unless the environment
  variable STRATALEDGER_ALLOW_TEST_KEYS is "1", which only tests/conftest.py sets.
* Keys travel as `SecretKey`: its repr and str are redacted, it cannot be pickled, and its bytes are reached
  only through `use_for_hmac()` (the chain) and `use_for_aead()` (key wrapping, KS4). It is never put in a
  ServiceContext, and errors name at most a key id.
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

    def use_for_aead(self):
        """The bytes as an AES-GCM key (key_wrap.py only, KS4)."""
        return self._value

    def __repr__(self):
        return "<SecretKey redacted>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("A SecretKey cannot be pickled or copied out of the process")

    def __reduce_ex__(self, protocol):
        return self.__reduce__()


class KeyProvider:
    """The interface. `get_key(company_id, key_id)` returns the key a company's ledger_chain_key row `key_id`
    names, active or retired, or raises KeyUnavailableError. Retired keys must stay available for as long as the
    entries they sealed exist (step 1c's local provider keeps every retired key, wrapped, forever)."""

    def get_key(self, company_id, key_id):
        raise NotImplementedError


class NullKeyProvider(KeyProvider):
    """No key is available on this computer; posting is refused and verification is Unavailable."""

    def get_key(self, company_id, key_id):
        raise KeyUnavailableError(NO_KEY_MESSAGE)


class FixedKeyProvider(KeyProvider):
    """Constant keys for the test suite only: one key for every key id, or a {key_id: bytes} map that holds
    several (an id that is not in the map is unavailable, like a lost key)."""

    def __init__(self, keys):
        if os.environ.get("STRATALEDGER_ALLOW_TEST_KEYS") != "1":
            raise RuntimeError("FixedKeyProvider is for the test suite only")
        if isinstance(keys, dict):
            self._keys = {key_id: SecretKey(value) for key_id, value in keys.items()}
            self._single = None
        else:
            self._keys = {}
            self._single = SecretKey(keys)

    def get_key(self, company_id, key_id):
        if self._single is not None:
            return self._single
        if key_id not in self._keys:
            raise KeyUnavailableError(f"Ledger key {key_id} is not available on this computer.")
        return self._keys[key_id]

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
