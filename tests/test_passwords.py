"""Password hashing: scrypt, per-user salt, one self-describing string, constant-time compare."""
import pytest

from modules.services import passwords
from modules.services.errors import ValidationError

GOOD = "correct horse battery"


def test_format_is_self_describing():
    stored = passwords.hash_password(GOOD)
    scheme, n, r, p, salt, digest = stored.split("$")
    assert (scheme, int(n), int(r), int(p)) == ("scrypt", passwords.N, passwords.R, passwords.P)
    assert passwords.N >= 2 ** 15 and passwords.R >= 8
    assert salt and digest


def test_each_hash_has_its_own_salt():
    first, second = passwords.hash_password(GOOD), passwords.hash_password(GOOD)
    assert first != second
    assert first.split("$")[4] != second.split("$")[4]


def test_verify_accepts_the_right_password_only():
    stored = passwords.hash_password(GOOD)
    assert passwords.verify_password(GOOD, stored)
    assert not passwords.verify_password(GOOD + "x", stored)
    assert not passwords.verify_password("", stored)


@pytest.mark.parametrize("stored", [
    GOOD,                                  # plaintext: never accepted
    "", None, "scrypt", "scrypt$1$2$3",
    "bcrypt$32768$8$1$c2FsdA==$aGFzaA==",  # unknown scheme
    "scrypt$x$8$1$c2FsdA==$aGFzaA==",      # bad number
    "scrypt$32768$8$1$***$aGFzaA==",       # bad base64
    "scrypt$32768$8$1$c2FsdA==$aGFzaA==$extra",
])
def test_anything_not_in_the_format_fails(stored):
    assert passwords.verify_password(GOOD, stored) is False


def test_verify_uses_a_constant_time_compare():
    source = open(passwords.__file__, encoding="utf-8").read()
    assert "hmac.compare_digest" in source
    assert "==" not in source.split("def verify_password")[1].split("def ")[0].replace("!=", "")


def test_old_parameters_still_verify_and_need_a_rehash(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(passwords, "N", 2 ** 14)
        old = passwords.hash_password(GOOD)
    assert passwords.verify_password(GOOD, old)
    assert passwords.needs_rehash(old)
    assert not passwords.needs_rehash(passwords.hash_password(GOOD))
    assert passwords.needs_rehash("garbage")


@pytest.mark.parametrize("candidate", ["", "short", "elevenchars", " " * 11])
def test_policy_rejects_short_passwords(candidate):
    with pytest.raises(ValidationError):
        passwords.check_password_policy(candidate)


@pytest.mark.parametrize("length,accepted", [(1023, True), (1024, True), (1025, False)])
def test_policy_maximum_is_exactly_1024_characters(length, accepted):
    assert passwords.MAX_LENGTH == 1024
    if accepted:
        passwords.check_password_policy("x" * length)
    else:
        with pytest.raises(ValidationError):
            passwords.check_password_policy("x" * length)


def test_policy_accepts_twelve_and_rejects_huge():
    passwords.check_password_policy("twelve chars")
    with pytest.raises(ValidationError):
        passwords.check_password_policy("x" * (passwords.MAX_LENGTH + 1))
    with pytest.raises(ValidationError):
        passwords.check_password_policy(None)


def test_recovery_code_is_high_entropy_and_verifies_loosely_formatted():
    code = passwords.generate_recovery_code()
    assert len(code.replace("-", "")) >= 32 and code != passwords.generate_recovery_code()
    stored = passwords.hash_recovery_code(code)
    assert passwords.verify_recovery_code(code, stored)
    assert passwords.verify_recovery_code(code.lower().replace("-", " "), stored)
    assert not passwords.verify_recovery_code(passwords.generate_recovery_code(), stored)
    assert code not in stored
