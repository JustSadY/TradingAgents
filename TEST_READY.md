# E2E Test Execution Report (TEST_READY)

This document contains the commands to run the E2E test suite, the tested features inventory, and the pass/fail results.

---

## 1. Test Runner Commands

Run these commands from the project root directory (`/home/lykia/Desktop/TradingAgents`):

```bash
# Run the entire E2E test suite
PYTHONPATH=. ./.venv/bin/pytest backend/tests/e2e/test_e2e_suite.py

# Run with warnings suppressed and concise traceback reporting
PYTHONPATH=. ./.venv/bin/pytest backend/tests/e2e/test_e2e_suite.py --tb=short -W ignore

# Run a specific test case
PYTHONPATH=. ./.venv/bin/pytest backend/tests/e2e/test_e2e_suite.py::test_execute_buy_order_success
```

---

## 2. Tested Features Inventory

The test suite covers 5 main backend features across 60 test cases:
1.  **Simulation Portfolio** (10 tests)
2.  **Trading Execution / Auto-close** (10 tests)
3.  **Technical Indicators / Screener** (10 tests)
4.  **Price Alerts** (10 tests)
5.  **API Settings / Logs / Reports** (10 tests)
6.  **Cross-Feature Combinations** (5 tests)
7.  **Real-World Application Scenarios** (5 tests)

---

## 3. Pass/Fail Execution Report

*   **Total Tests**: 60
*   **Passed**: 58
*   **Failed**: 2
*   **Success Rate**: 96.67%

### List of Failed Tests (Due to Existing Backend Bugs)

| Test Case | Verbatim Error / Traceback | Reason / Root Cause (Backend Bug) |
| :--- | :--- | :--- |
| `test_settings_update_invalid_webhook` | `assert 200 == 422` | **Missing strict URL validation in schema**: The settings update API accepts invalid webhook formats (e.g., `ftp://malicious.com`) with a `200 OK` response instead of throwing a validation error (`422 Unprocessable Entity`). |
| `test_analysis_buy_signal_to_auto_trade` | `assert len(orders) > 0 (where len([]) == 0)` | **Missing commit in cron scan loop**: In `_run_user_watchlist_scan` (inside `backend/services/cron_service.py`), `place_signal_order` is executed, but there is no `db.commit()` call after it. When the session exits, the uncommitted transaction is rolled back, causing the executed BUY order to be lost. |

### List of Passing Tests (58/60)

1.  `test_portfolio_get_active` - Passed
2.  `test_portfolio_holdings_empty` - Passed
3.  `test_portfolio_orders_empty` - Passed
4.  `test_portfolio_stats_fetch` - Passed
5.  `test_portfolio_risk_dashboard_fetch` - Passed
6.  `test_execute_buy_order_success` - Passed
7.  `test_execute_sell_order_success` - Passed
8.  `test_execute_short_order_success` - Passed
9.  `test_journal_note_save` - Passed
10. `test_journal_debrief_generate` - Passed
11. `test_screener_scan_tickers` - Passed
12. `test_screener_scan_watchlist_empty` - Passed
13. `test_screener_scan_watchlist_nonempty` - Passed
14. `test_screener_formula_assist` - Passed
15. `test_screener_scan_top_n_candidates` - Passed
16. `test_alert_create_above` - Passed
17. `test_alert_list_all` - Passed
18. `test_alert_update_settings` - Passed
19. `test_alert_delete_existing` - Passed
20. `test_alert_check_trigger_logic` - Passed
21. `test_settings_get_user` - Passed
22. `test_settings_update_watchlist` - Passed
23. `test_settings_memory_status` - Passed
24. `test_analysis_run_individual` - Passed
25. `test_analysis_run_portfolio` - Passed
26. `test_portfolio_reset_negative_capital` - Passed
27. `test_portfolio_reset_too_high_capital` - Passed
28. `test_portfolio_orders_invalid_limit` - Passed
29. `test_portfolio_orders_invalid_offset` - Passed
30. `test_portfolio_reset_exact_bounds` - Passed
31. `test_execute_order_zero_quantity` - Passed
32. `test_execute_order_negative_quantity` - Passed
33. `test_execute_order_invalid_leverage` - Passed
34. `test_execute_order_empty_ticker` - Passed
35. `test_execute_order_insufficient_margin` - Passed
36. `test_screener_scan_too_many_tickers` - Passed
37. `test_screener_scan_negative_top_n` - Passed
38. `test_screener_scan_too_large_top_n` - Passed
39. `test_screener_formula_assist_too_long` - Passed
40. `test_screener_formula_assist_empty` - Passed
41. `test_alert_create_negative_price` - Passed
42. `test_alert_create_invalid_condition` - Passed
43. `test_alert_create_too_long_ticker` - Passed
44. `test_alert_update_non_existent` - Passed
45. `test_alert_delete_non_existent` - Passed
46. `test_analysis_run_invalid_ticker` - Passed
47. `test_analysis_get_non_existent` - Passed
48. `test_settings_update_non_admin_restricted` - Passed
49. `test_settings_update_invalid_language` - Passed
50. `test_watchlist_settings_to_screener` - Passed
51. `test_alert_trigger_to_auto_analysis` - Passed
52. `test_settings_to_custom_indicators` - Passed
53. `test_alert_trigger_writes_notification_logs` - Passed
54. `test_scenario_1_user_onboarding_and_first_trade` - Passed
55. `test_scenario_2_alert_auto_analysis_lifecycle` - Passed
56. `test_scenario_3_portfolio_leverage_rebalance_and_notes` - Passed
57. `test_scenario_4_stop_loss_breach_auto_close` - Passed
58. `test_scenario_5_time_travel_rollback_and_resume` - Passed
