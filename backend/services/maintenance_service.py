"""Bounded retention jobs for transient AI/cache state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_

from backend.core.config import get_settings
from backend.core.rls_context import BackgroundCapability, trusted_background_session
from backend.models.assistant import AssistantPendingAction
from backend.models.log import SystemLog
from backend.models.news_cache import AnalystReportCache, NewsAnalysisCache, NewsCache
from backend.models.refresh_session import RefreshSession
from backend.models.shared_report import SharedReport

#: Expired and revoked refresh sessions are kept this long before deletion.
#: Rotation already refuses both, so the delay buys an audit trail rather than
#: any authentication behaviour.
_REFRESH_SESSION_GRACE = timedelta(days=1)


async def cleanup_transient_data() -> dict[str, int]:
    now = datetime.now(UTC)
    counts: dict[str, int] = {}
    async with trusted_background_session(BackgroundCapability.MAINTENANCE_CLEANUP) as db:
        statements = {
            "analyst_report_cache": delete(AnalystReportCache).where(
                AnalystReportCache.created_at < now - timedelta(days=30)
            ),
            "news_analysis_cache": delete(NewsAnalysisCache).where(
                NewsAnalysisCache.created_at < now - timedelta(days=30)
            ),
            "news_cache": delete(NewsCache).where(NewsCache.updated_at < now - timedelta(days=7)),
            "assistant_pending_actions": delete(AssistantPendingAction).where(
                (AssistantPendingAction.expires_at < now)
                | (AssistantPendingAction.consumed_at < now - timedelta(days=1))
            ),
            "shared_reports": delete(SharedReport).where(
                (SharedReport.expires_at < now - timedelta(days=7))
                | (SharedReport.revoked_at < now - timedelta(days=7))
            ),
            # A refresh session is dead once it expires or is revoked: rotation
            # rejects both. Nothing deleted them, so every sign-in left a row
            # behind for good.
            "refresh_sessions": delete(RefreshSession).where(
                or_(
                    RefreshSession.expires_at < now - _REFRESH_SESSION_GRACE,
                    RefreshSession.revoked_at < now - _REFRESH_SESSION_GRACE,
                )
            ),
        }

        # 0 means "keep everything", so the delete is skipped rather than
        # issued with a cutoff in the future.
        retention_days = int(get_settings().SYSTEM_LOG_RETENTION_DAYS or 0)
        if retention_days > 0:
            statements["system_logs"] = delete(SystemLog).where(
                SystemLog.created_at < now - timedelta(days=retention_days)
            )
        for name, statement in statements.items():
            result = await db.execute(statement)
            counts[name] = int(result.rowcount or 0)
        await db.commit()
    return counts
