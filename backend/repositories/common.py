"""Shared query helpers used across repositories and routers."""

from __future__ import annotations


def scope_to_user(query, model, user):
    """Restrict ``query`` to rows owned by ``user`` unless the user is an admin.

    Centralises the ``if not current_user.is_admin: q = q.where(Model.user_id ==
    current_user.id)`` pattern that was repeated across the alerts, analysis,
    preset and portfolio routers (an easy place to introduce an IDOR by
    forgetting the filter).
    """
    if user is not None and not getattr(user, "is_admin", False):
        return query.where(model.user_id == user.id)
    return query


async def get_settings_by_scope_generic(db, model, scope: str, user_id: int | None = None):
    from sqlalchemy import select

    stmt = select(model).where(model.scope == scope)
    if scope == "user":
        stmt = stmt.where(model.user_id == user_id)
    else:
        stmt = stmt.where(model.user_id.is_(None))
    res = await db.execute(stmt)
    return res.scalars().all()
