import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import modules.database as database
from config import Theme
from modules.services import auth, users
from modules.services.errors import ServiceError

NO_COMPANY = "(no company access yet)"


def _company_choices(master_db_path):
	"""Registry names for the optional company picker (a read; nothing is written here)."""
	conn = database.get_readonly_connection(master_db_path)
	try:
		return {
			f"{row['legal_name']} ({row['company_code']})": row["company_id"]
			for row in conn.execute(
				"SELECT company_id, company_code, legal_name FROM company_registry WHERE is_active = 1 ORDER BY legal_name"
			)
		}
	finally:
		conn.close()


def render_new_user_form(parent_view):
	"""Render the global user-registration form and save profiles to the master database."""
	for widget in parent_view.winfo_children():
		widget.destroy()

	reg_panel = ctk.CTkFrame(
		parent_view,
		width=620,
		height=590,
		fg_color=Theme.glass_panel,
		border_color=Theme.glass_border,
		border_width=1,
		corner_radius=12,
	)
	reg_panel.place(relx=0.5, rely=0.5, anchor="center")
	reg_panel.pack_propagate(False)

	ctk.CTkLabel(
		reg_panel,
		text="Create New User",
		font=Theme.title_font,
		text_color=Theme.text_primary,
	).pack(pady=(28, 5))
	ctk.CTkLabel(
		reg_panel,
		text="Create a global login profile for access to linked company workspaces.",
		font=Theme.small_font,
		text_color=Theme.text_secondary,
	).pack(pady=(0, 16))

	fields_frame = ctk.CTkFrame(reg_panel, fg_color="transparent")
	fields_frame.pack(fill="both", expand=True, padx=38, pady=(0, 8))
	fields_frame.grid_columnconfigure((0, 1), weight=1, uniform="user_fields")

	def create_user_entry(label, row, column, show=None):
		field_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
		field_frame.grid(row=row, column=column, sticky="ew", padx=7, pady=7)
		ctk.CTkLabel(field_frame, text=label, font=Theme.body_font, anchor="w").pack(
			fill="x", pady=(0, 3)
		)
		entry_options = {
			"height": 38,
			"fg_color": Theme.input_bg,
			"border_color": Theme.glass_border,
			"font": Theme.body_font,
		}
		if show:
			entry_options["show"] = show
		entry = ctk.CTkEntry(field_frame, **entry_options)
		entry.pack(fill="x")
		return entry

	username_entry = create_user_entry("Username:", 0, 0)
	password_entry = create_user_entry("Password:", 0, 1, show="*")
	first_name_entry = create_user_entry("First Name:", 1, 0)
	last_name_entry = create_user_entry("Last Name:", 1, 1)
	email_entry = create_user_entry("Email Address:", 2, 0)

	# Optional company and role for the new user (Phase 2.3: users.create_user).
	try:
		companies = _company_choices(parent_view.master_db_path)
	except Exception as exc:
		companies = {}
		messagebox.showerror("Companies", f"Unable to list companies: {exc}")
	company_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
	company_frame.grid(row=2, column=1, sticky="ew", padx=7, pady=7)
	ctk.CTkLabel(company_frame, text="Company (optional):", font=Theme.body_font, anchor="w").pack(fill="x", pady=(0, 3))
	company_var = tk.StringVar(value=NO_COMPANY)
	ctk.CTkOptionMenu(
		company_frame,
		height=38,
		values=[NO_COMPANY, *companies],
		variable=company_var,
		fg_color=Theme.input_bg,
		button_color=Theme.btn_secondary,
		font=Theme.body_font,
	).pack(fill="x")
	role_entry = create_user_entry("Role code in that company:", 3, 0)

	# Creating users needs a logged-in Master, or a user manager of that company.
	session = getattr(parent_view, "session", None)
	if session is None:
		actor_user_entry = create_user_entry("Your username (Master or Admin):", 4, 0)
		actor_password_entry = create_user_entry("Your password:", 4, 1, show="*")
	else:
		actor_user_entry = actor_password_entry = None

	def commit_new_user_profile():
		user = username_entry.get().strip()
		password = password_entry.get()
		first_name = first_name_entry.get().strip()
		last_name = last_name_entry.get().strip()
		email = email_entry.get().strip()
		company_id = companies.get(company_var.get())
		role_code = role_entry.get().strip() or None

		if not all((user, password, first_name, last_name, email)):
			messagebox.showerror("Validation Error", "Complete all fields to create the user profile.")
			return
		try:
			actor = session
			if actor is None:
				actor = auth.login(parent_view.master_db_path, actor_user_entry.get().strip(), actor_password_entry.get())
			users.create_user(
				actor, user, password, first_name, last_name, email,
				company_id=company_id, role_code=role_code if company_id is not None else None,
			)
		except ServiceError as exc:
			messagebox.showerror("Create User", str(exc))
			return
		messagebox.showinfo("Success", f"User '{user}' has been created.")
		parent_view.show_no_company_open_screen()

	ctk.CTkButton(
		reg_panel,
		text="Create New User",
		height=42,
		fg_color=Theme.btn_primary,
		hover_color=Theme.btn_primary_hover,
		text_color=Theme.btn_primary_text,
		font=Theme.semi_title_font,
		command=commit_new_user_profile,
	).pack(fill="x", padx=45, pady=(8, 5))
	ctk.CTkButton(
		reg_panel,
		text="Cancel",
		height=35,
		fg_color=Theme.btn_secondary,
		hover_color=Theme.btn_secondary_hover,
		border_color=Theme.btn_secondary_border,
		border_width=1,
		font=Theme.body_font,
		text_color=Theme.btn_secondary_text,
		command=parent_view.show_no_company_open_screen,
	).pack(fill="x", padx=45, pady=(0, 18))
