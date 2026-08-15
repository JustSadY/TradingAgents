from backend.core.catalog import LANGUAGES, LLM_CATALOG


def test_catalog_exposes_one_language_contract_for_all_litellm_models():
    expected = {item["value"] for item in LANGUAGES}
    assert expected

    for provider in LLM_CATALOG.values():
        for model in provider["models"]:
            assert set(model["supported_output_languages"]) == expected
