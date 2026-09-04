from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from backend.models.page_permission import SECTION_FIELDS
from backend.schemas.settings import SettingsBase, SettingsUpdate


class SchemaBundle(BaseModel):
    json_schema: dict[str, Any]
    ui_schema: dict[str, Any]
    settings_schema: list[dict[str, Any]] | None = None


class MetaSchemasResponse(BaseModel):
    schema_version: int = 1
    settings: SchemaBundle
    tools: dict[str, SchemaBundle]
    agents: dict[str, SchemaBundle]


_ADVANCED_SETTINGS = {
    "max_recur_limit",
    "node_retry_attempts",
    "node_retry_base_delay",
    "node_timeout_seconds",
    "tool_timeout_seconds",
    "circuit_breaker_threshold",
    "circuit_breaker_cooldown",
    "stall_timeout_seconds",
    "max_report_chars_in_prompts",
    "max_debate_history_chars",
    "max_tool_output_chars",
}


def _field_section(name: str) -> str:
    for section, fields in SECTION_FIELDS.items():
        if name in fields:
            return section
    return "advanced"


def _unwrap_nullable(schema: dict[str, Any]) -> dict[str, Any]:
    for candidate in schema.get("anyOf", []):
        if candidate.get("type") != "null":
            return candidate
    return schema


def _widget(name: str, schema: dict[str, Any]) -> str:
    core = _unwrap_nullable(schema)
    if name.endswith("_url"):
        return "url"
    if core.get("enum"):
        return "select"
    if core.get("type") == "boolean":
        return "toggle"
    if core.get("type") in {"integer", "number"}:
        return "number"
    if core.get("type") == "array":
        return "list"
    return "text"


def _default_for(name: str) -> Any:
    field = SettingsBase.model_fields[name]
    default = field.get_default(call_default_factory=True)
    return None if default is PydanticUndefined else default


def _copy_constraints(target: dict[str, Any], update_prop: dict[str, Any]) -> None:
    source = _unwrap_nullable(update_prop)
    for key in (
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "pattern",
        "enum",
    ):
        if key in source:
            target[key] = source[key]


def build_settings_schema_bundle() -> SchemaBundle:
    json_schema = SettingsBase.model_json_schema()
    update_schema = SettingsUpdate.model_json_schema()
    properties = json_schema.setdefault("properties", {})
    update_properties = update_schema.get("properties", {})
    update_fields = set(SettingsUpdate.model_fields)
    ui_fields: dict[str, dict[str, Any]] = {}

    for order, (name, prop) in enumerate(properties.items(), start=1):
        if name in update_properties:
            _copy_constraints(prop, update_properties[name])
        default = _default_for(name)
        if default is not None or SettingsBase.model_fields[name].default is None:
            prop["default"] = default
        core = _unwrap_nullable(prop)
        title = str(prop.get("title") or name.replace("_", " ").title())
        description = str(prop.get("description") or title)
        enum = core.get("enum")
        ui_fields[name] = {
            "title": title,
            "description": description,
            "default": default,
            "minimum": core.get("minimum"),
            "maximum": core.get("maximum"),
            "enum": enum,
            "section": _field_section(name),
            "order": order,
            "widget": _widget(name, prop),
            "advanced": name in _ADVANCED_SETTINGS or _field_section(name) == "advanced",
            "secret": False,
            "readOnly": name not in update_fields,
        }

    return SchemaBundle(json_schema=json_schema, ui_schema={"fields": ui_fields})


def _field_json_schema(field: dict[str, Any]) -> dict[str, Any]:
    field_type = str(field.get("type") or "string")
    schema: dict[str, Any] = {
        "title": str(field.get("label_key") or field.get("key") or "Setting"),
    }
    description = field.get("description_key")
    if description:
        schema["description"] = description
    if field_type == "boolean":
        schema["type"] = "boolean"
    elif field_type == "number":
        schema["type"] = "number"
    elif field_type in {"multi_select", "string_list"}:
        schema["type"] = "array"
        item: dict[str, Any] = {"type": "string"}
        options = field.get("options") or []
        if options:
            item["enum"] = [option.get("value") for option in options]
        schema["items"] = item
    else:
        schema["type"] = "string"
        options = field.get("options") or []
        if options:
            schema["enum"] = [option.get("value") for option in options]
    if field.get("min") is not None:
        schema["minimum"] = field["min"]
    if field.get("max") is not None:
        schema["maximum"] = field["max"]
    if field.get("secret"):
        schema["writeOnly"] = True
    elif "default" in field:
        schema["default"] = field.get("default")
    return schema


def _registry_bundle(settings_schema: list[dict[str, Any]], *, section: str) -> SchemaBundle:
    properties: dict[str, Any] = {}
    required: list[str] = []
    ui_fields: dict[str, dict[str, Any]] = {}
    sanitized_settings: list[dict[str, Any]] = []
    for order, raw in enumerate(settings_schema, start=1):
        field = dict(raw)
        key = str(field["key"])
        secret = bool(field.get("secret") or field.get("type") == "secret")
        if secret and field.get("default"):
            field["default"] = None
        sanitized_settings.append(field)
        prop = _field_json_schema(field)
        properties[key] = prop
        if field.get("required"):
            required.append(key)
        ui_fields[key] = {
            "title": str(field.get("label_key") or key),
            "description": str(field.get("description_key") or field.get("label_key") or key),
            "default": None if secret else field.get("default"),
            "minimum": field.get("min"),
            "maximum": field.get("max"),
            "enum": prop.get("enum") or (prop.get("items") or {}).get("enum"),
            "section": section,
            "order": order,
            "widget": str(field.get("type") or "string"),
            "advanced": bool(field.get("advanced", False)),
            "secret": secret,
            "readOnly": False,
        }
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return SchemaBundle(
        json_schema=schema,
        ui_schema={"fields": ui_fields},
        settings_schema=sanitized_settings,
    )


@lru_cache(maxsize=1)
def build_meta_schemas() -> MetaSchemasResponse:
    """Build immutable meta schemas once per process."""
    # Bootstrap is import-idempotent and only registers local tool classes; it
    # does not perform network or database work.
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401
    from backend.schemas.meta import AgentMeta
    from backend.schemas.tool_settings import ToolMeta
    from backend.trading_agents.agent_catalog import list_agents
    from backend.trading_agents.agents.tools import registry

    tools: dict[str, SchemaBundle] = {}
    for raw in registry.metadata():
        model = ToolMeta.model_validate(raw)
        payload = model.model_dump()
        tools[model.key] = _registry_bundle(payload["settings_schema"], section=f"tool:{model.key}")

    agents: dict[str, SchemaBundle] = {}
    for agent in list_agents():
        model = AgentMeta.model_validate(agent.metadata())
        payload = model.model_dump()
        agents[model.key] = _registry_bundle(payload["settings_schema"], section=f"agent:{model.key}")

    return MetaSchemasResponse(
        settings=build_settings_schema_bundle(),
        tools=tools,
        agents=agents,
    )