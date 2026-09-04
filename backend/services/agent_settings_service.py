from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_settings import AgentSetting
from backend.models.user import User
from backend.schemas.agent_settings import AgentSettingsRead, AgentSettingsUpdate, AgentSettingValue
from backend.trading_agents.agent_catalog import AgentInfo, get_agent, list_agents


def validate_agent_settings(agent: AgentInfo, incoming: dict[str, Any]) -> dict[str, Any]:
    schema_by_key = {field.key: field for field in agent.settings_schema}
    normalized = {}

    for key, value in incoming.items():
        if key not in schema_by_key:
            raise ValueError(f"Unknown setting '{key}' for agent '{agent.key}'.")
        normalized[key] = value

    for field in agent.settings_schema:
        if field.required and field.key not in normalized and field.default is None:
            raise ValueError(f"Missing required setting '{field.key}' for agent '{agent.key}'.")
        if field.key not in normalized:
            normalized[field.key] = field.default

    return normalized


def _agent_settings_read_from_rows(rows: dict[str, AgentSetting]) -> AgentSettingsRead:
    """Render the API settings view from an already-loaded row snapshot."""
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


async def get_agent_settings_by_scope(db: AsyncSession, scope: str, user_id: int | None = None) -> AgentSettingsRead:
    from backend.repositories.agent_settings import get_agent_settings_by_scope as _repo_get

    rows_list = await _repo_get(db, scope, user_id)
    rows = {row.agent_key: row for row in rows_list}
    return _agent_settings_read_from_rows(rows)


async def get_user_agent_settings(db: AsyncSession, user: User) -> AgentSettingsRead:
    return await get_agent_settings_by_scope(db, "user", user.id)


async def get_server_agent_settings(db: AsyncSession) -> AgentSettingsRead:
    return await get_agent_settings_by_scope(db, "server")


async def apply_agent_settings_update_by_scope(
    db: AsyncSession, scope: str, body: AgentSettingsUpdate, user_id: int | None = None
) -> AgentSettingsRead:
    from backend.repositories.agent_settings import get_agent_settings_by_scope as _repo_get
    from backend.repositories.agent_settings import persist_agent_setting

    rows_list = await _repo_get(db, scope, user_id)
    rows = {row.agent_key: row for row in rows_list}

    for agent_key, update in body.agents.items():
        agent = get_agent(agent_key)
        if not agent:
            raise ValueError(f"Unknown agent key '{agent_key}'.")

        if agent.parent_key is None and update.enabled is False:
            update = update.model_copy(update={"enabled": None})

        row = rows.get(agent_key)
        enabled = row.enabled if row is not None else agent.default_enabled
        if update.reset_enabled:
            enabled = agent.default_enabled
        elif update.enabled is not None:
            enabled = update.enabled

        current_settings = row.settings.copy() if row is not None else {}
        if update.reset_settings:
            default_settings = {field.key: field.default for field in agent.settings_schema}
            for key in update.reset_settings:
                if key in current_settings:
                    current_settings[key] = default_settings.get(key)
        elif update.settings is not None:
            validated = validate_agent_settings(agent, update.settings)
            current_settings.update(validated)

        rows[agent_key] = persist_agent_setting(
            db,
            row=row,
            scope=scope,
            user_id=user_id,
            agent_key=agent_key,
            enabled=enabled,
            settings=current_settings,
        )

    await db.flush()
    # ``rows`` already contains the persisted/mutated ORM objects. Re-querying
    # the same scope just to construct the response adds a redundant round trip.
    return _agent_settings_read_from_rows(rows)


async def apply_agent_settings_update(db: AsyncSession, user: User, body: AgentSettingsUpdate) -> AgentSettingsRead:
    return await apply_agent_settings_update_by_scope(db, "user", body, user.id)


async def apply_server_agent_settings_update(db: AsyncSession, body: AgentSettingsUpdate) -> AgentSettingsRead:
    return await apply_agent_settings_update_by_scope(db, "server", body)


def build_agent_runtime_state(
    agent: AgentInfo, server_row: AgentSetting | None, user_row: AgentSetting | None
) -> dict[str, Any]:
    server_settings = {field.key: field.default for field in agent.settings_schema}
    user_settings = {field.key: field.default for field in agent.settings_schema}

    if server_row:
        if server_row.settings:
            server_settings.update(server_row.settings)

    if user_row:
        if user_row.settings:
            user_settings.update(user_row.settings)

    if server_row is not None and server_row.enabled is False:
        effective_enabled = False
    elif user_row is not None and user_row.enabled is not None:
        effective_enabled = bool(user_row.enabled)
    elif server_row is not None and server_row.enabled is not None:
        effective_enabled = bool(server_row.enabled)
    else:
        effective_enabled = bool(agent.default_enabled)

    return {
        "enabled": effective_enabled,
        "settings": user_settings if user_row else server_settings,
    }


async def build_agent_runtime_context(db: AsyncSession, user_id: int | None) -> dict[str, Any]:
    from backend.repositories.agent_settings import get_server_agent_settings as _repo_get_server
    from backend.repositories.agent_settings import get_user_agent_settings as _repo_get_user

    server_rows_list = await _repo_get_server(db)
    server_rows = {row.agent_key: row for row in server_rows_list}

    user_rows = {}
    if user_id is not None:
        user_rows_list = await _repo_get_user(db, user_id)
        user_rows = {row.agent_key: row for row in user_rows_list}

    context = {}
    for agent in list_agents():
        state = build_agent_runtime_state(agent, server_rows.get(agent.key), user_rows.get(agent.key))
        if agent.parent_key is None and not state.get("enabled", True):
            state = {**state, "enabled": True}
        context[agent.key] = state

    return context
