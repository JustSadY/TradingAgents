from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

ToolSettingType = Literal[
    "boolean",
    "number",
    "string",
    "textarea",
    "select",
    "multi_select",
    "string_list",
    "secret",
]


@dataclass(frozen=True)
class ToolSettingOption:
    value: str
    label_key: str


@dataclass(frozen=True)
class ToolSettingField:
    key: str
    type: ToolSettingType
    label_key: str
    scope: Literal["server", "user", "both"] = "user"

    description_key: str | None = None
    default: Any = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[ToolSettingOption] = field(default_factory=list)
    secret: bool = False
    advanced: bool = False


@dataclass(frozen=True)
class ToolContext:
    user_id: int | None
    analyst_key: str
    ticker: str | None = None
    asset_type: str = "stock"
    run_id: str | None = None


class BaseAgentTool(ABC):
    key: str
    category: str
    default_enabled: bool = False
    allowed_analysts: list[str] = []
    label_key: str
    description_key: str
    settings_schema: list[ToolSettingField] = []
    langchain_tool_names: list[str] = []

    requires_secret: bool = False
    requires_network: bool = True
    requires_db: bool = False

    def metadata(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "category": self.category,
            "default_enabled": self.default_enabled,
            "allowed_analysts": self.allowed_analysts,
            "label_key": self.label_key,
            "description_key": self.description_key,
            "settings_schema": [
                {
                    "key": field.key,
                    "type": field.type,
                    "scope": field.scope,
                    "label_key": field.label_key,
                    "description_key": field.description_key,
                    "default": field.default,
                    "required": field.required,
                    "min": field.min,
                    "max": field.max,
                    "step": field.step,
                    "options": [{"value": opt.value, "label_key": opt.label_key} for opt in field.options],
                    "secret": field.secret,
                    "advanced": field.advanced,
                }
                for field in self.settings_schema
            ],
            "requires_secret": self.requires_secret,
            "requires_network": self.requires_network,
            "requires_db": self.requires_db,
        }

    def default_settings(self, scope: str | None = None) -> dict[str, Any]:
        return {
            field.key: field.default
            for field in self.settings_schema
            if scope is None or field.scope in (scope, "both")
        }

    @abstractmethod
    def get_langchain_tools(
        self,
        settings: dict[str, Any],
        context: ToolContext,
    ) -> list:
        raise NotImplementedError
