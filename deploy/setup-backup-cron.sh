#!/usr/bin/env bash
#
# TradingAgents — backup cron setup
#
# Installs a systemd timer to run backups daily and prune old ones weekly.
#
# Usage:
#   sudo bash deploy/setup-backup-cron.sh
#
# Environment variables (optional):
#   BACKUP_DIR       — where backups go (default: /var/backups/tradingagents)
#   BACKUP_TIME      — daily backup time in HH:MM format (default: 03:00)
#   RETENTION_DAYS   — how long to keep backups (default: 30)
#
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-tradingagents}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/tradingagents}"
BACKUP_TIME="${BACKUP_TIME:-03:00}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_SCRIPT="$PROJECT_ROOT/deploy/backup.sh"

BACKUP_TIMER="/etc/systemd/system/${SERVICE_NAME}-backup.timer"
BACKUP_SERVICE="/etc/systemd/system/${SERVICE_NAME}-backup.service"
PRUNE_TIMER="/etc/systemd/system/${SERVICE_NAME}-prune.timer"
PRUNE_SERVICE="/etc/systemd/system/${SERVICE_NAME}-prune.service"

info() { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Root required: sudo bash deploy/setup-backup-cron.sh"
[ -x "$BACKUP_SCRIPT" ] || die "Backup script not found: $BACKUP_SCRIPT"
command -v systemctl >/dev/null || die "systemd required"

HOUR="${BACKUP_TIME%%:*}"
MINUTE="${BACKUP_TIME##*:}"
[ "$HOUR" -ge 0 2>/dev/null ] && [ "$HOUR" -le 23 2>/dev/null ] || die "Invalid BACKUP_TIME: $BACKUP_TIME"
[ "$MINUTE" -ge 0 2>/dev/null ] && [ "$MINUTE" -le 59 2>/dev/null ] || die "Invalid BACKUP_TIME: $BACKUP_TIME"

# ── Backup service (oneshot) ──────────────────────────────────────
info "Creating backup service: $BACKUP_SERVICE"
cat > "$BACKUP_SERVICE" <<EOF
[Unit]
Description=TradingAgents daily database backup
Wants=postgresql.service

[Service]
Type=oneshot
ExecStart=$BACKUP_SCRIPT
Environment=BACKUP_DIR=$BACKUP_DIR
Environment=RETENTION_DAYS=$RETENTION_DAYS
EOF

# ── Backup timer ──────────────────────────────────────────────────
info "Creating backup timer: $BACKUP_TIMER"
cat > "$BACKUP_TIMER" <<EOF
[Unit]
Description=Daily TradingAgents database backup at $BACKUP_TIME

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

# ── Prune service (oneshot) ───────────────────────────────────────
info "Creating prune service: $PRUNE_SERVICE"
cat > "$PRUNE_SERVICE" <<EOF
[Unit]
Description=TradingAgents old backup prune
Wants=postgresql.service

[Service]
Type=oneshot
ExecStart=$BACKUP_SCRIPT --prune
Environment=BACKUP_DIR=$BACKUP_DIR
Environment=RETENTION_DAYS=$RETENTION_DAYS
EOF

# ── Prune timer ───────────────────────────────────────────────────
info "Creating prune timer: $PRUNE_TIMER"
cat > "$PRUNE_TIMER" <<EOF
[Unit]
Description=Weekly TradingAgents backup prune

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload

systemctl enable --now "${SERVICE_NAME}-backup.timer" >/dev/null 2>&1
systemctl enable --now "${SERVICE_NAME}-prune.timer" >/dev/null 2>&1

ok "Backup timers installed and started:"
ok "  ${SERVICE_NAME}-backup.timer  — daily at $BACKUP_TIME"
ok "  ${SERVICE_NAME}-prune.timer   — weekly (retention: ${RETENTION_DAYS}d)"
ok ""
ok "Manual run: systemctl start ${SERVICE_NAME}-backup.service"
ok "Backup dir: $BACKUP_DIR"
