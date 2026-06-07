import asyncio
import logging
from collections.abc import Callable
from typing import Any

_logger = logging.getLogger(__name__)

# Simple event bus to decouple services
_subscribers: dict[str, list[Callable]] = {}

# Strong references to in-flight handler tasks. asyncio only keeps a weak
# reference to tasks, so without this they can be garbage-collected mid-flight
# and silently cancelled.
_background_tasks: set[asyncio.Task] = set()


def subscribe(event_type: str, handler: Callable):
    if event_type not in _subscribers:
        _subscribers[event_type] = []
    _subscribers[event_type].append(handler)


def _on_task_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            _logger.error("Async event handler failed: %s", exc)


def emit(event_type: str, **kwargs: Any):
    _logger.debug("Emitting event: %s", event_type)
    for handler in _subscribers.get(event_type, []):
        try:
            if asyncio.iscoroutinefunction(handler):
                coro = handler(**kwargs)
                try:
                    task = asyncio.create_task(coro)
                except RuntimeError:
                    # No running event loop (emit called from a sync context):
                    # we can't schedule the coroutine here.
                    coro.close()
                    _logger.warning(
                        "Async handler for '%s' skipped: emit() called without a running event loop.",
                        event_type,
                    )
                    continue
                _background_tasks.add(task)
                task.add_done_callback(_on_task_done)
            else:
                handler(**kwargs)
        except Exception as e:
            _logger.error("Error in event handler for %s: %s", event_type, e)
