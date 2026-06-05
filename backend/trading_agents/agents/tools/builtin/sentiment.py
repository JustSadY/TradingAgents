from backend.trading_agents.dataflows.interface import route_to_vendor
from backend.trading_agents.agents.tools.base import ToolSettingField
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

def route_reddit_posts(*args, **kwargs):
    return route_to_vendor("fetch_reddit_posts", *args, **kwargs)

def route_stocktwits_messages(*args, **kwargs):
    return route_to_vendor("fetch_stocktwits_messages", *args, **kwargs)

reddit_sentiment_tool = FunctionToolAdapter(
    key="reddit_sentiment",
    category="sentiment",
    label_key="tools.reddit_sentiment.label",
    description_key="tools.reddit_sentiment.description",
    func=route_reddit_posts,
    allowed_analysts=["social"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="limit",
            type="number",
            scope="user",
            label_key="tools.reddit_sentiment.limit",
            default=20.0,
            min=1.0,
            max=100.0,
        ),
        ToolSettingField(
            key="reddit_client_id",
            type="string",
            scope="user",
            label_key="tools.reddit_sentiment.client_id",
            default="",
        ),
        ToolSettingField(
            key="reddit_client_secret",
            type="secret",
            scope="user",
            label_key="tools.reddit_sentiment.client_secret",
            default="",
        ),
        ToolSettingField(
            key="reddit_user_agent",
            type="string",
            scope="user",
            label_key="tools.reddit_sentiment.user_agent",
            default="TradingAgents/1.0",
        ),
    ],
    langchain_tool_names=["fetch_reddit_posts"],
)

stocktwits_sentiment_tool = FunctionToolAdapter(
    key="stocktwits_sentiment",
    category="sentiment",
    label_key="tools.stocktwits_sentiment.label",
    description_key="tools.stocktwits_sentiment.description",
    func=route_stocktwits_messages,
    allowed_analysts=["social"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="limit",
            type="number",
            scope="user",
            label_key="tools.stocktwits_sentiment.limit",
            default=30.0,
            min=5.0,
            max=100.0,
        )
    ],
    langchain_tool_names=["fetch_stocktwits_messages"],
)

registry.register(reddit_sentiment_tool)
registry.register(stocktwits_sentiment_tool)
