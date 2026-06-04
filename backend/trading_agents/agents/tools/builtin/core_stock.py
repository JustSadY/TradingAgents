from backend.trading_agents.agents.utils.core_stock_tools import get_stock_data
from backend.trading_agents.agents.tools.base import ToolSettingField
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

core_stock_tool = FunctionToolAdapter(
    key="core_stock_data",
    category="market",
    label_key="tools.core_stock_data.label",
    description_key="tools.core_stock_data.description",
    func=get_stock_data,
    allowed_analysts=["market", "portfolio_manager"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="default_lookback_days",
            type="number",
            scope="server",
            label_key="tools.core_stock_data.default_lookback_days",
            default=365.0,
            min=30.0,
            max=1825.0,
        )
    ],
)

registry.register(core_stock_tool)
