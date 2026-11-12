"""key_wrap.py: AES-256-GCM key wrapping and the recovery-code key-encryption key (Step 1c; KS2, KS4; audit design
2.7).

* A wrapped key is `version (1 byte) | nonce (12) | ciphertext (32) | tag (16)`. The version byte and the caller's
  associated data (which names the row the blob belongs to) are authenticated, so a blob changed anywhere, or moved
  to another row, is refused.
* The recovery-code key comes from hashlib.scrypt (N=2^15, r=8, p=1) over the normalised code, with its own salt
  behind a fixed label, so it can never equal any part of the stored recovery-code hash even if a salt were reused.
* Every refusal is KeyUnavailableError with the fixed text WRAP_REFUSED and no chained cause.
* Keys travel as SecretKey; its AES-GCM accessor is `use_for_aead()`.
"""
import hashlib
import pickle
import re
from pathlib import Path

import pytest

from modules.services import key_wrap, passwords
from modules.services.errors import KeyUnavailableError
from modules.services.key_wrap import (WRAP_REFUSED, associated_data, new_salt, new_secret_key, recovery_kek,
                                       unwrap_key, wrap_key)
from modules.services.keys import SecretKey

ROOT = Path(__file__).resolve().parent.parent
KEK = SecretKey(bytes(range(32)))
KEY = SecretKey(bytes(range(100, 132)))
AD = associated_data("installation", 1, "recovery")
CODE = "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"
SALT = bytes(16)


def _refused(call, *args):
    with pytest.raises(KeyUnavailableError) as caught:
        call(*args)
    assert str(caught.value) == WRAP_REFUSED
    assert caught.value.__cause__ is None
    return caught.value


# --- SecretKey's AES-GCM accessor (KS4) ----------------------------------------------------------------------------

def test_secret_key_names_its_aead_use_and_stays_redacted():
    assert KEY.use_for_aead() == bytes(range(100, 132)) == KEY.use_for_hmac()
    assert repr(KEY) == str(KEY) == "<SecretKey redacted>"
    with pytest.raises(TypeError):
        pickle.dumps(KEY)


# --- Wrapping ----------------------------------------------------------------------------------------------------

def test_a_wrapped_key_unwraps_to_the_same_key():
    unwrapped = unwrap_key(KEK, wrap_key(KEK, KEY, AD), AD)
    assert isinstance(unwrapped, SecretKey) and unwrapped.use_for_aead() == KEY.use_for_aead()


def test_the_blob_has_the_documented_layout_and_never_the_key_in_clear():
    blob = wrap_key(KEK, KEY, AD)
    assert len(blob) == 1 + 12 + 32 + 16 and blob[0] == key_wrap.WRAP_VERSION == 1
    assert KEY.use_for_aead() not in blob and KEK.use_for_aead() not in blob


def test_wrapping_twice_uses_a_new_nonce():
    first, second = wrap_key(KEK, KEY, AD), wrap_key(KEK, KEY, AD)
    assert first[1:13] != second[1:13] and first != second


def test_the_wrong_key_encryption_key_is_refused():
    _refused(unwrap_key, SecretKey(bytes(32)), wrap_key(KEK, KEY, AD), AD)


@pytest.mark.parametrize("position", [0, 1, 12, 13, 44, 45, 60], ids=["version", "nonce-first", "nonce-last",
                                                                       "ciphertext-first", "ciphertext-last",
                                                                       "tag-first", "tag-last"])
def test_a_blob_changed_anywhere_is_refused(position):
    blob = bytearray(wrap_key(KEK, KEY, AD))
    blob[position] ^= 0x01
    _refused(unwrap_key, KEK, bytes(blob), AD)


def test_a_blob_moved_to_another_row_is_refused():
    blob = wrap_key(KEK, KEY, associated_data("company_key", 7, "a" * 64, "chain"))
    for other in (associated_data("company_key", 8, "a" * 64, "chain"),
                  associated_data("company_key", 7, "b" * 64, "chain"),
                  associated_data("company_key", 7, "a" * 64, "encryption"),
                  b""):
        _refused(unwrap_key, KEK, blob, other)


@pytest.mark.parametrize("blob", [b"", b"\x01", b"\x01" + bytes(59), b"\x01" + bytes(61), bytes(61), "text", None],
                         ids=["empty", "version-only", "short", "long", "version-0", "str", "none"])
def test_a_blob_of_the_wrong_shape_is_refused(blob):
    _refused(unwrap_key, KEK, blob, AD)


def test_wrapping_takes_secret_keys_never_raw_bytes():
    with pytest.raises(TypeError):
        wrap_key(KEK.use_for_aead(), KEY, AD)
    with pytest.raises(TypeError):
        wrap_key(KEK, KEY.use_for_aead(), AD)
    with pytest.raises(TypeError):
        unwrap_key(KEK.use_for_aead(), wrap_key(KEK, KEY, AD), AD)
    with pytest.raises(TypeError):
        wrap_key(KEK, KEY, "not bytes")


def test_a_refusal_never_holds_a_key_or_the_blob():
    blob = wrap_key(KEK, KEY, AD)
    error = _refused(unwrap_key, SecretKey(bytes(32)), blob, AD)
    text = f"{error!r} {error}"
    for secret in (KEK.use_for_aead(), KEY.use_for_aead(), blob):
        assert secret.hex() not in text
    assert error.__suppress_context__


def test_a_new_secret_key_is_32_random_bytes():
    first, second = new_secret_key(), new_secret_key()
    assert isinstance(first, SecretKey) and len(first.use_for_aead()) == 32
    assert first.use_for_aead() != second.use_for_aead()


# --- Associated data ---------------------------------------------------------------------------------------------

def test_associated_data_has_a_fixed_label_and_length_prefixed_typed_parts():
    assert associated_data("ab", 7) == (b"StrataLedger key wrap v1"
                                        + b"s" + (2).to_bytes(4, "big") + b"ab"
                                        + b"i" + (1).to_bytes(4, "big") + b"7")


def test_associated_data_cannot_be_confused_between_parts():
    assert associated_data("ab", "c") != associated_data("a", "bc")
    assert associated_data(1) != associated_data("1")
    assert associated_data("a") != associated_data("a", "")


@pytest.mark.parametrize("part", [True, None, b"bytes", 1.5])
def test_associated_data_takes_only_text_and_whole_numbers(part):
    with pytest.raises(TypeError):
        associated_data("x", part)


# --- The recovery-code key-encryption key (KS2) --------------------------------------------------------------------

def test_the_recovery_key_is_scrypt_over_the_normalised_code_behind_its_label():
    expected = hashlib.scrypt(passwords.normalize_recovery_code(CODE).encode("utf-8"),
                              salt=b"StrataLedger recovery key v1" + SALT, n=2 ** 15, r=8, p=1, dklen=32,
                              maxmem=64 * 1024 * 1024)
    kek = recovery_kek(CODE, SALT)
    assert isinstance(kek, SecretKey) and kek.use_for_aead() == expected


def test_the_recovery_key_ignores_case_dashes_and_spaces():
    loose = " abcd efgh-ijkl mnop qrst-uvwx yz23 4567 "
    assert recovery_kek(loose, SALT).use_for_aead() == recovery_kek(CODE, SALT).use_for_aead()


def test_a_different_code_or_salt_gives_a_different_key():
    base = recovery_kek(CODE, SALT).use_for_aead()
    assert recovery_kek(CODE.replace("A", "B"), SALT).use_for_aead() != base
    assert recovery_kek(CODE, b"\x01" * 16).use_for_aead() != base


def test_the_recovery_key_is_never_part_of_the_stored_code_hash_even_with_the_same_salt():
    """passwords.py stores scrypt(code, salt, dklen 64); without the label the key would be its first half."""
    stored_style = hashlib.scrypt(passwords.normalize_recovery_code(CODE).encode("utf-8"), salt=SALT, n=2 ** 15,
                                  r=8, p=1, dklen=64, maxmem=64 * 1024 * 1024)
    kek = recovery_kek(CODE, SALT).use_for_aead()
    assert kek not in stored_style


def test_the_recovery_key_needs_a_code_and_a_16_byte_salt():
    for code in ("", "  - -  ", None):
        with pytest.raises(ValueError):
            recovery_kek(code, SALT)
    for salt in (b"", bytes(15), bytes(17), "0" * 16):
        with pytest.raises((ValueError, TypeError)):
            recovery_kek(CODE, salt)


def test_a_new_salt_is_16_random_bytes():
    assert len(new_salt()) == 16 and new_salt() != new_salt()


def test_a_code_wrapped_key_opens_with_the_code_and_not_with_another():
    blob = wrap_key(recovery_kek(CODE, SALT), KEY, AD)
    assert unwrap_key(recovery_kek(CODE.lower(), SALT), blob, AD).use_for_aead() == KEY.use_for_aead()
    _refused(unwrap_key, recovery_kek(CODE.replace("Z", "Y"), SALT), blob, AD)


# --- Where cryptography is used -------------------------------------------------------------------------------------

def test_cryptography_is_imported_only_by_the_key_wrap_module():
    pattern = re.compile(r"^\s*(from|import)\s+cryptography\b", re.MULTILINE)
    files = list((ROOT / "modules").rglob("*.py")) + [ROOT / "app_strata.pyw", ROOT / "config.py"]
    offenders = [str(p.relative_to(ROOT)) for p in files
                 if p.name != "key_wrap.py" and pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
