import contextvars
import threading
from copy import deepcopy

import backend.trading_agents.default_config as default_config

# Process-global config. Acts as the default baseline and as a best-effort
# fallback for readers that run *outside* an analysis run (e.g. cron/backfill
# jobs that never call ``set_config``).
_config: dict | None = None
# Guards the module-global ``_config`` so concurrent updates cannot interleave a
# partial update with a read.
_config_lock = threading.RLock()

# Per-run config. Each analysis run calls ``set_config`` with its fully resolved
# config, stored here. ContextVars are isolated per asyncio task — and copied
# into ``asyncio.to_thread`` worker threads — so concurrent runs (e.g. the
# portfolio orchestrator fanning out tickers via ``asyncio.gather``, or several
# alert-triggered analyses) can no longer clobber each other's provider API
# keys, persona, or output language through the shared global.
_run_config: contextvars.ContextVar[dict | None] = contextvars.ContextVar("trading_agents_run_config", default=None)


def _merge_into(target: dict, incoming: dict) -> None:
    """Shallow-merge ``incoming`` into ``target``, recursing one level for
    nested dicts (matching the historical merge semantics)."""
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            target[key].update(value)
        else:
            target[key] = value


def initialize_config():
    global _config
    with _config_lock:
        if _config is None:
            _config = deepcopy(default_config.DEFAULT_CONFIG)


def set_config(config):
    if hasattr(config, "to_dict"):
        config = config.to_dict()
    incoming = deepcopy(config)

    # Build this run's config from a pristine default baseline so that any key
    # the caller omits falls back to a default rather than leaking from another
    # concurrent run's config.
    run_config = deepcopy(default_config.DEFAULT_CONFIG)
    _merge_into(run_config, incoming)
    _run_config.set(run_config)

    # Reset module-level caches that depend on config (e.g. Alpha Vantage rate
    # limiter, key rotation index). They will be re-initialized lazily on next use.
    try:
        from .alpha_vantage_common import reset_state as _av_reset

        _av_reset()
    except ImportError:
        pass

    # Keep the process-global updated as a fallback for out-of-run readers
    # (last-writer-wins, matching the previous behaviour). Merge a fresh copy:
    # reusing ``incoming`` would alias the same nested dicts into both the
    # global and this run's config, letting a later run's in-place update leak
    # into another run's supposedly isolated ContextVar config.
    with _config_lock:
        initialize_config()
        _merge_into(_config, deepcopy(incoming))


def get_config() -> dict:
    run_config = _run_config.get()
    if run_config is not None:
        return deepcopy(run_config)
    with _config_lock:
        if _config is None:
            initialize_config()
        return deepcopy(_config)


initialize_config()
