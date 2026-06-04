# 🖥️ TradingAgents Backend

The backend layer of TradingAgents is a high-performance, asynchronous web server built with **FastAPI**, **SQLAlchemy** (using the `asyncpg` driver), and **APScheduler**. It handles API routing, real-time WebSocket communication, authentication, background portfolio/alert cron scheduling, paper trading simulation, and interacts directly with the **LangGraph** multi-agent AI system.

> 🧭 **Working on the backend (humans & AI agents)?** Read
> **[ARCHITECTURE.md](ARCHITECTURE.md)** first — it is the single, dense
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
│   ├── security.py       # bcrypt hashing, JWT, Fernet secret encryption
│   ├── log_handler.py    # Async DB log handler
│   └── websocket.py      # WS connection manager for real-time progress feeds
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
*   **Schema management:** On startup the app calls `Base.metadata.create_all` and then a small **additive, idempotent column migrator** ([core/migrations.py](core/migrations.py)) that issues `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for any newly added model columns. There is **no Alembic** in use — model changes that only *add* columns are picked up automatically; destructive changes (renames/drops/type changes) must be applied manually.
*   **APScheduler:** In-process, cron-like job scheduler for background analyses.
*   **WebSockets:** Dynamic progress updates streaming for long-running agent workflows.

---

## 🔐 Core Infrastructure Systems

### 1. Asynchronous Database Logging & Redaction
To aid system diagnostics, all application warnings, info logs, and agent runs are captured and written to the database (`system_logs` table) via [log_handler.py](core/log_handler.py).
*   **Redaction:** An interception layer automatically sanitizes API keys (e.g., `sk-...`) or passwords before they hit any logging sinks to prevent leakage into the terminal or DB logs.

### 2. WebSocket Stream Multiplexing
Long-running AI debates can take up to 2-3 minutes. Instead of blocking HTTP connections, the API accepts a request and runs the graph on an asynchronous worker. The React frontend connects via [websocket.py](core/websocket.py) to `/ws/analysis/{task_id}` to watch real-time node outputs, LLM token streams, and process states.

### 3. Automatic System Updater
The server integrates with a systemd-managed update wrapper. [update_service.py](services/update_service.py) regularly polls the GitHub remote repository. If an administrator clicks "Update" in the settings panel, it kicks off a one-shot systemd service to run safe git pulls, dependency updates, front-end compilation, and restarts the parent application daemon.

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
    pip install -r backend/requirements.txt
    ```
4.  **Database Setup / Migrations:**
    Tables and additive column migrations are applied automatically on startup
    (see [core/migrations.py](core/migrations.py)). No manual migration step is
    required for a fresh database; only destructive schema changes need manual SQL.
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
| `/ws/analysis/{task_id}` | `WS` | Yes² | Stream live LangGraph progress events. |
| `/health` | `GET` | No | Health check. Returns `{"status": "ok"}`. |

¹ Validated via the refresh token in the body, not a bearer header.
² Authenticated via a `token` query parameter (JWT access token).
