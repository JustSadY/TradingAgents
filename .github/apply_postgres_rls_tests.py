from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


replace(
    "backend/pyproject.toml",
    '''[tool.pytest.ini_options]\nasyncio_mode = "auto"\ntestpaths = ["tests"]\npythonpath = [".."]\n''',
    '''[tool.pytest.ini_options]\nasyncio_mode = "auto"\ntestpaths = ["tests"]\npythonpath = [".."]\nmarkers = [\n    "postgres_rls: PostgreSQL integration tests for runtime RLS contexts",\n]\n''',
)

Path("backend/postgres_tests").mkdir(exist_ok=True)
Path("backend/postgres_tests/test_rls_integration.py").write_text(
    r'''from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.postgres_rls

RUNTIME_URL = os.getenv("TEST_POSTGRES_RLS_URL")
MIGRATION_URL = os.getenv("TEST_POSTGRES_MIGRATION_URL")
if not RUNTIME_URL or not MIGRATION_URL:
    pytest.skip("TEST_POSTGRES_RLS_URL and TEST_POSTGRES_MIGRATION_URL are required", allow_module_level=True)

# The application engine must be created with the non-owner runtime role.
os.environ["DATABASE_URL"] = RUNTIME_URL
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "postgres-rls-test-secret")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("ANALYSIS_QUEUE_MODE", "inline")
os.environ.setdefault("TRADINGAGENTS_LOG_DIR", "/tmp")
os.environ.setdefault("TRADINGAGENTS_DATA_CACHE_DIR", "/tmp/ta_cache")
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", "/tmp/ta_results")

import backend.bootstrap  # noqa: E402,F401
import backend.models  # noqa: E402,F401
from backend.core.database import AsyncSessionLocal, engine as runtime_engine  # noqa: E402
from backend.core.rls_context import (  # noqa: E402
    set_request_admin_context,
    set_request_tenant_context,
)
from backend.core.security import hash_password  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.alert import PriceAlert  # noqa: E402
from backend.models.analysis import AnalysisResult  # noqa: E402
from backend.models.refresh_session import RefreshSession  # noqa: E402
from backend.models.settings import AppSettings  # noqa: E402
from backend.models.shared_report import SharedReport  # noqa: E402
from backend.models.user import User  # noqa: E402

migration_engine = create_async_engine(MIGRATION_URL, pool_pre_ping=True)
MigrationSession = async_sessionmaker(migration_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _clean_database():
    async with migration_engine.begin() as conn:
        # users is the root of the tenant-owned FK graph.
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
    yield
    async with migration_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def seeded():
    async with MigrationSession() as db:
        tenant_a = User(username="tenant-a", hashed_password=hash_password("pass-a"), role="user", is_active=True)
        tenant_b = User(username="tenant-b", hashed_password=hash_password("pass-b"), role="user", is_active=True)
        admin = User(username="rls-admin", hashed_password=hash_password("admin-pass"), role="admin", is_active=True)
        db.add_all([tenant_a, tenant_b, admin])
        await db.flush()

        settings_a = AppSettings(user_id=tenant_a.id, output_language="Turkish", cron_enabled=True)
        settings_a.watchlist = ["AAPL"]
        settings_b = AppSettings(user_id=tenant_b.id, output_language="German", cron_enabled=True)
        settings_b.watchlist = ["MSFT"]
        db.add_all([settings_a, settings_b])

        analyses = [
            AnalysisResult(user_id=tenant_a.id, ticker="AAPL", trade_date="2026-08-14", status="completed", final_decision="A report"),
            AnalysisResult(user_id=tenant_b.id, ticker="MSFT", trade_date="2026-08-14", status="completed", final_decision="B report"),
            AnalysisResult(user_id=tenant_a.id, ticker="NVDA", trade_date="2026-08-14", status="completed", final_decision="Expired report"),
            AnalysisResult(user_id=tenant_a.id, ticker="AMD", trade_date="2026-08-14", status="completed", final_decision="Revoked report"),
        ]
        db.add_all(analyses)
        await db.flush()
        now = datetime.now(UTC)
        db.add_all(
            [
                SharedReport(user_id=tenant_a.id, analysis_id=analyses[0].id, token="active-share", expires_at=now + timedelta(hours=1)),
                SharedReport(user_id=tenant_a.id, analysis_id=analyses[2].id, token="expired-share", expires_at=now - timedelta(seconds=1)),
                SharedReport(user_id=tenant_a.id, analysis_id=analyses[3].id, token="revoked-share", expires_at=now + timedelta(hours=1), revoked_at=now),
                PriceAlert(user_id=tenant_a.id, ticker="AAPL", condition="above", target_price=Decimal("9999"), enabled=True),
                PriceAlert(user_id=tenant_b.id, ticker="MSFT", condition="above", target_price=Decimal("9999"), enabled=True),
            ]
        )
        await db.commit()
        return SimpleNamespace(
            a=tenant_a.id,
            b=tenant_b.id,
            admin=admin.id,
            analysis_a=analyses[0].id,
            analysis_b=analyses[1].id,
        )


@pytest.mark.asyncio
async def test_runtime_role_is_non_owner_nosuperuser_nobypassrls():
    async with runtime_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT r.rolsuper, r.rolbypassrls, "
                    "EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=current_schema() AND c.relrowsecurity AND c.relowner=r.oid) AS owns_rls "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                )
            )
        ).one()
    assert tuple(bool(value) for value in row) == (False, False, False)


@pytest.mark.asyncio
async def test_tenant_isolation_admin_visibility_and_wrong_tenant_write(seeded):
    async with AsyncSessionLocal() as db:
        await set_request_tenant_context(db, seeded.a)
        visible = set((await db.execute(select(AppSettings.user_id))).scalars())
        assert visible == {seeded.a}
        assert await db.get(AppSettings, 2) is None

        result = await db.execute(
            update(AppSettings).where(AppSettings.user_id == seeded.b).values(output_language="English")
        )
        assert result.rowcount == 0
        await db.rollback()

    async with AsyncSessionLocal() as db:
        await set_request_admin_context(db, seeded.admin)
        assert set((await db.execute(select(AppSettings.user_id))).scalars()) == {seeded.a, seeded.b}

    async with MigrationSession() as db:
        language_b = (
            await db.execute(select(AppSettings.output_language).where(AppSettings.user_id == seeded.b))
        ).scalar_one()
        assert language_b == "German"


@pytest.mark.asyncio
async def test_refresh_rotation_and_logout_revoke_under_pre_auth_context(seeded):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/auth/login", json={"username": "tenant-a", "password": "pass-a"})
        assert login.status_code == 200, login.text
        first_cookie = client.cookies.get("ta_refresh")
        assert first_cookie

        refreshed = await client.post("/auth/refresh")
        assert refreshed.status_code == 200, refreshed.text
        second_cookie = client.cookies.get("ta_refresh")
        assert second_cookie and second_cookie != first_cookie

        async with MigrationSession() as owner_db:
            session = (await owner_db.execute(select(RefreshSession).where(RefreshSession.user_id == seeded.a))).scalar_one()
            assert session.previous_jti_hash
            assert session.current_jti_hash != session.previous_jti_hash
            sid = session.id

        logged_out = await client.post("/auth/logout")
        assert logged_out.status_code == 204

        async with MigrationSession() as owner_db:
            session = await owner_db.get(RefreshSession, sid)
            assert session is not None and session.revoked_at is not None


@pytest.mark.asyncio
async def test_public_share_context_reads_only_active_exact_report(seeded):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        active = await client.get("/api/share/active-share")
        assert active.status_code == 200, active.text
        assert active.json()["analysis"]["final_decision"] == "A report"

        expired = await client.get("/api/share/expired-share")
        assert expired.status_code == 410

        revoked = await client.get("/api/share/revoked-share")
        assert revoked.status_code == 404

        missing = await client.get("/api/share/does-not-exist")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_arq_worker_session_is_scoped_to_job_owner(seeded, monkeypatch):
    import backend.services.analysis_service as analysis_service
    import backend.worker as worker

    seen: dict[str, object] = {}

    async def fake_run_individual(_ticker, _date, _asset, _settings, db, _emitter, _triggered_by, _user):
        ids = set((await db.execute(select(AnalysisResult.user_id))).scalars())
        seen["visible"] = ids
        return {}, SimpleNamespace(id=seeded.analysis_a, signal=None, final_decision="", analysis_mode="live", learning_eligible=True)

    monkeypatch.setattr(analysis_service, "run_individual_analysis", fake_run_individual)
    monkeypatch.setattr(analysis_service, "_track_running_task", AsyncMock())
    monkeypatch.setattr(analysis_service, "_clear_terminal_task_state", AsyncMock())
    monkeypatch.setattr(analysis_service, "_emit_auto_order_result", AsyncMock())

    await worker.run_analysis_job({}, "AAPL", "2026-08-14", "stock", seeded.a, "worker-tenant-a")
    assert seen["visible"] == {seeded.a}


@pytest.mark.asyncio
async def test_cron_reads_owner_settings_and_writes_only_that_tenant(seeded, monkeypatch):
    import backend.services.analysis_queue as analysis_queue
    import backend.services.analysis_service as analysis_service
    from backend.services.cron_service import CronService

    dispatch = AsyncMock()
    monkeypatch.setattr(analysis_queue, "dispatch_analysis", dispatch)
    monkeypatch.setattr(analysis_service, "register_queued_task", AsyncMock())

    cron = CronService()
    await cron._run_user_watchlist_scan_once(seeded.a)
    assert dispatch.await_count == 1
    assert dispatch.await_args.kwargs["user"].id == seeded.a

    async with MigrationSession() as db:
        cron_rows = list(
            (await db.execute(select(AnalysisResult).where(AnalysisResult.triggered_by == "cron"))).scalars()
        )
        assert cron_rows and {row.user_id for row in cron_rows} == {seeded.a}


@pytest.mark.asyncio
async def test_alert_checker_can_discover_all_tenants_only_via_background_capability(seeded, monkeypatch):
    import backend.services.alert_service as alert_service

    observed: list[str] = []

    async def fake_prices(tickers):
        observed.extend(tickers)
        return {}

    monkeypatch.setattr(alert_service, "get_live_prices_batch", fake_prices)
    await alert_service.check_price_alerts()
    assert set(observed) == {"AAPL", "MSFT"}

    async with AsyncSessionLocal() as db:
        await set_request_tenant_context(db, seeded.a)
        tenant_alerts = set((await db.execute(select(PriceAlert.ticker))).scalars())
        assert tenant_alerts == {"AAPL"}


@pytest.mark.asyncio
async def test_transaction_local_context_does_not_leak_through_pool(seeded):
    async with AsyncSessionLocal() as db:
        await set_request_admin_context(db, seeded.admin)
        assert len((await db.execute(select(AppSettings.id))).scalars().all()) == 2
        await db.rollback()

    # No RLS context at all: pooled connection reuse must not inherit admin.
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(AppSettings.id))).scalars().all() == []
        await set_request_tenant_context(db, seeded.b)
        visible = set((await db.execute(select(AppSettings.user_id))).scalars())
        assert visible == {seeded.b}
''',
    encoding="utf-8",
)
