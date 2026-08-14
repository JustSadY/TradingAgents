from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolSettingValue(BaseModel):
    enabled: bool
    settings: dict[str, Any] = {}

class ToolSettingsRead(BaseModel):
    tools: dict[str, ToolSettingValue]

class ToolSettingUpdateValue(BaseModel):
    enabled: bool | None = None
    settings: dict[str, Any] | None = None
    reset_enabled: bool = False
    reset_settings: list[str] = []

class ToolSettingsUpdate(BaseModel):
    tools: dict[str, ToolSettingUpdateValue]

class ToolSettingFieldMeta(BaseModel):
    key: str
    type: str
    scope: str
    label_key: str
    description_key: str | None = None
    default: Any = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[dict] = []
    secret: bool = False
    advanced: bool = False

class ToolMeta(BaseModel):
    key: str
    category: str
    default_enabled: bool
    allowed_analysts: list[str]
    label_key: str
    description_key: str
    settings_schema: list[ToolSettingFieldMeta]
