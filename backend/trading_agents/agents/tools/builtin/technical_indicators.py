from backend.trading_agents.agents.utils.technical_indicators_tools import get_indicators
from backend.trading_agents.agents.tools.base import ToolSettingField
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

technical_indicators_tool = FunctionToolAdapter(
    key="technical_indicators",
    category="market",
    label_key="tools.technical_indicators.label",
    description_key="tools.technical_indicators.description",
    func=get_indicators,
    allowed_analysts=["market", "portfolio_manager"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="default_lookback_days",
            type="number",
            scope="server",
            label_key="tools.technical_indicators.default_lookback_days",
            default=30.0,
            min=5.0,
            max=365.0,
        )
    ],
)

registry.register(technical_indicators_tool)
