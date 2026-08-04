# TradingAgents Düzeltme Paketi — 2026-08-04

Bu paket, `docs/AUDIT_2026-08-04.md` denetimindeki üretim etkili bulgular için kaynak kod düzeltmelerini içerir. Öncelik sırası veri-zaman doğruluğu, analiz terminal durumu, kullanıcı verisi güvenliği, kuyruk güvenilirliği ve dağıtım bütünlüğüdür.

## Uygulanan kritik düzeltmeler

- **C-01 / H-01:** Analist araç limiti dolunca mesajları silmek yerine tool-free final rapor geçişi çalışıyor. Provider content block biçimleri ortak parser ile normalize ediliyor; boş sonuç için tek seferlik text-only recovery var.
- **C-02 / C-03:** Geçmiş tarihli koşularda güncel analist başarı ağırlıkları, sinyal sonuçları, canlı market pulse, aktif senaryolar, güncel portföy ve sonuç hafızaları dışlanıyor. Episodik ve QA hafızası `as_of` kesimi uyguluyor.
- **C-04 / M-20:** Analist cache anahtarları `trade_date` ve `temporal_mode` içeriyor. Historical mode stale fallback kullanmıyor; cache hit provenance kullanıcı akışına ekleniyor.
- **C-05:** Araçlar `point_in_time`, `date_bounded`, `live_only` olarak sınıflandırıldı. Historical mode live-only ve kayıtsız araçları fail-closed kapatıyor. Makro verisi seçilen tarih itibarıyla hesaplanıyor.
- **C-06:** Finansal tablolar yalnız dönem sonuna göre değil, filing/report tarihi veya konservatif 45/90 günlük yayın gecikmesine göre kesiliyor.

## Analiz, kuyruk ve kalıcılık

- `trade_date`, asset type ve tarih aralıkları merkezi ve strict doğrulanıyor; gelecek tarihler ve 3650 günü aşan backtest aralıkları reddediliyor.
- Worker hazırlık hataları terminal error yayımlayıp task metadata/owner/cancel kayıtlarını temizliyor.
- Dispatch başarısızlığında task owner geri alınıyor.
- Time-travel state değişikliği reset-only allowlist ile sınırlandı.
- Time-travel resume artık yeni gizli analiz satırı üretmiyor; seçilen sonucu aynı satırda yeniden yürütüyor ve eski türetilmiş rapor/metric alanlarını replay öncesi temizliyor.
- Review ve sentiment geçmiş sorguları yalnız tamamlanmış kayıtları ve doğru tarih sırasını kullanıyor.
- Multi-ticker, report chat, time-travel, assistant ve custom indicator yollarına rate limit eklendi.

## Historical AI davranışı

Geçmiş analiz artık canlı veriyle rapor uydurmak yerine veri kaynağı point-in-time desteklemiyorsa o aracı kapatır. Bunun sonucu olarak historical Options, Reddit/StockTwits, ownership, ratings, short interest, catalyst gibi live-only raporlar veri yok uyarısı verebilir. Bu davranış bilinçlidir: yanlış tarihli kesin rapor yerine açık eksik veri tercih edilir.

## Portfolio Assistant güvenliği

- Paper order ve alert işlemleri iki aşamalıdır: önce kısa ömürlü önizleme, sonra kullanıcı mesajındaki tek ve açık confirmation ID ile yürütme.
- Confirmation kullanıcıya bağlı, 10 dakika geçerli, tek kullanımlı ve concurrent çağrılarda atomik claim ile korunuyor.
- Assistant analiz başlatma normal ticker preflight ve merkezi queue yolunu kullanıyor.
- Tool/LLM exception ayrıntıları kullanıcıya ham olarak sızdırılmıyor.
- Tek assistant mesajında en fazla bir yan etkili işlem/önizleme çalıştırılıyor.

## Kimlik doğrulama ve tarayıcı verisi

- Refresh token JavaScript yanıtından ve `localStorage` alanından çıkarıldı; `HttpOnly`, `SameSite=Lax` cookie olarak saklanıyor.
- Access token ve son analiz çalışma durumu `sessionStorage` ile sekme/oturum kapsamına alındı; eski localStorage verileri migrate/temizleniyor.
- Logout, access token süresi dolmuş olsa bile refresh cookie'yi temizler; token version artırımı hesap genelinde revocation sağlar.
- Normal refresh token version artırmaz; böylece birden fazla tarayıcı sekmesi birbirinin access tokenını geçersiz kılmaz.

## Paylaşım, retention ve veri yaşam döngüsü

- Shared report için kullanıcı+analiz başına tek lifecycle satırı, rotate ve revoke endpointleri eklendi.
- Yalnız `completed` analizler paylaşılabilir.
- Cache, news cache, expired confirmation ve revoked/expired share kayıtları için günlük retention işi eklendi.
- PostgreSQL için üç Alembic migration, SQLite için idempotent additive normalizer eklendi.

## Backtest doğruluğu

- Consensus raporlarının inclusion/exclusion sayıları API'ye eklendi.
- Retroaktif oluşturulmuş ve işlem tarihinden sonra yaratılmış consensus raporları açıkça sayılıp dışlanıyor.
- Short işlemlere sabit %3 yıllık borrow financing maliyeti eklendi.
- Stop ve target aynı barda görülürse konservatif olarak stop önce kabul ediliyor ve varsayım API çıktısında açıklanıyor.
- Benchmark aynı commission ve slippage varsayımlarını kullanıyor.
- Short locate, margin call, dividend, tax ve değişken borrow rate'in modellenmediği API `assumptions` alanında belirtiliyor.

## Kurulum, CI ve dağıtım

- Destek sözleşmesi Python `>=3.11,<3.14` olarak hizalandı.
- İçeriği gerçek bağımlılıkları kilitlemeyen eski `uv.lock` kaldırıldı; `pyproject.toml` PEP 621 bağımlılık kaynağı olarak eklendi/güncellendi.
- GitHub Actions: Python 3.11/3.13, PostgreSQL migration, Ruff, Pyright, pytest+coverage, frontend lint/test/build kapıları eklendi.
- Update script izole worktree/venv preflight, kısa servis kesintisi, frontend/venv geri alma ve expand/contract migration kuralı kullanıyor.
- Production ortamında varsayılan secret/admin credential ile boot engelleniyor; development bootstrap parolası rastgele ve tek seferlik loglanıyor.

## Bilinen kalan sınırlar

- Backend için gerçek transitive lock dosyası bu çalışma ortamında paket kayıt sunucusu erişilemediği için üretilemedi. Yanıltıcı boş lock kaldırıldı; CI'da güvenilir registry üzerinden lock üretmek hâlâ önerilir.
- Frontend ana sayfalarının ve büyük orchestration servislerinin parçalanması yapısal refactor olarak bırakıldı; işlevsel hata düzeltmeleri uygulanmıştır.
- Historical live-only veri sağlayıcıları için arşiv sağlayıcı entegrasyonu eklenmedi; fail-closed davranış kullanılır.
- Gerçek broker short locate/margin/dividend modeli eklenmedi; eksik varsayımlar artık açıkça raporlanır.
