from __future__ import annotations

from .base import BaseAgentTool

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseAgentTool] = {}
        self._langchain_tool_to_agent_tool_key: dict[str, str] = {}

    def register(self, tool: BaseAgentTool) -> BaseAgentTool:
        if tool.key in self._tools:
            raise ValueError(f"duplicate tool key: {tool.key}")
        self._tools[tool.key] = tool
        for name in tool.langchain_tool_names:
            self._langchain_tool_to_agent_tool_key[name] = tool.key
        return tool

    def get(self, key: str) -> BaseAgentTool | None:
        return self._tools.get(key)

    def list(self) -> list[BaseAgentTool]:
        return list(self._tools.values())

    def metadata(self) -> list[dict]:
        return [tool.metadata() for tool in self.list()]

    def get_agent_tool_key_for_langchain_tool(self, langchain_tool_name: str) -> str | None:
        return self._langchain_tool_to_agent_tool_key.get(langchain_tool_name)

registry = ToolRegistry()

