import pytest

from backend.core import database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://postgres:pw%21159@db.example.com:5432/postgres",
        "postgresql+asyncpg://postgres:plain@db.example.com:5432/postgres",
    ],
)
def test_alembic_config_keeps_url_verbatim(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setattr(database.settings, "DATABASE_URL", url)
    assert database._alembic_config().get_main_option("sqlalchemy.url") == url
