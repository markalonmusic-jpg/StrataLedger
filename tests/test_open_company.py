"""open_company(): the only way a session gets a ServiceContext for a company."""
import sqlite3

import pytest

import modules.database as database
from modules.services import authz, companies
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)


def set_registry_path(world, company, path):
    conn = sqlite3.connect(world.master)
    conn.execute("UPDATE company_registry SET database_file_path = ? WHERE company_id = ?",
                 (str(path), world.company_id(company)))
    conn.commit()
    conn.close()


def test_open_returns_a_context_for_the_company(world):
    user_id = world.user("staff")
    world.role("PARENT", "R", ["ledger.view"])
    world.grant(user_id, "PARENT", "R")
    context = companies.open_company(world.session(user_id), world.company_id("PARENT"))
    assert (context.user_id, context.company_id, context.origin) == (user_id, world.company_id("PARENT"), "Human")
    assert context.company_db_path == str(world.path("PARENT").resolve())
    assert context.master_db_path == str(world.master)
    authz.authorize(context, "ledger.view")
    assert world.events("PARENT") == []  # a normal user's open is not an access event


def test_open_needs_access(world):
    user_id = world.user("outsider")
    with pytest.raises(PermissionDeniedError):
        companies.open_company(world.session(user_id), world.company_id("OTHER"))
    event = world.events("OTHER")[0]
    assert (event["event_type"], event["permission_code"], event["user_id"]) == ("Denied", None, user_id)


def test_open_through_inherited_access_and_deny(world):
    user_id = world.user("staff")
    world.role("PARENT", "R", ["ledger.view"])
    world.role("CHILD", "R", ["ledger.view"])
    world.grant(user_id, "PARENT", "R")
    companies.open_company(world.session(user_id), world.company_id("CHILD"))
    world.grant(user_id, "CHILD", None, mode="Deny")
    with pytest.raises(PermissionDeniedError):
        companies.open_company(world.session(user_id), world.company_id("CHILD"))


def test_open_needs_an_active_role(world):
    user_id = world.user("staff")
    world.role("PARENT", "R", ["ledger.view"], active=False)
    world.grant(user_id, "PARENT", "R")
    with pytest.raises(PermissionDeniedError):
        companies.open_company(world.session(user_id), world.company_id("PARENT"))


def test_master_open_is_logged(world):
    master = world.user("owner", master=True)
    companies.open_company(world.session(master), world.company_id("OTHER"))
    assert [(e["event_type"], e["actor_type"]) for e in world.events("OTHER")] == [("Open company", "Master")]


def test_inactive_company_opens_only_for_the_master(world):
    admin, master = world.user("admin"), world.user("owner", master=True)
    world.grant(admin, "PARENT", "Admin")
    world.set_company_active("PARENT", False)
    with pytest.raises(PermissionDeniedError):
        companies.open_company(world.session(admin), world.company_id("PARENT"))
    context = companies.open_company(world.session(master), world.company_id("PARENT"))
    authz.authorize(context, "company.backup")


def test_unknown_company(world):
    master = world.user("owner", master=True)
    with pytest.raises(NotFoundError):
        companies.open_company(world.session(master), 9999)


def test_relative_registry_path_resolves_under_the_installation_folder(world, tmp_path):
    master = world.user("owner", master=True)
    set_registry_path(world, "PARENT", "PARENT.db")  # relative to BASE_PROJECT_DIR (tmp_path here)
    context = companies.open_company(world.session(master), world.company_id("PARENT"))
    assert context.company_db_path == str((tmp_path / "PARENT.db").resolve())


@pytest.mark.parametrize("outside", ["../escape.db", "C:/Windows/evil.db"])
def test_path_outside_the_installation_folder_is_refused(world, outside):
    master = world.user("owner", master=True)
    set_registry_path(world, "PARENT", outside)
    with pytest.raises(ValidationError):
        companies.open_company(world.session(master), world.company_id("PARENT"))


def test_missing_file_is_not_created(world, tmp_path):
    master = world.user("owner", master=True)
    set_registry_path(world, "PARENT", tmp_path / "Companies" / "gone.db")
    with pytest.raises(NotFoundError):
        companies.open_company(world.session(master), world.company_id("PARENT"))
    assert not (tmp_path / "Companies" / "gone.db").exists()


def test_stale_file_is_blocked_and_left_unchanged(world):
    master = world.user("owner", master=True)
    path = world.path("PARENT")
    conn = sqlite3.connect(path)
    conn.execute("UPDATE schema_baseline SET sha256 = 'stale' WHERE id = 1")
    conn.commit()
    conn.close()
    original = path.read_bytes()
    with pytest.raises(database.SchemaUpgradeBlockedError):
        companies.open_company(world.session(master), world.company_id("PARENT"))
    assert path.read_bytes() == original


def test_authorize_rejects_a_context_whose_file_is_not_the_registered_one(world):
    master = world.user("owner", master=True)
    context = world.ctx(master, "PARENT")
    swapped = type(context)(user_id=context.user_id, company_id=context.company_id, origin="Human",
                            company_db_path=str(world.path("OTHER")), master_db_path=context.master_db_path)
    with pytest.raises(PermissionDeniedError):
        authz.authorize(swapped, "ledger.view")
    assert world.events("OTHER") == []  # nothing is written into the wrong file
