export interface ReportSection {
  key: string
  /** i18n key for the in-app label. */
  labelKey: string
  fallbackLabel: string
  category: 'decision' | 'analyst' | 'research'
  kind?: 'text' | 'structured' | 'debates' | 'portfolioDecision'
  /** Rendered on the public share page. */
  shareable: boolean
  /**
   * i18n key for the heading in a downloaded document, when the section is
   * exported at all. Export headings are deliberately more qualified than
   * the in-app ones because a document has no surrounding UI for context.
   */
  exportLabelKey?: string
  /** Position in a downloaded document, which is not the share-page order. */
  exportOrder?: number
}

/**
 * Every report section, once.
 *
 * Array order is the share-page order, where the Portfolio Manager decision
 * leads because it is what the page opens on. Documents order by
 * `exportOrder` instead, which groups the decision fields first and the
 * debate histories last.
 *
 * This metadata previously lived in three places: SharedReport held keys,
 * icons and categories, exportReport held its own key order plus a hardcoded
 * EN/TR label table, and neither knew about the other.
 */
export const REPORT_SECTIONS: ReportSection[] = [
  { key: 'portfolio_decision', labelKey: 'analysis.pm.title', fallbackLabel: 'Portfolio Manager Recommendation', category: 'decision', kind: 'portfolioDecision', shareable: true },
  { key: 'final_decision', labelKey: 'analysis.section.final_trade_decision', fallbackLabel: 'Final Decision', category: 'decision', shareable: true, exportLabelKey: 'export.section.final_decision', exportOrder: 0 },
  { key: 'investment_plan', labelKey: 'analysis.section.investment_plan', fallbackLabel: 'Research Evidence Summary', category: 'decision', shareable: true, exportLabelKey: 'export.section.investment_plan', exportOrder: 1 },
  { key: 'trader_plan', labelKey: 'analysis.section.trader_investment_plan', fallbackLabel: 'Legacy Trader Proposal', category: 'decision', shareable: true, exportLabelKey: 'export.section.trader_plan', exportOrder: 2 },
  { key: 'judge_decision', labelKey: 'analysis.section.judge_decision', fallbackLabel: 'Judge Decision', category: 'decision', shareable: true, exportLabelKey: 'export.section.judge_decision', exportOrder: 25 },
  { key: 'trader_proposal_json', labelKey: 'analysis.section.trader_proposal_json', fallbackLabel: 'Legacy Trade Proposal Details', category: 'decision', kind: 'structured', shareable: true },
  { key: 'market_report', labelKey: 'analysis.section.market_report', fallbackLabel: 'Market Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.market_report', exportOrder: 3 },
  { key: 'fundamentals_report', labelKey: 'analysis.section.fundamentals_report', fallbackLabel: 'Fundamental Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.fundamentals_report', exportOrder: 4 },
  { key: 'news_report', labelKey: 'analysis.section.news_report', fallbackLabel: 'News Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.news_report', exportOrder: 5 },
  { key: 'sentiment_report', labelKey: 'analysis.section.sentiment_report', fallbackLabel: 'Sentiment Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.sentiment_report', exportOrder: 6 },
  { key: 'macro_report', labelKey: 'analysis.section.macro_report', fallbackLabel: 'Macro Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.macro_report', exportOrder: 7 },
  { key: 'options_report', labelKey: 'analysis.section.options_report', fallbackLabel: 'Options Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.options_report', exportOrder: 8 },
  { key: 'quant_report', labelKey: 'analysis.section.quant_report', fallbackLabel: 'Quantitative Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.quant_report', exportOrder: 9 },
  { key: 'earnings_report', labelKey: 'analysis.section.earnings_report', fallbackLabel: 'Earnings Analysis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.earnings_report', exportOrder: 10 },
  { key: 'insider_report', labelKey: 'analysis.section.insider_report', fallbackLabel: 'Insider Activity', category: 'analyst', shareable: true, exportLabelKey: 'export.section.insider_report', exportOrder: 11 },
  { key: 'ownership_report', labelKey: 'analysis.section.ownership_report', fallbackLabel: 'Institutional Ownership', category: 'analyst', shareable: true, exportLabelKey: 'export.section.ownership_report', exportOrder: 12 },
  { key: 'ratings_report', labelKey: 'analysis.section.ratings_report', fallbackLabel: 'Analyst Ratings', category: 'analyst', shareable: true, exportLabelKey: 'export.section.ratings_report', exportOrder: 13 },
  { key: 'short_interest_report', labelKey: 'analysis.section.short_interest_report', fallbackLabel: 'Short Interest', category: 'analyst', shareable: true, exportLabelKey: 'export.section.short_interest_report', exportOrder: 14 },
  { key: 'valuation_report', labelKey: 'analysis.section.valuation_report', fallbackLabel: 'Valuation Comparison', category: 'analyst', shareable: true, exportLabelKey: 'export.section.valuation_report', exportOrder: 15 },
  { key: 'catalyst_report', labelKey: 'analysis.section.catalyst_report', fallbackLabel: 'Upcoming Catalysts', category: 'analyst', shareable: true, exportLabelKey: 'export.section.catalyst_report', exportOrder: 16 },
  { key: 'review_report', labelKey: 'analysis.section.review_report', fallbackLabel: 'Performance Review', category: 'analyst', shareable: true, exportLabelKey: 'export.section.review_report', exportOrder: 17 },
  { key: 'synthesis_report', labelKey: 'analysis.section.synthesis_report', fallbackLabel: 'Synthesis', category: 'analyst', shareable: true, exportLabelKey: 'export.section.synthesis_report', exportOrder: 18 },
  { key: 'audit_report', labelKey: 'analysis.section.audit_report', fallbackLabel: 'Audit', category: 'analyst', shareable: true, exportLabelKey: 'export.section.audit_report', exportOrder: 19 },
  { key: 'agent_qa_report', labelKey: 'analysis.section.agent_qa_report', fallbackLabel: 'Cross-Examination', category: 'analyst', shareable: true, exportLabelKey: 'export.section.agent_qa_report', exportOrder: 20 },
  { key: 'bull_history', labelKey: 'analysis.section.bull_history', fallbackLabel: 'Bull Arguments', category: 'research', kind: 'structured', shareable: true, exportLabelKey: 'export.section.bull_history', exportOrder: 21 },
  { key: 'bear_history', labelKey: 'analysis.section.bear_history', fallbackLabel: 'Bear Arguments', category: 'research', kind: 'structured', shareable: true, exportLabelKey: 'export.section.bear_history', exportOrder: 22 },
  { key: 'debates', labelKey: 'analysis.section.investment_debate_history', fallbackLabel: 'Consensus & Risk Debate', category: 'research', kind: 'debates', shareable: true },
  { key: 'risk_metrics', labelKey: 'analysis.section.risk_metrics', fallbackLabel: 'Risk Metrics', category: 'research', kind: 'structured', shareable: true },

  // Export only: the raw debate histories the share page shows combined.
  { key: 'investment_debate_history', labelKey: 'analysis.section.investment_debate_history', fallbackLabel: 'Investment Debate', category: 'research', shareable: false, exportLabelKey: 'export.section.investment_debate_history', exportOrder: 23 },
  { key: 'risk_debate_history', labelKey: 'analysis.section.risk_debate_history', fallbackLabel: 'Risk Debate', category: 'research', shareable: false, exportLabelKey: 'export.section.risk_debate_history', exportOrder: 24 },
]
