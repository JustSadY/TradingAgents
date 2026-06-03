from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables():
    # Import all models so SQLAlchemy knows about them before create_all
    import backend.models.user  # noqa: F401
    import backend.models.settings  # noqa: F401
    import backend.models.system_settings  # noqa: F401
    import backend.models.page_permission  # noqa: F401
    import backend.models.analysis  # noqa: F401
    import backend.models.portfolio  # noqa: F401
    import backend.models.order  # noqa: F401
    import backend.models.log  # noqa: F401
    import backend.models.alert  # noqa: F401
    import backend.models.preset  # noqa: F401
    import backend.models.portfolio_analysis  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_add_columns(conn)


async def _migrate_add_columns(conn):
    """Safely add new columns to existing tables (idempotent)."""
    # NOTE: These migrations are outside Alembic. After adding new entries here,
    # run `alembic revision --autogenerate` to keep migration history in sync.
    _ALLOWED = {
        "users", "app_settings", "analysis_results", "portfolios", "orders",
        "holdings", "multi_ticker_analyses", "config_presets", "price_alerts",
        "system_settings",
    }
    new_columns = [
        # ── Multi-tenant: users table ──────────────────────────────────────────
        ("users", "email",         "VARCHAR(255)"),
        ("users", "role",          "VARCHAR(20) DEFAULT 'user'"),
        ("users", "display_name",  "VARCHAR(100)"),
        ("users", "api_keys_enc",  "TEXT"),
        # ── Global settings configured via Web UI ─────────────────────────────
        ("system_settings", "searxng_url",             "VARCHAR(500)"),
        ("system_settings", "reddit_client_id",         "VARCHAR(255)"),
        ("system_settings", "reddit_client_secret",     "VARCHAR(255)"),
        ("system_settings", "reddit_user_agent",        "VARCHAR(255)"),
        ("system_settings", "alpha_vantage_api_key",    "VARCHAR(255)"),
        # ── Per-user settings ─────────────────────────────────────────────────
        ("app_settings", "user_id", "INTEGER REFERENCES users(id)"),
        # ── Data isolation: user_id on all core tables ─────────────────────────
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
        # Phase 1B: debate history
        ("analysis_results", "bull_history",                "TEXT DEFAULT ''"),
        ("analysis_results", "bear_history",                "TEXT DEFAULT ''"),
        ("analysis_results", "investment_debate_history",   "TEXT DEFAULT ''"),
        ("analysis_results", "risk_debate_history",         "TEXT DEFAULT ''"),
        ("analysis_results", "judge_decision",              "TEXT DEFAULT ''"),
        # Grafik annotasyonları (JSON)
        ("analysis_results", "chart_annotations",           "TEXT DEFAULT ''"),
        # Performans takibi
        ("analysis_results", "raw_return",                  "FLOAT"),
        ("analysis_results", "alpha_return",                "FLOAT"),
        ("analysis_results", "holding_days",                "INTEGER"),
        # Eskiye dönük analiz seçeneği
        ("app_settings", "include_historical_analyses",     "BOOLEAN DEFAULT FALSE"),
        ("app_settings", "historical_analyses_limit",       "INTEGER DEFAULT 5"),
        ("app_settings", "analyst_models",                  "TEXT DEFAULT '{}'"),
        # Webhook bildirimleri
        ("app_settings", "webhook_url",                     "VARCHAR(500)"),
        ("app_settings", "webhook_enabled",                 "BOOLEAN DEFAULT FALSE"),
        ("app_settings", "webhook_events",                  "TEXT DEFAULT '[\"analysis_complete\"]'"),
        # Phase 2: Preset ve LLM performans takibi
        ("app_settings", "active_preset_name",              "VARCHAR(100)"),
        ("analysis_results", "llm_provider",                "VARCHAR(50)"),
        ("analysis_results", "llm_model",                   "VARCHAR(100)"),
        ("analysis_results", "preset_name",                  "VARCHAR(100)"),
    ]
    from sqlalchemy import text, inspect
    for table, column, col_type in new_columns:
        if table not in _ALLOWED:
            raise ValueError(f"Unknown table in migration: {table!r}")
        if conn.dialect.name == "sqlite":
            def add_col_sqlite(sync_conn):
                inspector = inspect(sync_conn)
                cols = [c["name"] for c in inspector.get_columns(table)]
                if column not in cols:
                    sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            await conn.run_sync(add_col_sqlite)
        else:
            await conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
            ))
