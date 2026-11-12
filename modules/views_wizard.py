import os
import sys
import tkinter as tk
import customtkinter as ctk
import sqlite3

# Force local system path evaluation to prevent cross-module loading failures
modules_path = os.path.dirname(os.path.abspath(__file__))
if modules_path not in sys.path:
    sys.path.insert(0, modules_path)

from config import Theme

# ==============================================================================
# WIZARD STORAGE RUNTIME LAYER — THE DATA PERSISTENCE CONTROLLER
# ==============================================================================
class CustomerWizardController:
    @staticmethod
    def save_intake_form_action(wizard_instance):
        """Extracts field values and maps explicit address layout fields to distinct database columns."""
        name = wizard_instance.ent_name.get().strip()
        entity = wizard_instance.entity_type_var.get()
        tax = wizard_instance.tax_placeholder_entry.get().strip()
        email = wizard_instance.ent_email.get().strip()
        phone = wizard_instance.ent_phone.get().strip()
        bir_name = wizard_instance.ent_bir.get().strip() if hasattr(wizard_instance, 'ent_bir') else name

        # Extract explicit address field entries
        street = wizard_instance.ent_addr.get().strip()
        city = wizard_instance.ent_city.get().strip()
        state = wizard_instance.ent_state.get().strip()
        zip_code = wizard_instance.ent_zip.get().strip()

        if not name or not tax:
            print("⚠️ Form Validation Failure: Mandatory core fields are missing.")
            return
        
        try:
            conn = sqlite3.connect(wizard_instance.parent_view.db)
            cursor = conn.cursor()
            
            # 🔄 EDIT MODE STATE: Update unique columns without messing with older data blocks
            if wizard_instance.editing_contact_id:
                cursor.execute("""
                    UPDATE contact 
                    SET name=?, bir_registered_name=?, entity_type=?, email=?, phone=?, 
                        mailing_street=?, mailing_city=?, mailing_state=?, mailing_zip=?, tax_id=?
                    WHERE contact_id=?
                """, (name, bir_name, entity, email, phone, street, city, state, zip_code, tax, wizard_instance.editing_contact_id))
                contact_id = wizard_instance.editing_contact_id
                print(f"🎉 UPDATE SUCCESS: Customer ID #{contact_id} data profile columns updated successfully.")
            
            # 🆕 INTAKE MODE STATE: Build standard row records with granular column arrays
            else:
                cursor.execute("""
                    INSERT INTO contact (name, bir_registered_name, entity_type, is_customer, is_vendor, email, phone, 
                                        mailing_street, mailing_city, mailing_state, mailing_zip, tax_id) 
                    VALUES (?, ?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?)
                """, (name, bir_name, entity, email, phone, street, city, state, zip_code, tax))
                contact_id = cursor.lastrowid
                print(f"🎉 INSERT SUCCESS: Customer profile column entries initialized successfully.")

            # Handle subscription entries...
            if wizard_instance.channel_var.get() == "B2B SaaS Subscriptions" and hasattr(wizard_instance, 'saas_mrr'):
                tier = wizard_instance.saas_tier.get()
                mrr = int(wizard_instance.saas_mrr.get().strip() or 0)
                cursor.execute("INSERT OR REPLACE INTO saas_subscription (contact_id, plan_tier_name, base_mrr_cents, next_billing_cycle_date, status) VALUES (?, ?, ?, DATE('now', '+30 days'), 'Active')", (contact_id, tier, mrr))
                
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Database System Fault: {str(e)}")
            
        wizard_instance.parent_view.switch_customers_view("Dashboard")
# ==============================================================================
# UNIFIED VISUAL DISPLAY — THE ADAPTIVE INTAKE WIZARD CLASS FRAMEWORK
# ==============================================================================
class CustomerIntakeWizard:
    def __init__(self, parent_view, workspace_frame, edit_contact_id=None):
        self.parent_view = parent_view
        self.controller = CustomerWizardController
        self.editing_contact_id = edit_contact_id
        self.parent_view.set_breadcrumb(
            "PLATFORM",
            "CUSTOMERS",
            "EDIT PROFILE" if edit_contact_id else "NEW INTAKE",
        )

        workspace_frame.grid_rowconfigure(0, weight=1)
        workspace_frame.grid_rowconfigure(1, weight=0)
        workspace_frame.grid_columnconfigure(0, weight=1)
        self.wizard_scroll = ctk.CTkScrollableFrame(
            workspace_frame,
            corner_radius=0,
            fg_color="transparent",
        )
        self.wizard_scroll.grid(row=0, column=0, sticky="nsew")
        self.wizard_scroll.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.wizard_scroll, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 8))
        ctk.CTkLabel(
            header,
            text="Customer Intake Form",
            font=Theme.title_font,
            text_color=Theme.text_primary,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Complete the following steps to onboard a new corporate entity into the StrataLedger platform.",
            font=Theme.body_font,
            text_color=Theme.text_secondary,
        ).pack(anchor="w", pady=(3, 0))

        self.box_step1 = self._create_step_card(1, "CORPORATE ENTITY CLASSIFICATION")
        entity_row = ctk.CTkFrame(self.box_step1, fg_color="transparent")
        entity_row.pack(fill="x", padx=24, pady=(20, 10))
        entity_row.grid_columnconfigure(0, weight=3)
        entity_row.grid_columnconfigure(1, weight=2)

        name_field = ctk.CTkFrame(entity_row, fg_color="transparent")
        name_field.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self._create_field_label(name_field, "CUSTOMER NAME")
        self.ent_name = self._create_entry(
            name_field,
            placeholder="e.g., StrataLedger Corp Ltd",
        )

        type_field = ctk.CTkFrame(entity_row, fg_color="transparent")
        type_field.grid(row=0, column=1, sticky="ew", padx=(12, 0))
        self._create_field_label(type_field, "ENTITY TYPE")
        self.entity_type_var = tk.StringVar(value="Corp")
        self.segment_toggle = ctk.CTkSegmentedButton(
            type_field,
            values=["LLC", "Corp", "LLP"],
            command=self.execute_ux_entity_pivot_masking,
            variable=self.entity_type_var,
            font=Theme.small_font,
            selected_color=Theme.btn_primary,
            selected_hover_color=Theme.btn_primary_hover,
            unselected_color=Theme.input_bg,
            unselected_hover_color=Theme.btn_secondary_hover,
            text_color=Theme.btn_secondary_text,
            corner_radius=8,
            height=38,
        )
        self.segment_toggle.pack(fill="x", pady=(5, 0))

        legal_field = ctk.CTkFrame(self.box_step1, fg_color="transparent")
        legal_field.pack(fill="x", padx=24, pady=(0, 22))
        self._create_field_label(legal_field, "LEGAL NAME")
        self.compliance_shell = ctk.CTkFrame(legal_field, fg_color="transparent")
        self.compliance_shell.pack(fill="x")
        self.execute_ux_entity_pivot_masking(self.entity_type_var.get())

        self.box_step2 = self._create_step_card(2, "CORE COMMUNICATIONS & AR MAILING")
        contact_grid = ctk.CTkFrame(self.box_step2, fg_color="transparent")
        contact_grid.pack(fill="x", padx=24, pady=(20, 22))
        contact_grid.grid_columnconfigure((0, 1), weight=1)

        col_left = ctk.CTkFrame(contact_grid, fg_color="transparent")
        col_left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._create_field_label(col_left, "EMAIL ADDRESS")
        self.ent_email = self._create_entry(
            col_left,
            placeholder="billing@clientdomain.com",
        )
        self.ent_email.pack_configure(pady=(5, 12))
        self._create_field_label(col_left, "TAX ID (EIN/TIN)")
        self.tax_placeholder_entry = self._create_entry(
            col_left,
            placeholder="Enter 9-Digit EIN",
        )
        self.tax_placeholder_entry.pack_configure(pady=(5, 12))
        self._create_field_label(col_left, "PRIMARY PHONE")
        self.ent_phone = self._create_entry(
            col_left,
            placeholder="+1 (555) 019-2834",
        )
        self.ent_phone.pack_configure(pady=(5, 0))

        col_right = ctk.CTkFrame(contact_grid, fg_color="transparent")
        col_right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self._create_field_label(col_right, "STREET ADDRESS")
        self.ent_addr = self._create_entry(
            col_right,
            placeholder="e.g., 271 Shipley Ave",
        )
        self.ent_addr.pack_configure(pady=(5, 12))

        postal_row = ctk.CTkFrame(col_right, fg_color="transparent")
        postal_row.pack(fill="x")
        postal_row.grid_columnconfigure(0, weight=2)
        postal_row.grid_columnconfigure((1, 2), weight=1)
        for column, (label, attribute, placeholder) in enumerate(
            (
                ("CITY", "ent_city", "SF"),
                ("STATE", "ent_state", "CA"),
                ("ZIP", "ent_zip", "94103"),
            )
        ):
            field = ctk.CTkFrame(postal_row, fg_color="transparent")
            field.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 8, 0),
            )
            self._create_field_label(field, label)
            setattr(self, attribute, self._create_entry(field, placeholder=placeholder))

        self.box_step3 = self._create_step_card(3, "OPERATIONAL REVENUE FORK")
        self.channel_var = tk.StringVar(value="B2B SaaS Subscriptions")
        self.fork_toggle = ctk.CTkSegmentedButton(
            self.box_step3,
            values=["B2B SaaS Subscriptions", "Construction Contracts"],
            command=self.execute_ux_revenue_channel_fork,
            variable=self.channel_var,
            font=Theme.small_font,
            selected_color=Theme.btn_primary,
            selected_hover_color=Theme.btn_primary_hover,
            unselected_color=Theme.input_bg,
            unselected_hover_color=Theme.btn_secondary_hover,
            text_color=Theme.btn_secondary_text,
            corner_radius=8,
            height=38,
        )
        self.fork_toggle.pack(fill="x", padx=24, pady=(20, 12))

        self.dynamic_shell = ctk.CTkFrame(
            self.box_step3,
            fg_color=Theme.input_bg,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=8,
        )
        self.dynamic_shell.pack(fill="x", padx=24, pady=(0, 22))
        self.dynamic_title = ctk.CTkLabel(
            self.dynamic_shell,
            text="",
            font=Theme.section_font,
            text_color=Theme.text_secondary,
            anchor="w",
        )
        self.dynamic_title.pack(fill="x", padx=16, pady=(14, 2))
        self.dynamic_deck_frame = ctk.CTkFrame(
            self.dynamic_shell,
            fg_color="transparent",
        )
        self.dynamic_deck_frame.pack(fill="x", padx=16, pady=(4, 10))
        self.execute_ux_revenue_channel_fork(self.channel_var.get())

        footer = ctk.CTkFrame(workspace_frame, fg_color="transparent", corner_radius=0)
        footer.grid(row=1, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(
            footer,
            height=1,
            corner_radius=0,
            fg_color=Theme.glass_border,
        ).grid(row=0, column=0, sticky="ew")
        footer_content = ctk.CTkFrame(footer, fg_color="transparent")
        footer_content.grid(row=1, column=0, sticky="ew")
        footer_content.grid_columnconfigure(0, weight=1)

        progress = ctk.CTkFrame(footer_content, fg_color="transparent")
        progress.grid(row=0, column=0, sticky="w", padx=24, pady=12)
        ctk.CTkLabel(
            progress,
            text="PROGRESS",
            font=Theme.small_font,
            text_color=Theme.text_muted,
        ).pack(side="left", padx=(0, 12))
        for index in range(3):
            ctk.CTkFrame(
                progress,
                width=24,
                height=4,
                corner_radius=2,
                fg_color=Theme.btn_primary if index == 0 else Theme.glass_border,
            ).pack(side="left", padx=(0, 5))

        actions = ctk.CTkFrame(footer_content, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=18, pady=8)
        ctk.CTkButton(
            actions,
            text="DRAFT SAVE",
            height=36,
            font=Theme.small_font,
            fg_color="transparent",
            hover_color=Theme.btn_secondary_hover,
            text_color=Theme.text_muted,
            state="disabled",
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            actions,
            text="COMPLETE INTAKE",
            height=36,
            font=Theme.small_font,
            fg_color=Theme.btn_primary,
            hover_color=Theme.btn_primary_hover,
            text_color=Theme.btn_primary_text,
            command=lambda: self.controller.save_intake_form_action(self),
        ).pack(side="left")

        # 🚀 EXTRACT AND RECORD MAPPING: Pre-populate entries if an ID was passed down
        if self.editing_contact_id:
            self.load_and_populate_existing_profile_data()

    def _create_step_card(self, number, title):
        card = ctk.CTkFrame(
            self.wizard_scroll,
            fg_color=Theme.glass_panel,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=12,
        )
        card.pack(fill="x", padx=18, pady=8)
        heading = ctk.CTkFrame(card, fg_color="transparent")
        heading.pack(fill="x", padx=24, pady=(20, 0))
        ctk.CTkLabel(
            heading,
            text=str(number),
            width=30,
            height=30,
            corner_radius=15,
            fg_color=Theme.btn_primary,
            text_color=Theme.btn_primary_text,
            font=Theme.section_font,
        ).pack(side="left")
        ctk.CTkLabel(
            heading,
            text=title,
            font=Theme.section_font,
            text_color=Theme.text_primary,
            anchor="w",
        ).pack(side="left", padx=12)
        return card

    @staticmethod
    def _create_field_label(parent, text):
        ctk.CTkLabel(
            parent,
            text=text,
            font=Theme.small_font,
            text_color=Theme.text_muted,
            anchor="w",
        ).pack(fill="x")

    @staticmethod
    def _create_entry(parent, placeholder):
        entry = ctk.CTkEntry(
            parent,
            height=38,
            corner_radius=8,
            font=Theme.body_font,
            fg_color=Theme.input_bg,
            border_color=Theme.glass_border,
            placeholder_text=placeholder,
        )
        entry.pack(fill="x", pady=(5, 0))
        return entry

    def execute_ux_entity_pivot_masking(self, selection_value):
        """Redraws specific registration entry configurations based on the profile layout rules."""
        if not hasattr(self, "ent_bir"):
            self.ent_bir = self._create_entry(
                self.compliance_shell,
                placeholder="Legally Registered Entity Name",
            )
        if hasattr(self, "tax_placeholder_entry"):
            self.tax_placeholder_entry.configure(placeholder_text="Enter 9-Digit EIN")

    def execute_ux_revenue_channel_fork(self, selection_value):
        """Swaps custom entry boxes depending on corporate channel selections."""
        for child in self.dynamic_deck_frame.winfo_children():
            child.destroy()

        if "SaaS" in selection_value:
            self.dynamic_title.configure(text="AUTOMATED PROVISIONING LOGS")

            f_grid = ctk.CTkFrame(self.dynamic_deck_frame, fg_color="transparent")
            f_grid.pack(fill="x", pady=(8, 10))
            f_grid.grid_columnconfigure((0, 1), weight=1)

            col_l = ctk.CTkFrame(f_grid, fg_color="transparent")
            col_l.grid(row=0, column=0, sticky="ew", padx=(0, 10))
            self._create_field_label(col_l, "SUBSCRIPTION TIER")
            self.saas_tier = ctk.CTkComboBox(
                col_l,
                height=38,
                corner_radius=8,
                font=Theme.body_font,
                values=["Growth Sandbox Tier", "Enterprise Pro Cloud Track"],
                fg_color=Theme.input_bg,
                border_color=Theme.glass_border,
                button_color=Theme.btn_secondary,
                button_hover_color=Theme.btn_secondary_hover,
            )
            self.saas_tier.pack(fill="x", pady=(5, 0))

            col_r = ctk.CTkFrame(f_grid, fg_color="transparent")
            col_r.grid(row=0, column=1, sticky="ew", padx=(10, 0))
            self._create_field_label(col_r, "MRR VALUE (CENTS)")
            self.saas_mrr = ctk.CTkEntry(
                col_r,
                height=38,
                corner_radius=8,
                font=Theme.body_font,
                fg_color=Theme.input_bg,
                border_color=Theme.glass_border,
                placeholder_text="150000",
            )
            self.saas_mrr.pack(fill="x", pady=(5, 0))
            
        else:
            self.dynamic_title.configure(text="FIELD OPERATION FULFILLMENT")

            f_grid = ctk.CTkFrame(self.dynamic_deck_frame, fg_color="transparent")
            f_grid.pack(fill="x", pady=(8, 10))
            f_grid.grid_columnconfigure((0, 1), weight=1)

            col_l = ctk.CTkFrame(f_grid, fg_color="transparent")
            col_l.grid(row=0, column=0, sticky="ew", padx=(0, 10))
            self._create_field_label(col_l, "DEPARTMENT ALLOCATION")
            self.con_dept = ctk.CTkComboBox(
                col_l,
                height=38,
                corner_radius=8,
                font=Theme.body_font,
                values=["DEPT-100: Heavy Field Operations", "DEPT-400: Growth Systems"],
                fg_color=Theme.input_bg,
                border_color=Theme.glass_border,
                button_color=Theme.btn_secondary,
                button_hover_color=Theme.btn_secondary_hover,
            )
            self.con_dept.pack(fill="x", pady=(5, 0))

            col_r = ctk.CTkFrame(f_grid, fg_color="transparent")
            col_r.grid(row=0, column=1, sticky="ew", padx=(10, 0))
            self._create_field_label(col_r, "ASSIGNED SALES EXECUTIVE")
            self.con_exec = ctk.CTkComboBox(
                col_r,
                height=38,
                corner_radius=8,
                font=Theme.body_font,
                values=["Sales Executive John Smith", "Venture Analyst Jane Doe"],
                fg_color=Theme.input_bg,
                border_color=Theme.glass_border,
                button_color=Theme.btn_secondary,
                button_hover_color=Theme.btn_secondary_hover,
            )
            self.con_exec.pack(fill="x", pady=(5, 0))

    def load_and_populate_existing_profile_data(self):
        """Sweeps database tables for the active key to fill form entry values via explicit columns."""
        try:
            conn = sqlite3.connect(self.parent_view.db)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            contact_data = cursor.execute("SELECT * FROM contact WHERE contact_id=?", (self.editing_contact_id,)).fetchone()
            
            if contact_data:
                self.ent_name.delete(0, tk.END)
                self.ent_name.insert(0, contact_data['name'])
                
                entity_type = contact_data['entity_type'] or "Corp"
                if entity_type not in {"LLC", "Corp", "LLP"}:
                    entity_type = "LLC" if "LLC" in entity_type or "Individual" in entity_type else "Corp"
                self.entity_type_var.set(entity_type)
                self.execute_ux_entity_pivot_masking(entity_type)
                
                if hasattr(self, 'ent_bir') and contact_data['bir_registered_name']:
                    self.ent_bir.delete(0, tk.END)
                    self.ent_bir.insert(0, contact_data['bir_registered_name'])
                
                self.ent_email.delete(0, tk.END)
                self.ent_email.insert(0, contact_data['email'] or "")
                
                self.tax_placeholder_entry.delete(0, tk.END)
                self.tax_placeholder_entry.insert(0, contact_data['tax_id'] or "")
                
                self.ent_phone.delete(0, tk.END)
                self.ent_phone.insert(0, contact_data['phone'] or "")
                
                # 🎯 EXPLICIT DATA POPULATION LAYER
                self.ent_addr.delete(0, tk.END)
                self.ent_addr.insert(0, contact_data['mailing_street'] or "")
                
                self.ent_city.delete(0, tk.END)
                self.ent_city.insert(0, contact_data['mailing_city'] or "")
                
                self.ent_state.delete(0, tk.END)
                self.ent_state.insert(0, contact_data['mailing_state'] or "")
                
                self.ent_zip.delete(0, tk.END)
                self.ent_zip.insert(0, contact_data['mailing_zip'] or "")

                saas_data = cursor.execute("SELECT * FROM saas_subscription WHERE contact_id=?", (self.editing_contact_id,)).fetchone()
                if saas_data:
                    self.channel_var.set("B2B SaaS Subscriptions")
                    self.execute_ux_revenue_channel_fork("B2B SaaS Subscriptions")
                    self.saas_tier.set(saas_data['plan_tier_name'])
                    self.saas_mrr.delete(0, tk.END)
                    self.saas_mrr.insert(0, str(saas_data['base_mrr_cents']))
                else:
                    self.channel_var.set("Construction Contracts")
                    self.execute_ux_revenue_channel_fork("Construction Contracts")
            conn.close()
        except Exception as e:
            print(f"Error pre-populating fields: {str(e)}")
