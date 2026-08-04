import ast
import logging
import re

import pandas as pd

_logger = logging.getLogger(__name__)

def calculate_ema(prices: pd.Series, span: int = 20) -> pd.Series:
    """Compute Exponential Moving Average."""
    return prices.ewm(span=span, adjust=False).mean()

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder's smoothed-average method.

    Uses an exponential (Wilder) average with ``alpha = 1/period`` — the
    standard RSI — rather than a plain rolling mean, and guards against a
    zero average loss so a flat/rising window yields RSI≈100 instead of NaN.
    """
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    # RSI edge cases need explicit treatment: no gains and no losses is a
    # flat, neutral market (50), while gains without losses is 100 and losses
    # without gains is 0.
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    no_losses = (avg_loss == 0) & (avg_gain > 0)
    no_gains = (avg_gain == 0) & (avg_loss > 0)
    rs = avg_gain / avg_loss.where(avg_loss != 0)
    rsi = 100 - (100 / (1 + rs))
    return rsi.mask(both_zero, 50.0).mask(no_losses, 100.0).mask(no_gains, 0.0)

def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    """Compute MACD line and signal line."""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    return macd_line, signal_line

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average Directional Index (ADX)."""
    high = df["High"]
    low = df["Low"]

    up_move = high.diff()
    down_move = low.shift(1) - low

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr = calculate_atr(df, period)

    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(window=period).mean()
    return adx

def calculate_ichimoku(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Compute Ichimoku Cloud components."""
    high_9 = df["High"].rolling(window=9).max()
    low_9 = df["Low"].rolling(window=9).min()
    tenkan_sen = (high_9 + low_9) / 2

    high_26 = df["High"].rolling(window=26).max()
    low_26 = df["Low"].rolling(window=26).min()
    kijun_sen = (high_26 + low_26) / 2

    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

    high_52 = df["High"].rolling(window=52).max()
    low_52 = df["Low"].rolling(window=52).min()
    senkou_span_b = ((high_52 + low_52) / 2).shift(26)

    chikou_span = df["Close"].shift(-26)

    return {
        "tenkan_sen": tenkan_sen,
        "kijun_sen": kijun_sen,
        "senkou_span_a": senkou_span_a,
        "senkou_span_b": senkou_span_b,
        "chikou_span": chikou_span,
    }

def calculate_fibonacci_levels(df: pd.DataFrame, period: int = 100) -> dict[str, float]:
    """Calculate Fibonacci Retracement levels based on a period high/low."""
    recent_df = df.tail(period)
    high = recent_df["High"].max()
    low = recent_df["Low"].min()
    diff = high - low

    return {
        "level_0": high,
        "level_236": high - 0.236 * diff,
        "level_382": high - 0.382 * diff,
        "level_500": high - 0.5 * diff,
        "level_618": high - 0.618 * diff,
        "level_786": high - 0.786 * diff,
        "level_100": low,
    }

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Compute rolling Volume-Weighted Average Price over *period* bars."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    price_volume = (typical_price * df["Volume"]).rolling(window=period).sum()
    return price_volume / df["Volume"].rolling(window=period).sum()

_FORMULA_FUNCS: dict = {
    "VOLSMA": lambda df, n: df["Volume"].rolling(window=n).mean(),
    "VWAP": lambda df, n: calculate_vwap(df, n),
    "SHIFT": lambda df, n: df["Close"].shift(n),
    "SMA": lambda df, n: df["Close"].rolling(window=n).mean(),
    "EMA": lambda df, n: calculate_ema(df["Close"], n),
    "STD": lambda df, n: df["Close"].rolling(window=n).std(),
    "RSI": lambda df, n: calculate_rsi(df["Close"], n),
    "ADX": lambda df, n: calculate_adx(df, n),
    "ATR": lambda df, n: calculate_atr(df, n),
    "MAX": lambda df, n: df["High"].rolling(window=n).max(),
    "MIN": lambda df, n: df["Low"].rolling(window=n).min(),
}

def evaluate_formula_safely(df: pd.DataFrame, formula: str) -> pd.Series:
    """Evaluate a bounded, causal arithmetic indicator expression.

    Only current/past series and whitelisted rolling functions are permitted.
    Attribute access, subscripting, arbitrary function calls, and future shifts
    are rejected before pandas evaluates the expression.
    """
    formula = (formula or "").strip()
    if not formula or len(formula) > 300:
        raise ValueError("Formula must contain between 1 and 300 characters")
    if any(token in formula for token in (".", "[", "]", "{", "}", "'", '"', ";", "__")):
        raise ValueError("Formula contains unsupported syntax")

    processed_formula = formula
    local_dict = {
        "Open": df["Open"],
        "High": df["High"],
        "Low": df["Low"],
        "Close": df["Close"],
        "Volume": df["Volume"],
    }

    for name, func in _FORMULA_FUNCS.items():
        pattern = rf"\b{name}\s*\(\s*([+-]?\d+)\s*\)"
        for match in list(re.finditer(pattern, processed_formula, re.IGNORECASE)):
            n = int(match.group(1))
            if n < 1 or n > 500:
                raise ValueError(f"{name} period must be between 1 and 500")
            col_name = f"{name}_{n}"
            if col_name not in local_dict:
                local_dict[col_name] = func(df, n)
            processed_formula = re.sub(
                re.escape(match.group(0)), col_name, processed_formula, flags=re.IGNORECASE
            )

    # Any letters followed by '(' are an unrecognized function call.
    if re.search(r"[A-Za-z_]\w*\s*\(", processed_formula):
        raise ValueError("Formula contains an unsupported function")

    try:
        tree = ast.parse(processed_formula, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Formula syntax is invalid") from exc

    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError("Formula contains unsupported operations")
        if isinstance(node, ast.Name) and node.id not in local_dict:
            raise ValueError(f"Unknown formula symbol: {node.id}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("Formula constants must be numeric")

    try:
        res = pd.eval(processed_formula, local_dict=local_dict, engine="python")
        if isinstance(res, (int, float)):
            series = pd.Series([res] * len(df), index=df.index, dtype="float64")
        else:
            series = pd.to_numeric(pd.Series(res, index=df.index), errors="coerce")
        import numpy as np

        finite = np.isfinite(series.to_numpy(dtype="float64", na_value=np.nan))
        if not bool(finite.all()):
            raise ValueError("Formula result contains non-finite values")
        # Prevent huge finite values from later overflowing JSON/plotting code.
        if bool((series.abs() > 1e100).any()):
            raise ValueError("Formula result is outside the supported numeric range")
        return series
    except Exception as exc:
        _logger.warning("Custom formula evaluation failed: %s", exc)
        raise ValueError("Formula could not be calculated") from exc

async def fetch_sector(ticker: str) -> str:
    import asyncio

    import yfinance as yf

    try:
        info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
        return info.get("sector") or "Unknown"
    except Exception as exc:
        _logger.debug("Could not fetch sector for ticker %s: %s", ticker, exc)
        return "Unknown"
