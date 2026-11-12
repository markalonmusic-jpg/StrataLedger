"""The chart of accounts: creating and maintaining accounts (decisions A3, C1, C2, C3).

* Numbers have 4 to 8 digits and are suggested from the parent and the type (C1).
* An account that has child accounts cannot receive postings, at any level (C2): adding a child turns
  a parent into a header (refused if the parent already has posted entries). At most 4 levels.
* A name can always change. A number can change (Admin, logged) unless an active mapping or preset
  refers to it by text (C3). Type, parent, control type and normal balance lock after the first
  posting; the baseline trigger is the backstop for that.
* Normal balance defaults from the account type; a contra account may differ (A3).

Every change is audit-logged by the baseline triggers. Writers authorize before opening their
transaction (rule 10).
"""
from modules.services import chart_templates
from modules.services.authz import authorize
from modules.services.errors import NotFoundError, ValidationError
from modules.services.tx import read_connection, write_transaction

MANAGE = "account.manage"
VIEW = "ledger.view"
RENUMBER_ALSO = "company.settings"        # C3: numbers are editable by an Admin
MAX_LEVELS = chart_templates.MAX_LEVELS
TYPE_BASE = {"Asset": 1000, "Liability": 2000, "Equity": 3000, "Revenue": 4000, "Expense": 5000}
NORMAL_BALANCE = {"Asset": "D", "Liability": "C", "Equity": "C", "Revenue": "C", "Expense": "D"}


# --- Helpers -------------------------------------------------------------------------------------

def _check_code(code):
    if not isinstance(code, str) or not (code.isascii() and code.isdigit() and 4 <= len(code) <= 8):
        raise ValidationError("An account number has 4 to 8 digits")


def _check_name(name):
    name = (name or "").strip()
    if not name:
        raise ValidationError("Enter a name for the account")
    return name


def _account(conn, account_id):
    row = conn.execute(
        "SELECT a.*, t.name AS type_name FROM account AS a JOIN account_type AS t ON t.type_id = a.type_id "
        "WHERE a.account_id = ?", (account_id,)).fetchone()
    if row is None:
        raise NotFoundError("That account no longer exists")
    return row


def _depth(conn, account_id):
    return conn.execute(
        "WITH RECURSIVE up(id, parent, depth) AS ("
        "  SELECT account_id, parent_id, 1 FROM account WHERE account_id = ? "
        "  UNION ALL SELECT a.account_id, a.parent_id, up.depth + 1 FROM account AS a JOIN up ON a.account_id = up.parent) "
        "SELECT MAX(depth) FROM up", (account_id,)).fetchone()[0]


def _has_posted(conn, account_id):
    return conn.execute(
        "SELECT 1 FROM journal_line AS l JOIN journal_entry AS e ON e.entry_id = l.entry_id "
        "WHERE l.account_id = ? AND e.is_posted = 1 LIMIT 1", (account_id,)).fetchone() is not None


def _has_children(conn, account_id):
    return conn.execute("SELECT 1 FROM account WHERE parent_id = ? LIMIT 1", (account_id,)).fetchone() is not None


def _type_id(conn, type_name):
    row = conn.execute("SELECT type_id FROM account_type WHERE name = ?", (type_name,)).fetchone()
    if row is None:
        raise ValidationError(f"'{type_name}' is not an account type ({', '.join(chart_templates.ACCOUNT_TYPES)})")
    return row[0]


def _references_by_text(conn, code):
    """Active mappings or presets that refer to this account number by text (C3).

    Those tables arrive with the import and report steps; until then nothing can refer to a number.
    """
    return []


def _insert(conn, *, code, name, type_name, parent_id, control_type, normal_balance, subtype, is_postable,
            is_tax_strategy_only):
    """Validate and insert one account inside the caller's transaction. Returns the account_id."""
    _check_code(code)
    name = _check_name(name)
    type_id = _type_id(conn, type_name)
    if normal_balance is None:
        normal_balance = NORMAL_BALANCE[type_name]
    if normal_balance not in ("D", "C"):
        raise ValidationError("The normal balance must be D (debit) or C (credit)")
    if control_type is not None and control_type not in chart_templates.CONTROL_TYPES:
        raise ValidationError(f"'{control_type}' is not a control type")
    if conn.execute("SELECT 1 FROM account WHERE code = ?", (code,)).fetchone():
        raise ValidationError(f"The account number {code} is already used")
    if parent_id is not None:
        parent = _account(conn, parent_id)
        if not parent["is_active"]:
            raise ValidationError("The parent account is inactive")
        if parent["type_name"] != type_name:
            raise ValidationError(f"A {type_name} account cannot sit under a {parent['type_name']} account")
        if _depth(conn, parent_id) + 1 > MAX_LEVELS:
            raise ValidationError(f"The chart can have at most {MAX_LEVELS} levels")
        if parent["is_postable"]:
            if _has_posted(conn, parent_id):
                raise ValidationError(
                    f"Account {parent['code']} already has posted entries, so it cannot become a parent")
            conn.execute("UPDATE account SET is_postable = 0 WHERE account_id = ?", (parent_id,))
    return conn.execute(
        "INSERT INTO account (code, name, type_id, parent_id, is_postable, control_type, normal_balance, "
        "subtype, is_tax_strategy_only) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING account_id",
        (code, name, type_id, parent_id, int(bool(is_postable)), control_type, normal_balance, subtype,
         int(bool(is_tax_strategy_only)))).fetchone()[0]


def seed_chart(conn, rows):
    """Insert the validated rows of a chart (chart_templates.parse_chart) in one go.

    Used by create_company inside its own transaction. Returns {account_number: account_id}.
    """
    ids = {}
    pending = list(rows)
    while pending:
        progressed = False
        for row in list(pending):
            parent = row["parent_number"]
            if parent is not None and parent not in ids:
                continue
            ids[row["account_number"]] = _insert_template_row(conn, row, ids.get(parent))
            pending.remove(row)
            progressed = True
        if not progressed:
            raise ValidationError("The chart has accounts whose parents are missing")
    return ids


def _insert_template_row(conn, row, parent_id):
    return conn.execute(
        "INSERT INTO account (code, name, type_id, parent_id, is_postable, control_type, normal_balance, subtype) "
        "VALUES (?, ?, (SELECT type_id FROM account_type WHERE name = ?), ?, ?, ?, ?, ?) RETURNING account_id",
        (row["account_number"], row["name"], row["account_type"], parent_id, row["is_postable"],
         row["control_type"], row["normal_balance"], row["subtype"])).fetchone()[0]


# --- Reads ---------------------------------------------------------------------------------------

def list_accounts(context):
    """The chart as a list of dicts, sorted by number."""
    authorize(context, VIEW, record_type="account")
    conn = read_connection(context.company_db_path)
    try:
        rows = conn.execute(
            "SELECT a.account_id, a.code, a.name, t.name AS type, a.parent_id, p.code AS parent_code, "
            "a.is_postable, a.is_active, a.control_type, a.normal_balance, a.subtype, a.is_tax_strategy_only "
            "FROM account AS a JOIN account_type AS t ON t.type_id = a.type_id "
            "LEFT JOIN account AS p ON p.account_id = a.parent_id ORDER BY a.code").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def suggest_account_number(context, type_name, parent_id=None):
    """The next free number: step 10 under a parent, step 100 among top-level accounts of the type (C1)."""
    authorize(context, MANAGE, record_type="account")
    conn = read_connection(context.company_db_path)
    try:
        used = {r[0] for r in conn.execute("SELECT code FROM account")}
        if parent_id is not None:
            parent = _account(conn, parent_id)
            width, step = len(parent["code"]), 10
            siblings = [int(r[0]) for r in conn.execute("SELECT code FROM account WHERE parent_id = ?", (parent_id,))]
            candidate = max(siblings + [int(parent["code"])]) + step
        else:
            if type_name not in TYPE_BASE:
                raise ValidationError(f"'{type_name}' is not an account type")
            top = [int(r[0]) for r in conn.execute(
                "SELECT a.code FROM account AS a JOIN account_type AS t ON t.type_id = a.type_id "
                "WHERE a.parent_id IS NULL AND t.name = ?", (type_name,))]
            step = 100
            width = max(4, len(str(max(top)))) if top else 4
            candidate = TYPE_BASE[type_name] if not top else max(top) + step
    finally:
        conn.close()
    while str(candidate).zfill(width) in used:
        candidate += step
    if len(str(candidate)) > (width if parent_id is not None else 8):
        raise ValidationError("There is no free number left there; choose one by hand")
    return str(candidate).zfill(width)


# --- Writes --------------------------------------------------------------------------------------

def create_account(context, code, name, type_name, *, parent_id=None, control_type=None, normal_balance=None,
                   subtype=None, is_postable=True, is_tax_strategy_only=False):
    """Create an account. Returns its account_id."""
    authorize(context, MANAGE, record_type="account")
    _check_code(code)
    _check_name(name)
    with write_transaction(context.company_db_path, context) as conn:
        return _insert(conn, code=code, name=name, type_name=type_name, parent_id=parent_id,
                       control_type=control_type, normal_balance=normal_balance, subtype=subtype,
                       is_postable=is_postable, is_tax_strategy_only=is_tax_strategy_only)


def rename_account(context, account_id, name):
    """Change an account's name (always allowed, logged)."""
    authorize(context, MANAGE, record_type="account", record_id=account_id)
    name = _check_name(name)
    with write_transaction(context.company_db_path, context) as conn:
        _account(conn, account_id)
        conn.execute("UPDATE account SET name = ? WHERE account_id = ?", (name, account_id))


def renumber_account(context, account_id, new_code):
    """Change an account's number (Admin, logged; refused while a mapping or preset refers to it by text)."""
    authorize(context, MANAGE, record_type="account", record_id=account_id)
    authorize(context, RENUMBER_ALSO, record_type="account", record_id=account_id)
    _check_code(new_code)
    with write_transaction(context.company_db_path, context) as conn:
        account = _account(conn, account_id)
        if account["code"] == new_code:
            return
        if conn.execute("SELECT 1 FROM account WHERE code = ?", (new_code,)).fetchone():
            raise ValidationError(f"The account number {new_code} is already used")
        references = _references_by_text(conn, account["code"])
        if references:
            raise ValidationError("A saved mapping or report preset still uses this number: " + ", ".join(references))
        conn.execute("UPDATE account SET code = ? WHERE account_id = ?", (new_code, account_id))


def set_normal_balance(context, account_id, normal_balance):
    """The contra-account toggle (A3): allowed until the account has a posted entry."""
    authorize(context, MANAGE, record_type="account", record_id=account_id)
    if normal_balance not in ("D", "C"):
        raise ValidationError("The normal balance must be D (debit) or C (credit)")
    with write_transaction(context.company_db_path, context) as conn:
        account = _account(conn, account_id)
        if account["normal_balance"] == normal_balance:
            return
        if _has_posted(conn, account_id):
            raise ValidationError("This account already has posted entries, so its normal balance is locked")
        conn.execute("UPDATE account SET normal_balance = ? WHERE account_id = ?", (normal_balance, account_id))


def set_postable(context, account_id, is_postable):
    """Allow or stop postings to a leaf account. An account with child accounts is never postable (C2)."""
    authorize(context, MANAGE, record_type="account", record_id=account_id)
    with write_transaction(context.company_db_path, context) as conn:
        _account(conn, account_id)
        if is_postable and _has_children(conn, account_id):
            raise ValidationError("This account has accounts under it, so it cannot receive postings")
        conn.execute("UPDATE account SET is_postable = ? WHERE account_id = ?", (int(bool(is_postable)), account_id))


def deactivate_account(context, account_id):
    """Hide an account from new entries. Refused for an account the company uses as a system account."""
    authorize(context, MANAGE, record_type="account", record_id=account_id)
    with write_transaction(context.company_db_path, context) as conn:
        _account(conn, account_id)
        settings = conn.execute("SELECT * FROM company_settings WHERE id = 1").fetchone()
        if settings is not None:
            for role in chart_templates.SYSTEM_ROLES:
                if settings[chart_templates.settings_column(role)] == account_id:
                    raise ValidationError(
                        f"This account is the company's {role.replace('_', ' ')} account; choose another first")
        conn.execute("UPDATE account SET is_active = 0 WHERE account_id = ?", (account_id,))


def reactivate_account(context, account_id):
    authorize(context, MANAGE, record_type="account", record_id=account_id)
    with write_transaction(context.company_db_path, context) as conn:
        _account(conn, account_id)
        conn.execute("UPDATE account SET is_active = 1 WHERE account_id = ?", (account_id,))
