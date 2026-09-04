import json
import logging

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User

_logger = logging.getLogger(__name__)


class UserNotFoundError(LookupError):
    pass


class UsernameTakenError(ValueError):
    pass


class EmailTakenError(ValueError):
    pass


class UserPolicyError(PermissionError):
    pass


class CannotDeleteSelfError(ValueError):
    pass


class UnknownPermissionKeysError(ValueError):
    pass


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
    """Decrypt the user's stored key for ``provider`` using the app Fernet."""
    from backend.core.config import get_settings

    try:
        return get_user_api_key(user, provider, get_settings().get_fernet())
    except Exception as exc:
        _logger.debug("Failed to resolve user API key for provider %s: %s", provider, exc)
        return None


def set_user_api_key(user: User, provider: str, api_key: str, fernet: Fernet) -> bool:
    """Set one tenant-managed provider key and report whether it changed."""
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

    provider_key = provider.lower()
    if existing.get(provider_key) == api_key:
        return False

    existing[provider_key] = api_key
    user.api_keys_enc = encrypt_api_keys(existing, fernet)
    return True


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


def _app_fernet() -> Fernet:
    from backend.core.config import get_settings

    return get_settings().get_fernet()


def _invalidate_memory_cache_for_provider(user: User, provider: str) -> None:
    """Invalidate only credentials that can change the Mem0 store client."""
    if provider.strip().lower() != "openai":
        return
    from backend.services.memory_service import invalidate_user_memory_store_cache

    invalidate_user_memory_store_cache(user.id)


def list_stored_api_key_providers(user: User) -> list[str]:
    """List tenant-managed provider keys using the application encryption key."""
    return list_user_api_key_providers(user, _app_fernet())


async def save_stored_api_key(db: AsyncSession, user: User, provider: str, api_key: str) -> None:
    """Encrypt and persist a tenant-managed provider key only when it changes."""
    changed = set_user_api_key(user, provider, api_key, _app_fernet())
    if not changed:
        return
    await db.flush()
    _invalidate_memory_cache_for_provider(user, provider)


async def remove_stored_api_key(db: AsyncSession, user: User, provider: str) -> bool:
    """Delete a tenant-managed provider key and flush only when it changed."""
    deleted = delete_user_api_key(user, provider, _app_fernet())
    if deleted:
        await db.flush()
        _invalidate_memory_cache_for_provider(user, provider)
    return deleted


async def get_user_or_raise(db: AsyncSession, user_id: int) -> User:
    from backend.repositories.users import get_user_by_id

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise UserNotFoundError("User not found")
    return user


async def list_managed_users(db: AsyncSession) -> list[User]:
    from backend.repositories.users import list_users

    return await list_users(db)


async def get_effective_page_permissions(db: AsyncSession, user: User) -> list[str]:
    from backend.core.constants import PAGE_KEYS
    from backend.repositories.permissions import list_allowed_page_keys

    if user.is_admin:
        return [*PAGE_KEYS, "admin"]
    allowed = sorted(await list_allowed_page_keys(db, user.id))
    if "settings" not in allowed:
        allowed.append("settings")
    return allowed


async def get_effective_setting_permissions(db: AsyncSession, user: User) -> list[str]:
    from backend.core.constants import SETTING_KEYS
    from backend.repositories.permissions import list_allowed_setting_sections

    if user.is_admin:
        return list(SETTING_KEYS)
    return sorted(await list_allowed_setting_sections(db, user.id))


async def get_managed_page_permissions(db: AsyncSession, user_id: int) -> dict[str, bool]:
    from backend.models.page_permission import ALL_PAGE_KEYS
    from backend.repositories.permissions import get_user_page_permissions_map

    await get_user_or_raise(db, user_id)
    permissions = await get_user_page_permissions_map(db, user_id)
    return {key: permissions.get(key, False) for key in ALL_PAGE_KEYS}


async def set_managed_page_permissions(db: AsyncSession, user_id: int, permissions: dict[str, bool]) -> None:
    from backend.models.page_permission import ALL_PAGE_KEYS
    from backend.repositories.permissions import ensure_user_page_permission_row, list_user_page_permission_rows

    await get_user_or_raise(db, user_id)
    unknown = sorted(set(permissions) - set(ALL_PAGE_KEYS))
    if unknown:
        raise UnknownPermissionKeysError(f"Unknown page permission keys: {', '.join(unknown)}")

    rows = {row.page_key: row for row in await list_user_page_permission_rows(db, user_id)}
    dirty = False
    for page_key, allowed in permissions.items():
        row = rows.get(page_key)
        if row is None and allowed is False:
            continue
        if row is not None and row.allowed == allowed:
            continue
        row = ensure_user_page_permission_row(db, row=row, user_id=user_id, page_key=page_key)
        row.allowed = allowed
        rows[page_key] = row
        dirty = True
    if dirty:
        await db.flush()


async def get_managed_setting_permissions(db: AsyncSession, user_id: int) -> dict[str, bool]:
    from backend.core.constants import SETTING_KEYS
    from backend.repositories.permissions import get_user_setting_permissions_map

    await get_user_or_raise(db, user_id)
    permissions = await get_user_setting_permissions_map(db, user_id)
    return {key: permissions.get(key, False) for key in SETTING_KEYS}


async def set_managed_setting_permissions(db: AsyncSession, user_id: int, permissions: dict[str, bool]) -> None:
    from backend.core.constants import SETTING_KEYS
    from backend.repositories.permissions import ensure_user_setting_permission_row, list_user_setting_permission_rows

    await get_user_or_raise(db, user_id)
    unknown = sorted(set(permissions) - set(SETTING_KEYS))
    if unknown:
        raise UnknownPermissionKeysError(f"Unknown setting permission keys: {', '.join(unknown)}")

    rows = {row.setting_key: row for row in await list_user_setting_permission_rows(db, user_id)}
    dirty = False
    for setting_key, allowed in permissions.items():
        row = rows.get(setting_key)
        if row is None and allowed is False:
            continue
        if row is not None and row.allowed == allowed:
            continue
        row = ensure_user_setting_permission_row(db, row=row, user_id=user_id, setting_key=setting_key)
        row.allowed = allowed
        rows[setting_key] = row
        dirty = True
    if dirty:
        await db.flush()


async def update_profile(
    db: AsyncSession,
    user: User,
    *,
    email: str | None,
    display_name: str | None,
    password: str | None,
) -> User:
    """Apply self-service profile policy and persist the profile update."""
    from backend.core.password_hashing import hash_password
    from backend.repositories.users import email_exists, update_user_profile

    if email is not None and await email_exists(db, email, exclude_user_id=user.id):
        raise EmailTakenError("Email already in use")

    hashed_password = None
    if password:
        hashed_password = hash_password(password)
        user.token_version = (getattr(user, "token_version", 0) or 0) + 1

    return await update_user_profile(
        db,
        user,
        email=email,
        display_name=display_name,
        hashed_password=hashed_password,
    )


async def create_managed_user(
    db: AsyncSession,
    actor: User,
    *,
    username: str,
    password: str,
    email: str | None,
    display_name: str | None,
    role: str,
) -> User:
    """Create a user after enforcing uniqueness and owner/admin role policy."""
    from backend.core.password_hashing import hash_password
    from backend.repositories.users import create_user_with_permissions, email_exists, username_exists

    if await username_exists(db, username):
        raise UsernameTakenError("Username already taken")
    if email and await email_exists(db, email):
        raise EmailTakenError("Email already in use")
    if role == "owner":
        raise UserPolicyError("Assigning the Server Owner role is prohibited.")
    if role != "user" and actor.role != "owner":
        raise UserPolicyError("Only the Server Owner can create administrator accounts.")

    return await create_user_with_permissions(
        db,
        username=username,
        hashed_password=hash_password(password),
        email=email,
        display_name=display_name,
        role=role,
    )


async def update_managed_user(
    db: AsyncSession,
    actor: User,
    user_id: int,
    *,
    role: str | None,
    is_active: bool | None,
    email: str | None,
    display_name: str | None,
) -> User:
    """Apply administrator user-mutation policy and persist the update."""
    from backend.repositories.users import email_exists, update_user_admin

    user = await get_user_or_raise(db, user_id)

    if user.role == "owner":
        if role is not None and role != "owner":
            raise UserPolicyError("The Server Owner role is immutable.")
        if is_active is not None and is_active != user.is_active:
            raise UserPolicyError("The Server Owner account cannot be deactivated.")

    if role is not None:
        if role == "owner" and user.role != "owner":
            raise UserPolicyError("Assigning Server Owner is prohibited.")
        if actor.role != "owner":
            raise UserPolicyError("Only Server Owner can promote/demote admins.")

    if email is not None and await email_exists(db, email, exclude_user_id=user.id):
        raise EmailTakenError("Email already in use")

    return await update_user_admin(
        db,
        user,
        role=role,
        is_active=is_active,
        email=email,
        display_name=display_name,
    )


async def delete_managed_user(db: AsyncSession, actor: User, user_id: int) -> None:
    """Delete a user after enforcing self-delete and owner-account policy."""
    if user_id == actor.id:
        raise CannotDeleteSelfError("Cannot delete yourself")

    user = await get_user_or_raise(db, user_id)
    if user.role == "owner":
        raise UserPolicyError("The Server Owner account cannot be deleted.")

    await delete_user_and_emit(db, user)


async def delete_user_and_emit(db: AsyncSession, user: User) -> None:
    """Delete a tenant and clean up active task/memory process state."""
    from backend.core import task_store
    from backend.core.events import emit
    from backend.repositories.user_cleanup import delete_user_record, list_active_analysis_task_ids
    from backend.services.memory_service import invalidate_user_memory_store_cache

    task_ids = await list_active_analysis_task_ids(db, user.id)
    for task_id in task_ids:
        await task_store.request_cancel(task_id)
        await task_store.publish_cancel(task_id)

    await delete_user_record(db, user)
    invalidate_user_memory_store_cache(user.id)

    for task_id in task_ids:
        await task_store.clear_meta(task_id, user.id)
        await task_store.clear_owner(task_id)
        await task_store.clear_cancel_request(task_id)
    await emit("user_deleted", user_id=user.id)
