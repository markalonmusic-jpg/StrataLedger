"""No key, code, password or wrapped blob leaks from the Step 1c flows (secrets-auditor finding 3).

Each flow runs at DEBUG with the app's real log file attached. Afterwards none of its secrets may appear, in any
form (raw bytes, lower or upper hex; a code with and without dashes, lower case), in the log text, in any audit_log
or auth_event value of either file, or (for keys, codes and passwords) anywhere in the raw database files. The
wrapped blobs belong in the master's key tables, so for them only the logs and the audit tables are searched.
"""
import logging
import sqlite3
from pathlib import Path

import pytest

import config
from modules.services import (auth, installation_keys, key_store, key_wrap, keys, ledger_chain, ledger_keys,
                              logging_setup)
from modules.services.keys import SecretKey
from tests import ledger_helpers as lh
from tests.authz_world import PASSWORD, world  # noqa: F401  (fixture)
from tests.test_company_keys import CODE, _create, _installation
from tests.test_key_store import INSTALLATION, FakeMachineWrap

NEW = "Tr0ub4dor&3-horse-staple"
CHAIN_KEYS = [bytes([n]) * 32 for n in (11, 22, 33, 44, 161, 162, 163, 164)]
REPLACEMENT = SecretKey(bytes(range(100, 132)))           # not a palindrome: the fake DPAPI only reverses


@pytest.fixture
def log_file(tmp_path):
    path = tmp_path / "Logs" / "strataledger.log"
    logger = logging_setup.configure_logging(path)
    yield path
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", "").endswith("strataledger.log"):
            logger.removeHandler(handler)
            handler.close()


@pytest.fixture
def known(world, monkeypatch):
    """Known installation and chain keys, an installation key made with CODE, and a Master named root."""
    monkeypatch.setattr(key_wrap, "new_secret_key", lambda: INSTALLATION)
    queue = list(CHAIN_KEYS)
    monkeypatch.setattr(ledger_chain, "new_key", lambda: queue.pop(0))
    _installation(world, FakeMachineWrap())
    from modules.services import passwords
    conn = sqlite3.connect(world.master)
    conn.execute("INSERT INTO master_recovery (id, code_hash, created_at) VALUES (1, ?, 't')",
                 (passwords.hash_recovery_code(CODE),))
    conn.commit()
    conn.close()
    world.root = world.session(world.user("root", master=True))
    return world


def _text_forms(secret):
    if isinstance(secret, bytes):
        return [secret.hex(), secret.hex().upper()]
    return [secret, secret.replace("-", ""), secret.lower()]


def _byte_forms(secret):
    if isinstance(secret, bytes):
        return [secret, secret.hex().encode(), secret.hex().upper().encode()]
    return [s.encode("utf-8") for s in _text_forms(secret)]


def _audit_text(path):
    conn = sqlite3.connect(path)
    try:
        rows = list(conn.execute("SELECT old_value, new_value FROM audit_log"))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "auth_event" in tables:
            rows += list(conn.execute("SELECT * FROM auth_event"))
    finally:
        conn.close()
    return " ".join(repr(r) for r in rows)


def _blobs(world):
    conn = sqlite3.connect(world.master)
    try:
        found = [r[0] for r in conn.execute("SELECT wrapped_key FROM company_key")]
        for machine, recovery in conn.execute("SELECT machine_blob, recovery_blob FROM installation_key"):
            found += [b for b in (machine, recovery) if b]
    finally:
        conn.close()
    return [bytes(b) for b in found]


def _recover(world):
    result = auth.recover_master(world.master, CODE, NEW, machine_wrap=FakeMachineWrap())
    return [CODE, result.recovery_code, NEW], []


def _change(world):
    result = auth.change_master_password(world.root, PASSWORD, CODE, NEW, machine_wrap=FakeMachineWrap())
    return [CODE, result.recovery_code, NEW, PASSWORD], []


def _issue(world):
    result = auth.issue_recovery_code(world.root, PASSWORD, machine_wrap=FakeMachineWrap())
    return [CODE, result.recovery_code, PASSWORD], []


def _rotate(world):
    created = _create(world.root)
    ledger_keys.rotate_chain_key(world.root, created["company_id"])
    return [], [Path(config.BASE_PROJECT_DIR) / created["database_file_path"]]


def _key_lost(world, monkeypatch):
    monkeypatch.setattr(key_store, "_test_new_company_key", SecretKey(lh.TEST_CHAIN_KEY))
    created = _create(world.root)                                     # its key is not in this master: "lost"
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    ledger_keys.start_new_key_epoch(world.root, created["company_id"], confirm_company_code=created["company_code"])
    return [], [Path(config.BASE_PROJECT_DIR) / created["database_file_path"]]


def _replace(world, monkeypatch):
    """Step 1d: the installation key is lost (no DPAPI copy, code lost) and replaced; every company gets an epoch."""
    created = _create(world.root)
    conn = sqlite3.connect(world.master)
    conn.execute("UPDATE installation_key SET machine_blob = NULL, machine_wrapped_at = NULL")
    conn.commit()
    conn.close()
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap()))
    monkeypatch.setattr(key_wrap, "new_secret_key", lambda: REPLACEMENT)
    result = installation_keys.replace_installation_key(world.root, PASSWORD, confirm_text="NEW LEDGER KEY",
                                                        machine_wrap=FakeMachineWrap())
    assert {c["status"] for c in result.companies} == {"done"}
    return [CODE, result.recovery_code, PASSWORD], [Path(config.BASE_PROJECT_DIR) / created["database_file_path"]]


@pytest.mark.parametrize("flow", ["recover", "change", "issue", "rotate", "key_lost", "replace"])
def test_no_secret_from_a_key_flow_reaches_a_log_an_audit_row_or_a_file(known, monkeypatch, caplog, log_file, flow):
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(known.master, FakeMachineWrap()))
    with caplog.at_level(logging.DEBUG):
        if flow == "key_lost":
            secrets, company_files = _key_lost(known, monkeypatch)
        elif flow == "replace":
            secrets, company_files = _replace(known, monkeypatch)
        else:
            secrets, company_files = {"recover": _recover, "change": _change, "issue": _issue,
                                      "rotate": _rotate}[flow](known)
    for handler in logging.getLogger("strataledger").handlers:
        handler.flush()
    logs = caplog.text + (log_file.read_text(encoding="utf-8") if log_file.exists() else "")
    audit = " ".join(_audit_text(p) for p in [known.master, *company_files])
    keys_in_play = [INSTALLATION.use_for_aead(), REPLACEMENT.use_for_aead(), *CHAIN_KEYS]
    for secret in [*secrets, *keys_in_play, *_blobs(known)]:
        for form in _text_forms(secret):
            assert form not in logs, f"{flow}: a secret reached the log"
            assert form not in audit, f"{flow}: a secret reached audit_log or auth_event"
    raw = b"".join(Path(p).read_bytes() for p in [known.master, *company_files])
    for secret in [*secrets, *keys_in_play]:
        for form in _byte_forms(secret):
            assert form not in raw, f"{flow}: a secret is stored in clear"
