import json
from cryptography.fernet import Fernet
from backend.models.user import User
def encrypt_api_keys(keys: dict[str, str], fernet: Fernet) -> str:
    return fernet.encrypt(json.dumps(keys).encode()).decode()
def decrypt_api_keys(enc: str, fernet: Fernet) -> dict[str, str]:
    return json.loads(fernet.decrypt(enc.encode()).decode())
def get_user_api_key(user: User, provider: str, fernet: Fernet) -> str | None:
    if not user.api_keys_enc:
        return None
    try:
        keys = decrypt_api_keys(user.api_keys_enc, fernet)
        return keys.get(provider.lower())
    except Exception:
        return None
def set_user_api_key(user: User, provider: str, api_key: str, fernet: Fernet) -> None:
    existing: dict[str, str] = {}
    if user.api_keys_enc:
        try:
            existing = decrypt_api_keys(user.api_keys_enc, fernet)
        except Exception:
            existing = {}
    existing[provider.lower()] = api_key
    user.api_keys_enc = encrypt_api_keys(existing, fernet)
def delete_user_api_key(user: User, provider: str, fernet: Fernet) -> bool:
    if not user.api_keys_enc:
        return False
    try:
        existing = decrypt_api_keys(user.api_keys_enc, fernet)
    except Exception:
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
        return list(keys.keys())
    except Exception:
        return []
