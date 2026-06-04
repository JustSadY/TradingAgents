# Configuration & API Setup

TradingAgents configuration is split in two:

* **Infrastructure secrets** live in a `.env` file at the project root — the
  auth secret, admin bootstrap, database URL, Fernet encryption key and CORS
  origins (sections 1–2 below). These are the only values `core/config.py` reads
  from the environment.
* **Provider keys & operational settings** (LLM provider keys, data vendors,
  SearXNG, per-user engine options) are configured at runtime in the **Web UI**
  and stored — encrypted where sensitive — in the database.

---

## 🔑 1. Security & Authentication Configuration

These settings control API encryption, password hashing, and CORS access:

```ini
# Security Token Secret Key (Required)
# Generate one using: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=change-me-to-a-random-32-character-string

# Administrator Settings
ADMIN_USERNAME=admin
# Optional bcrypt hash. If empty, defaults to hash of "changeme" or a randomly printed installer password
ADMIN_PASSWORD_HASH=

# DB Credential Encryption Key (Required)
# Used to encrypt sensitive API keys stored inside the settings database.
# Generate one using: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your-fernet-key-here

# CORS Authorized Origins (Required)
# Must be a JSON array of domains allowed to call the FastAPI backend.
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
```

---

## 🗄️ 2. Database Connection

The database configuration utilizes SQLAlchemy async layers. PostgreSQL with the `asyncpg` driver is required:

```ini
# Format: postgresql+asyncpg://<user>:<password>@<host>:<port>/<dbname>
DATABASE_URL=postgresql+asyncpg://tradingagents:tradingagents@localhost:5432/tradingagents
```

---

## 🤖 3. LLM Provider Configurations

> ⚠️ **These are no longer `.env` variables.** LLM provider keys are configured
> at runtime through the **Web UI** and stored encrypted (Fernet) in the
> database — per-user under *Preferences → Account & API Keys*, and globally
> under *Admin Panel → Global Settings*. The `.env` only holds the
> infrastructure secrets in sections 1–2 above. The variable names below are
> kept for reference of which providers are supported.

Supported providers (set their keys in the Web UI):

```text
OPENAI      — GPT models (gpt-4o, o1, o3-mini)
ANTHROPIC   — Claude models (claude-sonnet / opus)
GOOGLE      — Gemini models (gemini-2.0/2.5-flash, pro)
XAI         — Grok models
DEEPSEEK    — DeepSeek V3 / R1 models
OPENROUTER  — Alternative multi-provider routing gateway
LITELLM     — LiteLLM Proxy endpoint
AZURE       — Enterprise Azure OpenAI endpoints
```

### Provider-Specific Reasoning Configurations
Some reasoning models accept configuration parameters that are mapped dynamically from the application's configuration dictionary:
*   **Google Gemini:** Accepts `google_thinking_level` to control gemini thinking budget.
*   **OpenAI:** Accepts `openai_reasoning_effort` (low, medium, high) for o-series models.
*   **Anthropic:** Accepts `anthropic_effort` to control reasoning parameters.

---

## 📊 4. Data Vendor Configurations

To query stock/crypto details, sentiment, and news, configure the following in
the **Web UI** (*Admin Panel → Global Settings*) — like the LLM keys, these are
stored in the database, not in `.env`:

```text
ALPHA_VANTAGE_API_KEY    — alternative vendor for splits, technicals, fundamentals
REDDIT_CLIENT_ID         — Reddit sentiment (r/wallstreetbets, etc.)
REDDIT_CLIENT_SECRET
REDDIT_USER_AGENT        — e.g. TradingAgents/1.0
```

---

## 🔍 5. Search Engine Configuration (SearXNG)

The News Analyst queries search engines to fetch global current events. To avoid
rate-limits, TradingAgents connects to a **SearXNG** instance, whose URL is set
in the **Web UI** (*Admin Panel → Global Settings*, `searxng_url`):

```text
SEARXNG_URL   e.g. http://localhost:8080
```

You can run a local SearXNG instance using Docker:
```bash
docker run -d -p 8080:8080 searxng/searxng
```

---

## 🎛️ 6. Platform Runtime Settings (Optional Overrides)

These environment variables can override the default parameters defined in [config.py](../backend/trading_agents/config.py) (re-exported as `DEFAULT_CONFIG` by [default_config.py](../backend/trading_agents/default_config.py)):

```ini
# Select default LLM Provider (openai, anthropic, google, etc.)
TRADINGAGENTS_LLM_PROVIDER=openai

# Define default model name
TRADINGAGENTS_LLM_MODEL=gpt-4o-mini

# Language for generated markdown reports (e.g. English, Turkish)
TRADINGAGENTS_OUTPUT_LANGUAGE=English

# Max rounds for bull/bear and risk debates
TRADINGAGENTS_MAX_DEBATE_ROUNDS=2
TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS=2

# Concurrency limits for analyst nodes (concurrency > 1 starts nodes in parallel)
TRADINGAGENTS_ANALYST_CONCURRENCY_LIMIT=2

# Include previous DB analysis reports in the AI graph context
TRADINGAGENTS_INCLUDE_HISTORICAL_ANALYSES=false

# Number of historical reports to fetch and include in context (1-50)
TRADINGAGENTS_HISTORICAL_ANALYSES_LIMIT=5

# JSON dictionary mapping analyst keys to specific provider-model strings.
# Example: {"market": "google:gemini-3.1-flash-lite", "news": "anthropic:claude-sonnet-4-6"}
# If a key is empty or missing, the default global provider/model is used.
TRADINGAGENTS_ANALYST_MODELS={}
```
