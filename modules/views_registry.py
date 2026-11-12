import customtkinter as ctk
import sqlite3
from tkinter import ttk
from config import Theme

def render_customer_master_registry(parent_view, workspace_frame):
    view_frame = ctk.CTkFrame(workspace_frame, corner_radius=0, fg_color="transparent")
    view_frame.grid(row=0, column=0, sticky="nsew")
    view_frame.grid_columnconfigure(0, weight=1)
    view_frame.grid_rowconfigure(2, weight=1)

    # Fixed Header Text
    lbl_head = ctk.CTkLabel(view_frame, text="Customer Master List", font=Theme.title_font, text_color=Theme.text_primary)
    lbl_head.grid(row=0, column=0, sticky="w", pady=(0, 20))

    # SEARCH ZONE AND FILTER BAR
    search_zone = ctk.CTkFrame(view_frame, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=8)
    search_zone.grid(row=1, column=0, sticky="ew", pady=(0, 15), padx=2)
    search_zone.grid_columnconfigure(0, weight=1)

    search_entry = ctk.CTkEntry(
        search_zone, height=40, font=Theme.body_font, fg_color=Theme.glass_panel, border_color=Theme.glass_border, placeholder_text="Search by Customer Name, Tax ID (TIN/EIN), Billing State..."
    )
    search_entry.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
    
    pills_frame = ctk.CTkFrame(search_zone, fg_color="transparent")
    pills_frame.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
    
    ctk.CTkButton(pills_frame, text="Show All Rows", width=90, height=26, font=Theme.small_font, fg_color=Theme.btn_primary, hover_color=Theme.btn_primary_hover, text_color=Theme.btn_primary_text).pack(side="left", padx=(0, 8))
    ctk.CTkButton(pills_frame, text="SaaS Accounts", width=90, height=26, font=Theme.small_font, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text).pack(side="left", padx=8)
    ctk.CTkButton(pills_frame, text="Construction Clients", width=120, height=26, font=Theme.small_font, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text).pack(side="left", padx=8)

    # DATA-GRID TREEVIEW LEDGER MATRIX PANEL
    grid_frame = ctk.CTkFrame(view_frame, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=8)
    grid_frame.grid(row=2, column=0, sticky="nsew", padx=2)
    grid_frame.grid_columnconfigure(0, weight=1)
    grid_frame.grid_rowconfigure(0, weight=1)

    style = ttk.Style()
    style.theme_use("default")
    style.configure("Treeview", background=Theme.glass_panel, foreground=Theme.text_primary, fieldbackground=Theme.glass_panel, rowheight=35, borderwidth=0, font=Theme.body_font)
    style.configure("Treeview.Heading", background=Theme.sidebar_bg, foreground=Theme.text_primary, borderwidth=0, font=Theme.semi_title_font)
    style.map("Treeview", background=[('selected', Theme.accent_glow)], foreground=[('selected', Theme.text_primary)])

    cols = ("contact_id", "name", "entity", "channel", "financials", "region")
    tree = ttk.Treeview(grid_frame, columns=cols, show="headings", style="Treeview")
    
    tree.heading("name", text="Customer Name", anchor="w")
    tree.heading("entity", text="Entity Type", anchor="w")
    tree.heading("channel", text="Commercial Channel", anchor="w")
    tree.heading("financials", text="AR Balance", anchor="w")
    tree.heading("region", text="State", anchor="w")

    tree.column("contact_id", width=0, minwidth=0, stretch=False)
    tree.column("name", width=280, anchor="w")
    tree.column("entity", width=140, anchor="w")
    tree.column("channel", width=180, anchor="w")
    tree.column("financials", width=180, anchor="w")
    tree.column("region", width=100, anchor="w")

    # 📊 LIVE DATABASE DATA SYNC LINK
    try:
        conn = sqlite3.connect(parent_view.db)
        cursor = conn.cursor()
        
        # Select active records from database matching contacts
        contacts = cursor.execute("""
            SELECT c.contact_id, c.name, c.entity_type, c.address,
                   CASE WHEN s.contact_id IS NOT NULL THEN 'B2B SaaS Subscriptions' ELSE 'Construction Contracts' END as channel
            FROM contact c
            LEFT JOIN saas_subscription s ON c.contact_id = s.contact_id
            WHERE c.is_customer = 1 AND c.is_active = 1
        """).fetchall()
        
        for row in contacts:
            c_id, name, entity, addr, channel = row
            # Format row data safely to mirror visual design parameters
            tree.insert("", "end", values=(
                c_id, 
                name, 
                entity if entity else "Corp", 
                channel, 
                "Balance: $0.00 (Current)", 
                addr if addr else "NCR (PH)"
            ))
        conn.close()
    except Exception as e:
        print(f"Error querying live rows from contact registry database space: {str(e)}")

    tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
    
    scrollbar = ttk.Scrollbar(grid_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns", pady=10)

    # MOUSE ROUTING HANDLER LAYER
    def handle_double_click_row(event):
        selected_item = tree.selection()
        if not selected_item:
            return
            
        row_values = tree.item(selected_item, "values")
        if row_values:
            target_contact_id = int(row_values[0])  # Extracts genuine database primary key index
            parent_view.switch_customers_view("Create", edit_id=target_contact_id)

    tree.bind("<Double-Button-1>", handle_double_click_row)
