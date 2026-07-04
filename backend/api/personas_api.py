"""CRUD endpoints for investor personas (built-in + user-created)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.services import persona_service
from backend.trading_agents.personas import list_personas

router = APIRouter(prefix="/api/personas", tags=["personas"])

_BUILTIN_KEYS: set[str] = set()


def _builtin_list() -> list[dict[str, Any]]:
    global _BUILTIN_KEYS
    result = []
    for p in list_personas():
        _BUILTIN_KEYS.add(p.key)
        result.append(
            {
                "key": p.key,
                "label": p.label,
                "description": p.description,
                "instructions": p.instructions,
                "is_builtin": True,
            }
        )
    return result


class PersonaCreate(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    instructions: str = Field(default="")


class PersonaUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    instructions: str = Field(default="")


@router.get("", response_model=list[dict[str, Any]])
async def list_all_personas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    builtins = _builtin_list()
    rows = await persona_service.get_user_personas(db, current_user.id)
    custom = [
        {
            "key": r.key,
            "label": r.label,
            "description": r.description,
            "instructions": r.instructions,
            "is_builtin": False,
        }
        for r in rows
    ]
    return builtins + custom


@router.post("", response_model=dict[str, Any], status_code=201, responses={400: {"description": "Key conflict or duplicate key"}})
async def create_persona(
    body: PersonaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _builtin_list()
    if body.key in _BUILTIN_KEYS:
        raise HTTPException(400, "Key conflicts with a built-in persona")
    if await persona_service.check_duplicate_persona(db, current_user.id, body.key):
        raise HTTPException(400, "A persona with this key already exists")
    persona = await persona_service.add_persona(
        db,
        current_user.id,
        body.key,
        body.label,
        body.description,
        body.instructions,
    )
    return {
        "key": persona.key,
        "label": persona.label,
        "description": persona.description,
        "instructions": persona.instructions,
        "is_builtin": False,
    }


@router.put(
    "/{key}",
    response_model=dict[str, Any],
    responses={400: {"description": "Cannot edit built-in persona"}, 404: {"description": "Persona not found"}},
)
async def update_persona(
    key: str,
    body: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _builtin_list()
    if key in _BUILTIN_KEYS:
        raise HTTPException(400, "Built-in personas cannot be edited")
    persona = await persona_service.get_persona(db, current_user.id, key)
    if not persona:
        raise HTTPException(404, "Persona not found")
    persona = await persona_service.edit_persona(
        db,
        persona,
        body.label,
        body.description,
        body.instructions,
    )
    return {
        "key": persona.key,
        "label": persona.label,
        "description": persona.description,
        "instructions": persona.instructions,
        "is_builtin": False,
    }


@router.delete(
    "/{key}",
    status_code=204,
    responses={400: {"description": "Cannot delete built-in persona"}, 404: {"description": "Persona not found"}},
)
async def delete_persona(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _builtin_list()
    if key in _BUILTIN_KEYS:
        raise HTTPException(400, "Built-in personas cannot be deleted")
    persona = await persona_service.get_persona(db, current_user.id, key)
    if not persona:
        raise HTTPException(404, "Persona not found")
    await persona_service.remove_persona(db, persona)
