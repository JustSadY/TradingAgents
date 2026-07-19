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

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tradingagents}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

now() { date -u +%Y%m%dT%H%M%SZ; }
info() { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

require_root() {
    [ "$(id -u)" -eq 0 ] || die "Root required: sudo bash deploy/backup.sh"
}

parse_db_url() {
    local url="$1"
    python3 -c "
import sys, urllib.parse as u
p = u.urlsplit('$url')
print(p.username or '')
print(p.password or '')
print(p.hostname or '')
print(p.port or 5432)
print((p.path or '/').lstrip('/'))
" 2>/dev/null || return 1
}

read_db_config() {
    [ -f "$ENV_FILE" ] || die ".env not found at $ENV_FILE"
    # shellcheck disable=SC2016
    local raw
    raw=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed "s/^DATABASE_URL=//; s/^'//; s/'$//" 2>/dev/null || true)
    [ -n "$raw" ] || die "DATABASE_URL not found in .env"
    read -r DB_USER DB_PASS DB_HOST DB_PORT DB_NAME <<< "$(parse_db_url "$raw")" || die "Failed to parse DATABASE_URL"
    [ -n "$DB_NAME" ] || die "Could not extract database name from DATABASE_URL"
}

do_backup() {
    require_root
    read_db_config
    mkdir -p "$BACKUP_DIR"
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
    mv "$filename.tmp" "$filename"
    ln -sf "$filename" "$BACKUP_DIR/${DB_NAME}_latest.sql.gz"
    ok "Backup created: $filename"
}

do_restore() {
    require_root
    local restore_file="${1:-}"
    [ -n "$restore_file" ] || die "Usage: deploy/backup.sh --restore <file>"
    [ -f "$restore_file" ] || die "Restore file not found: $restore_file"
    read_db_config
    info "Restoring $DB_NAME from $restore_file"
    info "This will DROP the current database and recreate it from backup."
    info "Press Ctrl+C within 5 seconds to abort..."
    sleep 5
    PGPASSWORD="$DB_PASS" pg_restore \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --clean \
        --no-owner \
        --no-acl \
        --verbose \
        "$restore_file"
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
