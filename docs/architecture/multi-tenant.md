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
| `analysis_results` | `user_id` | nullable; `NULL` denotes a system-owned run |
| `portfolios` | `user_id` | nullable |
| `price_alerts` | `user_id` | nullable |
| `app_settings` | `user_id` | per-user LLM/trading preferences |
| `config_presets` | `user_id` | saved preset snapshots |
| `system_settings` | — | singleton (id=1), admin-only |
| `user_page_permissions` | `user_id` | per-user page access flags |

## Data Migration

Historical records with no owner remain in the explicit system scope
(`user_id IS NULL`); they are never automatically attributed to an arbitrary
account. New user-initiated records carry the creating user's ID. User queries
must filter by that ID, while system jobs must filter with `IS NULL`; neither
may fall back to every tenant's records. Admin reporting can opt into an
all-user view explicitly.

PostgreSQL upgrades are versioned through Alembic. SQLite remains a local
development/test path and applies the small, idempotent compatibility updates
inside `create_all_tables()`.

## Deployment Notes

- The Server Owner is registered through the first-run setup screen, not from
  `.env`. `GET /auth/setup-status` reports an installation with no users and
  `POST /auth/setup` creates the single owner; both close permanently once any
  account exists.
- Set `ENCRYPTION_KEY` in `.env` to a 32-byte URL-safe base64 Fernet key for
  encrypting per-user API keys. Generate with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
