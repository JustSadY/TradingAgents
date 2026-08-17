from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_installer_owns_versioned_virtualenv_layout() -> None:
    source = (_repo_root() / "deploy" / "install.sh").read_text()

    assert 'VENV_ROOT="$PROJECT_ROOT/.tradingagents-venvs"' in source
    assert 'VENV_TARGET="$VENV_ROOT/${CURRENT_REV:0:16}"' in source
    assert 'ln -s "$VENV_TARGET" "$VENV"' in source
    assert '[ -d "$VENV" ] || "$PYTHON" -m venv "$VENV"' not in source


def test_updater_rejects_plain_legacy_venv_layout() -> None:
    source = (_repo_root() / "deploy" / "update.sh").read_text()

    assert '[ -L "$VENV" ] || fail' in source
    assert 'OLD_VENV_TARGET="$(readlink -f "$VENV")"' in source
    assert 'legacy-${FROM' not in source
    assert 'mv "$VENV" "$OLD_VENV_TARGET"' not in source


def test_updater_never_claims_database_schema_rollback() -> None:
    updater = (_repo_root() / "deploy" / "update.sh").read_text()
    readme = (_repo_root() / "deploy" / "README.md").read_text()

    assert "schema downgrades are never automated" in updater
    assert "Database schema downgrades are never automated" in readme
