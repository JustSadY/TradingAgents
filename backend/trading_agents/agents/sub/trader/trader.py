from __future__ import annotations

import asyncio
import functools

from langchain_core.messages import AIMessage

from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.runtime.structured import (
    bind_structured,
)
from backend.trading_agents.agents.schemas import TraderProposal, render_trader_proposal
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    async def trader_node(state, name):
        company_name = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(company_name, asset_type)
        investment_plan = state["investment_plan"]
        user_id = state.get("user_id")

        # 1. Fetch Portfolio Balance & Sector Concentration if available
        portfolio_balance = None
        sector_context = ""
        if user_id:
            try:
                from backend.core.database import AsyncSessionLocal
                from backend.repositories.portfolio import get_simulation_portfolio
                import yfinance as yf

                async with AsyncSessionLocal() as db:
                    portfolio = await get_simulation_portfolio(db, user_id=user_id)
                    if portfolio:
                        portfolio_balance = float(portfolio.current_balance)
                        
                        # Calculate Sector Concentration
                        holdings = portfolio.holdings
                        if holdings:
                            sectors = {}
                            total_value = float(portfolio.current_balance)
                            for h in holdings:
                                try:
                                    # Run the blocking yfinance lookup off the event loop.
                                    # (In a real system, cache sector info on the Holding model.)
                                    info = await asyncio.to_thread(lambda t=h.ticker: yf.Ticker(t).info)
                                    sector = info.get("sector", "Unknown")
                                    h_value = float(h.quantity) * float(h.current_price)
                                    sectors[sector] = sectors.get(sector, 0) + h_value
                                except Exception:
                                    continue
                            
                            if sectors:
                                sector_context = "=== PORTFOLIO SECTOR CONCENTRATION ===\n"
                                for sector, val in sectors.items():
                                    pct = (val / total_value) * 100
                                    sector_context += f"- {sector}: {pct:.1f}%\n"
                                sector_context += "\n"

            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Could not fetch portfolio context for trader: %s", e)

        balance_context = ""
        if portfolio_balance is not None:
            balance_context = f"User's Current Portfolio Balance: ${portfolio_balance:,.2f}\n"

        macd_args = {"ticker": company_name, "strategy_type": "macd_crossover"}
        rsi_args = {"ticker": company_name, "strategy_type": "rsi_oversold"}
        if state.get("trade_date"):
            macd_args["curr_date"] = state["trade_date"]
            rsi_args["curr_date"] = state["trade_date"]

        # run_strategy_backtest is synchronous and CPU/IO-heavy; keep it off the
        # event loop so it doesn't stall concurrent analyses.
        macd_results = await asyncio.to_thread(run_strategy_backtest.invoke, macd_args)
        rsi_results = await asyncio.to_thread(run_strategy_backtest.invoke, rsi_args)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior execution trader. Your task is to turn an investment plan into a precise trade proposal. "
                    "You must provide an 'Action' (Buy/Hold/Sell), 'Entry Price', 'Stop Loss', and 'Take Profit'. "
                    "CRITICAL: You must estimate a 'Confidence Score' (Win Probability) from 0.0 to 1.0 based on the "
                    "strength of the research plan and technical backtests. "
                    "You must also calculate the 'Kelly Criterion Size' (0.0 to 1.0) using the formula: K% = W - (1-W)/R, "
                    "where W is Confidence Score and R is Risk/Reward Ratio ((Take Profit - Entry) / (Entry - Stop Loss)). "
                    "If a 'User's Current Portfolio Balance' is provided, multiply the Kelly Size by the balance to provide the 'Suggested Capital Allocation'. "
                    "If Action is 'Hold' or 'Sell' (to close), set Kelly Size and Suggested Capital to 0. "
                    "Check the 'PORTFOLIO SECTOR CONCENTRATION' context. If adding this trade significantly increases exposure to a single sector (e.g., >30% in one sector), issue a warning in the reasoning. "
                    "Consider the 'GLOBAL MARKET PULSE' for overall market conditions. "
                    "Anchor your reasoning in the analysts' reports and the quantitative backtest results provided."
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{balance_context}"
                    f"{sector_context}"
                    f"Research Plan: {investment_plan}\n\n"
                    f"Historical Strategy Backtests:\n{macd_results}\n\n{rsi_results}\n\n"
                    f"{instrument_context}\n\n"
                    "Formulate a precise trade proposal with confidence metrics, Kelly positioning, and risk warnings."
                ),
            },
        ]

        from backend.trading_agents.agents.runtime.structured import ainvoke_structured_or_freetext

        trader_proposal = await ainvoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        # The helper returns a free-text string on fallback, or the structured
        # TraderProposal object when structured output succeeds.
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
