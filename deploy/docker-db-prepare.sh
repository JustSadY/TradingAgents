#!/bin/sh
set -eu
: "${PGHOST:?}"
: "${PGDATABASE:?}"
: "${PGUSER:?}"
: "${PGPASSWORD:?}"
: "${DB_RUNTIME_USER:?}"
: "${DB_RUNTIME_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 -d postgres -v runtime="$DB_RUNTIME_USER" -v runtime_pw="$DB_RUNTIME_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'runtime')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'runtime');
\gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS', :'runtime', :'runtime_pw');
\gexec
SQL

psql -v ON_ERROR_STOP=1 -d "$PGDATABASE" -v runtime="$DB_RUNTIME_USER" -v owner="$PGUSER" -v db="$PGDATABASE" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', :'runtime');
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'runtime');
\gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'runtime');
\gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'runtime');
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'owner', :'runtime');
\gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'owner', :'runtime');
\gexec
SQL
