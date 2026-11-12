import os
import sqlite3
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox

from config import COMPANIES_DIR, Theme
from modules.database import SchemaUpgradeBlockedError


def _sanitize_company_code(raw_value):
    value = (raw_value or "").strip()
    normalized = "".join(ch for ch in value.upper() if ch.isalnum() or ch == "_")
    return normalized[:20] or "COMPANY"


def _load_parent_company_options(app):
    try:
        conn = sqlite3.connect(app.master_db_path)
        rows = conn.execute(
            "SELECT company_id, company_code, legal_name FROM company_registry WHERE is_active = 1 ORDER BY legal_name ASC"
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def render_create_company_form(parent_view, container):
    """Renders a full-screen company creation panel for the secure multi-db architecture."""
    for widget in container.winfo_children():
        widget.destroy()

    form_panel = ctk.CTkFrame(
        container,
        width=760,
        height=560,
        fg_color=Theme.glass_panel,
        border_color=Theme.glass_border,
        border_width=1,
        corner_radius=12,
    )
    form_panel.place(relx=0.5, rely=0.5, anchor="center")
    form_panel.pack_propagate(False)

    header = ctk.CTkLabel(
        form_panel,
        text="Create New Company",
        font=Theme.title_font,
        text_color=Theme.text_primary,
        anchor="w",
    )
    header.pack(anchor="w", padx=26, pady=(28, 10))

    subtitle = ctk.CTkLabel(
        form_panel,
        text="Create a new standalone company ledger and register it inside the master company registry.",
        font=Theme.small_font,
        text_color=Theme.text_secondary,
        anchor="w",
    )
    subtitle.pack(anchor="w", padx=26, pady=(0, 18))

    body = ctk.CTkFrame(form_panel, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=26, pady=(0, 18))
    body.grid_columnconfigure((0, 1), weight=1)

    left = ctk.CTkFrame(body, fg_color="transparent")
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

    right = ctk.CTkFrame(body, fg_color="transparent")
    right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

    ctk.CTkLabel(left, text="Legal Company Name", font=Theme.body_font, anchor="w").pack(fill="x", pady=(0, 4))
    legal_name_entry = ctk.CTkEntry(left, height=38, placeholder_text="Acme Holdings LLC", fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
    legal_name_entry.pack(fill="x", pady=(0, 14))

    ctk.CTkLabel(left, text="Company Code", font=Theme.body_font, anchor="w").pack(fill="x", pady=(0, 4))
    company_code_entry = ctk.CTkEntry(left, height=38, placeholder_text="ACME", fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
    company_code_entry.pack(fill="x", pady=(0, 14))

    ctk.CTkLabel(left, text="Fiscal Year End", font=Theme.body_font, anchor="w").pack(fill="x", pady=(0, 4))
    fiscal_year_entry = ctk.CTkEntry(left, height=38, placeholder_text="12-31", fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
    fiscal_year_entry.pack(fill="x", pady=(0, 14))

    ctk.CTkLabel(left, text="Currency", font=Theme.body_font, anchor="w").pack(fill="x", pady=(0, 4))
    currency_var = tk.StringVar(value="USD")
    currency_option = ctk.CTkOptionMenu(
        left,
        values=["USD", "CAD", "EUR", "GBP", "AUD"],
        variable=currency_var,
        fg_color=Theme.input_bg,
        button_color=Theme.btn_secondary,
        width=220,
        font=Theme.body_font,
    )
    currency_option.pack(fill="x", pady=(0, 14))

    ctk.CTkLabel(right, text="Parent Company", font=Theme.body_font, anchor="w").pack(fill="x", pady=(0, 4))
    parent_rows = _load_parent_company_options(parent_view)
    parent_choices = ["Standalone / No Parent"]
    parent_map = {"Standalone / No Parent": None}
    for row in parent_rows:
        company_id, code, legal_name = row
        label = f"{legal_name} ({code})"
        parent_choices.append(label)
        parent_map[label] = company_id
    parent_var = tk.StringVar(value=parent_choices[0])
    parent_select = ctk.CTkOptionMenu(
        right,
        values=parent_choices,
        variable=parent_var,
        fg_color=Theme.input_bg,
        button_color=Theme.btn_secondary,
        width=320,
        font=Theme.body_font,
    )
    parent_select.pack(fill="x", pady=(0, 14))

    ctk.CTkLabel(right, text="Database File Path", font=Theme.body_font, anchor="w").pack(fill="x", pady=(0, 4))
    company_dir = COMPANIES_DIR
    os.makedirs(company_dir, exist_ok=True)
    path_display = ctk.CTkLabel(
        right,
        text=os.path.join(company_dir, "COMPANY.db"),
        font=Theme.small_font,
        text_color=Theme.text_secondary,
        anchor="w",
        justify="left",
    )
    path_display.pack(fill="x", pady=(0, 14))

    def preview_path(*_args):
        code = _sanitize_company_code(company_code_entry.get())
        path_display.configure(text=os.path.join(company_dir, f"{code}.db"))

    company_code_entry.bind("<KeyRelease>", preview_path)

    actions = ctk.CTkFrame(form_panel, fg_color="transparent")
    actions.pack(fill="x", padx=26, pady=(0, 28))

    def handle_create_company():
        legal_name = legal_name_entry.get().strip()
        company_code = _sanitize_company_code(company_code_entry.get())
        currency = currency_var.get().strip() or "USD"
        fiscal_year = fiscal_year_entry.get().strip() or "12-31"
        chosen_parent_label = parent_var.get()
        chosen_parent_id = parent_map.get(chosen_parent_label)

        if not legal_name:
            messagebox.showerror("Company Required", "Please enter a legal company name.")
            return

        if not company_code or company_code == "COMPANY":
            messagebox.showerror("Company Code Required", "Please enter a valid company code.")
            return

        db_path = os.path.join(company_dir, f"{company_code}.db")
        if os.path.exists(db_path):
            messagebox.showerror("Duplicate Company", f"A database already exists for '{company_code}'. Choose a different code.")
            return

        try:
            parent_view.ensure_company_database(db_path)
            conn = sqlite3.connect(parent_view.master_db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO company_registry (company_code, legal_name, database_file_path, parent_company_id, is_active) VALUES (?, ?, ?, ?, 1)",
                (company_code, legal_name, db_path, chosen_parent_id),
            )
            conn.commit()
            conn.close()

            # Seed profile metadata in the new company database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO company_profile (legal_name, company_code, fiscal_year_end, currency) VALUES (?, ?, ?, ?)",
                (legal_name, company_code, fiscal_year, currency),
            )
            conn.commit()
            conn.close()

            messagebox.showinfo("Success", f"Company '{legal_name}' created successfully.")
            parent_view.show_no_company_open_screen()
        except SchemaUpgradeBlockedError as exc:
            messagebox.showerror(
                "Company Upgrade Blocked",
                f"Unable to open {os.path.basename(exc.db_path)}:\n\n{exc.reason}",
            )
            parent_view.show_no_company_open_screen()
        except Exception as exc:
            messagebox.showerror("Company Creation Failed", f"Unable to create the new company record:\n\n{exc}")

    ctk.CTkButton(
        actions,
        text="Create Company",
        height=42,
        fg_color=Theme.btn_primary,
        hover_color=Theme.btn_primary_hover,
        text_color=Theme.btn_primary_text,
        font=Theme.body_font,
        command=handle_create_company,
    ).pack(side="right", padx=(0, 10))

    ctk.CTkButton(
        actions,
        text="Cancel",
        height=42,
        fg_color=Theme.btn_secondary,
        hover_color=Theme.btn_secondary_hover,
        border_color=Theme.btn_secondary_border,
        border_width=1,
        text_color=Theme.btn_secondary_text,
        font=Theme.body_font,
        command=parent_view.show_no_company_open_screen,
    ).pack(side="right")
