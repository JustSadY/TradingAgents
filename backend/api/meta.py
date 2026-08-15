from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.catalog import build_meta
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.meta import MetaResponse
from backend.schemas.schema_contracts import MetaSchemasResponse, build_meta_schemas

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("", response_model=MetaResponse, response_model_exclude_unset=True)
async def get_meta(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_meta(db, current_user)


@router.get("/schemas", response_model=MetaSchemasResponse, response_model_exclude_none=True)
async def get_meta_schemas(_: User = Depends(get_current_user)) -> MetaSchemasResponse:
    """Return additive JSON Schema/UI contracts without user secret values."""
    return build_meta_schemas()
