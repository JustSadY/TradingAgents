"""Regression tests for per-run config isolation.

``set_config`` previously mutated a single module-global dict, so concurrent
analysis runs (e.g. the portfolio orchestrator fanning out tickers, or several
alert-triggered analyses) could clobber each other's provider API keys,
persona, or output language. The config is now stored in a ContextVar that is
isolated per asyncio task and copied into ``asyncio.to_thread`` workers.
"""

import asyncio

import pytest

from backend.trading_agents.dataflows.config import get_config, set_config


@pytest.mark.asyncio
async def test_concurrent_runs_do_not_leak_config():
    async def run(name: str, lang: str, key: str):
        set_config(
            {
                "output_language": lang,
                "alpha_vantage_api_key": key,
                "nested": {"owner": name},
            }
        )
        # Yield so the sibling tasks interleave their set/read with ours.
        await asyncio.sleep(0.01)
        direct = get_config()
        # Worker threads must inherit this task's context.
        in_thread = await asyncio.to_thread(get_config)
        return name, direct, in_thread

    results = await asyncio.gather(
        run("A", "Turkish", "KEY_A"),
        run("B", "English", "KEY_B"),
        run("C", "German", "KEY_C"),
    )

    expected_lang = {"A": "Turkish", "B": "English", "C": "German"}
    for name, direct, in_thread in results:
        assert direct["output_language"] == expected_lang[name]
        assert direct["alpha_vantage_api_key"] == f"KEY_{name}"
        assert direct["nested"]["owner"] == name
        # The to_thread worker saw the same isolated config, not another run's.
        assert in_thread["output_language"] == expected_lang[name]


def test_omitted_keys_fall_back_to_defaults_not_previous_run():
    # First run sets a custom provider key.
    set_config({"alpha_vantage_api_key": "FROM_FIRST_RUN"})
    assert get_config()["alpha_vantage_api_key"] == "FROM_FIRST_RUN"

    # A later run in the same context that omits the key must not inherit it;
    # it should fall back to the pristine default baseline.
    set_config({"output_language": "Spanish"})
    cfg = get_config()
    assert cfg["output_language"] == "Spanish"
    assert cfg.get("alpha_vantage_api_key") != "FROM_FIRST_RUN"
