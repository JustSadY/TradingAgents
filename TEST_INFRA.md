# TradingAgents Backend E2E Testing Infrastructure

This document describes the End-to-End (E2E) testing framework, architecture, feature inventory, scenarios, and execution thresholds for the TradingAgents backend.

---

## 1. Testing Framework & Architecture

The E2E testing infrastructure is designed to validate the backend application in an isolated local environment using `pytest` and `pytest-asyncio`. 

### Isolation & Setup
*   **Database Redirection**: Before loading any backend code, `os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_e2e_db.sqlite"` redirects all database connections to a local test SQLite file.
*   **Database Cleanup**: On test session teardown, the SQLite database file is completely deleted, ensuring no state leakage between test sessions.
*   **FastAPI Lifespan Management**: An autouse fixture `run_app_lifespan` runs the ASGI lifespan context (`app.router.lifespan_context`) for each test, ensuring database tables are initialized, default settings seeded, and background services (like the database logger worker) are cleanly started/stopped per test.
*   **Authentication & Clients**: Helper fixtures provide automated admin and standard user tokens, along with authenticated `httpx.AsyncClient` instances (`admin_client` and `user_client`).

### Mocking Strategy (CODE_ONLY Compliant)
To ensure tests run quickly and reliably without external network dependencies, key external services are mocked in `conftest.py`:
1.  **yfinance download & history**: Redirected to return a synthetic 100-day historical `pandas.DataFrame` matching both single-ticker and MultiIndex formats.
2.  **Live Price Feeds**: `get_live_price`, `get_live_prices_batch`, and `get_live_prices_details_batch` are routed to read from a mutable global python dictionary (`LIVE_PRICES`). Tests can dynamically mutate this dictionary to trigger alert conditions or stop-loss rules.
3.  **LangGraph AI Analysis Tasks**: `run_analysis`, `run_analysis_task`, and `run_portfolio_task` are mocked to immediately write completed mock `AnalysisResult` and `MultiTickerAnalysis` rows to the database, preventing slow and failing calls to real LLM providers.
4.  **Formula Assistant**: `generate_formula` returns a static valid formula string `"(Close - SMA(20)) / STD(20)"`.
5.  **Portfolio Rebalancing Suggestions**: `get_rebalance_suggestions` is mocked to return static mock rebalance recommendations, bypassing real LLM calls.
6.  **Cron Scheduling**: `CronService.start` is patched to be a no-op, preventing cron jobs from executing concurrently during the test run.

---

## 2. Feature Inventory

The test suite covers the following 5 target features:
1.  **Simulation Portfolio**: Resetting capital, fetching portfolio stats, retrieving risk metrics, and listing holdings/orders.
2.  **Trading Execution / Auto-close**: Placements of BUY/SELL/SHORT orders, journaling notes, AI trade debriefs, and stop-loss auto-close triggers.
3.  **Technical Indicators / Screener**: Scanning universes, watchlist scans, and the formula assistant.
4.  **Price Alerts**: Creating alert rules (`above`/`below`), updating targets, checking trigger logic, and scheduling auto-analysis.
5.  **API Settings / Logs / Reports**: Modifying settings, managing watchlists, individual & portfolio analysis runs, and system logging.

---

## 3. Testing Tiers & Scenarios

The suite contains **60 test cases** structured into 4 Tiers:

*   **Tier 1: Feature Coverage (>= 5 per feature)**: Verification of standard happy paths for all 5 core features.
*   **Tier 2: Boundary & Corner Cases (>= 5 per feature)**: Stress-testing boundaries (e.g., negative or excessively high capital, invalid leverage limits, zero quantities, empty watchlists, malformed inputs).
*   **Tier 3: Cross-Feature Combinations**: Pairwise interaction tests (e.g., alert trigger scheduling auto-analysis, watchlist additions propagating to screener scans, Completed analysis signals triggering auto-trades).
*   **Tier 4: Real-World Application Scenarios (>= 5 scenarios)**:
    1.  *User Onboarding and First Trade*: Watchlist setup, screener run, manual analysis, trade execution, and holding verification.
    2.  *Alert Auto-Analysis Lifecycle*: Creating price alerts, triggering them by crossing, verifying status updates, and checking spawned analysis results.
    3.  *Portfolio Leverage Rebalance*: Resetting portfolio, placing leveraged trades, checking stats, retrieving rebalance suggestions, and saving notes.
    4.  *Stop-Loss Breach Auto-Close*: Buying stock, manually defining stop-loss, shifting live price, running monitor, and verifying closed holdings.
    5.  *Time-Travel Rollback and Resume*: Generating analysis checkpoints, running time-travel rollback with state updates, and resuming background execution.

---

## 4. Thresholds and Validation

*   **Target Coverage**: 100% of defined Happy Paths and Boundary conditions.
*   **API Response Thresholds**:
    *   Success status codes must match: `200 OK`, `201 Created`, or `204 No Content`.
    *   Validation failures must yield: `422 Unprocessable Entity`.
    *   Access violations must yield: `403 Forbidden` or `401 Unauthorized`.
    *   Non-existent resources must yield: `404 Not Found`.
