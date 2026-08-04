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
    except Exception as exc:
        _logger.debug("Failed to resolve user API key for provider %s: %s", provider, exc)
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
            _logger.error(
                "Refusing to overwrite undecryptable API keys for user %s: %s",
                getattr(user, "id", "unknown"),
                e,
            )
            raise RuntimeError(
                "Stored API credentials cannot be decrypted. Restore the configured encryption key before changing credentials."
            ) from e
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
    """Delete a tenant without leaving active tasks, alerts or portfolios behind.

    Existing installations may still have historical ``SET NULL`` foreign keys,
    so deletion is explicit rather than relying only on schema-level cascades.
    """
    from sqlalchemy import delete, select

    from backend.core import task_store
    from backend.core.events import emit
    from backend.models.alert import PriceAlert
    from backend.models.alert_outbox import AlertOutbox
    from backend.models.analysis import AnalysisResult
    from backend.models.portfolio import Portfolio
    from backend.models.portfolio_analysis import MultiTickerAnalysis
    from backend.models.webhook_delivery import WebhookDelivery

    active = await db.execute(
        select(AnalysisResult.task_id).where(
            AnalysisResult.user_id == user.id,
            AnalysisResult.status.in_(("queued", "running")),
            AnalysisResult.task_id.is_not(None),
        )
    )
    task_ids = [task_id for task_id in active.scalars().all() if task_id]
    for task_id in task_ids:
        await task_store.request_cancel(task_id)
        await task_store.publish_cancel(task_id)

    # Delete child/outbox rows first for databases created with older FK rules.
    await db.execute(delete(AlertOutbox).where(AlertOutbox.user_id == user.id))
    await db.execute(delete(PriceAlert).where(PriceAlert.user_id == user.id))
    await db.execute(delete(WebhookDelivery).where(WebhookDelivery.user_id == user.id))
    await db.execute(delete(MultiTickerAnalysis).where(MultiTickerAnalysis.user_id == user.id))
    await db.execute(delete(Portfolio).where(Portfolio.user_id == user.id))
    await db.execute(delete(AnalysisResult).where(AnalysisResult.user_id == user.id))
    await db.delete(user)
    await db.commit()

    for task_id in task_ids:
        await task_store.clear_meta(task_id, user.id)
        await task_store.clear_owner(task_id)
        await task_store.clear_cancel_request(task_id)
    await emit("user_deleted", user_id=user.id)
