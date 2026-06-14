import React, { createContext, useContext, useState } from 'react'

export type Language = 'en' | 'tr'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: string) => string
}

const TRANSLATIONS: Record<Language, Record<string, string>> = {
  en: {

    'nav.dashboard': 'Dashboard',
    'nav.analysis': 'Agent Analysis',
    'nav.chart': 'Technical Charts',
    'nav.simulation': 'Paper Trading',
    'nav.portfolio': 'My Portfolio',
    'nav.watchlist': 'Watchlist',
    'nav.orders': 'Order History',
    'nav.performance': 'Performance Stats',
    'nav.alerts': 'Price Alerts',
    'nav.screener': 'Stock Screener',
    'nav.sector_rotation': 'Sector Map',
    'nav.earnings_calendar': 'Earnings Calendar',
    'nav.settings': 'Preferences',
    'nav.ab_testing': 'A/B Testing',
    'nav.logs': 'System Logs',
    'nav.profile': 'Account & API Keys',
    'nav.admin': 'Admin Control Panel',
    'nav.logout': 'Logout',
    'nav.analyzing': 'Analyzing...',
    'nav.running_in_bg': 'Running in background...',
    'nav.next_run': 'Next:',
    'nav.section.trading_desk': 'Trading Desk',
    'nav.section.portfolio_trading': 'Portfolio & Trading',
    'nav.section.market_tools': 'Market Tools',
    'nav.section.system_config': 'Management & Settings',


    'dashboard.title': 'Dashboard',
    'dashboard.new_analysis': 'New Analysis',
    'dashboard.recent_analyses': 'Recent Analyses',
    'dashboard.all': 'All',
    'dashboard.ticker': 'Symbol',
    'dashboard.date': 'Date',
    'dashboard.signal': 'Signal',
    'dashboard.duration': 'Duration',
    'dashboard.no_analyses': 'No analyses run yet.',
    'dashboard.open_positions': 'Open Positions',
    'dashboard.no_open_positions': 'No open positions.',
    'dashboard.quantity': 'Quantity',
    'dashboard.price': 'Price',
    'dashboard.pnl': 'P&L',
    'dashboard.watchlist_news': 'Watchlist News Feed',
    'dashboard.portfolio_value': 'Portfolio Value',
    'dashboard.total_return': 'Total Return',
    'dashboard.cash': 'Cash',
    'dashboard.unrealized_pnl': 'Unrealized P&L',
    'dashboard.win_rate': 'Signal Win Rate',
    'dashboard.analyses': 'analyses',


    'watchlist.title': 'Watchlist',
    'watchlist.add': 'Add',
    'watchlist.loading': 'Loading...',
    'watchlist.empty': 'Watchlist is empty.',
    'watchlist.placeholder': 'Enter symbol (e.g. AAPL)',


    'common.loading': 'Loading...',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.error': 'Error',
    'common.success': 'Success',
    'common.delete': 'Delete',
    'common.add': 'Add',
    'common.no_data': 'No data available',


    'settings.title': 'Preferences',
    'settings.general': 'General Preferences',
    'settings.language': 'App Language',
    'settings.llm_settings': 'LLM Settings',
    'settings.cron_settings': 'Scheduler (Cron) Settings',
    'settings.watchlist': 'Watchlist Assets',
    'settings.save_success': 'Preferences saved successfully.',
    'settings.save_error': 'Failed to save preferences.',


    'logs.title': 'System Logs',
    'logs.all_levels': 'All Levels',
    'logs.no_logs': 'No logs available.',
  },
  tr: {

    'nav.dashboard': 'Pano (Dashboard)',
    'nav.analysis': 'Ajan Analizi',
    'nav.chart': 'Teknik Grafikler',
    'nav.simulation': 'Sanal İşlemler',
    'nav.portfolio': 'Portföyüm',
    'nav.watchlist': 'İzleme Listesi',
    'nav.orders': 'Emir Geçmişi',
    'nav.performance': 'Performans Analizi',
    'nav.alerts': 'Fiyat Alarmları',
    'nav.screener': 'Hisse Tarayıcı',
    'nav.sector_rotation': 'Sektör Haritası',
    'nav.earnings_calendar': 'Kazanç Takvimi',
    'nav.settings': 'Tercihler',
    'nav.ab_testing': 'A/B Testi',
    'nav.logs': 'Sistem Günlükleri',
    'nav.profile': 'Profil & API Anahtarları',
    'nav.admin': 'Yönetim Paneli',
    'nav.logout': 'Çıkış Yap',
    'nav.analyzing': 'analiz ediliyor',
    'nav.running_in_bg': 'Arka planda çalışıyor...',
    'nav.next_run': 'Sonraki:',
    'nav.section.trading_desk': 'İşlem Masası',
    'nav.section.portfolio_trading': 'Portföy & Yatırım',
    'nav.section.market_tools': 'Piyasa Takibi',
    'nav.section.system_config': 'Sistem & Ayarlar',


    'dashboard.title': 'Dashboard',
    'dashboard.new_analysis': 'Yeni Analiz',
    'dashboard.recent_analyses': 'Son Analizler',
    'dashboard.all': 'Tümü',
    'dashboard.ticker': 'Sembol',
    'dashboard.date': 'Tarih',
    'dashboard.signal': 'Sinyal',
    'dashboard.duration': 'Süre',
    'dashboard.no_analyses': 'Henüz analiz yapılmadı.',
    'dashboard.open_positions': 'Açık Pozisyonlar',
    'dashboard.no_open_positions': 'Açık pozisyon yok.',
    'dashboard.quantity': 'Miktar',
    'dashboard.price': 'Fiyat',
    'dashboard.pnl': 'K/Z',
    'dashboard.watchlist_news': 'İzleme Listesi Haberleri',
    'dashboard.portfolio_value': 'Portföy Değeri',
    'dashboard.total_return': 'Toplam Getiri',
    'dashboard.cash': 'Nakit',
    'dashboard.unrealized_pnl': 'Gerçekleşmemiş K/Z',
    'dashboard.win_rate': 'Sinyal Kazanma Oranı',
    'dashboard.analyses': 'analiz',


    'watchlist.title': 'İzleme Listesi',
    'watchlist.add': 'Ekle',
    'watchlist.loading': 'Yükleniyor...',
    'watchlist.empty': 'İzleme listesi boş.',
    'watchlist.placeholder': 'Sembol girin (örn. AAPL)',


    'common.loading': 'Yükleniyor...',
    'common.save': 'Kaydet',
    'common.cancel': 'İptal',
    'common.error': 'Hata',
    'common.success': 'Başarılı',
    'common.delete': 'Sil',
    'common.add': 'Ekle',
    'common.no_data': 'Veri bulunamadı',


    'settings.title': 'Ayarlar',
    'settings.general': 'Genel Ayarlar',
    'settings.language': 'Uygulama Dili',
    'settings.llm_settings': 'LLM Ayarları',
    'settings.cron_settings': 'Zamanlayıcı (Cron) Ayarları',
    'settings.watchlist': 'İzlenecek Varlıklar',
    'settings.save_success': 'Ayarlar başarıyla kaydedildi.',
    'settings.save_error': 'Ayarlar kaydedilemedi.',


    'logs.title': 'Sistem Logları',
    'logs.all_levels': 'Tüm Seviyeler',
    'logs.no_logs': 'Log yok.',
  }
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)






const _modules = import.meta.glob('../i18n/*.ts', { eager: true }) as Record<
  string,
  { default?: { en?: Record<string, string>; tr?: Record<string, string> } }
>
for (const mod of Object.values(_modules)) {
  const data = mod.default
  if (!data) continue
  Object.assign(TRANSLATIONS.en, data.en || {})
  Object.assign(TRANSLATIONS.tr, data.tr || {})
}

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>(() => {
    return (localStorage.getItem('ta_language') as Language) || 'en'
  })

  const setLanguage = (lang: Language) => {
    localStorage.setItem('ta_language', lang)
    setLanguageState(lang)
  }

  const t = (key: string): string => {
    return TRANSLATIONS[language]?.[key] || TRANSLATIONS['en']?.[key] || key
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export const useTranslation = () => {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useTranslation must be used within a LanguageProvider')
  }
  return context
}

