"""Mutation tests for commit 55a0e2b (owner answers: HA8 allow-list, HA11 names, KS12 tie).

Each test kills a mutant the commit's own tests let survive: resource_tree's two sorts, its check of the root and of
the last entry, _is_link's symbolic-link branch, and addons_off skipping a program folder that does not exist.
"""
import os
import types

import pytest

import config
import modules.database as database
from modules.services import addons, storage
from tests.test_addons import resources  # noqa: F401  (fixture)
from tests.test_storage import folders  # noqa: F401  (fixture)


def _fake_walk(folder_names, file_names):
    def walk(top, onerror=None):
        yield top, list(folder_names), list(file_names)       # deliberately not in order
    return walk


@pytest.fixture
def addons_root(folders):  # noqa: F811
    root = os.path.join(config.RESOURCE_DIR, "addons")
    for name in ("a", "b"):
        os.makedirs(os.path.join(root, name))
    for name in ("y.txt", "z.txt"):
        with open(os.path.join(root, name), "w", encoding="utf-8") as handle:
            handle.write("x")
    return root


def _names(root):
    real = os.path.realpath(root)
    return [os.path.relpath(p, real).replace(os.sep, "/") for p in storage.resource_tree("addons")]


def test_resource_tree_sorts_folders_whatever_order_the_file_system_lists_them(addons_root, monkeypatch):
    monkeypatch.setattr(storage.os, "walk", _fake_walk(["b", "a"], ["y.txt", "z.txt"]))
    assert _names(addons_root) == [".", "a", "b", "y.txt", "z.txt"]


def test_resource_tree_sorts_files_whatever_order_the_file_system_lists_them(addons_root, monkeypatch):
    monkeypatch.setattr(storage.os, "walk", _fake_walk(["a", "b"], ["z.txt", "y.txt"]))
    assert _names(addons_root) == [".", "a", "b", "y.txt", "z.txt"]


def _link_only(monkeypatch, wanted):
    real = storage._is_link
    monkeypatch.setattr(storage, "_is_link", lambda path: real(path) or wanted(path))


def test_resource_tree_refuses_when_the_folder_itself_is_a_link(addons_root, monkeypatch):
    root = os.path.realpath(addons_root)
    _link_only(monkeypatch, lambda path: os.path.realpath(path) == root)
    with pytest.raises(OSError, match="link"):
        storage.resource_tree("addons")


def test_resource_tree_refuses_when_the_last_entry_is_a_link(addons_root, monkeypatch):
    last = storage.resource_tree("addons")[-1]
    assert last.endswith("z.txt")
    _link_only(monkeypatch, lambda path: path == last)
    with pytest.raises(OSError, match="link"):
        storage.resource_tree("addons")


def test_is_link_is_true_for_a_symbolic_link_even_without_the_reparse_attribute(tmp_path, monkeypatch):
    target = tmp_path / "plain.txt"
    target.write_text("x", encoding="utf-8")
    plain = types.SimpleNamespace(st_file_attributes=0)
    monkeypatch.setattr(storage.os.path, "islink", lambda path: True)
    monkeypatch.setattr(storage.os, "lstat", lambda path: plain)
    assert storage._is_link(str(target)) is True
    monkeypatch.setattr(storage.os.path, "islink", lambda path: False)
    assert storage._is_link(str(target)) is False
    monkeypatch.setattr(storage.os, "lstat", lambda path: types.SimpleNamespace(st_file_attributes=0x400))
    assert storage._is_link(str(target)) is True


def test_addons_off_does_not_ask_about_a_program_folder_that_does_not_exist(resources, monkeypatch, tmp_path):  # noqa: F811
    missing = str(tmp_path / "no_such_program_folder")
    monkeypatch.setattr(config, "FROZEN", True)
    monkeypatch.setattr(storage, "resource_root", lambda: missing)
    asked = []

    def folder_check(path):
        asked.append(path)
        return not os.path.exists(path)
    addons.use_folder_check(folder_check)
    try:
        assert addons.addons_off() is None
    finally:
        addons.use_folder_check(None)
    assert missing not in asked


# --- database._looks_secret (HA11 names) ----------------------------------------------------------------------------

@pytest.mark.parametrize("column", [
    "acctno",                                    # the word on its own (not covered by a run or a pair)
    "myacctnum", "mycardnum", "myclientkey", "myconsumerkey", "myauthkey",    # a run inside a longer single word
    "account_num_id", "acct_num_id", "acc_no_id", "acc_num_id", "routing_num_id",   # a number pair keeps its id refused
    "acctno_id", "accno_id", "accnum_id", "cardnum_id",      # an id of a value that is the secret
    "account_numbers_id",                        # the plural of the number word is still the number
])
def test_these_names_are_still_refused(column):
    assert database._looks_secret(column)


def test_an_id_after_a_number_word_is_allowed_unless_the_two_words_before_it_are_a_secret_pair():
    """Owner 2026-11-18: names ending in id are allowed; only an id of an account or card number etc. is refused."""
    assert not database._looks_secret("password_number_id")
    assert not database._looks_secret("invoice_number_id")
