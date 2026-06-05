"""
Tier-3 data layer — the concrete data-fetch / computation implementations that
back the registered tools (yFinance, SEC, news, options, macro, quant,
backtests, charting, web search).

The ``tools/`` package wraps these in permission-aware ``BaseAgentTool`` objects;
``utils/agent_utils.py`` re-exports the LangChain tool callables. Sub-agents
reach them only through the tool registry, never directly.
"""
