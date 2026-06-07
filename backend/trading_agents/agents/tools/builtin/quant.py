from backend.trading_agents.agents.data.quant_tools import get_quant_data
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

quant_tool = FunctionToolAdapter(
    key="quant_data",
    category="quant",
    label_key="tools.quant_data.label",
    description_key="tools.quant_data.description",
    func=get_quant_data,
    allowed_analysts=["quant"],
    default_enabled=True,
)

registry.register(quant_tool)
