import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.shared_report import SharedReport
from backend.repositories import shared_report as repo


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def get_user_analysis(db: AsyncSession, analysis_id: int, user_id: int) -> AnalysisResult | None:
    return await repo.get_user_analysis_by_id(db, analysis_id, user_id)


async def get_or_create_shared_report(
    db: AsyncSession,
    analysis_id: int,
    user_id: int,
    current_time: datetime,
    *,
    rotate: bool = False,
) -> SharedReport:
    share = await repo.get_shared_report_by_analysis(
        db, analysis_id, user_id, for_update=True
    )
    if share is not None:
        active = share.revoked_at is None and _as_utc(share.expires_at) > _as_utc(current_time)
        if active and not rotate:
            return share
        share.token = uuid.uuid4().hex
        share.expires_at = current_time + timedelta(hours=48)
        share.revoked_at = None
        await db.commit()
        return share

    try:
        share = await repo.create_shared_report(db, user_id, analysis_id)
        await db.commit()
        return share
    except IntegrityError:
        await db.rollback()
        share = await repo.get_shared_report_by_analysis(
            db, analysis_id, user_id, for_update=True
        )
        if share is None:
            raise
        if rotate or share.revoked_at is not None or _as_utc(share.expires_at) <= _as_utc(current_time):
            share.token = uuid.uuid4().hex
            share.expires_at = current_time + timedelta(hours=48)
            share.revoked_at = None
            await db.commit()
        return share


async def revoke_shared_report(
    db: AsyncSession, analysis_id: int, user_id: int, current_time: datetime
) -> bool:
    share = await repo.get_shared_report_by_analysis(
        db, analysis_id, user_id, for_update=True
    )
    if share is None or share.revoked_at is not None:
        return False
    share.revoked_at = current_time
    await db.commit()
    return True


async def get_shared_report(db: AsyncSession, token: str) -> SharedReport | None:
    return await repo.get_shared_report_by_token(db, token)


async def get_analysis_for_share(db: AsyncSession, analysis_id: int) -> AnalysisResult | None:
    return await repo.get_analysis_by_id_public(db, analysis_id)
