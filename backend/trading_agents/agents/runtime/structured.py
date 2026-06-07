from __future__ import annotations

import logging
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


async def ainvoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    agent_name: str,
) -> Any:
    """Invoke with structured output, falling back to free text on failure.

    Returns the structured object if successful, otherwise the free-text string
    content (callers render the structured object themselves).
    """
    if structured_llm is not None:
        try:
            result = await structured_llm.ainvoke(prompt)
            return result
        except Exception as exc:
            logger.warning(
                "%s: structured-output ainvocation failed (%s); retrying once as free text",
                agent_name,
                exc,
            )
    response = await plain_llm.ainvoke(prompt)
    return response.content
