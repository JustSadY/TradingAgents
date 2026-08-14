from __future__ import annotations

import subprocess
import sys
from pathlib import Path


# Keep all PostgreSQL integration tests on one event loop because the app owns
# module-level async engines/pools. This changes only test lifecycle, not RLS.
path = Path("backend/postgres_tests/test_rls_integration.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "pytestmark = pytest.mark.postgres_rls\n",
    'pytestmark = [pytest.mark.postgres_rls, pytest.mark.asyncio(loop_scope="session")]\n',
    1,
)
text = text.replace(
    "@pytest_asyncio.fixture(autouse=True)\nasync def _clean_database():\n",
    '@pytest_asyncio.fixture(autouse=True, loop_scope="session")\nasync def _clean_database():\n',
    1,
)
text = text.replace(
    "@pytest_asyncio.fixture\nasync def seeded():\n",
    '@pytest_asyncio.fixture(loop_scope="session")\nasync def seeded():\n',
    1,
)
text = text.replace("@pytest.mark.asyncio\n", "")

old_import = '''from backend.core.rls_context import (  # noqa: E402\n    set_request_admin_context,\n    set_request_tenant_context,\n)\n'''
new_import = '''from backend.core.rls_context import (  # noqa: E402\n    BackgroundCapability,\n    set_public_share_context,\n    set_refresh_access_context,\n    set_request_admin_context,\n    set_request_tenant_context,\n    trusted_background_session,\n)\n'''
if old_import not in text:
    raise SystemExit("PostgreSQL RLS import block not found")
text = text.replace(old_import, new_import, 1)
text = text.replace(
    "from backend.models.user import User  # noqa: E402\n",
    "from backend.models.user import User  # noqa: E402\nfrom backend.repositories.analysis import create_analysis_result  # noqa: E402\n",
    1,
)

# The acceptance suite is intentionally eight tests matching the eight security
# behaviours requested for production RLS verification. The runtime-role check
# is folded into the tenant-isolation test so the suite remains exactly 8/8.
start = text.index("async def test_runtime_role_is_non_owner_nosuperuser_nobypassrls():")
prefix = text[:start]
tests = r'''async def test_tenant_cannot_read_or_write_other_tenant_and_runtime_role_is_non_owner(seeded):
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
'''
path.write_text(prefix + tests, encoding="utf-8")

pyproject = Path("backend/pyproject.toml")
config = pyproject.read_text(encoding="utf-8")
needle = 'include = ["core/temporal.py", "schemas"]\nexclude = ["tests", "postgres_tests"]\n'
replacement = 'include = ["core/temporal.py", "schemas"]\nexclude = ["tests", "postgres_tests"]\nextraPaths = [".."]\n'
if needle not in config:
    raise SystemExit("pyright include/exclude block not found")
pyproject.write_text(config.replace(needle, replacement, 1), encoding="utf-8")

cron = Path("backend/services/cron_service.py")
cron_text = cron.read_text(encoding="utf-8")
old = '''            trade_date = _trade_date_for_asset("stock")\n            _logger.info(\n                "User cron watchlist scan started for user=%s (id=%d), date=%s",\n                user.username, user_id, trade_date,\n            )\n'''
new = '''            trade_date = _trade_date_for_asset("stock")\n            username = user.username\n            _logger.info(\n                "User cron watchlist scan started for user=%s (id=%d), date=%s",\n                username, user_id, trade_date,\n            )\n'''
if old not in cron_text:
    raise SystemExit("cron username snapshot insertion point not found")
cron_text = cron_text.replace(old, new, 1)
start = cron_text.index("    async def _run_user_watchlist_scan_once")
end = cron_text.index("\n    def get_status", start)
segment = cron_text[start:end].replace("user.username", "username")
cron.write_text(cron_text[:start] + segment + cron_text[end:], encoding="utf-8")

# Normalize Ruff fixes before the exact acceptance commit. The workflow reruns
# every gate after this commit is created.
subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "uv"], check=True)
subprocess.run(["uv", "lock", "--check"], cwd="backend", check=True)
subprocess.run(["uv", "sync", "--frozen"], cwd="backend", check=True)
subprocess.run(["uv", "run", "ruff", "check", ".", "--fix"], cwd="backend", check=True)
subprocess.run(["uv", "run", "ruff", "check", "."], cwd="backend", check=True)

if subprocess.run(["git", "diff", "--quiet", "--", "frontend"]).returncode != 0:
    raise SystemExit("frontend changed while materializing backend hardening candidate")
subprocess.run(["git", "diff", "--check"], check=True)

subprocess.run(["git", "fetch", "origin", "integration/memory-maintenance-base", "tmp/backend-contract-hardening"], check=True)
local_before = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
remote_before = subprocess.check_output(
    ["git", "rev-parse", "origin/tmp/backend-contract-hardening"], text=True
).strip()
if local_before != remote_before:
    raise SystemExit(f"temp branch moved during candidate build: {remote_before} != {local_before}")
integration_sha = subprocess.check_output(
    ["git", "rev-parse", "origin/integration/memory-maintenance-base"], text=True
).strip()
if integration_sha != "dc4cd69be2a7ac654f5646883e657ff9541a8a90":
    raise SystemExit(f"integration branch moved before acceptance: {integration_sha}")
if subprocess.run(
    ["git", "diff", "--quiet", "54ab148cc4b0b6609ddaf0e9884391ece49e59df", integration_sha, "--", "backend"]
).returncode != 0:
    raise SystemExit("integration backend tree no longer matches verified B0")

subprocess.run(["git", "add", "backend"], check=True)
staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
if any(name.startswith("frontend/") for name in staged):
    raise SystemExit("frontend staged unexpectedly")
if not any(name.startswith("backend/") for name in staged):
    raise SystemExit("backend hardening candidate has no backend changes")

subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(
    ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
    check=True,
)
subprocess.run(["git", "commit", "-m", "Materialize B1-B4 backend hardening candidate"], check=True)
candidate_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
print(f"EXACT_ACCEPTANCE_SHA={candidate_sha}")
subprocess.run(["git", "push", "origin", "HEAD:tmp/backend-contract-hardening"], check=True)

if subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip():
    raise SystemExit("candidate commit is not clean before acceptance")
