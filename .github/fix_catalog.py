from pathlib import Path

catalog = Path("backend/core/catalog.py")
text = catalog.read_text(encoding="utf-8")
old_import = "from backend.trading_agents.llm_clients.capabilities import get_supported_output_languages\n"
if old_import not in text:
    raise SystemExit("stale capabilities import not found")
text = text.replace(old_import, "", 1)
old_call = '"supported_output_languages": get_supported_output_languages(value),'
if old_call not in text:
    raise SystemExit("stale capabilities call not found")
text = text.replace(
    old_call,
    '"supported_output_languages": [item["value"] for item in LANGUAGES],',
    1,
)
catalog.write_text(text, encoding="utf-8")

old_test = Path("backend/tests/test_core/test_llm_capabilities.py")
if old_test.exists():
    old_test.unlink()
Path("backend/tests/test_core/test_llm_catalog.py").write_text(
    '''from backend.core.catalog import LANGUAGES, LLM_CATALOG\n\n\ndef test_catalog_exposes_one_language_contract_for_all_litellm_models():\n    expected = {item["value"] for item in LANGUAGES}\n    assert expected\n\n    for provider in LLM_CATALOG.values():\n        for model in provider["models"]:\n            assert set(model["supported_output_languages"]) == expected\n''',
    encoding="utf-8",
)
