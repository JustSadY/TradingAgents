from __future__ import annotations

from pathlib import Path

import pytest


PYPROJECT = Path(__file__).parents[1] / "pyproject.toml"


def _pyright_include() -> str:
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
    config = _pyright_include()
    assert scope in config
