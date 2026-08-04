#!/usr/bin/env bash
#
# TradingAgents — PostgreSQL backup/restore automation
#
# Usage:
#   sudo bash deploy/backup.sh                    # create a backup
#   sudo bash deploy/backup.sh --restore <file>   # restore from backup
#   sudo bash deploy/backup.sh --list             # list available backups
#   sudo bash deploy/backup.sh --prune            # remove backups older than 30 days
#
# Environment variables (optional):
#   BACKUP_DIR   — where backups are stored (default: /var/backups/tradingagents)
#   RETENTION_DAYS — how long to keep backups (default: 30)
#
set -euo pipefail
umask 077

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tradingagents}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
HOOK_DIR="$PROJECT_ROOT/deploy/backup.d"
SERVICE_NAME="${SERVICE_NAME:-tradingagents}"
WORKER_SERVICE_NAME="${WORKER_SERVICE_NAME:-tradingagents-worker}"

now() { date -u +%Y%m%dT%H%M%SZ; }
info() { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

load_backup_env() {
    if [ -f "$HOOK_DIR/backup.env" ]; then
        # Site-owned root configuration; export values to hooks and pg tools.
        set -a
        # shellcheck disable=SC1090
        . "$HOOK_DIR/backup.env"
        set +a
    fi
}

run_hooks() {
    local suffix="$1" hook
    [ -d "$HOOK_DIR" ] || return 0
    shopt -s nullglob
    for hook in "$HOOK_DIR"/*".$suffix"; do
        [ -f "$hook" ] || continue
        info "Running backup hook: $(basename "$hook")"
        # shellcheck disable=SC1090
        . "$hook"
    done
    shopt -u nullglob
}

service_exists() { systemctl list-unit-files "$1.service" --no-legend 2>/dev/null | grep -q "^$1.service"; }

require_root() {
    [ "$(id -u)" -eq 0 ] || die "Root required: sudo bash deploy/backup.sh"
}

parse_db_url() {
    local url="$1"
    # Pass the URL on stdin rather than interpolating it into Python source.
    # Besides preserving special characters in credentials, this avoids a
    # project-local .env value being interpreted as Python when this script is
    # invoked through sudo.
    printf '%s' "$url" | python3 -c '
import sys
import urllib.parse as u

p = u.urlsplit(sys.stdin.read().strip())
for value in (p.username or "", p.password or "", p.hostname or "", p.port or 5432, (p.path or "/").lstrip("/")):
    print(u.unquote(str(value)))
' 2>/dev/null || return 1
}

read_db_config() {
    [ -f "$ENV_FILE" ] || die ".env not found at $ENV_FILE"
    # shellcheck disable=SC2016
    local raw
    raw=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed "s/^DATABASE_URL=//; s/^'//; s/'$//" 2>/dev/null || true)
    [ -n "$raw" ] || die "DATABASE_URL not found in .env"
    # ``read`` consumes only one line; parse_db_url intentionally emits one
    # value per line so credentials containing spaces remain intact.
    local -a db_parts=()
    mapfile -t db_parts < <(parse_db_url "$raw") || die "Failed to parse DATABASE_URL"
    [ "${#db_parts[@]}" -eq 5 ] || die "Could not parse DATABASE_URL"
    DB_USER="${db_parts[0]}"
    DB_PASS="${db_parts[1]}"
    DB_HOST="${db_parts[2]}"
    DB_PORT="${db_parts[3]}"
    DB_NAME="${db_parts[4]}"
    [ -n "$DB_NAME" ] || die "Could not extract database name from DATABASE_URL"
}

do_backup() {
    require_root
    read_db_config
    load_backup_env
    mkdir -p "$BACKUP_DIR"
    chmod 0700 "$BACKUP_DIR"
    run_hooks pre
    local stamp
    stamp="$(now)"
    local filename="${BACKUP_DIR}/${DB_NAME}_${stamp}.sql.gz"
    info "Backing up $DB_NAME -> $filename"
    PGPASSWORD="$DB_PASS" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-owner \
        --no-acl \
        --compress=9 \
        --format=custom \
        --file="$filename.tmp"
    chmod 0600 "$filename.tmp"
    mv "$filename.tmp" "$filename"
    ln -sfn "$filename" "$BACKUP_DIR/${DB_NAME}_latest.sql.gz"
    run_hooks post
    ok "Backup created: $filename"
}

do_restore() {
    require_root
    local restore_file="${1:-}"
    [ -n "$restore_file" ] || die "Usage: deploy/backup.sh --restore <file>"
    [ -f "$restore_file" ] || die "Restore file not found: $restore_file"
    load_backup_env
    read_db_config
    [[ "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]] || die "Unsafe database name: $DB_NAME"
    info "Restoring $DB_NAME from $restore_file"
    info "Application and worker services will be stopped during restore."
    info "Press Ctrl+C within 5 seconds to abort..."
    sleep 5

    local restart_web=0 restart_worker=0
    if service_exists "$SERVICE_NAME" && systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
        restart_web=1
    fi
    if service_exists "$WORKER_SERVICE_NAME" && systemctl is-active --quiet "$WORKER_SERVICE_NAME"; then
        systemctl stop "$WORKER_SERVICE_NAME"
        restart_worker=1
    fi
    restore_services() {
        [ "$restart_worker" -eq 1 ] && systemctl start "$WORKER_SERVICE_NAME" || true
        [ "$restart_web" -eq 1 ] && systemctl start "$SERVICE_NAME" || true
    }
    trap restore_services RETURN

    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();"
    PGPASSWORD="$DB_PASS" pg_restore \
        -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --clean --if-exists --exit-on-error --no-owner --no-acl --verbose "$restore_file"
    restore_services
    trap - RETURN
    ok "Restore completed from: $restore_file"
}

do_list() {
    mkdir -p "$BACKUP_DIR"
    echo "Available backups in $BACKUP_DIR:"
    echo ""
    if [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
        echo "  (no backups found)"
        return
    fi
    ls -lhS "$BACKUP_DIR"/*.sql.gz 2>/dev/null | awk '{printf "  %s  %s  %s\n", $6, $5, $9}' || echo "  (no backups found)"
}

do_prune() {
    require_root
    mkdir -p "$BACKUP_DIR"
    info "Removing backups older than $RETENTION_DAYS days from $BACKUP_DIR"
    find "$BACKUP_DIR" -maxdepth 1 -name '*.sql.gz' -type f -mtime "+$RETENTION_DAYS" -print -delete
    ok "Pruning complete"
}

case "${1:-}" in
    --restore)  shift; do_restore "$@" ;;
    --list)     do_list ;;
    --prune)    do_prune ;;
    --help|-h)
        echo "Usage: $(basename "$0") [--restore <file> | --list | --prune]"
        exit 0
        ;;
    *)          do_backup ;;
esac
