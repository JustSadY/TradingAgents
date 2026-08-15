from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.tool_settings import ToolMeta, ToolSettingFieldMeta


class Choice(BaseModel):
    value: str
    label: str
    description: str | None = None
    note: str | None = None


class AnalystMeta(BaseModel):
    key: str
    label: str
    description: str
    default: bool


class SignalMeta(BaseModel):
    value: str
    label: str
    tone: str


class AgentSettingFieldMeta(BaseModel):
    key: str
    type: str
    label_key: str
    description_key: str | None = None
    placeholder_key: str | None = None
    default: Any = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)


class AgentMeta(BaseModel):
    key: str
    label: str
    description: str
    category: str
    default_enabled: bool
    parent_key: str | None = None
    settings_schema: list[AgentSettingFieldMeta] = Field(default_factory=list)


class SectionMeta(BaseModel):
    key: str
    label: str
    category: str
    order: int
    icon: str


class MetaResponse(BaseModel):
    analysts: list[AnalystMeta]
    tools: list[ToolMeta]
    agents: list[AgentMeta]
    section_labels: dict[str, str]
    signals: list[SignalMeta]
    asset_types: list[Choice]
    languages: list[Choice]
    data_vendors: list[Choice]
    trading_modes: list[Choice]
    brokers: list[Choice]
    provider_labels: dict[str, str]
    investor_personas: list[Choice]
    effort_options: dict[str, list[Choice]]
    order_statuses: list[SignalMeta]
    order_actions: list[SignalMeta]
    chart_periods: list[Choice]
    page_keys: list[str]
    setting_keys: list[Choice]
    sections: list[SectionMeta]
    webhook_events: list[str]
    memory_stores: list[Choice]
    embedders: list[Choice]


__all__ = [
    "Choice",
    "AnalystMeta",
    "SignalMeta",
    "ToolSettingFieldMeta",
    "ToolMeta",
    "AgentSettingFieldMeta",
    "AgentMeta",
    "SectionMeta",
    "MetaResponse",
]
