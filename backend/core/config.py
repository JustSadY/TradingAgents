import logging
import threading
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).parent.parent.parent / ".env"
_DEFAULT_SECRET_KEY = "change-me-in-production-use-a-long-random-string"
_TEMP_KEY = None
_TEMP_FERNET = None
_TEMP_KEY_LOCK = threading.Lock()

_ASYNC_DB_DRIVERS = {
    "postgres": "postgresql+asyncpg",
    "postgresql": "postgresql+asyncpg",
    "postgresql+psycopg2": "postgresql+asyncpg",
    "postgresql+psycopg": "postgresql+asyncpg",
    "sqlite": "sqlite+aiosqlite",
    "sqlite+pysqlite": "sqlite+aiosqlite",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT_ENV), env_file_encoding="utf-8", extra="ignore")
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 180
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "postgresql+asyncpg://tradingagents:tradingagents@localhost:5432/tradingagents"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    ENCRYPTION_KEY: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    METRICS_TOKEN: str = ""
    MAX_REQUEST_BODY_BYTES: int = 2_000_000
    REDIS_URL: str = ""
    ANALYSIS_QUEUE_MODE: str = "inline"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    SYSTEM_LOG_DB_LEVEL: str = "INFO"
    #: Days of System Logs history to keep. 0 keeps everything, which is what
    #: the table did before this existed — an analysis writes hundreds of INFO
    #: rows, so it grew without bound.
    SYSTEM_LOG_RETENTION_DAYS: int = 14
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXY_CIDRS: str = ""
    ENABLE_LIVE_TRADING: bool = False
    APP_TIMEZONE: str = "UTC"
    # exchange_calendars code used for tickers with no venue suffix.
    DEFAULT_EXCHANGE_CALENDAR: str = "XNYS"

    @model_validator(mode="after")
    def _force_async_db_driver(self) -> "Settings":
        """Rewrite a sync DATABASE_URL onto the matching async driver.

        Every database access in this app goes through ``create_async_engine``.
        A plain ``postgresql://…`` URL makes SQLAlchemy select psycopg2, which
        is not a dependency, so the process dies at import time with
        ``ModuleNotFoundError: No module named 'psycopg2'`` instead of anything
        that points at the .env. Operators (and most Postgres docs) write the
        driverless form, so normalise it rather than fail.
        """
        url = self.DATABASE_URL.strip()
        scheme, sep, rest = url.partition("://")
        driver = _ASYNC_DB_DRIVERS.get(scheme.lower()) if sep else None
        if driver:
            logging.getLogger(__name__).warning(
                "DATABASE_URL uses the synchronous '%s' driver; connecting with '%s' instead.", scheme, driver
            )
            url = f"{driver}://{rest}"
        if url != self.DATABASE_URL:
            self.DATABASE_URL = url
        return self

    @model_validator(mode="after")
    def _validate_queue_mode(self) -> "Settings":
        mode = self.ANALYSIS_QUEUE_MODE.strip().lower()
        if mode not in ("inline", "worker"):
            raise ValueError("ANALYSIS_QUEUE_MODE must be 'inline' or 'worker'")
        if mode == "worker" and not self.REDIS_URL:
            raise ValueError("ANALYSIS_QUEUE_MODE=worker requires REDIS_URL to be set")
        return self

    @model_validator(mode="after")
    def _validate_system_log_db_level(self) -> "Settings":
        level = self.SYSTEM_LOG_DB_LEVEL.strip().upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError(
                "SYSTEM_LOG_DB_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        if level != self.SYSTEM_LOG_DB_LEVEL:
            self.SYSTEM_LOG_DB_LEVEL = level
        return self

    @model_validator(mode="after")
    def _validate_timezone(self) -> "Settings":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(self.APP_TIMEZONE)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"APP_TIMEZONE is not a valid IANA timezone: {self.APP_TIMEZONE}") from exc
        return self

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "Settings":
        """Refuse to boot in production with shipped-default secrets.

        In development the defaults stay usable out of the box; with
        ENVIRONMENT=production an operator must provide real secrets, otherwise
        JWTs are forgeable and encrypted API keys are silently lost on restart.
        The owner account is not part of this check: it is registered through
        the first-run setup screen rather than configured here.
        """
        if self.ENVIRONMENT.strip().lower() == "production":
            problems = []
            if not self.DATABASE_URL.lower().startswith("postgresql+asyncpg://"):
                problems.append("DATABASE_URL must use PostgreSQL/asyncpg in production")
            if not self.SECRET_KEY or self.SECRET_KEY == _DEFAULT_SECRET_KEY:
                problems.append("SECRET_KEY must be set to a long random value")
            if not self.ENCRYPTION_KEY:
                problems.append("ENCRYPTION_KEY must be set (encrypted data is lost on restart otherwise)")
            if problems:
                raise ValueError("Insecure configuration for ENVIRONMENT=production: " + "; ".join(problems))
        return self

    def get_fernet(self) -> Fernet:
        global _TEMP_KEY, _TEMP_FERNET
        key = self.ENCRYPTION_KEY
        if key:
            key_bytes = key.encode() if isinstance(key, str) else key
            try:
                return Fernet(key_bytes)
            except (ValueError, TypeError) as exc:
                raise RuntimeError(
                    "ENCRYPTION_KEY is not a valid Fernet key. Generate one with: "
                    'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                ) from exc
        with _TEMP_KEY_LOCK:
            if _TEMP_KEY is None:
                _TEMP_KEY = Fernet.generate_key().decode()
                import logging

                logging.warning(
                    "ENCRYPTION_KEY is not set in .env. Generating a temporary process-lifetime encryption key. Encrypted data will not persist across restarts!"
                )
            if _TEMP_FERNET is None:
                _TEMP_FERNET = Fernet(_TEMP_KEY.encode() if isinstance(_TEMP_KEY, str) else _TEMP_KEY)
            return _TEMP_FERNET


@lru_cache
def get_settings() -> Settings:
    return Settings()


def is_live_trading_enabled() -> bool:
    """Whether this server has explicitly opted in to real-money orders."""
    return get_settings().ENABLE_LIVE_TRADING
