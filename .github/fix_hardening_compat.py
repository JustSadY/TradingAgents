from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# Acceptance runs from backend/, so pyright include/exclude paths must be
# relative to that project root. The old paths returned success while checking
# no intended files.
replace(
    "backend/pyproject.toml",
    'include = ["backend/core/temporal.py", "backend/schemas"]\nexclude = ["backend/tests"]\n',
    'include = ["core/temporal.py", "schemas"]\nexclude = ["tests", "postgres_tests"]\n',
)

# Alert recovery now opens an audited trusted-background context instead of a
# raw AsyncSessionLocal session. Keep the unit doubles attached at the public
# seam they actually exercise.
replace(
    "backend/tests/test_services/test_alert_recovery.py",
    'monkeypatch.setattr(alert_service, "AsyncSessionLocal", lambda: _SessionContext(session))',
    'monkeypatch.setattr(alert_service, "trusted_background_session", lambda _cap: _SessionContext(session))',
    count=2,
)

# Internal terminal persistence gained the owner selector required to establish
# tenant RLS. The test double accepts that additive argument while preserving
# the assertion on the externally relevant task/status pair.
replace(
    "backend/tests/test_services/test_analysis_cancellation.py",
    '''    async def mark_terminal(task_id, status):\n        terminal.append((task_id, status))\n''',
    '''    async def mark_terminal(task_id, status, user_id=None):\n        assert user_id is None\n        terminal.append((task_id, status))\n''',
)
