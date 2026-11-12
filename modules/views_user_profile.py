import sqlite3
from tkinter import messagebox

import customtkinter as ctk

from config import Theme
from modules.services import auth
from modules.services.errors import ServiceError


def render_user_profile_view(parent_view, workspace_frame):
	"""Render the active user's profile and save edits to the master database."""
	for widget in workspace_frame.winfo_children():
		widget.destroy()

	ctk.CTkLabel(
		workspace_frame,
		text="USER ACCOUNT SECURITY PROFILE",
		font=Theme.title_font,
		text_color=Theme.text_primary,
	).pack(pady=(0, 5), anchor="w")
	ctk.CTkLabel(
		workspace_frame,
		text="Modify your global user registry parameters recorded inside the system master hub.",
		font=Theme.small_font,
		text_color=Theme.text_secondary,
	).pack(pady=(0, 20), anchor="w")

	edit_card = ctk.CTkFrame(
		workspace_frame,
		fg_color=Theme.glass_panel,
		border_color=Theme.glass_border,
		border_width=1,
		corner_radius=8,
	)
	edit_card.pack(fill="both", expand=True)
	edit_card.grid_columnconfigure((0, 1), weight=1)
	edit_card.grid_rowconfigure(0, weight=1)
	edit_card.grid_rowconfigure(1, weight=0, minsize=70)

	col_l = ctk.CTkFrame(edit_card, fg_color="transparent")
	col_l.grid(row=0, column=0, padx=25, pady=25, sticky="nsew")

	col_r = ctk.CTkFrame(edit_card, fg_color="transparent")
	col_r.grid(row=0, column=1, padx=25, pady=25, sticky="nsew")

	try:
		with sqlite3.connect(parent_view.master_db_path) as conn:
			conn.row_factory = sqlite3.Row
			user_data = conn.execute(
				"SELECT first_name, last_name, email, role FROM app_user WHERE username = ?",
				(parent_view.current_user,),
			).fetchone()
	except sqlite3.Error as exc:
		messagebox.showerror("Profile Error", f"Unable to read profile information: {exc}")
		return

	role_name = user_data["role"] if user_data and user_data["role"] else parent_view.current_role
	ctk.CTkLabel(col_l, text="Role:", font=Theme.body_font, anchor="w").pack(fill="x", pady=(5, 2))
	role_entry = ctk.CTkEntry(col_l, height=36, fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
	role_entry.pack(fill="x", pady=(0, 15))
	role_entry.insert(0, role_name)
	role_entry.configure(state="disabled")

	ctk.CTkLabel(col_l, text="First Name:", font=Theme.body_font, anchor="w").pack(fill="x", pady=(5, 2))
	ent_fname = ctk.CTkEntry(col_l, height=36, fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
	ent_fname.pack(fill="x", pady=(0, 15))
	if user_data and user_data["first_name"]:
		ent_fname.insert(0, user_data["first_name"])

	ctk.CTkLabel(col_l, text="Last Name:", font=Theme.body_font, anchor="w").pack(fill="x", pady=(5, 2))
	ent_lname = ctk.CTkEntry(col_l, height=36, fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
	ent_lname.pack(fill="x", pady=(0, 15))
	if user_data and user_data["last_name"]:
		ent_lname.insert(0, user_data["last_name"])

	ctk.CTkLabel(col_r, text="Email Address:", font=Theme.body_font, anchor="w").pack(fill="x", pady=(5, 2))
	ent_email = ctk.CTkEntry(col_r, height=36, fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
	ent_email.pack(fill="x", pady=(0, 15))
	if user_data and user_data["email"]:
		ent_email.insert(0, user_data["email"])

	ctk.CTkLabel(col_r, text="Current Password (needed to change it):", font=Theme.body_font, anchor="w").pack(fill="x", pady=(5, 2))
	ent_current = ctk.CTkEntry(col_r, height=36, show="*", fg_color=Theme.input_bg, border_color=Theme.glass_border, font=Theme.body_font)
	ent_current.pack(fill="x", pady=(0, 15))

	ctk.CTkLabel(
		col_r,
		text="New Password (leave blank to keep current):",
		font=Theme.body_font,
		anchor="w",
	).pack(fill="x", pady=(5, 2))
	ent_pass = ctk.CTkEntry(
		col_r,
		height=36,
		show="*",
		fg_color=Theme.input_bg,
		border_color=Theme.glass_border,
		placeholder_text="Leave blank to keep current",
		font=Theme.body_font,
	)
	ent_pass.pack(fill="x", pady=(0, 15))

	actions_bar = ctk.CTkFrame(edit_card, fg_color="transparent")
	actions_bar.grid(row=1, column=0, columnspan=2, padx=25, pady=(10, 25), sticky="ew")

	def save_profile_changes():
		first_name = ent_fname.get().strip()
		last_name = ent_lname.get().strip()
		email = ent_email.get().strip()
		new_password = ent_pass.get()

		if new_password:
			session = getattr(parent_view, "session", None)
			if session is None:
				messagebox.showerror("Password Change", "Log in again to change your password.")
				return
			try:
				auth.change_password(session, ent_current.get(), new_password)
			except ServiceError as exc:
				messagebox.showerror("Password Change", str(exc))
				return

		try:
			# Name and email are still saved here directly until Phase 3 rewrites this screen.
			with sqlite3.connect(parent_view.master_db_path) as conn:
				cursor = conn.cursor()
				cursor.execute(
					"UPDATE app_user SET first_name=?, last_name=?, email=? WHERE username=?",
					(first_name, last_name, email, parent_view.current_user),
				)
				if cursor.rowcount != 1:
					raise sqlite3.IntegrityError("The current user profile could not be found.")

			parent_view.user_first_name = first_name or parent_view.current_user
			parent_view.profile_card.configure(
				text=f"{parent_view.current_user}\n[Role: {parent_view.current_role}]"
			)
			messagebox.showinfo("Success", "Master account profile updated successfully.")
			parent_view.show_home_view()
		except sqlite3.Error as exc:
			messagebox.showerror("Profile Update Failed", f"Unable to save profile changes: {exc}")

	ctk.CTkButton(
		actions_bar,
		text="Save",
		font=Theme.semi_title_font,
		fg_color=Theme.btn_primary,
		hover_color=Theme.btn_primary_hover,
		text_color=Theme.btn_primary_text,
		height=42,
		width=250,
		command=save_profile_changes,
	).pack(side="left")
	ctk.CTkButton(
		actions_bar,
		text="Logout",
		font=Theme.semi_title_font,
		fg_color=Theme.btn_danger_bg,
		hover_color=Theme.btn_danger_hover,
		border_color=Theme.btn_danger_border,
		border_width=1,
		text_color=Theme.btn_danger_text,
		height=42,
		width=220,
		command=parent_view.handle_secure_logout,
	).pack(side="right")
