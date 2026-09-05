from __future__ import annotations

from backend.models.tool_settings import UserAgentAccess, UserToolAccess, UserToolFieldAccess
from backend.services.tool_access_service import get_user_access_overrides


async def test_access_override_snapshot_combines_agent_tool_and_field_rows(db_session, test_user) -> None:
    db_session.add_all(
        [
            UserAgentAccess(user_id=test_user.id, agent_key="market", can_run=False),
            UserToolAccess(
                user_id=test_user.id,
                tool_key="search_web",
                can_view=True,
                can_use=False,
                can_edit=True,
                can_enable=False,
            ),
            UserToolFieldAccess(
                user_id=test_user.id,
                tool_key="search_web",
                field_key="searxng_url",
                can_view=False,
                can_edit=True,
            ),
        ]
    )
    await db_session.flush()

    snapshot = await get_user_access_overrides(db_session, test_user.id)

    assert snapshot["agent_access"] == {"market": False}
    assert snapshot["tool_access"]["search_web"] == {
        "can_view": True,
        "can_use": False,
        "can_edit": True,
        "can_enable": False,
    }
    assert snapshot["field_access"]["search_web"]["searxng_url"] == {
        "can_view": False,
        "can_edit": True,
    }
