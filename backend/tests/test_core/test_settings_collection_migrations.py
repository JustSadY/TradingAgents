"""Regression coverage for retired settings collection formats."""

from __future__ import annotations

import json

from backend.core.migrations import (
    _normalize_fallback_chain_value,
    _normalize_preset_settings_collections,
    _normalize_webhook_events_value,
)


def test_webhook_event_normalizer_migrates_real_legacy_event_and_drops_phantom_event() -> None:
    events, discarded = _normalize_webhook_events_value(
        "analysis_complete, order_filled, risk_breach, analysis_complete"
    )

    assert events == ["analysis_complete", "trade_executed"]
    assert discarded is True

def test_webhook_event_normalizer_fails_closed_for_invalid_json_list() -> None:
    events, discarded = _normalize_webhook_events_value('["analysis_complete"')

    assert events == []
    assert discarded is True

def test_fallback_chain_normalizer_migrates_the_retired_field_pair() -> None:
    assert _normalize_fallback_chain_value(None, " NVIDIA ", " nvidia/nemotron ") == [
        {"provider": "nvidia", "model": "nvidia/nemotron"}
    ]

def test_fallback_chain_normalizer_keeps_an_existing_ordered_chain() -> None:
    assert _normalize_fallback_chain_value(
        [{"provider": "openai", "model": "gpt-4o-mini"}],
        "nvidia",
        "nvidia/nemotron",
    ) == [{"provider": "openai", "model": "gpt-4o-mini"}]

def test_preset_collection_normalizer_migrates_legacy_values_without_touching_other_settings() -> None:
    normalized, changed = _normalize_preset_settings_collections(
        json.dumps(
            {
                "investor_persona": "conservative",
                "webhook_events": "analysis_complete,order_filled,risk_breach",
                "fallback_llm_provider": "OpenAI",
                "fallback_llm_model": "gpt-4o-mini",
                "updated_at": "2026-07-29T00:00:00Z",
                "active_preset_name": "Old preset",
            }
        )
    )

    assert changed is True
    assert json.loads(normalized or "{}") == {
        "fallback_llm_chain": [{"provider": "openai", "model": "gpt-4o-mini"}],
        "investor_persona": "conservative",
        "webhook_events": ["analysis_complete", "trade_executed"],
    }

def test_invalid_preset_json_is_left_for_manual_repair() -> None:
    normalized, changed = _normalize_preset_settings_collections("{not-json")

    assert normalized is None
    assert changed is False
