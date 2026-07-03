# Project: TradingAgents Backend Refactoring and Optimization

## Architecture
The backend uses a standard FastAPI structure:
- **FastAPI Controllers (`api/`)**: Handle incoming requests, validation (via Pydantic), and call business services.
- **Business Services (`services/`)**: Implement core business logic, orchestrate repository calls, handle third-party APIs.
- **Repositories (`repositories/`)**: Execute database queries using SQLAlchemy.
- **Models (`models/`)**: Define the database schema (SQLAlchemy).
- **Schemas (`schemas/`)**: Define data serialization/validation schemas (Pydantic).
- **Core (`core/`)**: Core application components (settings, database session, redis).

## Code Layout
- `backend/api/` — API routers
- `backend/services/` — Business logic
- `backend/repositories/` — DB query logic
- `backend/models/` — SQLAlchemy models
- `backend/schemas/` — Pydantic models
- `backend/core/` — Core configs

## Completed Milestones

| # | Name | Scope |
|---|------|-------|
| 1 | Consolidate Duplicates | Merge duplicate RSI, Redis, sector lookups, settings repositories, LangChain callbacks, and OrderRequest |
| 2 | Repos-Service Pattern | Move direct database queries from routers into repositories and services |
| 3 | Critical Bugs Fixes | Fix simulation portfolio concurrency, GET idempotency, order validation, and price alert loop bugs |

## Interface Contracts
### `services/indicator_service.py` ↔ Other Services
- The consolidated RSI calculation is hosted in `indicator_service.py` as `calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series` or a similar unified function.
### `core/redis_bus.py` ↔ Other Services
- Expose a single unified Redis/ARQ teardown method.
### `services/sector_service.py`
- Create a new unified `SectorService` or module `sector_resolver.py` that handles `yfinance` caching/resolution for sector queries.
### `repositories/`
- Standardize agent and tool settings queries into a single base repository or helper, or keep them distinct but call a single generic query helper.
