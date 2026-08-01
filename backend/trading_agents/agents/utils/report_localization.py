"""Small, deterministic translations for analysis report scaffolding.

LLMs generate the report body, but a few structured-output renderers add their
own headings *after* generation.  Those headings used to be permanently
English, which produced reports such as a Turkish analysis with ``Action`` and
``Executive Summary`` labels in the middle.  Keep these deterministic labels
separate from model prompting so a provider cannot accidentally undo the
selected output language.

This is deliberately not a general UI i18n system.  It only covers the report
labels and fixed algorithmic chart text emitted by the analysis engine.
"""

from __future__ import annotations

from collections.abc import Iterable

_DEFAULT_LANGUAGE = "english"

def normalize_output_language(language: str | None = None) -> str:
    """Return the configured language as a stable catalog key.

    ``language`` is optional so renderers can be unit-tested without mutating
    run configuration.  Unknown languages safely use the English scaffolding;
    the LLM still receives the configured language instruction separately.
    """
    if language is None:
        try:
            from backend.trading_agents.dataflows.config import get_config

            language = get_config().get("output_language", "English")
        except Exception:
            language = "English"

    normalized = str(language or "English").strip().casefold()
    aliases = {
        "türkçe": "turkish",
        "deutsch": "german",
        "français": "french",
        "español": "spanish",
        "中文": "chinese",
        "日本語": "japanese",
        "العربية": "arabic",
    }
    return aliases.get(normalized, normalized)

_TEXT: dict[str, dict[str, str]] = {
    "english": {
        "recommendation": "Recommendation",
        "research_bias": "Research Bias",
        "rationale": "Rationale",
        "strategic_actions": "Strategic Actions",
        "key_evidence": "Key Evidence",
        "risk_conditions": "Risk Conditions",
        "action": "Action",
        "reasoning": "Reasoning",
        "confidence_score": "Confidence Score",
        "kelly_size": "Kelly Criterion Size",
        "suggested_capital": "Suggested Capital Allocation",
        "entry_price": "Entry Price",
        "stop_loss": "Stop Loss",
        "take_profit": "Take Profit",
        "position_sizing": "Position Sizing",
        "recommended_leverage": "Recommended Leverage",
        "final_transaction_proposal": "Final Transaction Proposal",
        "rating": "Rating",
        "executive_summary": "Executive Summary",
        "investment_thesis": "Investment Thesis",
        "price_target": "Price Target",
        "liquidation_price": "Liquidation Price",
        "time_horizon": "Time Horizon",
        "vision_chart_analysis": "Vision Chart Analysis",
        "algorithmic_pattern_analysis": "Algorithmic Chart Pattern Analysis",
        "no_price_data": "No price data available.",
        "detected_pattern": "Detected Pattern",
        "confidence": "Confidence",
        "consolidation_range": "Consolidation Range",
        "support_levels": "Drawn Support Levels",
        "resistance_levels": "Drawn Resistance Levels",
        "current_price_position": "Current Price Position",
        "testing_upper_range": "testing upper range limit",
        "rectangle_flag": "Rectangle / Flag Consolidation",
        "ascending_channel": "Ascending Price Channel",
        "medium": "Medium",
    },
    "turkish": {
        "recommendation": "Öneri",
        "research_bias": "Araştırma Eğilimi",
        "rationale": "Gerekçe",
        "strategic_actions": "Stratejik Adımlar",
        "key_evidence": "Temel Kanıtlar",
        "risk_conditions": "Risk Koşulları",
        "action": "İşlem",
        "reasoning": "Gerekçe",
        "confidence_score": "Güven Skoru",
        "kelly_size": "Kelly Kriteri Pozisyon Büyüklüğü",
        "suggested_capital": "Önerilen Sermaye Tahsisi",
        "entry_price": "Giriş Fiyatı",
        "stop_loss": "Zarar Durdur",
        "take_profit": "Kâr Al",
        "position_sizing": "Pozisyon Büyüklüğü",
        "recommended_leverage": "Önerilen Kaldıraç",
        "final_transaction_proposal": "Nihai İşlem Önerisi",
        "rating": "Derecelendirme",
        "executive_summary": "Yönetici Özeti",
        "investment_thesis": "Yatırım Tezi",
        "price_target": "Hedef Fiyat",
        "liquidation_price": "Tasfiye Fiyatı",
        "time_horizon": "Zaman Ufku",
        "vision_chart_analysis": "Görsel Grafik Analizi",
        "algorithmic_pattern_analysis": "Algoritmik Grafik Formasyonu Analizi",
        "no_price_data": "Fiyat verisi bulunamadı.",
        "detected_pattern": "Tespit Edilen Formasyon",
        "confidence": "Güven",
        "consolidation_range": "Konsolidasyon Aralığı",
        "support_levels": "Çizilen Destek Seviyeleri",
        "resistance_levels": "Çizilen Direnç Seviyeleri",
        "current_price_position": "Mevcut Fiyat Konumu",
        "testing_upper_range": "üst bant sınırı test ediliyor",
        "rectangle_flag": "Dikdörtgen / Bayrak Konsolidasyonu",
        "ascending_channel": "Yükselen Fiyat Kanalı",
        "medium": "Orta",
    },
    "german": {
        "recommendation": "Empfehlung",
        "research_bias": "Forschungsneigung",
        "rationale": "Begründung",
        "strategic_actions": "Strategische Maßnahmen",
        "key_evidence": "Wesentliche Evidenz",
        "risk_conditions": "Risikobedingungen",
        "action": "Aktion",
        "reasoning": "Begründung",
        "confidence_score": "Konfidenzwert",
        "kelly_size": "Kelly-Kriterium-Positionsgröße",
        "suggested_capital": "Empfohlene Kapitalallokation",
        "entry_price": "Einstiegspreis",
        "stop_loss": "Stop-Loss",
        "take_profit": "Gewinnmitnahme",
        "position_sizing": "Positionsgröße",
        "recommended_leverage": "Empfohlener Hebel",
        "final_transaction_proposal": "Endgültiger Handelsvorschlag",
        "rating": "Bewertung",
        "executive_summary": "Zusammenfassung",
        "investment_thesis": "Anlagethese",
        "price_target": "Kursziel",
        "liquidation_price": "Liquidationspreis",
        "time_horizon": "Zeithorizont",
        "vision_chart_analysis": "Visuelle Chartanalyse",
        "algorithmic_pattern_analysis": "Algorithmische Chartmusteranalyse",
        "no_price_data": "Keine Kursdaten verfügbar.",
        "detected_pattern": "Erkanntes Muster",
        "confidence": "Konfidenz",
        "consolidation_range": "Konsolidierungsspanne",
        "support_levels": "Ermittelte Unterstützungsniveaus",
        "resistance_levels": "Ermittelte Widerstandsniveaus",
        "current_price_position": "Aktuelle Kursposition",
        "testing_upper_range": "testet die obere Begrenzung",
        "rectangle_flag": "Rechteck-/Flaggenkonsolidierung",
        "ascending_channel": "Steigender Preiskanal",
        "medium": "Mittel",
    },
    "french": {
        "recommendation": "Recommandation",
        "research_bias": "Biais de recherche",
        "rationale": "Justification",
        "strategic_actions": "Actions stratégiques",
        "key_evidence": "Éléments probants clés",
        "risk_conditions": "Conditions de risque",
        "action": "Action",
        "reasoning": "Raisonnement",
        "confidence_score": "Score de confiance",
        "kelly_size": "Taille selon le critère de Kelly",
        "suggested_capital": "Allocation de capital suggérée",
        "entry_price": "Prix d'entrée",
        "stop_loss": "Stop-loss",
        "take_profit": "Prise de bénéfices",
        "position_sizing": "Taille de position",
        "recommended_leverage": "Effet de levier recommandé",
        "final_transaction_proposal": "Proposition finale de transaction",
        "rating": "Notation",
        "executive_summary": "Résumé exécutif",
        "investment_thesis": "Thèse d'investissement",
        "price_target": "Objectif de cours",
        "liquidation_price": "Prix de liquidation",
        "time_horizon": "Horizon temporel",
        "vision_chart_analysis": "Analyse graphique visuelle",
        "algorithmic_pattern_analysis": "Analyse algorithmique des figures graphiques",
        "no_price_data": "Aucune donnée de prix disponible.",
        "detected_pattern": "Figure détectée",
        "confidence": "Confiance",
        "consolidation_range": "Fourchette de consolidation",
        "support_levels": "Niveaux de support identifiés",
        "resistance_levels": "Niveaux de résistance identifiés",
        "current_price_position": "Position actuelle du prix",
        "testing_upper_range": "teste la limite supérieure de la fourchette",
        "rectangle_flag": "Consolidation en rectangle / drapeau",
        "ascending_channel": "Canal de prix ascendant",
        "medium": "Moyenne",
    },
    "spanish": {
        "recommendation": "Recomendación",
        "research_bias": "Sesgo de investigación",
        "rationale": "Justificación",
        "strategic_actions": "Acciones estratégicas",
        "key_evidence": "Evidencia clave",
        "risk_conditions": "Condiciones de riesgo",
        "action": "Acción",
        "reasoning": "Razonamiento",
        "confidence_score": "Puntuación de confianza",
        "kelly_size": "Tamaño según el criterio de Kelly",
        "suggested_capital": "Asignación de capital sugerida",
        "entry_price": "Precio de entrada",
        "stop_loss": "Stop loss",
        "take_profit": "Toma de ganancias",
        "position_sizing": "Tamaño de posición",
        "recommended_leverage": "Apalancamiento recomendado",
        "final_transaction_proposal": "Propuesta final de operación",
        "rating": "Calificación",
        "executive_summary": "Resumen ejecutivo",
        "investment_thesis": "Tesis de inversión",
        "price_target": "Precio objetivo",
        "liquidation_price": "Precio de liquidación",
        "time_horizon": "Horizonte temporal",
        "vision_chart_analysis": "Análisis visual del gráfico",
        "algorithmic_pattern_analysis": "Análisis algorítmico de patrones gráficos",
        "no_price_data": "No hay datos de precios disponibles.",
        "detected_pattern": "Patrón detectado",
        "confidence": "Confianza",
        "consolidation_range": "Rango de consolidación",
        "support_levels": "Niveles de soporte identificados",
        "resistance_levels": "Niveles de resistencia identificados",
        "current_price_position": "Posición actual del precio",
        "testing_upper_range": "probando el límite superior del rango",
        "rectangle_flag": "Consolidación en rectángulo / bandera",
        "ascending_channel": "Canal de precio ascendente",
        "medium": "Media",
    },
    "chinese": {
        "recommendation": "建议",
        "research_bias": "研究倾向",
        "rationale": "理由",
        "strategic_actions": "战略行动",
        "key_evidence": "关键证据",
        "risk_conditions": "风险条件",
        "action": "操作",
        "reasoning": "分析依据",
        "confidence_score": "置信评分",
        "kelly_size": "凯利准则仓位",
        "suggested_capital": "建议资金配置",
        "entry_price": "入场价",
        "stop_loss": "止损价",
        "take_profit": "止盈价",
        "position_sizing": "仓位规模",
        "recommended_leverage": "建议杠杆",
        "final_transaction_proposal": "最终交易建议",
        "rating": "评级",
        "executive_summary": "执行摘要",
        "investment_thesis": "投资论点",
        "price_target": "目标价",
        "liquidation_price": "强平价",
        "time_horizon": "时间范围",
        "vision_chart_analysis": "图表视觉分析",
        "algorithmic_pattern_analysis": "算法图表形态分析",
        "no_price_data": "暂无价格数据。",
        "detected_pattern": "检测到的形态",
        "confidence": "置信度",
        "consolidation_range": "盘整区间",
        "support_levels": "识别的支撑位",
        "resistance_levels": "识别的阻力位",
        "current_price_position": "当前价格位置",
        "testing_upper_range": "正在测试区间上沿",
        "rectangle_flag": "矩形 / 旗形盘整",
        "ascending_channel": "上升价格通道",
        "medium": "中等",
    },
    "japanese": {
        "recommendation": "推奨",
        "research_bias": "調査バイアス",
        "rationale": "根拠",
        "strategic_actions": "戦略的アクション",
        "key_evidence": "主要な根拠",
        "risk_conditions": "リスク条件",
        "action": "取引アクション",
        "reasoning": "判断理由",
        "confidence_score": "信頼度スコア",
        "kelly_size": "ケリー基準のポジションサイズ",
        "suggested_capital": "推奨資本配分",
        "entry_price": "エントリー価格",
        "stop_loss": "ストップロス",
        "take_profit": "利確価格",
        "position_sizing": "ポジションサイズ",
        "recommended_leverage": "推奨レバレッジ",
        "final_transaction_proposal": "最終取引提案",
        "rating": "評価",
        "executive_summary": "エグゼクティブサマリー",
        "investment_thesis": "投資仮説",
        "price_target": "目標価格",
        "liquidation_price": "清算価格",
        "time_horizon": "投資期間",
        "vision_chart_analysis": "ビジュアルチャート分析",
        "algorithmic_pattern_analysis": "アルゴリズムによるチャートパターン分析",
        "no_price_data": "価格データがありません。",
        "detected_pattern": "検出されたパターン",
        "confidence": "信頼度",
        "consolidation_range": "保ち合いレンジ",
        "support_levels": "検出されたサポート水準",
        "resistance_levels": "検出されたレジスタンス水準",
        "current_price_position": "現在の価格位置",
        "testing_upper_range": "レンジ上限を試しています",
        "rectangle_flag": "長方形 / フラッグの保ち合い",
        "ascending_channel": "上昇価格チャネル",
        "medium": "中程度",
    },
    "arabic": {
        "recommendation": "التوصية",
        "research_bias": "توجه البحث",
        "rationale": "المبررات",
        "strategic_actions": "الإجراءات الاستراتيجية",
        "key_evidence": "الأدلة الرئيسية",
        "risk_conditions": "شروط المخاطر",
        "action": "الإجراء",
        "reasoning": "المنطق",
        "confidence_score": "درجة الثقة",
        "kelly_size": "حجم معيار كيلي",
        "suggested_capital": "تخصيص رأس المال المقترح",
        "entry_price": "سعر الدخول",
        "stop_loss": "وقف الخسارة",
        "take_profit": "جني الأرباح",
        "position_sizing": "حجم المركز",
        "recommended_leverage": "الرافعة المالية الموصى بها",
        "final_transaction_proposal": "اقتراح التداول النهائي",
        "rating": "التصنيف",
        "executive_summary": "الملخص التنفيذي",
        "investment_thesis": "أطروحة الاستثمار",
        "price_target": "السعر المستهدف",
        "liquidation_price": "سعر التصفية",
        "time_horizon": "الأفق الزمني",
        "vision_chart_analysis": "تحليل الرسم البياني المرئي",
        "algorithmic_pattern_analysis": "تحليل أنماط الرسم البياني الخوارزمي",
        "no_price_data": "لا تتوفر بيانات أسعار.",
        "detected_pattern": "النمط المكتشف",
        "confidence": "الثقة",
        "consolidation_range": "نطاق التماسك",
        "support_levels": "مستويات الدعم المحددة",
        "resistance_levels": "مستويات المقاومة المحددة",
        "current_price_position": "موضع السعر الحالي",
        "testing_upper_range": "يختبر الحد العلوي للنطاق",
        "rectangle_flag": "تماسك مستطيل / علم",
        "ascending_channel": "قناة سعرية صاعدة",
        "medium": "متوسطة",
    },
}

_RATINGS: dict[str, dict[str, str]] = {
    "english": {},
    "turkish": {
        "Buy": "Al",
        "Overweight": "Ağırlığı Artır",
        "Hold": "Tut",
        "Underweight": "Ağırlığı Azalt",
        "Sell": "Sat",
    },
    "german": {
        "Buy": "Kaufen",
        "Overweight": "Übergewichten",
        "Hold": "Halten",
        "Underweight": "Untergewichten",
        "Sell": "Verkaufen",
    },
    "french": {
        "Buy": "Acheter",
        "Overweight": "Surpondérer",
        "Hold": "Conserver",
        "Underweight": "Sous-pondérer",
        "Sell": "Vendre",
    },
    "spanish": {
        "Buy": "Comprar",
        "Overweight": "Sobreponderar",
        "Hold": "Mantener",
        "Underweight": "Infraponderar",
        "Sell": "Vender",
    },
    "chinese": {
        "Buy": "买入",
        "Overweight": "增持",
        "Hold": "持有",
        "Underweight": "减持",
        "Sell": "卖出",
    },
    "japanese": {
        "Buy": "買い",
        "Overweight": "オーバーウェイト",
        "Hold": "ホールド",
        "Underweight": "アンダーウェイト",
        "Sell": "売り",
    },
    "arabic": {
        "Buy": "شراء",
        "Overweight": "زيادة الوزن",
        "Hold": "احتفاظ",
        "Underweight": "خفض الوزن",
        "Sell": "بيع",
    },
}

_RESEARCH_BIASES: dict[str, dict[str, str]] = {
    "english": {},
    "turkish": {"Bullish": "Olumlu", "Neutral": "Nötr", "Bearish": "Olumsuz"},
    "german": {"Bullish": "Positiv", "Neutral": "Neutral", "Bearish": "Negativ"},
    "french": {"Bullish": "Haussier", "Neutral": "Neutre", "Bearish": "Baissier"},
    "spanish": {"Bullish": "Alcista", "Neutral": "Neutral", "Bearish": "Bajista"},
    "chinese": {"Bullish": "看涨", "Neutral": "中性", "Bearish": "看跌"},
    "japanese": {"Bullish": "強気", "Neutral": "中立", "Bearish": "弱気"},
    "arabic": {"Bullish": "إيجابي", "Neutral": "محايد", "Bearish": "سلبي"},
}

def report_text(key: str, language: str | None = None) -> str:
    """Return a localized, fixed report label for *key*."""
    lang = normalize_output_language(language)
    return _TEXT.get(lang, _TEXT[_DEFAULT_LANGUAGE]).get(key, _TEXT[_DEFAULT_LANGUAGE].get(key, key))

def report_rating(value: str, language: str | None = None) -> str:
    """Return a display translation of a canonical structured rating/action."""
    lang = normalize_output_language(language)
    return _RATINGS.get(lang, {}).get(value, value)

def report_bias(value: str, language: str | None = None) -> str:
    """Return a display translation for non-executable research posture."""
    lang = normalize_output_language(language)
    return _RESEARCH_BIASES.get(lang, {}).get(value, value)

def executive_summary_headings() -> tuple[str, ...]:
    """Known localized executive-summary headings for prompt compaction."""
    return tuple(
        dict.fromkeys(values["executive_summary"] for values in _TEXT.values() if "executive_summary" in values)
    )

def report_texts(keys: Iterable[str], language: str | None = None) -> dict[str, str]:
    """Fetch a small group of labels with one language resolution."""
    lang = normalize_output_language(language)
    return {key: report_text(key, lang) for key in keys}
