import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler


def setup_unified_logging():
    tradingagents_home = os.environ.get(
        "TRADINGAGENTS_LOG_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents"),
    )
    os.makedirs(tradingagents_home, exist_ok=True)
    log_file_path = os.path.join(tradingagents_home, "tradingagents.log")
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    try:
        file_handler = RotatingFileHandler(log_file_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
    except Exception as e:
        sys.stderr.write(f"Failed to initialize rotating file log handler: {e}\n")
        file_handler = None
    console_level_name = os.environ.get("TRADINGAGENTS_CONSOLE_LOG_LEVEL", "WARNING").upper()
    if os.environ.get("DEBUG") in ("true", "1", "yes", "on"):
        console_level_name = "DEBUG"
    try:
        console_level = getattr(logging, console_level_name)
    except AttributeError:
        console_level = logging.WARNING
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    if file_handler:
        root_logger.addHandler(file_handler)
    tradingagents_logger = logging.getLogger("tradingagents")
    tradingagents_logger.setLevel(logging.DEBUG)
    tradingagents_logger.addHandler(console_handler)
    tradingagents_logger.propagate = True
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

    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        tb_str = "".join(tb_lines)
        logger = logging.getLogger("tradingagents.error_tracker")
        logger.error(f"Unhandled exception occurred:\n{tb_str}")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_unhandled_exception
    logger = logging.getLogger("tradingagents.initializer")
    logger.info("Unified logging initialized successfully.")
