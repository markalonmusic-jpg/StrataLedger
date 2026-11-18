import contextlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

import modules.database as database

# The tests never open real database files; every database is built in tmp_path.

# keys.FixedKeyProvider (a constant chain key) refuses to load unless this is set; only the tests set it.
os.environ["STRATALEDGER_ALLOW_TEST_KEYS"] = "1"


@pytest.fixture(autouse=True, scope="session")
def _companies_use_the_fixed_test_key():
    """create_company gives every new company the suite's fixed chain key (TEST_CHAIN_KEY) and stores nothing in
    the master (key_store test switch, KS7). Tests of the real key path turn it off for themselves."""
    from modules.services import key_store
    from tests.ledger_helpers import TEST_CHAIN_KEY
    key_store.use_test_key_for_new_companies(TEST_CHAIN_KEY)
    yield
    key_store.use_test_key_for_new_companies(None)


ROOT = Path(__file__).resolve().parent.parent

# The system clipboard is one per computer. A test with one of these markers holds CLIPBOARD_LOCK while it runs, so
# parallel workers (pytest-xdist) and a second test run at the same time take turns (tests/test_clipboard_lock.py).
# xdist_group cannot do this: xdist 3.8 renames `item._nodeid`, which pytest 9.2 no longer reads.
CLIPBOARD_MARKERS = ("system_clipboard", "live_clipboard")
CLIPBOARD_LOCK = Path(tempfile.gettempdir()) / "strataledger-tests-system-clipboard.lock"


@contextlib.contextmanager
def system_clipboard_lock(timeout=600):
    """Hold the cross-process clipboard lock; TimeoutError if it is not free within `timeout` seconds. The
    operating system releases it when the process ends, so a crashed worker never leaves it held."""
    handle = os.open(CLIPBOARD_LOCK, os.O_RDWR | os.O_CREAT)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    os.lseek(handle, 0, os.SEEK_SET)
                    msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("the system clipboard lock is held by another test process") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(handle, 0, os.SEEK_SET)
                msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(handle)


@pytest.fixture(autouse=True)
def _one_test_at_a_time_on_the_system_clipboard(request):
    if any(request.node.get_closest_marker(name) for name in CLIPBOARD_MARKERS):
        with system_clipboard_lock():
            yield
    else:
        yield


def pytest_configure(config):
    config.addinivalue_line("markers", "live_clipboard: uses the real Windows clipboard; runs only when "
                                       "STRATALEDGER_LIVE_CLIPBOARD=1")
    config.addinivalue_line("markers", "system_clipboard: uses the real system clipboard; holds the clipboard lock "
                                       "so parallel workers take turns")


def pytest_collection_modifyitems(config, items):
    """Live-clipboard tests are deselected (not skipped) unless STRATALEDGER_LIVE_CLIPBOARD=1. When they run, they
    hold the clipboard lock like system_clipboard tests (step-reviewer L7)."""
    if os.environ.get("STRATALEDGER_LIVE_CLIPBOARD") == "1":
        return
    live = [item for item in items if item.get_closest_marker("live_clipboard")]
    if live:
        config.hook.pytest_deselected(items=live)
        items[:] = [item for item in items if not item.get_closest_marker("live_clipboard")]


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    path = tmp_path / "Backups"
    monkeypatch.setattr(database, "BACKUP_DIR", str(path))
    return path


@pytest.fixture(scope="session")
def _company_template(tmp_path_factory):
    # A new file is never backed up, so BACKUP_DIR is not touched here.
    path = tmp_path_factory.mktemp("template") / "company.db"
    database.ensure_company_database(path)
    return path


@pytest.fixture
def fresh_company(tmp_path, backup_dir, _company_template):
    db_path = tmp_path / "company.db"
    shutil.copy2(_company_template, db_path)
    return db_path


@pytest.fixture(scope="session")
def tk_app():
    """The one hidden Tk window for the whole test session.

    Creating several Tk() roots in one process intermittently fails on Windows to find tk.tcl / init.tcl,
    so every test that needs real widgets builds them inside this window.
    """
    import tkinter
    import customtkinter as ctk
    try:
        app = ctk.CTk()
    except tkinter.TclError as error:  # genuinely no display available
        pytest.skip(f"no display: {error}")
    app.withdraw()
    yield app
    app.destroy()

