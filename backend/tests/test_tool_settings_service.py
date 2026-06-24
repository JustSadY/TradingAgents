from typing import Any

from backend.services.tool_settings_service import _get_pydantic_type


def test_get_pydantic_type_mapping():
    assert _get_pydantic_type("boolean") is bool
    assert _get_pydantic_type("number") is float
    assert _get_pydantic_type("string") is str
    assert _get_pydantic_type("textarea") is str
    assert _get_pydantic_type("secret") is str
    assert _get_pydantic_type("string_list") == list[str]
    assert _get_pydantic_type("select") is str
    assert _get_pydantic_type("multi_select") == list[str]
    assert _get_pydantic_type("nonexistent") == Any
