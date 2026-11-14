import ctypes
import io
import logging
import os
import tkinter as tk
import tkinter.font as tkfont
import zipfile
from urllib.request import urlopen

from config import FONT_DIR as _CONFIG_FONT_DIR

logger = logging.getLogger("strataledger.fonts")   # under the app logger, so warnings reach the log file (R38)

FONT_DIR = _CONFIG_FONT_DIR
FONT_FILES = (
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "Inter-Bold.ttf",
)
FONT_ARCHIVE_URL = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
DOWNLOAD_TIMEOUT_SECONDS = 20
MAX_ARCHIVE_SIZE = 40 * 1024 * 1024


def _registered_families():
    return set(tkfont.families())


def _extract_font_files(archive_data, font_dir=None):
    font_dir = font_dir or FONT_DIR
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        members = {name.rsplit("/", 1)[-1]: name for name in archive.namelist()}
        font_data = {
            filename: archive.read(members[filename])
            for filename in FONT_FILES
        }
        license_member = next(
            (
                name
                for name in archive.namelist()
                if name.rsplit("/", 1)[-1].lower() in {"ofl.txt", "license.txt"}
            ),
            None,
        )
        license_data = archive.read(license_member) if license_member else None

    os.makedirs(font_dir, exist_ok=True)
    for filename, contents in font_data.items():
        with open(os.path.join(font_dir, filename), "wb") as font_file:
            font_file.write(contents)
    if license_data:
        with open(os.path.join(font_dir, "OFL.txt"), "wb") as license_file:
            license_file.write(license_data)


def _download_and_extract_fonts():
    with urlopen(FONT_ARCHIVE_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        archive_data = response.read(MAX_ARCHIVE_SIZE + 1)
    if len(archive_data) > MAX_ARCHIVE_SIZE:
        raise ValueError("Inter font archive exceeds the download size limit")
    _extract_font_files(archive_data)


def _register_private_fonts():
    if os.name != "nt":
        raise OSError("Private Inter font registration is supported only on Windows")

    add_font = ctypes.windll.gdi32.AddFontResourceExW
    add_font.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    add_font.restype = ctypes.c_int
    for filename in FONT_FILES:
        path = os.path.join(FONT_DIR, filename)
        if not add_font(path, 0x10, 0):
            raise OSError(f"Windows could not register {filename}")


def ensure_inter_font():
    try:
        if "Inter" in _registered_families():
            return True
    except (RuntimeError, tk.TclError) as exc:
        logger.warning("Could not inspect Tk font families; using the system fallback: %s", exc)
        return False

    if os.name != "nt":
        logger.warning("Private Inter font provisioning requires Windows; using the system fallback")
        return False

    try:
        if not all(os.path.isfile(os.path.join(FONT_DIR, name)) for name in FONT_FILES):
            _download_and_extract_fonts()
        _register_private_fonts()
        if "Inter" in _registered_families():
            return True
        logger.warning("Inter fonts were registered, but Tk did not report the Inter family")
    except (AttributeError, OSError, RuntimeError, ValueError, tk.TclError, zipfile.BadZipFile, KeyError) as exc:
        logger.warning("Inter font provisioning failed; using Segoe UI: %s", exc)
    return False
