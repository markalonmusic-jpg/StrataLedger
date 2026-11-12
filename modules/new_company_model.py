"""The New Company wizard without any screen code (decision S5).

Holds the four steps' answers, their defaults (from the country), the checks that run before "Next", what is
sent to `companies.create_company`, and the plain-language wording of errors. The view in
views_new_company.py only draws widgets and calls these functions, so everything here is testable without Tk.

The four steps:
  1. Company details: legal name, display name, code, country, tax ID, optional parent company.
  2. Fiscal year: start month, first fiscal year, date format, time zone.
  3. Chart of accounts: a built-in template, the parent's chart (subsidiaries), or your own CSV.
  4. Approvals: "require a different user to approve" (off by default).
"""
from dataclasses import dataclass

from modules.services import chart_templates, companies, company_settings, periods
from modules.services.csv_table import CsvError
from modules.services.errors import (
    InstallationError, NotFoundError, PermissionDeniedError, ServiceError, ValidationError)

STEP_TITLES = ("Company details", "Fiscal year", "Chart of accounts", "Approvals")
COUNTRY_CHOICES = [("US", "United States"), ("PH", "Philippines")]
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
DATE_FORMAT_CHOICES = list(company_settings.DATE_FORMATS)
_CHART_LABELS = {
    "copy": "Copy my parent company's chart, roles and settings",
    "construction": "Construction: job costing, retainage and work in progress",
    "general": "General: services and software",
    "csv": "Import my own chart from a CSV file",
}


@dataclass
class Draft:
    legal_name: str = ""
    display_name: str = ""
    code: str = ""
    code_edited: bool = False
    country: str = "US"
    currency: str = "USD"
    tax_id: str = ""
    parent_company_id: object = None
    start_month: object = 1
    first_year: str = ""
    date_format: str = "MM/DD/YYYY"
    timezone: str = "America/Los_Angeles"
    chart_source: str = "construction"
    chart_csv_text: str = ""
    chart_csv_name: str = ""
    require_separate_approver: bool = False


def new_draft(current_year):
    draft = Draft(first_year=str(current_year))
    set_country(draft, "US")
    return draft


def set_country(draft, country):
    """Switching country resets currency, time zone and date format to that country's defaults (S5)."""
    defaults = company_settings.country_defaults(country)
    draft.country = country
    draft.currency = defaults["currency"]
    draft.timezone = defaults["timezone"]
    draft.date_format = defaults["date_format"]


def set_name(draft, name):
    """The code is suggested from the name until the user edits the code."""
    draft.legal_name = name
    if not draft.code_edited:
        draft.code = companies.company_code_from_name(name) if name.strip() else ""


def set_code(draft, code):
    draft.code = (code or "").strip().upper()
    draft.code_edited = True


def timezone_choices(country):
    return company_settings.timezones_for(country)


def chart_choices(has_parent):
    """[(key, label)] for step 3. 'copy' is offered first when a parent company is chosen (S7)."""
    keys = [t["key"] for t in chart_templates.list_templates()] + ["csv"]
    if has_parent:
        keys.insert(0, "copy")
    return [(key, _CHART_LABELS.get(key, key.title())) for key in keys]


# --- Checks ---------------------------------------------------------------------------------------

def _as_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


_DATE_PATTERNS = {"MM/DD/YYYY": "%m/%d/%Y", "DD/MM/YYYY": "%d/%m/%Y", "YYYY-MM-DD": "%Y-%m-%d"}


def format_date(day, date_format):
    return day.strftime(_DATE_PATTERNS[date_format])


def year_preview(draft):
    """'FY2027 runs from 07/01/2026 to 06/30/2027.' in the chosen date format, or '' if the inputs are not valid."""
    year, month = _as_int(draft.first_year), _as_int(draft.start_month)
    if year is None or month is None or not 1900 <= year <= 2200 or not 1 <= month <= 12 \
            or draft.date_format not in DATE_FORMAT_CHOICES:
        return ""
    start, end = periods.fiscal_year_bounds(month, year)
    return (f"{periods.year_name(end)} runs from {format_date(start, draft.date_format)} "
            f"to {format_date(end, draft.date_format)}.")


def _sentence(text):
    text = str(text).strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def validate_step(draft, index):
    """Plain-language problems with one step's answers; an empty list means 'Next' may proceed."""
    problems = []
    if index == 0:
        if not draft.legal_name.strip():
            problems.append("Enter the company's legal name.")
        try:
            companies.check_company_code(draft.code)
        except ValidationError as error:
            problems.append(_sentence(error))
    elif index == 1:
        year, month = _as_int(draft.first_year), _as_int(draft.start_month)
        if year is None or not 1900 <= year <= 2200 or len(str(draft.first_year).strip()) != 4:
            problems.append("Enter the first fiscal year as four digits, such as 2027.")
        if month is None or not 1 <= month <= 12:
            problems.append("Choose the month the fiscal year starts.")
        if draft.date_format not in DATE_FORMAT_CHOICES:
            problems.append("Choose a date format.")
        if draft.timezone not in timezone_choices(draft.country):
            problems.append("Choose one of the listed time zones.")
    elif index == 2:
        problems += _chart_problems(draft)
    elif index == 3:
        pass
    else:
        raise ValueError(f"There is no step {index}")
    return problems


def _chart_problems(draft):
    allowed = [key for key, _ in chart_choices(draft.parent_company_id is not None)]
    if draft.chart_source not in allowed:
        return ["Choose how to set up the chart of accounts."]
    if draft.chart_source != "csv":
        return []
    if not draft.chart_csv_text.strip():
        return ["Choose the CSV file that holds your chart of accounts."]
    try:
        chart_templates.parse_chart(draft.chart_csv_text)
    except CsvError as error:
        shown = "; ".join(CsvError._describe(e) for e in error.errors[:3])
        more = f" and {len(error.errors) - 3} more" if len(error.errors) > 3 else ""
        return [f"The chart file has problems: {shown}{more}. Fix the file and choose it again."]
    return []


def validate_all(draft):
    """[(step index, message)] across every step."""
    return [(index, message) for index in range(len(STEP_TITLES)) for message in validate_step(draft, index)]


# --- To and from the service --------------------------------------------------------------------------

def create_kwargs(draft):
    """The keyword arguments for companies.create_company (the session is passed separately)."""
    source = draft.chart_source
    return {
        "legal_name": draft.legal_name.strip(),
        "display_name": draft.display_name.strip() or None,
        "code": draft.code.strip().upper(),
        "tax_id": draft.tax_id.strip(),
        "country": draft.country,
        "timezone": draft.timezone,
        "date_format": draft.date_format,
        "fiscal_year_start_month": _as_int(draft.start_month),
        "first_fiscal_year": _as_int(draft.first_year),
        "template": None if source in ("csv", "copy") else source,
        "chart_csv": draft.chart_csv_text if source == "csv" else None,
        "parent_company_id": draft.parent_company_id,
        "require_separate_approver": bool(draft.require_separate_approver),
    }


def explain_error(error):
    """(dialog title, message) for an exception: what happened and what to do next. No codes or tracebacks."""
    if isinstance(error, PermissionDeniedError):
        return "Not allowed", ("You do not have permission to create a company here. Sign in as the Master, or ask "
                               "the Master to create it. Nothing was created.")
    if isinstance(error, InstallationError):
        return "Setup problem", _sentence(error)
    if isinstance(error, CsvError):
        return "Chart file problem", (f"{_sentence(error)} Fix the file, choose it again and press Create. "
                                      "Nothing was created.")
    if isinstance(error, NotFoundError):
        return "Not found", f"{_sentence(error)} Go back and choose again. Nothing was created."
    if isinstance(error, ValidationError):
        text = _sentence(error)
        advice = "Go back and choose a different one." if "already" in text.lower() \
            else "Go back, correct it and try again."
        return "Please check this", f"{text} {advice} Nothing was created."
    if isinstance(error, ServiceError):
        return "Cannot create the company", f"{_sentence(error)} Nothing was created."
    return "Something went wrong", ("The company was not created and nothing was saved. Try again. If this keeps "
                                    "happening, send the log file to support.")
