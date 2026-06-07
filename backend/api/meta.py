from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.catalog import build_meta
from backend.core.database import get_db
from backend.models.user import User

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("")
async def get_meta(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_meta(db, current_user)
