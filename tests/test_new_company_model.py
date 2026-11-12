"""new_company_model.py: the New Company wizard's defaults, checks and plain-language errors (decision S5)."""
import pytest

from modules import new_company_model as model
from modules.services.csv_table import CsvError, RowError
from modules.services.errors import (
    InstallationError, NotFoundError, PermissionDeniedError, ServiceError, ValidationError)


def draft(**changes):
    d = model.new_draft(2027)
    for name, value in changes.items():
        setattr(d, name, value)
    return d


# --- Defaults (S5) ---------------------------------------------------------------------------------

def test_new_draft_defaults():
    d = model.new_draft(2027)
    assert (d.country, d.start_month, d.first_year, d.chart_source) == ("US", 1, "2027", "construction")
    assert (d.currency, d.timezone, d.date_format) == ("USD", "America/Los_Angeles", "MM/DD/YYYY")
    assert d.require_separate_approver is False and d.parent_company_id is None


def test_country_sets_currency_timezone_and_date_format():
    d = model.new_draft(2027)
    model.set_country(d, "PH")
    assert (d.currency, d.timezone, d.date_format) == ("PHP", "Asia/Manila", "MM/DD/YYYY")
    model.set_country(d, "US")
    assert (d.currency, d.timezone) == ("USD", "America/Los_Angeles")
    with pytest.raises(ValidationError):
        model.set_country(d, "FR")


def test_choices_per_country():
    assert model.timezone_choices("US")[0] == "America/Los_Angeles" or "America/Los_Angeles" in model.timezone_choices("US")
    assert model.timezone_choices("PH") == ["Asia/Manila"]
    assert [value for value, _ in model.COUNTRY_CHOICES] == ["US", "PH"]
    assert len(model.MONTHS) == 12 and model.MONTHS[6] == "July"
    assert [key for key, _ in model.chart_choices(has_parent=False)] == ["construction", "general", "csv"]
    assert [key for key, _ in model.chart_choices(has_parent=True)] == ["copy", "construction", "general", "csv"]


def test_code_follows_the_name_until_it_is_edited():
    d = model.new_draft(2027)
    model.set_name(d, "Acme Builders")
    assert d.code == "ACME"
    model.set_code(d, "abc9")
    assert d.code == "ABC9" and d.code_edited
    model.set_name(d, "Zeta Software")
    assert d.code == "ABC9"
    model.set_name(d, "")
    assert d.code == "ABC9"


def test_cleared_name_clears_a_suggested_code():
    d = model.new_draft(2027)
    model.set_name(d, "Acme")
    model.set_name(d, "")
    assert d.code == ""


# --- Step checks -----------------------------------------------------------------------------------

def test_step_one_checks():
    assert model.validate_step(draft(legal_name="Acme", code="ACME"), 0) == []
    messages = model.validate_step(draft(legal_name=" ", code="ACME"), 0)
    assert any("legal name" in m.lower() for m in messages)
    for code in ("", "AB", "AB CD", "CON", "ABCDEFGHIJK"):
        found = model.validate_step(draft(legal_name="Acme", code=code), 0)
        assert found and all(m.endswith(".") for m in found), code


@pytest.mark.parametrize("year,month,ok", [("2027", 1, True), ("2027", 12, True), ("", 1, False), ("27", 1, False),
                                           ("abcd", 1, False), ("1800", 1, False), ("2027", 0, False),
                                           ("2027", 13, False), ("2027", "x", False)])
def test_step_two_checks(year, month, ok):
    found = model.validate_step(draft(first_year=year, start_month=month), 1)
    assert (found == []) is ok


def test_step_two_date_format_and_timezone():
    assert model.validate_step(draft(date_format="DD-MM-YY"), 1)
    assert model.validate_step(draft(timezone="Asia/Manila"), 1)           # not a US zone
    assert model.validate_step(draft(country="PH", timezone="Asia/Manila"), 1) == []


def test_year_preview_names_the_fiscal_year_with_its_dates():
    assert model.year_preview(draft(start_month=7, first_year="2027")) == \
        "FY2027 runs from 07/01/2026 to 06/30/2027."
    assert model.year_preview(draft(start_month=1, first_year="2028", date_format="YYYY-MM-DD")) == \
        "FY2028 runs from 2028-01-01 to 2028-12-31."
    assert model.year_preview(draft(start_month=3, first_year="2028", date_format="DD/MM/YYYY")) == \
        "FY2028 runs from 01/03/2027 to 29/02/2028."
    assert model.year_preview(draft(first_year="x")) == ""


def test_step_three_template_and_csv():
    assert model.validate_step(draft(chart_source="general"), 2) == []
    assert model.validate_step(draft(chart_source="nonsense"), 2)
    assert model.validate_step(draft(chart_source="csv", chart_csv_text=""), 2)
    assert model.validate_step(draft(chart_source="copy"), 2)               # no parent chosen
    assert model.validate_step(draft(chart_source="copy", parent_company_id=3), 2) == []


def test_step_three_reports_chart_file_problems_in_plain_words():
    found = model.validate_step(draft(chart_source="csv", chart_csv_text="account_number,name\n1000,Cash\n"), 2)
    assert len(found) == 1 and "chart file" in found[0].lower() and found[0].endswith(".")


def test_step_four_has_nothing_to_check():
    assert model.validate_step(draft(require_separate_approver=True), 3) == []


def test_validate_all_lists_the_step_of_each_problem():
    d = draft(legal_name="", code="", first_year="")
    problems = model.validate_all(d)
    assert {step for step, _ in problems} == {0, 1}
    assert model.validate_all(draft(legal_name="Acme", code="ACME")) == []


def test_unknown_step_is_a_programming_error():
    with pytest.raises(ValueError):
        model.validate_step(draft(), 7)


# --- What is sent to the service ----------------------------------------------------------------------

def test_kwargs_for_a_template_company():
    d = draft(legal_name=" Acme Builders ", display_name="Acme", code="acme", tax_id="12-3456789", start_month=7,
              first_year="2027", chart_source="general", require_separate_approver=True)
    assert model.create_kwargs(d) == {
        "legal_name": "Acme Builders", "display_name": "Acme", "code": "ACME", "tax_id": "12-3456789",
        "country": "US", "timezone": "America/Los_Angeles", "date_format": "MM/DD/YYYY",
        "fiscal_year_start_month": 7, "first_fiscal_year": 2027, "template": "general", "chart_csv": None,
        "parent_company_id": None, "require_separate_approver": True}


def test_kwargs_for_csv_and_copy():
    csv = model.create_kwargs(draft(legal_name="A", code="ABC", chart_source="csv", chart_csv_text="x,y\n"))
    assert csv["template"] is None and csv["chart_csv"] == "x,y\n"
    copy = model.create_kwargs(draft(legal_name="A", code="ABC", chart_source="copy", parent_company_id=5))
    assert copy["template"] is None and copy["chart_csv"] is None and copy["parent_company_id"] == 5


# --- Errors say what to do next -------------------------------------------------------------------

@pytest.mark.parametrize("error,fragment", [
    (PermissionDeniedError("Not permitted: master"), "permission"),
    (ValidationError("The company code ACME is already used"), "different"),
    (ValidationError("Enter the company's legal name"), "correct"),
    (NotFoundError("No such company: 9"), "choose again"),
    (InstallationError("Time zone data is missing for Asia/Manila; reinstall StrataLedger."), "reinstall"),
    (CsvError([RowError(4, "system_role", "The role 'x' is not a known system account role")]), "Row 4"),
    (ServiceError("odd"), "odd"),
])
def test_service_errors_become_a_title_and_one_next_step(error, fragment):
    title, message = model.explain_error(error)
    assert title and fragment.lower() in message.lower()
    assert "Traceback" not in message and message.rstrip().endswith(".")
    assert "nothing was created" in message.lower() or isinstance(error, InstallationError)


def test_unexpected_errors_do_not_leak_details():
    title, message = model.explain_error(RuntimeError("secret internals /path/to/file.py line 3"))
    assert "secret" not in message and "file.py" not in message
    assert "log" in message.lower() and "nothing" in message.lower()
