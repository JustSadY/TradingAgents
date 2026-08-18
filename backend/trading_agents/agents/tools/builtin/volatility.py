from backend.trading_agents.agents.data.volatility_tools import get_volatility_forecast
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.base import ToolSettingField, ToolSettingOption
from backend.trading_agents.agents.tools.registry import registry

volatility_forecast_tool = FunctionToolAdapter(
    key="volatility_forecast",
    # The fit uses only history up to the requested date, so a replay of an
    # earlier date reproduces the same forecast.
    temporal_semantics="point_in_time",
    category="quant",
    label_key="tools.volatility_forecast.label",
    description_key="tools.volatility_forecast.description",
    func=get_volatility_forecast,
    allowed_analysts=["quant", "risk_debate", "portfolio_manager"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="default_model",
            type="select",
            scope="both",
            label_key="tools.volatility_forecast.default_model",
            description_key="tools.volatility_forecast.default_model_description",
            default="tarch",
            options=[
                ToolSettingOption(value="garch", label_key="tools.volatility_forecast.model_garch"),
                ToolSettingOption(value="tarch", label_key="tools.volatility_forecast.model_tarch"),
                ToolSettingOption(value="egarch", label_key="tools.volatility_forecast.model_egarch"),
            ],
        ),
        ToolSettingField(
            key="default_horizon_days",
            type="number",
            scope="both",
            label_key="tools.volatility_forecast.default_horizon_days",
            default=10.0,
            min=1.0,
            max=60.0,
            step=1.0,
        ),
    ],
)

registry.register(volatility_forecast_tool)
