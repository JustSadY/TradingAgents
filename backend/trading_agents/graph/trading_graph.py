import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
from langgraph.prebuilt import ToolNode

from backend.core.utils import safe_ticker_component
from backend.trading_agents.agents.data.chart_tools import active_run_context
from backend.trading_agents.agents.hierarchy import AgentHierarchy
from backend.trading_agents.dataflows.config import set_config
from backend.trading_agents.default_config import DEFAULT_CONFIG
from backend.trading_agents.llm_clients import create_llm_client

from .checkpointer import (
    async_checkpoint_step,
    checkpoint_step,
    clear_checkpoint,
    get_async_checkpointer,
    get_checkpointer,
    thread_id,
)
from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .setup import GraphSetup
from .signal_processing import SignalProcessor


def _cap_tool_outputs(tool_node: ToolNode, max_chars: int):
    """Wrap a ToolNode so oversized tool results are middle-truncated before
    they enter the analyst's conversation, and a hard timeout prevents a hung
    external API from stalling the run.

    Every tool result stays in the message list and is re-sent on each LLM
    round-trip within the analyst's run, so one unbounded CSV dump multiplies
    across turns. Middle truncation keeps the head (CSV headers/context) and
    the tail (most recent rows) — see ``middle_truncate``."""

    async def _run(state, *args, **kwargs):
        import asyncio

        from backend.trading_agents.agents.runtime.report_aggregator import middle_truncate
        from backend.trading_agents.dataflows.config import get_config

        _cfg = get_config()
        timeout = _cfg.get("tool_timeout_seconds", 60)
        try:
            result = await asyncio.wait_for(tool_node.ainvoke(state, *args, **kwargs), timeout=timeout)
        except TimeoutError:
            from backend.trading_agents.agents.runtime.resilience import log_event

            log_event("tool_timeout", level=logging.WARNING, tool=tool_node.name if hasattr(tool_node, "name") else str(tool_node))
            return {"messages": [{"role": "tool", "content": f"Tool timed out after {timeout}s. Try a simpler query."}]}
        messages = result.get("messages", []) if isinstance(result, dict) else []
        for message in messages:
            content = getattr(message, "content", None)
            if isinstance(content, str) and len(content) > max_chars:
                message.content = middle_truncate(content, max_chars)
        return result

    return _run


class TradingAgentsGraph:
    def __init__(
        self,
        selected_analysts=None,
        debug=False,
        config: dict[str, Any] = None,
        callbacks: list | None = None,
    ):
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        set_config(self.config)
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # ------------------------------------------------------------------
        # Build the agent hierarchy from runtime context
        # ------------------------------------------------------------------
        runtime_agent_ctx = self.config.get("runtime_agent_context") or {}
        self.hierarchy = AgentHierarchy(runtime_agent_ctx)

        self._init_llms(runtime_agent_ctx)

        # ------------------------------------------------------------------
        # Filter selected analysts using hierarchy enable state.
        # is_enabled() cascades through market_intelligence → portfolio_manager,
        # so disabling either branch transparently drops every analyst.
        # ------------------------------------------------------------------
        _effective_analysts = [k for k in selected_analysts if self.hierarchy.is_enabled(k)]
        skipped = set(selected_analysts) - set(_effective_analysts)
        if skipped:
            logger.info(
                "The following analysts are disabled by hierarchy and will be skipped: %s",
                sorted(skipped),
            )

        self.tool_nodes = self._create_tool_nodes()
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
            analyst_concurrency_limit=self.config.get("analyst_concurrency_limit", 1),
            agent_llms=self.agent_llms,
            agent_hierarchy=self.hierarchy,
            config=self.config,
        )
        self.propagator = Propagator(max_recur_limit=self.config.get("max_recur_limit", 100))
        self.signal_processor = SignalProcessor(self.thinking_llm)
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}
        self.workflow = self.graph_setup.setup_graph(_effective_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _init_llms(self, runtime_agent_ctx: dict):
        # Resolve the Master (Portfolio Manager) LLM to use as thinking_llm
        pm_state = runtime_agent_ctx.get("portfolio_manager") or {}
        pm_settings = pm_state.get("settings") or {}

        main_prov = pm_settings.get("llm_provider") or self.config.get("llm_provider") or "openai"
        main_model = pm_settings.get("llm_model") or self.config.get("llm_model") or "gpt-4o-mini"
        self.llm_provider = main_prov
        self.llm_model = main_model

        main_kwargs = self._get_provider_kwargs(main_prov)
        if self.callbacks:
            main_kwargs["callbacks"] = self.callbacks

        # Merge PM-specific settings into main_kwargs if they exist
        if pm_settings.get("temperature") is not None:
            main_kwargs["temperature"] = float(pm_settings["temperature"])

        client = create_llm_client(
            provider=main_prov,
            model=main_model,
            **main_kwargs,
        )
        main_llm = self._with_fallback(client.get_llm(), main_prov, main_model)
        self.thinking_llm = main_llm.with_config(tags=["portfolio_manager"], metadata={"agent": "portfolio_manager"})

        # LLM factory used by the hierarchy for recursive resolution
        def _make_llm(provider: str, model: str, temperature=None) -> Any:
            prov_lower = provider.lower()
            kwargs = self._get_provider_kwargs(prov_lower)
            if temperature is not None:
                kwargs["temperature"] = float(temperature)
            if self.callbacks:
                kwargs["callbacks"] = self.callbacks
            c = create_llm_client(
                provider=prov_lower,
                model=model,
                **kwargs,
            )
            return self._with_fallback(c.get_llm(), prov_lower, model, temperature)

        # Resolve per-agent LLMs via hierarchy (supports parent fallback)
        from backend.trading_agents.agent_catalog import list_agents

        self.agent_llms: dict[str, Any] = {}
        for agent_info in list_agents():
            key = agent_info.key
            try:
                resolved = self.hierarchy.resolve_llm(key, self.thinking_llm, _make_llm)
                self.agent_llms[key] = resolved.with_config(tags=[key], metadata={"agent": key})
            except Exception as e:
                logger.warning("LLM resolution failed for agent '%s': %s – using global LLM.", key, e)
                self.agent_llms[key] = self.thinking_llm.with_config(tags=[key], metadata={"agent": key})

    def _with_fallback(self, llm, provider: str, model: str, temperature=None):
        """Wrap *llm* with the user's opt-in fallback chain.

        Reads ``fallback_llm_chain`` (a list of ``{"provider": ..., "model":
        ...}`` dicts) from config. Falls back to the legacy single
        ``fallback_llm_provider`` / ``fallback_llm_model`` keys when the new
        structured field is absent. Failure to build a fallback never blocks
        the run — entries that fail are silently dropped, and if nothing can be
        built the primary is returned unwrapped.
        """
        from backend.trading_agents.llm_clients.fallback import FallbackLLM

        # Resolve the fallback list from config, supporting both the new
        # structured chain and the legacy single-fallback keys.
        chain: list[dict] = self.config.get("fallback_llm_chain", [])
        if not chain:
            fb_prov = (self.config.get("fallback_llm_provider") or "").strip().lower()
            fb_model = (self.config.get("fallback_llm_model") or "").strip()
            if fb_prov and fb_model:
                chain = [{"provider": fb_prov, "model": fb_model}]
            else:
                return llm

        fallbacks = []
        for entry in chain:
            prov = entry.get("provider", "").strip().lower()
            mod = entry.get("model", "").strip()
            if not prov or not mod:
                continue
            if prov == (provider or "").lower() and mod == model:
                continue  # skip if same as primary to avoid pointless failover
            try:
                kwargs = self._get_provider_kwargs(prov)
                if temperature is not None:
                    kwargs["temperature"] = float(temperature)
                if self.callbacks:
                    kwargs["callbacks"] = self.callbacks
                fb = create_llm_client(provider=prov, model=mod, **kwargs).get_llm()
                fallbacks.append(fb)
            except Exception as exc:
                logger.warning("Fallback LLM %s/%s unavailable: %s — dropped from chain.", prov, mod, exc)

        if not fallbacks:
            return llm
        return FallbackLLM(llm, fallbacks)

    def _get_provider_kwargs(self, provider: str = None) -> dict[str, Any]:
        kwargs = {}
        prov_lower = (provider or self.config.get("llm_provider", "")).lower()
        if prov_lower == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level
        elif prov_lower == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
        elif prov_lower == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort
            kwargs["prompt_caching"] = bool(self.config.get("anthropic_prompt_caching", True))
        user_keys = self.config.get("user_api_keys") or {}
        user_key = user_keys.get(prov_lower)
        if user_key:
            kwargs["api_key"] = user_key
        elif self.config.get("api_key") and prov_lower == self.config.get("llm_provider", "").lower():
            kwargs["api_key"] = self.config["api_key"]
        return kwargs

    def _filter_tools_for_analyst(self, _analyst_key: str, raw_tools: list) -> list:
        runtime_ctx = self.config.get("runtime_tool_context")
        if not runtime_ctx:
            return raw_tools

        from backend.trading_agents.agents.tools.registry import registry

        filtered = []
        for tool_func in raw_tools:
            tool_name = tool_func.name if hasattr(tool_func, "name") else tool_func.__name__
            agent_tool_key = registry.get_agent_tool_key_for_langchain_tool(tool_name)

            if self._should_include_tool(agent_tool_key, tool_func, runtime_ctx):
                filtered.append(tool_func)

        return filtered

    def _should_include_tool(self, tool_key: str | None, _tool_func: Any, runtime_ctx: dict) -> bool:
        """Helper to determine if a tool should be included for an analyst."""
        if tool_key is None:
            return True

        from backend.trading_agents.agents.tools.registry import registry

        agent_tool = registry.get(tool_key)
        if not agent_tool:
            return True

        # Hierarchy gate: if every agent permitted to use this tool sits on a
        # disabled branch, the tool is unreachable and is stripped entirely.
        if self.hierarchy is not None and not self.hierarchy.tool_is_reachable(tool_key):
            return False

        tool_access = runtime_ctx.get("access", {}).get("tool_access", {}).get(tool_key, {})
        if not tool_access.get("can_use", True):
            return False

        return self._is_tool_enabled(tool_key, agent_tool, runtime_ctx)

    def _is_tool_enabled(self, tool_key: str, agent_tool: Any, runtime_ctx: dict) -> bool:
        """Check user/server/default enablement for a tool."""
        user_state = runtime_ctx.get("user_settings", {}).get(tool_key, {})
        server_state = runtime_ctx.get("server_settings", {}).get(tool_key, {})

        if user_state and user_state.get("enabled") is not None:
            return bool(user_state["enabled"])
        if server_state and server_state.get("enabled") is not None:
            return bool(server_state["enabled"])

        return bool(agent_tool.default_enabled)

    def _create_tool_nodes(self) -> dict[str, Any]:
        from backend.trading_agents.agents.analyst_registry import get_tools, list_analysts
        from backend.trading_agents.agents.runtime.resilience import tool_error_handler

        nodes: dict[str, ToolNode] = {}
        for key in list_analysts():
            tools = self._filter_tools_for_analyst(key, get_tools(key))
            try:
                tool_node = ToolNode(tools, handle_tool_errors=tool_error_handler)
            except TypeError:
                tool_node = ToolNode(tools)
            nodes[key] = _cap_tool_outputs(tool_node, int(self.config.get("max_tool_output_chars", 12000)))
        return nodes

    def propagate(self, company_name, trade_date, asset_type: str = "stock"):
        self.ticker = company_name
        self.custom_indicators = []
        self.visual_annotations = []
        self.support_levels = []
        self.resistance_levels = []
        token = active_run_context.set(
            {
                "graph": self,
                "custom_indicators": self.custom_indicators,
                "visual_annotations": self.visual_annotations,
                "support_levels": self.support_levels,
                "resistance_levels": self.resistance_levels,
            }
        )
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)
        step = checkpoint_step(self.config["data_cache_dir"], company_name, str(trade_date))
        if step is not None:
            logger.info("Resuming from step %d for %s on %s", step, company_name, trade_date)
        else:
            logger.info("Starting fresh for %s on %s", company_name, trade_date)
        try:
            return self._run_graph(company_name, trade_date, asset_type=asset_type)
        finally:
            active_run_context.reset(token)
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def _run_graph(self, company_name, trade_date, asset_type: str = "stock"):
        past_context = self.config.get("historical_context", "")
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, asset_type=asset_type, past_context=past_context
        )
        args = self.propagator.get_graph_args()
        tid = thread_id(company_name, str(trade_date))
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        step = checkpoint_step(self.config["data_cache_dir"], company_name, str(trade_date))
        state_input = None if step is not None else init_agent_state

        if self.debug:
            trace = []
            for chunk in self.graph.stream(state_input, **args):
                if len(chunk["messages"]) > 0:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(state_input, **args)
        self.curr_state = final_state
        self._log_state(trade_date, final_state)

        if not self.config.get("keep_checkpoints", True):
            clear_checkpoint(self.config["data_cache_dir"], company_name, str(trade_date))

        return final_state, self._resolve_final_signal(final_state)

    def _log_state(self, trade_date, final_state):
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "macro_report": final_state.get("macro_report", ""),
            "options_report": final_state.get("options_report", ""),
            "quant_report": final_state.get("quant_report", ""),
            "earnings_report": final_state.get("earnings_report", ""),
            "review_report": final_state.get("review_report", ""),
            "synthesis_report": final_state.get("synthesis_report", ""),
            "audit_report": final_state.get("audit_report", ""),
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"]["current_response"],
                "judge_decision": final_state["investment_debate_state"]["judge_decision"],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }
        if self.config.get("skip_disk_log", True):
            return
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    async def async_propagate(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        stream_observer: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ):
        self.ticker = company_name
        self.custom_indicators = []
        self.visual_annotations = []
        self.support_levels = []
        self.resistance_levels = []
        token = active_run_context.set(
            {
                "graph": self,
                "custom_indicators": self.custom_indicators,
                "visual_annotations": self.visual_annotations,
                "support_levels": self.support_levels,
                "resistance_levels": self.resistance_levels,
            }
        )

        try:
            async with get_async_checkpointer(self.config["data_cache_dir"], company_name) as saver:
                self.graph = self.workflow.compile(checkpointer=saver)
                step = await async_checkpoint_step(self.config["data_cache_dir"], company_name, str(trade_date))
                if step is not None:
                    logger.info("Resuming from step %d for %s on %s", step, company_name, trade_date)
                else:
                    logger.info("Starting fresh for %s on %s", company_name, trade_date)

                return await self._async_run_graph(
                    company_name, trade_date, asset_type, stream_observer=stream_observer
                )
        finally:
            active_run_context.reset(token)
            self.graph = self.workflow.compile()

    async def _async_run_graph(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        stream_observer: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ):
        import asyncio

        past_context = self.config.get("historical_context", "")
        init_state = self.propagator.create_initial_state(
            company_name, trade_date, asset_type=asset_type, past_context=past_context
        )
        args = self.propagator.get_graph_args()
        tid = thread_id(company_name, str(trade_date))
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid
        step = await async_checkpoint_step(self.config["data_cache_dir"], company_name, str(trade_date))
        state_input = None if step is not None else init_state

        if stream_observer is None:
            final_state = await self.graph.ainvoke(state_input, **args)
        else:
            cfg = dict(args.get("config") or {})
            prev_state: dict[str, Any] = {}
            final_state: dict[str, Any] = {}
            async for mode, chunk in self.graph.astream(
                state_input,
                stream_mode=["updates", "values"],
                config=cfg,
            ):
                await stream_observer(mode, chunk or {})
                if mode == "values":
                    curr = chunk or {}
                    for key, value in curr.items():
                        if key not in prev_state:
                            prev_state[key] = value
                    prev_state.update(curr)
                    final_state = dict(prev_state)
            if not final_state:
                final_state = await self.graph.ainvoke(state_input, **args)
        self.curr_state = final_state
        await asyncio.to_thread(self._log_state, trade_date, final_state)

        if not self.config.get("keep_checkpoints", True):
            clear_checkpoint(self.config["data_cache_dir"], company_name, str(trade_date))

        return final_state, self._resolve_final_signal(final_state)

    def _resolve_final_signal(self, final_state):
        """Prefer the Portfolio Manager's structured rating; fall back to parsing text.

        The structured path (``final_signal``) avoids re-parsing rendered markdown,
        which is brittle for free-text output.
        """
        structured = final_state.get("final_signal")
        if structured:
            return structured
        return self.process_signal(final_state["final_trade_decision"])

    def process_signal(self, full_signal):
        return self.signal_processor.process_signal(full_signal)
