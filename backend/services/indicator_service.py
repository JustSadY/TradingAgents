import logging
import re

import pandas as pd

_logger = logging.getLogger(__name__)

def calculate_ema(prices: pd.Series, span: int = 20) -> pd.Series:
    """Compute Exponential Moving Average."""
    return prices.ewm(span=span, adjust=False).mean()

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI using Wilder's smoothed-average method."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

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
    close = df["Close"]

    plus_dm = high.diff()
    minus_dm = low.diff()

    # DM calculation logic
    plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm.abs()), 0)
    minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm.abs()), 0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

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

def evaluate_formula_safely(df: pd.DataFrame, formula: str) -> pd.Series:
    """Evaluates a mathematical formula containing technical indicators."""
    processed_formula = formula
    local_dict = {
        "Open": df["Open"], "High": df["High"], "Low": df["Low"],
        "Close": df["Close"], "Volume": df["Volume"],
    }

    # SMA/EMA/STD/RSI/ADX extraction (case-insensitive)
    patterns = {
        r"SMA\s*\(\s*(\d+)\s*\)": lambda n: df["Close"].rolling(window=n).mean(),
        r"EMA\s*\(\s*(\d+)\s*\)": lambda n: calculate_ema(df["Close"], n),
        r"STD\s*\(\s*(\d+)\s*\)": lambda n: df["Close"].rolling(window=n).std(),
        r"RSI\s*\(\s*(\d+)\s*\)": lambda n: calculate_rsi(df["Close"], n),
        r"ADX\s*\(\s*(\d+)\s*\)": lambda n: calculate_adx(df, n),
    }

    for pattern, func in patterns.items():
        for m in re.finditer(pattern, formula, re.IGNORECASE):
            n = int(m.group(1))
            col_name = f"{pattern[:3]}_{n}"
            if col_name not in local_dict:
                local_dict[col_name] = func(n)
            processed_formula = re.sub(re.escape(m.group(0)), col_name, processed_formula, flags=re.IGNORECASE)

    try:
        res = pd.eval(processed_formula, local_dict=local_dict, engine="python")
        if isinstance(res, (int, float)):
            return pd.Series([res] * len(df), index=df.index)
        return pd.Series(res, index=df.index)
    except Exception as e:
        _logger.error("Error evaluating formula %s: %s", formula, e)
        raise ValueError(f"Formula could not be calculated: {str(e)}")
