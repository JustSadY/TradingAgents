"""Tests for analysis task ownership used to authorize WebSocket streams.

Previously the /ws/analysis/{task_id} endpoint validated the JWT but never
checked that the task belonged to the connecting user, so any authenticated
user could read another user's analysis stream.
"""

from backend.services.analysis_service import (
    clear_task_owner,
    is_task_owner,
    register_task_owner,
)


async def test_owner_can_subscribe_others_cannot():
    await register_task_owner("task-a", 5)
    try:
        assert await is_task_owner("task-a", 5) is True
        assert await is_task_owner("task-a", 6) is False
    finally:
        await clear_task_owner("task-a")


async def test_admin_may_observe_any_task():
    await register_task_owner("task-b", 5)
    try:
        assert await is_task_owner("task-b", 999, is_admin=True) is True
    finally:
        await clear_task_owner("task-b")


async def test_unknown_task_is_rejected():
    assert await is_task_owner("never-issued", 5) is False


async def test_system_owned_task_is_not_claimable():
    await register_task_owner("task-sys", None)
    try:
        # A task with no owner (system/cron) must not be claimable by a user id.
        assert await is_task_owner("task-sys", 5) is False
    finally:
        await clear_task_owner("task-sys")


async def test_cleared_task_is_rejected():
    await register_task_owner("task-c", 5)
    await clear_task_owner("task-c")
    assert await is_task_owner("task-c", 5) is False
