"""
Tier-3 data layer — concrete data-fetch and computation implementations that
back registered tools (yFinance, SEC, news, options, macro, quant, backtests,
charting, web search).

The ``tools/`` package wraps permission-sensitive capabilities in
``BaseAgentTool`` objects and ``utils/agent_utils.py`` re-exports commonly used
LangChain callables. Analyst implementations may also import Tier-3 helpers
directly when they are composing their declared tool set or deterministic data
preparation; permission enforcement remains the responsibility of the runtime
tool registry and analyst execution path.
"""
