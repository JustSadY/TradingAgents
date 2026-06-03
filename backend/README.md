# 🖥️ TradingAgents Backend

The backend layer of TradingAgents is a high-performance, asynchronous web server built with **FastAPI**, **SQLAlchemy** (using the `asyncpg` driver), and **APScheduler**. It handles API routing, real-time WebSocket communication, authentication, background portfolio/alert cron scheduling, paper trading simulation, and interacts directly with the **LangGraph** multi-agent AI system.

---

## 🏗️ Architecture Overview

The backend uses a clean, service-oriented structure designed to support asynchronous task execution and real-time dashboard state updates:

```text
backend/
├── api/                  # FastAPI routers and dependency injection
│   ├── deps.py           # Dependency injection (e.g., DB sessions, authenticated users)
│   ├── auth.py           # JWT Authentication & Login flow
│   ├── analysis.py       # Multi-Agent analysis execution and results
│   ├── watchlist.py      # Asset watchlists management
│   ├── portfolio.py      # Live/Simulation portfolio stats
│   ├── settings.py       # User-level LLM and API configurations
│   ├── cron.py           # Watchlist analysis cron schedules
│   ├── trading.py        # Order placement and execution endpoint
│   ├── alerts.py         # Signal alerts and threshold triggers
│   └── update.py         # Self-updating controls
├── core/                 # Platform configuration, DB engine, security, & WebSockets
│   ├── config.py         # Base settings loaded from .env
│   ├── database.py       # Asynchronous PostgreSQL session and engine initiation
│   ├── security.py       # Password hashing and JWT generation
│   ├── log_handler.py    # DB logging handler (pushes logs to database asynchronously)
│   └── websocket.py      # WS connection manager for real-time progress feeds
├── models/               # SQLAlchemy asynchronous DB models
│   ├── user.py           # User profiles (RBAC roles: user, admin, owner)
│   ├── portfolio.py      # Portfolios, cash, and performance indicators
│   ├── order.py          # Simulated paper trade records
│   ├── analysis.py       # Archived multi-agent output reports
│   └── settings.py       # API key settings per provider (encrypted at rest)
├── services/             # Core business logic services
│   ├── analysis_service.py  # Asynchronous multi-agent execution orchestrator
│   ├── cron_service.py      # Scheduler for recurring watchlist analysis jobs
│   ├── mock_trading_service.py # Paper trading matching and ledger engine
│   └── update_service.py    # Systemd-integrated automatic git update checks
└── trading_agents/       # Core multi-agent package (imported locally)
```

---

## 🛠️ Key Technologies

*   **FastAPI:** Modern, asynchronous web framework for Python. Provides interactive API documentation out-of-the-box (Swagger UI at `/docs`).
*   **SQLAlchemy Async:** Async IO ORM targeting PostgreSQL via `asyncpg`.
*   **Alembic:** Database schema migrations management.
*   **APScheduler:** In-process, cron-like job scheduler for background analyses.
*   **WebSockets:** Dynamic progress updates streaming for long-running agent workflows.

---

## 🔐 Core Infrastructure Systems

### 1. Asynchronous Database Logging & Redaction
To aid system diagnostics, all application warnings, info logs, and agent runs are captured and written to the database (`system_logs` table) via [log_handler.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/core/log_handler.py).
*   **Redaction:** An interception layer automatically sanitizes API keys (e.g., `sk-...`) or passwords before they hit any logging sinks to prevent leakage into the terminal or DB logs.

### 2. WebSocket Stream Multiplexing
Long-running AI debates can take up to 2-3 minutes. Instead of blocking HTTP connections, the API accepts a request and runs the graph on an asynchronous worker. The React frontend connects via [websocket.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/core/websocket.py) to `/ws/analysis/{task_id}` to watch real-time node outputs, LLM token streams, and process states.

### 3. Automatic System Updater
The server integrates with a systemd-managed update wrapper. [update_service.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/services/update_service.py) regularly polls the GitHub remote repository. If an administrator clicks "Update" in the settings panel, it kicks off a one-shot systemd service to run safe git pulls, dependency updates, front-end compilation, and restarts the parent application daemon.

---

## 🚀 Setup & Developer Onboarding

For comprehensive setup options (Linux scripts vs. Docker vs. Manual), please consult the main [docs/installation.md](file:///c:/Users/JustS/Desktop/TradingAgents/docs/installation.md).

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
    FastAPI automatically handles table creation on startup. If you make model changes, manage them via Alembic.
5.  **Run Development Server:**
    ```bash
    uvicorn backend.main:app --reload --port 8000
    ```
    Access the OpenAPI Swagger page at `http://localhost:8000/docs`.

---

## 📝 API Endpoints Summary

| Endpoint | Method | Auth Required | Description |
| :--- | :--- | :--- | :--- |
| `/api/auth/login` | `POST` | No | Authenticates user, returns JWT access and refresh tokens. |
| `/api/users/me` | `GET` | Yes | Retrieves current user profile. |
| `/api/analysis/run` | `POST` | Yes | Starts a multi-agent decision run for a given symbol. |
| `/api/watchlist` | `GET/POST` | Yes | Manages watchlist assets. |
| `/api/portfolio/stats` | `GET` | Yes | Returns summary statistics for paper trading. |
| `/api/trading/order` | `POST` | Yes | Submits a market/limit buy or sell order. |
| `/api/settings/keys` | `POST` | Yes (Admin) | Updates LLM provider API credentials securely. |
| `/ws/analysis/{task_id}`| `WS` | Yes | Streams active LangGraph progress events. |
| `/health` | `GET` | No | Health check. Returns `{"status": "ok"}`. |
