"""A small installation for permission tests: one master database and three
company files built from the fresh baseline (PARENT, its subsidiary CHILD, and
an unrelated OTHER). Tests write setup rows directly; the code under test only
reads them."""
import shutil
import sqlite3

import pytest

import config
import modules.database as database
from modules.services import passwords
from modules.services.auth import Session
from modules.services.context import ServiceContext

PASSWORD = "correct horse battery"  # 21 characters
_HASHES = {}


def _hash(password):
    """scrypt is deliberately slow; test users share one precomputed hash per password."""
    key = (password, passwords.N, passwords.R, passwords.P)  # a patched cost gets its own hash
    if key not in _HASHES:
        _HASHES[key] = passwords.hash_password(password)
    return _HASHES[key]


class World:
    def __init__(self, tmp_path, template):
        self.master = tmp_path / "master.db"
        database.ensure_master_database(self.master)
        self.companies = {}
        for code, parent in (("PARENT", None), ("CHILD", "PARENT"), ("OTHER", None)):
            path = tmp_path / f"{code}.db"
            shutil.copy2(template, path)
            parent_id = self.companies[parent][0] if parent else None
            with self._master() as c:
                company_id = c.execute(
                    "INSERT INTO company_registry (company_code, legal_name, database_file_path, parent_company_id) "
                    "VALUES (?, ?, ?, ?) RETURNING company_id", (code, code, str(path), parent_id)).fetchone()[0]
            self.companies[code] = (company_id, path)
        self._project_seq = 0

    # --- connections ------------------------------------------------------------
    def _master(self):
        return _Conn(self.master)

    def _company(self, company):
        return _Conn(self.companies[company][1])

    def path(self, company):
        return self.companies[company][1]

    def company_id(self, company):
        return self.companies[company][0]

    # --- master side ------------------------------------------------------------
    def user(self, username, *, master=False, active=True, password=PASSWORD, email=None):
        with self._master() as c:
            return c.execute(
                "INSERT INTO app_user (username, password_hash, first_name, last_name, email, role, is_active, is_master) "
                "VALUES (?, ?, 'F', 'L', ?, ?, ?, ?) RETURNING user_id",
                (username, _hash(password), email or f"{username}@x.test",
                 "Master" if master else None, int(active), int(master)),
            ).fetchone()[0]

    def session(self, user_id):
        """A Session as login() would return it (services re-read the user every call)."""
        with self._master() as c:
            row = c.execute("SELECT * FROM app_user WHERE user_id = ?", (user_id,)).fetchone()
        return Session(user_id=row["user_id"], username=row["username"], first_name=row["first_name"],
                       is_master=bool(row["is_master"]), legacy_role=row["role"],
                       must_change_password=bool(row["must_change_password"]), master_db_path=str(self.master))

    def master_rows(self, sql, params=()):
        with self._master() as c:
            return [dict(r) for r in c.execute(sql, params)]

    def grant(self, user_id, company, role_code, mode="Grant"):
        with self._master() as c:
            c.execute(
                "INSERT INTO user_company_access (user_id, company_id, role_code, access_mode) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (user_id, company_id) DO UPDATE SET role_code = excluded.role_code, "
                "access_mode = excluded.access_mode",
                (user_id, self.company_id(company), role_code, mode))

    def revoke(self, user_id, company):
        with self._master() as c:
            c.execute("DELETE FROM user_company_access WHERE user_id = ? AND company_id = ?",
                      (user_id, self.company_id(company)))

    def set_user_active(self, user_id, active):
        with self._master() as c:
            c.execute("UPDATE app_user SET is_active = ? WHERE user_id = ?", (int(active), user_id))

    def set_company_active(self, company, active):
        with self._master() as c:
            c.execute("UPDATE company_registry SET is_active = ? WHERE company_id = ?",
                      (int(active), self.company_id(company)))

    # --- company side -------------------------------------------------------------
    def role(self, company, code, permissions=(), *, scope="All", active=True):
        with self._company(company) as c:
            c.execute(
                "INSERT INTO role (role_code, name, is_system, is_active, project_scope, created_at) "
                "VALUES (?, ?, 0, ?, ?, '2026-01-01T00:00:00+00:00')", (code, code, int(active), scope))
            for permission in permissions:
                c.execute("INSERT INTO role_permission VALUES (?, ?)", (code, permission))

    def grant_permission(self, company, role_code, permission):
        with self._company(company) as c:
            c.execute("INSERT INTO role_permission VALUES (?, ?)", (role_code, permission))

    def remove_permission(self, company, role_code, permission):
        with self._company(company) as c:
            c.execute("DELETE FROM role_permission WHERE role_code = ? AND permission_code = ?", (role_code, permission))

    def set_role_active(self, company, role_code, active):
        with self._company(company) as c:
            c.execute("UPDATE role SET is_active = ? WHERE role_code = ?", (int(active), role_code))

    def limit(self, company, role_code, document_type, cents):
        with self._company(company) as c:
            c.execute("INSERT INTO approval_limit VALUES (?, ?, ?)", (role_code, document_type, cents))

    def project(self, company):
        self._project_seq += 1
        with self._company(company) as c:
            contact = c.execute("INSERT INTO contact (name) VALUES ('C') RETURNING contact_id").fetchone()[0]
            return c.execute(
                "INSERT INTO project (project_number, name, contact_id, assigned_pm_id) VALUES (?, 'Job', ?, 1) "
                "RETURNING project_id", (f"P-{self._project_seq}", contact)).fetchone()[0]

    def assign(self, company, user_id, project_id):
        with self._company(company) as c:
            c.execute("INSERT INTO user_project_scope VALUES (?, ?)", (user_id, project_id))

    def settings(self, company, *, require_separate_approver=1):
        with self._company(company) as c:
            c.execute(
                "INSERT INTO company_settings (id, company_name, fiscal_year_start, require_separate_approver) "
                "VALUES (1, ?, '01-01', ?) ON CONFLICT (id) DO UPDATE SET "
                "require_separate_approver = excluded.require_separate_approver",
                (company, require_separate_approver))

    def events(self, company):
        with self._company(company) as c:
            return [dict(r) for r in c.execute("SELECT * FROM access_event ORDER BY event_id")]

    def rows(self, company, sql, params=()):
        with self._company(company) as c:
            return [dict(r) for r in c.execute(sql, params)]

    # --- contexts ----------------------------------------------------------------
    def ctx(self, user_id, company, origin="Human"):
        return ServiceContext(
            user_id=user_id, company_id=self.company_id(company), origin=origin,
            company_db_path=str(self.path(company)), master_db_path=str(self.master),
        )


class _Conn:
    """Short-lived committed connection for test setup."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        self.conn.close()


@pytest.fixture
def world(tmp_path, backup_dir, _company_template, monkeypatch):
    # Company files live under the installation folder; point it at tmp_path.
    monkeypatch.setattr(config, "BASE_PROJECT_DIR", str(tmp_path))
    return World(tmp_path, _company_template)
