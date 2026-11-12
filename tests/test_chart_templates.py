"""chart_templates.py: loading and validating chart-of-accounts CSVs (decisions A7, C1, C2, I1)."""
import pytest

from modules.services import chart_templates as ct
from modules.services.csv_table import CsvError

HEADER = "account_number,name,parent_number,account_type,subtype,normal_balance,control_type,is_postable,system_role\n"
REQUIRED = {"ar": "1110", "ap": "2010", "sales_tax_payable": "2200", "default_bank": "1010",
            "retained_earnings": "3100", "opening_balance_equity": "3900"}


def minimal(extra="", drop=()):
    rows = [
        "1000,Assets,,Asset,Current asset,D,,0,",
        "1010,Checking,1000,Asset,Current asset,D,,1,default_bank",
        "1110,Accounts Receivable,1000,Asset,Current asset,D,AR,1,ar",
        "2000,Liabilities,,Liability,Current liability,C,,0,",
        "2010,Accounts Payable,2000,Liability,Current liability,C,AP,1,ap",
        "2200,Sales Tax Payable,2000,Liability,Current liability,C,Sales tax payable,1,sales_tax_payable",
        "3000,Equity,,Equity,Equity,C,,0,",
        "3100,Retained Earnings,3000,Equity,Equity,C,,1,retained_earnings",
        "3900,Opening Balance Equity,3000,Equity,Equity,C,,1,opening_balance_equity",
    ]
    rows = [r for r in rows if r.split(",")[0] not in drop]
    return HEADER + "\n".join(rows) + "\n" + extra


def errors_of(text):
    with pytest.raises(CsvError) as caught:
        ct.parse_chart(text)
    return caught.value.errors


def messages(text):
    return " | ".join(e.message for e in errors_of(text))


# --- The two approved templates ------------------------------------------------------------

@pytest.mark.parametrize("key,count", [("construction", 88), ("general", 72)])
def test_approved_templates_load_and_validate(key, count):
    rows = ct.load_template(key)
    assert len(rows) == count
    roles = {r["system_role"] for r in rows if r["system_role"]}
    assert set(ct.REQUIRED_ROLES) <= roles
    assert roles <= set(ct.SYSTEM_ROLES)


def test_template_list_has_the_two_templates_with_names():
    listed = {t["key"]: t["name"] for t in ct.list_templates()}
    assert listed == {"construction": "Construction", "general": "General"}


def test_unknown_template_is_not_found():
    from modules.services.errors import NotFoundError
    with pytest.raises(NotFoundError):
        ct.load_template("nope")
    with pytest.raises(NotFoundError):
        ct.load_template("../construction")


def test_every_template_control_type_is_in_the_database_check(fresh_company):
    import modules.database as database
    conn = database.get_connection(fresh_company)
    try:
        check = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'account'").fetchone()[0]
    finally:
        conn.close()
    for key in ("construction", "general"):
        for row in ct.load_template(key):
            if row["control_type"]:
                assert f"'{row['control_type']}'" in check, row["control_type"]
    assert set(ct.CONTROL_TYPES) == {t for t in ct.CONTROL_TYPES if f"'{t}'" in check}


def test_rows_are_typed_and_carry_their_file_row():
    rows = ct.parse_chart(minimal())
    first = rows[0]
    assert first["account_number"] == "1000" and first["parent_number"] is None
    assert first["is_postable"] == 0 and first["system_role"] is None and first["control_type"] is None
    assert rows[1]["parent_number"] == "1000" and rows[1]["row"] == 3


def test_minimal_chart_is_valid():
    assert len(ct.parse_chart(minimal())) == 9


# --- Each rule -------------------------------------------------------------------------------

@pytest.mark.parametrize("number", ["100", "123456789", "10a0", "10.0", ""])
def test_account_numbers_are_4_to_8_digits(number):
    assert "4 to 8 digits" in messages(minimal(f"{number},Odd,3000,Equity,Equity,C,,1,\n"))


def test_8_digit_number_is_fine():
    ct.parse_chart(minimal("30000001,Long,3000,Equity,Equity,C,,1,\n"))


def test_duplicate_numbers():
    assert "more than once" in messages(minimal("1010,Again,1000,Asset,Current asset,D,,1,\n"))


def test_missing_parent():
    assert "parent" in messages(minimal("1020,Orphan,9999,Asset,Current asset,D,,1,\n")).lower()


def test_account_with_children_cannot_be_postable():
    text = minimal("1011,Child,1010,Asset,Current asset,D,,1,\n")
    assert "cannot receive postings" in messages(text)


def test_five_levels_is_too_deep_and_four_is_fine():
    four = minimal("1100,L2,1000,Asset,Current asset,D,,0,\n1101,L3,1100,Asset,Current asset,D,,0,\n"
                   "1102,L4,1101,Asset,Current asset,D,,1,\n")
    ct.parse_chart(four)
    five = four.replace("1102,L4,1101,Asset,Current asset,D,,1,", "1102,L4,1101,Asset,Current asset,D,,0,")
    five += "1103,L5,1102,Asset,Current asset,D,,1,\n"
    assert "4 levels" in messages(five)


def test_parent_cycle_is_an_error_not_a_hang():
    text = HEADER + "1000,A,1001,Asset,x,D,,0,\n1001,B,1000,Asset,x,D,,0,\n"
    assert errors_of(text)


def test_system_role_unique_and_known():
    assert "used by more than one" in messages(minimal("1020,Second,1000,Asset,Current asset,D,,1,default_bank\n"))
    assert "not a known" in messages(minimal("1020,Odd,1000,Asset,Current asset,D,,1,made_up_role\n"))


@pytest.mark.parametrize("role", sorted(REQUIRED))
def test_each_required_role_must_be_present(role):
    text = minimal(drop={REQUIRED[role]})
    assert role in messages(text)


def test_all_missing_required_roles_are_listed_together():
    text = HEADER + "1000,Assets,,Asset,x,D,,0,\n1010,Checking,1000,Asset,x,D,,1,default_bank\n"
    found = messages(text)
    for role in ("ar", "ap", "sales_tax_payable", "retained_earnings", "opening_balance_equity"):
        assert role in found


def test_control_type_must_be_allowed():
    assert "control type" in messages(minimal("1020,Odd,1000,Asset,Current asset,D,Sales tax,1,\n")).lower()
    ct.parse_chart(minimal("1020,Ok,1000,Asset,Current asset,D,Fixed assets,1,\n"))


def test_type_normal_balance_and_postable_values():
    assert "account type" in messages(minimal("1020,Odd,1000,Cash,x,D,,1,\n")).lower()
    assert "D or C" in messages(minimal("1020,Odd,1000,Asset,x,X,,1,\n"))
    assert "0 or 1" in messages(minimal("1020,Odd,1000,Asset,x,D,,2,\n"))


def test_contra_accounts_may_differ_from_their_type():
    ct.parse_chart(minimal("1590,Accumulated Depreciation,1000,Asset,Fixed asset,C,,1,\n"))


def test_blank_name_is_an_error():
    assert "name" in messages(minimal("1020,,1000,Asset,x,D,,1,\n")).lower()


def test_every_problem_is_reported_in_one_pass_with_row_numbers():
    text = minimal("12,Short,3000,Equity,x,C,,1,\n1020,Odd,9999,Asset,x,D,,1,\n")
    rows = sorted({e.row for e in errors_of(text)})
    assert rows == [11, 12]


def test_wrong_header_is_reported():
    with pytest.raises(CsvError):
        ct.parse_chart("account_number,name\n1000,Cash\n")
