from backend.trading_agents.agents.data.macro_tools import get_macro_data
from backend.trading_agents.agents.tools.base import ToolSettingField
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

macro_tool = FunctionToolAdapter(
    key="macro_data",
    category="macro",
    label_key="tools.macro_data.label",
    description_key="tools.macro_data.description",
    func=get_macro_data,
    allowed_analysts=["macro"],
    default_enabled=True,
)

registry.register(macro_tool)
