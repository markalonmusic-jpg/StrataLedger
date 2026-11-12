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


# --- now and today (decision H2) -------------------------------------------------------------

def test_now_and_today_are_given_by_the_caller():
    context = make(now="2026-11-11T21:04:05+00:00", today="2026-11-11")
    assert (context.now, context.today) == ("2026-11-11T21:04:05+00:00", "2026-11-11")


def test_context_builder_fills_now_and_today_when_omitted():
    context = make()
    assert context.now.endswith("+00:00") and "T" in context.now and len(context.now) == 25
    assert context.today == context.now[:10]


def test_today_can_differ_from_the_utc_date():
    context = make(now="2026-11-12T02:00:00+00:00", today="2026-11-11")
    assert context.today == "2026-11-11"


@pytest.mark.parametrize("now", ["yesterday", "2026-11-11", "2026-11-11 21:04:05", "2026-11-11T21:04:05", 5])
def test_bad_now_is_rejected(now):
    with pytest.raises(ValidationError):
        make(now=now)


@pytest.mark.parametrize("today", ["2026-13-01", "11/11/2026", "2026-11-11T00:00:00+00:00", 5])
def test_bad_today_is_rejected(today):
    with pytest.raises(ValidationError):
        make(today=today)


def test_replace_keeps_the_clock_and_can_change_today():
    context = make(now="2026-11-12T02:00:00+00:00", today="2026-11-12")
    moved = dataclasses.replace(context, today="2026-11-11")
    assert moved.now == context.now and moved.today == "2026-11-11"
