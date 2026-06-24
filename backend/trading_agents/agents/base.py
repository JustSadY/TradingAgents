"""
Shared contracts for the 3-tier agent model.

A **Main Agent** is realised as a LangGraph node: ``Callable[[state], dict]``.
A **Sub-Agent** is realised as a plain runner invoked inside a main node:
``Callable[[state], dict]`` returning a partial state update.

These are intentionally lightweight (protocols + a shared run-context dataclass
+ a couple of helpers) — the heavy lifting lives in the concrete ``main/``
modules, which reuse the existing Tier-2 node factories.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

# A node/runner is just "state in → partial-state-update out".
StateUpdate = dict[str, Any]
NodeFn = Callable[[dict], StateUpdate]


class MainAgentNode(Protocol):
    """A Tier-1 main agent: one graph node that orchestrates its sub-agents."""

    def __call__(self, state: dict) -> StateUpdate: ...


class SubAgentRunner(Protocol):
    """A Tier-2 sub-agent runner invoked inside a main node."""

    def __call__(self, state: dict) -> StateUpdate: ...


@dataclass
class AgentRunContext:
    """
    Everything a main-agent node needs to orchestrate its branch.

    Built once by :class:`GraphSetup` and shared (read-only) across all main
    nodes.
    """

    hierarchy: Any  # AgentHierarchy
    llms: dict[str, Any]  # agent_key → resolved LLM
    fallback_llm: Any  # global thinking LLM
    tool_nodes: dict[str, Any]  # analyst_key → ToolNode
    conditional_logic: Any  # ConditionalLogic
    config: dict[str, Any]  # the run config dict
    selected_analysts: list[str]  # permitted + selected analyst keys

    def llm_for(self, key: str) -> Any:
        """Resolved LLM for *key*, falling back to the global thinking LLM."""
        return self.llms.get(key, self.fallback_llm)

    def is_enabled(self, key: str) -> bool:
        return self.hierarchy.is_enabled(key)

    def is_branch_enabled(self, key: str) -> bool:
        return self.hierarchy.is_branch_enabled(key)


def neutral_invest_debate_state(note: str = "") -> dict:
    """A valid-but-empty InvestDebateState (used by kill-switch stubs)."""
    return {
        "bull_history": "",
        "bear_history": "",
        "history": "",
        "current_response": "",
        "judge_decision": note,
        "count": 0,
    }


def neutral_risk_debate_state(note: str = "") -> dict:
    """A valid-but-empty RiskDebateState (used by kill-switch stubs)."""
    return {
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "history": "",
        "latest_speaker": "",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        "judge_decision": note,
        "count": 0,
    }
