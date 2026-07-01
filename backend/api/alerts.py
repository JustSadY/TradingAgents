import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.alert import AlertCreate, AlertRead, AlertUpdate

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
_logger = logging.getLogger(__name__)


@router.get("", response_model=list[AlertRead])
async def list_alerts_run(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.alerts import list_alerts as _repo_list

    return await _repo_list(db, user=current_user)


@router.post("", response_model=AlertRead)
async def create_alert_run(
    body: AlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.alerts import create_alert as _repo_create

    return await _repo_create(
        db,
        user_id=current_user.id,
        ticker=body.ticker,
        condition=body.condition,
        target_price=body.target_price,
        auto_analyze=body.auto_analyze,
        alert_type=body.alert_type,
    )


@router.patch("/{alert_id}", response_model=AlertRead, responses={404: {"description": "Alert not found"}})
async def update_alert(
    alert_id: int,
    body: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.alerts import get_alert_by_id as _repo_get

    alert = await _repo_get(db, alert_id, user=current_user)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(alert, field, value)
        if field == "enabled" and value is True:
            alert.triggered_at = None
    return alert


@router.delete("/{alert_id}", responses={404: {"description": "Alert not found"}})
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.alerts import get_alert_by_id as _repo_get

    alert = await _repo_get(db, alert_id, user=current_user)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    return {"deleted": True}
