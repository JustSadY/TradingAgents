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

from backend.services.indicator_service import evaluate_formula_safely
from backend.services.settings_service import get_or_create_settings

_logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 500
_MAX_FORMULA_CHARS = 300

_SYSTEM_PROMPT = """You translate a user's plain-language indicator request into ONE formula
for a restricted charting DSL. Reply with the formula only — no explanations,
no code fences, no quotes.

DSL rules:
- Price/volume series: Open, High, Low, Close, Volume
- Functions (integer argument only): SMA(n), EMA(n), STD(n), RSI(n), ADX(n)
  (all computed on Close; ADX uses High/Low/Close)
- Arithmetic only: + - * / and parentheses. Numeric constants allowed.
- NOT available: historical offsets (close[1]), crossovers, if/else, ta.*,
  min/max/abs functions, comparison operators.

Examples:
- "distance from the 20 day average in std devs" -> (Close - SMA(20)) / STD(20)
- "MACD line" -> EMA(12) - EMA(26)
- "Bollinger %B with 20/2" -> (Close - SMA(20) + 2*STD(20)) / (4*STD(20))
- "average volume of the last 20 days" -> UNSUPPORTED
  (SMA/EMA/STD only operate on Close, not Volume)
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
    # Keep the first non-empty line; models sometimes append commentary.
    for line in text.splitlines():
        line = line.strip().strip("`'\"")
        if line:
            return line
    return ""


async def generate_formula(db: AsyncSession, prompt: str, user) -> str:
    """Return a validated DSL formula for *prompt* using the user's LLM."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Describe the indicator you want, e.g. 'distance from the 50 day average'.")
    if len(prompt) > _MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt too long (max {_MAX_PROMPT_CHARS} characters).")

    from langchain_core.messages import HumanMessage, SystemMessage

    from backend.services.report_chat_service import _resolve_user_api_key
    from backend.trading_agents.llm_clients.factory import create_llm_client

    settings = await get_or_create_settings(db, user)
    provider = settings.llm_provider
    model = settings.llm_model

    api_key = _resolve_user_api_key(user, provider)
    if not api_key and not getattr(user, "is_admin", False):
        raise ValueError(f"No API key set for provider '{provider}'. Please add your API key in Settings.")

    client = create_llm_client(provider=provider, model=model, api_key=api_key)
    response = await client.get_llm().ainvoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)])

    formula = _extract_formula(str(response.content))
    if not formula or formula.upper() == "UNSUPPORTED":
        raise ValueError("That indicator cannot be expressed with the available functions (SMA/EMA/STD/RSI/ADX).")
    if len(formula) > _MAX_FORMULA_CHARS:
        raise ValueError("Generated formula is too long; try a simpler description.")

    # Never hand the client a formula that does not actually compute.
    try:
        evaluate_formula_safely(_synthetic_ohlcv(), formula)
    except ValueError as exc:
        _logger.warning("LLM produced an invalid formula %r for prompt %r: %s", formula, prompt, exc)
        raise ValueError("The AI produced an invalid formula; please rephrase your request.") from exc

    return formula
