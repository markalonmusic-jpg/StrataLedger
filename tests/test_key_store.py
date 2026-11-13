"""key_store.py, Step 1c sub-step 5: the installation key is made at first run; LocalKeyProvider unlocks it at
start-up (docs/audit_readiness_design.md 2.7; KS3, KS6, KS9).

* create_first_master makes the installation key in the same master transaction as the Master: two wrapped copies,
  DPAPI machine scope (through the machine wrap the app passes in; services never call the OS, H1) and the
  recovery code (AES-GCM under recovery_kek with its own salt). If the DPAPI copy cannot be made the Master is
  still created and the key is locked until restored with the code; if the recovery copy cannot be made nothing is
  created, because the code must always be able to open the key.
* LocalKeyProvider(master_db_path, machine_wrap) opens the DPAPI copy once and checks it against the stored
  fingerprint. Status 'unlocked', 'locked' (no DPAPI copy, DPAPI failed, or the copy opened to the wrong key), or
  'missing' (no installation key at all). While not unlocked it gives no key and creates none.
* The installation key is never stored or logged in clear; every row change writes an auth_event, not audit_log.
"""
import hashlib
import hmac
import logging
import re
import sqlite3
import sys
from pathlib import Path

import pytest

import modules.database as database
from modules import platform_support
from modules.services import auth, key_store, key_wrap, keys
from modules.services.errors import KeyStoreLockedError, KeyUnavailableError, ValidationError
from modules.services.keys import SecretKey
from tests.authz_world import PASSWORD

ROOT = Path(__file__).resolve().parent.parent
INSTALLATION = SecretKey(bytes(range(200, 232)))


class FakeMachineWrap:
    """Stands in for platform_support.DPAPI: reversible, and can be told to fail."""

    def __init__(self, fail_protect=False, fail_unprotect=False):
        self.fail_protect, self.fail_unprotect = fail_protect, fail_unprotect
        self.calls = []

    def protect(self, data):
        self.calls.append("protect")
        if self.fail_protect:
            raise RuntimeError("DPAPI is not available")
        return b"FAKE" + bytes(reversed(data))

    def unprotect(self, blob):
        self.calls.append("unprotect")
        if self.fail_unprotect or not blob.startswith(b"FAKE"):
            raise RuntimeError("DPAPI could not open it")
        return bytes(reversed(blob[4:]))


@pytest.fixture
def master_path(tmp_path, backup_dir):
    path = tmp_path / "master.db"
    database.ensure_master_database(path)
    return path


@pytest.fixture
def known_key(monkeypatch):
    """Make the next installation key a known value, so the files can be searched for it."""
    monkeypatch.setattr(key_wrap, "new_secret_key", lambda: INSTALLATION)
    return INSTALLATION


def _first_master(master_path, machine_wrap):
    return auth.create_first_master(master_path, "owner", PASSWORD, "Ann", "Owner", "ann@x.test",
                                    machine_wrap=machine_wrap)


def _row(master_path):
    conn = sqlite3.connect(master_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM installation_key").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _rows(master_path, sql):
    conn = sqlite3.connect(master_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def _fingerprint(key):
    return hmac.new(key.use_for_aead(), b"StrataLedger installation key fingerprint v1", hashlib.sha256).hexdigest()


# --- First run makes the installation key -------------------------------------------------------------------------

def test_first_run_stores_the_fingerprint_and_both_wrapped_copies(master_path, known_key):
    wrap = FakeMachineWrap()
    created = _first_master(master_path, wrap)
    row = _row(master_path)
    assert row["fingerprint"] == key_store.installation_fingerprint(known_key) == _fingerprint(known_key)
    assert wrap.unprotect(row["machine_blob"]) == known_key.use_for_aead()
    assert len(row["recovery_salt"]) == 16 and len(row["recovery_blob"]) == 61
    assert row["created_at"] == row["recovery_wrapped_at"] == row["machine_wrapped_at"]
    assert created.ledger_key_locked is False


def test_the_recovery_copy_opens_with_the_code_shown_once(master_path, known_key):
    created = _first_master(master_path, FakeMachineWrap())
    row = _row(master_path)
    kek = key_wrap.recovery_kek(created.recovery_code, row["recovery_salt"])
    opened = key_wrap.unwrap_key(kek, row["recovery_blob"], key_store.recovery_associated_data(1, row["fingerprint"]))
    assert opened.use_for_aead() == known_key.use_for_aead()


def test_the_recovery_salt_is_not_the_code_hash_salt(master_path):
    _first_master(master_path, FakeMachineWrap())
    [stored] = _rows(master_path, "SELECT code_hash FROM master_recovery")
    import base64
    code_salt = base64.b64decode(stored["code_hash"].split("$")[4])
    assert _row(master_path)["recovery_salt"] != code_salt


def test_the_installation_key_is_never_in_either_file_in_clear(master_path, known_key):
    created = _first_master(master_path, FakeMachineWrap())
    raw = Path(master_path).read_bytes()
    row = _row(master_path)
    kek = key_wrap.recovery_kek(created.recovery_code, row["recovery_salt"])
    for secret in (known_key.use_for_aead(), kek.use_for_aead()):
        assert secret not in raw and secret.hex().encode() not in raw
    assert created.recovery_code.encode() not in raw


def test_first_run_records_an_auth_event_and_nothing_in_the_audit_log(master_path):
    created = _first_master(master_path, FakeMachineWrap())
    events = _rows(master_path, "SELECT event_type, user_id FROM auth_event ORDER BY event_id")
    assert {"event_type": "Installation key created", "user_id": created.user_id} in events
    for row in _rows(master_path, "SELECT table_name, new_value FROM audit_log"):
        assert row["table_name"] != "installation_key"


def test_when_dpapi_fails_the_master_is_created_and_the_key_is_locked(master_path, caplog):
    caplog.set_level(logging.DEBUG)
    created = _first_master(master_path, FakeMachineWrap(fail_protect=True))
    row = _row(master_path)
    assert row["machine_blob"] is None and row["machine_wrapped_at"] is None and len(row["recovery_blob"]) == 61
    assert created.ledger_key_locked is True
    assert auth.login(master_path, "owner", PASSWORD).is_master
    assert "RuntimeError" in caplog.text and "not available" not in caplog.text


def test_without_a_machine_wrap_the_key_is_locked_too(master_path):
    created = _first_master(master_path, None)
    assert _row(master_path)["machine_blob"] is None and created.ledger_key_locked is True


def test_when_the_recovery_copy_cannot_be_made_nothing_is_created(master_path, monkeypatch):
    def broken(*args):
        raise RuntimeError("no AES today")
    monkeypatch.setattr(key_wrap, "wrap_key", broken)
    with pytest.raises(RuntimeError):
        _first_master(master_path, FakeMachineWrap())
    assert _row(master_path) is None
    assert _rows(master_path, "SELECT user_id FROM app_user") == []


def test_an_installation_that_already_has_a_key_never_gets_a_second(master_path):
    """The key cannot be replaced (company keys depend on it); a lost Master is restored with the code instead."""
    _first_master(master_path, FakeMachineWrap())
    before = _row(master_path)
    conn = sqlite3.connect(master_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM app_user")
    conn.commit()
    conn.close()
    with pytest.raises(ValidationError, match="recovery code"):
        _first_master(master_path, FakeMachineWrap())
    assert _row(master_path) == before
    assert _rows(master_path, "SELECT user_id FROM app_user") == []


# --- LocalKeyProvider unlocks at start-up -------------------------------------------------------------------------

def test_the_provider_unlocks_with_the_machine_copy(master_path):
    wrap = FakeMachineWrap()
    _first_master(master_path, wrap)
    provider = key_store.LocalKeyProvider(master_path, wrap)
    assert provider.status == "unlocked" and provider.is_unlocked
    assert isinstance(provider, keys.KeyProvider)


@pytest.mark.parametrize("make, opener", [
    (FakeMachineWrap(fail_protect=True), FakeMachineWrap()),          # no DPAPI copy was made
    (FakeMachineWrap(), FakeMachineWrap(fail_unprotect=True)),        # DPAPI fails now (another computer)
    (FakeMachineWrap(), None),                                        # the app gave no machine wrap
], ids=["no-copy", "dpapi-fails", "no-wrap"])
def test_the_provider_is_locked_when_the_machine_copy_cannot_be_opened(master_path, make, opener):
    _first_master(master_path, make)
    provider = key_store.LocalKeyProvider(master_path, opener)
    assert provider.status == "locked" and not provider.is_unlocked


def test_a_machine_copy_that_opens_to_another_key_is_locked(master_path):
    class Liar(FakeMachineWrap):
        def unprotect(self, blob):
            return bytes(32)
    _first_master(master_path, FakeMachineWrap())
    assert key_store.LocalKeyProvider(master_path, Liar()).status == "locked"


def test_a_machine_copy_of_the_wrong_size_is_locked(master_path):
    class Short(FakeMachineWrap):
        def unprotect(self, blob):
            return b"short"
    _first_master(master_path, FakeMachineWrap())
    assert key_store.LocalKeyProvider(master_path, Short()).status == "locked"


def test_a_master_without_an_installation_key_is_missing(master_path):
    assert key_store.LocalKeyProvider(master_path, FakeMachineWrap()).status == "missing"


def test_a_locked_provider_gives_no_key_and_makes_none(master_path):
    _first_master(master_path, FakeMachineWrap(fail_protect=True))
    provider = key_store.LocalKeyProvider(master_path, FakeMachineWrap())
    with pytest.raises(KeyUnavailableError) as caught:
        provider.get_key(1, 1)
    assert str(caught.value) == keys.NO_KEY_MESSAGE
    with pytest.raises(KeyStoreLockedError) as locked:
        provider.new_chain_key()
    assert str(locked.value) == key_store.KEY_STORE_LOCKED == (
        "Ask the Master to restore the ledger key with the recovery code first.")


def test_the_provider_never_shows_its_key(master_path, known_key, caplog):
    caplog.set_level(logging.DEBUG)
    wrap = FakeMachineWrap()
    _first_master(master_path, wrap)
    provider = key_store.LocalKeyProvider(master_path, wrap)
    text = f"{provider!r} {provider} {vars(provider) if hasattr(provider, '__dict__') else ''}"
    assert known_key.use_for_aead().hex() not in text and repr(provider) == "<LocalKeyProvider unlocked>"
    key_store.LocalKeyProvider(master_path, FakeMachineWrap(fail_unprotect=True))
    assert known_key.use_for_aead().hex() not in caplog.text


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI exists only on Windows")
def test_real_dpapi_first_run_then_a_new_provider_unlocks(master_path, known_key):
    _first_master(master_path, platform_support.DPAPI)
    provider = key_store.LocalKeyProvider(master_path, platform_support.DPAPI)
    assert provider.status == "unlocked"
    assert known_key.use_for_aead() not in Path(master_path).read_bytes()


# --- Where things live ---------------------------------------------------------------------------------------------

def test_services_never_import_the_platform_module():
    pattern = re.compile(r"^\s*(from\s+modules(\.platform_support|\s+import\s+[^\n]*\bplatform_support\b)"
                         r"|import\s+modules\.platform_support)", re.MULTILINE)
    offenders = [p.name for p in (ROOT / "modules" / "services").glob("*.py")
                 if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_the_platform_module_offers_the_dpapi_machine_wrap():
    assert platform_support.DPAPI.protect is platform_support.machine_protect
    assert platform_support.DPAPI.unprotect is platform_support.machine_unprotect


def test_the_recovery_copy_is_bound_to_its_row_by_the_associated_data(master_path, known_key):
    """Step 1c review: the right code and salt still refuse the recovery copy under any other associated data."""
    created = _first_master(master_path, FakeMachineWrap())
    row = _row(master_path)
    kek = key_wrap.recovery_kek(created.recovery_code, row["recovery_salt"])
    assert key_store.recovery_associated_data(1, row["fingerprint"]) == key_wrap.associated_data(
        "installation_key", 1, "recovery", row["fingerprint"])
    for other in (key_wrap.associated_data("installation_key", 1, "recovery", "0" * 64),
                  key_wrap.associated_data("installation_key", 2, "recovery", row["fingerprint"]),
                  key_wrap.associated_data("installation_key", 1, "machine", row["fingerprint"]),
                  key_wrap.associated_data("company_key", 1, "recovery", row["fingerprint"]), b""):
        with pytest.raises(KeyUnavailableError):
            key_wrap.unwrap_key(kek, row["recovery_blob"], other)
