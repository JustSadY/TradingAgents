# Role-Based Access Control (RBAC)

## Roles

| Role | Description |
|------|-------------|
| `admin` | Full access to all data, all pages, user management, system settings |
| `user` | Access only to explicitly granted pages; sees only own data |

## JWT Payload

```json
{
  "sub": "username",
  "role": "admin",
  "type": "access",
  "exp": 1234567890
}
```

The `role` claim is decoded by the frontend `useAuth` hook to drive UI visibility.

## FastAPI Dependencies

| Dependency | Purpose |
|-----------|---------|
| `get_current_user` | Decode JWT, load full `User` ORM object |
| `require_admin` | Raise 403 if `user.role != 'admin'` |
| `require_page(key)` | Check `user_page_permissions` table; admin bypasses |

## Admin Seeding

On startup, `_seed_admin_user()` in `main.py` reads `ADMIN_USERNAME` from `.env`
and creates (or upgrades) the user to `role='admin'`.

## Permission Matrix

| Resource | Admin | User (granted) | User (not granted) |
|----------|-------|---------------|-------------------|
| Own data | ✓ | ✓ | ✓ |
| Other users' data | ✓ | ✗ | ✗ |
| User management (`/api/users`) | ✓ | ✗ | ✗ |
| System settings (`/api/system-settings`) | ✓ | ✗ | ✗ |
| Allowed page | ✓ | ✓ | ✗ (403) |
| Settings page | ✓ | ✓ | ✓ (always open) |
| Admin page (`/admin`) | ✓ | ✗ | ✗ |
