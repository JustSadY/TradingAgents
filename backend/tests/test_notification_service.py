"""Tests for webhook notification gating and payload shaping."""

from types import SimpleNamespace

import pytest

from backend.services import notification_service as ns


def _settings(**kwargs):
    base = {
        "webhook_enabled": True,
        "webhook_url": "https://example.com/hook",
        "webhook_events": '["analysis_complete","trade_executed","alert_triggered"]',
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.fixture
def sent(monkeypatch):
    calls = []

    async def fake_send(url, event, data, retries=2):
        calls.append((url, event, data))
        return True

    monkeypatch.setattr(ns, "send_webhook", fake_send)
    return calls


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_webhook_sends_nothing(sent):
    await ns.notify_trade_executed("AAPL", "BUY", 10.0, 100.0, _settings(webhook_enabled=False))
    assert sent == []


@pytest.mark.asyncio
async def test_unsubscribed_event_sends_nothing(sent):
    await ns.notify_trade_executed("AAPL", "BUY", 10.0, 100.0, _settings(webhook_events='["analysis_complete"]'))
    assert sent == []


@pytest.mark.asyncio
async def test_missing_url_sends_nothing(sent):
    await ns.notify_alert_triggered("AAPL", "above", 150.0, _settings(webhook_url=""))
    assert sent == []


@pytest.mark.asyncio
async def test_malformed_events_json_fails_closed(sent):
    await ns.notify_analysis_complete("AAPL", "Buy", "2026-06-12", "plan", _settings(webhook_events="not json"))
    assert sent == []


@pytest.mark.asyncio
async def test_subscribed_event_fires_with_payload(sent):
    await ns.notify_trade_executed("AAPL", "BUY", 10.0, 100.0, _settings())
    ((url, event, data),) = sent
    assert url == "https://example.com/hook"
    assert event == "trade_executed"
    assert data == {"ticker": "AAPL", "action": "BUY", "quantity": 10.0, "price": 100.0}


@pytest.mark.asyncio
async def test_analysis_summary_is_truncated(sent):
    await ns.notify_analysis_complete("AAPL", "Buy", "2026-06-12", "x" * 1000, _settings())
    ((_, _, data),) = sent
    assert len(data["summary"]) == 300


# ---------------------------------------------------------------------------
# Payload shaping per destination
# ---------------------------------------------------------------------------


def test_slack_payload_uses_text_field():
    payload = ns._build_payload("https://hooks.slack.com/services/x", "trade_executed", {"ticker": "AAPL"})
    assert set(payload) == {"text"}


def test_discord_payload_uses_embeds():
    payload = ns._build_payload(
        "https://discord.com/api/webhooks/1/x", "alert_triggered", {"ticker": "AAPL", "target_price": 150.0}
    )
    assert payload["embeds"][0]["title"] == "🔔 Price Alert"
    assert payload["embeds"][0]["color"] == 0xF59E0B


def test_generic_payload_includes_event_and_data():
    data = {"ticker": "AAPL"}
    payload = ns._build_payload("https://example.com/hook", "analysis_complete", data)
    assert payload["event"] == "analysis_complete"
    assert payload["data"] is data


def test_alert_text_varies_by_alert_type():
    assert "SUPPORT BREACH" in ns._format_text(
        "alert_triggered", {"ticker": "AAPL", "target_price": 1.0, "alert_type": "support"}
    )
    assert "RESISTANCE BREACH" in ns._format_text(
        "alert_triggered", {"ticker": "AAPL", "target_price": 1.0, "alert_type": "resistance"}
    )
    assert "crossed above" in ns._format_text(
        "alert_triggered", {"ticker": "AAPL", "target_price": 1.0, "condition": "above"}
    )


def test_parse_events_handles_empty_and_invalid():
    assert ns._parse_events("") == []
    assert ns._parse_events("{bad") == []
    assert ns._parse_events('["a","b"]') == ["a", "b"]
