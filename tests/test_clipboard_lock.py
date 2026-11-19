"""The system clipboard is one per computer, so tests that use it hold one lock across processes (2026-11-18).

pytest-xdist's xdist_group does not work with pytest 9.2 (xdist 3.8 renames `item._nodeid`, which pytest 9 no
longer reads), so the grouped clipboard tests ran in parallel workers and raced. Instead, every test marked
`system_clipboard` (and every live_clipboard test, when they are turned on) holds a file lock in the system temp
folder while it runs: parallel workers, and a second test run at the same time, wait their turn. The operating
system releases the lock if a worker dies, so a crash never leaves it held.

Isolation under pytest-xdist (owner 2026-11-18): another worker may hold the shared lock at any moment for a real
clipboard test, so no test here asserts that the shared lock is free. The lock's own behaviour is tested on a
private lock file; the fixture's behaviour is tested by whether this process holds the shared lock.
"""
import subprocess
import sys
import textwrap

import pytest

from tests import conftest


def other_process_can_lock(path=None):
    code = textwrap.dedent('''
        import sys
        sys.path.insert(0, ".")
        from tests.conftest import system_clipboard_lock
        try:
            with system_clipboard_lock(timeout=0, path=sys.argv[1] or None):
                print("locked")
        except TimeoutError:
            print("busy")
    ''')
    result = subprocess.run([sys.executable, "-c", code, str(path or "")], capture_output=True, text=True,
                            timeout=60, cwd=conftest.ROOT)
    return result.stdout.strip()


def test_the_lock_keeps_out_another_process_while_held_and_lets_it_in_after(tmp_path):
    private = tmp_path / "private.lock"          # no other worker uses this file
    with conftest.system_clipboard_lock(path=private):
        assert other_process_can_lock(private) == "busy"
    assert other_process_can_lock(private) == "locked"


class Node:
    """The part of a pytest item that the lock helper reads."""

    def __init__(self, *marker_names):
        self.names = marker_names

    def get_closest_marker(self, name):
        return object() if name in self.names else None


def test_a_marked_test_holds_the_lock_and_lets_go_after(tmp_path):
    private = tmp_path / "private.lock"          # no other worker uses this file
    node = Node("live_clipboard")
    with conftest.hold_clipboard_lock_if_marked(node, path=private):
        assert node.clipboard_lock_held is True
        assert other_process_can_lock(private) == "busy"
    assert node.clipboard_lock_held is False
    assert other_process_can_lock(private) == "locked"


def test_an_unmarked_test_does_not_hold_it(tmp_path, request):
    private = tmp_path / "private.lock"
    node = Node()
    with conftest.hold_clipboard_lock_if_marked(node, path=private):
        assert node.clipboard_lock_held is False
        assert other_process_can_lock(private) == "locked"
    assert request.node.clipboard_lock_held is False     # and the fixture left this very test without it


@pytest.mark.live_clipboard
def test_the_autouse_fixture_holds_the_shared_lock_for_a_live_clipboard_test(request):
    assert request.node.clipboard_lock_held is True
    assert other_process_can_lock() == "busy"


def test_the_live_marker_is_the_only_locked_marker():
    assert set(conftest.CLIPBOARD_MARKERS) == {"live_clipboard"}


# --- A normal run never reaches the person's real clipboard (owner 2026-11-19) -----------------------------------------------

def test_a_normal_test_gets_a_fake_clipboard_shared_by_tk_and_the_windows_calls(tk_app, fake_clipboard):
    from modules import platform_support
    platform_support._copy_windows("from windows")
    assert tk_app.clipboard_get() == "from windows" and platform_support._read_windows() == "from windows"
    tk_app.clipboard_clear()
    tk_app.clipboard_append("from tk")
    assert platform_support._read_windows() == "from tk" and fake_clipboard.text == "from tk"
    platform_support._clear_windows()
    with pytest.raises(Exception, match="CLIPBOARD"):
        tk_app.clipboard_get()


def test_a_normal_test_that_reaches_the_real_windows_clipboard_fails_loudly():
    from modules import platform_support
    with pytest.raises(AssertionError, match="real clipboard"):
        platform_support._api()


def test_the_fake_clipboard_starts_empty_for_every_test(fake_clipboard):
    assert fake_clipboard.text == ""
    fake_clipboard.text = "left behind"


def test_the_fake_clipboard_does_not_carry_text_over_from_the_test_before(fake_clipboard):
    assert fake_clipboard.text == ""


@pytest.mark.live_clipboard
def test_a_live_clipboard_test_gets_the_real_one(fake_clipboard):
    assert fake_clipboard is None
