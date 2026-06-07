import numpy as np
import pandas as pd
from typing import Dict, Any

def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """Calculate the annualized Sharpe Ratio."""
    if len(returns) < 2:
        return 0.0
    
    mean_return = returns.mean()
    std_return = returns.std()
    
    if std_return == 0:
        return 0.0
    
    # Assuming daily returns, annualize by multiplying by sqrt(252)
    sharpe = (mean_return - (risk_free_rate / 252)) / std_return
    return float(sharpe * np.sqrt(252))

def calculate_max_drawdown(prices: pd.Series) -> float:
    """Calculate the Maximum Drawdown."""
    if len(prices) < 2:
        return 0.0
    
    rolling_max = prices.cummax()
    drawdown = (prices - rolling_max) / rolling_max
    return float(drawdown.min())

def calculate_volatility(returns: pd.Series) -> float:
    """Calculate the annualized volatility."""
    if len(returns) < 2:
        return 0.0

    # Annualized standard deviation of daily returns
    return float(returns.std() * np.sqrt(252))


def calculate_beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Calculate the Beta of the asset relative to a benchmark."""
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 1.0

    # Align the series to ensure they cover the same dates
    df = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(df) < 2:
        return 1.0

    covariance = df.iloc[:, 0].cov(df.iloc[:, 1])
    benchmark_variance = df.iloc[:, 1].var()

    if benchmark_variance == 0:
        return 1.0

    return float(covariance / benchmark_variance)


def calculate_correlation(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Calculate the correlation coefficient with the benchmark."""
    if len(returns) < 2 or len(benchmark_returns) < 2:
        return 0.0

    df = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(df) < 2:
        return 0.0

    return float(df.iloc[:, 0].corr(df.iloc[:, 1]))


def get_risk_metrics(prices: pd.Series, benchmark_prices: pd.Series | None = None) -> Dict[str, Any]:
    """Return a dictionary of key risk metrics."""
    returns = prices.pct_change().dropna()

    metrics = {
        "sharpe_ratio": round(calculate_sharpe_ratio(returns), 4),
        "max_drawdown": round(calculate_max_drawdown(prices), 4),
        "annualized_volatility": round(calculate_volatility(returns), 4),
    }

    if benchmark_prices is not None:
        bench_returns = benchmark_prices.pct_change().dropna()
        metrics["beta"] = round(calculate_beta(returns, bench_returns), 4)
        metrics["market_correlation"] = round(calculate_correlation(returns, bench_returns), 4)

    return metrics
