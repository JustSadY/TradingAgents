# Doğrulama Kaydı — 2026-08-04

## Başarılı kontroller

- Python `compileall`: başarılı.
- Python AST taraması: 432 kaynak dosya, 0 parse hatası.
- TypeScript/TSX parser taraması: 135 dosya, 0 parse hatası.
- JSON (JSONC tsconfig hariç) ve TOML parse: başarılı.
- `deploy/update.sh` Bash syntax: başarılı.
- Alembic revision graph: 12 revision, tek head `f708192a3b4c`, eksik parent yok.
- Pydantic schema contract smoke test: başarılı.
- Historical date/range helper smoke test: başarılı.
- Provider content-block rapor parser smoke test: başarılı.
- Backtest Decimal P&L, short financing ve konservatif intrabar stop smoke test: başarılı.

## Çalıştırılamayan tam kontroller

Bu inceleme ortamında `aiosqlite`, `asyncpg`, `langgraph`, `langchain_core`, `yfinance`, `redis` ve frontend `node_modules` yoktu. Paket kayıt sunucusu bağımlılık çözümünde 404/erişim hatası verdi. Bu nedenle aşağıdakiler burada tam çalıştırılamadı:

- Tüm backend pytest paketi
- Gerçek PostgreSQL Alembic upgrade
- Frontend Vitest/lint/Vite production build
- Gerçek LLM/provider ve market-data integration testleri

CI workflow bu kontrolleri normal paket registry erişimi olan temiz ortamda çalıştıracak şekilde eklendi. Paket deploy edilmeden önce CI'nın tamamen yeşil olması gerekir.
