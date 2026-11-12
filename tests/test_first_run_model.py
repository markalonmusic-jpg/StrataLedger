"""first_run_model.py: routing, form checks and wording for the first-run setup (decision S10)."""
import pytest

import modules.database as database
from modules import first_run_model as model
from modules.database import SchemaUpgradeBlockedError
from modules.services import auth
from modules.services.errors import PermissionDeniedError, ServiceError, ValidationError


def draft(**changes):
    d = model.Draft(username="root", first_name="Rita", last_name="Root", email="rita@example.com",
                    password="correct horse battery", repeat="correct horse battery")
    for name, value in changes.items():
        setattr(d, name, value)
    return d


# --- Routing (the stated mapping) ---------------------------------------------------------------------

def test_the_route_mapping_is_exactly_this():
    assert model.STATE_ROUTES == {"missing": "first_run", "no_users": "first_run", "ready": "launcher",
                                  "unreadable": "error"}


@pytest.fixture
def master(tmp_path, backup_dir):
    return tmp_path / "system_master.db"


def test_no_file_goes_to_first_run(master):
    assert model.startup_route(master) == "first_run"
    assert model.startup_check(master) == ("first_run", None)


def test_file_without_users_goes_to_first_run(master):
    database.ensure_master_database(master)
    assert model.startup_route(master) == "first_run"


def test_file_with_users_goes_to_the_launcher(master):
    database.ensure_master_database(master)
    auth.create_first_master(str(master), "root", "correct horse battery", "Root", "User", "r@x.test")
    assert model.startup_route(master) == "launcher"


def test_unreadable_file_goes_to_the_error_dialog(master):
    master.write_bytes(b"not a database " * 40)
    assert model.startup_check(master) == ("error", "DatabaseError")


def test_a_built_file_whose_master_creation_failed_goes_back_to_first_run(master, monkeypatch):
    database.ensure_master_database(master)

    def fail(*args, **kwargs):
        raise ValidationError("boom")
    monkeypatch.setattr(auth, "create_first_master", fail)
    with pytest.raises(ValidationError):
        auth.create_first_master(str(master), "root", "correct horse battery", "Root", "User", "r@x.test")
    assert master.exists() and model.startup_route(master) == "first_run"


# --- The form (S10: username, first/last name, email, password twice, 12+ characters) ----------------

def test_a_good_form_has_no_problems():
    assert model.validate(draft()) == []


@pytest.mark.parametrize("field,value", [
    ("username", ""), ("username", "ab"), ("username", "has space"), ("username", "x" * 65), ("username", "bad!name"),
    ("first_name", ""), ("first_name", "   "), ("last_name", ""), ("email", ""), ("email", "no-at-sign"),
    ("email", "@example.com"), ("email", "a b@example.com"),
])
def test_each_identity_field_is_checked(field, value):
    problems = model.validate(draft(**{field: value}))
    assert problems and all(p.endswith(".") for p in problems)


@pytest.mark.parametrize("password", ["short", "x" * 11, ""])
def test_password_needs_12_characters(password):
    problems = model.validate(draft(password=password, repeat=password))
    assert any("12 characters" in p for p in problems)


def test_exactly_12_characters_is_enough():
    assert model.validate(draft(password="abcdefghijkl", repeat="abcdefghijkl")) == []


def test_password_cannot_be_only_spaces():
    problems = model.validate(draft(password=" " * 14, repeat=" " * 14))
    assert any("only spaces" in p for p in problems)


def test_password_whitespace_is_never_stripped():
    padded = "  correct horse battery  "
    assert model.validate(draft(password=padded, repeat=padded)) == []
    assert model.validate(draft(password=padded, repeat=padded.strip()))          # the two must match exactly
    d = draft(password=padded, repeat=padded)
    model.validate(d)
    assert d.password == padded and model.sign_in_secret(d) == padded


def test_password_must_be_entered_twice_identically():
    assert any("match" in p for p in model.validate(draft(repeat="correct horse batterY")))
    assert any("match" in p for p in model.validate(draft(repeat="")))


def test_password_cannot_equal_the_username_ignoring_case():
    problems = model.validate(draft(username="administrator1", password="ADMINISTRATOR1", repeat="ADMINISTRATOR1"))
    assert any("username" in p.lower() for p in problems)
    assert model.validate(draft(username="administrator1", password=" administrator1", repeat=" administrator1")) == []


@pytest.mark.parametrize("length,accepted", [(1023, True), (1024, True), (1025, False)])
def test_password_maximum_boundary(length, accepted):
    password = "x" * length
    problems = model.validate(draft(password=password, repeat=password))
    assert (problems == []) is accepted
    if not accepted:
        assert any("1024" in p for p in problems)


def test_password_has_a_maximum_length():
    long = "x" * 1025
    assert any("1024" in p for p in model.validate(draft(password=long, repeat=long)))


def test_no_composition_rules():
    for simple in ("aaaaaaaaaaaa", "123456789012", "alllowercaseletters"):
        assert model.validate(draft(password=simple, repeat=simple)) == []


def test_every_problem_is_listed_at_once():
    problems = model.validate(draft(username="", email="x", password="short", repeat="other"))
    assert len(problems) >= 4


# --- Continue is gated by the checkbox -------------------------------------------------------------------

@pytest.mark.parametrize("shown,ticked,allowed", [(True, True, True), (True, False, False), (False, True, False),
                                                  (False, False, False)])
def test_continue_needs_the_code_shown_and_the_box_ticked(shown, ticked, allowed):
    assert model.can_continue(code_shown=shown, acknowledged=ticked) is allowed


def test_codes_are_compared_without_dashes_and_case():
    assert model.same_code("abcd-efgh-ijkl", "ABCDEFGHIJKL")
    assert model.same_code("  ABCD-EFGH\n", "ABCD-EFGH")
    assert not model.same_code("ABCD-EFGH", "ABCD-EFGX")
    assert not model.same_code("", "ABCD") and not model.same_code(None, "ABCD")


# --- Wording ------------------------------------------------------------------------------------------------

def test_unreadable_file_message_names_the_file_and_promises_no_changes():
    title, message = model.unreadable_message(r"C:\Data\system_master.db")
    assert r"C:\Data\system_master.db" in message
    assert "older version or damaged" in message
    assert "not changed" in message.lower() or "nothing was changed" in message.lower()
    assert "delete" not in message.lower() or "do not delete" in message.lower()
    assert title


@pytest.mark.parametrize("error,fragment", [
    (ValidationError("The first Master can only be created while there are no users"), "no users"),
    (PermissionDeniedError("Not permitted"), "permission"),
    (SchemaUpgradeBlockedError("x.db", "This database was built from a different schema baseline."), "older version"),
    (ServiceError("odd"), "odd"),
])
def test_known_errors_get_a_title_and_a_next_step(error, fragment):
    title, message = model.explain_error(error)
    assert title and fragment.lower() in message.lower() and message.rstrip().endswith(".")


def test_unexpected_errors_never_show_their_text():
    secret = "correct horse battery 7K3Q-ABCD"
    title, message = model.explain_error(RuntimeError(f"failed with {secret}"))
    assert secret not in message and "log" in message.lower()
