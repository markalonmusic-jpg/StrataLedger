r"""Paths and constants (decision P2a).

RESOURCE_DIR is the folder the app runs from: sys._MEIPASS when frozen, else the folder of this
file. Code, migrations, fonts, templates and help are read from there and never written.

DATA_DIR holds everything the app writes: the databases, Companies, Backups, Logs and uploads.
It is STRATALEDGER_DATA_DIR if that is set; otherwise the repo folder when running from source;
otherwise %PROGRAMDATA%\StrataLedger when frozen (created if missing).

BASE_PROJECT_DIR is kept as an alias of DATA_DIR. Services read it at call time, so tests can
patch it.
"""
import os
import sys

APP_VERSION = "0.2.0-dev"
DATA_DIR_ENV = "STRATALEDGER_DATA_DIR"


def resolve_resource_dir(frozen, meipass, executable):
    """The folder the app runs from."""
    if frozen:
        return os.path.abspath(meipass) if meipass else os.path.dirname(os.path.abspath(executable))
    return os.path.dirname(os.path.abspath(__file__))


def resolve_data_dir(environ, frozen, resource_dir):
    """Where the app keeps its data (see the module docstring). Creates the frozen default."""
    override = (environ.get(DATA_DIR_ENV) or "").strip()
    if override:
        return os.path.abspath(override)
    if not frozen:
        return os.path.abspath(resource_dir)
    base = environ.get("PROGRAMDATA") or environ.get("USERPROFILE") or environ.get("HOME") or resource_dir
    path = os.path.join(base, "StrataLedger")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass          # the first write reports the real problem, with its path
    return path


def build_paths(data_dir, resource_dir):
    """Every derived path: written data under data_dir, read-only resources under resource_dir."""
    log_dir = os.path.join(data_dir, "Logs")
    return {
        "MASTER_DB_PATH": os.path.join(data_dir, "system_master.db"),
        "COMPANIES_DIR": os.path.join(data_dir, "Companies"),
        "UPLOAD_DIR": os.path.join(data_dir, "Uploaded_Files"),
        "BACKUP_DIR": os.path.join(data_dir, "Backups"),
        "LOG_DIR": log_dir,
        "LOG_FILE": os.path.join(log_dir, "strataledger.log"),
        "MIGRATIONS_DIR": os.path.join(resource_dir, "migrations"),
        "FONT_DIR": os.path.join(resource_dir, "fonts"),
        "TEMPLATES_DIR": os.path.join(resource_dir, "templates"),
        "HELP_DIR": os.path.join(resource_dir, "help"),
    }


_FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_DIR = resolve_resource_dir(_FROZEN, getattr(sys, "_MEIPASS", None), sys.executable)
DATA_DIR = resolve_data_dir(os.environ, _FROZEN, RESOURCE_DIR)
BASE_PROJECT_DIR = DATA_DIR      # alias, kept so existing code and tests need no change

_paths = build_paths(DATA_DIR, RESOURCE_DIR)
MASTER_DB_PATH = _paths["MASTER_DB_PATH"]
COMPANIES_DIR = _paths["COMPANIES_DIR"]
UPLOAD_DIR = _paths["UPLOAD_DIR"]
BACKUP_DIR = _paths["BACKUP_DIR"]
LOG_DIR = _paths["LOG_DIR"]
LOG_FILE = _paths["LOG_FILE"]
MIGRATIONS_DIR = _paths["MIGRATIONS_DIR"]
FONT_DIR = _paths["FONT_DIR"]
TEMPLATES_DIR = _paths["TEMPLATES_DIR"]
HELP_DIR = _paths["HELP_DIR"]


class Theme:
    bg_color = "#090D16"
    sidebar_bg = "#0E1320"
    glass_panel = "#131824"
    glass_border = "#242C3E"
    input_bg = "#0F131C"
    accent_glow = "#2563EB"
    success_glow = "#34D399"
    error_glow = "#F87171"

    btn_primary = "#2563EB"
    btn_primary_hover = "#1D4ED8"
    btn_primary_text = "#F8FAFC"

    btn_secondary = "#1E293B"
    btn_secondary_hover = "#293548"
    btn_secondary_border = "#334155"
    btn_secondary_text = "#E2E8F0"

    btn_danger_bg = "#2A1519"
    btn_danger_hover = "#3B1D23"
    btn_danger_border = "#7F1D1D"
    btn_danger_text = "#FCA5A5"

    text_primary = "#F8FAFC"
    text_secondary = "#94A3B8"
    text_muted = "#64748B"
    focus_border = "#3B82F6"
    composer_bg = "#141A26"
    composer_border = "#232B3A"

    # Standardized slim dark scrollbar tokens
    scrollbar_width = 8
    scrollbar_radius = 4
    scrollbar_track = "#090D16"
    scrollbar_thumb = "#2A3446"
    scrollbar_thumb_hover = "#3B82F6"

    # Sidebar and shared navigation tokens (docs/CLAUDE_UI.md sections 2-3).
    accent = "#2563EB"            # marks, active indicators, the open-assistant dot
    accent_text = "#60A5FA"       # accent-colored text; ~6:1 on accent_tint (accent itself is ~3:1)
    accent_tint = "#16233F"       # flat accent-over-panel fill for the active nav row
    nav_hover = "#161D2C"         # subtle hover fill for nav rows
    card_bg = "#141A27"           # raised card inside the sidebar (user card)
    neutral = "#6B7280"           # decoration only, never text (closed-assistant dot)
    sidebar_width = 240
    nav_row_height = 34
    brand_mark_size = 24
    avatar_size = 34
    status_dot_size = 8
    active_bar_width = 3
    radius_sm = 6
    radius = 8
    focus_ring_width = 2
    pad_xs = 2
    pad_sm = 6
    pad_md = 12
    pad_lg = 20
    glyph_font_family = "Segoe UI Symbol"
    _resolved_font_family = None

    @property
    def font_family(self):
        if self._resolved_font_family:
            return self._resolved_font_family

        import tkinter.font as tkfont
        import tkinter as tk

        try:
            available_families = set(tkfont.families())
        except (RuntimeError, tk.TclError):
            return "Segoe UI"

        self._resolved_font_family = "Inter" if "Inter" in available_families else "Segoe UI"
        return self._resolved_font_family

    # Dynamic dynamic object layout routing getters to bypass Tkinter root window race blocks
    @property
    def title_font(self): 
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=24, weight="bold")
    @property
    def semi_title_font(self): 
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=16, weight="normal")
    @property
    def section_font(self): 
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=13, weight="bold")
    @property
    def body_font(self): 
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=13, weight="normal")
    @property
    def small_font(self): 
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=12, weight="normal")
    @property
    def brand_font(self):
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=16, weight="bold")
    @property
    def nav_font(self):
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=13, weight="normal")
    @property
    def nav_label_font(self):
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=13, weight="bold")
    @property
    def group_label_font(self):
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=11, weight="normal")
    @property
    def caption_font(self):
        import customtkinter as ctk
        return ctk.CTkFont(family=self.font_family, size=11, weight="normal")
    @property
    def glyph_font(self):
        import customtkinter as ctk
        return ctk.CTkFont(family=self.glyph_font_family, size=13, weight="normal")

# Turn the class track into a unified configuration reference block instance
Theme = Theme()
