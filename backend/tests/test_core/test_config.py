import pytest

from backend.core.config import Settings


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        # Sync drivers an operator may write in .env: without normalisation
        # SQLAlchemy picks psycopg2/pysqlite and the app dies at import time.
        ("postgresql://u:p@localhost:5432/ta", "postgresql+asyncpg://u:p@localhost:5432/ta"),
        ("postgres://u:p@localhost:5432/ta", "postgresql+asyncpg://u:p@localhost:5432/ta"),
        ("postgresql+psycopg2://u:p@localhost:5432/ta", "postgresql+asyncpg://u:p@localhost:5432/ta"),
        ("postgresql+psycopg://u:p@localhost:5432/ta", "postgresql+asyncpg://u:p@localhost:5432/ta"),
        ("sqlite:///./dev.db", "sqlite+aiosqlite:///./dev.db"),
        ("  postgresql://u:p@host/ta  ", "postgresql+asyncpg://u:p@host/ta"),
        # Already async: left untouched.
        ("postgresql+asyncpg://u:p@localhost:5432/ta", "postgresql+asyncpg://u:p@localhost:5432/ta"),
        ("sqlite+aiosqlite:///./dev.db", "sqlite+aiosqlite:///./dev.db"),
    ],
)
def test_database_url_uses_async_driver(configured: str, expected: str) -> None:
    assert Settings(DATABASE_URL=configured).DATABASE_URL == expected


def test_unknown_database_scheme_is_left_alone() -> None:
    url = "mysql+aiomysql://u:p@localhost/ta"
    assert Settings(DATABASE_URL=url).DATABASE_URL == url
