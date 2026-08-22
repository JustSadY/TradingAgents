import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta

from .stockstats_utils import filter_financials_by_date, load_ohlcv, yf_retry

_logger = logging.getLogger(__name__)

def _format_usd_amount(value: object) -> str:
    """Render Yahoo's raw monetary fields with an unambiguous USD unit.

    Yahoo Finance returns fields such as ``totalRevenue`` as a bare number of
    dollars.  Passing ``253500000000`` through to an LLM made it easy to call
    the figure ``$253.5M`` instead of ``$253.5B``.  The human-readable form is
    deliberately included at the data-source boundary so every analyst sees
    the same unit rather than having to infer it from the magnitude.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if pd.isna(value):
        return "N/A"

    magnitude = abs(float(value))
    for divisor, suffix in ((1_000_000_000_000, "T"), (1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if magnitude >= divisor:
            return f"${float(value) / divisor:,.2f}{suffix} USD"
    return f"${float(value):,.2f} USD"

_MONETARY_FUNDAMENTAL_LABELS = frozenset(
    {
        "Market Cap",
        "Revenue (TTM)",
        "Gross Profit",
        "EBITDA",
        "Net Income",
        "Free Cash Flow",
    }
)

def get_yfin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    # Yahoo treats `end` as exclusive while every caller — and the Alpha Vantage
    # implementation of the same vendor method — means it inclusively. Without
    # the extra day the trade date's own bar is missing from every indicator,
    # and a single-day request (start == end) returns nothing at all, which
    # yfinance reports as "possibly delisted".
    exclusive_end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    ticker = yf.Ticker(symbol.upper())
    data = yf_retry(
        lambda: ticker.history(start=start_date, end=exclusive_end, raise_errors=True),
        ticker=symbol,
    )
    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)
    data = data[data.index < end_dt + timedelta(days=1)]
    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)
    csv_string = data.to_csv()
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string

def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    from backend.services.indicator_service import calculate_atr, calculate_ema, calculate_macd, calculate_rsi

    data = load_ohlcv(symbol, curr_date)
    if data.empty:
        return f"No data found for {symbol}"

    if "Date" in data.columns:
        data = data.set_index("Date")

    series = data["Close"]
    res_series = None

    if indicator == "rsi":
        res_series = calculate_rsi(series)
    elif indicator in {"macd", "macds", "macdh"}:
        macd_line, signal_line = calculate_macd(series)
        if indicator == "macd":
            res_series = macd_line
        elif indicator == "macds":
            res_series = signal_line
        else:
            res_series = macd_line - signal_line
    elif "sma" in indicator:
        window = int(re.search(r"\d+", indicator).group())
        res_series = series.rolling(window=window).mean()
    elif "ema" in indicator:
        span = int(re.search(r"\d+", indicator).group())
        res_series = calculate_ema(series, span)
    elif indicator.startswith("boll"):
        sma20 = series.rolling(window=20).mean()
        std20 = series.rolling(window=20).std()
        if indicator == "boll":
            res_series = sma20
        elif indicator == "boll_ub":
            res_series = sma20 + (std20 * 2)
        elif indicator == "boll_lb":
            res_series = sma20 - (std20 * 2)
    elif indicator == "atr":
        res_series = calculate_atr(data)
    elif indicator == "vwma":
        volume = data["Volume"].where(data["Volume"] != 0)
        res_series = (series * volume).rolling(window=20).sum() / volume.rolling(window=20).sum()

    if res_series is None:
        return f"Indicator {indicator} not yet supported in centralized service"

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - relativedelta(days=look_back_days)

    df_res = pd.DataFrame({"value": res_series}, index=data.index)
    mask = (df_res.index >= start_dt) & (df_res.index <= end_dt)
    df_filtered = df_res.loc[mask].sort_index(ascending=False)

    ind_string = ""
    for dt, row in df_filtered.iterrows():
        val = row["value"]
        val_str = f"{val:.2f}" if pd.notna(val) else "N/A"
        ind_string += f"{dt.strftime('%Y-%m-%d')}: {val_str}\n"

    return f"## {indicator} values for {symbol} (back to {start_dt.strftime('%Y-%m-%d')}):\n\n{ind_string}"

def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None,
):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info, ticker=ticker)
        if not info:
            return f"No fundamentals data found for symbol '{ticker}'"
        fields = [
            ("Name", info.get("longName")),
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
            ("Market Cap", info.get("marketCap")),
            ("PE Ratio (TTM)", info.get("trailingPE")),
            ("Forward PE", info.get("forwardPE")),
            ("PEG Ratio", info.get("pegRatio")),
            ("Price to Book", info.get("priceToBook")),
            ("EPS (TTM)", info.get("trailingEps")),
            ("Forward EPS", info.get("forwardEps")),
            ("Dividend Yield", info.get("dividendYield")),
            ("Beta", info.get("beta")),
            ("52 Week High", info.get("fiftyTwoWeekHigh")),
            ("52 Week Low", info.get("fiftyTwoWeekLow")),
            ("50 Day Average", info.get("fiftyDayAverage")),
            ("200 Day Average", info.get("twoHundredDayAverage")),
            ("Revenue (TTM)", info.get("totalRevenue")),
            ("Gross Profit", info.get("grossProfits")),
            ("EBITDA", info.get("ebitda")),
            ("Net Income", info.get("netIncomeToCommon")),
            ("Profit Margin", info.get("profitMargins")),
            ("Operating Margin", info.get("operatingMargins")),
            ("Return on Equity", info.get("returnOnEquity")),
            ("Return on Assets", info.get("returnOnAssets")),
            ("Debt to Equity", info.get("debtToEquity")),
            ("Current Ratio", info.get("currentRatio")),
            ("Book Value", info.get("bookValue")),
            ("Free Cash Flow", info.get("freeCashflow")),
        ]
        lines = []
        for label, value in fields:
            if value is not None:
                rendered_value = _format_usd_amount(value) if label in _MONETARY_FUNDAMENTAL_LABELS else value
                lines.append(f"{label}: {rendered_value}")
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# Data retrieved on: {today} {datetime.now(UTC).strftime('%H:%M:%S')}\n"
        header += "# Monetary values are formatted in USD (B = billion, M = million); do not infer a different unit.\n"
        if curr_date and curr_date != today:
            header += (
                f"# WARNING: these are TODAY'S live metrics, not a historical snapshot as of {curr_date}. "
                "yfinance has no point-in-time fundamentals API — do not treat P/E, market cap, or other "
                "ratios below as what they were on the analysis date.\n"
            )
        header += "\n"
        return header + "\n".join(lines)
    except Exception:
        raise

def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet, ticker=ticker)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet, ticker=ticker)
        data = filter_financials_by_date(data, curr_date, frequency=freq)
        if data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n"
        if curr_date:
            lag = 45 if freq.lower() == "quarterly" else 90
            header += f"# Point-in-time safety: period-end columns are included only after a conservative {lag}-day publication lag.\n"
        header += "\n# Monetary statement rows are raw USD: 1,000,000,000 = $1.00B and 1,000,000 = $1.00M. Preserve period labels.\n\n"
        return header + csv_string
    except Exception:
        raise

def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow, ticker=ticker)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow, ticker=ticker)
        data = filter_financials_by_date(data, curr_date, frequency=freq)
        if data.empty:
            return f"No cash flow data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n"
        if curr_date:
            lag = 45 if freq.lower() == "quarterly" else 90
            header += f"# Point-in-time safety: period-end columns are included only after a conservative {lag}-day publication lag.\n"
        header += "\n# Monetary statement rows are raw USD: 1,000,000,000 = $1.00B and 1,000,000 = $1.00M. Preserve period labels.\n\n"
        return header + csv_string
    except Exception:
        raise

def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt, ticker=ticker)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt, ticker=ticker)
        data = filter_financials_by_date(data, curr_date, frequency=freq)
        if data.empty:
            return f"No income statement data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n"
        if curr_date:
            lag = 45 if freq.lower() == "quarterly" else 90
            header += f"# Point-in-time safety: period-end columns are included only after a conservative {lag}-day publication lag.\n"
        header += "\n# Monetary statement rows are raw USD: 1,000,000,000 = $1.00B and 1,000,000 = $1.00M. Preserve period labels.\n\n"
        return header + csv_string
    except Exception:
        raise

def get_insider_transactions(ticker: Annotated[str, "ticker symbol of the company"]):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: ticker_obj.insider_transactions, ticker=ticker)
        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"
        csv_string = data.head(25).to_csv()
        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception:
        raise

def get_short_interest(ticker: Annotated[str, "ticker symbol of the company"]):
    """Short-interest snapshot: shares short, short ratio (days-to-cover), and
    short % of float — the ingredients of a squeeze setup."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info, ticker=ticker) or {}
        fields = {
            "Shares Short": info.get("sharesShort"),
            "Shares Short (Prior Month)": info.get("sharesShortPriorMonth"),
            "Short Ratio (days to cover)": info.get("shortRatio"),
            "Short % of Float": info.get("shortPercentOfFloat"),
            "Short % of Shares Outstanding": info.get("sharesPercentSharesOut"),
            "Float Shares": info.get("floatShares"),
            "Shares Outstanding": info.get("sharesOutstanding"),
            "Date of Short Interest": info.get("dateShortInterest"),
        }
        rows = [f"- {k}: {v}" for k, v in fields.items() if v is not None]
        if not rows:
            return f"No short-interest data found for symbol '{ticker}'"
        header = f"# Short Interest data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + "\n".join(rows)
    except Exception:
        raise

_SECTOR_ETF_BY_LABEL = {
    "technology": "XLK",
    "financial": "XLF",
    "energy": "XLE",
    "healthcare": "XLV",
    "health care": "XLV",
    "consumer cyclical": "XLY",
    "consumer defensive": "XLP",
    "industrials": "XLI",
    "basic materials": "XLB",
    "utilities": "XLU",
    "real estate": "XLRE",
    "communication": "XLC",
}

_VALUATION_FIELDS = {
    "Trailing P/E": "trailingPE",
    "Forward P/E": "forwardPE",
    "Price/Sales": "priceToSalesTrailing12Months",
    "Price/Book": "priceToBook",
    "PEG Ratio": "pegRatio",
    "EV/EBITDA": "enterpriseToEbitda",
    "Profit Margin": "profitMargins",
}

def _sector_etf_for(sector: str | None) -> str | None:
    """Best-effort match of a yfinance sector label to a SPDR sector ETF ticker."""
    if not sector:
        return None
    s = sector.lower()
    for label, etf in _SECTOR_ETF_BY_LABEL.items():
        if label in s:
            return etf
    return None

def _valuation_lines(info: dict) -> list[str]:
    lines = []
    for label, field in _VALUATION_FIELDS.items():
        val = info.get(field)
        if val is not None:
            lines.append(f"- {label}: {val:.2f}" if isinstance(val, (int, float)) else f"- {label}: {val}")
    return lines

def get_valuation_comparison(ticker: Annotated[str, "ticker symbol of the company"]):
    """Compare a stock's valuation multiples against its sector ETF as a peer proxy."""
    try:
        ticker_upper = ticker.upper()
        info = yf_retry(lambda: yf.Ticker(ticker_upper).info, ticker=ticker_upper) or {}
        sector = info.get("sector")

        parts = [f"# Valuation Comparison for {ticker_upper}"]
        parts.append(f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n")
        parts.append(f"## {ticker_upper} Valuation Multiples (Sector: {sector or 'Unknown'})")
        own_lines = _valuation_lines(info)
        if not own_lines:
            return f"No valuation data found for symbol '{ticker}'"
        parts.extend(own_lines)

        etf = _sector_etf_for(sector)
        if etf:
            etf_info = yf_retry(lambda: yf.Ticker(etf).info, ticker=etf) or {}
            etf_lines = _valuation_lines(etf_info)
            if etf_lines:
                parts.append(f"\n## Sector Benchmark ({etf} — proxy for {sector} peers)")
                parts.extend(etf_lines)

        return "\n".join(parts)
    except Exception:
        raise

def get_analyst_ratings(ticker: Annotated[str, "ticker symbol of the company"]):
    """Wall Street analyst consensus: recommendation trend + price targets."""
    try:
        ticker_upper = ticker.upper()
        ticker_obj = yf.Ticker(ticker_upper)
        parts: list[str] = [f"# Analyst Ratings & Price Targets for {ticker_upper}"]
        parts.append(f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n")

        targets = yf_retry(lambda: ticker_obj.analyst_price_targets, ticker=ticker_upper)
        if isinstance(targets, dict) and targets:
            parts.append("## Price Targets")
            for key, value in targets.items():
                parts.append(f"- {key}: {value}")

        recommendations = yf_retry(lambda: ticker_obj.recommendations, ticker=ticker_upper)
        if recommendations is not None and not recommendations.empty:
            parts.append("\n## Recommendation Trend (analyst counts by period)")
            parts.append(recommendations.to_csv(index=False))

        info = yf_retry(lambda: ticker_obj.info, ticker=ticker_upper) or {}
        if len(parts) <= 2 or ("## Price Targets" not in "\n".join(parts) and info.get("targetMeanPrice")):
            rec_key = info.get("recommendationKey", "N/A")
            num_opinions = info.get("numberOfAnalystOpinions", "N/A")
            target_mean = info.get("targetMeanPrice")
            target_high = info.get("targetHighPrice")
            target_low = info.get("targetLowPrice")
            current_p = info.get("currentPrice") or info.get("regularMarketPrice")

            if target_mean or rec_key != "N/A":
                parts.append("\n## Summary Consensus & Target Ratings (from Info Overview)")
                parts.append(f"- Recommendation Key: {rec_key}")
                parts.append(f"- Number of Analysts: {num_opinions}")
                if current_p:
                    parts.append(f"- Current Price: {current_p}")
                if target_mean:
                    parts.append(f"- Target Mean Price: {target_mean}")
                if target_high:
                    parts.append(f"- Target High Price: {target_high}")
                if target_low:
                    parts.append(f"- Target Low Price: {target_low}")

        if len(parts) <= 2:
            return f"No analyst ratings data found for symbol '{ticker}'"
        return "\n".join(parts)
    except Exception:
        raise

def get_options_data(ticker: Annotated[str, "ticker symbol of the company"]):
    """Retrieve options chain summary metrics (Put/Call ratios, IV, Open Interest)."""
    try:
        ticker_upper = ticker.upper()
        ticker_obj = yf.Ticker(ticker_upper)
        expirations = yf_retry(lambda: ticker_obj.options, ticker=ticker_upper)
        if not expirations:
            return f"No options chain data available for symbol '{ticker_upper}' (symbol may not trade options or market is closed)."

        parts: list[str] = [f"# Options Market Derivatives & Chain Summary for {ticker_upper}"]
        parts.append(f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n")
        parts.append(f"- Available Expirations ({len(expirations)}): {', '.join(expirations[:5])}")

        total_call_vol = 0
        total_put_vol = 0
        total_call_oi = 0
        total_put_oi = 0
        iv_list = []

        for exp in expirations[:2]:
            # Bind exp per iteration; a late-invoked lambda would otherwise read
            # whichever expiration the loop had reached.
            chain = yf_retry(lambda exp=exp: ticker_obj.option_chain(exp), ticker=ticker_upper)
            if chain is None:
                continue
            calls = chain.calls
            puts = chain.puts
            if calls is not None and not calls.empty:
                if "volume" in calls.columns:
                    total_call_vol += calls["volume"].fillna(0).sum()
                if "openInterest" in calls.columns:
                    total_call_oi += calls["openInterest"].fillna(0).sum()
                if "impliedVolatility" in calls.columns:
                    iv_list.extend(calls["impliedVolatility"].dropna().tolist())
            if puts is not None and not puts.empty:
                if "volume" in puts.columns:
                    total_put_vol += puts["volume"].fillna(0).sum()
                if "openInterest" in puts.columns:
                    total_put_oi += puts["openInterest"].fillna(0).sum()
                if "impliedVolatility" in puts.columns:
                    iv_list.extend(puts["impliedVolatility"].dropna().tolist())

        pc_vol_ratio = (total_put_vol / total_call_vol) if total_call_vol > 0 else 0.0
        pc_oi_ratio = (total_put_oi / total_call_oi) if total_call_oi > 0 else 0.0
        mean_iv = (sum(iv_list) / len(iv_list) * 100) if iv_list else 0.0

        parts.append("\n## Options Sentiment & Volatility Metrics")
        parts.append(f"- Total Call Volume (near-term): {int(total_call_vol):,}")
        parts.append(f"- Total Put Volume (near-term): {int(total_put_vol):,}")
        parts.append(f"- Put/Call Volume Ratio: {pc_vol_ratio:.2f}")
        parts.append(f"- Total Call Open Interest: {int(total_call_oi):,}")
        parts.append(f"- Total Put Open Interest: {int(total_put_oi):,}")
        parts.append(f"- Put/Call Open Interest Ratio: {pc_oi_ratio:.2f}")
        parts.append(f"- Average Implied Volatility (IV): {mean_iv:.2f}%")

        near_exp = expirations[0]
        near_chain = yf_retry(lambda: ticker_obj.option_chain(near_exp), ticker=ticker_upper)
        if near_chain and near_chain.calls is not None and not near_chain.calls.empty:
            cols = [c for c in ["strike", "lastPrice", "volume", "openInterest", "impliedVolatility"] if c in near_chain.calls.columns]
            if "openInterest" in cols:
                top_calls = near_chain.calls.sort_values("openInterest", ascending=False).head(5)
                parts.append(f"\n## Top Call Options by Open Interest (Exp: {near_exp})")
                parts.append(top_calls[cols].to_csv(index=False))

        if near_chain and near_chain.puts is not None and not near_chain.puts.empty:
            cols = [c for c in ["strike", "lastPrice", "volume", "openInterest", "impliedVolatility"] if c in near_chain.puts.columns]
            if "openInterest" in cols:
                top_puts = near_chain.puts.sort_values("openInterest", ascending=False).head(5)
                parts.append(f"\n## Top Put Options by Open Interest (Exp: {near_exp})")
                parts.append(top_puts[cols].to_csv(index=False))

        return "\n".join(parts)
    except Exception as exc:
        return f"Options data currently unavailable for '{ticker}': {exc}"

def get_macro_data(curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None):
    """Retrieve macro benchmarks strictly as observed on or before ``curr_date``.

    The returned trend and percentile are calculated only from observations
    available by the requested date.  This keeps the macro prompt grounded and
    avoids asking the model to invent historical context from a single quote.
    """
    try:
        target = datetime.strptime(curr_date, "%Y-%m-%d").date() if curr_date else datetime.now(UTC).date()
        macro_tickers = {
            "VIX Volatility Index": "^VIX",
            "10-Year Treasury Yield": "^TNX",
            "Crude Oil WTI": "CL=F",
            "Gold Futures": "GC=F",
            "US Dollar Index ETF": "UUP",
            "S&P 500 Index": "^GSPC",
        }
        parts = [
            "# Point-in-Time Macroeconomic Benchmark Indicators",
            f"# Analysis as-of date: {target.isoformat()}",
            "# Values, trends, and percentiles use only market closes on or before the as-of date.",
            "| Indicator | Symbol | Last value | Observed | 20-session trend | 1-year percentile |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        start_date = (target - timedelta(days=400)).isoformat()
        end_date = (target + timedelta(days=1)).isoformat()

        observations = 0
        for label, symbol in macro_tickers.items():
            try:
                ticker_obj = yf.Ticker(symbol)
                hist = yf_retry(
                    lambda t=ticker_obj: t.history(start=start_date, end=end_date, raise_errors=True),
                    ticker=symbol,
                )
                if hist is None or hist.empty or "Close" not in hist:
                    continue
                if hist.index.tz is not None:
                    hist.index = hist.index.tz_localize(None)
                hist = hist[hist.index.date <= target]
                close = hist["Close"].dropna()
                if close.empty:
                    continue
                raw_value = float(close.iloc[-1])
                display_value = raw_value / 10.0 if symbol == "^TNX" else raw_value
                suffix = "%" if symbol == "^TNX" else ""
                observed_on = close.index[-1].date().isoformat()
                trailing = close.tail(252)
                percentile = float((trailing <= raw_value).mean() * 100.0)
                if len(close) >= 21 and float(close.iloc[-21]) != 0:
                    trend_pct = (raw_value / float(close.iloc[-21]) - 1.0) * 100.0
                    trend_text = f"{trend_pct:+.2f}%"
                else:
                    trend_text = "n/a"
                parts.append(
                    f"| {label} | {symbol} | {display_value:.2f}{suffix} | {observed_on} | "
                    f"{trend_text} | {percentile:.1f}% |"
                )
                observations += 1
            except Exception as exc:
                _logger.debug("Failed fetching historical macro symbol %s: %s", symbol, exc)

        if observations == 0:
            return f"No point-in-time macro indicator data was available on or before {target.isoformat()}."
        return "\n".join(parts)
    except Exception as exc:
        return f"Point-in-time macro indicator data currently unavailable: {exc}"

def get_catalyst_calendar(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "analysis reference date in YYYY-MM-DD format"] = None,
):
    """Upcoming known catalysts: next earnings date, ex-dividend date, and any
    recent/scheduled earnings dates with EPS estimates."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        parts: list[str] = [f"# Catalyst Calendar for {ticker.upper()} (live provider snapshot)"]
        parts.append(f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n")
        if curr_date:
            parts.append(
                f"# Analysis reference date: {curr_date}. This is a live calendar, not a point-in-time historical "
                "snapshot; do not call any event before the reference date 'upcoming'.\n"
            )

        calendar = yf_retry(lambda: ticker_obj.calendar, ticker=ticker)
        if isinstance(calendar, dict) and calendar:
            parts.append("## Scheduled Events")
            for key, value in calendar.items():
                parts.append(f"- {key}: {value}")

        try:
            earnings_dates = yf_retry(lambda: ticker_obj.get_earnings_dates(limit=8), ticker=ticker)
        except Exception as _e:
            _logger.warning("get_earnings_dates failed for %s: %s", ticker, _e)
            earnings_dates = None
        if earnings_dates is not None and not earnings_dates.empty:
            parts.append("\n## Provider Earnings Dates (verify date status against the analysis reference date)")
            parts.append(earnings_dates.head(8).to_csv())

        if len(parts) <= 2:
            return f"No upcoming catalyst data found for symbol '{ticker}'"
        return "\n".join(parts)
    except Exception:
        raise

def get_institutional_holdings(ticker: Annotated[str, "ticker symbol of the company"]):
    """Institutional (13F) and major-holder breakdown for a company."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        parts: list[str] = [f"# Institutional & Major Holders for {ticker.upper()}"]
        parts.append(f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n")

        major = yf_retry(lambda: ticker_obj.major_holders, ticker=ticker)
        if major is not None and not major.empty:
            parts.append("## Major Holders Breakdown")
            parts.append(major.to_csv())

        inst = yf_retry(lambda: ticker_obj.institutional_holders, ticker=ticker)
        if inst is not None and not inst.empty:
            parts.append("## Top Institutional Holders (13F)")
            parts.append(inst.head(15).to_csv(index=False))

        funds = yf_retry(lambda: ticker_obj.mutualfund_holders, ticker=ticker)
        if funds is not None and not funds.empty:
            parts.append("## Top Mutual Fund Holders")
            parts.append(funds.head(15).to_csv(index=False))

        if len(parts) <= 2:
            return f"No institutional holdings data found for symbol '{ticker}'"
        return "\n".join(parts)
    except Exception:
        raise

def get_sec_filings(ticker: Annotated[str, "ticker symbol of the company"]):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: getattr(ticker_obj, "sec_filings", None), ticker=ticker)
        if data is None or len(data) == 0:
            return f"No SEC filings data found for symbol '{ticker}'"

        import pandas as pd

        df = pd.DataFrame(data)
        cols_to_keep = ["date", "type", "title", "edgarUrl"]
        df = df[[c for m, c in enumerate(cols_to_keep) if c in df.columns]]

        csv_string = df.to_csv(index=False)
        header = f"# SEC Filings for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception:
        raise
