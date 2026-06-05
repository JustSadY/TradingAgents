from __future__ import annotations
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.agent_settings import AgentSetting
from backend.models.user import User
from backend.trading_agents.agent_catalog import list_agents, get_agent, AgentInfo
from backend.schemas.agent_settings import AgentSettingsRead, AgentSettingValue, AgentSettingsUpdate


def validate_agent_settings(agent: AgentInfo, incoming: dict[str, Any]) -> dict[str, Any]:
    schema_by_key = {field.key: field for field in agent.settings_schema}
    normalized = {}

    for key, value in incoming.items():
        if key not in schema_by_key:
            raise ValueError(f"Unknown setting '{key}' for agent '{agent.key}'.")
        field = schema_by_key[key]
        normalized[key] = value

    for field in agent.settings_schema:
        if field.required and field.key not in normalized and field.default is None:
            raise ValueError(f"Missing required setting '{field.key}' for agent '{agent.key}'.")
        if field.key not in normalized:
            normalized[field.key] = field.default

    return normalized


async def get_agent_settings_by_scope(db: AsyncSession, scope: str, user_id: int | None = None) -> AgentSettingsRead:
    stmt = select(AgentSetting).where(AgentSetting.scope == scope)
    if scope == "user":
        stmt = stmt.where(AgentSetting.user_id == user_id)
    else:
        stmt = stmt.where(AgentSetting.user_id.is_(None))
    
    result = await db.execute(stmt)
    rows = {row.agent_key: row for row in result.scalars().all()}

    agents_map = {}
    for agent in list_agents():
        default_enabled = agent.default_enabled
        default_settings = {field.key: field.default for field in agent.settings_schema}

        row = rows.get(agent.key)
        enabled = row.enabled if (row and row.enabled is not None) else default_enabled
        settings = default_settings.copy()
        if row and row.settings:
            settings.update(row.settings)

        agents_map[agent.key] = AgentSettingValue(enabled=enabled, settings=settings)

    return AgentSettingsRead(agents=agents_map)


async def get_user_agent_settings(db: AsyncSession, user: User) -> AgentSettingsRead:
    return await get_agent_settings_by_scope(db, "user", user.id)


async def get_server_agent_settings(db: AsyncSession) -> AgentSettingsRead:
    return await get_agent_settings_by_scope(db, "server")


async def apply_agent_settings_update_by_scope(
    db: AsyncSession, scope: str, body: AgentSettingsUpdate, user_id: int | None = None
) -> AgentSettingsRead:
    stmt = select(AgentSetting).where(AgentSetting.scope == scope)
    if scope == "user":
        stmt = stmt.where(AgentSetting.user_id == user_id)
    else:
        stmt = stmt.where(AgentSetting.user_id.is_(None))

    result = await db.execute(stmt)
    rows = {row.agent_key: row for row in result.scalars().all()}

    for agent_key, update in body.agents.items():
        agent = get_agent(agent_key)
        if not agent:
            raise ValueError(f"Unknown agent key '{agent_key}'.")

        row = rows.get(agent_key)
        if not row:
            row = AgentSetting(
                scope=scope,
                user_id=user_id if scope == "user" else None,
                agent_key=agent_key,
                enabled=agent.default_enabled,
                settings={}
            )
            db.add(row)

        if update.reset_enabled:
            row.enabled = agent.default_enabled
        elif update.enabled is not None:
            row.enabled = update.enabled

        current_settings = row.settings.copy()
        if update.reset_settings:
            default_settings = {field.key: field.default for field in agent.settings_schema}
            for k in update.reset_settings:
                if k in current_settings:
                    current_settings[k] = default_settings.get(k)
        elif update.settings is not None:
            validated = validate_agent_settings(agent, update.settings)
            current_settings.update(validated)

        row.settings = current_settings

    await db.flush()
    return await get_agent_settings_by_scope(db, scope, user_id)


async def apply_agent_settings_update(db: AsyncSession, user: User, body: AgentSettingsUpdate) -> AgentSettingsRead:
    return await apply_agent_settings_update_by_scope(db, "user", body, user.id)


async def apply_server_agent_settings_update(db: AsyncSession, body: AgentSettingsUpdate) -> AgentSettingsRead:
    return await apply_agent_settings_update_by_scope(db, "server", body)


def build_agent_runtime_state(agent: AgentInfo, server_row: AgentSetting | None, user_row: AgentSetting | None) -> dict[str, Any]:
    server_settings = {field.key: field.default for field in agent.settings_schema}
    user_settings = {field.key: field.default for field in agent.settings_schema}

    server_enabled = agent.default_enabled
    user_enabled = agent.default_enabled

    if server_row:
        if server_row.enabled is not None:
            server_enabled = server_row.enabled
        server_settings.update(server_row.settings)

    if user_row:
        if user_row.enabled is not None:
            user_enabled = user_row.enabled
        user_settings.update(user_row.settings)

    return {
        "enabled": user_enabled if user_row else server_enabled,
        "settings": user_settings if user_row else server_settings,
    }


async def build_agent_runtime_context(db: AsyncSession, user_id: int | None) -> dict[str, Any]:
    result = await db.execute(
        select(AgentSetting)
        .where(AgentSetting.scope == "server")
        .where(AgentSetting.user_id.is_(None))
    )
    server_rows = {row.agent_key: row for row in result.scalars().all()}

    user_rows = {}
    if user_id is not None:
        result = await db.execute(
            select(AgentSetting)
            .where(AgentSetting.scope == "user")
            .where(AgentSetting.user_id == user_id)
        )
        user_rows = {row.agent_key: row for row in result.scalars().all()}

    context = {}
    for agent in list_agents():
        context[agent.key] = build_agent_runtime_state(agent, server_rows.get(agent.key), user_rows.get(agent.key))

    return context
