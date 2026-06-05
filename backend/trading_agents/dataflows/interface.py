from typing import Annotated
import logging
import inspect
import asyncio

from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
    get_sec_filings as get_yfinance_sec_filings,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .utils import safe_ticker_component
from .config import get_config
from .cache import APICache, TOOLS_CATEGORIES, get_category_for_method
from .reddit import fetch_reddit_posts
from .stocktwits import fetch_stocktwits_messages

_logger = logging.getLogger(__name__)

_TICKER_FIRST_METHODS = frozenset({
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_insider_transactions",
    "get_sec_filings",
    "fetch_reddit_posts",
    "fetch_stocktwits_messages",
})

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]

VENDOR_METHODS = {
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    "get_sec_filings": {
        "yfinance": get_yfinance_sec_filings,
    },
    "fetch_reddit_posts": {
        "reddit": fetch_reddit_posts,
    },
    "fetch_stocktwits_messages": {
        "stocktwits": fetch_stocktwits_messages,
    },
}

def get_vendor(category: str, method: str = None) -> str:
    config = get_config()
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    return config.get("data_vendors", {}).get(category, "default")

async def route_to_vendor(method: str, *args, **kwargs):
    if method in _TICKER_FIRST_METHODS and args:
        safe_ticker_component(args[0])
    
    cached_val = APICache.get(method, *args, **kwargs)
    if cached_val is not None:
        return cached_val
    
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]
    
    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")
    
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)
            
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue
            
        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
        
        try:
            if inspect.iscoroutinefunction(impl_func):
                val = await impl_func(*args, **kwargs)
            else:
                # Wrap synchronous vendor calls in a thread to keep the event loop responsive
                val = await asyncio.to_thread(impl_func, *args, **kwargs)
                
            APICache.set(method, val, *args, **kwargs)
            return val
        except AlphaVantageRateLimitError:
            continue
            
    raise RuntimeError(f"No available vendor for '{method}'")
