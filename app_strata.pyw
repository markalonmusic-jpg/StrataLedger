import logging
import os
import sqlite3
import customtkinter as ctk
from tkinter import filedialog, messagebox

from config import BASE_PROJECT_DIR, MASTER_DB_PATH, UPLOAD_DIR, Theme
from modules.views_dashboard import render_dashboard_flight_deck
from modules.views_billing import render_billing_view
from modules.database import (
    SchemaUpgradeBlockedError,
    ensure_company_database as initialize_company_database,
    ensure_master_database as initialize_master_database,
)
from modules import first_run_model, platform_support
from modules.views_first_run import render_first_run, show_unreadable_master
from modules.views_new_company import render_create_company_form
from modules.views_new_user import render_new_user_form
from modules.views_payroll import render_payroll_view, save_payroll_record as persist_payroll_record
from modules.views_registry import render_customer_master_registry
from modules.views_user_profile import render_user_profile_view
from modules.views_wizard import CustomerIntakeWizard
from modules.font_loader import ensure_inter_font
from modules.sidebar import NavItem, Sidebar
from modules.services import auth, companies, key_store, keys, ledger_verify
from modules.services.errors import (
    AuthenticationError, LoginThrottledError, PasswordChangeRequiredError, ServiceError, ValidationError,
)

_logger = logging.getLogger("strataledger.app")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Sidebar navigation: (group, label, page_key, roles, glyph). roles=None means
# every role; the role lists are the checks the sidebar already applied.
_CUSTOMER_ROLES = ("Master", "Admin", "Accountant", "AR", "Sales")
NAV_ITEMS = (
    NavItem("MAIN CHANNELS", "Flight Deck Base", "home", None, "⌂"),
    NavItem("CUSTOMERS SYSTEMS", "Customers Flight Deck", "customers.dashboard", _CUSTOMER_ROLES, "◈"),
    NavItem("CUSTOMERS SYSTEMS", "Customer List", "customers.list", _CUSTOMER_ROLES, "☰"),
    NavItem("CUSTOMERS SYSTEMS", "Create / Edit Customers", "customers.create", _CUSTOMER_ROLES, "✚"),
    NavItem("REVENUES CORE TOOLS", "Billing & Invoices", "billing", ("Master", "Admin", "Accountant", "AR"), "▤"),
    NavItem("OPERATIONS & COST (AP)", "Workforce HR & Payroll", "payroll", ("Master", "Admin", "Accountant", "HR"), "⏲"),
)
_CUSTOMER_VIEW_KEYS = {"Dashboard": "customers.dashboard", "Master": "customers.list", "Create": "customers.create"}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ensure_inter_font()
        self.title("StrataLedger Enterprise Core Platform")
        self.geometry("1200x720")
        self.minsize(1000, 620)

        self.db = None
        self.active_company_name = ""
        self.current_user = None
        self.current_role = "Guest"
        self.user_first_name = ""
        self.master_db_path = MASTER_DB_PATH
        self.startup_failed = False   # set when the master file cannot be used and the app closes at once
        self.upload_dir = UPLOAD_DIR
        self.logo_file_path = ""
        self.session = None   # auth.Session after login
        self.key_provider = None   # key_store.LocalKeyProvider once the master has its installation key
        self.context = None   # ServiceContext of the open company
        self.is_copilot_visible = True
        self._breadcrumb_parts = ("PLATFORM", "OVERVIEW")
        self.protocol("WM_DELETE_WINDOW", self.on_app_exit)

        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir, exist_ok=True)

        self.configure(fg_color=Theme.bg_color)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        # Decide BEFORE building anything (decision S10): no master or no users -> first-run setup; a master
        # that cannot be used -> an error dialog and exit (the file is never touched); otherwise the launcher.
        route, error_type = first_run_model.startup_check(self.master_db_path)
        if route == "first_run":
            render_first_run(self, self)
        elif route == "error":
            show_unreadable_master(self, self.master_db_path, error_type)
        else:
            self.ensure_master_database()
            self.start_key_store()
            self.show_no_company_open_screen()

    def start_key_store(self):
        """Step 1c: open the installation key with DPAPI and make it this process's key provider, so posting and
        creating a company can get keys. A locked key (another computer or Windows account) refuses both with a
        plain sentence until the Master restores it with the recovery code."""
        self.key_provider = key_store.LocalKeyProvider(self.master_db_path, platform_support.DPAPI)
        keys.set_provider(self.key_provider)
        return self.key_provider

    def ensure_master_database(self):
        initialize_master_database(self.master_db_path)

    def ensure_company_database(self, db_path):
        initialize_company_database(db_path)

    def clear_window(self):
        if hasattr(self, 'workspace_frame') and self.workspace_frame.winfo_exists():
            view_container = getattr(self, "workspace_content", self.workspace_frame)
            for widget in view_container.winfo_children():
                widget.destroy()
        else:
            for widget in self.winfo_children():
                widget.destroy()

    def show_no_company_open_screen(self):
        for widget in self.winfo_children():
            widget.destroy()

        main_panel = ctk.CTkFrame(
            self,
            fg_color=Theme.sidebar_bg,
            width=860,
            height=500,
            corner_radius=8,
            border_color=Theme.glass_border,
            border_width=1,
        )
        main_panel.place(relx=0.5, rely=0.5, anchor="center")
        main_panel.pack_propagate(False)

        left_col = ctk.CTkFrame(main_panel, fg_color=Theme.glass_panel, width=500, corner_radius=0)
        left_col.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(left_col, text="Open a Regional Company File", font=Theme.title_font, text_color=Theme.text_primary, anchor="w").pack(padx=25, pady=(30, 5), fill="x")
        ctk.CTkLabel(left_col, text="Select the company ledger workspace you want to open:", font=Theme.small_font, text_color=Theme.text_secondary, anchor="w").pack(padx=25, pady=(0, 20), fill="x")

        scroll_box = ctk.CTkScrollableFrame(left_col, fg_color="transparent")
        scroll_box.pack(fill="both", expand=True, padx=20, pady=(0, 25))

        try:
            conn = sqlite3.connect(self.master_db_path)
            conn.row_factory = sqlite3.Row
            companies = conn.execute(
                """
                SELECT c1.company_id, c1.company_code, c1.legal_name, c1.database_file_path, c2.legal_name AS parent_name
                FROM company_registry c1
                LEFT JOIN company_registry c2 ON c1.parent_company_id = c2.company_id
                WHERE c1.is_active = 1
                ORDER BY c1.parent_company_id ASC, c1.legal_name ASC
                """
            ).fetchall()
            conn.close()

            for row in companies:
                display_label = f"{row['legal_name']} ({row['company_code']})"
                sub_text = f"↳ Subsidiary of {row['parent_name']}" if row['parent_name'] else "Primary Parent Entity / Independent Client"

                item_frame = ctk.CTkFrame(scroll_box, fg_color=Theme.btn_secondary, height=60, corner_radius=6, cursor="hand2")
                item_frame.pack(fill="x", pady=6, padx=5)
                item_frame.pack_propagate(False)

                lbl_main = ctk.CTkLabel(item_frame, text=display_label, font=Theme.semi_title_font, text_color=Theme.text_primary, anchor="w")
                lbl_main.pack(padx=15, pady=(8, 2), fill="x")
                lbl_sub = ctk.CTkLabel(item_frame, text=sub_text, font=Theme.small_font, text_color=Theme.text_secondary, anchor="w")
                lbl_sub.pack(padx=15, fill="x")

                action = lambda e, company_id=row['company_id'], company_name=row['legal_name']: self.prompt_for_company_credentials(company_id, company_name)
                item_frame.bind("<Button-1>", action)
                lbl_main.bind("<Button-1>", action)
                lbl_sub.bind("<Button-1>", action)
        except Exception as exc:
            ctk.CTkLabel(scroll_box, text=f"No local company profiles found or database missing: {exc}", font=Theme.body_font, text_color=Theme.error_glow).pack(pady=40)

        right_col = ctk.CTkFrame(main_panel, fg_color="transparent", width=350)
        right_col.pack(side="right", fill="both", padx=25, pady=30)
        right_col.pack_propagate(False)

        ctk.CTkLabel(right_col, text="StrataLedger Core", font=Theme.title_font, text_color=Theme.text_primary, anchor="w").pack(fill="x", pady=(0, 30))
        ctk.CTkButton(right_col, text="Open Existing Ledger File...", height=40, font=Theme.body_font, fg_color=Theme.btn_primary, hover_color=Theme.btn_primary_hover, text_color=Theme.btn_primary_text, anchor="w", command=self.handle_manual_file_browser).pack(fill="x", pady=6)
        ctk.CTkButton(right_col, text="Create a New Company File...", height=40, font=Theme.body_font, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text, anchor="w", command=self.create_new_company_file).pack(fill="x", pady=6)
        ctk.CTkButton(right_col, text="Provision Global Staff Login...", height=40, font=Theme.body_font, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text, anchor="w", command=self.show_registration_screen).pack(fill="x", pady=6)
        ctk.CTkButton(right_col, text="Launch Autonomous AI Audit Run...", height=40, font=Theme.body_font, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text, anchor="w").pack(fill="x", pady=6)

    def show_registration_screen(self):
        render_new_user_form(self)

    def prompt_for_company_credentials(self, company_id, company_name):
        for widget in self.winfo_children():
            widget.destroy()

        login_frame = ctk.CTkFrame(self, width=420, height=480, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=12)
        login_frame.place(relx=0.5, rely=0.5, anchor="center")
        login_frame.pack_propagate(False)

        ctk.CTkLabel(login_frame, text="Company Login Required", font=Theme.title_font, text_color=Theme.text_primary).pack(pady=(45, 5))
        ctk.CTkLabel(login_frame, text=f"Opening Workspace: {company_name}", font=Theme.small_font, text_color=Theme.text_secondary).pack(pady=(0, 35))

        ctk.CTkLabel(login_frame, text="Username:", font=Theme.body_font, anchor="w").pack(fill="x", padx=45, pady=(10, 2))
        self.user_inp = ctk.CTkEntry(login_frame, height=38, fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
        self.user_inp.pack(fill="x", padx=45)

        ctk.CTkLabel(login_frame, text="Password:", font=Theme.body_font, anchor="w").pack(fill="x", padx=45, pady=(15, 2))
        self.pass_inp = ctk.CTkEntry(login_frame, height=38, show="*", fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
        self.pass_inp.pack(fill="x", padx=45)
        self.pass_inp.bind("<Return>", lambda event: self.execute_secured_login(company_id, company_name))

        self.msg_lbl = ctk.CTkLabel(login_frame, text="", font=Theme.small_font)
        self.msg_lbl.pack(pady=15)

        ctk.CTkButton(login_frame, text="Open Ledger", height=42, fg_color=Theme.btn_primary, hover_color=Theme.btn_primary_hover, text_color=Theme.btn_primary_text, font=Theme.semi_title_font, command=lambda: self.execute_secured_login(company_id, company_name)).pack(fill="x", padx=45, pady=5)
        ctk.CTkButton(login_frame, text="Back to Company Directory", height=35, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, font=Theme.body_font, text_color=Theme.btn_secondary_text, command=self.show_no_company_open_screen).pack(fill="x", padx=45, pady=5)

    def execute_secured_login(self, company_id, company_name):
        """Log in through the auth service, then open the company through the companies service."""
        username = self.user_inp.get().strip()
        password = self.pass_inp.get()
        try:
            session = auth.login(self.master_db_path, username, password)
        except (AuthenticationError, LoginThrottledError) as exc:
            self.msg_lbl.configure(text=str(exc), text_color=Theme.error_glow)
            return
        except ServiceError as exc:
            messagebox.showerror("Login Failed", str(exc))
            return
        self.session = session
        if session.must_change_password:
            self.show_forced_password_change(company_id, company_name)
            return
        self.open_company_workspace(company_id, company_name)

    def open_company_workspace(self, company_id, company_name):
        try:
            context = companies.open_company(self.session, company_id)
        except SchemaUpgradeBlockedError as exc:
            self.reset_session()
            messagebox.showerror(
                "Company Upgrade Blocked",
                f"Unable to open {os.path.basename(exc.db_path)}:\n\n{exc.reason}",
            )
            self.show_no_company_open_screen()
            return
        except PasswordChangeRequiredError:
            self.show_forced_password_change(company_id, company_name)
            return
        except ServiceError as exc:
            self.reset_session()
            messagebox.showerror("Cannot Open Company", str(exc))
            self.show_no_company_open_screen()
            return
        self.context = context
        self.current_user = self.session.username
        self.current_role = "Master" if self.session.is_master else (self.session.legacy_role or "User")
        self.user_first_name = self.session.first_name or self.session.username
        self.db = context.company_db_path
        self.active_company_name = company_name
        self.build_master_layout_canvas()

    def action_context(self):
        """A fresh context for one post, approval, rejection or close of the open company (R19).

        self.context keeps the time the company was opened; never pass it to those services.
        """
        if self.context is None:
            raise ValidationError("Open a company first.")
        return companies.action_context(self.context)

    def close_company_ledger(self):
        """Sign a ledger checkpoint for the open company before it closes (audit design 2.6). Never blocks closing.

        The checkpoint records the time of closing, so it gets a fresh context (R26); if that cannot be built
        the failure is logged and the checkpoint skipped.
        """
        if self.context is None:
            return
        try:
            ledger_verify.checkpoint_on_close(self.action_context())
        except ServiceError:
            _logger.exception("The ledger checkpoint on close was skipped (company_id=%s)", self.context.company_id)

    def on_app_exit(self):
        self.close_company_ledger()
        self.destroy()

    def reset_session(self):
        self.session = None
        self.context = None
        self.db = None
        self.active_company_name = ""
        self.current_user = None
        self.current_role = "Guest"
        self.user_first_name = ""

    def show_forced_password_change(self, company_id, company_name):
        """After a password reset the user must choose a new password before anything else."""
        for widget in self.winfo_children():
            widget.destroy()
        frame = ctk.CTkFrame(self, width=420, height=520, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=12)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        frame.pack_propagate(False)
        ctk.CTkLabel(frame, text="Choose a New Password", font=Theme.title_font, text_color=Theme.text_primary).pack(pady=(40, 5))
        ctk.CTkLabel(frame, text="Your password was reset. Set a new one (at least 12 characters).", font=Theme.small_font, text_color=Theme.text_secondary, wraplength=340).pack(pady=(0, 25))
        entries = []
        for label in ("Current (temporary) password:", "New password:", "Repeat new password:"):
            ctk.CTkLabel(frame, text=label, font=Theme.body_font, anchor="w").pack(fill="x", padx=45, pady=(8, 2))
            entry = ctk.CTkEntry(frame, height=38, show="*", fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
            entry.pack(fill="x", padx=45)
            entries.append(entry)

        def submit():
            current, new, repeated = (e.get() for e in entries)
            if new != repeated:
                messagebox.showerror("Password Change", "The new passwords do not match.")
                return
            try:
                auth.change_password(self.session, current, new)
            except ServiceError as exc:
                messagebox.showerror("Password Change", str(exc))
                return
            messagebox.showinfo("Password Change", "Your password was changed.")
            self.open_company_workspace(company_id, company_name)

        ctk.CTkButton(frame, text="Change Password", height=42, fg_color=Theme.btn_primary, hover_color=Theme.btn_primary_hover, text_color=Theme.btn_primary_text, font=Theme.semi_title_font, command=submit).pack(fill="x", padx=45, pady=(25, 5))
        ctk.CTkButton(frame, text="Cancel", height=35, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, font=Theme.body_font, text_color=Theme.btn_secondary_text, command=lambda: (self.reset_session(), self.show_no_company_open_screen())).pack(fill="x", padx=45, pady=5)

    def create_new_company_file(self):
        render_create_company_form(self, self)

    def handle_manual_file_browser(self):
        selected_file = filedialog.askopenfilename(
            initialdir=BASE_PROJECT_DIR,
            title="Open Standalone StrataLedger File",
            filetypes=[("SQLite Database Files", "*.db")],
        )
        if selected_file:
            try:
                self.ensure_company_database(selected_file)
            except SchemaUpgradeBlockedError as exc:
                messagebox.showerror(
                    "Company Upgrade Blocked",
                    f"Unable to open {os.path.basename(exc.db_path)}:\n\n{exc.reason}",
                )
                self.show_no_company_open_screen()
                return
            clean_name = os.path.basename(selected_file).replace(".db", "").upper()
            self.prompt_for_company_credentials(selected_file, f"External: {clean_name}")

    def show_login_screen(self):
        self.show_no_company_open_screen()

    def handle_login(self):
        self.show_no_company_open_screen()

    def handle_registration(self):
        self.show_no_company_open_screen()

    def build_master_layout_canvas(self):
        self.clear_window()
        self.sidebar = Sidebar(
            self,
            items=NAV_ITEMS,
            current_role=self.current_role,
            user_name=self.current_user,
            on_navigate=self.navigate_to,
            on_user_click=self.show_user_profile_edit_view,
            on_toggle_assistant=self.toggle_ai_copilot_panel,
            assistant_open=self.is_copilot_visible,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar_frame = self.sidebar
        self.profile_card = self.sidebar.user_card

        self.workspace_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.workspace_frame.grid(row=0, column=1, padx=30, pady=30, sticky="nsew")
        self.workspace_frame.grid_columnconfigure(0, weight=1)
        self.workspace_frame.grid_rowconfigure(0, weight=0)
        self.workspace_frame.grid_rowconfigure(1, weight=1)

        workspace_header = ctk.CTkFrame(
            self.workspace_frame,
            height=36,
            corner_radius=0,
            fg_color="transparent",
        )
        workspace_header.grid(row=0, column=0, sticky="ew")
        workspace_header.grid_propagate(False)
        workspace_header.grid_columnconfigure(0, weight=1)
        workspace_header.grid_rowconfigure(0, weight=1)
        self.breadcrumb_lbl = ctk.CTkLabel(
            workspace_header,
            text="  >  ".join(self._breadcrumb_parts),
            font=ctk.CTkFont(family=Theme.font_family, size=11),
            text_color=Theme.text_muted,
            anchor="w",
        )
        self.breadcrumb_lbl.grid(row=0, column=0, sticky="ew", padx=4)
        ctk.CTkFrame(
            workspace_header,
            height=1,
            corner_radius=0,
            fg_color=Theme.glass_border,
        ).grid(row=1, column=0, sticky="ew")

        self.workspace_content = ctk.CTkFrame(
            self.workspace_frame,
            corner_radius=0,
            fg_color="transparent",
        )
        self.workspace_content.grid(row=1, column=0, sticky="nsew")
        self.workspace_content.grid_columnconfigure(0, weight=1)
        self.workspace_content.grid_rowconfigure(0, weight=1)

        self.copilot_frame = ctk.CTkFrame(self, width=340, corner_radius=0, fg_color=Theme.sidebar_bg, border_color=Theme.glass_border, border_width=1)
        self.copilot_frame.grid(row=0, column=2, sticky="nsew")
        self.copilot_frame.pack_propagate(False)

        self.copilot_frame.grid_columnconfigure(0, weight=1)
        self.copilot_frame.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.copilot_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 10))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="Strata AI", font=Theme.semi_title_font, text_color=Theme.text_primary).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(header, text="●", font=Theme.small_font, text_color=Theme.success_glow).grid(
            row=0, column=1, sticky="e", padx=(0, 5)
        )
        ctk.CTkLabel(header, text="Ready", font=Theme.small_font, text_color=Theme.text_muted).grid(
            row=0, column=2, sticky="e"
        )
        ctk.CTkButton(
            header,
            text="+",
            width=30,
            height=30,
            font=Theme.semi_title_font,
            fg_color=Theme.btn_secondary,
            hover_color=Theme.btn_secondary_hover,
            border_color=Theme.btn_secondary_border,
            border_width=1,
            text_color=Theme.btn_secondary_text,
            command=self.start_new_chat,
        ).grid(row=0, column=3, sticky="e", padx=(10, 0))

        self.chat_feed = ctk.CTkScrollableFrame(
            self.copilot_frame,
            fg_color="transparent",
            corner_radius=0,
        )
        self.chat_feed.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.chat_feed.grid_columnconfigure(0, weight=1)

        composer = ctk.CTkFrame(
            self.copilot_frame,
            fg_color=Theme.composer_bg,
            border_color=Theme.composer_border,
            border_width=1,
            corner_radius=12,
        )
        composer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 14))
        composer.grid_columnconfigure(0, weight=1)
        self.chat_attachments = []

        attach_row = ctk.CTkFrame(composer, fg_color="transparent")
        attach_row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 2))
        self.chat_attachment_row = attach_row
        ctk.CTkButton(
            attach_row,
            text="+ Attach CSV",
            width=105,
            height=26,
            font=Theme.small_font,
            fg_color=Theme.btn_secondary,
            hover_color=Theme.btn_secondary_hover,
            border_color=Theme.btn_secondary_border,
            border_width=1,
            text_color=Theme.btn_secondary_text,
            command=self.attach_chat_csv,
        ).pack(side="left")

        self.chat_entry = ctk.CTkTextbox(
            composer,
            height=78,
            fg_color="transparent",
            border_width=0,
            font=Theme.body_font,
            text_color=Theme.text_primary,
            wrap="word",
        )
        self.chat_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(2, 0))
        self.chat_entry.insert("1.0", "Message Strata AI...")
        self.chat_entry.configure(text_color=Theme.text_muted)
        self.chat_entry.bind("<Return>", self.process_ai_instruction)
        self.chat_entry.bind("<Shift-Return>", lambda _event: None)
        self.chat_entry.bind("<FocusIn>", self.highlight_chat_composer)
        self.chat_entry.bind("<FocusOut>", self.unhighlight_chat_composer)

        ctk.CTkLabel(
            composer,
            text="Enter to send · Shift+Enter for a new line",
            font=Theme.small_font,
            text_color=Theme.text_muted,
        ).grid(row=2, column=0, sticky="w", padx=10, pady=(3, 8))
        ctk.CTkButton(
            composer,
            text="↑",
            width=34,
            height=30,
            font=Theme.semi_title_font,
            fg_color=Theme.btn_primary,
            hover_color=Theme.btn_primary_hover,
            text_color=Theme.btn_primary_text,
            command=self.process_ai_instruction,
        ).grid(row=2, column=1, sticky="e", padx=9, pady=(3, 8))

        self.add_chat_message(
            f"Welcome to Strata AI. {self.active_company_name} is ready.",
            role="assistant",
            status="Workspace connected",
        )

        self.show_home_view()

    def set_breadcrumb(self, *parts):
        self._breadcrumb_parts = tuple(str(part).upper() for part in parts if part)
        label = getattr(self, "breadcrumb_lbl", None)
        if label is not None and label.winfo_exists():
            label.configure(text="  >  ".join(self._breadcrumb_parts))

    def navigate_to(self, page_key):
        """Open a sidebar page. Each target function also sets the active row."""
        handlers = {
            "home": self.show_home_view,
            "customers.dashboard": lambda: self.switch_customers_view("Dashboard"),
            "customers.list": lambda: self.switch_customers_view("Master"),
            "customers.create": lambda: self.switch_customers_view("Create"),
            "billing": self.show_billing_invoices_view,
            "payroll": self.show_payroll_view,
        }
        handlers[page_key]()

    def set_active_nav(self, page_key):
        sidebar = getattr(self, "sidebar", None)
        if sidebar is not None and sidebar.winfo_exists():
            sidebar.set_active(page_key)

    def toggle_ai_copilot_panel(self):
        if self.is_copilot_visible:
            self.copilot_frame.grid_forget()
            self.is_copilot_visible = False
        else:
            self.copilot_frame.grid(row=0, column=2, sticky="nsew")
            self.is_copilot_visible = True
        self.sidebar.set_assistant_open(self.is_copilot_visible)

    def add_chat_message(self, text, role, status=None):
        message_row = ctk.CTkFrame(self.chat_feed, fg_color="transparent")
        message_row.grid(
            row=len(self.chat_feed.winfo_children()),
            column=0,
            sticky="ew",
            padx=4,
            pady=5,
        )
        message_row.grid_columnconfigure(0, weight=1)

        is_user = role == "user"
        bubble = ctk.CTkFrame(
            message_row,
            fg_color=Theme.btn_secondary if is_user else Theme.glass_panel,
            corner_radius=12,
        )
        bubble.grid(row=0, column=0, sticky="e" if is_user else "w")
        if status:
            ctk.CTkLabel(
                bubble,
                text=status,
                font=Theme.small_font,
                text_color=Theme.text_muted,
                anchor="w",
            ).pack(anchor="w", padx=12, pady=(9, 0))
        ctk.CTkLabel(
            bubble,
            text=text,
            font=Theme.body_font,
            text_color=Theme.text_primary,
            justify="left",
            anchor="w",
            wraplength=245,
        ).pack(anchor="w", padx=12, pady=(7 if status else 9, 9))
        self.chat_feed.after_idle(lambda: self.chat_feed._parent_canvas.yview_moveto(1))

    def start_new_chat(self):
        for child in self.chat_feed.winfo_children():
            child.destroy()
        self.chat_attachments.clear()
        self.render_chat_attachments()
        self.add_chat_message(
            f"Welcome to Strata AI. {self.active_company_name} is ready.",
            role="assistant",
            status="Workspace connected",
        )
        self.chat_entry.delete("1.0", ctk.END)
        self.chat_entry.focus_set()

    def attach_chat_csv(self):
        selected_files = filedialog.askopenfilenames(
            title="Attach CSV files",
            filetypes=[("CSV files", "*.csv")],
        )
        for path in selected_files:
            if path not in self.chat_attachments:
                self.chat_attachments.append(path)
        self.render_chat_attachments()

    def render_chat_attachments(self):
        for child in self.chat_attachment_row.winfo_children():
            if child.winfo_exists() and child.cget("text") != "+ Attach CSV":
                child.destroy()

        for path in self.chat_attachments:
            filename = os.path.basename(path)
            ctk.CTkButton(
                self.chat_attachment_row,
                text=f"{filename} ×",
                width=130,
                height=26,
                font=Theme.small_font,
                fg_color=Theme.btn_secondary,
                hover_color=Theme.btn_secondary_hover,
                border_color=Theme.btn_secondary_border,
                border_width=1,
                text_color=Theme.btn_secondary_text,
                command=lambda selected=path: self.remove_chat_attachment(selected),
            ).pack(side="left", padx=(6, 0))

    def remove_chat_attachment(self, path):
        self.chat_attachments.remove(path)
        self.render_chat_attachments()

    def highlight_chat_composer(self, _event=None):
        if self.chat_entry.get("1.0", "end-1c") == "Message Strata AI...":
            self.chat_entry.delete("1.0", ctk.END)
            self.chat_entry.configure(text_color=Theme.text_primary)
        self.chat_entry.master.configure(
            border_color=Theme.focus_border,
            border_width=2,
        )

    def unhighlight_chat_composer(self, _event=None):
        if not self.chat_entry.get("1.0", "end-1c").strip():
            self.chat_entry.delete("1.0", ctk.END)
            self.chat_entry.insert("1.0", "Message Strata AI...")
            self.chat_entry.configure(text_color=Theme.text_muted)
        self.chat_entry.master.configure(
            border_color=Theme.composer_border,
            border_width=1,
        )

    def show_home_view(self):
        self.set_active_nav("home")
        self.set_breadcrumb("PLATFORM", "OVERVIEW")
        for w in self.workspace_content.winfo_children():
            w.destroy()
        info = ctk.CTkFrame(self.workspace_content, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=8)
        info.pack(fill="both", expand=True)
        ctk.CTkLabel(info, text=f"Welcome back to StrataLedger, {self.user_first_name}.", font=Theme.semi_title_font, text_color=Theme.text_primary).pack(pady=20, padx=20, anchor="w")
        ctk.CTkLabel(info, text=f"Active company file: {self.active_company_name} | Database: {self.db}", font=Theme.body_font, text_color=Theme.text_secondary).pack(pady=(0, 20), padx=20, anchor="w")

    def show_user_profile_edit_view(self):
        self.set_active_nav(None)
        self.set_breadcrumb("PLATFORM", "USER PROFILE")
        render_user_profile_view(self, self.workspace_content)

    def handle_secure_logout(self):
        """Clears session state and returns to the company directory."""
        if not messagebox.askyesno("Log Out", "Are you sure you want to log out and lock the active company ledger file?"):
            return

        self.close_company_ledger()
        self.reset_session()
        self.show_no_company_open_screen()

    def show_billing_invoices_view(self, cust="", amt=""):
        self.set_active_nav("billing")
        self.set_breadcrumb("PLATFORM", "REVENUE", "BILLING")
        render_billing_view(self, self.workspace_content, cust, amt)

    def show_payroll_view(self):
        self.set_active_nav("payroll")
        self.set_breadcrumb("PLATFORM", "OPERATIONS", "PAYROLL")
        render_payroll_view(self, self.workspace_content)

    def save_payroll_record(self):
        persist_payroll_record(self)

    def process_ai_instruction(self, _event=None):
        cmd = self.chat_entry.get("1.0", "end-1c").strip()
        if cmd == "Message Strata AI...":
            cmd = ""
        attachments = list(self.chat_attachments)
        if not cmd and not attachments:
            return "break"

        message = cmd or "Please review the attached CSV."
        if attachments:
            filenames = ", ".join(os.path.basename(path) for path in attachments)
            message = f"{message}\nAttached CSV: {filenames}"
        self.add_chat_message(message, role="user")
        self.chat_entry.delete("1.0", ctk.END)
        self.chat_entry.configure(text_color=Theme.text_primary)
        self.chat_attachments.clear()
        self.render_chat_attachments()

        if attachments:
            self.add_chat_message(
                "CSV attachments are displayed in this chat but are not processed by the current demo.",
                role="assistant",
                status="Attachment noted",
            )

        cmd_lower = cmd.lower()
        if "bill" in cmd_lower or "invoice" in cmd_lower:
            self.show_billing_invoices_view("Extracted Client", "1250.00")
            self.add_chat_message(
                "Opened the billing workspace with a sample invoice draft.",
                role="assistant",
                status="Workspace action",
            )
        elif cmd:
            self.add_chat_message(
                "This chat can open the billing workspace for invoice-related requests.",
                role="assistant",
                status="Available action",
            )
        return "break"

    def switch_customers_view(self, target_view, edit_id=None):
        self.set_active_nav(_CUSTOMER_VIEW_KEYS.get(target_view))
        for child in self.workspace_content.winfo_children():
            child.destroy()
        if target_view == "Dashboard":
            self.set_breadcrumb("PLATFORM", "CUSTOMERS", "OVERVIEW")
            render_dashboard_flight_deck(self, self.workspace_content)
        elif target_view == "Master":
            self.set_breadcrumb("PLATFORM", "CUSTOMERS", "CUSTOMER LIST")
            render_customer_master_registry(self, self.workspace_content)
        elif target_view == "Create":
            CustomerIntakeWizard(self, self.workspace_content, edit_contact_id=edit_id)


if __name__ == "__main__":
    app = App()
    if not app.startup_failed:
        app.mainloop()
