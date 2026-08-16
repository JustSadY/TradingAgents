"""SuperTokens SDK initialisation for the PoC.

Kept apart from ``bridge.py`` on purpose. This module is the only one that
imports the SDK, so the identity-mapping rules — the part with real
consequences for tenancy — stay testable without the package installed and
without the core service running.

The SDK is not a production dependency. Install the PoC group first::

    uv sync --group supertokens-poc

Nothing in ``backend.main`` imports this. Wiring it in is
``docs/poc/supertokens.md`` step 3, and deliberately a manual edit: the PoC is
here to be evaluated, not to be switched on by a merge.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SuperTokensSettings:
    """Where the core lives and how this app identifies itself to it.

    The core is a separate service — a Java process listening on 3567 with its
    own storage. That is the operational cost of this design, and naming it in
    one dataclass is the honest way to keep it visible.
    """

    connection_uri: str = os.getenv("SUPERTOKENS_CONNECTION_URI", "http://localhost:3567")
    api_key: str = os.getenv("SUPERTOKENS_API_KEY", "")
    app_name: str = "TradingAgents"
    api_domain: str = os.getenv("SUPERTOKENS_API_DOMAIN", "http://localhost:8000")
    website_domain: str = os.getenv("SUPERTOKENS_WEBSITE_DOMAIN", "http://localhost:5173")
    #: SuperTokens mounts its own routes under this prefix. The application
    #: already owns `/auth` (login/refresh/logout), so during a migration the
    #: two would collide; the PoC parks SuperTokens elsewhere rather than
    #: pretending that conflict does not exist.
    api_base_path: str = "/auth/st"
    website_base_path: str = "/auth"


def init_supertokens(settings: SuperTokensSettings | None = None) -> None:
    """Initialise the SDK. Call once, before the FastAPI app handles requests."""
    from supertokens_python import InputAppInfo, SupertokensConfig, init
    from supertokens_python.recipe import emailpassword, session

    config = settings or SuperTokensSettings()

    init(
        app_info=InputAppInfo(
            app_name=config.app_name,
            api_domain=config.api_domain,
            website_domain=config.website_domain,
            api_base_path=config.api_base_path,
            website_base_path=config.website_base_path,
        ),
        supertokens_config=SupertokensConfig(
            connection_uri=config.connection_uri,
            api_key=config.api_key or None,
        ),
        framework="fastapi",
        # Deliberately minimal. Social login, MFA and passwordless are the
        # reasons to adopt SuperTokens at all, but adding them here would hide
        # the question the PoC is meant to answer behind features.
        recipe_list=[emailpassword.init(), session.init()],
        mode="asgi",
    )


async def bind_supertokens_user_to_app_user(supertokens_user_id: str, app_user_id: int) -> None:
    """Register the app's ``users.id`` as the SuperTokens external user id.

    This is the hinge of the whole design. Without it a verified session yields
    a UUID, which is not a ``users.id``, and the bridge refuses it — correctly,
    but every request would fail. Registering the mapping makes every later
    session hand back ``"41"`` instead.

    It also means the two stores must be kept in step: creating an application
    user and creating its SuperTokens user are two writes to two systems with
    no transaction across them, and so is deleting one. That is the standing
    cost of the second store, and there is no version of this design without
    it.
    """
    from supertokens_python.asyncio import create_user_id_mapping

    await create_user_id_mapping(
        supertokens_user_id=supertokens_user_id,
        external_user_id=str(app_user_id),
    )
