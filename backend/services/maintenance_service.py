"""Bounded retention jobs for transient AI/cache state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from backend.core.rls_context import BackgroundCapability, trusted_background_session
from backend.models.assistant import AssistantPendingAction
from backend.models.news_cache import AnalystReportCache, NewsAnalysisCache, NewsCache
from backend.models.shared_report import SharedReport


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
        }
        for name, statement in statements.items():
            result = await db.execute(statement)
            counts[name] = int(result.rowcount or 0)
        await db.commit()
    return counts
