"""The one place for operating-system specific calls (decision P3: Windows only in v1, code stays portable).

copy_secret_text puts a secret (the Master's recovery code) on the clipboard. On Windows it also writes three
registered clipboard formats that ASK Windows to keep the copy out of clipboard history (Win+V) and cloud sync:

    ExcludeClipboardContentFromMonitorProcessing   (present: exclude from history, sync and other monitors)
    CanIncludeInClipboardHistory                   DWORD 0
    CanUploadToCloudClipboard                      DWORD 0

HONEST LIMIT: the flags are requested, but we could not observe Windows honouring them, because clipboard history
is switched off on the development machine. A copy may still remain in clipboard history on some systems, so the
screen says so. Nothing here can remove an entry that history already holds.

Failures are quiet: if any Windows call fails, the normal Tk clipboard is used instead and only the error TYPE is
logged. The text being copied is never logged and never put in an exception message. Off Windows the functions are
the plain Tk clipboard calls. Plain ctypes, no extra package. (font_loader.py also uses ctypes for fonts and will
move here later.)
"""
import logging
import struct
import sys
import time

IS_WINDOWS = sys.platform == "win32"

FORMAT_EXCLUDE_MONITOR = "ExcludeClipboardContentFromMonitorProcessing"
FORMAT_CAN_INCLUDE_IN_HISTORY = "CanIncludeInClipboardHistory"
FORMAT_CAN_UPLOAD_TO_CLOUD = "CanUploadToCloudClipboard"

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_OPEN_TRIES = 10
_OPEN_WAIT_SECONDS = 0.02

_logger = logging.getLogger("strataledger.platform")


def copy_secret_text(widget, text):
    """Copy text to the clipboard, asking Windows to keep it out of history and sync. Returns 'windows' or 'tk'.

    The Tk clipboard is cleared first on every path. If Tk had put text on the clipboard earlier it would keep
    serving its own cached copy and ignore a write made through the Windows API until its event loop runs.
    """
    widget.clipboard_clear()
    if IS_WINDOWS:
        try:
            if _copy_windows(text) is not False:
                return "windows"
        except Exception as error:  # noqa: BLE001  (any Windows failure falls back to the Tk clipboard)
            _logger.warning("Windows clipboard exclusion unavailable: %s", type(error).__name__)
    widget.clipboard_append(text)
    return "tk"


def read_clipboard_text(widget):
    """The text on the clipboard, or '' if there is none. Uses the Windows API on Windows.

    Tk keeps its own idea of the clipboard and can disagree with the system clipboard after a write made through
    the Windows API, so the check "does the clipboard still hold the recovery code?" must not depend on Tk.
    """
    if IS_WINDOWS:
        try:
            return _read_windows()
        except Exception as error:  # noqa: BLE001
            _logger.warning("Windows clipboard read unavailable: %s", type(error).__name__)
    try:
        return widget.clipboard_get()
    except Exception:  # noqa: BLE001  (Tk raises TclError when the clipboard is empty or not text)
        return ""


def clear_clipboard(widget):
    """Empty the clipboard (also through the Windows API on Windows, so text this module put there goes too)."""
    widget.clipboard_clear()
    if IS_WINDOWS:
        try:
            _clear_windows()
        except Exception as error:  # noqa: BLE001
            _logger.warning("Windows clipboard clear unavailable: %s", type(error).__name__)


# --- Windows implementation (ctypes is imported only here, only on Windows) --------------------------------------------------

def _api():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    return ctypes, user32, kernel32


def _open_clipboard(user32):
    """Another program may hold the clipboard for a moment, so try a few times."""
    for _attempt in range(_OPEN_TRIES):
        if user32.OpenClipboard(None):
            return
        time.sleep(_OPEN_WAIT_SECONDS)
    raise OSError("the clipboard is busy")


def _set_data(ctypes, user32, kernel32, clipboard_format, payload):
    handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(payload))
    if not handle:
        raise OSError("out of memory")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise OSError("could not lock memory")
    ctypes.memmove(pointer, payload, len(payload))
    kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(clipboard_format, handle):
        kernel32.GlobalFree(handle)         # on success Windows owns the memory
        raise OSError("could not set clipboard data")


def _copy_windows(text):
    """Write the text and the three exclusion formats. Returns True; raises OSError (without the text) on failure."""
    ctypes, user32, kernel32 = _api()
    _open_clipboard(user32)
    try:
        if not user32.EmptyClipboard():
            raise OSError("could not empty the clipboard")
        _set_data(ctypes, user32, kernel32, _CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        for name, value in ((FORMAT_EXCLUDE_MONITOR, 1), (FORMAT_CAN_INCLUDE_IN_HISTORY, 0),
                            (FORMAT_CAN_UPLOAD_TO_CLOUD, 0)):
            clipboard_format = user32.RegisterClipboardFormatW(name)
            if not clipboard_format:
                raise OSError("could not register a clipboard format")
            _set_data(ctypes, user32, kernel32, clipboard_format, struct.pack("<I", value))
    finally:
        user32.CloseClipboard()
    return True


def _read_windows():
    ctypes, user32, kernel32 = _api()
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _open_clipboard(user32)
    try:
        if not user32.IsClipboardFormatAvailable(_CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(_CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _clear_windows():
    _ctypes, user32, _kernel32 = _api()
    _open_clipboard(user32)
    try:
        if not user32.EmptyClipboard():
            raise OSError("could not empty the clipboard")
    finally:
        user32.CloseClipboard()
