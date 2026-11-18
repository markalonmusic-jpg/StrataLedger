"""HA11: add-on tables never hold secrets (owner 2026-11-18; B2 secrets audit M2).

HA9 copies every add-on column into the append-only audit log, so a secret written to an add-on table could never
be removed. The add-on migration runner refuses a column whose name looks like a secret (password, secret, token,
API or private key, account or routing number, IBAN, TIN and similar), with one sentence: secrets go only in
DATA_DIR\\Secrets. The check runs wherever the audit triggers are made, so CREATE TABLE, CREATE TABLE AS,
ALTER TABLE ADD COLUMN and RENAME COLUMN are all covered. Nothing is changed when it refuses.
"""
import pytest

import modules.database as database
from tests.test_addon_database import KEY, company, migrations, objects  # noqa: F401  (fixture and helpers)

REFUSED = ["password", "user_password", "passwd", "pwd", "passphrase", "secret", "client_secret", "secret_key",
           "token", "access_token", "refresh_tokens", "api_key", "apikey", "apiKey", "private_key", "PrivateKey",
           "access_key", "account_number", "accountNumber", "account_no", "acct_no", "acct_number",
           "routing_number", "routing_no", "bank_account", "card_number", "iban", "payee_iban", "tin", "vendor_tin",
           "ssn", "cvv", "pin", "credentials"]

ALLOWED = ["secretary_name", "setting", "destination", "account_name", "routing_code", "pinned", "tint",
           "bank_name", "keyword", "tokenizer_note", "label"]


@pytest.mark.parametrize("column", REFUSED)
def test_a_secret_looking_column_is_refused_with_the_secrets_sentence(company, tmp_path, column):
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, {column} TEXT);\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=r"secrets go only in DATA_DIR\\Secrets") as raised:
        database.apply_addon_migrations(company, KEY, folder)
    assert repr(column) in str(raised.value)
    assert "Nothing was changed." in str(raised.value)
    assert objects(company) == before


@pytest.mark.parametrize("column", ALLOWED)
def test_ordinary_names_that_contain_those_letters_are_allowed(company, tmp_path, column):
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, {column} TEXT);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    assert any(r[1] == "demo_a" for r in objects(company))


@pytest.mark.parametrize("script", [
    "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY);\nALTER TABLE demo_a ADD COLUMN api_token TEXT;",
    "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, note TEXT);\nALTER TABLE demo_a RENAME COLUMN note TO password;",
    "CREATE TABLE demo_src (v TEXT);\nCREATE TABLE demo_copy AS SELECT v AS iban FROM demo_src;",
])
def test_every_way_of_making_a_column_is_checked(company, tmp_path, script):
    folder = migrations(tmp_path, {"demo_001.sql": script + "\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=r"looks like a secret"):
        database.apply_addon_migrations(company, KEY, folder)
    assert objects(company) == before


def test_a_later_migration_adding_a_secret_column_is_refused_and_the_earlier_one_stays(company, tmp_path):
    first = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, label TEXT);\n"})
    database.apply_addon_migrations(company, KEY, first)
    after_first = objects(company)
    (first / "demo_002.sql").write_text("ALTER TABLE demo_a ADD COLUMN client_secret TEXT;\n", encoding="utf-8")
    with pytest.raises(database.AddonMigrationError, match=r"looks like a secret"):
        database.apply_addon_migrations(company, KEY, first)
    assert objects(company) == after_first
