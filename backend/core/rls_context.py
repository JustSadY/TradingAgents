"""Explicit PostgreSQL RLS execution contexts.

Normal request code receives a tenant/admin context through auth dependencies.
Pre-auth refresh and public-share flows receive narrowly scoped contexts tied to
one refresh-session id or one share token. Cross-tenant background scans are
only available through ``trusted_background_session`` and an audited capability
enum; repositories and ordinary request handlers never receive a generic
"system" setter.

PostgreSQL settings are always transaction-local ``set_config(..., true)``.
The selected logical context is kept only in ``AsyncSession.info`` and a
SQLAlchemy transaction hook reapplies it whenever that same ORM session opens a
new transaction after a repository-level commit. Pool connections therefore
never retain tenant/admin/system settings after transaction end.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


class RLSContextKind(StrEnum):
    TENANT = "tenant"
    ADMIN = "admin"
    SYSTEM = "system"
    REFRESH = "refresh"
    SHARE = "share"


class BackgroundCapability(StrEnum):
    ALERT_CHECKER = "alert_checker"
    ALERT_OUTBOX = "alert_outbox"
    PERFORMANCE_BACKFILL = "performance_backfill"
    POSITION_MONITOR = "position_monitor"
    MAINTENANCE_CLEANUP = "maintenance_cleanup"
    STARTUP_SEED = "startup_seed"
    STARTUP_CLEANUP = "startup_cleanup"
    CRON_BOOTSTRAP = "cron_bootstrap"
    ALERT_RECOVERY = "alert_recovery"
    SYSTEM_LOGGING = "system_logging"


_CONTEXT_KEYS = (
    "app.context_kind",
    "app.user_id",
    "app.is_admin",
    "app.refresh_session_id",
    "app.public_share_token",
    "app.share_analysis_id",
    "app.background_capability",
)
_CONTEXT_INFO_KEY = "tradingagents.rls_context"


def _is_postgres(db: AsyncSession) -> bool:
    """Return whether *db* is backed by PostgreSQL.

    A few API unit tests deliberately pass lightweight stand-ins instead of a
    SQLAlchemy session. Treat those as non-PostgreSQL rather than making the
    transport contract depend on test-only ``get_bind`` methods.
    """

    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return False
    bind = get_bind()
    return bool(bind is not None and bind.dialect.name == "postgresql")


def _apply_values_sync(connection: Any, values: dict[str, str]) -> None:
    if connection.dialect.name != "postgresql":
        return
    for key in _CONTEXT_KEYS:
        connection.execute(
            text("SELECT set_config(:key, :value, true)"),
            {"key": key, "value": values[key]},
        )


@event.listens_for(Session, "after_begin")
def _reapply_rls_context_after_begin(session: Session, _transaction: Any, connection: Any) -> None:
    """Reapply the logical RLS context to each physical DB transaction.

    ``SET LOCAL`` is deliberately cleared by PostgreSQL on commit/rollback.
    Repositories are allowed to commit internally, so the next transaction in
    the same ORM session must receive the same logical request/background
    context before its first statement. The context itself is never stored on
    the pooled connection.
    """

    values = session.info.get(_CONTEXT_INFO_KEY)
    if isinstance(values, dict):
        _apply_values_sync(connection, values)


async def _apply_context(
    db: AsyncSession,
    *,
    kind: RLSContextKind,
    user_id: int | None = None,
    is_admin: bool = False,
    refresh_session_id: str | None = None,
    public_share_token: str | None = None,
    share_analysis_id: int | None = None,
    background_capability: BackgroundCapability | None = None,
) -> None:
    if not _is_postgres(db):
        return

    values = {
        "app.context_kind": kind.value,
        "app.user_id": "" if user_id is None else str(int(user_id)),
        "app.is_admin": "true" if is_admin else "false",
        "app.refresh_session_id": refresh_session_id or "",
        "app.public_share_token": public_share_token or "",
        "app.share_analysis_id": "" if share_analysis_id is None else str(int(share_analysis_id)),
        "app.background_capability": background_capability.value if background_capability else "",
    }
    # Session.info is ORM-session-local, not connection/pool-local. Future
    # transactions reapply these values through the after_begin hook above.
    db.info[_CONTEXT_INFO_KEY] = values

    # If the caller already opened a transaction (for example login first read
    # the unprotected users table), after_begin has already fired. Update that
    # current transaction immediately and clear every selector from the previous
    # context at the same time.
    if db.in_transaction():
        for key in _CONTEXT_KEYS:
            await db.execute(
                text("SELECT set_config(:key, :value, true)"),
                {"key": key, "value": values[key]},
            )


async def set_request_tenant_context(db: AsyncSession, user_id: int) -> None:
    await _apply_context(db, kind=RLSContextKind.TENANT, user_id=user_id)


async def set_request_admin_context(db: AsyncSession, user_id: int) -> None:
    await _apply_context(db, kind=RLSContextKind.ADMIN, user_id=user_id, is_admin=True)


async def set_user_background_context(db: AsyncSession, user_id: int) -> None:
    """Tenant-scope a user-owned worker/cron operation.

    This intentionally does *not* grant system visibility. A queued job or
    watchlist scan may touch only its owner even though it runs off-request.
    """

    await _apply_context(db, kind=RLSContextKind.TENANT, user_id=user_id)


async def set_refresh_access_context(
    db: AsyncSession,
    *,
    session_id: str | None = None,
    user_id: int | None = None,
) -> None:
    if not session_id and user_id is None:
        raise ValueError("refresh context requires session_id or user_id")
    await _apply_context(
        db,
        kind=RLSContextKind.REFRESH,
        user_id=user_id,
        refresh_session_id=session_id,
    )


async def set_public_share_context(
    db: AsyncSession,
    *,
    token: str,
    analysis_id: int | None = None,
) -> None:
    if not token:
        raise ValueError("public share context requires token")
    await _apply_context(
        db,
        kind=RLSContextKind.SHARE,
        public_share_token=token,
        share_analysis_id=analysis_id,
    )


async def _set_trusted_system_context(db: AsyncSession, capability: BackgroundCapability) -> None:
    await _apply_context(
        db,
        kind=RLSContextKind.SYSTEM,
        background_capability=capability,
    )


@asynccontextmanager
async def trusted_background_session(capability: BackgroundCapability):
    """Open one audited cross-tenant background ORM-session scope.

    The system capability remains active only for transactions opened by this
    dedicated session. Commits may occur inside the service; each subsequent
    transaction is re-scoped by the session hook. Exiting the context closes the
    session and discards its logical capability while PostgreSQL has already
    cleared every transaction-local setting.
    """

    from backend.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _set_trusted_system_context(db, capability)
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
