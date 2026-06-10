from backend.trading_agents.agents.data.ownership_tools import get_institutional_holdings
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

institutional_holdings_tool = FunctionToolAdapter(
    key="institutional_holdings",
    category="news",
    label_key="tools.institutional_holdings.label",
    description_key="tools.institutional_holdings.description",
    func=get_institutional_holdings,
    allowed_analysts=["ownership", "fundamentals"],
    default_enabled=True,
)

registry.register(institutional_holdings_tool)
