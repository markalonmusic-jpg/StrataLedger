"""Phase 2.7 STOP C: the custom fields service (FR1 as amended; CODE_CHANGES_NEEDED.md section 27).

Owner answers 2026-11-18 (docs/next_step.md, STOP C):
* fields.manage defines fields: Admin and the Master only, never the Agent.
* A value is readable exactly when its record is: Invoice ar.view, Bill ap.view, Project project.view (scoped).
  Contact by kind: customer = either manager or ar.view; vendor = either manager or ap.view; both and neither =
  either manager or either view code. The Agent reads only through ar.view / ap.view.
* A value is set with the record's own edit check: Contact either manager (as contacts.update_contact),
  Invoice invoice.create, Bill bill.create, Project project.manage (scoped). The Agent never sets values.
* Estimate: refused with one sentence until an estimate service exists.
* Posted invoices and bills: values may change (audit triggers keep old and new), refused in a closed period and
  while Lock documents after posting is on.
"""
import math
import sqlite3
import threading

import pytest

import config
from modules.services import custom_fields as cf
from modules.services import permissions
from modules.services.errors import NotFoundError, PeriodClosedError, PermissionDeniedError, ValidationError
from modules.services.tx import write_transaction
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)


# --- Setup ------------------------------------------------------------------------------

class _Raw:
    def __init__(self, world):
        self.path = world.path("PARENT")

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        self.conn.close()


def user_with(world, name, codes, *, scope="All"):
    user_id = world.user(name)
    world.role("PARENT", name.upper(), codes, scope=scope)
    world.grant(user_id, "PARENT", name.upper())
    return user_id


def ctx_with(world, name, codes, *, scope="All", origin="Human"):
    return world.ctx(user_with(world, name, codes, scope=scope), "PARENT", origin=origin)


@pytest.fixture
def admin(world):
    user_id = world.user("boss")
    world.grant(user_id, "PARENT", "Admin")
    return world.ctx(user_id, "PARENT")


def contact(world, *, customer=False, vendor=False):
    with _Raw(world) as c:
        contact_id = c.execute("INSERT INTO contact (name) VALUES ('Client') RETURNING contact_id").fetchone()[0]
        if customer:
            c.execute("UPDATE contact SET is_customer = 1, customer_code = ? WHERE contact_id = ?",
                      (f"CL{contact_id:04d}", contact_id))
        if vendor:
            c.execute("UPDATE contact SET is_vendor = 1, vendor_code = ? WHERE contact_id = ?",
                      (f"VCL{contact_id:04d}", contact_id))
    return contact_id


def invoice(world, itype="Invoice", *, posted=False, entry_date="2026-03-15"):
    with _Raw(world) as c:
        entry_id = lh.posted_entry(c, entry_date=entry_date) if posted else None
        return lh.make_invoice(c, itype=itype, status="Sent" if posted else "Draft", entry_id=entry_id)


def rows(world, sql, params=()):
    return world.rows("PARENT", sql, params)


def audit_rows(world, table):
    return rows(world, "SELECT * FROM audit_log WHERE table_name = ? ORDER BY 1", (table,))


def value_of(values, key):
    return next(v["value"] for v in values if v["field_key"] == key)


# --- Permission registry and seed ---------------------------------------------------------

def test_fields_manage_is_a_sensitive_company_code_held_by_admin_only(world):
    from modules.services import role_templates
    assert permissions.PERMISSIONS["fields.manage"] == permissions.Permission("Company", "Define custom fields", True)
    assert "fields.manage" not in permissions.AGENT_ALLOWED
    assert "fields.manage" not in permissions.PROJECT_SCOPED
    assert not [r for r in role_templates.ROLES if "fields.manage" in role_templates.permissions_for(r)]
    holders = {r["role_code"] for r in rows(world, "SELECT role_code FROM role_permission "
                                                   "WHERE permission_code = 'fields.manage'")}
    assert holders == {"Admin"}


# --- Defining fields ----------------------------------------------------------------------

def test_define_field_returns_the_field_with_a_key_from_the_label(admin):
    field = cf.define_field(admin, "Project", label="  Système kW  ", data_type="Number")
    assert field["label"] == "Système kW"
    assert field["field_key"] == "systeme_kw"
    assert field["data_type"] == "Number"
    assert field["is_active"] is True and field["is_required"] is False
    assert field["choices"] is None


@pytest.mark.parametrize("label,key", [("Permit #", "permit"), ("PTO date", "pto_date"), ("Roof--age (yrs)", "roof_age_yrs"),
                                       ("日本", "field"), ("3 phase", "f_3_phase")])
def test_field_key_rules(admin, label, key):
    assert cf.define_field(admin, "Project", label=label, data_type="Text")["field_key"] == key


def test_colliding_keys_get_a_number_and_never_change(admin):
    first = cf.define_field(admin, "Project", label="Permit", data_type="Text")
    second = cf.define_field(admin, "Project", label="Permit #", data_type="Text")
    third = cf.define_field(admin, "Project", label="Permit!", data_type="Text")
    assert [first["field_key"], second["field_key"], third["field_key"]] == ["permit", "permit_2", "permit_3"]
    renamed = cf.update_field(admin, first["field_id"], label="Building permit")
    assert renamed["field_key"] == "permit" and renamed["label"] == "Building permit"


def test_sort_order_follows_the_order_defined(admin):
    a = cf.define_field(admin, "Invoice", label="A", data_type="Text")
    b = cf.define_field(admin, "Invoice", label="B", data_type="Text")
    assert b["sort_order"] > a["sort_order"]
    cf.update_field(admin, b["field_id"], sort_order=a["sort_order"] - 1)
    assert [f["label"] for f in cf.list_fields(admin, "Invoice")] == ["B", "A"]


@pytest.mark.parametrize("kwargs", [
    {"label": "", "data_type": "Text"}, {"label": "   ", "data_type": "Text"}, {"label": None, "data_type": "Text"},
    {"label": "x" * 81, "data_type": "Text"}, {"label": "X", "data_type": "Currency"},
    {"label": "X", "data_type": "Text", "choices": ["a"]}, {"label": "X", "data_type": "Choice"},
    {"label": "X", "data_type": "Choice", "choices": []}, {"label": "X", "data_type": "Choice", "choices": ["a", "A"]},
    {"label": "X", "data_type": "Choice", "choices": ["a", " "]}, {"label": "X", "data_type": "Choice", "choices": "a,b"},
    {"label": "X", "data_type": "Choice", "choices": [1]}, {"label": "X", "data_type": "Text", "is_required": "yes"},
])
def test_define_field_refuses_bad_input(admin, kwargs):
    with pytest.raises(ValidationError):
        cf.define_field(admin, "Project", **kwargs)
    assert cf.list_fields(admin, "Project", include_inactive=True) == []


@pytest.mark.parametrize("record_type", ["Customer", "contact", "", None])
def test_unknown_record_type_is_refused(admin, record_type):
    with pytest.raises(ValidationError):
        cf.define_field(admin, record_type, label="X", data_type="Text")


def test_choice_field_stores_choices_as_active(admin):
    field = cf.define_field(admin, "Project", label="Roof type", data_type="Choice", choices=[" Tile ", "Metal"])
    assert field["choices"] == [{"value": "Tile", "active": True}, {"value": "Metal", "active": True}]


# --- Labels are unique per record type, case-insensitive -----------------------------------

def test_label_unique_per_record_type_case_insensitive(admin):
    cf.define_field(admin, "Project", label="Utility", data_type="Text")
    with pytest.raises(ValidationError, match="already"):
        cf.define_field(admin, "Project", label="  UTILITY ", data_type="Number")
    cf.define_field(admin, "Contact", label="utility", data_type="Text")     # another record type: allowed


def test_label_unique_includes_inactive_fields(admin):
    field = cf.define_field(admin, "Project", label="Utility", data_type="Text")
    cf.deactivate_field(admin, field["field_id"])
    with pytest.raises(ValidationError, match="already"):
        cf.define_field(admin, "Project", label="utility", data_type="Text")


def test_unicode_case_folding_counts_as_the_same_label(admin):
    cf.define_field(admin, "Project", label="Straße", data_type="Text")
    with pytest.raises(ValidationError):
        cf.define_field(admin, "Project", label="STRASSE", data_type="Text")


def test_rename_checks_uniqueness_but_allows_its_own_label(admin):
    a = cf.define_field(admin, "Project", label="Utility", data_type="Text")
    cf.define_field(admin, "Project", label="Lender", data_type="Text")
    with pytest.raises(ValidationError, match="already"):
        cf.update_field(admin, a["field_id"], label="LENDER")
    assert cf.update_field(admin, a["field_id"], label="UTILITY")["label"] == "UTILITY"


def test_two_writers_defining_the_same_label_only_one_wins(world, admin):
    barrier = threading.Barrier(2)
    results = []

    def define(label):
        barrier.wait()
        try:
            cf.define_field(admin, "Project", label=label, data_type="Text")
            results.append("ok")
        except ValidationError:
            results.append("refused")

    threads = [threading.Thread(target=define, args=(label,)) for label in ("Utility", "UTILITY")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok", "refused"]
    assert len(rows(world, "SELECT * FROM custom_field_def")) == 1


# --- Contact bank-number check (deferred check 2) ----------------------------------------

@pytest.mark.parametrize("label", ["Routing number", "Account Number", "acct no", "Acct #", "IBAN", "SWIFT code",
                                   "BIC", "Sort code", "Bank account", "ABA", "BSB", "IFSC", "CLABE",
                                   "AccountNumber", "bank_account_no"])
def test_contact_bank_number_fields_are_refused(admin, label):
    with pytest.raises(ValidationError) as caught:
        cf.define_field(admin, "Contact", label=label, data_type="Text")
    assert "bank" in str(caught.value).lower()
    assert config.APP_NAME in str(caught.value)
    assert cf.list_fields(admin, "Contact", include_inactive=True) == []


@pytest.mark.parametrize("label", ["Account manager", "Basic info", "Cubic yards", "Swiftness", "Sort order",
                                   "Number of trucks", "Gate code"])
def test_contact_ordinary_fields_are_allowed(admin, label):
    cf.define_field(admin, "Contact", label=label, data_type="Text")


def test_contact_rename_to_a_bank_number_is_refused(admin):
    field = cf.define_field(admin, "Contact", label="Gate code", data_type="Text")
    with pytest.raises(ValidationError, match="bank"):
        cf.update_field(admin, field["field_id"], label="Routing number")


def test_bank_number_check_is_for_contacts_only(admin):
    cf.define_field(admin, "Project", label="Account number", data_type="Text")


# --- Updating fields ----------------------------------------------------------------------

def test_update_required_flag(admin):
    field = cf.define_field(admin, "Project", label="Utility", data_type="Text", is_required=True)
    assert field["is_required"] is True
    assert cf.update_field(admin, field["field_id"], is_required=False)["is_required"] is False


def test_update_unknown_field_is_not_found(admin):
    with pytest.raises(NotFoundError):
        cf.update_field(admin, 999, label="X")


@pytest.mark.parametrize("kwargs", [{"sort_order": "1"}, {"sort_order": True}, {"sort_order": 1.5},
                                    {"is_required": 1}, {"label": ""}])
def test_update_refuses_bad_input(admin, kwargs):
    field = cf.define_field(admin, "Project", label="Utility", data_type="Text")
    with pytest.raises(ValidationError):
        cf.update_field(admin, field["field_id"], **kwargs)


def test_data_type_changes_while_no_value_exists(world, admin):
    field = cf.define_field(admin, "Project", label="Size", data_type="Text")
    assert cf.update_field(admin, field["field_id"], data_type="Number")["data_type"] == "Number"
    choice = cf.update_field(admin, field["field_id"], data_type="Choice", choices=["S", "M"])
    assert choice["choices"] == [{"value": "S", "active": True}, {"value": "M", "active": True}]
    back = cf.update_field(admin, field["field_id"], data_type="Text")
    assert back["data_type"] == "Text" and back["choices"] is None


def test_data_type_change_to_choice_needs_choices(admin):
    field = cf.define_field(admin, "Project", label="Size", data_type="Text")
    with pytest.raises(ValidationError):
        cf.update_field(admin, field["field_id"], data_type="Choice")


def test_data_type_change_refused_while_a_value_exists(world, admin):
    project = world.project("PARENT")
    field = cf.define_field(admin, "Project", label="Size", data_type="Text")
    cf.set_value(admin, "Project", project, field["field_key"], "big")
    with pytest.raises(ValidationError, match="value"):
        cf.update_field(admin, field["field_id"], data_type="Number")
    # A cleared value no longer holds the old type: the change is allowed again.
    cf.set_value(admin, "Project", project, field["field_key"], None)
    assert cf.update_field(admin, field["field_id"], data_type="Number")["data_type"] == "Number"


def test_choices_on_a_non_choice_field_are_refused(admin):
    field = cf.define_field(admin, "Project", label="Size", data_type="Text")
    with pytest.raises(ValidationError):
        cf.update_field(admin, field["field_id"], choices=["a"])


def test_a_used_choice_is_deactivated_never_removed(world, admin):
    project = world.project("PARENT")
    field = cf.define_field(admin, "Project", label="Roof", data_type="Choice", choices=["Tile", "Metal", "Slate"])
    cf.set_value(admin, "Project", project, field["field_key"], "Tile")
    updated = cf.update_field(admin, field["field_id"], choices=["Metal", "Shingle"])
    assert updated["choices"] == [{"value": "Metal", "active": True}, {"value": "Shingle", "active": True},
                                  {"value": "Tile", "active": False}]           # Slate was unused: removed
    assert value_of(cf.get_values(admin, "Project", project), field["field_key"]) == "Tile"   # still reads
    other = world.project("PARENT")
    with pytest.raises(ValidationError):
        cf.set_value(admin, "Project", other, field["field_key"], "Tile")        # inactive choice: no new values
    again = cf.update_field(admin, field["field_id"], choices=["tile", "Metal"])  # listed again: active
    assert {"value": "Tile", "active": True} in again["choices"]


def test_deactivate_and_reactivate(world, admin):
    project = world.project("PARENT")
    field = cf.define_field(admin, "Project", label="Utility", data_type="Text")
    cf.set_value(admin, "Project", project, "utility", "PG&E")
    cf.deactivate_field(admin, field["field_id"])
    assert cf.list_fields(admin, "Project") == []
    assert [f["is_active"] for f in cf.list_fields(admin, "Project", include_inactive=True)] == [False]
    values = cf.get_values(admin, "Project", project)
    assert values == [{"field_key": "utility", "label": "Utility", "data_type": "Text", "is_active": False,
                       "value": "PG&E"}]
    with pytest.raises(ValidationError, match="inactive"):
        cf.set_value(admin, "Project", project, "utility", "SCE")
    cf.reactivate_field(admin, field["field_id"])
    cf.set_value(admin, "Project", project, "utility", "SCE")
    assert value_of(cf.get_values(admin, "Project", project), "utility") == "SCE"


def test_nothing_ever_deletes_a_definition_or_a_value():
    with open(cf.__file__, encoding="utf-8") as source:
        assert "DELETE" not in source.read().upper()


# --- Values: each type ------------------------------------------------------------------

@pytest.fixture
def typed(world, admin):
    project = world.project("PARENT")
    for label, data_type, choices in (("Note", "Text", None), ("Kw", "Number", None), ("Fee", "Money", None),
                                      ("Pto", "Date", None), ("Hoa", "Yes/No", None),
                                      ("Roof", "Choice", ["Tile", "Metal"])):
        cf.define_field(admin, "Project", label=label, data_type=data_type, choices=choices)
    return project


@pytest.mark.parametrize("key,value,stored,column", [
    ("note", "  gate 1234 ", "gate 1234", "value_text"),
    ("kw", 7.5, 7.5, "value_number"),
    ("kw", 8, 8, "value_number"),
    ("kw", -1.25, -1.25, "value_number"),
    ("fee", 2500, 2500, "value_cents"),
    ("fee", -100, -100, "value_cents"),
    ("pto", "2026-11-18", "2026-11-18", "value_date"),
    ("hoa", True, True, "value_bool"),
    ("hoa", False, False, "value_bool"),
    ("roof", "metal", "Metal", "value_text"),          # matched without case, stored as the choice is written
])
def test_valid_values_are_stored_in_their_typed_column(world, admin, typed, key, value, stored, column):
    cf.set_value(admin, "Project", typed, key, value)
    assert value_of(cf.get_values(admin, "Project", typed), key) == stored
    row = rows(world, "SELECT v.* FROM custom_field_value AS v JOIN custom_field_def AS d USING (field_id) "
                      "WHERE d.field_key = ? AND v.record_id = ?", (key, typed))[0]
    filled = [c for c in ("value_text", "value_number", "value_cents", "value_date", "value_bool")
              if row[c] is not None]
    assert filled == [column]


@pytest.mark.parametrize("key,value", [
    ("note", 5), ("note", True), ("note", "x" * 2001),
    ("kw", True), ("kw", "3"), ("kw", math.nan), ("kw", math.inf), ("kw", -math.inf), ("kw", [1]),
    ("fee", 25.0), ("fee", "25.00"), ("fee", True), ("fee", 25.5),
    ("pto", "2026-02-30"), ("pto", "18/11/2026"), ("pto", "2026-11-18T00:00:00"), ("pto", 20261118),
    ("pto", "2026-1-8"),
    ("hoa", 1), ("hoa", "yes"), ("hoa", 0),
    ("roof", "Slate"), ("roof", 1),
])
def test_invalid_values_are_refused_and_nothing_is_written(world, admin, typed, key, value):
    with pytest.raises(ValidationError):
        cf.set_value(admin, "Project", typed, key, value)
    assert rows(world, "SELECT * FROM custom_field_value") == []


def test_clearing_sets_every_column_to_null(world, admin, typed):
    cf.set_value(admin, "Project", typed, "fee", 2500)
    cf.set_value(admin, "Project", typed, "fee", None)
    (row,) = rows(world, "SELECT * FROM custom_field_value")
    assert [row[c] for c in ("value_text", "value_number", "value_cents", "value_date", "value_bool")] == [None] * 5
    assert value_of(cf.get_values(admin, "Project", typed), "fee") is None


def test_an_empty_text_clears(world, admin, typed):
    cf.set_value(admin, "Project", typed, "note", "hi")
    cf.set_value(admin, "Project", typed, "note", "   ")
    assert value_of(cf.get_values(admin, "Project", typed), "note") is None


def test_clearing_a_value_that_was_never_set_writes_nothing(world, admin, typed):
    cf.set_value(admin, "Project", typed, "fee", None)
    assert rows(world, "SELECT * FROM custom_field_value") == []


def test_get_values_lists_active_fields_in_order_with_none_for_unset(admin, typed):
    values = cf.get_values(admin, "Project", typed)
    assert [v["field_key"] for v in values] == ["note", "kw", "fee", "pto", "hoa", "roof"]
    assert all(v["value"] is None for v in values)


def test_unknown_field_key_is_not_found(admin, typed):
    with pytest.raises(NotFoundError):
        cf.set_value(admin, "Project", typed, "nope", "x")


def test_a_field_of_another_record_type_is_not_found(world, admin, typed):
    cf.define_field(admin, "Invoice", label="Po ref", data_type="Text")
    with pytest.raises(NotFoundError):
        cf.set_value(admin, "Project", typed, "po_ref", "x")


@pytest.mark.parametrize("record_type", ["Contact", "Invoice", "Bill", "Project"])
def test_the_record_must_exist(admin, record_type):
    cf.define_field(admin, record_type, label="Note", data_type="Text")
    with pytest.raises(NotFoundError):
        cf.set_value(admin, record_type, 9999, "note", "x")
    with pytest.raises(NotFoundError):
        cf.get_values(admin, record_type, 9999)


def test_an_invoice_id_is_not_a_bill_and_a_bill_id_is_not_an_invoice(world, admin):
    inv, bill = invoice(world, "Invoice"), invoice(world, "Bill")
    cf.define_field(admin, "Invoice", label="Note", data_type="Text")
    cf.define_field(admin, "Bill", label="Note", data_type="Text")
    with pytest.raises(NotFoundError):
        cf.set_value(admin, "Bill", inv, "note", "x")
    with pytest.raises(NotFoundError):
        cf.set_value(admin, "Invoice", bill, "note", "x")


@pytest.mark.parametrize("record_id", ["1", 1.0, True, None])
def test_record_id_must_be_an_integer(admin, typed, record_id):
    with pytest.raises(ValidationError):
        cf.set_value(admin, "Project", record_id, "note", "x")


def test_the_trigger_is_the_backstop_for_the_typed_column(world, admin, typed):
    field_id = rows(world, "SELECT field_id FROM custom_field_def WHERE field_key = 'fee'")[0]["field_id"]
    with _Raw(world) as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO custom_field_value (field_id, record_id, value_text) VALUES (?, ?, '25')",
                      (field_id, typed))


# --- Estimate: refused until an estimate service exists -------------------------------------

@pytest.mark.parametrize("call", [
    lambda c: cf.list_fields(c, "Estimate"),
    lambda c: cf.define_field(c, "Estimate", label="X", data_type="Text"),
    lambda c: cf.set_value(c, "Estimate", 1, "x", "y"),
    lambda c: cf.get_values(c, "Estimate", 1),
])
def test_estimate_calls_are_refused_with_one_sentence(world, admin, call):
    with pytest.raises(ValidationError) as caught:
        call(admin)
    message = str(caught.value)
    assert message.endswith(".") and message.count(". ") == 0 and "estimate" in message.lower()
    assert rows(world, "SELECT * FROM custom_field_def") == []


def test_an_estimate_field_made_outside_the_service_cannot_be_changed(world, admin):
    with _Raw(world) as c:
        field_id = c.execute("INSERT INTO custom_field_def (record_type, field_key, label, data_type) "
                             "VALUES ('Estimate', 'x', 'X', 'Text') RETURNING field_id").fetchone()[0]
    for call in (lambda: cf.update_field(admin, field_id, label="Y"), lambda: cf.deactivate_field(admin, field_id),
                 lambda: cf.reactivate_field(admin, field_id)):
        with pytest.raises(ValidationError, match="estimate"):
            call()


# --- Permissions: defining fields -----------------------------------------------------------

DEFINE_CALLS = [
    lambda c, f: cf.define_field(c, "Project", label="New", data_type="Text"),
    lambda c, f: cf.update_field(c, f, label="Renamed"),
    lambda c, f: cf.deactivate_field(c, f),
    lambda c, f: cf.reactivate_field(c, f),
]


@pytest.mark.parametrize("call", DEFINE_CALLS)
def test_defining_needs_fields_manage(world, admin, call):
    field_id = cf.define_field(admin, "Project", label="Utility", data_type="Text")["field_id"]
    everything_else = [c for c in permissions.PERMISSIONS if c != "fields.manage"]
    lacking = ctx_with(world, "clerk", everything_else)
    before = rows(world, "SELECT * FROM custom_field_def")
    with pytest.raises(PermissionDeniedError):
        call(lacking, field_id)
    assert rows(world, "SELECT * FROM custom_field_def") == before
    assert world.events("PARENT")[-1]["permission_code"] == "fields.manage"
    call(ctx_with(world, "fieldsman", ["fields.manage"]), field_id)


def test_the_master_defines_fields(world):
    master = world.ctx(world.user("root", master=True), "PARENT")
    cf.define_field(master, "Project", label="Utility", data_type="Text")


@pytest.mark.parametrize("call", DEFINE_CALLS)
def test_the_agent_never_defines_fields_even_as_admin(world, admin, call):
    field_id = cf.define_field(admin, "Project", label="Utility", data_type="Text")["field_id"]
    agent = world.ctx(admin.user_id, "PARENT", origin="Agent")
    with pytest.raises(PermissionDeniedError, match="AI assistant"):
        call(agent, field_id)


def test_the_denial_sentence_names_the_action_not_the_code(world):
    with pytest.raises(PermissionDeniedError) as caught:
        cf.define_field(ctx_with(world, "clerk", ["project.view"]), "Project", label="X", data_type="Text")
    assert "define custom fields" in str(caught.value) and "fields.manage" not in str(caught.value)


# --- Permissions: reading and setting values, per record type -------------------------------

def _check(call, ctx, allowed):
    if allowed:
        call(ctx)
    else:
        with pytest.raises(PermissionDeniedError):
            call(ctx)


@pytest.mark.parametrize("kind", ["customer", "vendor", "both", "neither"])
@pytest.mark.parametrize("code", ["customer.manage", "vendor.manage", "ar.view", "ap.view", "project.view"])
def test_contact_reads_follow_the_contact_kind(world, admin, kind, code):
    record = contact(world, customer=kind in ("customer", "both"), vendor=kind in ("vendor", "both"))
    cf.define_field(admin, "Contact", label="Gate code", data_type="Text")
    readers = {"customer": {"customer.manage", "vendor.manage", "ar.view"},
               "vendor": {"customer.manage", "vendor.manage", "ap.view"},
               "both": {"customer.manage", "vendor.manage", "ar.view", "ap.view"},
               "neither": {"customer.manage", "vendor.manage", "ar.view", "ap.view"}}[kind]
    ctx = ctx_with(world, "reader", [code])
    _check(lambda c: cf.get_values(c, "Contact", record), ctx, code in readers)
    _check(lambda c: cf.list_fields(c, "Contact"), ctx, code != "project.view")


@pytest.mark.parametrize("kind", ["customer", "vendor", "both", "neither"])
@pytest.mark.parametrize("code", ["customer.manage", "vendor.manage", "ar.view", "ap.view"])
def test_contact_values_are_set_with_the_contact_edit_check(world, admin, kind, code):
    # contacts.update_contact lets either manager edit any kind (listed for the 2.9 access-model replan).
    record = contact(world, customer=kind in ("customer", "both"), vendor=kind in ("vendor", "both"))
    cf.define_field(admin, "Contact", label="Gate code", data_type="Text")
    ctx = ctx_with(world, "writer", [code])
    _check(lambda c: cf.set_value(c, "Contact", record, "gate_code", "1234"), ctx,
           code in ("customer.manage", "vendor.manage"))


@pytest.mark.parametrize("kind,code,allowed", [
    ("customer", "ar.view", True), ("customer", "ap.view", False), ("customer", "customer.manage", False),
    ("vendor", "ap.view", True), ("vendor", "ar.view", False), ("vendor", "vendor.manage", False),
    ("both", "ar.view", True), ("both", "ap.view", True), ("neither", "ar.view", True), ("neither", "ap.view", True),
])
def test_the_agent_reads_contacts_only_through_the_view_codes(world, admin, kind, code, allowed):
    record = contact(world, customer=kind in ("customer", "both"), vendor=kind in ("vendor", "both"))
    cf.define_field(admin, "Contact", label="Gate code", data_type="Text")
    agent = world.ctx(user_with(world, "bot", [code]), "PARENT", origin="Agent")
    _check(lambda c: cf.get_values(c, "Contact", record), agent, allowed)


def test_reading_a_missing_contact_without_any_code_is_denied_not_not_found(world, admin):
    with pytest.raises(PermissionDeniedError):
        cf.get_values(ctx_with(world, "nobody", ["project.view"]), "Contact", 9999)


@pytest.mark.parametrize("record_type,read,write,other_read,other_write", [
    ("Invoice", "ar.view", "invoice.create", "ap.view", "bill.create"),
    ("Bill", "ap.view", "bill.create", "ar.view", "invoice.create"),
])
def test_invoice_and_bill_permissions(world, admin, record_type, read, write, other_read, other_write):
    record = invoice(world, record_type)
    cf.define_field(admin, record_type, label="Po ref", data_type="Text")
    get = lambda c: cf.get_values(c, record_type, record)                     # noqa: E731
    put = lambda c: cf.set_value(c, record_type, record, "po_ref", "PO-1")   # noqa: E731
    _check(get, ctx_with(world, "r1", [read]), True)
    _check(get, ctx_with(world, "r2", [other_read, write]), False)
    _check(lambda c: cf.list_fields(c, record_type), ctx_with(world, "r3", [read]), True)
    _check(lambda c: cf.list_fields(c, record_type), ctx_with(world, "r4", [other_read]), False)
    _check(put, ctx_with(world, "w1", [write]), True)
    _check(put, ctx_with(world, "w2", [read, other_write]), False)


def test_project_permissions_and_scope(world, admin):
    mine, theirs = world.project("PARENT"), world.project("PARENT")
    cf.define_field(admin, "Project", label="Utility", data_type="Text")
    pm_id = user_with(world, "pm", ["project.view", "project.manage"], scope="Assigned")
    world.assign("PARENT", pm_id, mine)
    pm = world.ctx(pm_id, "PARENT")
    cf.set_value(pm, "Project", mine, "utility", "PG&E")
    assert value_of(cf.get_values(pm, "Project", mine), "utility") == "PG&E"
    assert cf.list_fields(pm, "Project", project_id=mine)
    for call in (lambda: cf.set_value(pm, "Project", theirs, "utility", "x"),
                 lambda: cf.get_values(pm, "Project", theirs),
                 lambda: cf.list_fields(pm, "Project", project_id=theirs),
                 lambda: cf.list_fields(pm, "Project")):
        with pytest.raises(PermissionDeniedError):
            call()
    viewer = ctx_with(world, "viewer", ["project.view"])
    cf.get_values(viewer, "Project", theirs)
    cf.list_fields(viewer, "Project")
    with pytest.raises(PermissionDeniedError):
        cf.set_value(viewer, "Project", theirs, "utility", "x")


def test_fields_manage_alone_lists_definitions(world, admin):
    cf.define_field(admin, "Bill", label="Po ref", data_type="Text")
    assert [f["label"] for f in cf.list_fields(ctx_with(world, "fm", ["fields.manage"]), "Bill")] == ["Po ref"]


@pytest.mark.parametrize("record_type", ["Contact", "Invoice", "Bill", "Project"])
def test_the_agent_never_sets_values_even_as_admin(world, admin, record_type):
    record = {"Contact": lambda: contact(world, customer=True), "Invoice": lambda: invoice(world, "Invoice"),
              "Bill": lambda: invoice(world, "Bill"), "Project": lambda: world.project("PARENT")}[record_type]()
    cf.define_field(admin, record_type, label="Note", data_type="Text")
    agent = world.ctx(admin.user_id, "PARENT", origin="Agent")
    with pytest.raises(PermissionDeniedError, match="AI assistant"):
        cf.set_value(agent, record_type, record, "note", "x")
    assert rows(world, "SELECT * FROM custom_field_value") == []
    assert world.events("PARENT")[-1]["event_type"] == "Denied"


@pytest.mark.parametrize("record_type,code", [("Invoice", "ar.view"), ("Bill", "ap.view"), ("Project", "project.view")])
def test_the_agent_reads_through_its_view_codes(world, admin, record_type, code):
    record = {"Invoice": lambda: invoice(world, "Invoice"), "Bill": lambda: invoice(world, "Bill"),
              "Project": lambda: world.project("PARENT")}[record_type]()
    cf.define_field(admin, record_type, label="Note", data_type="Text")
    cf.set_value(admin, record_type, record, "note", "hello")
    agent = world.ctx(user_with(world, "bot", [code]), "PARENT", origin="Agent")
    assert value_of(cf.get_values(agent, record_type, record), "note") == "hello"


# --- Posted invoices and bills ---------------------------------------------------------------

@pytest.mark.parametrize("record_type", ["Invoice", "Bill"])
def test_a_posted_document_value_may_change_and_the_audit_row_holds_old_and_new(world, admin, record_type):
    record = invoice(world, record_type, posted=True)
    cf.define_field(admin, record_type, label="Po ref", data_type="Text")
    cf.set_value(admin, record_type, record, "po_ref", "PO-1")
    cf.set_value(admin, record_type, record, "po_ref", "PO-2")
    last = audit_rows(world, "custom_field_value")[-1]
    assert last["action"] == "Update" and last["user_id"] == admin.user_id
    assert '"value_text":"PO-1"' in last["old_value"].replace(" ", "")
    assert '"value_text":"PO-2"' in last["new_value"].replace(" ", "")


@pytest.mark.parametrize("record_type", ["Invoice", "Bill"])
def test_a_posted_document_in_a_closed_period_is_refused(world, admin, record_type):
    record = invoice(world, record_type, posted=True)
    cf.define_field(admin, record_type, label="Po ref", data_type="Text")
    with _Raw(world) as c:
        period_id = c.execute("SELECT period_id FROM journal_entry AS e JOIN invoice AS i ON i.entry_id = e.entry_id "
                              "WHERE i.invoice_id = ?", (record,)).fetchone()[0]
        lh.set_period_closed(c, period_id, True)
    with pytest.raises(PeriodClosedError):
        cf.set_value(admin, record_type, record, "po_ref", "PO-1")
    assert rows(world, "SELECT * FROM custom_field_value") == []
    assert value_of(cf.get_values(admin, record_type, record), "po_ref") is None     # reading still works


def test_a_draft_document_dated_in_a_closed_period_is_not_posted_so_it_may_change(world, admin):
    record = invoice(world, "Invoice")
    cf.define_field(admin, "Invoice", label="Po ref", data_type="Text")
    with _Raw(world) as c:
        lh.set_period_closed(c, lh.ensure_period(c, "2026-03-01"), True)
    cf.set_value(admin, "Invoice", record, "po_ref", "PO-1")


@pytest.mark.parametrize("record_type", ["Invoice", "Bill"])
def test_lock_documents_after_posting_refuses_posted_documents_only(world, admin, record_type):
    posted, draft = invoice(world, record_type, posted=True), invoice(world, record_type)
    cf.define_field(admin, record_type, label="Po ref", data_type="Text")
    world.settings("PARENT")
    with _Raw(world) as c:
        assert c.execute("SELECT lock_documents_after_posting FROM company_settings").fetchone()[0] == 0
    cf.set_value(admin, record_type, posted, "po_ref", "PO-1")            # OFF by default: allowed
    with _Raw(world) as c:
        c.execute("UPDATE company_settings SET lock_documents_after_posting = 1")
    with pytest.raises(ValidationError, match="Lock documents after posting"):
        cf.set_value(admin, record_type, posted, "po_ref", "PO-2")
    cf.set_value(admin, record_type, draft, "po_ref", "PO-3")             # a draft is not posted


# --- Audit -------------------------------------------------------------------------------

def test_definition_changes_are_audit_logged_with_the_user(world, admin):
    field = cf.define_field(admin, "Project", label="Utility", data_type="Text")
    cf.update_field(admin, field["field_id"], label="Utility company")
    cf.deactivate_field(admin, field["field_id"])
    log = audit_rows(world, "custom_field_def")
    assert [r["action"] for r in log] == ["Insert", "Update", "Update"]
    assert {r["user_id"] for r in log} == {admin.user_id}
    assert '"label":"Utility"' in log[1]["old_value"].replace(" ", "")
    assert '"label":"Utilitycompany"' in log[1]["new_value"].replace(" ", "")


def test_a_rolled_back_value_write_leaves_no_value_and_no_audit_row(world, admin, typed):
    before = audit_rows(world, "custom_field_value")
    field = rows(world, "SELECT * FROM custom_field_def WHERE field_key = 'fee'")[0]
    with pytest.raises(RuntimeError):
        with write_transaction(admin.company_db_path, admin) as conn:
            cf._store_value(conn, field, typed, 2500)
            assert conn.execute("SELECT COUNT(*) FROM custom_field_value").fetchone()[0] == 1
            raise RuntimeError("stop")
    assert rows(world, "SELECT * FROM custom_field_value") == []
    assert audit_rows(world, "custom_field_value") == before


def test_a_refused_write_leaves_no_audit_row(world, admin, typed):
    before = len(rows(world, "SELECT * FROM audit_log"))
    with pytest.raises(ValidationError):
        cf.set_value(admin, "Project", typed, "fee", 1.5)
    assert len(rows(world, "SELECT * FROM audit_log")) == before
