"""HA8 (owner 2026-11-18): the program folder's permissions, read in the platform module (P3).

Add-ons turn off when any principal other than SYSTEM, Administrators or TrustedInstaller (an allow-list, owner
answer M2) can change RESOURCE_DIR or anything under RESOURCE_DIR\addons: an allow entry with write, modify or
create rights, or owning it. The user's own account counts even when the process is elevated (M3), so the
process token is not read at all. Inheritable entries count; CREATOR OWNER and CREATOR GROUP on an inherit-only
entry are placeholders (a child gets the creator's real SID, and every child is read, M1); deny entries are not
subtracted; an empty (NULL) DACL, a missing owner or an ACL that cannot be read counts as open.
"""
import os
from types import SimpleNamespace

import pytest

from modules import platform_support as ps

USER = "S-1-5-21-1111111111-2222222222-3333333333-1001"
ADMINS, SYSTEM = "S-1-5-32-544", "S-1-5-18"
TRUSTED_INSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
USERS, AUTH_USERS, EVERYONE, INTERACTIVE = "S-1-5-32-545", "S-1-5-11", "S-1-1-0", "S-1-5-4"
READ_EXECUTE = 0x001200A9
FULL = 0x001F01FF
MODIFY = 0x001301BF
GENERIC_ALL, GENERIC_WRITE = 0x10000000, 0x40000000
INHERIT_ONLY_FILES = 0x01 | 0x08           # OBJECT_INHERIT | INHERIT_ONLY
CREATOR_OWNER, CREATOR_GROUP = "S-1-3-0", "S-1-3-1"
OTHER_PRINCIPALS = [USER, USERS, AUTH_USERS, EVERYONE, INTERACTIVE, CREATOR_OWNER, CREATOR_GROUP,
                    "S-1-5-32-547",                                    # Power Users
                    "S-1-5-32-551",                                    # Backup Operators
                    "S-1-5-19", "S-1-5-20",                            # LOCAL SERVICE, NETWORK SERVICE
                    "S-1-15-2-1",                                      # ALL APPLICATION PACKAGES
                    "S-1-5-21-1111111111-2222222222-3333333333-513",   # a domain group
                    "S-1-5-80-1111111111-2222222222-3333333333-4444444444-5555555555"]   # another service


def ace(sid, mask, ace_type=ps.ACCESS_ALLOWED, flags=0):
    return SimpleNamespace(type=ace_type, flags=flags, mask=mask, sid=sid)


def acl(*entries, owner=TRUSTED_INSTALLER, dacl_present=True):
    return SimpleNamespace(owner=owner, entries=list(entries) if dacl_present else None)


PROGRAM_FILES = acl(ace(TRUSTED_INSTALLER, FULL), ace(SYSTEM, FULL), ace(ADMINS, FULL), ace(USERS, READ_EXECUTE),
                    ace(CREATOR_OWNER, GENERIC_ALL, flags=0x0B),            # CREATOR OWNER, inherit only
                    ace("S-1-15-2-1", READ_EXECUTE))                        # ALL APPLICATION PACKAGES


def test_only_system_administrators_and_trustedinstaller_may_change_it():
    assert set(ps.ADMIN_SIDS) == {SYSTEM, ADMINS, TRUSTED_INSTALLER}


def test_an_admin_only_folder_keeps_addons():
    assert ps.non_admin_writers(PROGRAM_FILES) == []
    assert ps.non_admin_writers(acl(ace(SYSTEM, FULL), ace(ADMINS, GENERIC_ALL), owner=ADMINS)) == []
    assert ps.non_admin_writers(acl(ace(ADMINS, FULL), owner=SYSTEM)) == []


@pytest.mark.parametrize("sid", OTHER_PRINCIPALS)
@pytest.mark.parametrize("mask", [FULL, MODIFY, GENERIC_ALL, GENERIC_WRITE, 0x2, 0x4, 0x40, 0x10000, 0x40000,
                                  0x80000])
def test_any_other_principal_with_a_change_right_turns_addons_off(sid, mask):
    loose = acl(*PROGRAM_FILES.entries, ace(sid, mask))
    assert ps.non_admin_writers(loose) == [sid]


def test_an_inherit_only_entry_counts_because_it_reaches_the_addon_files():
    loose = acl(*PROGRAM_FILES.entries, ace(USERS, MODIFY, flags=INHERIT_ONLY_FILES))
    assert ps.non_admin_writers(loose) == [USERS]


@pytest.mark.parametrize("sid", [CREATOR_OWNER, CREATOR_GROUP])
def test_a_creator_placeholder_counts_only_when_it_applies_to_the_folder_itself(sid):
    """On an inherit-only entry it names no one: a child made later gets its creator's SID, and every existing
    child is read too (M1). On an entry that applies to the folder it is not a placeholder, so it counts."""
    assert ps.non_admin_writers(acl(*PROGRAM_FILES.entries, ace(sid, FULL, flags=0x0B))) == []
    assert ps.non_admin_writers(acl(*PROGRAM_FILES.entries, ace(sid, FULL, flags=0x03))) == [sid]


def test_the_users_own_sid_counts_even_when_elevated(tmp_path):
    """M3: the decision never asks whether the process is elevated."""
    mine = acl(*PROGRAM_FILES.entries, ace(USER, FULL))
    assert ps.non_admin_writers(mine) == [USER]
    assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=lambda p: mine) is True
    assert not hasattr(ps, "current_token")


@pytest.mark.parametrize("owner", [USER, USERS, EVERYONE, "S-1-5-32-547"])
def test_owning_it_counts_for_anyone_outside_the_allow_list(owner):
    """An owner can always rewrite the permissions, so owning it is a change right."""
    assert ps.non_admin_writers(acl(*PROGRAM_FILES.entries, owner=owner)) == [owner]


@pytest.mark.parametrize("owner", [None, ""])
def test_a_missing_owner_counts_as_open(owner):
    assert ps.non_admin_writers(acl(*PROGRAM_FILES.entries, owner=owner)) == ["no owner"]


def test_read_only_and_deny_entries_do_not_count_and_deny_does_not_cancel_an_allow():
    assert ps.non_admin_writers(acl(ace(EVERYONE, READ_EXECUTE), ace(USERS, FULL, ace_type=ps.ACCESS_DENIED))) == []
    both = acl(ace(USERS, FULL, ace_type=ps.ACCESS_DENIED), ace(USERS, MODIFY))
    assert ps.non_admin_writers(both) == [USERS]


@pytest.mark.parametrize("ace_type", [5, 11])        # ACCESS_ALLOWED_OBJECT, ACCESS_ALLOWED_CALLBACK_OBJECT
def test_an_allow_entry_the_reader_cannot_parse_counts_as_open(ace_type):
    """Step-reviewer L1: such entries are read with mask 0 and no SID, so they must not pass as harmless."""
    unread = acl(*PROGRAM_FILES.entries, ace("", 0, ace_type=ace_type))
    assert ps.non_admin_writers(unread) == [f"an allow entry of type {ace_type}"]


def test_a_null_dacl_is_open_to_everyone():
    assert ps.non_admin_writers(acl(dacl_present=False)) == [EVERYONE]


def test_folder_open_to_non_admins_uses_the_readers_and_fails_closed(tmp_path, caplog):
    loose = acl(ace(USERS, MODIFY))
    assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=lambda p: loose) is True
    assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=lambda p: PROGRAM_FILES) is False

    def broken(path):
        raise OSError(5, "Access is denied")
    assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=broken) is True
    assert any("OSError" in r.getMessage() for r in caplog.records)


@pytest.mark.skipif(not ps.IS_WINDOWS, reason="reads a real Windows ACL")
def test_the_real_reader_on_a_folder_and_a_file_this_user_made(tmp_path):
    """tmp_path is under the user's profile: this user has full control of it, elevated or not (M3)."""
    item = tmp_path / "addon.py"
    item.write_text("x = 1\n", encoding="utf-8")
    for path in (tmp_path, item):
        found = ps.read_folder_acl(str(path))
        assert found.entries and all(isinstance(e.mask, int) and e.sid.startswith("S-1-") for e in found.entries)
        assert found.owner.startswith("S-1-")
        assert ps.folder_open_to_non_admins(str(path)) is True


@pytest.mark.skipif(not ps.IS_WINDOWS or not os.path.isdir(r"C:\Program Files"), reason="reads a real Windows ACL")
def test_the_real_program_files_folder_is_admin_only():
    assert ps.folder_open_to_non_admins(r"C:\Program Files") is False


@pytest.mark.skipif(not ps.IS_WINDOWS, reason="reads a real Windows ACL")
def test_the_real_reader_refuses_a_missing_folder(tmp_path):
    with pytest.raises(OSError):
        ps.read_folder_acl(str(tmp_path / "missing"))
