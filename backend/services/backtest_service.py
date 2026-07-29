import asyncio
import json
import logging
import math
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import select

from backend.models.analysis import AnalysisResult
from backend.services.indicator_service import calculate_macd, calculate_rsi
from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv

_logger = logging.getLogger(__name__)

_COMMISSION_RATE = Decimal("0.001")
_MAX_HOLDING_DAYS = 10
_ALLOCATION_PCT = Decimal("0.95")
_DEFAULT_SLIPPAGE_BPS = Decimal("5.0")  # 0.05% — worsens every fill against the trader
_MONEY_QUANTUM = Decimal("0.0001")
_ZERO = Decimal("0")


def _decimal(value) -> Decimal:
    """Convert an external numeric value to a finite Decimal exactly once."""
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Expected a finite numeric value, got {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"Expected a finite numeric value, got {value!r}")
    return result


def _money(value: Decimal) -> Decimal:
    """Keep simulated fees at the same precision as the paper broker."""
    return value.quantize(_MONEY_QUANTUM)


def _apply_slippage_decimal(price: Decimal, action: str, slippage_bps: Decimal) -> Decimal:
    factor = slippage_bps / Decimal(10_000)
    return price * (Decimal(1) + factor) if action == "BUY" else price * (Decimal(1) - factor)


def _apply_slippage(price: float, action: str, slippage_bps: float) -> float:
    """Worsen a fill price by ``slippage_bps`` in the trader's disadvantage.

    ``action`` is the execution direction: "BUY" pays more, "SELL" receives less.
    ``slippage_bps=0`` is a no-op (byte-identical to no slippage modeling).

    This public helper keeps its float API for callers/tests.  The simulation
    itself uses ``_apply_slippage_decimal`` and never brings this float back
    into its cash or equity calculations.
    """
    return float(_apply_slippage_decimal(_decimal(price), action, _decimal(slippage_bps)))


def _trade_pnl_decimal(
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    size: Decimal,
    rate: Decimal,
) -> Decimal:
    """All-in trade P&L with the entry and exit fees charged once each."""
    gross = (exit_price - entry_price) * size if side == "long" else (entry_price - exit_price) * size
    entry_commission = _money(entry_price * size * rate)
    exit_commission = _money(exit_price * size * rate)
    return gross - entry_commission - exit_commission


def _trade_pnl(side: str, entry_price: float, exit_price: float, size: float, rate: float) -> float:
    """Realized P&L for closing ``size`` units, charging commission on both legs.

    Float-compatible wrapper around the Decimal implementation used by the
    simulator.
    """
    return float(_trade_pnl_decimal(side, _decimal(entry_price), _decimal(exit_price), _decimal(size), _decimal(rate)))


def _close_position_decimal(
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    size: Decimal,
    entry_date: str,
    exit_date: str,
    reason: str,
    rate: Decimal,
) -> tuple[Decimal, dict]:
    """Close a simulated position without losing Decimal precision.

    Opening commission was already debited from cash.  Its cost remains in
    all-in P&L, while close-leg cash only carries the exit fee to prevent a
    second debit.  This mirrors the simulation broker ledger.
    """
    pnl = _trade_pnl_decimal(side, entry_price, exit_price, size, rate)
    entry_notional = entry_price * size
    exit_notional = exit_price * size
    exit_commission = _money(exit_notional * rate)
    gross_pnl = (exit_price - entry_price) * size if side == "long" else (entry_price - exit_price) * size
    cash_delta = exit_notional - exit_commission if side == "long" else gross_pnl - exit_commission
    entry_commission = _money(entry_notional * rate)
    cost_basis = entry_notional + entry_commission
    return_pct = (pnl / cost_basis * Decimal(100)) if cost_basis > 0 else _ZERO
    trade = {
        "entry_date": entry_date,
        "exit_date": exit_date,
        "side": side,
        "entry_price": round(float(entry_price), 2),
        "exit_price": round(float(exit_price), 2),
        "return_pct": round(float(return_pct), 2),
        "pnl": round(float(pnl), 2),
        "reason": reason,
    }
    return cash_delta, trade


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
    """Float-compatible wrapper around the precise close implementation."""
    cash_delta, trade = _close_position_decimal(
        side,
        _decimal(entry_price),
        _decimal(exit_price),
        _decimal(size),
        entry_date,
        exit_date,
        reason,
        _decimal(rate),
    )
    return float(cash_delta), trade


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


def _generate_signal(
    data: pd.DataFrame,
    row,
    strategy_type: str,
    analyses_map: dict,
    *,
    consensus_signal_date: str | None = None,
):
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
        # A consensus report generated for a trading day cannot be filled at
        # that day's close: the report may itself use that close/that day's
        # full OHLCV data.  The caller supplies the preceding trading date so
        # this bar only acts on information known before its open.
        analysis = analyses_map.get(consensus_signal_date) if consensus_signal_date else None
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


def _normalise_exit_levels(
    side: str,
    entry_price: Decimal | float,
    recommended_stop_loss,
    recommended_take_profit,
) -> tuple[Decimal, Decimal]:
    """Return directionally valid stop/target levels for a simulated entry.

    Analyst annotations are sometimes written as a long plan even when the
    consensus action is ``SELL``.  Invalid levels must not immediately close a
    new short (or make its stop/target impossible); use conservative defaults
    instead.
    """
    entry_price = _decimal(entry_price)

    def _positive_finite(value) -> Decimal | None:
        try:
            parsed = _decimal(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    stop = _positive_finite(recommended_stop_loss)
    target = _positive_finite(recommended_take_profit)
    if side == "short":
        valid_stop = stop if stop is not None and stop > entry_price else entry_price * Decimal("1.05")
        valid_target = target if target is not None and target < entry_price else entry_price * Decimal("0.90")
    else:
        valid_stop = stop if stop is not None and stop < entry_price else entry_price * Decimal("0.95")
        valid_target = target if target is not None and target > entry_price else entry_price * Decimal("1.10")
    return valid_stop, valid_target


def _exit_reason_and_price(
    side: str,
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    stop_loss,
    take_profit,
    holding_days: int,
) -> tuple[str | None, Decimal]:
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


def _compute_metrics(daily_values: list[Decimal], trades: list[dict], initial_capital: Decimal) -> dict:
    """Summary performance stats using exact money/equity values.

    Sharpe requires a square root and is intentionally converted to float only
    after each exact Decimal daily return is calculated.  Cash, P&L, equity,
    total return, and drawdown remain Decimal until API serialization.
    """
    if not daily_values or initial_capital <= 0:
        raise ValueError("Backtest requires positive capital and at least one equity value")

    final_value = daily_values[-1]
    total_return = (final_value - initial_capital) / initial_capital

    winning_trades = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = winning_trades / len(trades) if trades else 0.0

    daily_returns: list[Decimal] = []
    for i in range(1, len(daily_values)):
        prev = daily_values[i - 1]
        curr = daily_values[i]
        daily_returns.append((curr - prev) / prev if prev > 0 else _ZERO)

    mean_return = sum(daily_returns, _ZERO) / len(daily_returns) if daily_returns else _ZERO
    variance = (
        sum(((r - mean_return) ** 2 for r in daily_returns), _ZERO) / len(daily_returns) if daily_returns else _ZERO
    )
    # This is the single intentional float boundary in the accounting path:
    # Sharpe is a statistical display metric, not a monetary ledger field.
    std_return = math.sqrt(float(variance))
    sharpe_ratio = float(mean_return) / std_return * math.sqrt(252) if std_return > 0 else 0.0

    max_dd = _ZERO
    peak = daily_values[0]
    for val in daily_values:
        if val > peak:
            peak = val
        dd = (val - peak) / peak if peak > 0 else _ZERO
        if dd < max_dd:
            max_dd = dd

    return {
        "final_value": round(float(final_value), 2),
        "total_return": round(float(total_return * Decimal(100)), 2),
        "win_rate": round(win_rate * 100, 2),
        "max_drawdown": round(float(max_dd * Decimal(100)), 2),
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
    """Map usable trade-date reports for the user-scoped consensus strategy.

    A historical re-run must not let an analysis created *after* its stated
    trade date influence that past bar.  The simulation consumes each report
    on the next trading bar, so reports are keyed by their own trade date here.
    """
    analyses_map: dict = {}
    if not user:
        return analyses_map
    # Include a short calendar buffer so a Friday report can be consumed on
    # the first Monday inside the requested range.
    query_start = (pd.Timestamp(start_date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    stmt = (
        select(AnalysisResult)
        .where(
            AnalysisResult.ticker == ticker.upper(),
            AnalysisResult.trade_date >= query_start,
            AnalysisResult.trade_date <= end_date,
            AnalysisResult.user_id == user.id,
            AnalysisResult.status == "completed",
        )
        .order_by(AnalysisResult.created_at.asc())
    )
    res = await db.execute(stmt)
    for row in res.scalars().all():
        # ``trade_date`` is stored as ISO text.  Treat a missing timestamp as
        # unavailable rather than silently granting a future-data exception.
        try:
            created_at = getattr(row, "created_at", None)
            if created_at is None or pd.Timestamp(created_at).date() > pd.Timestamp(row.trade_date).date():
                continue
        except (TypeError, ValueError):
            continue
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
    slippage_bps: float | Decimal = _DEFAULT_SLIPPAGE_BPS,
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

        initial_capital_decimal = _decimal(initial_capital)
        if initial_capital_decimal <= 0:
            return {"error": "Initial capital must be positive."}
        slippage_bps_decimal = _decimal(slippage_bps)
        if slippage_bps_decimal < 0:
            return {"error": "Slippage must not be negative."}

        cash = initial_capital_decimal
        position_size = _ZERO
        entry_price = _ZERO
        position_side = None
        entry_date = None
        stop_loss = None
        take_profit = None
        holding_days = 0

        trades = []
        equity_curve = []
        daily_values: list[Decimal] = []

        # Signals are evaluated only after a bar is complete and are filled on
        # the following bar's open.  Seed the first requested bar from the
        # preceding market bar when the data source provides one, so a Friday
        # signal may be acted on at Monday's open without peeking at Monday.
        preceding_data = data[data["Date"] < start_dt]
        previous_row = preceding_data.iloc[-1] if not preceding_data.empty else None
        previous_trade_date: str | None = (
            previous_row["Date"].strftime("%Y-%m-%d") if previous_row is not None else None
        )
        for _idx, row in backtest_data.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            close_price = _decimal(row["Close"])
            high_price = _decimal(row["High"])
            low_price = _decimal(row["Low"])
            open_price = _decimal(row["Open"])

            exited = False
            if position_side is not None:
                holding_days += 1
                exit_reason, exit_price = _exit_reason_and_price(
                    position_side, open_price, high_price, low_price, close_price, stop_loss, take_profit, holding_days
                )
                if exit_reason:
                    exit_price = _apply_slippage_decimal(
                        exit_price,
                        "SELL" if position_side == "long" else "BUY",
                        slippage_bps_decimal,
                    )
                    cash_delta, trade = _close_position_decimal(
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
                    position_size = _ZERO
                    stop_loss = None
                    take_profit = None
                    holding_days = 0
                    exited = True

            if not exited:
                if previous_row is None:
                    signal, rec_stop_loss, rec_take_profit = None, None, None
                else:
                    signal, rec_stop_loss, rec_take_profit = _generate_signal(
                        data,
                        previous_row if strategy_type != "consensus" else row,
                        strategy_type,
                        analyses_map,
                        consensus_signal_date=previous_trade_date,
                    )
                # Every strategy consumes information from a completed prior
                # bar and fills at this bar's open.  Trading at the same close
                # that generated MACD/RSI/consensus input is look-ahead bias.
                execution_price = open_price if open_price > 0 else close_price

                if signal == "BUY" and position_side != "long":
                    if position_side == "short":
                        cover_price = _apply_slippage_decimal(execution_price, "BUY", slippage_bps_decimal)
                        cash_delta, trade = _close_position_decimal(
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
                        position_size = _ZERO

                    fill_price = _apply_slippage_decimal(execution_price, "BUY", slippage_bps_decimal)
                    if cash > 0 and fill_price > 0:
                        allocated = cash * _ALLOCATION_PCT
                        position_size = allocated / fill_price
                        commission = _money(allocated * _COMMISSION_RATE)
                        cash -= allocated + commission
                        entry_price = fill_price
                        entry_date = date_str
                        position_side = "long"
                        holding_days = 0
                        stop_loss, take_profit = _normalise_exit_levels(
                            "long", fill_price, rec_stop_loss, rec_take_profit
                        )

                elif signal == "SELL" and position_side != "short":
                    if position_side == "long":
                        sell_price = _apply_slippage_decimal(execution_price, "SELL", slippage_bps_decimal)
                        cash_delta, trade = _close_position_decimal(
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
                        position_size = _ZERO

                    fill_price = _apply_slippage_decimal(execution_price, "SELL", slippage_bps_decimal)
                    if cash > 0 and fill_price > 0:
                        allocated = cash * _ALLOCATION_PCT
                        position_size = allocated / fill_price
                        commission = _money(allocated * _COMMISSION_RATE)
                        cash -= commission
                        entry_price = fill_price
                        entry_date = date_str
                        position_side = "short"
                        holding_days = 0
                        stop_loss, take_profit = _normalise_exit_levels(
                            "short", fill_price, rec_stop_loss, rec_take_profit
                        )

            holdings_value = _ZERO
            if position_side == "long":
                holdings_value = position_size * close_price
            elif position_side == "short":
                holdings_value = (entry_price - close_price) * position_size

            total_value = cash + holdings_value
            daily_values.append(total_value)
            equity_curve.append(
                {
                    "date": date_str,
                    "value": round(float(total_value), 2),
                    "cash": round(float(cash), 2),
                    "holdings_value": round(float(holdings_value), 2),
                }
            )
            previous_row = row
            previous_trade_date = date_str

        if position_side is not None:
            last_day = backtest_data.iloc[-1]
            date_str = last_day["Date"].strftime("%Y-%m-%d")
            close_price = _decimal(last_day["Close"])
            exit_price = _apply_slippage_decimal(
                close_price,
                "SELL" if position_side == "long" else "BUY",
                slippage_bps_decimal,
            )
            cash_delta, trade = _close_position_decimal(
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
                "value": round(float(cash), 2),
                "cash": round(float(cash), 2),
                "holdings_value": 0.0,
            }
            daily_values[-1] = cash

        metrics = _compute_metrics(daily_values, trades, initial_capital_decimal)
        benchmark = await _benchmark_return(benchmark_ticker, start_date, end_date)
        alpha_pct = round(metrics["total_return"] - benchmark["return_pct"], 2) if benchmark else None
        return {
            "initial_capital": float(initial_capital_decimal),
            "final_value": metrics["final_value"],
            "total_return": metrics["total_return"],
            "win_rate": metrics["win_rate"],
            "max_drawdown": metrics["max_drawdown"],
            "sharpe_ratio": metrics["sharpe_ratio"],
            "trades_count": len(trades),
            "trades": trades,
            "equity_curve": equity_curve,
            "slippage_bps": float(slippage_bps_decimal),
            "benchmark": benchmark,
            "alpha_pct": alpha_pct,
        }

    except Exception as e:
        _logger.exception("Backtest run failed: %s", e)
        return {"error": f"Error running simulation: {str(e)}"}
