from copy import deepcopy
from typing import Dict, Optional
import tradingagents.default_config as default_config
_config: Optional[Dict] = None
def initialize_config():
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)
def set_config(config):
    global _config
    initialize_config()
    if hasattr(config, "to_dict"):
        config = config.to_dict()
    incoming = deepcopy(config)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(_config.get(key), dict):
            _config[key].update(value)
        else:
            _config[key] = value
def get_config() -> Dict:
    if _config is None:
        initialize_config()
    return deepcopy(_config)
initialize_config()
