import json
import logging

_logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_EN = """You are a financial analyst assistant. Extract numerical price levels from the provided analysis report and respond ONLY in the following JSON format, do not write anything else:
{
  "support_levels": [number, number],
  "resistance_levels": [number, number],
  "target_price": number_or_null,
  "stop_loss": number_or_null,
  "leverage": number_or_null,
  "liquidation_price": number_or_null,
  "key_levels": [
    {"price": number, "label": "short_description", "type": "ma|indicator|other"}
  ]
}
Rules:
- Extract at most 4-5 support and resistance levels.
- Prices might be rounded — show clean values close to integers.
- Use null for missing or ambiguous values.
- leverage: the recommended leverage multiplier if the report states one (e.g. "3x" -> 3), else null.
- liquidation_price: the price at which a leveraged long would be liquidated if stated, else null.
- key_levels: list technical levels like moving average, Bollinger bands, etc. (max 4).
- Use only numerical values explicitly mentioned in the report, do not estimate or extrapolate."""

_LANG_PREFIXES: dict[str, str] = {
    "turkish": "Please respond in Turkish.\n\n",
    "türkçe": "Lütfen Türkçe yanıtla.\n\n",
}

async def extract_chart_annotations(
    market_report: str,
    final_decision: str,
    quick_llm,
    output_language: str = "English",
) -> dict:
    if not market_report and not final_decision:
        return {}

    lang = (output_language or "English").strip().lower()
    prefix = _LANG_PREFIXES.get(lang, "")
    system_prompt = prefix + _SYSTEM_PROMPT_EN

    text = f"PIYASA RAPORU:\n{market_report}\n\nSON KARAR:\n{final_decision}"
    try:
        response = await _call_llm_async(quick_llm, text, system_prompt)
        raw = response.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        data = json.loads(raw)
        return _validate_annotations(data)
    except Exception as exc:
        _logger.warning("Annotation extraction failed (non-fatal): %s", exc)
        return {}

async def _call_llm_async(llm, text: str, system_prompt: str) -> str:
    import asyncio

    from langchain_core.messages import HumanMessage, SystemMessage

    def _sync_call():
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=text),
        ]
        result = llm.invoke(messages)
        return result.content if hasattr(result, "content") else str(result)

    return await asyncio.to_thread(_sync_call)

def _validate_annotations(data: dict) -> dict:
    def _floats(lst) -> list[float]:
        if not isinstance(lst, list):
            return []
        return [round(float(x), 2) for x in lst if isinstance(x, (int, float)) and x > 0]

    def _float_or_none(val):
        try:
            v = float(val)
            return round(v, 2) if v > 0 else None
        except (TypeError, ValueError):
            return None

    key_levels = []
    for kl in data.get("key_levels") or []:
        if isinstance(kl, dict) and isinstance(kl.get("price"), (int, float)):
            key_levels.append(
                {
                    "price": round(float(kl["price"]), 2),
                    "label": str(kl.get("label", ""))[:40],
                    "type": str(kl.get("type", "other")),
                }
            )

    def _leverage_or_none(val):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return None
        return round(min(v, 10.0), 1) if v > 1.0 else None

    return {
        "support_levels": _floats(data.get("support_levels")),
        "resistance_levels": _floats(data.get("resistance_levels")),
        "target_price": _float_or_none(data.get("target_price")),
        "stop_loss": _float_or_none(data.get("stop_loss")),
        "leverage": _leverage_or_none(data.get("leverage")),
        "liquidation_price": _float_or_none(data.get("liquidation_price")),
        "key_levels": key_levels[:4],
    }
