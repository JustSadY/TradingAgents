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


def test_uninstall_purge_removes_versioned_virtualenv_root() -> None:
    source = (_repo_root() / "deploy" / "uninstall.sh").read_text()

    assert 'VENV_ROOT="$PROJECT_ROOT/.tradingagents-venvs"' in source
    assert 'rm -f "$VENV"' in source
    assert 'rm -rf "$VENV_ROOT"' in source


def test_updater_never_claims_database_schema_rollback() -> None:
    updater = (_repo_root() / "deploy" / "update.sh").read_text()
    readme = (_repo_root() / "deploy" / "README.md").read_text()

    assert "schema downgrades are never automated" in updater
    assert "Database schema downgrades are never automated" in readme


def test_pgvector_is_checked_before_migrations_run() -> None:
    """Revision 20260814_0018 raises without the extension, so a missing one
    must be reported by the preflight rather than mid-migration."""
    installer = (_repo_root() / "deploy" / "install.sh").read_text()

    check = installer.index("provision-pgvector.py")
    migrate = installer.index('alembic.ini" upgrade head')
    assert check < migrate


def test_updater_checks_pgvector_before_taking_the_site_down() -> None:
    updater = (_repo_root() / "deploy" / "update.sh").read_text()

    check = updater.index("provision-pgvector.py")
    stop = updater.index("stopping web/worker services")
    migrate = updater.index("alembic' -c backend/alembic.ini upgrade head")
    assert check < stop < migrate
