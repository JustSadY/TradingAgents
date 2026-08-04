from backend.trading_agents.agents.data.ownership_tools import (
    get_analyst_ratings,
    get_catalyst_calendar,
    get_institutional_holdings,
    get_short_interest,
    get_valuation_comparison,
)
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

institutional_holdings_tool = FunctionToolAdapter(
    key="institutional_holdings",
    temporal_semantics="live_only",
    category="news",
    label_key="tools.institutional_holdings.label",
    description_key="tools.institutional_holdings.description",
    func=get_institutional_holdings,
    allowed_analysts=["ownership", "fundamentals"],
    default_enabled=True,
)

catalyst_calendar_tool = FunctionToolAdapter(
    key="catalyst_calendar",
    temporal_semantics="live_only",
    category="news",
    label_key="tools.catalyst_calendar.label",
    description_key="tools.catalyst_calendar.description",
    func=get_catalyst_calendar,
    allowed_analysts=["catalyst", "earnings"],
    default_enabled=True,
)

analyst_ratings_tool = FunctionToolAdapter(
    key="analyst_ratings",
    temporal_semantics="live_only",
    category="news",
    label_key="tools.analyst_ratings.label",
    description_key="tools.analyst_ratings.description",
    func=get_analyst_ratings,
    allowed_analysts=["ratings"],
    default_enabled=True,
)

short_interest_tool = FunctionToolAdapter(
    key="short_interest",
    temporal_semantics="live_only",
    category="news",
    label_key="tools.short_interest.label",
    description_key="tools.short_interest.description",
    func=get_short_interest,
    allowed_analysts=["short_interest"],
    default_enabled=True,
)

valuation_comparison_tool = FunctionToolAdapter(
    key="valuation_comparison",
    temporal_semantics="live_only",
    category="fundamentals",
    label_key="tools.valuation_comparison.label",
    description_key="tools.valuation_comparison.description",
    func=get_valuation_comparison,
    allowed_analysts=["valuation"],
    default_enabled=True,
)

registry.register(institutional_holdings_tool)
registry.register(catalyst_calendar_tool)
registry.register(analyst_ratings_tool)
registry.register(short_interest_tool)
registry.register(valuation_comparison_tool)
