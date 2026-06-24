"""Adversarial and boundary tests for TradingAgents backend services"""

import math
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.api.correlation import get_correlation
from backend.api.fx import _cache, get_fx_rates
from backend.services.analysis.risk_metrics_service import (
    calculate_beta,
    calculate_correlation,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_volatility,
    get_risk_metrics,
)
from backend.services.backtest_service import run_backtest_simulation
from backend.services.margin_engine import (
    accrue_interest,
    clamp_leverage,
    is_liquidatable_short,
    liquidation_price_long,
    liquidation_price_short,
    margin_required,
    position_equity_short,
)
from backend.services.screener_service import run_screen
from backend.services.signal_backtest_service import (
    get_signal_replay_context,
    render_signal_replay,
)


def test_clamp_leverage_adversarial():
    """Test clamp leverage with negative, zero, invalid, and low max leverage inputs"""
    assert clamp_leverage(-5) == Decimal("1")
    assert clamp_leverage(0) == Decimal("1")
    assert clamp_leverage(1.5) == Decimal("1.5")
    assert clamp_leverage(10, Decimal("0.5")) == Decimal("0.5")
    assert clamp_leverage("invalid") == Decimal("1")


def test_margin_required_adversarial():
    """Test margin requirement with extremely low leverage and negative notional"""
    assert margin_required(Decimal("-1000"), Decimal("5")) == Decimal("-200")
    assert margin_required(Decimal("100"), Decimal("0")) == Decimal("100")
    assert margin_required(Decimal("100"), Decimal("1e-25")) == Decimal("1e27")


def test_liquidation_price_long_adversarial():
    """Test long liquidation price with invalid/extreme parameters"""
    assert liquidation_price_long(Decimal("-10"), Decimal("100"), Decimal("0.1")) == Decimal("0")
    assert liquidation_price_long(Decimal("10"), Decimal("-100"), Decimal("0.1")) == Decimal("0")
    assert liquidation_price_long(Decimal("10"), Decimal("100"), Decimal("1.5")) == Decimal("0")
    assert liquidation_price_long(Decimal("10"), Decimal("100"), Decimal("-0.5")) == Decimal("100") / (
        Decimal("10") * Decimal("1.5")
    )
    assert liquidation_price_long(Decimal("1e-10"), Decimal("100"), Decimal("0.9999999999")) > Decimal("1e10")


def test_liquidation_price_short_adversarial():
    """Test short liquidation price with invalid/extreme parameters"""
    assert liquidation_price_short(Decimal("-10"), Decimal("100"), Decimal("50"), Decimal("0.1")) == Decimal("0")
    assert liquidation_price_short(Decimal("10"), Decimal("100"), Decimal("-50"), Decimal("0.1")) == Decimal("0")
    assert liquidation_price_short(Decimal("10"), Decimal("100"), Decimal("50"), Decimal("-0.1")) == (
        Decimal("50") + Decimal("100") * Decimal("10")
    ) / (Decimal("10") * Decimal("0.9"))
    assert position_equity_short(Decimal("10"), Decimal("100"), Decimal("120"), Decimal("50")) == Decimal("50") + (
        Decimal("100") - Decimal("120")
    ) * Decimal("10")
    assert is_liquidatable_short(Decimal("130"), Decimal("120")) is True
    assert is_liquidatable_short(Decimal("110"), Decimal("120")) is False
    assert is_liquidatable_short(Decimal("100"), Decimal("0")) is False


def test_accrue_interest_adversarial():
    """Test interest accrual with zero/negative elapsed time or borrowed amount"""
    assert accrue_interest(Decimal("0"), Decimal("3600")) == Decimal("0")
    assert accrue_interest(Decimal("-1000"), Decimal("3600")) == Decimal("0")
    assert accrue_interest(Decimal("1000"), Decimal("-3600")) == Decimal("0")
    assert accrue_interest(Decimal("1000"), Decimal("0")) == Decimal("0")


def test_risk_metrics_adversarial():
    """Test risk metrics on empty, single-element, constant, and NaN/inf inputs"""
    empty_series = pd.Series([], dtype=float)
    single_series = pd.Series([100.0])
    assert calculate_sharpe_ratio(empty_series) == 0.0
    assert calculate_sharpe_ratio(single_series) == 0.0
    assert calculate_max_drawdown(empty_series) == 0.0
    assert calculate_max_drawdown(single_series) == 0.0
    assert calculate_volatility(empty_series) == 0.0
    assert calculate_volatility(single_series) == 0.0
    assert calculate_beta(empty_series, empty_series) == 1.0
    assert calculate_correlation(empty_series, empty_series) == 0.0

    zero_series = pd.Series([0.0, 0.0, 0.0])
    assert math.isnan(calculate_max_drawdown(zero_series))
    assert calculate_sharpe_ratio(zero_series) == 0.0

    constant_returns = pd.Series([0.01, 0.01, 0.01])
    assert calculate_volatility(constant_returns) == 0.0
    assert calculate_beta(constant_returns, constant_returns) == 1.0

    nan_series = pd.Series([1.0, float("nan"), 3.0])
    metrics = get_risk_metrics(nan_series)
    assert "sharpe_ratio" in metrics


@pytest.mark.asyncio
async def test_backtest_simulation_adversarial():
    """Test backtest simulation under edge conditions including zero capital and short double counting"""
    dates = pd.date_range(start="2026-05-01", periods=30)
    mock_df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 30,
            "High": [101.0] * 30,
            "Low": [99.0] * 30,
            "Close": [100.0] * 30,
            "Volume": [1000] * 30,
        }
    )

    with patch("backend.services.backtest_service.load_ohlcv", return_value=mock_df):
        res = await run_backtest_simulation(
            db=MagicMock(),
            ticker="AAPL",
            strategy_type="macd_crossover",
            start_date="2026-05-15",
            end_date="2026-05-30",
            initial_capital=0.0,
            user=None,
        )
        assert "error" in res


@pytest.mark.asyncio
async def test_backtest_consensus_annotations():
    """Test consensus strategy with malformed and valid chart annotations"""
    dates = pd.date_range(start="2026-05-01", periods=30)
    mock_df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 30,
            "High": [101.0] * 30,
            "Low": [99.0] * 30,
            "Close": [100.0] * 30,
            "Volume": [1000] * 30,
        }
    )

    class FakeRow:
        def __init__(self, date_str, sig, ann):
            self.trade_date = date_str
            self.signal = sig
            self.chart_annotations = ann
            self.ticker = "AAPL"
            self.user_id = 42

    class FakeUser:
        id = 42

    fake_db = MagicMock()
    fake_res = MagicMock()
    fake_res.scalars.return_value.all.return_value = [
        FakeRow("2026-05-20", "buy", "{invalid-json}"),
        FakeRow("2026-05-22", "sell", '{"stop_loss": 98.0, "target_price": 105.0}'),
    ]
    fake_db.execute = AsyncMock(return_value=fake_res)

    with patch("backend.services.backtest_service.load_ohlcv", return_value=mock_df):
        res = await run_backtest_simulation(
            db=fake_db,
            ticker="AAPL",
            strategy_type="consensus",
            start_date="2026-05-15",
            end_date="2026-05-30",
            initial_capital=10000.0,
            user=FakeUser(),
        )
        assert "error" not in res
        assert res["initial_capital"] == 10000.0


@pytest.mark.asyncio
async def test_backtest_short_double_counting_bug():
    """Expose the short position double-counting bug at end of simulation"""
    dates = pd.date_range(start="2026-05-01", periods=30)
    mock_df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 30,
            "High": [100.0] * 30,
            "Low": [100.0] * 30,
            "Close": [100.0] * 30,
            "Volume": [1000] * 30,
        }
    )

    class FakeRow:
        def __init__(self, date_str, sig):
            self.trade_date = date_str
            self.signal = sig
            self.chart_annotations = "{}"
            self.ticker = "AAPL"
            self.user_id = 42

    class FakeUser:
        id = 42

    fake_db = MagicMock()
    fake_res = MagicMock()
    fake_res.scalars.return_value.all.return_value = [
        FakeRow("2026-05-25", "sell"),
    ]
    fake_db.execute = AsyncMock(return_value=fake_res)

    with patch("backend.services.backtest_service.load_ohlcv", return_value=mock_df):
        res = await run_backtest_simulation(
            db=fake_db,
            ticker="AAPL",
            strategy_type="consensus",
            start_date="2026-05-01",
            end_date="2026-05-30",
            initial_capital=10000.0,
            user=FakeUser(),
        )
        assert "error" not in res
        assert res["final_value"] < 10000.0


def test_signal_replay_adversarial():
    """Test signal replay renderer and context with various edge cases"""

    class FakeRow:
        def __init__(self, sig, ret, date="2025-01-01"):
            self.signal = sig
            self.raw_return = ret
            self.trade_date = date

    rows = [
        FakeRow("Overweight", 4.0),
        FakeRow("Underweight", -2.0),
        FakeRow(None, 1.0),
        FakeRow("Buy", None),
        FakeRow("Sell", "invalid_float"),
    ]

    with pytest.raises((ValueError, TypeError)):
        render_signal_replay("AAPL", rows)

    good_rows = [
        FakeRow("Overweight", 4.0),
        FakeRow("Underweight", -2.0),
    ]
    md = render_signal_replay("AAPL", good_rows)
    assert "Overweight" in md
    assert "Underweight" in md


@pytest.mark.asyncio
async def test_get_signal_replay_context_exception():
    """Test that get_signal_replay_context handles DB exceptions gracefully by returning empty string"""
    bad_db = MagicMock()
    bad_db.execute = AsyncMock(side_effect=RuntimeError("DB block"))
    res = await get_signal_replay_context(bad_db, "AAPL", 1)
    assert res == ""


@pytest.mark.asyncio
async def test_screener_service_adversarial():
    """Test screener service with single ticker, empty downloads, and extreme top_n"""
    mock_empty = pd.DataFrame()
    with patch("yfinance.download", return_value=mock_empty):
        res = await run_screen(["AAPL"], top_n=5)
        assert res == []

    dates = pd.date_range(start="2026-05-01", periods=100)
    single_df = pd.DataFrame(
        {
            "Open": [100.0] * 100,
            "High": [101.0] * 100,
            "Low": [99.0] * 100,
            "Close": [100.0] * 100,
            "Volume": [1000] * 100,
        },
        index=dates,
    )

    with patch("yfinance.download", return_value=single_df):
        res = await run_screen(["AAPL"], top_n=-5)
        assert len(res) <= 1


@pytest.mark.asyncio
async def test_correlation_api_adversarial():
    """Test correlation API with insufficient holdings or download issues"""
    fake_db = MagicMock()
    fake_portfolio = MagicMock()
    fake_portfolio.id = 123

    with patch("backend.api.correlation.get_user_simulation_portfolio", return_value=fake_portfolio):

        class FakeHolding:
            def __init__(self, ticker):
                self.ticker = ticker

        with patch("backend.api.correlation.get_active_holdings", return_value=[FakeHolding("AAPL")]):
            res = await get_correlation(period="90d", db=fake_db, current_user=MagicMock())
            assert "Need at least 2 holdings" in res["warning"]


@pytest.mark.asyncio
async def test_fx_api_adversarial():
    """Test FX rates API and caching mechanism"""
    _cache["rates"] = {}
    _cache["ts"] = 0.0

    class FakeTicker:
        def __init__(self, sym):
            self.sym = sym

        def history(self, period):
            return pd.DataFrame({"Close": [1.25, 1.27]})

    with patch("yfinance.Ticker", side_effect=lambda s: FakeTicker(s)):
        res = await get_fx_rates()
        assert res["EUR"] == 1.27
        assert _cache["rates"]["EUR"] == 1.27

    with patch("backend.api.fx._fetch_rates") as mock_fetch:
        res2 = await get_fx_rates()
        mock_fetch.assert_not_called()
        assert res2["EUR"] == 1.27
