from backend.trading_agents.agents.data.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from backend.trading_agents.agents.data.sec_tools import (
    get_insider_transactions_deep,
    get_sec_filings,
)
from backend.trading_agents.agents.tools.adapters import FunctionToolAdapter
from backend.trading_agents.agents.tools.registry import registry

fundamentals_tool = FunctionToolAdapter(
    key="fundamentals_data",
    temporal_semantics="live_only",
    category="fundamentals",
    label_key="tools.fundamentals_data.label",
    description_key="tools.fundamentals_data.description",
    func=get_fundamentals,
    allowed_analysts=["fundamentals"],
    default_enabled=True,
)

balance_sheet_tool = FunctionToolAdapter(
    key="balance_sheet",
    temporal_semantics="date_bounded",
    category="fundamentals",
    label_key="tools.balance_sheet.label",
    description_key="tools.balance_sheet.description",
    func=get_balance_sheet,
    allowed_analysts=["fundamentals"],
    default_enabled=True,
)

cashflow_tool = FunctionToolAdapter(
    key="cashflow",
    temporal_semantics="date_bounded",
    category="fundamentals",
    label_key="tools.cashflow.label",
    description_key="tools.cashflow.description",
    func=get_cashflow,
    allowed_analysts=["fundamentals"],
    default_enabled=True,
)

income_statement_tool = FunctionToolAdapter(
    key="income_statement",
    temporal_semantics="date_bounded",
    category="fundamentals",
    label_key="tools.income_statement.label",
    description_key="tools.income_statement.description",
    func=get_income_statement,
    allowed_analysts=["fundamentals"],
    default_enabled=True,
)

sec_filings_tool = FunctionToolAdapter(
    key="sec_filings",
    temporal_semantics="live_only",
    category="fundamentals",
    label_key="tools.sec_filings.label",
    description_key="tools.sec_filings.description",
    func=get_sec_filings,
    allowed_analysts=["fundamentals"],
    default_enabled=True,
)

insider_transactions_deep_tool = FunctionToolAdapter(
    key="insider_transactions_deep",
    temporal_semantics="live_only",
    category="fundamentals",
    label_key="tools.insider_transactions_deep.label",
    description_key="tools.insider_transactions_deep.description",
    func=get_insider_transactions_deep,
    allowed_analysts=["fundamentals"],
    default_enabled=True,
)

registry.register(fundamentals_tool)
registry.register(balance_sheet_tool)
registry.register(cashflow_tool)
registry.register(income_statement_tool)
registry.register(sec_filings_tool)
registry.register(insider_transactions_deep_tool)
