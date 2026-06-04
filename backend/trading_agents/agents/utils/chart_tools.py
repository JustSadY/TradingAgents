import os
import re
import io
import base64
import logging
import contextvars
from typing import Annotated, Optional, List, Dict
import pandas as pd
import numpy as np
import yfinance as yf
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

_logger = logging.getLogger(__name__)

# Context for storing runtime registered indicators and annotations thread-safely
active_run_context: contextvars.ContextVar[Dict] = contextvars.ContextVar("active_run_context")

@tool
def add_chart_annotation(
    type: Annotated[str, "Type of annotation: 'arrowUp', 'arrowDown', or 'trendline'"],
    time: Annotated[str, "Date for the annotation in YYYY-MM-DD format (for trendline, this is start date)"],
    price: Annotated[float, "Price level for the annotation (for trendline, this is start price)"],
    text: Annotated[str, "Description or label for the annotation"],
    time2: Annotated[Optional[str], "End date in YYYY-MM-DD format (required only for trendline)"] = None,
    price2: Annotated[Optional[float], "End price level (required only for trendline)"] = None,
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
def add_custom_indicator(
    name: Annotated[str, "A short unique name for the custom indicator, e.g., 'NormalizedSpread'"],
    formula: Annotated[str, "Mathematical formula using variables Open, High, Low, Close, Volume and indicators SMA(N), EMA(N), STD(N), RSI(N). Example: (Close - SMA(20)) / STD(20)"],
    label: Annotated[Optional[str], "Optional display label for the indicator chart"] = None,
) -> str:
    """
    Creates a dynamic custom indicator based on a mathematical formula.
    The backend will safely compute this formula and the frontend will render it as a new series under the chart.
    """
    ctx = active_run_context.get(None)
    if ctx is None:
        return "Error: Active run context not found. Cannot register custom indicator."
    
    indicator = {
        "name": name,
        "formula": formula,
        "label": label or name
    }
    ctx["custom_indicators"].append(indicator)
    return f"Custom indicator '{name}' with formula '{formula}' registered successfully. It will be rendered on the user interface."

@tool
def get_vision_chart_analysis(
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
        from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv
        df = load_ohlcv(symbol, curr_date)
        if df.empty or len(df) < 10:
            return "Error: Not enough data to plot chart."
        
        # Plot last 90 trading days for pattern analysis
        df_plot = df.tail(90).copy()
        df_plot['Date'] = pd.to_datetime(df_plot['Date'])
        df_plot.set_index('Date', inplace=True)
        
        # Plotting using mplfinance
        import mplfinance as mpf
        import matplotlib
        matplotlib.use('Agg')
        
        buf = io.BytesIO()
        mpf.plot(
            df_plot, 
            type='candle', 
            style='charles', 
            volume=True, 
            title=f"{symbol.upper()} - Last 90 Trading Days",
            savefig=dict(fname=buf, format='png', dpi=100)
        )
        buf.seek(0)
        base64_image = base64.b64encode(buf.read()).decode('utf-8')
        
        # Prepare Vision LLM invocation
        llm = ctx["graph"].thinking_llm
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
        
        res = llm.invoke([message])
        content = res.content if hasattr(res, "content") else str(res)
        return f"--- Vision Chart Analysis for {symbol} ---\n{content}"
        
    except Exception as e:
        _logger.exception("Vision chart analysis failed: %s", e)
        return f"Error performing vision chart analysis: {str(e)}"

@tool
def get_mtf_trend(
    symbol: Annotated[str, "ticker symbol of the company"],
    timeframe: Annotated[str, "Timeframe for trend calculation: '1d', '1wk', '1mo'"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-MM-DD"],
) -> str:
    """
    Fetches stock data from a higher timeframe (e.g., Weekly '1wk' or Monthly '1mo'),
    calculates a smoothed trend (20-period EMA), and maps/overlays it back onto the primary daily chart.
    """
    ctx = active_run_context.get(None)
    if ctx is None:
        return "Error: Active run context not found. Cannot register trend overlay."
        
    try:
        from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv
        # Load daily data to get index mapping
        df_daily = load_ohlcv(symbol, curr_date)
        if df_daily.empty:
            return "Error: No daily data found."
            
        df_daily['Date'] = pd.to_datetime(df_daily['Date'])
        df_daily.sort_values('Date', inplace=True)
        
        # Download timeframe specific data
        ticker = yf.Ticker(symbol.upper())
        # We need historical data. Determine start based on lookback
        start_date = (df_daily['Date'].min() - pd.DateOffset(days=90)).strftime('%Y-%m-%d')
        
        df_mtf = ticker.history(start=start_date, end=curr_date, interval=timeframe)
        if df_mtf.empty:
            return f"Error: No data found for timeframe '{timeframe}'."
            
        if df_mtf.index.tz is not None:
            df_mtf.index = df_mtf.index.tz_localize(None)
            
        # Calculate 20 EMA
        df_mtf['EMA_20'] = df_mtf['Close'].ewm(span=20, adjust=False).mean()
        
        # Map MTF EMA to Daily dates (forward-fill)
        df_mtf_reset = df_mtf.reset_index()
        df_mtf_reset.rename(columns={'Date': 'MTF_Date'}, inplace=True)
        
        # Merge on daily index
        merged = pd.merge_asof(
            df_daily, 
            df_mtf_reset[['MTF_Date', 'EMA_20']], 
            left_on='Date', 
            right_on='MTF_Date', 
            direction='backward'
        )
        
        # Register this series as a custom indicator, labeled for overlay
        col_name = f"EMA20_{timeframe}"
        overlay_name = f"{timeframe.upper()} EMA(20) Trend"
        
        # We will store this calculated series in custom indicators with overlay option
        ctx["custom_indicators"].append({
            "name": col_name,
            "formula": f"Close * 0 + {col_name}", # dummy formula, but we pass custom calculated values in the series endpoint
            "label": overlay_name,
            "overlay": True,
            "values": {row['Date'].strftime('%Y-%m-%d'): round(float(row['EMA_20']), 2) for _, row in merged.iterrows() if not pd.isna(row['EMA_20'])}
        })
        
        latest_val = df_mtf['EMA_20'].iloc[-1]
        latest_date = df_mtf.index[-1].strftime('%Y-%m-%d')
        
        return f"Successfully registered MTF Trend ({overlay_name}) onto the main chart. Latest trend value on {latest_date} is ${latest_val:.2f}."
        
    except Exception as e:
        _logger.exception("MTF Trend calculation failed: %s", e)
        return f"Error calculating MTF trend: {str(e)}"
