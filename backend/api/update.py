import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import require_admin
from backend.models.user import User
from backend.services import update_service

router = APIRouter(prefix="/api/update", tags=["update"])

@router.get("/status", response_model=dict[str, Any])
async def update_status(_: User = Depends(require_admin)):
    return await asyncio.to_thread(update_service.get_status)

@router.post(
    "/apply",
    response_model=dict[str, Any],
    responses={409: {"description": "Update already in progress or not supported"}},
)
async def update_apply(_: User = Depends(require_admin)):
    try:
        return await asyncio.to_thread(update_service.request_update)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
