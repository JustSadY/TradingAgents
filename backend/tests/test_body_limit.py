"""Tests for the request body size limit middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.body_limit import BodySizeLimitMiddleware

LIMIT = 1024


def _make_client(max_body_size: int = LIMIT) -> TestClient:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=max_body_size)

    @app.post("/echo")
    async def _echo(payload: dict):
        return {"keys": len(payload)}

    return TestClient(app)


def test_small_body_passes():
    r = _make_client().post("/echo", json={"a": 1})
    assert r.status_code == 200
    assert r.json() == {"keys": 1}


def test_oversized_body_rejected_with_413():
    body = {"data": "x" * (LIMIT * 2)}
    r = _make_client().post("/echo", json=body)
    assert r.status_code == 413
    assert r.json()["detail"] == "Request body too large"


def test_oversized_body_without_content_length_rejected():
    # Chunked transfer: no Content-Length header, so the streaming counter
    # must catch it.
    def gen():
        for _ in range(4):
            yield b"x" * LIMIT

    r = _make_client().post("/echo", content=gen(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_zero_limit_disables_check():
    body = {"data": "x" * (LIMIT * 2)}
    r = _make_client(max_body_size=0).post("/echo", json=body)
    assert r.status_code == 200
