import logging
from typing import Any, Callable, Dict, List

_logger = logging.getLogger(__name__)

# Simple event bus to decouple services
_subscribers: Dict[str, List[Callable]] = {}

def subscribe(event_type: str, handler: Callable):
    if event_type not in _subscribers:
        _subscribers[event_type] = []
    _subscribers[event_type].append(handler)

def emit(event_type: str, **kwargs: Any):
    _logger.debug("Emitting event: %s", event_type)
    for handler in _subscribers.get(event_type, []):
        try:
            # Check if handler is async or sync is handled by the caller or just call
            # For simplicity in this project, we'll assume they can be either
            import asyncio
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler(**kwargs))
            else:
                handler(**kwargs)
        except Exception as e:
            _logger.error("Error in event handler for %s: %s", event_type, e)
