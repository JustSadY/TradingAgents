# Multi-Tenant Architecture

TradingAgents supports multiple isolated users with role-based access control (RBAC).

## Overview

Each user has their own:
- **Analysis history** (`analysis_results.user_id`)
- **Portfolio** (`portfolios.user_id`)
- **Price alerts** (`price_alerts.user_id`)
- **App settings** (`app_settings.user_id`) — LLM provider, model, trading mode, etc.
- **Config presets** (`config_presets.user_id`)
- **AI API keys** (encrypted in `users.api_keys_enc`)

Admin users bypass all user_id filters and see all data across the system.

## Database Tables

| Table | Isolation Column | Notes |
|-------|-----------------|-------|
| `users` | — | Central identity table |
| `analysis_results` | `user_id` | nullable, legacy rows stay NULL |
| `portfolios` | `user_id` | nullable |
| `price_alerts` | `user_id` | nullable |
| `app_settings` | `user_id` | per-user LLM/trading preferences |
| `config_presets` | `user_id` | saved preset snapshots |
| `system_settings` | — | singleton (id=1), admin-only |
| `user_page_permissions` | `user_id` | per-user page access flags |

## Data Migration

Existing records keep `user_id = NULL` (legacy). New records are tagged with the
creating user's ID. Admins see both.

The migration runs automatically at startup via `create_all_tables()` in
`backend/core/database.py` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## Deployment Notes

- Set `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` in `.env` to auto-seed the admin
  user on first run.
- Set `ENCRYPTION_KEY` in `.env` to a 32-byte URL-safe base64 Fernet key for
  encrypting per-user API keys. Generate with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
