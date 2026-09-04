"""migrate long-term memory settings to Mem0

Revision ID: 4c5de6f7081a
Revises: 3b4cd5e6f809
Create Date: 2026-09-04 07:30:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c5de6f7081a"
down_revision: str | None = "3b4cd5e6f809"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Mem0 is now the single runtime long-term-memory backend and stores vectors
    # in the application's PostgreSQL/pgvector database. Preserve supported
    # OpenAI/Ollama embedder choices while normalizing retired Pinecone values.
    op.execute(
        sa.text(
            """
            UPDATE app_settings
               SET memory_store = 'pgvector'
             WHERE memory_store = 'pinecone'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE app_settings
               SET memory_embedder = 'openai'
             WHERE memory_embedder = 'pinecone'
            """
        )
    )


def downgrade() -> None:
    # This is intentionally a one-way data normalization. Rewriting pgvector or
    # OpenAI values back to Pinecone would also overwrite settings that users
    # selected independently of this migration.
    pass
