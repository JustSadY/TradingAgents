from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# Acceptance runs from backend/, so pyright paths are relative to that project
# root. extraPaths keeps absolute ``backend.*`` imports resolvable from there.
replace(
    "backend/pyproject.toml",
    'include = ["backend/core/temporal.py", "backend/schemas"]\nexclude = ["backend/tests"]\n',
    'include = ["core/temporal.py", "schemas"]\nexclude = ["tests", "postgres_tests"]\nextraPaths = [".."]\n',
)

# Alert recovery now opens an audited trusted-background context instead of a
# raw AsyncSessionLocal session. Keep unit doubles attached to that public seam.
replace(
    "backend/tests/test_services/test_alert_recovery.py",
    'monkeypatch.setattr(alert_service, "AsyncSessionLocal", lambda: _SessionContext(session))',
    'monkeypatch.setattr(alert_service, "trusted_background_session", lambda _cap: _SessionContext(session))',
    count=2,
)

# Internal terminal persistence gained the owner selector required to establish
# tenant RLS. The test double accepts that additive argument.
replace(
    "backend/tests/test_services/test_analysis_cancellation.py",
    '''    async def mark_terminal(task_id, status):\n        terminal.append((task_id, status))\n''',
    '''    async def mark_terminal(task_id, status, user_id=None):\n        assert user_id is None\n        terminal.append((task_id, status))\n''',
)

# PostgreSQL integration tests use one event loop because the application owns
# module-level async engines/pools. This is test-harness lifecycle, not an RLS
# relaxation.
postgres_test = Path("backend/postgres_tests/test_rls_integration.py")
text = postgres_test.read_text(encoding="utf-8")
text = text.replace(
    "pytestmark = pytest.mark.postgres_rls\n",
    'pytestmark = [pytest.mark.postgres_rls, pytest.mark.asyncio(loop_scope="session")]\n',
    1,
)
text = text.replace(
    "@pytest_asyncio.fixture(autouse=True)\nasync def _clean_database():\n",
    '@pytest_asyncio.fixture(autouse=True, loop_scope="session")\nasync def _clean_database():\n',
    1,
)
text = text.replace(
    "@pytest_asyncio.fixture\nasync def seeded():\n",
    '@pytest_asyncio.fixture(loop_scope="session")\nasync def seeded():\n',
    1,
)
text = text.replace("@pytest.mark.asyncio\n", "")
text = text.replace(
    '        assert active.json()["analysis"]["final_decision"] == "A report"\n',
    '        assert active.json()["final_decision"] == "A report"\n',
    1,
)
postgres_test.write_text(text, encoding="utf-8")

# Snapshot the immutable username before repository commits. Logging must not
# trigger an async ORM lazy-load after a commit/rollback boundary.
cron = Path("backend/services/cron_service.py")
cron_text = cron.read_text(encoding="utf-8")
old = '''            trade_date = _trade_date_for_asset("stock")\n            _logger.info(\n                "User cron watchlist scan started for user=%s (id=%d), date=%s",\n                user.username, user_id, trade_date,\n            )\n'''
new = '''            trade_date = _trade_date_for_asset("stock")\n            username = user.username\n            _logger.info(\n                "User cron watchlist scan started for user=%s (id=%d), date=%s",\n                username, user_id, trade_date,\n            )\n'''
if old not in cron_text:
    raise SystemExit("cron username snapshot insertion point not found")
cron_text = cron_text.replace(old, new, 1)
start = cron_text.index("    async def _run_user_watchlist_scan_once")
end = cron_text.index("\n    def get_status", start)
segment = cron_text[start:end].replace("user.username", "username")
cron.write_text(cron_text[:start] + segment + cron_text[end:], encoding="utf-8")

# Build a candidate commit from the current integration tree, but push only to
# a temp ref. The workflow tests the exact same backend patch afterward; the
# integration ref is advanced only by the controlling agent after every gate
# succeeds.
BASE = "54ab148cc4b0b6609ddaf0e9884391ece49e59df"
EXPECTED_INTEGRATION = "95059fef4bf05f6d2ba5bdb989048d1f5b244070"
CANDIDATE_REF = "refs/heads/tmp/backend-hardening-candidate-rerun3"

subprocess.run(["git", "fetch", "origin", "integration/memory-maintenance-base"], check=True)
actual = subprocess.check_output(
    ["git", "rev-parse", "origin/integration/memory-maintenance-base"], text=True
).strip()
if actual != EXPECTED_INTEGRATION:
    raise SystemExit(f"integration branch moved: {actual}")

with tempfile.TemporaryDirectory(prefix="backend-hardening-candidate-") as tmp:
    root = Path(tmp)
    patch = root / "backend.patch"
    with patch.open("wb") as handle:
        subprocess.run(["git", "diff", "--binary", BASE, "--", "backend"], stdout=handle, check=True)
    if not patch.stat().st_size:
        raise SystemExit("backend hardening patch is empty")

    worktree = root / "worktree"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree), "origin/integration/memory-maintenance-base"],
        check=True,
    )
    try:
        subprocess.run(["git", "-C", str(worktree), "apply", "--index", str(patch)], check=True)
        validator = worktree / ".github/workflows/validate-backend-hardening-once.yml"
        if validator.exists():
            validator.unlink()
            subprocess.run(
                ["git", "-C", str(worktree), "add", "-u", ".github/workflows/validate-backend-hardening-once.yml"],
                check=True,
            )
        changed = subprocess.check_output(
            ["git", "-C", str(worktree), "diff", "--cached", "--name-only"], text=True
        ).splitlines()
        if any(path.startswith("frontend/") for path in changed):
            raise SystemExit("frontend would be included in backend hardening candidate")
        subprocess.run(["git", "-C", str(worktree), "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(
            ["git", "-C", str(worktree), "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "commit", "-m", "Harden RLS and backend API schema contracts"],
            check=True,
        )
        subprocess.run(["git", "-C", str(worktree), "push", "origin", f"HEAD:{CANDIDATE_REF}"], check=True)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], check=False)
