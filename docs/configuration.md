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

## 🚦 0. Deployment mode: `ENVIRONMENT`

```ini
# development (default) | production
ENVIRONMENT=production
```

This single value changes five behaviours, so a deployment left on the default
runs as a development instance no matter how it was installed:

| Behaviour | `development` | `production` |
| --- | --- | --- |
| Schema | startup runs `alembic upgrade head` itself | startup **verifies** the schema is already at head and refuses to serve otherwise |
| RLS role | checked, failures logged | strict: the runtime role must be non-owner, `NOSUPERUSER`, `NOBYPASSRLS` (also forced by `RLS_STRICT_MODE`) |
| Refresh cookie | issued without `Secure` | issued with `Secure` |
| HSTS | not sent | `Strict-Transport-Security` sent on HTTPS responses |
| Secrets | shipped defaults are usable | boot fails unless `DATABASE_URL` is PostgreSQL/asyncpg and `SECRET_KEY` / `ENCRYPTION_KEY` are set |

Set `ENVIRONMENT=production` on any internet-facing instance. It is required
where the database uses a migrator/runtime role split: the runtime role cannot
run DDL, so a development-mode startup crashes on the first DDL-bearing
revision instead of deferring to the deploy's `MIGRATION_DATABASE_URL`.

---

## 🔑 1. Security & Authentication Configuration

These settings control API encryption, password hashing, and CORS access:

```ini
# Security Token Secret Key (Required)
# Generate one using: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=change-me-to-a-random-32-character-string

# The administrator account is not configured here. While the database has no
# users the UI serves a one-time setup screen that registers the Server Owner.

# DB Credential Encryption Key (Required)
# Used to encrypt sensitive API keys stored inside the settings database.
# Generate one using: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your-fernet-key-here

# CORS Authorized Origins (Required)
# Must be a JSON array of domains allowed to call the FastAPI backend.
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# Optional external frontend URL for public report-share links. This value is
# consumed at frontend build time, so rebuild the frontend after changing it.
VITE_PUBLIC_APP_URL=https://trading.example.com

# Prometheus Metrics Endpoint (Optional)
# Bearer token protecting GET /metrics. Leave empty to disable the endpoint (404).
# Generate one using: python -c "import secrets; print(secrets.token_hex(32))"
METRICS_TOKEN=

# Maximum HTTP request body size in bytes (Optional)
# Oversized requests are rejected with 413. Set 0 to disable. Default: 2000000 (2 MB).
MAX_REQUEST_BODY_BYTES=2000000

# Horizontal scaling via Redis (Optional)
# When set, analysis WebSocket events fan out over Redis pub/sub and the task
# registry becomes cross-process. Leave empty for single-process deployments.
REDIS_URL=
# "inline" (default) runs analyses in the web process; "worker" enqueues them
# onto arq (requires REDIS_URL and: arq backend.worker.WorkerSettings)
ANALYSIS_QUEUE_MODE=inline
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

Registered providers (set their keys in the Web UI; the authoritative list and
per-provider model options live in
`backend/trading_agents/llm_clients/registry.py` and are served via
`GET /api/settings/llm-catalog`):

```text
openai      — OpenAI GPT / o-series models
anthropic   — Anthropic Claude models
google      — Google Gemini models
nvidia      — NVIDIA NIM (OpenAI-compatible; Llama/Nemotron models)
```

The key store itself accepts arbitrary provider names — e.g. `pinecone` is
stored the same way for vector memory — but only providers registered in the
LLM registry can be selected for analysis runs.

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

## 📅 6. Exchange Calendar & Scheduling

Scheduled watchlist scans and automated orders are gated on the instrument's
exchange actually holding a session that day. Holiday data comes from
`exchange_calendars` via `backend/services/market_calendar_service.py`.

```ini
# IANA timezone used for user cron schedules
# (stock trade dates still resolve against America/New_York)
APP_TIMEZONE=UTC

# exchange_calendars code for tickers with no venue suffix (AAPL, MSFT).
# Optional; defaults to XNYS.
DEFAULT_EXCHANGE_CALENDAR=XNYS
```

How an instrument is resolved:

| Ticker | Calendar | Behaviour on an exchange holiday |
| :--- | :--- | :--- |
| `AAPL`, `MSFT` | `DEFAULT_EXCHANGE_CALENDAR` (`XNYS`) | Scan skipped, auto-order skipped, stop-loss/take-profit held |
| `THYAO.IS`, `VOD.L`, `7203.T` | Venue from the suffix (`XIST`, `XLON`, `XTKS`) | Gated on that exchange's own holidays |
| `BTC-USD`, or asset type `crypto` | None (24/7) | Never gated |

Lookups fail open: a missing package, unknown calendar code, or out-of-range
date is treated as "open" and logged, so a calendar problem can never freeze
every tenant's automation. Manual, user-initiated analyses are not gated.

---

## 📋 7. System Logs

The in-app **System Logs** page reads the `system_logs` table, written by the
database log handler in every process that does application work — the API and
the arq worker both start it.

```ini
# Minimum level persisted to system_logs.
# DEBUG | INFO (default) | WARNING | ERROR | CRITICAL
SYSTEM_LOG_DB_LEVEL=INFO
```

Everything at or above this level is persisted, minus a denylist of chatty
third-party loggers (`httpx`, `uvicorn.access`, `sqlalchemy.engine` and
similar), which still reach the database at `WARNING` and above. Records
dropped because the queue is saturated are reported on stderr rather than
discarded silently.

```ini
# Days of System Logs history to keep. 0 keeps everything.
SYSTEM_LOG_RETENTION_DAYS=14
```

The daily maintenance job (`cleanup_transient_data`) deletes `system_logs` rows
older than this window, alongside expired/revoked `refresh_sessions` and the
analyst/news caches. One analysis writes hundreds of INFO rows, so leaving the
retention at `0` lets the table grow without bound.

---

## 🎛️ 8. Platform Runtime Settings

All of the runtime options below are no longer read from `.env` or system environment variables. They are fully managed through the application's **Web UI** under **Settings** (or **Admin Panel** for defaults) and stored in the database:

*   **LLM Provider & Model:** E.g., `openai`, `gpt-5.6-luna`.
*   **Output Language:** Output language for markdown reports (English, Turkish, etc.).
*   **Research Debate Rounds:** Number of Bull/Bear research discussion rounds.
*   **Analyst Concurrency Limit:** Concurrency control for parallel analyst nodes.
*   **Historical Analysis Scope:** Toggle and limit for loading historical reports into active context.
*   **Specific Analyst Models Mapping:** Mapping specific analyst plugins to different LLM models.
