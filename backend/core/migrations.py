"""Lightweight, idempotent SQLite schema compatibility helpers.

Production PostgreSQL databases are migrated by Alembic.  These additive
helpers remain for SQLite development/test databases, where ``create_all`` is
used to keep the local setup lightweight. Table names are validated against an
allow-list so the hand-built DDL strings can never reference an unexpected
table.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import inspect, text

from backend.core.constants import WEBHOOK_EVENTS

_logger = logging.getLogger(__name__)

_ALLOWED_TABLES = {
    "users",
    "app_settings",
    "analysis_results",
    "portfolios",
    "orders",
    "holdings",
    "multi_ticker_analyses",
    "config_presets",
    "price_alerts",
    "system_settings",
    "system_logs",
    "news_analysis_cache",
    "analyst_report_cache",
}

_ALLOWED_COLUMNS = {
    "users": {"email", "role", "display_name", "api_keys_enc", "token_version"},
    "system_settings": {
        "data_vendor_core_stock",
        "data_vendor_technicals",
        "data_vendor_fundamentals",
        "data_vendor_news",
        "trading_mode",
        "active_broker",
        "active_data_vendor",
        "updated_at",
    },
    "app_settings": {
        "user_id",
        "llm_model",
        "fallback_llm_chain",
        "openai_reasoning_effort",
        "anthropic_effort",
        "google_thinking_level",
        "output_language",
        "investor_persona",
        "analyst_concurrency_limit",
        "max_recur_limit",
        "benchmark_ticker",
        "webhook_url",
        "webhook_enabled",
        "webhook_events",
        "active_preset_name",
        "max_debate_rounds",
        "max_risk_rounds",
        "max_position_size_pct",
        "max_risk_per_trade_pct",
        "allow_short_selling",
        "max_concentration_pct",
        "max_gross_exposure",
        "strict_stop_loss_mode",
        "correlation_risk_enabled",
        "quality_gate_enabled",
        "drawdown_breaker_enabled",
        "max_portfolio_drawdown_pct",
        "node_retry_attempts",
        "node_retry_base_delay",
        "node_timeout_seconds",
        "tool_timeout_seconds",
        "circuit_breaker_threshold",
        "circuit_breaker_cooldown",
        "stall_timeout_seconds",
        "max_active_alerts",
        "max_ai_alerts_per_run",
        "ai_alert_cooldown_hours",
        "llm_provider",
        "cron_enabled",
        "cron_schedule",
        "price_tolerance_pct",
        "agent_qa_enabled",
        "memory_store",
        "pinecone_index",
        "pinecone_cloud",
        "pinecone_region",
        "memory_embedder",
        "pinecone_embed_model",
        "memory_openai_embed_model",
        "memory_ollama_embed_model",
        "anthropic_prompt_caching",
        "max_report_chars_in_prompts",
        "max_debate_history_chars",
        "max_tool_output_chars",
        "analyst_prefilter_enabled",
        "analyst_prefilter_min_samples",
        "analyst_prefilter_max_win_rate",
        "watchlist",
        "memory_recall_count",
        "summary_only_mode",
        "news_article_limit",
        "global_news_article_limit",
        "global_news_lookback_days",
        "updated_at",
    },
    "analysis_results": {
        "user_id",
        "bull_history",
        "bear_history",
        "investment_debate_history",
        "risk_debate_history",
        "judge_decision",
        "chart_annotations",
        "insider_report",
        "ownership_report",
        "ratings_report",
        "short_interest_report",
        "valuation_report",
        "catalyst_report",
        "quality",
        "raw_return",
        "alpha_return",
        "holding_days",
        "llm_provider",
        "llm_model",
        "preset_name",
        "reflection",
        "llm_calls",
        "tool_calls",
        "tokens_in",
        "tokens_out",
        "duration_seconds",
        "triggered_by",
        "task_id",
        "agent_qa_report",
        "status",
        "synthesis_report",
        "audit_report",
        "degraded",
        "failed_agents",
    },
    "news_analysis_cache": {
        "id",
        "user_id",
        "ticker",
        "articles_hash",
        "config_fingerprint",
        "analysis_result",
        "created_at",
    },
    "analyst_report_cache": {
        "id",
        "user_id",
        "analyst_key",
        "ticker",
        "data_hash",
        "config_fingerprint",
        "analysis_result",
        "created_at",
    },
    "portfolios": {"user_id", "initial_capital", "current_balance", "cash_available", "margin_used"},
    "config_presets": {"user_id"},
    "price_alerts": {"user_id", "target_price", "alert_type", "creation_source", "creation_run_id"},
    "multi_ticker_analyses": {"user_id"},
    "orders": {
        "quantity_requested",
        "quantity_filled",
        "price_per_share",
        "total_value",
        "commission",
        "entry_commission",
        "leverage",
        "side",
        "realized_pnl",
    },
    "holdings": {
        "quantity",
        "avg_buy_price",
        "current_price",
        "unrealized_pnl",
        "entry_commission",
        "side",
        "leverage",
        "margin_used",
        "borrowed_amount",
        "liquidation_price",
        "interest_accrued",
        "opened_at",
        "stop_loss",
        "take_profit",
    },
    "system_logs": {
        "level",
        "source",
        "message",
        "details",
        "user_id",
        "created_at",
    },
}

_TYPE_TEXT_DEFAULT_EMPTY = "TEXT DEFAULT ''"
_TYPE_VARCHAR_100 = "VARCHAR(100)"
_TYPE_VARCHAR_50 = "VARCHAR(50)"
_TYPE_VARCHAR_20 = "VARCHAR(20)"
_TYPE_VARCHAR_30 = "VARCHAR(30)"
_TYPE_VARCHAR_60 = "VARCHAR(60)"
_TYPE_VARCHAR_255 = "VARCHAR(255)"
_TYPE_VARCHAR_500 = "VARCHAR(500)"
_TYPE_BOOLEAN_DEFAULT_FALSE = "BOOLEAN DEFAULT FALSE"
_TYPE_BOOLEAN_DEFAULT_TRUE = "BOOLEAN DEFAULT TRUE"
_TYPE_INTEGER_DEFAULT_0 = "INTEGER DEFAULT 0"
_TYPE_INTEGER_DEFAULT_1 = "INTEGER DEFAULT 1"
_TYPE_VARCHAR_50_YFINANCE = "VARCHAR(50) DEFAULT 'yfinance'"
_TYPE_TIMESTAMP_WITH_TZ = "TIMESTAMP WITH TIME ZONE"
_TYPE_NUMERIC_20_8_DEFAULT_0 = "NUMERIC(20, 8) DEFAULT 0"
_TYPE_NUMERIC_20_8_DEFAULT_1 = "NUMERIC(20, 8) DEFAULT 1"
_TYPE_VARCHAR_5_DEFAULT_LONG = "VARCHAR(5) DEFAULT 'long'"
_TYPE_VARCHAR_20_DEFAULT_PRICE = "VARCHAR(20) DEFAULT 'price'"
_TYPE_VARCHAR_20_DEFAULT_MANUAL = "VARCHAR(20) DEFAULT 'manual'"
_TYPE_VARCHAR_20_DEFAULT_COMPLETED = "VARCHAR(20) DEFAULT 'completed'"
_TYPE_VARCHAR_20_DEFAULT_USER = "VARCHAR(20) DEFAULT 'user'"
_TYPE_VARCHAR_20_DEFAULT_SIMULATION = "VARCHAR(20) DEFAULT 'simulation'"

_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("analysis_results", "agent_qa_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "insider_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "ownership_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "ratings_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "short_interest_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "valuation_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "catalyst_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "synthesis_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "audit_report", _TYPE_TEXT_DEFAULT_EMPTY),
    ("app_settings", "correlation_risk_enabled", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "quality_gate_enabled", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "drawdown_breaker_enabled", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "max_portfolio_drawdown_pct", "FLOAT DEFAULT 20.0"),
    ("app_settings", "memory_store", "VARCHAR(20) DEFAULT 'pinecone'"),
    ("app_settings", "pinecone_index", "VARCHAR(100) DEFAULT 'tradingagents-memory'"),
    ("app_settings", "pinecone_cloud", _TYPE_VARCHAR_20 + " DEFAULT 'aws'"),
    ("app_settings", "pinecone_region", _TYPE_VARCHAR_30 + " DEFAULT 'us-east-1'"),
    ("app_settings", "memory_embedder", _TYPE_VARCHAR_20 + " DEFAULT 'pinecone'"),
    ("app_settings", "pinecone_embed_model", _TYPE_VARCHAR_60 + " DEFAULT 'llama-text-embed-v2'"),
    ("app_settings", "memory_openai_embed_model", _TYPE_VARCHAR_60 + " DEFAULT 'text-embedding-3-small'"),
    ("app_settings", "memory_ollama_embed_model", _TYPE_VARCHAR_60 + " DEFAULT 'nomic-embed-text'"),
    ("app_settings", "fallback_llm_chain", "JSON NOT NULL DEFAULT '[]'"),
    ("app_settings", "agent_qa_enabled", _TYPE_BOOLEAN_DEFAULT_TRUE),
    ("app_settings", "anthropic_prompt_caching", _TYPE_BOOLEAN_DEFAULT_TRUE),
    ("app_settings", "max_report_chars_in_prompts", "INTEGER DEFAULT 6000"),
    ("app_settings", "max_debate_history_chars", "INTEGER DEFAULT 8000"),
    ("app_settings", "max_tool_output_chars", "INTEGER DEFAULT 12000"),
    ("app_settings", "analyst_prefilter_enabled", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "analyst_prefilter_min_samples", "INTEGER DEFAULT 5"),
    ("app_settings", "analyst_prefilter_max_win_rate", "FLOAT DEFAULT 40.0"),
    ("app_settings", "memory_recall_count", "INTEGER DEFAULT 5"),
    ("app_settings", "summary_only_mode", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "news_article_limit", "INTEGER DEFAULT 20"),
    ("app_settings", "global_news_article_limit", "INTEGER DEFAULT 10"),
    ("app_settings", "global_news_lookback_days", "INTEGER DEFAULT 7"),
    ("app_settings", "max_active_alerts", "INTEGER DEFAULT 30"),
    ("app_settings", "max_ai_alerts_per_run", "INTEGER DEFAULT 3"),
    ("app_settings", "ai_alert_cooldown_hours", "INTEGER DEFAULT 24"),
    ("users", "email", _TYPE_VARCHAR_255),
    ("users", "role", _TYPE_VARCHAR_20_DEFAULT_USER),
    ("users", "display_name", _TYPE_VARCHAR_100),
    ("users", "api_keys_enc", "TEXT"),
    ("users", "token_version", _TYPE_INTEGER_DEFAULT_0),
    ("system_settings", "data_vendor_core_stock", _TYPE_VARCHAR_50_YFINANCE),
    ("system_settings", "data_vendor_technicals", _TYPE_VARCHAR_50_YFINANCE),
    ("system_settings", "data_vendor_fundamentals", _TYPE_VARCHAR_50_YFINANCE),
    ("system_settings", "data_vendor_news", _TYPE_VARCHAR_50_YFINANCE),
    ("system_settings", "trading_mode", _TYPE_VARCHAR_20_DEFAULT_SIMULATION),
    ("system_settings", "active_broker", _TYPE_VARCHAR_50 + " DEFAULT 'simulation'"),
    ("system_settings", "active_data_vendor", _TYPE_VARCHAR_50_YFINANCE),
    ("system_settings", "updated_at", _TYPE_TIMESTAMP_WITH_TZ),
]

_USER_REF = "INTEGER REFERENCES users(id)"

_NEW_COLUMNS += [
    ("app_settings", "user_id", _USER_REF),
    ("analysis_results", "user_id", _USER_REF),
    ("portfolios", "user_id", _USER_REF),
    ("config_presets", "user_id", _USER_REF),
    ("price_alerts", "user_id", _USER_REF),
    ("multi_ticker_analyses", "user_id", _USER_REF),
    ("news_analysis_cache", "user_id", _USER_REF),
    ("news_analysis_cache", "config_fingerprint", "VARCHAR(64)"),
    ("analyst_report_cache", "user_id", _USER_REF),
    ("analyst_report_cache", "config_fingerprint", "VARCHAR(64)"),
]

_NEW_COLUMNS += [
    ("app_settings", "llm_model", _TYPE_VARCHAR_100 + " DEFAULT 'gpt-4o-mini'"),
    ("app_settings", "openai_reasoning_effort", _TYPE_VARCHAR_20),
    ("app_settings", "anthropic_effort", _TYPE_VARCHAR_20),
    ("app_settings", "google_thinking_level", _TYPE_VARCHAR_20),
    ("app_settings", "output_language", _TYPE_VARCHAR_50 + " DEFAULT 'English'"),
    ("app_settings", "investor_persona", _TYPE_VARCHAR_50 + " DEFAULT 'conservative'"),
    ("app_settings", "analyst_concurrency_limit", _TYPE_INTEGER_DEFAULT_1),
    ("app_settings", "max_recur_limit", "INTEGER DEFAULT 1000"),
    ("app_settings", "benchmark_ticker", _TYPE_VARCHAR_20),
    ("analysis_results", "bull_history", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "bear_history", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "investment_debate_history", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "risk_debate_history", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "judge_decision", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "chart_annotations", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "quality", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "degraded", "INTEGER DEFAULT 0"),
    ("analysis_results", "failed_agents", _TYPE_TEXT_DEFAULT_EMPTY),
    ("analysis_results", "raw_return", "FLOAT"),
    ("analysis_results", "alpha_return", "FLOAT"),
    ("analysis_results", "holding_days", "INTEGER"),
    ("analysis_results", "reflection", _TYPE_TEXT_DEFAULT_EMPTY),
    ("app_settings", "webhook_url", _TYPE_VARCHAR_500),
    ("app_settings", "webhook_enabled", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "webhook_events", "JSON NOT NULL DEFAULT '[\"analysis_complete\"]'"),
    ("app_settings", "active_preset_name", _TYPE_VARCHAR_100),
    ("analysis_results", "llm_provider", _TYPE_VARCHAR_50),
    ("analysis_results", "llm_model", _TYPE_VARCHAR_100),
    ("analysis_results", "preset_name", _TYPE_VARCHAR_100),
    ("analysis_results", "llm_calls", _TYPE_INTEGER_DEFAULT_0),
    ("analysis_results", "tool_calls", _TYPE_INTEGER_DEFAULT_0),
    ("analysis_results", "tokens_in", _TYPE_INTEGER_DEFAULT_0),
    ("analysis_results", "tokens_out", _TYPE_INTEGER_DEFAULT_0),
    ("analysis_results", "duration_seconds", "FLOAT DEFAULT 0.0"),
    ("analysis_results", "triggered_by", _TYPE_VARCHAR_20_DEFAULT_MANUAL),
    ("analysis_results", "task_id", _TYPE_VARCHAR_100),
    ("analysis_results", "status", _TYPE_VARCHAR_20_DEFAULT_COMPLETED),
    ("app_settings", "max_debate_rounds", _TYPE_INTEGER_DEFAULT_1),
    ("app_settings", "max_risk_rounds", _TYPE_INTEGER_DEFAULT_1),
    ("app_settings", "max_position_size_pct", "FLOAT DEFAULT 10.0"),
    ("app_settings", "max_risk_per_trade_pct", "FLOAT DEFAULT 2.0"),
    ("app_settings", "allow_short_selling", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "max_concentration_pct", "FLOAT DEFAULT 25.0"),
    ("app_settings", "max_gross_exposure", "FLOAT DEFAULT 3.0"),
    ("app_settings", "strict_stop_loss_mode", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "node_retry_attempts", "INTEGER DEFAULT 2"),
    ("app_settings", "node_retry_base_delay", "FLOAT DEFAULT 1.0"),
    ("app_settings", "node_timeout_seconds", "INTEGER DEFAULT 120"),
    ("app_settings", "tool_timeout_seconds", "INTEGER DEFAULT 60"),
    ("app_settings", "circuit_breaker_threshold", "INTEGER DEFAULT 3"),
    ("app_settings", "circuit_breaker_cooldown", "INTEGER DEFAULT 60"),
    ("app_settings", "stall_timeout_seconds", "INTEGER DEFAULT 120"),
    ("app_settings", "llm_provider", _TYPE_VARCHAR_50 + " DEFAULT 'openai'"),
    ("app_settings", "cron_enabled", _TYPE_BOOLEAN_DEFAULT_FALSE),
    ("app_settings", "cron_schedule", _TYPE_VARCHAR_100 + " DEFAULT '0 9 * * 1-5'"),
    ("app_settings", "price_tolerance_pct", "FLOAT DEFAULT 0.5"),
    ("app_settings", "watchlist", _TYPE_TEXT_DEFAULT_EMPTY + " DEFAULT '[]'"),
    ("app_settings", "updated_at", _TYPE_TIMESTAMP_WITH_TZ),
    ("portfolios", "margin_used", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("holdings", "side", _TYPE_VARCHAR_5_DEFAULT_LONG),
    ("holdings", "entry_commission", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("holdings", "leverage", _TYPE_NUMERIC_20_8_DEFAULT_1),
    ("holdings", "margin_used", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("holdings", "borrowed_amount", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("holdings", "liquidation_price", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("holdings", "interest_accrued", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("holdings", "opened_at", _TYPE_TIMESTAMP_WITH_TZ),
    ("holdings", "stop_loss", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("holdings", "take_profit", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("orders", "leverage", _TYPE_NUMERIC_20_8_DEFAULT_1),
    ("orders", "side", _TYPE_VARCHAR_5_DEFAULT_LONG),
    ("orders", "entry_commission", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("orders", "realized_pnl", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("price_alerts", "alert_type", _TYPE_VARCHAR_20_DEFAULT_PRICE),
    ("price_alerts", "creation_source", _TYPE_VARCHAR_20_DEFAULT_MANUAL),
    ("price_alerts", "creation_run_id", _TYPE_VARCHAR_100),
    ("system_logs", "user_id", _USER_REF),
]


_NUMERIC_COLUMNS: list[tuple[str, tuple[str, ...]]] = [
    (
        "orders",
        ("quantity_requested", "quantity_filled", "price_per_share", "total_value", "commission", "entry_commission"),
    ),
    ("portfolios", ("initial_capital", "current_balance", "cash_available")),
    ("holdings", ("quantity", "avg_buy_price", "current_price", "unrealized_pnl", "entry_commission")),
    ("price_alerts", ("target_price",)),
]
_NUMERIC_PRECISION = "NUMERIC(20, 8)"


# Values written before the analysis signal enum was made canonical.  Keep
# this SQL deliberately narrow: recognised spellings are safe to rewrite,
# while unexpected historical text is left untouched for operators to inspect.
_NORMALIZE_ANALYSIS_SIGNALS_SQL = """
    UPDATE analysis_results
    SET signal = CASE lower(trim(signal))
        WHEN 'buy' THEN 'Buy'
        WHEN 'overweight' THEN 'Overweight'
        WHEN 'hold' THEN 'Hold'
        WHEN 'underweight' THEN 'Underweight'
        WHEN 'sell' THEN 'Sell'
    END
    WHERE lower(trim(signal)) IN ('buy', 'overweight', 'hold', 'underweight', 'sell')
"""

_LEGACY_WEBHOOK_EVENT_ALIASES = {"order_filled": "trade_executed"}


def _normalize_webhook_events_value(value: object) -> tuple[list[str], bool]:
    """Convert a pre-JSON event value without guessing malformed JSON.

    The bool tells the caller that a retired/unknown event was intentionally
    discarded.  In particular, ``risk_breach`` was once shown in metadata but
    never had an event producer, so retaining it would preserve a deceptive
    configuration instead of a working notification selection.
    """
    candidates: object = value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            candidates = []
        elif raw.startswith("["):
            try:
                candidates = json.loads(raw)
            except json.JSONDecodeError:
                return [], True
        else:
            candidates = raw.split(",")

    if not isinstance(candidates, list):
        return [], value not in (None, "", [])

    normalized: list[str] = []
    discarded = False
    for candidate in candidates:
        if not isinstance(candidate, str):
            discarded = True
            continue
        event = candidate.strip().lower()
        event = _LEGACY_WEBHOOK_EVENT_ALIASES.get(event, event)
        if event not in WEBHOOK_EVENTS:
            discarded = True
            continue
        if event not in normalized:
            normalized.append(event)
    return normalized, discarded


def _normalize_fallback_chain_value(
    value: object,
    legacy_provider: object = None,
    legacy_model: object = None,
) -> list[dict[str, str]]:
    """Return the current ordered chain, or migrate the former field pair."""
    candidates: object = value
    if isinstance(value, str):
        try:
            candidates = json.loads(value)
        except json.JSONDecodeError:
            candidates = []

    normalized: list[dict[str, str]] = []
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            provider = candidate.get("provider")
            model = candidate.get("model")
            if not isinstance(provider, str) or not isinstance(model, str):
                continue
            provider, model = provider.strip().lower(), model.strip()
            if provider and model and {"provider": provider, "model": model} not in normalized:
                normalized.append({"provider": provider, "model": model})
            if len(normalized) == 3:
                return normalized

    if normalized:
        return normalized

    provider = legacy_provider.strip().lower() if isinstance(legacy_provider, str) else ""
    model = legacy_model.strip() if isinstance(legacy_model, str) else ""
    return [{"provider": provider, "model": model}] if provider and model else []


def _normalize_preset_settings_collections(settings_json: object) -> tuple[str | None, bool]:
    """Upgrade known collection fields inside a stored preset JSON object.

    Invalid whole presets remain untouched so this migration never destroys a
    user-created template that needs manual repair for an unrelated reason.
    """
    if not isinstance(settings_json, str):
        return None, False
    try:
        settings = json.loads(settings_json)
    except json.JSONDecodeError:
        return None, False
    if not isinstance(settings, dict):
        return None, False

    changed = False
    # Pre-contract settings pages stored a whole SettingsRead response in a
    # preset.  These are response-only fields and the current strict preset
    # parser correctly rejects them, so remove only the known app-generated
    # metadata while preserving any other unexpected user data for review.
    for read_only_field in ("updated_at", "active_preset_name"):
        if read_only_field in settings:
            settings.pop(read_only_field)
            changed = True

    if "webhook_events" in settings:
        events, _ = _normalize_webhook_events_value(settings["webhook_events"])
        if settings["webhook_events"] != events:
            settings["webhook_events"] = events
            changed = True

    has_legacy_fallback = "fallback_llm_provider" in settings or "fallback_llm_model" in settings
    if has_legacy_fallback:
        chain = _normalize_fallback_chain_value(
            settings.get("fallback_llm_chain"),
            settings.get("fallback_llm_provider"),
            settings.get("fallback_llm_model"),
        )
        settings["fallback_llm_chain"] = chain
        settings.pop("fallback_llm_provider", None)
        settings.pop("fallback_llm_model", None)
        changed = True

    return (json.dumps(settings, separators=(",", ":"), sort_keys=True), True) if changed else (None, False)


async def apply_type_migrations(conn) -> None:
    """Convert legacy float money columns to exact NUMERIC on PostgreSQL."""
    if conn.dialect.name == "sqlite":
        return
    for table, columns in _NUMERIC_COLUMNS:
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"Unknown table in migration: {table!r}")
        for column in columns:
            if column not in _ALLOWED_COLUMNS.get(table, set()):
                raise ValueError(f"Column {column!r} is not allowed for table {table!r} in type migration")
            current = (
                await conn.execute(
                    text("SELECT data_type FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
                    {"t": table, "c": column},
                )
            ).scalar_one_or_none()
            if current is not None and current != "numeric":
                await conn.execute(
                    text(
                        f"ALTER TABLE {table} ALTER COLUMN {column} "
                        f"TYPE {_NUMERIC_PRECISION} USING {column}::numeric(20, 8)"
                    )
                )


async def normalize_sqlite_analysis_signals(conn) -> None:
    """Canonicalize known pre-enum signals in SQLite development databases.

    PostgreSQL receives the equivalent one-time Alembic data migration.  Do
    not erase unknown values here: the response DTO will continue to hide
    invalid values rather than silently discarding historical information.
    """
    if conn.dialect.name == "sqlite":
        await conn.execute(text(_NORMALIZE_ANALYSIS_SIGNALS_SQL))


def _sqlite_table_columns(sync_conn, table: str) -> set[str]:
    inspector = inspect(sync_conn)
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


async def normalize_sqlite_settings_collections(conn) -> None:
    """Upgrade legacy SQLite settings/presets after additive columns exist.

    SQLite cannot safely drop the retired columns without rebuilding the table,
    so they become inert after this one-time copy.  PostgreSQL removes them in
    the corresponding Alembic revision.
    """
    if conn.dialect.name != "sqlite":
        return

    settings_columns = await conn.run_sync(_sqlite_table_columns, "app_settings")
    if not {"id", "webhook_events", "fallback_llm_chain"}.issubset(settings_columns):
        return

    select_columns = ["id", "webhook_events", "fallback_llm_chain"]
    for legacy_column in ("fallback_llm_provider", "fallback_llm_model"):
        if legacy_column in settings_columns:
            select_columns.append(legacy_column)
    rows = (await conn.execute(text(f"SELECT {', '.join(select_columns)} FROM app_settings"))).mappings()

    discarded_events = 0
    for row in rows:
        events, discarded = _normalize_webhook_events_value(row["webhook_events"])
        chain = _normalize_fallback_chain_value(
            row["fallback_llm_chain"],
            row.get("fallback_llm_provider"),
            row.get("fallback_llm_model"),
        )
        await conn.execute(
            text("UPDATE app_settings SET webhook_events = :events, fallback_llm_chain = :chain WHERE id = :id"),
            {"id": row["id"], "events": json.dumps(events), "chain": json.dumps(chain)},
        )
        discarded_events += int(discarded)

    preset_columns = await conn.run_sync(_sqlite_table_columns, "config_presets")
    if {"id", "settings_json"}.issubset(preset_columns):
        preset_rows = (await conn.execute(text("SELECT id, settings_json FROM config_presets"))).mappings()
        for row in preset_rows:
            normalized, changed = _normalize_preset_settings_collections(row["settings_json"])
            if changed and normalized is not None:
                await conn.execute(
                    text("UPDATE config_presets SET settings_json = :settings_json WHERE id = :id"),
                    {"id": row["id"], "settings_json": normalized},
                )

    if discarded_events:
        _logger.warning(
            "Normalized SQLite webhook settings; removed %s retired or unsupported event selection(s)",
            discarded_events,
        )


async def normalize_sqlite_simulation_entry_commissions(conn) -> None:
    """Backfill the all-in fee ledger for existing SQLite paper portfolios.

    PostgreSQL does this once in Alembic revision ``a2b3c4d5e6f7``.  SQLite is
    intentionally an additive local/test compatibility path, so only records
    that have not yet received an opening-fee value are changed here.
    """
    if conn.dialect.name != "sqlite":
        return

    holding_columns = await conn.run_sync(_sqlite_table_columns, "holdings")
    order_columns = await conn.run_sync(_sqlite_table_columns, "orders")
    portfolio_columns = await conn.run_sync(_sqlite_table_columns, "portfolios")
    if "entry_commission" not in holding_columns or "entry_commission" not in order_columns:
        return
    if not {"id", "mode"}.issubset(portfolio_columns):
        return

    # Existing open positions lack their original fill ledger.  The simulator
    # has always used a fixed 10 bps opening commission, which is the only
    # recoverable value without fabricating an order-history pairing.
    await conn.execute(
        text(
            """
            UPDATE holdings
            SET entry_commission = round(max(avg_buy_price * quantity, 0) * 0.001, 4)
            WHERE coalesce(entry_commission, 0) = 0
              AND EXISTS (
                  SELECT 1 FROM portfolios
                  WHERE portfolios.id = holdings.portfolio_id
                    AND portfolios.mode = 'simulation'
              )
            """
        )
    )
    await conn.execute(
        text(
            """
            UPDATE orders
            SET entry_commission = coalesce(commission, 0)
            WHERE coalesce(entry_commission, 0) = 0
              AND EXISTS (
                  SELECT 1 FROM portfolios
                  WHERE portfolios.id = orders.portfolio_id
                    AND portfolios.mode = 'simulation'
              )
              AND (
                  (lower(coalesce(side, 'long')) = 'long' AND upper(action) = 'BUY')
                  OR (lower(coalesce(side, 'long')) = 'short' AND upper(action) = 'SELL')
              )
            """
        )
    )
    # Closing records written before the fee ledger deducted only the exit
    # fee.  The guard prevents this compatibility step from running twice.
    await conn.execute(
        text(
            """
            UPDATE orders
            SET entry_commission = round(
                    max(
                        CASE
                            WHEN lower(coalesce(side, 'long')) = 'short' THEN
                                coalesce(total_value, 0) + coalesce(realized_pnl, 0) + coalesce(commission, 0)
                            ELSE
                                coalesce(total_value, 0) - coalesce(realized_pnl, 0) - coalesce(commission, 0)
                        END,
                        0
                    ) * 0.001,
                    4
                ),
                realized_pnl = coalesce(realized_pnl, 0) - round(
                    max(
                        CASE
                            WHEN lower(coalesce(side, 'long')) = 'short' THEN
                                coalesce(total_value, 0) + coalesce(realized_pnl, 0) + coalesce(commission, 0)
                            ELSE
                                coalesce(total_value, 0) - coalesce(realized_pnl, 0) - coalesce(commission, 0)
                        END,
                        0
                    ) * 0.001,
                    4
                )
            WHERE coalesce(entry_commission, 0) = 0
              AND EXISTS (
                  SELECT 1 FROM portfolios
                  WHERE portfolios.id = orders.portfolio_id
                    AND portfolios.mode = 'simulation'
              )
              AND upper(coalesce(status, '')) IN ('FILLED', 'STOP_LOSS', 'TAKE_PROFIT', 'LIQUIDATED')
              AND (
                  (lower(coalesce(side, 'long')) = 'long' AND upper(action) = 'SELL')
                  OR (lower(coalesce(side, 'long')) = 'short' AND upper(action) = 'BUY')
              )
            """
        )
    )


async def apply_column_migrations(conn) -> None:
    """Add any missing columns from ``_NEW_COLUMNS`` to the connected database."""
    for table, column, col_type in _NEW_COLUMNS:
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"Unknown table in migration: {table!r}")
        if column not in _ALLOWED_COLUMNS.get(table, set()):
            raise ValueError(f"Column {column!r} is not allowed for table {table!r} in column migration")
        if conn.dialect.name == "sqlite":
            await conn.run_sync(_add_column_sqlite, table, column, col_type)
        else:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))


def _add_column_sqlite(sync_conn, table: str, column: str, col_type: str) -> None:
    """SQLite has no ``ADD COLUMN IF NOT EXISTS``; check the catalog first."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"Unknown table in migration: {table!r}")
    if column not in _ALLOWED_COLUMNS.get(table, set()):
        raise ValueError(f"Column {column!r} is not allowed for table {table!r} in column migration")
    existing = {c["name"] for c in inspect(sync_conn).get_columns(table)}
    if column not in existing:
        sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
