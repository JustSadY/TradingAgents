import asyncio
import logging
from collections.abc import Callable
from typing import Any

_logger = logging.getLogger(__name__)

# Simple event bus to decouple services
_subscribers: dict[str, list[Callable]] = {}


def subscribe(event_type: str, handler: Callable):
    if event_type not in _subscribers:
        _subscribers[event_type] = []
    _subscribers[event_type].append(handler)


async def emit(event_type: str, **kwargs: Any):
    _logger.debug("Emitting event: %s", event_type)
    for handler in _subscribers.get(event_type, []):
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(**kwargs)
            else:
                handler(**kwargs)
        except Exception:
            _logger.exception("Error in event handler for %s", event_type)
