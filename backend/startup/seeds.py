import logging

from sqlalchemy import select

from backend.core.config import get_settings
from backend.core.database import AsyncSessionLocal
from backend.core.password_hashing import hash_password, is_supported_password_hash
from backend.models.user import User

_logger = logging.getLogger(__name__)


async def seed_admin_user() -> None:
    settings = get_settings()
    if not settings.ADMIN_USERNAME:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        existing = result.scalar_one_or_none()
        if existing is None:
            raw_hash = settings.ADMIN_PASSWORD_HASH
            if raw_hash and not is_supported_password_hash(raw_hash):
                if settings.ENVIRONMENT.strip().lower() == "production":
                    raise RuntimeError("ADMIN_PASSWORD_HASH is not a valid Argon2 hash")
                _logger.warning(
                    "ADMIN_PASSWORD_HASH in .env is not a valid Argon2 hash; using development fallback."
                )
                raw_hash = None

            if raw_hash:
                hashed = raw_hash
                bootstrap_password = None
            else:
                import secrets

                bootstrap_password = secrets.token_urlsafe(18)
                hashed = hash_password(bootstrap_password)

            db.add(User(username=settings.ADMIN_USERNAME, hashed_password=hashed, role="owner"))
            await db.commit()
            if bootstrap_password:
                _logger.warning(
                    "Owner user %s created with a one-time development bootstrap password: %s. "
                    "Change it immediately.",
                    settings.ADMIN_USERNAME,
                    bootstrap_password,
                )
            else:
                _logger.info("Owner user created: %s", settings.ADMIN_USERNAME)
        elif existing.role != "owner":
            existing.role = "owner"
            await db.commit()
            _logger.info("Owner role set for existing user: %s", settings.ADMIN_USERNAME)
