from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.services.llm_content import llm_text
from backend.trading_agents.llm_clients.base_client import is_provider_function_degraded

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# These machine contracts are consumed by nodes that already own a deterministic,
# schema-valid fallback. If provider-native structured output is malformed, asking
# the same model to repair it only burns quota and wall-clock time.
_DETERMINISTIC_CALLER_FALLBACK_SCHEMAS = frozenset(
    {
        "AnalysisPlan",
        "SynthesisAssessment",
        "StrategyRevisionCandidate",
        "StrategyRevisionIntent",
        "PortfolioDecision",
    }
)


def _uses_deterministic_caller_fallback(schema: type[BaseModel] | None) -> bool:
    return schema is not None and schema.__name__ in _DETERMINISTIC_CALLER_FALLBACK_SCHEMAS


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Any | None:
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError, TypeError, ValueError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); falling back to free-text generation",
            agent_name,
            exc,
        )
        return None


def extract_json_block(text: str) -> str | None:
    """Extract a JSON substring from text, supporting markdown blocks or raw bounds."""
    if not text:
        return None
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return None


def validate_schema(schema: type[T], parsed_dict: dict) -> T:
    """Validate structured output with the project's Pydantic v2 contract."""
    return schema.model_validate(parsed_dict)


def get_json_schema(schema: type[T]) -> str:
    """Export the Pydantic v2 JSON schema used for self-correction prompts."""
    return json.dumps(schema.model_json_schema(), indent=2)


def parse_and_validate(text: str, schema: type[T]) -> T:
    """Extract a JSON block from ``text`` and validate it against ``schema``.

    Raises ``json.JSONDecodeError`` / validation errors on malformed input;
    callers decide how to recover. Falls back to the stripped text when no
    fenced/braced block is found.
    """
    json_str = extract_json_block(text) or text.strip()
    return validate_schema(schema, json.loads(json_str))


def _coerce_structured_result(result: Any, schema: type[T]) -> T:
    """Normalize a structured provider result into a validated model.

    A schema-bound call has a strict boundary: callers may only receive the
    requested Pydantic model (or, after the outer fallback path, plain text).
    Provider-specific response objects must not escape as validated results.
    """
    if isinstance(result, schema):
        return result
    if isinstance(result, dict):
        return validate_schema(schema, result)

    text = llm_text(result).strip()
    if not text:
        raise ValueError(f"Structured provider returned no parseable text for {schema.__name__}")
    try:
        return parse_and_validate(text, schema)
    except Exception as exc:
        raise ValueError(f"Structured provider result did not match {schema.__name__}: {exc}") from exc


async def _retry_llm_call(
    llm: Any,
    prompt: Any,
    agent_name: str,
    max_retries: int = 2,
    base_delay: float = 2.0,
    timeout: float = 90.0,
) -> Any:
    """Invoke an LLM through the runtime's single retry/timeout authority.

    ``max_retries`` keeps the historical call-site contract even though the
    value represents total attempts. The actual retry classification,
    exponential backoff and timeout implementation lives only in
    ``agents.runtime.resilience.retry_call``.
    """
    from backend.trading_agents.agents.runtime.resilience import retry_call

    return await retry_call(
        lambda: llm.ainvoke(prompt),
        label=f"llm:{agent_name}",
        attempts=max(1, int(max_retries)),
        base_delay=float(base_delay),
        timeout=float(timeout),
    )


async def self_correct_structured(
    plain_llm: Any,
    schema: type[T],
    original_prompt: Any,
    bad_output: str,
    validation_error: str,
    agent_name: str,
    attempt: int = 1,
) -> T | None:
    """Prompt the model to correct its malformed output against the schema and errors."""
    logger.info(
        "%s: Self-correction attempt %d for validation error: %s",
        agent_name,
        attempt,
        validation_error,
    )

    if isinstance(original_prompt, list):
        prompt_str = "\n".join(str(m) for m in original_prompt)
    else:
        prompt_str = str(original_prompt)

    system_content = (
        "You are a strict data-parsing assistant. Your task is to output valid JSON that conforms exactly "
        f"to the following JSON Schema:\n{get_json_schema(schema)}\n\n"
        "Return ONLY raw JSON. Do not include markdown code blocks, explanation text, or greeting prefixes/suffixes."
    )

    user_content = (
        f"We tried to process the task, but the generated output failed schema validation.\n\n"
        f"--- ORIGINAL TASK/PROMPT ---\n{prompt_str[:1500]}\n"
        f"--- INVALID OUTPUT ---\n{bad_output}\n"
        f"--- VALIDATION ERROR ---\n{validation_error}\n\n"
        "Please fix the invalid output so that it conforms strictly to the schema, and output the corrected JSON block now."
    )

    correction_messages = [{"role": "system", "content": system_content}, {"role": "user", "content": user_content}]

    try:
        # Semantic self-correction has its own outer loop below. This call gets
        # one runtime-controlled attempt so timeout/error classification still
        # comes from the same authority without multiplying retries.
        response = await _retry_llm_call(
            plain_llm,
            correction_messages,
            f"{agent_name}:self_correction",
            max_retries=1,
        )
        text = llm_text(response)
        return parse_and_validate(text, schema)
    except Exception as exc:
        if is_provider_function_degraded(exc):
            logger.warning(
                "%s: provider function is degraded during self-correction; stopping further correction attempts.",
                agent_name,
            )
            raise
        logger.warning(
            "%s: Self-correction attempt %d failed to validate: %s",
            agent_name,
            attempt,
            exc,
        )
        return None


async def ainvoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    agent_name: str,
    schema: type[T] | None = None,
) -> Any:
    """Invoke with structured output, falling back to parsing/self-correction on failure.

    If schema is provided, we guarantee validation of the returned Pydantic model
    by extracting JSON from free text and running a self-correction loop if it fails.
    """
    if structured_llm is not None:
        try:
            result = await _retry_llm_call(structured_llm, prompt, agent_name)
            if schema is None:
                return result
            return _coerce_structured_result(result, schema)
        except Exception as exc:
            if is_provider_function_degraded(exc):
                logger.warning(
                    "%s: provider function is degraded; skipping same-model free-text and self-correction requests.",
                    agent_name,
                )
                raise
            if _uses_deterministic_caller_fallback(schema):
                logger.warning(
                    "%s: structured output was unusable (%s); using the caller's deterministic fallback without extra LLM repair calls",
                    agent_name,
                    exc,
                )
                return ""
            logger.warning(
                "%s: structured-output invocation/coercion failed (%s); falling back to parsing free-text",
                agent_name,
                exc,
            )

    response = await _retry_llm_call(plain_llm, prompt, agent_name)
    raw_text = llm_text(response)

    if schema is None:
        return raw_text

    json_str = extract_json_block(raw_text)
    validation_error = ""
    if json_str:
        try:
            parsed = json.loads(json_str)
            return validate_schema(schema, parsed)
        except Exception as exc:
            validation_error = f"JSON/Schema Error: {exc}"
    else:
        validation_error = "Could not locate a valid JSON curly brace block in the text response."

    if _uses_deterministic_caller_fallback(schema):
        logger.warning(
            "%s: free-text structured recovery failed (%s); using the caller's deterministic fallback without self-correction",
            agent_name,
            validation_error,
        )
        return ""

    for attempt in range(1, 3):
        try:
            corrected = await self_correct_structured(
                plain_llm=plain_llm,
                schema=schema,
                original_prompt=prompt,
                bad_output=raw_text,
                validation_error=validation_error,
                agent_name=agent_name,
                attempt=attempt,
            )
        except Exception as exc:
            if is_provider_function_degraded(exc):
                logger.warning(
                    "%s: provider became degraded after free-text generation; keeping that output without another correction request.",
                    agent_name,
                )
                return raw_text
            raise
        if corrected is not None:
            return corrected

    logger.error(
        "%s: All parsing and self-correction attempts failed. Returning unvalidated free text.",
        agent_name,
    )
    return raw_text
