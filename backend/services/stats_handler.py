from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

_logger = logging.getLogger(__name__)


class StatsCallbackHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        self.llm_calls = 0
        self.tool_calls = 0
        self._run_usage: dict[Any, dict[str, int]] = {}
        self._seen_runs: set[Any] = set()

    @property
    def tokens_in(self) -> int:
        return sum(u["input"] for u in self._run_usage.values())

    @property
    def tokens_out(self) -> int:
        return sum(u["output"] for u in self._run_usage.values())

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id and run_id not in self._seen_runs:
            self._seen_runs.add(run_id)
            self.llm_calls += 1
        elif not run_id:
            self.llm_calls += 1

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        if run_id and run_id not in self._seen_runs:
            self._seen_runs.add(run_id)
            self.llm_calls += 1
        elif not run_id:
            self.llm_calls += 1

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage = self._extract_usage(response)
        if usage is None:
            _logger.warning("LLM token usage metadata not found; skipping token counters")
            return
        run_id = kwargs.get("run_id") or f"fallback_{len(self._run_usage)}"
        self._run_usage[run_id] = usage

    def on_tool_start(self, *args: Any, **kwargs: Any) -> None:
        self.tool_calls += 1

    @staticmethod
    def _to_int(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return 0
            try:
                return int(float(value))
            except ValueError:
                return 0
        return 0

    @classmethod
    def _parse_usage_dict(cls, usage: Any) -> dict[str, int] | None:
        if usage is None:
            return None

        # Providers hand usage back either as a dict (LangChain-normalized) or
        # as an SDK object with attributes; read both through one getter.
        if isinstance(usage, dict) or hasattr(usage, "get"):
            getter = usage.get
        else:
            def getter(key, default=None):
                return getattr(usage, key, default)

        input_tokens = cls._to_int(
            getter("prompt_tokens")
            or getter("input_tokens")
            or getter("prompt_token_count")
            or getter("input_token_count")
        )
        # Anthropic's RAW usage reports cached prompt tokens separately: its
        # input_tokens covers only the uncached remainder, so with prompt
        # caching enabled the counters under-report massively unless the cache
        # buckets are added back. (LangChain's normalized usage_metadata already
        # includes them in input_tokens under different detail keys, so these
        # raw key names never double-count.)
        input_tokens += cls._to_int(getter("cache_read_input_tokens"))
        input_tokens += cls._to_int(getter("cache_creation_input_tokens"))
        output_tokens = cls._to_int(
            getter("completion_tokens")
            or getter("output_tokens")
            or getter("candidates_token_count")
            or getter("output_token_count")
        )
        if input_tokens == 0 and output_tokens == 0:
            return None
        return {"input": input_tokens, "output": output_tokens}

    @classmethod
    def _extract_usage(cls, response: Any) -> dict[str, int] | None:
        # Prefer the standardized usage_metadata (on the result or its
        # messages): LangChain normalizes provider quirks there — e.g. Anthropic
        # cache reads/creations are already folded into input_tokens. The raw
        # llm_output dict is checked LAST because for some providers it
        # under-reports (Anthropic raw input_tokens excludes cached tokens).
        direct_usage = cls._parse_usage_dict(getattr(response, "usage_metadata", None))
        if direct_usage is not None:
            return direct_usage

        for gen_list in getattr(response, "generations", []) or []:
            for gen in gen_list:
                message = getattr(gen, "message", None)
                usage = cls._parse_usage_dict(getattr(message, "usage_metadata", None))
                if usage is not None:
                    return usage
                response_metadata = getattr(message, "response_metadata", None)
                usage = cls._parse_usage_dict(
                    (response_metadata or {}).get("token_usage") if isinstance(response_metadata, dict) else None
                )
                if usage is not None:
                    return usage
                usage = cls._parse_usage_dict(
                    (response_metadata or {}).get("usage") if isinstance(response_metadata, dict) else None
                )
                if usage is not None:
                    return usage

        llm_output = getattr(response, "llm_output", None)
        usage = cls._parse_usage_dict((llm_output or {}).get("token_usage") if isinstance(llm_output, dict) else None)
        if usage is not None:
            return usage
        usage = cls._parse_usage_dict((llm_output or {}).get("usage") if isinstance(llm_output, dict) else None)
        if usage is not None:
            return usage

        return None

    def get_stats(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }

