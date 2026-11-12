"""Static checks for the Customers dashboard ("Customers Flight Deck") view."""
import importlib
import re
from pathlib import Path

from modules import views_dashboard as view

VIEW = Path(__file__).resolve().parent.parent / "modules" / "views_dashboard.py"


def test_view_declares_its_page_key():
    # The same key the sidebar and App.navigate_to use for this screen (tests/test_page_keys.py checks the match).
    assert view.PAGE_KEY == "customers.dashboard"


def test_module_imports_without_a_database():
    assert importlib.import_module("modules.views_dashboard") is view


def test_view_has_no_sql_dialogs_prints_or_colors():
    text = "\n".join(l for l in VIEW.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("#"))
    assert "sqlite3" not in text and "execute(" not in text
    assert "messagebox" not in text
    assert not re.search(r"(?<![\w.])print\(", text)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), "hardcoded color"
