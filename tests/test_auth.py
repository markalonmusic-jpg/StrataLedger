"""Authentication: first Master, login, throttling, password change, recovery, must-change."""
import logging
from datetime import timedelta

import pytest

import modules.database as database
from modules.services import auth, authz, passwords
from modules.services.errors import (
    AuthenticationError, LoginThrottledError, PasswordChangeRequiredError, PermissionDeniedError, ValidationError,
)
from tests.authz_world import PASSWORD, world  # noqa: F401  (fixture)

NEW = "a brand new passphrase"


@pytest.fixture
def master_path(tmp_path, backup_dir):
    path = tmp_path / "master.db"
    database.ensure_master_database(path)
    return path


@pytest.fixture
def clock(monkeypatch):
    """Control auth's notion of now."""
    state = {"now": auth._now()}
    monkeypatch.setattr(auth, "_now", lambda: state["now"])

    def advance(seconds):
        state["now"] += timedelta(seconds=seconds)
    return advance


def all_master_text(world_or_path):
    """Every value in every master table, as one string (to prove secrets are never stored in clear)."""
    import sqlite3
    path = world_or_path.master if hasattr(world_or_path, "master") else world_or_path
    conn = sqlite3.connect(path)
    try:
        chunks = []
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
            for row in conn.execute(f'SELECT * FROM "{name}"'):
                chunks.append(repr(row))
        return "\n".join(chunks)
    finally:
        conn.close()


# --- First Master and the recovery code -----------------------------------------------------

def test_create_first_master_only_on_an_empty_master(master_path):
    created = auth.create_first_master(master_path, "owner", PASSWORD, "Ann", "Owner", "ann@x.test")
    session = auth.login(master_path, "owner", PASSWORD)
    assert session.user_id == created.user_id and session.is_master
    with pytest.raises(ValidationError):
        auth.create_first_master(master_path, "second", PASSWORD, "B", "B", "b@x.test")


def test_first_master_needs_a_valid_password_and_username(master_path):
    with pytest.raises(ValidationError):
        auth.create_first_master(master_path, "owner", "short", "A", "O", "a@x.test")
    with pytest.raises(ValidationError):
        auth.create_first_master(master_path, "bad name#", PASSWORD, "A", "O", "a@x.test")
    with pytest.raises(ValidationError):
        auth.create_first_master(master_path, "owner", PASSWORD, "A", "O", "not-an-email")


def test_recovery_code_is_shown_once_and_only_its_hash_is_stored(master_path, caplog):
    with caplog.at_level(logging.DEBUG):
        created = auth.create_first_master(master_path, "owner", PASSWORD, "Ann", "Owner", "ann@x.test")
    code = created.recovery_code
    stored = all_master_text(master_path)
    assert code not in stored and code.replace("-", "") not in stored
    assert PASSWORD not in stored
    assert code not in caplog.text and PASSWORD not in caplog.text
    events = [r["event_type"] for r in _rows(master_path, "SELECT event_type FROM auth_event")]
    assert events == ["First Master created", "Installation key created"]


def test_recover_master_sets_a_new_password_and_rotates_the_code(master_path):
    created = auth.create_first_master(master_path, "owner", PASSWORD, "Ann", "Owner", "ann@x.test")
    new_code = auth.recover_master(master_path, created.recovery_code, NEW).recovery_code
    assert new_code != created.recovery_code
    auth.login(master_path, "owner", NEW)
    with pytest.raises(AuthenticationError):
        auth.login(master_path, "owner", PASSWORD)
    with pytest.raises(AuthenticationError):
        auth.recover_master(master_path, created.recovery_code, PASSWORD + "x")  # the old code is spent
    auth.recover_master(master_path, new_code, PASSWORD + "y")
    events = [r["event_type"] for r in _rows(master_path, "SELECT event_type FROM auth_event ORDER BY event_id")]
    assert "Master recovered" in events and "Recovery failed" in events


def test_recover_master_is_throttled(master_path, clock):
    created = auth.create_first_master(master_path, "owner", PASSWORD, "Ann", "Owner", "ann@x.test")
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.recover_master(master_path, "WRONG-CODE", NEW)
    with pytest.raises(LoginThrottledError):
        auth.recover_master(master_path, created.recovery_code, NEW)  # refused even with the right code
    clock(31)
    auth.recover_master(master_path, created.recovery_code, NEW)


def test_recover_master_checks_the_new_password(master_path):
    created = auth.create_first_master(master_path, "owner", PASSWORD, "Ann", "Owner", "ann@x.test")
    with pytest.raises(ValidationError):
        auth.recover_master(master_path, created.recovery_code, "short")


# --- Login ---------------------------------------------------------------------------------

def test_login_returns_a_session(world):
    user_id = world.user("ann")
    session = auth.login(world.master, "ann", PASSWORD)
    assert (session.user_id, session.username, session.is_master, session.must_change_password) == (
        user_id, "ann", False, False)
    assert session.master_db_path == str(world.master)


@pytest.mark.parametrize("case", ["wrong password", "unknown user", "inactive user", "plaintext stored"])
def test_every_login_failure_looks_the_same(world, case):
    world.user("ann", active=(case != "inactive user"))
    if case == "plaintext stored":
        import sqlite3
        conn = sqlite3.connect(world.master)
        conn.execute("UPDATE app_user SET password_hash = ? WHERE username = 'ann'", (PASSWORD,))
        conn.commit()
        conn.close()
    username = "nobody" if case == "unknown user" else "ann"
    password = PASSWORD + "x" if case == "wrong password" else PASSWORD
    with pytest.raises(AuthenticationError) as error:
        auth.login(world.master, username, password)
    assert str(error.value) == "Invalid username or password"


def test_unknown_user_still_runs_a_hash(world, monkeypatch):
    calls = []
    real = passwords.verify_password
    monkeypatch.setattr(passwords, "verify_password", lambda pw, stored: calls.append(stored) or real(pw, stored))
    with pytest.raises(AuthenticationError):
        auth.login(world.master, "nobody", PASSWORD)
    assert len(calls) == 1 and calls[0].startswith("scrypt$")


def test_login_rehashes_old_parameters(world, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(passwords, "N", 2 ** 14)
        world.user("ann")
    auth.login(world.master, "ann", PASSWORD)
    stored = world.master_rows("SELECT password_hash FROM app_user WHERE username = 'ann'")[0]["password_hash"]
    assert stored.split("$")[1] == str(passwords.N)


def test_rehash_is_audited_as_the_user_and_leaves_no_audit_context(world, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(passwords, "N", 2 ** 14)
        user_id = world.user("ann")
    auth.login(world.master, "ann", PASSWORD)
    rows = world.master_rows("SELECT user_id, action FROM audit_log WHERE table_name = 'app_user' "
                             "AND record_id = ? AND action = 'Update'", (user_id,))
    assert rows and all(r["user_id"] == user_id for r in rows)
    assert world.master_rows("SELECT user_id FROM audit_context") == [{"user_id": None}]


def test_login_without_rehash_leaves_no_audit_context(world):
    world.user("ann")
    auth.login(world.master, "ann", PASSWORD)
    assert world.master_rows("SELECT user_id FROM audit_context") == [{"user_id": None}]


def test_a_rebuilt_user_table_cannot_set_up_a_second_master(master_path):
    """Before step 1c a wiped user table let first-run start again (the recovery row was upserted). Now the
    installation key exists and can never be replaced, so setting up again is refused and nothing changes; a
    lost Master is restored with the recovery code instead (key_store.ALREADY_HAS_A_KEY)."""
    import sqlite3
    auth.create_first_master(master_path, "root", "correct horse battery", "R", "T", "r@x.test")
    conn = sqlite3.connect(master_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM app_user")      # simulate a rebuilt user table; the recovery row stays
    conn.commit()
    before = conn.execute("SELECT id, code_hash FROM master_recovery").fetchall()
    conn.close()
    with pytest.raises(ValidationError, match="recovery code"):
        auth.create_first_master(master_path, "root", "correct horse battery", "R", "T", "r@x.test")
    conn = sqlite3.connect(master_path)
    try:
        assert conn.execute("SELECT id, code_hash FROM master_recovery").fetchall() == before
        assert conn.execute("SELECT COUNT(*) FROM app_user").fetchone()[0] == 0
    finally:
        conn.close()


def test_failed_logins_never_store_or_log_the_password(world, caplog):
    ann = world.user("ann")
    secret = "my wrong secret attempt"
    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            with pytest.raises(AuthenticationError):
                auth.login(world.master, "ann", secret)
    assert secret not in caplog.text
    assert secret not in all_master_text(world) and PASSWORD not in all_master_text(world)
    events = world.master_rows("SELECT event_type, username, user_id FROM auth_event")
    assert events == [{"event_type": "Login failed", "username": None, "user_id": ann}] * 3     # R32


# --- Throttling ------------------------------------------------------------------------------

def fail(world, username="ann", times=1):
    for _ in range(times):
        with pytest.raises(AuthenticationError):
            auth.login(world.master, username, "wrong password here")


def test_four_failures_do_not_lock(world, clock):
    world.user("ann")
    fail(world, times=4)
    auth.login(world.master, "ann", PASSWORD)


def test_the_fifth_failure_locks_and_the_delay_grows(world, clock):
    world.user("ann")
    fail(world, times=5)
    with pytest.raises(LoginThrottledError) as error:
        auth.login(world.master, "ann", PASSWORD)  # refused even with the right password
    assert error.value.retry_after == 30
    clock(31)
    fail(world)  # 6th failure: 60 seconds
    with pytest.raises(LoginThrottledError) as error:
        auth.login(world.master, "ann", PASSWORD)
    assert error.value.retry_after == 60
    clock(61)
    auth.login(world.master, "ann", PASSWORD)
    fail(world, times=4)  # the counter was reset by the success
    auth.login(world.master, "ann", PASSWORD)


def test_the_delay_is_capped(world, clock):
    world.user("ann")
    fail(world, times=5)
    for _ in range(10):  # failures 6-15, each after the previous lock ran out
        clock(10_000)
        fail(world)
    with pytest.raises(LoginThrottledError) as error:
        auth.login(world.master, "ann", PASSWORD)
    assert error.value.retry_after == 900


def test_attempts_during_a_lock_do_not_extend_it(world, clock):
    world.user("ann")
    fail(world, times=5)
    for _ in range(10):
        with pytest.raises(LoginThrottledError):
            auth.login(world.master, "ann", "wrong password here")
    clock(31)
    auth.login(world.master, "ann", PASSWORD)


def test_unknown_usernames_are_throttled_the_same_way(world, clock):
    fail(world, "nobody", times=5)
    with pytest.raises(LoginThrottledError):
        auth.login(world.master, "nobody", PASSWORD)


def test_a_lock_is_logged(world, clock):
    world.user("ann")
    fail(world, times=5)
    assert "Locked" in [r["event_type"] for r in world.master_rows("SELECT event_type FROM auth_event")]


# --- Change password, must-change ----------------------------------------------------------------

def test_change_password_needs_the_old_one(world):
    user_id = world.user("ann")
    session = world.session(user_id)
    with pytest.raises(AuthenticationError):
        auth.change_password(session, "not the old one!", NEW)
    with pytest.raises(ValidationError):
        auth.change_password(session, PASSWORD, "short")
    auth.change_password(session, PASSWORD, NEW)
    auth.login(world.master, "ann", NEW)
    events = [r["event_type"] for r in world.master_rows("SELECT event_type FROM auth_event")]
    assert "Password changed" in events


def test_password_change_is_audited_without_the_hash(world):
    user_id = world.user("ann")
    auth.change_password(world.session(user_id), PASSWORD, NEW)
    rows = world.master_rows("SELECT * FROM audit_log WHERE table_name = 'app_user' AND action = 'Update'")
    assert len(rows) == 1 and '"password_changed":1' in rows[0]["new_value"].replace(" ", "")
    assert rows[0]["user_id"] == user_id
    for row in world.master_rows("SELECT old_value, new_value FROM audit_log"):
        assert "password_hash" not in (row["old_value"] or "") + (row["new_value"] or "")
        assert "scrypt$" not in (row["old_value"] or "") + (row["new_value"] or "")


def test_must_change_session_is_flagged_and_blocks_everything_but_change_password(world):
    from modules.services import companies, users
    admin = world.user("admin")
    world.grant(admin, "PARENT", "Admin")
    import sqlite3
    conn = sqlite3.connect(world.master)
    conn.execute("UPDATE app_user SET must_change_password = 1 WHERE user_id = ?", (admin,))
    conn.commit()
    conn.close()
    session = auth.login(world.master, "admin", PASSWORD)
    assert session.must_change_password
    with pytest.raises(PasswordChangeRequiredError):
        companies.open_company(session, world.company_id("PARENT"))
    with pytest.raises(PasswordChangeRequiredError):
        users.grant_access(session, admin, world.company_id("CHILD"), "Admin")
    with pytest.raises(PasswordChangeRequiredError):
        authz.authorize(world.ctx(admin, "PARENT"), "ledger.view")  # an existing context stops working too
    auth.change_password(session, PASSWORD, NEW)
    assert not auth.login(world.master, "admin", NEW).must_change_password
    authz.authorize(world.ctx(admin, "PARENT"), "ledger.view")


def test_change_password_refuses_an_inactive_user(world):
    user_id = world.user("ann")
    world.set_user_active(user_id, False)
    with pytest.raises((AuthenticationError, PermissionDeniedError)):
        auth.change_password(world.session(user_id), PASSWORD, NEW)


def _rows(path, sql):
    import sqlite3
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()
