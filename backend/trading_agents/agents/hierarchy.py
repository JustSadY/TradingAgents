"""
Single source of truth for the 3-tier agent hierarchy.

  Tier 1 — Main Agents : one LangGraph node each. They own a branch of the
                         tree and orchestrate their sub-agents.
  Tier 2 — Sub-Agents  : reasoning units invoked *inside* a Main Agent node.
                         Not graph nodes themselves.
  Tier 3 — Tools       : LangChain tools (the `BaseAgentTool` registry).
                         Reachable only through an enabled sub-agent that sits
                         under an enabled main agent.

The tree itself (parent → child links, default-enabled flags, per-agent LLM
settings schema) lives in ``agent_catalog.AGENTS``. This module reads that
catalog and layers the runtime semantics on top:

  • Cascading kill-switch   — ``is_enabled`` walks the whole parent chain, so
    disabling a Main Agent transparently disables every descendant sub-agent
    and makes their tools unreachable. Zero tokens are spent on a dead branch.

  • Recursive LLM fallback  — ``resolve_llm`` climbs the parent chain until it
    finds an ancestor that declares an explicit provider+model, letting a
    branch-level default cascade down to its sub-agents.

  • Tool reachability       — ``tool_is_reachable`` answers "can ANY live
    sub-agent still call this tool?", which the graph uses to strip tools off
    disabled branches.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier-1 branch roots. These are the agents the backend checks access for
# *first*; everything else hangs beneath one of them.
# ---------------------------------------------------------------------------

MAIN_AGENT_KEYS: frozenset[str] = frozenset({
    "portfolio_manager",     # root / final decision maker
    "market_intelligence",   # owns the analyst sub-agents
    "research_manager",      # owns synthesis + bull/bear debate + auditor
    "trader",                # owns the execution planner
    "risk_debate",           # owns the aggressive/neutral/conservative debate
})


class AgentHierarchy:
    """
    Parent → child registry with cascading enable checks, recursive LLM
    resolution and tool-reachability queries.

    Parameters
    ----------
    runtime_agent_context:
        Dict keyed by ``agent_key``::

            {
              "market": {
                "enabled": True | False | None,
                "settings": {"llm_provider": ..., "llm_model": ...,
                             "temperature": ..., "system_instruction": ...},
              },
              ...
            }

        A missing entry or ``enabled: None`` falls back to the catalog's
        ``default_enabled`` for that agent.
    """

    def __init__(self, runtime_agent_context: Dict[str, Any] | None = None) -> None:
        from backend.trading_agents.agent_catalog import list_agents

        self._runtime_ctx: Dict[str, Any] = runtime_agent_context or {}
        self._info: Dict[str, Any] = {a.key: a for a in list_agents()}
        self._children: Dict[str, List[str]] = {}
        for agent in self._info.values():
            if agent.parent_key:
                self._children.setdefault(agent.parent_key, []).append(agent.key)

    # ------------------------------------------------------------------
    # Tree traversal
    # ------------------------------------------------------------------

    def children(self, key: str) -> List[str]:
        """Direct child keys of *key*, in catalog order."""
        return list(self._children.get(key, []))

    def descendants(self, key: str) -> List[str]:
        """All recursive descendant keys of *key* (breadth-first)."""
        out: List[str] = []
        queue = list(self._children.get(key, []))
        while queue:
            child = queue.pop(0)
            out.append(child)
            queue.extend(self._children.get(child, []))
        return out

    def parent_of(self, key: str) -> Optional[str]:
        agent = self._info.get(key)
        return agent.parent_key if agent else None

    def is_main_agent(self, key: str) -> bool:
        return key in MAIN_AGENT_KEYS

    def main_agents(self) -> List[Any]:
        """AgentInfo objects for the Tier-1 agents, in catalog order."""
        return [a for a in self._info.values() if a.key in MAIN_AGENT_KEYS]

    def subagents_of(self, key: str) -> List[Any]:
        """AgentInfo objects for the direct children of *key*."""
        return [self._info[k] for k in self.children(key) if k in self._info]

    # ------------------------------------------------------------------
    # Enable / disable resolution (cascading kill-switch)
    # ------------------------------------------------------------------

    def _own_enabled(self, key: str) -> Optional[bool]:
        """Explicit enabled flag for *key*, or None when unset."""
        state = self._runtime_ctx.get(key)
        if not state:
            return None
        v = state.get("enabled")
        return None if v is None else bool(v)

    def _default_enabled(self, key: str) -> bool:
        info = self._info.get(key)
        return bool(info.default_enabled) if info else True

    def is_enabled(self, key: str) -> bool:
        """
        True only when *key* and every ancestor are enabled.

        1. own flag explicitly False               → disabled
        2. any ancestor disabled (cascading)       → disabled
        3. own flag explicitly True                → enabled
        4. own flag unset (None)                   → catalog default_enabled
        """
        if self._own_enabled(key) is False:
            return False

        parent = self.parent_of(key)
        if parent and not self.is_enabled(parent):
            return False

        own = self._own_enabled(key)
        return self._default_enabled(key) if own is None else own

    def is_branch_enabled(self, main_key: str) -> bool:
        """
        Tier-1 own-flag check for a branch root. Does NOT cascade upward
        (a main agent's own switch is what gates its branch); use
        :meth:`is_enabled` for sub-agents that must also honour ancestors.
        """
        own = self._own_enabled(main_key)
        return self._default_enabled(main_key) if own is None else own

    # ------------------------------------------------------------------
    # LLM resolution (recursive parent fallback)
    # ------------------------------------------------------------------

    def resolve_llm(
        self,
        agent_key: str,
        fallback_llm: Any,
        llm_factory: Callable[..., Any],
    ) -> Any:
        """
        Resolve the best LLM for *agent_key*:

          1. the agent's own settings (needs both ``llm_provider`` + ``llm_model``)
          2. the nearest ancestor with complete settings (branch default)
          3. *fallback_llm* (the global thinking LLM)

        ``llm_factory(provider, model, temperature)`` builds a client.
        """
        state = self._runtime_ctx.get(agent_key) or {}
        settings = state.get("settings") or {}
        provider = settings.get("llm_provider")
        model = settings.get("llm_model")

        if provider and model:
            try:
                return llm_factory(
                    provider=provider,
                    model=model,
                    temperature=settings.get("temperature"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Custom LLM for agent '%s' failed (%s); climbing parent chain.",
                    agent_key, exc,
                )

        parent = self.parent_of(agent_key)
        if parent:
            return self.resolve_llm(parent, fallback_llm, llm_factory)
        return fallback_llm

    def get_effective_settings(self, key: str) -> Dict[str, Any]:
        """Resolved settings for *key*, filling gaps from the parent chain."""
        state = self._runtime_ctx.get(key) or {}
        settings = dict(state.get("settings") or {})
        parent = self.parent_of(key)
        if parent:
            for k, v in self.get_effective_settings(parent).items():
                if settings.get(k) is None:
                    settings[k] = v
        return settings

    # ------------------------------------------------------------------
    # Tool reachability (Tier-3 gating)
    # ------------------------------------------------------------------

    def tool_is_reachable(self, agent_tool_key: str) -> bool:
        """
        True if at least one *enabled* agent is permitted to call the tool.

        A tool registered against ``allowed_analysts=[...]`` is reachable only
        while one of those agents is still live. When the owning branch is
        switched off, every one of its tools becomes unreachable — exactly the
        "disable the top branch and its tools close" behaviour.
        """
        from backend.trading_agents.agents.tools.registry import registry

        tool = registry.get(agent_tool_key)
        if not tool:
            return False
        allowed = tool.allowed_analysts or []
        if not allowed:
            # Tools with no analyst restriction are always reachable.
            return True
        return any(self.is_enabled(a) for a in allowed)
