from backend.trading_agents.agents.runtime.agent_states import AgentState

# Mapping from analyst key to (tool_node_name, clear_node_name).
# Add a new analyst here instead of writing a new should_continue_* method.
_ANALYST_NODES: dict[str, tuple[str, str]] = {
    "market":       ("tools_market",       "Msg Clear Market"),
    "social":       ("tools_social",       "Msg Clear Sentiment"),
    "news":         ("tools_news",         "Msg Clear News"),
    "fundamentals": ("tools_fundamentals", "Msg Clear Fundamentals"),
    "macro":        ("tools_macro",        "Msg Clear Macro"),
    "options":      ("tools_options",      "Msg Clear Options"),
    "quant":        ("tools_quant",        "Msg Clear Quant"),
    "earnings":     ("tools_earnings",     "Msg Clear Earnings"),
    "review":       ("tools_review",       "Msg Clear Review"),
}


class ConditionalLogic:
    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    # ── Generic analyst router ───────────────────────────────────────────────
    def should_continue(self, state: AgentState, analyst_key: str) -> str:
        """Return the next node name for *analyst_key* based on whether the
        last message contains tool calls."""
        tool_node, clear_node = _ANALYST_NODES[analyst_key]
        last_message = state["messages"][-1]
        return tool_node if last_message.tool_calls else clear_node

    # ── Per-analyst shims (backward-compatible delegation) ───────────────────
    def should_continue_market(self, state: AgentState):
        return self.should_continue(state, "market")

    def should_continue_social(self, state: AgentState):
        return self.should_continue(state, "social")

    def should_continue_news(self, state: AgentState):
        return self.should_continue(state, "news")

    def should_continue_fundamentals(self, state: AgentState):
        return self.should_continue(state, "fundamentals")

    def should_continue_macro(self, state: AgentState):
        return self.should_continue(state, "macro")

    def should_continue_options(self, state: AgentState):
        return self.should_continue(state, "options")

    def should_continue_quant(self, state: AgentState):
        return self.should_continue(state, "quant")

    def should_continue_earnings(self, state: AgentState):
        return self.should_continue(state, "earnings")

    def should_continue_review(self, state: AgentState):
        return self.should_continue(state, "review")
    def should_continue_debate(self, state: AgentState) -> str:
        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"
    def should_continue_risk_analysis(self, state: AgentState) -> str:
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
