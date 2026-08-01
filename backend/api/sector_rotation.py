from fastapi import APIRouter, Depends

from backend.api.deps import require_page
from backend.models.user import User
from backend.schemas.common import SectorRotationResponse
from backend.services.sector_rotation_service import get_sector_rotation

router = APIRouter(prefix="/api/market", tags=["sector"])

@router.get("/sector-rotation", response_model=SectorRotationResponse)
async def sector_rotation(current_user: User = Depends(require_page("sector-rotation"))):
    data = await get_sector_rotation()
    return {"sectors": data, "count": len(data)}
