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
