import logging
from logging.handlers import RotatingFileHandler

import pytest

import config
from modules.services import logging_setup


@pytest.fixture(autouse=True)
def clean_logger():
    logger = logging.getLogger(logging_setup.LOGGER_NAME)
    saved = list(logger.handlers)
    logger.handlers.clear()
    yield logger
    for handler in list(logger.handlers):
        handler.close()
    logger.handlers[:] = saved


def test_config_defines_log_paths_under_base_dir():
    assert config.LOG_FILE.startswith(config.LOG_DIR)
    assert config.LOG_DIR.startswith(config.BASE_PROJECT_DIR)
    assert config.APP_VERSION


def test_configure_logging_writes_to_given_path(tmp_path):
    path = tmp_path / "logs" / "app.log"
    logger = logging_setup.configure_logging(path)
    logger.error("disk on fire")
    for handler in logger.handlers:
        handler.flush()
    assert "disk on fire" in path.read_text(encoding="utf-8")


def test_handler_is_rotating(tmp_path):
    logger = logging_setup.configure_logging(tmp_path / "app.log")
    handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes > 0 and handlers[0].backupCount > 0


def test_second_call_does_not_duplicate_handlers(tmp_path):
    path = tmp_path / "app.log"
    logging_setup.configure_logging(path)
    logger = logging_setup.configure_logging(path)
    assert len(logger.handlers) == 1


def test_default_path_is_config_log_file(tmp_path, monkeypatch):
    path = tmp_path / "default.log"
    monkeypatch.setattr(config, "LOG_FILE", str(path))
    logger = logging_setup.configure_logging()
    logger.error("x")
    assert path.exists()
