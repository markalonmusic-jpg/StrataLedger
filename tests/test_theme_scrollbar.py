"""Theme.create_scrollbar (Phase 2.7 step B2; the known issue "DataTable needs Theme.create_scrollbar").

The slim scrollbar takes every value from the Theme tokens. Only this helper is added to CustomTkinter: no Tk view
manager, modal class or event bus (AX5-AX8 are rules for the AQ2 front end).
"""
import customtkinter as ctk

from config import Theme
from modules.ui_components import DataTable


def test_the_scrollbar_uses_the_theme_tokens(tk_app):
    frame = ctk.CTkFrame(tk_app)
    try:
        calls = []
        bar = Theme.create_scrollbar(frame, orientation="vertical", command=lambda *a: calls.append(a))
        assert isinstance(bar, ctk.CTkScrollbar)
        assert bar.cget("width") == Theme.scrollbar_width
        assert bar.cget("corner_radius") == Theme.scrollbar_radius
        assert bar.cget("fg_color") == Theme.scrollbar_track
        assert bar.cget("button_color") == Theme.scrollbar_thumb
        assert bar.cget("button_hover_color") == Theme.scrollbar_thumb_hover
        assert bar.cget("orientation") == "vertical"
    finally:
        frame.destroy()


def test_a_data_table_can_be_built(tk_app):
    table = DataTable(tk_app, columns=[("name", "Name", 120, "w")])
    try:
        table.update_idletasks()
    finally:
        table.destroy()
