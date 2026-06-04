from backend.trading_agents.agents.utils.news_data_tools import get_news, get_global_news, get_insider_transactions
from backend.trading_agents.agents.tools.base import ToolSettingField
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

company_news_tool = FunctionToolAdapter(
    key="company_news",
    category="news",
    label_key="tools.company_news.label",
    description_key="tools.company_news.description",
    func=get_news,
    allowed_analysts=["news", "sentiment"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="article_limit",
            type="number",
            scope="user",
            label_key="tools.company_news.article_limit",
            default=20.0,
            min=5.0,
            max=50.0,
        )
    ],
)

global_news_tool = FunctionToolAdapter(
    key="global_news",
    category="news",
    label_key="tools.global_news.label",
    description_key="tools.global_news.description",
    func=get_global_news,
    allowed_analysts=["news", "macro"],
    default_enabled=True,
    settings_schema=[
        ToolSettingField(
            key="article_limit",
            type="number",
            scope="user",
            label_key="tools.global_news.article_limit",
            default=10.0,
            min=3.0,
            max=30.0,
        ),
        ToolSettingField(
            key="lookback_days",
            type="number",
            scope="user",
            label_key="tools.global_news.lookback_days",
            default=7.0,
            min=1.0,
            max=30.0,
        ),
    ],
)

insider_transactions_tool = FunctionToolAdapter(
    key="insider_transactions",
    category="news",
    label_key="tools.insider_transactions.label",
    description_key="tools.insider_transactions.description",
    func=get_insider_transactions,
    allowed_analysts=["news", "fundamentals"],
    default_enabled=True,
)

registry.register(company_news_tool)
registry.register(global_news_tool)
registry.register(insider_transactions_tool)
