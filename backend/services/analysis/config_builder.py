from __future__ import annotations

import json
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings as _cfg
from backend.models.settings import AppSettings
from backend.services.user_service import decrypt_api_keys, get_user_api_key
from backend.trading_agents.default_config import DEFAULT_CONFIG

_logger = logging.getLogger(__name__)


async def get_historical_analyses_context(
    ticker: str, trade_date: str, db: AsyncSession, limit: int = 5, output_language: str = "English"
) -> str:
    from backend.repositories.analysis import list_cross_ticker_lessons, list_historical_analyses

    # 1. Fetch same-ticker historical analyses
    rows_same = await list_historical_analyses(db, ticker=ticker, before_trade_date=trade_date, limit=limit)

    # 2. Fetch cross-ticker lessons (those with populated reflection)
    rows_cross = await list_cross_ticker_lessons(db, exclude_ticker=ticker, limit=3)

    if not rows_same and not rows_cross:
        return ""

    from backend.core.l10n import get_message

    parts = []

    if rows_same:
        parts.append(get_message("historical_reports_title", output_language, ticker=ticker))
        for row in reversed(rows_same):
            date_label = get_message("date_signal_label", output_language, date=row.trade_date)
            parts.append(f"--- {date_label}: {row.signal or 'N/A'} ---")
            parts.append(f"Final Decision:\n{row.final_decision}")
            if row.reflection:
                parts.append(f"Reflection/Outcome:\n{row.reflection}")
            parts.append("")

    if rows_cross:
        parts.append(get_message("cross_ticker_lessons_title", output_language))
        for row in rows_cross:
            parts.append(f"--- Ticker: {row.ticker} | Date: {row.trade_date} ---")
            parts.append(f"Reflection:\n{row.reflection}")
            parts.append("")

    return "\n".join(parts)


def inject_tool_credentials(config: dict) -> None:
    runtime_tool_context = config.get("runtime_tool_context")
    if not runtime_tool_context:
        return
    user_settings = runtime_tool_context.get("user_settings", {})
    server_settings = runtime_tool_context.get("server_settings", {})

    reddit_user = user_settings.get("reddit_sentiment", {}).get("settings", {})
    config["reddit_client_id"] = reddit_user.get("reddit_client_id")
    config["reddit_client_secret"] = reddit_user.get("reddit_client_secret")
    config["reddit_user_agent"] = reddit_user.get("reddit_user_agent")

    search_user = user_settings.get("search_web", {}).get("settings", {})
    config["searxng_url"] = search_user.get("searxng_url")

    stock_server = server_settings.get("core_stock_data", {}).get("settings", {})
    config["alpha_vantage_api_key"] = stock_server.get("alpha_vantage_api_key")


def build_analysis_config(settings: AppSettings, user=None, sys_settings=None) -> dict:
    _vendor_default = getattr(sys_settings, "active_data_vendor", None) or "yfinance"

    def _vendor(field: str) -> str:
        return getattr(sys_settings, field, None) or _vendor_default

    cfg: dict = {
        "data_cache_dir": os.environ.get("TRADINGAGENTS_DATA_CACHE_DIR", DEFAULT_CONFIG["data_cache_dir"]),
        "results_dir": os.environ.get("TRADINGAGENTS_RESULTS_DIR", DEFAULT_CONFIG["results_dir"]),
        "memory_log_path": os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH", DEFAULT_CONFIG["memory_log_path"]),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "max_debate_rounds": settings.max_debate_rounds,
        "max_risk_discuss_rounds": settings.max_risk_rounds,
        "output_language": settings.output_language or DEFAULT_CONFIG["output_language"],
        "investor_persona": settings.investor_persona or DEFAULT_CONFIG["investor_persona"],
        "analyst_concurrency_limit": settings.analyst_concurrency_limit or DEFAULT_CONFIG["analyst_concurrency_limit"],
        "skip_disk_log": True,
        "checkpoint_enabled": True,
        "node_retry_attempts": getattr(settings, "node_retry_attempts", DEFAULT_CONFIG["node_retry_attempts"])
        or DEFAULT_CONFIG["node_retry_attempts"],
        "node_retry_base_delay": getattr(settings, "node_retry_base_delay", DEFAULT_CONFIG["node_retry_base_delay"])
        or DEFAULT_CONFIG["node_retry_base_delay"],
        "strict_backtest_learning": getattr(
            settings, "strict_backtest_learning", DEFAULT_CONFIG["strict_backtest_learning"]
        )
        if getattr(settings, "strict_backtest_learning", None) is not None
        else DEFAULT_CONFIG["strict_backtest_learning"],
        "max_recur_limit": getattr(settings, "max_recur_limit", DEFAULT_CONFIG["max_recur_limit"])
        or DEFAULT_CONFIG["max_recur_limit"],
        "news_article_limit": getattr(settings, "news_article_limit", DEFAULT_CONFIG["news_article_limit"])
        or DEFAULT_CONFIG["news_article_limit"],
        "global_news_article_limit": getattr(
            settings, "global_news_article_limit", DEFAULT_CONFIG["global_news_article_limit"]
        )
        or DEFAULT_CONFIG["global_news_article_limit"],
        "global_news_lookback_days": getattr(
            settings, "global_news_lookback_days", DEFAULT_CONFIG["global_news_lookback_days"]
        )
        or DEFAULT_CONFIG["global_news_lookback_days"],
        "data_vendors": {
            "core_stock_apis": _vendor("data_vendor_core_stock"),
            "technical_indicators": _vendor("data_vendor_technicals"),
            "fundamental_data": _vendor("data_vendor_fundamentals"),
            "news_data": _vendor("data_vendor_news"),
        },
        "is_admin": getattr(user, "is_admin", False) if user is not None else False,
        "has_user": user is not None,
    }
    if getattr(settings, "benchmark_ticker", None):
        cfg["benchmark_ticker"] = settings.benchmark_ticker

    if user is not None:
        try:
            fernet = _cfg().get_fernet()
            current_provider = cfg.get("llm_provider", "openai")
            user_key = get_user_api_key(user, current_provider, fernet)
            if user.api_keys_enc:
                cfg["user_api_keys"] = decrypt_api_keys(user.api_keys_enc, fernet)
            else:
                cfg["user_api_keys"] = {}
        except Exception as e:
            _logger.error("Failed to decrypt user API keys in build_analysis_config: %s", e)
            user_key = None
            cfg["user_api_keys"] = {}
        if user_key:
            cfg["api_key"] = user_key
    return cfg


def history_json_from(value):
    if not value:
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        val_s = value.strip()
        if (val_s.startswith("[") and val_s.endswith("]")) or (val_s.startswith("{") and val_s.endswith("}")):
            try:
                return json.loads(val_s)
            except Exception as e:
                _logger.debug("Failed parsing history JSON string: %s", e)
    return value


async def prepare_graph_config(db: AsyncSession, user_id: int | None, config: dict) -> list[str]:
    """Resolve the user's permitted analysts and inject runtime tool/agent
    context + credentials into ``config``; returns the permitted analyst keys.

    Shared by the single- and multi-ticker orchestrators so the
    security-sensitive agent-access filtering can't diverge between them.
    """
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.services.tool_access_service import get_user_agent_access
    from backend.services.tool_settings_service import build_global_runtime_context
    from backend.trading_agents.agent_catalog import list_analysts

    agent_access_map = await get_user_agent_access(db, user_id) if user_id else {}
    permitted_analysts = [a.key for a in list_analysts() if agent_access_map.get(a.key, True)]

    config["runtime_tool_context"] = await build_global_runtime_context(db, user_id)
    config["runtime_agent_context"] = await build_agent_runtime_context(db, user_id)
    inject_tool_credentials(config)
    return permitted_analysts
