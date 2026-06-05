"""
Tier-1 Main Agents — one LangGraph node each.

Every main node:
  1. checks its own kill-switch via the hierarchy and short-circuits when off
     (no sub-agent or tool is touched → zero tokens),
  2. resolves and runs its permitted sub-agents (reusing the existing Tier-2
     node factories),
  3. aggregates the sub-agent outputs into the shared AgentState.

The top-level graph (see ``graph/setup.py``) wires these linearly:
    START → Market Intelligence → Research Manager → Trader
          → Risk Debate → Portfolio Manager → END
"""
from .market_intelligence import create_market_intelligence_node
from .research import create_research_manager_node
from .trade_execution import create_trader_node
from .risk import create_risk_debate_node
from .portfolio import create_portfolio_manager_node

__all__ = [
    "create_market_intelligence_node",
    "create_research_manager_node",
    "create_trader_node",
    "create_risk_debate_node",
    "create_portfolio_manager_node",
]
