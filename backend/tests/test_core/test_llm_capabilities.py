from backend.core.catalog import LLM_CATALOG


def test_catalog_exposes_known_model_language_metadata():
    """Model presentation metadata lives in the catalog, not a second SDK layer."""
    model = next(
        model
        for model in LLM_CATALOG["nvidia"]["models"]
        if model["value"] == "nvidia/nemotron-3-super-120b-a12b"
    )

    assert "Turkish" not in model["supported_output_languages"]
    assert "English" in model["supported_output_languages"]
