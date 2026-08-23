"""Mean-variance weights are advisory, so the guardrails are the contract.

The optimizer must never return a solution built on too little data, on a
single asset, or on prices it silently failed to load — a plausible-looking
weight vector is worse than an error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import portfolio_optimizer_service as svc
from backend.services.portfolio_optimizer_service import (
    MIN_OBSERVATIONS,
    OptimizerError,
    optimize_weights,
)

_AS_OF = "2026-08-20"


def _prices(tickers: list[str], rows: int = 400, seed: int = 3) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=_AS_OF, periods=rows)
    frames = {}
    for offset, ticker in enumerate(tickers):
        close = 100 + np.cumsum(rng.normal(0.05 + offset * 0.02, 1.0, rows))
        frames[ticker] = pd.DataFrame({"Date": dates, "Close": np.abs(close) + 10})
    return frames


@pytest.fixture
def loader(monkeypatch):
    def install(frames: dict[str, pd.DataFrame]):
        def fake_load(ticker: str, _as_of: str) -> pd.DataFrame:
            if ticker not in frames:
                raise RuntimeError(f"no data for {ticker}")
            return frames[ticker]

        monkeypatch.setattr(svc, "load_ohlcv", fake_load)

    return install


class TestGuardrails:
    def test_a_single_ticker_is_rejected(self, loader):
        loader(_prices(["AAPL"]))
        with pytest.raises(OptimizerError, match="at least two distinct"):
            optimize_weights(["AAPL", "aapl", " AAPL "], _AS_OF)

    def test_an_unknown_objective_is_rejected(self, loader):
        loader(_prices(["AAPL", "MSFT"]))
        with pytest.raises(OptimizerError, match="Unknown objective"):
            optimize_weights(["AAPL", "MSFT"], _AS_OF, objective="moon")

    def test_too_many_tickers_are_rejected(self, loader):
        loader({})
        with pytest.raises(OptimizerError, match="At most"):
            optimize_weights([f"T{i}" for i in range(31)], _AS_OF)

    def test_a_ticker_whose_prices_fail_to_load_does_not_produce_a_solution(self, loader):
        loader(_prices(["AAPL"]))
        with pytest.raises(OptimizerError, match="at least two tickers"):
            optimize_weights(["AAPL", "MSFT"], _AS_OF)

    def test_too_short_a_history_is_rejected(self, loader):
        loader(_prices(["AAPL", "MSFT"], rows=MIN_OBSERVATIONS - 1))
        with pytest.raises(OptimizerError, match="overlapping trading days"):
            optimize_weights(["AAPL", "MSFT"], _AS_OF)


class TestSolution:
    def test_weights_are_non_negative_and_sum_to_one(self, loader):
        loader(_prices(["AAPL", "MSFT", "NVDA"]))
        result = optimize_weights(["AAPL", "MSFT", "NVDA"], _AS_OF)

        assert set(result["weights"]) <= {"AAPL", "MSFT", "NVDA"}
        assert all(weight > 0 for weight in result["weights"].values())
        assert sum(result["weights"].values()) == pytest.approx(1.0, abs=1e-3)

    def test_minimum_volatility_is_not_riskier_than_maximum_sharpe(self, loader):
        loader(_prices(["AAPL", "MSFT", "NVDA"]))
        sharpe = optimize_weights(["AAPL", "MSFT", "NVDA"], _AS_OF, objective="max_sharpe")
        low_vol = optimize_weights(["AAPL", "MSFT", "NVDA"], _AS_OF, objective="min_volatility")

        assert low_vol["annual_volatility"] <= sharpe["annual_volatility"] + 1e-9

    def test_no_allocation_is_computed_without_a_portfolio_value(self, loader):
        loader(_prices(["AAPL", "MSFT"]))
        result = optimize_weights(["AAPL", "MSFT"], _AS_OF)

        assert result["allocation"] is None
        assert result["leftover_cash"] is None

    def test_a_discrete_allocation_spends_no_more_than_the_portfolio(self, loader):
        frames = _prices(["AAPL", "MSFT", "NVDA"])
        loader(frames)
        result = optimize_weights(["AAPL", "MSFT", "NVDA"], _AS_OF, total_value=50_000)

        latest = {ticker: float(frame["Close"].iloc[-1]) for ticker, frame in frames.items()}
        spent = sum(shares * latest[ticker] for ticker, shares in result["allocation"].items())

        assert all(isinstance(shares, int) and shares >= 0 for shares in result["allocation"].values())
        assert spent <= 50_000
        assert result["leftover_cash"] == pytest.approx(50_000 - spent, abs=0.01)
