import dataclasses

import pytest

from modules.services.context import ORIGINS, ServiceContext
from modules.services.errors import ValidationError


def make(**overrides):
    values = dict(user_id=1, company_id=1, origin="Human", company_db_path="c.db", master_db_path="m.db")
    values.update(overrides)
    return ServiceContext(**values)


def test_origins_are_the_four_documented_values():
    assert set(ORIGINS) == {"Human", "Agent", "Import", "System"}


@pytest.mark.parametrize("origin", ["Human", "Agent", "Import", "System"])
def test_valid_origin_accepted(origin):
    assert make(origin=origin).origin == origin


@pytest.mark.parametrize("origin", ["human", "Robot", "", None])
def test_invalid_origin_rejected(origin):
    with pytest.raises(ValidationError):
        make(origin=origin)


def test_agent_run_id_is_optional():
    assert make().agent_run_id is None
    assert make(origin="Agent", agent_run_id=7).agent_run_id == 7


def test_role_is_not_carried_on_the_context():
    # authorize() reads the role fresh from the master on every call.
    assert "role_code" not in {f.name for f in dataclasses.fields(ServiceContext)}
    with pytest.raises(TypeError):
        make(role_code="Admin")


def test_database_paths_are_required_and_stored_as_text():
    from pathlib import Path
    ctx = make(company_db_path=Path("c.db"), master_db_path=Path("m.db"))
    assert (ctx.company_db_path, ctx.master_db_path) == ("c.db", "m.db")
    with pytest.raises(TypeError):
        ServiceContext(user_id=1, company_id=1, origin="Human")


def test_context_is_frozen():
    ctx = make()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.user_id = 2
