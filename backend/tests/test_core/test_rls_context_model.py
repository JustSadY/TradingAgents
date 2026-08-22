from __future__ import annotations

from pathlib import Path

from backend.core.rls_context import BackgroundCapability, RLSContextKind


def test_context_kinds_are_explicit_and_non_overlapping():
    assert {item.value for item in RLSContextKind} == {"tenant", "admin", "system", "refresh", "share"}


def test_background_capabilities_are_auditable_allowlist():
    assert {item.value for item in BackgroundCapability} == {
        "alert_checker", "alert_outbox", "performance_backfill", "position_monitor",
        "maintenance_cleanup", "startup_seed", "startup_cleanup", "cron_bootstrap", "alert_recovery",
        "system_logging",
    }


def test_trusted_background_session_is_not_used_by_api_or_repository_modules():
    root = Path(__file__).resolve().parents[2]
    forbidden = [root / "api", root / "repositories"]
    offenders = []
    for directory in forbidden:
        for path in directory.rglob("*.py"):
            if "trusted_background_session" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []
