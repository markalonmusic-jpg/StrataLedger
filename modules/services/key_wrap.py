"""Key wrapping with AES-256-GCM and the recovery-code key-encryption key (Step 1c; KS2, KS4; audit design 2.7).

The only module that imports `cryptography` (a test enforces it).

* `wrap_key(kek, key, associated)` returns `version (1 byte) | nonce (12) | ciphertext (32) | tag (16)`. The nonce is
  random for every wrap. The version byte and the caller's associated data are authenticated: the associated data
  names the row a blob belongs to (`associated_data(...)`), so a blob copied to another row does not open.
* `unwrap_key(kek, blob, associated)` returns the key as a SecretKey. Any refusal (wrong key, a changed or moved
  blob, the wrong shape) is KeyUnavailableError with the fixed text WRAP_REFUSED and no chained cause.
* `recovery_kek(code, salt)` derives the key that wraps the installation key's recovery copy: hashlib.scrypt
  (N=2^15, r=8, p=1, 32 bytes) over the normalised code, with the salt behind the fixed label RECOVERY_LABEL. The
  salt is the key's own, never the login hash's (KS2); the label also keeps the result from ever being part of
  the stored recovery-code hash if a salt were reused.

Keys go in and come out as SecretKey only, so every use of the bytes stays named (`use_for_aead()`).
"""
import hashlib
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from modules.services.errors import KeyUnavailableError
from modules.services.keys import SecretKey
from modules.services.passwords import normalize_recovery_code

WRAP_VERSION = 1
NONCE_BYTES = 12
KEY_BYTES = 32
TAG_BYTES = 16
BLOB_BYTES = 1 + NONCE_BYTES + KEY_BYTES + TAG_BYTES
SALT_BYTES = 16
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
AD_LABEL = b"StrataLedger key wrap v1"
RECOVERY_LABEL = b"StrataLedger recovery key v1"

WRAP_REFUSED = "A stored ledger key could not be opened: it does not match this key, or it has been changed."


def new_secret_key():
    """32 random bytes from the operating system's secure source, as a SecretKey."""
    return SecretKey(secrets.token_bytes(KEY_BYTES))


def new_salt():
    return secrets.token_bytes(SALT_BYTES)


def associated_data(*parts):
    """The fixed label, then each part as a type letter, a 4-byte length and its UTF-8 text, so no two different
    lists of parts give the same bytes. Parts are text or whole numbers."""
    out = [AD_LABEL]
    for part in parts:
        if isinstance(part, bool) or not isinstance(part, (str, int)):
            raise TypeError("Associated data parts are text or whole numbers")
        kind, text = (b"i", str(part)) if isinstance(part, int) else (b"s", part)
        encoded = text.encode("utf-8")
        out.append(kind + len(encoded).to_bytes(4, "big") + encoded)
    return b"".join(out)


def _check_secret(value, name):
    if not isinstance(value, SecretKey):
        raise TypeError(f"{name} must be a SecretKey")


def _check_associated(associated):
    if not isinstance(associated, bytes):
        raise TypeError("Associated data must be bytes")


def wrap_key(kek, key, associated):
    _check_secret(kek, "The key-encryption key")
    _check_secret(key, "The key")
    _check_associated(associated)
    header = bytes([WRAP_VERSION])
    nonce = secrets.token_bytes(NONCE_BYTES)
    return header + nonce + AESGCM(kek.use_for_aead()).encrypt(nonce, key.use_for_aead(), header + associated)


def unwrap_key(kek, blob, associated):
    _check_secret(kek, "The key-encryption key")
    _check_associated(associated)
    if not isinstance(blob, bytes) or len(blob) != BLOB_BYTES or blob[0] != WRAP_VERSION:
        raise KeyUnavailableError(WRAP_REFUSED)
    header, nonce, sealed = blob[:1], blob[1:1 + NONCE_BYTES], blob[1 + NONCE_BYTES:]
    try:
        value = AESGCM(kek.use_for_aead()).decrypt(nonce, sealed, header + associated)
    except InvalidTag:
        raise KeyUnavailableError(WRAP_REFUSED) from None
    return SecretKey(value)


def recovery_kek(code, salt):
    """The recovery code's key-encryption key (KS2)."""
    normalised = normalize_recovery_code(code)
    if not normalised:
        raise ValueError("A recovery code is needed")
    if not isinstance(salt, bytes):
        raise TypeError("The salt must be bytes")
    if len(salt) != SALT_BYTES:
        raise ValueError(f"The salt is {SALT_BYTES} bytes")
    return SecretKey(hashlib.scrypt(normalised.encode("utf-8"), salt=RECOVERY_LABEL + salt, n=SCRYPT_N, r=SCRYPT_R,
                                    p=SCRYPT_P, dklen=KEY_BYTES, maxmem=SCRYPT_MAXMEM))
