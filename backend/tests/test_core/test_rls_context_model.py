from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.core.rls_context import (
    BackgroundCapability,
    RLSContextKind,
    _CONTEXT_KEYS,
    _apply_values_sync,
    set_request_tenant_context,
)


def test_context_kinds_are_explicit_and_non_overlapping():
    assert {item.value for item in RLSContextKind} == {"tenant", "admin", "system", "refresh", "share"}


def test_background_capabilities_are_auditable_allowlist():
    assert {item.value for item in BackgroundCapability} == {
        "alert_checker",
        "alert_outbox",
        "performance_backfill",
        "position_monitor",
        "maintenance_cleanup",
        "startup_seed",
        "startup_cleanup",
        "cron_bootstrap",
        "alert_recovery",
        "system_logging",
    }


def test_rls_after_begin_applies_all_selectors_in_one_execute():
    calls = []
    connection = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    connection.execute = lambda statement, params: calls.append((statement, params))
    values = {key: f"value-{index}" for index, key in enumerate(_CONTEXT_KEYS)}

    _apply_values_sync(connection, values)

    assert len(calls) == 1
    params = calls[0][1]
    assert {params[f"key_{index}"] for index in range(len(_CONTEXT_KEYS))} == set(_CONTEXT_KEYS)
    assert [params[f"value_{index}"] for index in range(len(_CONTEXT_KEYS))] == [
        values[key] for key in _CONTEXT_KEYS
    ]


async def test_existing_transaction_applies_tenant_context_in_one_execute():
    class _Db:
        def __init__(self) -> None:
            self.info = {}
            self.calls = []

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def in_transaction(self) -> bool:
            return True

        async def execute(self, statement, params):
            self.calls.append((statement, params))

    db = _Db()

    await set_request_tenant_context(db, 7)

    assert len(db.calls) == 1
    params = db.calls[0][1]
    assert params["value_0"] == "tenant"
    assert params["value_1"] == "7"
    assert params["value_2"] == "false"
    assert all(params[f"key_{index}"] == key for index, key in enumerate(_CONTEXT_KEYS))


def test_trusted_background_session_is_not_used_by_api_or_repository_modules():
    root = Path(__file__).resolve().parents[2]
    forbidden = [root / "api", root / "repositories"]
    offenders = []
    for directory in forbidden:
        for path in directory.rglob("*.py"):
            if "trusted_background_session" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []