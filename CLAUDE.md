# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🎯 Project: TradingAgents

A comprehensive, production-ready multi-agent AI investment platform. FastAPI backend orchestrates a **6-node LangGraph** state machine where specialized AI analysts, researchers, traders, and risk managers collaborate to produce final investment decisions. Includes **Pinecone vector memory** for episodic learning, real-time **WebSocket streaming**, **RBAC with page-level permissions**, **encrypted per-user API keys**, and extensive **developer extensibility** (custom analysts, tools, personas, etc.).

**START HERE:**
- [docs/introduction.md](docs/introduction.md) — Overview
- [docs/architecture/overview.md](docs/architecture/overview.md) — High-level design
- [backend/README.md](backend/README.md) — Backend architecture and layering

---

## 🏗️ Current Architecture (6-Node LangGraph)

```
START
  ↓
Market Intelligence (orchestrates 12 analyst plugins)
  ↓
Agent Q&A (inter-analyst cross-examination & conflict resolution)
  ↓
Research Manager (bull/bear debate, synthesis, auditing)
  ↓
Trader (signal processing & tactical execution)
  ↓
Risk Debate (aggressive/conservative/neutral negotiation)
  ↓
Portfolio Manager (final decision)
  ↓
END
```

### Execution Pipeline

1. **API:** `/api/analysis/run` → `run_analysis_task()`
2. **Config Builder:** Reads user's AppSettings + AgentSettings, builds `RuntimeAgentContext`
3. **Memory Recall:** If user has Pinecone configured, fetch similar past situations + losses
4. **LangGraph:** `TradingAgentsGraph(selected_analysts, config).propagate(ticker, date)` → 6 nodes execute
5. **Streaming:** `AnalysisEmitter` broadcasts `/ws/analysis/{task_id}` events in real-time
6. **Persistence:** Store in `AnalysisResult`, stream updates to `AnalysisChat`
7. **Memory Record:** After outcome known, embed & store in Pinecone for future recall
8. **Paper Trading:** `place_signal_order()` creates orders in `Order` table

### Tier System

- **Tier 1 (Main Agents):** 6 nodes in `agents/main/*.py` — guard-wrapped for resilience
- **Tier 2 (Sub-Agents):** Analysts, researchers, managers in `agents/sub/`
- **Tier 3 (Tools):** Modular registry in `agents/tools/` — dynamically registered, user-configurable

### Single Source of Truth

**`agents/hierarchy.py`** (`AgentHierarchy`):
- Cascading `is_enabled()` kill-switches (parent disabled → all children disabled)
- `resolve_llm()` recursive LLM fallback (agent → parent → global default)
- `tool_is_reachable()` gates tools when all allowed analysts disabled
- Parent links defined in `agent_catalog.py` (`AGENTS` list)

---

## 🛠️ Development Setup

### Prerequisites

- **Python 3.10+** (backend)
- **Node.js 20+** (frontend)
- **PostgreSQL 12+** (auto-created on Linux; manual on Windows/macOS)

### Local Dev Workflow

#### 1. Backend

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r backend/requirements.txt
cp .env.example .env
# Fill in: SECRET_KEY, ENCRYPTION_KEY, LLM provider keys (if testing)

uvicorn backend.main:app --reload --port 8000
# Auto-runs migrations on startup
```

#### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# Launches http://localhost:5173 with auto-proxy to :8000
```

#### 3. Database

PostgreSQL running, database named `tradingagents` (or match `DATABASE_URL` in `.env`).

#### Full Stack (two terminals)

```bash
# Terminal 1: Backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

---

## 📋 Key Tasks & Workflows

### Building & Deployment

**Frontend production build:**
```bash
cd frontend && npm run build
# Outputs to frontend/dist/ (served by FastAPI in production)
```

**Linux server installation:**
```bash
sudo bash deploy/install.sh
# Installs everything, creates systemd service, generates .env
```

**System management:**
```bash
systemctl status tradingagents
systemctl restart tradingagents
journalctl -u tradingagents -f
```

### Code Quality

**Frontend linting:**
```bash
cd frontend && npm run lint
```

**Backend linting and formatting:**
Backend code style is enforced using Ruff (config in `backend/pyproject.toml`).
```bash
cd backend
ruff check .        # Lint checks
ruff check . --fix  # Auto-fix lint issues
ruff format --check # Format checks
ruff format         # Format code
```

**Continuous Integration:**
`.github/workflows/ci.yml` runs on every push/PR to `main` and is blocking:
- Backend: ruff lint + format check, pytest (against a PostgreSQL service)
- Frontend: ESLint (errors fail; known debt is downgraded to warnings in `eslint.config.js`), Vitest, production build (`tsc -b && vite build`)

### Testing

**Running backend tests:**
Backend unit and integration tests are written in Pytest (~20 modules in `backend/tests/` covering leverage/margin trading, backtests, screeners, token accounting, permissions, and agent plumbing).
```bash
cd backend
pytest
```
- **Test Database:** Integration tests run against an in-memory SQLite database (`sqlite+aiosqlite:///:memory:`).
- **Mocking Market Data:** Live price feeds are stubbed during tests by monkeypatching the `mock_trading_service` (specifically `get_live_price` and `get_live_prices_batch`). See [backend/tests/test_leverage_trading.py](backend/tests/test_leverage_trading.py) for examples.

**Running frontend tests:**
Frontend unit tests use Vitest + Testing Library (jsdom), co-located as `*.test.ts(x)` next to their sources (e.g. `src/contexts/PermissionsContext.test.tsx` for RBAC logic).
```bash
cd frontend && npm test
```

For agent behavior, you can also spin up the full stack and run analyses through the UI.


---

## 🔑 Key Concepts & Patterns

### Layering (Backend)

Strict dependency flow: `api → services → repositories → models`

- **`api/`** — FastAPI routers; validate input, call service, return DTO. Keep handlers **thin** (no business logic, DB commits, or external API calls in handlers).
- **`services/`** — Business logic, orchestration, external IO
- **`repositories/`** — Data-access helpers; always apply `scope_to_user(user_id)` IDOR prevention
- **`models/`** — SQLAlchemy async ORM (PostgreSQL + asyncpg)
- **`core/`** — Config, DB, security, WebSockets, logging, memory, migrations

**Route Ordering Rule:**
In FastAPI routers, always declare **static paths before dynamic/parameterized paths** (e.g., register static `/history` before variable `/{id}`) to prevent route shadowing and 422 validation errors.

### Exact Decimal Arithmetic (Fixed Precision)

- **Monetary Fields:** Price, quantity, balance, and margin columns are defined as SQLAlchemy `MONEY = Numeric(20, 8, asdecimal=True)`.
- **Decimal End-to-End:** All calculations inside backend trading and risk services must use Python's `Decimal` type. Do not use float types to avoid accumulative rounding and precision errors.


### API Routes (Key Endpoints)

| Route | Method | Auth | Description |
|-------|--------|------|-------------|
| `/auth/login` | POST | — | JWT tokens (access + refresh) |
| `/api/analysis/run` | POST | Yes | Start single or multi-ticker analysis |
| `/api/analysis/history` | GET | Yes | Past analyses (scoped to user) |
| `/api/analysis/{id}/chat` | GET/POST | Yes | Q&A over completed analysis |
| `/api/market/ohlcv` | GET | Yes | OHLCV + indicators for charting |
| `/api/market/custom-indicator` | GET | Yes | Evaluate custom indicator formula |
| `/api/market/formula-assist` | POST | Yes | AI-generate formula from natural language |
| `/api/market/sentiment-history` | GET | Yes | Sentiment time series for chart overlay |
| `/api/trading/portfolio` | GET | Yes | Paper portfolio with P&L |
| `/api/trading/order` | POST | Yes | Place buy/sell paper order |
| `/api/settings` | GET/PUT | Yes | User LLM settings, memory config, effort |
| `/api/settings/tools` | GET/PUT | Yes | User-scoped tool settings |
| `/api/system-settings/tools` | GET/PUT | Admin | Global fallback tool defaults |
| `/api/users/{id}/agent-access` | GET/PUT | Admin | Which analysts user can run |
| `/api/users/{id}/tool-access` | GET/PUT | Admin | Which tools user can view/use/edit/enable |
| `/api/users/{id}/permissions` | GET/PUT | Admin | Which pages user can access |
| `/api/logs` | GET | Admin | List all system logs (level, source, user_id filters) |
| `/api/logs/me` | GET | Yes | Scoped system logs for the authenticated user |
| `/api/assistant/history` | GET | Yes | Fetch portfolio assistant conversation history |
| `/api/assistant/chat` | POST | Yes | Send message to portfolio assistant (tool-calling LLM) |
| `/api/assistant/history` | DELETE | Yes | Clear assistant conversation history |
| `/metrics` | GET | Bearer token | Prometheus metrics (enabled via `METRICS_TOKEN` in `.env`; 404 when unset) |
| `/ws/analysis/{task_id}` | WS | Token | Stream live LangGraph progress + reports |

### Tool System (Tier 3)

**To Register a New Tool:**

1. Create class in `agents/tools/builtin/` extending `BaseAgentTool` or `FunctionToolAdapter`
2. Define `settings_schema` (slider, text, toggle, etc.)
3. Implement `get_langchain_tools()` returning LangChain `@tool` functions
4. Import in `agents/tools/bootstrap.py` (auto-registered on startup)
5. Add i18n in `frontend/src/i18n/tools.ts`

**Example:**

```python
from backend.trading_agents.agents.tools.base import BaseAgentTool, ToolSettingField

class MyTool(BaseAgentTool):
    key = "my_tool"
    category = "market"
    default_enabled = True
    allowed_analysts = ["market", "social"]
    settings_schema = [
        ToolSettingField(key="param", type="number", label_key="...", min=1, max=100)
    ]
    
    def get_langchain_tools(self, settings, context):
        limit = int(settings.get("param", 10))
        
        @tool
        def do_thing(query: str) -> str:
            """Do the thing."""
            return f"Result: {query} (limit={limit})"
        
        return [do_thing]
```

**Access Control:**
- Global tool settings: `/api/system-settings/tools` (admin)
- User-scoped overrides: `/api/settings/tools` (user)
- `UserToolAccess`: can_view, can_use, can_edit, can_enable per tool
- `UserToolFieldAccess`: field-level visibility overrides

### Interactive Charting & AI Formula Assistant

**Chart Page** (`/chart`) — interactive OHLCV chart with:
- Recharts + lightweight-charts powered candlestick / line charts
- Built-in indicators: SMA(20), EMA(20), RSI(14), MACD(12,26,9)
- Custom indicator pane: RSI, MACD, Sentiment overlaid
- **Custom Formula Engine** (`GET /api/market/custom-indicator`) — evaluate user-defined formulas against OHLCV data using a safe DSL
  - Supported functions: `SMA(n)`, `EMA(n)`, `RSI(n)`, `MACD(f,s,sg)`, `ATR(n)`, `ADX(n)`, `VWAP`, `VOLSMA(n)`, `MAX(n)`, `MIN(n)`, `SHIFT(col,n)`
  - Example: `(Close - SMA(20)) / STD(20)` — Z-score distance from 20-day MA
- **AI Formula Assistant** (`POST /api/market/formula-assist`) — converts natural language to formulas
  - Powered by `services/formula_assist_service.py`
  - Validates generated formula against synthetic OHLCV before returning
  - Example: "distance from 20-day average in standard deviations" → `(Close - SMA(20)) / STD(20)`
- Analysis overlay: annotates chart with trade signal, target price, stop-loss, support/resistance from past analyses
- Sentiment history chart (`GET /api/market/sentiment-history`)

**Frontend Components:**
- `frontend/src/components/chart/ChartSearch.tsx` — ticker search
- `frontend/src/components/chart/TechnicalControls.tsx` — indicator toggles
- `frontend/src/components/chart/CustomIndicatorPane.tsx` — RSI/MACD/Sentiment sub-panes
- `frontend/src/components/chart/AnalysisDetailSidebar.tsx` — trade level annotations

### Portfolio Assistant (AI Chat Widget)

A floating AI chat widget available on **every page** (bottom-right corner). Uses the same LLM as the user's Portfolio Manager with full tool-calling.

**Capabilities:**
- Read-only: portfolio summary, past analysis history, analysis reports, watchlist, alerts, live prices
- Actions (with page-permission checks): create price alerts, trigger new analyses, place paper orders

**Tool List (9 tools):**
| Tool | Permission Required |
|------|---------------------|
| `get_portfolio_summary` | none |
| `get_analysis_history(ticker?, limit?)` | none |
| `get_analysis_report(analysis_id)` | none |
| `get_live_price(ticker)` | none |
| `get_watchlist` | none |
| `get_alerts` | none |
| `create_price_alert(ticker, condition, target_price)` | `alerts` page |
| `run_stock_analysis(ticker)` | `analysis` page |
| `place_paper_order(ticker, action, quantity)` | `trading` page |

**Architecture:**
- `backend/models/assistant.py` — `AssistantMessage` (persistent chat history, user-scoped)
- `backend/repositories/assistant.py` — CRUD for messages
- `backend/services/portfolio_assistant_service.py` — LangChain tool-calling loop (max 5 iterations)
- `backend/api/assistant.py` — `GET/POST /api/assistant/chat`, `GET/DELETE /api/assistant/history`
- `frontend/src/components/assistant/PortfolioAssistant.tsx` — floating widget component
- Uses `AsyncSessionLocal` in action tools to avoid session conflicts with the chat transaction

**Permission Checks at Service Level:**
- Action tools check `allowed_pages` set (from `list_allowed_page_keys()` for users, all pages for admins)
- Returns a "Permission denied" string (not an exception) so the LLM can report it gracefully

### Episodic Memory (Vector Store)

**Per-User Configuration (Settings → Memory):**
- Store choice: `pinecone` (managed, default) or `pgvector` (self-hosted in the app's own PostgreSQL; requires the pgvector extension + the user's OpenAI key for client-side embedding)
- Pinecone API key (encrypted per-user)
- Index name, cloud, region
- Embedder choice (Pinecone hosted or OpenAI client-side)
- Embed model selection

**Recording:**
- After trade outcome known, `memory_service.record_episode()` embeds situation + decision + realized alpha
- Stored as `MemoryRecord` with metadata (ticker, date, outcome, loss/gain flag)
- Namespaced per user (`ep_user_<id>`)

**Recall:**
- Before analysts run, retrieve similar past situations via `memory_service.recall_episode_lessons()`
- **Losses weighted first:** "Do not repeat: [past loss situations]"
- Continuous learning without model retraining

**Agent Q&A Memory:**
- After analysts produce reports, Agent Q&A node cross-examines them
- Transcript stored in `qa_user_<id>` namespace for future recall
- Helps preserve multi-analyst conflict resolution patterns

**Important:** Memory is opt-in and per-user. If no Pinecone key configured, all memory calls become no-ops.

### Access Control Hierarchy

**Three Levels:**

1. **Agent-Level** (`UserAgentAccess`) — Which analysts can run (per user)
2. **Tool-Level** (`UserToolAccess`) — can_view / can_use / can_edit / can_enable per tool (per user)
3. **Field-Level** (`UserToolFieldAccess`) — Hide/disable individual tool settings (per user)

**Resolution at Runtime:**
- `tool_access_service.get_user_tool_access(db, user_id)` → permission dict
- `tool_settings_service.resolve_user_tool_settings()` → merged defaults + overrides

### RBAC & Page Permissions

**Roles:**
- **Owner** — Server owner (immutable, one per server, seeded at startup from `ADMIN_USERNAME` in `.env`)
- **Admin** — Manager of users & global settings (promoted by owner)
- **User** — Regular user (starts with no page access except Settings)

**Page Permissions:**
- Regular users start with **no page access** (admin grants per page)
- Admin/Owner implicitly access all pages
- Pages: dashboard, analysis, chart, trading, portfolio, watchlist, orders, performance, backtest, alerts, ab-testing, logs, settings, profile

**Settings Permissions (granular):**
Admins can restrict which parts of Settings a user can modify:
- `general` (mode, broker, language, persona, benchmark)
- `llm` (provider, model, analysts)
- `risk` (position limits, risk per trade, debate rounds)
- `webhooks` (webhook URL)
- `cron` (user-specific scheduler)
- `presets` (configuration templates)

### Encrypted Per-User API Keys

**Storage:**
- `users.api_keys_enc` — Fernet-encrypted JSON blob
- The store accepts any provider name (also used for `pinecone`); LLM-selectable providers come from `llm_clients/registry.py` (currently openai, anthropic, google, nvidia)

**Injection Flow:**
1. User triggers analysis
2. `_build_config(settings, user)` checks user's key
3. If found: inject into config
4. If not found & user is admin: fall back to `.env`
5. LLM client uses injected key

**Security:**
- Keys never returned in API responses (only provider names listed)
- Fernet encryption (AES-128-CBC + HMAC-SHA256)
- Encryption key must be in `.env` as `ENCRYPTION_KEY`

### UI Metadata Single Source of Truth

- Frontend configuration templates, dropdown options, language keys, and investor personas must never be hardcoded.
- The React client fetches these values dynamically via **`GET /api/meta`** and **`GET /api/settings/llm-catalog`**. Color maps for statuses/signals are determined via backend-returned tone values (`positive`, `neutral`, `negative`).

### Logging & Security Redaction

- System logs are captured asynchronously and saved via `DatabaseLogHandler` to the `SystemLog` table in batches of 30 or every 3 seconds.
- The logger automatically applies a redaction filter (`log_redaction.py`) to prevent leakage of credentials, passwords, or JWT secrets. Never log raw API keys or passwords.

### WebSocket Real-Time Streaming

Long-running analyses (2–3 min) stream live progress:

1. API returns `task_id` immediately
2. Frontend connects to `/ws/analysis/{task_id}` with token query param
3. Backend emits events: `progress`, `report`, `debate`, `complete`
4. `AnalysisEmitter` broadcasts to all subscribers for that task

Events:
```json
{
  "type": "progress",
  "node": "Market Analyst",
  "stage": "analyst"
}
```

```json
{
  "type": "report",
  "section": "market_report",
  "content": "### Market Technical Analysis\n..."
}
```

```json
{
  "type": "complete",
  "analysis_id": 45,
  "duration_seconds": 38.5,
  "llm_calls": 12
}
```

### Resilience & Fallbacks

Every main node is **guard-wrapped** with retry logic + fallback stubs:

| Node | Fallback on persistent failure |
|------|------|
| Any analyst | empty report note (`⚠️ … unavailable`) |
| Bull/Bear researcher | advance debate count |
| Synthesis/Auditor | empty report |
| Research Manager | placeholder investment plan |
| Trader | placeholder proposal |
| Risk debators | advance debate count |
| **Portfolio Manager** | `Hold — automated fallback` |

Portfolio Manager **always** produces a final decision, so analysis completes even if terminal agent fails.

**Retry Config:**
- `node_retry_attempts` (default 2)
- `node_retry_base_delay` (default 1.0s, exponential backoff)

### Async & Database

All async:

```python
from backend.core.database import AsyncSessionLocal

async with AsyncSessionLocal() as db:
    result = await repository.get_thing(db, id)
    await db.commit()
```

No sync database calls in async context. Layering: repositories ← services ← api.

### Frontend i18n

Supports English (`en`) and Turkish (`tr`). Toggle persists in `localStorage`.

**Adding Translations:**

1. **Common labels:** Edit `LanguageContext.tsx`, add to both `en` and `tr` blocks
2. **Page-specific:** Add to relevant file in `frontend/src/i18n/`
3. **New page:** Create `.ts` file in `frontend/src/i18n/`, auto-merged at load time

Example:
```typescript
const translations = {
  en: { 'feature.title': 'My Feature' },
  tr: { 'feature.title': 'Özelliğim' }
}
export default translations
```

### Cron Scheduler & Background Tasks

APScheduler runs in-process:
- `services/cron_service.py` (init, start, stop)
- `api/cron.py` (user endpoints)

**Critical:** Single uvicorn worker only. Multiple workers duplicate jobs.

---

## 🚨 Important Gotchas

### Circular Imports

`agents/main/*.py` must NOT import from `graph/` at module level. Analyst execution structures have been relocated to `agents/runtime/analyst_execution.py` to prevent circular dependency cycles between `agents` and `graph` compilation.

### Single Uvicorn Worker (default) / Redis Scaling (opt-in)

By default the systemd service runs **one** uvicorn process. APScheduler, WebSockets, and in-memory task tracking rely on this. Do not add `--workers` without enabling the Redis layer below.

**Opt-in Redis scaling** (`REDIS_URL` in `.env`):
- Analysis WebSocket events fan out over Redis Pub/Sub (`core/event_bus.py`); each web process runs a forwarder that feeds its local `ws_manager`.
- Task ownership/registry mirrors to Redis (`core/task_store.py`) so `/api/analysis/active`, WS auth, and cancel work across processes. Cancel requests broadcast on a control channel.
- `ANALYSIS_QUEUE_MODE=worker` additionally enqueues analysis runs onto **arq**; run the worker with `arq backend.worker.WorkerSettings`. Jobs carry only primitive ids (user_id, task_id) — the worker re-loads user/settings from the DB. `docker-compose.yml` ships this topology (redis + backend + worker).
- With `REDIS_URL` unset everything falls back to the original in-process behaviour; Redis is never required for a simple deployment.
- APScheduler (cron) still runs in the web process only — keep a single web process unless cron is also externalized.

### Migrations: Additive at Startup, Alembic Opt-In

`core/migrations.py` applies `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` at startup — this is the default mechanism for every deployment.

- Adding columns: auto-applied
- Renaming/dropping/changing types: manual SQL (think hard first)
- Alembic is scaffolded as the opt-in successor (see `backend/alembic/README.md`). Once a database is stamped with a baseline (`alembic_version` table exists), the startup migrator defers to Alembic for that database. No revisions are committed yet — generate the baseline per that README before relying on it.

### IDOR Prevention

Every data query must apply `scope_to_user(query, Model, user)` in repositories (or API route helpers) to enforce user boundaries (e.g., scoping `/api/logs/me` or `/api/analysis/history`). See `repositories/common.py`.

### Bootstrap Order

- `backend/bootstrap.py` must be imported early — it sets engine temp-dir defaults (`TRADINGAGENTS_LOG_DIR`, etc.) dynamically, preventing writing results/caches to a read-only source tree. Main app does this automatically, but if importing `trading_agents` directly in a custom script, runner, or test, import bootstrap first.
- **Lazy Imports:** Import heavy AI engine/LangGraph packages lazily inside functions to speed up main application boot time.

### Memory Is Opt-In & Per-User

A vector store must be configured by the user in Settings → Memory: Pinecone (API key) or pgvector (`memory_store='pgvector'`, self-hosted; needs the pgvector extension and the user's OpenAI key). If not configured, memory calls become no-ops. No recording happens until after trade outcome known.

### Configuration Is Database-Driven

All operational settings (LLM provider keys, tool configs, debate rounds, etc.) are in the **Web UI**, not `.env`. Only infrastructure secrets in `.env`: `SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`, `CORS_ORIGINS`.

---

## 📁 Project Layout

```
backend/
├── main.py                    # FastAPI app factory; startup hooks
├── bootstrap.py               # Engine env setup (import early!)
├── api/                       # Routers (no business logic)
│   ├── analysis.py
│   ├── trading.py
│   ├── settings.py
│   ├── users.py
│   └── ...
├── worker.py                  # arq analysis worker (ANALYSIS_QUEUE_MODE=worker)
├── services/                  # Orchestration & business logic
│   ├── analysis_service.py
│   ├── analysis/              # Sub-modules (emitter, orchestrator, persistence)
│   ├── analysis_queue.py      # Dispatch runs inline (BackgroundTasks) or to arq
│   ├── formula_assist_service.py # AI formula generation from natural language
│   ├── memory_service.py      # Pinecone episodic memory interface
│   ├── portfolio_assistant_service.py # Portfolio assistant LLM + tool-calling
│   ├── tool_access_service.py # Agent/tool permission resolution
│   ├── trading_orchestrator.py # Paper trading order logic
│   ├── cron_service.py
│   └── ...
├── repositories/              # Data access (apply scope_to_user!)
├── models/                    # SQLAlchemy ORM
├── core/                      # Platform infrastructure
│   ├── config.py
│   ├── database.py
│   ├── migrations.py          # Additive-only migrations
│   ├── security.py            # JWT, bcrypt, Fernet
│   ├── websocket.py
│   ├── redis_bus.py           # Opt-in Redis client (REDIS_URL)
│   ├── event_bus.py           # Analysis events: direct WS or Redis pub/sub
│   ├── task_store.py          # Cross-process task registry + cancel channel
│   ├── memory/                # Vector store abstractions
│   │   ├── base.py
│   │   ├── pinecone_store.py
│   │   └── embedders.py
│   └── ...
├── schemas/                   # Pydantic DTOs
└── trading_agents/            # Core AI engine (LangGraph)
    ├── agent_catalog.py       # Agent metadata & hierarchy tree (AGENTS list)
    ├── personas.py            # Investor persona catalog (single source)
    ├── agents/
    │   ├── main/              # Tier-1: 6 main nodes
    │   │   ├── market_intelligence.py
    │   │   ├── agent_qa.py    # Inter-agent cross-examination
    │   │   ├── research.py
    │   │   ├── trade_execution.py
    │   │   ├── risk.py
    │   │   └── portfolio.py
    │   ├── sub/               # Tier-2: analysts, researchers, managers
    │   │   ├── analysts/      # 12 analyst plugins
    │   │   ├── managers/
    │   │   ├── researchers/
    │   │   ├── risk_mgmt/
    │   │   └── trader/
    │   ├── tools/             # Tier-3: tool registry & builtin tools
    │   │   ├── base.py
    │   │   ├── registry.py
    │   │   ├── bootstrap.py   # Register tools on startup
    │   │   └── builtin/
    │   ├── data/              # yFinance, Alpha Vantage, Reddit, SEC, etc.
    │   ├── runtime/           # Execution framework (resilience, memory, factory,
    │   │                      #   analyst_execution.py)
    │   ├── hierarchy.py       # Agent hierarchy + kill-switches (single source of truth!)
    │   └── base.py            # Shared contracts
    ├── graph/                 # LangGraph state machine
    │   ├── setup.py           # Assembles 6 main nodes
    │   ├── trading_graph.py   # Entry point (TradingAgentsGraph class)
    │   ├── signal_processing.py
    │   ├── checkpointer.py
    │   └── ...
    ├── dataflows/             # Config & data source abstractions
    │   ├── config.py
    │   ├── y_finance.py
    │   ├── alpha_vantage.py
    │   └── ...
    └── llm_clients/           # Unified LLM API clients
        ├── registry.py        # Provider registry
        ├── model_catalog.py   # Per-provider model lists (served via /api/settings/llm-catalog)
        └── *_client.py        # OpenAI, Anthropic, Google clients + base/fallback

frontend/
├── src/
│   ├── pages/                 # 16 pages: Dashboard, Analysis, Chart, MockTrading, Portfolio,
│   │                          #   Watchlist, Orders, Performance, Backtest, Alerts, ABTesting,
│   │                          #   Logs, Settings, Profile, Admin, Login
│   ├── components/
│   │   ├── Layout.tsx         # App shell with sidebar nav + Portfolio Assistant widget
│   │   ├── assistant/
│   │   │   └── PortfolioAssistant.tsx  # Floating AI chat widget (bottom-right, all pages)
│   │   ├── analysis/          # AnalysisChatWidget, report viewers
│   │   └── chart/             # ChartSearch, TechnicalControls, CustomIndicatorPane, AnalysisDetailSidebar
│   ├── contexts/              # Auth, Theme, Language
│   ├── hooks/                 # API queries, local storage
│   ├── i18n/                  # Translation dicts (en, tr)
│   ├── App.tsx
│   └── main.tsx
├── vite.config.ts
├── tailwind.config.js
└── package.json

docs/
├── introduction.md
├── installation.md
├── configuration.md
├── developer_guide.md          # Custom analysts, WebSocket, i18n, cron, advanced features
└── architecture/
    ├── overview.md
    ├── backend.md
    ├── multi_agent_system.md
    ├── modular_tool_system.md
    ├── api-keys.md             # Per-user encrypted API key storage
    ├── rbac.md                 # Owner/Admin/User roles
    ├── page-permissions.md     # Feature flags per page
    ├── resilience.md           # Retry logic & fallbacks
    └── multi-tenant.md
```

---

## 🚀 Deployment

**Linux Installer (recommended):**
```bash
sudo bash deploy/install.sh
# Creates: systemd service, venv, PostgreSQL db, .env, frontend build
```

**Docker Compose:**
```bash
docker-compose up -d --build
```

**Manual:**
1. PostgreSQL running (create `tradingagents` db)
2. Python venv + `pip install -r backend/requirements.txt`
3. Frontend: `npm install && npm run build`
4. `.env` configured
5. `uvicorn backend.main:app --host 0.0.0.0 --port 8000`

**Self-Updater:**
Backend polls `origin/main`, notifies UI, triggers `deploy/update.sh` (git pull, pip install, npm build, systemctl restart).

---

## 🧠 Developer Extensibility

### Custom Analysts

See `docs/developer_guide.md` section 1. Register with `@register_analyst` decorator, add to `AGENTS` list in `agent_catalog.py`.

### Custom Tools

Register in `agents/tools/builtin/`, import in `agents/tools/bootstrap.py`, add i18n in `frontend/src/i18n/tools.ts`.

### Custom Personas

Register an `InvestorPersona(...)` in `trading_agents/personas.py` (key, label, description, PM instruction block). The Portfolio Manager prompt and the `/api/meta.investor_personas` dropdown pick it up automatically.

### WebSocket Streaming

Hook `AnalysisEmitter` in `graph/trading_graph.py` callbacks or `services/analysis/emitter.py`.

### Advanced Features

See `docs/developer_guide.md` sections 5A–5I for:
- Interactive Q&A over reports
- Streaming debate bubbles
- Vision-based pattern recognition
- Multi-timeframe alignment
- Custom indicators
- Chart annotations
- Fractional shares
- etc.

---

## 📚 Reference

**Key Files:**
- `backend/main.py` — Entry point, lifespan hooks
- `backend/trading_agents/graph/trading_graph.py` — LangGraph runner
- `backend/trading_agents/agents/hierarchy.py` — Kill-switches, LLM fallback
- `backend/trading_agents/agent_catalog.py` — Agent metadata, hierarchy tree
- `backend/services/analysis_service.py` — Analysis orchestration
- `backend/services/memory_service.py` — Pinecone episodic memory interface
- `backend/services/portfolio_assistant_service.py` — Portfolio assistant LLM + tools
- `backend/services/formula_assist_service.py` — AI chart formula generation
- `backend/core/memory/` — Vector store abstractions
- `frontend/src/components/assistant/PortfolioAssistant.tsx` — Floating AI chat widget

**Documentation:**
- [docs/introduction.md](docs/introduction.md) — Feature overview
- [docs/architecture/backend.md](docs/architecture/backend.md) — Backend conventions (dense reference)
- [docs/architecture/multi_agent_system.md](docs/architecture/multi_agent_system.md) — Agent workflows
- [docs/architecture/modular_tool_system.md](docs/architecture/modular_tool_system.md) — Tool system
- [docs/architecture/resilience.md](docs/architecture/resilience.md) — Retry & fallback logic
- [docs/architecture/rbac.md](docs/architecture/rbac.md) — Role-based access control
- [docs/architecture/page-permissions.md](docs/architecture/page-permissions.md) — Page-level feature flags
- [docs/architecture/api-keys.md](docs/architecture/api-keys.md) — Per-user encrypted API keys
- [docs/configuration.md](docs/configuration.md) — .env setup & runtime settings
- [docs/developer_guide.md](docs/developer_guide.md) — Custom analysts, WebSocket, i18n, cron, advanced features
- [backend/core/memory/README.md](backend/core/memory/README.md) — Vector memory details
- [backend/README.md](backend/README.md) — Backend architecture
- [backend/trading_agents/README.md](backend/trading_agents/README.md) — Multi-agent system
- [frontend/README.md](frontend/README.md) — React SPA
- [deploy/README.md](deploy/README.md) — Installation & systemd

---

## 💡 When Working on This Codebase

- **Understand the graph first.** Read `agents/main/*.py` to see how the 6 nodes work.
- **Follow layering.** Keep `api → services → repositories → models` unidirectional.
- **Scope all queries.** Apply `scope_to_user()` in repositories.
- **Async throughout.** No sync database calls in async context.
- **Test in the UI.** Spin up full stack and run an analysis to verify changes.
- **Know the hierarchy.** Check `agent_catalog.py` parent links and kill-switch logic.
- **Memory is optional.** Pinecone is per-user, opt-in; remember off by default.
- **Configuration is database-driven.** Only infrastructure secrets in `.env`.
- **Guard against IDOR.** Every data query must check user ownership.
- **One uvicorn worker.** Never add `--workers`; APScheduler + WebSockets break.
- **Check the docs.** Before deep work, read the relevant `docs/architecture/` file.

---

## ✅ Maintenance Note

Last validated against the codebase on 2026-06-13 (READMEs, architecture docs, and direct code exploration; analyst count, agent_catalog/personas single-sources, Redis scaling layer, and file paths cross-checked against the tree). Added: chart page + AI formula assistant, Portfolio Assistant widget. If behaviour described here diverges from the code, trust the code — and update this file in the same change.
