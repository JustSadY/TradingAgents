/**
 * SuperTokens session wiring for the PoC.
 *
 * Deliberately outside `src/`, which is the only directory `tsconfig.app.json`
 * includes — so this compiles nowhere, lints nowhere, and ships in no bundle
 * until someone decides to adopt it. Install the SDK first:
 *
 *     npm i supertokens-auth-react supertokens-web-js
 *
 * The interesting part of this file is not the init block. It is the three
 * notes below about what the current app does that SuperTokens sessions do not
 * do for free.
 */

import SuperTokens from 'supertokens-auth-react'
import EmailPassword from 'supertokens-auth-react/recipe/emailpassword'
import Session from 'supertokens-auth-react/recipe/session'

export function initSuperTokens() {
  SuperTokens.init({
    appInfo: {
      appName: 'TradingAgents',
      apiDomain: import.meta.env.VITE_API_DOMAIN ?? 'http://localhost:8000',
      websiteDomain: import.meta.env.VITE_WEBSITE_DOMAIN ?? 'http://localhost:5173',
      // The app already owns `/auth` for its own login/refresh/logout, so the
      // SDK is parked beside it rather than on top of it. A real migration has
      // to resolve that collision, not route around it.
      apiBasePath: '/auth/st',
      websiteBasePath: '/auth',
    },
    recipeList: [EmailPassword.init(), Session.init()],
  })
}

/**
 * What this replaces, and what it does not.
 *
 * 1. **The access token stops being readable.** `contexts/AuthContext`
 *    exposes `getAccessToken()`, and the app uses it in exactly one place that
 *    matters: `analysis/analysisSocket.ts` puts the JWT in a WebSocket
 *    subprotocol (`tradingagents.jwt.<token>`), because browsers cannot set
 *    headers on a WebSocket handshake and the repo deliberately refuses to put
 *    tokens in query strings. SuperTokens sessions live in httpOnly cookies —
 *    unreadable from JS by design. Cookies are sent on the WebSocket handshake,
 *    so the backend could read one there instead, but that is a rewrite of the
 *    handshake auth on both ends, not a configuration change. It is the largest
 *    single piece of work this migration implies.
 *
 * 2. **Refresh becomes the SDK's.** The app has its own rotating refresh
 *    tokens with replay detection and a 15-second multi-tab grace window
 *    (`api/auth.py`), plus `users.token_version` for revoking every session at
 *    once. SuperTokens has its own equivalents. Running both is not an option:
 *    two independent refresh mechanisms racing on the same tab is a bug
 *    generator, so the cutover has to be atomic per user.
 *
 * 3. **Role still comes from the API.** `AuthContext` reads `role` off the
 *    decoded JWT to drive route guards. A SuperTokens session can carry custom
 *    claims, but the authority for `is_admin` stays in `users.role` — see the
 *    note in `backend/poc/supertokens/bridge.py` — so the frontend should fetch
 *    it rather than trust a claim that a second store could contradict.
 */
