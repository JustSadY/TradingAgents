# CLAUDE.md

This file provides implementation guidance for AI coding agents working in the TradingAgents repository. Treat current source code and maintained architecture documentation as authoritative. Historical audits, patch notes, and upgrade snapshots are evidence about prior states, not current architecture contracts.

## Start here

- [`docs/introduction.md`](docs/introduction.md) — documentation index and current system model.
- [`docs/architecture/overview.md`](docs/architecture/overview.md) — runtime architecture.
- [`backend/README.md`](backend/README.md) — backend layering and API conventions.
- [`backend/trading_agents/README.md`](backend/trading_agents/README.md) — multi-agent engine, tools, and LLM clients.
- [`docs/configuration.md`](docs/configuration.md) — environment/runtime configuration.
- [`docs/installation.md`](docs/installation.md) — Linux, Docker, and local setup.

Historical files such as `docs/AUDIT_2026-08-04.md`, `docs/PATCH_NOTES_2026-08-04.md`, and `docs/VALIDATION_2026-08-04.md` are snapshots only. Do not resurrect behavior from them unless the current code and migration history require it.

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

The current top-level analysis graph is strategy-aware and linear:

```text
START
  ↓
Strategy Context Loader
  ↓
Analysis Planner
  ↓
Market Intelligence
  ↓
Agent Q&A
  ↓
Research Manager
  ↓
Risk Debate
  ↓
Strategy Reconciler
  ↓
Portfolio Manager
  ↓
Decision Stability Controller
  ↓
END
```

Analysts, researchers, and risk agents produce evidence, debate, and guardrails. The **Portfolio Manager is the sole AI proposal authority**: it converts the evidence into one structured raw trade proposal. That proposal is not automatically executable.

The deterministic **Decision Stability Controller is the final graph stage**. When enforcement applies it decides which proposal becomes canonical, may reject a change, downgrade to Hold, or permit only a risk-reduction action. Application-side cash, exposure, concentration, broker, trading-mode, and other deterministic execution controls still apply after the graph.

Do not describe the Portfolio Manager as the unconditional final execution authority, and do not reintroduce the retired Trader agent as a live decision source.

Portfolio rebalancing sits outside this graph. `portfolio_rebalance_planner` computes actions, quantities, issues, and health scores in exact decimal arithmetic; the model writes summaries/rationales rather than authoritative numeric execution values.

---

## Backend layering

Keep dependencies flowing in this direction:

```text
api → services → repositories → models
```

### `backend/api/`

Routers should remain thin:

- validate request shape;
- apply authentication/authorization dependencies;
- call services;
- map service errors to HTTP responses;
- return response schemas.

Do not place substantial business logic, external network calls, token/session orchestration, or ad-hoc SQL directly in route handlers. Declare static FastAPI paths before overlapping parameterized paths to avoid route shadowing.

### `backend/services/`

Services own business logic, orchestration, vendor IO, calculations, auth/session workflows, analysis execution, notifications, trading workflows, updates, and scheduling.

Services may depend on repositories, models, schemas, core utilities, and the trading engine. Services must not import `backend.api`.

### `backend/repositories/`

Repositories/shared query helpers own reusable persistence logic. Preserve per-user scoping for user-owned resources and row-locking semantics where required. Do not move business decisions into repositories.

### `backend/models/` and `backend/schemas/`

- ORM persistence definitions live in `models/`.
- Pydantic request/response contracts live in `schemas/`.

For financial amounts, preserve the repository's exact-decimal conventions rather than introducing floating-point arithmetic into money/quantity/risk calculations.

---

## Database and migrations

PostgreSQL is the supported primary database and Alembic is the schema authority.

Outside production, startup upgrades PostgreSQL to Alembic head. In production the app refuses to serve a database that is not already at head, so deployment must run migrations first.

Every schema change needs a revision — additive ones included. SQLite is a development/test convenience: it builds from ORM metadata with `create_all` and has no migration path, so delete an old SQLite file to pick up model changes.

The test-suite/production split is important: tests commonly build SQLite from ORM metadata while production PostgreSQL is created by migrations. A model change with no revision can therefore pass ordinary tests and still be absent in production. `index=True`, foreign-key cascade changes, and constraint changes count as schema changes.

Check schema work against migration drift tooling before trusting it:

```bash
MIGRATION_DRIFT_DATABASE_URL=postgresql+asyncpg://postgres@localhost/ta_drift \
    uv run pytest tests/test_core/test_migration_drift.py
```

### LangGraph checkpoints

LangGraph checkpoints require PostgreSQL. `backend/trading_agents/graph/checkpointer.py` uses `PostgresSaver` / `AsyncPostgresSaver`; the old SQLite checkpoint fallback and file-import path are gone.

LangGraph owns its checkpoint tables. Saver `setup()` is idempotent/version-aware and runs once per DSN per process, so those tables are intentionally outside Alembic. Every application-owned table remains Alembic-managed.

Time Travel exposes only checkpoints compatible with the current graph topology. Historical checkpoints containing retired Trader nodes are not resumable.

---

## Multi-agent package

The engine lives under:

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

Use `backend.trading_agents.*` imports. The old top-level `tradingagents` compatibility package/alias is not the runtime contract.

### Agent hierarchy and metadata

Use the existing agent catalog/hierarchy as the source of truth for parent-child relationships, enable/disable behavior, labels, defaults, and LLM fallback resolution. Do not duplicate agent catalogs in frontend or services when `/api/meta` can publish the metadata.

### Tool system

New agent tools belong under `backend/trading_agents/agents/tools/` and should use the existing registry/settings-schema infrastructure.

Typical steps:

1. Implement the tool class/adapter.
2. Define a stable key, category, allowed analysts, defaults, and settings schema.
3. Return LangChain-compatible tool functions.
4. Register/import it through the bootstrap path.
5. Add frontend i18n labels for user-visible metadata.
6. Respect system and user-level tool access rules.

Data-vendor/service credentials belong in the tool-settings system when the tool owns them. Secret fields are persisted as Fernet ciphertext; runtime plaintext fallback for migrated tool secrets has been removed.

---

## Authentication and credentials

Access tokens are short-lived JWTs. Browser refresh credentials live in an HttpOnly cookie at the `/auth` path. Browser responses return access tokens only; do not add a refresh token back to `TokenResponse`.

The current `/auth/refresh` contract is cookie-only: refresh credentials are not accepted in the request body. Keep refresh-token rotation and replay protection in the auth-session service rather than reintroducing response-body or local-storage refresh-token compatibility.

Password hashing lives in `backend/core/password_hashing.py`. New passwords use Argon2 through `pwdlib`; bcrypt remains registered only to verify historical hashes and upgrade them to Argon2 after a successful login. Do not import password helpers through `backend.core.security`.

LLM/provider API keys are configured through the Web UI and stored encrypted in PostgreSQL. Do not reintroduce plaintext database fallbacks.

---

## Retries and error classification

`classify_error` in `llm_clients/base_client.py` is the single error taxonomy: `auth`, `quota`, `timeout`, `provider_degraded`, `transient`, `bug`. These strings are observable through metrics/events.

Three mechanisms can repeat a failed LLM call:

| Layer | Where | Default |
| --- | --- | --- |
| Node retry | `retry_call` / `guard_node` | `node_retry_attempts`, 2 attempts |
| Provider SDK retry | LangChain client `max_retries` | 0 by default |
| Provider failover | `FallbackLLM` | configured chain length |

`retry_call` is the application retry authority. Keep provider SDK retries disabled by default so node retry × SDK retry × failover does not multiply attempts unexpectedly. There is deliberately no analysis-level retry loop.

Node circuit-breaker state is shared through Redis when `REDIS_URL` is configured and falls back to process memory if Redis is unavailable.

---

## LLM providers

Provider/model source of truth:

```text
backend/trading_agents/llm_clients/registry.py
```

The frontend consumes the model catalog through:

```text
GET /api/settings/llm-catalog
```

Do not scatter provider/model lists across frontend components.

Model cost lookup is owned by `backend/core/model_pricing.py`, which uses LiteLLM's pinned catalog plus explicit overrides/fallback behavior. Do not restore a second hand-maintained pricing table in a service.

---

## Analysis execution and WebSockets

### Inline mode

```ini
ANALYSIS_QUEUE_MODE=inline
```

Analyses run in the FastAPI process.

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

Do not put JWTs into WebSocket query strings. Preserve the subprotocol-based authentication design and periodic authorization revalidation.

### Analysis event vocabulary

Socket event types are declared once in `backend/schemas/analysis_events.py` and published through `/api/meta`. The generated TypeScript client and frontend analysis-event tests use that vocabulary.

A new event type needs:

1. the backend event literal;
2. a frontend handler branch;
3. inclusion in `HANDLED_ANALYSIS_EVENTS`.

---

## Development setup

### Backend

```bash
cd backend
uv sync --frozen
cp ../.env.example ../.env
uv run uvicorn backend.main:app --reload --port 8000
```

`backend/pyproject.toml` is the hand-edited dependency manifest and `backend/uv.lock` is the lock. Docker and deploy scripts install with `uv sync --frozen`; do not create a second dependency source.

To change a dependency:

```bash
cd backend
# edit pyproject.toml
uv lock
```

Commit the lock update with the manifest.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api`, `/auth`, and `/ws` to FastAPI.

### Quality checks

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Backend:

```bash
cd backend
ruff check .
ruff format --check
```

Run focused subsystem tests in addition to lint/build. Schema changes also need Alembic validation; API-contract changes should regenerate the frontend client rather than leaving generated models stale.

---

## Deployment

### Linux/systemd

```bash
sudo bash deploy/install.sh
```

Production frontend assets are built into `frontend/dist` and served by FastAPI in the Linux/systemd topology. The dashboard updater is a live subsystem; do not delete isolated updater/version/deploy compatibility pieces without redesigning the deployment contract as a whole.

### Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

The Compose topology includes PostgreSQL, Redis, backend, arq worker, frontend/nginx, Prometheus, postgres-exporter, and redis-exporter.

---

## Documentation discipline

When code changes architecture, configuration, setup commands, endpoint ownership, provider registration, worker behavior, agent authority, persistence compatibility, or migration requirements, update the maintained documentation in the same change.

Do not document planned features as implemented. Do not preserve obsolete behavior merely because it appears in an old audit or patch note. When compatibility is still required for persisted data or external clients, document the migration/removal condition explicitly.
