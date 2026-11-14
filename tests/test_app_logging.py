"""R33: the app starts its log file before anything else (DATA_DIR\\Logs, rotating, with the R30 filter)."""
import ast
import importlib.machinery
import importlib.util
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

import config
from modules.services import logging_setup

APP = Path(__file__).resolve().parent.parent / "app_strata.pyw"


@pytest.fixture(scope="module")
def app_module():
    loader = importlib.machinery.SourceFileLoader("app_strata_for_logging", str(APP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def clean_logger():
    logger = logging.getLogger(logging_setup.LOGGER_NAME)
    before = list(logger.handlers)
    yield logger
    for handler in list(logger.handlers):
        if handler not in before:
            logger.removeHandler(handler)
            handler.close()


def _main_block():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            return node
    raise AssertionError("app_strata.pyw has no __main__ block")


def test_main_starts_logging_before_the_app():
    calls = [ast.unparse(n.func) for n in ast.walk(_main_block()) if isinstance(n, ast.Call)]
    assert "start_logging" in calls and "App" in calls
    assert calls.index("start_logging") < calls.index("App")


def test_the_log_file_is_under_the_data_folders_logs():
    assert Path(config.LOG_FILE).parent == Path(config.DATA_DIR) / "Logs"
    assert Path(config.LOG_FILE).name == "strataledger.log"


def test_start_logging_opens_a_rotating_filtered_file(app_module, clean_logger, tmp_path, monkeypatch):
    path = tmp_path / "Logs" / "strataledger.log"
    monkeypatch.setattr(config, "LOG_FILE", str(path))
    assert app_module.start_logging() is None
    handlers = [h for h in clean_logger.handlers if getattr(h, "baseFilename", None) == str(path.resolve())]
    assert len(handlers) == 1 and isinstance(handlers[0], RotatingFileHandler)
    handler = handlers[0]
    assert (handler.maxBytes, handler.backupCount) == (logging_setup.MAX_BYTES, logging_setup.BACKUP_COUNT)
    assert handler.maxBytes > 0 and handler.backupCount > 0
    assert any(isinstance(f, logging_setup.LogMessageFilter) for f in handler.filters)
    logging.getLogger("strataledger.app").error("started")
    handler.flush()
    assert "started" in path.read_text(encoding="utf-8")


def test_a_log_folder_that_cannot_be_made_still_starts(app_module, clean_logger, tmp_path, monkeypatch):
    blocker = tmp_path / "Logs"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setattr(config, "LOG_FILE", str(blocker / "strataledger.log"))
    assert app_module.start_logging() == app_module.LOG_UNAVAILABLE
    assert app_module.LOG_UNAVAILABLE == ("The log file could not be opened, so errors will not be recorded; "
                                          "check that the data folder can be written.")


# --- R38: every logger in the app is under the app's logger, so its lines reach the file ---------------------

ROOT = APP.parent


def _is_get_logger(node):
    """logging.getLogger(...) or a bare getLogger(...) imported from logging."""
    return isinstance(node, ast.Call) and "getLogger" in (getattr(node.func, "attr", None),
                                                          getattr(node.func, "id", None))


def _logger_names():
    """(file, name) for every logging.getLogger(...) call in app_strata.pyw and modules/."""
    found = []
    for path in [APP, *sorted((ROOT / "modules").rglob("*.py"))]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if _is_get_logger(node) and path.name != "logging_setup.py":
                arg = node.args[0] if node.args else None
                name = arg.value if isinstance(arg, ast.Constant) else ast.unparse(arg) if arg else ""
                found.append((path.name, name))
    return found


def test_the_logger_scan_sees_a_bare_getlogger():
    tree = ast.parse("from logging import getLogger\nlog = getLogger(__name__)\nlogging.getLogger('x')\n")
    assert len([n for n in ast.walk(tree) if _is_get_logger(n)]) == 2


def test_every_logger_is_under_the_app_logger():
    wrong = [(f, n) for f, n in _logger_names()
             if not (n == logging_setup.LOGGER_NAME or str(n).startswith(logging_setup.LOGGER_NAME + "."))]
    assert wrong == []


def test_a_font_warning_reaches_the_log_file(clean_logger, tmp_path):
    from modules import font_loader
    path = tmp_path / "Logs" / "strataledger.log"
    logging_setup.configure_logging(str(path))
    font_loader.logger.warning("Inter font provisioning failed; using Segoe UI")
    for handler in clean_logger.handlers:
        handler.flush()
    assert "Inter font provisioning failed" in path.read_text(encoding="utf-8")
