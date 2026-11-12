"""platform_support.py: the one place for Windows-specific calls (decision P3).

The recovery code is copied with three registered clipboard formats that ask Windows to keep it out of clipboard
history and cloud sync. The flags are requested; on the development machine clipboard history is off, so we could
not observe Windows honouring them. These tests prove the formats are written correctly and that failures fall back
quietly without ever logging the text.
"""
import logging
import re
import struct
import sys
import time
from pathlib import Path

import pytest

from modules import platform_support

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the Windows clipboard formats only exist on Windows")
# The tests that use the REAL Windows clipboard run only on demand (set STRATALEDGER_LIVE_CLIPBOARD=1; see
# tests/conftest.py). Another program (clipboard history, the user copying) can change the clipboard between two
# steps of a test, which no retry can prevent, and they wipe the user's clipboard. The default suite keeps every
# test that does not touch the real clipboard (the fallbacks and the static checks below).
live_clipboard = pytest.mark.live_clipboard
SECRET = "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"


class FakeWidget:
    """What copy_secret_text needs from a Tk widget."""

    def __init__(self):
        self.calls = []

    text = ""

    def clipboard_clear(self):
        self.calls.append(("clear",))

    def clipboard_get(self):
        if not self.text:
            raise RuntimeError("CLIPBOARD selection doesn't exist")
        return self.text

    def clipboard_append(self, text):
        self.calls.append(("append", text))


# --- Reading the real Windows clipboard back (test helpers) ------------------------------------------------------------

def _win():
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = wintypes.HANDLE
    u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    u32.RegisterClipboardFormatW.restype = wintypes.UINT
    u32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    u32.EnumClipboardFormats.restype = wintypes.UINT
    u32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    k32.GlobalSize.restype = ctypes.c_size_t
    return ctypes, u32, k32


def _open(u32):
    """Another program may hold the clipboard for a moment: retry for up to a second."""
    for _attempt in range(20):
        if u32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise AssertionError("could not open the clipboard")


def read_clipboard(format_names=()):
    """(text or None, {format name: DWORD}, list of every format id on the clipboard)."""
    ctypes, u32, k32 = _win()
    ids = {name: u32.RegisterClipboardFormatW(name) for name in format_names}
    _open(u32)
    try:
        def raw(fmt):
            handle = u32.GetClipboardData(fmt)
            if not handle:
                return None
            pointer = k32.GlobalLock(handle)
            data = ctypes.string_at(pointer, k32.GlobalSize(handle))
            k32.GlobalUnlock(handle)
            return data
        text = raw(13)
        values = {}
        for name, fmt in ids.items():
            data = raw(fmt) if u32.IsClipboardFormatAvailable(fmt) else None
            values[name] = struct.unpack("<I", data[:4])[0] if data else None
        found, fmt = [], 0
        while True:
            fmt = u32.EnumClipboardFormats(fmt)
            if not fmt:
                break
            found.append(fmt)
        return (text.decode("utf-16-le").rstrip("\0") if text else None), values, found
    finally:
        u32.CloseClipboard()


def empty_clipboard():
    ctypes, u32, _k32 = _win()
    _open(u32)
    try:
        u32.EmptyClipboard()
    finally:
        u32.CloseClipboard()


@pytest.fixture
def clean_clipboard():
    yield
    if sys.platform == "win32":
        empty_clipboard()


# --- Windows: the real clipboard ----------------------------------------------------------------------------------------

FORMATS = (platform_support.FORMAT_EXCLUDE_MONITOR, platform_support.FORMAT_CAN_INCLUDE_IN_HISTORY,
           platform_support.FORMAT_CAN_UPLOAD_TO_CLOUD)


def test_the_format_names_are_the_documented_ones():
    assert FORMATS == ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory",
                       "CanUploadToCloudClipboard")


@windows_only
@live_clipboard
def test_windows_copy_writes_the_text_and_the_three_formats(clean_clipboard):
    method = platform_support.copy_secret_text(FakeWidget(), SECRET)
    assert method == "windows"
    text, values, found = read_clipboard(FORMATS)
    assert text == SECRET
    assert values == {FORMATS[0]: 1, FORMATS[1]: 0, FORMATS[2]: 0}
    assert 13 in found                                                 # CF_UNICODETEXT
    registered = [f for f in found if f >= 0xC000]                     # Windows adds its own converted text formats
    assert len(registered) == 3                                        # but the only registered ones are our three


@windows_only
@live_clipboard
def test_windows_copy_replaces_what_was_there(clean_clipboard):
    platform_support.copy_secret_text(FakeWidget(), "first")
    platform_support.copy_secret_text(FakeWidget(), SECRET)
    assert read_clipboard()[0] == SECRET


@windows_only
@live_clipboard
def test_windows_copy_only_releases_the_tk_clipboard_and_never_hands_it_the_text(clean_clipboard):
    widget = FakeWidget()
    platform_support.copy_secret_text(widget, SECRET)
    assert widget.calls == [("clear",)]


@windows_only
@live_clipboard
def test_windows_read_returns_what_was_copied_and_empty_when_empty(tk_app, clean_clipboard):
    platform_support.copy_secret_text(tk_app, SECRET)
    assert platform_support.read_clipboard_text(tk_app) == SECRET
    platform_support.clear_clipboard(tk_app)
    assert platform_support.read_clipboard_text(tk_app) == ""


@windows_only
@live_clipboard
def test_windows_read_is_not_fooled_by_tk_having_owned_the_clipboard_earlier(tk_app, clean_clipboard):
    tk_app.clipboard_clear()
    tk_app.clipboard_append("text Tk put there earlier")
    platform_support.copy_secret_text(tk_app, SECRET)               # a later write through the Windows API
    assert platform_support.read_clipboard_text(tk_app) == SECRET
    platform_support.clear_clipboard(tk_app)
    assert platform_support.read_clipboard_text(tk_app) == ""       # and Tk's old copy does not come back


@windows_only
@live_clipboard
def test_windows_clear_empties_the_clipboard(tk_app, clean_clipboard):
    platform_support.copy_secret_text(tk_app, SECRET)
    platform_support.clear_clipboard(tk_app)
    text, _values, found = read_clipboard()
    assert text is None and found == []


@windows_only
@live_clipboard
def test_windows_copy_works_for_a_long_text_and_unicode(clean_clipboard):
    platform_support.copy_secret_text(FakeWidget(), SECRET * 40 + " é€")
    assert read_clipboard()[0] == SECRET * 40 + " é€"


# --- Not Windows, or Windows failing: the normal Tk clipboard, quietly -----------------------------------------------------

def test_off_windows_it_is_the_plain_tk_copy_and_never_touches_ctypes(monkeypatch):
    monkeypatch.setattr(platform_support, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_support, "_copy_windows",
                        lambda text: pytest.fail("the Windows path must not run off Windows"))
    widget = FakeWidget()
    assert platform_support.copy_secret_text(widget, SECRET) == "tk"
    assert widget.calls == [("clear",), ("append", SECRET)]


def test_off_windows_clear_is_the_plain_tk_clear(monkeypatch):
    monkeypatch.setattr(platform_support, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_support, "_clear_windows",
                        lambda: pytest.fail("the Windows path must not run off Windows"))
    widget = FakeWidget()
    platform_support.clear_clipboard(widget)
    assert widget.calls == [("clear",)]


def test_a_failing_windows_call_falls_back_quietly(monkeypatch, caplog):
    monkeypatch.setattr(platform_support, "IS_WINDOWS", True)

    def explode(text):
        raise OSError(f"clipboard busy while copying {text}")
    monkeypatch.setattr(platform_support, "_copy_windows", explode)
    widget = FakeWidget()
    with caplog.at_level(logging.DEBUG):
        method = platform_support.copy_secret_text(widget, SECRET)
    assert method == "tk" and widget.calls == [("clear",), ("append", SECRET)]
    assert SECRET not in caplog.text and SECRET.replace("-", "") not in caplog.text
    assert "OSError" in caplog.text                                     # only the error type is logged


def test_off_windows_read_is_the_plain_tk_read(monkeypatch):
    monkeypatch.setattr(platform_support, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_support, "_read_windows", lambda: pytest.fail("not on this platform"))
    widget = FakeWidget()
    assert platform_support.read_clipboard_text(widget) == ""        # Tk raises when empty: reported as ''
    widget.text = SECRET
    assert platform_support.read_clipboard_text(widget) == SECRET


def test_a_failing_windows_read_falls_back_to_tk(monkeypatch, caplog):
    monkeypatch.setattr(platform_support, "IS_WINDOWS", True)

    def explode():
        raise OSError("busy")
    monkeypatch.setattr(platform_support, "_read_windows", explode)
    widget = FakeWidget()
    widget.text = SECRET
    with caplog.at_level(logging.DEBUG):
        assert platform_support.read_clipboard_text(widget) == SECRET
    assert "OSError" in caplog.text and SECRET not in caplog.text


def test_a_failing_windows_clear_falls_back_quietly(monkeypatch, caplog):
    monkeypatch.setattr(platform_support, "IS_WINDOWS", True)

    def explode():
        raise OSError("clipboard busy")
    monkeypatch.setattr(platform_support, "_clear_windows", explode)
    widget = FakeWidget()
    with caplog.at_level(logging.DEBUG):
        platform_support.clear_clipboard(widget)
    assert widget.calls == [("clear",)] and "OSError" in caplog.text


def test_a_windows_call_that_reports_failure_falls_back_too(monkeypatch):
    monkeypatch.setattr(platform_support, "IS_WINDOWS", True)
    monkeypatch.setattr(platform_support, "_copy_windows", lambda text: False)
    widget = FakeWidget()
    assert platform_support.copy_secret_text(widget, SECRET) == "tk"
    assert ("append", SECRET) in widget.calls


# --- Where Windows calls are allowed to live (P3) -----------------------------------------------------------------------------------

# font_loader.py registers fonts with ctypes; it is the only other file with Windows calls and moves here later.
WINDOWS_CALLS_ALLOWED = {"platform_support.py", "font_loader.py"}


def test_windows_specific_calls_stay_in_the_platform_module():
    root = Path(__file__).resolve().parent.parent
    pattern = re.compile(r"\b(import ctypes|from ctypes|import winreg|import msvcrt|windll|WinDLL)\b")
    offenders = []
    for folder in (root / "modules", root / "modules" / "services"):
        for path in folder.glob("*.py"):
            if path.name not in WINDOWS_CALLS_ALLOWED and pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_every_test_that_uses_the_real_clipboard_runs_only_on_demand():
    import inspect
    module = sys.modules[__name__]
    live = [(name, function) for name, function in inspect.getmembers(module, inspect.isfunction)
            if name.startswith("test_") and "clean_clipboard" in inspect.signature(function).parameters]
    assert len(live) == 7
    for name, function in live:
        assert "live_clipboard" in {m.name for m in getattr(function, "pytestmark", [])}, name
