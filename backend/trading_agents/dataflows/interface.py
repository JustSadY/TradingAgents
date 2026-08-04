import asyncio
import inspect
import logging

from backend.core.utils import safe_ticker_component

from .alpha_vantage import (
    get_balance_sheet as get_alpha_vantage_balance_sheet,
)
from .alpha_vantage import (
    get_cashflow as get_alpha_vantage_cashflow,
)
from .alpha_vantage import (
    get_fundamentals as get_alpha_vantage_fundamentals,
)
from .alpha_vantage import (
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage import (
    get_income_statement as get_alpha_vantage_income_statement,
)
from .alpha_vantage import (
    get_indicator as get_alpha_vantage_indicator,
)
from .alpha_vantage import (
    get_insider_transactions as get_alpha_vantage_insider_transactions,
)
from .alpha_vantage import (
    get_news as get_alpha_vantage_news,
)
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .cache import APICache, get_category_for_method
from .config import get_config
from .reddit import fetch_reddit_posts
from .stockstats_utils import YFinanceTickerUnavailableError
from .stocktwits import StockTwitsUnavailable, fetch_stocktwits_messages
from .y_finance import (
    get_analyst_ratings as get_yfinance_analyst_ratings,
)
from .y_finance import (
    get_balance_sheet as get_yfinance_balance_sheet,
)
from .y_finance import (
    get_cashflow as get_yfinance_cashflow,
)
from .y_finance import (
    get_catalyst_calendar as get_yfinance_catalyst_calendar,
)
from .y_finance import (
    get_fundamentals as get_yfinance_fundamentals,
)
from .y_finance import (
    get_income_statement as get_yfinance_income_statement,
)
from .y_finance import (
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .y_finance import (
    get_institutional_holdings as get_yfinance_institutional_holdings,
)
from .y_finance import (
    get_sec_filings as get_yfinance_sec_filings,
)
from .y_finance import (
    get_short_interest as get_yfinance_short_interest,
)
from .y_finance import (
    get_stock_stats_indicators_window,
    get_yfin_data_online,
)
from .y_finance import (
    get_macro_data as get_yfinance_macro_data,
    get_options_data as get_yfinance_options_data,
    get_valuation_comparison as get_yfinance_valuation_comparison,
)
from .yfinance_news import get_global_news_yfinance, get_news_yfinance

_logger = logging.getLogger(__name__)

_TICKER_FIRST_METHODS = frozenset(
    {
        "get_stock_data",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_news",
        "get_insider_transactions",
        "get_sec_filings",
        "get_institutional_holdings",
        "get_catalyst_calendar",
        "get_analyst_ratings",
        "get_short_interest",
        "get_valuation_comparison",
        "fetch_reddit_posts",
        "fetch_stocktwits_messages",
    }
)


_LIVE_ONLY_METHODS = frozenset(
    {
        "get_fundamentals",
        "get_insider_transactions",
        "get_sec_filings",
        "get_institutional_holdings",
        "get_catalyst_calendar",
        "get_analyst_ratings",
        "get_short_interest",
        "get_valuation_comparison",
        "get_options_data",
        "fetch_reddit_posts",
        "fetch_stocktwits_messages",
    }
)

def _historical_live_data_block(method: str) -> str | None:
    """Fail closed when a historical run reaches a live-only data source."""
    config = get_config()
    historical_mode = bool(config.get("historical_mode", False))
    allow_live = bool(config.get("allow_live_data_in_historical", False))
    trade_date = str(config.get("trade_date") or "")

    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None) or {}
        historical_mode = bool(ctx.get("historical_mode", historical_mode))
        allow_live = bool(ctx.get("allow_live_data_in_historical", allow_live))
        trade_date = str(ctx.get("trade_date") or trade_date)
    except Exception:
        pass

    if historical_mode and not allow_live and method in _LIVE_ONLY_METHODS:
        label = trade_date or "the requested historical date"
        return (
            "# POINT-IN-TIME DATA UNAVAILABLE\n"
            f"The data source for `{method}` is live-only and was not queried during "
            f"the historical run for {label}. No current data was substituted."
        )
    return None

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]

VENDOR_METHODS = {
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_yfin_data_online,
    },
    "get_indicators": {
        "yfinance": get_stock_stats_indicators_window,
        "alpha_vantage": get_alpha_vantage_indicator,
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
    "get_institutional_holdings": {
        "yfinance": get_yfinance_institutional_holdings,
    },
    "get_catalyst_calendar": {
        "yfinance": get_yfinance_catalyst_calendar,
    },
    "get_analyst_ratings": {
        "yfinance": get_yfinance_analyst_ratings,
    },
    "get_short_interest": {
        "yfinance": get_yfinance_short_interest,
    },
    "get_valuation_comparison": {
        "yfinance": get_yfinance_valuation_comparison,
    },
    "get_options_data": {
        "yfinance": get_yfinance_options_data,
    },
    "get_macro_data": {
        "yfinance": get_yfinance_macro_data,
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

_VENDOR_CALL_TIMEOUT = 60

async def route_to_vendor(method: str, *args, **kwargs):
    blocked = _historical_live_data_block(method)
    if blocked is not None:
        return blocked

    if method in _TICKER_FIRST_METHODS and args:
        safe_ticker_component(args[0])

    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    cache_scope = f"vendors:{vendor_config}"
    cached_val = APICache.get(method, *args, cache_scope=cache_scope, **kwargs)
    if cached_val is not None:
        return cached_val

    primary_vendors = [v.strip() for v in vendor_config.split(",")]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    last_error: Exception | None = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            if inspect.iscoroutinefunction(impl_func):
                val = await impl_func(*args, **kwargs)
            else:
                val = await asyncio.wait_for(
                    asyncio.to_thread(impl_func, *args, **kwargs),
                    timeout=_VENDOR_CALL_TIMEOUT,
                )

            if isinstance(val, StockTwitsUnavailable):
                return val
            APICache.set(method, val, *args, cache_scope=cache_scope, **kwargs)
            return val
        except TimeoutError as exc:
            _logger.warning("Vendor '%s' timed out for method '%s' (timeout=%ss)", vendor, method, _VENDOR_CALL_TIMEOUT)
            last_error = exc
            continue
        except YFinanceTickerUnavailableError as exc:
            log = _logger.debug if exc.from_cooldown else _logger.warning
            log("Vendor '%s' cannot serve ticker for method '%s': %s", vendor, method, exc)
            last_error = exc
            continue
        except Exception as exc:
            if not isinstance(exc, AlphaVantageRateLimitError):
                _logger.warning("Vendor '%s' failed for method '%s': %s", vendor, method, exc)
            last_error = exc
            continue

    if last_error is not None:
        raise RuntimeError(f"All vendors failed for '{method}': {last_error}") from last_error
    raise RuntimeError(f"No available vendor for '{method}'")
