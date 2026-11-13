"""Step 1c sub-step 6: creating a company makes its chain key; the app sets the key provider, so posting through
the service works outside the test suite (docs/audit_readiness_design.md 2.7; KS3, KS6, KS7).

* create_company asks the key provider for a new chain key before it builds anything. A locked or absent key
  store refuses with KS6's sentence and nothing is created. The company file gets the active `ledger_chain_key`
  row (fingerprint only); the master gets the key wrapped by the installation key (`company_key`), bound to the
  company by its associated data, and an auth_event 'Ledger key created' naming the company.
* LocalKeyProvider.get_key(company_id, key_id) finds the key by the fingerprint of the company's key row (KS3).
* The test switch (`key_store.use_test_key_for_new_companies`) makes create_company use the suite's fixed key and
  store nothing in the master. It works only when STRATALEDGER_ALLOW_TEST_KEYS is "1" (KS7), like
  FixedKeyProvider; tests/conftest.py turns it on for the suite.
"""
import dataclasses
import inspect
import sqlite3
from pathlib import Path

import pytest

import config
from modules.services import companies, key_store, key_wrap, keys, ledger, ledger_chain, ledger_verify
from modules.services.errors import KeyStoreLockedError, KeyUnavailableError
from modules.services.keys import SecretKey
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_key_store import FakeMachineWrap
from tests.test_page_keys import _load_app

CODE = "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"
NOW = "2026-11-12T09:00:00+00:00"
CHAIN = SecretKey(bytes(range(50, 82)))


def _installation(world, wrap):
    """Give the world's master an installation key, as first run would."""
    conn = sqlite3.connect(world.master)
    try:
        key_store.create_installation_key(conn, CODE, wrap, NOW)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def real_keys(world, monkeypatch):
    """The real path: no test switch, an unlocked LocalKeyProvider over the world's master."""
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    wrap = FakeMachineWrap()
    _installation(world, wrap)
    provider = key_store.LocalKeyProvider(world.master, wrap)
    assert provider.is_unlocked
    monkeypatch.setattr(keys, "_provider", provider)
    world.root = world.session(world.user("root", master=True))
    return provider


def _create(session, name="Acme Builders"):
    return companies.create_company(session, legal_name=name, first_fiscal_year=2026, template="construction")


def _company_rows(world, created, sql):
    conn = sqlite3.connect(Path(config.BASE_PROJECT_DIR) / created["database_file_path"])
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def _master_rows(world, sql, params=()):
    conn = sqlite3.connect(world.master)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


# --- create_company makes the chain key -------------------------------------------------------------------------

def test_a_new_company_gets_an_active_key_in_its_file_and_the_wrapped_key_in_the_master(world, real_keys):
    created = _create(world.root)
    [row] = _company_rows(world, created, "SELECT key_id, fingerprint, is_active, created_by FROM ledger_chain_key")
    assert row["is_active"] == 1 and row["created_by"] == world.root.user_id
    [stored] = _master_rows(world, "SELECT * FROM company_key")
    assert (stored["company_id"], stored["purpose"], stored["fingerprint"]) == (
        created["company_id"], "chain", row["fingerprint"])
    assert len(stored["wrapped_key"]) == 61
    key = real_keys.get_key(created["company_id"], row["key_id"])
    assert ledger_chain.fingerprint(key.use_for_hmac()) == row["fingerprint"]


def test_creating_a_key_is_recorded_as_an_auth_event_naming_the_company(world, real_keys):
    created = _create(world.root)
    events = _master_rows(world, "SELECT user_id, company_id FROM auth_event WHERE event_type = 'Ledger key created'")
    assert events == [{"user_id": world.root.user_id, "company_id": created["company_id"]}]
    for row in _master_rows(world, "SELECT table_name FROM audit_log"):
        assert row["table_name"] != "company_key"


def test_each_company_gets_its_own_key(world, real_keys):
    first, second = _create(world.root, "Acme Builders"), _create(world.root, "Bravo Homes")
    fingerprints = [r["fingerprint"] for r in _master_rows(world, "SELECT fingerprint FROM company_key")]
    assert len(set(fingerprints)) == 2
    assert first["company_id"] != second["company_id"]


def test_the_chain_key_is_never_in_either_file_in_clear(world, real_keys, monkeypatch):
    monkeypatch.setattr(ledger_chain, "new_key", lambda: CHAIN.use_for_hmac())
    created = _create(world.root)
    company_file = Path(config.BASE_PROJECT_DIR) / created["database_file_path"]
    for path in (world.master, company_file):
        raw = Path(path).read_bytes()
        assert CHAIN.use_for_hmac() not in raw and CHAIN.use_for_hmac().hex().encode() not in raw


@pytest.mark.parametrize("provider_kind", ["locked", "null", "fixed"])
def test_without_an_unlocked_key_store_no_company_is_created(world, monkeypatch, provider_kind):
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    if provider_kind == "locked":
        _installation(world, FakeMachineWrap(fail_protect=True))
        provider = key_store.LocalKeyProvider(world.master, FakeMachineWrap())
        assert provider.status == "locked"
    elif provider_kind == "null":
        provider = keys.NullKeyProvider()
    else:
        provider = keys.FixedKeyProvider(lh.TEST_CHAIN_KEY)
    monkeypatch.setattr(keys, "_provider", provider)
    root = world.session(world.user("root", master=True))
    before = _master_rows(world, "SELECT company_id FROM company_registry")
    with pytest.raises(KeyStoreLockedError) as caught:
        _create(root)
    assert str(caught.value) == "Ask the Master to restore the ledger key with the recovery code first."
    assert _master_rows(world, "SELECT company_id FROM company_registry") == before
    assert _master_rows(world, "SELECT * FROM company_key") == []
    assert not (Path(config.BASE_PROJECT_DIR) / "Companies").exists() or not list(
        (Path(config.BASE_PROJECT_DIR) / "Companies").iterdir())


def test_a_failure_after_the_key_is_made_leaves_no_key_behind(world, real_keys, monkeypatch):
    def broken(conn, company_id, user_ids):
        raise RuntimeError("the grant failed")
    monkeypatch.setattr(companies, "_grant_admins", broken)
    with pytest.raises(RuntimeError):
        _create(world.root)
    assert _master_rows(world, "SELECT * FROM company_key") == []
    assert _master_rows(world, "SELECT * FROM auth_event WHERE event_type = 'Ledger key created'") == []


# --- get_key: matched by fingerprint (KS3) -------------------------------------------------------------------------

def test_an_unknown_key_id_is_unavailable(world, real_keys):
    created = _create(world.root)
    with pytest.raises(KeyUnavailableError):
        real_keys.get_key(created["company_id"], 99)
    with pytest.raises(KeyUnavailableError):
        real_keys.get_key(9999, 1)


def test_a_key_row_with_no_stored_key_is_unavailable(world, real_keys):
    created = _create(world.root)
    path = Path(config.BASE_PROJECT_DIR) / created["database_file_path"]
    conn = sqlite3.connect(path)
    conn.execute("UPDATE ledger_chain_key SET is_active = 0, retired_at = 't', retire_reason = 'Rotation'")
    new_id = conn.execute("INSERT INTO ledger_chain_key (fingerprint, created_at) VALUES (?, 't') RETURNING key_id",
                          ("c" * 64,)).fetchone()[0]
    conn.commit()
    conn.close()
    with pytest.raises(KeyUnavailableError):
        real_keys.get_key(created["company_id"], new_id)


def test_a_stored_key_is_bound_to_its_company(world, real_keys):
    """A wrapped key copied to another company's row does not open: the associated data names the company."""
    first, second = _create(world.root, "Acme Builders"), _create(world.root, "Bravo Homes")
    [a] = _master_rows(world, "SELECT * FROM company_key WHERE company_id = ?", (first["company_id"],))
    [b_key] = _company_rows(world, second, "SELECT key_id, fingerprint FROM ledger_chain_key")
    conn = sqlite3.connect(world.master)
    conn.execute("DROP TRIGGER company_key_no_update")      # simulate tampering with the file outside the app
    conn.execute("UPDATE company_key SET wrapped_key = ? WHERE company_id = ?",
                 (a["wrapped_key"], second["company_id"]))
    conn.commit()
    conn.close()
    fresh = key_store.LocalKeyProvider(world.master, FakeMachineWrap())
    with pytest.raises(KeyUnavailableError):
        fresh.get_key(second["company_id"], b_key["key_id"])


def test_a_locked_provider_gives_no_company_key(world, real_keys):
    created = _create(world.root)
    [row] = _company_rows(world, created, "SELECT key_id FROM ledger_chain_key")
    locked = key_store.LocalKeyProvider(world.master, FakeMachineWrap(fail_unprotect=True))
    with pytest.raises(KeyUnavailableError) as caught:
        locked.get_key(created["company_id"], row["key_id"])
    assert str(caught.value) == keys.NO_KEY_MESSAGE


# --- Posting works through the service with the real provider ---------------------------------------------------

def _two_postable_accounts(context):
    conn = sqlite3.connect(context.company_db_path)
    try:
        return [r[0] for r in conn.execute(
            "SELECT account_id FROM account AS a WHERE is_active = 1 AND is_postable = 1 AND control_type IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM account AS c WHERE c.parent_id = a.account_id) "
            "ORDER BY account_id LIMIT 2")]
    finally:
        conn.close()


def test_a_new_company_can_post_and_verify_with_the_real_provider(world, real_keys):
    created = _create(world.root)
    context = dataclasses.replace(companies.open_company(world.root, created["company_id"]),
                                  now="2026-03-20T10:00:00+00:00", today="2026-03-20")
    debit, credit = _two_postable_accounts(context)
    entry_id = ledger.create_entry(context, entry_date="2026-03-15", lines=[
        {"account_id": debit, "debit_cents": 1250}, {"account_id": credit, "credit_cents": 1250}])
    ledger.post_journal_entry(context, entry_id, confirm=True, acknowledge_date_warnings=True)
    [entry] = _company_rows(world, created, "SELECT entry_number, chain_hash FROM journal_entry")
    assert entry["entry_number"] == 1 and len(entry["chain_hash"]) == 64
    result = ledger_verify.verify_ledger(context, mode="full")
    assert result["status"] == "OK"


# --- The test switch (KS7) -----------------------------------------------------------------------------------------

def test_the_suite_creates_companies_with_the_fixed_test_key_and_stores_nothing(world):
    root = world.session(world.user("root", master=True))
    created = _create(root)
    [row] = _company_rows(world, created, "SELECT fingerprint, is_active FROM ledger_chain_key")
    assert row == {"fingerprint": ledger_chain.fingerprint(lh.TEST_CHAIN_KEY), "is_active": 1}
    assert _master_rows(world, "SELECT * FROM company_key") == []


def test_the_test_switch_refuses_to_turn_on_without_the_test_flag(monkeypatch):
    monkeypatch.delenv("STRATALEDGER_ALLOW_TEST_KEYS")
    with pytest.raises(RuntimeError, match="test suite only"):
        key_store.use_test_key_for_new_companies(lh.TEST_CHAIN_KEY)
    monkeypatch.setenv("STRATALEDGER_ALLOW_TEST_KEYS", "yes")
    with pytest.raises(RuntimeError, match="test suite only"):
        key_store.use_test_key_for_new_companies(lh.TEST_CHAIN_KEY)


def test_a_test_switch_left_on_is_refused_once_the_flag_is_gone(world, monkeypatch):
    root = world.session(world.user("root", master=True))
    monkeypatch.delenv("STRATALEDGER_ALLOW_TEST_KEYS")
    with pytest.raises(RuntimeError, match="test suite only"):
        _create(root)
    assert _master_rows(world, "SELECT company_id FROM company_registry WHERE company_code = 'ACME'") == []


def test_the_test_switch_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(key_store, "_test_new_company_key", key_store._test_new_company_key)
    key_store.use_test_key_for_new_companies(None)
    assert key_store._test_new_company_key is None


# --- The app sets the provider -----------------------------------------------------------------------------------

def test_the_app_unlocks_the_key_store_and_makes_it_the_provider(world, monkeypatch):
    wrap = FakeMachineWrap()
    _installation(world, wrap)
    app_module = _load_app()
    monkeypatch.setattr(app_module.platform_support, "DPAPI", wrap)
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())

    class StandIn:
        start_key_store = app_module.App.start_key_store
        master_db_path = world.master
    stand_in = StandIn()
    stand_in.start_key_store()
    assert keys.get_provider() is stand_in.key_provider
    assert isinstance(stand_in.key_provider, key_store.LocalKeyProvider) and stand_in.key_provider.is_unlocked


def test_the_app_starts_the_key_store_before_it_shows_the_launcher():
    source = inspect.getsource(_load_app().App.__init__)
    launcher = source[source.index("else:"):]
    assert launcher.index("self.start_key_store()") < launcher.index("self.show_no_company_open_screen()")


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="DPAPI exists only on Windows")
def test_end_to_end_with_real_dpapi_first_run_create_company_post_and_verify(tmp_path, backup_dir, monkeypatch):
    """What a person does by hand: first run, start the app again, create a company, post one entry, verify."""
    from modules import platform_support
    from modules.services import auth
    import modules.database as database
    monkeypatch.setattr(config, "BASE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(key_store, "_test_new_company_key", None)
    monkeypatch.setattr(keys, "_provider", keys.NullKeyProvider())
    master = tmp_path / "system_master.db"
    database.ensure_master_database(master)
    created = auth.create_first_master(master, "owner", "correct horse battery", "Ann", "Owner", "ann@x.test",
                                       machine_wrap=platform_support.DPAPI)
    assert created.ledger_key_locked is False
    provider = key_store.LocalKeyProvider(master, platform_support.DPAPI)     # a later start of the app
    keys.set_provider(provider)
    assert provider.status == "unlocked"
    session = auth.login(master, "owner", "correct horse battery")
    company = _create(session)
    context = dataclasses.replace(companies.open_company(session, company["company_id"]),
                                  now="2026-03-20T10:00:00+00:00", today="2026-03-20")
    debit, credit = _two_postable_accounts(context)
    entry_id = ledger.create_entry(context, entry_date="2026-03-15", lines=[
        {"account_id": debit, "debit_cents": 500}, {"account_id": credit, "credit_cents": 500}])
    ledger.post_journal_entry(context, entry_id, confirm=True, acknowledge_date_warnings=True)
    assert ledger_verify.verify_ledger(context, mode="full")["status"] == "OK"
