"""Strategy parameter optimization endpoints.

A search runs tens of full backtests, so it is executed as a tracked row rather
than a plain request/response: the run is persisted before the work starts and
updated when it ends, which is what makes a completed search findable later.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_page
from backend.core.database import get_db
from backend.core.limiter import limiter
from backend.models.user import User
from backend.schemas.optimization import (
    OptimizationCatalog,
    OptimizationRequest,
    OptimizationRunRead,
)
from backend.services.optimization_service import (
    DEFAULT_TRIALS,
    MAX_TRIALS,
    OBJECTIVES,
    OptimizationError,
    optimizable_strategies,
    optimize_strategy,
)

router = APIRouter(prefix="/api/optimization", tags=["optimization"])

_RUN_NOT_FOUND = "Optimization run not found"

_STRATEGY_LABELS = {
    "macd_crossover": "MACD crossover",
    "rsi_oversold": "RSI oversold/overbought",
}


@router.get("/catalog", response_model=OptimizationCatalog)
async def get_catalog(_: Annotated[User, Depends(require_page("backtest"))]):
    """What can be optimized, published from the simulation's own parameter space."""
    return OptimizationCatalog(
        strategies={
            strategy: {"label": _STRATEGY_LABELS.get(strategy, strategy), "params": params}
            for strategy, params in optimizable_strategies().items()
        },
        objectives={key: spec["label"] for key, spec in OBJECTIVES.items()},
        max_trials=MAX_TRIALS,
        default_trials=DEFAULT_TRIALS,
    )


@router.get("", response_model=list[OptimizationRunRead])
async def list_runs(
    current_user: Annotated[User, Depends(require_page("backtest"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    ticker: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    from backend.repositories.optimization import list_optimization_runs

    runs = await list_optimization_runs(db, current_user, ticker=ticker, limit=limit, offset=offset)
    # The trial history is large and only meaningful on a single run.
    return [OptimizationRunRead.model_validate(run).model_copy(update={"trials": None}) for run in runs]


@router.get("/{run_id}", response_model=OptimizationRunRead, responses={404: {"description": _RUN_NOT_FOUND}})
async def get_run(
    run_id: int,
    current_user: Annotated[User, Depends(require_page("backtest"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from backend.repositories.optimization import get_optimization_run

    run = await get_optimization_run(db, run_id, current_user)
    if run is None:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)
    return run


@router.post(
    "",
    response_model=OptimizationRunRead,
    responses={400: {"description": "Optimization could not be run"}},
)
@limiter.limit("6/hour")
async def run_optimization(
    # Annotated so FastAPI treats it as the ASGI request the rate limiter needs
    # rather than a required query parameter named "request".
    request: Request,  # noqa: ARG001 — the limiter reads it, the handler does not
    body: OptimizationRequest,
    current_user: Annotated[User, Depends(require_page("backtest"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Search the strategy's parameters and persist the result.

    Rate limited because one call is tens of backtests; a tight loop here is a
    self-inflicted denial of service on the price-data vendor.
    """
    from backend.repositories.optimization import (
        complete_optimization_run,
        create_optimization_run,
        fail_optimization_run,
    )

    run = await create_optimization_run(
        db,
        user_id=current_user.id,
        ticker=body.ticker,
        strategy_type=body.strategy_type,
        objective=body.objective,
        start_date=body.start_date,
        end_date=body.end_date,
        trials_requested=body.n_trials,
    )
    await db.commit()

    try:
        result = await optimize_strategy(
            db,
            ticker=body.ticker,
            strategy_type=body.strategy_type,
            start_date=body.start_date,
            end_date=body.end_date,
            objective=body.objective,
            n_trials=body.n_trials,
            initial_capital=body.initial_capital,
            user=current_user,
        )
    except OptimizationError as exc:
        await fail_optimization_run(db, run, str(exc))
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:
        # The row must not be left claiming to be running after the process
        # has already given up on it.
        await fail_optimization_run(db, run, str(exc))
        await db.commit()
        raise HTTPException(status_code=400, detail="Optimization failed unexpectedly.") from exc

    await complete_optimization_run(db, run, result.as_dict())
    await db.commit()
    return run
