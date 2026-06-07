from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor


@tool
async def get_options_data(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Retrieve options chain data, including Put/Call ratios and Implied Volatility (IV) metrics."""
    from datetime import datetime, timedelta

    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        trade_date_str = ctx.get("trade_date") if ctx else None
    except Exception:
        trade_date_str = None

    if trade_date_str:
        try:
            end_dt = datetime.strptime(trade_date_str, "%Y-%m-%d")
        except ValueError:
            end_dt = datetime.utcnow()
    else:
        end_dt = datetime.utcnow()

    start_dt = end_dt - timedelta(days=90)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")

    return await route_to_vendor("get_news", symbol, start_date, end_date)
