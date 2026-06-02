import React, { createContext, useContext, useState } from 'react'

export type Language = 'en' | 'tr'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: string) => string
}

const TRANSLATIONS: Record<Language, Record<string, string>> = {
  en: {
    // Nav
    'nav.dashboard': 'Dashboard',
    'nav.analysis': 'Analysis',
    'nav.chart': 'Charts',
    'nav.simulation': 'Simulation',
    'nav.portfolio': 'Portfolio',
    'nav.watchlist': 'Watchlist',
    'nav.orders': 'Orders',
    'nav.performance': 'Performance',
    'nav.alerts': 'Alerts',
    'nav.settings': 'Settings',
    'nav.logs': 'Logs',
    'nav.logout': 'Logout',
    'nav.analyzing': 'Analyzing...',
    'nav.running_in_bg': 'Running in background...',
    'nav.next_run': 'Next:',

    // Dashboard
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

    // Watchlist
    'watchlist.title': 'Watchlist',
    'watchlist.add': 'Add',
    'watchlist.loading': 'Loading...',
    'watchlist.empty': 'Watchlist is empty.',
    'watchlist.placeholder': 'Enter symbol (e.g. AAPL)',

    // General & Common
    'common.loading': 'Loading...',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.error': 'Error',
    'common.success': 'Success',
    'common.delete': 'Delete',
    'common.add': 'Add',
    'common.no_data': 'No data available',

    // Settings
    'settings.title': 'Settings',
    'settings.general': 'General Settings',
    'settings.language': 'App Language',
    'settings.llm_settings': 'LLM Settings',
    'settings.cron_settings': 'Scheduler (Cron) Settings',
    'settings.watchlist': 'Watchlist Assets',
    'settings.save_success': 'Settings saved successfully.',
    'settings.save_error': 'Failed to save settings.',

    // Logs
    'logs.title': 'System Logs',
    'logs.all_levels': 'All Levels',
    'logs.no_logs': 'No logs available.',
  },
  tr: {
    // Nav
    'nav.dashboard': 'Dashboard',
    'nav.analysis': 'Analiz',
    'nav.chart': 'Grafik',
    'nav.simulation': 'Simülasyon',
    'nav.portfolio': 'Portföy',
    'nav.watchlist': 'İzleme Listesi',
    'nav.orders': 'Emirler',
    'nav.performance': 'Performans',
    'nav.alerts': 'Alarmlar',
    'nav.settings': 'Ayarlar',
    'nav.logs': 'Loglar',
    'nav.logout': 'Çıkış',
    'nav.analyzing': 'analiz ediliyor',
    'nav.running_in_bg': 'Arka planda çalışıyor...',
    'nav.next_run': 'Sonraki:',

    // Dashboard
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

    // Watchlist
    'watchlist.title': 'İzleme Listesi',
    'watchlist.add': 'Ekle',
    'watchlist.loading': 'Yükleniyor...',
    'watchlist.empty': 'İzleme listesi boş.',
    'watchlist.placeholder': 'Sembol girin (örn. AAPL)',

    // General & Common
    'common.loading': 'Yükleniyor...',
    'common.save': 'Kaydet',
    'common.cancel': 'İptal',
    'common.error': 'Hata',
    'common.success': 'Başarılı',
    'common.delete': 'Sil',
    'common.add': 'Ekle',
    'common.no_data': 'Veri bulunamadı',

    // Settings
    'settings.title': 'Ayarlar',
    'settings.general': 'Genel Ayarlar',
    'settings.language': 'Uygulama Dili',
    'settings.llm_settings': 'LLM Ayarları',
    'settings.cron_settings': 'Zamanlayıcı (Cron) Ayarları',
    'settings.watchlist': 'İzlenecek Varlıklar',
    'settings.save_success': 'Ayarlar başarıyla kaydedildi.',
    'settings.save_error': 'Ayarlar kaydedilemedi.',

    // Logs
    'logs.title': 'Sistem Logları',
    'logs.all_levels': 'Tüm Seviyeler',
    'logs.no_logs': 'Log yok.',
  }
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

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
