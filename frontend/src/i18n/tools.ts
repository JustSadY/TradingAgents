const toolTranslations = {
  en: {
    // Categories
    'tools.category.market': 'Market & Technicals',
    'tools.category.news': 'News & Corporate Events',
    'tools.category.fundamentals': 'Fundamentals & SEC',
    'tools.category.sentiment': 'Social Sentiment',
    'tools.category.macro': 'Macroeconomics',
    'tools.category.options': 'Options Chain',
    'tools.category.quant': 'Quantitative Factors',
    'tools.category.chart': 'Interactive Charts',
    'tools.category.backtest': 'Backtesting & Performance',

    // Tool Labels
    'tools.core_stock_data.label': 'Core Stock Data',
    'tools.core_stock_data.description': 'Fetches historical stock prices, volume, and open-high-low-close candles.',
    'tools.core_stock_data.default_lookback_days': 'Default Lookback Days',

    'tools.technical_indicators.label': 'Technical Indicators',
    'tools.technical_indicators.description': 'Calculates SMA, EMA, RSI, MACD, and Bollinger Bands.',
    'tools.technical_indicators.default_lookback_days': 'Default Lookback Days',

    'tools.company_news.label': 'Company News',
    'tools.company_news.description': 'Retrieves company-specific news articles and headlines.',
    'tools.company_news.article_limit': 'Article Limit',

    'tools.global_news.label': 'Global News',
    'tools.global_news.description': 'Retrieves broader macroeconomic news and market-wide alerts.',
    'tools.global_news.article_limit': 'Article Limit',
    'tools.global_news.lookback_days': 'Lookback Days',

    'tools.insider_transactions.label': 'Insider Transactions (Standard)',
    'tools.insider_transactions.description': 'Pulls recent Form 4 filings representing standard insider buy/sell transactions.',

    'tools.fundamentals_data.label': 'Fundamentals Summary',
    'tools.fundamentals_data.description': 'Calculates valuation ratios, profit margins, and key financial ratios.',

    'tools.balance_sheet.label': 'Balance Sheet Statement',
    'tools.balance_sheet.description': 'Retrieves detailed assets, liabilities, and equity reports.',

    'tools.cashflow.label': 'Cash Flow Statement',
    'tools.cashflow.description': 'Retrieves cash inflows and outflows from operations, investing, and financing.',

    'tools.income_statement.label': 'Income Statement',
    'tools.income_statement.description': 'Retrieves corporate revenues, expenses, and net profit over time.',

    'tools.sec_filings.label': 'SEC Filings Search',
    'tools.sec_filings.description': 'Queries SEC Form 10-K, 10-Q, and corporate filing transcripts.',

    'tools.insider_transactions_deep.label': 'Insider Transactions (Deep)',
    'tools.insider_transactions_deep.description': 'Runs a deep analysis of insider transaction history and executive ownership levels.',

    'tools.reddit_sentiment.label': 'Reddit Sentiment',
    'tools.reddit_sentiment.description': 'Scrapes popular investment subreddits for stock mentions, upvotes, and sentiment ratios.',
    'tools.reddit_sentiment.limit': 'Post Scrape Limit',

    'tools.stocktwits_sentiment.label': 'StockTwits Sentiment',
    'tools.stocktwits_sentiment.description': 'Analyzes real-time retail message sentiment flow on StockTwits.',
    'tools.stocktwits_sentiment.limit': 'Message Limit',

    'tools.macro_data.label': 'Macroeconomic Data',
    'tools.macro_data.description': 'Fetches CPI, unemployment, and interest rate metrics.',

    'tools.options_data.label': 'Options Chain Data',
    'tools.options_data.description': 'Pulls open interest, volume ratios, and implied volatility surfaces.',

    'tools.quant_data.label': 'Quantitative Anomalies',
    'tools.quant_data.description': 'Examines returns volatility, statistical factor loadings, and returns anomalies.',

    'tools.chart_annotation.label': 'Chart Annotations',
    'tools.chart_annotation.description': 'Allows the AI to automatically draw arrows or support lines onto the chart.',

    'tools.custom_indicator.label': 'Custom Indicators Solver',
    'tools.custom_indicator.description': 'Enables the AI to calculate custom indicators mathematically (e.g. normalized spreads).',

    'tools.vision_chart_analysis.label': 'Vision Chart Recognition',
    'tools.vision_chart_analysis.description': 'Uses a vision model to visually recognize patterns on the chart image.',

    'tools.mtf_trend.label': 'Multi-Timeframe Trend Overlays',
    'tools.mtf_trend.description': 'Calculates higher-timeframe trend lines and maps them onto the daily chart.',

    'tools.strategy_backtest.label': 'Historical Backtesting',
    'tools.strategy_backtest.description': 'Executes local backtests of trading strategies on historical data.',

    'tools.search_web.label': 'SearXNG Web Search',
    'tools.search_web.description': 'Performs active web searches using SearXNG for real-time validation.',

    'tools.crypto_fear_greed.label': 'Crypto Fear & Greed Index',
    'tools.crypto_fear_greed.description': 'Pulls market sentiment indices for cryptocurrency assets.',

    'tools.past_performance.label': 'Historical Performance review',
    'tools.past_performance.description': 'Retrieves win-loss statistics and accuracy attributions of the AI agents.',
  },
  tr: {
    // Kategoriler
    'tools.category.market': 'Piyasa ve Teknik Analiz',
    'tools.category.news': 'Haberler ve Şirket Gelişmeleri',
    'tools.category.fundamentals': 'Temel Analiz ve SEC',
    'tools.category.sentiment': 'Sosyal Duygu Analizi',
    'tools.category.macro': 'Makroekonomi',
    'tools.category.options': 'Opsiyon Zinciri',
    'tools.category.quant': 'Kantitatif Faktörler',
    'tools.category.chart': 'Etkileşimli Grafikler',
    'tools.category.backtest': 'Geriye Dönük Test ve Performans',

    // Araç Başlıkları
    'tools.core_stock_data.label': 'Temel Hisse Senedi Verileri',
    'tools.core_stock_data.description': 'Geçmiş hisse senedi fiyatlarını, hacmini ve açılış-yüksek-düşük-kapanış mumlarını çeker.',
    'tools.core_stock_data.default_lookback_days': 'Varsayılan Geriye Dönük Gün Sayısı',

    'tools.technical_indicators.label': 'Teknik Göstergeler',
    'tools.technical_indicators.description': 'SMA, EMA, RSI, MACD ve Bollinger Bantlarını hesaplar.',
    'tools.technical_indicators.default_lookback_days': 'Varsayılan Geriye Dönük Gün Sayısı',

    'tools.company_news.label': 'Şirket Haberleri',
    'tools.company_news.description': 'Şirkete özel haber makalelerini ve manşetlerini çeker.',
    'tools.company_news.article_limit': 'Haber Limiti',

    'tools.global_news.label': 'Genel Haberler',
    'tools.global_news.description': 'Makroekonomik haberleri ve piyasa genelindeki uyarıları çeker.',
    'tools.global_news.article_limit': 'Haber Limiti',
    'tools.global_news.lookback_days': 'Geriye Dönük Gün Sayısı',

    'tools.insider_transactions.label': 'İçeriden Öğrenenlerin İşlemleri (Standart)',
    'tools.insider_transactions.description': 'Standart içeriden alım/satım işlemlerini temsil eden son Form 4 başvurularını çeker.',

    'tools.fundamentals_data.label': 'Temel Rasyolar Özeti',
    'tools.fundamentals_data.description': 'Değerleme oranlarını, kâr marjlarını ve temel finansal rasyoları hesaplar.',

    'tools.balance_sheet.label': 'Bilanço Tablosu',
    'tools.balance_sheet.description': 'Ayrıntılı varlık, yükümlülük ve özkaynak raporlarını getirir.',

    'tools.cashflow.label': 'Nakit Akış Tablosu',
    'tools.cashflow.description': 'Faaliyetlerden, yatırımlardan ve finansmandan kaynaklanan nakit giriş ve çıkışlarını getirir.',

    'tools.income_statement.label': 'Gelir Tablosu',
    'tools.income_statement.description': 'Zaman içindeki kurumsal gelirleri, giderleri ve net kârı getirir.',

    'tools.sec_filings.label': 'SEC Başvuruları Arama',
    'tools.sec_filings.description': 'SEC Form 10-K, 10-Q ve kurumsal bildirim metinlerini sorgular.',

    'tools.insider_transactions_deep.label': 'İçeriden Öğrenenlerin İşlemleri (Detaylı)',
    'tools.insider_transactions_deep.description': 'İçeriden öğrenenlerin işlem geçmişini ve yönetici sahiplik oranlarını derinlemesine analiz eder.',

    'tools.reddit_sentiment.label': 'Reddit Duygu Analizi',
    'tools.reddit_sentiment.description': 'Popüler yatırım subredditlerini hisse mentions, upvote ve duygu oranları için tarar.',
    'tools.reddit_sentiment.limit': 'Gönderi Tarama Limiti',

    'tools.stocktwits_sentiment.label': 'StockTwits Duygu Analizi',
    'tools.stocktwits_sentiment.description': 'StockTwits üzerindeki gerçek zamanlı bireysel yatırımcı mesaj duygu akışını analiz eder.',
    'tools.stocktwits_sentiment.limit': 'Mesaj Limiti',

    'tools.macro_data.label': 'Makroekonomik Veriler',
    'tools.macro_data.description': 'TÜFE, işsizlik ve faiz oranı metriklerini çeker.',

    'tools.options_data.label': 'Opsiyon Zinciri Verileri',
    'tools.options_data.description': 'Açık pozisyon sayısını, hacim oranlarını ve zımni volatilite yüzeylerini çeker.',

    'tools.quant_data.label': 'Kantitatif Sapmalar',
    'tools.quant_data.description': 'Fiyat getiri volatilitesini, istatistiksel faktör yüklerini ve getiri anomalilerini inceler.',

    'tools.chart_annotation.label': 'Grafik Notları',
    'tools.chart_annotation.description': 'Yapay zekanın grafik üzerine otomatik olarak oklar veya destek çizgileri çizmesine olanak tanır.',

    'tools.custom_indicator.label': 'Özel Gösterge Çözücü',
    'tools.custom_indicator.description': 'Yapay zekanın matematiksel olarak özel göstergeler hesaplamasını sağlar (örneğin normalize edilmiş spread).',

    'tools.vision_chart_analysis.label': 'Görsel Grafik Analizi',
    'tools.vision_chart_analysis.description': 'Grafik görselindeki formasyonları ve kalıpları tanımak için bir görsel analiz modeli kullanır.',

    'tools.mtf_trend.label': 'Çoklu Zaman Dilimi Trend Çizgileri',
    'tools.mtf_trend.description': 'Üst zaman dilimlerindeki trend çizgilerini hesaplar ve bunları günlük grafiğe yansıtır.',

    'tools.strategy_backtest.label': 'Geçmişe Dönük Strateji Testi',
    'tools.strategy_backtest.description': 'Geçmiş veriler üzerinde ticaret stratejilerinin yerel geriye dönük testlerini çalıştırır.',

    'tools.search_web.label': 'SearXNG Web Arama',
    'tools.search_web.description': 'Gerçek zamanlı doğrulama sağlamak amacıyla SearXNG kullanarak aktif web aramaları gerçekleştirir.',

    'tools.crypto_fear_greed.label': 'Kripto Korku ve Açgözlülük Endeksi',
    'tools.crypto_fear_greed.description': 'Kripto para varlıkları için piyasa duygu endekslerini çeker.',

    'tools.past_performance.label': 'Geçmiş Performans Değerlendirmesi',
    'tools.past_performance.description': 'Yapay zeka ajanlarının başarı-başarısızlık istatistiklerini ve doğruluk paylarını getirir.',
  }
}

export default toolTranslations
