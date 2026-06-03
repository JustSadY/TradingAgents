# Per-User AI API Keys

## Storage

API keys are stored encrypted in `users.api_keys_enc` as a Fernet-encrypted JSON
blob. The Fernet key is read from the `ENCRYPTION_KEY` environment variable.

Example stored value (after encryption):
```
gAAAAABk... (opaque Fernet ciphertext)
```

Decrypted JSON structure:
```json
{
  "openai": "sk-...",
  "anthropic": "sk-ant-...",
  "google": "AIza..."
}
```

## Service Functions (`backend/services/user_service.py`)

| Function | Description |
|----------|-------------|
| `encrypt_api_keys(keys, fernet)` | Encrypt a dict of keys to a string |
| `decrypt_api_keys(enc, fernet)` | Decrypt back to dict |
| `get_user_api_key(user, provider, fernet)` | Get one provider's key |
| `set_user_api_key(user, provider, key, fernet)` | Add/update one key |
| `delete_user_api_key(user, provider, fernet)` | Remove one key |
| `list_user_api_key_providers(user, fernet)` | List provider names (no values) |

## Injection Flow

1. Analysis is triggered by a user (`POST /api/analysis/run`)
2. `_build_config(settings, user)` in `analysis_service.py` checks the user's key
3. If found: `config["api_key"] = user_key`
4. If not found and user is not admin: raises `ValueError` → HTTP 400
5. If not found and user is admin: falls back to `os.environ` (`.env` key)
6. `TradingGraph._get_provider_kwargs()` passes `api_key` from config to the LLM client
7. LLM clients use `kwargs.get("api_key") or os.environ.get(api_key_env)`

## Supported Providers

`openai`, `anthropic`, `google`, `xai`, `deepseek`, `qwen`, `qwen-cn`, `glm`,
`glm-cn`, `minimax`, `minimax-cn`, `ollama`, `nvidia`, `litellm`, `azure`

## Security

- Keys are never returned in API responses — only the provider names are listed
- Values are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256)
- The encryption key must be set in `.env` as `ENCRYPTION_KEY`
