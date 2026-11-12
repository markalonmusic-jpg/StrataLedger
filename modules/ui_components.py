# DRAFT, not imported yet; wired up in Phase 3.
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

from config import Theme


# ==============================================================================
# 1. DARK-SLATE MODAL DIALOG SYSTEM (Replaces native tkinter.messagebox)
# ==============================================================================

_MODAL_STYLES = {
    "info": {
        "tag": "INFO",
        "accent": Theme.accent_text,
        "badge_bg": Theme.accent_tint,
        "border": Theme.glass_border,
    },
    "success": {
        "tag": "SUCCESS",
        "accent": Theme.success_glow,
        "badge_bg": "#102A22",
        "border": Theme.glass_border,
    },
    "warning": {
        "tag": "WARNING",
        "accent": Theme.warning_glow,
        "badge_bg": "#2B2111",
        "border": Theme.warning_glow,
    },
    "error": {
        "tag": "ERROR",
        "accent": Theme.error_glow,
        "badge_bg": Theme.btn_danger_bg,
        "border": Theme.btn_danger_border,
    },
    "confirm": {
        "tag": "CONFIRM",
        "accent": Theme.accent_text,
        "badge_bg": Theme.accent_tint,
        "border": Theme.glass_border,
    },
}


class StrataModal(ctk.CTkToplevel):
    """Centered dark-slate modal dialog matching config.Theme."""

    def __init__(
        self,
        parent,
        title: str,
        message: str,
        kind: str = "info",
        confirm_text: str = "OK",
        cancel_text: str | None = None,
        destructive: bool = False,
        details: str | None = None,
    ):
        super().__init__(parent)
        self.result = False
        self._details_visible = False

        style = _MODAL_STYLES.get(kind, _MODAL_STYLES["info"])
        root_win = parent.winfo_toplevel() if parent is not None else self

        self.title(title)
        self.configure(fg_color=Theme.bg_color)
        self.resizable(False, False)
        self.transient(root_win)

        # Outer card frame with semantic border
        card = ctk.CTkFrame(
            self,
            fg_color=Theme.glass_panel,
            border_color=style["border"],
            border_width=1,
            corner_radius=Theme.radius_lg,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        # Top row: semantic badge + title
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(20, 10))

        badge = ctk.CTkLabel(
            header,
            text=style["tag"],
            font=Theme.caption_font,
            text_color=style["accent"],
            fg_color=style["badge_bg"],
            corner_radius=Theme.radius_sm,
            padx=8,
            pady=3,
        )
        badge.pack(side="left")

        ctk.CTkLabel(
            header,
            text=title,
            font=Theme.semi_title_font,
            text_color=Theme.text_primary,
            anchor="w",
        ).pack(side="left", padx=(10, 0), fill="x", expand=True)

        # Body message
        ctk.CTkLabel(
            card,
            text=message,
            font=Theme.body_font,
            text_color=Theme.text_secondary,
            justify="left",
            anchor="w",
            wraplength=420,
        ).pack(fill="x", padx=22, pady=(2, 16))

        # Optional collapsible technical details (for error dialogs)
        if details:
            self._details_frame = ctk.CTkFrame(card, fg_color="transparent")
            self._details_box = ctk.CTkTextbox(
                self._details_frame,
                height=110,
                width=420,
                fg_color=Theme.input_bg,
                border_color=Theme.glass_border,
                border_width=1,
                font=Theme.small_font,
                text_color=Theme.text_secondary,
                wrap="word",
            )
            self._details_box.insert("1.0", str(details))
            self._details_box.configure(state="disabled")
            self._details_box.pack(fill="x")

        # Divider above action bar
        ctk.CTkFrame(card, height=1, fg_color=Theme.glass_border).pack(fill="x", padx=22)

        # Bottom action buttons
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(14, 18))

        if details:
            self._toggle_btn = ctk.CTkButton(
                actions,
                text="Show Details",
                width=105,
                height=34,
                font=Theme.small_font,
                fg_color="transparent",
                hover_color=Theme.btn_secondary_hover,
                text_color=Theme.text_muted,
                command=self._toggle_details,
            )
            self._toggle_btn.pack(side="left")

        if destructive:
            primary_kw = {
                "fg_color": Theme.btn_danger_bg,
                "hover_color": Theme.btn_danger_hover,
                "border_color": Theme.btn_danger_border,
                "border_width": 1,
                "text_color": Theme.btn_danger_text,
            }
        else:
            primary_kw = {
                "fg_color": Theme.btn_primary,
                "hover_color": Theme.btn_primary_hover,
                "text_color": Theme.btn_primary_text,
            }

        self._confirm_btn = ctk.CTkButton(
            actions,
            text=confirm_text,
            width=110,
            height=36,
            font=Theme.section_font,
            command=self._on_confirm,
            **primary_kw,
        )
        self._confirm_btn.pack(side="right")

        if cancel_text:
            ctk.CTkButton(
                actions,
                text=cancel_text,
                width=100,
                height=36,
                font=Theme.body_font,
                fg_color=Theme.btn_secondary,
                hover_color=Theme.btn_secondary_hover,
                border_color=Theme.btn_secondary_border,
                border_width=1,
                text_color=Theme.btn_secondary_text,
                command=self._on_cancel,
            ).pack(side="right", padx=(0, 10))

        self.bind("<Return>", lambda _e: self._on_confirm())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._center_over_parent(root_win)
        self.grab_set()
        self.focus_force()

    def _toggle_details(self):
        if self._details_visible:
            self._details_frame.pack_forget()
            self._toggle_btn.configure(text="Show Details")
            self._details_visible = False
        else:
            self._details_frame.pack(fill="x", padx=22, pady=(0, 12))
            self._toggle_btn.configure(text="Hide Details")
            self._details_visible = True
        self.update_idletasks()

    def _center_over_parent(self, root_win):
        self.update_idletasks()
        req_w = max(self.winfo_reqwidth(), 470)
        req_h = self.winfo_reqheight()
        try:
            px = root_win.winfo_rootx()
            py = root_win.winfo_rooty()
            pw = root_win.winfo_width()
            ph = root_win.winfo_height()
            x = px + max((pw - req_w) // 2, 0)
            y = py + max((ph - req_h) // 2, 0)
        except Exception:
            x = (self.winfo_screenwidth() - req_w) // 2
            y = (self.winfo_screenheight() - req_h) // 2
        self.geometry(f"{req_w}x{req_h}+{x}+{y}")

    def _on_confirm(self):
        self.result = True
        self.destroy()

    def _on_cancel(self):
        self.result = False
        self.destroy()
def show_info(parent, title: str, message: str) -> None:
    modal = StrataModal(parent, title=title, message=message, kind="info", confirm_text="OK")
    modal.wait_window()


def show_success(parent, title: str, message: str) -> None:
    modal = StrataModal(parent, title=title, message=message, kind="success", confirm_text="Done")
    modal.wait_window()


def show_warning(parent, title: str, message: str) -> None:
    modal = StrataModal(parent, title=title, message=message, kind="warning", confirm_text="Understood")
    modal.wait_window()


def show_error(parent, title: str, message: str, details: str | None = None) -> None:
    modal = StrataModal(
        parent,
        title=title,
        message=message,
        kind="error",
        confirm_text="Close",
        details=details,
    )
    modal.wait_window()


def ask_confirm(
    parent,
    title: str,
    message: str,
    confirm_text: str = "Confirm",
    cancel_text: str = "Cancel",
    destructive: bool = False,
) -> bool:
    modal = StrataModal(
        parent,
        title=title,
        message=message,
        kind="warning" if destructive else "confirm",
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        destructive=destructive,
    )
    modal.wait_window()
    return bool(modal.result)

# ==============================================================================
# 2. SHARED SCREEN COMPONENTS (docs/CLAUDE_UI.md Section 10)
# ==============================================================================

class Banner(ctk.CTkFrame):
    """Semantic status banner for DRAFT, POSTED (LOCKED), VOID, IMPORTED, SUGGESTED."""

    _VARIANTS = {
        "draft": ("DRAFT", Theme.text_secondary, Theme.btn_secondary, Theme.glass_border),
        "posted": ("POSTED · LOCKED", Theme.success_glow, "#102A22", Theme.success_glow),
        "void": ("VOID", Theme.error_glow, Theme.btn_danger_bg, Theme.btn_danger_border),
        "imported": ("IMPORTED · NEEDS REVIEW", Theme.warning_glow, "#2B2111", Theme.warning_glow),
        "suggested": ("AI SUGGESTED · REVIEW REQUIRED", Theme.accent_text, Theme.accent_tint, Theme.accent),
    }

    def __init__(self, parent, variant: str = "draft", text: str = ""):
        tag, fg, bg, border = self._VARIANTS.get(variant.lower(), self._VARIANTS["draft"])
        super().__init__(
            parent,
            fg_color=bg,
            border_color=border,
            border_width=1,
            corner_radius=Theme.radius,
        )
        ctk.CTkLabel(
            self,
            text=tag,
            font=Theme.caption_font,
            text_color=fg,
        ).pack(side="left", padx=(14, 10), pady=8)

        if text:
            ctk.CTkLabel(
                self,
                text=text,
                font=Theme.small_font,
                text_color=Theme.text_primary,
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=(0, 14), pady=8)


class PageHeader(ctk.CTkFrame):
    """Standard top page header with title, subtitle, and right-aligned action slot."""

    def __init__(self, parent, title: str, subtitle: str = ""):
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            left,
            text=title,
            font=Theme.title_font,
            text_color=Theme.text_primary,
            anchor="w",
        ).pack(anchor="w")

        if subtitle:
            ctk.CTkLabel(
                left,
                text=subtitle,
                font=Theme.body_font,
                text_color=Theme.text_secondary,
                anchor="w",
            ).pack(anchor="w", pady=(3, 0))

        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.grid(row=0, column=1, sticky="e")


class StepSection(ctk.CTkFrame):
    """Numbered step card for multi-step intake and setup forms."""

    def __init__(self, parent, step_number: int, title: str):
        super().__init__(
            parent,
            fg_color=Theme.glass_panel,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=Theme.radius_lg,
        )
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(
            heading,
            text=str(step_number),
            width=30,
            height=30,
            corner_radius=15,
            fg_color=Theme.btn_primary,
            text_color=Theme.btn_primary_text,
            font=Theme.section_font,
        ).pack(side="left")

        ctk.CTkLabel(
            heading,
            text=title.upper(),
            font=Theme.section_font,
            text_color=Theme.text_primary,
            anchor="w",
        ).pack(side="left", padx=12)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x", padx=24, pady=(16, 22))


class KpiCard(ctk.CTkFrame):
    """Clickable KPI summary card with uppercase label, formatted value, and context line."""

    def __init__(self, parent, label: str, value: str, context: str = "", on_click=None):
        super().__init__(
            parent,
            fg_color=Theme.glass_panel,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=Theme.radius,
            cursor="hand2" if on_click else "",
        )
        lbl_top = ctk.CTkLabel(
            self,
            text=label.upper(),
            font=Theme.caption_font,
            text_color=Theme.text_secondary,
            anchor="w",
        )
        lbl_top.pack(fill="x", padx=16, pady=(14, 4))

        lbl_val = ctk.CTkLabel(
            self,
            text=value,
            font=Theme.title_font,
            text_color=Theme.text_primary,
            anchor="w",
        )
        lbl_val.pack(fill="x", padx=16)

        lbl_ctx = None
        if context:
            lbl_ctx = ctk.CTkLabel(
                self,
                text=context,
                font=Theme.small_font,
                text_color=Theme.text_muted,
                anchor="w",
            )
            lbl_ctx.pack(fill="x", padx=16, pady=(4, 14))
        else:
            lbl_val.pack_configure(pady=(0, 14))

        if on_click:
            for widget in (self, lbl_top, lbl_val, lbl_ctx):
                if widget is not None:
                    widget.bind("<Button-1>", lambda _e: on_click())


class EmptyState(ctk.CTkFrame):
    """Standard empty state panel with guidance text and a primary CTA button."""

    def __init__(self, parent, title: str, message: str, cta_text: str | None = None, on_cta=None):
        super().__init__(
            parent,
            fg_color=Theme.glass_panel,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=Theme.radius_lg,
        )
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(expand=True, pady=48, padx=24)

        ctk.CTkLabel(
            inner,
            text=title,
            font=Theme.semi_title_font,
            text_color=Theme.text_primary,
        ).pack()

        ctk.CTkLabel(
            inner,
            text=message,
            font=Theme.body_font,
            text_color=Theme.text_secondary,
            wraplength=420,
        ).pack(pady=(6, 18))

        if cta_text and on_cta:
            ctk.CTkButton(
                inner,
                text=cta_text,
                height=38,
                font=Theme.section_font,
                fg_color=Theme.btn_primary,
                hover_color=Theme.btn_primary_hover,
                text_color=Theme.btn_primary_text,
                command=on_cta,
            ).pack()


class SummaryBar(ctk.CTkFrame):
    """Sticky bottom bar holding totals/status on the left and Cancel/Primary buttons on the right."""

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(self, height=1, fg_color=Theme.glass_border).grid(row=0, column=0, sticky="ew")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="ew")
        content.grid_columnconfigure(0, weight=1)

        self.left = ctk.CTkFrame(content, fg_color="transparent")
        self.left.grid(row=0, column=0, sticky="w", padx=20, pady=12)

        self.right = ctk.CTkFrame(content, fg_color="transparent")
        self.right.grid(row=0, column=1, sticky="e", padx=20, pady=10)

class DataTable(ctk.CTkFrame):
    """Styled dark-slate Treeview wrapper with slim Theme scrollbar and row selection helpers."""

    def __init__(self, parent, columns: list[tuple[str, str, int, str]], on_double_click=None):
        """
        columns: list of (col_key, heading_text, width, anchor)
                 Pass width=0 to hide an internal ID column.
        """
        super().__init__(
            parent,
            fg_color=Theme.glass_panel,
            border_color=Theme.glass_border,
            border_width=1,
            corner_radius=Theme.radius,
        )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Strata.Treeview",
            background=Theme.glass_panel,
            foreground=Theme.text_primary,
            fieldbackground=Theme.glass_panel,
            rowheight=36,
            borderwidth=0,
            font=(Theme.font_family, 12),
        )
        style.configure(
            "Strata.Treeview.Heading",
            background=Theme.sidebar_bg,
            foreground=Theme.text_secondary,
            borderwidth=0,
            font=(Theme.font_family, 11, "bold"),
        )
        style.map(
            "Strata.Treeview",
            background=[("selected", Theme.accent_tint)],
            foreground=[("selected", Theme.accent_text)],
        )

        col_keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(
            self,
            columns=col_keys,
            show="headings",
            style="Strata.Treeview",
            selectmode="browse",
        )

        for key, heading, width, anchor in columns:
            self.tree.heading(key, text=heading.upper(), anchor=anchor)
            if width == 0:
                self.tree.column(key, width=0, minwidth=0, stretch=False)
            else:
                self.tree.column(key, width=width, anchor=anchor)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)

        scrollbar = Theme.create_scrollbar(self, orientation="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 8), pady=10)

        if on_double_click:
            self.tree.bind("<Double-Button-1>", lambda _e: self._handle_dbl_click(on_double_click))

    def _handle_dbl_click(self, callback):
        values = self.get_selected_values()
        if values:
            callback(values)

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insert_row(self, values: tuple):
        self.tree.insert("", "end", values=values)

    def get_selected_values(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel, "values")
