from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.schemas.settings import SettingsUpdate
from backend.services.agent_settings_service import validate_agent_settings
from backend.services.settings_service import SettingsPermissionError, enforce_settings_update_permissions
from backend.trading_agents.agent_catalog import get_agent


def test_settings_update_rejects_retired_scalar_and_fallback_contracts() -> None:
    with pytest.raises(ValidationError):
        SettingsUpdate(webhook_events="analysis_complete,trade_executed")

    with pytest.raises(ValidationError):
        SettingsUpdate(
            fallback_llm_provider="openai",
            fallback_llm_model="gpt-4o-mini",
        )


def test_agent_settings_reject_retired_custom_system_instruction_alias() -> None:
    agent = get_agent("market")
    assert agent is not None

    with pytest.raises(ValueError, match="Unknown setting 'custom_system_instruction'"):
        validate_agent_settings(agent, {"custom_system_instruction": "legacy override"})

    current = validate_agent_settings(agent, {"system_instruction": "current override"})
    assert current["system_instruction"] == "current override"


async def test_advanced_settings_policy_lives_in_service(
    db: AsyncSession,
    test_user: User,
) -> None:
    with pytest.raises(SettingsPermissionError, match="administrators"):
        await enforce_settings_update_permissions(db, test_user, SettingsUpdate(max_recur_limit=50))


def test_settings_router_has_no_direct_repository_or_config_access() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "api" / "settings.py").read_text()

    assert "backend.repositories" not in source
    assert "backend.core.config" not in source
    assert "from pydantic import BaseModel" not in source
    assert "list_allowed_setting_sections" not in source
    assert "get_user_by_id" not in source
    assert "list_user_api_key_providers" not in source
    assert "enforce_settings_update_permissions" in source
    assert "list_stored_api_key_providers" in source


def test_settings_service_uses_repository_for_app_settings_queries() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "settings_service.py").read_text()

    assert "from sqlalchemy import select" not in source
    assert "IntegrityError" not in source
    assert "select(AppSettings" not in source
    assert "backend.repositories.settings" in source
