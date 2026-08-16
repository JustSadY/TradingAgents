from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSettingValue(BaseModel):
    enabled: bool
    settings: dict[str, Any] = Field(default_factory=dict)


class ToolSettingsRead(BaseModel):
    tools: dict[str, ToolSettingValue]


class ToolSettingUpdateValue(BaseModel):
    enabled: bool | None = None
    settings: dict[str, Any] | None = None
    reset_enabled: bool = False
    reset_settings: list[str] = Field(default_factory=list)


class ToolSettingsUpdate(BaseModel):
    tools: dict[str, ToolSettingUpdateValue]


class SettingOptionMeta(BaseModel):
    """One choice in a settings dropdown.

    The engine emits exactly these two keys; declaring them means the generated
    frontend client gets a real type instead of a free-form object, which is
    what previously forced the settings panels to cast.
    """

    value: str
    label_key: str


# Mirrors the engine's own Literals in
# `trading_agents/agents/tools/base.py`. Declaring them here rather than as
# bare `str` is what lets the generated frontend client keep the narrow unions
# its form builder switches on, instead of casting them back.
ToolSettingTypeName = Literal[
    "boolean", "number", "string", "textarea", "select", "multi_select", "string_list", "secret"
]
SettingScope = Literal["server", "user", "both"]


class ToolSettingFieldMeta(BaseModel):
    key: str
    type: ToolSettingTypeName
    scope: SettingScope
    label_key: str
    description_key: str | None = None
    default: Any = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[SettingOptionMeta] = Field(default_factory=list)
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
    requires_secret: bool
    requires_network: bool
    requires_db: bool
    temporal_semantics: str
