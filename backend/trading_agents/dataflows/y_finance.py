import logging
import re
from datetime import datetime
from typing import Annotated

import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta

from .stockstats_utils import filter_financials_by_date, load_ohlcv, yf_retry

_logger = logging.getLogger(__name__)


def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    ticker = yf.Ticker(symbol.upper())
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_date))
    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)
    csv_string = data.to_csv()
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string


def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    from backend.services.indicator_service import calculate_ema, calculate_macd, calculate_rsi

    data = load_ohlcv(symbol, curr_date)
    if data.empty:
        return f"No data found for {symbol}"

    if "Date" in data.columns:
        data = data.set_index("Date")

    # Calculate requested indicator using central service
    series = data["Close"]
    res_series = None

    if indicator == "rsi":
        res_series = calculate_rsi(series)
    elif indicator == "macd":
        macd_line, _ = calculate_macd(series)
        res_series = macd_line
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

    if res_series is None:
        return f"Indicator {indicator} not yet supported in centralized service"

    # Filter and format output
    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - relativedelta(days=look_back_days)

    # Align and filter
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
    _ = curr_date
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info)
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
                lines.append(f"{label}: {value}")
        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + "\n".join(lines)
    except Exception:
        # Re-raise so route_to_vendor can fall back to another vendor instead of
        # returning (and caching) an error string the router treats as data.
        raise


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet)
        data = filter_financials_by_date(data, curr_date)
        if data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
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
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow)
        data = filter_financials_by_date(data, curr_date)
        if data.empty:
            return f"No cash flow data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
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
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt)
        data = filter_financials_by_date(data, curr_date)
        if data.empty:
            return f"No income statement data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception:
        raise


def get_insider_transactions(ticker: Annotated[str, "ticker symbol of the company"]):
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: ticker_obj.insider_transactions)
        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"
        # Keep only the most recent rows; older Form 4 filings add tokens without
        # changing the signal the analyst is reading.
        csv_string = data.head(25).to_csv()
        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception:
        raise


def get_catalyst_calendar(ticker: Annotated[str, "ticker symbol of the company"]):
    """Upcoming known catalysts: next earnings date, ex-dividend date, and any
    recent/scheduled earnings dates with EPS estimates."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        parts: list[str] = [f"# Upcoming Catalysts for {ticker.upper()}"]
        parts.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        calendar = yf_retry(lambda: ticker_obj.calendar)
        if isinstance(calendar, dict) and calendar:
            parts.append("## Scheduled Events")
            for key, value in calendar.items():
                parts.append(f"- {key}: {value}")

        try:
            earnings_dates = yf_retry(lambda: ticker_obj.get_earnings_dates(limit=8))
        except Exception:
            earnings_dates = None
        if earnings_dates is not None and not earnings_dates.empty:
            parts.append("\n## Recent & Upcoming Earnings Dates")
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
        parts.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        major = yf_retry(lambda: ticker_obj.major_holders)
        if major is not None and not major.empty:
            parts.append("## Major Holders Breakdown")
            parts.append(major.to_csv())

        inst = yf_retry(lambda: ticker_obj.institutional_holders)
        if inst is not None and not inst.empty:
            parts.append("## Top Institutional Holders (13F)")
            parts.append(inst.head(15).to_csv(index=False))

        funds = yf_retry(lambda: ticker_obj.mutualfund_holders)
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
        data = yf_retry(lambda: getattr(ticker_obj, "sec_filings", None))
        if data is None or len(data) == 0:
            return f"No SEC filings data found for symbol '{ticker}'"

        import pandas as pd

        df = pd.DataFrame(data)
        # Drop excessive columns for context efficiency
        cols_to_keep = ["date", "type", "title", "edgarUrl"]
        df = df[[c for m, c in enumerate(cols_to_keep) if c in df.columns]]

        csv_string = df.to_csv(index=False)
        header = f"# SEC Filings for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception:
        raise
