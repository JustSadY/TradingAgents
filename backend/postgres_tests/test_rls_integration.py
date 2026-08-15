from __future__ import annotations

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

pytestmark = [pytest.mark.postgres_rls, pytest.mark.asyncio(loop_scope="session")]

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
from backend.core.database import AsyncSessionLocal  # noqa: E402
from backend.core.database import engine as runtime_engine
from backend.core.rls_context import (  # noqa: E402
    BackgroundCapability,
    set_public_share_context,
    set_refresh_access_context,
    set_request_admin_context,
    set_request_tenant_context,
    trusted_background_session,
)
from backend.core.security import hash_password  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.alert import PriceAlert  # noqa: E402
from backend.models.analysis import AnalysisResult  # noqa: E402
from backend.models.refresh_session import RefreshSession  # noqa: E402
from backend.models.settings import AppSettings  # noqa: E402
from backend.models.shared_report import SharedReport  # noqa: E402
from backend.models.user import User  # noqa: E402
from backend.repositories.analysis import create_analysis_result  # noqa: E402

migration_engine = create_async_engine(MIGRATION_URL, pool_pre_ping=True)
MigrationSession = async_sessionmaker(migration_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _clean_database():
    async with migration_engine.begin() as conn:
        # users is the root of the tenant-owned FK graph.
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
    yield
    async with migration_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(loop_scope="session")
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


async def test_tenant_cannot_read_or_write_other_tenant_and_runtime_role_is_non_owner(seeded):
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

    async with AsyncSessionLocal() as db:
        await set_request_tenant_context(db, seeded.a)
        visible = set((await db.execute(select(AppSettings.user_id))).scalars())
        assert visible == {seeded.a}
        result = await db.execute(
            update(AppSettings).where(AppSettings.user_id == seeded.b).values(output_language="English")
        )
        assert result.rowcount == 0
        await db.rollback()

    async with MigrationSession() as db:
        language_b = (
            await db.execute(select(AppSettings.output_language).where(AppSettings.user_id == seeded.b))
        ).scalar_one()
        assert language_b == "German"


async def test_admin_context_can_read_all_tenants(seeded):
    async with AsyncSessionLocal() as db:
        await set_request_admin_context(db, seeded.admin)
        context_kind = (
            await db.execute(text("SELECT current_setting('app.context_kind', true)"))
        ).scalar_one()
        visible = set((await db.execute(select(AppSettings.user_id))).scalars())
        assert context_kind == "admin"
        assert visible == {seeded.a, seeded.b}


async def test_refresh_context_is_exact_session_or_user_and_rotation_logout_work(seeded):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client_a, AsyncClient(
        transport=transport, base_url="http://test"
    ) as client_b:
        login_a = await client_a.post("/auth/login", json={"username": "tenant-a", "password": "pass-a"})
        login_b = await client_b.post("/auth/login", json={"username": "tenant-b", "password": "pass-b"})
        assert login_a.status_code == 200, login_a.text
        assert login_b.status_code == 200, login_b.text
        first_cookie = client_a.cookies.get("ta_refresh")
        assert first_cookie

        async with MigrationSession() as owner_db:
            rows = list((await owner_db.execute(select(RefreshSession))).scalars())
            sid_a = next(row.id for row in rows if row.user_id == seeded.a)
            sid_b = next(row.id for row in rows if row.user_id == seeded.b)

        async with AsyncSessionLocal() as db:
            await set_refresh_access_context(db, session_id=sid_a)
            by_session = set((await db.execute(select(RefreshSession.id))).scalars())
            assert by_session == {sid_a}
            await db.rollback()

            await set_refresh_access_context(db, user_id=seeded.b)
            by_user = set((await db.execute(select(RefreshSession.id))).scalars())
            assert by_user == {sid_b}

        refreshed = await client_a.post("/auth/refresh")
        assert refreshed.status_code == 200, refreshed.text
        second_cookie = client_a.cookies.get("ta_refresh")
        assert second_cookie and second_cookie != first_cookie

        async with MigrationSession() as owner_db:
            session = await owner_db.get(RefreshSession, sid_a)
            assert session is not None
            assert session.previous_jti_hash
            assert session.current_jti_hash != session.previous_jti_hash

        logged_out = await client_a.post("/auth/logout")
        assert logged_out.status_code == 204
        async with MigrationSession() as owner_db:
            session = await owner_db.get(RefreshSession, sid_a)
            assert session is not None and session.revoked_at is not None


async def test_public_share_context_is_token_then_exact_analysis_id(seeded):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        active = await client.get("/api/share/active-share")
        assert active.status_code == 200, active.text
        assert active.json()["final_decision"] == "A report"
        assert (await client.get("/api/share/expired-share")).status_code == 410
        assert (await client.get("/api/share/revoked-share")).status_code == 404
        assert (await client.get("/api/share/does-not-exist")).status_code == 404

    async with AsyncSessionLocal() as db:
        await set_public_share_context(db, token="active-share")
        tokens = set((await db.execute(select(SharedReport.token))).scalars())
        assert tokens == {"active-share"}
        assert (await db.execute(select(AnalysisResult.id))).scalars().all() == []
        await db.rollback()

        await set_public_share_context(db, token="active-share", analysis_id=seeded.analysis_a)
        analysis_ids = set((await db.execute(select(AnalysisResult.id))).scalars())
        assert analysis_ids == {seeded.analysis_a}
        assert seeded.analysis_b not in analysis_ids


async def test_unknown_background_capability_cannot_get_system_context(seeded):
    with pytest.raises(ValueError):
        BackgroundCapability("not-an-allowed-capability")

    async with trusted_background_session(BackgroundCapability.ALERT_CHECKER) as db:
        kind, capability = (
            await db.execute(
                text(
                    "SELECT current_setting('app.context_kind', true), "
                    "current_setting('app.background_capability', true)"
                )
            )
        ).one()
        tickers = set((await db.execute(select(PriceAlert.ticker))).scalars())
        assert kind == "system"
        assert capability == BackgroundCapability.ALERT_CHECKER.value
        assert tickers == {"AAPL", "MSFT"}


async def test_user_owned_arq_and_cron_use_tenant_scope_not_system(seeded, monkeypatch):
    import backend.services.analysis_queue as analysis_queue
    import backend.services.analysis_service as analysis_service
    import backend.worker as worker
    from backend.services.cron_service import CronService

    seen: dict[str, object] = {}

    async def fake_run_individual(_ticker, _date, _asset, _settings, db, _emitter, _triggered_by, _user):
        seen["visible"] = set((await db.execute(select(AnalysisResult.user_id))).scalars())
        seen["context"] = (
            await db.execute(
                text(
                    "SELECT current_setting('app.context_kind', true), "
                    "current_setting('app.background_capability', true)"
                )
            )
        ).one()
        return {}, SimpleNamespace(
            id=seeded.analysis_a,
            signal=None,
            final_decision="",
            analysis_mode="live",
            learning_eligible=True,
        )

    monkeypatch.setattr(analysis_service, "run_individual_analysis", fake_run_individual)
    monkeypatch.setattr(analysis_service, "_track_running_task", AsyncMock())
    monkeypatch.setattr(analysis_service, "_clear_terminal_task_state", AsyncMock())
    monkeypatch.setattr(analysis_service, "_emit_auto_order_result", AsyncMock())

    await worker.run_analysis_job({}, "AAPL", "2026-08-14", "stock", seeded.a, "worker-tenant-a")
    assert seen["visible"] == {seeded.a}
    assert tuple(seen["context"]) == ("tenant", "")

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


async def test_context_reapplies_after_repository_commit_on_real_postgres(seeded):
    async with AsyncSessionLocal() as db:
        await set_request_tenant_context(db, seeded.a)
        created = await create_analysis_result(
            db,
            user_id=seeded.a,
            ticker="TSLA",
            trade_date="2026-08-14",
            status="queued",
            task_id="rls-context-reapply",
            triggered_by="manual",
        )
        assert created.user_id == seeded.a
        kind, user_id = (
            await db.execute(
                text(
                    "SELECT current_setting('app.context_kind', true), "
                    "current_setting('app.user_id', true)"
                )
            )
        ).one()
        assert (kind, user_id) == ("tenant", str(seeded.a))
        assert set((await db.execute(select(AppSettings.user_id))).scalars()) == {seeded.a}
        wrong_write = await db.execute(
            update(AppSettings).where(AppSettings.user_id == seeded.b).values(output_language="English")
        )
        assert wrong_write.rowcount == 0
        await db.rollback()


async def test_transaction_local_context_does_not_leak_on_same_pooled_connection(seeded):
    await runtime_engine.dispose()

    async with AsyncSessionLocal() as db:
        await set_request_admin_context(db, seeded.admin)
        pid_before = (await db.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        assert set((await db.execute(select(AppSettings.user_id))).scalars()) == {seeded.a, seeded.b}
        await db.rollback()

    async with AsyncSessionLocal() as db:
        pid_after = (await db.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        assert pid_after == pid_before
        assert (await db.execute(select(AppSettings.id))).scalars().all() == []
        await set_request_tenant_context(db, seeded.b)
        kind, user_id = (
            await db.execute(
                text(
                    "SELECT current_setting('app.context_kind', true), "
                    "current_setting('app.user_id', true)"
                )
            )
        ).one()
        assert (kind, user_id) == ("tenant", str(seeded.b))
        assert set((await db.execute(select(AppSettings.user_id))).scalars()) == {seeded.b}
