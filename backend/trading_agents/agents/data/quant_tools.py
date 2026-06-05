import io
import pandas as pd
import numpy as np
from langchain_core.tools import tool
from backend.core.utils import resolve_benchmark
from backend.trading_agents.dataflows.interface import route_to_vendor

def _load_ohlcv_via_interface(symbol: str, curr_date: str) -> pd.DataFrame:
    start_date = (pd.to_datetime(curr_date) - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    csv_payload = route_to_vendor("get_stock_data", symbol, start_date, curr_date)
    lines = [line for line in (csv_payload or "").splitlines() if line and not line.startswith("#")]
    if not lines:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df = pd.read_csv(io.StringIO("\n".join(lines)))
    if "Date" not in df.columns and "Datetime" in df.columns:
        df.rename(columns={"Datetime": "Date"}, inplace=True)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    if price_cols:
        df[price_cols] = df[price_cols].apply(pd.to_numeric, errors="coerce")
    if "Close" in df.columns:
        df = df.dropna(subset=["Close"])
    if price_cols:
        df[price_cols] = df[price_cols].ffill().bfill()
    return df[df["Date"] <= pd.to_datetime(curr_date)] if "Date" in df.columns else df

@tool
def get_quant_data(
    ticker: str,
    curr_date: str | None = None
) -> str:
    """Calculate annualized volatility, beta, Sharpe Ratio, and benchmark correlation metrics for a given ticker symbol over the last 1 year."""
    try:
        from backend.trading_agents.dataflows.config import get_config
        if not curr_date:
            curr_date = pd.Timestamp.today().strftime("%Y-%m-%d")
        config = get_config()
        benchmark = resolve_benchmark(ticker, config)
        hist = _load_ohlcv_via_interface(ticker, curr_date)
        bench_hist = _load_ohlcv_via_interface(benchmark, curr_date)
        curr_date_dt = pd.to_datetime(curr_date)
        one_year_ago = curr_date_dt - pd.DateOffset(years=1)
        hist = hist[hist['Date'] >= one_year_ago]
        bench_hist = bench_hist[bench_hist['Date'] >= one_year_ago]
        if len(hist) < 20 or len(bench_hist) < 20:
            return f"Not enough historical data to calculate quant metrics for {ticker}."
        hist_indexed = hist.set_index('Date')
        bench_indexed = bench_hist.set_index('Date')
        data = pd.DataFrame({
            'Stock': hist_indexed['Close'],
            'Benchmark': bench_indexed['Close']
        }).dropna()
        returns = data.pct_change().dropna()
        stock_volatility = returns['Stock'].std() * np.sqrt(252)
        bench_volatility = returns['Benchmark'].std() * np.sqrt(252)
        covariance = returns['Stock'].cov(returns['Benchmark'])
        bench_variance = returns['Benchmark'].var()
        beta = covariance / bench_variance if bench_variance > 0 else 0
        rf = 0.04
        daily_rf = rf / 252
        excess_returns = returns['Stock'] - daily_rf
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252) if excess_returns.std() > 0 else 0
        correlation = returns['Stock'].corr(returns['Benchmark'])
        report = [
            f"Quantitative Metrics for {ticker} (1-Year, benchmark: {benchmark}):",
            f"- Beta: {beta:.2f} (vs {benchmark})",
            f"- Annualized Volatility: {stock_volatility:.2%} ({benchmark}: {bench_volatility:.2%})",
            f"- Sharpe Ratio: {sharpe:.2f}",
            f"- Correlation with {benchmark}: {correlation:.2f}"
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Error calculating quant data for {ticker}: {str(e)}"
