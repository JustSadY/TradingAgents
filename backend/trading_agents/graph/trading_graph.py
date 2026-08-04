import json
import logging
import os
import uuid
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

def _cap_tool_outputs(tool_node: ToolNode, max_chars: int, *, analyst_key: str):
    """Wrap a ToolNode so oversized tool results are middle-truncated before
    they enter the analyst's conversation, and a hard timeout prevents a hung
    external API from stalling the run.

    Every tool result stays in the message list and is re-sent on each LLM
    round-trip within the analyst's run, so one unbounded CSV dump multiplies
    across turns. Middle truncation keeps the head (CSV headers/context) and
    the tail (most recent rows) — see ``middle_truncate``."""

    async def _run(state, *args, **kwargs):
        import asyncio

        from backend.services.analysis.activity import touch_current_analysis
        from backend.trading_agents.agents.runtime.report_aggregator import middle_truncate
        from backend.trading_agents.dataflows.config import get_config

        _cfg = get_config()
        timeout = _cfg.get("tool_timeout_seconds", 60)
        touch_current_analysis()
        try:
            result = await asyncio.wait_for(tool_node.ainvoke(state, *args, **kwargs), timeout=timeout)
        except TimeoutError:
            from backend.trading_agents.agents.runtime.tool_telemetry import log_tool_timeout

            touch_current_analysis()
            return {"messages": log_tool_timeout(state, analyst=analyst_key, timeout_seconds=timeout)}
        messages = result.get("messages", []) if isinstance(result, dict) else []
        for message in messages:
            content = getattr(message, "content", None)
            if isinstance(content, str) and len(content) > max_chars:
                message.content = middle_truncate(content, max_chars)
        touch_current_analysis()
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
        self.config = dict(config or DEFAULT_CONFIG)
        self.config.setdefault("checkpoint_scope", f"ephemeral:{uuid.uuid4()}")
        self.callbacks = callbacks or []
        set_config(self.config)
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        runtime_agent_ctx = self.config.get("runtime_agent_context") or {}
        self.hierarchy = AgentHierarchy(runtime_agent_ctx)

        self._init_llms(runtime_agent_ctx)

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
        self.ticker = None
        self.log_states_dict = {}
        self.workflow = self.graph_setup.setup_graph(_effective_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _checkpoint_scope(self) -> str:
        scope = self.config.get("checkpoint_scope")
        if not isinstance(scope, str) or not scope:
            raise ValueError("checkpoint_scope is required for graph execution")
        return scope

    def _init_llms(self, runtime_agent_ctx: dict):
        pm_state = runtime_agent_ctx.get("portfolio_manager") or {}
        pm_settings = pm_state.get("settings") or {}

        main_prov = pm_settings.get("llm_provider") or self.config.get("llm_provider") or "openai"
        main_model = pm_settings.get("llm_model") or self.config.get("llm_model") or "gpt-4o-mini"
        self.llm_provider = main_prov
        self.llm_model = main_model

        main_kwargs = self._get_provider_kwargs(main_prov)
        if self.callbacks:
            main_kwargs["callbacks"] = self.callbacks

        if pm_settings.get("temperature") is not None:
            main_kwargs["temperature"] = float(pm_settings["temperature"])

        client = create_llm_client(
            provider=main_prov,
            model=main_model,
            **main_kwargs,
        )
        main_llm = self._with_fallback(client.get_llm(), main_prov, main_model)
        self.thinking_llm = main_llm.with_config(tags=["portfolio_manager"], metadata={"agent": "portfolio_manager"})

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
        ...}`` dicts) from config. Failure to build a fallback never blocks the
        run — unavailable entries are dropped, and if nothing can be built the
        primary is returned unwrapped.
        """
        from backend.trading_agents.config import normalize_fallback_llm_chain
        from backend.trading_agents.llm_clients.fallback import FallbackLLM

        chain = normalize_fallback_llm_chain(self.config.get("fallback_llm_chain"))
        if not chain:
            return llm

        fallbacks = []
        for entry in chain:
            prov = entry["provider"]
            mod = entry["model"]
            if prov == (provider or "").lower() and mod == model:
                continue
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

        from backend.trading_agents.llm_clients.registry import provider_requires_api_key

        if not provider_requires_api_key(prov_lower):
            return kwargs

        user_keys = self.config.get("user_api_keys") or {}
        user_key = user_keys.get(prov_lower)
        if user_key:
            kwargs["api_key"] = user_key
        elif self.config.get("api_key") and prov_lower == self.config.get("llm_provider", "").lower():
            kwargs["api_key"] = self.config["api_key"]
        return kwargs

    def _filter_tools_for_analyst(self, analyst_key: str, raw_tools: list) -> list:
        runtime_ctx = self.config.get("runtime_tool_context") or {}

        from backend.trading_agents.agents.tools.registry import registry

        filtered = []
        for tool_func in raw_tools:
            tool_name = tool_func.name if hasattr(tool_func, "name") else tool_func.__name__
            agent_tool_key = registry.get_agent_tool_key_for_langchain_tool(tool_name)

            if self._should_include_tool(analyst_key, agent_tool_key, tool_func, runtime_ctx):
                filtered.append(tool_func)

        return filtered

    def _should_include_tool(self, analyst_key: str, tool_key: str | None, _tool_func: Any, runtime_ctx: dict) -> bool:
        """Helper to determine if a tool should be included for an analyst."""
        if tool_key is None:
            # Unknown/unregistered tools have no temporal contract. Historical
            # runs fail closed rather than assuming an arbitrary network tool
            # is point-in-time safe.
            if self.config.get("historical_mode") and not self.config.get("allow_live_data_in_historical", False):
                tool_name = getattr(_tool_func, "name", getattr(_tool_func, "__name__", "unknown"))
                logger.warning("Historical run: excluding unregistered tool '%s'.", tool_name)
                return False
            return True

        from backend.trading_agents.agents.tools.registry import registry

        agent_tool = registry.get(tool_key)
        if not agent_tool:
            return True

        if self.config.get("historical_mode") and not self.config.get("allow_live_data_in_historical", False):
            if getattr(agent_tool, "temporal_semantics", "live_only") == "live_only":
                logger.info(
                    "Historical run: excluding live-only tool '%s' from analyst '%s'.",
                    tool_key,
                    analyst_key,
                )
                return False

        if agent_tool.allowed_analysts and analyst_key not in agent_tool.allowed_analysts:
            logger.warning(
                "Tool '%s' is wired into analyst '%s' but its registry allowed_analysts=%s doesn't "
                "include it — excluding. Add '%s' to the tool's allowed_analysts.",
                tool_key,
                analyst_key,
                agent_tool.allowed_analysts,
                analyst_key,
            )
            return False

        if self.hierarchy is not None and not self.hierarchy.tool_is_reachable(tool_key):
            return False

        tool_access = runtime_ctx.get("access", {}).get("tool_access", {}).get(tool_key, {})
        if not tool_access.get("can_use", True):
            return False

        return self._is_tool_enabled(tool_key, agent_tool, runtime_ctx)

    def _is_tool_enabled(self, tool_key: str, agent_tool: Any, runtime_ctx: dict) -> bool:
        """Check effective tool enablement.

        Server settings are a policy ceiling, not merely a fallback.  In
        particular, a server-side ``enabled=False`` must not be re-enabled by
        an otherwise-default user setting.  User settings can still opt out
        of a server-enabled tool.
        """
        user_state = runtime_ctx.get("user_settings", {}).get(tool_key, {})
        server_state = runtime_ctx.get("server_settings", {}).get(tool_key, {})

        if server_state and server_state.get("enabled") is False:
            return False
        if user_state and user_state.get("enabled") is not None:
            return bool(user_state["enabled"])
        if server_state and server_state.get("enabled") is not None:
            return bool(server_state["enabled"])

        return bool(agent_tool.default_enabled)

    def _create_tool_nodes(self) -> dict[str, Any]:
        from backend.trading_agents.agents.analyst_registry import get_tools, list_analysts
        from backend.trading_agents.agents.runtime.tool_telemetry import (
            make_async_tool_call_wrapper,
            tool_error_handler,
        )

        nodes: dict[str, ToolNode] = {}
        for key in list_analysts():
            tools = self._filter_tools_for_analyst(key, get_tools(key))
            tool_node = ToolNode(
                tools,
                handle_tool_errors=tool_error_handler,
                awrap_tool_call=make_async_tool_call_wrapper(key),
            )
            nodes[key] = _cap_tool_outputs(
                tool_node,
                int(self.config.get("max_tool_output_chars", 12000)),
                analyst_key=key,
            )
        return nodes

    def propagate(self, company_name, trade_date, asset_type: str = "stock"):
        self.ticker = company_name
        self.custom_indicators = []
        self.visual_annotations = []
        self.support_levels = []
        self.resistance_levels = []
        existing_ctx = active_run_context.get({})
        token = active_run_context.set(
            {
                **existing_ctx,
                "graph": self,
                "custom_indicators": self.custom_indicators,
                "visual_annotations": self.visual_annotations,
                "support_levels": self.support_levels,
                "resistance_levels": self.resistance_levels,
                "trade_date": str(trade_date),
                "historical_mode": bool(self.config.get("historical_mode", False)),
                "allow_live_data_in_historical": bool(self.config.get("allow_live_data_in_historical", False)),
                "user_id": self.config.get("user_id"),
            }
        )
        checkpoint_scope = self._checkpoint_scope()
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name, checkpoint_scope)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)
        step = checkpoint_step(self.config["data_cache_dir"], company_name, str(trade_date), checkpoint_scope)
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
        checkpoint_scope = self._checkpoint_scope()
        tid = thread_id(company_name, str(trade_date), checkpoint_scope)
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        step = checkpoint_step(self.config["data_cache_dir"], company_name, str(trade_date), checkpoint_scope)
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
            clear_checkpoint(self.config["data_cache_dir"], company_name, str(trade_date), checkpoint_scope)

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
            "insider_report": final_state.get("insider_report", ""),
            "ownership_report": final_state.get("ownership_report", ""),
            "ratings_report": final_state.get("ratings_report", ""),
            "short_interest_report": final_state.get("short_interest_report", ""),
            "valuation_report": final_state.get("valuation_report", ""),
            "catalyst_report": final_state.get("catalyst_report", ""),
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
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "portfolio_decision": final_state.get("portfolio_decision_json", "{}"),
            "final_trade_decision": final_state["final_trade_decision"],
        }
        if self.config.get("skip_disk_log", True):
            logger.debug("skip_disk_log is enabled; skipping full state log disk write.")
            return
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / f"full_states_log_{trade_date}.json"
        log_data = self.log_states_dict.get(str(trade_date), self.log_states_dict)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4)

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
        existing_ctx = active_run_context.get({})
        token = active_run_context.set(
            {
                **existing_ctx,
                "graph": self,
                "custom_indicators": self.custom_indicators,
                "visual_annotations": self.visual_annotations,
                "support_levels": self.support_levels,
                "resistance_levels": self.resistance_levels,
                "trade_date": str(trade_date),
                "historical_mode": bool(self.config.get("historical_mode", False)),
                "allow_live_data_in_historical": bool(self.config.get("allow_live_data_in_historical", False)),
                "user_id": self.config.get("user_id"),
            }
        )

        try:
            checkpoint_scope = self._checkpoint_scope()
            async with get_async_checkpointer(self.config["data_cache_dir"], company_name, checkpoint_scope) as saver:
                self.graph = self.workflow.compile(checkpointer=saver)
                step = await async_checkpoint_step(
                    self.config["data_cache_dir"], company_name, str(trade_date), checkpoint_scope
                )
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
        checkpoint_scope = self._checkpoint_scope()
        tid = thread_id(company_name, str(trade_date), checkpoint_scope)
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid
        step = await async_checkpoint_step(
            self.config["data_cache_dir"], company_name, str(trade_date), checkpoint_scope
        )
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
            clear_checkpoint(self.config["data_cache_dir"], company_name, str(trade_date), checkpoint_scope)

        return final_state, self._resolve_final_signal(final_state)

    def _resolve_final_signal(self, final_state):
        """Prefer the Portfolio Manager's structured rating; fall back to parsing text.

        The structured path (``final_signal``) avoids re-parsing rendered markdown,
        which is brittle for free-text output.
        """
        structured = final_state.get("final_signal")
        if structured:
            logger.info("Final signal (structured): %r", structured)
            return structured
        parsed = self.process_signal(final_state.get("final_trade_decision", ""))
        logger.info("Final signal (parsed from text): %r", parsed)
        return parsed

    def process_signal(self, full_signal):
        return self.signal_processor.process_signal(full_signal)
