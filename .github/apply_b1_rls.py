from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# 0019: replace the broad 0018 policy with explicit context kinds. 0018 stays
# immutable/published and its 0017 -> 0018 ancestry remains unchanged.
Path("backend/alembic/versions/20260814_0019-8a90b2c3d4e5_contextual_rls.py").write_text(
    r'''"""add explicit request/background/refresh/share RLS contexts

Revision ID: 8a90b2c3d4e5
Revises: 7f8091a2b3c4
Create Date: 2026-08-14 18:20:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8a90b2c3d4e5"
down_revision: str | None = "7f8091a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM_CAPABILITIES = (
    "alert_checker",
    "alert_outbox",
    "performance_backfill",
    "position_monitor",
    "maintenance_cleanup",
    "startup_seed",
    "startup_cleanup",
    "cron_bootstrap",
    "alert_recovery",
)


def _base_predicate(table_name: str) -> str:
    system_values = ", ".join(f"'{value}'" for value in _SYSTEM_CAPABILITIES)
    clauses = [
        "current_setting('app.context_kind', true) = 'admin'",
        (
            "(current_setting('app.context_kind', true) = 'system' "
            f"AND current_setting('app.background_capability', true) IN ({system_values}))"
        ),
        (
            "(current_setting('app.context_kind', true) = 'tenant' "
            "AND user_id = NULLIF(current_setting('app.user_id', true), '')::bigint)"
        ),
    ]
    if table_name == "refresh_sessions":
        clauses.append(
            "(current_setting('app.context_kind', true) = 'refresh' AND ("
            "id = NULLIF(current_setting('app.refresh_session_id', true), '') "
            "OR user_id = NULLIF(current_setting('app.user_id', true), '')::bigint))"
        )
    elif table_name == "shared_reports":
        clauses.append(
            "(current_setting('app.context_kind', true) = 'share' "
            "AND token = NULLIF(current_setting('app.public_share_token', true), ''))"
        )
    elif table_name == "analysis_results":
        clauses.append(
            "(current_setting('app.context_kind', true) = 'share' "
            "AND id = NULLIF(current_setting('app.share_analysis_id', true), '')::bigint)"
        )
    return " OR ".join(clauses)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        """
        SELECT DISTINCT c.table_schema, c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.table_schema = current_schema()
          AND c.column_name = 'user_id'
          AND t.table_type = 'BASE TABLE'
          AND c.table_name <> 'alembic_version'
        ORDER BY c.table_name
        """
    ).fetchall()
    for schema_name, table_name in rows:
        policy_name = f"tenant_isolation_{table_name}"
        predicate = _base_predicate(table_name)
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{schema_name}"."{table_name}"')
        op.execute(f'ALTER TABLE "{schema_name}"."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{policy_name}" ON "{schema_name}"."{table_name}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        """
        SELECT DISTINCT c.table_schema, c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.table_schema = current_schema()
          AND c.column_name = 'user_id'
          AND t.table_type = 'BASE TABLE'
          AND c.table_name <> 'alembic_version'
        ORDER BY c.table_name
        """
    ).fetchall()
    legacy = (
        "current_setting('app.is_admin', true) = 'true' OR "
        "user_id = NULLIF(current_setting('app.user_id', true), '')::bigint"
    )
    for schema_name, table_name in rows:
        policy_name = f"tenant_isolation_{table_name}"
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{schema_name}"."{table_name}"')
        op.execute(
            f'CREATE POLICY "{policy_name}" ON "{schema_name}"."{table_name}" '
            f"USING ({legacy}) WITH CHECK ({legacy})"
        )
''',
    encoding="utf-8",
)

# Existing compatibility entrypoint remains, but it now establishes the richer
# context model rather than owning policy details itself.
replace(
    "backend/core/database.py",
    '''async def set_tenant_context(db: AsyncSession, *, user_id: int, is_admin: bool = False) -> None:\n    """Set transaction-local PostgreSQL values consumed by tenant RLS policies."""\n    bind = db.get_bind()\n    if bind.dialect.name != "postgresql":\n        return\n    await db.execute(\n        text(\n            "SELECT set_config('app.user_id', :user_id, true), "\n            "set_config('app.is_admin', :is_admin, true)"\n        ),\n        {"user_id": str(int(user_id)), "is_admin": "true" if is_admin else "false"},\n    )\n''',
    '''async def set_tenant_context(db: AsyncSession, *, user_id: int, is_admin: bool = False) -> None:\n    """Compatibility wrapper for authenticated request context."""\n    from backend.core.rls_context import set_request_admin_context, set_request_tenant_context\n\n    if is_admin:\n        await set_request_admin_context(db, user_id)\n    else:\n        await set_request_tenant_context(db, user_id)\n''',
)

# Authenticated requests explicitly distinguish admin and tenant context.
replace(
    "backend/api/deps.py",
    "from backend.core.database import get_db, set_tenant_context\n",
    "from backend.core.database import get_db\nfrom backend.core.rls_context import set_request_admin_context, set_request_tenant_context\n",
)
replace(
    "backend/api/deps.py",
    "    await set_tenant_context(db, user_id=user.id, is_admin=user.is_admin)\n",
    "    if user.is_admin:\n        await set_request_admin_context(db, user.id)\n    else:\n        await set_request_tenant_context(db, user.id)\n",
)

# Refresh-session access is pre-auth and selected by session id/token, never by
# an all-tenant admin bypass.
replace(
    "backend/api/auth.py",
    "from backend.core.limiter import limiter\n",
    "from backend.core.limiter import limiter\nfrom backend.core.rls_context import set_refresh_access_context\n",
)
replace(
    "backend/api/auth.py",
    "    sid, jti = new_token_id(), new_token_id()\n    db.add(RefreshSession(\n",
    "    sid, jti = new_token_id(), new_token_id()\n    await set_refresh_access_context(db, session_id=sid, user_id=user.id)\n    db.add(RefreshSession(\n",
)
replace(
    "backend/api/auth.py",
    "    row = await db.execute(select(RefreshSession).where(RefreshSession.id == sid).with_for_update())\n",
    "    await set_refresh_access_context(db, session_id=sid)\n    row = await db.execute(select(RefreshSession).where(RefreshSession.id == sid).with_for_update())\n",
    1,
)
# Only the cookie logout occurrence remains after the refresh replacement above.
replace(
    "backend/api/auth.py",
    "            if sid:\n                row = await db.execute(select(RefreshSession).where(RefreshSession.id == sid).with_for_update())\n",
    "            if sid:\n                await set_refresh_access_context(db, session_id=sid)\n                row = await db.execute(select(RefreshSession).where(RefreshSession.id == sid).with_for_update())\n",
)

# Public share access gets a token-scoped policy first, then an exact analysis id
# selector after the share row is validated.
replace(
    "backend/api/share.py",
    "from backend.models.user import User\n",
    "from backend.core.rls_context import set_public_share_context\nfrom backend.models.user import User\n",
)
replace(
    "backend/api/share.py",
    "async def get_shared_report(token: str, db: AsyncSession = Depends(get_db)):\n    share = await share_service.get_shared_report(db, token)\n",
    "async def get_shared_report(token: str, db: AsyncSession = Depends(get_db)):\n    await set_public_share_context(db, token=token)\n    share = await share_service.get_shared_report(db, token)\n",
)
replace(
    "backend/api/share.py",
    "    analysis = await share_service.get_analysis_for_share(db, share.analysis_id)\n",
    "    await set_public_share_context(db, token=token, analysis_id=share.analysis_id)\n    analysis = await share_service.get_analysis_for_share(db, share.analysis_id)\n",
)

# User-specific memory settings always re-establish their own tenant context on
# the internal session.
replace(
    "backend/services/memory_service.py",
    "        from backend.core.database import AsyncSessionLocal\n",
    "        from backend.core.database import AsyncSessionLocal\n        from backend.core.rls_context import set_user_background_context\n",
)
replace(
    "backend/services/memory_service.py",
    "            if not user:\n                return None\n\n            row = (await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))).scalar_one_or_none()\n",
    "            if not user:\n                return None\n            await set_user_background_context(db, user_id)\n\n            row = (await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))).scalar_one_or_none()\n",
)

# Maintenance is an explicitly allowlisted cross-tenant background capability.
replace(
    "backend/services/maintenance_service.py",
    "from backend.core.database import AsyncSessionLocal\n",
    "from backend.core.rls_context import BackgroundCapability, trusted_background_session\n",
)
replace(
    "backend/services/maintenance_service.py",
    "    async with AsyncSessionLocal() as db:\n",
    "    async with trusted_background_session(BackgroundCapability.MAINTENANCE_CLEANUP) as db:\n",
)

# Worker preparation is user-scoped; terminal updates also receive the owner id.
replace(
    "backend/worker.py",
    "async def _mark_analysis_terminal(task_id: str, status: str) -> None:\n",
    "async def _mark_analysis_terminal(task_id: str, status: str, user_id: int | None) -> None:\n",
)
replace(
    "backend/worker.py",
    "    from backend.models.analysis import AnalysisResult\n\n    try:\n        async with AsyncSessionLocal() as db:\n",
    "    from backend.models.analysis import AnalysisResult\n    from backend.core.rls_context import set_user_background_context\n\n    try:\n        async with AsyncSessionLocal() as db:\n            if user_id is not None:\n                await set_user_background_context(db, user_id)\n",
)
# Preparation sessions: resolve the user on the unprotected users table, then
# tenant-scope every user-owned table access.
for needle in (
    "            user = await db.get(User, user_id) if user_id is not None else None\n            if user_id is not None and user is None:\n",
):
    # There are two identical analysis/portfolio occurrences.
    text = Path("backend/worker.py").read_text(encoding="utf-8")
    occurrences = text.count(needle)
    if occurrences != 2:
        raise SystemExit(f"expected two worker user-load patterns, got {occurrences}")
    replacement = (
        "            user = await db.get(User, user_id) if user_id is not None else None\n"
        "            if user_id is not None:\n"
        "                from backend.core.rls_context import set_user_background_context\n"
        "                await set_user_background_context(db, user_id)\n"
        "            if user_id is not None and user is None:\n"
    )
    Path("backend/worker.py").write_text(text.replace(needle, replacement), encoding="utf-8")

# Every terminal helper call now carries the owner selector.
worker = Path("backend/worker.py")
text = worker.read_text(encoding="utf-8")
text = text.replace('await _mark_analysis_terminal(task_id, "failed")', 'await _mark_analysis_terminal(task_id, "failed", user_id)')
text = text.replace('await _mark_analysis_terminal(task_id, "cancelled")', 'await _mark_analysis_terminal(task_id, "cancelled", user_id)')
worker.write_text(text, encoding="utf-8")

# Analysis lifecycle sessions opened after request/queue dispatch must recreate
# tenant scope explicitly; contextvars alone do not configure PostgreSQL.
replace(
    "backend/services/analysis_service.py",
    "from backend.core.database import AsyncSessionLocal\n",
    "from backend.core.database import AsyncSessionLocal\nfrom backend.core.rls_context import set_user_background_context\n",
)
replace(
    "backend/services/analysis_service.py",
    "                async with AsyncSessionLocal() as db:\n                    await db.execute(\n",
    "                async with AsyncSessionLocal() as db:\n                    if user_id is not None:\n                        await set_user_background_context(db, user_id)\n                    await db.execute(\n",
)
replace(
    "backend/services/analysis_service.py",
    "    async with AsyncSessionLocal() as db:\n        try:\n            _, row = await run_analysis(\n",
    "    async with AsyncSessionLocal() as db:\n        if user is not None:\n            await set_user_background_context(db, user.id)\n        try:\n            _, row = await run_analysis(\n",
)
replace(
    "backend/services/analysis_service.py",
    "        async with AsyncSessionLocal() as db:\n            await run_portfolio_analysis(\n",
    "        async with AsyncSessionLocal() as db:\n            if user is not None:\n                await set_user_background_context(db, user.id)\n            await run_portfolio_analysis(\n",
)
replace(
    "backend/services/analysis_service.py",
    "            async with AsyncSessionLocal() as session:\n                try:\n                    from backend.services.analysis.orchestrator import run_individual_analysis\n",
    "            async with AsyncSessionLocal() as session:\n                if current_user is not None:\n                    await set_user_background_context(session, current_user.id)\n                try:\n                    from backend.services.analysis.orchestrator import run_individual_analysis\n",
)

# Annotation persistence receives the owner id from the orchestrator so its
# detached background session never needs system access.
replace(
    "backend/services/analysis/tasks.py",
    "    output_language: str = \"English\",\n) -> None:\n",
    "    output_language: str = \"English\",\n    user_id: int | None = None,\n) -> None:\n",
)
replace(
    "backend/services/analysis/tasks.py",
    "        async with AsyncSessionLocal() as s:\n            from backend.repositories.analysis import get_analysis_by_id as _repo_get\n",
    "        async with AsyncSessionLocal() as s:\n            if user_id is not None:\n                from backend.core.rls_context import set_user_background_context\n\n                await set_user_background_context(s, user_id)\n            from backend.repositories.analysis import get_analysis_by_id as _repo_get\n",
)
# Call site adds the known analysis owner. Keep keyword placement additive.
orch = Path("backend/services/analysis/orchestrator.py")
text = orch.read_text(encoding="utf-8")
needle = "extract_and_save_annotations("
pos = text.find(needle)
if pos == -1:
    raise SystemExit("annotation call not found")
# Add user_id only to the call, not the definition (which lives elsewhere).
call_end = text.find("\n            )", pos)
if call_end == -1:
    call_end = text.find("\n        )", pos)
segment = text[pos:call_end]
if "user_id=" not in segment:
    insertion = "\n                user_id=user_id," if "                output_language=" in segment else "\n            user_id=user_id,"
    # place immediately before closing paren using its actual indentation
    text = text[:call_end] + insertion + text[call_end:]
orch.write_text(text, encoding="utf-8")

# Cron: user watchlist jobs are tenant-scoped. Global jobs use auditable system
# capabilities, never app.is_admin=true.
replace(
    "backend/services/cron_service.py",
    "        async with AsyncSessionLocal() as db:\n            u_res = await db.execute(select(User).where(User.id == user_id))\n",
    "        async with AsyncSessionLocal() as db:\n            from backend.core.rls_context import set_user_background_context\n\n            await set_user_background_context(db, user_id)\n            u_res = await db.execute(select(User).where(User.id == user_id))\n",
)
replace(
    "backend/services/cron_service.py",
    "            async with AsyncSessionLocal() as db:\n                await backfill_returns(db)\n",
    "            from backend.core.rls_context import BackgroundCapability, trusted_background_session\n\n            async with trusted_background_session(BackgroundCapability.PERFORMANCE_BACKFILL) as db:\n                await backfill_returns(db)\n",
)
replace(
    "backend/services/cron_service.py",
    "            async with AsyncSessionLocal() as db:\n                closed = await monitor_open_positions(db)\n",
    "            from backend.core.rls_context import BackgroundCapability, trusted_background_session\n\n            async with trusted_background_session(BackgroundCapability.POSITION_MONITOR) as db:\n                closed = await monitor_open_positions(db)\n",
)

# Startup cross-tenant scans are explicit system capabilities. Owner bootstrap
# remains on users (which is intentionally not a tenant-owned table).
replace(
    "backend/main.py",
    "        from backend.core.database import AsyncSessionLocal\n        from backend.repositories.analysis import cleanup_stale_analyses\n\n        async with AsyncSessionLocal() as db:\n",
    "        from backend.core.rls_context import BackgroundCapability, trusted_background_session\n        from backend.repositories.analysis import cleanup_stale_analyses\n\n        async with trusted_background_session(BackgroundCapability.STARTUP_CLEANUP) as db:\n",
)
# Seed setting permissions.
replace(
    "backend/main.py",
    "    from backend.core.database import AsyncSessionLocal\n    from backend.models.page_permission import UserSettingPermission\n",
    "    from backend.core.rls_context import BackgroundCapability, trusted_background_session\n    from backend.models.page_permission import UserSettingPermission\n",
    1,
)
replace(
    "backend/main.py",
    "    async with AsyncSessionLocal() as db:\n        res = await db.execute(select(User))\n        users = res.scalars().all()\n        for u in users:\n            for s_key in SETTING_KEYS:\n",
    "    async with trusted_background_session(BackgroundCapability.STARTUP_SEED) as db:\n        res = await db.execute(select(User))\n        users = res.scalars().all()\n        for u in users:\n            for s_key in SETTING_KEYS:\n",
    1,
)
# Analysis-subpage permission migration is another startup seed operation.
segment_start = Path("backend/main.py").read_text(encoding="utf-8").index("async def _migrate_analysis_subpage_permissions")
main_text = Path("backend/main.py").read_text(encoding="utf-8")
segment_end = main_text.index("async def _load_cron_settings", segment_start)
segment = main_text[segment_start:segment_end]
segment = segment.replace(
    "    from backend.core.database import AsyncSessionLocal\n",
    "    from backend.core.rls_context import BackgroundCapability, trusted_background_session\n",
)
segment = segment.replace(
    "    async with AsyncSessionLocal() as db:\n",
    "    async with trusted_background_session(BackgroundCapability.STARTUP_SEED) as db:\n",
)
main_text = main_text[:segment_start] + segment + main_text[segment_end:]
# Cron bootstrap loads every user's AppSettings.
segment_start = main_text.index("async def _load_cron_settings")
segment_end = main_text.index("from slowapi", segment_start)
segment = main_text[segment_start:segment_end]
segment = segment.replace(
    "        from backend.core.database import AsyncSessionLocal\n",
    "        from backend.core.rls_context import BackgroundCapability, trusted_background_session\n",
)
segment = segment.replace(
    "        async with AsyncSessionLocal() as db:\n",
    "        async with trusted_background_session(BackgroundCapability.CRON_BOOTSTRAP) as db:\n",
)
main_text = main_text[:segment_start] + segment + main_text[segment_end:]
Path("backend/main.py").write_text(main_text, encoding="utf-8")

# Alert system: cross-tenant discovery is system-scoped, but every mutation and
# user settings delivery is re-opened in that alert owner's tenant context.
alert_path = Path("backend/services/alert_service.py")
alert = alert_path.read_text(encoding="utf-8")
alert = alert.replace(
    "from backend.core.database import AsyncSessionLocal\n",
    "from backend.core.database import AsyncSessionLocal\nfrom backend.core.rls_context import (\n    BackgroundCapability,\n    set_user_background_context,\n    trusted_background_session,\n)\n",
    1,
)
# Replace process_alert_outbox and check_price_alerts + recovery with context-safe versions.
start = alert.index("async def process_alert_outbox(")
end = alert.index("\n\nasync def check_price_alerts", start)
process_impl = r'''async def process_alert_outbox(limit: int = 50) -> None:
    """Claim globally, then deliver each item in its owner's tenant context."""
    async with trusted_background_session(BackgroundCapability.ALERT_OUTBOX) as db:
        stale_cutoff = datetime.now(UTC).timestamp() - 300
        rows = await db.execute(
            select(AlertOutbox)
            .where(
                or_(
                    AlertOutbox.status == "pending",
                    (AlertOutbox.status == "processing")
                    & (AlertOutbox.claimed_at < datetime.fromtimestamp(stale_cutoff, UTC)),
                )
            )
            .order_by(AlertOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        items = list(rows.scalars().all())
        claimed: list[tuple[int, int | None]] = []
        for item in items:
            item.status = "processing"
            item.claimed_at = datetime.now(UTC)
            item.attempts = (item.attempts or 0) + 1
            claimed.append((item.id, item.user_id))
        await db.commit()

    for item_id, user_id in claimed:
        async with AsyncSessionLocal() as delivery_db:
            if user_id is not None:
                await set_user_background_context(delivery_db, user_id)
            else:
                # Legacy/system-owned outbox rows are rare but still need an
                # explicit audited capability rather than an admin bypass.
                async with trusted_background_session(BackgroundCapability.ALERT_OUTBOX) as system_db:
                    await _deliver_outbox_item(system_db, item_id)
                continue
            await _deliver_outbox_item(delivery_db, item_id)


async def _deliver_outbox_item(db, item_id: int) -> None:
    row = await db.execute(select(AlertOutbox).where(AlertOutbox.id == item_id).with_for_update())
    item = row.scalar_one_or_none()
    if not item or item.status != "processing":
        return
    alert = await db.get(PriceAlert, item.alert_id)
    try:
        if not alert:
            item.status = "completed"
            item.completed_at = datetime.now(UTC)
        else:
            from backend.repositories.system_settings import get_system_settings

            settings = await get_system_settings(db)
            value = float(item.current_value) if item.current_value is not None else None
            await _deliver_alert_side_effects(db, alert, settings, value)
            item.status = "completed"
            item.completed_at = datetime.now(UTC)
            item.last_error = None
        await db.commit()
    except Exception as exc:
        await db.rollback()
        if item.user_id is not None:
            await set_user_background_context(db, item.user_id)
        failed = await db.get(AlertOutbox, item_id)
        if failed:
            failed.status = "pending" if failed.attempts < 10 else "failed"
            failed.last_error = str(exc)[:1000]
            await db.commit()
        _logger.exception("Alert outbox delivery failed id=%s", item_id)
'''
alert = alert[:start] + process_impl + alert[end:]
start = alert.index("async def check_price_alerts()")
end = alert.index("\n\nasync def _throttled_analyze", start)
check_impl = r'''async def _claim_alert_for_owner(alert_id: int, user_id: int | None, current_value: float | None) -> bool:
    if user_id is None:
        async with trusted_background_session(BackgroundCapability.ALERT_CHECKER) as db:
            alert = await db.get(PriceAlert, alert_id)
            return bool(alert and await _claim_alert(db, alert, current_value))
    async with AsyncSessionLocal() as db:
        await set_user_background_context(db, user_id)
        alert = await db.get(PriceAlert, alert_id)
        return bool(alert and await _claim_alert(db, alert, current_value))


async def check_price_alerts() -> None:
    # Cross-tenant discovery is the only system-scoped part of this job.
    async with trusted_background_session(BackgroundCapability.ALERT_CHECKER) as db:
        from backend.repositories.alerts import get_enabled_alerts

        alerts = list(await get_enabled_alerts(db))

    if not alerts:
        return
    price_alerts = [a for a in alerts if getattr(a, "alert_type", "price") not in _INDICATOR_ALERT_TYPES]
    indicator_alerts = [a for a in alerts if getattr(a, "alert_type", "price") in _INDICATOR_ALERT_TYPES]
    prices = await get_live_prices_batch([a.ticker for a in price_alerts]) if price_alerts else {}

    for alert in price_alerts:
        price = prices.get(alert.ticker)
        if price is None:
            continue
        hit = (alert.condition == "above" and price >= alert.target_price) or (
            alert.condition == "below" and price <= alert.target_price
        )
        if hit:
            _logger.info("Alert triggered: %s %s $%.2f (current: $%.2f)", alert.ticker, alert.condition, alert.target_price, price)
            await _claim_alert_for_owner(alert.id, alert.user_id, float(price))

    for alert in indicator_alerts:
        try:
            hit, detail = await _check_indicator_alert(alert)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Indicator alert check failed for %s: %s", alert.ticker, exc)
            continue
        if hit:
            _logger.info("Indicator alert triggered: %s %s (%s)", alert.ticker, alert.alert_type, detail)
            await _claim_alert_for_owner(alert.id, alert.user_id, None)

    await process_alert_outbox()
'''
alert = alert[:start] + check_impl + alert[end:]
# Auto-analysis tenant context.
alert = alert.replace(
    "        async with AsyncSessionLocal() as new_db:\n            result = await new_db.execute(select(User).where(User.id == user_id))\n",
    "        async with AsyncSessionLocal() as new_db:\n            if user_id is not None:\n                await set_user_background_context(new_db, user_id)\n            result = await new_db.execute(select(User).where(User.id == user_id))\n",
    1,
)
# Recovery scan only discovers globally; auto-analysis later scopes each owner.
start = alert.index("async def check_and_recover_lost_alerts()")
# Preserve function tail after its DB/gather implementation by replacing only first session opener.
recovery_segment = alert[start:]
recovery_segment = recovery_segment.replace(
    "    async with AsyncSessionLocal() as db:\n",
    "    async with trusted_background_session(BackgroundCapability.ALERT_RECOVERY) as db:\n",
    1,
)
alert = alert[:start] + recovery_segment
alert_path.write_text(alert, encoding="utf-8")

# Static unit tests for context API and module-level system allowlist.
Path("backend/tests/test_core/test_rls_context_model.py").write_text(
    '''from __future__ import annotations\n\nfrom pathlib import Path\n\nfrom backend.core.rls_context import BackgroundCapability, RLSContextKind\n\n\ndef test_context_kinds_are_explicit_and_non_overlapping():\n    assert {item.value for item in RLSContextKind} == {"tenant", "admin", "system", "refresh", "share"}\n\n\ndef test_background_capabilities_are_auditable_allowlist():\n    assert {item.value for item in BackgroundCapability} == {\n        "alert_checker", "alert_outbox", "performance_backfill", "position_monitor",\n        "maintenance_cleanup", "startup_seed", "startup_cleanup", "cron_bootstrap", "alert_recovery",\n    }\n\n\ndef test_trusted_background_session_is_not_used_by_api_or_repository_modules():\n    root = Path(__file__).resolve().parents[2]\n    forbidden = [root / "api", root / "repositories"]\n    offenders = []\n    for directory in forbidden:\n        for path in directory.rglob("*.py"):\n            if "trusted_background_session" in path.read_text(encoding="utf-8"):\n                offenders.append(str(path.relative_to(root)))\n    assert offenders == []\n''',
    encoding="utf-8",
)
