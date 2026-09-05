from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.repositories import portfolio as portfolio_repo
from backend.services import mock_trading_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _portfolio_fixture():
    now = datetime.now(UTC)
    holding = SimpleNamespace(
        ticker="AAPL",
        quantity=Decimal("2"),
        avg_buy_price=Decimal("50"),
        current_price=Decimal("50"),
        unrealized_pnl=Decimal("0"),
        entry_commission=Decimal("0"),
        side="long",
        leverage=Decimal("1"),
        margin_used=Decimal("0"),
        borrowed_amount=Decimal("0"),
        interest_accrued=Decimal("0"),
        interest_updated_at=now,
        liquidation_price=Decimal("0"),
        stop_loss=Decimal("0"),
        take_profit=Decimal("0"),
        opened_at=now,
    )
    return SimpleNamespace(
        id=7,
        mode="simulation",
        broker="paper",
        initial_capital=Decimal("1000"),
        current_balance=Decimal("1000"),
        cash_available=Decimal("900"),
        margin_used=Decimal("0"),
        holdings=[holding],
    )


@pytest.mark.asyncio
async def test_read_snapshot_can_release_db_before_live_price_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    portfolio = _portfolio_fixture()

    async def fake_get_portfolio(*_args, **_kwargs):
        return portfolio

    async def fake_prices(tickers: list[str]):
        assert tickers == ["AAPL"]
        assert db.commits == 1
        return {"AAPL": 60.0}

    monkeypatch.setattr(portfolio_repo, "get_portfolio_by_id", fake_get_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_live_prices_batch", fake_prices)
    monkeypatch.setattr(mock_trading_service, "is_trading_day", lambda *_a, **_k: True)

    result = await mock_trading_service.get_portfolio_with_live_prices(
        db,
        portfolio_id=portfolio.id,
        read_only=True,
        release_before_price_io=True,
    )

    assert db.commits == 1
    assert result["holdings"][0]["current_price"] == 60.0
    assert result["total_value"] == 1020.0


@pytest.mark.asyncio
async def test_snapshot_default_does_not_commit_caller_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    portfolio = _portfolio_fixture()

    async def fake_get_portfolio(*_args, **_kwargs):
        return portfolio

    async def fake_prices(_tickers: list[str]):
        assert db.commits == 0
        return {"AAPL": 60.0}

    monkeypatch.setattr(portfolio_repo, "get_portfolio_by_id", fake_get_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_live_prices_batch", fake_prices)
    monkeypatch.setattr(mock_trading_service, "is_trading_day", lambda *_a, **_k: True)

    await mock_trading_service.get_portfolio_with_live_prices(
        db,
        portfolio_id=portfolio.id,
        read_only=True,
    )

    assert db.commits == 0


@pytest.mark.asyncio
async def test_release_before_price_io_is_rejected_for_write_snapshots() -> None:
    db = _TrackingDB()

    with pytest.raises(ValueError, match="requires read_only=True"):
        await mock_trading_service.get_portfolio_with_live_prices(
            db,
            portfolio_id=1,
            read_only=False,
            release_before_price_io=True,
        )

    assert db.commits == 0
