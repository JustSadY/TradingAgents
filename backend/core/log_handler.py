"""Persist application logs to ``system_logs`` for the in-app System Logs page.

Every process that does application work attaches this handler and must call
``db_log_handler.start()`` once an event loop exists — the FastAPI lifespan and
the arq worker both do. A process that skips ``start()`` still logs to console
and file but writes nothing to the database, which is why worker-mode analyses
used to be missing from the System Logs page entirely.

What reaches the database is a level threshold (``SYSTEM_LOG_DB_LEVEL``, INFO by
default) minus a small denylist of chatty third-party loggers, not an allowlist
of ``backend.*`` prefixes. An allowlist silently drops whole subsystems — the
trading engine, repositories, the worker, uvicorn — the moment they are renamed
or added.
"""

import asyncio
import contextvars
import logging

current_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("current_user_id", default=None)

_BATCH_SIZE = 30
_FLUSH_INTERVAL = 3.0
_QUEUE_MAXSIZE = 10000
_DROP_REPORT_INTERVAL = 500

# Third-party loggers whose DEBUG/INFO chatter is per-request or per-socket
# noise. They still reach the database at WARNING and above.
_NOISY_LOGGER_PREFIXES = (
    "aiosqlite",
    "apscheduler.executors",
    "apscheduler.scheduler",
    "arq.worker",
    "asyncio",
    "botocore",
    "charset_normalizer",
    "google",
    "httpcore",
    "httpx",
    "matplotlib",
    "openai._base_client",
    "peewee",
    "PIL",
    "rich",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "urllib3",
    "uvicorn.access",
    "watchfiles",
    "yfinance",
)

_DEFAULT_DB_LEVEL = logging.INFO


def _configured_db_level() -> int:
    """Resolve the minimum level persisted to the database."""
    try:
        from backend.core.config import get_settings

        raw = (get_settings().SYSTEM_LOG_DB_LEVEL or "").strip().upper()
    except Exception:  # noqa: BLE001 — logging must never depend on settings loading
        return _DEFAULT_DB_LEVEL
    resolved = logging.getLevelName(raw) if raw else None
    return resolved if isinstance(resolved, int) else _DEFAULT_DB_LEVEL


class _BackendFilter(logging.Filter):
    """Keep everything at or above the configured level, minus known noise."""

    def __init__(self):
        super().__init__()
        self.min_level = _DEFAULT_DB_LEVEL

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        if record.levelno < self.min_level:
            return False
        return not record.name.startswith(_NOISY_LOGGER_PREFIXES)


class DatabaseLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self._backend_filter = _BackendFilter()
        self.addFilter(self._backend_filter)
        from backend.core.log_redaction import redaction_filter

        self.addFilter(redaction_filter)
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None
        self._started = False
        self._dropped = 0

    async def start(self):
        if self._started:
            return
        self._backend_filter.min_level = _configured_db_level()
        # The root logger's own level gates records before any handler sees
        # them, so a root left at WARNING would keep INFO out of the database
        # no matter what this handler accepts.
        root = logging.getLogger()
        if root.level > self._backend_filter.min_level:
            root.setLevel(self._backend_filter.min_level)
        self._queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._task = asyncio.create_task(self._worker(), name="db-log-worker")
        self._started = True

    def stop(self):
        if self._queue is not None:
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def emit(self, record: logging.LogRecord):
        if not self._started or self._queue is None:
            return
        user_id = getattr(record, "user_id", None)
        if user_id is None:
            user_id = current_user_id.get(None)
        try:
            self._queue.put_nowait(
                {
                    "level": record.levelname[:20],
                    # ``system_logs.source`` is String(100); an over-long logger
                    # name would fail the whole batch insert, not just its row.
                    "source": record.name[:100],
                    "message": self.format(record),
                    "details": self._exc_text(record),
                    "user_id": user_id,
                }
            )
        except asyncio.QueueFull:
            # Losing log lines without saying so is what makes "the System Logs
            # page is missing entries" impossible to diagnose from inside the app.
            self._dropped += 1
            if self._dropped % _DROP_REPORT_INTERVAL == 1:
                import sys

                sys.stderr.write(
                    f"DatabaseLogHandler queue is full; {self._dropped} log record(s) not persisted.\n"
                )

    @staticmethod
    def _exc_text(record: logging.LogRecord) -> str | None:
        if record.exc_text:
            return record.exc_text
        if record.exc_info:
            import traceback

            return "".join(traceback.format_exception(*record.exc_info))
        return None

    async def _worker(self):
        from backend.core.rls_context import BackgroundCapability, trusted_background_session
        from backend.models.log import SystemLog

        batch: list[dict] = []

        async def flush():
            if not batch:
                return
            items = batch.copy()
            batch.clear()
            try:
                # A batch mixes records from several tenants with records that
                # belong to none, so no single tenant context can insert it.
                # Row-level security rejects an unscoped session outright, which
                # silently emptied the System Logs page on PostgreSQL.
                async with trusted_background_session(BackgroundCapability.SYSTEM_LOGGING) as db:
                    for entry in items:
                        db.add(
                            SystemLog(
                                level=entry["level"],
                                source=entry["source"],
                                message=entry["message"],
                                details=entry["details"],
                                user_id=entry["user_id"],
                            )
                        )
                    await db.commit()
            except Exception as exc:
                import sys

                sys.stderr.write(f"DatabaseLogHandler flush failed: {exc}\n")

        while True:
            try:
                entry = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=_FLUSH_INTERVAL,
                )
                if entry is None:
                    await flush()
                    return
                batch.append(entry)
                if len(batch) >= _BATCH_SIZE:
                    await flush()
            except TimeoutError:
                await flush()

db_log_handler = DatabaseLogHandler()
_fmt = logging.Formatter("%(message)s")
db_log_handler.setFormatter(_fmt)
logging.getLogger().addHandler(db_log_handler)
