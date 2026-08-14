from pathlib import Path

path = Path("backend/pyproject.toml")
text = path.read_text(encoding="utf-8")
duplicate = '''pythonpath = [".."]
markers = [
    "postgres_rls: PostgreSQL integration tests for runtime RLS contexts",
]
markers = [
    "slow: marks tests as slow (deselect with '-m \\"not slow\\"')",
    "integration: marks tests as integration tests (require external services)",
    "llm: marks tests that call LLM endpoints",
]
'''
merged = '''pythonpath = [".."]
markers = [
    "slow: marks tests as slow (deselect with '-m \\"not slow\\"')",
    "integration: marks tests as integration tests (require external services)",
    "llm: marks tests that call LLM endpoints",
    "postgres_rls: PostgreSQL integration tests for runtime RLS contexts",
]
'''
if duplicate not in text:
    raise SystemExit("expected duplicate pytest marker block not found")
path.write_text(text.replace(duplicate, merged, 1), encoding="utf-8")
