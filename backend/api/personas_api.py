"""CRUD endpoints for investor personas (built-in + user-created)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.persona import UserPersona
from backend.models.user import User
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


@router.get("")
async def list_all_personas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    builtins = _builtin_list()
    rows = (await db.execute(select(UserPersona).where(UserPersona.user_id == current_user.id))).scalars().all()
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


@router.post("", status_code=201)
async def create_persona(
    body: PersonaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _builtin_list()  # ensure _BUILTIN_KEYS is populated
    if body.key in _BUILTIN_KEYS:
        raise HTTPException(400, "Key conflicts with a built-in persona")
    existing = (
        await db.execute(
            select(UserPersona).where(
                UserPersona.user_id == current_user.id,
                UserPersona.key == body.key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "A persona with this key already exists")
    persona = UserPersona(
        user_id=current_user.id,
        key=body.key,
        label=body.label,
        description=body.description,
        instructions=body.instructions,
    )
    db.add(persona)
    await db.commit()
    return {
        "key": persona.key,
        "label": persona.label,
        "description": persona.description,
        "instructions": persona.instructions,
        "is_builtin": False,
    }


@router.put("/{key}")
async def update_persona(
    key: str,
    body: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _builtin_list()
    if key in _BUILTIN_KEYS:
        raise HTTPException(400, "Built-in personas cannot be edited")
    persona = (
        await db.execute(
            select(UserPersona).where(
                UserPersona.user_id == current_user.id,
                UserPersona.key == key,
            )
        )
    ).scalar_one_or_none()
    if not persona:
        raise HTTPException(404, "Persona not found")
    persona.label = body.label
    persona.description = body.description
    persona.instructions = body.instructions
    await db.commit()
    return {
        "key": persona.key,
        "label": persona.label,
        "description": persona.description,
        "instructions": persona.instructions,
        "is_builtin": False,
    }


@router.delete("/{key}", status_code=204)
async def delete_persona(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _builtin_list()
    if key in _BUILTIN_KEYS:
        raise HTTPException(400, "Built-in personas cannot be deleted")
    persona = (
        await db.execute(
            select(UserPersona).where(
                UserPersona.user_id == current_user.id,
                UserPersona.key == key,
            )
        )
    ).scalar_one_or_none()
    if not persona:
        raise HTTPException(404, "Persona not found")
    await db.delete(persona)
    await db.commit()
