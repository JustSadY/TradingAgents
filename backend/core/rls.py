"""PostgreSQL row-level-security deployment checks.

Alembic owns policy creation. This module validates that the application runtime
role cannot silently bypass those policies by being a superuser, carrying
BYPASSRLS, or owning an RLS-enabled table.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

_logger = logging.getLogger(__name__)


def _strict_enabled() -> bool:
    return os.getenv("RLS_STRICT_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def rls_role_is_safe(*, is_superuser: bool, bypass_rls: bool, owned_rls_tables: int) -> bool:
    return not is_superuser and not bypass_rls and int(owned_rls_tables) == 0


async def verify_runtime_rls_role(engine) -> bool:
    """Validate that PostgreSQL RLS is effective for the connected runtime role.

    PostgreSQL table owners, superusers and BYPASSRLS roles can bypass ordinary
    row-security policies. In strict mode this becomes a startup error; without
    strict mode it is logged so existing single-role deployments remain usable
    while they migrate to a dedicated non-owner runtime role.
    """
    if engine.dialect.name != "postgresql":
        return True

    async with engine.connect() as conn:
        role = (
            await conn.execute(
                text(
                    "SELECT current_user AS role_name, r.rolsuper, r.rolbypassrls "
                    "FROM pg_roles r WHERE r.rolname = current_user"
                )
            )
        ).mappings().one()

        owned_rls_tables = int(
            (
                await conn.execute(
                    text(
                        "SELECT count(*) "
                        "FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = current_schema() "
                        "AND c.relkind IN ('r', 'p') "
                        "AND c.relrowsecurity "
                        "AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
                    )
                )
            ).scalar_one()
        )

    safe = rls_role_is_safe(
        is_superuser=bool(role["rolsuper"]),
        bypass_rls=bool(role["rolbypassrls"]),
        owned_rls_tables=owned_rls_tables,
    )
    if safe:
        _logger.info("PostgreSQL RLS runtime role validated: %s", role["role_name"])
        return True

    reasons: list[str] = []
    if role["rolsuper"]:
        reasons.append("role is superuser")
    if role["rolbypassrls"]:
        reasons.append("role has BYPASSRLS")
    if owned_rls_tables:
        reasons.append(f"role owns {owned_rls_tables} RLS-enabled table(s)")
    message = (
        f"PostgreSQL RLS is bypassable for runtime role {role['role_name']!r}: "
        + ", ".join(reasons)
        + ". Use a dedicated non-owner, NOBYPASSRLS application role."
    )

    if _strict_enabled():
        raise RuntimeError(message)
    _logger.warning("%s Set RLS_STRICT_MODE=true after separating migration and runtime roles.", message)
    return False
