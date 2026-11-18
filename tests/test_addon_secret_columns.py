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

# Owner answers 2026-11-18 (B2 review L2): names the check missed. Account numbers and hashes stay refused (RP1: bank
# numbers are never stored), and session_id stays refused although it ends in _id: it is the secret, not a reference.
REFUSED_OWNER_ANSWERS = [
    "mypwd", "MyPwd", "userpwd", "pwd_value", "mypw", "mypass", "mypin", "acctnum", "AcctNum", "acct_num",
    "acctNum", "account_num", "accountnum", "acc_no", "accno", "acc_num", "accnum", "card_num", "cardnum",
    "routing_num", "routingnum", "client_key", "clientKey", "clientkey", "consumer_key", "app_key", "appkey",
    "auth_key", "authkey", "nonce", "nonces", "auth_nonce", "authnonce", "Nonce2", "file_hash", "account_number",
    "payee_account_number", "account_number_hash", "session_id", "session_ids", "SessionId", "sessionid",
    # step-review 1: an id or count of a value that is itself the secret (a TIN, an account number, a hash) is the
    # value under another name ("TIN ID" is the Philippine name for the TIN), so the exemption does not cover it.
    "tin_id", "customer_tin_id", "ssn_id", "iban_id", "pin_id", "otp_id", "totp_id", "cvv_id", "cvc_id", "hash_id",
    "password_hash_id", "routing_number_id", "account_number_id", "account_number_ids", "acct_no_id", "card_num_id",
    "acctnum_id", "cardno_id", "hash_counts"]

# B2 review L3: a name ending in _id or _count is a reference or a tally, not the secret itself.
ALLOWED_ID_AND_COUNT = ["bank_account_id", "bankAccountId", "pass_count", "token_count", "api_key_id", "nonce_id",
                        "password_reset_count", "secret_id2", "bank_account_count", "routing_code_id"]

ALLOWED = ["secretary_name", "setting", "destination", "account_name", "routing_code", "pinned", "tint",
           "bank_name", "keyword", "tokenizer_note", "label", "secretaries", "hashtag", "passenger_count",
           "status_code", "key_date", "session_count", "description", "address", "compass", "spinner", "tints",
           "line2", "x9",
           # step-review 2: the new runs must not catch these.
           "non_certified", "noncertified", "client_keyword", "client_keywords", "auth_keyword", "markup_wdays",
           "stop_wd", "session_idle_minutes"]


@pytest.mark.parametrize("column", REFUSED + REFUSED_PROJECT_SECRETS + REFUSED_SPELLINGS + REFUSED_OWNER_ANSWERS)
def test_a_secret_looking_column_is_refused_with_the_secrets_sentence(company, tmp_path, column):
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, {column} TEXT);\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=r"secrets go only in DATA_DIR\\Secrets") as raised:
        database.apply_addon_migrations(company, KEY, folder)
    assert repr(column) in str(raised.value)
    assert "Nothing was changed." in str(raised.value)
    assert objects(company) == before


@pytest.mark.parametrize("column", ALLOWED + ALLOWED_ID_AND_COUNT)
def test_ordinary_names_that_contain_those_letters_are_allowed(company, tmp_path, column):
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_a (a_id INTEGER PRIMARY KEY, {column} TEXT);\n"})
    database.apply_addon_migrations(company, KEY, folder)
    assert any(r[1] == "demo_a" for r in objects(company))


def test_id_and_count_alone_are_ordinary_names():
    assert not database._looks_secret("id") and not database._looks_secret("count")


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
    (f"INSERT INTO demo_missing VALUES ('{LITERAL}');", r"statement 2 of demo_001.sql failed \(OperationalError\)"),
])
def test_the_installed_build_names_the_file_and_statement_but_never_the_sql_or_sqlites_message(
        company, tmp_path, monkeypatch, statement, match):
    """Secrets audit LOW-2, owner 2026-11-18: in the installed (frozen) build the refusal, which the add-on service
    logs, gives only the error type: SQL text and SQLite's message can both carry a literal from the migration."""
    monkeypatch.setattr(database.config, "FROZEN", True)
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_first (x);\n{statement}\n"})
    before = objects(company)
    with pytest.raises(database.AddonMigrationError, match=match) as raised:
        database.apply_addon_migrations(company, KEY, folder)
    assert LITERAL not in str(raised.value) and "hunter2" not in str(raised.value)
    assert raised.value.__cause__ is None or LITERAL not in str(raised.value.__cause__)
    assert objects(company) == before


@pytest.mark.parametrize("statement, message", [
    ("INSERT INTO demo_first VALUES (1) 'lit';", 'near "\'lit\'": syntax error'),
    ("INSERT INTO demo_missing VALUES (1);", "no such table: demo_missing"),
])
def test_a_source_run_gives_sqlites_full_message_for_the_addons_author(company, tmp_path, monkeypatch, statement,
                                                                         message):
    monkeypatch.setattr(database.config, "FROZEN", False)
    folder = migrations(tmp_path, {"demo_001.sql": f"CREATE TABLE demo_first (x);\n{statement}\n"})
    with pytest.raises(database.AddonMigrationError) as raised:
        database.apply_addon_migrations(company, KEY, folder)
    assert f"statement 2 of demo_001.sql failed ({message})" in str(raised.value)


def test_the_runners_own_failure_is_redacted_the_same_way(company, tmp_path, monkeypatch):
    """A failure outside the add-on's statements (here: recording the version) follows the same rule."""
    folder = migrations(tmp_path, {"demo_001.sql": "CREATE TABLE demo_first (x);\n"})
    real_execute = database.sqlite3.Connection.execute

    def failing(conn, sql, *args):
        if sql.startswith("INSERT INTO addon_schema_version"):
            raise database.sqlite3.OperationalError("detail that could quote 'lit'")
        return real_execute(conn, sql, *args)
    for frozen, shown in ((True, "(OperationalError)"), (False, "(detail that could quote 'lit')")):
        monkeypatch.setattr(database.config, "FROZEN", frozen)
        monkeypatch.setattr(database, "get_connection", _wrapping(database.get_connection, failing))
        with pytest.raises(database.AddonMigrationError) as raised:
            database.apply_addon_migrations(company, KEY, folder)
        assert shown in str(raised.value)
        monkeypatch.undo()


def _wrapping(get_connection, execute):
    class Wrapped:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args):
            return execute(self._conn, sql, *args)

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def __setattr__(self, name, value):
            if name == "_conn":
                object.__setattr__(self, name, value)
            else:
                setattr(self._conn, name, value)

    return lambda *args, **kwargs: Wrapped(get_connection(*args, **kwargs))
