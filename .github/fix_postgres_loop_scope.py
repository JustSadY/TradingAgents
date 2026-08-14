from pathlib import Path

path = Path("backend/postgres_tests/test_rls_integration.py")
text = path.read_text(encoding="utf-8")
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
path.write_text(text, encoding="utf-8")

# Resolve absolute `backend.*` imports when acceptance invokes pyright from the
# backend project root.
pyproject = Path("backend/pyproject.toml")
config = pyproject.read_text(encoding="utf-8")
needle = 'include = ["core/temporal.py", "schemas"]\nexclude = ["tests", "postgres_tests"]\n'
replacement = 'include = ["core/temporal.py", "schemas"]\nexclude = ["tests", "postgres_tests"]\nextraPaths = [".."]\n'
if needle not in config:
    raise SystemExit("pyright include/exclude block not found")
pyproject.write_text(config.replace(needle, replacement, 1), encoding="utf-8")

# Snapshot the immutable username before repository commits. Logging must not
# trigger async ORM lazy-loads after a commit/rollback boundary.
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

# These files were only used to try to trigger a fresh workflow. The existing
# failed run is being rerun against the latest branch instead, so remove them
# from the working tree before the final clean integration commit is assembled.
for obsolete in (
    ".github/fix_final_rls_acceptance.py",
    ".github/workflows/backend-contract-hardening-final-once.yml",
):
    candidate = Path(obsolete)
    if candidate.exists():
        candidate.unlink()
