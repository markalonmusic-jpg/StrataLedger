"""Secrets audit fixes for add-ons (Phase 2.7 STOP B, HA7).

* MEDIUM-1: add-on SQL, in a handler or a migration, reads the sensitive columns as NULL: full bank numbers, tax
  ids, exemption certificates, audit log values and audit_context. They are shown only through the services, which
  check view.bank_details and view.tax_ids.
* LOW-2: a failing handler's own exception text never reaches the log; its type and traceback frames do.
* LOW-4: a migration file that is a link leading outside the add-on's migrations folder is refused.
* LOW-5: add-ons load only when the data folder and the add-ons folder are apart (or the same root when running
  from source).
"""
import logging
import os
from pathlib import Path

import pytest

import config
import modules.database as database
from modules.services import addons
from modules.services.errors import AddonError
from tests import ledger_helpers as lh
from tests.test_addon_database import applied, migrations, objects  # noqa: F401  (helpers)
from tests.test_addons import admin, draft, write_addon  # noqa: F401  (helpers)
from tests.test_addons import ctx_for, env, keyed, resources, setup, world  # noqa: F401  (fixtures)
from modules.services import ledger

SECRETS = {"routing": "021000021", "account": "123456789012", "tax": "12-3456789", "cert": "EX-998877",
           "company_tax": "98-7654321"}


@pytest.fixture
def company_with_secrets(fresh_company):
    conn = database.get_connection(fresh_company)
    try:
        conn.execute("INSERT INTO company_settings (id, company_name, fiscal_year_start, tax_id) "
                     "VALUES (1, 'Co', '01-01', ?)", (SECRETS["company_tax"],))
        account_id = lh.make_account(conn, "1010")
        conn.execute("INSERT INTO bank_account (account_id, routing_number, account_number) VALUES (?, ?, ?)",
                     (account_id, SECRETS["routing"], SECRETS["account"]))
        conn.execute("INSERT INTO contact (name, tax_id, tax_exempt_status, exemption_cert_no) "
                     "VALUES ('C', ?, 'Exempt', ?)", (SECRETS["tax"], SECRETS["cert"]))
        conn.execute("UPDATE contact SET name = 'C'")                  # an audit row with an old value
        conn.execute("UPDATE audit_context SET user_id = 7, terminal_id = 'pc' WHERE id = 1")
        conn.commit()
    finally:
        conn.close()
    return fresh_company


READS = [
    ("SELECT routing_number FROM bank_account", None),
    ("SELECT account_number FROM bank_account", None),
    ("SELECT tax_id FROM contact", None),
    ("SELECT exemption_cert_no FROM contact", None),
    ("SELECT tax_id FROM company_settings", None),
    ("SELECT user_id FROM audit_context", None),
    ("SELECT terminal_id FROM audit_context", None),
    ("SELECT MAX(old_value) FROM audit_log", None),
    ("SELECT new_value FROM audit_log LIMIT 1", None),
    ("SELECT MAX(table_name) FROM audit_log", None),                   # every column of the audit tables
]


@pytest.mark.parametrize("sql, expected", READS)
def test_a_handler_reads_sensitive_columns_as_null(company_with_secrets, sql, expected):
    conn = database.get_connection(company_with_secrets)
    try:
        assert conn.execute(sql).fetchone()[0] is not None           # core sees the value
        with database.addon_write_guard(conn, "demo"):
            assert conn.execute(sql).fetchone()[0] is expected
    finally:
        conn.close()


def test_a_handler_still_reads_ordinary_columns(company_with_secrets):
    conn = database.get_connection(company_with_secrets)
    try:
        with database.addon_write_guard(conn, "demo"):
            assert conn.execute("SELECT name FROM contact").fetchone()[0] == "C"
            row = conn.execute("SELECT * FROM bank_account").fetchone()
            assert row["account_id"] and row["account_number"] is None and row["routing_number"] is None
    finally:
        conn.close()


def test_a_migration_cannot_copy_sensitive_columns(company_with_secrets, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": (
        "CREATE TABLE demo_copy AS SELECT b.routing_number AS routing_number, b.account_number AS account_number, "
        "c.tax_id AS tax_id, c.exemption_cert_no AS exemption_cert_no FROM bank_account AS b, contact AS c;\n"
        "CREATE TABLE demo_log AS SELECT old_value, new_value FROM audit_log;\n")})
    database.apply_addon_migrations(company_with_secrets, "demo", folder)
    conn = database.get_connection(company_with_secrets)
    try:
        values = [tuple(r) for r in conn.execute("SELECT * FROM demo_copy")]
        values += [tuple(r) for r in conn.execute("SELECT * FROM demo_log")]
    finally:
        conn.close()
    assert values and all(v is None for row in values for v in row)


def test_a_view_over_sensitive_columns_shows_null_to_a_handler(company_with_secrets, tmp_path):
    """A view's reads are checked on the columns underneath, so the view gives nothing away."""
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE VIEW demo_peek AS SELECT tax_id, name FROM contact;\n"})
    database.apply_addon_migrations(company_with_secrets, "demo", folder)
    conn = database.get_connection(company_with_secrets)
    try:
        with database.addon_write_guard(conn, "demo"):
            assert tuple(conn.execute("SELECT tax_id, name FROM demo_peek").fetchone()) == (None, "C")
    finally:
        conn.close()


# --- LOW-2: the handler's own text stays out of the log -------------------------------------------------------

def test_a_failing_handlers_message_is_not_logged(setup, resources, caplog):
    write_addon(resources, "leaky", name="Leaky", code='''
        def register(hooks):
            hooks.on("entry.posted", handler)

        def handler(db, payload):
            raise ValueError("bad account 123456789012")
        ''', files={})
    addons.enable(admin(setup), "leaky")
    entry_id = draft(setup)
    with caplog.at_level(logging.DEBUG, logger="strataledger"):
        with pytest.raises(AddonError):
            ledger.post_journal_entry(ctx_for(setup), entry_id, confirm=True)
    assert "123456789012" not in caplog.text
    assert "ValueError" in caplog.text and "leaky" in caplog.text


@pytest.mark.parametrize("where", ["register", "import"])
def test_a_failing_addon_start_is_not_logged_verbatim(setup, resources, caplog, where):
    code = ('def register(hooks):\n    raise ValueError("tax 12-3456789")\n' if where == "register"
            else 'raise ValueError("tax 12-3456789")\n')
    write_addon(resources, "starty", code=code, files={})
    with caplog.at_level(logging.DEBUG, logger="strataledger"):
        with pytest.raises(AddonError):
            addons.enable(admin(setup), "starty")
    assert "12-3456789" not in caplog.text and "ValueError" in caplog.text


# --- LOW-4: migration files are inside their folder ---------------------------------------------------------------

def test_a_migration_file_linked_from_elsewhere_is_refused(company_with_secrets, tmp_path):
    outside = tmp_path / "elsewhere.sql"
    outside.write_text("CREATE TABLE demo_x (y);\n", encoding="utf-8")
    folder = migrations(tmp_path, {})
    try:
        os.symlink(outside, folder / "demo_001.sql")
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symbolic links")
    before = objects(company_with_secrets)
    with pytest.raises(database.AddonMigrationError, match="outside"):
        database.apply_addon_migrations(company_with_secrets, "demo", folder)
    assert objects(company_with_secrets) == before


# --- LOW-5: the data folder and the add-ons folder are apart ---------------------------------------------------

def test_a_data_folder_inside_the_addons_folder_is_refused(setup, monkeypatch, caplog):
    monkeypatch.setattr(config, "DATA_DIR", str(Path(config.RESOURCE_DIR) / "addons" / "data"))
    with caplog.at_level(logging.ERROR, logger="strataledger"):
        assert addons.discover() == {}
    assert "data folder" in caplog.text


def test_the_same_root_is_allowed_when_running_from_source(setup, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", config.RESOURCE_DIR)
    assert "demo" in addons.discover()
