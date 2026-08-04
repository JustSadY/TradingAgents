from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass
class AnalystRegistration:
    key: str
    agent_node: str
    clear_node: str
    tool_node: str
    report_key: str
    factory: Callable
    tools: list


_REGISTRY: dict[str, AnalystRegistration] = {}


def register_analyst(
    key: str,
    agent_node: str,
    clear_node: str,
    tool_node: str,
    report_key: str,
    tools: list,
):
    def decorator(factory_fn: Callable) -> Callable:
        reg = AnalystRegistration(
            key=key,
            agent_node=agent_node,
            clear_node=clear_node,
            tool_node=tool_node,
            report_key=report_key,
            factory=factory_fn,
            tools=list(tools),
        )
        _REGISTRY[key] = reg
        _logger.debug("Registered analyst: key=%r agent_node=%r", key, agent_node)
        return factory_fn

    return decorator


def sync_registry_to_graph() -> None:
    from backend.trading_agents.agents.runtime.analyst_execution import ANALYST_NODE_SPECS, AnalystNodeSpec
    from backend.trading_agents.graph.conditional_logic import ConditionalLogic

    for reg in _REGISTRY.values():
        if reg.key not in ANALYST_NODE_SPECS:
            ANALYST_NODE_SPECS[reg.key] = AnalystNodeSpec(
                key=reg.key,
                agent_node=reg.agent_node,
                clear_node=reg.clear_node,
                tool_node=reg.tool_node,
                report_key=reg.report_key,
            )
        method_name = f"should_continue_{reg.key}"
        if not hasattr(ConditionalLogic, method_name):
            _tn = reg.tool_node
            _cn = reg.clear_node

            def _condition(self, state, _tool_node=_tn, _clear_node=_cn):
                msgs = state["messages"]
                last = msgs[-1]
                if not (hasattr(last, "tool_calls") and last.tool_calls):
                    return _clear_node

                # Always execute a pending tool call.  The shared analyst runner
                # counts completed tool turns and performs the next pass with a
                # tool-free LLM once the configured limit is reached.  Routing
                # directly to the clear node here used to discard gathered data
                # before a final report could be written.
                return _tool_node

            _condition.__name__ = method_name
            _condition.__doc__ = (
                f"Auto-generated router for the {reg.agent_node} node.\n"
                f"Routes to {_tn!r} when tool calls are pending, "
                f"otherwise to {_cn!r}."
            )
            setattr(ConditionalLogic, method_name, _condition)
            _logger.debug("Injected %s into ConditionalLogic", method_name)


def get_factory(key: str) -> Callable:
    reg = _REGISTRY.get(key)
    if reg is None:
        available = sorted(_REGISTRY)
        raise KeyError(
            f"Analyst {key!r} is not registered. "
            f"Available keys: {available}. "
            "Did you forget to import the analyst module?"
        )
    return reg.factory


def get_tools(key: str) -> list:
    reg = _REGISTRY.get(key)
    if reg is None:
        raise KeyError(f"Analyst {key!r} is not registered.")
    return list(reg.tools)


def list_analysts() -> list[str]:
    return sorted(_REGISTRY)


def report_key_for(key: str) -> str | None:
    """Return the report_key an analyst writes to, or ``None`` if not registered."""
    reg = _REGISTRY.get(key)
    return reg.report_key if reg else None


def analyst_key_for_report(report_key: str) -> str | None:
    """Return the registered analyst key for a report state field.

    Report fields are presentation names, not guaranteed to be the same as
    the runtime agent key: ``sentiment_report`` belongs to the ``social``
    analyst. Runtime policy (LLM overrides, tool access, telemetry) must use
    the registered key rather than guessing from the field name.
    """
    for key, reg in _REGISTRY.items():
        if reg.report_key == report_key:
            return key
    return None


def all_report_keys() -> tuple[str, ...]:
    """Every registered analyst's report key, in registration order.

    Single source of truth for "which analyst report fields exist", so callers
    never have to hardcode (and drift out of sync with) the analyst roster.
    """
    return tuple(reg.report_key for reg in _REGISTRY.values())


def get_report_fields() -> dict[str, str]:
    """Return a mapping of report_key to the analyst's human-readable label."""
    from backend.trading_agents.agent_catalog import label_for

    return {reg.report_key: label_for(reg.key) for reg in _REGISTRY.values()}
