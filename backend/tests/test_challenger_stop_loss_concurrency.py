import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.services.trading_orchestrator import _position_quantity
from backend.trading_agents.agents.main.agent_qa import _Question, _Questions, create_agent_qa_node
from backend.trading_agents.agents.utils.agent_utils import run_macd_rsi_backtests

# --- Stop Loss Floor Edge Cases ---


def test_stop_loss_floor_math():
    # Base risk: 1% of 100,000 = $1,000. Price = 100.
    # Normal case: stop_loss = 95.0. risk_per_share = 5.0. Qty = 1000 / 5 = 200. Max qty = 10k/100 = 100. Min(200, 100) = 100.
    assert _position_quantity(1.0, 100_000, 100.0, stop_loss=95.0) == pytest.approx(100.0)

    # Stop loss close to entry: stop_loss = 99.9. risk_per_share = abs(100 - 99.9) = 0.1, but floored to 0.005 * 100 = 0.5.
    # Qty = 1000 / 0.5 = 2000. Max qty = 100. Min(2000, 100) = 100.
    # Let's increase max_position_size_pct to 500% to avoid capping.
    # Qty = 1000 / 0.5 = 2000. Max qty = 500,000 / 100 = 5000. Min(2000, 5000) = 2000.
    assert _position_quantity(1.0, 100_000, 100.0, stop_loss=99.9, max_position_size_pct=500.0) == pytest.approx(2000.0)

    # Stop loss extremely close to entry: stop_loss = 99.9999. Floored to 0.5. Qty = 2000.
    assert _position_quantity(1.0, 100_000, 100.0, stop_loss=99.9999, max_position_size_pct=500.0) == pytest.approx(
        2000.0
    )

    # Stop loss slightly above entry (short? But the code says if stop_loss and stop_loss != price):
    # stop_loss = 100.1. risk_per_share = abs(100 - 100.1) = 0.1, floored to 0.5. Qty = 2000.
    assert _position_quantity(1.0, 100_000, 100.0, stop_loss=100.1, max_position_size_pct=500.0) == pytest.approx(
        2000.0
    )

    # Stop loss negative: stop_loss = -50.0. Under <= 0 check, falls back to risk_usd / price.
    # Qty = 1000 / 100 = 10. Max qty = 5000. Min(10, 5000) = 10.
    assert _position_quantity(1.0, 100_000, 100.0, stop_loss=-50.0, max_position_size_pct=500.0) == pytest.approx(10.0)

    # Stop loss zero: stop_loss = 0.0. Falls back to risk_usd / price = 10.
    assert _position_quantity(1.0, 100_000, 100.0, stop_loss=0.0, max_position_size_pct=500.0) == pytest.approx(10.0)

    # Stop loss exactly price: stop_loss = 100.0. Falls back to risk_usd / price = 10.
    assert _position_quantity(1.0, 100_000, 100.0, stop_loss=100.0, max_position_size_pct=500.0) == pytest.approx(10.0)

    # Price very small: price = 0.01, stop_loss = 0.0099.
    # floor = 0.005 * 0.01 = 0.00005.
    # abs(price - stop_loss) = 0.0001. Since 0.0001 > 0.00005, floor is not applied.
    # risk_per_share = 0.0001. Qty = 1000 / 0.0001 = 10,000,000.
    # Max qty = 500,000 / 0.01 = 50,000,000. Min(10,000,000, 50,000,000) = 10,000,000.
    assert _position_quantity(1.0, 100_000, 0.01, stop_loss=0.0099, max_position_size_pct=500.0) == pytest.approx(
        10_000_000.0
    )

    # Price very small, stop_loss extremely close: price = 0.01, stop_loss = 0.009999.
    # floor = 0.00005.
    # abs(price - stop_loss) = 0.000001. Since 0.000001 < 0.00005, floor is applied.
    # risk_per_share = 0.00005. Qty = 1000 / 0.00005 = 20,000,000.
    assert _position_quantity(1.0, 100_000, 0.01, stop_loss=0.009999, max_position_size_pct=500.0) == pytest.approx(
        20_000_000.0
    )

    # Kelly multiplier edge cases:
    # kelly_multiplier = 0.0 -> risk_usd = 0 -> quantity = 0.
    assert _position_quantity(1.0, 100_000, 100.0, kelly_multiplier=0.0) == pytest.approx(0.0)
    # kelly_multiplier = -0.5 -> clamped to 0 -> quantity = 0.
    assert _position_quantity(1.0, 100_000, 100.0, kelly_multiplier=-0.5) == pytest.approx(0.0)
    # kelly_multiplier = 1.5 -> clamped to 1 -> quantity = 10 (without stop loss, max_qty = 100).
    assert _position_quantity(1.0, 100_000, 100.0, kelly_multiplier=1.5) == pytest.approx(10.0)


# --- Concurrency Tests ---


@pytest.mark.asyncio
async def test_run_macd_rsi_backtests_concurrency():
    # We want to verify that run_macd_rsi_backtests runs the two strategy backtests concurrently.
    # We mock run_strategy_backtest.invoke to sleep for 0.1 seconds and record call times.
    call_times = []

    def mock_invoke(args):
        call_times.append(time.time())
        time.sleep(0.1)
        return f"Mocked {args.get('strategy_type')}"

    mock_tool = MagicMock()
    mock_tool.invoke = mock_invoke

    with patch("backend.trading_agents.agents.utils.agent_utils.run_strategy_backtest", mock_tool):
        start = time.time()
        macd_res, rsi_res = await run_macd_rsi_backtests("AAPL")
        end = time.time()

        assert macd_res == "Mocked macd_crossover"
        assert rsi_res == "Mocked rsi_oversold"
        assert len(call_times) == 2
        # If they were run sequentially, the total time would be at least 0.2s.
        # If run in parallel via to_thread/gather, the invoke calls would start almost simultaneously (difference < 0.05s)
        # and total time would be closer to 0.1s.
        time_diff = abs(call_times[0] - call_times[1])
        assert time_diff < 0.05, f"Backtests did not run concurrently; call times: {call_times}"
        assert end - start < 0.18, f"Total execution time too high: {end - start}"


@pytest.mark.asyncio
async def test_agent_qa_moderator_concurrency():
    # We want to verify that create_agent_qa_node runs answer generation concurrently.
    # We mock _answer_as_analyst to sleep for 0.1 seconds.
    # If concurrent, answering 2 questions should take ~0.1s instead of 0.2s.
    from backend.trading_agents.dataflows.config import set_config

    set_config({"agent_qa_enabled": True})

    class _FakeStructured:
        async def ainvoke(self, _prompt):
            return _Questions(
                questions=[
                    _Question(to="Market Analyst", question="Q1"),
                    _Question(to="Sentiment Analyst", question="Q2"),
                ]
            )

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _FakeStructured()

    class _FakeCtx:
        def llm_for(self, _key):
            return _FakeLLM()

    call_times = []

    async def mock_answer_as_analyst(ctx, target_key, target_label, target_report, question):
        call_times.append(time.time())
        await asyncio.sleep(0.1)
        return f"Answer to {question}"

    node = create_agent_qa_node(_FakeCtx())

    with patch("backend.trading_agents.agents.main.agent_qa._answer_as_analyst", side_effect=mock_answer_as_analyst):
        start = time.time()
        out = await node(
            {
                "company_of_interest": "AAPL",
                "market_report": "report1",
                "sentiment_report": "report2",
            }
        )
        end = time.time()

        assert "agent_qa_report" in out
        assert len(call_times) == 2
        time_diff = abs(call_times[0] - call_times[1])
        assert time_diff < 0.05, f"QA answers did not run concurrently; call times: {call_times}"
        assert end - start < 0.18, f"Total execution time too high: {end - start}"
