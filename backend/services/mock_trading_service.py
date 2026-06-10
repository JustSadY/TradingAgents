import logging
import math
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.services.market_data_service import get_live_price, get_live_prices_batch

_logger = logging.getLogger(__name__)

# Default simulation commission rate (0.1%).
_DEFAULT_COMMISSION_RATE = Decimal("0.001")


async def get_or_create_sim_portfolio(
    db: AsyncSession,
    initial_capital: float = 100_000.0,
    user=None,
    portfolio_id: int | None = None,
) -> Portfolio:
    from backend.repositories.portfolio import get_portfolio_by_id, get_simulation_portfolio

    user_id = getattr(user, "id", None) if user is not None else None

    if portfolio_id is not None:
        portfolio = await get_portfolio_by_id(db, portfolio_id, user=user)
        if portfolio:
            return portfolio

    portfolio = await get_simulation_portfolio(db, user_id=user_id)
    if portfolio is None:
        initial_capital_dec = Decimal(str(initial_capital))
        portfolio = Portfolio(
            mode="simulation",
            broker="paper",
            initial_capital=initial_capital_dec,
            current_balance=initial_capital_dec,
            cash_available=initial_capital_dec,
            status="active",
            user_id=user_id,
        )
        db.add(portfolio)
        await db.flush()
        await db.refresh(portfolio, ["holdings"])
    return portfolio


async def get_portfolio_with_live_prices(
    db: AsyncSession,
    user=None,
    portfolio_id: int | None = None,
) -> dict:
    from backend.repositories.portfolio import get_portfolio_by_id, get_simulation_portfolio

    user_id = getattr(user, "id", None) if user is not None else None

    if portfolio_id is not None:
        portfolio = await get_portfolio_by_id(db, portfolio_id, user=user)
    else:
        portfolio = await get_simulation_portfolio(db, user_id=user_id)

    if portfolio is None:
        portfolio = await get_or_create_sim_portfolio(db, user=user, portfolio_id=portfolio_id)

    tickers = [h.ticker for h in portfolio.holdings]
    prices: dict[str, float] = {}
    if tickers:
        prices = await get_live_prices_batch(tickers)

    holdings_data = []
    positions_value = Decimal("0.0")
    for h in portfolio.holdings:
        fetched = prices.get(h.ticker)
        if fetched is not None:
            price = Decimal(str(fetched))
        elif h.current_price is not None:
            price = h.current_price
        else:
            price = h.avg_buy_price

        cost_basis = h.avg_buy_price * h.quantity
        market_value = price * h.quantity
        unrealized_pnl = market_value - cost_basis
        pnl_pct = (unrealized_pnl / cost_basis * Decimal("100")) if cost_basis else Decimal("0.0")

        h.current_price = price
        h.unrealized_pnl = unrealized_pnl
        positions_value += market_value
        holdings_data.append(
            {
                "ticker": h.ticker,
                "quantity": float(h.quantity),
                "avg_buy_price": float(h.avg_buy_price),
                "current_price": float(price),
                "market_value": round(float(market_value), 2),
                "unrealized_pnl": round(float(unrealized_pnl), 2),
                "pnl_pct": round(float(pnl_pct), 2),
            }
        )

    total_value = portfolio.cash_available + positions_value
    total_pnl = total_value - portfolio.initial_capital
    total_pnl_pct = (
        (total_pnl / portfolio.initial_capital * Decimal("100")) if portfolio.initial_capital else Decimal("0.0")
    )

    portfolio.current_balance = total_value
    await db.flush()

    return {
        "id": portfolio.id,
        "mode": portfolio.mode,
        "initial_capital": float(portfolio.initial_capital),
        "cash_available": round(float(portfolio.cash_available), 2),
        "positions_value": round(float(positions_value), 2),
        "total_value": round(float(total_value), 2),
        "total_pnl": round(float(total_pnl), 2),
        "total_pnl_pct": round(float(total_pnl_pct), 2),
        "holdings": holdings_data,
    }


async def execute_order(
    db: AsyncSession,
    ticker: str,
    action: str,
    quantity: float,
    analysis_id: int | None = None,
    user=None,
    portfolio_id: int | None = None,
) -> dict:
    from backend.core.l10n import get_message
    from backend.repositories.portfolio import get_holding
    from backend.services.settings_service import get_user_language

    lang = await get_user_language(db, user)

    action = action.upper()
    if action not in ("BUY", "SELL"):
        raise ValueError(get_message("invalid_action", lang))
    if not math.isfinite(quantity) or quantity <= 0:
        raise ValueError("quantity must be a positive finite number")

    price_val = await get_live_price(ticker)
    if price_val is None or not math.isfinite(price_val) or price_val <= 0:
        raise ValueError(get_message("invalid_price", lang, ticker=ticker))

    price = Decimal(str(price_val))
    qty_dec = Decimal(str(quantity))

    # Get or create the portfolio first
    portfolio = await get_or_create_sim_portfolio(db, user=user, portfolio_id=portfolio_id)

    # Re-fetch with lock to ensure atomic bakiye check and update
    stmt = select(Portfolio).where(Portfolio.id == portfolio.id).with_for_update()
    res = await db.execute(stmt)
    portfolio = res.scalar_one()

    total_cost = price * qty_dec
    commission = (total_cost * _DEFAULT_COMMISSION_RATE).quantize(Decimal("0.0001"))

    if action == "BUY":
        required = total_cost + commission
        if portfolio.cash_available < required:
            raise ValueError(
                get_message(
                    "insufficient_funds", lang, required=float(required), available=float(portfolio.cash_available)
                )
            )
        portfolio.cash_available -= required
        holding = await get_holding(db, portfolio.id, ticker)
        if holding:
            new_qty = holding.quantity + qty_dec
            holding.avg_buy_price = (holding.avg_buy_price * holding.quantity + price * qty_dec) / new_qty
            holding.quantity = new_qty
        else:
            db.add(
                Holding(
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    quantity=qty_dec,
                    avg_buy_price=price,
                    current_price=price,
                    unrealized_pnl=Decimal("0.0"),
                )
            )
    else:
        holding = await get_holding(db, portfolio.id, ticker)
        if holding is None or holding.quantity < qty_dec:
            available = holding.quantity if holding else Decimal("0.0")
            raise ValueError(get_message("insufficient_position", lang, available=float(available), requested=quantity))
        portfolio.cash_available += total_cost - commission
        holding.quantity -= qty_dec
        if holding.quantity < Decimal("1e-6"):
            await db.delete(holding)

    order = Order(
        portfolio_id=portfolio.id,
        mode="simulation",
        broker="paper",
        ticker=ticker,
        action=action,
        quantity_requested=qty_dec,
        quantity_filled=qty_dec,
        status="FILLED",
        price_per_share=price,
        total_value=total_cost,
        commission=commission,
        analysis_id=analysis_id,
        executed_at=datetime.now(UTC),
    )
    db.add(order)
    await db.flush()
    return {
        "order_id": order.id,
        "ticker": ticker,
        "action": action,
        "quantity": float(qty_dec),
        "price": float(price),
        "total_value": round(float(total_cost), 2),
        "commission": float(commission),
        "status": "FILLED",
    }


async def reset_portfolio(db: AsyncSession, initial_capital: float = 100_000.0, user=None) -> dict:
    from backend.repositories.portfolio import get_simulation_portfolio

    user_id = getattr(user, "id", None) if user is not None else None
    portfolio = await get_simulation_portfolio(db, user_id=user_id)

    initial_capital_dec = Decimal(str(initial_capital))
    if portfolio:
        await db.execute(delete(Order).where(Order.portfolio_id == portfolio.id))
        await db.execute(delete(Holding).where(Holding.portfolio_id == portfolio.id))
        portfolio.cash_available = initial_capital_dec
        portfolio.current_balance = initial_capital_dec
        portfolio.initial_capital = initial_capital_dec
    else:
        portfolio = Portfolio(
            mode="simulation",
            broker="paper",
            initial_capital=initial_capital_dec,
            current_balance=initial_capital_dec,
            cash_available=initial_capital_dec,
            status="active",
            user_id=user_id,
        )
        db.add(portfolio)

    await db.flush()
    from backend.core.l10n import get_message
    from backend.services.settings_service import get_user_language

    lang = await get_user_language(db, user)
    msg = get_message("portfolio_reset", lang)
    return {"message": msg, "initial_capital": initial_capital}


async def get_performance(db: AsyncSession, user=None) -> dict:
    portfolio_data = await get_portfolio_with_live_prices(db, user=user)

    from backend.services.market_data_service import get_benchmark_return

    spy_return_pct = await get_benchmark_return("SPY", period="1y")

    return {
        **portfolio_data,
        "benchmark_ticker": "SPY",
        "benchmark_return_pct": round(spy_return_pct, 2) if spy_return_pct is not None else None,
        "alpha_pct": round(portfolio_data["total_pnl_pct"] - (spy_return_pct or 0.0), 2)
        if spy_return_pct is not None
        else None,
    }
