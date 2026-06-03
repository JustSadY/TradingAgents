const translations = {
  en: {
    // Page loading state
    'settings.loading': 'Loading...',

    // Section titles
    'settings.section_working_mode': 'Trading Mode Preferences',
    'settings.section_cron': 'Cron / Auto Scan',
    'settings.section_risk': 'Risk & Safety',
    'settings.section_active_analysts': 'Active Analysts & Models',
    'settings.section_data_sources': 'Data Sources Routing',
    'settings.section_advanced': 'Admin Engine Routing',
    'settings.section_presets': 'Configuration Templates',
    'settings.section_notifications': 'Personal Webhooks',

    // Row labels — Working Mode
    'settings.row_mode': 'Mode',
    'settings.row_active_broker': 'Active Broker',
    'settings.row_data_source': 'Data Source',

    // Row labels — Cron
    'settings.row_active': 'Active',
    'settings.row_schedule': 'Schedule (Cron)',
    'settings.row_price_tolerance': 'Price Tolerance (%)',

    // Row labels — LLM
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

    // ModelSelect
    'settings.custom_model_id': 'Custom model ID',
    'settings.model_id_placeholder': 'Enter model ID...',

    // Provider reasoning effort options
    'settings.effort_default': 'Default',
    'settings.effort_low_fast_cheap': 'Low — Fast, cheap',
    'settings.effort_medium_balanced': 'Medium — Balanced',
    'settings.effort_high_deep': 'High — Deepest thinking',
    'settings.effort_low_fast': 'Low — Fast',
    'settings.effort_high_extended': 'High — Extended thinking',
    'settings.effort_minimal_fastest': 'Minimal — Fastest',
    'settings.effort_high_deepest': 'High — Deepest',

    // Investor Personas
    'settings.row_investor_persona': 'Investor Persona',
    'settings.persona_conservative': 'Conservative Dividend Investor',
    'settings.persona_risk_loving': 'Risk-Loving Crypto/Growth Trader',
    'settings.persona_esg_focused': 'Sustainability/ESG-Focused',

    // Row labels — Risk Management
    'settings.row_max_position_size': 'Max Position Size (%)',
    'settings.row_risk_per_trade': 'Risk Per Trade (%)',

    // Active analysts loading
    'settings.analysts_loading': 'Loading...',

    // Data Sources rows
    'settings.data_core_stock': 'Stock Price',
    'settings.data_technicals': 'Technical Indicators',
    'settings.data_fundamentals': 'Fundamental Data',
    'settings.data_news': 'News',

    // Advanced Settings rows
    'settings.row_checkpoint': 'Checkpoint (Resume)',
    'settings.row_historical_analyses': 'Historical Analyses',
    'settings.historical_analyses_hint': 'Include previous reports for AI',
    'settings.historical_limit_label': 'Number of recent analyses to include:',
    'settings.row_news_limit_ticker': 'News Count (Ticker)',
    'settings.row_global_news_limit': 'Global News Count',
    'settings.row_global_news_lookback': 'Global News Lookback (Days)',
    'settings.row_max_recursion': 'Max Recursion Limit',
    'settings.row_benchmark_symbol': 'Benchmark Symbol',
    'settings.benchmark_placeholder': 'Leave empty = auto (SPY)',
    'settings.row_azure_deployment': 'Azure Deployment Name',

    // Presets section
    'settings.preset_name_placeholder': 'Template name...',
    'settings.preset_save_button': 'Save',
    'settings.preset_no_presets': 'No templates yet.',
    'settings.preset_apply_title': 'Apply',

    // Notifications section
    'settings.row_webhook_url': 'Webhook URL',
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

    // Save button
    'settings.save_button': 'Save',
    'settings.save_button_saved': 'Saved ✓',

    // Save error fallback
    'settings.save_error_default': 'Save failed.',
  },
  tr: {
    // Page loading state
    'settings.loading': 'Yükleniyor...',

    // Section titles
    'settings.section_working_mode': 'İşlem Modu Tercihleri',
    'settings.section_cron': 'Cron / Otomatik Tarama',
    'settings.section_risk': 'Risk ve Güvenlik Limitleri',
    'settings.section_active_analysts': 'Aktif Analistler & Modeller',
    'settings.section_data_sources': 'Veri Kaynağı Yönlendirmeleri',
    'settings.section_advanced': 'Yönetici Motor Yönlendirmeleri',
    'settings.section_presets': 'Ayar Şablonları',
    'settings.section_notifications': 'Kişisel Webhooklar',

    // Row labels — Working Mode
    'settings.row_mode': 'Mod',
    'settings.row_active_broker': 'Aktif Broker',
    'settings.row_data_source': 'Veri Kaynağı',

    // Row labels — Cron
    'settings.row_active': 'Aktif',
    'settings.row_schedule': 'Zamanlama (Cron)',
    'settings.row_price_tolerance': 'Fiyat Toleransı (%)',

    // Row labels — LLM
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

    // ModelSelect
    'settings.custom_model_id': 'Özel model ID',
    'settings.model_id_placeholder': 'Model ID girin...',

    // Provider reasoning effort options
    'settings.effort_default': 'Varsayılan',
    'settings.effort_low_fast_cheap': 'Low — Hızlı, ucuz',
    'settings.effort_medium_balanced': 'Medium — Dengeli',
    'settings.effort_high_deep': 'High — En derin düşünce',
    'settings.effort_low_fast': 'Low — Hızlı',
    'settings.effort_high_extended': 'High — Extended thinking',
    'settings.effort_minimal_fastest': 'Minimal — En hızlı',
    'settings.effort_high_deepest': 'High — En derin',

    // Investor Personas
    'settings.row_investor_persona': 'Yatırımcı Kişiliği',
    'settings.persona_conservative': 'Muhafazakar Temettü Yatırımcısı',
    'settings.persona_risk_loving': 'Risk Sever Kripto/Büyüme Traderı',
    'settings.persona_esg_focused': 'Sürdürülebilirlik/ESG Odaklı',

    // Row labels — Risk Management
    'settings.row_max_position_size': 'Maks. Pozisyon Büyüklüğü (%)',
    'settings.row_risk_per_trade': 'Trade Başına Risk (%)',

    // Active analysts loading
    'settings.analysts_loading': 'Yükleniyor...',

    // Data Sources rows
    'settings.data_core_stock': 'Hisse Fiyatı',
    'settings.data_technicals': 'Teknik Göstergeler',
    'settings.data_fundamentals': 'Temel Veriler',
    'settings.data_news': 'Haber',

    // Advanced Settings rows
    'settings.row_checkpoint': 'Checkpoint (Devam Etme)',
    'settings.row_historical_analyses': 'Eskiye Dönük Analizler',
    'settings.historical_analyses_hint': 'Önceki raporları AI\'ya dahil et',
    'settings.historical_limit_label': 'Dahil edilecek son analiz sayısı:',
    'settings.row_news_limit_ticker': 'Haber Sayısı (Ticker)',
    'settings.row_global_news_limit': 'Global Haber Sayısı',
    'settings.row_global_news_lookback': 'Global Haber Geriye (Gün)',
    'settings.row_max_recursion': 'Max Recursion Limiti',
    'settings.row_benchmark_symbol': 'Benchmark Sembolü',
    'settings.benchmark_placeholder': 'Boş bırakın = otomatik (SPY)',
    'settings.row_azure_deployment': 'Azure Deployment Adı',

    // Presets section
    'settings.preset_name_placeholder': 'Şablon adı...',
    'settings.preset_save_button': 'Kaydet',
    'settings.preset_no_presets': 'Henüz şablon yok.',
    'settings.preset_apply_title': 'Uygula',

    // Notifications section
    'settings.row_webhook_url': 'Webhook URL',
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

    // Save button
    'settings.save_button': 'Kaydet',
    'settings.save_button_saved': 'Kaydedildi ✓',

    // Save error fallback
    'settings.save_error_default': 'Kaydetme başarısız.',
  },
}

export default translations
