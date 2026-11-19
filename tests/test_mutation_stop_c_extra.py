"""Mutation-test additions for STOP C (custom fields): one test per mutant the main file let survive."""
import pytest

from modules.services import custom_fields as cf
from modules.services import permissions
from modules.services.errors import NotFoundError, PermissionDeniedError, ValidationError
from tests import ledger_helpers as lh
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_custom_fields import (_Raw, admin, contact, ctx_with, invoice, rows, snapshot,  # noqa: F401
                                      typed, user_with, value_of)


def test_the_fields_manage_seed_row_is_sensitive(world):
    assert rows(world, "SELECT is_sensitive FROM permission WHERE permission_code = 'fields.manage'") == \
        [{"is_sensitive": 1}]


def test_a_label_and_a_choice_of_exactly_80_characters_are_accepted(admin):
    cf.define_field(admin, "Project", label="x" * 80, data_type="Text")
    field = cf.define_field(admin, "Project", label="Pick", data_type="Choice", choices=["y" * 80])
    assert field["choices"][0]["value"] == "y" * 80


def test_a_text_value_of_exactly_2000_characters_is_accepted(world, admin, typed):
    cf.set_value(admin, "Project", typed, "note", "t" * 2000)
    with pytest.raises(ValidationError):
        cf.set_value(admin, "Project", typed, "note", "t" * 2001)


def test_a_spaced_out_bank_word_is_refused_on_a_contact_field(admin):
    with pytest.raises(ValidationError, match="bank"):
        cf.define_field(admin, "Contact", label="I.B.A.N", data_type="Text")


def test_renaming_a_non_contact_field_to_a_bank_looking_name_is_allowed(admin):
    field = cf.define_field(admin, "Invoice", label="Reference", data_type="Text")
    assert cf.update_field(admin, field["field_id"], label="Routing number")["label"] == "Routing number"


def test_yes_no_is_refused_for_a_number_field(world, admin, typed):
    with pytest.raises(ValidationError, match="takes a number"):
        cf.set_value(admin, "Project", typed, "kw", True)
    with pytest.raises(ValidationError, match="whole cents"):
        cf.set_value(admin, "Project", typed, "fee", True)
    assert rows(world, "SELECT * FROM custom_field_value") == []


def test_a_date_with_trailing_text_is_refused_as_not_a_date(admin, typed):
    with pytest.raises(ValidationError, match="takes a date"):
        cf.set_value(admin, "Project", typed, "pto", "2026-01-31x")


def test_yes_no_reads_back_as_a_real_bool(admin, typed):
    cf.set_value(admin, "Project", typed, "hoa", False)
    value = value_of(cf.get_values(admin, "Project", typed), "hoa")
    assert value is False
    cf.set_value(admin, "Project", typed, "hoa", True)
    assert value_of(cf.get_values(admin, "Project", typed), "hoa") is True


def test_an_inactive_field_without_a_value_is_not_listed_in_values(admin, typed):
    field = next(f for f in cf.list_fields(admin, "Project") if f["field_key"] == "note")
    cf.deactivate_field(admin, field["field_id"])
    assert "note" not in [v["field_key"] for v in cf.get_values(admin, "Project", typed)]


@pytest.mark.parametrize("kind,first", [({"customer": True}, "ar.view"), ({"vendor": True}, "ap.view"),
                                        ({}, "ar.view")])
def test_a_denied_contact_read_logs_the_first_code_of_its_group(world, kind, first):
    record = contact(world, **kind)
    with pytest.raises(PermissionDeniedError):
        cf.get_values(ctx_with(world, "nobody", ["period.view"]), "Contact", record)
    assert world.events("PARENT")[-1]["permission_code"] == first


def test_a_denied_list_logs_the_record_type_view_code_not_fields_manage(world):
    with pytest.raises(PermissionDeniedError):
        cf.list_fields(ctx_with(world, "nobody", ["period.view"]), "Invoice")
    assert world.events("PARENT")[-1]["permission_code"] == "ar.view"


def test_a_choice_listed_again_in_another_case_keeps_one_spelling_and_no_inactive_copy(world, admin):
    project = world.project("PARENT")
    field = cf.define_field(admin, "Project", label="Roof", data_type="Choice", choices=["Tile", "Metal"])
    cf.set_value(admin, "Project", project, "roof", "Tile")
    updated = cf.update_field(admin, field["field_id"], choices=["tile", "metal"])
    assert updated["choices"] == [{"value": "Tile", "active": True}, {"value": "Metal", "active": True}]


def test_update_refuses_an_unknown_data_type_with_a_sentence(admin):
    field = cf.define_field(admin, "Project", label="Note", data_type="Text")
    with pytest.raises(ValidationError):
        cf.update_field(admin, field["field_id"], data_type="Bogus")


def test_a_no_op_update_writes_no_audit_row(world, admin):
    field = cf.define_field(admin, "Project", label="Utility", data_type="Text")
    before = snapshot(world)
    assert cf.update_field(admin, field["field_id"], label="Utility", is_required=False) == field
    assert snapshot(world) == before


def test_an_unposted_entry_document_may_change_while_lock_is_on(world, admin):
    with _Raw(world) as c:
        entry_id = lh.make_entry(c, [(1000, 0), (0, 1000)])          # a draft entry, not posted
        record = lh.make_invoice(c, itype="Invoice", status="Sent", entry_id=entry_id)
        c.execute("INSERT INTO company_settings (id, company_name, fiscal_year_start, lock_documents_after_posting) "
                  "VALUES (1, 'P', '01-01', 1) ON CONFLICT (id) DO UPDATE SET lock_documents_after_posting = 1")
        lh.set_period_closed(c, c.execute("SELECT period_id FROM journal_entry WHERE entry_id = ?",
                                          (entry_id,)).fetchone()[0], True)
    cf.define_field(admin, "Invoice", label="Po ref", data_type="Text")
    cf.set_value(admin, "Invoice", record, "po_ref", "PO-1")


def test_one_field_holds_separate_values_per_record(world, admin):
    first, second = world.project("PARENT"), world.project("PARENT")
    cf.define_field(admin, "Project", label="Note", data_type="Text")
    cf.set_value(admin, "Project", first, "note", "one")
    cf.set_value(admin, "Project", second, "note", "two")
    assert value_of(cf.get_values(admin, "Project", first), "note") == "one"
    assert value_of(cf.get_values(admin, "Project", second), "note") == "two"
    cf.set_value(admin, "Project", second, "note", None)
    assert value_of(cf.get_values(admin, "Project", first), "note") == "one"


def test_a_missing_record_is_reported_before_an_unknown_field(world, admin):
    with pytest.raises(NotFoundError, match="does not exist"):
        cf.set_value(admin, "Project", 9999, "nope", "x")


def test_the_record_is_checked_again_inside_the_write_transaction(world, admin, monkeypatch):
    cf.define_field(admin, "Project", label="Note", data_type="Text")
    monkeypatch.setattr(cf, "_read_record", lambda *a: {"project_id": 9999})     # the early lookup is fooled
    with pytest.raises(NotFoundError):
        cf.set_value(admin, "Project", 9999, "note", "x")
