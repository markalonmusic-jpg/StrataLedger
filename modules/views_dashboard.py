import customtkinter as ctk
from config import Theme

def render_dashboard_flight_deck(parent_view, workspace_frame):
    view_frame = ctk.CTkScrollableFrame(workspace_frame, corner_radius=0, fg_color="transparent")
    view_frame.grid(row=0, column=0, sticky="nsew")
    view_frame.grid_columnconfigure(0, weight=1)

    # Header Section
    lbl_head = ctk.CTkLabel(view_frame, text="Customers Command Center", font=Theme.title_font, text_color=Theme.text_primary)
    lbl_head.pack(anchor="w", padx=30, pady=(30, 20))

    # --- PANEL A: QUICK ACTIONS ACCELERATORS ---
    lbl_sec1 = ctk.CTkLabel(view_frame, text="QUICK ACTIONS", font=Theme.section_font, text_color=Theme.accent_glow)
    lbl_sec1.pack(anchor="w", padx=30, pady=(10, 5))
    
    actions_frame = ctk.CTkFrame(view_frame, fg_color="transparent")
    actions_frame.pack(fill="x", padx=30, pady=(0, 20))
    
    btn_act1 = ctk.CTkButton(actions_frame, text="Go to CRM Sales Desk", height=50, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text, font=Theme.body_font)
    btn_act1.pack(side="left", expand=True, fill="x", padx=(0, 10))
    
    btn_act2 = ctk.CTkButton(actions_frame, text="Create New Customer", height=50, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text, font=Theme.body_font, command=lambda: parent_view.switch_customers_view("Create"))
    btn_act2.pack(side="left", expand=True, fill="x", padx=10)
    
    btn_act3 = ctk.CTkButton(actions_frame, text="View Customer Master List", height=50, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text, font=Theme.body_font, command=lambda: parent_view.switch_customers_view("Master"))
    btn_act3.pack(side="left", expand=True, fill="x", padx=(10, 0))

    # --- PANEL B: COMMERCIAL SNAPSHOTS ---
    lbl_sec2 = ctk.CTkLabel(view_frame, text="REVENUE FUNNEL SNAPSHOT", font=Theme.section_font, text_color=Theme.accent_glow)
    lbl_sec2.pack(anchor="w", padx=30, pady=(10, 5))

    metrics_frame = ctk.CTkFrame(view_frame, fg_color="transparent")
    metrics_frame.pack(fill="x", padx=30, pady=(0, 25))

    card_m1 = ctk.CTkFrame(metrics_frame, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=8)
    card_m1.pack(side="left", expand=True, fill="x", padx=(0, 10))
    ctk.CTkLabel(card_m1, text="Total Active Accounts", font=Theme.small_font, text_color=Theme.text_secondary).pack(anchor="w", padx=15, pady=(15, 2))
    ctk.CTkLabel(card_m1, text="142 Clients", font=Theme.semi_title_font, text_color=Theme.text_primary).pack(anchor="w", padx=15, pady=(0, 15))

    card_m2 = ctk.CTkFrame(metrics_frame, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=8)
    card_m2.pack(side="left", expand=True, fill="x", padx=10)
    ctk.CTkLabel(card_m2, text="B2B SaaS ARR Cohort Run-Rate", font=Theme.small_font, text_color=Theme.text_secondary).pack(anchor="w", padx=15, pady=(15, 2))
    ctk.CTkLabel(card_m2, text="$142,500.00", font=Theme.semi_title_font, text_color=Theme.text_primary).pack(anchor="w", padx=15, pady=(0, 15))

    card_m3 = ctk.CTkFrame(metrics_frame, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=8)
    card_m3.pack(side="left", expand=True, fill="x", padx=(10, 0))
    ctk.CTkLabel(card_m3, text="Open Commercial Sales Pipeline", font=Theme.small_font, text_color=Theme.text_secondary).pack(anchor="w", padx=15, pady=(15, 2))
    ctk.CTkLabel(card_m3, text="$685,000.00", font=Theme.semi_title_font, text_color=Theme.text_primary).pack(anchor="w", padx=15, pady=(0, 15))

    # --- PANEL C: REVENUE PIPELINE ALERTS ---
    lbl_sec3 = ctk.CTkLabel(view_frame, text="REVENUE PIPELINE ALERTS", font=Theme.section_font, text_color=Theme.error_glow)
    lbl_sec3.pack(anchor="w", padx=30, pady=(10, 5))

    alerts_frame = ctk.CTkFrame(view_frame, fg_color=Theme.glass_panel, border_color=Theme.glass_border, border_width=1, corner_radius=8)
    alerts_frame.pack(fill="x", padx=30, pady=(0, 30))

    alerts_data = [
        ("INBOUND LEAD", "New Web Form Submission: Acme Corp requested Enterprise Sandbox tier plan.", "ASSIGN SALES REP"),
        ("STALLED OPPORTUNITY", "Deal 'Highway 101 Expansion' has sat trapped over 22 days in Proposal Sent validation.", "VIEW TIMELINE"),
        ("CONVERSION TRIGGER", "Pipeline shift to Closed-Won: Mark Aglugub Construction signed contract terms.", "GENERATE INTAKE")
    ]

    for i, (prefix, details, action_txt) in enumerate(alerts_data):
        row_frame = ctk.CTkFrame(alerts_frame, fg_color="transparent")
        row_frame.pack(fill="x", padx=15, pady=10)
        
        lbl_alert = ctk.CTkLabel(row_frame, text=f"{prefix} {details}", font=Theme.body_font, text_color=Theme.text_primary)
        lbl_alert.pack(side="left", anchor="w")
        
        btn_action = ctk.CTkButton(row_frame, text=action_txt, width=130, height=28, font=Theme.small_font, fg_color=Theme.btn_secondary, hover_color=Theme.btn_secondary_hover, border_color=Theme.btn_secondary_border, border_width=1, text_color=Theme.btn_secondary_text)
        btn_action.pack(side="right", anchor="e")
        
        if i < len(alerts_data) - 1:
            divider = ctk.CTkFrame(alerts_frame, height=1, fg_color=Theme.glass_border)
            divider.pack(fill="x", padx=15)
