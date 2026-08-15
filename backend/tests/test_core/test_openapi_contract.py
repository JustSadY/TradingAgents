from __future__ import annotations

import socket

import pytest

from backend.core.openapi_contract import (
    CORE_OPERATION_IDS,
    build_validated_openapi,
    operation_id_map,
    render_openapi,
    validate_no_secret_examples,
    validate_openapi_schema,
    validate_operation_ids,
)


def test_openapi_is_valid_and_operation_ids_are_unique_and_stable():
    schema = build_validated_openapi()
    validate_openapi_schema(schema)
    mapping = operation_id_map(schema)
    for key, expected in CORE_OPERATION_IDS.items():
        assert mapping[key] == expected


def test_duplicate_operation_id_is_rejected():
    schema = {
        "openapi": "3.1.0",
        "info": {"title": "x", "version": "1"},
        "paths": {
            "/a": {"get": {"operationId": "same", "responses": {"200": {"description": "ok"}}}},
            "/b": {"get": {"operationId": "same", "responses": {"200": {"description": "ok"}}}},
        },
    }
    with pytest.raises(ValueError, match="Duplicate OpenAPI operationId"):
        validate_operation_ids(schema)


def test_openapi_render_is_deterministic():
    schema = build_validated_openapi()
    first = render_openapi(schema)
    second = render_openapi(build_validated_openapi())
    assert first == second


def test_openapi_generation_does_not_open_database_or_network(monkeypatch):
    def forbidden_connect(*_args, **_kwargs):
        raise AssertionError("network access attempted during OpenAPI export")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)

    from sqlalchemy.ext.asyncio import AsyncEngine

    def forbidden_db_connect(*_args, **_kwargs):
        raise AssertionError("database access attempted during OpenAPI export")

    monkeypatch.setattr(AsyncEngine, "connect", forbidden_db_connect)
    schema = build_validated_openapi()
    assert schema["paths"]


def test_secret_examples_are_rejected_but_masked_values_are_allowed():
    good = {"components": {"schemas": {"X": {"properties": {"api_key": {"example": "***"}}}}}}
    validate_no_secret_examples(good)
    bad = {"components": {"schemas": {"X": {"properties": {"api_key": {"example": "sk-live-secret"}}}}}}
    with pytest.raises(ValueError, match="secret example/default"):
        validate_no_secret_examples(bad)
