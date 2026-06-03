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

