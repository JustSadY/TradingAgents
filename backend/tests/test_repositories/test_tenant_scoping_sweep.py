"""Systematic cross-tenant read isolation for user-owned repositories.

The existing tenant tests are targeted — checkpoints, presets, assistant, the
Ollama credential endpoint. This sweep is the generic counterpart: for every
repository read path listed here, seed rows for two users and assert a
non-admin only ever sees their own.

This is the bug class PostgreSQL RLS would defend against at the database
layer. Until that exists, application scoping is the only line, so it is worth
testing directly rather than by inspection.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.password_hashing import hash_password
from backend.models.alert import PriceAlert
from backend.models.analysis import AnalysisResult
from backend.models.portfolio import Portfolio
from backend.models.user import User
from backend.repositories.alerts import get_alert_by_id, list_alerts
from backend.repositories.analysis import get_analysis_by_id, list_analyses
from backend.repositories.common import scope_to_user
from backend.repositories.portfolio import get_portfolio_by_id, list_portfolios


@pytest.fixture
async def other_user(db: AsyncSession) -> User:
    user = User(
        username="tenant-b",
        hashed_password=hash_password("pass"),
        email="b@example.com",
        role="user",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_analysis(db: AsyncSession, user_id: int, ticker: str) -> AnalysisResult:
    row = AnalysisResult(
        user_id=user_id,
        ticker=ticker,
        trade_date="2026-08-14",
        signal="buy",
        status="completed",
    )
    db.add(row)
    await db.flush()
    return row


async def _seed_alert(db: AsyncSession, user_id: int, ticker: str) -> PriceAlert:
    row = PriceAlert(
        user_id=user_id,
        ticker=ticker,
        condition="above",
        target_price=100,
        auto_analyze=False,
        enabled=True,
    )
    db.add(row)
    await db.flush()
    return row


async def _seed_portfolio(db: AsyncSession, user_id: int) -> Portfolio:
    row = Portfolio(
        user_id=user_id,
        mode="simulation",
        broker="paper",
        initial_capital=Decimal("100000"),
        current_balance=Decimal("100000"),
        cash_available=Decimal("100000"),
    )
    db.add(row)
    await db.flush()
    return row


async def test_analysis_listing_excludes_another_tenant(db, test_user, other_user):
    await _seed_analysis(db, test_user.id, "MINE")
    await _seed_analysis(db, other_user.id, "THEIRS")

    tickers = {row.ticker for row in await list_analyses(db, user=test_user)}

    assert "MINE" in tickers
    assert "THEIRS" not in tickers


async def test_analysis_by_id_refuses_another_tenants_row(db, test_user, other_user):
    theirs = await _seed_analysis(db, other_user.id, "THEIRS")

    assert await get_analysis_by_id(db, theirs.id, user=test_user) is None
    # The row exists; it is the scoping that hides it, not a missing record.
    assert await db.get(AnalysisResult, theirs.id) is not None


async def test_alert_listing_excludes_another_tenant(db, test_user, other_user):
    await _seed_alert(db, test_user.id, "MINE")
    await _seed_alert(db, other_user.id, "THEIRS")

    tickers = {row.ticker for row in await list_alerts(db, user=test_user)}

    assert tickers == {"MINE"}


async def test_alert_by_id_refuses_another_tenants_row(db, test_user, other_user):
    theirs = await _seed_alert(db, other_user.id, "THEIRS")

    assert await get_alert_by_id(db, theirs.id, user=test_user) is None


async def test_portfolio_listing_excludes_another_tenant(db, test_user, other_user):
    mine = await _seed_portfolio(db, test_user.id)
    theirs = await _seed_portfolio(db, other_user.id)

    ids = {row.id for row in await list_portfolios(db, user=test_user)}

    assert mine.id in ids
    assert theirs.id not in ids


async def test_portfolio_by_id_refuses_another_tenants_row(db, test_user, other_user):
    theirs = await _seed_portfolio(db, other_user.id)

    assert await get_portfolio_by_id(db, theirs.id, user=test_user) is None


async def test_admin_deliberately_sees_every_tenant(db, test_user, other_user):
    """Admin bypass is intended; pinned so it stays a decision, not an accident."""
    await _seed_analysis(db, test_user.id, "MINE")
    await _seed_analysis(db, other_user.id, "THEIRS")
    # is_admin is derived from role, not settable.
    test_user.role = "admin"

    tickers = {row.ticker for row in await list_analyses(db, user=test_user)}

    assert {"MINE", "THEIRS"} <= tickers


def test_scope_to_user_returns_an_unscoped_query_for_no_user():
    """Passing no user disables scoping — a footgun worth stating out loud.

    ``scope_to_user(q, Model, None)`` returns every tenant's rows. That is
    intended for trusted background paths (cron, workers) which have no request
    user, but it means forgetting the argument on a request path is a silent
    IDOR rather than an error.
    """
    query = select(AnalysisResult)

    assert str(scope_to_user(query, AnalysisResult, None)) == str(query)
    a_user = SimpleNamespace(id=1, is_admin=False)
    assert str(scope_to_user(query, AnalysisResult, a_user)) != str(query)
