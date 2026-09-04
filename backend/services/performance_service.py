import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.constants import (
    DEFAULT_HOLDING_DAYS as HOLDING_DAYS,
)
from backend.core.utils import resolve_benchmark
from backend.repositories.performance import (
    apply_reflection,
    apply_return_outcome,
    list_resolved_learning_analyses,
    list_return_backfill_candidates,
)
from backend.repositories.settings import get_app_settings_map
from backend.repositories.users import get_users_by_ids
from backend.services.market_data_service import calculate_returns
from backend.services.outcome_semantics import rating_outcome_success

_logger = logging.getLogger(__name__)

_WEIGHT_PRIOR_STRENGTH = 8.0
_WEIGHT_COMPONENTS = (
    ("global", 0.40),
    ("ticker", 0.25),
    ("regime", 0.20),
    ("recent", 0.15),
)
_REGIME_KEYS = ("trend", "volatility", "risk", "macro")
_REGIME_FRESHNESS = timedelta(hours=36)
_BACKFILL_RETURN_CONCURRENCY = 4
_OWNER_USER_UNSET = object()


def _analysis_regime(row: object) -> dict[str, str]:
    raw = getattr(row, "market_regime_json", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = None
    if not isinstance(raw, dict):
        return {}
    return {
        key: str(raw[key]).strip().lower()
        for key in _REGIME_KEYS
        if raw.get(key) is not None and str(raw[key]).strip()
    }


def _normalise_regime(
    regime: dict[str, Any] | None,
    *,
    require_fresh: bool = False,
    now: datetime | None = None,
) -> dict[str, str]:
    if not isinstance(regime, dict):
        return {}
    if require_fresh:
        raw_as_of = regime.get("as_of")
        if not raw_as_of:
            return {}
        try:
            observed = datetime.fromisoformat(str(raw_as_of).replace("Z", "+00:00"))
        except ValueError:
            return {}
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        observed = observed.astimezone(UTC)
        current = (now or datetime.now(UTC)).astimezone(UTC)
        if observed > current + timedelta(minutes=5) or current - observed > _REGIME_FRESHNESS:
            return {}
    return {
        key: str(regime[key]).strip().lower()
        for key in _REGIME_KEYS
        if regime.get(key) is not None and str(regime[key]).strip()
    }


def _is_matching_regime(row: object, current_regime: dict[str, str]) -> bool:
    """Require a meaningful overlap, not a coincidental one-field match."""
    if not current_regime:
        return False
    observed = _analysis_regime(row)
    shared = [key for key in _REGIME_KEYS if key in current_regime and key in observed]
    if not shared:
        return False
    matches = sum(current_regime[key] == observed[key] for key in shared)
    required = 2 if len(shared) >= 2 else 1
    return matches >= required


def _is_recent(row: object, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    try:
        observed = datetime.fromisoformat(str(getattr(row, "trade_date", "")).replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    return observed >= now - timedelta(days=90)


def _prediction_success(report: object, raw_return: object, alpha_return: object = None) -> bool | None:
    """Score an analyst rating with the platform's canonical five-tier semantics."""
    from backend.trading_agents.agents.runtime.rating import parse_rating

    prediction = parse_rating(str(report or ""), default=None)
    if not prediction:
        return None
    return rating_outcome_success(
        prediction,
        raw_return=raw_return,
        alpha_return=alpha_return,
    )


def _posterior_accuracy(successes: int, count: int, *, prior_mean: float = 0.5) -> float:
    return (successes + prior_mean * _WEIGHT_PRIOR_STRENGTH) / (count + _WEIGHT_PRIOR_STRENGTH)


def _regime_aware_weight_rows(
    rows: list[object],
    *,
    ticker: str,
    current_regime: dict[str, Any] | None,
    report_fields: dict[str, str],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Compute shrinkage-based per-analyst weights from resolved outcomes."""
    normalized_regime = _normalise_regime(current_regime, require_fresh=True, now=now)
    counters: dict[str, dict[str, list[int]]] = {
        key: {component: [0, 0] for component, _ in _WEIGHT_COMPONENTS}
        for key in (field.removesuffix("_report") for field in report_fields)
    }
    ticker = ticker.upper()
    for row in rows:
        ticker_match = str(getattr(row, "ticker", "")).upper() == ticker
        regime_match = _is_matching_regime(row, normalized_regime)
        recent_match = _is_recent(row, now=now)
        for report_field in report_fields:
            analyst = report_field.removesuffix("_report")
            success = _prediction_success(
                getattr(row, report_field, ""),
                getattr(row, "raw_return", None),
                getattr(row, "alpha_return", None),
            )
            if success is None:
                continue
            counters[analyst]["global"][0] += 1
            counters[analyst]["global"][1] += int(success)
            if ticker_match:
                counters[analyst]["ticker"][0] += 1
                counters[analyst]["ticker"][1] += int(success)
            if regime_match:
                counters[analyst]["regime"][0] += 1
                counters[analyst]["regime"][1] += int(success)
            if recent_match:
                counters[analyst]["recent"][0] += 1
                counters[analyst]["recent"][1] += int(success)

    output: list[dict[str, Any]] = []
    for report_field, label in report_fields.items():
        analyst = report_field.removesuffix("_report")
        counts = counters[analyst]
        global_count, global_successes = counts["global"]
        global_accuracy = _posterior_accuracy(global_successes, global_count)
        weighted_accuracy = 0.0
        applied_weight = 0.0
        metrics: dict[str, Any] = {}
        for component, base_weight in _WEIGHT_COMPONENTS:
            count, successes = counts[component]
            accuracy = _posterior_accuracy(successes, count, prior_mean=global_accuracy)
            reliability = 1.0 if component == "global" else count / (count + _WEIGHT_PRIOR_STRENGTH)
            component_weight = base_weight * reliability
            weighted_accuracy += component_weight * accuracy
            applied_weight += component_weight
            metrics[f"{component}_samples"] = count
            metrics[f"{component}_accuracy"] = round(accuracy * 100, 1)
        effective_accuracy = weighted_accuracy / applied_weight if applied_weight else global_accuracy
        output.append(
            {
                "key": analyst,
                "label": label,
                **metrics,
                "effective_accuracy": round(effective_accuracy * 100, 1),
                "_raw_weight": max(0.05, effective_accuracy),
            }
        )

    total = sum(item["_raw_weight"] for item in output) or 1.0
    for item in output:
        item["effective_weight"] = round(100.0 * item.pop("_raw_weight") / total, 1)
    return output


async def get_regime_aware_analyst_attribution_stats(
    db,
    *,
    user_id: int | None,
    ticker: str,
    current_regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return privacy-scoped Bayesian analyst weights for one live run.

    A fresh broad-market snapshot is preferred. A recent caller-supplied regime
    remains an allowed fast path, but an old/undated AssetStrategy assumption
    is never treated as the current market regime.
    """
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    effective_regime: dict[str, Any] | None = current_regime
    if not _normalise_regime(effective_regime, require_fresh=True):
        try:
            from backend.services.analysis.market_pulse_service import get_current_regime_snapshot

            effective_regime = await get_current_regime_snapshot()
        except Exception as exc:  # noqa: BLE001 - regime slice is optional
            _logger.warning("Could not load current market regime; using non-regime attribution: %s", exc)
            effective_regime = {}

    rows = await list_resolved_learning_analyses(db, user_id=user_id)
    report_fields = get_report_fields()
    fresh_regime = _normalise_regime(effective_regime, require_fresh=True)
    return {
        "method": "beta_binomial_global_ticker_regime_recency_v2",
        "ticker": ticker.upper(),
        "regime": fresh_regime,
        "attribution": _regime_aware_weight_rows(
            rows,
            ticker=ticker,
            current_regime=effective_regime,
            report_fields=report_fields,
        ),
        "total_resolved_runs": len(rows),
    }


async def _create_reflector_for_row(db, row, settings_obj, *, owner_user=_OWNER_USER_UNSET):
    """Build reflection LLM from preloaded owner/provider configuration."""
    from backend.services.user_service import resolve_user_api_key
    from backend.trading_agents.default_config import DEFAULT_CONFIG
    from backend.trading_agents.graph.reflection import Reflector
    from backend.trading_agents.llm_clients import create_llm_client
    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    provider = str(
        getattr(settings_obj, "llm_provider", None)
        or DEFAULT_CONFIG.get("llm_provider", "openai")
    ).strip().lower()
    model = str(
        getattr(settings_obj, "llm_model", None)
        or DEFAULT_CONFIG.get("llm_model", "gpt-5.6-luna")
    ).strip()

    api_key = None
    if getattr(row, "user_id", None) is not None:
        if owner_user is _OWNER_USER_UNSET:
            from backend.repositories.users import get_user_by_id

            user = await get_user_by_id(db, int(row.user_id))
        else:
            user = owner_user
        if user is not None:
            api_key = resolve_user_api_key(user, provider)

    if provider_requires_api_key(provider) and not api_key:
        raise ValueError(
            f"No stored API key is available for reflection provider '{provider}'"
        )

    client_kwargs = {"api_key": api_key} if api_key else {}
    client = create_llm_client(provider=provider, model=model, **client_kwargs)
    return Reflector(client.get_llm())


async def backfill_returns(db) -> int:
    from backend.trading_agents.dataflows.config import get_config

    cutoff = (datetime.now(UTC) - timedelta(days=HOLDING_DAYS + 2)).strftime("%Y-%m-%d")
    rows = await list_return_backfill_candidates(db, cutoff_trade_date=cutoff, limit=50)
    updated = 0
    config = get_config()

    owner_ids = {int(row.user_id) for row in rows if getattr(row, "user_id", None) is not None}
    settings_by_user = await get_app_settings_map(db, owner_ids)
    users_by_id = await get_users_by_ids(db, owner_ids)

    work_items: list[tuple[object, int | None, object, str]] = []
    for row in rows:
        row_config = dict(config)
        owner_id = int(row.user_id) if getattr(row, "user_id", None) is not None else None
        settings_obj = settings_by_user.get(owner_id) if owner_id is not None else None
        if settings_obj:
            bt = getattr(settings_obj, "benchmark_ticker", None)
            if bt:
                row_config["benchmark_ticker"] = bt
        benchmark = resolve_benchmark(row.ticker, row_config)
        work_items.append((row, owner_id, settings_obj, benchmark))

    semaphore = asyncio.Semaphore(_BACKFILL_RETURN_CONCURRENCY)

    async def _calculate(item):
        row, _owner_id, _settings_obj, benchmark = item
        async with semaphore:
            return await calculate_returns(
                row.ticker,
                row.trade_date,
                holding_days=HOLDING_DAYS,
                benchmark=benchmark,
            )

    outcomes = await asyncio.gather(*[_calculate(item) for item in work_items])

    for (row, owner_id, settings_obj, benchmark), (raw, alpha, days) in zip(work_items, outcomes, strict=True):
        if raw is not None:
            apply_return_outcome(
                row,
                raw_return=raw,
                alpha_return=alpha,
                holding_days=days,
            )

            try:
                reflector = await _create_reflector_for_row(
                    db,
                    row,
                    settings_obj,
                    owner_user=users_by_id.get(owner_id) if owner_id is not None else None,
                )
                reflection = await asyncio.to_thread(
                    reflector.reflect_on_final_decision,
                    final_decision=row.final_decision,
                    raw_return=raw,
                    alpha_return=alpha,
                    benchmark_name=benchmark,
                )
                apply_reflection(row, reflection)
            except Exception as ref_exc:
                _logger.warning("Could not generate reflection for analysis_id=%s: %s", row.id, ref_exc)

            from backend.services.memory_service import record_episode

            await record_episode(
                user_id=row.user_id,
                ticker=row.ticker,
                trade_date=row.trade_date,
                signal=row.signal,
                situation_text=(getattr(row, "market_report", "") or "") or (row.final_decision or ""),
                decision=row.final_decision or "",
                raw_return=raw,
                alpha_return=alpha,
                reflection=row.reflection or "",
            )

            updated += 1
    if updated:
        await db.commit()
    _logger.info("Performance backfill: updated %d rows with custom benchmarks", updated)
    return updated


async def get_analyst_attribution_stats(db, user_id: int | None = None) -> dict:
    """Return attribution statistics for one tenant or the system scope."""
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    rows = await list_resolved_learning_analyses(db, user_id=user_id)

    report_fields = get_report_fields()
    analysts = {
        rf.replace("_report", ""): {"label": label, "report_field": rf}
        for rf, label in report_fields.items()
    }
    stats = {
        k: {
            "key": k,
            "label": val["label"],
            "total_predictions": 0,
            "correct_predictions": 0,
            "win_rate": 50.0,
        }
        for k, val in analysts.items()
    }

    for row in rows:
        for key, config in analysts.items():
            success = _prediction_success(
                getattr(row, config["report_field"], ""),
                getattr(row, "raw_return", None),
                getattr(row, "alpha_return", None),
            )
            if success is None:
                continue
            stats[key]["total_predictions"] += 1
            if success:
                stats[key]["correct_predictions"] += 1

    win_rates = {}
    for key, s in stats.items():
        total = s["total_predictions"]
        correct = s["correct_predictions"]
        s["win_rate"] = round((correct / total) * 100, 1) if total > 0 else 50.0
        win_rates[key] = s["win_rate"]
    sum_win_rates = sum(win_rates.values())
    for key, s in stats.items():
        if sum_win_rates > 0:
            s["weight"] = round((win_rates[key] / sum_win_rates) * 100, 1)
        else:
            s["weight"] = round(100.0 / len(stats), 1)

    from backend.services.analyst_prefilter_service import _PROTECTED_ANALYSTS

    chronic_min_samples = 10
    chronic_max_win_rate = 40.0
    for key, s in stats.items():
        s["chronic_underperformer"] = (
            key not in _PROTECTED_ANALYSTS
            and s["total_predictions"] >= chronic_min_samples
            and s["win_rate"] < chronic_max_win_rate
        )

    attribution_list = list(stats.values())
    total_runs_evaluated = sum(s["total_predictions"] for s in attribution_list)
    return {"attribution": attribution_list, "total_evaluated_runs": total_runs_evaluated}


async def get_analyst_performance_context(
    db,
    user_id: int | None = None,
    *,
    ticker: str | None = None,
    current_regime: dict[str, Any] | None = None,
    regime_aware: bool = False,
) -> str:
    """Return a tenant-scoped Markdown summary for AI prompt injection."""
    try:
        if regime_aware and ticker:
            attribution_data = await get_regime_aware_analyst_attribution_stats(
                db,
                user_id=user_id,
                ticker=ticker,
                current_regime=current_regime,
            )
            attribution = attribution_data.get("attribution") or []
            if not attribution:
                return ""
            md = "=== REGIME-AWARE ANALYST PERFORMANCE & WEIGHTS ===\n"
            md += (
                "Effective weights use beta-binomial shrinkage across global, ticker-specific, "
                "fresh matching-regime, and recent accuracy. A stale/undated AssetStrategy assumption "
                "is replaced by a direction-neutral broad-market snapshot when available. Sparse local "
                "samples are pulled toward the global baseline.\n"
            )
            for att in attribution:
                md += (
                    f"- {att['label']}: Effective Accuracy = {att['effective_accuracy']}%, "
                    f"Weight = {att['effective_weight']}% "
                    f"(global {att['global_accuracy']}%/{att['global_samples']}, "
                    f"ticker {att['ticker_accuracy']}%/{att['ticker_samples']}, "
                    f"regime {att['regime_accuracy']}%/{att['regime_samples']}, "
                    f"recent {att['recent_accuracy']}%/{att['recent_samples']})\n"
                )
            md += "\n[IMPORTANT] Treat these as evidence-quality priors, not as a substitute for current source-grounded evidence.\n\n"
            return md

        attribution_data = await get_analyst_attribution_stats(db, user_id=user_id)
        if not attribution_data.get("attribution"):
            return ""
        md = "=== ANALYST PERFORMANCE ATTRIBUTION & WEIGHTS ===\n"
        md += "Below are the historical win rates and normalized voting weights assigned to each analyst based on empirical accuracy:\n"
        for att in attribution_data["attribution"]:
            md += f"- {att['label']}: Win Rate = {att['win_rate']}%, Assigned Weight = {att['weight']}%\n"
        md += "\n[IMPORTANT] During decision synthesis, discount opinions of analysts with lower weights and heavily prioritize opinions of analysts with higher weights.\n\n"
        return md
    except Exception as e:
        _logger.warning("Could not load analyst attribution stats (skipping): %s", e)
        return ""