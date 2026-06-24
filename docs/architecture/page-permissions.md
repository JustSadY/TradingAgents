# Page Permissions (Feature Flags)

## Overview

Each regular user starts with access to **no pages** (except Preferences and Account & API Keys, which are always accessible). Admins/Owners explicitly grant access per page.

## Page Keys

| Key | Page |
|-----|------|
| `dashboard` | Dashboard |
| `analysis` | Analysis |
| `chart` | Charts |
| `trading` | Simulation / Mock Trading |
| `portfolio` | Portfolio |
| `watchlist` | Watchlist |
| `orders` | Orders |
| `performance` | Performance |
| `alerts` | Alerts |
| `ab-testing` | A/B Testing |
| `logs` | System Logs |
| `settings` | Settings (always allowed) |

Admin and Owner users implicitly have access to all pages plus `/admin`.

## Database

```sql
CREATE TABLE user_page_permissions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id),
    page_key VARCHAR(50) NOT NULL,
    allowed  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (user_id, page_key)
);
```

## API

| Endpoint | Who | Description |
|----------|-----|-------------|
| `GET /api/users/me/permissions` | Any auth user | Own allowed page list |
| `GET /api/users/{id}/permissions` | Admin/Owner | Per-user page permission map |
| `PUT /api/users/{id}/permissions` | Admin/Owner | Update page permissions |

`GET /api/users/me/permissions` returns:
```json
{ "allowed_pages": ["dashboard", "analysis", "settings"] }
```

## Frontend

`Layout.tsx` fetches `/api/users/me/permissions` on mount and filters the sidebar nav to only show allowed pages. The preferences link and admin link are always shown (filtered by role in the admin/owner case).

`RequireAdmin` component in `App.tsx` redirects non-admin/non-owner users away from `/admin`.

Backend `require_page(key)` dependency provides authoritative server-side enforcement.
