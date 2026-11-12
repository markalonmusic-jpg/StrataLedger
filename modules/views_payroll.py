import sqlite3
from tkinter import messagebox

import customtkinter as ctk

from config import Theme


def render_payroll_view(parent_view, workspace_frame):
    for widget in workspace_frame.winfo_children():
        widget.destroy()

    ctk.CTkLabel(
        workspace_frame,
        text="WORKFORCE HR & PAYROLL",
        font=Theme.title_font,
        text_color=Theme.text_primary,
    ).pack(pady=5, anchor="w")
    entry_card = ctk.CTkFrame(
        workspace_frame,
        fg_color=Theme.glass_panel,
        border_color=Theme.glass_border,
        border_width=1,
        corner_radius=8,
    )
    entry_card.pack(fill="x", pady=10)

    ctk.CTkLabel(
        entry_card,
        text="Employee Time Entry",
        font=Theme.semi_title_font,
        text_color=Theme.accent_glow,
    ).pack(padx=20, pady=15, anchor="w")
    ctk.CTkLabel(entry_card, text="Employee ID Link Number (contact_id):", font=Theme.body_font).pack(
        padx=20, anchor="w"
    )
    parent_view.emp_inp = ctk.CTkEntry(entry_card, width=400, font=Theme.body_font)
    parent_view.emp_inp.pack(padx=20, pady=(2, 10), anchor="w")

    ctk.CTkLabel(entry_card, text="Shift Hours Worked:", font=Theme.body_font).pack(padx=20, anchor="w")
    parent_view.hours_inp = ctk.CTkEntry(entry_card, width=400, font=Theme.body_font)
    parent_view.hours_inp.pack(padx=20, pady=(2, 10), anchor="w")

    ctk.CTkLabel(entry_card, text="Gross Wage (in Cents):", font=Theme.body_font).pack(padx=20, anchor="w")
    parent_view.wage_inp = ctk.CTkEntry(entry_card, width=400, font=Theme.body_font)
    parent_view.wage_inp.pack(padx=20, pady=(2, 10), anchor="w")

    ctk.CTkLabel(entry_card, text="Tax Burden (in Cents):", font=Theme.body_font).pack(padx=20, anchor="w")
    parent_view.burden_inp = ctk.CTkEntry(entry_card, width=400, font=Theme.body_font)
    parent_view.burden_inp.pack(padx=20, pady=(2, 15), anchor="w")
    ctk.CTkButton(
        entry_card,
        text="Stage Labor Time Record to DB",
        command=parent_view.save_payroll_record,
        font=Theme.body_font,
        fg_color=Theme.btn_primary,
        hover_color=Theme.btn_primary_hover,
        text_color=Theme.btn_primary_text,
    ).pack(padx=20, pady=(5, 20), anchor="w")


def save_payroll_record(parent_view):
    employee_id = parent_view.emp_inp.get().strip()
    hours = parent_view.hours_inp.get().strip()
    wage = parent_view.wage_inp.get().strip()
    burden = parent_view.burden_inp.get().strip()
    if not all((employee_id, hours, wage, burden)):
        return

    try:
        with sqlite3.connect(parent_view.db) as conn:
            conn.execute(
                "INSERT INTO time_entry (contact_id, work_date, hours, wage_cents, burden_cents) "
                "VALUES (?, DATE('now'), ?, ?, ?)",
                (employee_id, hours, wage, burden),
            )
        messagebox.showinfo("Success", "Labor run logged successfully inside database space.")
        parent_view.emp_inp.delete(0, ctk.END)
        parent_view.hours_inp.delete(0, ctk.END)
        parent_view.wage_inp.delete(0, ctk.END)
        parent_view.burden_inp.delete(0, ctk.END)
    except sqlite3.Error as exc:
        messagebox.showerror("Error", str(exc))
