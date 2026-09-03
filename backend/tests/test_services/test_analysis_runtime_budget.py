from types import SimpleNamespace

from backend.services.analysis.config_builder import _effective_analyst_concurrency, build_analysis_config
from backend.trading_agents.default_config import DEFAULT_CONFIG


def _settings(provider: str = "openai", concurrency: int = 1):
    return SimpleNamespace(
        llm_provider=provider,
        llm_model="test-model",
        fallback_llm_chain=[],
        max_debate_rounds=1,
        output_language="English",
        investor_persona="conservative",
        analyst_concurrency_limit=concurrency,
    )


def test_default_analyst_tool_budget_is_bounded_to_four_rounds() -> None:
    assert DEFAULT_CONFIG["max_analyst_tool_turns"] == 4
    config = build_analysis_config(_settings())
    assert config["max_analyst_tool_turns"] == 4


def test_nvidia_parallelism_is_capped_for_small_provider_worker_pools() -> None:
    assert _effective_analyst_concurrency(_settings("nvidia", 8)) == 2


def test_hosted_parallelism_has_a_process_safe_ceiling() -> None:
    assert _effective_analyst_concurrency(_settings("openai", 8)) == 4


def test_user_can_still_choose_serial_analysis() -> None:
    assert _effective_analyst_concurrency(_settings("nvidia", 1)) == 1
