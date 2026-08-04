from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.data.review_tools import get_past_performance_data
from backend.trading_agents.agents.data.search_tools import get_crypto_fear_and_greed_index, search_web
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.base import ToolSettingField
from backend.trading_agents.agents.tools.registry import registry

strategy_backtest_tool = FunctionToolAdapter(
    key="strategy_backtest",
    temporal_semantics="point_in_time",
    category="backtest",
    label_key="tools.strategy_backtest.label",
    description_key="tools.strategy_backtest.description",
    func=run_strategy_backtest,
    allowed_analysts=["review", "earnings", "market"],
    default_enabled=True,
)

search_web_tool = FunctionToolAdapter(
    key="search_web",
    temporal_semantics="date_bounded",
    category="market",
    label_key="tools.search_web.label",
    description_key="tools.search_web.description",
    func=search_web,
    allowed_analysts=["market", "news", "macro", "earnings"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="searxng_url",
            type="string",
            scope="user",
            label_key="tools.search_web.searxng_url",
            default="http://localhost:8080",
        )
    ],
)

crypto_fear_greed_tool = FunctionToolAdapter(
    key="crypto_fear_greed",
    temporal_semantics="live_only",
    category="sentiment",
    label_key="tools.crypto_fear_greed.label",
    description_key="tools.crypto_fear_greed.description",
    func=get_crypto_fear_and_greed_index,
    allowed_analysts=["social", "news"],
    default_enabled=True,
)

past_performance_tool = FunctionToolAdapter(
    key="past_performance",
    temporal_semantics="point_in_time",
    category="backtest",
    label_key="tools.past_performance.label",
    description_key="tools.past_performance.description",
    func=get_past_performance_data,
    allowed_analysts=["review"],
    default_enabled=True,
)

registry.register(strategy_backtest_tool)
registry.register(search_web_tool)
registry.register(crypto_fear_greed_tool)
registry.register(past_performance_tool)
