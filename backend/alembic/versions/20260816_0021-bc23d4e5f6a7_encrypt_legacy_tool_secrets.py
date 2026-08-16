"""encrypt legacy plaintext tool credentials

Revision ID: bc23d4e5f6a7
Revises: 9b01c2d3e4f5
Create Date: 2026-08-16 13:30:00.000000+00:00

Older rows could contain plaintext values for the two tool fields that are now
stored as Fernet ciphertext. Encrypt those values once at migration time so the
runtime no longer needs a plaintext compatibility fallback.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from cryptography.fernet import InvalidToken

from alembic import op
from backend.core.config import get_settings

revision: str = "bc23d4e5f6a7"
down_revision: str | None = "9b01c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SECRET_FIELDS = {
    "core_stock_data": ("alpha_vantage_api_key",),
    "reddit_sentiment": ("reddit_client_secret",),
}


def _looks_like_fernet_token(value: str) -> bool:
    # Fernet tokens are URL-safe base64 encodings of a version byte (0x80),
    # which currently renders with the stable ``gAAAA`` prefix. If such a
    # token cannot be decrypted, the configured key is wrong; never re-encrypt
    # the ciphertext string as if it were an old plaintext credential.
    return value.startswith("gAAAA")


def upgrade() -> None:
    bind = op.get_bind()
    fernet = get_settings().get_fernet()
    table = sa.table(
        "agent_tool_settings",
        sa.column("id", sa.Integer()),
        sa.column("tool_key", sa.String()),
        sa.column("settings_json", sa.JSON()),
    )

    rows = bind.execute(
        sa.select(table.c.id, table.c.tool_key, table.c.settings_json).where(
            table.c.tool_key.in_(tuple(_SECRET_FIELDS))
        )
    ).mappings()

    for row in rows:
        settings = dict(row["settings_json"] or {})
        changed = False
        for key in _SECRET_FIELDS[row["tool_key"]]:
            value = settings.get(key)
            if not isinstance(value, str) or not value:
                continue
            try:
                fernet.decrypt(value.encode())
                continue
            except InvalidToken:
                if _looks_like_fernet_token(value):
                    raise RuntimeError(
                        "Stored tool credential looks encrypted but cannot be decrypted. "
                        "Restore the ENCRYPTION_KEY used to write existing credentials before migrating."
                    ) from None
                settings[key] = fernet.encrypt(value.encode()).decode()
                changed = True

        if changed:
            bind.execute(table.update().where(table.c.id == row["id"]).values(settings_json=settings))


def downgrade() -> None:
    # Keep credentials encrypted. Older application versions already know how
    # to decrypt Fernet values, and writing plaintext again would be a security
    # regression rather than a meaningful schema downgrade.
    pass
