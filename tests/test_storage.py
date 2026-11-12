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
