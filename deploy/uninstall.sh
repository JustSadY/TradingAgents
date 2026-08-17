#!/usr/bin/env bash
#
# TradingAgents — service uninstaller.
#
#   sudo bash deploy/uninstall.sh            # stops + removes service (data preserved)
#   sudo bash deploy/uninstall.sh --purge    # additionally deletes DB, role, venvs and .env
#
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-tradingagents}"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
UPDATE_UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}-update.service"
SUDOERS_FILE="/etc/sudoers.d/${SERVICE_NAME}-update"
UPDATER_BIN="/usr/local/sbin/tradingagents-update"
UPDATE_CONF="/etc/tradingagents/update.env"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
VENV="$PROJECT_ROOT/.venv"
VENV_ROOT="$PROJECT_ROOT/.tradingagents-venvs"
PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

info() { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Root required: sudo bash deploy/uninstall.sh"; exit 1; }

info "Stopping service..."
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$SERVICE_NAME" 2>/dev/null || true
rm -f "$UNIT_FILE"
# Automatic update components
rm -f "$UPDATE_UNIT_FILE" "$SUDOERS_FILE" "$UPDATER_BIN" "$UPDATE_CONF"
rmdir /etc/tradingagents 2>/dev/null || true
rm -f "$PROJECT_ROOT/.update.json" "$PROJECT_ROOT/.update.log"
systemctl daemon-reload
ok "Service and update components removed: $SERVICE_NAME"

if [ "$PURGE" = 1 ]; then
    warn "--purge: deleting database, versioned venvs, and .env..."
    # Read DB credentials from .env if available
    if [ -f "$ENV_FILE" ] && [ -x "$VENV/bin/python" ]; then
        read DB_USER DB_NAME < <(
            "$VENV/bin/python" - "$ENV_FILE" <<'PY'
import sys, urllib.parse as u
from dotenv import dotenv_values
p = u.urlsplit(dotenv_values(sys.argv[1]).get("DATABASE_URL",""))
print(p.username or "", (p.path or "/").lstrip("/"))
PY
        ) || true
        if command -v psql >/dev/null && [ -n "${DB_NAME:-}" ]; then
            runuser -u postgres -- dropdb --maintenance-db=template1 --if-exists "$DB_NAME" 2>/dev/null || true
            runuser -u postgres -- psql -d template1 -c "DROP ROLE IF EXISTS \"$DB_USER\";" 2>/dev/null || true
            ok "PostgreSQL database/role removed."
        fi
    fi
    rm -f "$VENV"
    rm -rf "$VENV_ROOT"
    rm -f "$ENV_FILE"
    ok "Versioned venvs and .env removed."
else
    info "Data preserved (DB, .env, versioned venvs). To completely remove: --purge"
fi
