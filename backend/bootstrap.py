"""Runtime bootstrap for the TradingAgents backend.

The AI engine under ``backend/trading_agents`` is a *normal sub-package of
``backend``* — it is imported as ``backend.trading_agents.*`` like any other
backend module (no import aliasing / meta-path tricks).

Importing this module (idempotently) guarantees one thing the engine relies on:

1. ``TRADINGAGENTS_*`` environment variables point at writable temp directories
   so the engine never writes into the (possibly read-only) source tree.

Import it early (before anything that pulls in ``backend.trading_agents``):
``import backend.bootstrap``.
"""

from __future__ import annotations

import os
import sys
import tempfile

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

def _configure_env() -> None:
    """Point the engine's cache/results/log paths at the system temp dir."""
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

init()
