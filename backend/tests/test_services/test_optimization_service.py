"""Parameter search over the real backtest.

The backtest itself is stubbed here — what matters is the search contract:
that proposals stay inside the strategy's declared space, that a trial which
did not produce a usable backtest cannot win, and that a baseline is measured
so "better" means better than the shipped defaults.
"""

from __future__ import annotations

import pytest

from backend.services import optimization_service as opt
from backend.services.backtest_service import STRATEGY_PARAM_SPACE, strategy_defaults
from backend.services.optimization_service import (
    OBJECTIVES,
    OptimizationError,
    _score,
    optimizable_strategies,
    optimize_strategy,
)

pytest.importorskip("optuna", reason="parameter optimization requires the optuna package")


def _backtest_result(**overrides):
    base = {
        "total_return": 10.0,
        "sharpe_ratio": 1.0,
        "max_drawdown": -5.0,
        "win_rate": 55.0,
        "trades_count": 12,
        "final_value": 110_000.0,
        "calmar_ratio": 2.0,
    }
    base.update(overrides)
    return base


class TestCatalog:
    def test_only_strategies_with_a_space_are_optimizable(self):
        strategies = optimizable_strategies()
        assert set(strategies) == {"macd_crossover", "rsi_oversold"}
        # consensus replays stored analyses; there is nothing to tune.
        assert "consensus" not in strategies

    def test_every_objective_declares_a_direction_and_label(self):
        for spec in OBJECTIVES.values():
            assert spec["direction"] == "maximize"
            assert spec["label"]


class TestScoring:
    @pytest.mark.parametrize(
        ("objective", "expected"),
        [("sharpe_ratio", 1.0), ("total_return", 10.0), ("win_rate", 55.0), ("calmar", 2.0)],
    )
    def test_each_objective_reads_its_metric(self, objective, expected):
        assert _score(objective, _backtest_result()) == pytest.approx(expected)

    def test_calmar_falls_back_to_raw_return_without_a_ratio(self):
        assert _score("calmar", _backtest_result(calmar_ratio=None)) == pytest.approx(10.0)

    def test_a_failed_backtest_has_no_score(self):
        assert _score("sharpe_ratio", {"error": "no data"}) is None
        assert _score("sharpe_ratio", None) is None

    def test_a_strategy_that_barely_trades_has_no_score(self):
        """Otherwise 'never traded' wins on drawdown and win rate."""
        assert _score("win_rate", _backtest_result(trades_count=1)) is None
        assert _score("total_return", _backtest_result(trades_count=0)) is None

    def test_non_finite_metrics_are_rejected(self):
        assert _score("sharpe_ratio", _backtest_result(sharpe_ratio=float("inf"))) is None
        assert _score("sharpe_ratio", _backtest_result(sharpe_ratio="nonsense")) is None


class TestSearch:
    async def test_finds_the_parameters_that_score_best(self, monkeypatch):
        """A planted optimum must be the reported best."""

        async def fake_backtest(db, **kwargs):
            params = kwargs["strategy_params"]
            # Reward RSI periods near 25 so the search has a real target.
            distance = abs(params["rsi_period"] - 25)
            return _backtest_result(sharpe_ratio=5.0 - distance * 0.1)

        monkeypatch.setattr(opt, "run_backtest_simulation", fake_backtest)

        result = await optimize_strategy(
            None,
            ticker="nvda",
            strategy_type="rsi_oversold",
            start_date="2024-01-01",
            end_date="2024-12-31",
            n_trials=25,
        )

        assert result.ticker == "NVDA"
        assert result.trials_completed == 25
        assert abs(result.best_params["rsi_period"] - 25) <= 5
        assert result.best_value == max(t.value for t in result.trials if t.value is not None)

    async def test_measures_the_shipped_defaults_as_a_baseline(self, monkeypatch):
        seen: list[dict] = []

        async def fake_backtest(db, **kwargs):
            seen.append(kwargs["strategy_params"])
            return _backtest_result()

        monkeypatch.setattr(opt, "run_backtest_simulation", fake_backtest)

        result = await optimize_strategy(
            None,
            ticker="AAPL",
            strategy_type="rsi_oversold",
            start_date="2024-01-01",
            end_date="2024-12-31",
            n_trials=3,
        )

        assert seen[0] == strategy_defaults("rsi_oversold")
        assert result.baseline_params == strategy_defaults("rsi_oversold")
        assert result.baseline_value == pytest.approx(1.0)
        assert result.as_dict()["improvement"] == pytest.approx(0.0)

    async def test_every_proposal_stays_inside_the_declared_space(self, monkeypatch):
        proposals: list[dict] = []

        async def fake_backtest(db, **kwargs):
            proposals.append(kwargs["strategy_params"])
            return _backtest_result()

        monkeypatch.setattr(opt, "run_backtest_simulation", fake_backtest)

        await optimize_strategy(
            None,
            ticker="AAPL",
            strategy_type="macd_crossover",
            start_date="2024-01-01",
            end_date="2024-12-31",
            n_trials=15,
        )

        space = STRATEGY_PARAM_SPACE["macd_crossover"]
        for params in proposals:
            assert set(params) == set(space)
            for key, value in params.items():
                assert space[key]["min"] <= value <= space[key]["max"]
            assert params["macd_fast"] < params["macd_slow"]

    async def test_a_trial_that_fails_does_not_end_the_search(self, monkeypatch):
        calls = {"n": 0}

        async def flaky_backtest(db, **kwargs):
            calls["n"] += 1
            if calls["n"] % 3 == 0:
                raise RuntimeError("vendor timeout")
            return _backtest_result()

        monkeypatch.setattr(opt, "run_backtest_simulation", flaky_backtest)

        result = await optimize_strategy(
            None,
            ticker="AAPL",
            strategy_type="rsi_oversold",
            start_date="2024-01-01",
            end_date="2024-12-31",
            n_trials=9,
        )

        assert result.trials_completed < 9
        assert any(t.state == "failed" for t in result.trials)
        assert result.best_value is not None

    async def test_a_search_where_nothing_ran_is_an_error_not_an_empty_result(self, monkeypatch):
        async def always_failing(db, **kwargs):
            return {"error": "Not enough historical price data."}

        monkeypatch.setattr(opt, "run_backtest_simulation", always_failing)

        with pytest.raises(OptimizationError, match="No trial produced a usable backtest"):
            await optimize_strategy(
                None,
                ticker="AAPL",
                strategy_type="rsi_oversold",
                start_date="2024-01-01",
                end_date="2024-12-31",
                n_trials=4,
            )

    async def test_the_seed_makes_a_search_reproducible(self, monkeypatch):
        async def fake_backtest(db, **kwargs):
            return _backtest_result(sharpe_ratio=kwargs["strategy_params"]["rsi_period"] / 10)

        monkeypatch.setattr(opt, "run_backtest_simulation", fake_backtest)

        async def run():
            return await optimize_strategy(
                None,
                ticker="AAPL",
                strategy_type="rsi_oversold",
                start_date="2024-01-01",
                end_date="2024-12-31",
                n_trials=8,
                seed=7,
            )

        first, second = await run(), await run()
        assert [t.params for t in first.trials] == [t.params for t in second.trials]


class TestRefusals:
    async def test_an_unknown_objective_is_refused(self):
        with pytest.raises(OptimizationError, match="Unknown objective"):
            await optimize_strategy(
                None,
                ticker="AAPL",
                strategy_type="rsi_oversold",
                start_date="2024-01-01",
                end_date="2024-12-31",
                objective="vibes",
            )

    async def test_a_strategy_without_tunables_is_refused(self):
        with pytest.raises(OptimizationError, match="no tunable parameters"):
            await optimize_strategy(
                None,
                ticker="AAPL",
                strategy_type="consensus",
                start_date="2024-01-01",
                end_date="2024-12-31",
            )

    @pytest.mark.parametrize("n_trials", [0, -5, 5000])
    async def test_an_out_of_range_trial_count_is_refused(self, n_trials):
        with pytest.raises(OptimizationError, match="n_trials"):
            await optimize_strategy(
                None,
                ticker="AAPL",
                strategy_type="rsi_oversold",
                start_date="2024-01-01",
                end_date="2024-12-31",
                n_trials=n_trials,
            )
