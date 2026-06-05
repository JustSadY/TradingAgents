import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional
import yfinance as yf
logger = logging.getLogger(__name__)
from langgraph.prebuilt import ToolNode
from backend.trading_agents.llm_clients import create_llm_client
from backend.trading_agents.agents import *
from backend.trading_agents.default_config import DEFAULT_CONFIG
from backend.trading_agents.agents.runtime.memory import TradingMemoryLog
from backend.trading_agents.dataflows.utils import safe_ticker_component
from backend.trading_agents.agents.runtime.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from backend.trading_agents.agents.data.chart_tools import active_run_context
from backend.trading_agents.dataflows.config import set_config
from backend.trading_agents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_macro_data,
    get_options_data,
    get_quant_data,
    search_web,
    get_crypto_fear_and_greed_index,
)
from backend.trading_agents.agents.data.review_tools import get_past_performance_data
from backend.trading_agents.agents.agent_hierarchy import AgentHierarchy
from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor
class TradingAgentsGraph:
    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        set_config(self.config)
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)
        main_prov = self.config["llm_provider"]
        main_kwargs = self._get_provider_kwargs(main_prov)
        if self.callbacks:
            main_kwargs["callbacks"] = self.callbacks
        client = create_llm_client(
            provider=main_prov,
            model=self.config["llm_model"],
            base_url=self.config.get("backend_url"),
            **main_kwargs,
        )
        self.thinking_llm = client.get_llm()

        # ------------------------------------------------------------------
        # Build the agent hierarchy from runtime context
        # ------------------------------------------------------------------
        runtime_agent_ctx = self.config.get("runtime_agent_context") or {}
        self.hierarchy = AgentHierarchy(runtime_agent_ctx)

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
                base_url=self.config.get("backend_url"),
                **kwargs,
            )
            return c.get_llm()

        # Resolve per-agent LLMs via hierarchy (supports parent fallback)
        from backend.trading_agents.agent_catalog import list_agents
        self.agent_llms: Dict[str, Any] = {}
        for agent_info in list_agents():
            key = agent_info.key
            try:
                self.agent_llms[key] = self.hierarchy.resolve_llm(
                    key, self.thinking_llm, _make_llm
                )
            except Exception as e:
                logger.warning(
                    "LLM resolution failed for agent '%s': %s – using global LLM.", key, e
                )
                self.agent_llms[key] = self.thinking_llm

        # ------------------------------------------------------------------
        # Filter selected analysts using hierarchy enable state.
        # is_enabled() cascades through market_intelligence → portfolio_manager,
        # so disabling either branch transparently drops every analyst.
        # ------------------------------------------------------------------
        _effective_analysts = [
            k for k in selected_analysts if self.hierarchy.is_enabled(k)
        ]
        skipped = set(selected_analysts) - set(_effective_analysts)
        if skipped:
            logger.info(
                "The following analysts are disabled by hierarchy and will be skipped: %s",
                sorted(skipped),
            )

        self.memory_log = TradingMemoryLog(self.config)
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
        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100)
        )
        self.reflector = Reflector(self.thinking_llm)
        self.signal_processor = SignalProcessor(self.thinking_llm)
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}
        self.workflow = self.graph_setup.setup_graph(_effective_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None
    def _get_provider_kwargs(self, provider: str = None) -> Dict[str, Any]:
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
        user_keys = self.config.get("user_api_keys") or {}
        user_key = user_keys.get(prov_lower)
        if user_key:
            kwargs["api_key"] = user_key
        elif self.config.get("api_key") and prov_lower == self.config.get("llm_provider", "").lower():
            kwargs["api_key"] = self.config["api_key"]
        if not kwargs.get("api_key") and self.config.get("has_user", False) and not self.config.get("is_admin", False):
            from backend.trading_agents.llm_clients.api_key_env import get_api_key_env
            api_key_env = get_api_key_env(prov_lower)
            if api_key_env:
                raise ValueError(
                    f"No API key set for provider '{prov_lower}'. "
                    "Go to Profile → API Keys to add your key."
                )
        return kwargs
    def _filter_tools_for_analyst(self, analyst_key: str, raw_tools: list) -> list:
        runtime_ctx = self.config.get("runtime_tool_context")
        if not runtime_ctx:
            return raw_tools

        from backend.trading_agents.agents.tools.registry import registry

        filtered = []
        for tool_func in raw_tools:
            tool_name = tool_func.name if hasattr(tool_func, "name") else tool_func.__name__
            agent_tool_key = registry.get_agent_tool_key_for_langchain_tool(tool_name)

            if agent_tool_key is None:
                filtered.append(tool_func)
                continue

            agent_tool = registry.get(agent_tool_key)
            if not agent_tool:
                filtered.append(tool_func)
                continue

            # Hierarchy gate: if every agent permitted to use this tool sits on a
            # disabled branch, the tool is unreachable and is stripped entirely.
            if self.hierarchy is not None and not self.hierarchy.tool_is_reachable(agent_tool_key):
                continue

            tool_access = runtime_ctx.get("access", {}).get("tool_access", {}).get(agent_tool_key, {})
            can_use = tool_access.get("can_use", True)
            if not can_use:
                continue

            user_state = runtime_ctx.get("user_settings", {}).get(agent_tool_key, {})
            server_state = runtime_ctx.get("server_settings", {}).get(agent_tool_key, {})

            enabled = None
            if user_state and user_state.get("enabled") is not None:
                enabled = user_state["enabled"]
            elif server_state and server_state.get("enabled") is not None:
                enabled = server_state["enabled"]
            else:
                enabled = agent_tool.default_enabled

            if not enabled:
                continue

            filtered.append(tool_func)

        return filtered

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        from backend.trading_agents.agents.analyst_registry import get_tools, list_analysts
        from backend.trading_agents.agents.runtime.resilience import tool_error_handler
        nodes: Dict[str, ToolNode] = {}
        for key in list_analysts():
            tools = self._filter_tools_for_analyst(key, get_tools(key))
            try:
                nodes[key] = ToolNode(tools, handle_tool_errors=tool_error_handler)
            except TypeError:
                nodes[key] = ToolNode(tools)
        return nodes
    def _resolve_benchmark(self, ticker: str) -> str:
        explicit = self.config.get("benchmark_ticker")
        if explicit:
            return explicit
        benchmark_map = self.config.get("benchmark_map", {})
        ticker_upper = ticker.upper()
        for suffix, benchmark in benchmark_map.items():
            if suffix and ticker_upper.endswith(suffix.upper()):
                return benchmark
        return benchmark_map.get("", "SPY")
    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5,
        benchmark: str = "SPY",
    ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)
            end_str = end.strftime("%Y-%m-%d")
            stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
            bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)
            if len(stock) < 2 or len(bench) < 2:
                return None, None, None
            actual_days = min(holding_days, len(stock) - 1, len(bench) - 1)
            raw = float(
                (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
                / stock["Close"].iloc[0]
            )
            bench_ret = float(
                (bench["Close"].iloc[actual_days] - bench["Close"].iloc[0])
                / bench["Close"].iloc[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "Could not resolve outcome for %s on %s vs %s (will retry next run): %s",
                ticker, trade_date, benchmark, e,
            )
            return None, None, None
    def _resolve_pending_entries(self, ticker: str) -> None:
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return
        benchmark = self._resolve_benchmark(ticker)
        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(
                ticker, entry["date"], benchmark=benchmark,
            )
            if raw is None:
                continue
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })
        if updates:
            self.memory_log.batch_update_with_outcomes(updates)
    def propagate(self, company_name, trade_date, asset_type: str = "stock"):
        self.ticker = company_name
        self.custom_indicators = []
        self.visual_annotations = []
        token = active_run_context.set({
            "graph": self,
            "custom_indicators": self.custom_indicators,
            "visual_annotations": self.visual_annotations
        })
        self._resolve_pending_entries(company_name)
        self._checkpointer_ctx = get_checkpointer(
            self.config["data_cache_dir"], company_name
        )
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)
        step = checkpoint_step(
            self.config["data_cache_dir"], company_name, str(trade_date)
        )
        if step is not None:
            logger.info(
                "Resuming from step %d for %s on %s", step, company_name, trade_date
            )
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
        past_context = self.memory_log.get_past_context(company_name)
        historical_context = self.config.get("historical_context", "")
        if historical_context:
            past_context = f"{past_context}\n\n{historical_context}" if past_context else historical_context
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, asset_type=asset_type, past_context=past_context
        )
        args = self.propagator.get_graph_args()
        tid = thread_id(company_name, str(trade_date))
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid
        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(init_agent_state, **args)
        self.curr_state = final_state
        self._log_state(trade_date, final_state)
        self.memory_log.store_decision(
            ticker=company_name,
            trade_date=trade_date,
            final_trade_decision=final_state["final_trade_decision"],
        )
        clear_checkpoint(
            self.config["data_cache_dir"], company_name, str(trade_date)
        )
        return final_state, self.process_signal(final_state["final_trade_decision"])
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
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
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
        if self.config.get("skip_disk_log"):
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
    ):
        import asyncio
        self.ticker = company_name
        self.custom_indicators = []
        self.visual_annotations = []
        token = active_run_context.set({
            "graph": self,
            "custom_indicators": self.custom_indicators,
            "visual_annotations": self.visual_annotations
        })
        await self._async_resolve_pending_entries(company_name)
        self._checkpointer_ctx = get_checkpointer(
            self.config["data_cache_dir"], company_name
        )
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)
        try:
            return await self._async_run_graph(company_name, trade_date, asset_type)
        finally:
            active_run_context.reset(token)
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()
    async def _async_run_graph(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
    ):
        import asyncio
        past_context = self.memory_log.get_past_context(company_name)
        historical_context = self.config.get("historical_context", "")
        if historical_context:
            past_context = f"{past_context}\n\n{historical_context}" if past_context else historical_context
        init_state = self.propagator.create_initial_state(
            company_name, trade_date, asset_type=asset_type, past_context=past_context
        )
        args = self.propagator.get_graph_args()
        tid = thread_id(company_name, str(trade_date))
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid
        final_state = await asyncio.to_thread(self.graph.invoke, init_state, **args)
        self.curr_state = final_state
        await asyncio.to_thread(self._log_state, trade_date, final_state)
        await asyncio.to_thread(
            self.memory_log.store_decision,
            company_name,
            trade_date,
            final_state["final_trade_decision"],
        )
        clear_checkpoint(
            self.config["data_cache_dir"], company_name, str(trade_date)
        )
        return final_state, self.process_signal(final_state["final_trade_decision"])
    async def _async_resolve_pending_entries(self, ticker: str) -> None:
        import asyncio
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return
        benchmark = self._resolve_benchmark(ticker)
        updates = []
        for entry in pending:
            raw, alpha, days = await asyncio.to_thread(
                self._fetch_returns, ticker, entry["date"], benchmark=benchmark
            )
            if raw is None:
                continue
            reflection = await asyncio.to_thread(
                self.reflector.reflect_on_final_decision,
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })
        if updates:
            await asyncio.to_thread(self.memory_log.batch_update_with_outcomes, updates)
    def process_signal(self, full_signal):
        return self.signal_processor.process_signal(full_signal)
