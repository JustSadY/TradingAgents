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
from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic
class GraphSetup:
    def __init__(
        self,
        llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
        analyst_llms: Dict[str, Any] = None,
    ):
        self.llm = llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.analyst_concurrency_limit = analyst_concurrency_limit
        self.analyst_llms = analyst_llms or {}
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
                lambda k=spec.key: get_factory(k)(self.analyst_llms.get(k, self.llm))
            )
            for spec in plan.specs
        }
        bull_researcher_node = create_bull_researcher(self.llm)
        bear_researcher_node = create_bear_researcher(self.llm)
        synthesis_manager_node = create_synthesis_manager(self.llm)
        auditor_node = create_auditor_node(self.llm)
        research_manager_node = create_research_manager(self.llm)
        trader_node = create_trader(self.llm)
        aggressive_analyst = create_aggressive_debator(self.llm)
        neutral_analyst = create_neutral_debator(self.llm)
        conservative_analyst = create_conservative_debator(self.llm)
        portfolio_manager_node = create_portfolio_manager(self.llm)
        workflow = StateGraph(AgentState)
        for spec in plan.specs:
            workflow.add_node(spec.agent_node, analyst_factories[spec.key]())
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
