# SuperTokens PoC

Evaluation only. Nothing here is wired into the running application: no
production module imports `backend/poc/`, the frontend files sit outside the
directory `tsconfig.app.json` compiles, and the SDK is an optional dependency
group. Adopting it is a decision, not a merge.

## The question

Replacing the identity provider is easy to demonstrate and hard to be sure
about, because the easy demonstration — a login succeeds — exercises the half
that was never in doubt.

What was in doubt is tenancy. Every tenant-owned table in this schema carries
the same row-level security policy, created by revision `7f8091a2b3c4` for
every table with a `user_id` column:

```sql
current_setting('app.is_admin', true) = 'true'
OR user_id = NULLIF(current_setting('app.user_id', true), '')::bigint
```

Isolation is therefore enforced by PostgreSQL against a `bigint`, across ~700
`user_id` references in ~100 files, and it is keyed on the integer `users.id`.
SuperTokens identifies people by UUID.

## The answer

It survives, and the reason is narrow enough to state in one sentence:
SuperTokens' own user-ID mapping lets the application's integer `users.id` be
registered as the *external* user id, so a verified session yields `"41"`
rather than a UUID, and the RLS context is established exactly as it is today.

That claim is not argued in this document. `backend/tests/test_poc/
test_supertokens_rls.py` migrates a throwaway database to Alembic head, binds
sessions through the bridge, and reads a real tenant table:

```
tests/test_poc/test_supertokens_bridge.py   12 passed   (mapping rules, SQLite)
tests/test_poc/test_supertokens_rls.py       5 passed   (isolation, PostgreSQL 16)
```

Run the second one against a database you may drop:

```bash
MIGRATION_DRIFT_DATABASE_URL=postgresql+asyncpg://postgres@localhost/ta_poc \
    uv run pytest tests/test_poc/test_supertokens_rls.py
```

Two things that harness gets right, and any replacement for it must too:

* **It connects as a role RLS applies to.** PostgreSQL exempts superusers and
  table owners from row-level security. A test that connects as the migrating
  role sees every tenant's rows and passes nothing;
  `deploy/provision-postgres-roles.sh` is where the real deployment splits the
  schema-owning migrator from a `NOBYPASSRLS` runtime role, and the fixture
  reproduces that split.
* **It checks the fail-open case explicitly.** With no context established, a
  tenant query does not error and does not deny — `NULLIF('', '')::bigint`
  compares NULL and the endpoint returns an empty, entirely plausible result.
  That is why `bridge.py` refuses an unmappable session instead of letting it
  through.

## What it costs

The auth code this would delete is small and was recently modernised:

| File | Lines | |
| --- | --- | --- |
| `api/auth.py` | 161 | login / refresh / logout |
| `schemas/auth.py` | 20 | |
| `core/security.py` | 107 | about half is `encrypt_secret`/`decrypt_secret` for provider credentials — stays either way |

What it adds:

* **A service.** The core is a Java process on 3567 with its own storage, to
  run, monitor, back up and upgrade. `deploy/supertokens/docker-compose.poc.yml`
  points it at the application's PostgreSQL under a separate schema so one
  backup covers both.
* **~20 packages**, including twilio, pyotp, phonenumbers and a second HTTP
  stack (aiohttp alongside the existing httpx).
* **A second user store.** `users` cannot go away: RBAC, per-user settings,
  encrypted provider credentials, presets, alerts, paper trading and analyses
  all key on it, with the delete-cascade repaired in `b2d49d4`. So user
  creation and deletion become two writes to two systems with no transaction
  across them. This is the same class of bug as that cascade drift — one thing
  described in two places with nothing checking they agree — except that half
  of it lives in another process, where `alembic check` cannot reach it.
* **The WebSocket handshake.** `analysis/analysisSocket.ts` authenticates by
  putting the JWT in a subprotocol, because browsers cannot set headers on a
  WebSocket handshake and this repo deliberately refuses query-string tokens.
  SuperTokens sessions are httpOnly cookies, unreadable from JS. Cookies do
  reach the handshake, so the backend can read one there — but that is a
  rewrite of handshake auth on both ends. It is the largest single piece of
  work this migration implies, and it is not covered by this PoC.

## What is unproven

**The core service was never started.** This environment has no Docker daemon,
and `supertokens.com` and arbitrary GitHub release downloads are both blocked by
its egress proxy, so the compose file, the SDK init and the FastAPI adapter are
written and reviewed but not executed. Concretely, still to verify on a machine
that can run the core:

1. `init()` succeeds against a live core and mounts `/auth/st/*`.
2. `create_user_id_mapping` binds a signed-up user to an existing `users.id`,
   and `get_user_id()` then returns that integer as a string.
3. Sign-up, sign-in, refresh and sign-out round-trip from the browser.
4. `/api/poc/supertokens/my-presets` returns only the caller's rows against the
   live stack — the same assertion `test_supertokens_rls.py` already makes
   directly against PostgreSQL.

Steps 1–3 are the part nobody doubts. Step 4 is the one that matters, and it is
the one already proven.

## Running it

```bash
cd backend && uv sync --group supertokens-poc
cd frontend && npm i supertokens-auth-react supertokens-web-js

# SUPERTOKENS_API_KEY must be set in .env
docker compose -f docker-compose.yml \
               -f deploy/supertokens/docker-compose.poc.yml up -d
```

Then wire it in by hand — `init_supertokens()` at startup, SuperTokens'
middleware and CORS headers on the app, and `poc.supertokens.routes.router`
included. Left manual on purpose.

## Recommendation

The tenancy risk is real but answered: it works, and the seam is one function.

The maintenance-cost argument still does not hold. About 200 lines of
recently-modernised auth code come out; a service, ~20 packages, a second user
store and a WebSocket rewrite go in.

The case that does hold is capability. Social login, MFA, passwordless and a
user-management dashboard are things nobody here wants to write, and
SuperTokens gives all four. If those are wanted, this is a reasonable way to
get them and the tenancy model will not fight it. If they are not, this
migration buys a harder deployment.
