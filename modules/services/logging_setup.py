"""Rotating file log for errors (CLAUDE.md rule 12)."""
import logging
import os
from logging.handlers import RotatingFileHandler

import config

LOGGER_NAME = "strataledger"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5


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
    logger.addHandler(handler)
    return logger
