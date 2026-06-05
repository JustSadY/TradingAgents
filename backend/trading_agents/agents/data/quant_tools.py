import io
import pandas as pd
from langchain_core.tools import tool
from typing import Annotated
from backend.trading_agents.dataflows.interface import route_to_vendor
@tool
async def get_quant_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"],
) -> str:
    """Retrieve quantitative risk metrics (Beta, Sharpe Ratio, Volatility, Max Drawdown) for an asset."""
    try:
        # Load last year of daily data
        start_date = (pd.to_datetime(curr_date) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
        csv_payload = await route_to_vendor("get_stock_data", symbol, start_date, curr_date)
        
        # Strip comments/headers
        lines = [line for line in csv_payload.splitlines() if line and not line.startswith("#")]
        if not lines:
            return "Error: No price data available for quantitative analysis."
            
        df = pd.read_csv(io.StringIO("\n".join(lines)))
        if df.empty or len(df) < 20:
            return "Error: Insufficient data for quantitative metrics."
            
        # Basic Quant Stats
        returns = df["Close"].pct_change().dropna()
        volatility = returns.std() * (252**0.5)
        sharpe = (returns.mean() / returns.std()) * (252**0.5) if returns.std() != 0 else 0
        
        # Max Drawdown
        cum_returns = (1 + returns).cumprod()
        running_max = cum_returns.cummax()
        drawdown = (cum_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        report = (
            f"## Quantitative Risk Report for {symbol.upper()} up to {curr_date}\n\n"
            f"- **Annualized Volatility:** {volatility:.2%}\n"
            f"- **Annualized Sharpe Ratio:** {sharpe:.2f}\n"
            f"- **Max Drawdown (1Y):** {max_drawdown:.2%}\n"
            "- **Daily Returns (Avg):** {:.4%}\n".format(returns.mean())
        )
        return report
    except Exception as e:
        return f"Error performing quantitative analysis: {str(e)}"
