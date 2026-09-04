from backend.schemas.schema_contracts import build_meta_schemas


def test_meta_schema_contract_is_cached_per_process() -> None:
    build_meta_schemas.cache_clear()

    first = build_meta_schemas()
    second = build_meta_schemas()
    info = build_meta_schemas.cache_info()

    assert first is second
    assert info.misses == 1
    assert info.hits == 1

    build_meta_schemas.cache_clear()
