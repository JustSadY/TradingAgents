# CLAUDE.md

This file provides concise implementation guidance for AI coding agents working in the TradingAgents repository. Treat the current source code and the maintained architecture docs as authoritative; do not resurrect roadmap-only behavior from historical audit or patch-note files.

## Start here

- [`docs/introduction.md`](docs/introduction.md) — documentation index and current system model.
- [`docs/architecture/overview.md`](docs/architecture/overview.md) — current runtime architecture.
- [`backend/README.md`](backend/README.md) — backend layering and API conventions.
- [`backend/trading_agents/README.md`](backend/trading_agents/README.md) — multi-agent engine, tools, and LLM clients.
- [`docs/configuration.md`](docs/configuration.md) — environment/runtime configuration.
- [`docs/installation.md`](docs/installation.md) — Linux, Docker, and local setup.

Historical files such as `docs/AUDIT_2026-08-04.md`, `docs/PATCH_NOTES_2026-08-04.md`, and `docs/VALIDATION_2026-08-04.md` are snapshots, not the current architecture contract.

---

## Current architecture

TradingAgents consists of:

- React 19 + TypeScript + Vite frontend.
- FastAPI backend with async SQLAlchemy/`asyncpg` and PostgreSQL.
- LangGraph multi-agent analysis engine under `backend/trading_agents/`.
- Optional Redis + `arq` worker for out-of-process analyses.
- Authenticated WebSocket progress streaming.
- Encrypted user/provider credentials stored in PostgreSQL.
- RBAC, per-user settings, tool permissions, scheduling, alerts, paper trading, and optional broker execution.

### Decision flow

```text
START
  ↓
Market Intelligence / enabled analyst plugins
  ↓
Cross-examination + research synthesis / Bull-Bear debate
  ↓
Risk Debate (aggressive / conservative / neutral evidence)
  ↓
Portfolio Manager (sole final structured investment decision)
  ↓
Validation + deterministic application-side execution controls
  ↓
END
```

The current analyst catalog contains 12 specialized analyst plugins. Analysts, researchers, and risk agents produce evidence. The **Portfolio Manager is the only agent with final decision authority**. Risk agents do not independently own final Buy/Sell/Hold direction, allocation, quantity, leverage, stop, or target.

Agent output is still not equivalent to an executable order. Application-side cash, exposure, concentration, risk, broker, and trading-mode controls can reduce or reject the final proposal.

Portfolio rebalancing sits outside this graph and follows the same rule more
strictly: `portfolio_rebalance_planner` computes every action, quantity, issue
and health score in exact decimal arithmetic, and the model only writes the
summary and per-trade rationale. Do not move a number back into the prompt —
these suggestions feed an order form.

---

## Backend layering

Keep dependencies flowing in this direction:

```text
api → services → repositories → models
```

### `backend/api/`

Routers should remain thin:

- validate requests
- apply authentication/authorization dependencies
- call services
- return response schemas

Do not place substantial business logic, external network calls, or ad-hoc database orchestration directly in route handlers.

Declare static FastAPI paths before overlapping parameterized paths to avoid route shadowing.

### `backend/services/`

Services own business logic, orchestration, vendor IO, calculations, analysis execution, notifications, trading workflows, updates, and scheduling.

Do not block the event loop with heavy synchronous work. Use the existing async APIs or appropriate `asyncio.to_thread`/worker boundaries where needed.

### `backend/repositories/`

Repositories/shared query helpers own repeated persistence logic. Preserve per-user scoping for user-owned resources; do not introduce IDOR regressions.

### `backend/models/` and `backend/schemas/`

- ORM persistence definitions live in `models/`.
- Pydantic request/response contracts live in `schemas/`.

For financial amounts, preserve the repository's exact-decimal conventions rather than introducing floating-point arithmetic into money/quantity/risk calculations.

---

## Database and migrations

PostgreSQL is the supported primary database.

On startup, the app creates missing tables and can apply supported additive/idempotent column migrations. Once a database is explicitly managed by Alembic, startup migration logic defers to Alembic.

Do not treat startup additive migration as a replacement for destructive migrations. Renames, drops, incompatible type changes, and data transforms need an explicit migration plan.

### LangGraph checkpoints

Analysis checkpoints are stored in the application database when `DATABASE_URL`
points at PostgreSQL, so a run can resume on any worker or pod and one backup
policy covers both. A non-PostgreSQL `DATABASE_URL` (the test suite, or a SQLite
deployment) falls back to per-analysis SQLite files under the data cache dir.

LangGraph owns the checkpoint schema; its `setup()` is idempotent and runs once
per process, so those tables are deliberately not in Alembic. Every application
table still belongs to Alembic.

---

## Multi-agent package

The agent engine lives under:

```text
backend/trading_agents/
├── agent_catalog.py
├── personas.py
├── agents/
│   ├── analyst_registry.py
│   ├── hierarchy.py
│   ├── main/
│   ├── sub/
│   ├── runtime/
│   └── tools/
├── graph/
├── dataflows/
└── llm_clients/
```

### Agent hierarchy

Use the existing agent catalog/hierarchy as the source of truth for parent-child relationships, enable/disable behavior, and LLM fallback resolution. Do not duplicate agent catalogs in UI or service code when metadata can be consumed from the existing source.

### Tool system

New agent tools belong under `backend/trading_agents/agents/tools/` and should use the existing registry and settings-schema infrastructure.

Typical steps:

1. Implement the tool class/adapter.
2. Define stable key, category, allowed analysts, defaults, and settings schema.
3. Return LangChain-compatible tool functions.
4. Register/import it through the bootstrap path.
5. Add frontend i18n labels for user-visible metadata.
6. Respect system and user-level tool access rules.

Do not hardcode duplicate settings controls in React when `/api/meta`/tool metadata can drive them.

---

## Retries and error classification

`classify_error` in `llm_clients/base_client.py` is the **single** error
taxonomy: `auth`, `quota`, `timeout`, `provider_degraded`, `transient`, `bug`.
Those strings are emitted as Prometheus labels (`NODE_ERRORS_BY_TYPE`) and on
the analysis WebSocket, so changing one is an observable change. `resilience`
re-exports it; do not add a second classifier.

Three things can repeat a failed LLM call. Know which one you are changing:

| Layer | Where | Default |
| --- | --- | --- |
| Node retry | `retry_call` / `guard_node` | `node_retry_attempts`, 2 attempts |
| Provider SDK retry | LangChain client `max_retries` | **0** — `SDK_RETRIES`, set on every client |
| Provider failover | `FallbackLLM` | length of the configured chain |

`retry_call` is the single retry authority. LangChain clients default to ~2
internal retries of their own; leaving that unset multiplied with the node
attempts and the fallback chain, so the engine now pins it to 0. An explicit
`max_retries` in agent settings still wins. There is deliberately **no**
analysis-level retry: `_maybe_retry_analysis` returns `False` on purpose.

Node circuit-breaker state lives in `agents/runtime/circuit_breaker.py`. It is
shared through Redis when `REDIS_URL` is set, so one worker's observation of a
failing provider protects the others, and falls back to process memory
otherwise. A Redis outage degrades to local counting rather than failing nodes.

## LLM providers

The provider/model source of truth is:

```text
backend/trading_agents/llm_clients/registry.py
```

The UI consumes the catalog through:

```text
GET /api/settings/llm-catalog
```

Supported providers are registered centrally. Provider-specific reasoning controls should be mapped through the LLM client layer rather than scattered through agent prompts or frontend code.

### API keys

LLM and normal data-provider keys are **not developer `.env` values**. They are configured through the Web UI and stored encrypted in PostgreSQL.

The root `.env` is primarily for infrastructure configuration such as:

- `SECRET_KEY`
- `DATABASE_URL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD_HASH`
- `ENCRYPTION_KEY`
- `CORS_ORIGINS`
- optional Redis/worker settings
- observability/proxy/server-managed integration settings

Use `.env.example` and `docs/configuration.md` as the current reference.

---

## Analysis execution and WebSockets

### Inline mode

```ini
ANALYSIS_QUEUE_MODE=inline
```

Analyses run inside the FastAPI process.

### Worker mode

```ini
REDIS_URL=redis://localhost:6379/0
ANALYSIS_QUEUE_MODE=worker
```

Analyses are queued to `arq` and executed by:

```bash
arq backend.worker.WorkerSettings
```

Redis also provides cross-process event fan-out, task ownership, and cancellation support.

### WebSocket auth

Analysis progress is streamed through:

```text
/ws/analysis/{task_id}
```

Do not put JWTs into WebSocket query strings. Preserve the existing subprotocol-based authentication design and `tradingagents.v1` application protocol.

---

## Development setup

### Backend

```bash
cd backend
uv sync --frozen
cp ../.env.example ../.env
uv run uvicorn backend.main:app --reload --port 8000
```

### Dependencies

`backend/pyproject.toml` is the single hand-edited dependency manifest, locked by
`backend/uv.lock`. There is no second dependency source: Docker, `deploy/install.sh`
and `deploy/update.sh` all install with `uv sync --frozen`, so nothing can drift
out of the lock.

To change a dependency:

```bash
cd backend
# edit pyproject.toml, then:
uv lock
```

Commit the updated lock alongside the manifest. `uv lock --check` fails if the
two disagree, and every install path runs it before syncing.

Configure infrastructure values such as `DATABASE_URL`, `SECRET_KEY`, and `ENCRYPTION_KEY` in `.env` as needed. Configure LLM/provider keys after login through the Web UI, not in `.env`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite development server runs at `http://localhost:5173` and proxies `/api`, `/auth`, and `/ws` to FastAPI on port `8000`.

### Quality checks

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Backend Ruff configuration is in `backend/pyproject.toml`:

```bash
cd backend
ruff check .
ruff format --check
```

Run focused tests for the subsystem you modify in addition to lint/build checks.

---

## Deployment

### Linux/systemd

```bash
sudo bash deploy/install.sh
```

Production frontend assets are built into `frontend/dist` and served by FastAPI in the Linux/systemd topology. The dashboard updater uses the repository's managed update flow; see `deploy/README.md`.

### Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

The current Compose topology contains PostgreSQL, Redis, backend, arq worker, frontend/nginx, Prometheus, postgres-exporter, and redis-exporter.

`DB_PASSWORD` must be set for the current Compose stack. Do not expose loopback-bound monitoring ports publicly without an authenticated reverse proxy or VPN.

---

## Documentation discipline

When a code change alters architecture, configuration, setup commands, endpoint ownership, provider registration, worker behavior, or agent authority, update the relevant maintained `.md` file in the same change.

Do not document planned features as implemented. If an idea such as a new analyst, scanner, vendor integration, or automated execution subsystem does not have corresponding production code, keep it in a clearly labeled roadmap/issue rather than the architecture overview.