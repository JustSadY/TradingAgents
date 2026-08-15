# 🖥️ TradingAgents Backend

The backend layer of TradingAgents is a high-performance, asynchronous web server built with **FastAPI**, **SQLAlchemy** (using the `asyncpg` driver), and **APScheduler**. It handles API routing, real-time WebSocket communication, authentication, background portfolio/alert cron scheduling, paper trading simulation, and interacts directly with the **LangGraph** multi-agent AI system.

> 🧭 **Working on the backend (humans & AI agents)?** Read
> **[docs/architecture/backend.md](../docs/architecture/backend.md)** first — it is the single, dense
> reference for the layering, where each kind of code belongs, the conventions
> to follow, and the gotchas to avoid. It exists so you can understand the
> design without re-scanning the whole tree.

---

## 🏗️ Architecture Overview

The backend uses a clean, service-oriented structure designed to support asynchronous task execution and real-time dashboard state updates:

```text
backend/
├── main.py               # FastAPI app factory: wires routers, CORS, WS, SPA static mount
├── bootstrap.py          # Idempotent runtime setup: TRADINGAGENTS_* env, the local
│                         #   engine env defaults + logging stub (imported once, early)
├── api/                  # 🔵 Presentation layer — thin FastAPI routers (no business logic)
│   ├── deps.py           # DI dependencies: get_current_user / require_admin / require_page
│   ├── auth.py           # JWT login & refresh (router prefix: /auth)
│   ├── analysis.py       # Analysis runs, history, A/B, performance, report Q&A
│   ├── market.py         # OHLCV, custom indicators, sentiment history
│   ├── news.py           # Cached news feed
│   ├── watchlist.py      # Asset watchlists
│   ├── portfolio.py      # Portfolios / holdings / orders listing
│   ├── trading.py        # Paper order placement, portfolio, performance, reset
│   ├── settings.py       # Per-user LLM / engine configuration
│   ├── users.py          # User management, RBAC permissions, per-user API keys
│   └── ...               # alerts, presets, cron, logs, meta, update, system_settings
├── services/             # 🟠 Business logic — orchestration, external IO, computation
│   ├── analysis_service.py       # Multi-agent run orchestration (+ run_analysis_task)
│   ├── settings_service.py       # AppSettings get-or-create, DTO mapping, updates
│   ├── market_service.py         # OHLCV/indicator/sentiment computation (off the event loop)
│   ├── news_service.py           # TTL-cached news retrieval
│   ├── analysis_stats_service.py # Cost estimate, A/B comparison, signal performance
│   ├── report_chat_service.py    # Report-grounded Q&A (context, LLM, persistence)
│   ├── trading_orchestrator.py   # Signal → sized paper order (shared by run + cron)
│   ├── cron_service.py           # APScheduler recurring watchlist scans
│   ├── mock_trading_service.py   # Paper-trading ledger engine
│   └── ...                       # alert, performance, notification, update, user, annotation
├── repositories/         # 🟢 Data-access helpers (lightweight)
│   ├── common.py         # scope_to_user(): the per-user ownership filter (anti-IDOR)
│   └── users.py          # get_user_by_username / get_user_by_id
├── core/                 # Platform: config, DB engine, security, WebSockets, logging
│   ├── config.py         # Pydantic settings loaded from .env
│   ├── database.py       # Async engine/session + table creation
│   ├── migrations.py     # Additive, idempotent column migrations (see note below)
│   ├── security.py       # JWT, Fernet secret encryption (hashing: password_hashing.py)
│   ├── log_handler.py    # Async DB log handler
│   ├── websocket.py      # WS connection manager for real-time progress feeds
│   ├── redis_bus.py      # Opt-in Redis client (REDIS_URL) for horizontal scaling
│   ├── event_bus.py      # Analysis events: direct WS or Redis pub/sub fan-out
│   ├── task_store.py     # Cross-process task registry/ownership + cancel channel
│   └── body_limit.py     # Request body size limit middleware (413)
├── worker.py             # arq analysis worker entrypoint (ANALYSIS_QUEUE_MODE=worker)
├── schemas/              # Pydantic request/response DTOs
├── models/               # SQLAlchemy async ORM models (User, Portfolio, Order, Analysis, …)
└── trading_agents/       # Core multi-agent LangGraph engine (imported as backend.trading_agents)
```

> **Layering rule:** dependencies flow one way — `api → services → repositories → models`.
> Routers stay thin (validate → call a service → return a DTO); services never import from `api`.

---

## 🛠️ Key Technologies

*   **FastAPI:** Modern, asynchronous web framework for Python. Provides interactive API documentation out-of-the-box (Swagger UI at `/docs`).
*   **SQLAlchemy Async:** Async IO ORM targeting PostgreSQL via `asyncpg`.
*   **Schema management:** On startup the app calls `Base.metadata.create_all` and then a small **additive, idempotent column migrator** ([core/migrations.py](core/migrations.py)) that issues `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for any newly added model columns — model changes that only *add* columns are picked up automatically; destructive changes (renames/drops/type changes) must be applied manually. **Alembic is scaffolded as the opt-in successor** (see [alembic/README.md](alembic/README.md)): once a database is stamped with a baseline (`alembic_version` table exists), the startup migrator automatically defers to Alembic for that database.
*   **APScheduler:** In-process, cron-like job scheduler for background analyses.
*   **WebSockets:** Dynamic progress updates streaming for long-running agent workflows.

---

## 🔐 Core Infrastructure Systems

### 1. Asynchronous Database Logging & Redaction
To aid system diagnostics, all application warnings, info logs, and agent runs are captured and written to the database (`system_logs` table) via [log_handler.py](core/log_handler.py).
*   **Redaction:** An interception layer automatically sanitizes API keys (e.g., `sk-...`) or passwords before they hit any logging sinks to prevent leakage into the terminal or DB logs.
*   **Scoping:** Logs can be associated with a specific user account (scoped logs) via the `current_user_id` context variable. Standard users only see logs related to their own actions.

### 2. WebSocket Stream Multiplexing
Long-running AI debates can take up to 2-3 minutes. Instead of blocking HTTP connections, the API accepts a request and runs the graph as an async background task (or on a separate **arq worker** process when `ANALYSIS_QUEUE_MODE=worker`). The React frontend connects via [websocket.py](core/websocket.py) to `/ws/analysis/{task_id}` to watch real-time node outputs, LLM token streams, and process states. With `REDIS_URL` configured, events fan out across processes over Redis pub/sub ([event_bus.py](core/event_bus.py)) so streams work no matter which process executes the run.

### 3. Automatic System Updater
The server integrates with a systemd-managed update wrapper. [update_service.py](services/update_service.py) regularly polls the GitHub remote repository. If an administrator clicks "Update" in the settings panel, it kicks off a one-shot systemd service to run safe git pulls, dependency updates, front-end compilation, and restarts the parent application daemon.

### 4. Dynamic Modular Tool System & Access Permissions
To support flexible tool execution inside analyst nodes, the platform implements a dynamically resolved modular tool registry:
*   **Database Models (`backend/models/tool_settings.py`):**
    *   `AgentToolSetting`: Stores global defaults and user-specific customizations for tool fields.
    *   `UserAgentAccess`: Restricts or grants access to run specific analyst nodes (e.g., Market Analyst).
    *   `UserToolAccess`: Configures granular user actions for individual tools (`can_view`, `can_use`, `can_edit`, `can_enable`).
    *   `UserToolFieldAccess`: Overrides field-level visibility (`can_view`, `can_edit`) for individual tool configuration settings.
*   **Access Control Services (`backend/services/tool_access_service.py` & `tool_settings_service.py`):**
    *   Maintains helper utilities to retrieve, update, and resolve user-specific permission profiles and override configurations.
*   **API Endpoints:**
    *   `/api/settings/tools` (`GET/PUT`): Reads/updates active tool settings for the calling user.
    *   `/api/system-settings/tools` (`GET/PUT`): Admin-only route to manage global fallback tool settings.
    *   `/api/users/{id}/agent-access` (`GET/PUT`): Admin-only route to manage which analyst nodes a user is permitted to invoke.
    *   `/api/users/{id}/tool-access` (`GET/PUT`): Admin-only route to configure tool-level user permissions.

---

## 🚀 Setup & Developer Onboarding

For comprehensive setup options (Linux scripts vs. Docker vs. Manual), please consult the main [docs/installation.md](../docs/installation.md).

### Local Running (Manual Mode)

Ensure you have a PostgreSQL database server running and a database named `tradingagents` created.

1.  **Create `.env` Configuration:**
    Create a `.env` file in the project root containing your credentials. You can use `.env.example` as a template:
    ```bash
    cp .env.example .env
    ```
2.  **Initialize Virtual Environment:**
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # Linux/Mac:
    source .venv/bin/activate
    ```
3.  **Install Packages:**
    ```bash
    cd backend && uv sync --frozen
    ```
    `pyproject.toml + uv.lock` is generated from `uv.lock` and is fully pinned; do not
    edit it by hand. Declare dependencies in `pyproject.toml`, then run
    `uv lock && ./scripts/export-requirements.sh`. Contributors with uv can use
    `uv sync` instead, which also installs the `dev` group (ruff, pyright, pytest).
4.  **Database Setup / Migrations:**
    Tables and additive column migrations are applied automatically on startup
    (see [core/migrations.py](core/migrations.py)). No manual migration step is
    required for a fresh database; only destructive schema changes need manual SQL.
    To manage a database with Alembic instead, follow [alembic/README.md](alembic/README.md).
5.  **Run Development Server:**
    ```bash
    uvicorn backend.main:app --reload --port 8000
    ```
    Access the OpenAPI Swagger page at `http://localhost:8000/docs`.

---

## 📝 API Endpoints Summary

> The full, always-current contract (every route, parameter and schema) is the
> OpenAPI page at **`/docs`**. The table below is a representative subset.
> Note the auth router is mounted at **`/auth`** (not `/api/auth`).

| Endpoint | Method | Auth | Description |
| :--- | :--- | :--- | :--- |
| `/auth/login` | `POST` | No | Authenticate; returns JWT access + refresh tokens. |
| `/auth/refresh` | `POST` | No¹ | Exchange a refresh token for new tokens. |
| `/api/users/me` | `GET/PUT` | Yes | Read / update the current user profile. |
| `/api/users/me/api-keys` | `GET/PUT/DELETE` | Yes | Manage the current user's per-provider LLM API keys (encrypted at rest). |
| `/api/users/{id}/api-keys` | `GET/PUT/DELETE` | Admin | Manage another user's API keys. |
| `/api/analysis/run` | `POST` | Yes | Start a multi-agent decision run for one symbol. |
| `/api/analysis/history` | `GET` | Yes | List past analyses (scoped to the caller). |
| `/api/analysis/{id}/chat` | `GET/POST` | Yes | Report-grounded Q&A over a completed analysis. |
| `/api/analysis/performance` | `GET` | Yes | Aggregate signal performance / win rate. |
| `/api/market/ohlcv` | `GET` | Yes | OHLCV candles + indicators for charting. |
| `/api/watchlist` | `GET/POST/DELETE` | Yes | Manage watchlist assets. |
| `/api/trading/portfolio` | `GET` | Yes | Paper portfolio with live prices & P&L. |
| `/api/trading/order` | `POST` | Yes | Submit a paper buy/sell order. |
| `/api/settings` | `GET/PUT` | Yes | Read / update per-user LLM & engine settings. |
| `/api/settings/tools` | `GET/PUT` | Yes | Read / update user-specific agent tool settings. |
| `/api/system-settings/tools` | `GET/PUT` | Admin | Manage system-default fallback tool settings. |
| `/api/users/{id}/agent-access` | `GET/PUT` | Admin | Read / update user permissions for analyst nodes. |
| `/api/users/{id}/tool-access` | `GET/PUT` | Admin | Read / update user permissions for agent tools. |
| `/api/logs` | `GET` | Admin | List all system logs (level, source, user_id filters). |
| `/api/logs/me` | `GET` | Yes | Scoped system logs for the authenticated user. |
| `/api/meta` | `GET` | No | Returns system metadata, dynamic tool schemas and lists. |
| `/ws/analysis/{task_id}` | `WS` | Yes² | Stream live LangGraph progress events. |
| `/health` | `GET` | No | Health check. Returns `{"status": "ok"}`. |

¹ Validated via the refresh token in the body, not a bearer header.
² Authenticated through a private `tradingagents.jwt.<access-token>` WebSocket
subprotocol. Clients must also offer `tradingagents.v1`, which is the only
subprotocol the server selects; JWTs must never be placed in the URL.
