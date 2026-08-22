"""Regression coverage for analysis-originated order audit and WS outcomes."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from backend.services.execution.base import OrderRequest, OrderResult


async def test_simulation_trader_forwards_analysis_provenance_to_persisted_order(monkeypatch):
    from backend.services.execution import simulation

    received: dict = {}

    async def fake_execute_order(**kwargs):
        received.update(kwargs)
        return {
            "order_id": 73,
            "status": "FILLED",
            "price": 123.45,
            "quantity": 2.5,
            "commission": 0.31,
        }

    monkeypatch.setattr(simulation, "execute_order", fake_execute_order)
    trader = simulation.SimulationTrader(db=object(), portfolio_id=44)

    result = await trader.place_order(
        OrderRequest(
            ticker="NVDA",
            action="BUY",
            quantity=Decimal("2.5"),
            reference_price=Decimal("123.45"),
            analysis_id=19,
            ai_signal="Buy",
            ai_reasoning="Final Portfolio Manager rationale",
        )
    )

    assert result.status == "FILLED"
    assert received["analysis_id"] == 19
    assert received["ai_signal"] == "Buy"
    assert received["ai_reasoning"] == "Final Portfolio Manager rationale"

async def test_final_portfolio_decision_constrains_auto_order_and_provenance(monkeypatch):
    """A historical Trader proposal must not override the final PM decision."""
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import mock_trading_service, trading_orchestrator

    class FakeTrader:
        request = None

        async def get_current_price(self, _ticker):
            return 100.0

        async def place_order(self, request):
            self.request = request
            return OrderResult(
                order_id="auto-1",
                status="FILLED",
                filled_price=Decimal("100"),
                filled_quantity=request.quantity,
            )

    portfolio = SimpleNamespace(id=44, initial_capital=Decimal("10000"), cash_available=Decimal("10000"))
    trader = FakeTrader()

    async def fake_system_settings(_db):
        return None

    async def fake_holding(_db, _portfolio_id, _ticker):
        return SimpleNamespace(side="long", quantity=Decimal("2"))

    async def fake_portfolio(_db, user=None):
        return portfolio

    async def fake_snapshot(_db, **_kwargs):
        return {"total_value": 10_000.0, "holdings": [{"ticker": "NVDA", "market_value": 200.0}]}

    monkeypatch.setattr(system_settings_repo, "get_system_settings", fake_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", fake_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", fake_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", fake_snapshot)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)

    row = SimpleNamespace(
        id=19,
        signal="Buy",
        final_decision="Portfolio Manager: Buy because the final risk-adjusted decision is positive.",
        portfolio_decision_json={
            "rating": "Buy",
            "confidence_score": 0.8,
            "entry_price": 100,
            "stop_loss": 95,
            "take_profit_price": 110,
            "position_size_pct": 5,
            "suggested_capital": 300,
            "recommended_leverage": 2.5,
        },
        chart_annotations={
            "trader_proposal": {"stop_loss": 80, "take_profit_price": 140, "position_size_pct": 90},
        },
    )
    settings = SimpleNamespace(
        quality_gate_enabled=False,
        allow_short_selling=False,
        drawdown_breaker_enabled=False,
        max_risk_per_trade_pct=2.0,
        max_position_size_pct=10.0,
        max_concentration_pct=25.0,
        max_gross_exposure=3.0,
        correlation_risk_enabled=False,
    )

    result = await trading_orchestrator.place_signal_order(
        object(), ticker="NVDA", row=row, settings=settings, include_skip_result=True
    )

    assert result is not None and result.status == "FILLED"
    assert trader.request is not None
    assert trader.request.quantity == Decimal("3.0")
    assert trader.request.stop_loss == Decimal("95.0")
    assert trader.request.take_profit == Decimal("110.0")
    assert trader.request.leverage == 2.5
    assert trader.request.analysis_id == 19
    assert trader.request.ai_signal == "Buy"
    assert "Portfolio Manager" in trader.request.ai_reasoning

async def test_legacy_trader_proposal_is_display_only_and_cannot_open_an_order():
    from backend.services import trading_orchestrator

    result = await trading_orchestrator.place_signal_order(
        object(),
        ticker="NVDA",
        row=SimpleNamespace(
            id=21,
            signal="Buy",
            final_decision="",
            chart_annotations={
                "trader_proposal": {
                    "rating": "Buy",
                    "position_size_pct": 90,
                    "stop_loss": 80,
                }
            },
        ),
        settings=SimpleNamespace(quality_gate_enabled=False),
        include_skip_result=True,
    )

    assert result is not None
    assert result.status == "SKIPPED"
    assert result.reason_code == "portfolio_decision_missing"

async def test_underweight_reduces_only_to_final_target_allocation(monkeypatch):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import mock_trading_service, trading_orchestrator

    class FakeTrader:
        request = None

        async def get_current_price(self, _ticker):
            return 100.0

        async def place_order(self, request):
            self.request = request
            return OrderResult(
                order_id="reduce-1",
                status="FILLED",
                filled_price=Decimal("100"),
                filled_quantity=request.quantity,
            )

    portfolio = SimpleNamespace(id=45, initial_capital=Decimal("10000"), cash_available=Decimal("9000"))
    holding = SimpleNamespace(side="long", quantity=Decimal("10"))
    trader = FakeTrader()

    async def fake_system_settings(_db):
        return None

    async def fake_holding(_db, _portfolio_id, _ticker):
        return holding

    async def fake_portfolio(_db, user=None):
        return portfolio

    async def fake_snapshot(_db, **_kwargs):
        return {"total_value": 10_000.0, "holdings": []}

    monkeypatch.setattr(system_settings_repo, "get_system_settings", fake_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", fake_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", fake_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", fake_snapshot)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)

    row = SimpleNamespace(
        id=20,
        signal="Underweight",
        final_decision="Portfolio Manager: reduce the long position to a 6% allocation.",
        portfolio_decision_json={
            "rating": "Underweight",
            "position_size_pct": 6,
            "suggested_capital": 400,
            "recommended_leverage": 1,
        },
        chart_annotations={},
    )

    result = await trading_orchestrator.place_signal_order(
        object(),
        ticker="NVDA",
        row=row,
        settings=SimpleNamespace(quality_gate_enabled=False, allow_short_selling=False, drawdown_breaker_enabled=False),
        include_skip_result=True,
    )

    assert result is not None and result.status == "FILLED"
    assert trader.request is not None
    assert trader.request.action == "SELL"
    assert trader.request.quantity == Decimal("4.0")

async def test_background_analysis_emits_filled_order_result_after_durable_commit(monkeypatch):
    from backend.services import analysis_service

    events: list[dict] = []
    commits: list[str] = []

    class FakeEmitter:
        def __init__(self, _task_id):
            pass

        async def emit_order_result(self, **event):
            events.append(event)

        async def close(self):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            commits.append("commit")

        async def rollback(self):
            commits.append("rollback")

    row = SimpleNamespace(
        id=31,
        signal="Buy",
        final_decision="The Portfolio Manager approved this position.",
        quality=None,
        chart_annotations={},
    )

    async def fake_run_analysis(*_args, **_kwargs):
        return "observable-order", row

    async def not_cancelled(_task_id):
        return False

    async def fake_place_order(*_args, **kwargs):
        assert kwargs["include_skip_result"] is True
        assert kwargs["row"].id == 31
        return OrderResult(
            order_id="fill-31",
            status="FILLED",
            filled_price=Decimal("99.5"),
            filled_quantity=Decimal("4"),
            commission=Decimal("0.4"),
            message="Simulation order filled",
        )

    async def clear_terminal(*_args, **_kwargs):
        pass

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", FakeEmitter)
    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(analysis_service, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(analysis_service, "place_signal_order", fake_place_order)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", not_cancelled)
    monkeypatch.setattr(analysis_service, "_clear_terminal_task_state", clear_terminal)

    await analysis_service.run_analysis_task(
        "NVDA",
        "2026-08-01",
        "stock",
        SimpleNamespace(auto_execute_signals=True),
        "observable-order",
    )

    assert commits == ["commit", "commit"]
    assert events == [
        {
            "analysis_id": 31,
            "ticker": "NVDA",
            "action": "BUY",
            "signal": "Buy",
            "outcome": "filled",
            "broker_status": "FILLED",
            "order_id": "fill-31",
            "filled_quantity": Decimal("4"),
            "filled_price": Decimal("99.5"),
            "commission": Decimal("0.4"),
            "message": "Simulation order filled",
            "reason_code": "",
        }
    ]

async def test_background_analysis_reports_disabled_auto_execution_as_skip(monkeypatch):
    from backend.services import analysis_service

    events: list[dict] = []

    class FakeEmitter:
        def __init__(self, _task_id):
            pass

        async def emit_order_result(self, **event):
            events.append(event)

        async def close(self):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

        async def rollback(self):
            pass

    row = SimpleNamespace(id=32, signal="Sell", final_decision="Holdings should be reduced.", quality=None, chart_annotations={})

    async def fake_run_analysis(*_args, **_kwargs):
        return "disabled-auto-order", row

    async def not_cancelled(_task_id):
        return False

    def must_not_place(*_args, **_kwargs):
        raise AssertionError("auto execution must be an explicit opt-in")

    async def clear_terminal(*_args, **_kwargs):
        pass

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", FakeEmitter)
    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(analysis_service, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(analysis_service, "place_signal_order", must_not_place)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", not_cancelled)
    monkeypatch.setattr(analysis_service, "_clear_terminal_task_state", clear_terminal)

    await analysis_service.run_analysis_task(
        "NVDA",
        "2026-08-01",
        "stock",
        SimpleNamespace(auto_execute_signals=False),
        "disabled-auto-order",
    )

    assert events[0]["outcome"] == "skipped"
    assert events[0]["reason_code"] == "auto_execution_disabled"

async def test_background_analysis_reports_persistence_failure_without_attempting_order(monkeypatch):
    """A complete event must not hide a failed final analysis commit."""
    from backend.services import analysis_service

    errors: list[str] = []
    order_attempted = False

    class FakeEmitter:
        def __init__(self, _task_id):
            pass

        async def emit_error(self, message):
            errors.append(message)

        async def close(self):
            pass

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            raise RuntimeError("database offline")

        async def rollback(self):
            pass

    row = SimpleNamespace(id=33, signal="Buy", final_decision="Saved only if commit succeeds.")

    async def fake_run_analysis(*_args, **_kwargs):
        return "failed-analysis-commit", row

    async def not_cancelled(_task_id):
        return False

    async def must_not_place(*_args, **_kwargs):
        nonlocal order_attempted
        order_attempted = True
        raise AssertionError("order cannot run before analysis persistence")

    async def clear_terminal(*_args, **_kwargs):
        pass

    monkeypatch.setattr(analysis_service, "AnalysisEmitter", FakeEmitter)
    monkeypatch.setattr(analysis_service, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(analysis_service, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(analysis_service, "place_signal_order", must_not_place)
    monkeypatch.setattr(analysis_service.task_store, "is_cancel_requested", not_cancelled)
    monkeypatch.setattr(analysis_service, "_clear_terminal_task_state", clear_terminal)

    await analysis_service.run_analysis_task(
        "NVDA",
        "2026-08-01",
        "stock",
        SimpleNamespace(auto_execute_signals=True),
        "failed-analysis-commit",
    )

    assert order_attempted is False
    assert errors == ["Analysis could not be saved. Please try again."]
