"""Step 1d part B: replacing a lost installation key (docs/audit_readiness_design.md 2.7; KS13, KS17, KS19-KS21).

installation_keys.replace_installation_key(session, password, *, confirm_text, machine_wrap), Master only:
* refused first for anyone but the Master, then on a mistyped phrase (NEW LEDGER KEY) or a wrong password, and
  while the installation key still opens on this computer (its DPAPI copy works: the key is not lost);
* in one master transaction: the old installation key retired ('Key lost'), a new one with a NEW recovery code (it
  replaces the master_recovery hash) and this computer's DPAPI copy, and an 'Installation key replaced' event;
* then every company in the registry, archived included, enters a key-lost epoch under a chain key wrapped by the
  new installation key. Not atomic across files: the result lists each company as done or failed in one sentence,
  and finish_remaining_companies completes the ones left behind.
* The result shows the code once and redacts it everywhere else. replacement_preview gives the screen the count.
"""
import copy
import dataclasses
import os
import pickle
import shutil
import sqlite3
from pathlib import Path

import pytest

import config
from modules.services import (auth, companies, installation_keys, key_store, keys, ledger, ledger_verify,
                              passwords)
from modules.services.errors import (AuthenticationError, KeyStoreLockedError, KeyUnavailableError,
                                     PermissionDeniedError, ValidationError)
from tests.authz_world import PASSWORD, world  # noqa: F401  (fixture)
from tests.test_company_keys import CODE, _create, _installation, _two_postable_accounts
from tests.test_key_store import FakeMachineWrap

NOW = "2026-03-20T10:00:00+00:00"
PHRASE = "NEW LEDGER KEY"


def _rows(path, sql, params=()):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def _master_write(world, *statements):
    conn = sqlite3.connect(world.master)
    try:
        for statement in statements:
            conn.execute(*statement) if isinstance(statement, tuple) else conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def _registry(world):
    """Every registered company: the test world's own three (made with the test key) and the fixture's three."""
    return _rows(world.master, "SELECT company_id, company_code, is_archived FROM company_registry "
                               "ORDER BY company_id")


def _path(created):
    return Path(config.BASE_PROJECT_DIR) / created["database_file_path"]


def _context(world, company_id):
    return dataclasses.replace(companies.open_company(world.root, company_id), now=NOW, today="2026-03-20")


def _post(world, company_id, cents=1000):
    context = _context(world, company_id)
    debit, credit = _two_postable_accounts(context)
    entry_id = ledger.create_entry(context, entry_date="2026-03-15", lines=[
        {"account_id": debit, "debit_cents": cents}, {"account_id": credit, "credit_cents": cents}])
    ledger.post_journal_entry(context, entry_id, confirm=True, acknowledge_date_warnings=True)


def _lose_the_installation_key(world, monkeypatch):
    """This computer's DPAPI copy is gone (the recovery code is lost too): the key store is locked."""
    _master_write(world, "UPDATE installation_key SET machine_blob = NULL, machine_wrapped_at = NULL "
                         "WHERE is_active = 1")
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap()))


@pytest.fixture
def installation(world, monkeypatch):
    """A Master (root, PASSWORD), an installation key made with CODE, and three companies (one archived, one with
    two posted entries), all with real keys. The key is not lost yet."""
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    _installation(world, FakeMachineWrap())
    _master_write(world, ("INSERT INTO master_recovery (id, code_hash, created_at) VALUES (1, ?, 't')",
                          (passwords.hash_recovery_code(CODE),)))
    monkeypatch.setattr(keys, "_provider", key_store.LocalKeyProvider(world.master, FakeMachineWrap()))
    world.root = world.session(world.user("root", master=True))
    world.companies = [_create(world.root, name) for name in ("Acme Builders", "Beta Books", "Old Archive")]
    _post(world, world.companies[0]["company_id"], 1000)
    _post(world, world.companies[0]["company_id"], 2000)
    _master_write(world, ("UPDATE company_registry SET is_archived = 1 WHERE company_id = ?",
                          (world.companies[2]["company_id"],)))
    return world


@pytest.fixture
def lost(installation, monkeypatch):
    _lose_the_installation_key(installation, monkeypatch)
    return installation


def _replace(world, *, session=None, password=PASSWORD, phrase=PHRASE, wrap=None):
    return installation_keys.replace_installation_key(session or world.root, password, confirm_text=phrase,
                                                      machine_wrap=wrap or FakeMachineWrap())


def _snapshot(world, *, with_auth=True):
    """Every key and checkpoint row in the master and in every company file (and, with_auth, every auth row)."""
    master = [_rows(world.master, f"SELECT * FROM {table}") for table in (
        "installation_key", "company_key", "master_recovery", "chain_checkpoint")]
    if with_auth:
        master += [_rows(world.master, "SELECT * FROM auth_event"), _rows(world.master, "SELECT * FROM login_throttle")]
    files = [(_rows(_path(c), "SELECT * FROM ledger_chain_key"), _rows(_path(c), "SELECT * FROM ledger_checkpoint"),
              _rows(_path(c), "SELECT * FROM audit_log")) for c in world.companies]
    return master, files


# --- Refusals ------------------------------------------------------------------------------------------------------

def test_a_non_master_is_refused_before_anything_else(lost):
    before = _snapshot(lost, with_auth=False)
    clerk = lost.session(lost.user("clerk"))
    with pytest.raises(PermissionDeniedError):
        _replace(lost, session=clerk, password="wrong", phrase="wrong")    # the denial comes first
    assert _snapshot(lost, with_auth=False) == before
    with pytest.raises(PermissionDeniedError):
        installation_keys.replacement_preview(clerk, machine_wrap=FakeMachineWrap())
    with pytest.raises(PermissionDeniedError):
        installation_keys.finish_remaining_companies(clerk)


@pytest.mark.parametrize("phrase", ["", "new ledger key", "NEW LEDGER KEY ", "NEW KEY", None])
def test_a_wrong_confirmation_writes_nothing(lost, phrase):
    before = _snapshot(lost)
    with pytest.raises(ValidationError) as caught:
        _replace(lost, phrase=phrase)
    assert PHRASE in str(caught.value)
    assert _snapshot(lost) == before


def test_a_wrong_password_writes_no_key_and_touches_no_company(lost):
    before = _snapshot(lost, with_auth=False)
    with pytest.raises(AuthenticationError):
        _replace(lost, password="not the password")
    assert _snapshot(lost, with_auth=False) == before
    assert not _rows(lost.master, "SELECT 1 FROM auth_event WHERE event_type = 'Installation key replaced'")


def test_refused_while_the_key_still_opens_on_this_computer(installation):
    before = _snapshot(installation)
    with pytest.raises(ValidationError) as caught:
        _replace(installation)
    assert str(caught.value) == installation_keys.KEY_NOT_LOST
    assert _snapshot(installation) == before


def test_refused_when_this_computer_cannot_protect_the_new_key(lost):
    before = _snapshot(lost, with_auth=False)
    with pytest.raises(KeyStoreLockedError) as caught:
        _replace(lost, wrap=FakeMachineWrap(fail_protect=True))
    assert str(caught.value) == installation_keys.NEW_KEY_NOT_PROTECTED
    assert _snapshot(lost, with_auth=False) == before


def test_refused_when_there_is_no_installation_key_yet(world, monkeypatch):
    world.root = world.session(world.user("root", master=True))
    with pytest.raises(ValidationError) as caught:
        _replace(world)
    assert str(caught.value) == installation_keys.NO_INSTALLATION_KEY


# --- Success -------------------------------------------------------------------------------------------------------

def test_the_old_key_is_retired_and_a_new_one_with_a_new_code_is_active(lost):
    [old] = _rows(lost.master, "SELECT * FROM installation_key")
    result = _replace(lost)
    rows = _rows(lost.master, "SELECT * FROM installation_key ORDER BY id")
    assert [(r["id"], r["is_active"], r["retire_reason"]) for r in rows] == [(1, 0, "Key lost"), (2, 1, None)]
    assert rows[0]["retired_at"] is not None and rows[0]["fingerprint"] == old["fingerprint"]
    assert bytes(rows[0]["recovery_blob"]) == bytes(old["recovery_blob"])          # the old copy is kept
    assert rows[1]["machine_blob"] is not None and rows[1]["fingerprint"] != old["fingerprint"]
    assert result.recovery_code != CODE


def test_the_new_code_opens_the_new_key_and_the_old_code_opens_nothing(lost):
    result = _replace(lost)
    conn = sqlite3.connect(lost.master)
    conn.row_factory = sqlite3.Row
    try:
        new = key_store.open_with_recovery_code(conn, result.recovery_code)
        assert new is not None
        assert key_store.installation_fingerprint(new) == conn.execute(
            "SELECT fingerprint FROM installation_key WHERE is_active = 1").fetchone()[0]
        assert key_store.open_with_recovery_code(conn, CODE) is None
        [stored] = conn.execute("SELECT code_hash FROM master_recovery").fetchall()
    finally:
        conn.close()
    assert passwords.verify_recovery_code(result.recovery_code, stored[0])
    assert not passwords.verify_recovery_code(CODE, stored[0])
    with pytest.raises(AuthenticationError):
        auth.recover_master(lost.master, CODE, "a brand new password 1", machine_wrap=FakeMachineWrap())


def test_the_replacement_is_recorded(lost):
    _replace(lost)
    events = _rows(lost.master, "SELECT event_type, user_id FROM auth_event WHERE event_type IN "
                                "('Installation key replaced', 'Recovery code issued', 'Ledger key lost') "
                                "ORDER BY event_id")
    assert events[:2] == [{"event_type": "Installation key replaced", "user_id": lost.root.user_id},
                          {"event_type": "Recovery code issued", "user_id": lost.root.user_id}]
    assert [e["event_type"] for e in events[2:]] == ["Ledger key lost"] * len(_registry(lost))


def test_every_company_archived_included_enters_a_key_epoch(lost):
    result = _replace(lost)
    assert [(c["company_id"], c["status"]) for c in result.companies] == [
        (c["company_id"], "done") for c in _registry(lost)]
    for created, expected_through in zip(lost.companies, (2, 0, 0)):
        keys_rows = _rows(_path(created), "SELECT key_id, is_active, retire_reason FROM ledger_chain_key "
                                          "ORDER BY key_id")
        assert [(k["is_active"], k["retire_reason"]) for k in keys_rows] == [(0, "Key lost"), (1, None)]
        [checkpoint] = _rows(_path(created), "SELECT * FROM ledger_checkpoint WHERE kind = 'Key lost'")
        assert checkpoint["through_entry_number"] == expected_through
        stored = _rows(lost.master, "SELECT installation_key_id FROM company_key WHERE company_id = ? "
                                    "ORDER BY company_key_id", (created["company_id"],))
        assert [s["installation_key_id"] for s in stored] == [1, 2]                    # the old row is kept
    assert keys.get_provider().is_unlocked


def test_posting_and_verification_work_in_every_company_afterwards(lost):
    _replace(lost)
    for created in lost.companies[:2]:
        _post(lost, created["company_id"], 3000)
    result = ledger_verify.verify_ledger(_context(lost, lost.companies[0]["company_id"]), mode="full")
    assert (result["status"], result["through_entry_number"], result["unverified_through"]) == ("OK", 3, 2)
    result = ledger_verify.verify_ledger(_context(lost, lost.companies[1]["company_id"]), mode="full")
    assert (result["status"], result["unverified_through"]) == ("OK", None)


def test_keys_wrapped_by_the_retired_installation_key_are_not_opened(lost):
    before = {c["company_id"]: _rows(_path(c), "SELECT key_id FROM ledger_chain_key")[0]["key_id"]
              for c in lost.companies}
    _replace(lost)
    provider = keys.get_provider()
    for company_id, old_key_id in before.items():
        with pytest.raises(KeyUnavailableError):
            provider.get_key(company_id, old_key_id)


def test_the_result_redacts_the_code_and_cannot_be_copied(lost):
    result = _replace(lost)
    assert result.recovery_code not in repr(result) and result.recovery_code not in str(result)
    assert "<redacted>" in repr(result)
    for attempt in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError):
            attempt(result)
    assert result.message


# --- The preview (KS17) ------------------------------------------------------------------------------------------

def test_the_preview_counts_the_companies_that_get_an_epoch(lost):
    preview = installation_keys.replacement_preview(lost.root, machine_wrap=FakeMachineWrap())
    registry = _registry(lost)
    assert preview["company_count"] == len(registry) == 6 and preview["key_available_here"] is False
    assert [c["company_code"] for c in preview["companies"]] == [c["company_code"] for c in registry]
    assert [c["is_archived"] for c in preview["companies"][-3:]] == [False, False, True]
    assert PHRASE in preview["message"] and "6 companies" in preview["message"]
    result = _replace(lost)
    assert len([c for c in result.companies if c["status"] == "done"]) == preview["company_count"]


def test_the_preview_says_when_the_key_is_not_lost(installation):
    preview = installation_keys.replacement_preview(installation.root, machine_wrap=FakeMachineWrap())
    assert preview["key_available_here"] is True and preview["message"] == installation_keys.KEY_NOT_LOST


# --- Partial failure and finishing later ------------------------------------------------------------------------

def test_a_missing_company_file_is_reported_and_can_be_finished_later(lost, tmp_path):
    missing = lost.companies[1]
    aside = tmp_path / "aside.db"
    shutil.move(_path(missing), aside)
    result = _replace(lost)
    statuses = {c["company_id"]: c for c in result.companies}
    assert statuses[missing["company_id"]]["status"] == "failed"
    assert statuses[missing["company_id"]]["message"] == "The company file is missing."
    assert [statuses[c["company_id"]]["status"] for c in (lost.companies[0], lost.companies[2])] == ["done", "done"]
    assert "1 company" in result.message
    remaining = installation_keys.remaining_companies(lost.root)
    assert [c["company_id"] for c in remaining] == [missing["company_id"]]
    shutil.move(aside, _path(missing))
    finished = installation_keys.finish_remaining_companies(lost.root)
    assert [(c["company_id"], c["status"]) for c in finished] == [(missing["company_id"], "done")]
    assert installation_keys.remaining_companies(lost.root) == []
    _post(lost, missing["company_id"], 500)
    assert installation_keys.finish_remaining_companies(lost.root) == []


def test_a_company_file_that_fails_for_another_reason_says_so_in_one_sentence(lost, monkeypatch, caplog):
    from modules.services import ledger_keys
    real = ledger_keys.start_new_key_epoch
    target = lost.companies[0]["company_id"]

    def failing(session, company_id, **kwargs):
        if company_id == target:
            raise RuntimeError("disk full at C:\\secret\\path")
        return real(session, company_id, **kwargs)
    monkeypatch.setattr(ledger_keys, "start_new_key_epoch", failing)
    result = _replace(lost)
    [failed] = [c for c in result.companies if c["status"] == "failed"]
    assert failed["message"] == installation_keys.COMPANY_NOT_FINISHED
    assert "secret" not in failed["message"] and "secret" not in caplog.text
    assert "RuntimeError" in caplog.text                                  # only the error's type is logged


def test_before_any_replacement_no_company_with_a_stored_key_is_left_behind(installation):
    """The test world's own companies were made with the test key, which this master never stored, so they count
    as left behind; the fixture's companies, whose keys are stored, do not."""
    remaining = {c["company_id"] for c in installation_keys.remaining_companies(installation.root)}
    assert remaining == {c["company_id"] for c in _registry(installation)} - {
        c["company_id"] for c in installation.companies}


# --- KS21: each installation key's copies are bound to its own row ------------------------------------------------

def test_a_copy_from_one_installation_key_row_is_refused_on_another(lost):
    result = _replace(lost)
    [row] = _rows(lost.master, "SELECT * FROM installation_key WHERE is_active = 1")
    assert row["id"] == 2
    assert key_store.open_machine_copy(row, FakeMachineWrap()) is not None
    assert key_store.open_recovery_copy(row, result.recovery_code) is not None
    moved = dict(row, id=3)
    assert key_store.open_machine_copy(moved, FakeMachineWrap()) is None
    assert key_store.open_recovery_copy(moved, result.recovery_code) is None
    first = dict(row, id=1)
    assert key_store.open_machine_copy(first, FakeMachineWrap()) is None
    assert key_store.open_recovery_copy(first, result.recovery_code) is None


def test_key_one_keeps_its_binding(installation):
    """Row 1's recovery copy is bound as in Step 1c and its DPAPI copy holds the bare key (32 bytes)."""
    [row] = _rows(installation.master, "SELECT * FROM installation_key")
    assert key_store.recovery_associated_data(1, row["fingerprint"]) == key_store.key_wrap.associated_data(
        "installation_key", 1, "recovery", row["fingerprint"])
    assert len(FakeMachineWrap().unprotect(bytes(row["machine_blob"]))) == 32
    assert key_store.open_machine_copy(dict(row, id=2), FakeMachineWrap()) is None
    assert key_store.open_recovery_copy(dict(row, id=2), CODE) is None
    assert key_store.open_recovery_copy(row, CODE) is not None


# --- Review of Step 1d: the new code is never lost once it has committed ------------------------------------------

def test_a_registry_path_outside_the_folder_fails_that_company_only(lost):
    outside = lost.companies[1]
    elsewhere = os.path.abspath(os.sep + "outside_strataledger_install.db")      # never created
    _master_write(lost, ("UPDATE company_registry SET database_file_path = ? WHERE company_id = ?",
                         (elsewhere, outside["company_id"])))
    result = _replace(lost)
    statuses = {c["company_id"]: c for c in result.companies}
    assert statuses[outside["company_id"]]["status"] == "failed"
    assert statuses[outside["company_id"]]["message"] == "The company file is outside the installation folder"
    assert statuses[lost.companies[0]["company_id"]]["status"] == "done"
    conn = sqlite3.connect(lost.master)
    conn.row_factory = sqlite3.Row
    try:
        assert key_store.open_with_recovery_code(conn, result.recovery_code) is not None
    finally:
        conn.close()
    assert outside["company_id"] in {c["company_id"] for c in installation_keys.remaining_companies(lost.root)}


def test_a_failure_after_the_commit_still_returns_the_new_code(lost, monkeypatch):
    def failing(master_db_path):
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(installation_keys, "_registry", failing)
    result = _replace(lost)
    assert result.companies == [{"company_id": None, "company_code": None, "status": "failed",
                                 "message": installation_keys.COMPANIES_NOT_REACHED}]
    conn = sqlite3.connect(lost.master)
    conn.row_factory = sqlite3.Row
    try:
        assert key_store.open_with_recovery_code(conn, result.recovery_code) is not None
    finally:
        conn.close()
    monkeypatch.undo()
    assert len(installation_keys.finish_remaining_companies(lost.root)) == 6


def test_the_lost_check_is_repeated_inside_the_write(installation, monkeypatch):
    """If the key opens again between the first check and the write, nothing is replaced."""
    before = _snapshot(installation, with_auth=False)
    monkeypatch.setattr(installation_keys, "_key_opens_here", lambda path, wrap: False)
    with pytest.raises(ValidationError) as caught:
        _replace(installation)
    assert str(caught.value) == installation_keys.KEY_NOT_LOST
    assert _snapshot(installation, with_auth=False) == before


def test_the_preview_needs_the_machine_wrap(lost):
    with pytest.raises(TypeError):
        installation_keys.replacement_preview(lost.root)


# --- Mutation check of Step 1d: the survivors -----------------------------------------------------------------------

def test_a_non_master_cannot_list_the_companies_left_behind(lost):
    clerk = lost.session(lost.user("clerk"))
    with pytest.raises(PermissionDeniedError):
        installation_keys.remaining_companies(clerk)


def test_a_wrong_phrase_is_refused_before_the_password_is_checked(lost):
    """A mistyped phrase never counts as a failed sign-in, even with a wrong password too."""
    before = _snapshot(lost)
    with pytest.raises(ValidationError) as caught:
        _replace(lost, password="not the password", phrase="new ledger key")
    assert str(caught.value) == installation_keys.WRONG_PHRASE
    assert _snapshot(lost) == before                                    # no failed sign-in, no throttle row


def test_a_mirror_failure_is_named_in_that_companys_result(lost, monkeypatch):
    def failing(*args, **kwargs):
        raise RuntimeError("master busy")
    monkeypatch.setattr(ledger_verify, "_insert_mirror", failing)
    result = _replace(lost)
    statuses = {c["company_id"]: c for c in result.companies}
    for created in lost.companies:                    # the companies whose lost key leaves a Key lost record
        assert statuses[created["company_id"]]["status"] == "done"
        assert statuses[created["company_id"]]["message"].endswith(
            " " + ledger_verify.KEY_LOST_CHECKPOINT_NOT_MIRRORED)


def test_a_company_with_no_active_key_records_no_checkpoint(installation):
    """The test world's own companies have no ledger key in their files: nothing was lost, nothing is recorded."""
    from modules.services import ledger_keys
    ours = {c["company_id"] for c in installation.companies}
    parent = [c for c in _registry(installation) if c["company_id"] not in ours][0]
    [stored] = _rows(installation.master, "SELECT database_file_path FROM company_registry WHERE company_id = ?",
                     (parent["company_id"],))
    path = Path(config.BASE_PROJECT_DIR) / stored["database_file_path"]
    assert _rows(path, "SELECT key_id FROM ledger_chain_key WHERE is_active = 1") == []
    result = ledger_keys.start_new_key_epoch(installation.root, parent["company_id"],
                                             confirm_company_code=parent["company_code"])
    assert (result["checkpoint_id"], result["recorded_in"]) == (None, [])
    assert "checkpoint_error" not in result
    assert _rows(path, "SELECT 1 FROM ledger_checkpoint WHERE kind = 'Key lost'") == []


def _left_behind_by_one(lost, tmp_path):
    """Replace the key while one company's file is away, then bring it back: it is left behind."""
    away = lost.companies[1]
    aside = tmp_path / "aside.db"
    shutil.move(_path(away), aside)
    _replace(lost)
    shutil.move(aside, _path(away))
    [active] = _rows(_path(away), "SELECT fingerprint FROM ledger_chain_key WHERE is_active = 1")
    return away, active["fingerprint"]


def _store_chain_row(lost, company_id, fingerprint):
    _master_write(lost, ("INSERT INTO company_key (company_id, purpose, fingerprint, wrapped_key, "
                         "installation_key_id, created_at) VALUES (?, 'chain', ?, ?, 2, 't')",
                         (company_id, fingerprint, bytes(61))))


def test_a_stored_key_with_another_fingerprint_does_not_finish_a_company(lost, tmp_path):
    away, _ = _left_behind_by_one(lost, tmp_path)
    _store_chain_row(lost, away["company_id"], "f" * 64)            # a chain row under the new key, not its own
    assert away["company_id"] in {c["company_id"] for c in installation_keys.remaining_companies(lost.root)}


def test_another_companys_stored_key_does_not_finish_a_company(lost, tmp_path):
    away, fingerprint = _left_behind_by_one(lost, tmp_path)
    _store_chain_row(lost, lost.companies[0]["company_id"], fingerprint)      # its fingerprint, another company
    assert away["company_id"] in {c["company_id"] for c in installation_keys.remaining_companies(lost.root)}


def test_a_new_code_after_a_replacement_rewraps_the_new_key(lost):
    _replace(lost)
    issued = auth.issue_recovery_code(lost.root, PASSWORD, machine_wrap=FakeMachineWrap())
    conn = sqlite3.connect(lost.master)
    conn.row_factory = sqlite3.Row
    try:
        rows = {r["id"]: r for r in conn.execute("SELECT * FROM installation_key")}
        assert key_store.open_recovery_copy(rows[2], issued.recovery_code) is not None
        assert key_store.open_recovery_copy(rows[1], issued.recovery_code) is None
        assert key_store.open_with_recovery_code(conn, issued.recovery_code) is not None
    finally:
        conn.close()
