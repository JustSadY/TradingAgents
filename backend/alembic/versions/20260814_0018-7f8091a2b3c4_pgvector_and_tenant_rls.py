"""move pgvector schema to Alembic and add tenant RLS guardrails

Revision ID: 7f8091a2b3c4
Revises: 6e7f8091a2b3
Create Date: 2026-08-14 16:10:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f8091a2b3c4"
down_revision: str | None = "6e7f8091a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_vectors (
            namespace TEXT NOT NULL,
            id TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            embedding vector NOT NULL,
            PRIMARY KEY (namespace, id)
        )
        """
    )
    op.execute(
        r"""
        DO $$
        DECLARE
            r record;
            policy_name text;
        BEGIN
            FOR r IN
                SELECT c.table_schema, c.table_name
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema
                 AND t.table_name = c.table_name
                WHERE c.table_schema = current_schema()
                  AND c.column_name = 'user_id'
                  AND t.table_type = 'BASE TABLE'
                  AND c.table_name <> 'alembic_version'
            LOOP
                policy_name := 'tenant_isolation_' || r.table_name;
                EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', r.table_schema, r.table_name);
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = r.table_schema
                      AND tablename = r.table_name
                      AND policyname = policy_name
                ) THEN
                    EXECUTE format(
                        $policy$
                        CREATE POLICY %I ON %I.%I
                        USING (
                            current_setting('app.is_admin', true) = 'true'
                            OR user_id = NULLIF(current_setting('app.user_id', true), '')::bigint
                        )
                        WITH CHECK (
                            current_setting('app.is_admin', true) = 'true'
                            OR user_id = NULLIF(current_setting('app.user_id', true), '')::bigint
                        )
                        $policy$,
                        policy_name, r.table_schema, r.table_name
                    );
                END IF;
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        DO $$
        DECLARE
            r record;
            policy_name text;
        BEGIN
            FOR r IN
                SELECT c.table_schema, c.table_name
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema
                 AND t.table_name = c.table_name
                WHERE c.table_schema = current_schema()
                  AND c.column_name = 'user_id'
                  AND t.table_type = 'BASE TABLE'
            LOOP
                policy_name := 'tenant_isolation_' || r.table_name;
                EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', policy_name, r.table_schema, r.table_name);
                EXECUTE format('ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY', r.table_schema, r.table_name);
            END LOOP;
        END $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS memory_vectors")
