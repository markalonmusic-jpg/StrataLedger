"""File storage for services: a local-disk backend (decision H3).

Services never build file paths themselves. Read-only resources (chart templates, help) come from
`config.RESOURCE_DIR`; everything the app writes (uploads, exports, company files) goes under the
data folder, `config.BASE_PROJECT_DIR` (the alias of `config.DATA_DIR`), read at call time so tests
can point it elsewhere. A hosted version replaces this module with an object-storage backend that
has the same functions. Every path given here is relative and may not leave its folder.
"""
import os

import config
from modules.services.errors import NotFoundError, ValidationError


def _safe_join(base, relative):
    if not isinstance(relative, str) or not relative.strip() or "\0" in relative:
        raise ValidationError("That file location is not valid")
    text = relative.replace("\\", "/")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":") or ".." in text.split("/"):
        raise ValidationError("That file location is not valid")
    root = os.path.realpath(base)
    resolved = os.path.realpath(os.path.join(root, *[p for p in text.split("/") if p]))
    try:
        inside = os.path.commonpath([os.path.normcase(root), os.path.normcase(resolved)]) == os.path.normcase(root)
    except ValueError:                      # different drives on Windows
        inside = False
    if not inside:
        raise ValidationError("That file location is not valid")
    return resolved


# --- Read-only resources -----------------------------------------------------------------------

def resource_path(relative):
    return _safe_join(config.RESOURCE_DIR, relative)


def read_resource_text(relative):
    """Text of a bundled resource; a UTF-8 byte-order mark is dropped."""
    path = resource_path(relative)
    if not os.path.isfile(path):
        raise NotFoundError("That file is missing from the installation")
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return handle.read()


def list_resources(relative_dir, suffix=""):
    """Sorted file names in a resource folder (empty if the folder does not exist)."""
    path = resource_path(relative_dir)
    if not os.path.isdir(path):
        return []
    return sorted(name for name in os.listdir(path)
                  if name.lower().endswith(suffix.lower()) and os.path.isfile(os.path.join(path, name)))


# --- Writable data -----------------------------------------------------------------------------

def data_path(relative):
    return _safe_join(config.BASE_PROJECT_DIR, relative)


def data_exists(relative):
    return os.path.exists(data_path(relative))


def read_data(relative):
    path = data_path(relative)
    if not os.path.isfile(path):
        raise NotFoundError("That file no longer exists")
    with open(path, "rb") as handle:
        return handle.read()


def write_data(relative, content):
    """Write text (UTF-8) or bytes, creating folders as needed. Returns the absolute path."""
    path = data_path(relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode, data = ("wb", content) if isinstance(content, (bytes, bytearray)) else ("w", content)
    with open(path, mode, **({} if mode == "wb" else {"encoding": "utf-8", "newline": ""})) as handle:
        handle.write(data)
    return path


def delete_data(relative):
    """Delete a file; a file that is already gone is not an error."""
    path = data_path(relative)
    if os.path.isfile(path):
        os.remove(path)
