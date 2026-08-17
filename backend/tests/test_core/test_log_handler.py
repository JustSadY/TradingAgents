"""What the System Logs page is allowed to miss."""

from __future__ import annotations

import logging

from backend.core.log_handler import _NOISY_LOGGER_PREFIXES, DatabaseLogHandler, _BackendFilter


def _record(name: str, level: int) -> logging.LogRecord:
    return logging.LogRecord(name=name, level=level, pathname=__file__, lineno=1, msg="m", args=(), exc_info=None)


class TestDatabaseLogFilter:
    def test_keeps_info_from_any_application_logger(self):
        """An allowlist of ``backend.`` prefixes silently dropped whole subsystems."""
        log_filter = _BackendFilter()

        for name in (
            "backend.services.analysis_service",
            "backend.repositories.analysis",
            "backend.trading_agents.graph.trading_graph",
            "backend.worker",
            "tradingagents.run",
        ):
            assert log_filter.filter(_record(name, logging.INFO)) is True, name

    def test_keeps_warnings_and_errors_even_from_noisy_libraries(self):
        log_filter = _BackendFilter()

        for name in _NOISY_LOGGER_PREFIXES:
            assert log_filter.filter(_record(name, logging.WARNING)) is True, name
            assert log_filter.filter(_record(name, logging.ERROR)) is True, name

    def test_drops_third_party_info_chatter(self):
        log_filter = _BackendFilter()

        assert log_filter.filter(_record("httpx", logging.INFO)) is False
        assert log_filter.filter(_record("uvicorn.access", logging.INFO)) is False

    def test_honours_a_raised_threshold(self):
        log_filter = _BackendFilter()
        log_filter.min_level = logging.WARNING

        assert log_filter.filter(_record("backend.services.x", logging.INFO)) is False
        assert log_filter.filter(_record("backend.services.x", logging.WARNING)) is True


class TestDatabaseLogHandler:
    async def test_start_lowers_a_root_logger_that_would_gate_info_records(self):
        handler = DatabaseLogHandler()
        root = logging.getLogger()
        original = root.level
        root.setLevel(logging.WARNING)
        try:
            await handler.start()
            assert root.level <= logging.INFO
        finally:
            handler.stop()
            root.setLevel(original)

    async def test_long_logger_names_are_truncated_to_the_column_width(self):
        handler = DatabaseLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        await handler.start()
        try:
            handler.emit(_record("x" * 250, logging.ERROR))
            entry = handler._queue.get_nowait()
            assert len(entry["source"]) == 100
        finally:
            handler.stop()
