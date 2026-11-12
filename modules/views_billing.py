import sqlite3
import tkinter as tk
from datetime import datetime
from datetime import timedelta
from tkinter import messagebox

import customtkinter as ctk

from config import Theme


def render_billing_view(parent_view, workspace_frame, cust="", amt=""):
    return BillingTransactionForm(parent_view, workspace_frame, cust, amt)


class BillingTransactionForm:
    def __init__(self, parent_view, container, cust="", amt=""):
        self.parent_view = parent_view
        self.container = container
        self.line_item_rows = []
        self.entity_map = {}
        self.project_map = {}
        self.account_map = {}
        self.parent_dimension_map = {}
        self.initial_customer = cust
        self.initial_amount = amt
        self.initialize_view_canvas()

    def initialize_view_canvas(self):
        for widget in self.container.winfo_children():
            widget.destroy()

        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(1, weight=1)

        header_card = ctk.CTkFrame(
            self.container,
            fg_color=Theme.glass_panel,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=8,
        )
        header_card.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 15))
        header_card.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(header_card, text="Transaction Type:", font=Theme.body_font).grid(
            row=0, column=0, padx=15, pady=(15, 2), sticky="w"
        )
        self.txn_type_var = ctk.StringVar(value="Invoice")
        ctk.CTkOptionMenu(
            header_card,
            height=36,
            values=["Invoice", "Bill", "Credit Memo"],
            variable=self.txn_type_var,
            fg_color=Theme.input_bg,
            button_color=Theme.btn_secondary,
            font=Theme.body_font,
        ).grid(row=0, column=1, padx=15, pady=(15, 2), sticky="ew")

        ctk.CTkLabel(header_card, text="Document Reference #:", font=Theme.body_font).grid(
            row=0, column=2, padx=15, pady=(15, 2), sticky="w"
        )
        self.inv_num_entry = ctk.CTkEntry(
            header_card,
            height=36,
            fg_color=Theme.input_bg,
            border_color=Theme.glass_border,
            font=Theme.body_font,
        )
        self.inv_num_entry.grid(row=0, column=3, padx=15, pady=(15, 2), sticky="ew")
        self.inv_num_entry.insert(0, f"INV-{datetime.now().strftime('%Y')}-001")

        ctk.CTkLabel(header_card, text="Account Contact:", font=Theme.body_font).grid(
            row=1, column=0, padx=15, pady=8, sticky="w"
        )
        self.load_entity_registry_lookups()
        entity_choices = list(self.entity_map.keys())
        entity_default = entity_choices[0]
        self.cust_var = ctk.StringVar(value=entity_default)
        if self.initial_customer:
            customer_search = self.initial_customer.casefold()
            for choice in entity_choices:
                if customer_search in choice.casefold():
                    self.cust_var.set(choice)
                    break
        ctk.CTkOptionMenu(
            header_card,
            height=36,
            values=entity_choices,
            variable=self.cust_var,
            fg_color=Theme.input_bg,
            button_color=Theme.btn_secondary,
            font=Theme.body_font,
        ).grid(row=1, column=1, padx=15, pady=8, sticky="ew")

        ctk.CTkLabel(header_card, text="Associated Project/Job:", font=Theme.body_font).grid(
            row=1, column=2, padx=15, pady=8, sticky="w"
        )
        self.load_project_registry_lookups()
        project_choices = list(self.project_map.keys())
        self.proj_var = ctk.StringVar(value=project_choices[0])
        ctk.CTkOptionMenu(
            header_card,
            height=36,
            values=project_choices,
            variable=self.proj_var,
            fg_color=Theme.input_bg,
            button_color=Theme.btn_secondary,
            font=Theme.body_font,
        ).grid(row=1, column=3, padx=15, pady=8, sticky="ew")

        ctk.CTkLabel(header_card, text="Net Payment Terms:", font=Theme.body_font).grid(
            row=2, column=0, padx=15, pady=(8, 15), sticky="w"
        )
        self.terms_var = ctk.StringVar(value="Net 30")
        ctk.CTkOptionMenu(
            header_card,
            height=36,
            values=["Due on Receipt", "Net 15", "Net 30", "Net 60"],
            variable=self.terms_var,
            fg_color=Theme.input_bg,
            button_color=Theme.btn_secondary,
            font=Theme.body_font,
            command=self.calculate_due_date_parameters,
        ).grid(row=2, column=1, padx=15, pady=(8, 15), sticky="ew")

        ctk.CTkLabel(header_card, text="Issue/Posting Date:", font=Theme.body_font).grid(
            row=2, column=2, padx=15, pady=(8, 15), sticky="w"
        )
        self.date_entry = ctk.CTkEntry(
            header_card,
            height=36,
            fg_color=Theme.input_bg,
            border_color=Theme.glass_border,
            font=Theme.body_font,
        )
        self.date_entry.grid(row=2, column=3, padx=15, pady=(8, 15), sticky="ew")
        self.date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.date_entry.bind("<KeyRelease>", lambda _event: self.calculate_due_date_parameters(self.terms_var.get()))

        line_items_card = ctk.CTkFrame(
            self.container,
            fg_color=Theme.glass_panel,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=8,
        )
        line_items_card.grid(row=1, column=0, sticky="nsew", padx=2)
        line_items_card.grid_columnconfigure(0, weight=1)
        line_items_card.grid_rowconfigure(1, weight=1)

        tray_controls = ctk.CTkFrame(line_items_card, fg_color="transparent", height=40)
        tray_controls.grid(row=0, column=0, columnspan=2, sticky="ew", padx=15, pady=10)
        ctk.CTkLabel(
            tray_controls,
            text="LINE ITEM DISTRIBUTION",
            font=Theme.section_font,
            text_color=Theme.accent_glow,
        ).pack(side="left")
        ctk.CTkButton(
            tray_controls,
            text="Add Entry Row",
            width=140,
            height=28,
            font=Theme.small_font,
            fg_color=Theme.btn_secondary,
            hover_color=Theme.btn_secondary_hover,
            border_color=Theme.btn_secondary_border,
            border_width=1,
            text_color=Theme.btn_secondary_text,
            command=self.append_blank_matrix_row,
        ).pack(side="right")

        self.canvas_scroll_wrapper = tk.Canvas(
            line_items_card,
            bg=Theme.input_bg,
            bd=0,
            highlightthickness=0,
        )
        self.canvas_scroll_wrapper.grid(row=1, column=0, sticky="nsew", padx=(15, 0))

        v_scrollbar = ctk.CTkScrollbar(
            line_items_card,
            orientation="vertical",
            command=self.canvas_scroll_wrapper.yview,
            width=12,
            fg_color=Theme.glass_panel,
            button_color=Theme.glass_border,
            button_hover_color=Theme.btn_primary,
            corner_radius=6,
        )
        v_scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 15))

        h_scrollbar = ctk.CTkScrollbar(
            line_items_card,
            orientation="horizontal",
            command=self.canvas_scroll_wrapper.xview,
            height=12,
            fg_color=Theme.glass_panel,
            button_color=Theme.glass_border,
            button_hover_color=Theme.btn_primary,
            corner_radius=6,
        )
        h_scrollbar.grid(row=2, column=0, sticky="ew", padx=(15, 15), pady=(5, 10))

        line_items_card.grid_columnconfigure(1, weight=0)
        self.canvas_scroll_wrapper.configure(
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set,
        )

        self.matrix_scroll_canvas = ctk.CTkFrame(
            self.canvas_scroll_wrapper,
            fg_color="transparent",
        )
        self.canvas_window_id = self.canvas_scroll_wrapper.create_window(
            (0, 0),
            window=self.matrix_scroll_canvas,
            anchor="nw",
        )

        def update_scroll_region(_event):
            self.canvas_scroll_wrapper.configure(
                scrollregion=self.canvas_scroll_wrapper.bbox("all")
            )

        self.matrix_scroll_canvas.bind("<Configure>", update_scroll_region)

        self.load_account_registry_lookups()
        self.load_parent_dimension_lookups()
        for _ in range(3):
            self.append_blank_matrix_row()
        if self.initial_amount:
            first_price = self.line_item_rows[0]["price"]
            first_price.delete(0, ctk.END)
            first_price.insert(0, self.initial_amount)

        footer_card = ctk.CTkFrame(self.container, fg_color="transparent", height=60)
        footer_card.grid(row=2, column=0, sticky="ew", padx=2, pady=(15, 0))
        self.running_total_lbl = ctk.CTkLabel(
            footer_card,
            text="Total Consolidated Balance: $0.00 USD",
            font=Theme.title_font,
            text_color=Theme.text_primary,
        )
        self.running_total_lbl.pack(side="left", padx=10)
        ctk.CTkButton(
            footer_card,
            text="Post Transaction",
            height=45,
            font=Theme.semi_title_font,
            fg_color=Theme.btn_primary,
            hover_color=Theme.btn_primary_hover,
            text_color=Theme.btn_primary_text,
            command=self.post_transaction_to_ledger,
            width=260,
        ).pack(side="right", padx=5)
        ctk.CTkButton(
            footer_card,
            text="Cancel",
            height=45,
            font=Theme.body_font,
            fg_color=Theme.btn_secondary,
            hover_color=Theme.btn_secondary_hover,
            border_color=Theme.btn_secondary_border,
            border_width=1,
            text_color=Theme.btn_secondary_text,
            command=self.parent_view.show_home_view,
            width=120,
        ).pack(side="right", padx=5)
        self.calculate_due_date_parameters(self.terms_var.get())
        self.recalculate_aggregate_invoice_totals()

    def load_entity_registry_lookups(self):
        try:
            with sqlite3.connect(self.parent_view.db) as conn:
                rows = conn.execute("SELECT contact_id, display_name FROM contact ORDER BY display_name").fetchall()
            self.entity_map = {
                f"{display_name or f'Contact #{contact_id}'} [ID: {contact_id}]": contact_id
                for contact_id, display_name in rows
            }
        except sqlite3.Error:
            self.entity_map = {}
        if not self.entity_map:
            self.entity_map = {"No local entities mapped": None}

    def load_project_registry_lookups(self):
        try:
            with sqlite3.connect(self.parent_view.db) as conn:
                rows = conn.execute(
                    "SELECT project_id, project_name FROM project WHERE status='Open' ORDER BY project_name"
                ).fetchall()
            self.project_map = {name: project_id for project_id, name in rows}
        except sqlite3.Error:
            self.project_map = {}
        if not self.project_map:
            self.project_map = {"None / General Overhead": None}

    def load_account_registry_lookups(self):
        try:
            with sqlite3.connect(self.parent_view.db) as conn:
                rows = conn.execute(
                    "SELECT account_id, account_code, account_name FROM chart_of_accounts ORDER BY account_code"
                ).fetchall()
            self.account_map = {
                f"{code} - {name}": account_id
                for account_id, code, name in rows
            }
        except sqlite3.Error:
            self.account_map = {}
        if not self.account_map:
            self.account_map = {"No chart of accounts loaded": None}

    def load_parent_dimension_lookups(self):
        self.parent_dimension_map = {"Select Parent Dim...": None}
        try:
            with sqlite3.connect(self.parent_view.db) as conn:
                rows = conn.execute(
                    "SELECT node_id, node_code, node_name FROM dimension_node "
                    "WHERE parent_node_id IS NULL ORDER BY node_code"
                ).fetchall()
            for node_id, node_code, node_name in rows:
                self.parent_dimension_map[f"{node_code} ({node_name})"] = node_id
        except sqlite3.Error:
            pass

    def append_blank_matrix_row(self):
        row_frame = ctk.CTkFrame(
            self.matrix_scroll_canvas,
            fg_color=Theme.input_bg,
            height=45,
            width=980,
            corner_radius=4,
            border_color=Theme.glass_border,
            border_width=1,
        )
        row_frame.pack(fill="x", pady=4, padx=2)
        row_frame.pack_propagate(False)

        account_var = ctk.StringVar(value=next(iter(self.account_map)))
        account_dropdown = ctk.CTkOptionMenu(
            row_frame,
            width=180,
            height=32,
            values=list(self.account_map),
            variable=account_var,
            fg_color=Theme.glass_panel,
            button_color=Theme.btn_secondary,
            font=Theme.small_font,
        )
        account_dropdown.pack(side="left", padx=5, pady=6)

        parent_dim_var = ctk.StringVar(value="Select Parent Dim...")
        parent_dim_dropdown = ctk.CTkOptionMenu(
            row_frame,
            width=140,
            height=32,
            values=list(self.parent_dimension_map),
            variable=parent_dim_var,
            fg_color=Theme.glass_panel,
            button_color=Theme.btn_secondary,
            font=Theme.small_font,
        )
        parent_dim_dropdown.pack(side="left", padx=5)

        sub_dim_var = ctk.StringVar(value="Select Sub-Dim...")
        sub_dimension_map = {"Select Sub-Dim...": None}
        row_metadata = {"sub_dimension_map": sub_dimension_map}

        def update_sub_dimensions(parent_label):
            parent_node_id = self.parent_dimension_map.get(parent_label)
            updated_map = {"Select Sub-Dim...": None}
            if parent_node_id is not None:
                try:
                    with sqlite3.connect(self.parent_view.db) as conn:
                        child_rows = conn.execute(
                            "SELECT node_id, node_code, node_name FROM dimension_node "
                            "WHERE parent_node_id = ? ORDER BY node_code",
                            (parent_node_id,),
                        ).fetchall()
                    for node_id, node_code, node_name in child_rows:
                        updated_map[f"{node_code} ({node_name})"] = node_id
                except sqlite3.Error:
                    pass
            row_metadata["sub_dimension_map"] = updated_map
            sub_dim_var.set("Select Sub-Dim...")
            sub_dim_dropdown.configure(values=list(updated_map))

        parent_dim_dropdown.configure(command=update_sub_dimensions)
        sub_dim_dropdown = ctk.CTkOptionMenu(
            row_frame,
            width=140,
            height=32,
            values=list(sub_dimension_map),
            variable=sub_dim_var,
            fg_color=Theme.glass_panel,
            button_color=Theme.btn_secondary,
            font=Theme.small_font,
        )
        sub_dim_dropdown.pack(side="left", padx=5)

        description_entry = ctk.CTkEntry(
            row_frame,
            placeholder_text="Line item explanation...",
            height=32,
            font=Theme.small_font,
            fg_color=Theme.input_bg,
            border_color=Theme.glass_border,
        )
        description_entry.pack(side="left", fill="x", expand=True, padx=5)

        quantity_entry = ctk.CTkEntry(row_frame, width=60, height=32, font=Theme.small_font, placeholder_text="1")
        quantity_entry.pack(side="left", padx=5)
        quantity_entry.insert(0, "1")

        price_entry = ctk.CTkEntry(row_frame, width=100, height=32, font=Theme.small_font, placeholder_text="0.00")
        price_entry.pack(side="left", padx=5)
        price_entry.insert(0, "0.00")

        row_total_label = ctk.CTkLabel(row_frame, text="$0.00", font=Theme.body_font, width=100, anchor="e")
        row_total_label.pack(side="left", padx=15)

        row_metadata.update({
            "frame": row_frame,
            "account_var": account_var,
            "parent_dim_var": parent_dim_var,
            "parent_dimension_map": self.parent_dimension_map,
            "sub_dim_var": sub_dim_var,
            "update_sub_dimensions": update_sub_dimensions,
            "description": description_entry,
            "quantity": quantity_entry,
            "price": price_entry,
            "total_label": row_total_label,
        })
        self.line_item_rows.append(row_metadata)
        quantity_entry.bind("<KeyRelease>", lambda _event: self.recalculate_aggregate_invoice_totals())
        price_entry.bind("<KeyRelease>", lambda _event: self.recalculate_aggregate_invoice_totals())
        self.recalculate_aggregate_invoice_totals()

    def recalculate_aggregate_invoice_totals(self):
        grand_total = 0.0
        for row in self.line_item_rows:
            try:
                quantity = float(row["quantity"].get().strip() or 0)
                price = float(row["price"].get().strip() or 0)
                row_total = quantity * price
                grand_total += row_total
                row["total_label"].configure(text=f"${row_total:,.2f}")
            except ValueError:
                row["total_label"].configure(text="$0.00")
        if hasattr(self, "running_total_lbl"):
            self.running_total_lbl.configure(text=f"Total Consolidated Balance: ${grand_total:,.2f} USD")

    def calculate_due_date_parameters(self, terms_selection):
        try:
            issue_date = datetime.strptime(self.date_entry.get().strip(), "%Y-%m-%d")
            days_by_term = {"Due on Receipt": 0, "Net 15": 15, "Net 30": 30, "Net 60": 60}
            due_date = issue_date + timedelta(days=days_by_term.get(terms_selection, 30))
            self.due_date = due_date.strftime("%Y-%m-%d")
        except ValueError:
            self.due_date = ""

    def post_transaction_to_ledger(self):
        contact_id = self.entity_map.get(self.cust_var.get())
        project_id = self.project_map.get(self.proj_var.get())
        invoice_number = self.inv_num_entry.get().strip()
        issue_date = self.date_entry.get().strip()
        transaction_type = self.txn_type_var.get()
        terms = self.terms_var.get()

        if not contact_id or not invoice_number:
            messagebox.showerror(
                "Validation Failure",
                "Select a contact and enter a document reference before posting.",
            )
            return
        try:
            datetime.strptime(issue_date, "%Y-%m-%d")
            self.calculate_due_date_parameters(terms)
            if not self.due_date:
                raise ValueError("Enter a valid issue date in YYYY-MM-DD format.")

            posting_lines = []
            for row in self.line_item_rows:
                account_id = self.account_map.get(row["account_var"].get())
                if not account_id:
                    continue
                quantity = float(row["quantity"].get().strip() or 1)
                unit_price = float(row["price"].get().strip() or 0)
                if quantity <= 0 or unit_price < 0:
                    raise ValueError("Line quantities must be positive and prices cannot be negative.")
                amount_cents = int(round(quantity * unit_price * 100))
                parent_dimension_id = row["parent_dimension_map"].get(row["parent_dim_var"].get())
                sub_dimension_id = row["sub_dimension_map"].get(row["sub_dim_var"].get())
                posting_lines.append(
                    (
                        account_id,
                        parent_dimension_id,
                        sub_dimension_id,
                        row["description"].get().strip(),
                        quantity,
                        int(round(unit_price * 100)),
                        amount_cents,
                    )
                )

            if not posting_lines:
                raise ValueError("Add at least one line item with a valid chart-of-accounts entry.")

            with sqlite3.connect(self.parent_view.db) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO invoice (invoice_type, contact_id, project_id, invoice_number, issue_date, due_date, terms, status, total_cents) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', 0)",
                    (
                        transaction_type,
                        contact_id,
                        project_id,
                        invoice_number,
                        issue_date,
                        self.due_date,
                        terms,
                    ),
                )
                invoice_id = cursor.lastrowid
                total_cents = 0
                for account_id, parent_dimension_id, sub_dimension_id, description, quantity, unit_price_cents, amount_cents in posting_lines:
                    total_cents += amount_cents
                    cursor.execute(
                        "INSERT INTO invoice_line (invoice_id, account_id, parent_dimension_id, sub_dimension_id, description, quantity, unit_price_cents, amount_cents) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            invoice_id,
                            account_id,
                            parent_dimension_id,
                            sub_dimension_id,
                            description,
                            quantity,
                            unit_price_cents,
                            amount_cents,
                        ),
                    )
                cursor.execute(
                    "UPDATE invoice SET total_cents = ? WHERE invoice_id = ?",
                    (total_cents, invoice_id),
                )

            messagebox.showinfo(
                "Success",
                f"Transaction {invoice_number} posted successfully into the company sub-ledger.",
            )
            self.parent_view.show_home_view()
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("Ledger Write Failure", f"Unable to post transaction: {exc}")
