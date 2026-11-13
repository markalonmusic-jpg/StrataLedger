"""Step 1c sub-step 7: every new Master recovery code re-wraps the installation key (KS5, PW9, backlog 11;
docs/audit_readiness_design.md 2.7, docs/password_recovery_design.md 3).

* recover_master (forgotten password, the code alone): opens the installation key with the old code, issues a new
  code and re-wraps the key's recovery copy with it, re-wraps the DPAPI copy for THIS computer (a new computer, or
  a key locked since first run, is restored this way) and sets the password, in one transaction. If the code is
  valid but its copy will not open (damaged), the password is still reset and the result says the ledger key
  could not be restored (KS5), so the key-lost path can follow.
* change_master_password (PW9): the current password AND the code; a new code at once, key re-wrapped with it.
* issue_recovery_code (backlog 11): the Master re-enters the password; the DPAPI copy opens the key and the
  recovery copy is re-wrapped with a new code. Refused while the key is locked: a new code must always open it.
* Each returns CodeIssued(recovery_code, ledger_key_restored, message). The old code stops working every time.
"""
import logging
import sqlite3
from pathlib import Path

import pytest

import modules.database as database
from modules.services import auth, key_store, key_wrap, keys
from modules.services.errors import (AuthenticationError, KeyStoreLockedError, PermissionDeniedError,
                                     ValidationError)
from tests.authz_world import PASSWORD
from tests.test_key_store import INSTALLATION, FakeMachineWrap

NEW = "a brand new passphrase"


class OtherComputer(FakeMachineWrap):
    """A second computer's DPAPI: it cannot open the first computer's copy."""

    def protect(self, data):
        self.calls.append("protect")
        return b"OTHR" + bytes(reversed(data))

    def unprotect(self, blob):
        if not blob.startswith(b"OTHR"):
            raise RuntimeError("not this computer's copy")
        return bytes(reversed(blob[4:]))


@pytest.fixture
def master_path(tmp_path, backup_dir, monkeypatch):
    monkeypatch.setattr(key_wrap, "new_secret_key", lambda: INSTALLATION)
    path = tmp_path / "master.db"
    database.ensure_master_database(path)
    return path


def _first(master_path, wrap=None):
    return auth.create_first_master(master_path, "owner", PASSWORD, "Ann", "Owner", "ann@x.test",
                                    machine_wrap=wrap if wrap is not None else FakeMachineWrap())


def _row(master_path):
    conn = sqlite3.connect(master_path)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM installation_key").fetchone())
    finally:
        conn.close()


def _events(master_path):
    conn = sqlite3.connect(master_path)
    try:
        return [r[0] for r in conn.execute("SELECT event_type FROM auth_event ORDER BY event_id")]
    finally:
        conn.close()


def _opens_with(master_path, code):
    row = _row(master_path)
    try:
        key = key_wrap.unwrap_key(key_wrap.recovery_kek(code, row["recovery_salt"]), row["recovery_blob"],
                                  key_store.recovery_associated_data(1, row["fingerprint"]))
    except keys.KeyUnavailableError:
        return False
    return key.use_for_aead() == INSTALLATION.use_for_aead()


def _damage_the_recovery_copy(master_path):
    conn = sqlite3.connect(master_path)
    blob = bytearray(_row(master_path)["recovery_blob"])
    blob[-1] ^= 1
    conn.execute("UPDATE installation_key SET recovery_blob = ?", (bytes(blob),))
    conn.commit()
    conn.close()


def _master_session(master_path, password=PASSWORD):
    return auth.login(master_path, "owner", password)


# --- recover_master (KS5) ------------------------------------------------------------------------------------

def test_recovery_rewraps_the_key_with_the_new_code_and_the_old_code_stops_working(master_path):
    created = _first(master_path)
    before = _row(master_path)
    result = auth.recover_master(master_path, created.recovery_code, NEW, machine_wrap=FakeMachineWrap())
    assert isinstance(result, auth.CodeIssued) and result.ledger_key_restored and result.message is None
    assert result.recovery_code != created.recovery_code
    assert _opens_with(master_path, result.recovery_code)
    assert not _opens_with(master_path, created.recovery_code)
    after = _row(master_path)
    assert after["fingerprint"] == before["fingerprint"] and after["recovery_salt"] != before["recovery_salt"]
    assert _master_session(master_path, NEW).is_master


def test_recovery_on_a_new_computer_restores_the_key_there(master_path):
    created = _first(master_path)
    other = OtherComputer()
    assert key_store.LocalKeyProvider(master_path, other).status == "locked"
    result = auth.recover_master(master_path, created.recovery_code, NEW, machine_wrap=other)
    assert result.ledger_key_restored
    assert key_store.LocalKeyProvider(master_path, other).status == "unlocked"


def test_recovery_unlocks_a_key_that_was_locked_since_first_run(master_path):
    created = _first(master_path, FakeMachineWrap(fail_protect=True))
    assert created.ledger_key_locked and _row(master_path)["machine_blob"] is None
    result = auth.recover_master(master_path, created.recovery_code, NEW, machine_wrap=FakeMachineWrap())
    assert result.ledger_key_restored
    provider = key_store.LocalKeyProvider(master_path, FakeMachineWrap())
    assert provider.status == "unlocked"
    assert isinstance(provider.new_chain_key(), keys.SecretKey)      # creating a company is possible again


def test_recovery_where_dpapi_still_fails_resets_the_password_and_says_the_key_stays_locked(master_path):
    created = _first(master_path)
    before = _row(master_path)
    result = auth.recover_master(master_path, created.recovery_code, NEW,
                                 machine_wrap=FakeMachineWrap(fail_protect=True))
    assert not result.ledger_key_restored and result.message == auth.LEDGER_KEY_LOCKED_HERE
    assert _opens_with(master_path, result.recovery_code)              # the new code still opens the key
    assert _row(master_path)["machine_blob"] == before["machine_blob"]  # the old copy is kept
    assert _master_session(master_path, NEW).is_master


def test_recovery_with_both_copies_unusable_still_resets_the_password_and_says_the_key_was_not_restored(master_path):
    created = _first(master_path)
    _damage_the_recovery_copy(master_path)
    damaged = _row(master_path)
    result = auth.recover_master(master_path, created.recovery_code, NEW,
                                 machine_wrap=FakeMachineWrap(fail_unprotect=True))
    assert not result.ledger_key_restored and result.message == auth.LEDGER_KEY_NOT_RESTORED
    assert "the ledger key could not be restored" in result.message
    assert _master_session(master_path, NEW).is_master
    assert _row(master_path) == damaged
    assert "Installation key rewrapped" not in _events(master_path)


def test_recovery_records_the_rewrap_and_never_stores_or_logs_a_code_or_key(master_path, caplog):
    caplog.set_level(logging.DEBUG)
    created = _first(master_path)
    result = auth.recover_master(master_path, created.recovery_code, NEW, machine_wrap=FakeMachineWrap())
    assert _events(master_path)[-2:] == ["Installation key rewrapped", "Master recovered"]
    raw = Path(master_path).read_bytes()
    for secret in (result.recovery_code, created.recovery_code):
        assert secret.encode() not in raw and secret not in caplog.text
    assert INSTALLATION.use_for_aead() not in raw and INSTALLATION.use_for_aead().hex() not in caplog.text


def test_a_wrong_code_changes_nothing(master_path):
    _first(master_path)
    before = _row(master_path)
    with pytest.raises(AuthenticationError):
        auth.recover_master(master_path, "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG-HHHH", NEW, machine_wrap=FakeMachineWrap())
    assert _row(master_path) == before


# --- change_master_password (PW9) ----------------------------------------------------------------------------

def test_a_master_password_change_needs_the_password_and_the_code_and_issues_a_new_code(master_path):
    created = _first(master_path)
    session = _master_session(master_path)
    result = auth.change_master_password(session, PASSWORD, created.recovery_code, NEW)
    assert _events(master_path)[-3:] == ["Installation key rewrapped", "Recovery code issued", "Password changed"]
    assert result.ledger_key_restored and result.message is None
    assert _opens_with(master_path, result.recovery_code) and not _opens_with(master_path, created.recovery_code)
    assert _master_session(master_path, NEW).is_master
    with pytest.raises(AuthenticationError):
        auth.recover_master(master_path, created.recovery_code, "yet another passphrase")


def test_a_master_password_change_with_a_wrong_password_or_code_changes_nothing(master_path):
    created = _first(master_path)
    session = _master_session(master_path)
    before = _row(master_path)
    with pytest.raises(AuthenticationError, match="current password"):
        auth.change_master_password(session, PASSWORD + "x", created.recovery_code, NEW)
    with pytest.raises(AuthenticationError, match="recovery code"):
        auth.change_master_password(session, PASSWORD, "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG-HHHH", NEW)
    assert _row(master_path) == before
    assert _master_session(master_path).is_master
    assert "Recovery failed" in _events(master_path)


def test_a_master_password_change_checks_the_new_password(master_path):
    created = _first(master_path)
    session = _master_session(master_path)
    with pytest.raises(ValidationError):
        auth.change_master_password(session, PASSWORD, created.recovery_code, "short")
    with pytest.raises(ValidationError):
        auth.change_master_password(session, PASSWORD, created.recovery_code, PASSWORD)
    assert _opens_with(master_path, created.recovery_code)


def test_only_the_master_changes_the_master_password_this_way(master_path):
    created = _first(master_path)
    master = _master_session(master_path)
    from modules.services import users
    users.create_user(master, username="clerk", password=PASSWORD, first_name="C", last_name="L",
                      email="c@x.test")
    clerk = auth.login(master_path, "clerk", PASSWORD)
    with pytest.raises(PermissionDeniedError):
        auth.change_master_password(clerk, PASSWORD, created.recovery_code, NEW)
    assert _opens_with(master_path, created.recovery_code)


def test_a_damaged_recovery_copy_is_rebuilt_from_this_computers_copy(master_path):
    """Step 1c review: when the code's copy is damaged but DPAPI still opens the key, the new code re-wraps it."""
    created = _first(master_path)
    _damage_the_recovery_copy(master_path)
    result = auth.recover_master(master_path, created.recovery_code, NEW, machine_wrap=FakeMachineWrap())
    assert result.ledger_key_restored and result.message is None
    assert _opens_with(master_path, result.recovery_code)


def test_a_master_password_change_rebuilds_a_damaged_recovery_copy_from_this_computers_copy(master_path):
    created = _first(master_path)
    _damage_the_recovery_copy(master_path)
    result = auth.change_master_password(_master_session(master_path), PASSWORD, created.recovery_code, NEW,
                                         machine_wrap=FakeMachineWrap())
    assert result.ledger_key_restored and _opens_with(master_path, result.recovery_code)


def test_the_not_restored_message_says_what_happened_without_claiming_a_reset():
    assert "could not be restored" in auth.LEDGER_KEY_NOT_RESTORED
    assert "reset" not in auth.LEDGER_KEY_NOT_RESTORED and "start a new ledger key" not in auth.LEDGER_KEY_NOT_RESTORED


def test_a_master_password_change_with_a_damaged_copy_says_the_key_was_not_restored(master_path):
    created = _first(master_path)
    _damage_the_recovery_copy(master_path)
    result = auth.change_master_password(_master_session(master_path), PASSWORD, created.recovery_code, NEW)
    assert not result.ledger_key_restored and result.message == auth.LEDGER_KEY_NOT_RESTORED


# --- issue_recovery_code (backlog 11) -------------------------------------------------------------------------

def test_a_new_code_after_the_password_rewraps_the_key_through_the_machine_copy(master_path):
    created = _first(master_path)
    result = auth.issue_recovery_code(_master_session(master_path), PASSWORD, machine_wrap=FakeMachineWrap())
    assert result.recovery_code != created.recovery_code and result.ledger_key_restored
    assert _opens_with(master_path, result.recovery_code) and not _opens_with(master_path, created.recovery_code)
    with pytest.raises(AuthenticationError):
        auth.recover_master(master_path, created.recovery_code, NEW)
    auth.recover_master(master_path, result.recovery_code, NEW)
    assert _events(master_path).count("Recovery code issued") == 1


@pytest.mark.parametrize("wrap", [FakeMachineWrap(fail_unprotect=True), None], ids=["dpapi-fails", "no-wrap"])
def test_a_new_code_is_refused_while_the_key_is_locked(master_path, wrap):
    created = _first(master_path)
    before = _row(master_path)
    with pytest.raises(KeyStoreLockedError) as caught:
        auth.issue_recovery_code(_master_session(master_path), PASSWORD, machine_wrap=wrap)
    assert str(caught.value) == auth.NEW_CODE_NEEDS_KEY
    assert _row(master_path) == before and _opens_with(master_path, created.recovery_code)
    assert "Recovery code issued" not in _events(master_path)


def test_a_new_code_needs_the_right_password(master_path):
    created = _first(master_path)
    with pytest.raises(AuthenticationError):
        auth.issue_recovery_code(_master_session(master_path), PASSWORD + "x", machine_wrap=FakeMachineWrap())
    assert _opens_with(master_path, created.recovery_code)


def test_only_the_master_issues_a_recovery_code(master_path):
    _first(master_path)
    from modules.services import users
    users.create_user(_master_session(master_path), username="clerk", password=PASSWORD, first_name="C",
                      last_name="L", email="c@x.test")
    with pytest.raises(PermissionDeniedError):
        auth.issue_recovery_code(auth.login(master_path, "clerk", PASSWORD), PASSWORD, machine_wrap=FakeMachineWrap())


# --- The results never show the code (step-reviewer and secrets-auditor finding) -----------------------------------

@pytest.mark.parametrize("result", [
    auth.FirstMaster(7, "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567", False),
    auth.CodeIssued("ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567", True, None),
], ids=["FirstMaster", "CodeIssued"])
def test_a_result_holding_a_recovery_code_never_shows_it(result):
    import copy
    import pickle
    code = result.recovery_code
    for text in (repr(result), str(result), f"{result}", "%s %r" % (result, result), repr([result])):
        for form in (code, code.replace("-", ""), code.lower()):
            assert form not in text
        assert "<redacted>" in text
    for leak in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError):
            leak(result)
    assert result.recovery_code == code                               # the caller still gets it


@pytest.mark.parametrize("make", [
    lambda: auth.FirstMaster(7, "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567", False),
    lambda: auth.FirstMaster(7, "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"),
    lambda: auth.CodeIssued("ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567", True, None),
    lambda: auth.CodeIssued(recovery_code="ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567", ledger_key_restored=False,
                            message="why"),
], ids=["FirstMaster", "FirstMaster-default", "CodeIssued", "CodeIssued-keywords"])
def test_a_result_holding_a_recovery_code_is_not_a_tuple(make):
    """The code is reached only through .recovery_code: no index, iteration, _asdict, vars() or JSON (before
    Step 4; the same rule as installation_keys.KeyReplaced)."""
    import copy
    import dataclasses
    import json
    import pickle
    result = make()
    assert not isinstance(result, tuple)
    with pytest.raises(TypeError):
        vars(result)
    for attempt in (lambda r: r[0], lambda r: r[1], lambda r: list(r), lambda r: tuple(r), lambda r: dict(r),
                    lambda r: r._asdict(), lambda r: json.dumps(r), lambda r: dataclasses.asdict(r)):
        with pytest.raises((TypeError, AttributeError)):
            attempt(result)
    for attempt in (pickle.dumps, copy.copy, copy.deepcopy, lambda r: pickle.dumps(r, protocol=0),
                    lambda r: r.__reduce_ex__(2)):
        with pytest.raises(TypeError):
            attempt(result)
    with pytest.raises(AttributeError):
        result.recovery_code = "something else"
    with pytest.raises(AttributeError):
        del result.recovery_code
    assert result.recovery_code == "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"


def test_the_other_fields_keep_their_names_and_defaults():
    first = auth.FirstMaster(7, "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567")
    assert (first.user_id, first.ledger_key_locked) == (7, False)
    issued = auth.CodeIssued("ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567", False, "why")
    assert (issued.ledger_key_restored, issued.message) == (False, "why")
    for bad in (lambda: auth.CodeIssued("X", True), lambda: auth.CodeIssued("X", True, None, 4),
                lambda: auth.CodeIssued("X", True, None, colour="red"),
                lambda: auth.CodeIssued("X", True, recovery_code="Y")):
        with pytest.raises(TypeError):
            bad()


# --- Mutation-test gaps ---------------------------------------------------------------------------------------

def test_every_rewrap_uses_a_new_salt(master_path):
    """KS2: the recovery copy gets its own new salt each time the code changes."""
    created = _first(master_path)
    salts = [_row(master_path)["recovery_salt"]]
    first = auth.recover_master(master_path, created.recovery_code, NEW, machine_wrap=FakeMachineWrap())
    salts.append(_row(master_path)["recovery_salt"])
    auth.change_master_password(_master_session(master_path, NEW), NEW, first.recovery_code, "yet another passphrase")
    salts.append(_row(master_path)["recovery_salt"])
    assert len(set(salts)) == 3


def test_when_both_copies_fail_the_new_code_is_still_the_masters_code(master_path):
    """The not-restored message says the new code is saved: it must work for the next recovery."""
    created = _first(master_path)
    _damage_the_recovery_copy(master_path)
    result = auth.recover_master(master_path, created.recovery_code, NEW,
                                 machine_wrap=FakeMachineWrap(fail_unprotect=True))
    assert not result.ledger_key_restored
    auth.recover_master(master_path, result.recovery_code, "yet another passphrase")
