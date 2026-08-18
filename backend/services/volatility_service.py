"""Conditional volatility forecasting and parametric risk measures.

Realized volatility answers "how much did this move?"; it says nothing about
what comes next, and it treats a shock two months ago exactly like one
yesterday. `quant_tools` already reports trailing annualised volatility, so the
risk agents could only ever reason about the past.

GARCH-family models fit the *clustering* in returns — the tendency of turbulent
days to follow turbulent days — which makes a forward horizon meaningful. The
asymmetric variants (GJR/TARCH, EGARCH) additionally let a negative return
raise expected volatility more than an equally sized positive one, which is the
usual behaviour in equities.

Everything here is deterministic numerics. The model produces the numbers; the
LLM only narrates them.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)

TRADING_DAYS = 252
# arch fits on returns scaled to percent; a 1e-2 scale makes the optimiser
# badly conditioned and it warns on every call.
_RETURN_SCALE = 100.0
_MIN_OBSERVATIONS = 60
_MAX_HORIZON = 60

VolatilityModel = Literal["garch", "tarch", "egarch"]

_MODEL_SPECS: dict[str, dict] = {
    # vol/p/o/q as arch's arch_model() takes them. o>0 is the asymmetry term.
    "garch": {"vol": "GARCH", "p": 1, "o": 0, "q": 1},
    "tarch": {"vol": "GARCH", "p": 1, "o": 1, "q": 1},
    "egarch": {"vol": "EGARCH", "p": 1, "o": 1, "q": 1},
}

# EGARCH models log-variance, so multi-step variance has no closed form and
# arch refuses an analytic forecast beyond one step. Those models are forecast
# by simulating the variance path instead.
_SIMULATION_ONLY_MODELS = frozenset({"egarch"})
_FORECAST_SIMULATIONS = 1000


class VolatilityError(RuntimeError):
    """A forecast could not be produced from the supplied returns."""


@dataclass(frozen=True)
class VolatilityForecast:
    """One conditional-volatility forecast and the risk measures implied by it."""

    model: str
    horizon_days: int
    observations: int
    # Annualised, expressed as a fraction (0.24 == 24%).
    current_volatility: float
    forecast_volatility: float
    realized_volatility: float
    # Fraction of the horizon's value at risk / expected shortfall, positive.
    value_at_risk: float
    expected_shortfall: float
    confidence: float
    persistence: float
    # True when the fitted model says negative shocks raise volatility more.
    asymmetric: bool
    converged: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _clean_returns(returns: pd.Series) -> pd.Series:
    series = pd.Series(returns, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < _MIN_OBSERVATIONS:
        raise VolatilityError(
            f"At least {_MIN_OBSERVATIONS} return observations are required; received {len(series)}."
        )
    return series


def returns_from_prices(prices: pd.Series) -> pd.Series:
    """Log returns, which is what a GARCH model expects."""
    series = pd.Series(prices, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    series = series[series > 0]
    return np.log(series).diff().dropna()


def _normal_quantile(confidence: float) -> float:
    """Standard-normal quantile without pulling in SciPy for one number."""
    # Acklam's inverse-normal approximation; accurate to ~1e-9 over (0, 1).
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    p_low, p_high = 0.02425, 1 - 0.02425
    p = min(max(confidence, 1e-9), 1 - 1e-9)
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > p_high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1
    )


def _normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _persistence(params: pd.Series) -> float:
    """Sum of the ARCH/GARCH terms: how slowly a shock decays.

    Near 1.0 means volatility shocks persist for a long time; above 1.0 the
    fitted process is not stationary and the forecast should not be trusted.
    """
    total = 0.0
    for name, value in params.items():
        key = str(name).lower()
        if key.startswith(("alpha", "beta")):
            total += float(value)
        elif key.startswith("gamma"):
            # Asymmetry applies to half the distribution on average.
            total += float(value) / 2.0
    return total


def forecast_volatility(
    returns: pd.Series,
    *,
    model: VolatilityModel = "garch",
    horizon_days: int = 10,
    confidence: float = 0.99,
) -> VolatilityForecast:
    """Fit a GARCH-family model and forecast volatility over ``horizon_days``.

    ``returns`` are simple or log returns as a fraction (0.012 == 1.2%).
    Raises :class:`VolatilityError` rather than returning a misleading number.
    """
    spec = _MODEL_SPECS.get(str(model).lower())
    if spec is None:
        raise VolatilityError(f"Unknown volatility model '{model}'. Expected one of {sorted(_MODEL_SPECS)}.")
    if not 1 <= int(horizon_days) <= _MAX_HORIZON:
        raise VolatilityError(f"horizon_days must be between 1 and {_MAX_HORIZON}.")
    if not 0.5 < float(confidence) < 1.0:
        raise VolatilityError("confidence must be between 0.5 and 1.0 (exclusive).")

    try:
        from arch import arch_model
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise VolatilityError("The 'arch' package is required for volatility forecasting.") from exc

    series = _clean_returns(returns)
    horizon = int(horizon_days)
    scaled = series * _RETURN_SCALE

    needs_simulation = horizon > 1 and str(model).lower() in _SIMULATION_ONLY_MODELS
    try:
        fitted = arch_model(scaled, mean="Constant", dist="normal", **spec).fit(disp="off", show_warning=False)
        if needs_simulation:
            forecast = fitted.forecast(
                horizon=horizon,
                method="simulation",
                simulations=_FORECAST_SIMULATIONS,
                # Seeded so the same request returns the same number; an
                # unseeded simulation would make the forecast jitter per call.
                rng=np.random.default_rng(0).standard_normal,
                reindex=False,
            )
        else:
            forecast = fitted.forecast(horizon=horizon, reindex=False)
        # variance is in percent^2 per day; average over the horizon.
        daily_variance = np.asarray(forecast.variance.iloc[-1], dtype="float64")
    except Exception as exc:  # noqa: BLE001 — optimiser failures are data-dependent
        raise VolatilityError(f"Volatility model did not converge: {exc}") from exc

    if daily_variance.size == 0 or not np.isfinite(daily_variance).all() or (daily_variance <= 0).any():
        raise VolatilityError("Volatility model produced a non-finite variance path.")

    mean_daily_variance = float(daily_variance.mean()) / (_RETURN_SCALE**2)
    daily_sigma = math.sqrt(mean_daily_variance)
    horizon_sigma = daily_sigma * math.sqrt(horizon)

    conditional = np.asarray(fitted.conditional_volatility, dtype="float64") / _RETURN_SCALE
    current_daily = float(conditional[-1]) if conditional.size else daily_sigma

    quantile = _normal_quantile(float(confidence))
    var = quantile * horizon_sigma
    # Expected shortfall of a normal: sigma * pdf(q) / (1 - confidence).
    shortfall = horizon_sigma * _normal_pdf(quantile) / (1.0 - float(confidence))

    params = fitted.params
    return VolatilityForecast(
        model=str(model).lower(),
        horizon_days=horizon,
        observations=int(len(series)),
        current_volatility=current_daily * math.sqrt(TRADING_DAYS),
        forecast_volatility=daily_sigma * math.sqrt(TRADING_DAYS),
        realized_volatility=float(series.std(ddof=1)) * math.sqrt(TRADING_DAYS),
        value_at_risk=float(var),
        expected_shortfall=float(shortfall),
        confidence=float(confidence),
        persistence=float(_persistence(params)),
        asymmetric=any(str(name).lower().startswith("gamma") for name in params.index),
        converged=bool(np.isfinite(float(fitted.loglikelihood))),
    )


def describe_forecast(ticker: str, forecast: VolatilityForecast) -> str:
    """Render a forecast as the markdown an agent reads."""
    direction = "above" if forecast.forecast_volatility >= forecast.realized_volatility else "below"
    regime = (
        "highly persistent (shocks decay slowly)"
        if forecast.persistence >= 0.95
        else "moderately persistent"
        if forecast.persistence >= 0.80
        else "fast mean-reverting"
    )
    lines = [
        f"## Conditional Volatility Forecast — {ticker.upper()}",
        "",
        f"- **Model:** {forecast.model.upper()} on {forecast.observations} observations"
        f"{' (asymmetric)' if forecast.asymmetric else ''}",
        f"- **Forecast horizon:** {forecast.horizon_days} trading day(s)",
        f"- **Expected annualised volatility:** {forecast.forecast_volatility:.2%} "
        f"({direction} the {forecast.realized_volatility:.2%} realized over the sample)",
        f"- **Current conditional volatility:** {forecast.current_volatility:.2%} annualised",
        f"- **{forecast.confidence:.0%} Value at Risk ({forecast.horizon_days}d):** "
        f"{forecast.value_at_risk:.2%} of position value",
        f"- **Expected shortfall beyond that VaR:** {forecast.expected_shortfall:.2%}",
        f"- **Volatility persistence:** {forecast.persistence:.3f} — {regime}",
    ]
    if forecast.persistence >= 1.0:
        lines.append(
            "- **Caution:** persistence at or above 1.0 means the fitted process is not "
            "stationary; treat the horizon forecast as indicative only."
        )
    lines += [
        "",
        "VaR and expected shortfall assume normally distributed returns at the forecast "
        "volatility. They size a plausible adverse move; they are not a worst case.",
    ]
    return "\n".join(lines)
