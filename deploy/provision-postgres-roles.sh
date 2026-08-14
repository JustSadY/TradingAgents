#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "provision-postgres-roles.sh requires root" >&2; exit 1; }
: "${DB_USER:?missing DB_USER}"
: "${DB_PASS:?missing DB_PASS}"
: "${DB_NAME:?missing DB_NAME}"
MIGRATION_ENV_FILE="${MIGRATION_ENV_FILE:-/etc/tradingagents/migration.env}"
MIGRATOR_USER="${DB_MIGRATOR_USER:-${DB_USER}_migrator}"
[ "$MIGRATOR_USER" != "$DB_USER" ] || { echo "migration and runtime roles must differ" >&2; exit 1; }

if [ -f "$MIGRATION_ENV_FILE" ]; then
    read EXISTING_USER MIGRATOR_PASS EXISTING_DB < <(python3 - "$MIGRATION_ENV_FILE" <<'PY'
import sys, urllib.parse as u
from pathlib import Path
line = next((x for x in Path(sys.argv[1]).read_text().splitlines() if x.startswith("MIGRATION_DATABASE_URL=")), "")
raw = line.split("=", 1)[1].strip().strip("'\"") if line else ""
p = u.urlsplit(raw)
print(p.username or "", u.unquote(p.password or ""), (p.path or "/").lstrip("/"))
PY
)
    [ "$EXISTING_USER" = "$MIGRATOR_USER" ] || { echo "existing migration env uses unexpected role" >&2; exit 1; }
    [ "$EXISTING_DB" = "$DB_NAME" ] || { echo "existing migration env targets unexpected database" >&2; exit 1; }
else
    MIGRATOR_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi

psql_admin() { runuser -u postgres -- psql -d template1 -v ON_ERROR_STOP=1 "$@"; }
psql_admin -v runtime="$DB_USER" -v runtime_pw="$DB_PASS" -v migrator="$MIGRATOR_USER" -v migrator_pw="$MIGRATOR_PASS" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'migrator')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator');
\gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', :'migrator', :'migrator_pw');
\gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', :'runtime', :'runtime_pw');
\gexec
SQL

psql_admin -v db="$DB_NAME" -v migrator="$MIGRATOR_USER" <<'SQL'
SELECT format('ALTER DATABASE %I OWNER TO %I', :'db', :'migrator');
\gexec
SQL

runuser -u postgres -- psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -v runtime="$DB_USER" -v migrator="$MIGRATOR_USER" -v db="$DB_NAME" <<'SQL'
SELECT format('REASSIGN OWNED BY %I TO %I', :'runtime', :'migrator');
\gexec
SELECT format('ALTER SCHEMA public OWNER TO %I', :'migrator');
\gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', :'runtime');
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'runtime');
\gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'runtime');
\gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'runtime');
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'migrator', :'runtime');
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'migrator', :'runtime');
\gexec
SQL

install -d -m 700 "$(dirname "$MIGRATION_ENV_FILE")"
MIGRATOR_USER="$MIGRATOR_USER" MIGRATOR_PASS="$MIGRATOR_PASS" DB_NAME="$DB_NAME" python3 - "$MIGRATION_ENV_FILE" <<'PY'
import os, urllib.parse as u, sys
from pathlib import Path
user = u.quote(os.environ["MIGRATOR_USER"], safe="")
pw = u.quote(os.environ["MIGRATOR_PASS"], safe="")
db = u.quote(os.environ["DB_NAME"], safe="")
url = f"postgresql+asyncpg://{user}:{pw}@localhost:5432/{db}"
Path(sys.argv[1]).write_text(f"MIGRATION_DATABASE_URL='{url}'\n", encoding="utf-8")
PY
chmod 600 "$MIGRATION_ENV_FILE"
