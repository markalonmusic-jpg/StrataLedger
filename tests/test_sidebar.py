"""Smoke tests for the sidebar: built from fake items only (no database, no app)."""
import importlib.util
import re
import tkinter as tk
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ctk = pytest.importorskip("customtkinter")

from config import Theme  # noqa: E402
from modules.sidebar import NavItem, Sidebar, initials_for, visible_items  # noqa: E402

ITEMS = (
    NavItem("MAIN", "Home", "home", None, "⌂"),
    NavItem("MONEY", "Billing", "billing", ("Master", "AR"), "▤"),
    NavItem("MONEY", "Payroll", "payroll", ("Master", "HR"), "⏲"),
)


@pytest.fixture(scope="session")
def tk_app():
    # One Tk instance per test session: creating several Tk() roots in one
    # process intermittently fails on Windows to find tk.tcl / init.tcl.
    try:
        app = ctk.CTk()
    except tk.TclError as error:  # genuinely no display available
        pytest.skip(f"no display: {error}")
    app.withdraw()
    yield app
    app.destroy()


@pytest.fixture
def root(tk_app):
    window = ctk.CTkToplevel(tk_app)
    window.withdraw()
    yield window
    window.destroy()
    tk_app.update_idletasks()


def build(root, role="Master", calls=None):
    calls = calls if calls is not None else []
    sidebar = Sidebar(root, items=ITEMS, current_role=role, user_name="mark aglugub",
                      on_navigate=lambda key: calls.append(("nav", key)),
                      on_user_click=lambda: calls.append(("user", None)),
                      on_toggle_assistant=lambda: calls.append(("toggle", None)),
                      assistant_open=True)
    sidebar.grid(row=0, column=0, sticky="nsw")
    root.update_idletasks()
    return sidebar, calls


def test_builds_and_destroys(root):
    sidebar, _ = build(root)
    assert set(sidebar.rows) == {"home", "billing", "payroll"}
    sidebar.destroy()
    root.update_idletasks()


def test_role_filter_matches_the_old_rule(root):
    sidebar, _ = build(root, role="AR")
    assert set(sidebar.rows) == {"home", "billing"}
    assert [i.page_key for i in visible_items(ITEMS, "HR")] == ["home", "payroll"]


def test_set_active_switches_styling(root):
    sidebar, _ = build(root)
    sidebar.set_active("billing")
    assert sidebar.rows["billing"].cget("fg_color") == Theme.accent_tint
    assert sidebar.rows["billing"].label.cget("text_color") == Theme.accent_text
    assert sidebar.rows["home"].cget("fg_color") == Theme.sidebar_bg
    sidebar.set_active(None)
    assert all(row.cget("fg_color") == Theme.sidebar_bg for row in sidebar.rows.values())


def test_keyboard_and_click_activate(root):
    sidebar, calls = build(root)
    row = sidebar.rows["payroll"]
    row._activate()                       # what Return/Space/click call
    sidebar.assistant_toggle._activate()
    sidebar.user_card._activate()
    assert calls == [("nav", "payroll"), ("toggle", None), ("user", None)]
    assert int(tk.Frame.cget(row, "takefocus")) == 1
    row._on_focus_in()
    assert row.cget("border_color") == Theme.focus_border
    row._on_focus_out()
    assert row.cget("border_color") != Theme.focus_border


def test_assistant_dot(root):
    sidebar, _ = build(root)
    assert sidebar.assistant_toggle.dot.cget("fg_color") == Theme.accent
    sidebar.set_assistant_open(False)
    assert sidebar.assistant_toggle.dot.cget("fg_color") == Theme.neutral


def test_user_card_shows_plain_role_and_accepts_legacy_text(root):
    sidebar, _ = build(root)
    card = sidebar.user_card
    assert card.role_label.cget("text") == "Master"
    card.configure(text="newname\n[Role: Admin]")   # how views_user_profile.py updates it
    assert (card.name_label.cget("text"), card.role_label.cget("text")) == ("newname", "Admin")


def test_initials():
    assert initials_for("mark aglugub") == "MA"
    assert initials_for("markaglugub") == "M"
    assert initials_for("") == "?"


def test_sidebar_has_no_hardcoded_colors_or_sql():
    source = (ROOT / "modules" / "sidebar.py").read_text(encoding="utf-8")
    assert re.findall(r"#[0-9A-Fa-f]{3,8}\b", source) == []
    assert "sqlite3" not in source and "SELECT" not in source


def test_preview_tool_builds_and_destroys(root):
    spec = importlib.util.spec_from_file_location("preview_sidebar", ROOT / "tools" / "preview_sidebar.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    window, sidebar = module.build_preview(role="Accountant", active="billing", root=root)
    window.update_idletasks()
    assert set(sidebar.rows) == {"home", "billing", "payroll"}
    assert sidebar.active_key == "billing"


def test_scrolls_only_when_items_overflow(root):
    many = ITEMS + tuple(NavItem("MORE", f"Item {n}", f"more.{n}", None, "") for n in range(30))
    sidebar = Sidebar(root, items=many, current_role="Master", user_name="u", on_navigate=lambda k: None,
                      on_user_click=lambda: None, on_toggle_assistant=lambda: None, assistant_open=False)
    sidebar.grid(row=0, column=0, sticky="nsw")
    root.geometry("300x400")
    root.update()
    assert sidebar.overflows()
    assert sidebar.nav.cget("scrollbar_button_color") == Theme.glass_border
