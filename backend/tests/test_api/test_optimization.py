"""Optimization endpoints: catalog, tenant scoping, and run persistence."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.optimization import OptimizationRun
from backend.models.user import User

pytest.importorskip("optuna", reason="parameter optimization requires the optuna package")


async def _seed_run(db: AsyncSession, user: User, **overrides) -> OptimizationRun:
    run = OptimizationRun(
        user_id=user.id,
        ticker=overrides.pop("ticker", "AAPL"),
        strategy_type="rsi_oversold",
        objective="sharpe_ratio",
        start_date="2024-01-01",
        end_date="2024-12-31",
        trials_requested=10,
        trials_completed=10,
        status="completed",
        best_params={"rsi_period": 22, "rsi_oversold": 28, "rsi_overbought": 72},
        best_value=1.8,
        **overrides,
    )
    db.add(run)
    await db.flush()
    return run


class TestCatalog:
    async def test_publishes_the_simulation_parameter_space(self, authenticated_client: AsyncClient):
        response = await authenticated_client.get("/api/optimization/catalog")
        assert response.status_code == 200

        body = response.json()
        assert set(body["strategies"]) == {"macd_crossover", "rsi_oversold"}
        assert set(body["objectives"]) == {"sharpe_ratio", "total_return", "calmar", "win_rate"}

        rsi = body["strategies"]["rsi_oversold"]["params"]["rsi_period"]
        assert rsi["default"] == 14
        assert rsi["min"] < rsi["default"] < rsi["max"]

    async def test_requires_authentication(self, async_client: AsyncClient):
        assert (await async_client.get("/api/optimization/catalog")).status_code == 401


class TestListing:
    async def test_lists_the_callers_runs_without_the_trial_history(
        self, authenticated_client: AsyncClient, db: AsyncSession, test_user: User
    ):
        await _seed_run(db, test_user, trials=[{"number": 0, "params": {}, "value": 1.0}])

        response = await authenticated_client.get("/api/optimization")
        assert response.status_code == 200

        body = response.json()
        assert len(body) == 1
        assert body[0]["ticker"] == "AAPL"
        # Large and only meaningful on a single run.
        assert body[0]["trials"] is None

    async def test_filters_by_ticker(
        self, authenticated_client: AsyncClient, db: AsyncSession, test_user: User
    ):
        await _seed_run(db, test_user, ticker="AAPL")
        await _seed_run(db, test_user, ticker="NVDA")

        body = (await authenticated_client.get("/api/optimization", params={"ticker": "nvda"})).json()
        assert [run["ticker"] for run in body] == ["NVDA"]

    async def test_another_users_run_is_not_listed(
        self, authenticated_client: AsyncClient, db: AsyncSession, admin_user: User
    ):
        await _seed_run(db, admin_user, ticker="SECRET")

        body = (await authenticated_client.get("/api/optimization")).json()
        assert [run["ticker"] for run in body] == []


class TestDetail:
    async def test_returns_the_full_run_including_trials(
        self, authenticated_client: AsyncClient, db: AsyncSession, test_user: User
    ):
        run = await _seed_run(db, test_user, trials=[{"number": 0, "params": {"rsi_period": 9}, "value": 0.4}])

        body = (await authenticated_client.get(f"/api/optimization/{run.id}")).json()
        assert body["best_params"]["rsi_period"] == 22
        assert body["trials"][0]["params"]["rsi_period"] == 9

    async def test_another_users_run_is_not_readable(
        self, authenticated_client: AsyncClient, db: AsyncSession, admin_user: User
    ):
        run = await _seed_run(db, admin_user)
        assert (await authenticated_client.get(f"/api/optimization/{run.id}")).status_code == 404

    async def test_a_missing_run_is_a_404(self, authenticated_client: AsyncClient):
        assert (await authenticated_client.get("/api/optimization/999999")).status_code == 404


class TestRunValidation:
    async def test_a_strategy_without_tunables_is_rejected_by_the_schema(
        self, authenticated_client: AsyncClient
    ):
        response = await authenticated_client.post(
            "/api/optimization",
            json={
                "ticker": "AAPL",
                "strategy_type": "consensus",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("n_trials", [0, 5000])
    async def test_an_out_of_range_trial_count_is_rejected(
        self, authenticated_client: AsyncClient, n_trials
    ):
        response = await authenticated_client.post(
            "/api/optimization",
            json={
                "ticker": "AAPL",
                "strategy_type": "rsi_oversold",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "n_trials": n_trials,
            },
        )
        assert response.status_code == 422

    async def test_a_failed_search_persists_the_failure_rather_than_a_running_row(
        self, authenticated_client: AsyncClient, db: AsyncSession, monkeypatch
    ):
        """A row left claiming to be running would never resolve."""
        from backend.api import optimization as optimization_api
        from backend.services.optimization_service import OptimizationError

        async def failing_search(*args, **kwargs):
            raise OptimizationError("No trial produced a usable backtest.")

        monkeypatch.setattr(optimization_api, "optimize_strategy", failing_search)

        response = await authenticated_client.post(
            "/api/optimization",
            json={
                "ticker": "AAPL",
                "strategy_type": "rsi_oversold",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "n_trials": 2,
            },
        )
        assert response.status_code == 400
        assert "No trial produced" in response.json()["detail"]

        listed = (await authenticated_client.get("/api/optimization")).json()
        assert listed[0]["status"] == "failed"
        assert "No trial produced" in listed[0]["error"]
