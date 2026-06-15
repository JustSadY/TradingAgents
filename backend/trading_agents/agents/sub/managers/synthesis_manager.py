import asyncio

from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    run_strategy_backtest,
)


def create_synthesis_manager(llm):
    async def synthesis_manager_node(state) -> dict:
        from backend.trading_agents.dataflows.config import get_config

        if not get_config().get("synthesis_enabled", True):
            return {"synthesis_report": "Synthesis disabled by user settings."}

        ticker = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(ticker, asset_type)

        # Pillar 3: Quantitative Baseline (Backtesting)
        macd_args = {"ticker": ticker, "strategy_type": "macd_crossover"}
        rsi_args = {"ticker": ticker, "strategy_type": "rsi_oversold"}
        if state.get("trade_date"):
            macd_args["curr_date"] = state["trade_date"]
            rsi_args["curr_date"] = state["trade_date"]

        # run_strategy_backtest is synchronous and heavy; run it off the event
        # loop so it doesn't stall concurrent analyses.
        macd_results = await asyncio.to_thread(run_strategy_backtest.invoke, macd_args)
        rsi_results = await asyncio.to_thread(run_strategy_backtest.invoke, rsi_args)

        from backend.trading_agents.agents.analyst_registry import get_report_fields
        from backend.trading_agents.agents.runtime.report_aggregator import build_resources

        resources_text = build_resources(state, get_report_fields(), prefix="### ")

        prompt = f"""You are a Senior Investment Strategist. Your task is to synthesize the following analyst reports and historical backtests for {ticker}. Identify key alignments and critical conflicts.

### Objective:
1. **Alignments:** Areas where multiple analysts agree (e.g., both Technical and Sentiment are bullish).
2. **Conflicts:** Contradictory signals that require careful debate.
3. **Historical Context:** Use the backtest data below to set a performance baseline. If backtests show poor performance (< 50% win rate), flag this as a 'Critical Risk' for the upcoming debate.
4. **Primary Narrative:** The dominant story currently driving the asset's price action.

### Historical Baseline (Backtests):
{macd_results}
{rsi_results}

### Analyst Resources:
{resources_text}

{instrument_context}

### Output Format:
Your synthesis MUST follow this structure:
1. **Executive Synthesis Summary:** A 3-bullet point overview of the combined research landscape.
2. **Key Alignments:** List specific points of agreement across analytical disciplines.
3. **Critical Conflicts:** Explicitly identify contradictions. This serves as the primary agenda for the Bull vs. Bear debate.
4. **Data Synthesis Table:** A Markdown table summarizing each analyst's bias and top 1-2 evidence points.

{get_general_settings_block()}
"""
        response = await llm.ainvoke(prompt)
        return {"synthesis_report": response.content}

    return synthesis_manager_node
