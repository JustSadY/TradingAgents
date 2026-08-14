from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# Docker's database image must actually ship the pgvector extension required by Alembic.
replace(
    "docker-compose.yml",
    "  postgres:\n    image: postgres:16-alpine\n",
    "  postgres:\n    image: pgvector/pgvector:0.8.6-pg16\n",
)

# Provision vector as the database superuser before the lower-privilege migration step.
prepare = Path("deploy/docker-db-prepare.sh")
text = prepare.read_text(encoding="utf-8")
needle = 'psql -v ON_ERROR_STOP=1 -d "$PGDATABASE" -v runtime="$DB_RUNTIME_USER" -v owner="$PGUSER" -v db="$PGDATABASE" <<\'SQL\'\n'
if needle not in text:
    raise SystemExit("docker db prepare SQL block not found")
text = text.replace(needle, needle + "CREATE EXTENSION IF NOT EXISTS vector;\n", 1)
prepare.write_text(text, encoding="utf-8")

# Alembic owns the pgvector table/schema, but infrastructure owns extension installation.
migration = "backend/alembic/versions/20260814_0018-7f8091a2b3c4_pgvector_and_tenant_rls.py"
replace(
    migration,
    '    op.execute("CREATE EXTENSION IF NOT EXISTS vector")\n',
    '''    op.execute(\n        """\n        DO $$\n        BEGIN\n            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN\n                RAISE EXCEPTION 'pgvector extension is not installed; provision it before running Alembic';\n            END IF;\n        END $$;\n        """\n    )\n''',
)

# Local Linux provisioning creates the extension with postgres, not the migration role.
provision = Path("deploy/provision-postgres-roles.sh")
text = provision.read_text(encoding="utf-8")
needle = 'psql_admin() { runuser -u postgres -- psql -d template1 -v ON_ERROR_STOP=1 "$@"; }\n'
if needle not in text:
    raise SystemExit("psql_admin helper not found")
text = text.replace(
    needle,
    needle
    + 'runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector"\n',
    1,
)
provision.write_text(text, encoding="utf-8")

# Ensure pgvector's server files are present for installer-managed local PostgreSQL.
install = Path("deploy/install.sh")
text = install.read_text(encoding="utf-8")
readiness = '    for _ in $(seq 1 10); do runuser -u postgres -- psql -d template1 -tAc \'SELECT 1\' >/dev/null 2>&1 && break; sleep 1; done\n\n'
if readiness not in text:
    raise SystemExit("PostgreSQL readiness loop not found")
pgvector_block = r'''    # pgvector is a database-server extension. Prefer a distro package; when it is
    # unavailable, build the pinned upstream release against the running server.
    if ! runuser -u postgres -- psql -d template1 -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1; then
        info "Installing pgvector 0.8.6 for local PostgreSQL..."
        PG_MAJOR="$(runuser -u postgres -- psql -d template1 -tAc 'SHOW server_version' | sed 's/\..*//')"
        if [ "$PM" = apt ]; then
            pm_install "postgresql-${PG_MAJOR}-pgvector" >/dev/null 2>&1 || true
            if ! runuser -u postgres -- psql -d template1 -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1; then
                pm_install "postgresql-server-dev-${PG_MAJOR}"
            fi
        else
            pm_install "pgvector_${PG_MAJOR}" >/dev/null 2>&1 || pm_install pgvector >/dev/null 2>&1 || true
            if ! runuser -u postgres -- psql -d template1 -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1; then
                pm_install "postgresql${PG_MAJOR}-devel" >/dev/null 2>&1 || pm_install postgresql-devel
            fi
        fi

        if ! runuser -u postgres -- psql -d template1 -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1; then
            PG_CONFIG_BIN="/usr/lib/postgresql/${PG_MAJOR}/bin/pg_config"
            [ -x "$PG_CONFIG_BIN" ] || PG_CONFIG_BIN="$(command -v pg_config || true)"
            [ -n "$PG_CONFIG_BIN" ] && [ -x "$PG_CONFIG_BIN" ] || die "pg_config not found after installing PostgreSQL development headers."
            CONFIG_MAJOR="$($PG_CONFIG_BIN --version | grep -oE '[0-9]+' | head -1)"
            [ "$CONFIG_MAJOR" = "$PG_MAJOR" ] || die "pg_config major $CONFIG_MAJOR does not match running PostgreSQL $PG_MAJOR."
            rm -rf /tmp/tradingagents-pgvector
            git clone --quiet --depth 1 --branch v0.8.6 https://github.com/pgvector/pgvector.git /tmp/tradingagents-pgvector
            make -C /tmp/tradingagents-pgvector PG_CONFIG="$PG_CONFIG_BIN" >/dev/null
            make -C /tmp/tradingagents-pgvector PG_CONFIG="$PG_CONFIG_BIN" install >/dev/null
            rm -rf /tmp/tradingagents-pgvector
        fi

        runuser -u postgres -- psql -d template1 -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q 1 \
            || die "pgvector server extension installation failed."
        ok "pgvector server extension installed."
    fi

'''
text = text.replace(readiness, readiness + pgvector_block, 1)

# Repair the external-DB migration credential writer introduced during role separation.
bad = 'Path(sys.argv[1]).write_text("MIGRATION_DATABASE_URL=" + shlex.quote(os.environ["MIGRATION_DATABASE_URL"]) + "\n", encoding="utf-8")'
# `bad` above represents a literal newline between the quotes in the shell file.
if bad not in text:
    raise SystemExit("migration env writer pattern not found")
text = text.replace(
    bad,
    'Path(sys.argv[1]).write_text("MIGRATION_DATABASE_URL=" + shlex.quote(os.environ["MIGRATION_DATABASE_URL"]) + "\\n", encoding="utf-8")',
    1,
)
install.write_text(text, encoding="utf-8")

# The updater must explicitly carry the root-loaded migration credential across runuser.
update = Path("deploy/update.sh")
text = update.read_text(encoding="utf-8")
text = text.replace(
    '        asuser bash -c "cd \'$WORKTREE\' && \'$NEW_VENV/bin/alembic\' -c backend/alembic.ini downgrade \'$OLD_DB_REVISION\'" >>"$LOG" 2>&1 || true\n',
    '        asuser env "MIGRATION_DATABASE_URL=$MIGRATION_DATABASE_URL" bash -c "cd \'$WORKTREE\' && \'$NEW_VENV/bin/alembic\' -c backend/alembic.ini downgrade \'$OLD_DB_REVISION\'" >>"$LOG" 2>&1 || true\n',
    1,
)
old_upgrade = 'if ! asuser bash -c "cd \'$WORKTREE\' && \'$NEW_VENV/bin/alembic\' -c backend/alembic.ini upgrade head" >>"$LOG" 2>&1; then\n'
if old_upgrade not in text:
    raise SystemExit("updater migration command not found")
text = text.replace(
    old_upgrade,
    'if ! asuser env "MIGRATION_DATABASE_URL=$MIGRATION_DATABASE_URL" bash -c "cd \'$WORKTREE\' && \'$NEW_VENV/bin/alembic\' -c backend/alembic.ini upgrade head" >>"$LOG" 2>&1; then\n',
    1,
)
update.write_text(text, encoding="utf-8")

# Keep deployment documentation aligned with the infrastructure contract.
arch = Path("docs/architecture-integrations.md")
text = arch.read_text(encoding="utf-8")
anchor = "Migration credentials are excluded from the application `.env`/process."
if anchor not in text:
    raise SystemExit("architecture RLS paragraph not found")
text = text.replace(
    anchor,
    "The pgvector extension itself is provisioned by the database superuser before Alembic; Alembic owns the `memory_vectors` table and tenant schema changes. Docker pins `pgvector/pgvector:0.8.6-pg16`, while the Linux installer installs or builds the same pinned extension release.\n\n" + anchor,
    1,
)
arch.write_text(text, encoding="utf-8")
