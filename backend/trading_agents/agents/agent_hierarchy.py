"""Backward-compatible shim.

The hierarchy implementation now lives in :mod:`hierarchy`. This module is kept
so existing imports (``from backend.trading_agents.agents.agent_hierarchy import
AgentHierarchy``) keep working.
"""
from backend.trading_agents.agents.hierarchy import AgentHierarchy, MAIN_AGENT_KEYS

__all__ = ["AgentHierarchy", "MAIN_AGENT_KEYS"]
