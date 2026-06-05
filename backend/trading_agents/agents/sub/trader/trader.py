from __future__ import annotations
import functools
from langchain_core.messages import AIMessage
from backend.trading_agents.agents.schemas import TraderProposal, render_trader_proposal
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from backend.trading_agents.agents.runtime.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest

def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")
    
    async def trader_node(state, name):
        company_name = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(company_name, asset_type)
        investment_plan = state["investment_plan"]
        
        macd_args = {
            "ticker": company_name,
            "strategy_type": "macd_crossover"
        }
        rsi_args = {
            "ticker": company_name,
            "strategy_type": "rsi_oversold"
        }
        if state.get("trade_date"):
            macd_args["curr_date"] = state["trade_date"]
            rsi_args["curr_date"] = state["trade_date"]
            
        macd_results = run_strategy_backtest.invoke(macd_args)
        rsi_results = run_strategy_backtest.invoke(rsi_args)
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior execution trader. Your task is to turn an investment plan into a precise trade proposal. "
                    "You must provide an 'Action' (Buy/Hold/Sell), 'Entry Price', 'Stop Loss', and 'Take Profit'. "
                    "CRITICAL: You must estimate a 'Confidence Score' (Win Probability) from 0.0 to 1.0 based on the "
                    "strength of the research plan and technical backtests. This score is used for Kelly Criterion sizing. "
                    "Anchor your reasoning in the analysts' reports and the quantitative backtest results provided."
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Research Plan: {investment_plan}\n\n"
                    f"Historical Strategy Backtests:\n{macd_results}\n\n{rsi_results}\n\n"
                    f"{instrument_context}\n\n"
                    "Formulate a precise trade proposal with confidence metrics."
                ),
            },
        ]
        
        # invoke_structured_or_freetext is currently sync, but we'll await ainvoke directly here
        # or update the helper. Let's update the helper or just call directly.
        # Actually, let's just use ainvoke directly for better consistency.
        from backend.trading_agents.agents.runtime.structured import ainvoke_structured_or_freetext
        trader_proposal = await ainvoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )
        
        # If the helper returned a string (render_trader_proposal was called), it's already rendered.
        # But wait, ainvoke_structured_or_freetext might return the object.
        # Let's check the helper.
        
        # Assuming it returns the Pydantic object if using structured_llm
        if isinstance(trader_proposal, str):
            trader_plan = trader_proposal
            proposal_json = "{}"
        else:
            trader_plan = render_trader_proposal(trader_proposal)
            proposal_json = trader_proposal.model_dump_json()
        
        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "trader_proposal_json": proposal_json,
            "sender": name,
        }
        
    return functools.partial(trader_node, name="Trader")
