"""Mean-variance portfolio weights from PyPortfolioOpt.

This is advisory and separate from ``portfolio_rebalance_planner``, which
enforces the deterministic concentration policy in exact decimal arithmetic.
An optimizer answers a different question — what weights a covariance estimate
implies — so its output is a proposal, never an execution instruction.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import pandas as pd
from pypfopt import EfficientFrontier, expected_returns, objective_functions, risk_models
from pypfopt.discrete_allocation import DiscreteAllocation

from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv

_logger = logging.getLogger(__name__)

Objective = Literal["max_sharpe", "min_volatility", "max_quadratic_utility"]

OBJECTIVES: dict[str, dict[str, str]] = {
    "max_sharpe": {"label": "Maximum Sharpe ratio"},
    "min_volatility": {"label": "Minimum volatility"},
    "max_quadratic_utility": {"label": "Maximum quadratic utility"},
}

MIN_TICKERS = 2
MAX_TICKERS = 30
MIN_OBSERVATIONS = 60


class OptimizerError(Exception):
    """A request the optimizer cannot answer."""


def _price_frame(tickers: list[str], as_of: str) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {}
    for ticker in tickers:
        try:
            frame = load_ohlcv(ticker, as_of)
        except Exception:
            _logger.warning("Optimizer could not load prices for %s", ticker, exc_info=True)
            continue
        if frame.empty or "Close" not in frame:
            continue
        series = frame.set_index("Date")["Close"].astype(float) if "Date" in frame else frame["Close"].astype(float)
        columns[ticker] = series[~series.index.duplicated(keep="last")]

    if len(columns) < MIN_TICKERS:
        raise OptimizerError("Need usable price history for at least two tickers.")

    prices = pd.DataFrame(columns).sort_index().dropna()
    if len(prices) < MIN_OBSERVATIONS:
        raise OptimizerError(
            f"Need at least {MIN_OBSERVATIONS} overlapping trading days; got {len(prices)}."
        )
    return prices


def _solve(prices: pd.DataFrame, objective: str, risk_aversion: float) -> tuple[dict, tuple]:
    mu = expected_returns.mean_historical_return(prices)
    # Ledoit-Wolf shrinkage keeps the covariance invertible when the lookback is
    # short relative to the number of assets, which a sample covariance is not.
    covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()

    frontier = EfficientFrontier(mu, covariance)

    if objective == "min_volatility":
        # L2 regularisation spreads weight off the few lowest-variance assets;
        # max_sharpe rewrites the problem, so it cannot carry extra objectives.
        frontier.add_objective(objective_functions.L2_reg, gamma=0.1)
        frontier.min_volatility()
    elif objective == "max_quadratic_utility":
        frontier.add_objective(objective_functions.L2_reg, gamma=0.1)
        frontier.max_quadratic_utility(risk_aversion=risk_aversion)
    else:
        frontier.max_sharpe()

    weights = frontier.clean_weights()
    return weights, frontier.portfolio_performance()


def optimize_weights(
    tickers: list[str],
    as_of: str,
    *,
    objective: str = "max_sharpe",
    total_value: float | None = None,
    risk_aversion: float = 1.0,
) -> dict:
    if objective not in OBJECTIVES:
        raise OptimizerError(f"Unknown objective '{objective}'. Expected one of {sorted(OBJECTIVES)}.")

    unique = list(dict.fromkeys(t.strip().upper() for t in tickers if t and t.strip()))
    if len(unique) < MIN_TICKERS:
        raise OptimizerError("Provide at least two distinct tickers.")
    if len(unique) > MAX_TICKERS:
        raise OptimizerError(f"At most {MAX_TICKERS} tickers can be optimized at once.")

    prices = _price_frame(unique, as_of)
    try:
        weights, performance = _solve(prices, objective, risk_aversion)
    except Exception as exc:
        raise OptimizerError(f"The optimizer could not find a solution: {exc}") from exc

    expected_return, volatility, sharpe = performance
    result = {
        "objective": objective,
        "tickers": list(prices.columns),
        "observations": int(len(prices)),
        "weights": {ticker: round(float(weight), 4) for ticker, weight in weights.items() if weight > 0},
        "expected_annual_return": round(float(expected_return), 4),
        "annual_volatility": round(float(volatility), 4),
        "sharpe_ratio": round(float(sharpe), 4),
        "allocation": None,
        "leftover_cash": None,
    }

    if total_value and total_value > 0:
        latest = prices.iloc[-1]
        allocator = DiscreteAllocation(weights, latest, total_portfolio_value=float(total_value))
        allocation, leftover = allocator.greedy_portfolio()
        result["allocation"] = {ticker: int(shares) for ticker, shares in allocation.items()}
        result["leftover_cash"] = round(float(leftover), 2)

    return result


async def optimize_weights_async(tickers: list[str], as_of: str, **kwargs) -> dict:
    return await asyncio.to_thread(optimize_weights, tickers, as_of, **kwargs)
