"""Regression tests for the engine's unified logging setup.

The legacy implementation cleared the root logger's handlers on import of the
engine package, silently destroying the web process's console logging (no app
logs in journalctl) and dropping the secret-redaction filter. These tests pin
the fixed contract: additive, idempotent, redacted.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

import pytest

from backend.core.log_redaction import redaction_filter
from backend.trading_agents.agents.runtime import logging_config


@pytest.fixture
def clean_logging(monkeypatch, tmp_path):
    """Snapshot global logging state and reset the module's idempotency flag."""
    monkeypatch.setenv("TRADINGAGENTS_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(logging_config, "_CONFIGURED", False)
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_hook = sys.excepthook
    yield root
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    sys.excepthook = saved_hook


def _file_handlers(root):
    return [h for h in root.handlers if isinstance(h, RotatingFileHandler)]


def test_web_context_console_handler_is_preserved(clean_logging):
    root = clean_logging
    # Simulate the web app: backend/main.py installed a console handler.
    console = logging.StreamHandler(sys.stderr)
    root.handlers[:] = [console]
    root.setLevel(logging.INFO)

    logging_config.setup_unified_logging()

    assert console in root.handlers, "host console handler must survive"
    # Web verbosity is the host's choice; the engine must not lower it.
    assert root.level == logging.INFO
    assert len(_file_handlers(root)) == 1


def test_file_handler_redacts_secrets(clean_logging):
    root = clean_logging
    root.handlers[:] = [logging.StreamHandler(sys.stderr)]

    logging_config.setup_unified_logging()

    (file_handler,) = _file_handlers(root)
    assert redaction_filter in file_handler.filters


def test_setup_is_idempotent(clean_logging):
    root = clean_logging
    root.handlers[:] = [logging.StreamHandler(sys.stderr)]

    logging_config.setup_unified_logging()
    logging_config.setup_unified_logging()

    assert len(_file_handlers(root)) == 1


def test_standalone_context_gets_console_and_debug(clean_logging):
    root = clean_logging
    root.handlers[:] = []  # CLI script: nothing configured yet

    logging_config.setup_unified_logging()

    assert root.level == logging.DEBUG
    assert len(_file_handlers(root)) == 1
    consoles = [h for h in root.handlers if type(h) is logging.StreamHandler]
    assert len(consoles) == 1
    assert redaction_filter in consoles[0].filters
