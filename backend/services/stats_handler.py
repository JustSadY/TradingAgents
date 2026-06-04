from __future__ import annotations
import logging
from typing import Any
from langchain_core.callbacks import BaseCallbackHandler
_logger = logging.getLogger(__name__)
class StatsCallbackHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.llm_calls += 1
    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self.llm_calls += 1
    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        try:
            usage = self._extract_usage(response)
            self.tokens_in += int(usage.get("input", 0) or 0)
            self.tokens_out += int(usage.get("output", 0) or 0)
        except Exception:
            pass
    def on_tool_start(self, *args: Any, **kwargs: Any) -> None:
        self.tool_calls += 1
    @staticmethod
    def _extract_usage(response: Any) -> dict:
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            tu = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if tu:
                return {
                    "input": tu.get("prompt_tokens") or tu.get("input_tokens") or 0,
                    "output": tu.get("completion_tokens") or tu.get("output_tokens") or 0,
                }
        try:
            for gen_list in getattr(response, "generations", []) or []:
                for gen in gen_list:
                    message = getattr(gen, "message", None)
                    um = getattr(message, "usage_metadata", None)
                    if um:
                        return {
                            "input": um.get("input_tokens", 0),
                            "output": um.get("output_tokens", 0),
                        }
        except Exception:
            pass
        return {"input": 0, "output": 0}
    def get_stats(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }
