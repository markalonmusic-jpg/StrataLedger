"""Mutation gap: update_entry must store a changed manual source (Manual -> Adjustment)."""
from modules.services import ledger
from tests.authz_world import world  # noqa: F401
from tests.test_ledger_drafts import ctx, entry_row, env, two_lines  # noqa: F401  (fixtures and helpers)


def test_update_stores_a_changed_manual_source(env, ctx):
    entry_id = ledger.create_entry(ctx, entry_date="2026-03-15", lines=two_lines(env), source="Manual")
    ledger.update_entry(ctx, entry_id, source="Adjustment")
    assert entry_row(env, entry_id)["source"] == "Adjustment"
