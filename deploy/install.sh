#!/usr/bin/env bash
#
# TradingAgents — single-command Linux installation + systemd service.
#
#   sudo bash deploy/install.sh
#
# Actions performed (all idempotent — safe to re-run):
#   1. System dependencies: Python 3.11–3.13, Node 20, PostgreSQL, git, curl
#   2. Versioned Python virtual environment + backend/pyproject.toml + backend/uv.lock
#   3. Frontend build (npm) -> frontend/dist (served by backend)
#   4. PostgreSQL database + user setup
#   5. .env generation (secure random SECRET_KEY / ENCRYPTION_KEY / DB password)
#      — only if .env does not exist. The administrator account is registered
#      in the browser on first visit, not from .env.
#   6. systemd service (single process: in-memory WebSocket + APScheduler cron
#      will break with multiple workers, so uvicorn runs as single process)
#   7. Enable + start service and perform health check
#
# Environment variable overrides (optional):
#   SERVICE_NAME=tradingagents  SERVICE_USER=<user>  APP_PORT=8000
#   NODE_MAJOR=20
#   SKIP_DB=1 (use external PostgreSQL)   BUILD_FRONTEND=0 (skip UI build)
#
set -euo pipefail

# ── Configuration (can be overridden via environment variables) ────────────
SERVICE_NAME="${SERVICE_NAME:-tradingagents}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
DB_NAME_DEFAULT="${DB_NAME:-tradingagents}"
DB_USER_DEFAULT="${DB_USER:-tradingagents}"
NODE_MAJOR="${NODE_MAJOR:-20}"
SKIP_DB="${SKIP_DB:-0}"
BUILD_FRONTEND="${BUILD_FRONTEND:-1}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJECT_ROOT/.venv"
VENV_ROOT="$PROJECT_ROOT/.tradingagents-venvs"
ENV_FILE="$PROJECT_ROOT/.env"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# In-app auto-updater components
UPDATE_UNIT="${SERVICE_NAME}-update"
UPDATE_UNIT_FILE="/etc/systemd/system/${UPDATE_UNIT}.service"
UPDATER_BIN="/usr/local/sbin/tradingagents-update"
UPDATE_CONF="/etc/tradingagents/update.env"
MIGRATION_ENV_FILE="/etc/tradingagents/migration.env"
SUDOERS_FILE="/etc/sudoers.d/${SERVICE_NAME}-update"

# Service execution user: defaults to the user who invoked sudo if not set.
RUN_USER="${SERVICE_USER:-${SUDO_USER:-root}}"

# ── Logging ─────────────────────────────────────────────────────────────────────
info() { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# ── Pre-flight checks ───────────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "This script requires root: sudo bash deploy/install.sh"
[ -f "$PROJECT_ROOT/backend/pyproject.toml" ] || die "backend/pyproject.toml not found — run from project root."
[ -f "$PROJECT_ROOT/backend/uv.lock" ] || die "backend/uv.lock not found — run uv lock before deployment."
[ -d "$PROJECT_ROOT/frontend" ] || die "frontend/ directory not found — unexpected project layout."
command -v systemctl >/dev/null || die "systemd (systemctl) not found — this script is for systemd-based distributions."
SYSTEMCTL_BIN="$(command -v systemctl)"

id "$RUN_USER" &>/dev/null || {
    info "Creating service user '$RUN_USER'..."
    useradd --system --create-home --shell /usr/sbin/nologin "$RUN_USER"
}

# ── Package manager detection ────────────────────────────────────────────────────
if   command -v apt-get >/dev/null; then PM=apt
elif command -v dnf     >/dev/null; then PM=dnf
elif command -v yum     >/dev/null; then PM=yum
else die "No supported package manager found (apt/dnf/yum)."; fi
info "Package manager: $PM"

pm_install() {
    case "$PM" in
        apt) DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
        dnf) dnf install -y "$@" ;;
        yum) yum install -y "$@" ;;
    esac
}

# ── 1. System dependencies ────────────────────────────────────────────────────
info "Installing system packages..."
if [ "$PM" = apt ]; then
    apt-get update -y
    pm_install python3 python3-venv python3-dev build-essential libpq-dev git curl ca-certificates sudo
    [ "$SKIP_DB" = 1 ] || pm_install postgresql postgresql-contrib
else
    pm_install python3 python3-devel gcc gcc-c++ make git curl sudo
    [ "$SKIP_DB" = 1 ] || pm_install postgresql-server postgresql-contrib || true
fi
ok "System packages ready."

# ── Select Python 3.11–3.13 ────────────────────────────────────────────────────
pick_python() {
    local c v
    for c in python3.13 python3.12 python3.11 python3; do
        command -v "$c" >/dev/null || continue
        v=$("$c" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
        if [ "$v" -ge 311 ] && [ "$v" -lt 314 ]; then echo "$c"; return 0; fi
    done
    return 1
}
PYTHON="$(pick_python)" || die "No supported Python 3.11–3.13 interpreter found. Please install python3.11–3.13."
info "Python: $PYTHON ($("$PYTHON" --version 2>&1))"

# ── 2. Node 20 (Required for Vite 8) ───────────────────────────────────────────
if [ "$BUILD_FRONTEND" = 1 ]; then
    node_major() { command -v node >/dev/null && node -v | sed 's/v\([0-9]*\).*/\1/' || echo 0; }
    if [ "$(node_major)" -lt "$NODE_MAJOR" ]; then
        info "Installing Node $NODE_MAJOR (NodeSource)..."
        if [ "$PM" = apt ]; then
            curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource.sh
            bash /tmp/nodesource.sh >/dev/null
            pm_install nodejs
        else
            curl -fsSL "https://rpm.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource.sh
            bash /tmp/nodesource.sh >/dev/null
            pm_install nodejs
        fi
    fi
    ok "Node $(node -v) / npm $(npm -v)"
fi

# ── 3. Versioned Python venv + dependencies ───────────────────────────────────
CURRENT_REV="$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null)" || die "Project root is not a Git checkout."
VENV_TARGET="$VENV_ROOT/${CURRENT_REV:0:16}"
info "Preparing versioned Python virtual environment: $VENV_TARGET"
mkdir -p "$VENV_ROOT"

# Old installers created a plain .venv directory. It contains only derived
# dependencies, so normalize it by rebuilding rather than preserving a second
# compatibility layout. New installs and reruns always leave .venv as a symlink.
if [ -e "$VENV" ] && [ ! -L "$VENV" ]; then
    warn "Replacing obsolete plain .venv layout with the versioned release layout."
    rm -rf "$VENV"
fi
if [ ! -x "$VENV_TARGET/bin/python" ]; then
    "$PYTHON" -m venv "$VENV_TARGET"
fi
rm -f "$VENV"
ln -s "$VENV_TARGET" "$VENV"

"$VENV_TARGET/bin/pip" install --upgrade pip wheel uv >/dev/null
info "Syncing backend dependencies from pyproject.toml + uv.lock..."
(
    cd "$PROJECT_ROOT/backend"
    UV_PROJECT_ENVIRONMENT="$VENV_TARGET" "$VENV_TARGET/bin/uv" lock --check
    UV_PROJECT_ENVIRONMENT="$VENV_TARGET" "$VENV_TARGET/bin/uv" sync --frozen --no-dev
)
ok "Frozen Python dependencies installed."

# ── 4. Frontend build ───────────────────────────────────────────────────────────
if [ "$BUILD_FRONTEND" = 1 ]; then
    info "Building frontend (npm)..."
    pushd "$PROJECT_ROOT/frontend" >/dev/null
    if [ -f package-lock.json ]; then npm ci || npm install; else npm install; fi
    npm run build
    popd >/dev/null
    [ -f "$PROJECT_ROOT/frontend/dist/index.html" ] || die "Frontend build failed (dist/index.html not found)."
    ok "Frontend built -> frontend/dist"
else
    warn "BUILD_FRONTEND=0 — UI build skipped (API only)."
fi

# ── 5. .env (generate only if missing) ─────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    info "Generating .env (secure random secrets)..."
    SECRET_KEY=$("$PYTHON" -c 'import secrets;print(secrets.token_hex(32))')
    ENCRYPTION_KEY=$("$PYTHON" -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
    DB_USER="$DB_USER_DEFAULT"
    DB_NAME="$DB_NAME_DEFAULT"
    DB_PASS=$("$PYTHON" -c 'import secrets;print(secrets.token_urlsafe(24))')

    {
        printf "ENVIRONMENT='production'\n"
        printf "RLS_STRICT_MODE='true'\n"
        printf "SECRET_KEY='%s'\n"          "$SECRET_KEY"
        printf "ENCRYPTION_KEY='%s'\n"      "$ENCRYPTION_KEY"
        printf "DATABASE_URL='postgresql+asyncpg://%s:%s@localhost:5432/%s'\n" "$DB_USER" "$DB_PASS" "$DB_NAME"
        printf "CORS_ORIGINS='[\"http://localhost:%s\"]'\n" "$APP_PORT"
        printf '\n# LLM Provider API keys — fill at least one, then: systemctl restart %s\n' "$SERVICE_NAME"
        printf '\n# Data provider API keys (optional)\nALPHA_VANTAGE_API_KEY=\nREDDIT_CLIENT_ID=\nREDDIT_CLIENT_SECRET=\n'
    } > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ok ".env created."
else
    info ".env already exists — preserving existing file (secrets not regenerated)."
fi

# Installer-managed systemd deployments are production and RLS fail-closed.
if grep -q "^ENVIRONMENT=" "$ENV_FILE"; then
    sed -i "s/^ENVIRONMENT=.*/ENVIRONMENT=production/" "$ENV_FILE"
else
    printf "\nENVIRONMENT=production\n" >> "$ENV_FILE"
fi
if grep -q "^RLS_STRICT_MODE=" "$ENV_FILE"; then
    sed -i "s/^RLS_STRICT_MODE=.*/RLS_STRICT_MODE=true/" "$ENV_FILE"
else
    printf "RLS_STRICT_MODE=true\n" >> "$ENV_FILE"
fi

# Read DB credentials from .env for Postgres setup
read DB_USER DB_PASS DB_NAME < <(
    "$VENV/bin/python" - "$ENV_FILE" <<'PY'
import sys, urllib.parse as u
from dotenv import dotenv_values
url = dotenv_values(sys.argv[1]).get("DATABASE_URL", "")
p = u.urlsplit(url)
print(p.username or "", p.password or "", (p.path or "/").lstrip("/"))
PY
) || true
[ -n "${DB_NAME:-}" ] || die "Could not parse DATABASE_URL from .env."

# ── 6. PostgreSQL database + user ────────────────────────────────────────
if [ "$SKIP_DB" = 1 ]; then
    warn "SKIP_DB=1 — Skipping PostgreSQL setup (expecting external DB)."
else
    info "Configuring PostgreSQL..."
    if [ "$PM" != apt ]; then
        if [ ! -s /var/lib/pgsql/data/PG_VERSION ]; then
            (postgresql-setup --initdb || /usr/bin/postgresql-setup initdb) || true
        fi
        HBA=/var/lib/pgsql/data/pg_hba.conf
        [ -f "$HBA" ] && sed -i 's/^\(host\s\+all\s\+all\s\+127.0.0.1\/32\s\+\)ident/\1scram-sha-256/' "$HBA" || true
    fi
    systemctl enable --now postgresql >/dev/null 2>&1 || systemctl enable --now postgresql || die "Failed to start postgresql."

    for _ in $(seq 1 10); do runuser -u postgres -- psql -d template1 -tAc 'SELECT 1' >/dev/null 2>&1 && break; sleep 1; done

    # pgvector is a database-server extension. Prefer a distro package; when it is
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

    psql_admin() { runuser -u postgres -- psql -d template1 -v ON_ERROR_STOP=1 "$@"; }
    if psql_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        psql_admin -c "ALTER ROLE \"$DB_USER\" LOGIN PASSWORD '$DB_PASS';"
    else
        psql_admin -c "CREATE ROLE \"$DB_USER\" LOGIN PASSWORD '$DB_PASS';"
    fi
    if ! psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
        runuser -u postgres -- createdb --maintenance-db=template1 -O "$DB_USER" "$DB_NAME"
    fi
    ok "PostgreSQL ready (db=$DB_NAME, user=$DB_USER)."
fi

# ── 6b. Separate migration/runtime database roles + migrate ─────────────────
if [ "$SKIP_DB" = 1 ]; then
    [ -n "${MIGRATION_DATABASE_URL:-}" ] || die "SKIP_DB=1 requires MIGRATION_DATABASE_URL in the installer environment; it is never stored in the app .env."
    install -d -m 700 "$(dirname "$MIGRATION_ENV_FILE")"
    MIGRATION_DATABASE_URL="$MIGRATION_DATABASE_URL" "$PYTHON" - "$MIGRATION_ENV_FILE" <<'PY'
import os, shlex, sys
from pathlib import Path
Path(sys.argv[1]).write_text("MIGRATION_DATABASE_URL=" + shlex.quote(os.environ["MIGRATION_DATABASE_URL"]) + "\n", encoding="utf-8")
PY
    chmod 600 "$MIGRATION_ENV_FILE"
else
    DB_USER="$DB_USER" DB_PASS="$DB_PASS" DB_NAME="$DB_NAME" \
        MIGRATION_ENV_FILE="$MIGRATION_ENV_FILE" \
        bash "$PROJECT_ROOT/deploy/provision-postgres-roles.sh"
fi

set -a
# shellcheck disable=SC1090
. "$MIGRATION_ENV_FILE"
set +a
: "${MIGRATION_DATABASE_URL:?migration URL was not provisioned}"
info "Applying Alembic migrations with the isolated migration role..."
PYTHONPATH="$PROJECT_ROOT" "$VENV/bin/alembic" -c "$PROJECT_ROOT/backend/alembic.ini" upgrade head
# LangGraph creates its checkpoint tables through setup(), which needs CREATE
# on the schema. The runtime role deliberately has none, so they are
# provisioned here with the migration credential instead.
info "Provisioning LangGraph checkpoint tables with the migration role..."
PYTHONPATH="$PROJECT_ROOT" "$VENV/bin/python" "$PROJECT_ROOT/backend/scripts/provision-checkpoints.py"
unset MIGRATION_DATABASE_URL
ok "Database migrations applied; runtime role remains non-owner/NOBYPASSRLS."

# ── File Ownership ─────────────────────────────────────────────────────────────
info "Giving file ownership to '$RUN_USER' user..."
chown -R "$RUN_USER":"$RUN_USER" "$PROJECT_ROOT" 2>/dev/null || true

# ── 7. systemd service ──────────────────────────────────────────────────────────
info "Writing systemd service unit: $UNIT_FILE"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=TradingAgents Web (FastAPI + multi-agent LLM trading)
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_ROOT
Environment=PYTHONPATH=$PROJECT_ROOT
Environment=PYTHONUNBUFFERED=1
Environment=TRADINGAGENTS_UPDATE_UNIT=${UPDATE_UNIT}.service
Environment=TRADINGAGENTS_SYSTEMCTL=$SYSTEMCTL_BIN
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/uvicorn backend.main:app --host $APP_HOST --port $APP_PORT --no-date-header --no-access-log --ws-ping-interval 20 --ws-ping-timeout 20
Restart=on-failure
RestartSec=5
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# ── In-app automatic updater ("Update" button) ────────────────────────
info "Installing automatic update components..."
mkdir -p "$(dirname "$UPDATE_CONF")" "$(dirname "$UPDATER_BIN")"
cat > "$UPDATE_CONF" <<EOF
PROJECT_ROOT=$PROJECT_ROOT
SERVICE_NAME=$SERVICE_NAME
RUN_USER=$RUN_USER
VENV=$VENV
MIGRATION_ENV_FILE=$MIGRATION_ENV_FILE
EOF
chmod 644 "$UPDATE_CONF"

install -m 0755 -o root -g root "$PROJECT_ROOT/deploy/update.sh" "$UPDATER_BIN"

cat > "$UPDATE_UNIT_FILE" <<EOF
[Unit]
Description=TradingAgents in-place updater (oneshot)
After=network-online.target

[Service]
Type=oneshot
ExecStart=$UPDATER_BIN
EOF

cat > "$SUDOERS_FILE" <<EOF
$RUN_USER ALL=(root) NOPASSWD: $SYSTEMCTL_BIN start --no-block ${UPDATE_UNIT}.service
EOF
chmod 440 "$SUDOERS_FILE"
if visudo -cf "$SUDOERS_FILE" >/dev/null 2>&1; then
    ok "In-app updater ready."
else
    rm -f "$SUDOERS_FILE"
    warn "sudoers validation failed — in-app updater disabled (manual: sudo bash deploy/update.sh)."
fi

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl restart "$SERVICE_NAME"
ok "Service started: $SERVICE_NAME"

# ── 8. Logrotate ────────────────────────────────────────────────────────────────
if command -v logrotate >/dev/null; then
    info "Installing Logrotate configuration..."
    cp "$PROJECT_ROOT/deploy/logrotate.conf" /etc/logrotate.d/tradingagents 2>/dev/null && \
        ok "Logrotate installed: /etc/logrotate.d/tradingagents" || \
        warn "Logrotate configuration failed."
else
    warn "logrotate not found — log rotation skipped."
fi

if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "${APP_PORT}/tcp" >/dev/null 2>&1 || true
    info "ufw: opened port ${APP_PORT}/tcp."
fi

# ── Health check ─────────────────────────────────────────────────────────────
info "Performing health check..."
HEALTHY=0
for _ in $(seq 1 15); do
    if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then HEALTHY=1; break; fi
    sleep 1
done

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
if [ "$HEALTHY" = 1 ]; then
    ok "============================================================"
    ok " TradingAgents is running 🎉"
    ok "============================================================"
    echo "  UI       :  http://localhost:${APP_PORT}"
    [ -n "$LAN_IP" ] && echo "             http://${LAN_IP}:${APP_PORT}"
    echo "  Admin    :  open the UI — the first visit asks you to create the"
    echo "              administrator account (no password is stored in .env)."
    echo
    echo "  ⚠  Add LLM API key:  nano $ENV_FILE   then: systemctl restart $SERVICE_NAME"
    echo
    echo "  🔄 Updates: An 'Update' button appears in the UI header when a new commit is pushed"
    echo "             (staged build + migration + release switch). Manual: sudo bash deploy/update.sh"
    echo
    echo "  Management Commands:"
    echo "    journalctl -u $SERVICE_NAME -f              # live logs"
    echo "    systemctl restart|stop $SERVICE_NAME"
    echo "    bash deploy/backup.sh                       # manual backup"
    echo "    bash deploy/setup-backup-cron.sh            # automatic backup (systemd timer)"
    echo "    bash deploy/uninstall.sh                     # uninstall"
else
    err "Service health check failed. Inspect logs:"
    err "    journalctl -u $SERVICE_NAME -n 50 --no-pager"
    exit 1
fi
