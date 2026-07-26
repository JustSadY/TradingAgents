import adminTranslations from '../admin'
import alertsTranslations from '../alerts'
import analysisTranslations from '../analysis'
import backtestTranslations from '../backtest'
import chartTranslations from '../chart'
import dashboardTranslations from '../dashboard'
import earningsCalendarTranslations from '../earnings_calendar'
import loginTranslations from '../login'
import logsTranslations from '../logs'
import mocktradingTranslations from '../mocktrading'
import ordersTranslations from '../orders'
import performanceTranslations from '../performance'
import portfolioTranslations from '../portfolio'
import profileTranslations from '../profile'
import screenerTranslations from '../screener'
import sectorRotationTranslations from '../sector_rotation'
import settingsTranslations from '../settings'
import sharedReportTranslations from '../shared_report'
import toolsTranslations from '../tools'

const CORE_EN: Record<string, string> = {
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
  'common.retry': 'Retry Connection',
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
}

const CORE_TR: Record<string, string> = {
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
  'common.retry': 'Yeniden Bağlan',
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

const PAGE_MODULES: { en: Record<string, string>; tr: Record<string, string> }[] = [
  adminTranslations,
  alertsTranslations,
  analysisTranslations,
  backtestTranslations,
  chartTranslations,
  dashboardTranslations,
  earningsCalendarTranslations,
  loginTranslations,
  logsTranslations,
  mocktradingTranslations,
  ordersTranslations,
  performanceTranslations,
  portfolioTranslations,
  profileTranslations,
  screenerTranslations,
  sectorRotationTranslations,
  settingsTranslations,
  sharedReportTranslations,
  toolsTranslations,
]

function loadAll(): { en: Record<string, string>; tr: Record<string, string> } {
  const en: Record<string, string> = { ...CORE_EN }
  const tr: Record<string, string> = { ...CORE_TR }
  for (const mod of PAGE_MODULES) {
    Object.assign(en, mod.en || {})
    Object.assign(tr, mod.tr || {})
  }
  return { en, tr }
}

const ALL = loadAll()
export const TRANSLATIONS_EN = ALL.en
export const TRANSLATIONS_TR = ALL.tr
