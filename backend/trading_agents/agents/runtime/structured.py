from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

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
    """Support both Pydantic v1 and v2 validation methods."""
    if hasattr(schema, "model_validate"):
        return schema.model_validate(parsed_dict)
    if hasattr(schema, "parse_obj"):
        return schema.parse_obj(parsed_dict)
    return schema(**parsed_dict)


def get_json_schema(schema: type[T]) -> str:
    """Support both Pydantic v1 and v2 schema export."""
    if hasattr(schema, "model_json_schema"):
        return json.dumps(schema.model_json_schema(), indent=2)
    if hasattr(schema, "schema"):
        return json.dumps(schema.schema(), indent=2)
    return "{}"


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
    
    # Convert original prompt to a readable string representation
    if isinstance(original_prompt, list):
        prompt_str = "\n".join(str(m) for m in original_prompt)
    else:
        prompt_str = str(original_prompt)

    # Build system instructions and correction user prompt
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

    correction_messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]

    try:
        response = await plain_llm.ainvoke(correction_messages)
        text = response.content if hasattr(response, "content") else str(response)
        json_str = extract_json_block(text) or text.strip()
        parsed = json.loads(json_str)
        return validate_schema(schema, parsed)
    except Exception as exc:
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
    # 1. Attempt structured LLM if configured
    if structured_llm is not None:
        try:
            result = await structured_llm.ainvoke(prompt)
            # Ensure it is validated if a schema is given
            if schema is not None:
                if isinstance(result, schema):
                    return result
                if isinstance(result, dict):
                    return validate_schema(schema, result)
            return result
        except Exception as exc:
            logger.warning(
                "%s: structured-output ainvocation failed (%s); falling back to parsing free-text",
                agent_name,
                exc,
            )

    # 2. Call plain LLM
    response = await plain_llm.ainvoke(prompt)
    raw_text = response.content if hasattr(response, "content") else str(response)

    # If no schema was requested, we return raw text content
    if schema is None:
        return raw_text

    # 3. Try to extract and validate JSON from the raw response
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

    # 4. Trigger self-correction loop (max 2 attempts)
    for attempt in range(1, 3):
        corrected = await self_correct_structured(
            plain_llm=plain_llm,
            schema=schema,
            original_prompt=prompt,
            bad_output=raw_text,
            validation_error=validation_error,
            agent_name=agent_name,
            attempt=attempt,
        )
        if corrected is not None:
            return corrected
        
    # 5. Ultimate fallback if all attempts fail: log error and return raw text
    logger.error(
        "%s: All parsing and self-correction attempts failed. Returning unvalidated free text.",
        agent_name,
    )
    return raw_text
