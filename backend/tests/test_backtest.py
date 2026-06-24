from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.services.backtest_service import run_backtest_simulation


@pytest.mark.asyncio
async def test_run_backtest_macd_crossover():
    # Mock data for 25 days to allow MACD/RSI warm up calculations (MACD uses 12/26 periods, EMA is fast/slow)
    # Let's provide 30 days of mock prices
    dates = pd.date_range(start="2026-05-01", periods=30)
    mock_df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0 + i for i in range(30)],
            "High": [102.0 + i for i in range(30)],
            "Low": [98.0 + i for i in range(30)],
            "Close": [101.0 + i for i in range(30)],
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
            initial_capital=100000.0,
            user=None,
        )
        assert "error" not in res
        assert res["initial_capital"] == 100000.0
        assert len(res["equity_curve"]) > 0
        assert "trades_count" in res
        assert "win_rate" in res
        assert "max_drawdown" in res
        assert "sharpe_ratio" in res


@pytest.mark.asyncio
async def test_run_backtest_rsi_oversold():
    dates = pd.date_range(start="2026-05-01", periods=30)
    # Generate prices that cross above/below oversold
    mock_df = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * 30,
            "High": [102.0] * 30,
            "Low": [98.0] * 30,
            "Close": [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 60.0, 70.0, 80.0, 90.0] * 3,
            "Volume": [1000] * 30,
        }
    )

    with patch("backend.services.backtest_service.load_ohlcv", return_value=mock_df):
        res = await run_backtest_simulation(
            db=MagicMock(),
            ticker="AAPL",
            strategy_type="rsi_oversold",
            start_date="2026-05-15",
            end_date="2026-05-30",
            initial_capital=100000.0,
            user=None,
        )
        assert "error" not in res
        assert res["initial_capital"] == 100000.0
        assert "trades" in res
