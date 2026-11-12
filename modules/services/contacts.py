"""Contacts: customers, vendors and employees, and their automatic codes (Phase 2.6).

Codes (CLAUDE.md section 6, "Customer codes" and "Vendor codes"):
* Assigned only here, by make_customer / make_vendor (or create_contact with the flag set). The
  UI never builds a code and nothing edits one (a baseline trigger blocks it).
* The number is the `seq` of a new row in customer_number / vendor_number, inserted in the same
  write transaction that sets the code. It is never MAX+1, so two users saving at once get
  different numbers, and a number is never reused.
* customer_code = 2-letter prefix + seq (AC0001); vendor_code = 'V' + prefix + seq (VAC0001).
  The seq is zero-padded to at least 4 digits and may grow. Sort by seq, not by the code text.

Permissions: customer.manage for customer actions, vendor.manage for vendor actions; plain
contacts and employees need either. Tax IDs are masked unless the user holds view.tax_ids.
"""
import re
import unicodedata

from modules.services.authz import authorize, is_allowed
from modules.services.errors import DuplicateContactError, NotFoundError, ValidationError
from modules.services.tx import read_connection, write_transaction

__all__ = ["DuplicateContactError", "code_prefix", "format_code", "create_contact", "update_contact",
           "deactivate_contact", "make_customer", "make_vendor", "find_duplicates"]

CUSTOMER_PERMISSION = "customer.manage"
VENDOR_PERMISSION = "vendor.manage"
ARTICLES = {"the", "a", "an"}
EDITABLE_FIELDS = ("name", "bir_registered_name", "entity_type", "email", "phone", "address", "tax_id",
                   "mailing_street", "mailing_city", "mailing_state", "mailing_zip", "is_employee")
# Letters that do not decompose into a base letter plus an accent.
_SPECIAL_LETTERS = str.maketrans({"Ø": "O", "ø": "o", "Æ": "AE", "æ": "ae",
                                  "Œ": "OE", "œ": "oe", "Ł": "L", "ł": "l",
                                  "Đ": "D", "đ": "d", "ß": "ss"})


# --- Code building (pure) -----------------------------------------------------------------

def _plain(text):
    """Accents removed (NFKD, combining marks dropped)."""
    decomposed = unicodedata.normalize("NFKD", (text or "").translate(_SPECIAL_LETTERS))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def code_prefix(name):
    """First 2 letters of the name, uppercase, accents removed; always 2 characters.

    A leading The / A / An is skipped only when the next word starts with a letter.
    Digits, punctuation and non-Latin letters are ignored; the result is padded with X
    (so a name with no Latin letters gets XX).
    """
    words = _plain(name).split()
    if len(words) > 1 and words[0].lower() in ARTICLES and words[1][0].isalpha():
        words = words[1:]
    letters = [ch for ch in "".join(words).upper() if "A" <= ch <= "Z"]
    return ("".join(letters[:2]) + "XX")[:2]


def format_code(prefix, seq, vendor=False):
    """prefix + seq zero-padded to at least 4 digits; vendors get a leading 'V'."""
    return f"{'V' if vendor else ''}{prefix}{seq:04d}"


# --- Helpers ------------------------------------------------------------------------------

def _clean(value):
    value = (value or "").strip()
    return value or None


def _either_permission(context):
    """The permission to authorize for an action either manager may do.

    A non-raising choice only; the caller then calls authorize() itself (rule 10), so a denial
    is logged once, for customer.manage.
    """
    if is_allowed(context, CUSTOMER_PERMISSION):
        return CUSTOMER_PERMISSION
    if is_allowed(context, VENDOR_PERMISSION):
        return VENDOR_PERMISSION
    return CUSTOMER_PERMISSION


def _digits(value):
    return re.sub(r"\D", "", value or "")


def _mask_tax_id(tax_id):
    digits = _digits(tax_id)
    if not digits:
        return "***" if tax_id else None
    return "***-**-" + digits[-4:]


def _name_key(name):
    return re.sub(r"[^a-z0-9]", "", _plain(name).casefold())


def _find(conn, name, tax_id, email, show_tax_ids):
    key, digits, mail = _name_key(name), _digits(tax_id), (email or "").strip().lower()
    found = []
    for r in conn.execute("SELECT contact_id, name, email, tax_id, customer_code, vendor_code, is_active "
                          "FROM contact ORDER BY contact_id"):
        matched = []
        if key and _name_key(r["name"]) == key:
            matched.append("name")
        if digits and _digits(r["tax_id"]) == digits:
            matched.append("tax_id")
        if mail and (r["email"] or "").strip().lower() == mail:
            matched.append("email")
        if matched:
            found.append({
                "contact_id": r["contact_id"], "name": r["name"], "email": r["email"],
                "tax_id": r["tax_id"] if show_tax_ids else _mask_tax_id(r["tax_id"]),
                "customer_code": r["customer_code"], "vendor_code": r["vendor_code"],
                "is_active": r["is_active"], "matched_on": matched,
            })
    return found


def _contact(conn, contact_id):
    row = conn.execute("SELECT * FROM contact WHERE contact_id = ?", (contact_id,)).fetchone()
    if row is None:
        raise NotFoundError("That contact no longer exists")
    return row


def _assign(conn, row, *, vendor):
    """Give the contact its code if it has none, set the flag, return the code.

    Runs inside the caller's write transaction: the sequence row and the code commit together.
    """
    table, code_col, flag_col = (("vendor_number", "vendor_code", "is_vendor") if vendor
                                 else ("customer_number", "customer_code", "is_customer"))
    code = row[code_col]
    if code is None:
        seq = conn.execute(f"INSERT INTO {table} (contact_id) VALUES (?) RETURNING seq",
                           (row["contact_id"],)).fetchone()[0]
        code = format_code(code_prefix(row["name"]), seq, vendor=vendor)
        conn.execute(f"UPDATE contact SET {code_col} = ?, {flag_col} = 1 WHERE contact_id = ?",
                     (code, row["contact_id"]))
    elif not row[flag_col]:
        conn.execute(f"UPDATE contact SET {flag_col} = 1 WHERE contact_id = ?", (row["contact_id"],))
    return code


# --- Services -----------------------------------------------------------------------------

def find_duplicates(context, name, tax_id=None, email=None):
    """Contacts that share the name (case, accents and punctuation ignored), tax ID digits or email.

    Inactive contacts are included. Tax IDs are masked unless the user holds view.tax_ids.
    """
    authorize(context, _either_permission(context), record_type="contact")
    show = is_allowed(context, "view.tax_ids")
    conn = read_connection(context.company_db_path)
    try:
        return _find(conn, name, tax_id, email, show)
    finally:
        conn.close()


def create_contact(context, name, *, is_customer=False, is_vendor=False, is_employee=False,
                   email=None, phone=None, address=None, tax_id=None, entity_type=None,
                   confirm_duplicates=False):
    """Create a contact and, for each role flag, assign its code. Returns the contact_id.

    If a contact with the same name, tax ID or email exists, raises DuplicateContactError unless
    confirm_duplicates is true. Nothing is written (and no code number consumed) in that case.
    """
    name = _clean(name)
    if name is None:
        raise ValidationError("Enter a name for the contact")
    if is_customer:
        authorize(context, CUSTOMER_PERMISSION, record_type="contact")
    if is_vendor:
        authorize(context, VENDOR_PERMISSION, record_type="contact")
    if not (is_customer or is_vendor):
        authorize(context, _either_permission(context), record_type="contact")
    show = is_allowed(context, "view.tax_ids")
    with write_transaction(context.company_db_path, context) as conn:
        matches = _find(conn, name, tax_id, email, show)
        if matches and not confirm_duplicates:
            raise DuplicateContactError(
                "A contact with the same name, tax ID or email already exists. "
                "Open it, or confirm to create another.", matches)
        contact_id = conn.execute(
            "INSERT INTO contact (name, is_employee, email, phone, address, tax_id, entity_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING contact_id",
            (name, int(bool(is_employee)), _clean(email), _clean(phone), _clean(address),
             _clean(tax_id), entity_type)).fetchone()[0]
        row = _contact(conn, contact_id)
        if is_customer:
            _assign(conn, row, vendor=False)
        if is_vendor:
            _assign(conn, row, vendor=True)
    return contact_id


def update_contact(context, contact_id, /, **fields):
    """Change contact details. Codes, role flags and is_active are not editable here."""
    unknown = sorted(set(fields) - set(EDITABLE_FIELDS))
    if unknown:
        raise ValidationError(f"These fields cannot be changed here: {', '.join(unknown)}")
    if "name" in fields and _clean(fields["name"]) is None:
        raise ValidationError("Enter a name for the contact")
    authorize(context, _either_permission(context), record_type="contact", record_id=contact_id)
    if not fields:
        return
    values = {k: (v if k == "is_employee" else _clean(v)) for k, v in fields.items()}
    with write_transaction(context.company_db_path, context) as conn:
        _contact(conn, contact_id)
        assignments = ", ".join(f"{column} = ?" for column in values)
        conn.execute(f"UPDATE contact SET {assignments} WHERE contact_id = ?", (*values.values(), contact_id))


def deactivate_contact(context, contact_id):
    """Make a contact inactive. Its codes stay reserved; a coded contact is never deleted."""
    authorize(context, _either_permission(context), record_type="contact", record_id=contact_id)
    with write_transaction(context.company_db_path, context) as conn:
        _contact(conn, contact_id)
        conn.execute("UPDATE contact SET is_active = 0 WHERE contact_id = ?", (contact_id,))


def make_customer(context, contact_id):
    """Flag the contact as a customer, assigning its code the first time. Returns the customer code."""
    authorize(context, CUSTOMER_PERMISSION, record_type="contact", record_id=contact_id)
    with write_transaction(context.company_db_path, context) as conn:
        return _assign(conn, _contact(conn, contact_id), vendor=False)


def make_vendor(context, contact_id):
    """Flag the contact as a vendor, assigning its code the first time. Returns the vendor code."""
    authorize(context, VENDOR_PERMISSION, record_type="contact", record_id=contact_id)
    with write_transaction(context.company_db_path, context) as conn:
        return _assign(conn, _contact(conn, contact_id), vendor=True)
