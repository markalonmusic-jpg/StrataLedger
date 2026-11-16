"""Invoice numbering (decision R6, the gapless registered series rule), Phase 2.5 step 7.

`sequences.next_invoice_number` runs in the caller's write transaction. Moved here from
tests/test_service_rules_pending.py: "the numbering service assigns the next number" (a strict xfail).
"""
import pytest

from modules.services import sequences
from modules.services.errors import ValidationError
from modules.services.tx import write_transaction
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_posting import ctx_for, env, keyed  # noqa: F401


def next_number(env, document_type="Invoice", issue_date="2026-03-10"):
    context = ctx_for(env, "System")
    with write_transaction(context.company_db_path, context) as conn:
        return sequences.next_invoice_number(conn, context, document_type, issue_date=issue_date)


def series(env):
    return env.rows("PARENT", "SELECT * FROM invoice_series ORDER BY series_id")


@pytest.mark.parametrize("document_type, prefix", [("Invoice", "INV-"), ("Credit Memo", "CM-")])
def test_the_first_number_creates_the_default_series(env, document_type, prefix):
    result = next_number(env, document_type)
    rows = series(env)
    assert len(rows) == 1
    assert (rows[0]["document_type"], rows[0]["prefix"], rows[0]["registered_from"]) == (document_type, prefix, None)
    assert result == {"series_id": rows[0]["series_id"], "sequence_number": 1, "invoice_number": f"{prefix}000001"}


def test_numbers_are_gapless_and_per_document_type(env):
    assert [next_number(env)["invoice_number"] for _ in range(3)] == ["INV-000001", "INV-000002", "INV-000003"]
    assert next_number(env, "Credit Memo")["invoice_number"] == "CM-000001"
    assert next_number(env)["sequence_number"] == 4


def test_an_existing_active_series_is_used(env):
    with env._company("PARENT") as c:
        inactive = lh.make_series(c, "Invoice", "OLD-", active=0)
        active = lh.make_series(c, "Invoice", "SI-")
    result = next_number(env)
    assert (result["series_id"], result["invoice_number"]) == (active, "SI-000001")
    assert result["series_id"] != inactive


def test_the_philippines_add_on_needs_a_registered_series(env):
    with env._company("PARENT") as c:
        c.execute("INSERT INTO company_addon (addon_key, enabled) VALUES ('ph_tax', 1)")
    with pytest.raises(ValidationError, match="Register an invoice series"):
        next_number(env)
    assert series(env) == []


def test_a_disabled_philippines_add_on_still_gets_the_default(env):
    with env._company("PARENT") as c:
        c.execute("INSERT INTO company_addon (addon_key, enabled) VALUES ('ph_tax', 0)")
    assert next_number(env)["invoice_number"] == "INV-000001"


def test_a_registered_series_stops_at_its_last_number(env):
    with env._company("PARENT") as c:
        lh.make_series(c, "Invoice", "SI-", registered=(51, 52))
    assert [next_number(env)["sequence_number"] for _ in range(2)] == [51, 52]
    with pytest.raises(ValidationError, match="used up"):
        next_number(env)


def test_a_registered_series_past_its_valid_until_date_is_refused(env):
    """The document's issue date counts (the leave-Draft trigger checks the same), not the day it is sent."""
    with env._company("PARENT") as c:
        lh.make_series(c, "Invoice", "SI-", registered=(1, 100), valid_until="2026-03-10")
    assert next_number(env, issue_date="2026-03-10")["sequence_number"] == 1
    with pytest.raises(ValidationError, match="expired"):
        next_number(env, issue_date="2026-03-11")


def test_under_the_philippines_add_on_an_unregistered_series_is_refused(env):
    with env._company("PARENT") as c:
        c.execute("INSERT INTO company_addon (addon_key, enabled) VALUES ('ph_tax', 1)")
        lh.make_series(c, "Invoice", "SI-")
    with pytest.raises(ValidationError, match="not registered"):
        next_number(env)
    with env._company("PARENT") as c:
        lh.make_series(c, "Invoice", "BIR-", registered=(1, 500))
    assert next_number(env)["invoice_number"] == "BIR-000001"


def test_a_used_up_or_expired_older_series_gives_way_to_the_next_active_one(env):
    with env._company("PARENT") as c:
        lh.make_series(c, "Invoice", "OLD-", registered=(1, 1))
        lh.make_series(c, "Invoice", "EXP-", registered=(1, 9), valid_until="2026-01-31")
        lh.make_series(c, "Invoice", "NEW-")
    assert next_number(env)["invoice_number"] == "OLD-000001"
    assert next_number(env)["invoice_number"] == "NEW-000001"


@pytest.mark.parametrize("issue_date", ["10/03/2026", None, 20260310])
def test_the_issue_date_must_be_an_iso_date(env, issue_date):
    with pytest.raises(ValidationError, match="issue date"):
        next_number(env, issue_date=issue_date)


def test_an_unknown_document_type_is_refused(env):
    with pytest.raises(ValidationError, match="Invoice or Credit Memo"):
        next_number(env, "Bill")


def test_with_no_usable_series_the_oldest_ones_problem_is_reported(env):
    """Mutation check: the first problem found is kept, so the message names the oldest series."""
    with env._company("PARENT") as c:
        lh.make_series(c, "Invoice", "OLD-", registered=(1, 1))
        c.execute("UPDATE invoice_series SET last_number = 1 WHERE prefix = 'OLD-'")
        lh.make_series(c, "Invoice", "EXP-", registered=(1, 9), valid_until="2026-01-31")
    with pytest.raises(ValidationError, match="OLD- series is used up"):
        next_number(env)

