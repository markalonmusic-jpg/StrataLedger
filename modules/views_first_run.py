"""The first-run setup screen (decision S10).

Shown instead of the login when system_master.db is missing or has no users: a Welcome form that creates the Master,
a code screen that shows the one-time recovery code, then a sign-in and the offer to create the first company.

A view builds widgets and calls services; it holds no SQL and no business rules (docs/CLAUDE_UI.md section 1). The
routing, the form checks and the error wording are in modules/first_run_model.py. Colours, fonts and radii come from
config.Theme only (H6); dialogs are the shared modal in ui_components.

Secrets: the Copy button goes through platform_support.copy_secret_text, which on Windows ASKS Windows to keep the
copy out of clipboard history and cloud sync. That is a request: we could not observe Windows honouring it (clipboard
history is off on the development machine), so the screen warns that a copy may remain in history on some systems.
The password and the recovery code are held only in this controller, only until the sign-in. After the sign-in
the controller drops its references to them (it does not and cannot overwrite the memory they occupied). Neither is
ever logged: this module logs the type of an error and the path of a file, nothing else.
"""
import logging
import tkinter as tk

import customtkinter as ctk

import modules.database as database
from config import Theme
from modules import first_run_model as model
from modules import platform_support
from modules.services import auth
from modules.services.errors import ServiceError
from modules.ui_components import ask_confirm, show_error

_logger = logging.getLogger("strataledger.ui")

PAGE_KEY = "setup.first_run"
PANEL_WIDTH = 720
PANEL_HEIGHT = 660


def render_first_run(app, container):
    """Show the first-run setup inside `container`. Returns its controller (used by the tests)."""
    return FirstRunSetup(app, container)


def show_unreadable_master(app, path, error_type):
    """Tell the user the master file cannot be used, then close the app. The file is never touched."""
    _logger.error("master database unusable: %s (%s)", path, error_type)
    title, message = model.unreadable_message(str(path))
    show_error(app, title, message)
    app.startup_failed = True
    app.destroy()


class FirstRunSetup:
    def __init__(self, app, container):
        self.app = app
        self.container = container
        self.stage = "form"             # form, code, offer or closed
        self.vars = {}
        self.draft = model.Draft()
        self.welcome_text = model.WELCOME_TEXT
        self.code_notice = model.CODE_NOTICE
        self.code_shown = False
        self.continue_button = None
        self._code = None
        self._password = None
        self._username = None
        self._set_close_handler(self.on_window_close)
        self._show_form()

    # --- Frames -----------------------------------------------------------------------------------

    def _clear(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def _panel(self, title, subtitle):
        self._clear()
        panel = ctk.CTkFrame(self.container, width=PANEL_WIDTH, height=PANEL_HEIGHT, fg_color=Theme.glass_panel,
                             border_color=Theme.glass_border, border_width=1, corner_radius=Theme.radius_lg)
        panel.place(relx=0.5, rely=0.5, anchor="center")
        panel.pack_propagate(False)
        ctk.CTkLabel(panel, text=title, font=Theme.title_font, text_color=Theme.text_primary,
                     anchor="w").pack(anchor="w", padx=Theme.pad_lg, pady=(Theme.pad_lg, Theme.pad_sm))
        ctk.CTkLabel(panel, text=subtitle, font=Theme.small_font, text_color=Theme.text_secondary, anchor="w",
                     justify="left", wraplength=PANEL_WIDTH - 2 * Theme.pad_lg).pack(
            anchor="w", padx=Theme.pad_lg, pady=(0, Theme.pad_md))
        return panel

    def _button(self, parent, text, command, primary=False):
        if primary:
            return ctk.CTkButton(parent, text=text, command=command, height=Theme.nav_row_height + 8,
                                 fg_color=Theme.btn_primary, hover_color=Theme.btn_primary_hover,
                                 text_color=Theme.btn_primary_text, font=Theme.body_font)
        return ctk.CTkButton(parent, text=text, command=command, height=Theme.nav_row_height + 8,
                             fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover,
                             border_color=Theme.btn_secondary_border, border_width=1,
                             text_color=Theme.btn_secondary_text, font=Theme.body_font)

    def _label(self, parent, text, muted=False):
        ctk.CTkLabel(parent, text=text, font=Theme.small_font if muted else Theme.body_font, anchor="w",
                     justify="left", wraplength=PANEL_WIDTH - 4 * Theme.pad_lg,
                     text_color=Theme.text_secondary if muted else Theme.text_primary).pack(
            fill="x", pady=(Theme.pad_sm, 2))

    def _entry(self, parent, label, key, hidden=False):
        self._label(parent, label)
        self.vars[key] = tk.StringVar(master=self.container)
        ctk.CTkEntry(parent, textvariable=self.vars[key], show="*" if hidden else "", height=Theme.nav_row_height + 4,
                     fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font).pack(fill="x")

    # --- Window close ------------------------------------------------------------------------------------

    def _set_close_handler(self, handler):
        if hasattr(self.app, "protocol"):
            self.app.protocol("WM_DELETE_WINDOW", handler)

    def on_window_close(self):
        """The X button. On the form it is the same as Exit; on the code screen it asks first."""
        if self.stage == "code":
            if not ask_confirm(self.container, "Recovery code not confirmed",
                               "You have not confirmed that you saved your recovery code. It is shown only once and "
                               "is the only way to reset the Master password if you forget it. Close anyway?",
                               confirm_text="Close anyway", cancel_text="Go back", destructive=True):
                return
        self.exit_app()

    def exit_app(self):
        self.stage = "closed"
        self.app.destroy()

    # --- Step 1: Welcome and the Master's details --------------------------------------------------------------------

    def _show_form(self):
        self.stage = "form"
        panel = self._panel("Welcome to StrataLedger", "Set up your installation")
        body = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=Theme.pad_lg)
        self.vars = {}
        self._label(body, self.welcome_text, muted=True)
        self._entry(body, "Username", "username")
        self._entry(body, "First name", "first_name")
        self._entry(body, "Last name", "last_name")
        self._entry(body, "Email", "email")
        self._entry(body, "Password (at least 12 characters)", "password", hidden=True)
        self._entry(body, "Repeat the password", "repeat", hidden=True)
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill="x", padx=Theme.pad_lg, pady=Theme.pad_lg)
        self._button(actions, "Create Master", self.submit, primary=True).pack(side="right")
        self._button(actions, "Exit", self.exit_app).pack(side="left")

    def _collect(self):
        d, v = self.draft, self.vars
        d.username, d.first_name, d.last_name, d.email = (v[k].get() for k in
                                                          ("username", "first_name", "last_name", "email"))
        d.password, d.repeat = v["password"].get(), v["repeat"].get()

    def submit(self):
        """Check the form, build the master database, create the Master. Invalid input builds nothing."""
        self._collect()
        problems = model.validate(self.draft)
        if problems:
            show_error(self.container, "Please check this", "\n".join(problems))
            return
        path = self.app.master_db_path
        state, error_type = auth.inspect_master(path)
        if state == "unreadable":
            show_unreadable_master(self.app, path, error_type)
            return
        d = self.draft
        try:
            database.ensure_master_database(path)
            created = auth.create_first_master(path, d.username, model.sign_in_secret(d), d.first_name, d.last_name,
                                               d.email)
        except Exception as error:  # noqa: BLE001  (any failure becomes a plain dialog; no user is created)
            _logger.error("first-run setup failed: %s", type(error).__name__)
            title, message = model.explain_error(error)
            show_error(self.container, title, message)
            return
        self._username, self._password, self._code = d.username.strip(), model.sign_in_secret(d), created.recovery_code
        self.draft = model.Draft()
        self._show_code()

    # --- Step 2: the recovery code, shown once -------------------------------------------------------------------------------

    def _show_code(self):
        self.stage = "code"
        self.code_shown = True
        panel = self._panel("Save your recovery code",
                            "The Master account was created. This code is shown only once.")
        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=Theme.pad_lg)
        self._label(body, self.code_notice, muted=True)
        self.vars = {"code": tk.StringVar(master=self.container, value=self._code),
                     "acknowledged": tk.BooleanVar(master=self.container, value=False)}
        ctk.CTkEntry(body, textvariable=self.vars["code"], state="readonly", justify="center",
                     height=Theme.nav_row_height + 12, fg_color=Theme.input_bg, border_color=Theme.accent,
                     text_color=Theme.accent_text, font=Theme.semi_title_font).pack(fill="x", pady=Theme.pad_lg)
        self._button(body, "Copy", self.copy_code).pack(anchor="w")
        ctk.CTkCheckBox(body, text="I have saved this code", variable=self.vars["acknowledged"],
                        command=self.on_ack_changed, font=Theme.body_font, text_color=Theme.text_primary,
                        fg_color=Theme.accent).pack(anchor="w", pady=Theme.pad_lg)
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill="x", padx=Theme.pad_lg, pady=Theme.pad_lg)
        self.continue_button = self._button(actions, "Continue", self.continue_, primary=True)
        self.continue_button.pack(side="right")
        self.continue_button.configure(state="disabled")

    def copy_code(self):
        platform_support.copy_secret_text(self.container, self._code)

    def on_ack_changed(self):
        allowed = model.can_continue(self.code_shown, bool(self.vars["acknowledged"].get()))
        self.continue_button.configure(state="normal" if allowed else "disabled")

    def _clear_clipboard_if_code(self):
        held = platform_support.read_clipboard_text(self.container)
        if model.same_code(held, self._code):
            platform_support.clear_clipboard(self.container)

    # --- Step 3: sign in and offer the first company ---------------------------------------------------------------------------

    def continue_(self):
        """Sign in as the new Master and offer to create the first company. False if it is not allowed yet."""
        if not model.can_continue(self.code_shown, bool(self.vars["acknowledged"].get())):
            return False
        self._clear_clipboard_if_code()
        try:
            session = auth.login(self.app.master_db_path, self._username, self._password)
        except ServiceError as error:
            _logger.error("first-run sign-in failed: %s", type(error).__name__)
            title, message = model.explain_error(error)
            show_error(self.container, title, message)
            return False
        self._drop_secrets()
        self.app.session = session
        self.stage = "offer"
        self._set_close_handler(self.app.destroy)
        if ask_confirm(self.container, "Setup complete",
                       "You are signed in as the Master. Would you like to create your first company now?",
                       confirm_text="Create your first company", cancel_text="Later"):
            self.stage = "closed"
            self.app.create_new_company_file()
        else:
            self.stage = "closed"
            self.app.reset_session()
            self.app.show_no_company_open_screen()
        return True

    def _drop_secrets(self):
        """Drop this controller's references to the password and the code (the shown code is blanked as well)."""
        self._password = None
        self._code = None
        self._username = None
        if "code" in self.vars:
            self.vars["code"].set("")
