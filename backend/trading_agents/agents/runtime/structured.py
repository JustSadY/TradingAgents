from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.trading_agents.llm_clients.base_client import is_provider_function_degraded

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Any | None:
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
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
    # Try finding json markdown code blocks
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Try finding any markdown code blocks
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try finding a bounding brace block
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


def _coerce_structured_result(result: Any, schema: type[T]) -> Any:
    """Normalize a ``with_structured_output`` result into a validated model.

    Handles the three shapes a provider may return: an already-built model, a
    plain dict, or an AIMessage/string carrying JSON. Returns the raw ``result``
    unchanged when it cannot be coerced.
    """
    if isinstance(result, schema):
        return result
    if isinstance(result, dict):
        return validate_schema(schema, result)
    content = getattr(result, "content", result)
    if isinstance(content, str):
        try:
            return parse_and_validate(content, schema)
        except Exception:
            pass
    return result


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
        response = await plain_llm.ainvoke(correction_messages)
        text = response.content if hasattr(response, "content") else str(response)
        return parse_and_validate(text, schema)
    except Exception as exc:
        # A NIM ``DEGRADED function`` response is a provider-side deployment
        # outage.  Trying the same model again cannot repair JSON and merely
        # creates two more failing requests.  Let the caller retain the
        # already-generated free text instead.
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


def _is_quota_exhausted(exc: Exception) -> bool:
    """Check if the error indicates a hard quota exhaustion (not a transient rate limit).

    ``ResourceExhausted`` with "total request limit" or "quota" means the provider
    has permanently denied requests for the current period — retrying is useless.
    Also catches ``QuotaExhaustedError`` from the LLM client layer.
    """
    err_msg = str(exc).lower()
    if "quota exhausted" in err_msg:
        return True
    return "resourceexhausted" in err_msg and ("total" in err_msg or "quota" in err_msg)


def _is_rate_limit(exc: Exception) -> bool:
    """Check if the error is a transient rate limit (429) worth retrying."""
    err_msg = str(exc).lower()
    return "429" in err_msg or "rate limit" in err_msg or "rate_limit" in err_msg


def _is_server_error(exc: Exception) -> bool:
    """Check if the error is a transient server error worth retrying."""
    err_msg = str(exc).lower()
    return "503" in err_msg or "service unavailable" in err_msg or "502" in err_msg


async def _retry_llm_call(
    llm: Any,
    prompt: Any,
    agent_name: str,
    max_retries: int = 2,
    base_delay: float = 2.0,
    timeout: float = 90.0,
) -> Any:
    """Invoke *llm* with retry and exponential backoff for transient errors.

    Permanent quota exhaustion (``ResourceExhausted`` + "total"/"quota") is detected
    immediately — no retries wasted, the exception propagates so callers can use fallback.

    Note: ``max_retries = 2`` (1 retry) is the default — the provider quota (32
    requests) is tight; burning 3+ requests per failed call can exhaust it before
    essential nodes get to run.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(llm.ainvoke(prompt), timeout=timeout)
        except Exception as exc:
            last_exc = exc
            # NVIDIA NIM reports an unhealthy hosted model deployment as a
            # 400 ``DEGRADED function`` error.  It is neither a malformed
            # prompt nor a recoverable same-model retry, so preserve it for a
            # configured fallback chain or the graph-level safe fallback.
            if is_provider_function_degraded(exc):
                raise
            if _is_quota_exhausted(exc):
                logger.warning(
                    "%s: quota exhausted (%s) — skipping retries, using fallback.",
                    agent_name,
                    exc,
                )
                raise
            retriable = _is_rate_limit(exc) or _is_server_error(exc) or "timeout" in str(exc).lower()
            if not retriable:
                raise
            delay = min(base_delay * (2**attempt), 30.0)
            if attempt + 1 < max_retries:
                logger.warning(
                    "%s: LLM call failed (attempt %d/%d, retry in %.0fs): %s",
                    agent_name,
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


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
            # ``structured_llm`` is already built with any configured model
            # fallbacks.  If its invocation still surfaces a degraded hosted
            # function, do not issue a plain-text request and then two JSON
            # self-corrections against that same unavailable deployment.
            # Re-raise so the graph can use its explicit safe fallback.
            if is_provider_function_degraded(exc):
                logger.warning(
                    "%s: provider function is degraded; skipping same-model free-text and self-correction requests.",
                    agent_name,
                )
                raise
            logger.warning(
                "%s: structured-output ainvocation failed (%s); falling back to parsing free-text",
                agent_name,
                exc,
            )

    response = await _retry_llm_call(plain_llm, prompt, agent_name)
    raw_text = response.content if hasattr(response, "content") else str(response)

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
