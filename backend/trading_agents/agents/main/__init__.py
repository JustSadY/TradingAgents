"""
Tier-1 Main Agents — one LangGraph node each.

Every main node:
  1. checks its own kill-switch via the hierarchy and short-circuits when off
     (no sub-agent or tool is touched → zero tokens),
  2. resolves and runs its permitted sub-agents (reusing the existing Tier-2
     node factories),
  3. aggregates the sub-agent outputs into the shared AgentState.

The top-level graph (see ``graph/setup.py``) is strategy-aware and wires these
stages linearly:
    START → Strategy Context Loader → Analysis Planner → Market Intelligence
          → Agent Q&A → Research Manager → Risk Debate → Strategy Reconciler
          → Portfolio Manager → Decision Stability Controller → END

Portfolio Manager produces the raw AI trade proposal. The deterministic
Decision Stability Controller is the final graph stage and decides which
proposal becomes canonical when enforcement applies.
"""

from .agent_qa import create_agent_qa_node
from .analysis_planner import create_analysis_planner_node
from .decision_stability import create_decision_stability_controller_node
from .market_intelligence import create_market_intelligence_node
from .portfolio import create_portfolio_manager_node
from .research import create_research_manager_node
from .risk import create_risk_debate_node
from .strategy_reconciler import create_strategy_reconciler_node

__all__ = [
    "create_analysis_planner_node",
    "create_decision_stability_controller_node",
    "create_market_intelligence_node",
    "create_agent_qa_node",
    "create_research_manager_node",
    "create_risk_debate_node",
    "create_portfolio_manager_node",
    "create_strategy_reconciler_node",
]
