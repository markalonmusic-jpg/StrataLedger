"""Phase 2.6: customer and vendor codes (CLAUDE.md section 6, docs/crm_pm_design.md section 5)."""
import sqlite3
import threading

import pytest

from modules.services import contacts, permissions
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)

# --- The prefix rule -----------------------------------------------------------------

PREFIXES = [
    ("Acme Corp", "AC"),
    ("acme", "AC"),
    ("Élan Builders", "EL"),
    ("Zoë Café", "ZO"),
    ("Ñandú SA", "NA"),
    ("Müller GmbH", "MU"),
    ("The Home Depot", "HO"),
    ("the home depot", "HO"),
    ("A Better Roof", "BE"),
    ("An Apple a Day", "AP"),
    ("A & B Plumbing", "AB"),      # next word starts with a symbol: keep the "A"
    ("The 3M Company", "TH"),      # next word starts with a digit: keep "The"
    ("The", "TH"),                 # an article alone is the name
    ("A", "AX"),
    ("An", "AN"),
    ("Theodore Ltd", "TH"),        # "The" must be a whole word
    ("Anderson", "AN"),
    ("3M", "MX"),
    ("123", "XX"),
    ("7-Eleven", "EL"),
    ("O'Brien & Sons", "OB"),
    ("B", "BX"),
    ("  padded  name ", "PA"),
    ("", "XX"),
    ("日本商事", "XX"),
    ("Москва", "XX"),
    ("Αθήνα", "XX"),
    ("Ab", "AB"),
]


@pytest.mark.parametrize("name,expected", PREFIXES)
def test_prefix_rule(name, expected):
    assert contacts.code_prefix(name) == expected


def test_format_code_pads_to_four_digits_and_grows():
    assert contacts.format_code("AC", 1) == "AC0001"
    assert contacts.format_code("AC", 9999) == "AC9999"
    assert contacts.format_code("AC", 10000) == "AC10000"
    assert contacts.format_code("AC", 1, vendor=True) == "VAC0001"
    assert contacts.format_code("AC", 123456, vendor=True) == "VAC123456"


# --- Fixtures --------------------------------------------------------------------------

@pytest.fixture
def staff(world):
    """A user with customer.manage and vendor.manage in PARENT."""
    user_id = world.user("clerk")
    world.role("PARENT", "CLERK", ["customer.manage", "vendor.manage"])
    world.grant(user_id, "PARENT", "CLERK")
    return world.ctx(user_id, "PARENT")


def row(world, contact_id):
    return world.rows("PARENT", "SELECT * FROM contact WHERE contact_id = ?", (contact_id,))[0]


def raw(world, sql, params=()):
    conn = sqlite3.connect(world.path("PARENT"))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def count(world, table):
    return world.rows("PARENT", f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


# --- Assignment ----------------------------------------------------------------------

def test_create_customer_gets_a_code_and_a_sequence_row(world, staff):
    contact_id = contacts.create_contact(staff, "Acme Corp", is_customer=True)
    assert row(world, contact_id)["customer_code"] == "AC0001"
    assert row(world, contact_id)["vendor_code"] is None
    seq = world.rows("PARENT", "SELECT seq, contact_id FROM customer_number")
    assert seq == [{"seq": 1, "contact_id": contact_id}]


def test_create_vendor_uses_its_own_sequence_and_v_prefix(world, staff):
    first = contacts.create_contact(staff, "Acme Corp", is_customer=True)
    vendor = contacts.create_contact(staff, "Bolt Supply", is_vendor=True)
    assert row(world, first)["customer_code"] == "AC0001"
    assert row(world, vendor)["vendor_code"] == "VBO0001"
    assert row(world, vendor)["customer_code"] is None


def test_default_contact_is_not_a_customer_and_has_no_code(world, staff):
    contact_id = contacts.create_contact(staff, "Pat Worker", is_employee=True)
    r = row(world, contact_id)
    assert (r["is_customer"], r["is_vendor"], r["is_employee"]) == (0, 0, 1)
    assert r["customer_code"] is None and r["vendor_code"] is None


def test_sequence_counts_up_and_ignores_the_name(world, staff):
    a = contacts.create_contact(staff, "Acme", is_customer=True)
    b = contacts.create_contact(staff, "Zeta", is_customer=True)
    c = contacts.create_contact(staff, "Acme Two", is_customer=True)
    assert [row(world, x)["customer_code"] for x in (a, b, c)] == ["AC0001", "ZE0002", "AC0003"]


def test_make_customer_on_existing_contact_and_idempotent(world, staff):
    contact_id = contacts.create_contact(staff, "Prospect Inc")
    assert contacts.make_customer(staff, contact_id) == "PR0001"
    assert contacts.make_customer(staff, contact_id) == "PR0001"
    assert row(world, contact_id)["is_customer"] == 1
    assert count(world, "customer_number") == 1


def test_contact_can_hold_both_codes(world, staff):
    contact_id = contacts.create_contact(staff, "Acme Corp", is_customer=True, is_vendor=True)
    r = row(world, contact_id)
    assert (r["customer_code"], r["vendor_code"]) == ("AC0001", "VAC0001")


def test_make_vendor_after_customer_keeps_the_customer_code(world, staff):
    contact_id = contacts.create_contact(staff, "Acme Corp", is_customer=True)
    assert contacts.make_vendor(staff, contact_id) == "VAC0001"
    assert row(world, contact_id)["customer_code"] == "AC0001"


def test_name_change_does_not_change_the_code(world, staff):
    contact_id = contacts.create_contact(staff, "Acme Corp", is_customer=True)
    contacts.update_contact(staff, contact_id, name="Zenith Corp")
    assert row(world, contact_id)["customer_code"] == "AC0001"


def test_update_contact_rejects_codes_and_flags(world, staff):
    contact_id = contacts.create_contact(staff, "Acme Corp", is_customer=True)
    for field in ("customer_code", "vendor_code", "is_customer", "is_vendor", "contact_id", "is_active", "bogus"):
        with pytest.raises(ValidationError):
            contacts.update_contact(staff, contact_id, **{field: "X"})


def test_unknown_contact_is_not_found(world, staff):
    for call in (contacts.make_customer, contacts.make_vendor, contacts.deactivate_contact):
        with pytest.raises(NotFoundError):
            call(staff, 9999)
    with pytest.raises(NotFoundError):
        contacts.update_contact(staff, 9999, name="X")


def test_blank_name_is_rejected(world, staff):
    with pytest.raises(ValidationError):
        contacts.create_contact(staff, "   ", is_customer=True)


def test_failed_assignment_leaves_no_sequence_row(world, staff, monkeypatch):
    contact_id = contacts.create_contact(staff, "Acme Corp")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    with monkeypatch.context() as patch:
        patch.setattr(contacts, "format_code", boom)
        with pytest.raises(RuntimeError):
            contacts.make_customer(staff, contact_id)
    assert count(world, "customer_number") == 0
    assert contacts.make_customer(staff, contact_id) == "AC0001"


# --- Concurrency -----------------------------------------------------------------------

def _run_parallel(make, ids):
    codes, errors = [], []
    start = threading.Barrier(len(ids))

    def work(contact_id):
        try:
            start.wait()
            codes.append(make(contact_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return codes, errors


def test_parallel_customer_assignments_get_different_sequences(world, staff):
    ids = [contacts.create_contact(staff, f"Firm {i}") for i in range(8)]
    codes, errors = _run_parallel(lambda i: contacts.make_customer(staff, i), ids)
    assert not errors
    assert len(set(codes)) == len(ids)
    seqs = sorted(r["seq"] for r in world.rows("PARENT", "SELECT seq FROM customer_number"))
    assert seqs == list(range(1, len(ids) + 1))


def test_parallel_vendor_assignments_get_different_sequences(world, staff):
    ids = [contacts.create_contact(staff, f"Supplier {i}") for i in range(6)]
    codes, errors = _run_parallel(lambda i: contacts.make_vendor(staff, i), ids)
    assert not errors and len(set(codes)) == len(ids)


def test_parallel_assignment_of_the_same_contact_gives_one_code(world, staff):
    contact_id = contacts.create_contact(staff, "Acme")
    codes, errors = _run_parallel(lambda i: contacts.make_customer(staff, i), [contact_id] * 4)
    assert not errors and set(codes) == {"AC0001"}
    assert count(world, "customer_number") == 1


# --- Never reused ----------------------------------------------------------------------

def test_codes_are_not_reused_after_deactivation(world, staff):
    first = contacts.create_contact(staff, "Acme Corp", is_customer=True)
    contacts.deactivate_contact(staff, first)
    second = contacts.create_contact(staff, "Acme Corp Again", is_customer=True, confirm_duplicates=True)
    assert row(world, first)["is_active"] == 0
    assert row(world, first)["customer_code"] == "AC0001"
    assert row(world, second)["customer_code"] == "AC0002"


def test_sequence_never_goes_backwards_even_if_a_row_is_removed(world, staff):
    contacts.create_contact(staff, "Acme", is_customer=True)
    contacts.create_contact(staff, "Beta", is_customer=True)
    raw(world, "DELETE FROM customer_number WHERE seq = 2")   # AUTOINCREMENT still remembers 2
    third = contacts.create_contact(staff, "Gamma", is_customer=True)
    assert row(world, third)["customer_code"] == "GA0003"


def test_deactivate_keeps_the_flags_and_codes(world, staff):
    contact_id = contacts.create_contact(staff, "Acme", is_customer=True, is_vendor=True)
    contacts.deactivate_contact(staff, contact_id)
    r = row(world, contact_id)
    assert (r["is_active"], r["customer_code"], r["vendor_code"]) == (0, "AC0001", "VAC0001")


def test_returning_customer_keeps_the_same_code(world, staff):
    contact_id = contacts.create_contact(staff, "Acme", is_customer=True)
    raw(world, "UPDATE contact SET is_customer = 0 WHERE contact_id = ?", (contact_id,))
    assert contacts.make_customer(staff, contact_id) == "AC0001"
    assert row(world, contact_id)["is_customer"] == 1


# --- Five digits -----------------------------------------------------------------------

def test_growth_past_9999(world, staff):
    contacts.create_contact(staff, "Acme", is_customer=True)
    raw(world, "UPDATE sqlite_sequence SET seq = 9998 WHERE name = 'customer_number'")
    nine = contacts.create_contact(staff, "Nine", is_customer=True)
    ten = contacts.create_contact(staff, "Ten", is_customer=True)
    assert row(world, nine)["customer_code"] == "NI9999"
    assert row(world, ten)["customer_code"] == "TE10000"
    by_seq = world.rows("PARENT", "SELECT c.customer_code FROM customer_number n "
                        "JOIN contact c USING (contact_id) ORDER BY n.seq")
    assert [r["customer_code"] for r in by_seq] == ["AC0001", "NI9999", "TE10000"]


# --- CHECKs and triggers ----------------------------------------------------------------

def test_flag_without_code_is_rejected(world):
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, "INSERT INTO contact (name, is_customer) VALUES ('X', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, "INSERT INTO contact (name, is_vendor) VALUES ('X', 1)")


def test_plain_insert_is_not_a_customer(world):
    raw(world, "INSERT INTO contact (name) VALUES ('Plain')")
    assert world.rows("PARENT", "SELECT is_customer FROM contact")[0]["is_customer"] == 0


def test_code_is_unique(world):
    raw(world, "INSERT INTO contact (name, customer_code) VALUES ('A', 'AC0001')")
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, "INSERT INTO contact (name, customer_code) VALUES ('B', 'AC0001')")
    raw(world, "INSERT INTO contact (name, vendor_code) VALUES ('A', 'VAC0001')")
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, "INSERT INTO contact (name, vendor_code) VALUES ('B', 'VAC0001')")


@pytest.mark.parametrize("column,new", [("customer_code", "ZZ0001"), ("customer_code", None),
                                        ("vendor_code", "VZZ0001"), ("vendor_code", None)])
def test_code_cannot_change_once_set(world, column, new):
    raw(world, "INSERT INTO contact (name, customer_code, vendor_code) VALUES ('A', 'AC0001', 'VAC0001')")
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, f"UPDATE contact SET {column} = ?", (new,))


def test_code_can_be_set_once_when_empty(world):
    raw(world, "INSERT INTO contact (name) VALUES ('A')")
    raw(world, "UPDATE contact SET customer_code = 'AC0001', is_customer = 1")
    raw(world, "UPDATE contact SET customer_code = 'AC0001'")     # same value is not a change


def test_coded_contact_cannot_be_deleted_but_uncoded_can(world):
    raw(world, "INSERT INTO contact (name, customer_code, is_customer) VALUES ('A', 'AC0001', 1)")
    raw(world, "INSERT INTO contact (name, vendor_code, is_vendor) VALUES ('B', 'VBB0001', 1)")
    raw(world, "INSERT INTO contact (name) VALUES ('C')")
    for name in ("A", "B"):
        with pytest.raises(sqlite3.IntegrityError):
            raw(world, "DELETE FROM contact WHERE name = ?", (name,))
    raw(world, "DELETE FROM contact WHERE name = 'C'")


def test_sequence_row_needs_a_real_contact_and_is_one_per_contact(world):
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, "INSERT INTO customer_number (contact_id) VALUES (999)")
    raw(world, "INSERT INTO contact (name) VALUES ('A')")
    raw(world, "INSERT INTO customer_number (contact_id) VALUES (1)")
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, "INSERT INTO customer_number (contact_id) VALUES (1)")
    raw(world, "INSERT INTO vendor_number (contact_id) VALUES (1)")


def test_is_employee_column_and_check(world):
    raw(world, "INSERT INTO contact (name, is_employee) VALUES ('Emp', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        raw(world, "INSERT INTO contact (name, is_employee) VALUES ('Bad', 2)")


# --- Permissions -----------------------------------------------------------------------

def test_customer_needs_customer_manage_and_vendor_needs_vendor_manage(world):
    cust, vend = world.user("cust"), world.user("vend")
    world.role("PARENT", "C", ["customer.manage"])
    world.role("PARENT", "V", ["vendor.manage"])
    world.grant(cust, "PARENT", "C")
    world.grant(vend, "PARENT", "V")
    cctx, vctx = world.ctx(cust, "PARENT"), world.ctx(vend, "PARENT")
    contacts.create_contact(cctx, "Acme", is_customer=True)
    contacts.create_contact(vctx, "Bolt", is_vendor=True)
    with pytest.raises(PermissionDeniedError):
        contacts.create_contact(cctx, "Nope Vendor", is_vendor=True)
    with pytest.raises(PermissionDeniedError):
        contacts.create_contact(vctx, "Nope Customer", is_customer=True)
    target = contacts.create_contact(cctx, "Plain")
    with pytest.raises(PermissionDeniedError):
        contacts.make_vendor(cctx, target)
    with pytest.raises(PermissionDeniedError):
        contacts.make_customer(vctx, target)
    names = [r["name"] for r in world.rows("PARENT", "SELECT name FROM contact ORDER BY contact_id")]
    assert names == ["Acme", "Bolt", "Plain"]
    assert world.events("PARENT")  # the denials are logged


def test_user_without_either_permission_can_do_nothing(world):
    user_id = world.user("nobody")
    world.role("PARENT", "N", ["ledger.view"])
    world.grant(user_id, "PARENT", "N")
    ctx = world.ctx(user_id, "PARENT")
    for call in (lambda: contacts.create_contact(ctx, "X"),
                 lambda: contacts.find_duplicates(ctx, "X"),
                 lambda: contacts.update_contact(ctx, 1, name="Y"),
                 lambda: contacts.deactivate_contact(ctx, 1)):
        with pytest.raises(PermissionDeniedError):
            call()


def test_agent_origin_cannot_manage_contacts(world, staff):
    agent = world.ctx(staff.user_id, "PARENT", origin="Agent")
    assert "customer.manage" not in permissions.AGENT_ALLOWED
    with pytest.raises(PermissionDeniedError):
        contacts.create_contact(agent, "Acme", is_customer=True)
    assert count(world, "contact") == 0


def test_other_company_user_is_denied(world, staff):
    stranger = world.user("stranger")
    world.role("OTHER", "S", ["customer.manage"])
    world.grant(stranger, "OTHER", "S")
    with pytest.raises(PermissionDeniedError):
        contacts.create_contact(world.ctx(stranger, "PARENT"), "Acme", is_customer=True)


# --- Duplicates --------------------------------------------------------------------------

def test_duplicate_found_by_name_ignoring_case_accents_and_punctuation(world, staff):
    contacts.create_contact(staff, "Café Müller, Inc.", is_customer=True)
    matches = contacts.find_duplicates(staff, "CAFE MULLER INC")
    assert len(matches) == 1 and "name" in matches[0]["matched_on"]


def test_duplicate_found_by_tax_id_and_by_email(world, staff):
    contacts.create_contact(staff, "Acme", tax_id="12-3456789", email="Bill@Acme.com", is_customer=True)
    assert contacts.find_duplicates(staff, "Other name", tax_id="123456789")[0]["matched_on"] == ["tax_id"]
    assert contacts.find_duplicates(staff, "Other name", email="bill@acme.COM")[0]["matched_on"] == ["email"]
    assert contacts.find_duplicates(staff, "Other name", tax_id="99-9999999", email="x@y.z") == []


def test_blank_tax_id_and_email_never_match(world, staff):
    contacts.create_contact(staff, "Acme", is_customer=True)
    contacts.create_contact(staff, "Beta", is_customer=True)
    assert contacts.find_duplicates(staff, "Gamma", tax_id="", email="  ") == []


def test_create_with_a_duplicate_needs_explicit_confirmation(world, staff):
    contacts.create_contact(staff, "Acme Corp", is_customer=True)
    with pytest.raises(contacts.DuplicateContactError) as caught:
        contacts.create_contact(staff, "ACME corp", is_customer=True)
    assert len(caught.value.matches) == 1
    assert count(world, "contact") == 1
    assert count(world, "customer_number") == 1   # no sequence number was consumed
    second = contacts.create_contact(staff, "ACME corp", is_customer=True, confirm_duplicates=True)
    assert row(world, second)["customer_code"] == "AC0002"


def test_no_duplicate_means_no_confirmation_needed(world, staff):
    contacts.create_contact(staff, "Acme", is_customer=True)
    contacts.create_contact(staff, "Beta", is_customer=True)


def test_tax_ids_are_masked_without_view_tax_ids(world, staff):
    contacts.create_contact(staff, "Acme", tax_id="12-3456789", is_customer=True)
    shown = contacts.find_duplicates(staff, "Acme")[0]
    assert shown["tax_id"] == "***-**-6789" and "123456789" not in str(shown)
    assert not any("bank" in key for key in shown)

    viewer = world.user("auditor")
    world.role("PARENT", "T", ["customer.manage", "view.tax_ids"])
    world.grant(viewer, "PARENT", "T")
    assert contacts.find_duplicates(world.ctx(viewer, "PARENT"), "Acme")[0]["tax_id"] == "12-3456789"


def test_duplicate_error_matches_are_masked_too(world, staff):
    contacts.create_contact(staff, "Acme", tax_id="12-3456789", is_customer=True)
    with pytest.raises(contacts.DuplicateContactError) as caught:
        contacts.create_contact(staff, "Acme", is_customer=True)
    assert caught.value.matches[0]["tax_id"] == "***-**-6789"


def test_inactive_contacts_still_count_as_duplicates(world, staff):
    first = contacts.create_contact(staff, "Acme", is_customer=True)
    contacts.deactivate_contact(staff, first)
    assert contacts.find_duplicates(staff, "Acme")[0]["is_active"] == 0


def test_employee_contact_can_be_created(world, staff):
    contacts.create_contact(staff, "Pat Worker", is_employee=True)
