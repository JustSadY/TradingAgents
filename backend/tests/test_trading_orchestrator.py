"""Tests for signal-to-order orchestration (``trading_orchestrator``).

Covers the pure sizing/extraction helpers and ``place_signal_order``'s
decision flow with a stubbed trader, portfolio, and risk snapshot — no
database or live price feed involved.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services import trading_orchestrator as tro
from backend.services.execution.base import OrderResult

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _row(**kwargs):
    base = {
        "id": 1,
        "signal": "Buy",
        "chart_annotations": None,
        "final_decision": "",
        "trader_plan": "",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_is_actionable():
    assert tro.is_actionable("Buy")
    assert tro.is_actionable("Underweight")
    assert not tro.is_actionable("Hold")
    assert not tro.is_actionable(None)


def test_confidence_from_structured_trader_proposal():
    row = _row(chart_annotations={"trader_proposal": {"confidence_score": 0.8}})
    assert tro._extract_confidence_score(row) == 0.8


def test_confidence_from_text_percent_is_normalized_and_clamped():
    row = _row(trader_plan="Confidence Score: 75")
    assert tro._extract_confidence_score(row) == 0.75
    row = _row(final_decision="confidence score = 0.6")
    assert tro._extract_confidence_score(row) == 0.6
    assert tro._extract_confidence_score(_row()) is None


def test_leverage_structured_clamped_to_10x():
    row = _row(chart_annotations={"recommended_leverage": 99})
    assert tro._extract_leverage(row) == 10.0


def test_leverage_from_decision_text():
    row = _row(final_decision="**Recommended Leverage:** 3x")
    assert tro._extract_leverage(row) == 3.0


def test_leverage_defaults_to_cash():
    assert tro._extract_leverage(_row()) == 1.0


def test_kelly_ceiling_from_annotations_and_text():
    row = _row(chart_annotations={"kelly_recommendation_pct": 12.5})
    assert tro._extract_kelly_ceiling_pct(row, confidence_score=None, current_price=100.0) == 12.5

    row = _row(final_decision="Suggested Maximum Position Size: 8%")
    assert tro._extract_kelly_ceiling_pct(row, confidence_score=None, current_price=100.0) == 8.0

    # Nothing structured, no stop/target in the plan -> no ceiling.
    assert tro._extract_kelly_ceiling_pct(_row(), confidence_score=0.7, current_price=100.0) is None


def test_position_quantity_risk_based_sizing():
    # 1% of 100k = $1000 risk; no stop -> notional sizing at $100/share = 10 shares.
    assert tro._position_quantity(1.0, 100_000, 100.0) == 10.0
    # Stop at 95 -> $5 risk/share -> 200 shares, but 10% max alloc caps at 100.
    assert tro._position_quantity(1.0, 100_000, 100.0, stop_loss=95.0) == 100.0
    # Kelly multiplier scales the risk budget down.
    assert tro._position_quantity(1.0, 100_000, 100.0, kelly_multiplier=0.5) == 5.0
    # Multiplier is clamped to [0, 1] — kelly may never size UP past the base risk.
    assert tro._position_quantity(1.0, 100_000, 100.0, kelly_multiplier=5.0) == 10.0
    # Stop loss near entry (e.g. stop_loss=99.99, price=100.0) -> risk_per_share floored to 0.005 * price = 0.5.
    # Risk USD = 1000. Max allocation = $500,000. Quantity = 1000 / 0.5 = 2000.
    assert tro._position_quantity(1.0, 100_000, 100.0, stop_loss=99.99, max_position_size_pct=500.0) == 2000.0


# ---------------------------------------------------------------------------
# place_signal_order flow
# ---------------------------------------------------------------------------


class FakeTrader:
    def __init__(self, price: float = 100.0):
        self.price = price
        self.requests = []

    async def get_current_price(self, ticker):
        return self.price

    async def place_order(self, request):
        self.requests.append(request)
        return OrderResult(
            order_id="t-1",
            status="FILLED",
            filled_price=self.price,
            filled_quantity=request.quantity,
        )


def _settings(**kwargs):
    base = {"max_risk_per_trade_pct": 1.0, "max_position_size_pct": 10.0}
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.fixture
def env(monkeypatch):
    """Stub out every external dependency of place_signal_order."""
    trader = FakeTrader()
    portfolio = SimpleNamespace(
        id=1,
        initial_capital=Decimal("100000"),
        cash_available=Decimal("100000"),
    )
    snapshot = {"total_value": 100_000.0, "holdings": []}

    async def fake_get_portfolio(db, user=None):
        return portfolio

    monkeypatch.setattr(tro, "get_or_create_sim_portfolio", fake_get_portfolio)
    monkeypatch.setattr(tro, "get_trader", lambda **kwargs: trader)

    # Lazily imported dependencies must be patched at their source modules.
    import backend.repositories.analysis as analysis_repo
    import backend.repositories.portfolio as portfolio_repo
    import backend.services.mock_trading_service as mts

    state = SimpleNamespace(
        trader=trader,
        portfolio=portfolio,
        snapshot=snapshot,
        sys_settings=None,
        holding=None,
    )

    async def fake_sys_settings(db):
        return state.sys_settings

    async def fake_get_holding(db, portfolio_id, ticker):
        return state.holding

    async def fake_snapshot(db, portfolio_id=None):
        return state.snapshot

    monkeypatch.setattr(analysis_repo, "get_system_settings", fake_sys_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", fake_get_holding)
    monkeypatch.setattr(mts, "get_portfolio_with_live_prices", fake_snapshot)
    return state


@pytest.mark.asyncio
async def test_hold_signal_is_not_actionable(env):
    result = await tro.place_signal_order(None, ticker="AAPL", row=_row(signal="Hold"), settings=_settings())
    assert result is None
    assert env.trader.requests == []


@pytest.mark.asyncio
async def test_buy_sizes_against_risk_budget(env):
    result = await tro.place_signal_order(None, ticker="AAPL", row=_row(), settings=_settings())
    assert result.status == "FILLED"
    (req,) = env.trader.requests
    # 1% of $100k = $1000 / $100 share = 10 shares, cash leverage by default.
    assert req.action == "BUY"
    assert req.quantity == 10.0
    assert req.leverage == 1.0
    assert req.stop_loss is None


@pytest.mark.asyncio
async def test_buy_attaches_exit_levels_and_sizes_off_stop(env):
    row = _row(chart_annotations={"stop_loss": 95.0, "target_price": 120.0})
    await tro.place_signal_order(None, ticker="AAPL", row=row, settings=_settings())
    (req,) = env.trader.requests
    # $1000 risk / $5 per-share risk = 200 shares, capped at 10% alloc = 100 shares.
    assert req.quantity == 100.0
    assert req.stop_loss == 95.0
    assert req.take_profit == 120.0


@pytest.mark.asyncio
async def test_kelly_ceiling_shrinks_position(env):
    row = _row(chart_annotations={"kelly_recommendation_pct": 0.5})
    await tro.place_signal_order(None, ticker="AAPL", row=row, settings=_settings())
    (req,) = env.trader.requests
    # Effective risk = min(1%, 0.5%) -> half the base size.
    assert req.quantity == 5.0


@pytest.mark.asyncio
async def test_strict_stop_loss_mode_skips_orders_without_stop(env):
    settings = _settings(strict_stop_loss_mode=True)
    result = await tro.place_signal_order(None, ticker="AAPL", row=_row(), settings=settings)
    assert result is None
    assert env.trader.requests == []


@pytest.mark.asyncio
async def test_no_price_skips_order(env):
    env.trader.price = 0.0
    result = await tro.place_signal_order(None, ticker="AAPL", row=_row(), settings=_settings())
    assert result is None


@pytest.mark.asyncio
async def test_alpaca_broker_requires_owner(env):
    env.sys_settings = SimpleNamespace(trading_mode="live", active_broker="alpaca")
    user = SimpleNamespace(is_owner=False)
    result = await tro.place_signal_order(None, ticker="AAPL", row=_row(), settings=_settings(), user=user)
    assert result is None
    assert env.trader.requests == []


@pytest.mark.asyncio
async def test_concentration_cap_reduces_quantity(env):
    # $24,500 already in AAPL with a 25% ($25,000) single-name cap and a
    # $1,000 proposed order -> only $500 of headroom remains -> 5 shares.
    env.snapshot = {
        "total_value": 100_000.0,
        "holdings": [{"ticker": "AAPL", "market_value": 24_500.0}],
    }
    await tro.place_signal_order(None, ticker="AAPL", row=_row(), settings=_settings())
    (req,) = env.trader.requests
    assert req.quantity == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_risk_snapshot_failure_does_not_block_trading(env, monkeypatch):
    import backend.services.mock_trading_service as mts

    async def boom(db, portfolio_id=None):
        raise RuntimeError("price feed down")

    monkeypatch.setattr(mts, "get_portfolio_with_live_prices", boom)
    result = await tro.place_signal_order(None, ticker="AAPL", row=_row(), settings=_settings())
    assert result is not None
    (req,) = env.trader.requests
    assert req.quantity == 10.0


@pytest.mark.asyncio
async def test_sell_against_existing_long_is_a_close_not_a_short(env):
    env.holding = SimpleNamespace(side="long", quantity=Decimal("50"))
    row = _row(
        signal="Sell",
        chart_annotations={"stop_loss": 95.0, "target_price": 120.0, "recommended_leverage": 5},
    )
    await tro.place_signal_order(None, ticker="AAPL", row=row, settings=_settings())
    (req,) = env.trader.requests
    assert req.action == "SELL"
    # A pure close must not attach fresh leverage or exit levels.
    assert req.leverage == 1.0
    assert req.stop_loss is None
    assert req.take_profit is None


@pytest.mark.asyncio
async def test_sell_with_no_position_opens_short_with_exit_levels(env):
    row = _row(
        signal="Sell",
        chart_annotations={"stop_loss": 110.0, "target_price": 80.0, "recommended_leverage": 2},
    )
    await tro.place_signal_order(None, ticker="AAPL", row=row, settings=_settings(allow_short_selling=True))
    (req,) = env.trader.requests
    assert req.action == "SELL"
    assert req.leverage == 2.0
    assert req.stop_loss == 110.0
    assert req.take_profit == 80.0
    assert req.allow_short is True
