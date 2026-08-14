from backend.core.catalog import LLM_CATALOG
from backend.trading_agents.llm_clients.capabilities import (
    get_supported_output_languages,
    supports_output_language,
)


def test_nemotron_3_language_support_is_explicit_and_case_insensitive():
    model = "nvidia/nemotron-3-super-120b-a12b"

    assert supports_output_language(model, "English") is True
    assert supports_output_language(model, "japanese") is True
    assert supports_output_language(model, "Turkish") is False
    assert get_supported_output_languages(model) == [
        "Chinese",
        "English",
        "French",
        "German",
        "Italian",
        "Japanese",
        "Spanish",
    ]

def test_unknown_model_language_support_is_not_guessed():
    assert supports_output_language("custom/unverified-model", "Turkish") is None
    assert get_supported_output_languages("custom/unverified-model") is None

def test_catalog_exposes_known_model_language_metadata():
    model = next(
        model
        for model in LLM_CATALOG["nvidia"]["models"]
        if model["value"] == "nvidia/nemotron-3-super-120b-a12b"
    )

    assert "Turkish" not in model["supported_output_languages"]
    assert "English" in model["supported_output_languages"]
