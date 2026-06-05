# Backend Architecture — Agent Read-First Guide

> **Purpose of this file.** Read *this* before touching the backend instead of
> re-scanning the whole `backend/` tree. It describes the layering, where each
> kind of code lives, the conventions to follow, and the gotchas to avoid so a
> change lands consistently with the existing design. Keep it updated when the
> structure changes.

---

## 1. Big picture

FastAPI app (`backend/main.py`) exposing a REST + WebSocket API for an
AI-powered trading dashboard. It drives a vendored LangGraph multi-agent engine
(`backend/trading_agents/`), persists to PostgreSQL via async SQLAlchemy, runs
background jobs with APScheduler, and serves the built React SPA.

**Layered, one-directional dependency flow:**

```
api (routers)  →  services (business logic)  →  repositories (DB access)  →  models (ORM)
        │                  │                            │
        └── schemas (DTOs) └── core (config/db/security/ws/log)   trading_agents (AI engine)
```

**Hard rules:**
- `api/` routers stay **thin**: validate input → call a service → return a DTO. No business logic, no multi-step DB work, no external API calls in handlers.
- `services/` hold business logic/orchestration/IO/computation. They may import `repositories`, `models`, `schemas`, `core`, `trading_agents`. **Services must never import from `backend.api`** (that inversion was removed — do not reintroduce it).
- `repositories/` hold reusable DB queries only.
- `models/` (SQLAlchemy) and `schemas/` (Pydantic) hold no logic.
- `trading_agents/` is a **normal sub-package of `backend`** — imported as `backend.trading_agents.*` like everything else (see §6). It's still a cohesive subsystem with its own conventions, but it is part of the backend, not an aliased external package.

---

## 2. Directory map (what lives where)

| Path | Responsibility |
| --- | --- |
| `main.py` | App factory: lifespan (create tables, seed admin, cron, log handler), CORS, router includes, `/ws/analysis/{task_id}`, `/health`, SPA static mount. |
| `bootstrap.py` | **Import once, early.** Idempotent runtime setup: `TRADINGAGENTS_*` temp-dir env and a no-op `logging_config` stub. Any module that imports `backend.trading_agents.*` should `import backend.bootstrap` first (so the engine's env + logging are set before its modules execute). |
| `api/*.py` | One thin router per domain. `deps.py` = DI dependencies (`get_current_user`, `require_admin`, `require_page`). |
| `services/*.py` | Business logic. See §3 for the map. |
| `repositories/common.py` | `scope_to_user(query, model, user)` — the per-user ownership filter (anti-IDOR). |
| `repositories/users.py` | `get_user_by_username`, `get_user_by_id`. |
| `core/config.py` | Pydantic `Settings` from `.env` (infra secrets only — see §5). `get_settings()` is `lru_cache`d. |
| `core/database.py` | Async `engine`, `AsyncSessionLocal`, `get_db()` (commits on success / rolls back on error), `Base`, `create_all_tables()`, and the **`MONEY`** column type. |
| `core/migrations.py` | Additive, idempotent schema migrations (no Alembic — see §5). |
| `core/security.py` | bcrypt hashing, JWT encode/decode, Fernet `encrypt_secret`/`decrypt_secret`. |
| `core/websocket.py` | `ws_manager` for real-time progress feeds. |
| `core/log_handler.py`, `log_redaction.py` | Async DB log handler + secret redaction. |
| `models/*.py` | SQLAlchemy ORM (`User`, `Portfolio`/`Holding`, `Order`, `AnalysisResult`, `AppSettings`, `PriceAlert`, …). |
| `schemas/*.py` | Pydantic request/response DTOs. |
| `trading_agents/` | LangGraph engine (agents, graph, dataflows, llm_clients, mock_trading). |

---

## 3. Services map (the business layer)

| Service | Owns |
| --- | --- |
| `analysis_service` | Multi-agent run orchestration. **`run_analysis_task` / `run_portfolio_task`** are the background entrypoints the routes schedule (own their session, persist, place order, emit WS errors). `run_analysis` does the actual graph run. |
| `settings_service` | `get_or_create_settings`, `settings_to_read` (AppSettings→DTO, single source of truth), `apply_settings_update`. **Use this everywhere** for AppSettings — do not re-add a helper in a router. |
| `trading_orchestrator` | `place_signal_order` — maps a signal to a sized paper order against the portfolio's available cash. Shared by the analysis flow and cron. |
| `market_service` | OHLCV + indicators, custom-formula series, sentiment history. Validates tickers; runs blocking yfinance/pandas in `asyncio.to_thread`. Raises `MarketDataError(status_code)`. |
| `news_service` | TTL-cached news feed (off the event loop). |
| `analysis_stats_service` | Cost estimate, A/B comparison, signal performance. Houses the single `MODEL_COST_PER_1K` table. |
| `report_chat_service` | Report-grounded Q&A: ownership check, context build, LLM call, persistence. |
| `mock_trading_service` | Paper-trading ledger engine (portfolio/holdings/orders, live valuation). |
| `cron_service` | APScheduler: per-user watchlist scans + alert checks + perf backfill. `get_cron_service()` / `init_cron_service()`. |
| `performance_service` | Return backfill + analyst attribution stats. |
| `alert_service`, `notification_service`, `update_service`, `user_service`, `annotation_service`, `indicator_service`, `execution/` | Alerts, webhooks/notifications, self-update, API-key crypto helpers, chart-annotation extraction, safe formula eval, trader abstraction (`get_trader`, `SimulationTrader`). |

---

## 4. How to make common changes (recipes)

**Add an endpoint:** add a thin handler to the relevant `api/<domain>.py` →
put the logic in (or extend) the matching `services/<domain>_service.py` →
add request/response DTOs in `schemas/`. Reuse `Depends(get_current_user)` /
`require_admin` / `require_page("<key>")` for auth. For "list/get my X", scope
the query with `repositories.common.scope_to_user(q, Model, current_user)`
instead of hand-writing the `if not is_admin` filter.

**Add a model/column:** add the column to the `models/*.py` class **and** append
a `(table, column, type)` tuple to `core/migrations.py::_NEW_COLUMNS` so existing
databases get it on startup. For money/price/quantity use the `MONEY` type from
`core.database` (see §5), not `Float`.

**Add an AppSettings field:** add it to the model + `_NEW_COLUMNS`, to
`schemas/settings.py`, and to `settings_service.settings_to_read`.

**Long-running work from a route:** don't `await` it in the handler. Add a
`*_task` coroutine to the service and schedule it via `BackgroundTasks`
(pattern: `analysis_service.run_analysis_task`). Background tasks open their own
`AsyncSessionLocal`.

**Add an analyst:** declare graph wiring + tools with `@register_analyst` in
`trading_agents/agents/sub/analysts/<name>.py` (reuse `run_tool_analyst` from
`agents/runtime/analyst_node_factory.py` for the standard tool-using scaffold),
import the module in `graph/setup.py`, and add the selection metadata
(label/description/default) to `trading_agents/analyst_catalog.py`. The frontend
picks it up via `/api/meta` — no frontend edit. (See `docs/developer_guide.md`.)

**Add an investor persona:** add one `InvestorPersona(...)` to
`trading_agents/personas.py` (key + label + description + PM instruction block).
The Portfolio Manager and `/api/meta.investor_personas` pick it up automatically.

**Anything touching the engine:** ensure `import backend.bootstrap` has run;
import engine modules lazily inside functions (they pull heavy deps).

---

## 5. Conventions & gotchas (read before changing infra)

- **No Alembic.** Migrations are additive only, applied on startup:
  `core/migrations.apply_column_migrations` (`ADD COLUMN IF NOT EXISTS`) and
  `apply_type_migrations` (float→`NUMERIC(20,8)` for money columns on Postgres).
  Renames / drops / non-additive type changes must be done with manual SQL.
- **Money columns use `MONEY = Numeric(20, 8, asdecimal=False)`** (from
  `core.database`): exact decimal storage, but Python values stay `float` so the
  trading arithmetic is plain float. **Do not** mix in `Decimal` ad-hoc — moving
  to `asdecimal=True` end-to-end is a deliberate, separate change that needs a
  live-DB test pass.
- **Route ordering:** in a router, declare **static paths before dynamic
  `/{id}` paths**. FastAPI matches in registration order; a `GET /{id:int}`
  placed first will shadow `GET /literal` and return 422. (This bit us once.)
- **Auth router prefix is `/auth`** (login/refresh), everything else is `/api/*`.
- **`.env` holds infra secrets only** (`SECRET_KEY`, `ADMIN_*`, `DATABASE_URL`,
  `ENCRYPTION_KEY`, `CORS_ORIGINS`). LLM provider keys, data-vendor keys and
  SearXNG are configured at runtime in the Web UI and stored (encrypted) in the
  DB — never read from the environment by `core/config.py`.
- **Passwords** are hashed with `bcrypt` directly (not passlib).
- **`get_db` auto-commits** on a clean return and rolls back on exception, so a
  route doesn't strictly need an explicit commit — but background-task sessions
  manage their own commit/rollback.
- The OpenAPI page at **`/docs`** is the always-current source of truth for the
  HTTP contract.

---

## 6. The `trading_agents` engine (subsystem)

- Imported as **`backend.trading_agents.*`** — an ordinary backend sub-package
  (the old top-level `tradingagents` alias and its meta-path finder were
  removed; `import tradingagents` no longer resolves). Internal modules use
  absolute `backend.trading_agents...` imports; if you add a module, follow the
  same prefix.
- Structure: `graph/` (LangGraph wiring — `trading_graph.py`, `setup.py`,
  `conditional_logic.py`, checkpointer), `agents/` (the sub-agents under `sub/`
  [analysts, managers, researchers, risk_mgmt, trader], execution runtime helpers
  in `runtime/`, tool data helpers in `data/`, shared utilities in `utils/` +
  `analyst_registry.py` + `schemas.py`), `dataflows/` (vendor-routed data via
  `interface.py`), `llm_clients/` (provider factory), `mock_trading/`.
- **Engine-root single-source modules** (dependency-free, importable by the
  backend without the heavy `agents` chain): `personas.py` (investor personas),
  `analyst_catalog.py` (analyst selection metadata). `agents/runtime/` holds shared
  scaffolds: `analyst_node_factory.run_tool_analyst` (the common tool-using
  analyst turn) and `report_aggregator.build_resources`.
- **High-risk zone:** graph compilation depends on the analyst registry's dynamic
  `ConditionalLogic` method injection and on agent state field names. Do **not**
  rewire the graph, rename registry methods, or change state field names without
  tests — these break graph compilation silently. Prefer additive, isolated
  changes (e.g. shared helpers like `agents/runtime/report_aggregator.py`).
- **Env note:** the engine targets `langchain-core` 0.3.x. On newer 1.x the
  `@tool` decorator rejects functions without docstrings, so the `agents`
  subpackage may fail to import in a mismatched environment — that's a
  dependency-version issue, not a code bug. Verify engine edits with
  `python -m py_compile`.

---

## 7. Verifying a change locally

```bash
pip install -r backend/requirements.txt          # langchain-core may resolve to 1.x; see §6
python -c "import backend.main; print('import OK')"   # app must always import
uvicorn backend.main:app --reload --port 8000     # /docs for the live contract
```

For DB-touching logic without Postgres, point `DATABASE_URL` at
`sqlite+aiosqlite:///:memory:`, create tables, and exercise the service
(the money/order flow was validated this way).

---

## 8. Backend is the single source of truth for UI metadata

The frontend should **fetch** option lists / labels / defaults, never hardcode
them. The backend already exposes everything the UI needs:

**`GET /api/meta`** (`core/catalog.build_meta`) returns:

| Key | Contents | Backed by |
| --- | --- | --- |
| `analysts` | `{key, label, description, default}[]` | `trading_agents/analyst_catalog.py` |
| `investor_personas` | `{value, label, description}[]` | `trading_agents/personas.py` |
| `signals` | `{value, label, tone}[]` (Buy/Overweight/Hold/Underweight/Sell) | catalog |
| `section_labels` | report-column → label map | catalog |
| `asset_types`, `languages`, `data_vendors`, `trading_modes`, `brokers` | `{value, label}[]` | catalog |
| `provider_labels` | provider id → display name | catalog |
| `effort_options` | per-provider reasoning/thinking levels (`openai`/`anthropic`/`google`) | catalog |
| `order_statuses`, `order_actions` | `{value, label, tone}[]` | catalog |
| `chart_periods` | `{value, label}[]` (matches `/api/market/ohlcv`) | catalog |

`build_meta(db, user)` is **async and user-aware**: it also returns `tools`
(from the tool registry, filtered by the user's tool/agent permissions — see §9)
and filters `analysts` to the ones the user may run.

**`GET /api/settings/llm-catalog`** returns the model dropdown per provider,
sourced from `trading_agents/llm_clients/model_catalog.py`.

**Rule:** when the UI needs a new option list, add it to `core/catalog.py`
(deriving from the engine where the engine owns the concept — e.g. personas,
analysts), surface it in `build_meta()`, and have the frontend read it. The
`tone` fields (`positive`/`neutral`/`negative`) let the UI map to colors without
hardcoding hex per signal/status.

---

## 9. Modular tool system (`trading_agents/agents/tools/`)

Agent tools are a **DB-driven plugin system** (see modular_tool_system.md).
Each tool is a `BaseAgentTool` (or a `FunctionToolAdapter` wrapping an existing
`@tool` function) declaring `key`, `category`, `allowed_analysts`, and a
`settings_schema` of `ToolSettingField`s. Tools self-register into the singleton
`registry` (auto-loaded via `agents/tools/bootstrap.py`).

- **Settings & access** live in DB tables (`models/tool_settings.py`):
  `AgentToolSetting` (server/user scoped field values + enablement),
  `UserAgentAccess`, `UserToolAccess`, `UserToolFieldAccess`. Services:
  `tool_settings_service.py` (resolve/update + `build_global_runtime_context`)
  and `tool_access_service.py` (permission maps).
- **Runtime:** `analysis_service` calls `build_global_runtime_context(db, user_id)`
  and puts it on `config["runtime_tool_context"]`; `_inject_tool_credentials`
  copies the relevant secrets into the engine config, and the graph filters
  tools per analyst via `_filter_tools_for_analyst` before binding.
- **Credential convention — important:** data-vendor / external-service config
  (Reddit `client_id`/`secret`/`user_agent`, SearXNG `searxng_url`, Alpha Vantage
  `alpha_vantage_api_key`) lives **only** in the tool system (as `ToolSettingField`s
  on the `reddit_sentiment` / `search_web` / `core_stock_data` tools), is injected
  at runtime, and is read in the engine via `get_config()`. Do **not** re-add these
  as `SystemSettings`/`system_settings` columns — the old orphaned columns were
  removed from `core/migrations.py`.
.
