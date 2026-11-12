"""bank_accounts.py: routing and account numbers, masked without view.bank_details (decision C4)."""
import pytest

from modules.services import accounts, bank_accounts
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)

ROUTING, NUMBER = "021000021", "123456789012"


@pytest.fixture
def manager(world):
    world.settings("PARENT", require_separate_approver=0)
    user = world.user("banker")
    world.role("PARENT", "BK", ["account.manage", "ledger.view", "view.bank_details"])
    world.grant(user, "PARENT", "BK")
    return world.ctx(user, "PARENT")


@pytest.fixture
def checking(world, manager):
    return accounts.create_account(manager, "1010", "Checking", "Asset")


@pytest.fixture
def plain(world):
    user = world.user("plain")
    world.role("PARENT", "PL", ["account.manage", "ledger.view"])
    world.grant(user, "PARENT", "PL")
    return world.ctx(user, "PARENT")


def test_set_and_read_back_in_full_with_view_bank_details(world, manager, checking):
    bank_accounts.set_bank_details(manager, checking, bank_name="First Bank", routing_number=ROUTING,
                                   account_number=NUMBER)
    details = bank_accounts.get_bank_details(manager, checking)
    assert details == {"account_id": checking, "bank_name": "First Bank", "routing_number": ROUTING,
                       "account_number": NUMBER, "account_last4": "9012", "masked": False}


def test_masked_without_view_bank_details(world, manager, checking, plain):
    bank_accounts.set_bank_details(manager, checking, bank_name="First Bank", routing_number=ROUTING,
                                   account_number=NUMBER)
    shown = bank_accounts.get_bank_details(plain, checking)
    assert shown["masked"] is True
    assert shown["routing_number"] == "*****0021" and shown["account_number"] == "********9012"
    assert ROUTING not in str(shown) and NUMBER not in str(shown)


def test_an_agent_only_ever_sees_the_masked_form(world, manager, checking):
    bank_accounts.set_bank_details(manager, checking, bank_name="B", routing_number=ROUTING, account_number=NUMBER)
    agent = world.ctx(manager.user_id, "PARENT", origin="Agent")
    shown = bank_accounts.get_bank_details(agent, checking)
    assert shown["masked"] is True and NUMBER not in str(shown)
    with pytest.raises(PermissionDeniedError):
        bank_accounts.set_bank_details(agent, checking, bank_name="B", routing_number=ROUTING, account_number=NUMBER)


def test_full_numbers_never_reach_the_audit_log(world, manager, checking):
    bank_accounts.set_bank_details(manager, checking, bank_name="First", routing_number=ROUTING, account_number=NUMBER)
    bank_accounts.set_bank_details(manager, checking, bank_name="Second", routing_number="111000025",
                                   account_number="99887766554433")
    everything = " ".join(str(r) for r in world.rows("PARENT", "SELECT * FROM audit_log"))
    for secret in (ROUTING, NUMBER, "111000025", "99887766554433"):
        assert secret not in everything
    logged = world.rows("PARENT", "SELECT * FROM audit_log WHERE table_name = 'bank_account' ORDER BY log_id")
    assert [r["action"] for r in logged] == ["Insert", "Update"]
    assert "9012" in logged[0]["new_value"] and "4433" in logged[1]["new_value"]


def test_update_replaces_and_one_row_per_account(world, manager, checking):
    bank_accounts.set_bank_details(manager, checking, bank_name="A", routing_number=ROUTING, account_number=NUMBER)
    bank_accounts.set_bank_details(manager, checking, bank_name="B", routing_number=ROUTING, account_number="55556666")
    rows = world.rows("PARENT", "SELECT * FROM bank_account")
    assert len(rows) == 1 and rows[0]["bank_name"] == "B" and rows[0]["account_last4"] == "6666"


@pytest.mark.parametrize("routing,number", [("12345", NUMBER), ("12345678a", NUMBER), (ROUTING, "12"),
                                            (ROUTING, "12-34-56"), (ROUTING, "1" * 18)])
def test_numbers_are_validated(manager, checking, routing, number):
    with pytest.raises(ValidationError):
        bank_accounts.set_bank_details(manager, checking, bank_name="B", routing_number=routing,
                                       account_number=number)


def test_missing_account_and_missing_details(manager, checking):
    with pytest.raises(NotFoundError):
        bank_accounts.set_bank_details(manager, 9999, bank_name="B", routing_number=ROUTING, account_number=NUMBER)
    assert bank_accounts.get_bank_details(manager, checking) is None


def test_only_asset_accounts_can_hold_bank_details(manager):
    liability = accounts.create_account(manager, "2010", "Card", "Liability")
    # A credit card is a liability account; it may carry details too.
    bank_accounts.set_bank_details(manager, liability, bank_name="Card Co", routing_number=ROUTING,
                                   account_number=NUMBER)
    revenue = accounts.create_account(manager, "4010", "Sales", "Revenue")
    with pytest.raises(ValidationError):
        bank_accounts.set_bank_details(manager, revenue, bank_name="B", routing_number=ROUTING, account_number=NUMBER)


def test_permissions(world, checking, plain):
    nobody = world.user("nobody")
    world.role("PARENT", "NB", ["period.view"])
    world.grant(nobody, "PARENT", "NB")
    nctx = world.ctx(nobody, "PARENT")
    with pytest.raises(PermissionDeniedError):
        bank_accounts.get_bank_details(nctx, checking)
    with pytest.raises(PermissionDeniedError):
        bank_accounts.set_bank_details(nctx, checking, bank_name="B", routing_number=ROUTING, account_number=NUMBER)
    reader = world.user("reader")
    world.role("PARENT", "RD", ["ledger.view"])
    world.grant(reader, "PARENT", "RD")
    with pytest.raises(PermissionDeniedError):
        bank_accounts.set_bank_details(world.ctx(reader, "PARENT"), checking, bank_name="B",
                                       routing_number=ROUTING, account_number=NUMBER)
