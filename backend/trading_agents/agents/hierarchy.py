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
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

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

    def __init__(self, runtime_agent_context: dict[str, Any] | None = None) -> None:
        from backend.trading_agents.agent_catalog import list_agents

        self._runtime_ctx: dict[str, Any] = runtime_agent_context or {}
        self._info: dict[str, Any] = {a.key: a for a in list_agents()}
        self._children: dict[str, list[str]] = {}
        for agent in self._info.values():
            if agent.parent_key:
                self._children.setdefault(agent.parent_key, []).append(agent.key)

    def children(self, key: str) -> list[str]:
        """Direct child keys of *key*, in catalog order."""
        return list(self._children.get(key, []))

    def parent_of(self, key: str) -> str | None:
        agent = self._info.get(key)
        return agent.parent_key if agent else None

    def _own_enabled(self, key: str) -> bool | None:
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

    def resolve_llm(
        self,
        agent_key: str,
        fallback_llm: Any,
        llm_factory: Callable[..., Any],
        *,
        _origin_key: str | None = None,
    ) -> Any:
        """
        Resolve the best LLM for *agent_key*:

          1. the agent's own settings (needs both ``llm_provider`` + ``llm_model``)
          2. the nearest ancestor with complete settings (branch default)
          3. *fallback_llm* (the global thinking LLM)

        ``llm_factory(provider, model, temperature)`` builds a client. The
        *temperature* passed is always the originally-queried agent's own
        setting (``_origin_key``, captured on the first call) — a child that
        inherits an ancestor's provider/model still gets its own temperature
        dial, instead of silently losing it while climbing the parent chain.
        """
        origin_key = _origin_key or agent_key
        state = self._runtime_ctx.get(agent_key) or {}
        settings = state.get("settings") or {}
        provider = settings.get("llm_provider")
        model = settings.get("llm_model")

        if provider and model:
            origin_state = self._runtime_ctx.get(origin_key) or {}
            origin_temperature = (origin_state.get("settings") or {}).get("temperature")
            try:
                return llm_factory(
                    provider=provider,
                    model=model,
                    temperature=origin_temperature,
                )
            except Exception as exc:
                logger.warning(
                    "Custom LLM for agent '%s' failed (%s); climbing parent chain.",
                    agent_key,
                    exc,
                )

        parent = self.parent_of(agent_key)
        if parent:
            return self.resolve_llm(parent, fallback_llm, llm_factory, _origin_key=origin_key)

        if agent_key != "portfolio_manager":
            return self.resolve_llm("portfolio_manager", fallback_llm, llm_factory, _origin_key=origin_key)

        return fallback_llm

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
            return True
        return any(self.is_enabled(a) for a in allowed)
