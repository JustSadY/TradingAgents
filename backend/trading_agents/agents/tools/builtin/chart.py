from backend.trading_agents.agents.data.chart_tools import (
    add_chart_annotation,
    add_custom_indicator,
    get_mtf_trend,
    get_vision_chart_analysis,
)
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

chart_annotation_tool = FunctionToolAdapter(
    key="chart_annotation",
    category="chart",
    label_key="tools.chart_annotation.label",
    description_key="tools.chart_annotation.description",
    func=add_chart_annotation,
    allowed_analysts=["market"],
    default_enabled=True,
)

custom_indicator_tool = FunctionToolAdapter(
    key="custom_indicator",
    category="chart",
    label_key="tools.custom_indicator.label",
    description_key="tools.custom_indicator.description",
    func=add_custom_indicator,
    allowed_analysts=["market"],
    default_enabled=True,
)

vision_chart_tool = FunctionToolAdapter(
    key="vision_chart_analysis",
    category="chart",
    label_key="tools.vision_chart_analysis.label",
    description_key="tools.vision_chart_analysis.description",
    func=get_vision_chart_analysis,
    allowed_analysts=["market"],
    default_enabled=True,
)

mtf_trend_tool = FunctionToolAdapter(
    key="mtf_trend",
    category="chart",
    label_key="tools.mtf_trend.label",
    description_key="tools.mtf_trend.description",
    func=get_mtf_trend,
    allowed_analysts=["market"],
    default_enabled=True,
)

registry.register(chart_annotation_tool)
registry.register(custom_indicator_tool)
registry.register(vision_chart_tool)
registry.register(mtf_trend_tool)
