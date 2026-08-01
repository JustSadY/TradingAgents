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

def test_unversioned_empty_database_is_not_stamped() -> None:
    assert database._is_complete_unversioned_app_schema(set()) is False

def test_complete_unversioned_schema_can_be_stamped() -> None:
    assert database._is_complete_unversioned_app_schema(set(database._BASELINE_APP_TABLES)) is True

def test_partial_unversioned_schema_is_refused_before_stamping() -> None:
    with pytest.raises(RuntimeError, match="partial unversioned Paperclip schema"):
        database._is_complete_unversioned_app_schema({"users", "analysis_results"})
