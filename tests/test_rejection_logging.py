"""Rejection reasons never reach the log file (decision R30; CLAUDE.md rule 12).

A refusal that quotes the rejection reason shows it to the person; the log file gets a fixed sentence without it
(ServiceError.log_message, applied by the file handler's filter). The reason itself stays in approval_action.
"""
import ast
import logging
from pathlib import Path

import pytest

from modules.services import approvals, errors, logging_setup
from modules.services.errors import PostingError, ServiceError, ValidationError
from tests.authz_world import world  # noqa: F401  (fixture)
from tests.test_ledger_approvals import _require_approval, actions_of, as_, make, post, submit, team  # noqa: F401
from tests.test_ledger_posting import env, keyed  # noqa: F401  (fixtures)

MARKER = "MARKER-7f3c-private"
POSTING_LOG = "This entry was rejected; change it and send it for approval again."
RESUBMIT_LOG = "Change the entry before sending it again; it was rejected."
SERVICES = Path(__file__).resolve().parent.parent / "modules" / "services"


@pytest.fixture
def log_file(tmp_path):
    logger = logging.getLogger(logging_setup.LOGGER_NAME)
    saved = list(logger.handlers)
    logger.handlers.clear()
    path = tmp_path / "logs" / "app.log"
    logging_setup.configure_logging(path)

    def read():
        for handler in logger.handlers:
            handler.flush()
        return path.read_text(encoding="utf-8")
    yield read
    for handler in list(logger.handlers):
        handler.close()
    logger.handlers[:] = saved


def _rejected(team):
    _require_approval(team)
    entry_id = make(team)
    request_id = submit(team, entry_id)
    approvals.reject(as_(team, "appr1"), request_id, f"Wrong account {MARKER}.")
    return entry_id, request_id


def _log_every_way(error):
    """The ways a screen or service might log an error."""
    logger = logging.getLogger("strataledger.app")
    logger.error("refused: %s", error)
    logger.error(error)
    logger.warning("refused (%r)", error)
    try:
        raise error
    except ServiceError:
        logger.exception("the action failed")
    try:
        try:
            raise error
        except ServiceError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError:
        logger.exception("a chained failure")


def test_posting_a_rejected_entry_never_logs_the_reason(team, log_file):
    entry_id, request_id = _rejected(team)
    with pytest.raises(PostingError) as error:
        post(team, entry_id)
    assert MARKER in str(error.value)                         # the person sees the reason
    assert error.value.log_message == POSTING_LOG
    _log_every_way(error.value)
    text = log_file()
    assert MARKER not in text
    assert text.count(POSTING_LOG) >= 5
    assert MARKER in actions_of(team, request_id)[0]["reason"]   # the reason stays in approval_action


def test_resubmitting_a_rejected_entry_never_logs_the_reason(team, log_file):
    entry_id, _ = _rejected(team)
    with pytest.raises(ValidationError) as error:
        submit(team, entry_id)
    assert MARKER in str(error.value)
    assert error.value.log_message == RESUBMIT_LOG
    _log_every_way(error.value)
    text = log_file()
    assert MARKER not in text and RESUBMIT_LOG in text


def test_an_error_without_a_log_message_is_logged_as_it_reads(log_file):
    error = ValidationError("Enter a date.")
    assert error.log_message is None and errors.log_text(error) == "Enter a date."
    _log_every_way(error)
    assert log_file().count("Enter a date.") >= 5


def test_log_text_prefers_the_log_message():
    error = PostingError("Rejected (secret)", log_message="Rejected.")
    assert (str(error), errors.log_text(error), error.args) == ("Rejected (secret)", "Rejected.", ("Rejected (secret)",))


def test_the_filter_leaves_other_handlers_and_records_alone(log_file):
    logging.getLogger("strataledger").info("plain %s", "text")
    assert "plain text" in log_file()


def _reason_violations(source):
    found = []
    error_names = {n.name for n in ast.parse((SERVICES / "errors.py").read_text(encoding="utf-8")).body
                   if isinstance(n, ast.ClassDef)}
    for node in ast.walk(ast.parse(source)):
        name = None
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
        if name not in error_names:
            continue
        quotes_reason = any(
            isinstance(v, ast.FormattedValue) and "reason" in ast.unparse(v.value)
            for sub in ast.walk(node) if isinstance(sub, ast.JoinedStr) for v in sub.values)
        if quotes_reason and not any(k.arg == "log_message" for k in node.keywords):
            found.append(node.lineno)
    return found


def test_every_refusal_quoting_a_reason_has_a_fixed_log_message():
    found = {path.name: _reason_violations(path.read_text(encoding="utf-8")) for path in SERVICES.glob("*.py")}
    assert {name: lines for name, lines in found.items() if lines} == {}


def test_the_reason_check_catches_a_missing_log_message():
    assert _reason_violations('raise PostingError(f"Rejected ({reason_text(state[\'reason\'])})")') == [1]
    assert _reason_violations('raise PostingError(f"Rejected ({reason})", log_message="Rejected.")') == []
    assert _reason_violations('raise errors.PostingError(f"Rejected ({reason})")') == [1]


# --- Review fixes: the paths the filter cannot see are forbidden; the ones it can see are covered -----------------

LOG_LEVELS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
LOGGING_SOURCES = sorted(Path(__file__).resolve().parent.parent.joinpath("modules").rglob("*.py")) + [
    Path(__file__).resolve().parent.parent / "app_strata.pyw"]


def _logging_violations(source):
    """A logger call that passes an error's text instead of the error (the filter swaps only error objects), or a
    reason: an f-string, str(...), repr(...), .args, or anything naming a reason."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_LEVELS
                and "log" in ast.unparse(node.func.value).lower()):
            continue
        for arg in node.args:
            if (isinstance(arg, (ast.JoinedStr, ast.BinOp))
                    or (isinstance(arg, ast.Call) and getattr(arg.func, "id", None) in ("str", "repr", "format_exc"))
                    or (isinstance(arg, ast.Call) and getattr(arg.func, "attr", None) in ("format", "format_exc"))
                    or any(isinstance(n, ast.Attribute) and n.attr == "args" for n in ast.walk(arg))
                    or "reason" in ast.unparse(arg)):
                found.append(f"{node.lineno}: {ast.unparse(arg)[:60]}")
    return found


def test_no_logger_call_passes_an_errors_text_or_a_reason():
    found = {path.name: _logging_violations(path.read_text(encoding="utf-8")) for path in LOGGING_SOURCES}
    assert {name: lines for name, lines in found.items() if lines} == {}


@pytest.mark.parametrize("source", [
    '_logger.error("refused: %s", str(error))',
    '_logger.error(f"refused: {error}")',
    'logger.warning("refused: %s", error.args)',
    '_logger.error("refused: %s", repr(error))',
    '_logger.error("refused: %s" % error)',
    '_logger.error("refused: {}".format(error))',
    '_logger.error("trace: %s", traceback.format_exc())',
    '_logger.info("rejected because %s", reason)',
])
def test_the_logging_check_catches_text_of_an_error(source):
    assert _logging_violations(source) != []


def test_the_logging_check_passes_the_error_itself():
    assert _logging_violations('_logger.error("refused: %s", error)') == []
    assert _logging_violations('_logger.exception("the action failed (company_id=%s)", company_id)') == []
    assert _logging_violations('_logger.warning("failed: %s", type(error).__name__)') == []


def test_a_reason_with_newlines_and_quotes_is_hidden_too(team, log_file):
    _require_approval(team)
    entry_id = make(team)
    approvals.reject(as_(team, "appr1"), submit(team, entry_id), f"Wrong 'acct'\n\"{MARKER}\"\ok")
    with pytest.raises(PostingError) as error:
        post(team, entry_id)
    _log_every_way(error.value)
    assert MARKER not in log_file()


def _raise_wrapped(error, style):
    try:
        raise error
    except ServiceError as inner:
        if style == "context":
            raise RuntimeError("cleanup failed")                         # implicit __context__
        if style == "from None":
            raise ValidationError(f"The step failed: {inner}") from None  # chain cut, text quoted
        if style == "repr":
            raise RuntimeError(f"wrapped {inner!r}") from inner
        raise ExceptionGroup("several", [inner, ValueError("other")])


@pytest.mark.parametrize("style", ["context", "from None", "repr", "group"])
def test_wrapped_and_grouped_errors_are_hidden(team, log_file, style):
    entry_id, _ = _rejected(team)
    with pytest.raises(PostingError) as error:
        post(team, entry_id)
    try:
        _raise_wrapped(error.value, style)
    except BaseException:  # noqa: BLE001
        logging.getLogger("strataledger.app").exception("a wrapped failure")
    text = log_file()
    assert MARKER not in text and POSTING_LOG in text


def test_a_service_error_quoting_another_keeps_its_log_message():
    """Re-wrapping inside a service: the new error's text quotes the old one, so the filter swaps that part too."""
    inner = PostingError(f"Rejected ({MARKER})", log_message="Rejected.")
    outer = ValidationError(f"The step failed: {inner}")
    outer.__context__ = inner
    record = logging.LogRecord("strataledger", logging.ERROR, __file__, 1, "x %s", (outer,), None)
    logging_setup.LogMessageFilter().filter(record)
    assert MARKER not in record.getMessage()


def test_every_reason_text_call_is_inside_an_error_with_a_log_message():
    """Low 2: a reason read through any name still reaches a sentence only through reason_text."""
    for path in SERVICES.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and "reason_text" in ast.unparse(n.func)]
        covered = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and any(k.arg == "log_message" for k in node.keywords):
                covered |= {id(n) for n in ast.walk(node)}
        assert [c.lineno for c in calls if id(c) not in covered] == [], path.name


# --- Mutation-test gaps (db67342) ---------------------------------------------------------------------------

def _hidden_error():
    return PostingError(f"Rejected ({MARKER})", log_message="Rejected.")


def _filtered(record):
    logging_setup.LogMessageFilter().filter(record)
    return record


def _record(msg, args=None, exc_info=None):
    return logging.LogRecord("strataledger", logging.ERROR, __file__, 1, msg, args, exc_info)


def test_dict_arguments_are_cleaned():
    record = _filtered(_record("refused: %(e)s", ({"e": _hidden_error()},)))
    assert record.getMessage() == "refused: Rejected."


def test_a_cause_set_without_a_context_is_cleaned():
    outer = RuntimeError(f"wrapped: {_hidden_error()}")
    outer.__cause__ = _hidden_error()
    outer.__cause__.args = (f"Rejected ({MARKER})",)
    assert outer.__context__ is None
    assert MARKER not in _filtered(_record("x %s", (outer,))).getMessage()


def test_an_exception_group_member_is_cleaned():
    group = ExceptionGroup("several", [_hidden_error(), ValueError("other")])
    assert group.__context__ is None and group.__cause__ is None
    record = _filtered(_record("failed", None, (ExceptionGroup, group, None)))
    assert MARKER not in record.exc_text and "Rejected." in record.exc_text


def test_a_cycle_of_linked_errors_ends():
    first, second = _hidden_error(), RuntimeError("second")
    first.__context__, second.__context__ = second, first
    import threading
    record = _record("x %s", (second,))
    worker = threading.Thread(target=_filtered, args=(record,), daemon=True)
    worker.start()
    worker.join(10)
    assert not worker.is_alive(), "the filter loops on a cycle of linked errors"
    assert MARKER not in record.getMessage()


def test_the_cleaned_traceback_has_no_trailing_newline():
    error = _hidden_error()
    record = _filtered(_record("failed", None, (PostingError, error, None)))
    assert record.exc_text and not record.exc_text.endswith("\n") and MARKER not in record.exc_text
