import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_page
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.alert import AlertCreate, AlertRead, AlertUpdate
from backend.schemas.common import DeleteResponse

router = APIRouter(prefix="/api/alerts", tags=["alerts"])
_logger = logging.getLogger(__name__)


@router.get("", response_model=list[AlertRead])
async def list_alerts_run(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("alerts")),
):
    from backend.repositories.alerts import list_alerts as _repo_list

    return await _repo_list(db, user=current_user)


@router.post("", response_model=AlertRead, responses={409: {"description": "Alert limit reached"}})
async def create_alert_run(
    body: AlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("alerts")),
):
    from backend.services.alert_creation_service import AlertGuardrailViolation, create_alert_with_guardrails

    try:
        alert = await create_alert_with_guardrails(
            db,
            user_id=current_user.id,
            ticker=body.ticker,
            condition=body.condition,
            target_price=body.target_price,
            auto_analyze=body.auto_analyze,
            alert_type=body.alert_type,
        )
    except AlertGuardrailViolation as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    assert alert is not None
    return alert


@router.patch(
    "/{alert_id}",
    response_model=AlertRead,
    responses={404: {"description": "Alert not found"}, 409: {"description": "Alert limit reached"}},
)
async def update_alert(
    alert_id: int,
    body: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("alerts")),
):
    from backend.services.alert_creation_service import AlertGuardrailViolation
    from backend.services.alert_management_service import AlertUpdateValidationError, update_user_alert

    try:
        alert = await update_user_alert(
            db,
            user=current_user,
            alert_id=alert_id,
            changes=body.model_dump(exclude_none=True),
        )
    except AlertGuardrailViolation as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except AlertUpdateValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc

    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.delete("/{alert_id}", response_model=DeleteResponse, responses={404: {"description": "Alert not found"}})
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("alerts")),
):
    from backend.services.alert_management_service import delete_user_alert

    deleted = await delete_user_alert(db, user=current_user, alert_id=alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"deleted": True}
