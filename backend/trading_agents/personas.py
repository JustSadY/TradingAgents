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


_INSTRUCTIONS_EN = {
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
}

_INSTRUCTIONS_TR = {
    "conservative": (
        "**INVESTOR PERSONA: Muhafazakar Temettü Yatırımcısı**\n"
        "- Müşteriniz riskten son derece kaçınır; anaparanın korunmasına, düzenli gelire (temettü) ve düşük oynaklıklı mavi çipli varlıklara odaklanır.\n"
        "- Belirsizlik yüksekse 'Tut' veya 'Sat/Ağırlık Azalt' seçeneğini tercih edin. Ezici ölçüde olumlu temel verilerle desteklenmediği sürece agresif pozisyon alma, yüksek kaldıraç veya spekülatif varlıklar önermeyin.\n"
        "- Nakit güvenliğini ön planda tutarak pozisyon büyüklüğünü muhafazakar tutun.\n"
    ),
    "risk_loving": (
        "**INVESTOR PERSONA: Risk Sever Kripto ve Büyüme Yatırımcısı**\n"
        "- Müşteriniz yüksek getiri hedefler ve yüksek oynaklığı, kaldıracı, spekülatif büyüme veya kripto varlıkları kabul etmeye isteklidir.\n"
        "- Büyüme potansiyelini ve ivmeyi vurgulayın. Temeller zayıf veya tartışmalar karışık olsa bile, güçlü bir teknik kırılma veya yüksek sosyal duyarlılık varsa 'Al' veya 'Ağırlık Artır' önerisi yapmaya istekli olun.\n"
    ),
    "esg_focused": (
        "**INVESTOR PERSONA: Sürdürülebilirlik / ESG Odaklı Yatırımcı**\n"
        "- Müşteriniz finansal getirilerin yanı sıra çevresel, sosyal ve kurumsal yönetim metriklerine öncelik verir.\n"
        "- Tartışmalı çevre geçmişine, zayıf kurumsal yönetime veya düzenleyici sorunlara sahip şirketleri kesinlikle cezalandırın. Temiz enerjiyi, olumlu sosyal yönetimi ve sürdürülebilir iş modellerini yoğun bir şekilde destekleyin.\n"
    ),
}


def get_persona_instructions(key: str | None) -> str:
    """Return the PM instruction block for ``key`` (empty string if unknown)."""
    key = key or ""
    try:
        from backend.trading_agents.dataflows.config import get_config
        lang = get_config().get("output_language", "English").strip().lower()
    except Exception:
        lang = "english"
    
    is_tr = lang in ("turkish", "türkçe")
    if is_tr:
        return _INSTRUCTIONS_TR.get(key, "")
    return _INSTRUCTIONS_EN.get(key, "")


def list_personas() -> list[InvestorPersona]:
    return list(_PERSONAS.values())


# --- Built-in personas (instruction text preserved verbatim from the PM) -------

register_persona(InvestorPersona(
    key="conservative",
    label="Conservative",
    description="Capital preservation, dividend income, and focus on low-volatility blue-chip stocks",
    instructions=_INSTRUCTIONS_EN["conservative"],
))

register_persona(InvestorPersona(
    key="risk_loving",
    label="Risk Loving",
    description="High returns, momentum, growth, and acceptance of high volatility for crypto",
    instructions=_INSTRUCTIONS_EN["risk_loving"],
))

register_persona(InvestorPersona(
    key="esg_focused",
    label="ESG Focused",
    description="Environmental, social, and governance metrics are prioritized alongside financial returns",
    instructions=_INSTRUCTIONS_EN["esg_focused"],
))
