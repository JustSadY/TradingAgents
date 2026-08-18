"""First-run owner registration.

The Server Owner used to be seeded at startup from ``ADMIN_USERNAME`` and
``ADMIN_PASSWORD_HASH`` in ``.env``. That put a credential in a file every
operator has to hand-edit before the app is usable, and it produced a
"development bootstrap password" printed into the logs whenever the hash was
missing.

The owner is now registered through the UI: while the ``users`` table is empty
the app serves a one-time setup screen, and the account it creates becomes the
single ``owner``. Once any user exists the endpoint is closed permanently, so
this is not a public sign-up route.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User

_logger = logging.getLogger(__name__)

# Stable key for the PostgreSQL advisory lock that serialises setup attempts.
_SETUP_LOCK_KEY = 728_314_559


class SetupAlreadyCompletedError(RuntimeError):
    """Raised when first-run setup is attempted on a populated installation."""


async def _user_count(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(User))).scalar_one())


async def owner_setup_required(db: AsyncSession) -> bool:
    """Whether the installation still has no accounts at all."""
    return await _user_count(db) == 0


async def create_first_owner(
    *,
    username: str,
    password: str,
    email: str | None = None,
    display_name: str | None = None,
) -> User:
    """Create the one and only Server Owner on an empty installation.

    Runs in a trusted background session because the new row's default page and
    setting permissions are RLS-protected and there is no authenticated caller
    yet. Two concurrent requests are serialised by a transaction-scoped advisory
    lock, so the second one sees a non-empty table and is rejected.
    """
    from backend.core.password_hashing import hash_password
    from backend.core.rls_context import BackgroundCapability, trusted_background_session
    from backend.repositories.users import create_user_with_permissions

    async with trusted_background_session(BackgroundCapability.STARTUP_SEED) as db:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SETUP_LOCK_KEY})

        if await _user_count(db) > 0:
            raise SetupAlreadyCompletedError("Initial setup has already been completed.")

        user = await create_user_with_permissions(
            db,
            username=username,
            hashed_password=hash_password(password),
            email=email,
            display_name=display_name,
            role="owner",
        )
        await db.commit()
        await db.refresh(user)
        _logger.info("Initial Server Owner account registered: %s", user.username)
        return user
