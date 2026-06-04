from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    run_strategy_backtest,
)

def create_synthesis_manager(llm):
    def synthesis_manager_node(state) -> dict:
        from tradingagents.dataflows.config import get_config
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
            
        macd_results = run_strategy_backtest.invoke(macd_args)
        rsi_results = run_strategy_backtest.invoke(rsi_args)
        
        report_fields = {
            "market_report": "Market Research Report",
            "sentiment_report": "Social Media Sentiment Report",
            "news_report": "Latest World Affairs News",
            "fundamentals_report": "Fundamentals Report",
            "macro_report": "Macroeconomic Indicators Report",
            "options_report": "Options Market Derivatives Report",
            "quant_report": "Quantitative Metrics Report",
            "earnings_report": "Corporate Guidance & Earnings Report",
            "review_report": "Hindsight Performance Review Report",
        }
        
        resources = []
        for field, label in report_fields.items():
            content = state.get(field, "")
            if content and content.strip():
                resources.append(f"### {label}:\n{content.strip()}")
        
        resources_text = "\n\n".join(resources)
        
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

{get_language_instruction()}
"""
        response = llm.invoke(prompt)
        return {"synthesis_report": response.content}
    
    return synthesis_manager_node
