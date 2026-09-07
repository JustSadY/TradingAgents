from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.schemas.tool_settings import ToolSettingsUpdate, ToolSettingUpdateValue
from backend.services.tool_settings_service import _apply_tool_setting_row_update, validate_tool_settings


def _tool():
    return SimpleNamespace(
        key="test_tool",
        default_enabled=True,
        settings_schema=[
            SimpleNamespace(key="visible", type="number", default=10, min=1, max=100, options=[]),
            SimpleNamespace(key="locked", type="string", default="server-default", min=None, max=None, options=[]),
        ],
    )


def test_partial_tool_settings_validation_does_not_materialize_missing_defaults():
    assert validate_tool_settings(_tool(), {"visible": 20}) == {"visible": 20.0}


def test_reset_tool_setting_removes_only_that_override():
    row = SimpleNamespace(enabled=True, settings={"visible": 20, "locked": "admin-value"})

    _apply_tool_setting_row_update(row, ToolSettingUpdateValue(reset_settings=["visible"]), _tool())

    assert row.settings == {"locked": "admin-value"}


@pytest.mark.asyncio
async def test_hidden_tool_field_cannot_be_changed_by_direct_request(monkeypatch):
    from backend.api import deps

    access_calls = 0

    async def allow_section(*args):
        return None

    async def access_snapshot(*args):
        nonlocal access_calls
        access_calls += 1
        return {
            "agent_access": {},
            "tool_access": {"test_tool": {"can_view": True, "can_edit": True, "can_enable": True}},
            "field_access": {"test_tool": {"locked": {"can_view": False, "can_edit": True}}},
        }

    monkeypatch.setattr(deps, "enforce_setting_section_permission", allow_section)
    monkeypatch.setattr(deps, "get_user_access_overrides", access_snapshot)
    monkeypatch.setattr(deps.registry, "get", lambda key: _tool() if key == "test_tool" else None)

    body = ToolSettingsUpdate(tools={"test_tool": ToolSettingUpdateValue(settings={"locked": "attempt"})})
    with pytest.raises(HTTPException) as exc:
        await deps.enforce_tool_settings_permission(SimpleNamespace(), SimpleNamespace(id=1, is_admin=False), body)

    assert exc.value.status_code == 403
    assert access_calls == 1
