#!/usr/bin/env bash
#
# In-place updater — NOT executed standalone. install.sh copies this to
# /usr/local/sbin/tradingagents-update (owned by root) and triggers it
# via a oneshot systemd unit. Backend only starts that unit via
# `sudo -n systemctl start --no-block`.
#
# Flow: git pull + dependencies + frontend build (as RUN_USER) ->
# restart main service (root). Because pulled code is built as RUN_USER,
# there is no privilege escalation; only systemctl restart runs as root.
#
set -euo pipefail

CONF="${TRADINGAGENTS_UPDATE_CONF:-/etc/tradingagents/update.env}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"

# Fallback values to allow running manually without update.env
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-tradingagents}"
RUN_USER="${RUN_USER:-${SUDO_USER:-root}}"
VENV="${VENV:-$PROJECT_ROOT/.venv}"

: "${PROJECT_ROOT:?update.env or default missing: PROJECT_ROOT}"
: "${SERVICE_NAME:?update.env or default missing: SERVICE_NAME}"
: "${RUN_USER:?update.env or default missing: RUN_USER}"
: "${VENV:?update.env or default missing: VENV}"

STATUS="$PROJECT_ROOT/.update.json"
LOG="$PROJECT_ROOT/.update.log"

# RUN_USER's HOME — write npm/pip/git caches here (to avoid permission errors in /root)
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
[ -n "$RUN_HOME" ] || RUN_HOME="/home/$RUN_USER"

now()  { date -u +%Y-%m-%dT%H:%M:%SZ; }
asuser() { runuser -u "$RUN_USER" -- env "HOME=$RUN_HOME" "$@"; }

write_status() { # state [error-message]
    local err="null"
    [ -n "${2:-}" ] && err="$(printf '%s' "$2" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '"error"')"
    printf '{"state":"%s","at":"%s","from":"%s","to":"%s","error":%s}\n' \
        "$1" "$(now)" "${FROM:-?}" "${TO:-?}" "$err" > "$STATUS" 2>/dev/null || true
    chown "$RUN_USER":"$RUN_USER" "$STATUS" 2>/dev/null || true
}
log() { echo "[$(now)] $*" >> "$LOG" 2>/dev/null || true; chown "$RUN_USER":"$RUN_USER" "$LOG" 2>/dev/null || true; }

FROM="$(asuser git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
TO="$FROM"
write_status running
log "=== Update started ($FROM) ==="

fail() { log "ERROR: $1"; TO="$(asuser git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"; write_status failed "$1"; exit 1; }
run()  { log "+ $*"; if ! asuser "$@" >>"$LOG" 2>&1; then fail "Command failed: $*"; fi; }

# 1. Pull code (fast-forward only — stops if local commits exist)
run git -C "$PROJECT_ROOT" fetch --all --quiet
asuser git -C "$PROJECT_ROOT" pull --ff-only >>"$LOG" 2>&1 || fail "git pull --ff-only failed (local changes/divergence may exist)"

# 2. Backend dependencies (if requirements changed)
run "$VENV/bin/pip" install -q -r "$PROJECT_ROOT/backend/requirements.txt"

# 2a. Migrations are part of a deploy, not an optional startup side effect.
# Run them before the new process is restarted so a failed schema change keeps
# the currently running service alive and the updater reports a failure.
run bash -c "cd '$PROJECT_ROOT' && '$VENV/bin/alembic' -c backend/alembic.ini upgrade head"

# 3. Frontend build (if changed)
if [ -d "$PROJECT_ROOT/frontend" ]; then
    run bash -c "cd '$PROJECT_ROOT/frontend' && { npm ci || npm install; } && npm run build"
fi

TO="$(asuser git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
log "Build complete: $FROM -> $TO. Restarting service."

# 4. Restart main service (root — because this updater is in a separate cgroup,
#    restart will not kill this process)
if ! systemctl restart "$SERVICE_NAME"; then
    fail "systemctl restart failed: $SERVICE_NAME"
fi
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    fail "Service not active after restart: $SERVICE_NAME"
fi
write_status done
log "=== Update completed ($TO) ==="
