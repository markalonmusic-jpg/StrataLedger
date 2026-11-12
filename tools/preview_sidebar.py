"""Preview the sidebar on its own, with fake items and a fake user.

    python tools/preview_sidebar.py [--role Accountant] [--active billing]

Opens no database and does not start the app (the app upgrades databases on
launch). Clicking a row moves the highlight; the toggle flips the status dot.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk  # noqa: E402

from config import Theme  # noqa: E402
from modules.sidebar import NavItem, Sidebar  # noqa: E402

FAKE_ITEMS = (
    NavItem("MAIN CHANNELS", "Flight Deck Base", "home", None, "⌂"),
    NavItem("CUSTOMERS SYSTEMS", "Customers Flight Deck", "customers.dashboard", ("Master", "Admin"), "◈"),
    NavItem("CUSTOMERS SYSTEMS", "Customer List", "customers.list", ("Master", "Admin"), "☰"),
    NavItem("CUSTOMERS SYSTEMS", "Create / Edit Customers", "customers.create", ("Master", "Admin"), "✚"),
    NavItem("REVENUES CORE TOOLS", "Billing & Invoices", "billing", ("Master", "Admin", "Accountant"), "▤"),
    NavItem("OPERATIONS & COST (AP)", "Workforce HR & Payroll", "payroll", ("Master", "Accountant"), "⏲"),
)


def build_preview(role="Master", active="home", user_name="preview user", items=FAKE_ITEMS, root=None):
    """Build the preview window; pass root (e.g. a CTkToplevel) to reuse an existing Tk instance."""
    root = root or ctk.CTk()
    root.title("Sidebar preview")
    root.geometry(f"{Theme.sidebar_width + 360}x640")
    root.configure(fg_color=Theme.bg_color)
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=1)
    status = ctk.CTkLabel(root, text="", font=Theme.body_font, text_color=Theme.text_secondary)
    status.grid(row=0, column=1, sticky="n", pady=Theme.pad_lg)
    state = {"open": True}

    def navigate(page_key):
        sidebar.set_active(page_key)
        status.configure(text=f"navigate -> {page_key}")

    def toggle():
        state["open"] = not state["open"]
        sidebar.set_assistant_open(state["open"])
        status.configure(text=f"assistant open = {state['open']}")

    sidebar = Sidebar(root, items=items, current_role=role, user_name=user_name,
                      on_navigate=navigate, on_user_click=lambda: navigate(None),
                      on_toggle_assistant=toggle, assistant_open=state["open"])
    sidebar.grid(row=0, column=0, sticky="nsw")
    sidebar.set_active(active)
    return root, sidebar


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--role", default="Master")
    parser.add_argument("--active", default="home")
    args = parser.parse_args(argv)
    ctk.set_appearance_mode("Dark")
    root, _ = build_preview(args.role, args.active)
    root.mainloop()


if __name__ == "__main__":
    main()
