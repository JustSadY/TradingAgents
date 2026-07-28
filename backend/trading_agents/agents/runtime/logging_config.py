import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

_CONFIGURED = False


def _redaction_filter():
    """The backend's secret-redaction filter (None if unavailable)."""
    try:
        from backend.core.log_redaction import redaction_filter

        return redaction_filter
    except Exception:  # noqa: BLE001 — logging must never break engine import
        return None


def setup_unified_logging():
    """Attach the engine's rotating file log without disturbing the host app.

    Historically this cleared the root logger's handlers, which silently
    destroyed the web process's console logging (journalctl showed no
    application logs) and dropped the redaction filter. It is now additive and
    idempotent: the file handler is appended, and console handling / DEBUG
    verbosity are only configured when running standalone (CLI scripts) where
    no logging has been set up yet.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    tradingagents_home = os.environ.get(
        "TRADINGAGENTS_LOG_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents"),
    )
    os.makedirs(tradingagents_home, exist_ok=True)
    log_file_path = os.path.join(tradingagents_home, "tradingagents.log")
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    redaction = _redaction_filter()

    root_logger = logging.getLogger()
    # No handlers means no host application configured logging (CLI usage);
    # the web app installs its console handler in backend/main.py.
    standalone = not root_logger.handlers

    try:
        file_handler = RotatingFileHandler(log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        if redaction is not None:
            file_handler.addFilter(redaction)
        root_logger.addHandler(file_handler)
    except Exception as e:  # noqa: BLE001 — a read-only disk must not break startup
        sys.stderr.write(f"Failed to initialize rotating file log handler: {e}\n")

    if standalone:
        root_logger.setLevel(logging.DEBUG)
        console_level_name = os.environ.get("TRADINGAGENTS_CONSOLE_LOG_LEVEL", "WARNING").upper()
        if os.environ.get("DEBUG") in ("true", "1", "yes", "on"):
            console_level_name = "DEBUG"
        console_level = getattr(logging, console_level_name, logging.WARNING)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        if redaction is not None:
            console_handler.addFilter(redaction)
        root_logger.addHandler(console_handler)

    # Quiet chatty third-party libraries regardless of context.
    for logger_name in [
        "urllib3",
        "asyncio",
        "openai",
        "httpcore",
        "httpx",
        "peewee",
        "yfinance",
        "charset_normalizer",
        "matplotlib",
        "google",
        "httpcore.connection",
        "httpcore.http11",
        "openai._base_client",
        "rich",
    ]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # mplfinance asks for medium/semibold weights that Alpine's bundled fonts
    # map to normal/bold. The fallback is harmless, but it otherwise floods
    # persisted system logs once per chart render.
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        tb_str = "".join(tb_lines)
        logging.getLogger("tradingagents.error_tracker").error(f"Unhandled exception occurred:\n{tb_str}")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_unhandled_exception
    logging.getLogger("tradingagents.initializer").info("Unified logging initialized successfully.")
