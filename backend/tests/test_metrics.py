"""Tests for the Prometheus metrics endpoint and engine instrumentation."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

import backend.api.metrics as metrics_api
from backend.trading_agents.agents.runtime.resilience import guard_node


class _FakeSettings:
    def __init__(self, token: str):
        self.METRICS_TOKEN = token


def _make_client(monkeypatch, token: str) -> TestClient:
    monkeypatch.setattr(metrics_api, "get_settings", lambda: _FakeSettings(token))
    app = FastAPI()
    app.include_router(metrics_api.router)
    return TestClient(app)


def test_metrics_disabled_without_token(monkeypatch):
    r = _make_client(monkeypatch, "").get("/metrics")
    assert r.status_code == 404


def test_metrics_rejects_missing_or_wrong_token(monkeypatch):
    client = _make_client(monkeypatch, "s3cret")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_metrics_serves_payload_with_token(monkeypatch):
    client = _make_client(monkeypatch, "s3cret")
    r = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    assert "tradingagents_websocket_connections" in r.text


def _fallback_count() -> float:
    return (
        REGISTRY.get_sample_value("tradingagents_node_fallbacks_total", {"node": "metrics-probe", "kind": "agent"})
        or 0.0
    )


async def test_guard_node_records_fallback_metric():
    async def failing(state):
        raise RuntimeError("explode")

    def fallback(state, exc):
        return {"ok": True}

    before = _fallback_count()
    wrapped = guard_node(failing, name="metrics-probe", kind="agent", fallback=fallback)
    result = await wrapped({})

    assert result == {"ok": True}
    assert _fallback_count() == before + 1.0
