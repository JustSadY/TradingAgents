# Role-Based Access Control (RBAC)

## Roles

| Role | Description |
|------|-------------|
| `owner` | **Server Owner:** Highest level role. Immutable and cannot be demoted, deactivated, or deleted. Only one account can have this role (seeded on startup). Can promote/demote users between `user` and `admin`, and create administrator accounts. Cannot assign the `owner` role to any other account. |
| `admin` | **Administrator:** Managed by the Server Owner. Can create regular user accounts and edit user data, but **cannot modify roles or change admin status** (their own or anyone else's). Can manage global system settings and override user API keys. |
| `user` | **Regular User:** Access restricted to explicitly granted pages; can only edit settings sections permitted by the Administrator/Owner. |

## JWT Payload

```json
{
  "sub": "username",
  "role": "admin", // Can be 'owner', 'admin', or 'user'
  "type": "access",
  "exp": 1234567890
}
```

The `role` claim is decoded by the frontend `useAuth` hook to drive UI visibility.

## FastAPI Dependencies

| Dependency | Purpose |
|-----------|---------|
| `get_current_user` | Decode JWT, load full `User` ORM object |
| `require_admin` | Raise 403 if `user.role` is not `'admin'` or `'owner'` |
| `require_page(key)` | Check `user_page_permissions` table; admins/owners bypass |

## Owner Seeding

On startup, `_seed_admin_user()` in `main.py` reads `ADMIN_USERNAME` from `.env` and creates (or upgrades) the initial user to `role='owner'`. Only one owner exists in the system.

## Permission Matrix

| Resource | Owner | Admin | User (granted) | User (not granted) |
|----------|-------|-------|---------------|-------------------|
| Own data | ✓ | ✓ | ✓ | ✓ |
| Other users' data | ✓ | ✓ | ✗ | ✗ |
| User management (create user, modify password/email) | ✓ | ✓ | ✗ | ✗ |
| User role change (promote/demote admin) | ✓ | ✗ | ✗ | ✗ |
| Promote/demote to owner | ✗ | ✗ | ✗ | ✗ |
| Delete/demote owner | ✗ | ✗ | ✗ | ✗ |
| System settings (`/api/system-settings`) | ✓ | ✓ | ✗ | ✗ |
| Allowed page | ✓ | ✓ | ✓ | ✗ (403) |
| Preferences page | ✓ | ✓ | ✓ | ✓ (always open) |
| Admin page (`/admin`) | ✓ | ✓ | ✗ | ✗ |
| User-specific Cron | ✓ | ✓ | ✓ (if permitted) | ✗ |
| Global System Cron | ✗ | ✗ | ✗ | ✗ (Removed) |
| System logs (`/api/logs`) | ✓ | ✓ | ✗ | ✗ |
| My scoped logs (`/api/logs/me`) | ✓ | ✓ | ✓ (if `logs` page permitted) | ✗ |

## Settings Permission System

Administrators can granularly control which parts of the "Settings" page a user can modify. This is managed via the **Access Control** tab in the Admin panel.

| Section | Key | Controlled Fields |
|---------|-----|-------------------|
| Preferences | `general` | Mode, Broker, Language, Persona, Benchmark |
| AI Engine | `llm` | Provider, Model, API URL, Analysts |
| Risk & Safety | `risk` | Position limits, Risk per trade, Debate rounds |
| Alerts | `webhooks` | Webhook URL and notification events |
| Scheduler | `cron` | **User-specific** automated scan schedule |
| Templates | `presets` | Saving and applying configuration presets |

System notifications (toasts) and banners are filtered based on the active session role:

| Notification Type | Visibility | Description |
|-------------------|------------|-------------|
| **General Alerts** | Everyone (`all`) | Task progress, successful saves, analysis completions. |
| **System Admin Alerts** | `admin` + `owner` | Admin panel changes, system-level logs (if enabled). |
| **Update Available** | `owner` Only | Notifications about new git commits/releases on the upstream repository. |
| **System Updating...** | Everyone (`all`) | Active update process alerts informing users that the service is restarting. |

