from __future__ import annotations

from types import SimpleNamespace

import backend.services.tool_settings_service as tool_settings_service
from backend.services.tool_settings_service import validate_tool_settings


def test_tool_validation_model_is_compiled_once_per_tool_instance(monkeypatch) -> None:
    create_calls = 0
    original_create_model = tool_settings_service.create_model
    tool = SimpleNamespace(
        key="__validation_cache_test__",
        settings_schema=[
            SimpleNamespace(
                key="limit",
                type="number",
                default=10,
                min=1,
                max=100,
                options=[],
            )
        ],
    )

    def counted_create_model(*args, **kwargs):
        nonlocal create_calls
        create_calls += 1
        return original_create_model(*args, **kwargs)

    monkeypatch.setattr(tool_settings_service, "create_model", counted_create_model)
    tool_settings_service._tool_validation_model_cache.pop(id(tool), None)

    try:
        assert validate_tool_settings(tool, {"limit": 20}) == {"limit": 20.0}
        assert validate_tool_settings(tool, {"limit": 30}) == {"limit": 30.0}
        assert create_calls == 1
    finally:
        tool_settings_service._tool_validation_model_cache.pop(id(tool), None)
