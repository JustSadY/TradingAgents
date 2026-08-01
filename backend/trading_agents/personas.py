"""Investor persona registry — the single source of truth for personas.

Each persona is defined once here: its key, a short UI label/description (so the
backend can surface the available personas to the frontend via ``/api/meta``),
and the instruction block injected into the Portfolio Manager's prompt. Adding a
persona is a one-place change; the PM and the API pick it up automatically.

This module is intentionally dependency-free and lives at the engine root (not
under ``agents/``) so the backend can import it for metadata without triggering
the heavy ``agents`` package import chain.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PERSONA = "conservative"

@dataclass(frozen=True)
class InvestorPersona:
    key: str
    label: str
    description: str
    instructions: str

_PERSONAS: dict[str, InvestorPersona] = {}

def register_persona(persona: InvestorPersona) -> None:
    _PERSONAS[persona.key] = persona

def get_persona(key: str | None) -> InvestorPersona | None:
    return _PERSONAS.get(key or "")

_PERSONA_INSTRUCTIONS = {
    "conservative": (
        "**INVESTOR PERSONA: Conservative Dividend Investor**\n"
        "- Your client is highly risk-averse, focusing on capital preservation, steady income (dividends), and low-volatility blue-chip assets.\n"
        "- Prefer 'Hold' or 'Sell/Underweight' if uncertainty is high. Do not recommend aggressive positioning, high leverage, or speculative assets unless backed by overwhelming positive fundamental data.\n"
        "- Keep position sizing conservative, prioritizing cash safety.\n"
    ),
    "risk_loving": (
        "**INVESTOR PERSONA: Risk-Loving Crypto & Growth Trader**\n"
        "- Your client seeks high returns and is willing to accept high volatility, leverage, and speculative growth or crypto assets.\n"
        "- Emphasize growth potential and momentum. Be willing to recommend 'Buy' or 'Overweight' sizing if there is a strong technical breakout or high social sentiment, even if fundamentals are weak or debate is mixed.\n"
    ),
    "esg_focused": (
        "**INVESTOR PERSONA: Sustainability / ESG-Focused Investor**\n"
        "- Your client prioritizes environmental, social, and corporate governance metrics alongside financial returns.\n"
        "- Strictly penalize companies with controversial environmental track records, poor corporate governance, or regulatory issues. Heavily favor clean energy, positive social governance, and sustainable business models.\n"
    ),
    "aggressive": (
        "**INVESTOR PERSONA: Aggressive Growth Investor**\n"
        "- Your client is a high-conviction, aggressive growth investor who seeks maximum capital appreciation and is comfortable with concentrated positions, high volatility, and short-term drawdowns.\n"
        "- Favor momentum-driven breakouts, high-beta stocks, and leveraged positions when technicals and sentiment align. Be willing to recommend 'Buy' or 'Strong Buy' with overweight sizing on high-conviction setups.\n"
        "- Prioritize reward over capital preservation; cash is for the weak. Use aggressive position sizing when the risk/reward ratio exceeds 1:3 and confidence is high.\n"
        "- Short-term trading opportunities are welcome; hold periods of days to weeks are acceptable if the momentum thesis is intact.\n"
    ),
}

def get_persona_instructions(key: str | None) -> str:
    """Return the PM instruction block for ``key`` (empty string if unknown). Always in English for maximum reasoning quality."""
    return _PERSONA_INSTRUCTIONS.get(key or "", "")



def list_personas() -> list[InvestorPersona]:
    return list(_PERSONAS.values())

register_persona(
    InvestorPersona(
        key="conservative",
        label="Conservative",
        description="Capital preservation, dividend income, and focus on low-volatility blue-chip stocks",
        instructions=_PERSONA_INSTRUCTIONS["conservative"],
    )
)

register_persona(
    InvestorPersona(
        key="risk_loving",
        label="Risk Loving",
        description="High returns, momentum, growth, and acceptance of high volatility for crypto",
        instructions=_PERSONA_INSTRUCTIONS["risk_loving"],
    )
)

register_persona(
    InvestorPersona(
        key="esg_focused",
        label="ESG Focused",
        description="Environmental, social, and governance metrics are prioritized alongside financial returns",
        instructions=_PERSONA_INSTRUCTIONS["esg_focused"],
    )
)

register_persona(
    InvestorPersona(
        key="aggressive",
        label="Aggressive",
        description="High-conviction momentum trading, concentrated positions, and maximum growth",
        instructions=_PERSONA_INSTRUCTIONS["aggressive"],
    )
)

