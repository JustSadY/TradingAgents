import asyncio
import json
import logging
import math

import pandas as pd
from sqlalchemy import select

from backend.models.analysis import AnalysisResult
from backend.services.indicator_service import calculate_macd, calculate_rsi
from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv

_logger = logging.getLogger(__name__)

_COMMISSION_RATE = 0.001
_MAX_HOLDING_DAYS = 10
_ALLOCATION_PCT = 0.95
_DEFAULT_SLIPPAGE_BPS = 5.0  # 0.05% — worsens every fill against the trader


def _apply_slippage(price: float, action: str, slippage_bps: float) -> float:
    """Worsen a fill price by ``slippage_bps`` in the trader's disadvantage.

    ``action`` is the execution direction: "BUY" pays more, "SELL" receives less.
    ``slippage_bps=0`` is a no-op (byte-identical to no slippage modeling).
    """
    factor = slippage_bps / 10_000.0
    return price * (1 + factor) if action == "BUY" else price * (1 - factor)


def _trade_pnl(side: str, entry_price: float, exit_price: float, size: float, rate: float) -> float:
    """Realized P&L for closing ``size`` units, charging commission on both legs."""
    gross = (exit_price - entry_price) * size if side == "long" else (entry_price - exit_price) * size
    return gross - (exit_price * size * rate) - (entry_price * size * rate)


def _close_position(
    side: str,
    entry_price: float,
    exit_price: float,
    size: float,
    entry_date: str,
    exit_date: str,
    reason: str,
    rate: float,
) -> tuple[float, dict]:
    """Close a position: return ``(cash_delta, trade_record)``.

    A long returns its notional plus P&L to cash; a short returns only P&L
    (its collateral was never deducted on entry).
    """
    pnl = _trade_pnl(side, entry_price, exit_price, size, rate)
    cash_delta = (exit_price * size + pnl) if side == "long" else pnl
    trade = {
        "entry_date": entry_date,
        "exit_date": exit_date,
        "side": side,
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "return_pct": round((pnl / (entry_price * size)) * 100, 2),
        "pnl": round(pnl, 2),
        "reason": reason,
    }
    return cash_delta, trade


def _prepare_data(data: pd.DataFrame, strategy_type: str) -> pd.DataFrame:
    """Sort by date and attach the indicator columns the strategy needs."""
    data["Date"] = pd.to_datetime(data["Date"])
    data = data.sort_values("Date").reset_index(drop=True)

    close_series = data["Close"]
    if strategy_type == "macd_crossover":
        macd, signal = calculate_macd(close_series)
        data["macd"] = macd
        data["macd_signal"] = signal
    elif strategy_type == "rsi_oversold":
        data["rsi"] = calculate_rsi(close_series)
    return data


def _generate_signal(data: pd.DataFrame, row, strategy_type: str, analyses_map: dict):
    """Return ``(signal, rec_stop_loss, rec_take_profit)`` for the current day."""
    signal = None
    rec_stop_loss = None
    rec_take_profit = None

    if strategy_type in ("macd_crossover", "rsi_oversold"):
        orig_idx = data[data["Date"] == row["Date"]].index[0]
        if orig_idx <= 0:
            return signal, rec_stop_loss, rec_take_profit
        if strategy_type == "macd_crossover":
            prev_macd = data.loc[orig_idx - 1, "macd"]
            prev_signal = data.loc[orig_idx - 1, "macd_signal"]
            curr_macd = data.loc[orig_idx, "macd"]
            curr_signal = data.loc[orig_idx, "macd_signal"]
            if curr_macd > curr_signal and prev_macd <= prev_signal:
                signal = "BUY"
            elif curr_macd < curr_signal and prev_macd >= prev_signal:
                signal = "SELL"
        else:
            prev_rsi = data.loc[orig_idx - 1, "rsi"]
            curr_rsi = data.loc[orig_idx, "rsi"]
            if curr_rsi < 30 and prev_rsi >= 30:
                signal = "BUY"
            elif curr_rsi > 70 and prev_rsi <= 70:
                signal = "SELL"
    elif strategy_type == "consensus":
        analysis = analyses_map.get(row["Date"].strftime("%Y-%m-%d"))
        if analysis:
            sig = (analysis.signal or "").strip().lower()
            if sig in ("buy", "overweight"):
                signal = "BUY"
            elif sig in ("sell", "underweight"):
                signal = "SELL"

            ann = analysis.chart_annotations
            if isinstance(ann, str):
                try:
                    ann = json.loads(ann)
                except Exception as exc:
                    _logger.debug("Skipping malformed chart annotations in backtest: %s", exc)
                    ann = {}
            if isinstance(ann, dict):
                rec_stop_loss = ann.get("stop_loss")
                rec_take_profit = ann.get("target_price")

    return signal, rec_stop_loss, rec_take_profit


def _exit_reason_and_price(
    side: str,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    stop_loss,
    take_profit,
    holding_days: int,
) -> tuple[str | None, float]:
    """Decide whether an open position exits today and at what fill price."""
    if side == "long":
        if stop_loss is not None and low_price <= stop_loss:
            return "STOP_LOSS", min(open_price, stop_loss)
        if take_profit is not None and high_price >= take_profit:
            return "TAKE_PROFIT", max(open_price, take_profit)
    elif side == "short":
        if stop_loss is not None and high_price >= stop_loss:
            return "STOP_LOSS", max(open_price, stop_loss)
        if take_profit is not None and low_price <= take_profit:
            return "TAKE_PROFIT", min(open_price, take_profit)
    if holding_days >= _MAX_HOLDING_DAYS:
        return "MAX_HOLDING_DAYS", close_price
    return None, close_price


def _compute_metrics(daily_values: list[float], trades: list[dict], initial_capital: float) -> dict:
    """Summary performance stats: return, win rate, Sharpe, max drawdown."""
    final_value = daily_values[-1]
    total_return = (final_value - initial_capital) / initial_capital

    winning_trades = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = winning_trades / len(trades) if trades else 0.0

    daily_returns = []
    for i in range(1, len(daily_values)):
        prev = daily_values[i - 1]
        curr = daily_values[i]
        daily_returns.append((curr - prev) / prev if prev > 0 else 0)

    mean_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
    var_return = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns) if daily_returns else 0.0
    std_return = math.sqrt(var_return)
    sharpe_ratio = (mean_return / std_return) * math.sqrt(252) if std_return > 0 else 0.0

    max_dd = 0.0
    peak = daily_values[0]
    for val in daily_values:
        if val > peak:
            peak = val
        dd = (val - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    return {
        "final_value": round(final_value, 2),
        "total_return": round(total_return * 100, 2),
        "win_rate": round(win_rate * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
    }


async def _benchmark_return(benchmark_ticker: str | None, start_date: str, end_date: str) -> dict | None:
    """Buy-and-hold return of ``benchmark_ticker`` over the same date range.

    Returns ``None`` (never raises) when the benchmark can't be loaded — the
    backtest result itself must never fail over a missing comparison series.
    """
    if not benchmark_ticker:
        return None
    try:
        bench_data = await asyncio.to_thread(load_ohlcv, benchmark_ticker, end_date)
        if bench_data.empty:
            return None
        bench_data["Date"] = pd.to_datetime(bench_data["Date"])
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        window = bench_data[(bench_data["Date"] >= start_dt) & (bench_data["Date"] <= end_dt)]
        if len(window) < 2:
            return None
        first_close = float(window.iloc[0]["Close"])
        last_close = float(window.iloc[-1]["Close"])
        if first_close <= 0:
            return None
        return {
            "ticker": benchmark_ticker,
            "return_pct": round((last_close - first_close) / first_close * 100, 2),
        }
    except Exception as exc:  # noqa: BLE001 — benchmark comparison is best-effort
        _logger.warning("Benchmark fetch failed for %s: %s", benchmark_ticker, exc)
        return None


async def _load_consensus_analyses(db, ticker: str, start_date: str, end_date: str, user) -> dict:
    """Map trade_date -> AnalysisResult for the consensus strategy (user-scoped)."""
    analyses_map: dict = {}
    if not user:
        return analyses_map
    stmt = select(AnalysisResult).where(
        AnalysisResult.ticker == ticker.upper(),
        AnalysisResult.trade_date >= start_date,
        AnalysisResult.trade_date <= end_date,
        AnalysisResult.user_id == user.id,
    )
    res = await db.execute(stmt)
    for row in res.scalars().all():
        analyses_map[row.trade_date] = row
    return analyses_map


async def run_backtest_simulation(
    db,
    ticker: str,
    strategy_type: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    user=None,
    slippage_bps: float = _DEFAULT_SLIPPAGE_BPS,
    benchmark_ticker: str | None = "SPY",
) -> dict:
    try:
        data = await asyncio.to_thread(load_ohlcv, ticker, end_date)
        if data.empty or len(data) < 20:
            return {"error": f"Not enough historical price data for {ticker}."}

        data = _prepare_data(data, strategy_type)

        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        backtest_data = data[(data["Date"] >= start_dt) & (data["Date"] <= end_dt)].copy()
        if backtest_data.empty:
            return {"error": f"No trading days found in the range {start_date} to {end_date}."}

        analyses_map = {}
        if strategy_type == "consensus":
            analyses_map = await _load_consensus_analyses(db, ticker, start_date, end_date, user)

        cash = initial_capital
        position_size = 0.0
        entry_price = 0.0
        position_side = None
        entry_date = None
        stop_loss = None
        take_profit = None
        holding_days = 0

        trades = []
        equity_curve = []
        daily_values = []

        for _idx, row in backtest_data.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            close_price = float(row["Close"])
            high_price = float(row["High"])
            low_price = float(row["Low"])
            open_price = float(row["Open"])

            exited = False
            if position_side is not None:
                holding_days += 1
                exit_reason, exit_price = _exit_reason_and_price(
                    position_side, open_price, high_price, low_price, close_price, stop_loss, take_profit, holding_days
                )
                if exit_reason:
                    exit_price = _apply_slippage(exit_price, "SELL" if position_side == "long" else "BUY", slippage_bps)
                    cash_delta, trade = _close_position(
                        position_side,
                        entry_price,
                        exit_price,
                        position_size,
                        entry_date,
                        date_str,
                        exit_reason,
                        _COMMISSION_RATE,
                    )
                    cash += cash_delta
                    trades.append(trade)
                    position_side = None
                    position_size = 0.0
                    stop_loss = None
                    take_profit = None
                    holding_days = 0
                    exited = True

            if not exited:
                signal, rec_stop_loss, rec_take_profit = _generate_signal(data, row, strategy_type, analyses_map)

                if signal == "BUY" and position_side != "long":
                    if position_side == "short":
                        cover_price = _apply_slippage(close_price, "BUY", slippage_bps)
                        cash_delta, trade = _close_position(
                            "short",
                            entry_price,
                            cover_price,
                            position_size,
                            entry_date,
                            date_str,
                            "SIGNAL",
                            _COMMISSION_RATE,
                        )
                        cash += cash_delta
                        trades.append(trade)
                        position_side = None
                        position_size = 0.0

                    fill_price = _apply_slippage(close_price, "BUY", slippage_bps)
                    allocated = cash * _ALLOCATION_PCT
                    position_size = allocated / fill_price
                    commission = allocated * _COMMISSION_RATE
                    cash -= allocated + commission
                    entry_price = fill_price
                    entry_date = date_str
                    position_side = "long"
                    holding_days = 0
                    stop_loss = float(rec_stop_loss) if rec_stop_loss else fill_price * 0.95
                    take_profit = float(rec_take_profit) if rec_take_profit else fill_price * 1.10

                elif signal == "SELL" and position_side != "short":
                    if position_side == "long":
                        sell_price = _apply_slippage(close_price, "SELL", slippage_bps)
                        cash_delta, trade = _close_position(
                            "long",
                            entry_price,
                            sell_price,
                            position_size,
                            entry_date,
                            date_str,
                            "SIGNAL",
                            _COMMISSION_RATE,
                        )
                        cash += cash_delta
                        trades.append(trade)
                        position_side = None
                        position_size = 0.0

                    fill_price = _apply_slippage(close_price, "SELL", slippage_bps)
                    allocated = cash * _ALLOCATION_PCT
                    position_size = allocated / fill_price
                    commission = allocated * _COMMISSION_RATE
                    cash -= commission
                    entry_price = fill_price
                    entry_date = date_str
                    position_side = "short"
                    holding_days = 0
                    stop_loss = float(rec_stop_loss) if rec_stop_loss else fill_price * 1.05
                    take_profit = float(rec_take_profit) if rec_take_profit else fill_price * 0.90

            holdings_value = 0.0
            if position_side == "long":
                holdings_value = position_size * close_price
            elif position_side == "short":
                holdings_value = (entry_price - close_price) * position_size

            total_value = cash + holdings_value
            daily_values.append(total_value)
            equity_curve.append(
                {
                    "date": date_str,
                    "value": round(total_value, 2),
                    "cash": round(cash, 2),
                    "holdings_value": round(holdings_value, 2),
                }
            )

        if position_side is not None:
            last_day = backtest_data.iloc[-1]
            date_str = last_day["Date"].strftime("%Y-%m-%d")
            close_price = float(last_day["Close"])
            exit_price = _apply_slippage(close_price, "SELL" if position_side == "long" else "BUY", slippage_bps)
            cash_delta, trade = _close_position(
                position_side,
                entry_price,
                exit_price,
                position_size,
                entry_date,
                date_str,
                "END_OF_SIMULATION",
                _COMMISSION_RATE,
            )
            cash += cash_delta
            trades.append(trade)

            equity_curve[-1] = {
                "date": date_str,
                "value": round(cash, 2),
                "cash": round(cash, 2),
                "holdings_value": 0.0,
            }
            daily_values[-1] = cash

        metrics = _compute_metrics(daily_values, trades, initial_capital)
        benchmark = await _benchmark_return(benchmark_ticker, start_date, end_date)
        alpha_pct = round(metrics["total_return"] - benchmark["return_pct"], 2) if benchmark else None
        return {
            "initial_capital": initial_capital,
            "final_value": metrics["final_value"],
            "total_return": metrics["total_return"],
            "win_rate": metrics["win_rate"],
            "max_drawdown": metrics["max_drawdown"],
            "sharpe_ratio": metrics["sharpe_ratio"],
            "trades_count": len(trades),
            "trades": trades,
            "equity_curve": equity_curve,
            "slippage_bps": slippage_bps,
            "benchmark": benchmark,
            "alpha_pct": alpha_pct,
        }

    except Exception as e:
        _logger.exception("Backtest run failed: %s", e)
        return {"error": f"Error running simulation: {str(e)}"}
