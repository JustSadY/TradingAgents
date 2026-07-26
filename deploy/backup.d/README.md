# backup.d — Site-Specific Backup Configuration

This directory is sourced by `deploy/backup.sh` before running a backup.
Place site-specific scripts or configuration files here to supplement or
override the default backup behaviour.

## Usage

### 1. Pre-backup hooks

Files matching `*.pre` are sourced before the backup runs. Useful for:

- Taking application snapshots (e.g. freeze writes, flush caches)
- Notifying external monitoring that a backup is starting
- Dumping additional data sources (files, configs) alongside PostgreSQL

### 2. Post-backup hooks

Files matching `*.post` are sourced after a successful backup. Useful for:

- Shipping backups off-site (rsync, s3, b2, etc.)
- Pinging healthchecks.io or similar heartbeat services
- Cleaning up temporary snapshots

### 3. Environment overrides

Create `backup.env` to set per-site defaults:

```bash
BACKUP_DIR=/mnt/backups/tradingagents
RETENTION_DAYS=60
S3_BUCKET=s3://my-bucket/backups
```

## Example

```bash
# deploy/backup.d/sync-s3.post
aws s3 cp "$BACKUP_DIR/$(basename $(readlink $BACKUP_DIR/latest.sql.gz))" \
    "s3://my-bucket/tradingagents/$(date -u +%Y/%m/%d)-backup.sql.gz"
```

All files in this directory are gitignored by default so each deployment
can customise without merge conflicts.