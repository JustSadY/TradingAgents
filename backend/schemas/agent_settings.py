from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AgentSettingValue(BaseModel):
    enabled: bool
    settings: dict[str, Any] = {}


class AgentSettingsRead(BaseModel):
    agents: dict[str, AgentSettingValue]


class AgentSettingUpdateValue(BaseModel):
    enabled: bool | None = None
    settings: dict[str, Any] | None = None
    reset_enabled: bool = False
    reset_settings: list[str] = []


class AgentSettingsUpdate(BaseModel):
    agents: dict[str, AgentSettingUpdateValue]
