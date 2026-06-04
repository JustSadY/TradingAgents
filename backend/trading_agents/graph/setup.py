from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from backend.trading_agents.agents import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
    create_msg_delete,
    create_bear_researcher,
    create_bull_researcher,
    create_aggressive_debator,
    create_conservative_debator,
    create_neutral_debator,
    create_research_manager,
    create_synthesis_manager,
    create_auditor_node,
    create_portfolio_manager,
    create_trader,
)
import backend.trading_agents.agents.analysts.market_analyst
import backend.trading_agents.agents.analysts.sentiment_analyst
import backend.trading_agents.agents.analysts.news_analyst
import backend.trading_agents.agents.analysts.fundamentals_analyst
import backend.trading_agents.agents.analysts.macro_analyst
import backend.trading_agents.agents.analysts.options_analyst
import backend.trading_agents.agents.analysts.quant_analyst
import backend.trading_agents.agents.analysts.earnings_analyst
import backend.trading_agents.agents.analysts.review_analyst
from backend.trading_agents.agents.analyst_registry import get_factory, sync_registry_to_graph
from backend.trading_agents.agents.utils.resilience import guard_node
from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic


# --- Safe fallbacks: when a downstream agent fails after retries, return a
# minimal valid state update so the run completes (degraded) instead of aborting.

def _fb_report(key: str):
    return lambda state, exc: {key: ""}


def _fb_text(key: str, msg: str):
    return lambda state, exc: {key: msg}


def _fb_invest_debate(speaker_note: str):
    def fb(state, exc):
        ds = dict(state.get("investment_debate_state") or {})
        ds["count"] = int(ds.get("count", 0)) + 1
        ds["current_response"] = speaker_note
        return {"investment_debate_state": ds}
    return fb


def _fb_risk_debate(speaker: str):
    def fb(state, exc):
        rs = dict(state.get("risk_debate_state") or {})
        rs["count"] = int(rs.get("count", 0)) + 1
        rs["latest_speaker"] = speaker
        return {"risk_debate_state": rs}
    return fb


def _fb_analyst(report_key: str):
    def fb(state, exc):
        from langchain_core.messages import AIMessage
        analyst = report_key.replace("_report", "").title()
        return {"messages": [AIMessage(content="")],
                report_key: f"⚠️ {analyst} analysis unavailable (agent error: {exc})."}
    return fb
class GraphSetup:
    def __init__(
        self,
        llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
        agent_llms: Dict[str, Any] = None,
    ):
        self.llm = llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.analyst_concurrency_limit = analyst_concurrency_limit
        self.agent_llms = agent_llms or {}
    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        sync_registry_to_graph()
        plan = build_analyst_execution_plan(
            selected_analysts,
            concurrency_limit=self.analyst_concurrency_limit,
        )
        analyst_factories = {
            spec.key: (
                lambda k=spec.key: get_factory(k)(self.agent_llms.get(k, self.llm))
            )
            for spec in plan.specs
        }
        bull_researcher_node = guard_node(
            create_bull_researcher(self.agent_llms.get("bull_researcher", self.llm)), name="Bull Researcher", kind="research",
            fallback=_fb_invest_debate("(Bull researcher unavailable.)"))
        bear_researcher_node = guard_node(
            create_bear_researcher(self.agent_llms.get("bear_researcher", self.llm)), name="Bear Researcher", kind="research",
            fallback=_fb_invest_debate("(Bear researcher unavailable.)"))
        synthesis_manager_node = guard_node(
            create_synthesis_manager(self.agent_llms.get("synthesis_manager", self.llm)), name="Synthesis Manager", kind="manager",
            fallback=_fb_report("synthesis_report"))
        auditor_node = guard_node(
            create_auditor_node(self.agent_llms.get("auditor", self.llm)), name="Auditor", kind="manager",
            fallback=_fb_report("audit_report"))
        research_manager_node = guard_node(
            create_research_manager(self.agent_llms.get("research_manager", self.llm)), name="Research Manager", kind="manager",
            fallback=_fb_text("investment_plan",
                              "Research manager unavailable; proceeding with available analyst reports."))
        trader_node = guard_node(
            create_trader(self.agent_llms.get("trader", self.llm)), name="Trader", kind="manager",
            fallback=lambda state, exc: {
                "trader_investment_plan": "Trader agent unavailable; deferring to risk debate.",
                "trader_proposal_json": "{}",
            })
        aggressive_analyst = guard_node(
            create_aggressive_debator(self.agent_llms.get("risk_debate", self.llm)), name="Aggressive Analyst", kind="risk",
            fallback=_fb_risk_debate("Aggressive"))
        neutral_analyst = guard_node(
            create_neutral_debator(self.agent_llms.get("risk_debate", self.llm)), name="Neutral Analyst", kind="risk",
            fallback=_fb_risk_debate("Neutral"))
        conservative_analyst = guard_node(
            create_conservative_debator(self.agent_llms.get("risk_debate", self.llm)), name="Conservative Analyst", kind="risk",
            fallback=_fb_risk_debate("Conservative"))
        portfolio_manager_node = guard_node(
            create_portfolio_manager(self.agent_llms.get("portfolio_manager", self.llm)), name="Portfolio Manager", kind="decision",
            fallback=_fb_text("final_trade_decision",
                              "Hold — automated fallback: Portfolio Manager unavailable."))
        workflow = StateGraph(AgentState)
        for spec in plan.specs:
            workflow.add_node(
                spec.agent_node,
                guard_node(analyst_factories[spec.key](), name=spec.agent_node,
                           kind="analyst", fallback=_fb_analyst(spec.report_key)),
            )
            workflow.add_node(spec.clear_node, create_msg_delete())
            workflow.add_node(spec.tool_node, self.tool_nodes[spec.key])
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Synthesis Manager", synthesis_manager_node)
        workflow.add_node("Auditor", auditor_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)
        if self.analyst_concurrency_limit == 1:
            for i, spec in enumerate(plan.specs):
                if i == 0:
                    workflow.add_edge(START, spec.agent_node)
                else:
                    prev_spec = plan.specs[i - 1]
                    workflow.add_edge(prev_spec.clear_node, spec.agent_node)
                current_analyst = spec.agent_node
                current_tools = spec.tool_node
                current_clear = spec.clear_node
                workflow.add_conditional_edges(
                    current_analyst,
                    getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                    [current_tools, current_clear],
                )
                workflow.add_edge(current_tools, current_analyst)
            if plan.specs:
                workflow.add_edge(plan.specs[-1].clear_node, "Synthesis Manager")
        else:
            for spec in plan.specs:
                workflow.add_edge(START, spec.agent_node)
            for spec in plan.specs:
                current_analyst = spec.agent_node
                current_tools = spec.tool_node
                current_clear = spec.clear_node
                workflow.add_conditional_edges(
                    current_analyst,
                    getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                    [current_tools, current_clear],
                )
                workflow.add_edge(current_tools, current_analyst)
                workflow.add_edge(current_clear, "Synthesis Manager")
        
        workflow.add_edge("Synthesis Manager", "Bull Researcher")
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Auditor": "Auditor",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Auditor": "Auditor",
            },
        )
        workflow.add_edge("Auditor", "Research Manager")
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_edge("Portfolio Manager", END)
        return workflow
