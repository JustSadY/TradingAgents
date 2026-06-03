"""Price alert CRUD — trigger notifications when price thresholds are hit."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import get_db
from backend.api.deps import get_current_user
from backend.models.alert import PriceAlert
from backend.models.user import User
from backend.schemas.alert import AlertCreate, AlertUpdate, AlertRead

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
_logger = logging.getLogger(__name__)


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(PriceAlert).order_by(PriceAlert.created_at.desc())
    if not current_user.is_admin:
        q = q.where(PriceAlert.user_id == current_user.id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=AlertRead)
async def create_alert(
    body: AlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = PriceAlert(
        ticker=body.ticker.upper(),
        condition=body.condition,
        target_price=body.target_price,
        auto_analyze=body.auto_analyze,
        user_id=current_user.id,
    )
    db.add(alert)
    await db.flush()
    return alert


@router.patch("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: int,
    body: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(PriceAlert).where(PriceAlert.id == alert_id)
    if not current_user.is_admin:
        q = q.where(PriceAlert.user_id == current_user.id)
    result = await db.execute(q)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alarm bulunamadı")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(alert, field, value)
    return alert


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(PriceAlert).where(PriceAlert.id == alert_id)
    if not current_user.is_admin:
        q = q.where(PriceAlert.user_id == current_user.id)
    result = await db.execute(q)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alarm bulunamadı")
    await db.delete(alert)
    return {"deleted": True}
