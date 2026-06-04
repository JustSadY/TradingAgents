"""Runtime bootstrap for the TradingAgents backend.

Importing this module (which is idempotent) guarantees three things that the
rest of the backend and the vendored AI engine rely on:

1. ``TRADINGAGENTS_*`` environment variables point at writable temp directories
   so the engine never tries to write into the (possibly read-only) source tree.
2. The vendored package under ``backend/trading_agents`` is importable under its
   historical top-level name ``tradingagents`` via a dedicated meta-path finder.
3. A no-op stub for ``tradingagents.agents.utils.logging_config`` is installed so
   the engine skips its file-based "unified logging" setup in the web context.

This logic previously lived (duplicated) at the top of ``main.py``,
``services/analysis_service.py`` and ``services/execution/simulation.py``.
Centralising it removes the ``__import__`` / ``sys.path`` hacks scattered across
those modules.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import types

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_TRADING_AGENTS_ROOT = os.path.join(_BACKEND_DIR, "trading_agents")

_LOGGING_CONFIG_MODULE = "tradingagents.agents.utils.logging_config"


def _configure_env() -> None:
    """Point the engine's cache/results/log paths at the system temp dir."""
    tmp = tempfile.gettempdir()
    os.environ.setdefault("TRADINGAGENTS_LOG_DIR", tmp)
    os.environ.setdefault("TRADINGAGENTS_DATA_CACHE_DIR", os.path.join(tmp, "ta_cache"))
    os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", os.path.join(tmp, "ta_results"))
    os.environ.setdefault("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(tmp, "ta_memory.md"))


def _ensure_project_on_path() -> None:
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)


class _LocalTradingAgentsFinder(importlib.abc.MetaPathFinder):
    """Resolve ``tradingagents[.*]`` imports to ``backend/trading_agents``."""

    _root = _TRADING_AGENTS_ROOT

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "tradingagents" and not fullname.startswith("tradingagents."):
            return None
        base = os.path.join(self._root, *fullname.split(".")[1:])
        if os.path.isdir(base):
            init = os.path.join(base, "__init__.py")
            if os.path.isfile(init):
                return importlib.util.spec_from_file_location(
                    fullname, init, submodule_search_locations=[base],
                )
            spec = importlib.machinery.ModuleSpec(fullname, loader=None, is_package=True)
            spec.submodule_search_locations = [base]
            return spec
        pyfile = base + ".py"
        if os.path.isfile(pyfile):
            return importlib.util.spec_from_file_location(fullname, pyfile)
        return None


def _install_import_finder() -> None:
    if not any(isinstance(f, _LocalTradingAgentsFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _LocalTradingAgentsFinder())


def _install_logging_stub() -> None:
    """Pre-empt the engine's disk-based logging setup with a no-op stub."""
    if _LOGGING_CONFIG_MODULE in sys.modules:
        return
    stub = types.ModuleType(_LOGGING_CONFIG_MODULE)
    stub.setup_unified_logging = lambda: None
    sys.modules[_LOGGING_CONFIG_MODULE] = stub


_INITIALISED = False


def init() -> None:
    """Apply all bootstrap steps exactly once (safe to call repeatedly)."""
    global _INITIALISED
    if _INITIALISED:
        return
    _configure_env()
    _ensure_project_on_path()
    _install_logging_stub()
    _install_import_finder()
    _INITIALISED = True


# Apply on import so a bare ``import backend.bootstrap`` is enough.
init()
