import ast
import logging
import re

import pandas as pd

_logger = logging.getLogger(__name__)


def _ta():
    """Load the sole standard-indicator engine."""
    try:
        import pandas_ta_classic as ta
    except ImportError as exc:
        raise RuntimeError(
            "pandas-ta-classic is required for technical indicators. Sync backend dependencies before calculating indicators."
        ) from exc
    return ta


def _series(value, index: pd.Index, name: str) -> pd.Series:
    if value is None:
        return pd.Series(float("nan"), index=index, name=name, dtype="float64")
    return pd.Series(value, index=index, dtype="float64", name=name)


def calculate_ema(prices: pd.Series, span: int = 20) -> pd.Series:
    """Compute EMA with pandas-ta-classic."""
    prices = prices.astype(float)
    return _series(_ta().ema(prices, length=span, talib=False), prices.index, f"EMA_{span}")


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI with pandas-ta-classic."""
    prices = prices.astype(float)
    return _series(_ta().rsi(prices, length=period, talib=False), prices.index, f"RSI_{period}")


def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    """Compute MACD and signal line with pandas-ta-classic."""
    prices = prices.astype(float)
    result = _ta().macd(prices, fast=fast, slow=slow, signal=signal, talib=False)
    if result is None or result.empty:
        empty = pd.Series(float("nan"), index=prices.index, dtype="float64")
        return empty.copy(), empty.copy()

    macd_col = next((c for c in result.columns if str(c).startswith("MACD_")), None)
    signal_col = next((c for c in result.columns if str(c).startswith("MACDs_")), None)
    if macd_col is None or signal_col is None:
        raise RuntimeError(f"Unexpected pandas-ta-classic MACD columns: {list(result.columns)}")
    return (
        _series(result[macd_col], prices.index, str(macd_col)),
        _series(result[signal_col], prices.index, str(signal_col)),
    )


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ADX with pandas-ta-classic."""
    result = _ta().adx(
        df["High"].astype(float),
        df["Low"].astype(float),
        df["Close"].astype(float),
        length=period,
    )
    if result is None or result.empty:
        return pd.Series(float("nan"), index=df.index, dtype="float64", name=f"ADX_{period}")
    column = f"ADX_{period}"
    if column not in result:
        column = next((c for c in result.columns if str(c).startswith("ADX_")), None)
    if column is None:
        raise RuntimeError(f"Unexpected pandas-ta-classic ADX columns: {list(result.columns)}")
    return _series(result[column], df.index, str(column))


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ATR with pandas-ta-classic."""
    result = _ta().atr(
        df["High"].astype(float),
        df["Low"].astype(float),
        df["Close"].astype(float),
        length=period,
        talib=False,
    )
    return _series(result, df.index, f"ATR_{period}")


def calculate_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Compute rolling volume-weighted typical price with pandas-ta-classic.

    ``vwma`` preserves this application's historical ``period`` semantics;
    pandas-ta's session-anchored ``vwap`` has a different contract.
    """
    typical_price = (df["High"].astype(float) + df["Low"].astype(float) + df["Close"].astype(float)) / 3.0
    result = _ta().vwma(typical_price, df["Volume"].astype(float), length=period)
    return _series(result, df.index, f"VWAP_{period}")


def _frame_column(result, prefix: str, indicator: str):
    """Return the column of ``result`` whose name starts with ``prefix``.

    pandas-ta embeds its parameters in column names (``BBU_20_2.0``,
    ``STOCHk_14_3_3``, ``CCI_20_0.015``), and the constant in that suffix is not
    always the one that was passed in. Matching on the prefix keeps these
    wrappers working when a caller changes a period.
    """
    column = next((c for c in result.columns if str(c).startswith(prefix)), None)
    if column is None:
        raise RuntimeError(f"Unexpected pandas-ta-classic {indicator} columns: {list(result.columns)}")
    return column


def calculate_sma(prices: pd.Series, period: int = 20) -> pd.Series:
    """Compute SMA with pandas-ta-classic."""
    prices = prices.astype(float)
    return _series(_ta().sma(prices, length=period, talib=False), prices.index, f"SMA_{period}")


def calculate_bbands(
    prices: pd.Series,
    period: int = 20,
    std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute Bollinger Bands as ``(lower, middle, upper)``."""
    prices = prices.astype(float)
    result = _ta().bbands(prices, length=period, std=std, talib=False)
    if result is None or result.empty:
        empty = pd.Series(float("nan"), index=prices.index, dtype="float64")
        return empty.copy(), empty.copy(), empty.copy()

    lower = _frame_column(result, "BBL_", "BBANDS")
    middle = _frame_column(result, "BBM_", "BBANDS")
    upper = _frame_column(result, "BBU_", "BBANDS")
    return (
        _series(result[lower], prices.index, str(lower)),
        _series(result[middle], prices.index, str(middle)),
        _series(result[upper], prices.index, str(upper)),
    )


def calculate_stoch(
    df: pd.DataFrame,
    k: int = 14,
    d: int = 3,
    smooth_k: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Compute the stochastic oscillator as ``(%K, %D)``."""
    result = _ta().stoch(
        df["High"].astype(float),
        df["Low"].astype(float),
        df["Close"].astype(float),
        k=k,
        d=d,
        smooth_k=smooth_k,
        talib=False,
    )
    if result is None or result.empty:
        empty = pd.Series(float("nan"), index=df.index, dtype="float64")
        return empty.copy(), empty.copy()

    k_col = _frame_column(result, "STOCHk_", "STOCH")
    d_col = _frame_column(result, "STOCHd_", "STOCH")
    return (
        _series(result[k_col], df.index, str(k_col)),
        _series(result[d_col], df.index, str(d_col)),
    )


def calculate_cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Compute the Commodity Channel Index with pandas-ta-classic."""
    result = _ta().cci(
        df["High"].astype(float),
        df["Low"].astype(float),
        df["Close"].astype(float),
        length=period,
        talib=False,
    )
    return _series(result, df.index, f"CCI_{period}")


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute the Money Flow Index with pandas-ta-classic."""
    result = _ta().mfi(
        df["High"].astype(float),
        df["Low"].astype(float),
        df["Close"].astype(float),
        df["Volume"].astype(float),
        length=period,
        talib=False,
    )
    return _series(result, df.index, f"MFI_{period}")


def calculate_willr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Williams %R with pandas-ta-classic."""
    result = _ta().willr(
        df["High"].astype(float),
        df["Low"].astype(float),
        df["Close"].astype(float),
        length=period,
        talib=False,
    )
    return _series(result, df.index, f"WILLR_{period}")


_FORMULA_FUNCS: dict = {
    "VOLSMA": lambda df, n: df["Volume"].rolling(window=n).mean(),
    "VWAP": lambda df, n: calculate_vwap(df, n),
    "SHIFT": lambda df, n: df["Close"].shift(n),
    "SMA": lambda df, n: calculate_sma(df["Close"], n),
    "EMA": lambda df, n: calculate_ema(df["Close"], n),
    "STD": lambda df, n: df["Close"].rolling(window=n).std(),
    "RSI": lambda df, n: calculate_rsi(df["Close"], n),
    "ADX": lambda df, n: calculate_adx(df, n),
    "ATR": lambda df, n: calculate_atr(df, n),
    "CCI": lambda df, n: calculate_cci(df, n),
    "MFI": lambda df, n: calculate_mfi(df, n),
    "WILLR": lambda df, n: calculate_willr(df, n),
    # Bollinger bands and the stochastic return several series, so each band or
    # line gets its own formula symbol. Defaults match the standalone helpers.
    "BBL": lambda df, n: calculate_bbands(df["Close"], n)[0],
    "BBM": lambda df, n: calculate_bbands(df["Close"], n)[1],
    "BBU": lambda df, n: calculate_bbands(df["Close"], n)[2],
    "STOCHK": lambda df, n: calculate_stoch(df, k=n)[0],
    "STOCHD": lambda df, n: calculate_stoch(df, k=n)[1],
    "MAX": lambda df, n: df["High"].rolling(window=n).max(),
    "MIN": lambda df, n: df["Low"].rolling(window=n).min(),
}


def evaluate_formula_safely(df: pd.DataFrame, formula: str) -> pd.Series:
    """Evaluate a bounded, causal arithmetic indicator expression."""
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
            processed_formula = re.sub(re.escape(match.group(0)), col_name, processed_formula, flags=re.IGNORECASE)

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

        values = series.to_numpy(dtype="float64", na_value=np.nan)
        if bool(np.isinf(values).any()):
            raise ValueError("Formula result contains non-finite values")
        if not bool(np.isfinite(values).any()):
            raise ValueError("Formula result has no finite values over this range")
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
