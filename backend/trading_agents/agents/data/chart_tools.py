import asyncio
import base64
import contextvars
import io
import logging
from typing import Annotated

import pandas as pd
import yfinance as yf
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor

_logger = logging.getLogger(__name__)

# Context for storing runtime registered indicators and annotations thread-safely
active_run_context: contextvars.ContextVar[dict] = contextvars.ContextVar("active_run_context")


async def _load_ohlcv_via_interface_async(symbol: str, curr_date: str) -> pd.DataFrame:
    start_date = (pd.to_datetime(curr_date) - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    csv_payload = await route_to_vendor("get_stock_data", symbol, start_date, curr_date)
    lines = [line for line in (csv_payload or "").splitlines() if line and not line.startswith("#")]
    if not lines:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df = pd.read_csv(io.StringIO("\n".join(lines)))
    if "Date" not in df.columns and "Datetime" in df.columns:
        df.rename(columns={"Datetime": "Date"}, inplace=True)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    if price_cols:
        df[price_cols] = df[price_cols].apply(pd.to_numeric, errors="coerce")
    if "Close" in df.columns:
        df = df.dropna(subset=["Close"])
    if price_cols:
        df[price_cols] = df[price_cols].ffill().bfill()
    return df[df["Date"] <= pd.to_datetime(curr_date)] if "Date" in df.columns else df


@tool
async def add_chart_annotation(
    type: Annotated[str, "Type of annotation: 'arrowUp', 'arrowDown', or 'trendline'"],
    time: Annotated[str, "Date for the annotation in YYYY-MM-DD format (for trendline, this is start date)"],
    price: Annotated[float, "Price level for the annotation (for trendline, this is start price)"],
    text: Annotated[str, "Description or label for the annotation"],
    time2: Annotated[str | None, "End date in YYYY-MM-DD format (required only for trendline)"] = None,
    price2: Annotated[float | None, "End price level (required only for trendline)"] = None,
) -> str:
    """
    Adds a visual marker (ArrowUp, ArrowDown) or trendline onto the user's interactive chart.
    Use this when you identify key events such as breakout levels, support/resistance tests, or trendline lines.
    """
    ctx = active_run_context.get(None)
    if ctx is None:
        return "Error: Active run context not found. Cannot add annotation."

    annotation = {
        "type": type,
        "time": time,
        "price": price,
        "text": text,
    }
    if time2 is not None:
        annotation["time2"] = time2
    if price2 is not None:
        annotation["price2"] = price2

    ctx["visual_annotations"].append(annotation)
    return f"Visual annotation ({type}) successfully registered at {time} / ${price}."


@tool
async def add_custom_indicator(
    name: Annotated[str, "A short unique name for the custom indicator, e.g., 'NormalizedSpread'"],
    formula: Annotated[
        str,
        "Mathematical formula using variables Open, High, Low, Close, Volume and indicators SMA(N), EMA(N), STD(N), RSI(N). Example: (Close - SMA(20)) / STD(20)",
    ],
    label: Annotated[str | None, "Optional display label for the indicator chart"] = None,
) -> str:
    """
    Creates a dynamic custom indicator based on a mathematical formula.
    The backend will safely compute this formula and the frontend will render it as a new series under the chart.
    """
    ctx = active_run_context.get(None)
    if ctx is None:
        return "Error: Active run context not found. Cannot register custom indicator."

    indicator = {"name": name, "formula": formula, "label": label or name}
    ctx["custom_indicators"].append(indicator)
    return f"Custom indicator '{name}' with formula '{formula}' registered successfully. It will be rendered on the user interface."


@tool
async def get_vision_chart_analysis(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-MM-DD"],
) -> str:
    """
    Uses a vision model to review the chart image of the stock.
    Detects visual patterns like head-and-shoulders, cup-and-handle, double top/bottom, etc.
    """
    ctx = active_run_context.get(None)
    if ctx is None or "graph" not in ctx:
        return "Error: Graph client not found in context. Vision analysis unavailable."

    try:
        df = await _load_ohlcv_via_interface_async(symbol, curr_date)
        if df.empty or len(df) < 10:
            return "Error: Not enough data to plot chart."

        # Plot last 90 trading days for pattern analysis
        df_plot = df.tail(90).copy()
        df_plot["Date"] = pd.to_datetime(df_plot["Date"])
        df_plot.set_index("Date", inplace=True)

        # Plotting using mplfinance
        import matplotlib
        import mplfinance as mpf

        matplotlib.use("Agg")

        buf = io.BytesIO()
        mpf.plot(
            df_plot,
            type="candle",
            style="charles",
            volume=True,
            title=f"{symbol.upper()} - Last 90 Trading Days",
            savefig=dict(fname=buf, format="png", dpi=100),
        )
        buf.seek(0)
        base64_image = base64.b64encode(buf.read()).decode("utf-8")

        # Resolve LLM for vision.
        # If the thinking model is not multimodal, try to find a multimodal one or provide a helpful error.
        llm = ctx["graph"].thinking_llm
        model_name = getattr(llm, "model_name", getattr(llm, "model", "")).lower()

        # Common non-multimodal model patterns (heuristic)
        non_multimodal = ["nemotron", "llama-3", "mixtral", "deepseek-v3", "o1-preview", "o1-mini"]
        if any(nm in model_name for nm in non_multimodal) and "vision" not in model_name:
            return f"Vision analysis skipped: The current model ({model_name}) is not multimodal. Please switch to a vision-capable model (like GPT-4o, Claude 3.5 Sonnet, or Gemini 1.5 Pro) in settings to enable this feature."

        from backend.trading_agents.dataflows.config import get_config

        lang = get_config().get("output_language", "English")

        prompt = (
            f"You are a professional technical analyst reviewing a chart. Here is the daily candlestick chart image for {symbol} up to {curr_date}.\n"
            "Examine this image and detect any visual chart patterns (e.g. Head and Shoulders, Cup and Handle, Double Top/Bottom, Triangles, Channels, Flags).\n"
            "State the patterns found, confidence level (High/Medium/Low), break direction direction, and target level if possible.\n"
            f"Please respond completely in {lang}."
        )

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                },
            ]
        )

        res = await llm.ainvoke([message])
        content = res.content if hasattr(res, "content") else str(res)

        # Include image in the output string for frontend to pick up if it wants
        return f"--- Vision Chart Analysis for {symbol} ---\nIMAGE_DATA:data:image/png;base64,{base64_image}\n\n{content}"

    except Exception as e:
        err_msg = str(e)
        if "not a multimodal model" in err_msg or "BadRequestError" in err_msg:
            return "Vision analysis failed: The current model does not support image input. Please use a multimodal model (e.g., GPT-4o, Claude 3.5, Gemini 1.5)."
        _logger.exception("Vision chart analysis failed: %s", e)
        return f"Error performing vision chart analysis: {err_msg}"


def _local_calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _local_calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_line, signal_line, macd_hist


def _local_find_support_resistance(df: pd.DataFrame, current_price: float, window: int = 5) -> tuple[list[float], list[float]]:
    supports = []
    resistances = []

    if len(df) <= window * 2:
        return [round(float(df["Low"].min()), 2)], [round(float(df["High"].max()), 2)]

    for i in range(window, len(df) - window):
        low_val = df["Low"].iloc[i]
        high_val = df["High"].iloc[i]

        is_support = True
        is_resistance = True
        for j in range(i - window, i + window + 1):
            if df["Low"].iloc[j] < low_val:
                is_support = False
            if df["High"].iloc[j] > high_val:
                is_resistance = False

        if is_support:
            supports.append(round(float(low_val), 2))
        if is_resistance:
            resistances.append(round(float(high_val), 2))

    unique_supports = sorted(list(set(supports)))
    unique_resistances = sorted(list(set(resistances)))

    valid_supports = [s for s in unique_supports if s < current_price]
    valid_resistances = [r for r in unique_resistances if r > current_price]

    if not valid_supports:
        valid_supports = [round(float(df["Low"].min()), 2)]
    if not valid_resistances:
        valid_resistances = [round(float(df["High"].max()), 2)]

    return valid_supports[-3:], valid_resistances[:3]


@tool
async def get_mtf_trend(
    symbol: Annotated[str, "ticker symbol of the company"],
    timeframe: Annotated[str, "Timeframe for trend calculation: '1d', '1wk', '1mo'"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-MM-DD"],
) -> str:
    """
    Fetches stock data from a higher timeframe (e.g., Weekly '1wk' or Monthly '1mo'),
    calculates a smoothed trend (20-period EMA), RSI, MACD, and major support/resistance levels,
    and maps/overlays the indicators and levels back onto the primary daily chart.
    """
    ctx = active_run_context.get(None)
    if ctx is None:
        return "Error: Active run context not found. Cannot register trend overlay."

    try:
        # Load daily data to get index mapping
        df_daily = await _load_ohlcv_via_interface_async(symbol, curr_date)
        if df_daily.empty:
            return "Error: No daily data found."

        df_daily["Date"] = pd.to_datetime(df_daily["Date"])
        if df_daily["Date"].dt.tz is not None:
            df_daily["Date"] = df_daily["Date"].dt.tz_localize(None)
        df_daily["Date"] = df_daily["Date"].astype("datetime64[ns]")
        df_daily.sort_values("Date", inplace=True)

        # Download timeframe specific data
        ticker = yf.Ticker(symbol.upper())
        # We need historical data. Determine start based on lookback
        start_date = (df_daily["Date"].min() - pd.DateOffset(days=90)).strftime("%Y-%m-%d")

        # yfinance download is sync
        df_mtf = await asyncio.to_thread(ticker.history, start=start_date, end=curr_date, interval=timeframe)
        if df_mtf.empty:
            return f"Error: No data found for timeframe '{timeframe}'."

        if df_mtf.index.tz is not None:
            df_mtf.index = df_mtf.index.tz_localize(None)

        df_mtf = df_mtf.dropna(subset=["Close", "High", "Low"])

        # Calculate Indicators
        df_mtf["EMA_20"] = df_mtf["Close"].ewm(span=20, adjust=False).mean()
        df_mtf["RSI_14"] = _local_calculate_rsi(df_mtf["Close"], 14)
        macd_line, signal_line, macd_hist = _local_calculate_macd(df_mtf["Close"], 12, 26, 9)
        df_mtf["MACD_Line"] = macd_line
        df_mtf["MACD_Signal"] = signal_line
        df_mtf["MACD_Hist"] = macd_hist

        latest_close = float(df_mtf["Close"].iloc[-1])
        latest_ema = float(df_mtf["EMA_20"].iloc[-1])
        latest_rsi = float(df_mtf["RSI_14"].iloc[-1]) if not pd.isna(df_mtf["RSI_14"].iloc[-1]) else 50.0
        latest_macd = float(df_mtf["MACD_Line"].iloc[-1])
        latest_macd_sig = float(df_mtf["MACD_Signal"].iloc[-1])
        latest_macd_hist = float(df_mtf["MACD_Hist"].iloc[-1])

        # Map MTF EMA to Daily dates (forward-fill)
        df_mtf_reset = df_mtf.reset_index()
        df_mtf_reset.rename(columns={"Date": "MTF_Date"}, inplace=True)
        df_mtf_reset["MTF_Date"] = pd.to_datetime(df_mtf_reset["MTF_Date"])
        if df_mtf_reset["MTF_Date"].dt.tz is not None:
            df_mtf_reset["MTF_Date"] = df_mtf_reset["MTF_Date"].dt.tz_localize(None)
        df_mtf_reset["MTF_Date"] = df_mtf_reset["MTF_Date"].astype("datetime64[ns]")

        # Merge on daily index
        merged = pd.merge_asof(
            df_daily, df_mtf_reset[["MTF_Date", "EMA_20"]], left_on="Date", right_on="MTF_Date", direction="backward"
        )

        # Register EMA series as a custom indicator, labeled for overlay
        col_name = f"EMA20_{timeframe}"
        overlay_name = f"{timeframe.upper()} EMA(20) Trend"

        # We will store this calculated series in custom indicators with overlay option
        ctx["custom_indicators"].append(
            {
                "name": col_name,
                "formula": f"Close * 0 + {col_name}",  # dummy formula
                "label": overlay_name,
                "overlay": True,
                "values": {
                    row["Date"].strftime("%Y-%m-%d"): round(float(row["EMA_20"]), 2)
                    for _, row in merged.iterrows()
                    if not pd.isna(row["EMA_20"])
                },
            }
        )

        # Determine trend conditions
        ema_trend = "BULLISH" if latest_close > latest_ema else "BEARISH"
        rsi_condition = "OVERBOUGHT" if latest_rsi >= 70 else ("OVERSOLD" if latest_rsi <= 30 else "NEUTRAL")
        macd_trend = "BULLISH (MACD Line is above Signal Line)" if latest_macd > latest_macd_sig else "BEARISH (MACD Line is below Signal Line)"

        # Calculate support/resistance
        valid_supports, valid_resistances = _local_find_support_resistance(df_mtf, latest_close, window=5)

        # Add support/resistance to ctx if available
        if "support_levels" in ctx:
            ctx["support_levels"].extend(valid_supports)
        if "resistance_levels" in ctx:
            ctx["resistance_levels"].extend(valid_resistances)

        latest_date = df_mtf.index[-1].strftime("%Y-%m-%d")

        summary = (
            f"--- Multi-Timeframe Trend Analysis ({timeframe.upper()}) for {symbol.upper()} ---\n"
            f"Current Reference Date: {curr_date}\n"
            f"Latest Ticker Close Price: ${latest_close:.2f} (on {latest_date})\n"
            f"1. EMA (20): ${latest_ema:.2f} ({ema_trend} - Price is {'above' if ema_trend == 'BULLISH' else 'below'} 20 EMA)\n"
            f"2. RSI (14): {latest_rsi:.1f} ({rsi_condition})\n"
            f"3. MACD (12, 26, 9): Line = {latest_macd:.4f}, Signal = {latest_macd_sig:.4f}, Hist = {latest_macd_hist:.4f} ({macd_trend})\n"
            f"4. Major Support Levels (Below Price): {', '.join([f'${s:.2f}' for s in valid_supports])}\n"
            f"5. Major Resistance Levels (Above Price): {', '.join([f'${r:.2f}' for r in valid_resistances])}\n"
            f"--------------------------------------------------------------------------------"
        )
        return summary

    except Exception as e:
        _logger.exception("MTF Trend calculation failed: %s", e)
        return f"Error calculating MTF trend: {str(e)}"
