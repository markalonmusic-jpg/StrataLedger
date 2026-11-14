"""R35: an unexpected database error during a service write is a plain sentence; its own text goes to the log only."""
import sqlite3

import pytest

from modules.services import auth, ledger, logging_setup
from modules.services.errors import SaveFailedError, ServiceError, ValidationError
from modules.services.tx import write_transaction
from tests.test_ledger_posting import ctx, ctx_for, draft, entry_row, env, keyed, world  # noqa: F401
from tests.test_refusal_messages import code_like

SENTENCE = "Something went wrong saving this; nothing was saved. The details are in the log."
MARKER = "boom-marker-R35"


@pytest.fixture
def log_file(tmp_path):
    path = tmp_path / "Logs" / "strataledger.log"
    logger = logging_setup.configure_logging(path)
    yield path
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", None) == str(path.resolve()):
            logger.removeHandler(handler)
            handler.close()


def _trigger(path, sql):
    conn = sqlite3.connect(path)
    try:
        conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def test_a_database_error_at_posting_is_the_plain_sentence(env, ctx, log_file):
    entry_id = draft(env, ctx)
    _trigger(env.path("PARENT"), "CREATE TRIGGER boom BEFORE UPDATE OF is_posted ON journal_entry "
                                 f"BEGIN SELECT RAISE(ABORT, '{MARKER}'); END")
    with pytest.raises(SaveFailedError) as error:
        ledger.post_journal_entry(ctx, entry_id, confirm=True)
    assert str(error.value) == SENTENCE == SaveFailedError.MESSAGE
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert code_like(str(error.value)) == []
    assert entry_row(env, entry_id)["is_posted"] == 0                       # nothing was saved
    assert MARKER in log_file.read_text(encoding="utf-8")                   # the details are in the log


def test_a_unique_failure_at_posting_does_not_show_the_database_text(env, ctx, log_file):
    entry_id = draft(env, ctx)
    _trigger(env.path("PARENT"), "CREATE TRIGGER same_code AFTER UPDATE OF is_posted ON journal_entry BEGIN "
                                 "INSERT INTO contact (name, is_customer, customer_code) VALUES ('Twin', 1, 'CL0001'); "
                                 "END")
    with pytest.raises(SaveFailedError) as error:
        ledger.post_journal_entry(ctx, entry_id, confirm=True)
    for word in ("UNIQUE", "constraint", "contact", "customer_code"):
        assert word not in str(error.value)
    assert "UNIQUE" in log_file.read_text(encoding="utf-8")
    assert entry_row(env, entry_id)["is_posted"] == 0


def test_any_service_write_is_covered(world, log_file):
    ann = world.user("ann")
    _trigger(world.master, f"CREATE TRIGGER boom BEFORE INSERT ON auth_event BEGIN SELECT RAISE(ABORT, '{MARKER}'); END")
    with pytest.raises(SaveFailedError) as error:
        auth.change_password(world.session(ann), "correct horse battery", "a brand new passphrase")
    assert str(error.value) == SENTENCE
    assert MARKER in log_file.read_text(encoding="utf-8")


def test_a_service_error_inside_the_block_is_not_wrapped(world):
    context = world.ctx(world.user("ann"), "PARENT")
    with pytest.raises(ValidationError, match="^kept$"):
        with write_transaction(context.company_db_path, context):
            raise ValidationError("kept")


def test_a_database_error_is_rolled_back_and_wrapped(world):
    context = world.ctx(world.user("ann"), "PARENT")
    with pytest.raises(SaveFailedError):
        with write_transaction(context.company_db_path, context) as conn:
            conn.execute("INSERT INTO contact (name, is_customer, customer_code) VALUES ('Kept?', 1, 'CK0001')")
            conn.execute("INSERT INTO no_such_table VALUES (1)")
    assert world.rows("PARENT", "SELECT * FROM contact WHERE name = 'Kept?'") == []
    assert issubclass(SaveFailedError, ServiceError)


def test_a_non_database_error_passes_through(world):
    context = world.ctx(world.user("ann"), "PARENT")
    with pytest.raises(KeyError):
        with write_transaction(context.company_db_path, context):
            raise KeyError("programming error")


def test_an_earlier_error_is_not_printed_with_the_database_error(world, log_file, monkeypatch):
    """A rollback that fails while a service error is on its way out: the log gets the database error only."""
    from modules.services import tx
    context = world.ctx(world.user("ann"), "PARENT")
    real = tx.database.get_connection

    class Failing:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def __setattr__(self, name, value):
            if name == "_conn":
                object.__setattr__(self, name, value)
            else:
                setattr(self._conn, name, value)

        def execute(self, sql, *args):
            if sql == "ROLLBACK":
                self._conn.execute("ROLLBACK")
                raise sqlite3.OperationalError("disk I/O error")
            return self._conn.execute(sql, *args)

    monkeypatch.setattr(tx.database, "get_connection", lambda path: Failing(real(path)))
    with pytest.raises(SaveFailedError):
        with write_transaction(context.company_db_path, context):
            raise ValidationError("The company code TYPED-BY-A-PERSON is already used")
    text = log_file.read_text(encoding="utf-8")
    assert "disk I/O error" in text and "TYPED-BY-A-PERSON" not in text
