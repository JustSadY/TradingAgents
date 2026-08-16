from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.settings import SettingsUpdate
from backend.services.agent_settings_service import validate_agent_settings
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
