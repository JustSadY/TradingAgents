"""Runtime bootstrap for the TradingAgents backend.

The AI engine under ``backend/trading_agents`` is a normal sub-package of
``backend``. Importing this module idempotently configures writable runtime
paths, project imports, and optional technical tracing.
"""

from __future__ import annotations

import os
import sys
import tempfile

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)


def _configure_env() -> None:
    tmp = tempfile.gettempdir()
    os.environ.setdefault("TRADINGAGENTS_LOG_DIR", tmp)
    os.environ.setdefault("TRADINGAGENTS_DATA_CACHE_DIR", os.path.join(tmp, "ta_cache"))
    os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", os.path.join(tmp, "ta_results"))


def _ensure_project_on_path() -> None:
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)


_INITIALISED = False


def init() -> None:
    """Apply all bootstrap steps exactly once (safe to call repeatedly)."""
    global _INITIALISED
    if _INITIALISED:
        return
    _configure_env()
    _ensure_project_on_path()
    _INITIALISED = True

    # Instrumentation remains entirely opt-in. Keeping it here means it runs
    # before FastAPI/httpx clients are constructed, while an installation that
    # does not include OpenTelemetry has zero runtime dependency on it.
    try:
        from backend.core.observability import configure_optional_opentelemetry

        configure_optional_opentelemetry()
    except Exception:
        # Observability must never make the trading application unbootable.
        import logging

        logging.getLogger(__name__).exception("Optional OpenTelemetry bootstrap failed")


init()
