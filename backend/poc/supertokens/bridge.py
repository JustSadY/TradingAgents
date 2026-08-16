"""Bind a SuperTokens identity to this application's tenant.

This is the part of a SuperTokens migration that is actually in doubt, so it is
the part the PoC makes real and testable.

Everything downstream of authentication in this codebase is keyed on the
integer ``users.id``. Revision ``7f8091a2b3c4`` enables row-level security on
every table that has a ``user_id`` column and gives each one the same policy::

    current_setting('app.is_admin', true) = 'true'
    OR user_id = NULLIF(current_setting('app.user_id', true), '')::bigint

So tenancy is enforced by PostgreSQL against a ``::bigint``, not by application
code that could be swapped out. SuperTokens identifies users by UUID. The two
are reconciled by SuperTokens' own user-ID mapping: the app's integer id is
registered as the *external* user id, so a verified session hands back
``"41"`` rather than a UUID.

That leaves exactly one seam, and it is this module. Note what it does *not*
receive: a token, a cookie, or anything else requiring verification. The SDK
verifies the session; this takes the already-verified external id and answers
the only question the rest of the app cares about — which row in ``users``, and
therefore which RLS context. Keeping the seam this narrow is why the logic can
be tested without the SuperTokens core running, and why swapping providers
again later would touch one function.

Two properties are load-bearing and both are asserted in the tests:

* It fails closed. A mapping that is absent, non-numeric, or points at a
  deleted or deactivated user must raise, never fall through to a request that
  runs with no tenant context — under RLS, an unset ``app.user_id`` is not
  "deny", it is a policy comparison against NULL on every table at once.
* Admin still comes from ``users.role``. SuperTokens has a roles recipe, but
  ``app.is_admin`` is what bypasses every tenant policy in the database, so the
  authority for it stays in the table this application owns.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.rls_context import set_request_admin_context, set_request_tenant_context
from backend.models.user import User


class IdentityMappingError(Exception):
    """A verified session that this application cannot bind to a tenant.

    Separate from ``HTTPException`` so the mapping rules can be tested without
    a request, and so a caller cannot accidentally turn it into a 200.
    """


def parse_external_user_id(external_user_id: str | None) -> int:
    """Read the app's integer ``users.id`` out of a SuperTokens external id.

    SuperTokens stores external ids as opaque strings. The RLS policy casts to
    ``bigint``, so anything that is not an integer would fail deep inside a
    query — as a 500 on an arbitrary endpoint rather than an authentication
    failure. Reject it here instead.
    """
    if external_user_id is None:
        raise IdentityMappingError("session carried no external user id")

    candidate = external_user_id.strip()
    if not candidate:
        raise IdentityMappingError("session carried an empty external user id")

    try:
        user_id = int(candidate)
    except ValueError:
        raise IdentityMappingError(
            f"external user id {external_user_id!r} is not an integer, so it cannot be a users.id. "
            "The SuperTokens user was probably created without createUserIdMapping."
        ) from None

    if user_id <= 0:
        raise IdentityMappingError(f"external user id {external_user_id!r} is not a positive users.id")
    return user_id


async def tenant_from_supertokens_session(db: AsyncSession, external_user_id: str | None) -> User:
    """Resolve a verified SuperTokens session to a user and its RLS context.

    The context established here is byte-for-byte the one
    ``api/deps.get_user_from_access_token`` establishes today, which is the
    point: every repository, service and policy below this line is untouched by
    the change of identity provider.
    """
    user_id = parse_external_user_id(external_user_id)

    # Deliberately read before any context is applied. `users` is not itself
    # tenant-scoped, and applying a context for a user that turns out not to
    # exist would leave the session carrying a tenant that cannot be verified.
    row = await db.execute(select(User).where(User.id == user_id))
    user = row.scalar_one_or_none()

    if user is None:
        raise IdentityMappingError(
            f"external user id {user_id} has no row in users. The SuperTokens user outlived "
            "the application user — this is the two-store consistency problem, showing up."
        )
    if not user.is_active:
        raise IdentityMappingError(f"user {user_id} is deactivated")

    # Admin authority stays with the application's own table. SuperTokens knows
    # who signed in; it does not know who may bypass every tenant policy.
    if user.is_admin:
        await set_request_admin_context(db, user.id)
    else:
        await set_request_tenant_context(db, user.id)
    return user


async def current_user_from_session(db: AsyncSession, external_user_id: str | None) -> User:
    """``tenant_from_supertokens_session`` as an HTTP boundary.

    Every mapping failure is a 401: from the caller's side an unmappable
    session is an unusable one, and the distinctions between them are operator
    detail that belongs in logs, not in a response body.
    """
    try:
        return await tenant_from_supertokens_session(db, external_user_id)
    except IdentityMappingError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
