"""Chart-of-accounts templates and chart CSVs (decisions A7, A6, C1, C2, I1).

A template is a CSV file in templates/coa/ read through storage.py and parsed by csv_table.py, the
same path "Import my own CSV" uses. Nothing here touches a database: create_company turns the
validated rows into accounts. Every problem in a file is reported at once, with its row number.

Columns: account_number, name, parent_number, account_type, subtype, normal_balance, control_type,
is_postable, system_role (the company_settings pointer the account fills).
"""
import os

from modules.services import csv_table, storage
from modules.services.csv_table import CsvError, RowError
from modules.services.errors import NotFoundError

TEMPLATE_DIR = "templates/coa"
REQUIRED_COLUMNS = ["account_number", "name", "account_type", "normal_balance", "is_postable"]
OPTIONAL_COLUMNS = ["parent_number", "subtype", "control_type", "system_role"]

ACCOUNT_TYPES = ("Asset", "Liability", "Equity", "Revenue", "Expense")
# Must equal the account.control_type CHECK in the baseline (a test compares them).
CONTROL_TYPES = (
    "AR", "AP", "Retainage receivable", "Retainage payable", "Sales tax payable", "Use tax payable",
    "Undeposited funds", "GRNI", "Inventory", "Fixed assets", "Loans",
    "Deferral", "Over/under billing", "Employee advance", "Employee material advance",
)
# The six that must exist before the first posting (decision 1.2).
REQUIRED_ROLES = ("ar", "ap", "sales_tax_payable", "default_bank", "retained_earnings", "opening_balance_equity")
# Every system role is a company_settings column named "<role>_acct_id".
SYSTEM_ROLES = REQUIRED_ROLES + (
    "undeposited_funds", "retainage_receivable", "retainage_payable", "employee_advances", "prepaid_expenses",
    "grni", "credit_card_clearing", "use_tax_payable", "unearned_revenue", "customer_deposits",
    "equipment_recovery", "inventory_adjustments", "bank_charges", "interest_income", "gain_loss_disposal",
    "interest_expense", "rounding_variance", "contract_revenue", "underbilled", "overbilled", "payroll_clearing",
)
MAX_LEVELS = 4


def settings_column(role):
    return f"{role}_acct_id"


def list_templates():
    """[{'key': 'construction', 'name': 'Construction'}, ...] for the CSV files in templates/coa/."""
    return [{"key": os.path.splitext(name)[0], "name": os.path.splitext(name)[0].replace("_", " ").title()}
            for name in storage.list_resources(TEMPLATE_DIR, ".csv")]


def load_template(key):
    """Parsed, validated rows of a built-in template."""
    if not isinstance(key, str) or not key.isidentifier():
        raise NotFoundError("That chart template does not exist")
    name = f"{key}.csv"
    if name not in storage.list_resources(TEMPLATE_DIR, ".csv"):
        raise NotFoundError("That chart template does not exist")
    return parse_chart(storage.read_resource_text(f"{TEMPLATE_DIR}/{name}"))


def parse_chart(text):
    """Parse and validate chart CSV text. Returns a list of typed account dicts or raises CsvError."""
    table = csv_table.parse_table(text, REQUIRED_COLUMNS, OPTIONAL_COLUMNS)
    rows = []
    for raw, line in zip(table.rows, table.row_numbers):
        rows.append({
            "row": line,
            "account_number": raw["account_number"],
            "name": raw["name"],
            "parent_number": raw["parent_number"] or None,
            "account_type": raw["account_type"],
            "subtype": raw["subtype"] or None,
            "normal_balance": raw["normal_balance"].upper(),
            "control_type": raw["control_type"] or None,
            "is_postable": raw["is_postable"],
            "system_role": raw["system_role"] or None,
        })
    errors = validate_chart(rows)
    if errors:
        raise CsvError(errors)
    for row in rows:
        row["is_postable"] = int(row["is_postable"])
    return rows


def _is_number(value):
    return value.isascii() and value.isdigit() and 4 <= len(value) <= 8


def validate_chart(rows):
    """Return a list of RowError (empty when the chart is valid)."""
    errors = []

    def bad(row, column, message):
        errors.append(RowError(row["row"], column, message))

    by_number, seen_roles = {}, {}
    for row in rows:
        number = row["account_number"]
        if not _is_number(number):
            bad(row, "account_number", f"'{number}' is not a number of 4 to 8 digits")
        elif number in by_number:
            bad(row, "account_number", f"The account number {number} is used more than once")
        else:
            by_number[number] = row
        if not row["name"]:
            bad(row, "name", "Every account needs a name")
        if row["account_type"] not in ACCOUNT_TYPES:
            bad(row, "account_type", f"'{row['account_type']}' is not an account type "
                                     f"({', '.join(ACCOUNT_TYPES)})")
        if row["normal_balance"] not in ("D", "C"):
            bad(row, "normal_balance", "The normal balance must be D or C")
        if row["is_postable"] not in ("0", "1"):
            bad(row, "is_postable", "is_postable must be 0 or 1")
        if row["control_type"] is not None and row["control_type"] not in CONTROL_TYPES:
            bad(row, "control_type", f"'{row['control_type']}' is not a control type")
        role = row["system_role"]
        if role is not None:
            if role not in SYSTEM_ROLES:
                bad(row, "system_role", f"'{role}' is not a known system account role")
            elif role in seen_roles:
                bad(row, "system_role", f"The role '{role}' is used by more than one account")
            else:
                seen_roles[role] = row

    children = {}
    for row in rows:
        parent = row["parent_number"]
        if parent is None:
            continue
        if parent not in by_number:
            bad(row, "parent_number", f"The parent account {parent} is not in this chart")
        else:
            children.setdefault(parent, []).append(row)

    for number, kids in children.items():
        parent_row = by_number[number]
        if parent_row["is_postable"] == "1":
            bad(parent_row, "is_postable", f"Account {number} has accounts under it, so it cannot receive postings")

    for row in rows:
        depth, cursor, trail = 1, row, {row["account_number"]}
        while cursor["parent_number"] is not None and cursor["parent_number"] in by_number:
            cursor = by_number[cursor["parent_number"]]
            if cursor["account_number"] in trail:
                bad(row, "parent_number", "The accounts form a loop")
                break
            trail.add(cursor["account_number"])
            depth += 1
        else:
            if depth > MAX_LEVELS:
                bad(row, "parent_number", f"Account {row['account_number']} is {depth} levels deep; "
                                          f"the limit is {MAX_LEVELS} levels")

    missing = [role for role in REQUIRED_ROLES if role not in seen_roles]
    if missing:
        errors.append(RowError(0, "system_role", "These required roles have no account: " + ", ".join(missing)))
    return sorted(errors, key=lambda e: (e.row, e.column or ""))
