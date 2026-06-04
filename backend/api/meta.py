from fastapi import APIRouter, Depends
from backend.core.catalog import build_meta
from backend.models.user import User
from backend.api.deps import get_current_user
router = APIRouter(prefix="/api/meta", tags=["meta"])
@router.get("")
async def get_meta(_: User = Depends(get_current_user)):
    return build_meta()
