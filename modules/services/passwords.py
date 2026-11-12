"""Password and recovery-code hashing (CLAUDE.md rule 13).

Stored format, one self-describing string:

    scrypt$<N>$<r>$<p>$<salt, base64>$<hash, base64>

The salt is 16 random bytes per hash. Verification recomputes with the stored
parameters and compares with hmac.compare_digest. Anything not in this exact
format (plaintext, empty, another scheme) never verifies. Raising N, R or P
later makes needs_rehash() true for older hashes; login then rewrites them.
"""
import base64
import binascii
import hashlib
import hmac
import secrets

from modules.services.errors import ValidationError

SCHEME = "scrypt"
N = 2 ** 15
R = 8
P = 1
SALT_BYTES = 16
DKLEN = 64
MAXMEM = 64 * 1024 * 1024  # N=2^15, r=8 needs ~32 MiB, exactly hashlib's default ceiling
MIN_LENGTH = 12
MAX_LENGTH = 1024
RECOVERY_BYTES = 20  # 160 bits


def check_password_policy(password):
    if not isinstance(password, str) or len(password) < MIN_LENGTH:
        raise ValidationError(f"Passwords must be at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise ValidationError(f"Passwords must be at most {MAX_LENGTH} characters")


def _derive(secret, salt, n, r, p):
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=DKLEN, maxmem=MAXMEM)


def _encode(raw):
    return base64.b64encode(raw).decode("ascii")


def hash_password(password):
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, N, R, P)
    return f"{SCHEME}${N}${R}${P}${_encode(salt)}${_encode(digest)}"


def _parse(stored):
    """(n, r, p, salt, digest) or None when stored is not in the format."""
    if not isinstance(stored, str):
        return None
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != SCHEME:
        return None
    try:
        n, r, p = (int(x) for x in parts[1:4])
        salt = base64.b64decode(parts[4], validate=True)
        digest = base64.b64decode(parts[5], validate=True)
    except (ValueError, binascii.Error):
        return None
    if n < 2 or n & (n - 1) or r < 1 or p < 1 or not salt or len(digest) != DKLEN:
        return None
    return n, r, p, salt, digest


def verify_password(password, stored):
    parsed = _parse(stored)
    if parsed is None or not isinstance(password, str):
        return False
    n, r, p, salt, digest = parsed
    try:
        candidate = _derive(password, salt, n, r, p)
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(candidate, digest)


def needs_rehash(stored):
    parsed = _parse(stored)
    if parsed is None:
        return True
    n, r, p, _, _ = parsed
    return n < N or r < R or p < P


# --- Recovery codes -------------------------------------------------------------------

def generate_recovery_code():
    """A one-time code: 160 random bits as 8 groups of 4 base32 characters."""
    raw = base64.b32encode(secrets.token_bytes(RECOVERY_BYTES)).decode("ascii")
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def normalize_recovery_code(code):
    """The code as it is hashed and as its key is derived: letters and digits only, upper case."""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def hash_recovery_code(code):
    return hash_password(normalize_recovery_code(code))


def verify_recovery_code(code, stored):
    return verify_password(normalize_recovery_code(code), stored)
