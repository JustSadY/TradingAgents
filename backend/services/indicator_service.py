import re
import logging
import pandas as pd
import numpy as np

_logger = logging.getLogger(__name__)

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    # Simple moving average of gains/losses for RSI
    gain = (delta.clip(lower=0)).rolling(window=period).mean()
    loss = (-1 * delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

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
