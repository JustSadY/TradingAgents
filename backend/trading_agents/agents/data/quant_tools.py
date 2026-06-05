import pandas as pd
import numpy as np
from langchain_core.tools import tool
from backend.core.utils import resolve_benchmark

@tool
def get_quant_data(
    ticker: str,
    curr_date: str | None = None
) -> str:
    """Calculate annualized volatility, beta, Sharpe Ratio, and benchmark correlation metrics for a given ticker symbol over the last 1 year."""
    try:
        from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv
        from backend.trading_agents.dataflows.config import get_config
        if not curr_date:
            curr_date = pd.Timestamp.today().strftime("%Y-%m-%d")
        config = get_config()
        benchmark = resolve_benchmark(ticker, config)
        hist = load_ohlcv(ticker, curr_date)
        bench_hist = load_ohlcv(benchmark, curr_date)
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
