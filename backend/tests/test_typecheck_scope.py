from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parents[2]
PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"
VALIDATION_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "backend-validation.yml"


def _pyright_section() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    marker = "[tool.pyright]"
    assert marker in text
    return text.split(marker, 1)[1]


@pytest.mark.parametrize(
    "scope",
    [
        '"repositories"',
        '"core"',
        '"services"',
        '"api"',
    ],
)
def test_pyright_covers_backend_layers(scope: str) -> None:
    assert scope in _pyright_section()


def test_backend_validation_keeps_type_lint_and_test_gates() -> None:
    workflow = VALIDATION_WORKFLOW.read_text(encoding="utf-8")

    assert "uv run --project backend pyright" in workflow
    assert "uv run --project backend ruff check" in workflow
    assert "uv run --project backend pytest backend/tests" in workflow
    assert "pull_request:" in workflow
    assert "- main" in workflow
