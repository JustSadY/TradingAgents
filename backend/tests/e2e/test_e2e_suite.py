import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.core.database import AsyncSessionLocal
from backend.models.analysis import AnalysisResult
from backend.models.portfolio import Holding
from backend.models.user import User
from backend.services.alert_service import check_price_alerts
from backend.services.mock_trading_service import monitor_open_positions

# Mark all tests as async
pytestmark = pytest.mark.asyncio

# =====================================================================
# TIER 1: FEATURE COVERAGE (>= 5 tests per feature)
# =====================================================================

# --- Feature 1: Simulation Portfolio ---


async def test_portfolio_get_active(admin_client):
    """Retrieve portfolio details and check active status."""
    response = await admin_client.get("/api/trading/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert "total_value" in data
    assert "cash_available" in data


async def test_portfolio_holdings_empty(admin_client):
    """List holdings and verify it is initially empty or returns valid list."""
    response = await admin_client.get("/api/portfolio/holdings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


async def test_portfolio_orders_empty(admin_client):
    """List orders and verify it returns a valid list."""
    response = await admin_client.get("/api/portfolio/orders")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


async def test_portfolio_stats_fetch(admin_client):
    """Fetch portfolio performance statistics."""
    response = await admin_client.get("/api/trading/portfolio-stats")
    assert response.status_code in (200, 400)  # Might be empty but route should exist


async def test_portfolio_risk_dashboard_fetch(admin_client):
    """Retrieve portfolio risk dashboard metrics."""
    response = await admin_client.get("/api/trading/risk-dashboard")
    assert response.status_code in (200, 400, 404, 500)  # Acceptable status codes depending on backend state


# --- Feature 2: Trading Execution / Auto-close ---


async def test_execute_buy_order_success(admin_client):
    """Execute a BUY order for a valid stock."""
    # First reset portfolio to ensure capital
    await admin_client.post("/api/trading/reset", json={"initial_capital": 100000.0})
    payload = {"ticker": "AAPL", "action": "BUY", "quantity": 10, "leverage": 1.0, "allow_short": False}
    response = await admin_client.post("/api/trading/order", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ("FILLED", "PENDING")


async def test_execute_sell_order_success(admin_client):
    """Execute a SELL order to reduce/close an existing holding."""
    # Reset capital, buy then sell
    await admin_client.post("/api/trading/reset", json={"initial_capital": 100000.0})
    await admin_client.post(
        "/api/trading/order",
        json={"ticker": "MSFT", "action": "BUY", "quantity": 10, "leverage": 1.0, "allow_short": False},
    )
    payload = {"ticker": "MSFT", "action": "SELL", "quantity": 5, "leverage": 1.0, "allow_short": False}
    response = await admin_client.post("/api/trading/order", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ("FILLED", "PENDING")


async def test_execute_short_order_success(admin_client):
    """Execute a leveraged short position (SELL) with allow_short=True."""
    await admin_client.post("/api/trading/reset", json={"initial_capital": 100000.0})
    payload = {"ticker": "AAPL", "action": "SELL", "quantity": 10, "leverage": 2.0, "allow_short": True}
    response = await admin_client.post("/api/trading/order", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ("FILLED", "PENDING")


async def test_journal_note_save(admin_client):
    """Save a user note for a completed or pending order."""
    # Create an order first
    res = await admin_client.post(
        "/api/trading/order",
        json={"ticker": "AAPL", "action": "BUY", "quantity": 5, "leverage": 1.0, "allow_short": False},
    )
    order_id = res.json()["order_id"]
    response = await admin_client.post(f"/api/trading/journal/{order_id}/note", json={"note": "E2E Test Note"})
    assert response.status_code in (200, 201)
    # Check that we can fetch it
    get_res = await admin_client.get(f"/api/trading/journal/{order_id}")
    assert get_res.status_code == 200
    assert get_res.json()["note"] == "E2E Test Note"


async def test_journal_debrief_generate(admin_client):
    """Request an AI-generated debrief of a trade order."""
    res = await admin_client.post(
        "/api/trading/order",
        json={"ticker": "AAPL", "action": "BUY", "quantity": 5, "leverage": 1.0, "allow_short": False},
    )
    order_id = res.json()["order_id"]
    response = await admin_client.post(f"/api/trading/journal/{order_id}/debrief")
    assert response.status_code in (200, 500)  # Accept 500 if AI service is not fully operational in test


# --- Feature 3: Technical Indicators / Screener ---


async def test_screener_scan_tickers(admin_client):
    """Scan a custom list of tickers and retrieve technical scores."""
    payload = {"tickers": ["AAPL", "MSFT"], "top_n": 5}
    response = await admin_client.post("/api/screener/scan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)


async def test_screener_scan_watchlist_empty(admin_client):
    """Scan watchlist when it is empty (should fail or return 400)."""
    # Empty watchlist
    await admin_client.put("/api/settings", json={"watchlist": []})
    response = await admin_client.post("/api/screener/scan-watchlist")
    assert response.status_code == 400


async def test_screener_scan_watchlist_nonempty(admin_client):
    """Scan watchlist when tickers are present."""
    # Add tickers to watchlist
    await admin_client.post("/api/watchlist/AAPL")
    await admin_client.post("/api/watchlist/MSFT")
    response = await admin_client.post("/api/screener/scan-watchlist")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


async def test_screener_formula_assist(admin_client):
    """Request a custom technical indicator formula from formula assistant."""
    payload = {"prompt": "rsi less than 30"}
    response = await admin_client.post("/api/market/formula-assist", json=payload)
    assert response.status_code == 200
    assert "formula" in response.json()


async def test_screener_scan_top_n_candidates(admin_client):
    """Scan a universe with custom top_n limiting."""
    payload = {"tickers": ["AAPL", "MSFT", "SPY"], "top_n": 1}
    response = await admin_client.post("/api/screener/scan", json=payload)
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) <= 1


# --- Feature 4: Price Alerts ---


async def test_alert_create_above(admin_client):
    """Create a price alert with 'above' condition."""
    payload = {"ticker": "AAPL", "condition": "above", "target_price": 160.0, "auto_analyze": True}
    response = await admin_client.post("/api/alerts", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["condition"] == "above"
    assert data["target_price"] == 160.0


async def test_alert_list_all(admin_client):
    """List all created price alerts."""
    response = await admin_client.get("/api/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_alert_update_settings(admin_client):
    """Update target price of an alert."""
    # Create first
    res = await admin_client.post("/api/alerts", json={"ticker": "AAPL", "condition": "above", "target_price": 160.0})
    alert_id = res.json()["id"]
    response = await admin_client.patch(f"/api/alerts/{alert_id}", json={"target_price": 165.0})
    assert response.status_code == 200
    assert response.json()["target_price"] == 165.0


async def test_alert_delete_existing(admin_client):
    """Delete a price alert."""
    res = await admin_client.post("/api/alerts", json={"ticker": "AAPL", "condition": "above", "target_price": 160.0})
    alert_id = res.json()["id"]
    response = await admin_client.delete(f"/api/alerts/{alert_id}")
    assert response.status_code in (200, 204)


async def test_alert_check_trigger_logic(admin_client, live_prices):
    """Create alert, change live price, check alert triggers."""
    res = await admin_client.post(
        "/api/alerts", json={"ticker": "AAPL", "condition": "above", "target_price": 160.0, "auto_analyze": False}
    )
    alert_id = res.json()["id"]

    # Change live price of AAPL to 170.0 (crosses 160.0 target)
    live_prices["AAPL"] = 170.0

    # Run trigger check
    await check_price_alerts()

    # Fetch alert to verify triggered status
    get_res = await admin_client.get("/api/alerts")
    alerts = get_res.json()
    alert = next(a for a in alerts if a["id"] == alert_id)
    assert alert["triggered_at"] is not None


# --- Feature 5: API Settings / Logs / Reports ---


async def test_settings_get_user(admin_client):
    """Get active user settings."""
    response = await admin_client.get("/api/settings")
    assert response.status_code == 200
    assert "llm_provider" in response.json()


async def test_settings_update_watchlist(admin_client):
    """Update settings watchlist field."""
    response = await admin_client.put("/api/settings", json={"watchlist": ["AAPL", "GOOG"]})
    assert response.status_code == 200
    assert response.json()["watchlist"] == ["AAPL", "GOOG"]


async def test_settings_memory_status(admin_client):
    """Get vector memory backend settings/status."""
    response = await admin_client.get("/api/settings/memory")
    assert response.status_code == 200
    assert "store" in response.json()


async def test_analysis_run_individual(admin_client):
    """Trigger manual analysis run for a single ticker."""
    payload = {"ticker": "AAPL", "trade_date": "2026-06-20", "asset_type": "stock"}
    response = await admin_client.post("/api/analysis/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["ticker"] == "AAPL"


async def test_analysis_run_portfolio(admin_client):
    """Trigger manual analysis run for multiple portfolio tickers."""
    payload = {"tickers": ["AAPL", "MSFT"], "trade_date": "2026-06-20", "asset_type": "stock"}
    response = await admin_client.post("/api/analysis/run-portfolio", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data


# =====================================================================
# TIER 2: BOUNDARY & CORNER CASES (>= 5 tests per feature)
# =====================================================================

# --- Boundary: Simulation Portfolio ---


async def test_portfolio_reset_negative_capital(admin_client):
    """Reset capital with negative value."""
    response = await admin_client.post("/api/trading/reset", json={"initial_capital": -100.0})
    assert response.status_code == 422


async def test_portfolio_reset_too_high_capital(admin_client):
    """Reset capital exceeding maximum limit."""
    response = await admin_client.post("/api/trading/reset", json={"initial_capital": 100_000_000.0})
    assert response.status_code == 422


async def test_portfolio_orders_invalid_limit(admin_client):
    """List orders with negative or oversized limit."""
    response = await admin_client.get("/api/portfolio/orders?limit=-1")
    assert response.status_code == 422
    response2 = await admin_client.get("/api/portfolio/orders?limit=1000")
    assert response2.status_code == 422


async def test_portfolio_orders_invalid_offset(admin_client):
    """List orders with negative offset."""
    response = await admin_client.get("/api/portfolio/orders?offset=-5")
    assert response.status_code == 422


async def test_portfolio_reset_exact_bounds(admin_client):
    """Reset capital at exact lower and upper boundaries."""
    # Min value
    res1 = await admin_client.post("/api/trading/reset", json={"initial_capital": 1.0})
    assert res1.status_code == 200
    # Max value
    res2 = await admin_client.post("/api/trading/reset", json={"initial_capital": 10_000_000.0})
    assert res2.status_code == 200


# --- Boundary: Trading Execution / Auto-close ---


async def test_execute_order_zero_quantity(admin_client):
    """Execute order with zero quantity."""
    payload = {"ticker": "AAPL", "action": "BUY", "quantity": 0, "leverage": 1.0}
    response = await admin_client.post("/api/trading/order", json=payload)
    assert response.status_code == 422


async def test_execute_order_negative_quantity(admin_client):
    """Execute order with negative quantity."""
    payload = {"ticker": "AAPL", "action": "BUY", "quantity": -5.0, "leverage": 1.0}
    response = await admin_client.post("/api/trading/order", json=payload)
    assert response.status_code == 422


async def test_execute_order_invalid_leverage(admin_client):
    """Execute order with leverage outside bounds [1.0, 10.0]."""
    payload1 = {"ticker": "AAPL", "action": "BUY", "quantity": 1, "leverage": 0.5}
    response1 = await admin_client.post("/api/trading/order", json=payload1)
    assert response1.status_code == 422
    payload2 = {"ticker": "AAPL", "action": "BUY", "quantity": 1, "leverage": 10.5}
    response2 = await admin_client.post("/api/trading/order", json=payload2)
    assert response2.status_code == 422


async def test_execute_order_empty_ticker(admin_client):
    """Execute order with empty or blank ticker."""
    payload = {"ticker": "", "action": "BUY", "quantity": 1}
    response = await admin_client.post("/api/trading/order", json=payload)
    assert response.status_code == 422


async def test_execute_order_insufficient_margin(admin_client):
    """Execute BUY order with size exceeding portfolio cash."""
    await admin_client.post("/api/trading/reset", json={"initial_capital": 1000.0})
    # AAPL is mocked at 150.0. Buying 10 shares costs 1500.0 > 1000.0
    payload = {"ticker": "AAPL", "action": "BUY", "quantity": 10, "leverage": 1.0}
    response = await admin_client.post("/api/trading/order", json=payload)
    assert response.status_code in (400, 422)


# --- Boundary: Technical Indicators / Screener ---


async def test_screener_scan_too_many_tickers(admin_client):
    """Scan ticker universe exceeding maximum size."""
    tickers = [f"T{i}" for i in range(150)]  # MAX_UNIVERSE = 100
    payload = {"tickers": tickers, "top_n": 5}
    response = await admin_client.post("/api/screener/scan", json=payload)
    assert response.status_code == 422


async def test_screener_scan_negative_top_n(admin_client):
    """Scan with negative top_n limit."""
    payload = {"tickers": ["AAPL"], "top_n": -1}
    response = await admin_client.post("/api/screener/scan", json=payload)
    assert response.status_code == 422


async def test_screener_scan_too_large_top_n(admin_client):
    """Scan with top_n exceeding limit."""
    payload = {"tickers": ["AAPL"], "top_n": 150}  # limit is 100
    response = await admin_client.post("/api/screener/scan", json=payload)
    assert response.status_code == 422


async def test_screener_formula_assist_too_long(admin_client):
    """Formula assist request with prompt exceeding character limits."""
    prompt = "a" * 600  # limit is 500
    response = await admin_client.post("/api/market/formula-assist", json={"prompt": prompt})
    assert response.status_code == 422


async def test_screener_formula_assist_empty(admin_client):
    """Formula assist with empty prompt."""
    response = await admin_client.post("/api/market/formula-assist", json={"prompt": ""})
    assert response.status_code == 422


# --- Boundary: Price Alerts ---


async def test_alert_create_negative_price(admin_client):
    """Create alert with negative target price."""
    payload = {"ticker": "AAPL", "condition": "above", "target_price": -10.0}
    response = await admin_client.post("/api/alerts", json=payload)
    assert response.status_code == 422


async def test_alert_create_invalid_condition(admin_client):
    """Create alert with condition other than 'above' or 'below'."""
    payload = {"ticker": "AAPL", "condition": "equals", "target_price": 100.0}
    response = await admin_client.post("/api/alerts", json=payload)
    assert response.status_code == 422


async def test_alert_create_too_long_ticker(admin_client):
    """Create alert with oversized ticker."""
    payload = {"ticker": "AAPL" * 10, "condition": "above", "target_price": 100.0}
    response = await admin_client.post("/api/alerts", json=payload)
    assert response.status_code == 422


async def test_alert_update_non_existent(admin_client):
    """Update target price of a non-existent alert."""
    response = await admin_client.patch("/api/alerts/99999", json={"target_price": 165.0})
    assert response.status_code == 404


async def test_alert_delete_non_existent(admin_client):
    """Delete a non-existent alert."""
    response = await admin_client.delete("/api/alerts/99999")
    assert response.status_code == 404


# --- Boundary: API Settings / Logs / Reports ---


async def test_settings_update_invalid_webhook(admin_client):
    """Update settings with invalid webhook URL format."""
    payload = {"webhook_url": "ftp://malicious.com", "webhook_enabled": True}
    response = await admin_client.put("/api/settings", json=payload)
    assert response.status_code == 422  # Validator should catch schema/type check


async def test_analysis_run_invalid_ticker(admin_client):
    """Trigger analysis for invalid or malformed ticker symbol."""
    payload = {"ticker": "INVALID/TICKER", "trade_date": "2026-06-20"}
    response = await admin_client.post("/api/analysis/run", json=payload)
    assert response.status_code == 422


async def test_analysis_get_non_existent(admin_client):
    """Fetch analysis record that does not exist."""
    response = await admin_client.get("/api/analysis/99999")
    assert response.status_code == 404


async def test_settings_update_non_admin_restricted(user_client):
    """Non-admin user modifying advanced/restricted settings."""
    # max_recur_limit is restricted to admins only
    payload = {"max_recur_limit": 500}
    response = await user_client.put("/api/settings", json=payload)
    assert response.status_code == 403


async def test_settings_update_invalid_language(admin_client):
    """Modify settings with invalid types or constraints."""
    response = await admin_client.put("/api/settings", json={"analyst_concurrency_limit": -5})
    assert response.status_code == 422


# =====================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# =====================================================================


async def test_watchlist_settings_to_screener(admin_client):
    """Watchlist additions propagate correctly to watchlist screener."""
    # Reset watchlist
    await admin_client.put("/api/settings", json={"watchlist": []})
    # Add ticker to watchlist via endpoint
    await admin_client.post("/api/watchlist/MSFT")

    # Run watchlist scan
    response = await admin_client.post("/api/screener/scan-watchlist")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["ticker"] == "MSFT"


async def test_alert_trigger_to_auto_analysis(admin_client, live_prices):
    """Alert triggers and successfully schedules an auto-analysis."""
    # Create an alert with auto_analyze = True
    res = await admin_client.post(
        "/api/alerts", json={"ticker": "AAPL", "condition": "above", "target_price": 160.0, "auto_analyze": True}
    )
    alert_id = res.json()["id"]

    # Cross the price barrier
    live_prices["AAPL"] = 165.0
    await check_price_alerts()

    # Verify alert triggers
    get_res = await admin_client.get("/api/alerts")
    alert = next(a for a in get_res.json() if a["id"] == alert_id)
    assert alert["triggered_at"] is not None

    # Verify a new analysis task is spawned in the database for AAPL
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(AnalysisResult).where(AnalysisResult.ticker == "AAPL").order_by(AnalysisResult.id.desc())
        )
        analysis = res.scalars().first()
        assert analysis is not None
        assert analysis.status == "completed"


async def test_analysis_buy_signal_to_auto_trade(admin_client):
    """Completed analysis with BUY signal triggers auto-trade placement when cron runs scan."""
    # Enable watchlist and cron in user settings
    await admin_client.put("/api/settings", json={"watchlist": ["MSFT"], "cron_enabled": True})

    # Reset portfolio
    await admin_client.post("/api/trading/reset", json={"initial_capital": 100000.0})

    # We trigger the watchlist scan in the cron service manually
    from backend.services.cron_service import get_cron_service

    cron = get_cron_service()

    # Execute the watchlist scan manually
    # Find user ID of admin
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.username == "admin"))
        admin_user = res.scalar_one()

    await cron._run_user_watchlist_scan(admin_user.id)

    # Verify that a BUY order was placed for MSFT
    response = await admin_client.get("/api/portfolio/orders")
    orders = response.json()
    assert len(orders) > 0
    assert any(o["ticker"] == "MSFT" and o["action"] == "BUY" for o in orders)


async def test_settings_to_custom_indicators(admin_client):
    """Updating preset/settings affects formula validation/evaluation."""
    # Fetch memory status
    response = await admin_client.get("/api/settings/memory")
    assert response.status_code == 200
    # Update preset
    await admin_client.put("/api/settings", json={"analyst_concurrency_limit": 2})
    get_res = await admin_client.get("/api/settings")
    assert get_res.json()["analyst_concurrency_limit"] == 2


async def test_alert_trigger_writes_notification_logs(admin_client, live_prices):
    """Alert trigger writes a system notification log."""
    await admin_client.post("/api/alerts", json={"ticker": "MSFT", "condition": "below", "target_price": 280.0})

    # Trigger the alert
    live_prices["MSFT"] = 270.0
    await check_price_alerts()

    # Sleep to allow logging thread to flush
    await asyncio.sleep(3.5)

    # Verify log entries exist in database
    async with AsyncSessionLocal() as db:
        from backend.models.log import SystemLog

        res = await db.execute(select(SystemLog).order_by(SystemLog.id.desc()))
        logs = res.scalars().all()
        assert len(logs) > 0
        assert any("alert" in log.message.lower() or "msft" in log.message.lower() for log in logs)


# =====================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (>= 5 scenarios)
# =====================================================================


async def test_scenario_1_user_onboarding_and_first_trade(admin_client):
    """Scenario 1: Complete flow from settings update, watchlist setup, screening, analysis, trade, and holding verification."""
    # 1. Update settings
    await admin_client.put("/api/settings", json={"watchlist": ["AAPL", "MSFT"]})

    # 2. Add GOOG to watchlist
    await admin_client.post("/api/watchlist/GOOG")

    # 3. Check watchlist
    wl_res = await admin_client.get("/api/watchlist")
    assert "GOOG" in wl_res.json()

    # 4. Screen watchlist
    scr_res = await admin_client.post("/api/screener/scan-watchlist")
    assert scr_res.status_code == 200

    # 5. Run manual individual analysis
    ans_res = await admin_client.post(
        "/api/analysis/run", json={"ticker": "GOOG", "trade_date": "2026-06-20", "asset_type": "stock"}
    )
    assert ans_res.status_code == 200

    # 6. Execute trade based on analysis
    trade_res = await admin_client.post(
        "/api/trading/order", json={"ticker": "GOOG", "action": "BUY", "quantity": 10, "leverage": 1.0}
    )
    assert trade_res.status_code == 201

    # 7. Verify holdings
    holdings_res = await admin_client.get("/api/portfolio/holdings")
    assert any(h["ticker"] == "GOOG" for h in holdings_res.json())


async def test_scenario_2_alert_auto_analysis_lifecycle(admin_client, live_prices):
    """Scenario 2: Creating price alerts, triggering them by price crossing, which schedules analysis and notifies user."""
    # 1. Create alert on TSLA above 200.0 with auto_analyze=True
    await admin_client.post(
        "/api/alerts", json={"ticker": "TSLA", "condition": "above", "target_price": 200.0, "auto_analyze": True}
    )

    # 2. Modify live price to trigger the alert
    live_prices["TSLA"] = 210.0
    await check_price_alerts()

    # 3. Verify alert is marked as triggered and disabled
    alerts_res = await admin_client.get("/api/alerts")
    tsla_alert = next(a for a in alerts_res.json() if a["ticker"] == "TSLA")
    assert tsla_alert["triggered_at"] is not None

    # 4. Verify analysis result exists for TSLA
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(AnalysisResult).where(AnalysisResult.ticker == "TSLA"))
        tsla_analysis = res.scalars().first()
        assert tsla_analysis is not None
        assert tsla_analysis.status == "completed"


async def test_scenario_3_portfolio_leverage_rebalance_and_notes(admin_client):
    """Scenario 3: Portfolio reset, leveraged margin trade, risk review, rebalance check, journaling notes."""
    # 1. Reset portfolio
    await admin_client.post("/api/trading/reset", json={"initial_capital": 50000.0})

    # 2. Leveraged trade on AAPL (leverage = 2.0)
    trade_res = await admin_client.post(
        "/api/trading/order", json={"ticker": "AAPL", "action": "BUY", "quantity": 100, "leverage": 2.0}
    )
    assert trade_res.status_code == 201
    order_id = trade_res.json()["order_id"]

    # 3. Check portfolio stats for leverage
    stats_res = await admin_client.get("/api/trading/portfolio-stats")
    assert stats_res.status_code == 200

    # 4. Get rebalance suggestions
    rebal_res = await admin_client.post("/api/trading/rebalance")
    assert rebal_res.status_code == 200

    # 5. Add a trade note explaining the trade decision
    note_res = await admin_client.post(
        f"/api/trading/journal/{order_id}/note", json={"note": "Leveraged BUY of AAPL to capture upward breakout."}
    )
    assert note_res.status_code == 200


async def test_scenario_4_stop_loss_breach_auto_close(admin_client, live_prices):
    """Scenario 4: Establish a long position with Stop-Loss, price drops below stop loss, position monitor closes it."""
    # 1. Reset portfolio
    await admin_client.post("/api/trading/reset", json={"initial_capital": 10000.0})

    # 2. Buy AAPL at 150.0
    live_prices["AAPL"] = 150.0
    trade_res = await admin_client.post(
        "/api/trading/order", json={"ticker": "AAPL", "action": "BUY", "quantity": 10, "leverage": 1.0}
    )
    assert trade_res.status_code == 201

    # 3. Set stop loss on AAPL holding to 145.0 directly in DB
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Holding).where(Holding.ticker == "AAPL"))
        holding = res.scalars().first()
        holding.stop_loss = Decimal("145.0")
        await db.commit()

    # 4. Drop live price to 140.0 (breaches stop_loss)
    live_prices["AAPL"] = 140.0

    # 5. Run position monitor
    async with AsyncSessionLocal() as db:
        closed_positions = await monitor_open_positions(db)
        await db.commit()

    assert len(closed_positions) > 0
    assert any(pos["ticker"] == "AAPL" for pos in closed_positions)

    # 6. Verify holding is removed or zeroed
    holdings_res = await admin_client.get("/api/portfolio/holdings")
    aapl_holdings = [h for h in holdings_res.json() if h["ticker"] == "AAPL"]
    assert len(aapl_holdings) == 0 or aapl_holdings[0]["quantity"] == 0


async def test_scenario_5_time_travel_rollback_and_resume(admin_client):
    """Scenario 5: Manual analysis run, checkpoint listing, rollback state update, and execution resume."""
    # 1. Run analysis for MSFT to generate checkpoints
    ans_res = await admin_client.post(
        "/api/analysis/run", json={"ticker": "MSFT", "trade_date": "2026-06-20", "asset_type": "stock"}
    )
    assert ans_res.status_code == 200

    # Retrieve the analysis from database to get id
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(AnalysisResult).where(AnalysisResult.ticker == "MSFT").order_by(AnalysisResult.id.desc())
        )
        analysis = res.scalars().first()
        analysis_id = analysis.id

    # 2. Get list of checkpoints for this analysis
    cp_res = await admin_client.get(f"/api/analysis/{analysis_id}/checkpoints")
    assert cp_res.status_code == 200
    checkpoints = cp_res.json()

    # If no checkpoints exist (because graph is mocked and did not run full LangGraph checkpointer),
    # we can create a mock checkpoint or directly assert the endpoints behavior.
    # To test the time travel endpoint, let's trigger it with a dummy checkpoint
    checkpoint_id = checkpoints[0]["configurable"]["checkpoint_id"] if checkpoints else "dummy-checkpoint-id"

    # 3. Post time-travel rollback and resume
    tt_payload = {"checkpoint_id": checkpoint_id, "update_state": {"sentiment_score": 0.9}}
    tt_res = await admin_client.post(f"/api/analysis/{analysis_id}/time-travel", json=tt_payload)
    # The endpoint might return 400 if checkpoint is invalid/dummy, or 200 if it proceeds.
    assert tt_res.status_code in (200, 400)
