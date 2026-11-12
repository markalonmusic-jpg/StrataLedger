"""The New Company screen: a four-step wizard over companies.create_company (decision S5).

A view builds widgets and calls services; it holds no SQL and no business rules (docs/CLAUDE_UI.md section 1).
The wizard's defaults, checks and error wording live in modules/new_company_model.py. Colours, fonts and radii
come from config.Theme only (H6). Dialogs are the shared modal in ui_components.

Who can open it (S8): the launcher has no signed-in user, so the screen first asks for a sign-in. The Master may
create a top-level company or a subsidiary of any company. Anyone else may only create a subsidiary of a company in
which they hold `company.create` (an Admin of that company); everyone else is told who to ask and sent back.
"""
import logging
import tkinter as tk
from datetime import date
from tkinter import filedialog

import customtkinter as ctk

from config import Theme
from modules import new_company_model as model
from modules.services import auth, chart_templates, companies
from modules.services.errors import ServiceError
from modules.ui_components import ask_confirm, show_error, show_info

_logger = logging.getLogger("strataledger.ui")

PAGE_KEY = "setup.new_company"
PANEL_WIDTH = 780
PANEL_HEIGHT = 640
TOP_LEVEL_LABEL = "None: a new top-level company"
_COUNTRY_LABEL = dict(model.COUNTRY_CHOICES)
_COUNTRY_CODE = {label: code for code, label in model.COUNTRY_CHOICES}


def render_create_company_form(app, container):
    """Show the New Company wizard inside `container`. Returns its controller (used by the tests)."""
    return NewCompanyWizard(app, container)


class NewCompanyWizard:
    def __init__(self, app, container):
        self.app = app
        self.container = container
        self.stage = "sign_in"          # sign_in, wizard or closed
        self.step = 0
        self.draft = None
        self.options = None
        self.vars = {}
        self.parent_labels = []
        self._parent_ids = {}
        self.signed_in_here = False
        self._message = None
        if app.session is None:
            self._show_sign_in()
        else:
            self._start()

    # --- Frames -------------------------------------------------------------------------------------

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
                     text_color=Theme.text_secondary if muted else Theme.text_primary).pack(fill="x", pady=(Theme.pad_sm, 2))

    def _entry(self, parent, label, key, value="", help_text=None, on_key=None):
        self._label(parent, label)
        self.vars[key] = tk.StringVar(master=self.container, value=value)
        entry = ctk.CTkEntry(parent, textvariable=self.vars[key], height=Theme.nav_row_height + 4,
                             fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
        entry.pack(fill="x")
        if on_key:
            entry.bind("<KeyRelease>", lambda _event: on_key())
        if help_text:
            self._label(parent, help_text, muted=True)
        return entry

    def _menu(self, parent, label, key, values, value, command=None):
        self._label(parent, label)
        self.vars[key] = tk.StringVar(master=self.container, value=value)
        ctk.CTkOptionMenu(parent, values=list(values), variable=self.vars[key], height=Theme.nav_row_height + 4,
                          fg_color=Theme.input_bg, button_color=Theme.btn_secondary,
                          button_hover_color=Theme.btn_secondary_hover, font=Theme.body_font,
                          dropdown_font=Theme.body_font, command=(lambda _value: command()) if command else None
                          ).pack(fill="x")

    # --- Sign-in (the launcher has no user) -------------------------------------------------------------

    def _show_sign_in(self):
        self.stage = "sign_in"
        panel = self._panel("Create a New Company",
                            "Sign in first. The Master can create any company; an Admin can add a subsidiary to a "
                            "company they administer.")
        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=Theme.pad_lg)
        self._entry(body, "Username", "username")
        self._label(body, "Password")
        self.vars["password"] = tk.StringVar(master=self.container)
        password = ctk.CTkEntry(body, textvariable=self.vars["password"], show="*", height=Theme.nav_row_height + 4,
                                fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
        password.pack(fill="x")
        password.bind("<Return>", lambda _event: self._submit_sign_in())
        self._message = ctk.CTkLabel(body, text="", font=Theme.small_font, text_color=Theme.error_glow,
                                     wraplength=PANEL_WIDTH - 4 * Theme.pad_lg, justify="left", anchor="w")
        self._message.pack(fill="x", pady=Theme.pad_md)
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill="x", padx=Theme.pad_lg, pady=Theme.pad_lg)
        self._button(actions, "Sign in", self._submit_sign_in, primary=True).pack(side="right")
        self._button(actions, "Cancel", self.cancel).pack(side="right", padx=Theme.pad_md)

    def _submit_sign_in(self):
        self.sign_in(self.vars["username"].get(), self.vars["password"].get())

    def sign_in(self, username, password):
        """Sign in with the auth service. True when signed in (the wizard or a 'not allowed' message follows)."""
        try:
            session = auth.login(self.app.master_db_path, (username or "").strip(), password)
        except ServiceError as error:
            if self._message is not None:
                self._message.configure(text=str(error))
            return False
        self.app.session = session
        self.signed_in_here = True
        self._start()
        return True

    # --- Starting -------------------------------------------------------------------------------------

    def _start(self):
        try:
            self.options = companies.creation_options(self.app.session)
        except ServiceError as error:
            title, message = model.explain_error(error)
            show_error(self.container, title, message)
            self._leave()
            return
        if not self.options["top_level"] and not self.options["parents"]:
            show_info(self.container, "Creating a company",
                      "Only the Master can create a new company. An Admin can add a subsidiary to a company they "
                      "administer. Ask your Master to create the company for you.")
            self._leave()
            return
        self.draft = model.new_draft(date.today().year)
        self.parent_labels = ([TOP_LEVEL_LABEL] if self.options["top_level"] else [])
        self._parent_ids = {TOP_LEVEL_LABEL: None}
        for parent in self.options["parents"]:
            label = f"{parent['legal_name']} ({parent['company_code']})"
            self.parent_labels.append(label)
            self._parent_ids[label] = parent["company_id"]
        if not self.options["top_level"]:
            self.draft.parent_company_id = self._parent_ids[self.parent_labels[0]]
            self.draft.chart_source = "copy"
        self.stage = "wizard"
        self.step = 0
        self._show_step()

    # --- The steps ----------------------------------------------------------------------------------------

    def _show_step(self):
        title = model.STEP_TITLES[self.step]
        panel = self._panel("Create a New Company", f"Step {self.step + 1} of {len(model.STEP_TITLES)}: {title}")
        progress = ctk.CTkProgressBar(panel, progress_color=Theme.accent, fg_color=Theme.input_bg)
        progress.pack(fill="x", padx=Theme.pad_lg, pady=(0, Theme.pad_md))
        progress.set((self.step + 1) / len(model.STEP_TITLES))
        body = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=Theme.pad_lg)
        self.vars = {}
        (self._build_company, self._build_year, self._build_chart, self._build_approvals)[self.step](body)
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill="x", padx=Theme.pad_lg, pady=Theme.pad_lg)
        last = self.step == len(model.STEP_TITLES) - 1
        self._button(actions, "Create company" if last else "Next", self.submit if last else self.next,
                     primary=True).pack(side="right")
        if self.step > 0:
            self._button(actions, "Back", self.back).pack(side="right", padx=Theme.pad_md)
        self._button(actions, "Cancel", self.cancel).pack(side="left")

    def _build_company(self, body):
        d = self.draft
        self._entry(body, "Legal company name", "legal_name", d.legal_name, on_key=self.on_name_changed)
        self._entry(body, "Display name (optional)", "display_name", d.display_name,
                    help_text="Shown in the title bar and on reports. Leave empty to use the legal name.")
        self._entry(body, "Company code", "code", d.code, on_key=self.on_code_changed,
                    help_text="3 to 10 capital letters or digits. It names the company file and cannot be changed later.")
        self._file_hint = ctk.CTkLabel(body, text=self._file_text(), font=Theme.small_font,
                                       text_color=Theme.text_secondary, anchor="w")
        self._file_hint.pack(fill="x")
        self._menu(body, "Country", "country", [label for _code, label in model.COUNTRY_CHOICES],
                   _COUNTRY_LABEL[d.country], command=self.on_country_changed)
        self._currency_hint = ctk.CTkLabel(body, text=f"Currency: {d.currency}", font=Theme.small_font,
                                           text_color=Theme.text_secondary, anchor="w")
        self._currency_hint.pack(fill="x")
        self._entry(body, "Tax ID (optional)", "tax_id", d.tax_id)
        current = next((label for label, ident in self._parent_ids.items() if ident == d.parent_company_id),
                       self.parent_labels[0])
        self._menu(body, "Parent company", "parent", self.parent_labels, current, command=self.on_parent_changed)

    def _build_year(self, body):
        d = self.draft
        self._menu(body, "The fiscal year starts in", "start_month", model.MONTHS,
                   model.MONTHS[int(d.start_month) - 1], command=self.on_year_changed)
        self._entry(body, "First fiscal year to record", "first_year", d.first_year, on_key=self.on_year_changed,
                    help_text="A fiscal year is named for the calendar year it ends in.")
        self._year_hint = ctk.CTkLabel(body, text=model.year_preview(d), font=Theme.body_font,
                                       text_color=Theme.accent_text, anchor="w")
        self._year_hint.pack(fill="x", pady=Theme.pad_sm)
        self._menu(body, "Date format", "date_format", model.DATE_FORMAT_CHOICES, d.date_format,
                   command=self.on_year_changed)
        self._menu(body, "Time zone", "timezone", model.timezone_choices(d.country), d.timezone)

    def _build_chart(self, body):
        d = self.draft
        self._label(body, "Choose the starting chart of accounts. You can add and rename accounts later.", muted=True)
        self.vars["chart_source"] = tk.StringVar(master=self.container, value=d.chart_source)
        for key, label in model.chart_choices(d.parent_company_id is not None):
            ctk.CTkRadioButton(body, text=label, variable=self.vars["chart_source"], value=key,
                               font=Theme.body_font, text_color=Theme.text_primary,
                               fg_color=Theme.accent).pack(anchor="w", pady=Theme.pad_sm)
            detail = self._chart_detail(key)
            if detail:
                self._label(body, detail, muted=True)
        self._button(body, "Choose CSV file...", self.choose_csv_file).pack(anchor="w", pady=Theme.pad_sm)
        self._csv_status = ctk.CTkLabel(body, text=self._csv_text(), font=Theme.small_font,
                                        text_color=Theme.text_secondary, anchor="w", justify="left")
        self._csv_status.pack(fill="x")

    def _build_approvals(self, body):
        d = self.draft
        self.vars["require_separate_approver"] = tk.BooleanVar(master=self.container, value=d.require_separate_approver)
        ctk.CTkSwitch(body, text="Require a different user to approve entries and bills",
                      variable=self.vars["require_separate_approver"], font=Theme.body_font,
                      text_color=Theme.text_primary, progress_color=Theme.accent).pack(anchor="w", pady=Theme.pad_md)
        self._label(body, "Off by default. You can turn it on later in Settings > Controls.", muted=True)
        self._label(body, "Please check your answers", muted=False)
        for line in self._summary_lines():
            self._label(body, line, muted=True)

    def _chart_detail(self, key):
        if key in ("construction", "general"):
            try:
                return f"{len(chart_templates.load_template(key))} accounts"
            except ServiceError:
                return ""
        return ""

    def _csv_text(self):
        if self.draft.chart_csv_text:
            return f"Chart file loaded: {self.draft.chart_csv_name or 'chart.csv'}"
        return "No chart file chosen."

    def _file_text(self):
        return f"Company file: Companies/{self.draft.code or '...'}.db"

    def _summary_lines(self):
        d = self.draft
        chart = dict(model.chart_choices(d.parent_company_id is not None)).get(d.chart_source, d.chart_source)
        parent = next((label for label, ident in self._parent_ids.items() if ident == d.parent_company_id), "")
        lines = [f"{d.legal_name} ({d.code}), {_COUNTRY_LABEL[d.country]}, {d.currency}",
                 model.year_preview(d), f"Chart: {chart}"]
        if d.parent_company_id is not None:
            lines.insert(1, f"Subsidiary of {parent}")
        return lines

    # --- Reading the widgets back into the draft ---------------------------------------------------------------

    def _collect(self):
        d, v = self.draft, self.vars
        if "legal_name" in v:
            d.display_name = v["display_name"].get()
            d.tax_id = v["tax_id"].get()
            d.legal_name = v["legal_name"].get()
            code = v["code"].get().strip().upper()
            if code != d.code:
                model.set_code(d, code)
            d.country = _COUNTRY_CODE.get(v["country"].get(), d.country)
            d.parent_company_id = self._parent_ids.get(v["parent"].get(), d.parent_company_id)
        if "first_year" in v:
            d.first_year = v["first_year"].get().strip()
            d.start_month = model.MONTHS.index(v["start_month"].get()) + 1 if v["start_month"].get() in model.MONTHS \
                else d.start_month
            d.date_format = v["date_format"].get()
            d.timezone = v["timezone"].get()
        if "chart_source" in v:
            d.chart_source = v["chart_source"].get()
        if "require_separate_approver" in v:
            d.require_separate_approver = bool(v["require_separate_approver"].get())

    # --- Events -----------------------------------------------------------------------------------------------------

    def on_name_changed(self):
        model.set_name(self.draft, self.vars["legal_name"].get())
        if not self.draft.code_edited:
            self.vars["code"].set(self.draft.code)
        self._refresh_file_hint()

    def on_code_changed(self):
        model.set_code(self.draft, self.vars["code"].get())
        self._refresh_file_hint()

    def _refresh_file_hint(self):
        if getattr(self, "_file_hint", None) is not None and self._file_hint.winfo_exists():
            self._file_hint.configure(text=self._file_text())

    def on_country_changed(self):
        model.set_country(self.draft, _COUNTRY_CODE[self.vars["country"].get()])
        if getattr(self, "_currency_hint", None) is not None and self._currency_hint.winfo_exists():
            self._currency_hint.configure(text=f"Currency: {self.draft.currency}")

    def on_parent_changed(self):
        d = self.draft
        previous = d.parent_company_id
        d.parent_company_id = self._parent_ids.get(self.vars["parent"].get())
        if d.parent_company_id is not None and previous is None:
            d.chart_source = "copy"
        elif d.parent_company_id is None and d.chart_source == "copy":
            d.chart_source = "construction"

    def on_year_changed(self):
        self._collect()
        if getattr(self, "_year_hint", None) is not None and self._year_hint.winfo_exists():
            self._year_hint.configure(text=model.year_preview(self.draft))

    def choose_csv_file(self):
        path = filedialog.askopenfilename(title="Choose your chart of accounts",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.load_csv_file(path)

    def load_csv_file(self, path):
        """Read a chart CSV chosen by the user; it is checked when the user presses Next."""
        try:
            with open(path, encoding="utf-8-sig", newline="") as handle:
                self.draft.chart_csv_text = handle.read()
        except (OSError, UnicodeDecodeError):
            show_error(self.container, "Cannot read the file",
                       "That file could not be read as text. Save it as CSV (UTF-8) and choose it again.")
            return
        self.draft.chart_csv_name = path.replace("\\", "/").rsplit("/", 1)[-1]
        self.draft.chart_source = "csv"
        if "chart_source" in self.vars:
            self.vars["chart_source"].set("csv")
        if getattr(self, "_csv_status", None) is not None and self._csv_status.winfo_exists():
            self._csv_status.configure(text=self._csv_text())

    # --- Moving, creating, leaving -------------------------------------------------------------------------------------

    def next(self):
        self._collect()
        problems = model.validate_step(self.draft, self.step)
        if problems:
            show_error(self.container, "Please check this", "\n".join(problems))
            return
        self.step += 1
        self._show_step()

    def back(self):
        self._collect()
        self.step -= 1
        self._show_step()

    def submit(self):
        self._collect()
        problems = model.validate_all(self.draft)
        if problems:
            show_error(self.container, "Please check this", "\n".join(message for _step, message in problems))
            self.step = problems[0][0]
            self._show_step()
            return
        try:
            created = companies.create_company(self.app.session, **model.create_kwargs(self.draft))
        except Exception as error:  # noqa: BLE001  (any failure becomes a plain dialog; nothing is created)
            if not isinstance(error, ServiceError):
                _logger.exception("creating a company failed")
            title, message = model.explain_error(error)
            show_error(self.container, title, message)
            return
        _logger.info("company created: %s", created["company_code"])
        name = self.draft.display_name.strip() or self.draft.legal_name.strip()
        if ask_confirm(self.container, "Company created",
                       f"{name} was created with the code {created['company_code']}. Open it now?",
                       confirm_text="Open now", cancel_text="Not now"):
            self.stage = "closed"
            self.app.open_company_workspace(created["company_id"], name)
        else:
            self._leave()

    def cancel(self):
        self._leave()

    def _leave(self):
        self.stage = "closed"
        if self.signed_in_here:
            self.app.reset_session()
        self.app.show_no_company_open_screen()
