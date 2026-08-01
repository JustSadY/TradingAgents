from typing import Any

MESSAGES = {
    "insufficient_funds": {
        "en": "Insufficient funds. Required: ${required:.2f}, Available: ${available:.2f}",
        "tr": "Yetersiz bakiye. Gerekli: ${required:.2f}, Mevcut: ${available:.2f}",
    },
    "insufficient_position": {
        "en": "Insufficient position. Available: {available:.4f}, Requested to sell: {requested:.4f}",
        "tr": "Yetersiz pozisyon. Mevcut: {available:.4f}, Satılmak istenen: {requested:.4f}",
    },
    "portfolio_reset": {
        "en": "Portfolio reset",
        "tr": "Portföy sıfırlandı",
    },
    "invalid_price": {
        "en": "Could not fetch valid price for {ticker}",
        "tr": "{ticker} için geçerli fiyat alınamadı",
    },
    "invalid_action": {
        "en": "Action must be BUY or SELL",
        "tr": "İşlem AL veya SAT olmalıdır",
    },
}

def get_message(key: str, lang: str = "English", **kwargs: Any) -> str:
    lang_code = "tr" if (lang or "").lower() in ("turkish", "türkçe") else "en"
    msg_dict = MESSAGES.get(key, {})
    template = msg_dict.get(lang_code, msg_dict.get("en", key))
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
