from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.core.temporal import normalize_iso_date, validate_date_range
from backend.schemas.analysis import AnalysisRunRequest, TimeTravelRequest
from backend.services.analysis_service import _time_travel_checkpoint_overrides
from backend.trading_agents.graph import checkpointer


def test_real_calendar_date_is_required():
    with pytest.raises(ValueError):
        normalize_iso_date("2026-02-30")


def test_future_trade_date_is_rejected():
    future = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        AnalysisRunRequest(ticker="AAPL", trade_date=future, asset_type="stock")


def test_date_range_must_be_ordered_and_bounded():
    with pytest.raises(ValueError, match="on or before"):
        validate_date_range("2025-02-01", "2025-01-01")
    with pytest.raises(ValueError, match="cannot exceed"):
        validate_date_range("2010-01-01", "2025-01-01", max_days=3650)


def test_time_travel_rejects_protected_and_unknown_fields():
    with pytest.raises(ValueError):
        TimeTravelRequest(checkpoint_id="cp", update_state={"trade_date": "2020-01-01"})
    with pytest.raises(ValueError):
        TimeTravelRequest(checkpoint_id="cp", update_state={"arbitrary": "value"})


def test_time_travel_rejects_retired_trader_state_fields():
    for field, empty_value in (
        ("trader_investment_plan", ""),
        ("trader_proposal_json", "{}"),
    ):
        with pytest.raises(ValueError, match="unsupported state fields"):
            TimeTravelRequest(checkpoint_id="cp", update_state={field: empty_value})


def test_retired_checkpoint_node_detection_is_case_and_separator_safe():
    assert checkpointer.is_retired_checkpoint_node("Trader") is True
    assert checkpointer.is_retired_checkpoint_node("trader_agent") is True
    assert checkpointer.is_retired_checkpoint_node("trader-agent") is True
    assert checkpointer.is_retired_checkpoint_node("Portfolio Manager") is False


@pytest.mark.asyncio
async def test_checkpoint_listing_rejects_entire_retired_trader_topology(monkeypatch):
    checkpoints = [
        SimpleNamespace(
            metadata={"step": 0},
            checkpoint={"versions_seen": {"Trader": {"state": 1}}, "ts": "2026-08-01T00:00:00Z"},
            config={"configurable": {"checkpoint_id": "legacy-trader"}},
        ),
        SimpleNamespace(
            metadata={"step": 1},
            checkpoint={
                "versions_seen": {
                    "Trader": {"state": 1},
                    "Portfolio Manager": {"state": 1},
                },
                "ts": "2026-08-01T00:01:00Z",
            },
            config={"configurable": {"checkpoint_id": "legacy-after-trader"}},
        ),
        SimpleNamespace(
            metadata={"step": 2},
            checkpoint={
                "versions_seen": {"Portfolio Manager": {"state": 2}},
                "ts": "2026-08-01T00:02:00Z",
            },
            config={"configurable": {"checkpoint_id": "current-portfolio-manager"}},
        ),
    ]

    class FakeSaver:
        async def alist(self, _config):
            for item in checkpoints:
                yield item

    @asynccontextmanager
    async def fake_checkpointer(*_args, **_kwargs):
        yield FakeSaver()

    monkeypatch.setattr(checkpointer, "get_async_checkpointer", fake_checkpointer)

    visible = await checkpointer.list_checkpoints_for_thread("unused", "AAPL", "2026-08-01", "scope")

    assert [item["checkpoint_id"] for item in visible] == ["current-portfolio-manager"]
    assert all(item["node"] != "Trader" for item in visible)


def test_time_travel_server_overrides_replace_live_checkpoint_context():
    overrides = _time_travel_checkpoint_overrides(
        strategy_context={"source": "historical_version", "learning_eligible": False},
        historical_context="=== POINT-IN-TIME MODE ===\n",
    )
    resumed_state = {
        "analysis_mode": "live",
        "learning_eligible": True,
        "past_context": "live attribution and current market pulse",
        "strategy_context": {"source": "active_strategy"},
        **overrides,
    }

    assert resumed_state["analysis_mode"] == "time_travel"
    assert resumed_state["learning_eligible"] is False
    assert resumed_state["past_context"] == "=== POINT-IN-TIME MODE ===\n"
    assert resumed_state["strategy_context"]["source"] == "historical_version"
