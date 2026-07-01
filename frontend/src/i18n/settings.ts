const translations = {
  en: {

    'settings.loading': 'Loading...',


    'settings.section_working_mode': 'Trading Mode Preferences',
    'settings.section_cron': 'Cron / Auto Scan',
    'settings.section_risk': 'Risk & Safety',
    'settings.section_active_analysts': 'Active Analysts & Models',
    'settings.section_data_sources': 'Data Sources Routing',
    'settings.section_engine_routing': 'Engine Routing',
    'settings.section_advanced': 'Admin Engine Routing',
    'settings.section_tools': 'Agent Tools',
    'settings.section_presets': 'Configuration Templates',
    'settings.section_notifications': 'Personal Webhooks',


    'settings.row_mode': 'Mode',
    'settings.row_active_broker': 'Active Broker',
    'settings.row_data_source': 'Data Source',


    'settings.row_active': 'Active',
    'settings.row_schedule': 'Schedule (Cron)',
    'settings.row_price_tolerance': 'Price Tolerance (%)',


    'settings.row_deep_think_model': 'Deep Think Model',
    'settings.row_quick_think_model': 'Quick Think Model',
    'settings.row_default_model': 'Default Model',
    'settings.analyst_default_provider': 'Default Provider',
    'settings.analyst_default_model': 'Default Model',
    'settings.analyst_select_model': 'Select Model...',
    'settings.model_quick_suffix': 'Quick',
    'settings.model_deep_suffix': 'Deep',
    'settings.custom_model_option': 'Custom model...',
    'settings.custom_model_placeholder': 'Model ID (e.g. gpt-4o)',
    'settings.row_output_language': 'Output Language',
    'settings.row_debate_rounds': 'Debate Rounds',
    'settings.row_risk_rounds': 'Risk Rounds',
    'settings.row_parallel_analysts': 'Parallel Analysts',


    'settings.custom_model_id': 'Custom model ID',
    'settings.model_id_placeholder': 'Enter model ID...',


    'settings.effort_default': 'Default',
    'settings.effort_low_fast_cheap': 'Low — Fast, cheap',
    'settings.effort_medium_balanced': 'Medium — Balanced',
    'settings.effort_high_deep': 'High — Deepest thinking',
    'settings.effort_low_fast': 'Low — Fast',
    'settings.effort_high_extended': 'High — Extended thinking',
    'settings.effort_minimal_fastest': 'Minimal — Fastest',
    'settings.effort_high_deepest': 'High — Deepest',


    'settings.row_fallback_provider': 'Fallback Provider',
    'settings.row_fallback_model': 'Fallback Model',
    'settings.fallback_disabled': 'Disabled',
    'settings.fallback_model_placeholder': 'e.g. gpt-4o-mini',
    'settings.fallback_hint': 'Used when the primary provider fails mid-analysis. Requires an API key for the fallback provider.',


    'settings.row_memory_store': 'Memory Store',
    'settings.memory_store_pinecone': 'Pinecone (managed)',
    'settings.memory_store_pgvector': 'PostgreSQL (pgvector, self-hosted)',
    'settings.memory_disabled_pinecone': 'DISABLED — add a Pinecone API key',
    'settings.memory_disabled_pgvector': 'DISABLED — add an OpenAI API key',
    'settings.pgvector_hint': "Episodes are stored in the app's own PostgreSQL database. Requires the pgvector extension on the database server and your OpenAI API key (Profile → API Keys) for embedding.",


    'settings.row_investor_persona': 'Investor Persona',
    'settings.persona_conservative': 'Conservative Dividend Investor',
    'settings.persona_risk_loving': 'Risk-Loving Crypto/Growth Trader',
    'settings.persona_esg_focused': 'Sustainability/ESG-Focused',
    'settings.persona_aggressive': 'Aggressive Growth Investor',


    'settings.row_max_position_size': 'Max Position Size (%)',
    'settings.row_risk_per_trade': 'Risk Per Trade (%)',
    'settings.row_strict_stop_loss': 'Strict Stop Loss Mode',
    'settings.row_correlation_risk': 'Correlation-Aware Sizing',
    'settings.row_node_retry_attempts': 'Node Retry Attempts',
    'settings.row_node_retry_base_delay': 'Retry Base Delay (s)',
    'settings.token_budget': 'Token Budget',
    'settings.token_budget_hint': 'Lower values reduce LLM token cost per analysis at the expense of how much detail each agent re-reads.',
    'settings.row_prompt_caching': 'Anthropic Prompt Caching',
    'settings.row_max_report_chars': 'Max Report Chars / Prompt',
    'settings.row_max_debate_history': 'Max Debate History Chars',
    'settings.row_max_tool_output': 'Max Tool Output Chars',
    'settings.row_prefilter_enabled': 'Pre-screen Weak Analysts',
    'settings.prefilter_hint': 'Skip analysts whose past calls on the analysed ticker have a poor hit rate. Needs realized history; core analysts are always kept.',
    'settings.row_prefilter_min_samples': 'Min. Graded Calls',
    'settings.row_prefilter_max_win_rate': 'Drop Below Win Rate (%)',


    'settings.analysts_loading': 'Loading...',


    'settings.data_core_stock': 'Stock Price',
    'settings.data_technicals': 'Technical Indicators',
    'settings.data_fundamentals': 'Fundamental Data',
    'settings.data_news': 'News',


    'settings.row_checkpoint': 'Checkpoint (Resume)',
    'settings.row_news_limit_ticker': 'News Count (Ticker)',
    'settings.row_global_news_limit': 'Global News Count',
    'settings.row_global_news_lookback': 'Global News Lookback (Days)',
    'settings.row_max_recursion': 'Max Recursion Limit',
    'settings.row_benchmark_symbol': 'Benchmark Symbol',
    'settings.benchmark_placeholder': 'Leave empty = auto (SPY)',
    'settings.row_reddit_enabled': 'Reddit Sentiment Data',
    'settings.reddit_enabled_hint': 'Use Reddit posts for sentiment analysis',
    'settings.row_azure_deployment': 'Azure Deployment Name',


    'settings.preset_name_placeholder': 'Template name...',
    'settings.preset_save_button': 'Save',
    'settings.preset_no_presets': 'No templates yet.',
    'settings.preset_apply_title': 'Apply',


    'settings.row_webhook_url': 'Webhook URL',
    'settings.webhook_help': 'Supported channels: Slack (hooks.slack.com), Discord (discord.com/api/webhooks), Telegram (api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>), or any custom endpoint that accepts a JSON POST. The format is auto-detected from the URL.',
    'settings.row_webhook_active': 'Webhook Active',
    'settings.webhook_test_button': 'Test',
    'settings.webhook_success': '✓ Success',
    'settings.webhook_failed': '✗ Failed',
    'settings.row_notification_events': 'Notification Events',
    'settings.event_analysis_complete': 'Analysis completed',
    'settings.event_trade_executed': 'Trade executed',
    'settings.event_alert_triggered': 'Price alert triggered',
    'settings.row_browser_notifications': 'Browser Notifications',
    'settings.browser_notify_on': 'On',
    'settings.browser_notify_off': 'Off',


    'settings.save_button': 'Save',
    'settings.save_button_saved': 'Saved ✓',


    'settings.save_error_default': 'Save failed.',
  },
  tr: {

    'settings.loading': 'Yükleniyor...',


    'settings.section_working_mode': 'İşlem Modu Tercihleri',
    'settings.section_cron': 'Cron / Otomatik Tarama',
    'settings.section_risk': 'Risk ve Güvenlik Limitleri',
    'settings.section_active_analysts': 'Aktif Analistler & Modeller',
    'settings.section_data_sources': 'Veri Kaynağı Yönlendirmeleri',
    'settings.section_engine_routing': 'Motor Yönlendirmeleri',
    'settings.section_advanced': 'Yönetici Motor Yönlendirmeleri',
    'settings.section_tools': 'Ajan Araçları (Tools)',
    'settings.section_presets': 'Ayar Şablonları',
    'settings.section_notifications': 'Kişisel Webhooklar',


    'settings.row_mode': 'Mod',
    'settings.row_active_broker': 'Aktif Broker',
    'settings.row_data_source': 'Veri Kaynağı',


    'settings.row_active': 'Aktif',
    'settings.row_schedule': 'Zamanlama (Cron)',
    'settings.row_price_tolerance': 'Fiyat Toleransı (%)',


    'settings.row_deep_think_model': 'Derin Düşünce Modeli',
    'settings.row_quick_think_model': 'Hızlı Düşünce Modeli',
    'settings.row_default_model': 'Varsayılan Model',
    'settings.analyst_default_provider': 'Varsayılan Sağlayıcı',
    'settings.analyst_default_model': 'Varsayılan Model',
    'settings.analyst_select_model': 'Model Seçin...',
    'settings.model_quick_suffix': 'Hızlı',
    'settings.model_deep_suffix': 'Derin',
    'settings.custom_model_option': 'Özel model...',
    'settings.custom_model_placeholder': 'Model ID (örn: gpt-4o)',
    'settings.row_output_language': 'Çıktı Dili',
    'settings.row_debate_rounds': 'Tartışma Turları',
    'settings.row_risk_rounds': 'Risk Turları',
    'settings.row_parallel_analysts': 'Paralel Analist Sayısı',


    'settings.custom_model_id': 'Özel model ID',
    'settings.model_id_placeholder': 'Model ID girin...',


    'settings.effort_default': 'Varsayılan',
    'settings.effort_low_fast_cheap': 'Low — Hızlı, ucuz',
    'settings.effort_medium_balanced': 'Medium — Dengeli',
    'settings.effort_high_deep': 'High — En derin düşünce',
    'settings.effort_low_fast': 'Low — Hızlı',
    'settings.effort_high_extended': 'High — Extended thinking',
    'settings.effort_minimal_fastest': 'Minimal — En hızlı',
    'settings.effort_high_deepest': 'High — En derin',


    'settings.row_fallback_provider': 'Yedek Sağlayıcı',
    'settings.row_fallback_model': 'Yedek Model',
    'settings.fallback_disabled': 'Kapalı',
    'settings.fallback_model_placeholder': 'örn. gpt-4o-mini',
    'settings.fallback_hint': 'Birincil sağlayıcı analiz sırasında hata verdiğinde kullanılır. Yedek sağlayıcı için API anahtarı gerekir.',


    'settings.row_memory_store': 'Bellek Deposu',
    'settings.memory_store_pinecone': 'Pinecone (yönetilen)',
    'settings.memory_store_pgvector': 'PostgreSQL (pgvector, kendi sunucunda)',
    'settings.memory_disabled_pinecone': 'KAPALI — Pinecone API anahtarı ekleyin',
    'settings.memory_disabled_pgvector': 'KAPALI — OpenAI API anahtarı ekleyin',
    'settings.pgvector_hint': 'Epizotlar uygulamanın kendi PostgreSQL veritabanında saklanır. Veritabanı sunucusunda pgvector eklentisi ve embedding için OpenAI API anahtarınız (Profil → API Anahtarları) gerekir.',


    'settings.row_investor_persona': 'Yatırımcı Kişiliği',
    'settings.persona_conservative': 'Muhafazakar Temettü Yatırımcısı',
    'settings.persona_risk_loving': 'Risk Sever Kripto/Büyüme Traderı',
    'settings.persona_esg_focused': 'Sürdürülebilirlik/ESG Odaklı',
    'settings.persona_aggressive': 'Agresif Büyüme Yatırımcısı',


    'settings.row_max_position_size': 'Maks. Pozisyon Büyüklüğü (%)',
    'settings.row_risk_per_trade': 'Trade Başına Risk (%)',
    'settings.row_strict_stop_loss': 'Sıkı Stop-Loss Modu',
    'settings.row_correlation_risk': 'Korelasyon-Farkında Boyutlama',
    'settings.token_budget': 'Token Bütçesi',
    'settings.token_budget_hint': 'Daha düşük değerler analiz başına LLM token maliyetini azaltır; karşılığında her ajanın yeniden okuduğu ayrıntı miktarı düşer.',
    'settings.row_prompt_caching': 'Anthropic Prompt Önbellekleme',
    'settings.row_max_report_chars': 'Maks. Rapor Karakteri / Prompt',
    'settings.row_max_debate_history': 'Maks. Müzakere Geçmişi Karakteri',
    'settings.row_max_tool_output': 'Maks. Araç Çıktısı Karakteri',
    'settings.row_prefilter_enabled': 'Zayıf Analistleri Ön-ele',
    'settings.prefilter_hint': 'Analiz edilen hissede geçmiş çağrıları düşük isabetli olan analistleri atla. Gerçekleşmiş geçmiş gerektirir; çekirdek analistler her zaman korunur.',
    'settings.row_prefilter_min_samples': 'Min. Derecelendirilmiş Çağrı',
    'settings.row_prefilter_max_win_rate': 'Şu İsabet Altında Ele (%)',
    'settings.row_node_retry_attempts': 'Ajan Düğüm Deneme Sayısı',
    'settings.row_node_retry_base_delay': 'Deneme Gecikme Süresi (sn)',


    'settings.analysts_loading': 'Yükleniyor...',


    'settings.data_core_stock': 'Hisse Fiyatı',
    'settings.data_technicals': 'Teknik Göstergeler',
    'settings.data_fundamentals': 'Temel Veriler',
    'settings.data_news': 'Haber',


    'settings.row_checkpoint': 'Checkpoint (Devam Etme)',
    'settings.row_news_limit_ticker': 'Haber Sayısı (Ticker)',
    'settings.row_global_news_limit': 'Global Haber Sayısı',
    'settings.row_global_news_lookback': 'Global Haber Geriye (Gün)',
    'settings.row_max_recursion': 'Max Recursion Limiti',
    'settings.row_benchmark_symbol': 'Benchmark Sembolü',
    'settings.benchmark_placeholder': 'Boş bırakın = otomatik (SPY)',
    'settings.row_reddit_enabled': 'Reddit Duygu Verisi',
    'settings.reddit_enabled_hint': 'Duygu analizi için Reddit gönderilerini kullan',
    'settings.row_azure_deployment': 'Azure Deployment Adı',


    'settings.preset_name_placeholder': 'Şablon adı...',
    'settings.preset_save_button': 'Kaydet',
    'settings.preset_no_presets': 'Henüz şablon yok.',
    'settings.preset_apply_title': 'Uygula',


    'settings.row_webhook_url': 'Webhook URL',
    'settings.webhook_help': 'Desteklenen kanallar: Slack (hooks.slack.com), Discord (discord.com/api/webhooks), Telegram (api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>) veya JSON POST kabul eden herhangi bir özel adres. Format URL\'den otomatik algılanır.',
    'settings.row_webhook_active': 'Webhook Aktif',
    'settings.webhook_test_button': 'Test Et',
    'settings.webhook_success': '✓ Başarılı',
    'settings.webhook_failed': '✗ Başarısız',
    'settings.row_notification_events': 'Bildirim Olayları',
    'settings.event_analysis_complete': 'Analiz tamamlandı',
    'settings.event_trade_executed': 'İşlem gerçekleşti',
    'settings.event_alert_triggered': 'Fiyat alarmı tetiklendi',
    'settings.row_browser_notifications': 'Tarayıcı Bildirimleri',
    'settings.browser_notify_on': 'Açık',
    'settings.browser_notify_off': 'Kapalı',


    'settings.save_button': 'Kaydet',
    'settings.save_button_saved': 'Kaydedildi ✓',


    'settings.save_error_default': 'Kaydetme başarısız.',
  },
}

export default translations

