import asyncio
import contextvars
import logging

current_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("current_user_id", default=None)

_BATCH_SIZE = 30
_FLUSH_INTERVAL = 3.0
_QUEUE_MAXSIZE = 2000
_VERBOSE_PREFIXES = (
    "backend.services.",
    "backend.api.",
    "backend.core.websocket",
    "tradingagents.run",
)


class _BackendFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        if record.levelno == logging.INFO:
            return any(record.name.startswith(p) for p in _VERBOSE_PREFIXES)
        return False


class DatabaseLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.addFilter(_BackendFilter())
        from backend.core.log_redaction import redaction_filter

        self.addFilter(redaction_filter)
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None
        self._started = False

    async def start(self):
        if self._started:
            return
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
                    "level": record.levelname,
                    "source": record.name,
                    "message": self.format(record),
                    "details": self._exc_text(record),
                    "user_id": user_id,
                }
            )
        except asyncio.QueueFull:
            pass

    @staticmethod
    def _exc_text(record: logging.LogRecord) -> str | None:
        if record.exc_text:
            return record.exc_text
        if record.exc_info:
            import traceback

            return "".join(traceback.format_exception(*record.exc_info))
        return None

    async def _worker(self):
        from backend.core.database import AsyncSessionLocal
        from backend.models.log import SystemLog

        batch: list[dict] = []

        async def flush():
            if not batch:
                return
            items = batch.copy()
            batch.clear()
            try:
                async with AsyncSessionLocal() as db:
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
            except Exception:
                pass

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
