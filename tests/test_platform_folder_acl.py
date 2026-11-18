"""HA8 (owner 2026-11-18): the program folder's permissions, read in the platform module (P3).

Add-ons turn off when a non-admin principal can change RESOURCE_DIR or RESOURCE_DIR\\addons: an allow entry with
write, modify or create rights for Users, Authenticated Users, Everyone or Interactive, or for the user's own SID
when the process is not elevated. An elevated administrator on a properly installed folder (Administrators,
SYSTEM and TrustedInstaller may write; Users only read) keeps add-ons. Inheritable entries count (they reach the
add-on files); deny entries are not subtracted; an empty (NULL) DACL or an ACL that cannot be read counts as open.
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


def ace(sid, mask, ace_type=ps.ACCESS_ALLOWED, flags=0):
    return SimpleNamespace(type=ace_type, flags=flags, mask=mask, sid=sid)


def acl(*entries, owner=TRUSTED_INSTALLER, dacl_present=True):
    return SimpleNamespace(owner=owner, entries=list(entries) if dacl_present else None)


PROGRAM_FILES = acl(ace(TRUSTED_INSTALLER, FULL), ace(SYSTEM, FULL), ace(ADMINS, FULL), ace(USERS, READ_EXECUTE),
                    ace("S-1-3-0", GENERIC_ALL, flags=0x0B),                # CREATOR OWNER, inherit only
                    ace("S-1-15-2-1", READ_EXECUTE))                        # ALL APPLICATION PACKAGES


def test_the_non_admin_groups():
    assert set(ps.NON_ADMIN_GROUP_SIDS) == {USERS, AUTH_USERS, EVERYONE, INTERACTIVE}


@pytest.mark.parametrize("elevated", [True, False])
def test_an_admin_only_folder_keeps_addons(elevated):
    assert ps.non_admin_writers(PROGRAM_FILES, USER, elevated) == []


@pytest.mark.parametrize("sid", [USERS, AUTH_USERS, EVERYONE, INTERACTIVE])
@pytest.mark.parametrize("mask", [FULL, MODIFY, GENERIC_ALL, GENERIC_WRITE, 0x2, 0x4, 0x40, 0x10000, 0x40000,
                                  0x80000])
def test_a_loose_entry_for_a_non_admin_group_turns_addons_off(sid, mask):
    loose = acl(*PROGRAM_FILES.entries, ace(sid, mask))
    assert ps.non_admin_writers(loose, USER, elevated=True) == [sid]


def test_an_inherit_only_entry_counts_because_it_reaches_the_addon_files():
    loose = acl(*PROGRAM_FILES.entries, ace(USERS, MODIFY, flags=INHERIT_ONLY_FILES))
    assert ps.non_admin_writers(loose, USER, elevated=True) == [USERS]


def test_the_users_own_sid_counts_only_when_not_elevated():
    mine = acl(*PROGRAM_FILES.entries, ace(USER, FULL))
    assert ps.non_admin_writers(mine, USER, elevated=False) == [USER]
    assert ps.non_admin_writers(mine, USER, elevated=True) == []


def test_owning_the_folder_counts_when_not_elevated():
    """An owner can always rewrite the folder's permissions, so owning it is a change right."""
    owned = acl(*PROGRAM_FILES.entries, owner=USER)
    assert ps.non_admin_writers(owned, USER, elevated=False) == [USER]
    assert ps.non_admin_writers(owned, USER, elevated=True) == []
    assert ps.non_admin_writers(acl(*PROGRAM_FILES.entries, owner=USERS), USER, elevated=True) == [USERS]


def test_read_only_and_deny_entries_do_not_count_and_deny_does_not_cancel_an_allow():
    assert ps.non_admin_writers(acl(ace(EVERYONE, READ_EXECUTE), ace(USERS, FULL, ace_type=ps.ACCESS_DENIED)),
                                USER, False) == []
    both = acl(ace(USERS, FULL, ace_type=ps.ACCESS_DENIED), ace(USERS, MODIFY))
    assert ps.non_admin_writers(both, USER, True) == [USERS]


def test_a_null_dacl_is_open_to_everyone():
    assert ps.non_admin_writers(acl(dacl_present=False), USER, elevated=True) == [EVERYONE]


def test_folder_open_to_non_admins_uses_the_readers_and_fails_closed(tmp_path, caplog):
    loose = acl(ace(USERS, MODIFY))
    assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=lambda p: loose,
                                        token_reader=lambda: (USER, True)) is True
    assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=lambda p: PROGRAM_FILES,
                                        token_reader=lambda: (USER, True)) is False

    def broken(path):
        raise OSError(5, "Access is denied")
    assert ps.folder_open_to_non_admins(str(tmp_path), acl_reader=broken, token_reader=lambda: (USER, True)) is True
    assert any("OSError" in r.getMessage() for r in caplog.records)


@pytest.mark.skipif(not ps.IS_WINDOWS, reason="reads a real Windows ACL")
def test_the_real_readers_on_a_folder_this_user_made(tmp_path):
    """tmp_path is under the user's profile: owned by this user, who has full control of it."""
    user_sid, elevated = ps.current_token()
    assert user_sid.startswith("S-1-5-") and isinstance(elevated, bool)
    folder = ps.read_folder_acl(str(tmp_path))
    assert folder.entries and all(isinstance(e.mask, int) and e.sid.startswith("S-1-") for e in folder.entries)
    assert any(e.sid == user_sid and e.mask & ps.CHANGE_RIGHTS for e in folder.entries)
    if not elevated:
        assert ps.folder_open_to_non_admins(str(tmp_path)) is True


@pytest.mark.skipif(not ps.IS_WINDOWS or not os.path.isdir(r"C:\Program Files"), reason="reads a real Windows ACL")
def test_the_real_program_files_folder_is_admin_only():
    assert ps.folder_open_to_non_admins(r"C:\Program Files") is False


@pytest.mark.skipif(not ps.IS_WINDOWS, reason="reads a real Windows ACL")
def test_the_real_reader_refuses_a_missing_folder(tmp_path):
    with pytest.raises(OSError):
        ps.read_folder_acl(str(tmp_path / "missing"))
