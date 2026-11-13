"""Rotating file log for errors (CLAUDE.md rule 12).

The file handler carries LogMessageFilter (decision R30): a service error that quotes what a person typed (a
rejection reason) is written to the file as its fixed log_message, never as the text the person saw.
"""
import logging
import os
import traceback
from logging.handlers import RotatingFileHandler

import config

LOGGER_NAME = "strataledger"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5


class LogMessageFilter(logging.Filter):
    """Swap the text of each error that has a log_message for that sentence: in the message, in the arguments and
    in the traceback. Every error linked to the logged one is searched: causes, contexts (even when the chain was
    cut with `from None`) and the members of an exception group, so an error that quotes a hidden one is cleaned
    too. The record is changed in place, so handlers after this one also get the clean text.

    The filter sees only error objects. Logging an error's text (str(error), an f-string) would bypass it, so a
    static test forbids that (tests/test_rejection_logging.py).
    """

    def filter(self, record):
        record.msg = _clean(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_clean(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _clean(v) for k, v in record.args.items()}
        if record.exc_info and record.exc_info[1] is not None:
            hidden = _hidden(record.exc_info[1])
            if hidden:
                record.exc_text = _redact("".join(traceback.format_exception(*record.exc_info)), hidden).rstrip("\n")
        return True


def _clean(value):
    """An error linked to a hidden one becomes its cleaned text; anything else is returned unchanged."""
    if not isinstance(value, BaseException):
        return value
    hidden = _hidden(value)
    return _redact(str(value), hidden) if hidden else value


def _hidden(error):
    return [e for e in _linked(error) if getattr(e, "log_message", None) is not None]


def _redact(text, hidden):
    for error in hidden:
        shown = str(error)
        for form in (repr(error), repr(shown)[1:-1], shown):    # repr first: it contains the plain text
            text = text.replace(form, error.log_message)
    return text


def _linked(error):
    """The error and every error reachable from it: __cause__, __context__ and exception group members."""
    seen, todo = [], [error]
    while todo:
        current = todo.pop()
        if current is None or any(current is s for s in seen):
            continue
        seen.append(current)
        todo += [current.__cause__, current.__context__, *getattr(current, "exceptions", ())]
    return seen


def configure_logging(log_path=None):
    """Attach one rotating file handler to the app logger; safe to call twice."""
    path = os.fspath(log_path if log_path is not None else config.LOG_FILE)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    target = os.path.abspath(path)
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename == target:
            return logger
    handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(LogMessageFilter())
    logger.addHandler(handler)
    return logger
