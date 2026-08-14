#!/usr/bin/env bash
#
# Staged updater. The target revision is built and validated in an isolated
# worktree/virtualenv before the running service is stopped. The live checkout
# and venv are switched only after preflight succeeds; restart failures restore
# the previous revision and environment. Database changes must follow the
# expand/contract rule because schema downgrades are never automated.
#
set -euo pipefail

CONF="${TRADINGAGENTS_UPDATE_CONF:-/etc/tradingagents/update.env}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-tradingagents}"
WORKER_SERVICE_NAME="${WORKER_SERVICE_NAME:-tradingagents-worker}"
RUN_USER="${RUN_USER:-${SUDO_USER:-root}}"
VENV="${VENV:-$PROJECT_ROOT/.venv}"
MIGRATION_ENV_FILE="${MIGRATION_ENV_FILE:-/etc/tradingagents/migration.env}"
[ -r "$MIGRATION_ENV_FILE" ] || { echo "Missing migration credential file: $MIGRATION_ENV_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
. "$MIGRATION_ENV_FILE"
set +a
: "${MIGRATION_DATABASE_URL:?missing MIGRATION_DATABASE_URL}"

: "${PROJECT_ROOT:?missing PROJECT_ROOT}"
: "${SERVICE_NAME:?missing SERVICE_NAME}"
: "${RUN_USER:?missing RUN_USER}"
: "${VENV:?missing VENV}"

STATUS="$PROJECT_ROOT/.update.json"
LOG="$PROJECT_ROOT/.update.log"
LOCK_FILE="$PROJECT_ROOT/.update.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "Another update is already running" >&2; exit 1; }
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
[ -n "$RUN_HOME" ] || RUN_HOME="/home/$RUN_USER"

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
asuser() { runuser -u "$RUN_USER" -- env "HOME=$RUN_HOME" "$@"; }
log() { echo "[$(now)] $*" >>"$LOG" 2>/dev/null || true; chown "$RUN_USER":"$RUN_USER" "$LOG" 2>/dev/null || true; }
write_status() {
    local err="null"
    [ -n "${2:-}" ] && err="$(printf '%s' "$2" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '"error"')"
    local tmp_status="${STATUS}.tmp.$$"
    printf '{"state":"%s","at":"%s","from":"%s","to":"%s","error":%s}\n' \
        "$1" "$(now)" "${FROM:-?}" "${TO:-?}" "$err" >"$tmp_status" 2>/dev/null || true
    chown "$RUN_USER":"$RUN_USER" "$tmp_status" 2>/dev/null || true
    mv -f "$tmp_status" "$STATUS"
}
fail() { log "ERROR: $1"; write_status failed "$1"; exit 1; }
run_user() { log "+ $*"; asuser "$@" >>"$LOG" 2>&1 || fail "Command failed: $*"; }

FROM="$(asuser git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo '?')"
TO="$FROM"
write_status running
log "=== Staged update started (${FROM:0:12}) ==="

if ! asuser git -C "$PROJECT_ROOT" diff --quiet --ignore-submodules -- || \
   ! asuser git -C "$PROJECT_ROOT" diff --cached --quiet --ignore-submodules --; then
    fail "Local tracked changes exist; refusing to overwrite the live checkout"
fi

run_user git -C "$PROJECT_ROOT" fetch --all --prune --quiet
UPSTREAM="$(asuser git -C "$PROJECT_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
[ -n "$UPSTREAM" ] || fail "Current branch has no upstream"
TO="$(asuser git -C "$PROJECT_ROOT" rev-parse "$UPSTREAM")"
if [ "$TO" = "$FROM" ]; then
    write_status done
    log "Already up to date"
    exit 0
fi

STAGE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/tradingagents-release.XXXXXX")"
WORKTREE="$STAGE_ROOT/src"
VENV_ROOT="$(dirname "$VENV")/.tradingagents-venvs"
NEW_VENV="$VENV_ROOT/${TO:0:16}"
DIST_ARCHIVE="$STAGE_ROOT/frontend-dist.tar"
OLD_DIST_ARCHIVE="$STAGE_ROOT/old-frontend-dist.tar"
OLD_VENV_TARGET=""
SERVICE_STOPPED=0
WORKER_STOPPED=0
SWITCHED=0
DB_MIGRATED=0
OLD_DB_REVISION=""

cleanup() {
    asuser git -C "$PROJECT_ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
    rm -rf "$STAGE_ROOT" >/dev/null 2>&1 || true
}
trap cleanup EXIT

rollback() {
    local reason="$1"
    log "Rollback requested: $reason"
    if [ "$SWITCHED" -eq 1 ]; then
        asuser git -C "$PROJECT_ROOT" reset --hard "$FROM" >>"$LOG" 2>&1 || true
        if [ -f "$OLD_DIST_ARCHIVE" ]; then
            rm -rf "$PROJECT_ROOT/frontend/dist"
            mkdir -p "$PROJECT_ROOT/frontend/dist"
            tar -xf "$OLD_DIST_ARCHIVE" -C "$PROJECT_ROOT/frontend/dist" 2>>"$LOG" || true
            chown -R "$RUN_USER":"$RUN_USER" "$PROJECT_ROOT/frontend/dist" 2>/dev/null || true
        fi
        if [ -n "$OLD_VENV_TARGET" ]; then
            rm -rf "$VENV"
            if [ -L "$OLD_VENV_TARGET" ] || [ -d "$OLD_VENV_TARGET" ]; then
                ln -s "$OLD_VENV_TARGET" "$VENV"
            fi
        fi
    fi
    if [ "$DB_MIGRATED" -eq 1 ] && [ -n "$OLD_DB_REVISION" ]; then
        asuser bash -c "cd '$WORKTREE' && '$NEW_VENV/bin/alembic' -c backend/alembic.ini downgrade '$OLD_DB_REVISION'" >>"$LOG" 2>&1 || true
    fi
    if [ "$WORKER_STOPPED" -eq 1 ]; then
        systemctl start "$WORKER_SERVICE_NAME" >>"$LOG" 2>&1 || true
    fi
    if [ "$SERVICE_STOPPED" -eq 1 ]; then
        systemctl start "$SERVICE_NAME" >>"$LOG" 2>&1 || true
    fi
    fail "$reason"
}

# Isolated preflight: source, dependencies, imports, tests, and frontend build.
run_user git -C "$PROJECT_ROOT" worktree add --detach "$WORKTREE" "$TO"
mkdir -p "$VENV_ROOT"
chown -R "$RUN_USER":"$RUN_USER" "$VENV_ROOT"
if [ ! -x "$NEW_VENV/bin/python" ]; then
    run_user python3 -m venv "$NEW_VENV"
fi
run_user "$NEW_VENV/bin/python" -m pip install --upgrade pip wheel uv
run_user "$NEW_VENV/bin/uv" lock --check --project "$WORKTREE/backend"
run_user env UV_PROJECT_ENVIRONMENT="$NEW_VENV" "$NEW_VENV/bin/uv" sync --frozen --no-dev --project "$WORKTREE/backend"
run_user "$NEW_VENV/bin/python" -m compileall -q "$WORKTREE/backend"
if [ -d "$WORKTREE/frontend" ]; then
    run_user bash -c "cd '$WORKTREE/frontend' && npm ci && npm run lint && npm test && npm run build"
    tar -cf "$DIST_ARCHIVE" -C "$WORKTREE/frontend/dist" .
fi

# Keep a reversible copy of browser assets and the existing venv target.
if [ -d "$PROJECT_ROOT/frontend/dist" ]; then
    tar -cf "$OLD_DIST_ARCHIVE" -C "$PROJECT_ROOT/frontend/dist" .
fi
if [ -L "$VENV" ]; then
    OLD_VENV_TARGET="$(readlink -f "$VENV")"
elif [ -d "$VENV" ]; then
    OLD_VENV_TARGET="$VENV_ROOT/legacy-${FROM:0:16}"
fi

log "Preflight passed; stopping web/worker services for migration and release switch"
if systemctl list-unit-files "$WORKER_SERVICE_NAME.service" --no-legend 2>/dev/null | grep -q "^$WORKER_SERVICE_NAME.service"; then
    systemctl stop "$WORKER_SERVICE_NAME" >>"$LOG" 2>&1 || rollback "Could not stop worker: $WORKER_SERVICE_NAME"
    WORKER_STOPPED=1
fi
systemctl stop "$SERVICE_NAME" >>"$LOG" 2>&1 || rollback "Could not stop service: $SERVICE_NAME"
SERVICE_STOPPED=1
OLD_DB_REVISION="$(asuser bash -c "cd '$PROJECT_ROOT' && '$VENV/bin/alembic' -c backend/alembic.ini current 2>/dev/null | head -1 | awk '{print \$1}'" || true)"

# PostgreSQL DDL migrations are transactional. Migrations in this repository
# must remain backward-compatible with the previous release (expand/contract).
if ! asuser bash -c "cd '$WORKTREE' && '$NEW_VENV/bin/alembic' -c backend/alembic.ini upgrade head" >>"$LOG" 2>&1; then
    rollback "Database migration failed"
fi
DB_MIGRATED=1

if ! asuser git -C "$PROJECT_ROOT" reset --hard "$TO" >>"$LOG" 2>&1; then
    rollback "Could not switch live checkout to target revision"
fi
if [ -f "$DIST_ARCHIVE" ]; then
    rm -rf "$PROJECT_ROOT/frontend/dist"
    mkdir -p "$PROJECT_ROOT/frontend/dist"
    tar -xf "$DIST_ARCHIVE" -C "$PROJECT_ROOT/frontend/dist"
    chown -R "$RUN_USER":"$RUN_USER" "$PROJECT_ROOT/frontend/dist" 2>/dev/null || true
fi

if [ -d "$VENV" ] && [ ! -L "$VENV" ]; then
    rm -rf "$OLD_VENV_TARGET"
    mv "$VENV" "$OLD_VENV_TARGET"
fi
rm -f "$VENV"
ln -s "$NEW_VENV" "$VENV"
SWITCHED=1

if [ "$WORKER_STOPPED" -eq 1 ]; then
    systemctl start "$WORKER_SERVICE_NAME" >>"$LOG" 2>&1 || rollback "Worker restart failed"
fi
if ! systemctl start "$SERVICE_NAME" >>"$LOG" 2>&1; then
    rollback "Service restart failed"
fi
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    rollback "Service is not active after restart"
fi
SERVICE_STOPPED=0
WORKER_STOPPED=0
DB_MIGRATED=0

write_status done
log "=== Staged update completed (${FROM:0:12} -> ${TO:0:12}) ==="
