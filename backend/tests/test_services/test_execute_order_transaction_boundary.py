from __future__ import annotations

import pytest

from backend.services import mock_trading_service, settings_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_execute_order_can_release_db_before_live_price_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    async def fake_language(*_args, **_kwargs):
        return "English"

    async def fake_price(ticker: str):
        assert ticker == "AAPL"
        assert db.commits == 1
        raise RuntimeError("price boundary reached")

    monkeypatch.setattr(settings_service, "get_user_language", fake_language)
    monkeypatch.setattr(mock_trading_service, "get_live_price", fake_price)

    with pytest.raises(RuntimeError, match="price boundary reached"):
        await mock_trading_service.execute_order(
            db,
            ticker="AAPL",
            action="BUY",
            quantity=1.0,
            release_before_price_io=True,
        )

    assert db.commits == 1


@pytest.mark.asyncio
async def test_execute_order_default_preserves_caller_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    async def fake_language(*_args, **_kwargs):
        return "English"

    async def fake_price(_ticker: str):
        assert db.commits == 0
        raise RuntimeError("price boundary reached")

    monkeypatch.setattr(settings_service, "get_user_language", fake_language)
    monkeypatch.setattr(mock_trading_service, "get_live_price", fake_price)

    with pytest.raises(RuntimeError, match="price boundary reached"):
        await mock_trading_service.execute_order(
            db,
            ticker="AAPL",
            action="BUY",
            quantity=1.0,
        )

    assert db.commits == 0
