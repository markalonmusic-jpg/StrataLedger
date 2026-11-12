"""accounts.py: creating and maintaining the chart of accounts (decisions A3, C1, C2, C3)."""
import sqlite3

import pytest

from modules.services import accounts
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)


@pytest.fixture
def ctx(world):
    """A user with account.manage + ledger.view in PARENT (settings row present)."""
    world.settings("PARENT", require_separate_approver=0)
    user = world.user("acct")
    world.role("PARENT", "ACCT", ["account.manage", "ledger.view"])
    world.grant(user, "PARENT", "ACCT")
    return world.ctx(user, "PARENT")


def row(world, account_id):
    return world.rows("PARENT", "SELECT * FROM account WHERE account_id = ?", (account_id,))[0]


def post_to(world, account_id):
    """Put a posted journal line on the account."""
    from tests import ledger_helpers as lh
    with world._company("PARENT") as c:
        period = lh.ensure_period(c, "2026-03-15")
        other = lh.make_account(c, "9999")
        entry = c.execute("INSERT INTO journal_entry (entry_date, period_id, created_by) "
                          "VALUES ('2026-03-15', ?, 1) RETURNING entry_id", (period,)).fetchone()[0]
        c.execute("INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, ?, 100, 0)",
                  (entry, account_id))
        c.execute("INSERT INTO journal_line (entry_id, account_id, debit_cents, credit_cents) VALUES (?, ?, 0, 100)",
                  (entry, other))
        lh.post(c, entry)


# --- Creating ---------------------------------------------------------------------------------

def test_create_account_defaults_normal_balance_from_the_type(world, ctx):
    asset = accounts.create_account(ctx, "1010", "Checking", "Asset")
    revenue = accounts.create_account(ctx, "4010", "Sales", "Revenue")
    assert row(world, asset)["normal_balance"] == "D" and row(world, revenue)["normal_balance"] == "C"
    assert row(world, asset)["is_postable"] == 1 and row(world, asset)["is_active"] == 1


def test_contra_account_may_differ_from_its_type(world, ctx):
    contra = accounts.create_account(ctx, "1590", "Accumulated Depreciation", "Asset", normal_balance="C")
    assert row(world, contra)["normal_balance"] == "C"


@pytest.mark.parametrize("code", ["100", "123456789", "10a0", "1 010", ""])
def test_account_numbers_are_4_to_8_digits(ctx, code):
    with pytest.raises(ValidationError):
        accounts.create_account(ctx, code, "Bad", "Asset")


def test_8_digit_number_is_fine_and_duplicates_are_refused(ctx):
    accounts.create_account(ctx, "10100000", "Long", "Asset")
    with pytest.raises(ValidationError):
        accounts.create_account(ctx, "10100000", "Again", "Asset")


def test_bad_inputs_are_refused(ctx):
    for kwargs in ({"name": " "}, {"type_name": "Cash"}, {"normal_balance": "X"}, {"control_type": "Sales tax"}):
        args = {"code": "1020", "name": "X", "type_name": "Asset", **kwargs}
        with pytest.raises(ValidationError):
            accounts.create_account(ctx, args.pop("code"), args.pop("name"), args.pop("type_name"), **args)


def test_control_type_accepts_the_allowed_list_only(world, ctx):
    account = accounts.create_account(ctx, "1110", "AR", "Asset", control_type="AR")
    assert row(world, account)["control_type"] == "AR"


def test_child_inherits_type_rules_and_makes_its_parent_a_header(world, ctx):
    parent = accounts.create_account(ctx, "1000", "Cash", "Asset")
    child = accounts.create_account(ctx, "1010", "Checking", "Asset", parent_id=parent)
    assert row(world, parent)["is_postable"] == 0        # C2: an account with children takes no postings
    assert row(world, child)["parent_id"] == parent
    with pytest.raises(ValidationError):
        accounts.create_account(ctx, "1020", "Wrong type", "Liability", parent_id=parent)


def test_parent_with_posted_entries_cannot_get_a_child(world, ctx):
    parent = accounts.create_account(ctx, "1000", "Cash", "Asset")
    post_to(world, parent)
    with pytest.raises(ValidationError):
        accounts.create_account(ctx, "1010", "Checking", "Asset", parent_id=parent)
    assert row(world, parent)["is_postable"] == 1


def test_four_levels_allowed_five_refused(ctx):
    l1 = accounts.create_account(ctx, "1000", "L1", "Asset")
    l2 = accounts.create_account(ctx, "1100", "L2", "Asset", parent_id=l1)
    l3 = accounts.create_account(ctx, "1110", "L3", "Asset", parent_id=l2)
    l4 = accounts.create_account(ctx, "1111", "L4", "Asset", parent_id=l3)
    with pytest.raises(ValidationError):
        accounts.create_account(ctx, "1112", "L5", "Asset", parent_id=l4)


def test_inactive_or_missing_parent_is_refused(ctx):
    parent = accounts.create_account(ctx, "1000", "Cash", "Asset")
    accounts.deactivate_account(ctx, parent)
    with pytest.raises(ValidationError):
        accounts.create_account(ctx, "1010", "Checking", "Asset", parent_id=parent)
    with pytest.raises(NotFoundError):
        accounts.create_account(ctx, "1011", "Checking", "Asset", parent_id=9999)


def test_create_is_audited(world, ctx):
    account = accounts.create_account(ctx, "1010", "Checking", "Asset")
    log = world.rows("PARENT", "SELECT * FROM audit_log WHERE table_name = 'account' AND record_id = ?", (account,))
    assert [r["action"] for r in log] == ["Insert"] and log[0]["user_id"] == ctx.user_id


# --- Number suggestion (C1) ------------------------------------------------------------------

def test_suggestions_for_top_level_accounts_follow_the_type(ctx):
    assert accounts.suggest_account_number(ctx, "Asset") == "1000"
    assert accounts.suggest_account_number(ctx, "Liability") == "2000"
    assert accounts.suggest_account_number(ctx, "Equity") == "3000"
    assert accounts.suggest_account_number(ctx, "Revenue") == "4000"
    assert accounts.suggest_account_number(ctx, "Expense") == "5000"


def test_suggestions_skip_used_numbers_and_step_from_the_parent(ctx):
    parent = accounts.create_account(ctx, "1000", "Cash", "Asset")
    assert accounts.suggest_account_number(ctx, "Asset") == "1100"
    assert accounts.suggest_account_number(ctx, "Asset", parent_id=parent) == "1010"
    accounts.create_account(ctx, "1010", "Checking", "Asset", parent_id=parent)
    accounts.create_account(ctx, "1020", "Savings", "Asset", parent_id=parent)
    assert accounts.suggest_account_number(ctx, "Asset", parent_id=parent) == "1030"


def test_suggestion_keeps_the_parents_digit_count(ctx):
    parent = accounts.create_account(ctx, "10000000", "Cash", "Asset")
    assert accounts.suggest_account_number(ctx, "Asset", parent_id=parent) == "10000010"


# --- Maintaining -----------------------------------------------------------------------------

def test_rename_is_logged_and_allowed_after_posting(world, ctx):
    account = accounts.create_account(ctx, "1010", "Checking", "Asset")
    post_to(world, account)
    accounts.rename_account(ctx, account, "Operating Checking")
    assert row(world, account)["name"] == "Operating Checking"
    assert any(r["action"] == "Update" for r in world.rows(
        "PARENT", "SELECT * FROM audit_log WHERE table_name = 'account' AND record_id = ?", (account,)))
    with pytest.raises(ValidationError):
        accounts.rename_account(ctx, account, " ")


def test_renumber_needs_the_settings_permission_and_a_free_number(world, ctx):
    account = accounts.create_account(ctx, "1010", "Checking", "Asset")
    accounts.create_account(ctx, "1020", "Savings", "Asset")
    with pytest.raises(PermissionDeniedError):          # account.manage alone is not enough (C3: Admin)
        accounts.renumber_account(ctx, account, "1015")
    admin = world.user("boss")
    world.role("PARENT", "BOSS", ["account.manage", "ledger.view", "company.settings"])
    world.grant(admin, "PARENT", "BOSS")
    actx = world.ctx(admin, "PARENT")
    accounts.renumber_account(actx, account, "1015")
    assert row(world, account)["code"] == "1015"
    for bad in ("1020", "12", "abcd"):
        with pytest.raises(ValidationError):
            accounts.renumber_account(actx, account, bad)


def test_renumber_is_still_allowed_after_posting(world, ctx):
    account = accounts.create_account(ctx, "1010", "Checking", "Asset")
    post_to(world, account)
    admin = world.user("boss")
    world.role("PARENT", "BOSS", ["account.manage", "company.settings"])
    world.grant(admin, "PARENT", "BOSS")
    accounts.renumber_account(world.ctx(admin, "PARENT"), account, "1015")
    assert row(world, account)["code"] == "1015"


def test_contra_toggle_works_before_posting_and_is_locked_after(world, ctx):
    account = accounts.create_account(ctx, "1590", "Accum Depr", "Asset")
    accounts.set_normal_balance(ctx, account, "C")
    assert row(world, account)["normal_balance"] == "C"
    post_to(world, account)
    with pytest.raises(ValidationError):
        accounts.set_normal_balance(ctx, account, "D")
    with pytest.raises(sqlite3.IntegrityError):       # the database backstop agrees
        with world._company("PARENT") as c:
            c.execute("UPDATE account SET normal_balance = 'D' WHERE account_id = ?", (account,))


def test_set_postable_refuses_accounts_with_children(world, ctx):
    parent = accounts.create_account(ctx, "1000", "Cash", "Asset")
    accounts.create_account(ctx, "1010", "Checking", "Asset", parent_id=parent)
    with pytest.raises(ValidationError):
        accounts.set_postable(ctx, parent, True)
    leaf = accounts.create_account(ctx, "1020", "Savings", "Asset")
    accounts.set_postable(ctx, leaf, False)
    assert row(world, leaf)["is_postable"] == 0


def test_deactivate_refuses_a_system_account(world, ctx):
    account = accounts.create_account(ctx, "1110", "AR", "Asset", control_type="AR")
    with world._company("PARENT") as c:
        c.execute("UPDATE company_settings SET ar_acct_id = ? WHERE id = 1", (account,))
    with pytest.raises(ValidationError):
        accounts.deactivate_account(ctx, account)
    other = accounts.create_account(ctx, "1120", "Misc", "Asset")
    accounts.deactivate_account(ctx, other)
    assert row(world, other)["is_active"] == 0
    accounts.reactivate_account(ctx, other)
    assert row(world, other)["is_active"] == 1


def test_list_accounts_returns_the_chart(ctx):
    parent = accounts.create_account(ctx, "1000", "Cash", "Asset")
    accounts.create_account(ctx, "1010", "Checking", "Asset", parent_id=parent)
    listed = accounts.list_accounts(ctx)
    assert [a["code"] for a in listed] == ["1000", "1010"]
    assert listed[1]["parent_code"] == "1000" and listed[0]["type"] == "Asset"


# --- Permissions ---------------------------------------------------------------------------

def test_writes_need_account_manage_and_reads_need_ledger_view(world):
    reader = world.user("reader")
    world.role("PARENT", "R", ["ledger.view"])
    world.grant(reader, "PARENT", "R")
    rctx = world.ctx(reader, "PARENT")
    assert accounts.list_accounts(rctx) == []
    with pytest.raises(PermissionDeniedError):
        accounts.create_account(rctx, "1010", "Checking", "Asset")
    nobody = world.user("nobody")
    world.role("PARENT", "N", ["period.view"])
    world.grant(nobody, "PARENT", "N")
    with pytest.raises(PermissionDeniedError):
        accounts.list_accounts(world.ctx(nobody, "PARENT"))


def test_agent_origin_cannot_change_the_chart(world, ctx):
    agent = world.ctx(ctx.user_id, "PARENT", origin="Agent")
    with pytest.raises(PermissionDeniedError):
        accounts.create_account(agent, "1010", "Checking", "Asset")
