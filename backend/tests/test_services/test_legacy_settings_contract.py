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
        await enforce_settings_update_permissions(db, test_user, SettingsUpdate(max_recur_limit=100))


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


def test_analysis_stats_and_calibration_use_repository_queries_only() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    stats = (backend_root / "services" / "analysis_stats_service.py").read_text()
    calibration = (backend_root / "services" / "confidence_calibration_service.py").read_text()

    assert "from sqlalchemy import select" not in stats
    assert "backend.models.analysis" not in stats
    assert "DB may be unmigrated" not in stats
    assert "backend.repositories.analysis_stats" in stats

    assert "from sqlalchemy import select" not in calibration
    assert "backend.models.analysis" not in calibration
    assert "chart_annotations" not in calibration
    assert "backend.repositories.analysis_stats" in calibration


def test_runtime_access_and_strategy_context_do_not_own_analysis_or_access_sql() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    tool_settings = (backend_root / "services" / "tool_settings_service.py").read_text()
    strategy_context = (backend_root / "services" / "strategy_context_service.py").read_text()

    assert "from sqlalchemy import select" not in tool_settings
    assert "UserAgentAccess" not in tool_settings
    assert "UserToolAccess" not in tool_settings
    assert "UserToolFieldAccess" not in tool_settings
    assert "get_user_access_overrides" in tool_settings

    assert "from sqlalchemy import select" not in strategy_context
    assert "backend.models.analysis" not in strategy_context
    assert "backend.repositories.strategy_context" in strategy_context


def test_memory_service_reads_relational_configuration_via_repositories() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "memory_service.py").read_text()

    assert "from sqlalchemy import select" not in source
    assert "backend.models.settings" not in source
    assert "backend.models.user" not in source
    assert "backend.repositories.settings" in source
    assert "backend.repositories.users" in source
