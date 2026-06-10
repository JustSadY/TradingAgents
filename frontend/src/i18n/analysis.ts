const analysis = {
  en: {

    'analysis.title': 'Analysis',


    'analysis.tab.single': 'Single Stock',
    'analysis.tab.multi': 'Multi Stock',
    'analysis.tab.history': 'History',


    'analysis.label.symbol': 'Symbol',
    'analysis.label.date': 'Date',
    'analysis.label.type': 'Type',


    'analysis.btn.start': 'Start Analysis',
    'analysis.btn.stop': 'Stop',
    'analysis.btn.rerun': 'Re-run',
    'analysis.btn.cancel': 'Cancel',


    'analysis.cost_estimate': 'Estimated cost: ~$',
    'analysis.existing_analysis': '⚠ There is a saved analysis for this date — you will re-run it',
    'analysis.running': 'analyzing',


    'analysis.rerun.title': 'Existing Analysis Found',
    'analysis.rerun.body': 'An analysis for {ticker} on {date} already exists. A new analysis will consume more API credits.',


    'analysis.log.title': 'Live Log',
    'analysis.log.lines': 'lines',


    'analysis.reports.title': 'Reports',
    'analysis.reports.sections': 'sections',
    'analysis.reports.empty': 'Reports will appear here during analysis.',


    'analysis.report_card.show': 'Show',
    'analysis.report_card.hide': 'Hide',


    'analysis.ws.complete': '— Completed',
    'analysis.ws.llm_calls': 'LLM calls',
    'analysis.ws.error_prefix': '✗ ERROR:',
    'analysis.ws.conn_error': '✗ Connection error.',
    'analysis.ws.conn_closed_reconnect': '— Analysis completed or connection dropped. Check the History tab.',
    'analysis.ws.conn_closed': 'Connection closed — backend error or LLM API key may be missing.',
    'analysis.ws.stopped': '— Analysis stopped.',
    'analysis.ws.failed_to_start': 'Failed to start',
    'analysis.ws.analysis_error_title': 'Analysis Error',
    'analysis.ws.analysis_failed': 'Analysis failed.',
    'analysis.ws.analysis_interrupted': 'Analysis Interrupted',
    'analysis.ws.analysis_complete_notif': 'analysis completed',
    'analysis.ws.signal_label': 'Signal:',


    'analysis.multi.description': 'At least 2, at most 10 stocks. SuperPortfolioManager analyzes all stocks and recommends portfolio allocation.',
    'analysis.multi.label_symbols': 'Symbols',
    'analysis.multi.btn_start': 'Start Portfolio Analysis',
    'analysis.multi.running': 'Running...',
    'analysis.multi.started': 'Started in the background — you can track it from the "Portfolio History" tab.',
    'analysis.multi.error_default': 'Portfolio analysis could not be started.',


    'analysis.portfolio_history.title': 'Portfolio Analysis History',
    'analysis.portfolio_history.loading': 'Loading...',
    'analysis.portfolio_history.empty': 'No portfolio analyses yet.',
    'analysis.portfolio_history.report_not_ready': 'Report not ready yet.',


    'analysis.history.loading': 'Loading...',
    'analysis.history.empty': 'No analysis history yet.',
    'analysis.history.col_symbol': 'Symbol',
    'analysis.history.col_date': 'Date',
    'analysis.history.col_signal': 'Signal',
    'analysis.history.col_duration': 'Duration',
    'analysis.history.col_source': 'Source',
    'analysis.history.col_time': 'Time',
    'analysis.history.detail_loading': 'Loading...',
    'analysis.history.btn_download_md': 'Download Markdown',
    'analysis.history.btn_download_pdf': 'Download PDF',


    'analysis.section.market_report': 'Market Analysis',
    'analysis.section.sentiment_report': 'Sentiment Analysis',
    'analysis.section.news_report': 'News Analysis',
    'analysis.section.fundamentals_report': 'Fundamental Analysis',
    'analysis.section.macro_report': 'Macro Analysis',
    'analysis.section.options_report': 'Options Analysis',
    'analysis.section.quant_report': 'Quantitative Analysis',
    'analysis.section.earnings_report': 'Earnings Analysis',
    'analysis.section.insider_report': 'Insider Activity',
    'analysis.section.ownership_report': 'Institutional Ownership',
    'analysis.section.review_report': 'Performance Review',
    'analysis.section.investment_plan': 'Investment Plan',
    'analysis.section.trader_investment_plan': 'Trader Plan',
    'analysis.section.final_trade_decision': 'PM Decision',
    'analysis.section.bull_history': 'Bull Arguments',
    'analysis.section.bear_history': 'Bear Arguments',
    'analysis.section.investment_debate_history': 'Debate',
    'analysis.section.risk_debate_history': 'Risk Debate',
    'analysis.section.judge_decision': 'Judge Decision',
    'analysis.tab.reports': 'Reports',
    'analysis.tab.debate': 'Debate Logs',
    'analysis.tab.qa': 'Q&A Chat',
    'analysis.tab.live_debate': 'Live Debate',
    'analysis.tabs.progress': 'Analysis Progress',
    'analysis.tabs.live_debate': 'Live Debate',
    'analysis.log.empty': 'No logs yet.',
    'analysis.chat.welcome_title': 'Start a conversation with the analyst on this report.',
    'analysis.chat.welcome_desc': 'You can ask questions about stock comparisons or macro interest rate effects.',
    'analysis.chat.thinking': 'Thinking...',
    'analysis.chat.placeholder': 'Ask a question about the report...',
    'analysis.chat.send': 'Send',
    'analysis.chat.error': 'Failed to get chat response.',
  },
  tr: {

    'analysis.title': 'Analiz',


    'analysis.tab.single': 'Tek Hisse',
    'analysis.tab.multi': 'Çoklu Hisse',
    'analysis.tab.history': 'Geçmiş',


    'analysis.label.symbol': 'Sembol',
    'analysis.label.date': 'Tarih',
    'analysis.label.type': 'Tür',


    'analysis.btn.start': 'Analiz Başlat',
    'analysis.btn.stop': 'Durdur',
    'analysis.btn.rerun': 'Yeniden Çalıştır',
    'analysis.btn.cancel': 'İptal',


    'analysis.cost_estimate': 'Tahmini maliyet: ~$',
    'analysis.existing_analysis': '⚠ Bu tarih için kayıtlı analiz var — yeniden çalıştıracaksınız',
    'analysis.running': 'analiz ediliyor',


    'analysis.rerun.title': 'Mevcut Analiz Var',
    'analysis.rerun.body': '{ticker} için {date} tarihli bir analiz zaten mevcut. Yeni analiz daha fazla API kredisi harcayacak.',


    'analysis.log.title': 'Canlı Log',
    'analysis.log.lines': 'satır',


    'analysis.reports.title': 'Raporlar',
    'analysis.reports.sections': 'bölüm',
    'analysis.reports.empty': 'Raporlar analiz sırasında burada görünecek.',


    'analysis.report_card.show': 'Göster',
    'analysis.report_card.hide': 'Gizle',


    'analysis.ws.complete': '— Tamamlandı',
    'analysis.ws.llm_calls': 'LLM çağrısı',
    'analysis.ws.error_prefix': '✗ HATA:',
    'analysis.ws.conn_error': '✗ Bağlantı hatası.',
    'analysis.ws.conn_closed_reconnect': '— Analiz tamamlanmış veya bağlantı kesildi. Geçmiş sekmesini kontrol et.',
    'analysis.ws.conn_closed': 'Bağlantı kapandı — backend hatası veya LLM API anahtarı eksik olabilir.',
    'analysis.ws.stopped': '— Analiz durduruldu.',
    'analysis.ws.failed_to_start': 'Başlatılamadı',
    'analysis.ws.analysis_error_title': 'Analiz Hatası',
    'analysis.ws.analysis_failed': 'Analiz başarısız.',
    'analysis.ws.analysis_interrupted': 'Analiz Kesildi',
    'analysis.ws.analysis_complete_notif': 'analizi tamamlandı',
    'analysis.ws.signal_label': 'Sinyal:',


    'analysis.multi.description': 'En az 2, en fazla 10 hisse. SuperPortfolioManager tüm hisseleri analiz edip portföy dağılımı önerir.',
    'analysis.multi.label_symbols': 'Semboller',
    'analysis.multi.btn_start': 'Portföy Analizi Başlat',
    'analysis.multi.running': 'Çalışıyor...',
    'analysis.multi.started': 'Arka planda başlatıldı — "Portföy Geçmişi" tabından takip edebilirsiniz.',
    'analysis.multi.error_default': 'Portföy analizi başlatılamadı.',


    'analysis.portfolio_history.title': 'Portföy Analizi Geçmişi',
    'analysis.portfolio_history.loading': 'Yükleniyor...',
    'analysis.portfolio_history.empty': 'Henüz portföy analizi yok.',
    'analysis.portfolio_history.report_not_ready': 'Rapor henüz hazır değil.',


    'analysis.history.loading': 'Yükleniyor...',
    'analysis.history.empty': 'Henüz analiz geçmişi yok.',
    'analysis.history.col_symbol': 'Sembol',
    'analysis.history.col_date': 'Tarih',
    'analysis.history.col_signal': 'Sinyal',
    'analysis.history.col_duration': 'Süre',
    'analysis.history.col_source': 'Kaynak',
    'analysis.history.col_time': 'Zaman',
    'analysis.history.detail_loading': 'Yükleniyor...',
    'analysis.history.btn_download_md': 'Markdown İndir',
    'analysis.history.btn_download_pdf': 'PDF İndir',


    'analysis.section.market_report': 'Piyasa Analizi',
    'analysis.section.sentiment_report': 'Duygu Analizi',
    'analysis.section.news_report': 'Haber Analizi',
    'analysis.section.fundamentals_report': 'Temel Analiz',
    'analysis.section.macro_report': 'Makro Analiz',
    'analysis.section.options_report': 'Opsiyon Analizi',
    'analysis.section.quant_report': 'Kantitatif Analiz',
    'analysis.section.earnings_report': 'Kazanç Analizi',
    'analysis.section.insider_report': 'İçeriden İşlemler',
    'analysis.section.ownership_report': 'Kurumsal Sahiplik',
    'analysis.section.review_report': 'Performans İnceleme',
    'analysis.section.investment_plan': 'Yatırım Planı',
    'analysis.section.trader_investment_plan': 'Trader Planı',
    'analysis.section.final_trade_decision': 'PM Kararı',
    'analysis.section.bull_history': 'Boğa Argümanları',
    'analysis.section.bear_history': 'Ayı Argümanları',
    'analysis.section.investment_debate_history': 'Tartışma',
    'analysis.section.risk_debate_history': 'Risk Tartışması',
    'analysis.section.judge_decision': 'Hakem Kararı',
    'analysis.tab.reports': 'Raporlar',
    'analysis.tab.debate': 'Tartışma Kayıtları',
    'analysis.tab.qa': 'Yapay Zeka Sohbet',
    'analysis.tab.live_debate': 'Canlı Tartışma',
    'analysis.tabs.progress': 'Analiz Süreci',
    'analysis.tabs.live_debate': 'Canlı Tartışma',
    'analysis.log.empty': 'Henüz log yok.',
    'analysis.chat.welcome_title': 'Rapor özelinde analistle sohbete başlayın.',
    'analysis.chat.welcome_desc': 'Hisse kıyaslamaları veya makro faiz etkileri hakkında sorular sorabilirsiniz.',
    'analysis.chat.thinking': 'Düşünüyor...',
    'analysis.chat.placeholder': 'Rapor hakkında soru sorun...',
    'analysis.chat.send': 'Gönder',
    'analysis.chat.error': 'Sohbet yanıtı alınamadı.',
  },
}

export default analysis

