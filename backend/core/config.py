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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT_ENV), env_file_encoding="utf-8", extra="ignore")
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://tradingagents:tradingagents@localhost:5432/tradingagents"
    ENCRYPTION_KEY: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # Bearer token for GET /metrics (Prometheus). Endpoint returns 404 while unset.
    METRICS_TOKEN: str = ""
    # Maximum accepted HTTP request body size in bytes (0 disables the check).
    MAX_REQUEST_BODY_BYTES: int = 2_000_000
    # Optional Redis (e.g. redis://localhost:6379/0). When set, analysis
    # WebSocket events fan out over pub/sub and the task registry becomes
    # cross-process. Empty = original single-process in-memory behaviour.
    REDIS_URL: str = ""
    # "inline" runs analyses in the web process (default). "worker" enqueues
    # them onto arq (requires REDIS_URL and a running `arq backend.worker.WorkerSettings`).
    ANALYSIS_QUEUE_MODE: str = "inline"

    @model_validator(mode="after")
    def _validate_queue_mode(self) -> "Settings":
        mode = self.ANALYSIS_QUEUE_MODE.strip().lower()
        if mode not in ("inline", "worker"):
            raise ValueError("ANALYSIS_QUEUE_MODE must be 'inline' or 'worker'")
        if mode == "worker" and not self.REDIS_URL:
            raise ValueError("ANALYSIS_QUEUE_MODE=worker requires REDIS_URL to be set")
        return self

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "Settings":
        """Refuse to boot in production with shipped-default secrets.

        In development the defaults stay usable out of the box; with
        ENVIRONMENT=production an operator must provide real secrets, otherwise
        JWTs are forgeable, the owner account password defaults to 'changeme',
        and encrypted API keys are silently lost on restart.
        """
        if self.ENVIRONMENT.strip().lower() != "production":
            return self
        problems = []
        if not self.SECRET_KEY or self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY must be set to a long random value")
        if not self.ENCRYPTION_KEY:
            problems.append("ENCRYPTION_KEY must be set (encrypted data is lost on restart otherwise)")
        if not self.ADMIN_PASSWORD_HASH:
            problems.append("ADMIN_PASSWORD_HASH must be set (the admin password defaults to 'changeme' otherwise)")
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
