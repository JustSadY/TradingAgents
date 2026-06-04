from __future__ import annotations
def _node_specs() -> dict:
    try:
        from backend.trading_agents.graph.analyst_execution import ANALYST_NODE_SPECS
        return ANALYST_NODE_SPECS
    except Exception:
        return {}
_ANALYST_META: dict[str, tuple[str, str, bool]] = {
    "market":       ("Piyasa",      "Teknik göstergeler, fiyat trendi ve momentum",      True),
    "social":       ("Duygu",       "Sosyal medya, StockTwits ve Reddit duygu analizi",  True),
    "news":         ("Haber",       "Şirkete özel ve sektörel haber akışı",              True),
    "fundamentals": ("Temel",       "Bilanço, gelir tablosu ve değerleme",               True),
    "macro":        ("Makro",       "Faiz, enflasyon ve genel ekonomik görünüm",         False),
    "options":      ("Opsiyon",     "Opsiyon zinciri, implied volatility ve akış",       False),
    "quant":        ("Kantitatif",  "İstatistiksel faktör ve nicel sinyaller",           False),
    "earnings":     ("Kazanç",      "Kazanç çağrıları, tahminler ve sürprizler",         False),
    "review":       ("İnceleme",    "Geçmiş kararların performans incelemesi",           False),
}
def available_analysts() -> list[dict]:
    specs = _node_specs()
    out: list[dict] = []
    for key, (label, desc, default) in _ANALYST_META.items():
        if not specs or key in specs:
            out.append({"key": key, "label": label, "description": desc, "default": default})
    return out
def _analyst_label(key: str) -> str:
    meta = _ANALYST_META.get(key)
    return meta[0] if meta else key.title()
SECTION_LABELS: dict[str, str] = {
    "market_report":             "Piyasa Analizi",
    "sentiment_report":          "Duygu Analizi",
    "news_report":               "Haber Analizi",
    "fundamentals_report":       "Temel Analiz",
    "macro_report":              "Makro Analiz",
    "options_report":            "Opsiyon Analizi",
    "quant_report":              "Kantitatif Analiz",
    "earnings_report":           "Kazanç Analizi",
    "review_report":             "Performans İnceleme",
    "investment_plan":           "Yatırım Planı",
    "trader_investment_plan":    "Trader Planı",
    "trader_plan":               "Trader Planı",
    "final_trade_decision":      "PM Kararı",
    "final_decision":            "PM Kararı",
    "bull_history":              "Boğa Argümanları",
    "bear_history":              "Ayı Argümanları",
    "investment_debate_history": "Tartışma",
    "risk_debate_history":       "Risk Tartışması",
    "judge_decision":            "Hakem Kararı",
}
SIGNALS: list[dict] = [
    {"value": "Buy",         "label": "Al",    "tone": "positive"},
    {"value": "Overweight",  "label": "Artır", "tone": "positive"},
    {"value": "Hold",        "label": "Tut",   "tone": "neutral"},
    {"value": "Underweight", "label": "Azalt", "tone": "negative"},
    {"value": "Sell",        "label": "Sat",   "tone": "negative"},
]
ASSET_TYPES: list[dict] = [
    {"value": "stock",  "label": "Hisse"},
    {"value": "crypto", "label": "Kripto"},
]
LANGUAGES: list[dict] = [
    {"value": "English",  "label": "English"},
    {"value": "Turkish",  "label": "Türkçe"},
    {"value": "German",   "label": "Deutsch"},
    {"value": "French",   "label": "Français"},
    {"value": "Spanish",  "label": "Español"},
    {"value": "Chinese",  "label": "中文"},
    {"value": "Japanese", "label": "日本語"},
    {"value": "Arabic",   "label": "العربية"},
]
DATA_VENDORS: list[dict] = [
    {"value": "yfinance",      "label": "yFinance"},
    {"value": "alpha_vantage", "label": "Alpha Vantage"},
]
TRADING_MODES: list[dict] = [
    {"value": "simulation", "label": "Simülasyon (Paper Trading)"},
    {"value": "live",       "label": "Canlı (Live)"},
]
BROKERS: list[dict] = [
    {"value": "simulation", "label": "Simülasyon"},
]
PROVIDER_LABELS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "google": "Google (Gemini)",
    "xai": "xAI (Grok)",
    "deepseek": "DeepSeek",
    "qwen": "Qwen (Global)",
    "qwen-cn": "Qwen (China)",
    "glm": "GLM / Z.AI (Global)",
    "glm-cn": "GLM / BigModel (China)",
    "minimax": "MiniMax (Global)",
    "minimax-cn": "MiniMax (China)",
    "ollama": "Ollama (Local)",
    "nvidia": "NVIDIA NIM",
    "litellm": "LiteLLM Proxy",
    "azure": "Azure OpenAI",
}
def build_meta() -> dict:
    return {
        "analysts": available_analysts(),
        "section_labels": SECTION_LABELS,
        "signals": SIGNALS,
        "asset_types": ASSET_TYPES,
        "languages": LANGUAGES,
        "data_vendors": DATA_VENDORS,
        "trading_modes": TRADING_MODES,
        "brokers": BROKERS,
        "provider_labels": PROVIDER_LABELS,
    }
_STATIC_NODE_LABELS: dict[str, tuple[str, str]] = {
    "Bull Researcher":     ("Boğa Araştırmacısı", "research"),
    "Bear Researcher":     ("Ayı Araştırmacısı", "research"),
    "Research Manager":    ("Araştırma Müdürü — yatırım planı", "research"),
    "Trader":              ("Trader — işlem planı", "trade"),
    "Aggressive Analyst":  ("Agresif Risk Analisti", "risk"),
    "Conservative Analyst": ("Muhafazakâr Risk Analisti", "risk"),
    "Neutral Analyst":     ("Nötr Risk Analisti", "risk"),
    "Portfolio Manager":   ("Portföy Yöneticisi — nihai karar", "decision"),
}
_ANALYST_NODE_LABELS: dict[str, tuple[str, str]] | None = None
def _analyst_node_labels() -> dict[str, tuple[str, str]]:
    global _ANALYST_NODE_LABELS
    if _ANALYST_NODE_LABELS is None:
        mapping: dict[str, tuple[str, str]] = {}
        for key, spec in _node_specs().items():
            label = _analyst_label(key)
            mapping[spec.agent_node] = (f"{label} Analisti", "analyst")
            mapping[spec.tool_node] = (f"{label} — veri çekiliyor", "tool")
        _ANALYST_NODE_LABELS = mapping
    return _ANALYST_NODE_LABELS
def node_progress(node_name: str) -> dict | None:
    hit = _analyst_node_labels().get(node_name) or _STATIC_NODE_LABELS.get(node_name)
    if hit is None:
        return None
    label, stage = hit
    return {"type": "progress", "node": node_name, "label": label, "stage": stage}
