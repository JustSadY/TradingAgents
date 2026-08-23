import ast
import logging
import re

import numpy as np
import pandas as pd
import talib

_logger = logging.getLogger(__name__)


def _values(series: pd.Series) -> np.ndarray:
    return np.ascontiguousarray(series.to_numpy(dtype="float64"))


def _series(value, index: pd.Index, name: str) -> pd.Series:
    if value is None:
        return pd.Series(float("nan"), index=index, name=name, dtype="float64")
    return pd.Series(value, index=index, dtype="float64", name=name)


def _nan(index: pd.Index, name: str) -> pd.Series:
    return pd.Series(float("nan"), index=index, name=name, dtype="float64")


def _hlcv(df: pd.DataFrame) -> tuple[np.ndarray, ...]:
    return tuple(
        _values(df[column].astype(float)) for column in ("High", "Low", "Close", "Volume") if column in df
    )


def calculate_ema(prices: pd.Series, span: int = 20) -> pd.Series:
    prices = prices.astype(float)
    name = f"EMA_{span}"
    if len(prices) < span:
        return _nan(prices.index, name)
    return _series(talib.EMA(_values(prices), timeperiod=span), prices.index, name)


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    prices = prices.astype(float)
    name = f"RSI_{period}"
    if len(prices) <= period:
        return _nan(prices.index, name)
    return _series(talib.RSI(_values(prices), timeperiod=period), prices.index, name)


def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series]:
    prices = prices.astype(float)
    macd_name = f"MACD_{fast}_{slow}_{signal}"
    signal_name = f"MACDs_{fast}_{slow}_{signal}"
    if len(prices) < slow + signal:
        return _nan(prices.index, macd_name), _nan(prices.index, signal_name)
    macd, macd_signal, _ = talib.MACD(
        _values(prices), fastperiod=fast, slowperiod=slow, signalperiod=signal
    )
    return (
        _series(macd, prices.index, macd_name),
        _series(macd_signal, prices.index, signal_name),
    )


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    name = f"ADX_{period}"
    if len(df) < period * 2:
        return _nan(df.index, name)
    high, low, close = _hlcv(df)[:3]
    return _series(talib.ADX(high, low, close, timeperiod=period), df.index, name)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    name = f"ATR_{period}"
    if len(df) <= period:
        return _nan(df.index, name)
    high, low, close = _hlcv(df)[:3]
    return _series(talib.ATR(high, low, close, timeperiod=period), df.index, name)


def calculate_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Rolling volume-weighted typical price.

    TA-Lib has no VWMA, and its session-anchored VWAP has a different contract
    from this application's ``period`` semantics.
    """
    typical = (df["High"].astype(float) + df["Low"].astype(float) + df["Close"].astype(float)) / 3.0
    volume = df["Volume"].astype(float)
    weighted = (typical * volume).rolling(window=period).sum()
    total = volume.rolling(window=period).sum()
    return _series(weighted / total.where(total != 0), df.index, f"VWAP_{period}")


def calculate_sma(prices: pd.Series, period: int = 20) -> pd.Series:
    prices = prices.astype(float)
    name = f"SMA_{period}"
    if len(prices) < period:
        return _nan(prices.index, name)
    return _series(talib.SMA(_values(prices), timeperiod=period), prices.index, name)


def calculate_bbands(
    prices: pd.Series,
    period: int = 20,
    std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands as ``(lower, middle, upper)``."""
    prices = prices.astype(float)
    names = (f"BBL_{period}_{std}", f"BBM_{period}_{std}", f"BBU_{period}_{std}")
    if len(prices) < period:
        return tuple(_nan(prices.index, name) for name in names)
    upper, middle, lower = talib.BBANDS(
        _values(prices), timeperiod=period, nbdevup=std, nbdevdn=std, matype=talib.MA_Type.SMA
    )
    return (
        _series(lower, prices.index, names[0]),
        _series(middle, prices.index, names[1]),
        _series(upper, prices.index, names[2]),
    )


def calculate_stoch(
    df: pd.DataFrame,
    k: int = 14,
    d: int = 3,
    smooth_k: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Stochastic oscillator as ``(%K, %D)``."""
    names = (f"STOCHk_{k}_{d}_{smooth_k}", f"STOCHd_{k}_{d}_{smooth_k}")
    if len(df) < k + smooth_k + d:
        return tuple(_nan(df.index, name) for name in names)
    high, low, close = _hlcv(df)[:3]
    slowk, slowd = talib.STOCH(
        high,
        low,
        close,
        fastk_period=k,
        slowk_period=smooth_k,
        slowk_matype=talib.MA_Type.SMA,
        slowd_period=d,
        slowd_matype=talib.MA_Type.SMA,
    )
    return _series(slowk, df.index, names[0]), _series(slowd, df.index, names[1])


def calculate_cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    name = f"CCI_{period}"
    if len(df) < period:
        return _nan(df.index, name)
    high, low, close = _hlcv(df)[:3]
    return _series(talib.CCI(high, low, close, timeperiod=period), df.index, name)


def calculate_mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    name = f"MFI_{period}"
    if len(df) <= period:
        return _nan(df.index, name)
    high, low, close, volume = _hlcv(df)
    return _series(talib.MFI(high, low, close, volume, timeperiod=period), df.index, name)


def calculate_willr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    name = f"WILLR_{period}"
    if len(df) < period:
        return _nan(df.index, name)
    high, low, close = _hlcv(df)[:3]
    return _series(talib.WILLR(high, low, close, timeperiod=period), df.index, name)


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
