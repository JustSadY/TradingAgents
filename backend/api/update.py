import asyncio

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_current_user
from backend.models.user import User
from backend.services import update_service

router = APIRouter(prefix="/api/update", tags=["update"])


@router.get("/status")
async def update_status(_: User = Depends(get_current_user)):
    return await asyncio.to_thread(update_service.get_status)


@router.post("/apply")
async def update_apply(_: User = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(update_service.request_update)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
