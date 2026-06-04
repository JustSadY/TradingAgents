from __future__ import annotations
from typing import Any
from .base import BaseAgentTool, ToolSettingField, ToolContext


class FunctionToolAdapter(BaseAgentTool):
    def __init__(
        self,
        *,
        key: str,
        category: str,
        label_key: str,
        description_key: str,
        func: Any,
        allowed_analysts: list[str],
        default_enabled: bool = True,
        settings_schema: list[ToolSettingField] | None = None,
        langchain_tool_names: list[str] | None = None,
    ):
        self.key = key
        self.category = category
        self.label_key = label_key
        self.description_key = description_key
        self.func = func
        self.allowed_analysts = allowed_analysts
        self.default_enabled = default_enabled
        self.settings_schema = settings_schema or []
        self.langchain_tool_names = langchain_tool_names or [func.name if hasattr(func, "name") else func.__name__]

    def get_langchain_tools(self, settings: dict[str, Any], context: ToolContext) -> list:
        return [self.func]
