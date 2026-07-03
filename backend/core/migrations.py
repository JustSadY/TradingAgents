"""Lightweight, idempotent column migrations.

The project does not use Alembic; instead, on every startup we ensure that
newly added model columns exist on the live database. This is intentionally
simple (``ADD COLUMN IF NOT EXISTS``) and additive only — it never drops or
alters existing columns. Table names are validated against an allow-list so the
hand-built DDL strings can never reference an unexpected table.

If this project ever adopts Alembic, this module is the single place to retire.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

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
        "node_retry_attempts",
        "node_retry_base_delay",
        "node_timeout_seconds",
        "tool_timeout_seconds",
        "circuit_breaker_threshold",
        "circuit_breaker_cooldown",
        "stall_timeout_seconds",
    },
    "app_settings": {
        "user_id",
        "llm_model",
        "fallback_llm_provider",
        "fallback_llm_model",
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
        "ticker",
        "articles_hash",
        "analysis_result",
        "created_at",
    },
    "analyst_report_cache": {
        "id",
        "analyst_key",
        "ticker",
        "data_hash",
        "analysis_result",
        "created_at",
    },
    "portfolios": {"user_id", "initial_capital", "current_balance", "cash_available", "margin_used"},
    "config_presets": {"user_id"},
    "price_alerts": {"user_id", "target_price", "alert_type"},
    "multi_ticker_analyses": {"user_id"},
    "orders": {
        "quantity_requested",
        "quantity_filled",
        "price_per_share",
        "total_value",
        "commission",
        "leverage",
        "side",
        "realized_pnl",
    },
    "holdings": {
        "quantity",
        "avg_buy_price",
        "current_price",
        "unrealized_pnl",
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
    ("app_settings", "fallback_llm_provider", _TYPE_VARCHAR_50),
    ("app_settings", "fallback_llm_model", _TYPE_VARCHAR_100),
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
    ("users", "email", _TYPE_VARCHAR_255),
    ("users", "role", _TYPE_VARCHAR_20_DEFAULT_USER),
    ("users", "display_name", _TYPE_VARCHAR_100),
    ("users", "api_keys_enc", "TEXT"),
    ("users", "token_version", _TYPE_INTEGER_DEFAULT_0),
    ("system_settings", "node_retry_attempts", "INTEGER DEFAULT 2"),
    ("system_settings", "node_retry_base_delay", "FLOAT DEFAULT 1.0"),
    ("system_settings", "node_timeout_seconds", "INTEGER DEFAULT 120"),
    ("system_settings", "tool_timeout_seconds", "INTEGER DEFAULT 60"),
    ("system_settings", "circuit_breaker_threshold", "INTEGER DEFAULT 3"),
    ("system_settings", "circuit_breaker_cooldown", "INTEGER DEFAULT 60"),
    ("system_settings", "stall_timeout_seconds", "INTEGER DEFAULT 120"),
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
    ("app_settings", "webhook_events", _TYPE_TEXT_DEFAULT_EMPTY + " DEFAULT '[\"analysis_complete\"]'"),
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
    ("orders", "realized_pnl", _TYPE_NUMERIC_20_8_DEFAULT_0),
    ("price_alerts", "alert_type", _TYPE_VARCHAR_20_DEFAULT_PRICE),
    ("system_logs", "user_id", _USER_REF),
]


_NUMERIC_COLUMNS: list[tuple[str, tuple[str, ...]]] = [
    ("orders", ("quantity_requested", "quantity_filled", "price_per_share", "total_value", "commission")),
    ("portfolios", ("initial_capital", "current_balance", "cash_available")),
    ("holdings", ("quantity", "avg_buy_price", "current_price", "unrealized_pnl")),
    ("price_alerts", ("target_price",)),
]
_NUMERIC_PRECISION = "NUMERIC(20, 8)"


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
