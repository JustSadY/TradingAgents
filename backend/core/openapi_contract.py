"""Validation helpers shared by offline OpenAPI export and tests."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from fastapi.openapi.models import OpenAPI

# These are intentionally a small, stable frontend contract rather than a
# snapshot of every route. Adding a route does not churn this list; renaming a
# consumed operation must be an explicit decision.
CORE_OPERATION_IDS: dict[tuple[str, str], str] = {
    ("/auth/login", "post"): "auth_login",
    ("/auth/refresh", "post"): "auth_refresh",
    ("/auth/logout", "post"): "auth_logout",
    ("/api/meta", "get"): "meta_get_meta",
    ("/api/meta/schemas", "get"): "meta_get_meta_schemas",
    ("/api/settings", "get"): "settings_get_settings",
    ("/api/settings", "put"): "settings_update_settings",
    ("/api/analysis/run", "post"): "analysis_run_analysis",
    ("/api/analysis/history", "get"): "analysis_list_analysis",
}

_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_SENSITIVE_FIELD_NAMES = {
    "password",
    "api_key",
    "apikey",
    "secret_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "encryption_key",
}
_EXAMPLE_KEYS = {"default", "example", "examples"}


def iter_operations(schema: dict[str, Any]):
    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() in _HTTP_METHODS and isinstance(operation, dict):
                yield path, method.lower(), operation


def operation_id_map(schema: dict[str, Any]) -> dict[tuple[str, str], str]:
    return {
        (path, method): str(operation.get("operationId") or "")
        for path, method, operation in iter_operations(schema)
    }


def validate_operation_ids(schema: dict[str, Any]) -> None:
    ids = [str(operation.get("operationId") or "") for _, _, operation in iter_operations(schema)]
    missing = [item for item in ids if not item]
    if missing:
        raise ValueError("OpenAPI contains operation(s) without operationId")
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate OpenAPI operationId values: {', '.join(duplicates)}")

    actual = operation_id_map(schema)
    problems = []
    for key, expected in CORE_OPERATION_IDS.items():
        value = actual.get(key)
        if value != expected:
            problems.append(f"{key[1].upper()} {key[0]} expected {expected!r}, got {value!r}")
    if problems:
        raise ValueError("Stable OpenAPI operationId contract changed: " + "; ".join(problems))


def _sensitive_path(path: tuple[str, ...]) -> bool:
    for part in path:
        normalized = part.lower().replace("-", "_")
        if normalized == "token_type":
            continue
        if normalized in _SENSITIVE_FIELD_NAMES:
            return True
        if any(normalized.endswith("_" + name) for name in _SENSITIVE_FIELD_NAMES):
            return True
    return False


def _nonempty_string_values(value: Any):
    if isinstance(value, str):
        if value.strip():
            yield value.strip()
    elif isinstance(value, list):
        for item in value:
            yield from _nonempty_string_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _nonempty_string_values(item)


def validate_no_secret_examples(schema: dict[str, Any]) -> None:
    leaked: list[str] = []

    def walk(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                next_path = (*path, str(key))
                if key in _EXAMPLE_KEYS and _sensitive_path(path):
                    for literal in _nonempty_string_values(child):
                        if literal not in {"***", "<redacted>", "REDACTED"}:
                            leaked.append(".".join(path))
                walk(child, next_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))

    walk(schema)
    if leaked:
        raise ValueError("OpenAPI contains non-masked secret example/default values at: " + ", ".join(sorted(set(leaked))))

    rendered = json.dumps(schema, sort_keys=True)
    if "openapi-export-placeholder-key" in rendered:
        raise ValueError("OpenAPI leaked the exporter's placeholder SECRET_KEY")


def validate_openapi_schema(schema: dict[str, Any]) -> None:
    # FastAPI ships a Pydantic representation of the OpenAPI document; using it
    # avoids adding a second validator dependency solely for export.
    OpenAPI.model_validate(schema)
    validate_operation_ids(schema)
    validate_no_secret_examples(schema)


def render_openapi(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def build_validated_openapi() -> dict[str, Any]:
    from backend.main import app

    schema = app.openapi()
    validate_openapi_schema(schema)
    return schema
