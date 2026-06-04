"""Analyst catalog — the single source of truth for selectable analysts.

Each analyst's UI/selection metadata (key, localized label, description, and
whether it is enabled by default) is declared once here. The backend's
``/api/meta`` derives the analyst list from this module so the frontend never
hardcodes it, and the engine graph wiring keys off the same ``key`` values.

Like ``personas.py`` this module is dependency-free and lives at the engine root
so the backend can import it without triggering the heavy ``agents`` package.
Structural wiring (graph nodes, tools, report column) stays with each analyst's
``@register_analyst`` declaration; this catalog is the selection/presentation
metadata.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystInfo:
    key: str
    label: str
    description: str
    default_on: bool


ANALYSTS: list[AnalystInfo] = [
    AnalystInfo("market",       "Piyasa",     "Teknik göstergeler, fiyat trendi ve momentum",     True),
    AnalystInfo("social",       "Duygu",      "Sosyal medya, StockTwits ve Reddit duygu analizi", True),
    AnalystInfo("news",         "Haber",      "Şirkete özel ve sektörel haber akışı",             True),
    AnalystInfo("fundamentals", "Temel",      "Bilanço, gelir tablosu ve değerleme",              True),
    AnalystInfo("macro",        "Makro",      "Faiz, enflasyon ve genel ekonomik görünüm",        False),
    AnalystInfo("options",      "Opsiyon",    "Opsiyon zinciri, implied volatility ve akış",      False),
    AnalystInfo("quant",        "Kantitatif", "İstatistiksel faktör ve nicel sinyaller",          False),
    AnalystInfo("earnings",     "Kazanç",     "Kazanç çağrıları, tahminler ve sürprizler",        False),
    AnalystInfo("review",       "İnceleme",   "Geçmiş kararların performans incelemesi",          False),
]

_BY_KEY = {a.key: a for a in ANALYSTS}


def list_analysts() -> list[AnalystInfo]:
    return list(ANALYSTS)


def get_analyst(key: str) -> AnalystInfo | None:
    return _BY_KEY.get(key)


def label_for(key: str) -> str:
    info = _BY_KEY.get(key)
    return info.label if info else key.title()
