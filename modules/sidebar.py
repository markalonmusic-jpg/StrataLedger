"""Left navigation sidebar (docs/CLAUDE_UI.md sections 2-4).

The sidebar only draws navigation. It holds no SQL and no routing: it calls
on_navigate(page_key) when an item is chosen, and the app decides what to show.
The app calls set_active(page_key) from the same functions that navigate, so
the highlight follows navigation started anywhere (including other screens).

Every color, font, size and spacing value comes from config.Theme.
"""
import tkinter as tk
import tkinter.font as tkfont
from collections import namedtuple

import customtkinter as ctk

from config import Theme

NavItem = namedtuple("NavItem", "group label page_key roles glyph")
NavItem.__doc__ = """One navigation entry. roles=None means every role sees it."""


def initials_for(name):
    """'mark aglugub' -> 'MA', 'markaglugub' -> 'M', '' -> '?'."""
    words = [w for w in str(name or "").replace(".", " ").replace("_", " ").split() if w]
    if not words:
        return "?"
    return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper()


def visible_items(items, current_role):
    """Items the role may see (the same rule the old sidebar applied inline)."""
    return [item for item in items if item.roles is None or current_role in item.roles]


def _glyph_font_available(widget):
    try:
        return Theme.glyph_font_family in tkfont.families(widget)
    except tk.TclError:
        return False


class _Activatable:
    """Mouse, hover and keyboard behavior shared by nav rows, the user card and
    the assistant toggle: Tab focuses it (with a visible ring), Enter or Space
    activates it, a click anywhere on it activates it."""

    def _wire(self, command, rest_color):
        self._command = command
        self._rest_color = rest_color
        self._hovered = False
        self._focused = False
        # CTkFrame is a tkinter.Frame; key and focus events go to that widget.
        tk.Frame.configure(self, takefocus=True)
        for sequence in ("<Return>", "<KP_Enter>", "<space>"):
            tk.Misc.bind(self, sequence, self._activate, add="+")
        tk.Misc.bind(self, "<FocusIn>", self._on_focus_in, add="+")
        tk.Misc.bind(self, "<FocusOut>", self._on_focus_out, add="+")
        self._bind_mouse(self)

    def _bind_mouse(self, widget):
        widget.bind("<Button-1>", self._activate, add="+")
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")

    def _activate(self, _event=None):
        if self._command:
            self._command()
        return "break"

    def _on_enter(self, _event=None):
        self._hovered = True
        self._restyle()

    def _on_leave(self, _event=None):
        # Moving from the frame onto one of its labels also fires <Leave>.
        self.after(15, self._check_pointer)

    def _check_pointer(self):
        if not self.winfo_exists():
            return
        x, y = self.winfo_pointerxy()
        inside = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                  and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        if inside != self._hovered:
            self._hovered = inside
            self._restyle()

    def _on_focus_in(self, _event=None):
        self._focused = True
        self._restyle()

    def _on_focus_out(self, _event=None):
        self._focused = False
        self._restyle()

    def _ring_color(self):
        return Theme.focus_border if self._focused else self._rest_color

    def _restyle(self):
        raise NotImplementedError


class NavRow(ctk.CTkFrame, _Activatable):
    """A flat, full-width navigation row: active bar, glyph, label."""

    def __init__(self, master, item, on_select, show_glyph):
        super().__init__(
            master,
            height=Theme.nav_row_height,
            corner_radius=Theme.radius_sm,
            fg_color=Theme.sidebar_bg,
            border_width=Theme.focus_ring_width,
            border_color=Theme.sidebar_bg,
        )
        self.item = item
        self.active = False
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)

        self.bar = ctk.CTkFrame(self, width=Theme.active_bar_width, corner_radius=Theme.pad_xs,
                                fg_color=Theme.sidebar_bg)
        self.bar.grid(row=0, column=0, sticky="ns", padx=(Theme.focus_ring_width, 0), pady=Theme.pad_sm)
        self.glyph = None
        if show_glyph and item.glyph:
            self.glyph = ctk.CTkLabel(self, text=item.glyph, font=Theme.glyph_font,
                                      width=Theme.pad_lg, text_color=Theme.text_secondary)
            self.glyph.grid(row=0, column=1, padx=(Theme.pad_sm, 0))
        self.label = ctk.CTkLabel(self, text=item.label, font=Theme.nav_font, anchor="w",
                                  text_color=Theme.text_secondary)
        self.label.grid(row=0, column=2, sticky="ew", padx=(Theme.pad_sm, Theme.pad_sm))

        self._wire(lambda: on_select(item.page_key), Theme.sidebar_bg)
        for child in (self.bar, self.glyph, self.label):
            if child is not None:
                self._bind_mouse(child)

    def set_active(self, active):
        self.active = active
        self._restyle()

    def _restyle(self):
        if self.active:
            fill, text, bar, font = Theme.accent_tint, Theme.accent_text, Theme.accent, Theme.nav_label_font
        elif self._hovered:
            fill, text, bar, font = Theme.nav_hover, Theme.text_primary, Theme.nav_hover, Theme.nav_font
        else:
            fill, text, bar, font = Theme.sidebar_bg, Theme.text_secondary, Theme.sidebar_bg, Theme.nav_font
        self._rest_color = fill
        self.configure(fg_color=fill, border_color=self._ring_color())
        self.bar.configure(fg_color=bar)
        self.label.configure(text_color=text, font=font)
        if self.glyph is not None:
            self.glyph.configure(text_color=text)


class UserCard(ctk.CTkFrame, _Activatable):
    """Initials circle, username, role. Opens the user profile."""

    def __init__(self, master, user_name, role, on_click):
        super().__init__(master, corner_radius=Theme.radius, fg_color=Theme.card_bg,
                         border_width=Theme.focus_ring_width, border_color=Theme.glass_border)
        self.grid_columnconfigure(1, weight=1)
        self.avatar = ctk.CTkLabel(
            self, text=initials_for(user_name), width=Theme.avatar_size, height=Theme.avatar_size,
            corner_radius=Theme.avatar_size // 2, fg_color=Theme.accent, text_color=Theme.text_primary,
            font=Theme.nav_label_font,
        )
        self.avatar.grid(row=0, column=0, padx=Theme.pad_md, pady=Theme.pad_md)
        text_block = ctk.CTkFrame(self, fg_color="transparent")
        text_block.grid(row=0, column=1, sticky="ew", padx=(0, Theme.pad_md))
        self.name_label = ctk.CTkLabel(text_block, text=str(user_name or ""), font=Theme.nav_label_font,
                                       text_color=Theme.text_primary, anchor="w", height=Theme.pad_lg)
        self.name_label.pack(fill="x")
        self.role_label = ctk.CTkLabel(text_block, text=str(role or ""), font=Theme.caption_font,
                                       text_color=Theme.text_secondary, anchor="w", height=Theme.pad_lg - Theme.pad_xs)
        self.role_label.pack(fill="x")
        self._wire(on_click, Theme.glass_border)
        for child in (self.avatar, text_block, self.name_label, self.role_label):
            self._bind_mouse(child)

    def set_user(self, user_name, role):
        self.avatar.configure(text=initials_for(user_name))
        self.name_label.configure(text=str(user_name or ""))
        self.role_label.configure(text=str(role or ""))

    def configure(self, require_redraw=False, **kwargs):
        # Compatibility: views_user_profile.py still updates the old button-style
        # card with configure(text="name\n[Role: X]"). Show it in the new layout.
        text = kwargs.pop("text", None)
        if text is not None:
            lines = str(text).split("\n")
            role = lines[1].strip() if len(lines) > 1 else self.role_label.cget("text")
            if role.startswith("[Role:") and role.endswith("]"):
                role = role[len("[Role:"):-1].strip()
            self.set_user(lines[0], role)
        if kwargs:
            super().configure(require_redraw=require_redraw, **kwargs)

    def _restyle(self):
        self.configure(fg_color=Theme.nav_hover if self._hovered else Theme.card_bg,
                       border_color=self._ring_color())


class AssistantToggle(ctk.CTkFrame, _Activatable):
    """'Toggle AI assistant' with a status dot (accent = open, neutral = closed)."""

    def __init__(self, master, on_toggle, is_open):
        super().__init__(master, height=Theme.nav_row_height + Theme.pad_sm, corner_radius=Theme.radius,
                         fg_color=Theme.card_bg, border_width=Theme.focus_ring_width,
                         border_color=Theme.glass_border)
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.label = ctk.CTkLabel(self, text="Toggle AI assistant", font=Theme.nav_font,
                                  text_color=Theme.text_primary, anchor="w")
        self.label.grid(row=0, column=0, sticky="ew", padx=Theme.pad_md)
        self.dot = ctk.CTkFrame(self, width=Theme.status_dot_size, height=Theme.status_dot_size,
                                corner_radius=Theme.status_dot_size // 2, fg_color=Theme.neutral)
        self.dot.grid(row=0, column=1, padx=Theme.pad_md)
        self._wire(on_toggle, Theme.glass_border)
        for child in (self.label, self.dot):
            self._bind_mouse(child)
        self.set_open(is_open)

    def set_open(self, is_open):
        self.is_open = bool(is_open)
        self.dot.configure(fg_color=Theme.accent if self.is_open else Theme.neutral)

    def _restyle(self):
        self.configure(fg_color=Theme.nav_hover if self._hovered else Theme.card_bg,
                       border_color=self._ring_color())


class Sidebar(ctk.CTkFrame):
    """Fixed-width, full-height sidebar: header, user card, scrolling nav, pinned toggle."""

    def __init__(self, master, *, items, current_role, user_name, on_navigate,
                 on_user_click, on_toggle_assistant, assistant_open):
        super().__init__(master, width=Theme.sidebar_width, corner_radius=0, fg_color=Theme.sidebar_bg,
                         border_width=1, border_color=Theme.glass_border)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._on_navigate = on_navigate
        self.rows = {}
        self.active_key = None

        # 1. Header: accent mark, "StrataLedger" + "Core".
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=Theme.pad_lg, pady=(Theme.pad_lg, Theme.pad_md))
        ctk.CTkFrame(header, width=Theme.brand_mark_size, height=Theme.brand_mark_size,
                     corner_radius=Theme.radius_sm, fg_color=Theme.accent).pack(side="left")
        ctk.CTkLabel(header, text="StrataLedger", font=Theme.brand_font,
                     text_color=Theme.text_primary).pack(side="left", padx=(Theme.pad_sm + Theme.pad_xs, 0))
        ctk.CTkLabel(header, text=" Core", font=Theme.brand_font,
                     text_color=Theme.accent_text).pack(side="left")

        # 2. User card.
        self.user_card = UserCard(self, user_name, current_role, on_user_click)
        self.user_card.grid(row=1, column=0, sticky="ew", padx=Theme.pad_md, pady=(0, Theme.pad_md))

        # 3. Navigation, scrolling when it overflows.
        self.nav = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0,
                                          scrollbar_button_color=Theme.glass_border,
                                          scrollbar_button_hover_color=Theme.btn_secondary_border)
        self.nav.grid(row=2, column=0, sticky="nsew", padx=(Theme.pad_sm, Theme.pad_xs))
        self.nav.grid_columnconfigure(0, weight=1)
        show_glyph = _glyph_font_available(self)
        allowed = {item.page_key for item in visible_items(items, current_role)}
        row_index = 0
        groups = []
        for item in items:  # group labels show even when every item is hidden (as before)
            if item.group not in groups:
                groups.append(item.group)
        for group in groups:
            ctk.CTkLabel(self.nav, text=group.upper(), font=Theme.group_label_font,
                         text_color=Theme.text_secondary, anchor="w").grid(
                row=row_index, column=0, sticky="ew", padx=Theme.pad_sm,
                pady=(Theme.pad_md if row_index else Theme.pad_xs, Theme.pad_xs))
            row_index += 1
            for item in items:
                if item.group != group or item.page_key not in allowed:
                    continue
                row = NavRow(self.nav, item, self._select, show_glyph)
                row.grid(row=row_index, column=0, sticky="ew", pady=Theme.pad_xs // 2)
                self.rows[item.page_key] = row
                row_index += 1

        # The scrollbar shows only when the items overflow.
        self._nav_viewport().bind("<Configure>", self._update_scrollbar, add="+")
        self.after_idle(self._update_scrollbar)

        # 4. Pinned assistant toggle under a divider.
        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=Theme.glass_border).grid(
            row=3, column=0, sticky="ew", padx=Theme.focus_ring_width)
        self.assistant_toggle = AssistantToggle(self, on_toggle_assistant, assistant_open)
        self.assistant_toggle.grid(row=4, column=0, sticky="ew", padx=Theme.pad_md, pady=Theme.pad_md)

    def _select(self, page_key):
        self._on_navigate(page_key)

    def _nav_viewport(self):
        # CTkScrollableFrame draws its content on a canvas; that canvas is the
        # visible area (the inner frame itself grows with the content).
        return getattr(self.nav, "_parent_canvas", self.nav)

    def overflows(self):
        """True when the nav items are taller than the space shown for them."""
        self.update_idletasks()
        return self.nav.winfo_reqheight() > self._nav_viewport().winfo_height()

    def _update_scrollbar(self, _event=None):
        if not self.winfo_exists():
            return
        if self.overflows():
            self.nav.configure(scrollbar_button_color=Theme.glass_border,
                               scrollbar_button_hover_color=Theme.btn_secondary_border)
        else:
            self.nav.configure(scrollbar_button_color=Theme.sidebar_bg,
                               scrollbar_button_hover_color=Theme.sidebar_bg)

    def set_active(self, page_key):
        """Highlight page_key (None or an unknown key clears the highlight)."""
        self.active_key = page_key if page_key in self.rows else None
        for key, row in self.rows.items():
            row.set_active(key == self.active_key)

    def set_assistant_open(self, is_open):
        self.assistant_toggle.set_open(is_open)
