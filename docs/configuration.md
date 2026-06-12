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

# Prometheus Metrics Endpoint (Optional)
# Bearer token protecting GET /metrics. Leave empty to disable the endpoint (404).
# Generate one using: python -c "import secrets; print(secrets.token_hex(32))"
METRICS_TOKEN=

# Maximum HTTP request body size in bytes (Optional)
# Oversized requests are rejected with 413. Set 0 to disable. Default: 2000000 (2 MB).
MAX_REQUEST_BODY_BYTES=2000000
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
GOOGLE      — Gemini models (gemini-1.5/2.0-flash, pro)
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

To query stock/crypto details, sentiment, and news, configure the following in the **Web UI** as modular tool parameters. They are stored in the database rather than read from `.env` files:

*   **Alpha Vantage API Key (`alpha_vantage_api_key`):** Configured globally by the administrator in **Admin Panel → Global Settings** under the **Core Stock Data** tool settings card (Server Scope).
*   **Reddit Credentials (`reddit_client_id`, `reddit_client_secret`, `reddit_user_agent`):** Configured individually by users in **Settings → Tools** under the **Reddit Sentiment** tool settings card (User Scope). Reverts to default user agent strings if not set.

---

## 🔍 5. Search Engine Configuration (SearXNG)

The News Analyst queries search engines to fetch global current events. To avoid rate-limits, TradingAgents connects to a **SearXNG** instance, whose URL is configured individually by users in **Settings → Tools** under the **SearXNG Web Search** tool settings card (User Scope, defaults to `http://localhost:8080` if empty):

```text
searxng_url   e.g. http://localhost:8080
```

You can run a local SearXNG instance using Docker:
```bash
docker run -d -p 8080:8080 searxng/searxng
```

---

## 🎛️ 6. Platform Runtime Settings

All of the runtime options below are no longer read from `.env` or system environment variables. They are fully managed through the application's **Web UI** under **Settings** (or **Admin Panel** for defaults) and stored in the database:

*   **LLM Provider & Model:** E.g., `openai`, `gpt-4o-mini`.
*   **Output Language:** Output language for markdown reports (English, Turkish, etc.).
*   **Debate & Risk Rounds:** Number of discussion rounds for Bull/Bear researchers and Risk agents.
*   **Analyst Concurrency Limit:** Concurrency control for parallel analyst nodes.
*   **Historical Analysis Scope:** Toggle and limit for loading historical reports into active context.
*   **Specific Analyst Models Mapping:** Mapping specific analyst plugins to different LLM models.
