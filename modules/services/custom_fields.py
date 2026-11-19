"""Custom fields: company-defined fields on contacts, invoices, bills and projects (Phase 2.7 STOP C).

FR1 as amended by CODE_CHANGES_NEEDED.md section 27 (owner 2026-11-17): no field packs, no seeded fields, no cap.
The baseline tables are custom_field_def and custom_field_value (one typed column per type; triggers match the
column to the field's type). Owner answers 2026-11-18 (docs/next_step.md, STOP C):

* Defining (define, update, deactivate, reactivate) needs fields.manage: Admin and the Master only, never the
  Agent. A field is never removed: "Remove" makes it inactive and its values stay; the audit log is the history.
* Labels are unique per record type, ignoring case (inactive fields count), checked inside the write transaction.
  field_key comes from the label when the field is defined and never changes.
* A Contact field whose name looks like a bank number is refused (deferred check 2; RP1 bank_payee_id).
* A value is readable exactly when its record is: Invoice ar.view, Bill ap.view, Project project.view (project
  scope). Contact by kind: a customer needs ar.view or either manager, a vendor ap.view or either manager, a
  contact that is both or neither either view code or either manager. The Agent reads only through view codes.
* A value is set with the record's own edit check: Contact customer.manage or vendor.manage (contacts.py's
  update_contact; the loose "either manager" is listed for the 2.9 access-model replan), Invoice invoice.create,
  Bill bill.create, Project project.manage (project scope). The Agent never sets values.
* A posted invoice or bill may have its values changed (they are in no ledger seal or chain); refused while
  Lock documents after posting is on, or when its entry's period is closed. The audit triggers keep the old
  and new values. Area locks (fiscal_period_lock) wait for the rule 8 editable-documents work.
* Estimate: refused until an estimate service exists (the baseline has no estimate read code; listed for 2.9).
"""
import json
import math
import re
import unicodedata
from datetime import date

import config
from modules.services import permissions
from modules.services.authz import authorize, deny, is_allowed
from modules.services.errors import NotFoundError, PeriodClosedError, ValidationError
from modules.services.tx import read_connection, write_transaction

__all__ = ["RECORD_TYPES", "DATA_TYPES", "list_fields", "define_field", "update_field", "deactivate_field",
           "reactivate_field", "set_value", "get_values"]

MANAGE = "fields.manage"
RECORD_TYPES = ("Contact", "Invoice", "Bill", "Project")          # the baseline also allows Estimate (refused)
DATA_TYPES = ("Text", "Number", "Money", "Date", "Yes/No", "Choice")
LABEL_MAX = 80
TEXT_MAX = 2000
VALUE_COLUMNS = ("value_text", "value_number", "value_cents", "value_date", "value_bool")
_COLUMN = {"Text": "value_text", "Choice": "value_text", "Number": "value_number", "Money": "value_cents",
           "Date": "value_date", "Yes/No": "value_bool"}

ESTIMATE_REFUSED = f"Custom fields on estimates are not available yet in {config.APP_NAME}."
BANK_REFUSED = (f"{config.APP_NAME} does not keep bank account numbers in custom fields; add the contact's bank "
                "details as a bank payee instead.")
AGENT_CANNOT_SET = "The AI assistant cannot change custom field values; a person must do this."

# What may read a record's values, and what may set them (owner 2026-11-18). Order matters: the first code is
# the one a denial names.
_READ = {"Invoice": ("ar.view",), "Bill": ("ap.view",), "Project": ("project.view",)}
_CONTACT_READ = {(True, False): ("ar.view", "customer.manage", "vendor.manage"),
                 (False, True): ("ap.view", "customer.manage", "vendor.manage")}
_CONTACT_READ_ANY = ("ar.view", "ap.view", "customer.manage", "vendor.manage")
_WRITE = {"Contact": ("customer.manage", "vendor.manage"), "Invoice": ("invoice.create",),
          "Bill": ("bill.create",), "Project": ("project.manage",)}

# Deferred check 2: names that look like a bank number, on Contact fields only.
_BANK_WORDS = frozenset({"routing", "iban", "swift", "bic", "aba", "bsb", "ifsc", "clabe", "accountnumber",
                         "accountno", "accountnum", "acctnumber", "acctno", "acctnum", "bankaccount", "banknumber",
                         "sortcode", "routingnumber"})
_BANK_PAIRS = frozenset({("account", "number"), ("account", "no"), ("account", "num"), ("acct", "number"),
                         ("acct", "no"), ("acct", "num"), ("bank", "account"), ("bank", "number"),
                         ("sort", "code")})


# --- Checks (pure) ------------------------------------------------------------------------

def _record_type(record_type):
    if record_type == "Estimate":
        raise ValidationError(ESTIMATE_REFUSED)
    if record_type not in RECORD_TYPES:
        raise ValidationError(f"Custom fields can be added to {', '.join(RECORD_TYPES)}; "
                              f"{record_type!r} is not one of them")
    return record_type


def _record_id(record_id):
    if type(record_id) is not int:
        raise ValidationError("The record id must be a whole number")
    return record_id


def _label(label):
    if not isinstance(label, str) or not label.strip():
        raise ValidationError("Enter a name for the field")
    label = label.strip()
    if len(label) > LABEL_MAX:
        raise ValidationError(f"A field name can be at most {LABEL_MAX} characters")
    return label


def _flag(value, what):
    if not isinstance(value, bool):
        raise ValidationError(f"{what} must be yes or no")
    return value


def _choices(choices):
    if not isinstance(choices, (list, tuple)) or not choices:
        raise ValidationError("A pick-list field needs at least one choice")
    cleaned, seen = [], set()
    for choice in choices:
        if not isinstance(choice, str) or not choice.strip():
            raise ValidationError("Each choice needs a name")
        choice = choice.strip()
        if len(choice) > LABEL_MAX:
            raise ValidationError(f"A choice can be at most {LABEL_MAX} characters")
        if choice.casefold() in seen:
            raise ValidationError(f"The choice {choice!r} is listed twice")
        seen.add(choice.casefold())
        cleaned.append(choice)
    return cleaned


def _ascii(text):
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _key_base(label):
    key = re.sub(r"[^a-z0-9]+", "_", _ascii(label).lower()).strip("_")
    if not key:
        return "field"
    return f"f_{key}" if key[0].isdigit() else key


def _looks_like_bank_number(label):
    words = re.findall(r"[a-z0-9]+", _ascii(label).lower().replace("#", " number "))
    if _BANK_WORDS.intersection(words) or "".join(words) in _BANK_WORDS:
        return True
    return any(pair in _BANK_PAIRS for pair in zip(words, words[1:]))


def _clean_value(field, value):
    """The value to store for this field (None clears it), or ValidationError with what to do."""
    if value is None:
        return None
    kind, label = field["data_type"], field["label"]
    if kind == "Text":
        if not isinstance(value, str):
            raise ValidationError(f"{label} takes text")
        value = value.strip()
        if len(value) > TEXT_MAX:
            raise ValidationError(f"{label} can be at most {TEXT_MAX} characters")
        return value or None
    if kind == "Number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValidationError(f"{label} takes a number")
        return value
    if kind == "Money":
        if type(value) is not int:     # integer cents only (rule 1): floats, text and yes/no are refused
            raise ValidationError(f"{label} takes an amount in whole cents")
        return value
    if kind == "Date":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", value):
            raise ValidationError(f"{label} takes a date like 2026-01-31")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValidationError(f"{value} is not a real date; check the day and month") from None
        return value
    if kind == "Yes/No":
        if not isinstance(value, bool):
            raise ValidationError(f"{label} takes yes or no")
        return int(value)
    # Choice: an active choice, matched without case and stored as the choice is written.
    active = [c["value"] for c in _parse_choices(field["choices_json"]) if c["active"]]
    if isinstance(value, str):
        for choice in active:
            if choice.casefold() == value.strip().casefold():
                return choice
    raise ValidationError(f"Choose one of the choices for {label}: {', '.join(active)}")


def _parse_choices(choices_json):
    return json.loads(choices_json) if choices_json else []


def _dump_choices(choices):
    return json.dumps(choices, ensure_ascii=False, separators=(",", ":")) if choices is not None else None


# --- Permissions ------------------------------------------------------------------------

def _pick(context, codes, project_id=None):
    """The code to authorize: the first one the user holds, else the first (whose denial is then logged).

    A non-raising choice only; the caller then calls authorize() itself (rule 10). The Agent is offered only the
    codes it may use, so it reads through view codes alone.
    """
    if context.origin == "Agent":
        codes = tuple(c for c in codes if c in permissions.AGENT_ALLOWED) or codes
    for code in codes:
        if is_allowed(context, code, project_id):
            return code
    return codes[0]


def _contact_read_codes(row):
    if row is None:
        return _CONTACT_READ_ANY
    return _CONTACT_READ.get((bool(row["is_customer"]), bool(row["is_vendor"])), _CONTACT_READ_ANY)


def _load_record(conn, record_type, record_id):
    if record_type == "Contact":
        return conn.execute("SELECT contact_id, is_customer, is_vendor FROM contact WHERE contact_id = ?",
                            (record_id,)).fetchone()
    if record_type == "Project":
        return conn.execute("SELECT project_id FROM project WHERE project_id = ?", (record_id,)).fetchone()
    return conn.execute("SELECT invoice_id, entry_id FROM invoice WHERE invoice_id = ? AND invoice_type = ?",
                        (record_id, record_type)).fetchone()


def _read_record(context, record_type, record_id):
    conn = read_connection(context.company_db_path)
    try:
        return _load_record(conn, record_type, record_id)
    finally:
        conn.close()


def _not_found(record_type):
    return NotFoundError(f"That {record_type.lower()} does not exist")


# --- Reading ------------------------------------------------------------------------------

def _field_dict(row):
    choices = row["choices_json"]
    return {"field_id": row["field_id"], "record_type": row["record_type"], "field_key": row["field_key"],
            "label": row["label"], "data_type": row["data_type"],
            "choices": _parse_choices(choices) if choices else None, "is_required": bool(row["is_required"]),
            "is_active": bool(row["is_active"]), "sort_order": row["sort_order"]}


_DEF_COLUMNS = ("d.field_id, d.record_type, d.field_key, d.label, d.data_type, d.choices_json, d.is_required, "
                "d.is_active, d.sort_order")


def _field(conn, field_id):
    row = conn.execute(f"SELECT {_DEF_COLUMNS} FROM custom_field_def AS d WHERE d.field_id = ?",
                       (field_id,)).fetchone()
    if row is None:
        raise NotFoundError("That custom field does not exist")
    if row["record_type"] == "Estimate":
        raise ValidationError(ESTIMATE_REFUSED)
    return row


def list_fields(context, record_type, *, include_inactive=False, project_id=None):
    """The record type's fields in order. Needs a code that reads that record type, or fields.manage.

    project_id: for Project fields under project scope ('Assigned'), the project the list is for.
    """
    record_type = _record_type(record_type)
    readers = _CONTACT_READ_ANY if record_type == "Contact" else _READ[record_type]
    scope = project_id if record_type == "Project" else None
    code = _pick(context, readers + (MANAGE,), scope)
    authorize(context, code, scope, record_type="custom_field_def")
    conn = read_connection(context.company_db_path)
    try:
        rows = conn.execute(
            f"SELECT {_DEF_COLUMNS} FROM custom_field_def AS d WHERE d.record_type = ? "
            "AND (d.is_active = 1 OR ?) ORDER BY d.sort_order, d.field_id",
            (record_type, int(bool(include_inactive)))).fetchall()
    finally:
        conn.close()
    return [_field_dict(r) for r in rows]


def get_values(context, record_type, record_id):
    """The record's values: every active field (None when unset) and every inactive field that holds a value.

    Each item: field_key, label, data_type, is_active, value (money in cents, Yes/No as bool).
    """
    record_type = _record_type(record_type)
    record_id = _record_id(record_id)
    record = _read_record(context, record_type, record_id)
    readers = _contact_read_codes(record) if record_type == "Contact" else _READ[record_type]
    scope = record_id if record_type == "Project" else None
    authorize(context, _pick(context, readers, scope), scope, record_type=record_type.lower(), record_id=record_id)
    if record is None:
        raise _not_found(record_type)
    conn = read_connection(context.company_db_path)
    try:
        rows = conn.execute(
            "SELECT d.field_key, d.label, d.data_type, d.is_active, v.value_text, v.value_number, v.value_cents, "
            "v.value_date, v.value_bool FROM custom_field_def AS d LEFT JOIN custom_field_value AS v "
            "ON v.field_id = d.field_id AND v.record_id = ? WHERE d.record_type = ? "
            "ORDER BY d.sort_order, d.field_id", (record_id, record_type)).fetchall()
    finally:
        conn.close()
    values = []
    for r in rows:
        value = r[_COLUMN[r["data_type"]]]
        if r["data_type"] == "Yes/No" and value is not None:
            value = bool(value)
        if r["is_active"] or value is not None:
            values.append({"field_key": r["field_key"], "label": r["label"], "data_type": r["data_type"],
                           "is_active": bool(r["is_active"]), "value": value})
    return values


# --- Defining fields ----------------------------------------------------------------------

def _label_taken(conn, record_type, label, except_id=None):
    folded = label.casefold()
    for row in conn.execute("SELECT field_id, label FROM custom_field_def WHERE record_type = ?", (record_type,)):
        if row["field_id"] != except_id and row["label"].casefold() == folded:
            raise ValidationError(f"A {record_type.lower()} field named {row['label']!r} already exists; "
                                  "choose another name")


def _new_key(conn, record_type, label):
    taken = {r["field_key"] for r in conn.execute("SELECT field_key FROM custom_field_def WHERE record_type = ?",
                                                  (record_type,))}
    base = key = _key_base(label)
    number = 2
    while key in taken:
        key, number = f"{base}_{number}", number + 1
    return key


def define_field(context, record_type, *, label, data_type, choices=None, is_required=False):
    """Add a field to a record type. Returns the field (as list_fields gives it)."""
    record_type = _record_type(record_type)
    label = _label(label)
    if data_type not in DATA_TYPES:
        raise ValidationError(f"Choose a field type: {', '.join(DATA_TYPES)}")
    if data_type == "Choice":
        choices = [{"value": c, "active": True} for c in _choices(choices)]
    elif choices is not None:
        raise ValidationError("Only a pick-list field has choices")
    is_required = _flag(is_required, "Required")
    if record_type == "Contact" and _looks_like_bank_number(label):
        raise ValidationError(BANK_REFUSED)
    authorize(context, MANAGE, record_type="custom_field_def")
    with write_transaction(context.company_db_path, context) as conn:
        _label_taken(conn, record_type, label)
        key = _new_key(conn, record_type, label)
        last = conn.execute("SELECT MAX(sort_order) FROM custom_field_def WHERE record_type = ?",
                            (record_type,)).fetchone()[0]
        field_id = conn.execute(
            "INSERT INTO custom_field_def (record_type, field_key, label, data_type, choices_json, is_required, "
            "is_active, sort_order) VALUES (?, ?, ?, ?, ?, ?, 1, ?) RETURNING field_id",
            (record_type, key, label, data_type, _dump_choices(choices), int(is_required),
             (last or 0) + 1)).fetchone()[0]
        return _field_dict(_field(conn, field_id))


def _has_values(conn, field_id):
    return conn.execute(
        "SELECT 1 FROM custom_field_value WHERE field_id = ? AND (value_text IS NOT NULL OR value_number IS NOT "
        "NULL OR value_cents IS NOT NULL OR value_date IS NOT NULL OR value_bool IS NOT NULL)",
        (field_id,)).fetchone() is not None


def _merged_choices(conn, field_id, current, wanted):
    """The wanted choices, active, then each current choice left out but still used, inactive (never removed).

    A wanted choice that matches a current one without case keeps the current spelling (values store it).
    """
    spelled = {c["value"].casefold(): c["value"] for c in current}
    merged = [{"value": spelled.get(w.casefold(), w), "active": True} for w in wanted]
    listed = {c["value"].casefold() for c in merged}
    for choice in current:
        if choice["value"].casefold() in listed:
            continue
        used = conn.execute("SELECT 1 FROM custom_field_value WHERE field_id = ? AND value_text = ?",
                            (field_id, choice["value"])).fetchone()
        if used:
            merged.append({"value": choice["value"], "active": False})
    return merged


def update_field(context, field_id, *, label=None, sort_order=None, is_required=None, choices=None,
                 data_type=None):
    """Change a field's name, order, required flag, choices or type. The field_key never changes.

    The type changes only while no value is stored. A choice that is left out but used stays, inactive.
    """
    if label is not None:
        label = _label(label)
    if sort_order is not None and type(sort_order) is not int:
        raise ValidationError("The order must be a whole number")
    if is_required is not None:
        _flag(is_required, "Required")
    if data_type is not None and data_type not in DATA_TYPES:
        raise ValidationError(f"Choose a field type: {', '.join(DATA_TYPES)}")
    wanted = _choices(choices) if choices is not None else None
    authorize(context, MANAGE, record_type="custom_field_def", record_id=field_id)
    with write_transaction(context.company_db_path, context) as conn:
        field = _field(conn, field_id)
        new_type = data_type or field["data_type"]
        if new_type != field["data_type"] and _has_values(conn, field_id):
            raise ValidationError(f"{field['label']} already has values; clear them before changing its type")
        if new_type == "Choice":
            current = _parse_choices(field["choices_json"]) if field["data_type"] == "Choice" else []
            if wanted is not None:
                new_choices = _merged_choices(conn, field_id, current, wanted)
            elif not current:
                raise ValidationError("A pick-list field needs at least one choice")
            else:
                new_choices = current
        else:
            if wanted is not None:
                raise ValidationError("Only a pick-list field has choices")
            new_choices = None
        if label is not None:
            if field["record_type"] == "Contact" and _looks_like_bank_number(label):
                raise ValidationError(BANK_REFUSED)
            _label_taken(conn, field["record_type"], label, except_id=field_id)
        conn.execute(
            "UPDATE custom_field_def SET label = ?, data_type = ?, choices_json = ?, is_required = ?, sort_order = ? "
            "WHERE field_id = ?",
            (label if label is not None else field["label"], new_type, _dump_choices(new_choices),
             int(is_required) if is_required is not None else field["is_required"],
             sort_order if sort_order is not None else field["sort_order"], field_id))
        return _field_dict(_field(conn, field_id))


def _set_active(context, field_id, active):
    authorize(context, MANAGE, record_type="custom_field_def", record_id=field_id)
    with write_transaction(context.company_db_path, context) as conn:
        _field(conn, field_id)
        conn.execute("UPDATE custom_field_def SET is_active = ? WHERE field_id = ?", (active, field_id))
        return _field_dict(_field(conn, field_id))


def deactivate_field(context, field_id):
    """Make a field inactive ("Remove"): it leaves the lists, its values stay and still read."""
    return _set_active(context, field_id, 0)


def reactivate_field(context, field_id):
    """Make an inactive field active again."""
    return _set_active(context, field_id, 1)


# --- Setting values -----------------------------------------------------------------------

def _check_posted(conn, record_type, invoice_id):
    """A posted invoice or bill: refused while Lock documents after posting is on, or in a closed period."""
    entry = conn.execute(
        "SELECT e.is_posted, p.name, p.is_closed FROM invoice AS i JOIN journal_entry AS e ON e.entry_id = i.entry_id "
        "JOIN fiscal_period AS p ON p.period_id = e.period_id WHERE i.invoice_id = ?", (invoice_id,)).fetchone()
    if entry is None or not entry["is_posted"]:
        return
    word = record_type.lower()
    settings = conn.execute("SELECT lock_documents_after_posting FROM company_settings").fetchone()
    if settings is not None and settings["lock_documents_after_posting"]:
        raise ValidationError(f"This {word} is posted and Lock documents after posting is on; an Admin can turn it "
                              "off in Company Settings > Controls")
    if entry["is_closed"]:
        raise PeriodClosedError(f"{entry['name']} is closed; reopen it to change this {word}'s custom fields")


def _store_value(conn, field, record_id, value):
    """Write a checked value (None clears every column) inside the caller's transaction."""
    columns = {c: None for c in VALUE_COLUMNS}
    if value is not None:
        columns[_COLUMN[field["data_type"]]] = value
    existing = conn.execute("SELECT value_id FROM custom_field_value WHERE field_id = ? AND record_id = ?",
                            (field["field_id"], record_id)).fetchone()
    if existing is not None:
        conn.execute(f"UPDATE custom_field_value SET {', '.join(f'{c} = ?' for c in columns)} WHERE value_id = ?",
                     (*columns.values(), existing["value_id"]))
    elif value is not None:
        conn.execute(f"INSERT INTO custom_field_value (field_id, record_id, {', '.join(columns)}) "
                     f"VALUES (?, ?, {', '.join('?' * len(columns))})", (field["field_id"], record_id, *columns.values()))


def set_value(context, record_type, record_id, field_key, value):
    """Set or clear (value None) one field's value on a record. Money is integer cents, dates are ISO."""
    record_type = _record_type(record_type)
    record_id = _record_id(record_id)
    writers = _WRITE[record_type]
    if context.origin == "Agent":
        deny(context, writers[0], record_type=record_type.lower(), record_id=record_id, message=AGENT_CANNOT_SET)
    record = _read_record(context, record_type, record_id)
    scope = record_id if record_type == "Project" else None
    authorize(context, _pick(context, writers, scope), scope, record_type=record_type.lower(), record_id=record_id)
    if record is None:
        raise _not_found(record_type)
    with write_transaction(context.company_db_path, context) as conn:
        field = conn.execute(f"SELECT {_DEF_COLUMNS} FROM custom_field_def AS d WHERE d.record_type = ? "
                             "AND d.field_key = ?", (record_type, field_key)).fetchone()
        if field is None:
            raise NotFoundError(f"There is no {record_type.lower()} field {field_key!r}")
        if not field["is_active"]:
            raise ValidationError(f"{field['label']} is inactive; reactivate it to enter new values")
        cleaned = _clean_value(field, value)
        if _load_record(conn, record_type, record_id) is None:
            raise _not_found(record_type)
        if record_type in ("Invoice", "Bill"):
            _check_posted(conn, record_type, record_id)
        _store_value(conn, field, record_id, cleaned)
