import logging
import math
import json
import pandas as pd
from sqlalchemy import select
from datetime import datetime
from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv
from backend.services.indicator_service import calculate_macd, calculate_rsi
from backend.models.analysis import AnalysisResult

_logger = logging.getLogger(__name__)

async def run_backtest_simulation(
    db,
    ticker: str,
    strategy_type: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    user = None,
) -> dict:
    try:
        # Load daily stock data up to end_date
        data = load_ohlcv(ticker, end_date)
        if data.empty or len(data) < 20:
            return {"error": f"Not enough historical price data for {ticker}."}

        # Ensure Date column is datetime
        data["Date"] = pd.to_datetime(data["Date"])
        
        # Sort values
        data = data.sort_values("Date").reset_index(drop=True)

        # Pre-calculate indicators on all available historical data to prevent cold-start issues
        close_series = data["Close"]
        if strategy_type == "macd_crossover":
            macd, signal = calculate_macd(close_series)
            data["macd"] = macd
            data["macd_signal"] = signal
        elif strategy_type == "rsi_oversold":
            data["rsi"] = calculate_rsi(close_series)

        # Filter dataset to backtest range
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        backtest_data = data[(data["Date"] >= start_dt) & (data["Date"] <= end_dt)].copy()
        
        if backtest_data.empty:
            return {"error": f"No trading days found in the range {start_date} to {end_date}."}

        # Fetch consensus results if applicable
        analyses_map = {}
        if strategy_type == "consensus" and user:
            stmt = select(AnalysisResult).where(
                AnalysisResult.ticker == ticker.upper(),
                AnalysisResult.trade_date >= start_date,
                AnalysisResult.trade_date <= end_date,
                AnalysisResult.user_id == user.id
            )
            res = await db.execute(stmt)
            for row in res.scalars().all():
                analyses_map[row.trade_date] = row

        # Initialize simulation state
        cash = initial_capital
        position_size = 0.0
        entry_price = 0.0
        position_side = None # None, "long", "short"
        entry_date = None
        stop_loss = None
        take_profit = None
        holding_days = 0
        max_holding_days = 10
        commission_rate = 0.001 # 0.1%

        trades = []
        equity_curve = []
        daily_values = []

        # Iterate chronologically day by day
        for idx, row in backtest_data.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            close_price = float(row["Close"])
            high_price = float(row["High"])
            low_price = float(row["Low"])
            open_price = float(row["Open"])

            # 1. Manage existing position exits (breaches & time limits)
            exited = False
            if position_side is not None:
                holding_days += 1
                exit_reason = None
                exit_price = close_price

                # Check Stop-Loss / Take-Profit breaches
                if position_side == "long":
                    if stop_loss is not None and low_price <= stop_loss:
                        exit_price = min(open_price, stop_loss)  # Exit at stop loss or open if gap down
                        exit_reason = "STOP_LOSS"
                    elif take_profit is not None and high_price >= take_profit:
                        exit_price = max(open_price, take_profit) # Exit at target or open if gap up
                        exit_reason = "TAKE_PROFIT"
                    elif holding_days >= max_holding_days:
                        exit_price = close_price
                        exit_reason = "MAX_HOLDING_DAYS"
                elif position_side == "short":
                    if stop_loss is not None and high_price >= stop_loss:
                        exit_price = max(open_price, stop_loss)
                        exit_reason = "STOP_LOSS"
                    elif take_profit is not None and low_price <= take_profit:
                        exit_price = min(open_price, take_profit)
                        exit_reason = "TAKE_PROFIT"
                    elif holding_days >= max_holding_days:
                        exit_price = close_price
                        exit_reason = "MAX_HOLDING_DAYS"

                # If exited, realize PnL
                if exit_reason:
                    notional = position_size * exit_price
                    commission = notional * commission_rate
                    
                    if position_side == "long":
                        pnl = (exit_price - entry_price) * position_size - commission - (entry_price * position_size * commission_rate)
                    else: # short
                        pnl = (entry_price - exit_price) * position_size - commission - (entry_price * position_size * commission_rate)

                    cash += notional + pnl if position_side == "long" else (entry_price * position_size) + pnl
                    return_pct = (pnl / (entry_price * position_size))
                    
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date_str,
                        "side": position_side,
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(exit_price, 2),
                        "return_pct": round(return_pct * 100, 2),
                        "pnl": round(pnl, 2),
                        "reason": exit_reason
                    })

                    position_side = None
                    position_size = 0.0
                    stop_loss = None
                    take_profit = None
                    holding_days = 0
                    exited = True

            # 2. Strategy Signal Entries / Flip Exits
            if not exited:
                signal = None # "BUY", "SELL", or None
                rec_stop_loss = None
                rec_take_profit = None

                # Generate signals based on strategy
                if strategy_type == "macd_crossover":
                    # Check crossover on data index
                    orig_idx = data[data["Date"] == row["Date"]].index[0]
                    if orig_idx > 0:
                        prev_macd = data.loc[orig_idx - 1, "macd"]
                        prev_signal = data.loc[orig_idx - 1, "macd_signal"]
                        curr_macd = data.loc[orig_idx, "macd"]
                        curr_signal = data.loc[orig_idx, "macd_signal"]
                        if curr_macd > curr_signal and prev_macd <= prev_signal:
                            signal = "BUY"
                        elif curr_macd < curr_signal and prev_macd >= prev_signal:
                            signal = "SELL"
                elif strategy_type == "rsi_oversold":
                    orig_idx = data[data["Date"] == row["Date"]].index[0]
                    if orig_idx > 0:
                        prev_rsi = data.loc[orig_idx - 1, "rsi"]
                        curr_rsi = data.loc[orig_idx, "rsi"]
                        # Cross below 30 is Buy, Cross above 70 is Sell
                        if curr_rsi < 30 and prev_rsi >= 30:
                            signal = "BUY"
                        elif curr_rsi > 70 and prev_rsi <= 70:
                            signal = "SELL"
                elif strategy_type == "consensus":
                    analysis = analyses_map.get(date_str)
                    if analysis:
                        sig = (analysis.signal or "").strip().lower()
                        if sig in ("buy", "overweight"):
                            signal = "BUY"
                        elif sig in ("sell", "underweight"):
                            signal = "SELL"
                        
                        # Extract SL/TP if available
                        ann = analysis.chart_annotations
                        if isinstance(ann, str):
                            try:
                                ann = json.loads(ann)
                            except:
                                ann = {}
                        if isinstance(ann, dict):
                            rec_stop_loss = ann.get("stop_loss")
                            rec_take_profit = ann.get("target_price")

                # Process Signal
                if signal == "BUY" and position_side != "long":
                    # Exit short first
                    if position_side == "short":
                        notional = position_size * close_price
                        commission = notional * commission_rate
                        pnl = (entry_price - close_price) * position_size - commission - (entry_price * position_size * commission_rate)
                        cash += (entry_price * position_size) + pnl
                        trades.append({
                            "entry_date": entry_date,
                            "exit_date": date_str,
                            "side": "short",
                            "entry_price": round(entry_price, 2),
                            "exit_price": round(close_price, 2),
                            "return_pct": round((pnl / (entry_price * position_size)) * 100, 2),
                            "pnl": round(pnl, 2),
                            "reason": "SIGNAL"
                        })
                        position_side = None
                        position_size = 0.0

                    # Open Long position
                    allocated = cash * 0.95  # Allocate 95% to allow for commission room
                    position_size = allocated / close_price
                    commission = allocated * commission_rate
                    cash -= (allocated + commission)
                    entry_price = close_price
                    entry_date = date_str
                    position_side = "long"
                    holding_days = 0
                    stop_loss = float(rec_stop_loss) if rec_stop_loss else close_price * 0.95
                    take_profit = float(rec_take_profit) if rec_take_profit else close_price * 1.10

                elif signal == "SELL" and position_side != "short":
                    # Exit long first
                    if position_side == "long":
                        notional = position_size * close_price
                        commission = notional * commission_rate
                        pnl = (close_price - entry_price) * position_size - commission - (entry_price * position_size * commission_rate)
                        cash += notional + pnl
                        trades.append({
                            "entry_date": entry_date,
                            "exit_date": date_str,
                            "side": "long",
                            "entry_price": round(entry_price, 2),
                            "exit_price": round(close_price, 2),
                            "return_pct": round((pnl / (entry_price * position_size)) * 100, 2),
                            "pnl": round(pnl, 2),
                            "reason": "SIGNAL"
                        })
                        position_side = None
                        position_size = 0.0

                    # Open Short position
                    allocated = cash * 0.95
                    position_size = allocated / close_price
                    commission = allocated * commission_rate
                    cash -= commission  # short margin is not paid out, cash remains, but we borrow the notional
                    entry_price = close_price
                    entry_date = date_str
                    position_side = "short"
                    holding_days = 0
                    stop_loss = float(rec_stop_loss) if rec_stop_loss else close_price * 1.05
                    take_profit = float(rec_take_profit) if rec_take_profit else close_price * 0.90

            # 3. Calculate Daily Portfolio Value
            holdings_value = 0.0
            if position_side == "long":
                holdings_value = position_size * close_price
            elif position_side == "short":
                # Short equity = initial short value + short pnl = (entry_price * size) + (entry_price - close_price) * size
                pnl = (entry_price - close_price) * position_size
                holdings_value = (entry_price * position_size) + pnl
            
            total_value = cash + holdings_value
            daily_values.append(total_value)
            equity_curve.append({
                "date": date_str,
                "value": round(total_value, 2),
                "cash": round(cash, 2),
                "holdings_value": round(holdings_value, 2)
            })

        # Close out any remaining position at the end of the simulation
        if position_side is not None:
            last_day = backtest_data.iloc[-1]
            date_str = last_day["Date"].strftime("%Y-%m-%d")
            close_price = float(last_day["Close"])
            notional = position_size * close_price
            commission = notional * commission_rate
            
            if position_side == "long":
                pnl = (close_price - entry_price) * position_size - commission - (entry_price * position_size * commission_rate)
            else: # short
                pnl = (entry_price - close_price) * position_size - commission - (entry_price * position_size * commission_rate)

            cash += notional + pnl if position_side == "long" else (entry_price * position_size) + pnl
            return_pct = (pnl / (entry_price * position_size))
            
            trades.append({
                "entry_date": entry_date,
                "exit_date": date_str,
                "side": position_side,
                "entry_price": round(entry_price, 2),
                "exit_price": round(close_price, 2),
                "return_pct": round(return_pct * 100, 2),
                "pnl": round(pnl, 2),
                "reason": "END_OF_SIMULATION"
            })
            
            # Recalculate last equity curve value
            equity_curve[-1] = {
                "date": date_str,
                "value": round(cash, 2),
                "cash": round(cash, 2),
                "holdings_value": 0.0
            }
            daily_values[-1] = cash

        # Calculate final metrics
        final_value = daily_values[-1]
        total_return = (final_value - initial_capital) / initial_capital

        # Win rate
        winning_trades = sum(1 for t in trades if t["pnl"] > 0)
        win_rate = winning_trades / len(trades) if trades else 0.0

        # Sharpe ratio
        daily_returns = []
        for i in range(1, len(daily_values)):
            prev = daily_values[i-1]
            curr = daily_values[i]
            daily_returns.append((curr - prev) / prev if prev > 0 else 0)

        mean_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
        var_return = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns) if daily_returns else 0.0
        std_return = math.sqrt(var_return)
        
        sharpe_ratio = 0.0
        if std_return > 0:
            # Annualize daily Sharpe ratio
            sharpe_ratio = (mean_return / std_return) * math.sqrt(252)

        # Max drawdown
        max_dd = 0.0
        peak = daily_values[0]
        for val in daily_values:
            if val > peak:
                peak = val
            dd = (val - peak) / peak if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd

        return {
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "total_return": round(total_return * 100, 2),
            "win_rate": round(win_rate * 100, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "trades_count": len(trades),
            "trades": trades,
            "equity_curve": equity_curve
        }

    except Exception as e:
        _logger.exception("Backtest run failed: %s", e)
        return {"error": f"Error running simulation: {str(e)}"}
