// Section headings for downloaded reports.
//
// Kept separate from the in-app `analysis.section.*` labels on purpose: a
// standalone document has no surrounding UI, so several headings carry a
// qualifier the app does not need — "Final Decision (Portfolio Manager)"
// rather than just "Final Decision". These strings are the ones the export
// already produced; they moved here so a third language reaches them too.
const exportSections = {
  en: {
    'export.section.final_decision': 'Final Decision (Portfolio Manager)',
    'export.section.investment_plan': 'Research Evidence Summary',
    'export.section.market_report': 'Market Analysis',
    'export.section.fundamentals_report': 'Fundamentals',
    'export.section.news_report': 'News Analysis',
    'export.section.sentiment_report': 'Sentiment Analysis',
    'export.section.macro_report': 'Macro Analysis',
    'export.section.options_report': 'Options Analysis',
    'export.section.quant_report': 'Quantitative Analysis',
    'export.section.earnings_report': 'Earnings Analysis',
    'export.section.insider_report': 'Insider Activity',
    'export.section.ownership_report': 'Institutional Ownership',
    'export.section.ratings_report': 'Analyst Ratings',
    'export.section.short_interest_report': 'Short Interest',
    'export.section.valuation_report': 'Valuation Comparison',
    'export.section.catalyst_report': 'Upcoming Catalysts',
    'export.section.review_report': 'Review',
    'export.section.synthesis_report': 'Synthesis',
    'export.section.audit_report': 'Audit',
    'export.section.agent_qa_report': 'Agent Cross-Examination',
    'export.section.bull_history': 'Bull Arguments',
    'export.section.bear_history': 'Bear Arguments',
    'export.section.investment_debate_history': 'Investment Debate',
    'export.section.risk_debate_history': 'Risk Debate',
  },
  tr: {
    'export.section.final_decision': 'Nihai Karar (Portfolio Manager)',
    'export.section.investment_plan': 'Araştırma Kanıt Özeti',
    'export.section.market_report': 'Piyasa Analizi',
    'export.section.fundamentals_report': 'Temel Analiz',
    'export.section.news_report': 'Haber Analizi',
    'export.section.sentiment_report': 'Duygu Analizi',
    'export.section.macro_report': 'Makro Analiz',
    'export.section.options_report': 'Opsiyon Analizi',
    'export.section.quant_report': 'Kantitatif Analiz',
    'export.section.earnings_report': 'Kazanç Analizi',
    'export.section.insider_report': 'İçeriden İşlem',
    'export.section.ownership_report': 'Kurumsal Sahiplik',
    'export.section.ratings_report': 'Analist Tavsiyeleri',
    'export.section.short_interest_report': 'Açığa Satış',
    'export.section.valuation_report': 'Değerleme Karşılaştırması',
    'export.section.catalyst_report': 'Yaklaşan Katalizörler',
    'export.section.review_report': 'Performans İnceleme',
    'export.section.synthesis_report': 'Sentez',
    'export.section.audit_report': 'Denetim',
    'export.section.agent_qa_report': 'Ajan Çapraz Sorgu',
    'export.section.bull_history': 'Boğa Argümanları',
    'export.section.bear_history': 'Ayı Argümanları',
    'export.section.investment_debate_history': 'Yatırım Tartışması',
    'export.section.risk_debate_history': 'Risk Tartışması',
  },
}

export default exportSections