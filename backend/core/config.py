import threading
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).parent.parent.parent / ".env"
_TEMP_KEY = None
_TEMP_FERNET = None
_TEMP_KEY_LOCK = threading.Lock()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT_ENV), env_file_encoding="utf-8", extra="ignore")
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://tradingagents:tradingagents@localhost:5432/tradingagents"
    ENCRYPTION_KEY: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    def get_fernet(self) -> Fernet:
        global _TEMP_KEY, _TEMP_FERNET
        key = self.ENCRYPTION_KEY
        if key:
            key_bytes = key.encode() if isinstance(key, str) else key
            return Fernet(key_bytes)
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
