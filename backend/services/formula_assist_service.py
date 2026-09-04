"""Natural-language → custom-indicator formula generation.

The Chart page's formula box accepts a restricted DSL evaluated by
``indicator_service.evaluate_formula_safely``. This service lets the user
describe an indicator in plain language; the configured LLM writes the formula
and the result is validated against synthetic OHLCV data (no network) before
it is ever returned, so the client only receives formulas that actually
compute.
"""

from __future__ import annotations

import logging
import re

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from backend.core.exceptions import ExternalServiceError
from backend.services.indicator_service import evaluate_formula_safely
from backend.services.settings_service import get_or_create_settings

_logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 500
_MAX_FORMULA_CHARS = 300
_LLM_ATTEMPTS = 3
_LLM_RETRY_BASE_DELAY_SECONDS = 0.5
_TRANSIENT_PROVIDER_HINTS = (
    "worker local total request limit reached",
    "too many requests",
    "rate limit",
    "rate_limit",
    "429",
    "temporarily unavailable",
    "service unavailable",
    "overloaded",
)

_SYSTEM_PROMPT = """You translate a user's plain-language indicator request into ONE formula
for a restricted charting DSL. Reply with the formula only — no explanations,
no code fences, no quotes.

DSL rules:
- Price/volume series: Open, High, Low, Close, Volume
- Functions (single integer argument only):
  SMA(n), EMA(n), STD(n), RSI(n)   — computed on Close
  ATR(n), ADX(n), CCI(n), WILLR(n) — computed on High/Low/Close
  MFI(n)                           — computed on High/Low/Close/Volume
  BBL(n), BBM(n), BBU(n)           — Bollinger lower/middle/upper band (2 std)
  STOCHK(n), STOCHD(n)             — stochastic %K and %D
  MAX(n)  highest High of last n bars, MIN(n) lowest Low of last n bars
  VWAP(n) rolling volume-weighted average price
  VOLSMA(n) average Volume of last n bars
  SHIFT(n) the Close from n bars ago
- Arithmetic only: + - * / and parentheses. Numeric constants allowed.
- NOT available: if/else, comparisons, crossover detection, abs/min/max of
  two expressions, nested function-of-function calls like EMA(RSI(14)).

Examples:
- "distance from the 20 day average in std devs" -> (Close - SMA(20)) / STD(20)
- "MACD line" -> EMA(12) - EMA(26)
- "Bollinger %B with 20/2" -> (Close - BBL(20)) / (BBU(20) - BBL(20))
- "stochastic %K 14" -> STOCHK(14)
- "how far above the upper Bollinger band" -> Close - BBU(20)
- "10 day rate of change in percent" -> (Close / SHIFT(10) - 1) * 100
- "volume vs its 20 day average" -> Volume / VOLSMA(20)
- "alert me when MACD crosses the signal line" -> UNSUPPORTED
If the request cannot be expressed in this DSL, reply with exactly: UNSUPPORTED
"""


def _synthetic_ohlcv(rows: int = 120) -> pd.DataFrame:
    """Deterministic OHLCV frame used to validate formulas without network IO."""
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, rows))
    spread = np.abs(rng.normal(0.5, 0.2, rows))
    return pd.DataFrame(
        {
            "Open": close + rng.normal(0, 0.3, rows),
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": rng.integers(1_000, 50_000, rows).astype(float),
        }
    )


def _extract_formula(raw: str) -> str:
    """Pull the bare formula out of an LLM reply (strip fences/quotes/prose)."""
    text = raw.strip()
    fence = re.search(r"```(?:\w+)?\s*(.+?)\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    for line in text.splitlines():
        line = line.strip().strip("`'\"")
        if line:
            return line
    return ""


def _is_transient_provider_error(exc: BaseException) -> bool:
    """Return whether an upstream LLM failure is safe to retry briefly."""
    message = str(exc).lower()
    return any(hint in message for hint in _TRANSIENT_PROVIDER_HINTS)


async def _invoke_formula_llm(llm, messages):
    """Invoke the formula LLM with bounded backoff for provider saturation."""
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(_LLM_ATTEMPTS),
            wait=wait_exponential_jitter(initial=_LLM_RETRY_BASE_DELAY_SECONDS, max=30.0),
            retry=retry_if_exception(_is_transient_provider_error),
            before_sleep=before_sleep_log(_logger, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                return await llm.ainvoke(messages)
    except Exception as exc:
        if _is_transient_provider_error(exc):
            raise ExternalServiceError(
                "The AI provider is temporarily at capacity. Please try again shortly.",
                status_code=503,
            ) from exc
        raise
    raise AssertionError("unreachable")


async def generate_formula(db: AsyncSession, prompt: str, user) -> str:
    """Return a validated DSL formula for *prompt* using the user's LLM."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Describe the indicator you want, e.g. 'distance from the 50 day average'.")
    if len(prompt) > _MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long (max {_MAX_PROMPT_CHARS} characters).")

    from langchain_core.messages import HumanMessage, SystemMessage

    from backend.services.user_service import resolve_user_api_key
    from backend.trading_agents.llm_clients.factory import create_llm_client
    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    settings = await get_or_create_settings(db, user)
    provider = settings.llm_provider
    model = settings.llm_model

    api_key = resolve_user_api_key(user, provider)
    if provider_requires_api_key(provider) and not api_key:
        raise ValueError(f"No API key set for provider '{provider}'. Please add your API key in Settings.")

    client = create_llm_client(provider=provider, model=model, api_key=api_key)
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]

    # Settings are the only DB dependency of formula generation. Close the read
    # transaction before provider retries/backoff so capacity pressure on the
    # LLM cannot consume a database pool slot at the same time.
    await db.commit()
    response = await _invoke_formula_llm(client.get_llm(), messages)

    from backend.services.llm_content import llm_text

    formula = _extract_formula(llm_text(response))
    if not formula or formula.upper() == "UNSUPPORTED":
        raise ValueError(
            "That indicator cannot be expressed with the available functions "
            "(SMA/EMA/STD/RSI/ATR/ADX/CCI/MFI/WILLR/BBL/BBM/BBU/STOCHK/STOCHD/MAX/MIN/VWAP/VOLSMA/SHIFT)."
        )
    if len(formula) > _MAX_FORMULA_CHARS:
        raise ValueError("Generated formula is too long; try a simpler description.")

    try:
        evaluate_formula_safely(_synthetic_ohlcv(), formula)
    except ValueError as exc:
        _logger.warning("LLM produced an invalid formula %r for prompt %r: %s", formula, prompt, exc)
        raise ValueError("The AI produced an invalid formula; please rephrase your request.") from exc

    return formula
