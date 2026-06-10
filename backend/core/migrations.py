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

# Tables that column migrations are permitted to touch.
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
}

# Strict mapping of table names to their permitted column names.
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
        "node_retry_attempts",
        "node_retry_base_delay",
        "llm_provider",
        "cron_enabled",
        "cron_schedule",
        "price_tolerance_pct",
        "agent_qa_enabled",
        "pinecone_index",
        "pinecone_cloud",
        "pinecone_region",
        "memory_embedder",
        "pinecone_embed_model",
        "memory_openai_embed_model",
        "anthropic_prompt_caching",
        "max_report_chars_in_prompts",
        "max_debate_history_chars",
        "max_tool_output_chars",
        "watchlist",
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
        "catalyst_report",
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
}

# (table, column, column_type) tuples applied additively on startup.
_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("analysis_results", "agent_qa_report", "TEXT DEFAULT ''"),
    ("analysis_results", "insider_report", "TEXT DEFAULT ''"),
    ("analysis_results", "ownership_report", "TEXT DEFAULT ''"),
    ("analysis_results", "catalyst_report", "TEXT DEFAULT ''"),
    ("app_settings", "pinecone_index", "VARCHAR(100) DEFAULT 'tradingagents-memory'"),
    ("app_settings", "pinecone_cloud", "VARCHAR(20) DEFAULT 'aws'"),
    ("app_settings", "pinecone_region", "VARCHAR(30) DEFAULT 'us-east-1'"),
    ("app_settings", "memory_embedder", "VARCHAR(20) DEFAULT 'pinecone'"),
    ("app_settings", "pinecone_embed_model", "VARCHAR(60) DEFAULT 'llama-text-embed-v2'"),
    ("app_settings", "memory_openai_embed_model", "VARCHAR(60) DEFAULT 'text-embedding-3-small'"),
    ("app_settings", "agent_qa_enabled", "BOOLEAN DEFAULT TRUE"),
    ("app_settings", "anthropic_prompt_caching", "BOOLEAN DEFAULT TRUE"),
    ("app_settings", "max_report_chars_in_prompts", "INTEGER DEFAULT 6000"),
    ("app_settings", "max_debate_history_chars", "INTEGER DEFAULT 8000"),
    ("app_settings", "max_tool_output_chars", "INTEGER DEFAULT 12000"),
    ("users", "email", "VARCHAR(255)"),
    ("users", "role", "VARCHAR(20) DEFAULT 'user'"),
    ("users", "display_name", "VARCHAR(100)"),
    ("users", "api_keys_enc", "TEXT"),
    ("users", "token_version", "INTEGER DEFAULT 0"),
    ("system_settings", "data_vendor_core_stock", "VARCHAR(50) DEFAULT 'yfinance'"),
    ("system_settings", "data_vendor_technicals", "VARCHAR(50) DEFAULT 'yfinance'"),
    ("system_settings", "data_vendor_fundamentals", "VARCHAR(50) DEFAULT 'yfinance'"),
    ("system_settings", "data_vendor_news", "VARCHAR(50) DEFAULT 'yfinance'"),
    ("system_settings", "trading_mode", "VARCHAR(20) DEFAULT 'simulation'"),
    ("system_settings", "active_broker", "VARCHAR(50) DEFAULT 'simulation'"),
    ("system_settings", "active_data_vendor", "VARCHAR(50) DEFAULT 'yfinance'"),
    ("system_settings", "updated_at", "TIMESTAMP WITH TIME ZONE"),
    ("app_settings", "user_id", "INTEGER REFERENCES users(id)"),
    ("analysis_results", "user_id", "INTEGER REFERENCES users(id)"),
    ("portfolios", "user_id", "INTEGER REFERENCES users(id)"),
    ("config_presets", "user_id", "INTEGER REFERENCES users(id)"),
    ("price_alerts", "user_id", "INTEGER REFERENCES users(id)"),
    ("multi_ticker_analyses", "user_id", "INTEGER REFERENCES users(id)"),
    ("app_settings", "llm_model", "VARCHAR(100) DEFAULT 'gpt-4o-mini'"),
    ("app_settings", "openai_reasoning_effort", "VARCHAR(20)"),
    ("app_settings", "anthropic_effort", "VARCHAR(20)"),
    ("app_settings", "google_thinking_level", "VARCHAR(20)"),
    ("app_settings", "output_language", "VARCHAR(50) DEFAULT 'English'"),
    ("app_settings", "investor_persona", "VARCHAR(50) DEFAULT 'conservative'"),
    ("app_settings", "analyst_concurrency_limit", "INTEGER DEFAULT 1"),
    ("app_settings", "max_recur_limit", "INTEGER DEFAULT 1000"),
    ("app_settings", "benchmark_ticker", "VARCHAR(20)"),
    ("analysis_results", "bull_history", "TEXT DEFAULT ''"),
    ("analysis_results", "bear_history", "TEXT DEFAULT ''"),
    ("analysis_results", "investment_debate_history", "TEXT DEFAULT ''"),
    ("analysis_results", "risk_debate_history", "TEXT DEFAULT ''"),
    ("analysis_results", "judge_decision", "TEXT DEFAULT ''"),
    ("analysis_results", "chart_annotations", "TEXT DEFAULT ''"),
    ("analysis_results", "raw_return", "FLOAT"),
    ("analysis_results", "alpha_return", "FLOAT"),
    ("analysis_results", "holding_days", "INTEGER"),
    ("analysis_results", "reflection", "TEXT DEFAULT ''"),
    ("app_settings", "webhook_url", "VARCHAR(500)"),
    ("app_settings", "webhook_enabled", "BOOLEAN DEFAULT FALSE"),
    ("app_settings", "webhook_events", "TEXT DEFAULT '[\"analysis_complete\"]'"),
    ("app_settings", "active_preset_name", "VARCHAR(100)"),
    ("analysis_results", "llm_provider", "VARCHAR(50)"),
    ("analysis_results", "llm_model", "VARCHAR(100)"),
    ("analysis_results", "preset_name", "VARCHAR(100)"),
    ("analysis_results", "llm_calls", "INTEGER DEFAULT 0"),
    ("analysis_results", "tool_calls", "INTEGER DEFAULT 0"),
    ("analysis_results", "tokens_in", "INTEGER DEFAULT 0"),
    ("analysis_results", "tokens_out", "INTEGER DEFAULT 0"),
    ("analysis_results", "duration_seconds", "FLOAT DEFAULT 0.0"),
    ("analysis_results", "triggered_by", "VARCHAR(20) DEFAULT 'manual'"),
    ("analysis_results", "task_id", "VARCHAR(100)"),
    ("analysis_results", "status", "VARCHAR(20) DEFAULT 'completed'"),
    ("app_settings", "max_debate_rounds", "INTEGER DEFAULT 1"),
    ("app_settings", "max_risk_rounds", "INTEGER DEFAULT 1"),
    ("app_settings", "max_position_size_pct", "FLOAT DEFAULT 10.0"),
    ("app_settings", "max_risk_per_trade_pct", "FLOAT DEFAULT 2.0"),
    ("app_settings", "strict_stop_loss_mode", "BOOLEAN DEFAULT FALSE"),
    ("app_settings", "node_retry_attempts", "INTEGER DEFAULT 2"),
    ("app_settings", "node_retry_base_delay", "FLOAT DEFAULT 1.0"),
    ("app_settings", "llm_provider", "VARCHAR(50) DEFAULT 'openai'"),
    ("app_settings", "cron_enabled", "BOOLEAN DEFAULT FALSE"),
    ("app_settings", "cron_schedule", "VARCHAR(100) DEFAULT '0 9 * * 1-5'"),
    ("app_settings", "price_tolerance_pct", "FLOAT DEFAULT 0.5"),
    ("app_settings", "watchlist", "TEXT DEFAULT '[]'"),
    ("app_settings", "updated_at", "TIMESTAMP WITH TIME ZONE"),
    # Leverage / margin trading.
    ("portfolios", "margin_used", "NUMERIC(20, 8) DEFAULT 0"),
    ("holdings", "side", "VARCHAR(5) DEFAULT 'long'"),
    ("holdings", "leverage", "NUMERIC(20, 8) DEFAULT 1"),
    ("holdings", "margin_used", "NUMERIC(20, 8) DEFAULT 0"),
    ("holdings", "borrowed_amount", "NUMERIC(20, 8) DEFAULT 0"),
    ("holdings", "liquidation_price", "NUMERIC(20, 8) DEFAULT 0"),
    ("holdings", "interest_accrued", "NUMERIC(20, 8) DEFAULT 0"),
    ("holdings", "opened_at", "TIMESTAMP WITH TIME ZONE"),
    ("holdings", "stop_loss", "NUMERIC(20, 8) DEFAULT 0"),
    ("holdings", "take_profit", "NUMERIC(20, 8) DEFAULT 0"),
    ("orders", "leverage", "NUMERIC(20, 8) DEFAULT 1"),
    ("orders", "side", "VARCHAR(5) DEFAULT 'long'"),
    ("orders", "realized_pnl", "NUMERIC(20, 8) DEFAULT 0"),
    ("price_alerts", "alert_type", "VARCHAR(20) DEFAULT 'price'"),
]


# Columns converted from FLOAT/double precision to exact NUMERIC(20, 8).
# For fresh databases ``create_all`` already creates them as NUMERIC; this step
# migrates pre-existing PostgreSQL databases in place (idempotent — it inspects
# the current type and only alters columns still stored as floating point).
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
        # SQLite is dynamically typed (dev only); create_all covers fresh DBs.
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
