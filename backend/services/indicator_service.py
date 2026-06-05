import re
import logging
import pandas as pd
import numpy as np

_logger = logging.getLogger(__name__)

def calculate_rsi(prices: "pd.Series", period: int = 14) -> "pd.Series":
    """Compute RSI using Wilder's smoothed-average method.

    Uses ``clip()`` with a small epsilon to avoid division-by-zero on
    perfectly trending series. This is the canonical RSI implementation
    for the codebase — ``backtest_tools.py`` and ``indicator_service.py``
    both delegate here instead of duplicating the formula.
    """
    delta = prices.diff()
    gain = (delta.clip(lower=0)).rolling(window=period).mean()
    loss = (-1 * delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def calculate_ema(prices: "pd.Series", span: int) -> "pd.Series":
    """Compute exponential moving average with ``adjust=False`` (Wilder/standard style)."""
    return prices.ewm(span=span, adjust=False).mean()


def calculate_macd(
    prices: "pd.Series",
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> "tuple[pd.Series, pd.Series]":
    """Compute MACD line and signal line.

    Returns:
        (macd_line, signal_line) — both are ``pd.Series`` aligned to *prices*.

    This is the canonical MACD implementation for the codebase — replaces
    the inline EWM calculations that were previously duplicated in
    ``backtest_tools.py``.
    """
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    return macd_line, signal_line

def evaluate_formula_safely(df: pd.DataFrame, formula: str) -> pd.Series:
    """
    Evaluates a mathematical formula containing variables like Open, High, Low, Close, Volume
    and indicators like SMA(N), EMA(N), STD(N), RSI(N) on a given OHLCV DataFrame.
    """
    processed_formula = formula
    
    local_dict = {
        'Open': df['Open'],
        'High': df['High'],
        'Low': df['Low'],
        'Close': df['Close'],
        'Volume': df['Volume'],
    }
    
    # Extract and compute SMA(N)
    for m in re.finditer(r'SMA\s*\(\s*(\d+)\s*\)', formula, re.IGNORECASE):
        n = int(m.group(1))
        col_name = f"SMA_{n}"
        if col_name not in local_dict:
            local_dict[col_name] = df['Close'].rolling(window=n).mean()
        processed_formula = re.sub(rf'SMA\s*\(\s*{n}\s*\)', col_name, processed_formula, flags=re.IGNORECASE)

    # Extract and compute EMA(N)
    for m in re.finditer(r'EMA\s*\(\s*(\d+)\s*\)', formula, re.IGNORECASE):
        n = int(m.group(1))
        col_name = f"EMA_{n}"
        if col_name not in local_dict:
            local_dict[col_name] = df['Close'].ewm(span=n, adjust=False).mean()
        processed_formula = re.sub(rf'EMA\s*\(\s*{n}\s*\)', col_name, processed_formula, flags=re.IGNORECASE)

    # Extract and compute STD(N)
    for m in re.finditer(r'STD\s*\(\s*(\d+)\s*\)', formula, re.IGNORECASE):
        n = int(m.group(1))
        col_name = f"STD_{n}"
        if col_name not in local_dict:
            local_dict[col_name] = df['Close'].rolling(window=n).std()
        processed_formula = re.sub(rf'STD\s*\(\s*{n}\s*\)', col_name, processed_formula, flags=re.IGNORECASE)

    # Extract and compute RSI(N)
    for m in re.finditer(r'RSI\s*\(\s*(\d+)\s*\)', formula, re.IGNORECASE):
        n = int(m.group(1))
        col_name = f"RSI_{n}"
        if col_name not in local_dict:
            local_dict[col_name] = calculate_rsi(df['Close'], period=n)
        processed_formula = re.sub(rf'RSI\s*\(\s*{n}\s*\)', col_name, processed_formula, flags=re.IGNORECASE)

    # Strip out any dangerous characters or builtins before eval
    # pandas.eval automatically handles mapping using local_dict and restricts raw python builtins
    try:
        res = pd.eval(processed_formula, local_dict=local_dict, engine='python')
        if isinstance(res, (int, float)):
            # If a constant is returned, construct a series
            return pd.Series(res, index=df.index)
        return pd.Series(res, index=df.index)
    except Exception as e:
        _logger.error("Error evaluating formula %s: %s", formula, e)
        raise ValueError(f"Formula could not be calculated: {str(e)}")
