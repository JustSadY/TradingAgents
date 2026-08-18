"""Search rule-based strategy parameters against the real backtest.

Picking RSI 14 over RSI 10, or a 3% stop over 5%, was previously a matter of
editing a constant and eyeballing one backtest. This runs Optuna over the same
`run_backtest_simulation` the Backtest page uses, so an optimized parameter set
is reproducible by simply re-running that backtest with it.

Two deliberate constraints:

* **The simulation owns the parameter space.** Bounds come from
  `backtest_service.STRATEGY_PARAM_SPACE`, and every proposal is passed through
  `normalise_strategy_params`, so a sampler cannot produce a combination the
  backtest would reject.
* **Optuna never runs the objective itself.** `study.optimize` wants a
  synchronous callable, and the backtest is async. The ask/tell API lets the
  trials be driven from the event loop instead of pushing an event loop into a
  worker thread.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Literal

from backend.services.backtest_service import (
    STRATEGY_PARAM_SPACE,
    normalise_strategy_params,
    run_backtest_simulation,
)

_logger = logging.getLogger(__name__)

MAX_TRIALS = 200
DEFAULT_TRIALS = 40
# A run that cannot produce a single valid backtest is a configuration error,
# not a search that happened to go badly.
_MIN_SUCCESSFUL_TRIALS = 1

Objective = Literal["sharpe_ratio", "total_return", "calmar", "win_rate"]

OBJECTIVES: dict[str, dict[str, str]] = {
    "sharpe_ratio": {"label": "Sharpe ratio", "direction": "maximize"},
    "total_return": {"label": "Total return %", "direction": "maximize"},
    "calmar": {"label": "Return / max drawdown", "direction": "maximize"},
    "win_rate": {"label": "Win rate %", "direction": "maximize"},
}

# A search that never trades scores "no drawdown, no losses" on several
# objectives. Require some activity before a result counts.
_MIN_TRADES = 3


class OptimizationError(RuntimeError):
    """The search could not be run as configured."""


@dataclass(frozen=True)
class TrialResult:
    number: int
    params: dict
    value: float | None
    metrics: dict
    state: str


@dataclass(frozen=True)
class OptimizationResult:
    ticker: str
    strategy_type: str
    objective: str
    trials_requested: int
    trials_completed: int
    best_params: dict
    best_value: float | None
    best_metrics: dict
    baseline_params: dict
    baseline_value: float | None
    baseline_metrics: dict
    trials: list[TrialResult]

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "strategy_type": self.strategy_type,
            "objective": self.objective,
            "trials_requested": self.trials_requested,
            "trials_completed": self.trials_completed,
            "best_params": self.best_params,
            "best_value": self.best_value,
            "best_metrics": self.best_metrics,
            "baseline_params": self.baseline_params,
            "baseline_value": self.baseline_value,
            "baseline_metrics": self.baseline_metrics,
            "improvement": (
                None
                if self.best_value is None or self.baseline_value is None
                else round(self.best_value - self.baseline_value, 6)
            ),
            "trials": [
                {
                    "number": trial.number,
                    "params": trial.params,
                    "value": trial.value,
                    "metrics": trial.metrics,
                    "state": trial.state,
                }
                for trial in self.trials
            ],
        }


def optimizable_strategies() -> dict[str, dict]:
    """Strategies with a declared search space, and what can be tuned."""
    return {strategy: dict(space) for strategy, space in STRATEGY_PARAM_SPACE.items() if space}


def _score(objective: str, result: dict) -> float | None:
    """Reduce a backtest result to the single number being maximised."""
    if not isinstance(result, dict) or result.get("error"):
        return None
    if int(result.get("trades_count") or 0) < _MIN_TRADES:
        # Not a real strategy outcome — it simply never traded.
        return None

    try:
        if objective == "sharpe_ratio":
            value = float(result["sharpe_ratio"])
        elif objective == "total_return":
            value = float(result["total_return"])
        elif objective == "win_rate":
            value = float(result["win_rate"])
        elif objective == "calmar":
            drawdown = abs(float(result.get("max_drawdown") or 0.0))
            total_return = float(result["total_return"])
            # A run with no drawdown has no risk-adjusted meaning here; fall
            # back to the raw return rather than dividing by zero.
            value = total_return / drawdown if drawdown > 1e-9 else total_return
        else:
            raise OptimizationError(f"Unknown objective '{objective}'.")
    except (KeyError, TypeError, ValueError):
        return None

    return value if math.isfinite(value) else None


def _suggest(trial, strategy_type: str) -> dict:
    """Draw one parameter set from the strategy's declared space."""
    proposal: dict[str, Any] = {}
    for key, spec in STRATEGY_PARAM_SPACE.get(strategy_type, {}).items():
        if spec["type"] == "int":
            proposal[key] = trial.suggest_int(key, int(spec["min"]), int(spec["max"]))
        else:
            proposal[key] = trial.suggest_float(key, float(spec["min"]), float(spec["max"]))
    # Clamped here too: what the trial records must be what actually ran.
    return normalise_strategy_params(strategy_type, proposal)


async def optimize_strategy(
    db,
    *,
    ticker: str,
    strategy_type: str,
    start_date: str,
    end_date: str,
    objective: str = "sharpe_ratio",
    n_trials: int = DEFAULT_TRIALS,
    initial_capital: float = 100_000.0,
    user=None,
    seed: int | None = 42,
) -> OptimizationResult:
    """Search ``strategy_type``'s parameters for the best ``objective``.

    ``seed`` is fixed by default so the same request reproduces the same
    search; pass ``None`` for an independent exploration.
    """
    if objective not in OBJECTIVES:
        raise OptimizationError(f"Unknown objective '{objective}'. Expected one of {sorted(OBJECTIVES)}.")
    space = STRATEGY_PARAM_SPACE.get(strategy_type)
    if not space:
        raise OptimizationError(
            f"Strategy '{strategy_type}' has no tunable parameters. "
            f"Optimizable strategies: {sorted(optimizable_strategies())}."
        )
    trials_requested = int(n_trials)
    if not 1 <= trials_requested <= MAX_TRIALS:
        raise OptimizationError(f"n_trials must be between 1 and {MAX_TRIALS}.")

    try:
        import optuna
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise OptimizationError("The 'optuna' package is required for parameter optimization.") from exc

    # Optuna logs one line per trial at INFO; that is per-run noise in the
    # System Logs page, and the trial history is returned to the caller anyway.
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    async def evaluate(params: dict) -> tuple[float | None, dict]:
        result = await run_backtest_simulation(
            db,
            ticker=ticker,
            strategy_type=strategy_type,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            user=user,
            strategy_params=params,
        )
        if not isinstance(result, dict):
            return None, {}
        metrics = {
            key: result.get(key)
            for key in ("total_return", "sharpe_ratio", "max_drawdown", "win_rate", "trades_count", "final_value")
        }
        if result.get("error"):
            metrics["error"] = result["error"]
        return _score(objective, result), metrics

    baseline_params = normalise_strategy_params(strategy_type, None)
    baseline_value, baseline_metrics = await evaluate(baseline_params)

    study = optuna.create_study(
        direction=OBJECTIVES[objective]["direction"],
        sampler=optuna.samplers.TPESampler(seed=seed),
    )

    trials: list[TrialResult] = []
    completed = 0
    for _ in range(trials_requested):
        trial = study.ask()
        params = _suggest(trial, strategy_type)
        try:
            value, metrics = await evaluate(params)
        except Exception as exc:  # noqa: BLE001 — one bad trial must not end the search
            _logger.warning("Optimization trial failed for %s/%s: %s", ticker, strategy_type, exc)
            value, metrics = None, {"error": str(exc)}

        if value is None:
            study.tell(trial, state=optuna.trial.TrialState.FAIL)
            state = "failed"
        else:
            study.tell(trial, value)
            completed += 1
            state = "completed"
        trials.append(TrialResult(number=trial.number, params=params, value=value, metrics=metrics, state=state))

    if completed < _MIN_SUCCESSFUL_TRIALS:
        raise OptimizationError(
            "No trial produced a usable backtest. Check the ticker, the date range, "
            f"and that the strategy trades at least {_MIN_TRADES} times in it."
        )

    best = max((t for t in trials if t.value is not None), key=lambda t: t.value)
    return OptimizationResult(
        ticker=ticker.upper(),
        strategy_type=strategy_type,
        objective=objective,
        trials_requested=trials_requested,
        trials_completed=completed,
        best_params=best.params,
        best_value=best.value,
        best_metrics=best.metrics,
        baseline_params=baseline_params,
        baseline_value=baseline_value,
        baseline_metrics=baseline_metrics,
        trials=trials,
    )
