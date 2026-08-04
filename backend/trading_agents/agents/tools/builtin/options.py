from backend.trading_agents.agents.data.options_tools import get_options_data
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

options_tool = FunctionToolAdapter(
    key="options_data",
    temporal_semantics="live_only",
    category="options",
    label_key="tools.options_data.label",
    description_key="tools.options_data.description",
    func=get_options_data,
    allowed_analysts=["options"],
    default_enabled=True,
)

registry.register(options_tool)
