from __future__ import annotations

from types import SimpleNamespace

from backend.repositories.portfolio import get_or_create_simulation_portfolio


class _Result:
    def __init__(self, row) -> None:
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _ExistingPortfolioSession:
    def __init__(self, row) -> None:
        self.row = row
        self.execute_calls = 0

    async def execute(self, _statement):
        self.execute_calls += 1
        return _Result(self.row)

    async def refresh(self, *_args, **_kwargs):  # pragma: no cover - failure guard
        raise AssertionError("existing eager-loaded portfolio must not be refreshed")


async def test_get_or_create_existing_portfolio_does_not_refresh_holdings() -> None:
    portfolio = SimpleNamespace(id=17, holdings=[SimpleNamespace(ticker="AAPL")])
    db = _ExistingPortfolioSession(portfolio)

    result = await get_or_create_simulation_portfolio(
        db,
        user_id=7,
        initial_capital=100_000,
    )

    assert result is portfolio
    assert result.holdings[0].ticker == "AAPL"
    assert db.execute_calls == 1
