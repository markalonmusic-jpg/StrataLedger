"""storage.py: the local-disk backend that services use for files (decision H3)."""
import os

import pytest

import config
from modules.services import storage
from modules.services.errors import NotFoundError, ValidationError


@pytest.fixture
def folders(tmp_path, monkeypatch):
    data, res = tmp_path / "data", tmp_path / "res"
    data.mkdir()
    (res / "templates" / "coa").mkdir(parents=True)
    (res / "templates" / "coa" / "a.csv").write_bytes(b"\xef\xbb\xbfcol\r\n1\r\n")
    (res / "templates" / "coa" / "b.csv").write_text("x", encoding="utf-8")
    (res / "templates" / "coa" / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "BASE_PROJECT_DIR", str(data))
    monkeypatch.setattr(config, "RESOURCE_DIR", str(res))
    return data, res


def test_read_resource_text_strips_a_bom(folders):
    assert storage.read_resource_text("templates/coa/a.csv") == "col\r\n1\r\n"


def test_list_resources_filters_by_suffix_and_sorts(folders):
    assert storage.list_resources("templates/coa", ".csv") == ["a.csv", "b.csv"]
    assert storage.list_resources("templates/missing", ".csv") == []


def test_missing_resource_is_not_found(folders):
    with pytest.raises(NotFoundError):
        storage.read_resource_text("templates/coa/none.csv")


def test_resources_are_read_only(folders):
    assert not hasattr(storage, "write_resource")
    with pytest.raises(ValidationError):
        storage.write_data("../res/templates/coa/a.csv", "x")


def test_write_read_exists_delete_data(folders):
    data, _ = folders
    storage.write_data("Uploaded_Files/sub/x.txt", "hello")
    assert (data / "Uploaded_Files" / "sub" / "x.txt").read_text(encoding="utf-8") == "hello"
    assert storage.data_exists("Uploaded_Files/sub/x.txt")
    assert storage.read_data("Uploaded_Files/sub/x.txt") == b"hello"
    storage.write_data("Uploaded_Files/sub/y.bin", b"\x00\x01")
    assert storage.read_data("Uploaded_Files/sub/y.bin") == b"\x00\x01"
    storage.delete_data("Uploaded_Files/sub/x.txt")
    assert not storage.data_exists("Uploaded_Files/sub/x.txt")
    storage.delete_data("Uploaded_Files/sub/x.txt")        # deleting twice is fine


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/abs/path", "C:/abs/path", "C:\\abs\\path", "", "a\0b",
                                 "\\\\server\\share\\f"])
def test_paths_that_escape_or_are_absolute_are_refused(folders, bad):
    for call in (lambda: storage.data_path(bad), lambda: storage.write_data(bad, "x"),
                 lambda: storage.read_resource_text(bad)):
        with pytest.raises(ValidationError):
            call()


def test_data_path_stays_under_the_data_folder(folders):
    data, _ = folders
    path = storage.data_path("Companies/X.db")
    assert os.path.normcase(path).startswith(os.path.normcase(str(data)))


def test_services_never_open_files_outside_storage():
    """H3: only storage.py, paths.py, companies.py and logging_setup.py touch the file system."""
    import re
    from pathlib import Path
    allowed = {"storage.py", "paths.py", "companies.py", "logging_setup.py", "tx.py"}
    offenders = []
    for path in Path(config.RESOURCE_DIR, "modules", "services").glob("*.py"):
        if path.name in allowed:
            continue
        if re.search(r"(?<![\w.])open\(|os\.makedirs|shutil\.|\.write_text\(|\.read_text\(|os\.remove\(", path.read_text(encoding="utf-8")):
            offenders.append(path.name)
    assert offenders == []


# --- resource_tree (HA8 M1, owner 2026-11-18) ---------------------------------------------------------------------

def test_resource_tree_lists_the_folder_then_every_folder_and_file_in_order(folders):
    root = os.path.join(config.RESOURCE_DIR, "addons")
    os.makedirs(os.path.join(root, "b", "inner"))
    os.makedirs(os.path.join(root, "a"))
    for relative in ("z.txt", "a/one.py", "b/inner/two.sql"):
        with open(os.path.join(root, *relative.split("/")), "w", encoding="utf-8") as handle:
            handle.write("x")
    real = os.path.realpath(root)
    found = [os.path.relpath(p, real).replace(os.sep, "/") for p in storage.resource_tree("addons")]
    assert found == [".", "a", "b", "z.txt", "a/one.py", "b/inner", "b/inner/two.sql"]


def test_resource_tree_of_a_missing_folder_is_empty_and_a_bad_path_is_refused(folders):
    assert storage.resource_tree("addons") == []
    with pytest.raises(ValidationError):
        storage.resource_tree("../outside")


def test_resource_tree_raises_when_a_folder_cannot_be_listed(folders, monkeypatch):
    os.makedirs(os.path.join(config.RESOURCE_DIR, "addons", "a"))

    def walk(top, onerror=None):
        onerror(PermissionError(5, "Access is denied"))
        yield from ()
    monkeypatch.setattr(storage.os, "walk", walk)
    with pytest.raises(PermissionError):
        storage.resource_tree("addons")


@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_resource_tree_refuses_a_link_anywhere_in_it(folders, tmp_path, kind):
    """Step-review 3 (fail closed): a link reaches files outside the tree that would never be checked."""
    import subprocess
    root = os.path.join(config.RESOURCE_DIR, "addons", "demo")
    os.makedirs(root)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "hidden.py").write_text("x", encoding="utf-8")
    link = os.path.join(root, "link")
    try:
        if kind == "symlink":
            os.symlink(str(target), link, target_is_directory=True)
        else:
            if os.name != "nt":
                pytest.skip("junctions are Windows only")
            subprocess.run(["cmd", "/c", "mklink", "/J", link, str(target)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip(f"this account cannot make a {kind}")
    with pytest.raises(OSError, match="link"):
        storage.resource_tree("addons")
