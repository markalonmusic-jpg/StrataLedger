"""R32: a failed sign-in never logs or stores the typed username in clear text.

The log line and auth_event name the user id when the typed name matches an account, otherwise "unknown username";
the per-username throttle is keyed by an HMAC of the normalized name under the master's throttle secret.
"""
import logging
from datetime import timedelta

import pytest

from modules.services import auth, logging_setup, users
from modules.services.keys import SecretKey
from modules.services.errors import AuthenticationError, LoginThrottledError
from tests.authz_world import PASSWORD, world  # noqa: F401  (fixture)
from tests.test_auth import all_master_text

MARKER = "Secret-Pa55-MARKER"     # a password typed into the username box


@pytest.fixture
def clock(monkeypatch):
    state = {"now": auth._now()}
    monkeypatch.setattr(auth, "_now", lambda: state["now"])
    return lambda seconds: state.__setitem__("now", state["now"] + timedelta(seconds=seconds))


@pytest.fixture
def log_file(tmp_path):
    path = tmp_path / "Logs" / "strataledger.log"
    logger = logging_setup.configure_logging(path)
    yield path
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", None) == str(path.resolve()):
            logger.removeHandler(handler)
            handler.close()


def fail(world, username, times=1):
    for _ in range(times):
        with pytest.raises(AuthenticationError):
            auth.login(world.master, username, "wrong password here")


def test_a_typed_marker_is_never_stored_or_logged(world, clock, log_file, caplog):
    boss = world.user("boss", master=True)
    with caplog.at_level(logging.DEBUG):
        fail(world, MARKER, times=5)                          # five failures lock the name
        with pytest.raises(LoginThrottledError):
            auth.login(world.master, MARKER, PASSWORD)
        with pytest.raises(LoginThrottledError):              # a spacing and case variant is the same name
            auth.login(world.master, f"  {MARKER.lower()}  ", PASSWORD)
        clock(31)
        fail(world, f"  {MARKER.lower()}  ")
    stored = all_master_text(world)
    secret = world.master_rows("SELECT secret FROM throttle_secret")[0]["secret"]
    for form in (MARKER, MARKER.lower(), MARKER.upper(), MARKER.casefold(), "wrong password here", secret.hex()):
        assert form not in stored.replace(repr(secret), "")       # the secret's own row aside
        assert form not in caplog.text
        assert form not in log_file.read_text(encoding="utf-8")
    assert repr(secret) not in caplog.text
    events = world.master_rows("SELECT event_type, username, user_id FROM auth_event WHERE event_type <> 'Login'")
    assert {e["event_type"] for e in events} == {"Login failed", "Locked"}
    assert all(e["username"] is None and e["user_id"] is None for e in events)
    assert "user=unknown username" in log_file.read_text(encoding="utf-8")
    assert boss  # the installation has a Master; the marker never matched it


def test_a_known_users_failure_names_the_user_id(world, log_file, caplog):
    ann = world.user("ann")
    with caplog.at_level(logging.DEBUG):
        fail(world, "ann")
    assert world.master_rows("SELECT event_type, username, user_id FROM auth_event") == [
        {"event_type": "Login failed", "username": None, "user_id": ann}]
    assert f"user={ann} " in log_file.read_text(encoding="utf-8")
    assert "username=ann" not in caplog.text and "=ann " not in caplog.text


def test_a_wrong_current_password_logs_the_user_id_only(world, log_file):
    ann = world.user("ann")
    with pytest.raises(AuthenticationError):
        auth.change_password(world.session(ann), "not the old one!", "a brand new passphrase")
    assert world.master_rows("SELECT username, user_id FROM auth_event") == [{"username": None, "user_id": ann}]
    assert "ann" not in log_file.read_text(encoding="utf-8").replace(f"user={ann}", "")


def test_the_throttle_key_is_a_keyed_hash_of_the_normalized_name(world):
    fail(world, MARKER)
    keys = [r["throttle_key"] for r in world.master_rows("SELECT throttle_key FROM login_throttle")]
    assert len(keys) == 1 and len(keys[0]) == 64 and set(keys[0]) <= set("0123456789abcdef")
    secret = world.master_rows("SELECT id, secret FROM throttle_secret")
    assert len(secret) == 1 and secret[0]["id"] == 1 and len(secret[0]["secret"]) == 32
    assert keys[0] == auth.throttle_key(SecretKey(secret[0]["secret"]), f" {MARKER.upper()} ")
    fail(world, MARKER.lower())
    assert [r["failed_count"] for r in world.master_rows("SELECT failed_count FROM login_throttle")] == [2]
    assert len(world.master_rows("SELECT secret FROM throttle_secret")) == 1     # made once


def test_two_installations_hash_the_same_name_differently():
    a, b = SecretKey(b"a" * 32), SecretKey(b"b" * 32)
    assert auth.throttle_key(a, "ann") != auth.throttle_key(b, "ann")
    assert auth.throttle_key(a, "Ann ") == auth.throttle_key(a, "ann")


def test_the_secret_is_held_as_a_secret_key(world):
    fail(world, "nobody")
    conn = auth.read_connection(world.master)
    try:
        secret = auth._throttle_secret(conn)
    finally:
        conn.close()
    assert isinstance(secret, SecretKey) and repr(secret) == "<SecretKey redacted>"


def test_no_secret_yet_means_no_lock(world):
    assert world.master_rows("SELECT * FROM throttle_secret") == []
    world.user("ann")
    auth.login(world.master, "ann", PASSWORD)          # no failure yet: nothing to check, nothing made
    assert world.master_rows("SELECT * FROM throttle_secret") == []


def test_case_variants_share_one_lock(world, clock):
    world.user("ann")
    fail(world, "ANN", times=5)
    with pytest.raises(LoginThrottledError):
        auth.login(world.master, "ann", PASSWORD)


def test_success_and_reset_clear_the_hashed_key(world, clock):
    boss = world.user("boss", master=True)
    ann = world.user("ann")
    fail(world, "Ann", times=4)
    auth.login(world.master, "ann", PASSWORD)
    assert world.master_rows("SELECT * FROM login_throttle") == []
    fail(world, "ann", times=5)
    users.reset_password(world.session(boss), ann, "a temporary passphrase")
    assert world.master_rows("SELECT * FROM login_throttle") == []
    auth.login(world.master, "ann", "a temporary passphrase")


def test_recovery_throttle_key_stays_literal(world, clock):
    with pytest.raises(AuthenticationError):
        auth.recover_master(world.master, "WRONG-CODE-0000", "a brand new passphrase")
    assert [r["throttle_key"] for r in world.master_rows("SELECT throttle_key FROM login_throttle")] == [
        auth.RECOVERY_KEY]


def test_a_username_that_differs_only_in_case_is_not_available(world):
    """The throttle key folds case, so two accounts may never differ only in case (R32, step-reviewer)."""
    from modules.services.errors import ValidationError
    boss = world.user("boss", master=True)
    world.user("ann")
    for taken in ("Ann", "ANN"):
        with pytest.raises(ValidationError, match="^That username is not available$"):
            users.create_user(world.session(boss), taken, PASSWORD, "A", "N", f"other{len(taken)}{taken[-1]}@y.test")
    users.create_user(world.session(boss), "anne", PASSWORD, "A", "N", "anne@x.test")


def _keys(world):
    return [r["throttle_key"] for r in world.master_rows("SELECT throttle_key FROM login_throttle")]


def test_an_idle_throttle_row_is_purged_after_a_day(world, clock):
    """A password typed into the username box leaves a keyed hash; it is kept only while it can matter (R32)."""
    ann = world.user("ann")
    fail(world, MARKER, times=5)                                      # locked for 30 seconds
    clock(auth.THROTTLE_RETENTION_SECONDS - 10)
    fail(world, "someone else")                                       # inside the day: the marker row is kept
    assert len(_keys(world)) == 2
    clock(60)
    fail(world, "a third name")                                       # a day after its last failure: purged
    assert len(_keys(world)) == 2 and _keys(world)[0] != _keys(world)[1]
    clock(auth.THROTTLE_RETENTION_SECONDS + 1)
    auth.login(world.master, "ann", PASSWORD)                         # a success purges idle rows too
    assert _keys(world) == []
    assert ann


def test_a_lock_still_counts_until_it_is_idle_for_a_day(world, clock):
    world.user("ann")
    fail(world, "ann", times=5)
    for _ in range(6):                                                # failures 6-11, each after the lock ran out
        clock(auth.MAX_LOCK_SECONDS + 1)
        fail(world, "ann")
    with pytest.raises(LoginThrottledError) as error:
        auth.login(world.master, "ann", PASSWORD)
    assert error.value.retry_after == auth.MAX_LOCK_SECONDS          # the count was not reset by the purge


def test_a_temporary_password_never_reaches_the_log_when_the_save_fails(world, log_file):
    import sqlite3
    from modules.services.errors import SaveFailedError
    boss, ann = world.user("boss", master=True), world.user("ann")
    temporary = "Temp-Pa55-MARKER-reset"
    conn = sqlite3.connect(world.master)
    conn.execute("CREATE TRIGGER boom BEFORE UPDATE OF password_hash ON app_user BEGIN SELECT RAISE(ABORT, 'x'); END")
    conn.commit()
    conn.close()
    with pytest.raises(SaveFailedError):
        users.reset_password(world.session(boss), ann, temporary)
    text = log_file.read_text(encoding="utf-8")
    assert "a database error stopped a save" in text
    for form in (temporary, temporary.lower(), temporary.upper(), "scrypt$"):
        assert form not in text
