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

# B2 secrets audit of b4ea844, HIGH-1: the project's own secret types (recovery and backup codes, chain, HMAC,
# installation and master keys, DPAPI blobs, salts and hashes, one-time codes) and short forms of "password".
REFUSED_PROJECT_SECRETS = [
    "recovery_code", "recoveryCode", "backup_code", "backup_codes", "reset_code", "chain_key", "chainkey", "hmac_key",
    "hmac", "installation_key", "install_key", "master_key", "encryption_key", "enc_key", "signing_key",
    "session_key", "dpapi_blob", "dpapi", "salt", "salt_value", "hash", "pwhash", "pw_hash", "otp", "totp", "mfa",
    "cred", "creds", "privkey", "priv_key", "pass", "pw", "pword", "passcode", "pass_code", "smtp_pass", "bearer",
    "jwt", "cookie", "session_id", "cvc", "card_no", "cardno", "passhash", "password_hashes"]

# HIGH-2: digits, capitals, run-together spellings, plurals and letters split by underscores.
REFUSED_SPELLINGS = [
    "token1", "secret2", "pwd1", "pin1", "TIN2", "mysecret", "MYSECRET", "mytoken", "apitoken", "APITOKEN",
    "accesstoken", "ACCESSTOKEN", "feedtoken", "tokenvalue", "TOKENvalue", "secretvalue", "SECRETKEY", "SECRETkey",
    "secret9key", "pins", "ibans", "tins", "ssns", "PINs", "p_w_d", "s_e_c_r_e_t", "mycredential", "userpassphrase",
    "feedtokens2", "recoverycodes"]

ALLOWED = ["secretary_name", "setting", "destination", "account_name", "routing_code", "pinned", "tint",
           "bank_name", "keyword", "tokenizer_note", "label", "secretaries", "hashtag", "passenger_count",
           "status_code", "key_date", "session_count", "description", "address", "compass", "spinner", "tints",
           "line2", "x9"]


@pytest.mark.parametrize("column", REFUSED + REFUSED_PROJECT_SECRETS + REFUSED_SPELLINGS)
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


def test_a_secret_column_already_in_the_file_is_refused_even_with_nothing_pending(company, tmp_path):
    """Secrets audit LOW-1: a table made before the check (or by hand) is checked again on every run, not only when a
    migration is pending; the refusal changes nothing in the file."""
    import sqlite3
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, label TEXT);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    raw = sqlite3.connect(company)
    raw.execute("ALTER TABLE demo_a ADD COLUMN feed_token TEXT")
    raw.commit()
    raw.close()
    before = company.read_bytes()
    with pytest.raises(database.AddonMigrationError, match=r"'feed_token', which looks like a secret"):
        database.apply_addon_migrations(company, KEY, folder)
    assert company.read_bytes() == before


def test_a_clean_file_with_nothing_pending_still_applies_nothing(company, tmp_path):
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, label TEXT);\n"})
    assert database.apply_addon_migrations(company, KEY, folder) == [1]
    before = company.read_bytes()
    assert database.apply_addon_migrations(company, KEY, folder) == []
    assert company.read_bytes() == before


LITERAL = "S3cr3tLiteral-hunter2"


@pytest.mark.parametrize("statement, match", [
    (f"UPDATE company_settings SET company_name = '{LITERAL}';",
     r"statement 2 of demo_001.sql reaches outside"),
    (f"INSERT INTO demo_first VALUES (1) '{LITERAL}';", r"statement 2 of demo_001.sql failed \(OperationalError\)"),
    # a message whose only variable part is a plain name is kept: it tells the add-on's author what to fix
    (f"INSERT INTO demo_missing VALUES ('{LITERAL}');",
     r"statement 2 of demo_001.sql failed \(no such table: demo_missing\)"),
])
def test_a_refusal_names_the_file_and_statement_but_never_the_sql_text(company, tmp_path, statement, match):
    """Secrets audit LOW-2: the refusal (which the add-on service logs) never echoes SQL text or SQLite's message,
    either of which can carry a literal from the migration."""
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_first (x);\n{statement}\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=match) as raised:
        database.apply_addon_migrations(company, KEY, folder)
    assert LITERAL not in str(raised.value) and "hunter2" not in str(raised.value)
    assert raised.value.__cause__ is None or LITERAL not in str(raised.value.__cause__)
    assert objects(company) == before
