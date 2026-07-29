import json
import logging

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User

_logger = logging.getLogger(__name__)


def encrypt_api_keys(keys: dict[str, str], fernet: Fernet) -> str:
    return fernet.encrypt(json.dumps(keys).encode()).decode()


def decrypt_api_keys(enc: str, fernet: Fernet) -> dict[str, str]:
    return json.loads(fernet.decrypt(enc.encode()).decode())


def get_user_api_key(user: User, provider: str, fernet: Fernet) -> str | None:
    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    # Local/server-managed providers do not consume a tenant credential. This
    # also prevents stale values written by pre-contract releases from being
    # carried into any LLM call path.
    if not provider_requires_api_key(provider):
        return None
    if not user.api_keys_enc:
        return None
    try:
        keys = decrypt_api_keys(user.api_keys_enc, fernet)
        return keys.get(provider.lower())
    except Exception as e:
        _logger.warning(
            "Failed to decrypt user %s API keys for provider %s: %s", getattr(user, "id", "unknown"), provider, e
        )
        return None


def resolve_user_api_key(user: User, provider: str) -> str | None:
    """Decrypt the user's stored key for ``provider`` using the app Fernet.

    Convenience wrapper over :func:`get_user_api_key` that sources the Fernet
    from config and never raises — the single home for the per-service
    "look up this user's provider key" helper that was copied across the
    daily-summary, report-chat and portfolio-assistant services.
    """
    from backend.core.config import get_settings

    try:
        return get_user_api_key(user, provider, get_settings().get_fernet())
    except Exception:
        return None


def set_user_api_key(user: User, provider: str, api_key: str, fernet: Fernet) -> None:
    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    if not provider_requires_api_key(provider):
        raise ValueError(f"Provider '{provider}' is server-managed and does not accept a tenant API key")
    existing: dict[str, str] = {}
    if user.api_keys_enc:
        try:
            existing = decrypt_api_keys(user.api_keys_enc, fernet)
        except Exception as e:
            _logger.warning(
                "Failed to decrypt existing API keys during set for user %s: %s (initializing empty)",
                getattr(user, "id", "unknown"),
                e,
            )
            existing = {}
    existing[provider.lower()] = api_key
    user.api_keys_enc = encrypt_api_keys(existing, fernet)


def delete_user_api_key(user: User, provider: str, fernet: Fernet) -> bool:
    if not user.api_keys_enc:
        return False
    try:
        existing = decrypt_api_keys(user.api_keys_enc, fernet)
    except Exception as e:
        _logger.warning("Failed to decrypt API keys during delete for user %s: %s", getattr(user, "id", "unknown"), e)
        return False
    if provider.lower() not in existing:
        return False
    del existing[provider.lower()]
    user.api_keys_enc = encrypt_api_keys(existing, fernet) if existing else None
    return True


def list_user_api_key_providers(user: User, fernet: Fernet) -> list[str]:
    if not user.api_keys_enc:
        return []
    try:
        keys = decrypt_api_keys(user.api_keys_enc, fernet)
        from backend.trading_agents.llm_clients.registry import provider_requires_api_key

        return [provider for provider in keys if provider_requires_api_key(provider)]
    except Exception as e:
        _logger.warning(
            "Failed to list API key providers for user %s due to decryption failure: %s",
            getattr(user, "id", "unknown"),
            e,
        )
        return []


async def delete_user_and_emit(db: AsyncSession, user: User) -> None:
    from backend.core.events import emit

    await db.delete(user)
    await db.commit()
    await emit("user_deleted", user_id=user.id)
