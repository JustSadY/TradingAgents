from __future__ import annotations

from backend.schemas.meta import MetaResponse
from backend.schemas.schema_contracts import build_meta_schemas


def test_meta_response_schema_covers_every_catalog_field():
    assert set(MetaResponse.model_fields) == {
        "analysts", "tools", "agents", "section_labels", "signals", "asset_types", "languages",
        "data_vendors", "trading_modes", "brokers", "provider_labels", "investor_personas",
        "effort_options", "order_statuses", "order_actions", "chart_periods", "page_keys",
        "setting_keys", "sections", "webhook_events", "memory_stores", "embedders",
        "analysis_event_types",
    }


def test_settings_schema_defaults_come_from_pydantic_model():
    from backend.schemas.settings import SettingsBase

    contract = build_meta_schemas()
    props = contract.settings.json_schema["properties"]
    assert props["llm_provider"]["default"] == SettingsBase.model_fields["llm_provider"].default
    assert props["memory_store"]["default"] == SettingsBase.model_fields["memory_store"].default
    assert contract.settings.ui_schema["fields"]["active_preset_name"]["readOnly"] is True


def test_schema_endpoint_never_contains_nonempty_secret_defaults():
    contract = build_meta_schemas().model_dump(mode="json")
    for bundle in list(contract["tools"].values()) + list(contract["agents"].values()):
        fields = bundle["ui_schema"].get("fields", {})
        for name, ui in fields.items():
            if ui.get("secret"):
                assert ui.get("default") in (None, ""), name
                prop = bundle["json_schema"]["properties"][name]
                assert prop.get("default") in (None, "")
