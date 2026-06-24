"""Tests for the centralized HTTP exception handlers.

Routers no longer wrap service calls in try/except ValueError -> 400 /
Exception -> 500; these handlers do it in one place.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.exceptions import register_exception_handlers


def _make_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/value-error")
    async def _value_error():
        raise ValueError("bad input")

    @app.get("/boom")
    async def _boom():
        raise RuntimeError("kaboom")

    # raise_server_exceptions=False so the 500 handler's response is returned
    # instead of the exception being re-raised into the test.
    return TestClient(app, raise_server_exceptions=False)


def test_value_error_maps_to_400_with_message():
    r = _make_client().get("/value-error")
    assert r.status_code == 400
    assert r.json()["detail"] == "bad input"


def test_unhandled_exception_maps_to_generic_500():
    r = _make_client().get("/boom")
    assert r.status_code == 500
    # internal details are not leaked
    assert r.json()["detail"] == "Internal server error"
