from fastapi import APIRouter, Depends

from backend.api.deps import get_current_user
from backend.models.user import User
from backend.schemas.common import SectorRotationResponse
from backend.services.sector_rotation_service import get_sector_rotation

router = APIRouter(prefix="/api/market", tags=["sector"])


@router.get("/sector-rotation", response_model=SectorRotationResponse)
async def sector_rotation(current_user: User = Depends(get_current_user)):
    data = await get_sector_rotation()
    return {"sectors": data, "count": len(data)}
