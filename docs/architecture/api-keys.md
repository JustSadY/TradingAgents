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
2. `build_analysis_config(settings, user, ...)` decrypts the selected cloud
   provider's key and injects it into the per-run configuration.
3. `TradingAgentsGraph._get_provider_kwargs()` passes that key only to
   providers whose registry metadata says a tenant key is required.
4. Cloud-provider calls without a key are rejected by the service/client
   boundary for every role; there is no `.env` fallback.
5. Server-managed providers such as Ollama receive neither a tenant key nor a
   tenant-controlled base URL. Their endpoint comes only from server config.

## Supported Providers

For LLM execution, the providers a user can select are the ones registered in
`backend/trading_agents/llm_clients/registry.py` — currently `openai`,
`anthropic`, `google`, `mistral`, `groq`, `nvidia`, `deepseek`, and `ollama` —
exposed via `GET /api/settings/llm-catalog`. The same stored OpenAI credential is
used when Mem0 long-term memory is configured with the OpenAI embedder. Ollama
is server-managed and does not accept or expose a per-user API key.

## Security

- Keys are never returned in API responses — only the provider names are listed
- Providers marked `requires_api_key=False` are omitted from the stored-key
  listing; stale encrypted values are inert at runtime
- Values are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256)
- The encryption key must be set in `.env` as `ENCRYPTION_KEY`
