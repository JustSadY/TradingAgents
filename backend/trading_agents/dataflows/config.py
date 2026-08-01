import contextvars
import threading
from copy import deepcopy

import backend.trading_agents.default_config as default_config

_config: dict | None = None
_config_lock = threading.RLock()

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

    run_config = deepcopy(default_config.DEFAULT_CONFIG)
    _merge_into(run_config, incoming)
    _run_config.set(run_config)

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
