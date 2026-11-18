"""The system clipboard is one per computer, so tests that use it hold one lock across processes (2026-11-18).

pytest-xdist's xdist_group does not work with pytest 9.2 (xdist 3.8 renames `item._nodeid`, which pytest 9 no
longer reads), so the grouped clipboard tests ran in parallel workers and raced. Instead, every test marked
`system_clipboard` (and every live_clipboard test, when they are turned on) holds a file lock in the system temp
folder while it runs: parallel workers, and a second test run at the same time, wait their turn. The operating
system releases the lock if a worker dies, so a crash never leaves it held.
"""
import subprocess
import sys
import textwrap

import pytest

from tests import conftest


def other_process_can_lock():
    code = textwrap.dedent('''
        import sys
        sys.path.insert(0, ".")
        from tests.conftest import system_clipboard_lock
        try:
            with system_clipboard_lock(timeout=0):
                print("locked")
        except TimeoutError:
            print("busy")
    ''')
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                            cwd=conftest.ROOT)
    return result.stdout.strip()


def test_the_lock_keeps_out_another_process_while_held_and_lets_it_in_after():
    with conftest.system_clipboard_lock():
        assert other_process_can_lock() == "busy"
    assert other_process_can_lock() == "locked"


@pytest.mark.system_clipboard
def test_the_autouse_fixture_holds_the_lock_for_a_marked_test():
    assert other_process_can_lock() == "busy"


def test_an_unmarked_test_does_not_hold_it():
    assert other_process_can_lock() == "locked"


@pytest.mark.live_clipboard
def test_a_live_clipboard_test_holds_it_too():
    assert other_process_can_lock() == "busy"


def test_the_live_marker_is_one_of_the_locked_markers():
    assert set(conftest.CLIPBOARD_MARKERS) == {"system_clipboard", "live_clipboard"}
