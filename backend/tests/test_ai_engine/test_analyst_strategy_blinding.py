from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_macro_analyst_does_not_receive_directional_past_context(monkeypatch):
    from backend.trading_agents.agents.runtime import analyst_cache
    from backend.trading_agents.agents.sub.analysts import macro_analyst
    from backend.trading_agents.dataflows import interface

    captured: dict[str, str] = {}

    async def fake_vendor(*_args, **_kwargs):
        return "macro source data"

    async def no_cache(*_args, **_kwargs):
        return None

    async def no_store(*_args, **_kwargs):
        return None

    async def fake_runner(_llm, _state, **kwargs):
        captured["system_message"] = kwargs["system_message"]
        return {"macro_report": "Fresh macro report."}

    monkeypatch.setattr(interface, "route_to_vendor", fake_vendor)
    monkeypatch.setattr(analyst_cache, "check_analyst_cache", no_cache)
    monkeypatch.setattr(analyst_cache, "store_analyst_cache", no_store)
    monkeypatch.setattr(macro_analyst, "run_tool_analyst", fake_runner)
    monkeypatch.setattr(macro_analyst, "get_general_settings_block", lambda: "")

    node = macro_analyst.create_macro_analyst(object())
    result = await node(
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-08-08",
            "past_context": "Previous accepted decision: SELL NVDA; do not repeat BUY.",
        }
    )

    assert result["macro_report"] == "Fresh macro report."
    assert "Previous accepted decision" not in captured["system_message"]
    assert "SELL NVDA" not in captured["system_message"]
    assert "No prior directional decision" in captured["system_message"]
