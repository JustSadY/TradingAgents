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
    instructions: str  # injected verbatim into the Portfolio Manager prompt


_PERSONAS: dict[str, InvestorPersona] = {}


def register_persona(persona: InvestorPersona) -> None:
    _PERSONAS[persona.key] = persona


def get_persona(key: str | None) -> InvestorPersona | None:
    return _PERSONAS.get(key or "")


def get_persona_instructions(key: str | None) -> str:
    """Return the PM instruction block for ``key`` (empty string if unknown)."""
    persona = _PERSONAS.get(key or "")
    return persona.instructions if persona else ""


def list_personas() -> list[InvestorPersona]:
    return list(_PERSONAS.values())


# --- Built-in personas (instruction text preserved verbatim from the PM) -------

register_persona(InvestorPersona(
    key="conservative",
    label="Muhafazakâr",
    description="Sermaye koruma, temettü ve düşük volatiliteli blue-chip odaklı",
    instructions=(
        "**INVESTOR PERSONA: Conservative Dividend Investor (Muhafazakar)**\n"
        "- Your client is highly risk-averse, focusing on capital preservation, steady income (dividends), and low-volatility blue-chip assets.\n"
        "- Prefer 'Hold' or 'Sell/Underweight' if uncertainty is high. Do not recommend aggressive positioning, high leverage, or speculative assets unless backed by overwhelming positive fundamental data.\n"
        "- Keep position sizing conservative, prioritizing cash safety.\n"
    ),
))

register_persona(InvestorPersona(
    key="risk_loving",
    label="Risk Sever",
    description="Yüksek getiri, momentum, büyüme ve kripto için yüksek volatilite kabulü",
    instructions=(
        "**INVESTOR PERSONA: Risk-Loving Crypto & Growth Trader (Risk Sever)**\n"
        "- Your client seeks high returns and is willing to accept high volatility, leverage, and speculative growth or crypto assets.\n"
        "- Emphasize growth potential and momentum. Be willing to recommend 'Buy' or 'Overweight' sizing if there is a strong technical breakout or high social sentiment, even if fundamentals are weak or debate is mixed.\n"
    ),
))

register_persona(InvestorPersona(
    key="esg_focused",
    label="ESG Odaklı",
    description="Çevre, sosyal ve yönetişim metrikleri finansal getiriyle birlikte önceliklendirilir",
    instructions=(
        "**INVESTOR PERSONA: Sustainability / ESG-Focused Investor (ESG Odaklı)**\n"
        "- Your client prioritizes environmental, social, and corporate governance metrics alongside financial returns.\n"
        "- Strictly penalize companies with controversial environmental track records, poor corporate governance, or regulatory issues. Heavily favor clean energy, positive social governance, and sustainable business models.\n"
    ),
))
