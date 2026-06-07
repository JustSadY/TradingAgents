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


def test_owner_can_subscribe_others_cannot():
    register_task_owner("task-a", 5)
    try:
        assert is_task_owner("task-a", 5) is True
        assert is_task_owner("task-a", 6) is False
    finally:
        clear_task_owner("task-a")


def test_admin_may_observe_any_task():
    register_task_owner("task-b", 5)
    try:
        assert is_task_owner("task-b", 999, is_admin=True) is True
    finally:
        clear_task_owner("task-b")


def test_unknown_task_is_rejected():
    assert is_task_owner("never-issued", 5) is False


def test_system_owned_task_is_not_claimable():
    register_task_owner("task-sys", None)
    try:
        # A task with no owner (system/cron) must not be claimable by a user id.
        assert is_task_owner("task-sys", 5) is False
    finally:
        clear_task_owner("task-sys")


def test_cleared_task_is_rejected():
    register_task_owner("task-c", 5)
    clear_task_owner("task-c")
    assert is_task_owner("task-c", 5) is False
