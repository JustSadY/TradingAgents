"""replace legacy long-term memory storage with Mem0

Revision ID: 4c5de6f7081a
Revises: 3b4cd5e6f809
Create Date: 2026-09-04 07:30:00.000000+00:00

This revision is the destructive cut-over from the retired custom memory stack
to Mem0.  It removes the old vector table, Pinecone-only settings columns,
legacy preset keys, and stored tenant Pinecone credentials.  Mem0's own
pgvector collection is created lazily by Mem0 and is intentionally not managed
by this migration.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from cryptography.fernet import InvalidToken
from alembic import op

revision: str = "4c5de6f7081a"
down_revision: str | None = "3b4cd5e6f809"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_MEMORY_COLUMNS = (
    "memory_store",
    "pinecone_index",
    "pinecone_cloud",
    "pinecone_region",
    "pinecone_embed_model",
)
_LEGACY_PRESET_KEYS = frozenset(_LEGACY_MEMORY_COLUMNS)


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _clean_saved_presets(bind) -> None:
    if "config_presets" not in _table_names(bind):
        return

    presets = sa.table(
        "config_presets",
        sa.column("id", sa.Integer()),
        sa.column("settings_json", sa.Text()),
    )
    rows = list(bind.execute(sa.select(presets.c.id, presets.c.settings_json)).mappings())
    for row in rows:
        raw = row["settings_json"] or "{}"
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        changed = False
        for key in _LEGACY_PRESET_KEYS:
            if key in payload:
                payload.pop(key, None)
                changed = True

        embedder = str(payload.get("memory_embedder") or "openai").strip().lower()
        normalized_embedder = embedder if embedder in {"openai", "ollama"} else "openai"
        if payload.get("memory_embedder") != normalized_embedder:
            payload["memory_embedder"] = normalized_embedder
            changed = True

        if changed:
            bind.execute(
                presets.update()
                .where(presets.c.id == row["id"])
                .values(settings_json=json.dumps(payload, separators=(",", ":")))
            )


def _remove_stored_pinecone_keys(bind) -> None:
    if "users" not in _table_names(bind) or "api_keys_enc" not in _column_names(bind, "users"):
        return

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("api_keys_enc", sa.Text()),
    )
    rows = list(
        bind.execute(
            sa.select(users.c.id, users.c.api_keys_enc).where(users.c.api_keys_enc.is_not(None))
        ).mappings()
    )
    if not rows:
        return

    # The credential blob is Fernet-encrypted, so SQL cannot safely remove one
    # provider entry.  Follow the same migration-time encryption policy used by
    # revision bc23d4e5f6a7 and require the installation's durable key.
    from backend.core.config import get_settings

    app_config = get_settings()
    if not app_config.ENCRYPTION_KEY:
        raise RuntimeError(
            "Stored API credentials require the installation ENCRYPTION_KEY before the retired Pinecone key can be removed."
        )
    fernet = app_config.get_fernet()

    for row in rows:
        encrypted = row["api_keys_enc"]
        if not encrypted:
            continue
        try:
            payload = json.loads(fernet.decrypt(encrypted.encode()).decode())
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Stored API credentials cannot be decrypted. Restore the ENCRYPTION_KEY used by this installation before migrating."
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Stored API credential payload is not a provider mapping")

        filtered = {key: value for key, value in payload.items() if str(key).lower() != "pinecone"}
        if len(filtered) == len(payload):
            continue
        replacement = fernet.encrypt(json.dumps(filtered).encode()).decode() if filtered else None
        bind.execute(users.update().where(users.c.id == row["id"]).values(api_keys_enc=replacement))


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "app_settings" in tables:
        columns = _column_names(bind, "app_settings")
        if "memory_embedder" in columns:
            op.execute(
                sa.text(
                    """
                    UPDATE app_settings
                       SET memory_embedder = 'openai'
                     WHERE memory_embedder IS NULL
                        OR LOWER(memory_embedder) NOT IN ('openai', 'ollama')
                    """
                )
            )

    _clean_saved_presets(bind)
    _remove_stored_pinecone_keys(bind)

    # Delete the retired custom pgvector table. Mem0 uses its own collection and
    # does not read or migrate these embeddings.
    if "memory_vectors" in tables:
        if bind.dialect.name == "postgresql":
            op.execute("DROP TABLE memory_vectors CASCADE")
        else:
            op.drop_table("memory_vectors")

    if "app_settings" in tables:
        columns = _column_names(bind, "app_settings")
        with op.batch_alter_table("app_settings") as batch_op:
            for column_name in _LEGACY_MEMORY_COLUMNS:
                if column_name in columns:
                    batch_op.drop_column(column_name)


def downgrade() -> None:
    # Recreate only the legacy schema shape so an older application revision can
    # boot after a downgrade. Deleted vectors and Pinecone credentials are not
    # recoverable and are intentionally not reconstructed.
    bind = op.get_bind()
    if "app_settings" in _table_names(bind):
        columns = _column_names(bind, "app_settings")
        with op.batch_alter_table("app_settings") as batch_op:
            if "memory_store" not in columns:
                batch_op.add_column(sa.Column("memory_store", sa.String(length=20), nullable=False, server_default="pgvector"))
            if "pinecone_index" not in columns:
                batch_op.add_column(
                    sa.Column("pinecone_index", sa.String(length=100), nullable=False, server_default="tradingagents-memory")
                )
            if "pinecone_cloud" not in columns:
                batch_op.add_column(sa.Column("pinecone_cloud", sa.String(length=20), nullable=False, server_default="aws"))
            if "pinecone_region" not in columns:
                batch_op.add_column(sa.Column("pinecone_region", sa.String(length=30), nullable=False, server_default="us-east-1"))
            if "pinecone_embed_model" not in columns:
                batch_op.add_column(
                    sa.Column("pinecone_embed_model", sa.String(length=60), nullable=False, server_default="llama-text-embed-v2")
                )

    if bind.dialect.name == "postgresql" and "memory_vectors" not in _table_names(bind):
        op.execute(
            """
            CREATE TABLE memory_vectors (
                namespace TEXT NOT NULL,
                id TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                embedding vector NOT NULL,
                PRIMARY KEY (namespace, id)
            )
            """
        )
