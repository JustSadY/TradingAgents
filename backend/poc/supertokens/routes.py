"""The FastAPI adapter: a verified SuperTokens session becomes a tenant.

Thin on purpose. Everything here is SDK plumbing; the decisions live in
``bridge.py``. Compare this to ``api/deps.get_current_user`` — the shape is the
same, and so is what it hands the rest of the application. That is the point:
below this line nothing changes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.models.user import User
from backend.poc.supertokens.bridge import current_user_from_session

router = APIRouter(prefix="/api/poc/supertokens", tags=["poc"])


async def get_current_user_st(
    db: Annotated[AsyncSession, Depends(get_db)],
    session=Depends(lambda: _verify_session()),  # noqa: B008 - see _verify_session
) -> User:
    """The SuperTokens equivalent of ``api.deps.get_current_user``.

    ``get_user_id()`` returns the *external* id once the mapping exists, which
    is why the bridge can treat it as a ``users.id`` — and why it checks rather
    than trusts.
    """
    return await current_user_from_session(db, session.get_user_id())


def _verify_session():
    """Import the SDK lazily so this module stays importable without it.

    The PoC's dependency group is optional; a stray import of this file during
    collection should not break a suite that has no reason to touch it.
    """
    from supertokens_python.recipe.session.framework.fastapi import verify_session

    return verify_session()


@router.get("/whoami")
async def whoami(user: Annotated[User, Depends(get_current_user_st)]) -> dict[str, object]:
    """Proof of life: a SuperTokens session resolved to an application user."""
    return {"id": user.id, "username": user.username, "role": user.role, "is_admin": user.is_admin}


@router.get("/my-presets")
async def my_presets(
    user: Annotated[User, Depends(get_current_user_st)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """A tenant-scoped read with no tenant filter in the query.

    There is no ``WHERE user_id = ...`` here, and that is deliberate: the
    isolation is the row-level security policy the bridge armed, not a clause
    an endpoint could forget. ``test_supertokens_rls.py`` is the same
    assertion, made against a real PostgreSQL.
    """
    from sqlalchemy import text

    rows = await db.execute(text("SELECT id, name FROM config_presets ORDER BY name"))
    return {"user_id": user.id, "presets": [{"id": i, "name": n} for i, n in rows.all()]}
