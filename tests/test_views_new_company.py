"""The New Company screen (decisions S5, S8, H6; docs/CLAUDE_UI.md section 1).

Static checks always run. The Tk tests build the real widgets in a hidden window and drive the wizard through its
controller, with the modal dialogs replaced so nothing blocks.
"""
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
from modules.services import companies
from tests.authz_world import world  # noqa: F401  (fixture)

VIEW = Path(__file__).resolve().parent.parent / "modules" / "views_new_company.py"


# --- Static rules for a view ---------------------------------------------------------------------------

def _code_lines():
    text = VIEW.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if not line.strip().startswith("#")]


def test_view_has_no_sql_dialogs_prints_or_colors():
    text = "\n".join(_code_lines())
    assert "sqlite3" not in text and "execute(" not in text                      # rule 2: no SQL in a view
    assert "messagebox" not in text                                              # dialogs are the shared modal
    assert not re.search(r"(?<![\w.])print\(", text)                             # rule 5
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), "hardcoded color"        # rule 3 / H6: Theme tokens only
    assert not re.search(r"\b(rgb|rgba|hsl)\(", text)


def test_view_uses_only_theme_tokens_that_exist():
    from config import Theme
    # type(Theme): the font properties need a Tk window, so check the names without evaluating them.
    for name in set(re.findall(r"Theme\.([a-z_]+)", VIEW.read_text(encoding="utf-8"))):
        assert hasattr(type(Theme), name), name


def test_the_shared_dialog_tokens_exist():
    from config import Theme
    assert Theme.radius_lg > 0 and Theme.warning_glow
    import modules.ui_components  # noqa: F401  (imports only if every token it uses exists)


def test_view_calls_the_services_not_the_database():
    text = VIEW.read_text(encoding="utf-8")
    assert "companies.create_company" in text and "auth.login" in text and "creation_options" in text
    assert "company_profile" not in text


# --- The real widgets -------------------------------------------------------------------------------

@pytest.fixture
def tk_root(tk_app):
    """The session's hidden window; widgets a test creates in it are removed afterwards."""
    yield tk_app
    for child in tk_app.winfo_children():
        child.destroy()


class FakeApp:
    """The few things the screen needs from the main window."""

    def __init__(self, master_path, session=None):
        self.master_db_path = str(master_path)
        self.session = session
        self.calls = []

    def show_no_company_open_screen(self):
        self.calls.append(("launcher",))

    def open_company_workspace(self, company_id, company_name):
        self.calls.append(("open", company_id, company_name))

    def reset_session(self):
        self.calls.append(("reset",))
        self.session = None


@pytest.fixture
def dialogs(monkeypatch):
    from modules import views_new_company as view
    shown = SimpleNamespace(errors=[], infos=[], confirms=[], answer=True)
    monkeypatch.setattr(view, "show_error", lambda parent, title, message, details=None: shown.errors.append((title, message)))
    monkeypatch.setattr(view, "show_info", lambda parent, title, message: shown.infos.append((title, message)))

    def confirm(parent, title, message, confirm_text="Confirm", cancel_text="Cancel", destructive=False):
        shown.confirms.append((title, message, confirm_text, cancel_text))
        return shown.answer
    monkeypatch.setattr(view, "ask_confirm", confirm)
    return shown


def start(tk_root, app):
    from modules import views_new_company as view
    import customtkinter as ctk
    holder = ctk.CTkFrame(tk_root)
    holder.pack()
    return view.render_create_company_form(app, holder)


def fill_step_one(wizard, name="Acme Builders", **extra):
    wizard.vars["legal_name"].set(name)
    wizard.on_name_changed()
    for key, value in extra.items():
        wizard.vars[key].set(value)


def test_master_signs_in_on_the_screen_and_creates_a_company(world, tk_root, dialogs):
    master = world.user("root", master=True)
    app = FakeApp(world.master)
    wizard = start(tk_root, app)
    assert wizard.stage == "sign_in" and app.session is None
    assert wizard.sign_in("root", "wrong password here") is False
    assert wizard.sign_in("root", "correct horse battery") is True
    assert app.session is not None and wizard.stage == "wizard" and wizard.step == 0
    assert master == app.session.user_id

    fill_step_one(wizard)
    assert wizard.vars["code"].get() == "ACME"
    wizard.next()
    assert wizard.step == 1 and wizard.vars["first_year"].get() == wizard.draft.first_year
    wizard.vars["start_month"].set("July")
    wizard.vars["first_year"].set("2027")
    wizard.next()
    assert wizard.step == 2
    wizard.vars["chart_source"].set("general")
    wizard.next()
    assert wizard.step == 3
    wizard.submit()
    assert dialogs.errors == []
    assert os.path.isfile(os.path.join(config.BASE_PROJECT_DIR, "Companies", "ACME.db"))
    assert dialogs.confirms and "Open now" in dialogs.confirms[0]
    assert app.calls[-1][0] == "open" and app.calls[-1][2] == "Acme Builders"
    created = world.master_rows("SELECT * FROM company_registry WHERE company_code = 'ACME'")[0]
    assert app.calls[-1][1] == created["company_id"]


def test_declining_to_open_returns_to_the_launcher_and_signs_out(world, tk_root, dialogs):
    world.user("root", master=True)
    app = FakeApp(world.master)
    wizard = start(tk_root, app)
    wizard.sign_in("root", "correct horse battery")
    fill_step_one(wizard)
    for _ in range(3):
        wizard.next()
    dialogs.answer = False
    wizard.submit()
    assert [c[0] for c in app.calls][-2:] == ["reset", "launcher"]
    assert os.path.isfile(os.path.join(config.BASE_PROJECT_DIR, "Companies", "ACME.db"))


def test_step_checks_block_next_and_say_what_to_do(world, tk_root, dialogs):
    world.user("root", master=True)
    wizard = start(tk_root, FakeApp(world.master))
    wizard.sign_in("root", "correct horse battery")
    wizard.next()                                           # nothing entered yet
    assert wizard.step == 0 and dialogs.errors
    title, message = dialogs.errors[-1]
    assert "legal name" in message.lower()
    fill_step_one(wizard)
    wizard.next()
    wizard.vars["first_year"].set("27")
    wizard.next()
    assert wizard.step == 1 and "four digits" in dialogs.errors[-1][1]


def test_back_keeps_the_answers(world, tk_root, dialogs):
    world.user("root", master=True)
    wizard = start(tk_root, FakeApp(world.master))
    wizard.sign_in("root", "correct horse battery")
    fill_step_one(wizard, tax_id="12-3456789")
    wizard.next()
    wizard.back()
    assert wizard.step == 0 and wizard.vars["legal_name"].get() == "Acme Builders"
    assert wizard.vars["tax_id"].get() == "12-3456789"


def test_country_changes_the_defaults(world, tk_root, dialogs):
    world.user("root", master=True)
    wizard = start(tk_root, FakeApp(world.master))
    wizard.sign_in("root", "correct horse battery")
    wizard.vars["country"].set("Philippines")
    wizard.on_country_changed()
    assert wizard.draft.currency == "PHP" and wizard.draft.timezone == "Asia/Manila"
    fill_step_one(wizard)
    wizard.next()
    assert wizard.vars["timezone"].get() == "Asia/Manila"


def test_a_service_error_shows_a_dialog_and_stays_on_the_last_step(world, tk_root, dialogs):
    world.user("root", master=True)
    existing = companies.create_company(world.session(world.master_rows(
        "SELECT user_id FROM app_user WHERE username = 'root'")[0]["user_id"]), legal_name="Taken",
        code="ACME", first_fiscal_year=2027, template="general")
    assert existing["company_code"] == "ACME"
    app = FakeApp(world.master)
    wizard = start(tk_root, app)
    wizard.sign_in("root", "correct horse battery")
    fill_step_one(wizard)
    for _ in range(3):
        wizard.next()
    wizard.submit()
    assert wizard.step == 3 and app.calls == []
    title, message = dialogs.errors[-1]
    assert "already used" in message and "different" in message and "Nothing was created" in message
    assert not dialogs.confirms


def test_only_the_master_or_an_admin_with_a_parent_can_open_the_screen(world, tk_root, dialogs):
    world.user("nobody")
    app = FakeApp(world.master)
    wizard = start(tk_root, app)
    assert wizard.sign_in("nobody", "correct horse battery") is True
    assert wizard.stage == "closed"
    assert dialogs.infos and "Master" in dialogs.infos[0][1]
    assert [c[0] for c in app.calls][-2:] == ["reset", "launcher"]


def test_parent_admin_creates_a_subsidiary_with_the_parents_chart(world, tk_root, dialogs):
    master_user = world.user("root", master=True)
    boss = world.user("boss")
    parent = companies.create_company(world.session(master_user), legal_name="Parent Co", code="PARENTCO",
                                      first_fiscal_year=2027, template="general", admin_user_id=boss)
    app = FakeApp(world.master)
    wizard = start(tk_root, app)
    assert wizard.sign_in("boss", "correct horse battery") is True
    assert [c["company_id"] for c in wizard.options["parents"]] == [parent["company_id"]]
    assert wizard.options["top_level"] is False
    assert "None" not in " ".join(wizard.parent_labels)                    # a top-level company is not offered
    fill_step_one(wizard, name="Field Works")
    wizard.vars["parent"].set(wizard.parent_labels[0])
    wizard.on_parent_changed()
    assert wizard.draft.parent_company_id == parent["company_id"] and wizard.draft.chart_source == "copy"
    for _ in range(3):
        wizard.next()
    wizard.submit()
    assert dialogs.errors == []
    child = world.master_rows("SELECT * FROM company_registry WHERE company_code = 'FIELD'")
    assert child and child[0]["parent_company_id"] == parent["company_id"]


def test_chart_csv_file_is_read_and_checked(world, tk_root, dialogs, tmp_path):
    world.user("root", master=True)
    wizard = start(tk_root, FakeApp(world.master))
    wizard.sign_in("root", "correct horse battery")
    bad = tmp_path / "bad.csv"
    bad.write_text("account_number,name\n1000,Cash\n", encoding="utf-8")
    wizard.load_csv_file(str(bad))
    assert wizard.draft.chart_source == "csv"
    assert wizard.draft.chart_csv_text.startswith("account_number")
    fill_step_one(wizard)
    wizard.next()
    wizard.next()
    wizard.next()
    assert wizard.step == 2 and "chart file" in dialogs.errors[-1][1].lower()


def test_cancel_signs_out_only_if_it_signed_in(world, tk_root, dialogs):
    world.user("root", master=True)
    app = FakeApp(world.master)
    wizard = start(tk_root, app)
    wizard.sign_in("root", "correct horse battery")
    wizard.cancel()
    assert [c[0] for c in app.calls] == ["reset", "launcher"]

    other = FakeApp(world.master, session=world.session(world.master_rows(
        "SELECT user_id FROM app_user WHERE username = 'root'")[0]["user_id"]))
    again = start(tk_root, other)
    assert again.stage == "wizard"                                           # already signed in: no sign-in step
    again.cancel()
    assert [c[0] for c in other.calls] == ["launcher"]


def test_the_shared_dialogs_build_with_real_widgets(tk_root):
    from modules.ui_components import StrataModal
    for kind in ("info", "success", "warning", "error", "confirm"):
        modal = StrataModal(tk_root, title="Title", message="Message", kind=kind, confirm_text="OK",
                            cancel_text="Cancel" if kind == "confirm" else None)
        modal.update_idletasks()
        modal.destroy()
