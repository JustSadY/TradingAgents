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
    "users", "app_settings", "analysis_results", "portfolios", "orders",
    "holdings", "multi_ticker_analyses", "config_presets", "price_alerts",
    "system_settings",
}

# (table, column, column_type) tuples applied additively on startup.
_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("users", "email",         "VARCHAR(255)"),
    ("users", "role",          "VARCHAR(20) DEFAULT 'user'"),
    ("users", "display_name",  "VARCHAR(100)"),
    ("users", "api_keys_enc",  "TEXT"),
    ("system_settings", "searxng_url",             "VARCHAR(500)"),
    ("system_settings", "reddit_client_id",         "VARCHAR(255)"),
    ("system_settings", "reddit_client_secret",     "VARCHAR(255)"),
    ("system_settings", "reddit_user_agent",        "VARCHAR(255)"),
    ("system_settings", "alpha_vantage_api_key",    "VARCHAR(255)"),
    ("app_settings", "user_id", "INTEGER REFERENCES users(id)"),
    ("analysis_results",      "user_id", "INTEGER REFERENCES users(id)"),
    ("portfolios",            "user_id", "INTEGER REFERENCES users(id)"),
    ("config_presets",        "user_id", "INTEGER REFERENCES users(id)"),
    ("price_alerts",          "user_id", "INTEGER REFERENCES users(id)"),
    ("multi_ticker_analyses", "user_id", "INTEGER REFERENCES users(id)"),
    ("app_settings", "backend_url",                "VARCHAR(500)"),
    ("app_settings", "llm_model",                  "VARCHAR(100) DEFAULT 'gpt-4o-mini'"),
    ("app_settings", "openai_reasoning_effort",    "VARCHAR(20)"),
    ("app_settings", "anthropic_effort",           "VARCHAR(20)"),
    ("app_settings", "google_thinking_level",      "VARCHAR(20)"),
    ("app_settings", "output_language",            "VARCHAR(50) DEFAULT 'English'"),
    ("app_settings", "investor_persona",           "VARCHAR(50) DEFAULT 'conservative'"),
    ("app_settings", "analyst_concurrency_limit",  "INTEGER DEFAULT 1"),
    ("app_settings", "checkpoint_enabled",         "BOOLEAN DEFAULT FALSE"),
    ("app_settings", "max_recur_limit",            "INTEGER DEFAULT 1000"),
    ("app_settings", "news_article_limit",         "INTEGER DEFAULT 20"),
    ("app_settings", "global_news_article_limit",  "INTEGER DEFAULT 10"),
    ("app_settings", "global_news_lookback_days",  "INTEGER DEFAULT 7"),
    ("app_settings", "benchmark_ticker",           "VARCHAR(20)"),
    ("app_settings", "azure_deployment",           "VARCHAR(100)"),
    ("app_settings", "data_vendor_core_stock",     "VARCHAR(50) DEFAULT 'yfinance'"),
    ("app_settings", "data_vendor_technicals",     "VARCHAR(50) DEFAULT 'yfinance'"),
    ("app_settings", "data_vendor_fundamentals",   "VARCHAR(50) DEFAULT 'yfinance'"),
    ("app_settings", "data_vendor_news",           "VARCHAR(50) DEFAULT 'yfinance'"),
    ("analysis_results", "bull_history",                "TEXT DEFAULT ''"),
    ("analysis_results", "bear_history",                "TEXT DEFAULT ''"),
    ("analysis_results", "investment_debate_history",   "TEXT DEFAULT ''"),
    ("analysis_results", "risk_debate_history",         "TEXT DEFAULT ''"),
    ("analysis_results", "judge_decision",              "TEXT DEFAULT ''"),
    ("analysis_results", "chart_annotations",           "TEXT DEFAULT ''"),
    ("analysis_results", "raw_return",                  "FLOAT"),
    ("analysis_results", "alpha_return",                "FLOAT"),
    ("analysis_results", "holding_days",                "INTEGER"),
    ("app_settings", "include_historical_analyses",     "BOOLEAN DEFAULT FALSE"),
    ("app_settings", "historical_analyses_limit",       "INTEGER DEFAULT 5"),
    ("app_settings", "analyst_models",                  "TEXT DEFAULT '{}'"),
    ("app_settings", "webhook_url",                     "VARCHAR(500)"),
    ("app_settings", "webhook_enabled",                 "BOOLEAN DEFAULT FALSE"),
    ("app_settings", "webhook_events",                  "TEXT DEFAULT '[\"analysis_complete\"]'"),
    ("app_settings", "active_preset_name",              "VARCHAR(100)"),
    ("analysis_results", "llm_provider",                "VARCHAR(50)"),
    ("analysis_results", "llm_model",                   "VARCHAR(100)"),
    ("analysis_results", "preset_name",                  "VARCHAR(100)"),
    ("app_settings", "max_debate_rounds",          "INTEGER DEFAULT 1"),
    ("app_settings", "max_risk_rounds",            "INTEGER DEFAULT 1"),
    ("app_settings", "max_position_size_pct",      "FLOAT DEFAULT 10.0"),
    ("app_settings", "max_risk_per_trade_pct",     "FLOAT DEFAULT 2.0"),
    ("app_settings", "synthesis_enabled",          "BOOLEAN DEFAULT TRUE"),
    ("app_settings", "auditor_enabled",            "BOOLEAN DEFAULT TRUE"),
    ("app_settings", "kelly_sizing_enabled",       "BOOLEAN DEFAULT TRUE"),
    ("app_settings", "sec_insights_enabled",       "BOOLEAN DEFAULT TRUE"),
    ("app_settings", "strict_backtest_learning",   "BOOLEAN DEFAULT TRUE"),
    ("app_settings", "broker_credentials_enc",     "TEXT"),
]


async def apply_column_migrations(conn) -> None:
    """Add any missing columns from ``_NEW_COLUMNS`` to the connected database."""
    for table, column, col_type in _NEW_COLUMNS:
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"Unknown table in migration: {table!r}")
        if conn.dialect.name == "sqlite":
            await conn.run_sync(_add_column_sqlite, table, column, col_type)
        else:
            await conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
            ))


def _add_column_sqlite(sync_conn, table: str, column: str, col_type: str) -> None:
    """SQLite has no ``ADD COLUMN IF NOT EXISTS``; check the catalog first."""
    existing = {c["name"] for c in inspect(sync_conn).get_columns(table)}
    if column not in existing:
        sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
