"""The first-run setup screen (decision S10): welcome, create the Master, show the recovery code once, sign in."""
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from tkinter import TclError

import modules.database as database
from modules import first_run_model as model
from modules import views_first_run as view
from modules.services import auth, logging_setup, passwords
from modules.services.errors import ValidationError

VIEW = Path(__file__).resolve().parent.parent / "modules" / "views_first_run.py"
PASSWORD = "correct horse battery"


# --- Static rules for a view ---------------------------------------------------------------------------

def test_view_has_no_sql_dialogs_prints_or_colors():
    text = "\n".join(l for l in VIEW.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("#"))
    assert "sqlite3" not in text and "execute(" not in text
    assert "messagebox" not in text
    assert not re.search(r"(?<![\w.])print\(", text)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), "hardcoded color"
    assert not re.search(r"\b(rgb|rgba|hsl)\(", text)


def test_view_uses_only_theme_tokens_that_exist():
    from config import Theme
    for name in set(re.findall(r"Theme\.([a-z_]+)", VIEW.read_text(encoding="utf-8"))):
        assert hasattr(type(Theme), name), name


def test_view_declares_its_page_key():
    assert view.PAGE_KEY == "setup.first_run"


def test_view_never_logs_the_password_or_the_code():
    text = VIEW.read_text(encoding="utf-8")
    for line in (l for l in text.splitlines() if "_logger." in l):
        assert "password" not in line.lower() and "code" not in line.lower().replace("error_code", ""), line


# --- The real widgets ------------------------------------------------------------------------------------

class FakeApp:
    """The few things the screen needs from the main window."""

    def __init__(self, master_path):
        self.master_db_path = str(master_path)
        self.session = None
        self.startup_failed = False
        self.calls = []
        self.protocols = {}

    def protocol(self, name, func):
        self.protocols[name] = func

    def destroy(self):
        self.calls.append(("destroy",))

    def show_no_company_open_screen(self):
        self.calls.append(("launcher",))

    def create_new_company_file(self):
        self.calls.append(("new_company", self.session is not None))

    def reset_session(self):
        self.calls.append(("reset",))
        self.session = None


@pytest.fixture
def tk_root(tk_app):
    yield tk_app
    for child in tk_app.winfo_children():
        child.destroy()


@pytest.fixture
def dialogs(monkeypatch):
    shown = SimpleNamespace(errors=[], infos=[], confirms=[], answer=True)
    monkeypatch.setattr(view, "show_error", lambda parent, title, message, details=None: shown.errors.append((title, message)))

    def confirm(parent, title, message, confirm_text="Confirm", cancel_text="Cancel", destructive=False):
        shown.confirms.append((title, message, confirm_text, cancel_text))
        return shown.answer
    monkeypatch.setattr(view, "ask_confirm", confirm)
    return shown


@pytest.fixture
def setup(tmp_path, backup_dir, tk_root, dialogs, monkeypatch):
    import config
    import customtkinter as ctk
    monkeypatch.setattr(config, "BASE_PROJECT_DIR", str(tmp_path))
    master = tmp_path / "system_master.db"
    app = FakeApp(master)
    holder = ctk.CTkFrame(tk_root)
    holder.pack()
    wizard = view.render_first_run(app, holder)
    return SimpleNamespace(app=app, wizard=wizard, master=master, holder=holder, dialogs=dialogs, tmp=tmp_path)


def fill(wizard, **changes):
    values = dict(username="root", first_name="Rita", last_name="Root", email="rita@example.com",
                  password=PASSWORD, repeat=PASSWORD)
    values.update(changes)
    for key, value in values.items():
        wizard.vars[key].set(value)


def users(master):
    import sqlite3
    conn = sqlite3.connect(master)
    try:
        return conn.execute("SELECT username, is_master FROM app_user").fetchall()
    finally:
        conn.close()


# --- Starting and leaving -----------------------------------------------------------------------------------

def test_the_screen_starts_on_the_form_and_creates_nothing(setup):
    assert setup.wizard.stage == "form"
    assert not setup.master.exists()
    assert setup.app.protocols["WM_DELETE_WINDOW"] == setup.wizard.on_window_close


def test_exit_button_closes_the_app_and_creates_nothing(setup):
    setup.wizard.exit_app()
    assert setup.app.calls == [("destroy",)]
    assert not setup.master.exists()


def test_closing_the_window_before_submit_is_the_same_as_exit(setup):
    fill(setup.wizard)                                    # even with a filled-in form
    setup.app.protocols["WM_DELETE_WINDOW"]()
    assert setup.app.calls == [("destroy",)]
    assert not setup.master.exists() and setup.dialogs.confirms == []


def test_the_welcome_text_explains_the_setup(setup):
    assert "Master" in setup.wizard.welcome_text and "recovery code" in setup.wizard.welcome_text.lower()


# --- Invalid input never creates a file ------------------------------------------------------------------------

@pytest.mark.parametrize("changes", [
    {"password": "short", "repeat": "short"}, {"repeat": "different password!"}, {"username": ""},
    {"email": "nope"}, {"first_name": ""}, {"password": "root" * 3, "repeat": "root" * 3, "username": "ROOTROOTROOT"},
])
def test_invalid_submit_leaves_no_file_and_does_not_touch_the_database_module(setup, changes, monkeypatch):
    monkeypatch.setattr(view.database, "ensure_master_database",
                        lambda *a, **k: pytest.fail("the form must be checked before any file is built"))
    fill(setup.wizard, **changes)
    setup.wizard.submit()
    assert setup.wizard.stage == "form" and setup.dialogs.errors
    assert not setup.master.exists()


def test_errors_list_every_problem_in_one_dialog(setup):
    fill(setup.wizard, username="", email="x", password="short", repeat="other")
    setup.wizard.submit()
    title, message = setup.dialogs.errors[-1]
    assert message.count("\n") >= 3 and not setup.master.exists()


# --- The whole happy path ---------------------------------------------------------------------------------------------

def make_master(setup):
    fill(setup.wizard)
    setup.wizard.submit()


def test_submit_builds_the_master_and_shows_the_code_screen(setup):
    make_master(setup)
    assert setup.dialogs.errors == []
    assert users(setup.master) == [("root", 1)]
    assert setup.wizard.stage == "code" and setup.wizard.code_shown
    code = setup.wizard.vars["code"].get()
    assert re.fullmatch(r"([A-Z2-7]{4}-){7}[A-Z2-7]{4}", code)
    assert auth.master_setup_state(setup.master) == "ready"


def test_continue_is_refused_until_the_box_is_ticked(setup):
    make_master(setup)
    assert str(setup.wizard.continue_button.cget("state")) == "disabled"
    assert setup.wizard.continue_() is False
    assert setup.app.session is None and setup.dialogs.confirms == []
    setup.wizard.vars["acknowledged"].set(True)
    setup.wizard.on_ack_changed()
    assert str(setup.wizard.continue_button.cget("state")) == "normal"
    setup.wizard.vars["acknowledged"].set(False)
    setup.wizard.on_ack_changed()
    assert str(setup.wizard.continue_button.cget("state")) == "disabled"
    assert setup.wizard.continue_() is False


def finish(setup, answer=True):
    make_master(setup)
    setup.dialogs.answer = answer
    setup.wizard.vars["acknowledged"].set(True)
    setup.wizard.on_ack_changed()
    return setup.wizard.continue_()


def test_continue_signs_in_and_offers_the_first_company(setup):
    assert finish(setup) is True
    assert setup.app.session is not None and setup.app.session.is_master and setup.app.session.username == "root"
    title, message, yes, no = setup.dialogs.confirms[-1]
    assert (yes, no) == ("Create your first company", "Later")
    assert setup.app.calls[-1] == ("new_company", True)          # signed in already: no second sign-in
    assert setup.wizard.stage == "closed"


def test_later_signs_out_and_shows_the_launcher(setup):
    assert finish(setup, answer=False) is True
    assert [c[0] for c in setup.app.calls][-2:] == ["reset", "launcher"]
    assert setup.app.session is None


def test_the_window_close_handler_is_restored_when_setup_is_over(setup):
    finish(setup)
    assert setup.app.protocols["WM_DELETE_WINDOW"] == setup.app.destroy


def test_password_and_code_references_are_dropped_after_sign_in(setup):
    make_master(setup)
    assert setup.wizard._password == PASSWORD and setup.wizard._code      # kept only until the sign-in
    setup.wizard.vars["acknowledged"].set(True)
    setup.wizard.on_ack_changed()
    setup.wizard.continue_()
    assert setup.wizard._password is None and setup.wizard._code is None
    assert setup.wizard.vars.get("code") is None or setup.wizard.vars["code"].get() == ""


def test_the_form_variables_are_gone_once_the_master_is_created(setup):
    make_master(setup)
    assert "password" not in setup.wizard.vars and "repeat" not in setup.wizard.vars


# --- Closing the window on the code screen -----------------------------------------------------------------------------

def test_closing_on_the_code_screen_asks_first(setup):
    make_master(setup)
    setup.dialogs.answer = False
    setup.wizard.on_window_close()
    assert setup.app.calls == [] and setup.wizard.stage == "code"
    title, message, yes, no = setup.dialogs.confirms[-1]
    assert "recovery code" in message.lower() and (yes, no) == ("Close anyway", "Go back")
    setup.dialogs.answer = True
    setup.wizard.on_window_close()
    assert setup.app.calls == [("destroy",)]


def test_closing_after_the_box_is_ticked_still_asks_until_continue(setup):
    make_master(setup)
    setup.wizard.vars["acknowledged"].set(True)
    setup.wizard.on_ack_changed()
    setup.dialogs.answer = False
    setup.wizard.on_window_close()
    assert setup.app.calls == []                                   # ticked but not yet continued: still asks


# --- The clipboard ---------------------------------------------------------------------------------------------------

def clipboard(root):
    try:
        return root.clipboard_get()
    except TclError:
        return ""


def test_copy_puts_the_code_on_the_clipboard(setup, tk_root):
    make_master(setup)
    setup.wizard.copy_code()
    assert clipboard(tk_root) == setup.wizard.vars["code"].get()


def test_continue_clears_the_clipboard_if_it_still_holds_the_code(setup, tk_root):
    make_master(setup)
    setup.wizard.copy_code()
    setup.wizard.vars["acknowledged"].set(True)
    setup.wizard.on_ack_changed()
    setup.wizard.continue_()
    assert clipboard(tk_root) == ""


def test_continue_leaves_other_clipboard_text_alone(setup, tk_root):
    make_master(setup)
    setup.wizard.copy_code()
    tk_root.clipboard_clear()
    tk_root.clipboard_append("something else the user copied")
    setup.wizard.vars["acknowledged"].set(True)
    setup.wizard.on_ack_changed()
    setup.wizard.continue_()
    assert clipboard(tk_root) == "something else the user copied"


def test_continue_clears_a_clipboard_holding_the_code_without_dashes(setup, tk_root):
    make_master(setup)
    code = setup.wizard.vars["code"].get()
    tk_root.clipboard_clear()
    tk_root.clipboard_append(code.replace("-", "").lower())
    setup.wizard.vars["acknowledged"].set(True)
    setup.wizard.on_ack_changed()
    setup.wizard.continue_()
    assert clipboard(tk_root) == ""


# --- Failures ------------------------------------------------------------------------------------------------------------

def test_a_failed_master_creation_returns_to_setup_next_launch(setup, monkeypatch):
    def fail(*args, **kwargs):
        raise ValidationError("The first Master can only be created while there are no users")
    monkeypatch.setattr(view.auth, "create_first_master", fail)
    fill(setup.wizard)
    setup.wizard.submit()
    assert setup.wizard.stage == "form" and setup.dialogs.errors
    assert setup.master.exists()                                    # the file was built...
    assert auth.master_setup_state(setup.master) == "no_users"      # ...but there is no user,
    assert model.startup_route(setup.master) == "first_run"         # so the next launch shows setup again
    monkeypatch.undo()
    setup.wizard.submit()                                           # and the same form works afterwards
    assert setup.wizard.stage == "code" and users(setup.master) == [("root", 1)]


def test_an_unreadable_file_appearing_before_submit_is_reported_and_never_built_over(setup):
    setup.master.write_bytes(b"not a database " * 40)
    before = setup.master.read_bytes()
    fill(setup.wizard)
    setup.wizard.submit()
    title, message = setup.dialogs.errors[-1]
    assert str(setup.master) in message and "older version or damaged" in message
    assert setup.master.read_bytes() == before and setup.app.calls == [("destroy",)]


def test_unreadable_master_dialog_names_the_file_and_exits_without_touching_it(setup):
    setup.master.write_bytes(b"not a database " * 40)
    before = setup.master.read_bytes()
    view.show_unreadable_master(setup.app, setup.master, "DatabaseError")
    title, message = setup.dialogs.errors[-1]
    assert str(setup.master) in message and "older version or damaged" in message
    assert setup.app.startup_failed is True and setup.app.calls == [("destroy",)]
    assert setup.master.read_bytes() == before and list(setup.tmp.glob("Backups")) == []


def test_unreadable_master_logs_only_the_path_and_the_error_type(setup, caplog):
    setup.master.write_bytes(b"not a database " * 40)
    with caplog.at_level(logging.DEBUG):
        view.show_unreadable_master(setup.app, setup.master, "DatabaseError")
    text = caplog.text
    assert str(setup.master) in text and "DatabaseError" in text
    assert "older version" not in text


# --- Secrets never reach a log ------------------------------------------------------------------------------------------------

@pytest.fixture
def log_file(tmp_path):
    path = tmp_path / "Logs" / "strataledger.log"
    logger = logging_setup.configure_logging(path)
    yield path
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", "").endswith("strataledger.log"):
            logger.removeHandler(handler)
            handler.close()


def all_logs(caplog, log_file):
    for handler in logging.getLogger("strataledger").handlers:
        handler.flush()
    return caplog.text + (log_file.read_text(encoding="utf-8") if log_file.exists() else "")


def test_a_full_run_logs_neither_the_password_nor_the_code(setup, caplog, log_file):
    secret_password = "Tr0ub4dor&3-horse-staple"
    with caplog.at_level(logging.DEBUG):
        fill(setup.wizard, password=secret_password, repeat=secret_password)
        setup.wizard.submit()
        code = setup.wizard.vars["code"].get()
        setup.wizard.copy_code()
        setup.wizard.vars["acknowledged"].set(True)
        setup.wizard.on_ack_changed()
        setup.wizard.continue_()
    text = all_logs(caplog, log_file)
    assert "first Master created" in text                              # the run was logged, without secrets
    for secret in (secret_password, code, code.replace("-", ""), code.lower()):
        assert secret not in text
    shown = " ".join(m for _t, m in setup.dialogs.errors) + " ".join(m for _t, m, *_ in setup.dialogs.confirms)
    assert secret_password not in shown and code not in shown


def test_a_failure_whose_message_carries_the_secrets_still_logs_neither(setup, caplog, log_file, monkeypatch):
    secret_password = "Tr0ub4dor&3-horse-staple"
    fixed_code = "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG-HHHH"
    monkeypatch.setattr(passwords, "generate_recovery_code", lambda: fixed_code)

    def explode(code):
        raise RuntimeError(f"hash failed for code {code} (password {secret_password})")
    monkeypatch.setattr(passwords, "hash_recovery_code", explode)
    with caplog.at_level(logging.DEBUG):
        fill(setup.wizard, password=secret_password, repeat=secret_password)
        setup.wizard.submit()
    assert setup.wizard.stage == "form" and users(setup.master) == []
    text = all_logs(caplog, log_file)
    assert "RuntimeError" in text                                       # the error TYPE is logged
    for secret in (secret_password, fixed_code, fixed_code.replace("-", "")):
        assert secret not in text, secret
    shown = " ".join(m for _t, m in setup.dialogs.errors)
    assert secret_password not in shown and fixed_code not in shown and "log" in shown.lower()
    assert "Traceback" not in text or secret_password not in text


def test_the_database_error_path_logs_no_secret_either(setup, caplog, log_file, monkeypatch):
    secret_password = "Tr0ub4dor&3-horse-staple"

    def explode(*args, **kwargs):
        raise OSError(f"disk full while saving {secret_password}")
    monkeypatch.setattr(view.database, "ensure_master_database", explode)
    with caplog.at_level(logging.DEBUG):
        fill(setup.wizard, password=secret_password, repeat=secret_password)
        setup.wizard.submit()
    assert secret_password not in all_logs(caplog, log_file)
    assert all(secret_password not in m for _t, m in setup.dialogs.errors)
