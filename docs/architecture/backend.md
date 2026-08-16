# Backend Architecture — Read-First Guide

This file describes the current backend implementation and the boundaries new changes must preserve.

## Layering

```text
api routers
    ↓
services / application orchestration
    ↓
repositories / reusable database access
    ↓
SQLAlchemy models

schemas = HTTP DTOs
core    = infrastructure/security/database/runtime primitives
trading_agents = internal LangGraph analysis subsystem
```

Rules:

- `backend/api/` stays thin: validate/authorize, call services, map domain failures to HTTP responses.
- Multi-step database work and business policy belong in services/repositories, not routers.
- Services must not import `backend.api`.
- Reusable SQL belongs in repositories.
- User-owned reads/writes must preserve tenant/RLS ownership boundaries.
- PostgreSQL/Alembic is the production schema authority.

## Important paths

| Path | Responsibility |
| --- | --- |
| `backend/main.py` | FastAPI lifespan, router registration, WebSocket endpoint, static SPA serving. |
| `backend/bootstrap.py` | Idempotent runtime paths/import setup and optional OpenTelemetry bootstrap. |
| `backend/api/` | HTTP/WebSocket presentation layer. |
| `backend/services/` | Business logic and application orchestration. |
| `backend/repositories/` | Shared database queries and persistence helpers. |
| `backend/models/` | SQLAlchemy ORM models. |
| `backend/schemas/` | Pydantic request/response contracts. |
| `backend/core/config.py` | Infrastructure settings loaded from `.env`. |
| `backend/core/database.py` | Async SQLAlchemy engine/session, `Base`, `MONEY`, Alembic startup integration. |
| `backend/core/security.py` | JWT and token identity helpers. |
| `backend/core/password_hashing.py` | Argon2-only password hashing through `pwdlib`. |
| `backend/core/redis_bus.py`, `event_bus.py`, `task_store.py` | Optional Redis cross-process event/task infrastructure. |
| `backend/worker.py` | arq worker entrypoint for worker queue mode. |
| `backend/trading_agents/` | LangGraph analysis engine, agents, tools, dataflows and LLM clients. |

## Authentication

Passwords use Argon2 through `pwdlib`. Retired bcrypt hashes are not accepted and there is no bcrypt verification/rehash compatibility path.

Login returns a short-lived access token and sets the refresh token in the HttpOnly `ta_refresh` cookie. `/auth/refresh` is cookie-only; refresh tokens are not accepted in JSON request bodies and are not returned in response bodies.

Refresh-session creation, row locking, rotation, replay detection and revocation belong to the auth session service/repository layer rather than the router.

Provider/API secrets stored in the application database use Fernet encryption. Runtime plaintext credential fallback is not supported.

## Database and migrations

PostgreSQL is the supported application database. Alembic is the sole PostgreSQL schema authority.

- Every PostgreSQL schema change requires a new revision.
- Production startup verifies that the database is already at the current Alembic head and refuses to serve otherwise.
- Development/staging PostgreSQL upgrades to head through Alembic.
- There is no unversioned-schema auto-stamp bridge.
- SQLite is only a development/test convenience built from ORM metadata; it is not a production migration target.
- Runtime startup functions must not act as hidden historical data migrations. Backfills belong in explicit Alembic revisions.

Money/price/quantity database columns should use `MONEY = Numeric(20, 8, asdecimal=True)` from `core.database` where exact decimal storage is required.

## Settings and permissions

New users receive the current page/setting permission rows when they are created. Historical permission backfills are Alembic migrations, not startup seed loops.

Infrastructure values such as `SECRET_KEY`, `DATABASE_URL`, `ENCRYPTION_KEY`, queue/Redis configuration and production bootstrap settings live in `.env`.

LLM/provider credentials and normal runtime analysis settings live in application storage and are managed through the UI/API. Do not add provider API keys back to environment configuration unless a deliberately server-managed integration requires it.

## Analysis execution

`analysis_service` and `backend/services/analysis/` own analysis orchestration. Runs can execute inline or through the Redis/arq worker path.

The current high-level graph is:

```text
Strategy Context Loader
→ Analysis Planner
→ Market Intelligence / enabled analysts
→ Agent Q&A / cross-examination
→ Research synthesis + Bull/Bear debate + audit
→ Risk Debate (one panel node / one LLM call)
→ Strategy Reconciler
→ Portfolio Manager raw proposal
→ Decision Stability Controller
→ canonical result
```

There is no separate `risk_mgmt` sub-agent package. Aggressive, conservative and neutral risk perspectives are produced inside the single Risk Debate node and are non-executable evidence.

The canonical structured accepted decision persisted by the application is `AnalysisResult.portfolio_decision_json`. Execution/share/history/strategy-continuity code must not reconstruct a decision from chart annotations, retired Trader fields, or raw PM proposal data.

## Checkpoints and Time Travel

LangGraph checkpoints are PostgreSQL-backed through `backend/trading_agents/graph/checkpointer.py`. There is no pickle/file import path and no SQLite checkpoint fallback.

Checkpoint state is graph-internal state. Application report/history fields remain in `AnalysisResult`. Retired graph topologies are not valid resumable current checkpoints.

Time-travel/historical work must preserve point-in-time semantics. Business time and recorded/knowledge time are separate concepts; later knowledge must not leak into an earlier replay.

## Tool and analyst metadata

The backend is the source of truth for UI metadata.

- analyst hierarchy/selection metadata: `backend/trading_agents/agent_catalog.py`
- investor personas: `backend/trading_agents/personas.py`
- tool registry: `backend/trading_agents/agents/tools/`
- LLM provider/model catalog: `backend/trading_agents/llm_clients/registry.py`
- application metadata endpoint: `GET /api/meta`
- LLM catalog endpoint: `GET /api/settings/llm-catalog`

Do not duplicate backend-owned option catalogs in the frontend.

## Adding an endpoint

1. Add or reuse request/response schemas.
2. Put business behavior in a service.
3. Put reusable SQL in a repository.
4. Add a thin route with the appropriate authentication/page/admin dependency.
5. Preserve per-user ownership/RLS constraints.
6. Regenerate the frontend OpenAPI client when the HTTP schema changes.

## Adding a model/column

1. Update the ORM model.
2. Create a new Alembic revision; do not rewrite an already-applied historical migration.
3. Update API schemas/services if the field is externally visible.
4. Regenerate generated clients when the OpenAPI contract changes.
5. For removals, migrate/backfill data first and drop the old field in a later/current revision as appropriate.

## Adding an analyst or tool

Analysts register through the analyst registry and graph synchronization path. Standard tool-using analysts should reuse the current runtime factory rather than creating a parallel execution framework.

Agent-facing configurable tools belong in the modular registry. Pure data/helper functions may be imported directly when there is no registry/permission boundary to preserve.

## Deployment/update contract

The updater stages source/dependencies/frontend work before switching the live release. Database migrations follow expand/contract rules. Rollback may restore application code/assets/runtime environment, but it must not automate a destructive Alembic downgrade.

The updater still contains a one-time flat-`.venv` to release-venv transition because the current installer creates a direct `.venv`; that bridge cannot be removed until the installer and installed-base migration contract are changed together.

## Source-of-truth rule

Do not preserve old systems just because documentation or a historical test mentions them. Trace the current production call path. If compatibility is required for persisted data, move it through an explicit migration and remove the runtime compatibility path once the migration boundary is established.
