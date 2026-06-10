import logging
import math
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.services.margin_engine import (
    DEFAULT_MAX_LEVERAGE,
    accrue_interest,
    clamp_leverage,
    is_liquidatable_long,
    liquidation_price_long,
    maintenance_rate_for_leverage,
    margin_required,
)


def _liquidation_for_holding(quantity: Decimal, borrowed: Decimal, leverage: Decimal) -> Decimal:
    """Liquidation price using the maintenance rate implied by the holding's leverage."""
    maintenance_rate = maintenance_rate_for_leverage(leverage)
    return liquidation_price_long(quantity, borrowed, maintenance_rate)
from backend.services.market_data_service import get_live_price, get_live_prices_batch

_logger = logging.getLogger(__name__)

# Default simulation commission rate (0.1%).
_DEFAULT_COMMISSION_RATE = Decimal("0.001")
_DUST = Decimal("1e-6")


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

    now = datetime.now(UTC)
    holdings_data = []
    positions_equity = Decimal("0.0")
    margin_used_total = Decimal("0.0")
    liquidations: list[dict] = []
    for h in list(portfolio.holdings):
        fetched = prices.get(h.ticker)
        if fetched is not None:
            price = Decimal(str(fetched))
        elif h.current_price is not None and h.current_price > 0:
            price = h.current_price
        else:
            price = h.avg_buy_price

        borrowed = h.borrowed_amount or Decimal("0.0")

        # Accrue simple interest on any borrowed funds since this holding was
        # last marked. Interest is charged from cash and tracked on the holding.
        if borrowed > 0:
            last_marked = h.updated_at or h.opened_at or now
            # Some DB drivers (e.g. SQLite) return naive datetimes; treat as UTC.
            if last_marked.tzinfo is None:
                last_marked = last_marked.replace(tzinfo=UTC)
            elapsed = Decimal(str(max(0.0, (now - last_marked).total_seconds())))
            interest = accrue_interest(borrowed, elapsed)
            if interest > 0:
                portfolio.cash_available -= interest
                h.interest_accrued = (h.interest_accrued or Decimal("0.0")) + interest

        # Force-liquidate a leveraged long whose equity has collapsed to the
        # maintenance threshold (price at/below the precomputed liquidation level).
        if is_liquidatable_long(price, h.liquidation_price or Decimal("0.0")):
            proceeds = price * h.quantity
            commission = (proceeds * _DEFAULT_COMMISSION_RATE).quantize(Decimal("0.0001"))
            realized = (price - h.avg_buy_price) * h.quantity - commission
            portfolio.cash_available += proceeds - borrowed - commission
            portfolio.margin_used -= h.margin_used or Decimal("0.0")
            db.add(
                Order(
                    portfolio_id=portfolio.id,
                    mode=portfolio.mode,
                    broker=portfolio.broker,
                    ticker=h.ticker,
                    action="SELL",
                    side=h.side,
                    leverage=h.leverage or Decimal("1.0"),
                    quantity_requested=h.quantity,
                    quantity_filled=h.quantity,
                    status="LIQUIDATED",
                    price_per_share=price,
                    total_value=proceeds,
                    commission=commission,
                    realized_pnl=realized,
                    executed_at=now,
                )
            )
            liquidations.append({"ticker": h.ticker, "price": float(price), "realized_pnl": round(float(realized), 2)})
            await db.delete(h)
            continue

        market_value = price * h.quantity
        equity = market_value - borrowed
        cost_basis = h.avg_buy_price * h.quantity
        # P&L on the trader's own equity (margin), not the leveraged notional.
        unrealized_pnl = market_value - cost_basis
        invested = (h.margin_used or Decimal("0.0")) or cost_basis
        pnl_pct = (unrealized_pnl / invested * Decimal("100")) if invested else Decimal("0.0")

        h.current_price = price
        h.unrealized_pnl = unrealized_pnl
        positions_equity += equity
        margin_used_total += h.margin_used or Decimal("0.0")
        holdings_data.append(
            {
                "ticker": h.ticker,
                "quantity": float(h.quantity),
                "avg_buy_price": float(h.avg_buy_price),
                "current_price": float(price),
                "side": h.side,
                "leverage": float(h.leverage or Decimal("1.0")),
                "market_value": round(float(market_value), 2),
                "equity": round(float(equity), 2),
                "borrowed_amount": round(float(borrowed), 2),
                "margin_used": round(float(h.margin_used or Decimal("0.0")), 2),
                "liquidation_price": round(float(h.liquidation_price or Decimal("0.0")), 2),
                "unrealized_pnl": round(float(unrealized_pnl), 2),
                "pnl_pct": round(float(pnl_pct), 2),
            }
        )

    portfolio.margin_used = margin_used_total
    # Account equity = free cash + the trader's equity in each position.
    total_value = portfolio.cash_available + positions_equity
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
        "margin_used": round(float(margin_used_total), 2),
        "positions_value": round(float(positions_equity), 2),
        "total_value": round(float(total_value), 2),
        "total_pnl": round(float(total_pnl), 2),
        "total_pnl_pct": round(float(total_pnl_pct), 2),
        "holdings": holdings_data,
        "liquidations": liquidations,
    }


async def execute_order(
    db: AsyncSession,
    ticker: str,
    action: str,
    quantity: float,
    analysis_id: int | None = None,
    user=None,
    portfolio_id: int | None = None,
    leverage: float = 1.0,
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

    lev = clamp_leverage(leverage, DEFAULT_MAX_LEVERAGE)

    price_val = await get_live_price(ticker)
    if price_val is None or not math.isfinite(price_val) or price_val <= 0:
        raise ValueError(get_message("invalid_price", lang, ticker=ticker))

    price = Decimal(str(price_val))
    qty_dec = Decimal(str(quantity))

    # Get or create the portfolio first
    portfolio = await get_or_create_sim_portfolio(db, user=user, portfolio_id=portfolio_id)

    # Re-fetch with lock to ensure atomic balance check and update
    stmt = select(Portfolio).where(Portfolio.id == portfolio.id).with_for_update()
    res = await db.execute(stmt)
    portfolio = res.scalar_one()

    notional = price * qty_dec
    commission = (notional * _DEFAULT_COMMISSION_RATE).quantize(Decimal("0.0001"))
    realized_pnl = Decimal("0.0")
    status = "FILLED"

    if action == "BUY":
        # Only the margin portion of a leveraged position is funded from cash;
        # the broker lends the rest (borrowed). Spot trades are leverage == 1.
        margin = margin_required(notional, lev)
        borrowed = notional - margin
        required = margin + commission
        if portfolio.cash_available < required:
            raise ValueError(
                get_message(
                    "insufficient_funds", lang, required=float(required), available=float(portfolio.cash_available)
                )
            )
        portfolio.cash_available -= required
        portfolio.margin_used = (portfolio.margin_used or Decimal("0.0")) + margin

        holding = await get_holding(db, portfolio.id, ticker)
        if holding:
            new_qty = holding.quantity + qty_dec
            holding.avg_buy_price = (holding.avg_buy_price * holding.quantity + price * qty_dec) / new_qty
            holding.quantity = new_qty
            holding.margin_used = (holding.margin_used or Decimal("0.0")) + margin
            holding.borrowed_amount = (holding.borrowed_amount or Decimal("0.0")) + borrowed
            # Blended leverage = total notional / total equity posted.
            holding.leverage = (
                (holding.margin_used + holding.borrowed_amount) / holding.margin_used
                if holding.margin_used > 0
                else Decimal("1.0")
            )
            holding.liquidation_price = _liquidation_for_holding(
                holding.quantity, holding.borrowed_amount, holding.leverage
            )
            holding.current_price = price
        else:
            db.add(
                Holding(
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    quantity=qty_dec,
                    avg_buy_price=price,
                    current_price=price,
                    unrealized_pnl=Decimal("0.0"),
                    side="long",
                    leverage=lev,
                    margin_used=margin,
                    borrowed_amount=borrowed,
                    liquidation_price=_liquidation_for_holding(qty_dec, borrowed, lev),
                )
            )
    else:
        holding = await get_holding(db, portfolio.id, ticker)
        if holding is None or holding.quantity < qty_dec:
            available = holding.quantity if holding else Decimal("0.0")
            raise ValueError(get_message("insufficient_position", lang, available=float(available), requested=quantity))

        # Close (fully or partially). Repay the borrowed principal pro-rata; the
        # remainder of the proceeds returns to free cash.
        fraction = qty_dec / holding.quantity
        repaid_borrowed = (holding.borrowed_amount or Decimal("0.0")) * fraction
        released_margin = (holding.margin_used or Decimal("0.0")) * fraction
        proceeds = notional
        realized_pnl = (price - holding.avg_buy_price) * qty_dec - commission

        portfolio.cash_available += proceeds - repaid_borrowed - commission
        portfolio.margin_used = (portfolio.margin_used or Decimal("0.0")) - released_margin
        lev = holding.leverage or Decimal("1.0")

        holding.quantity -= qty_dec
        holding.borrowed_amount = (holding.borrowed_amount or Decimal("0.0")) - repaid_borrowed
        holding.margin_used = (holding.margin_used or Decimal("0.0")) - released_margin
        if holding.quantity < _DUST:
            await db.delete(holding)
        else:
            holding.liquidation_price = _liquidation_for_holding(
                holding.quantity, holding.borrowed_amount, holding.leverage
            )
            holding.current_price = price

    order = Order(
        portfolio_id=portfolio.id,
        mode="simulation",
        broker="paper",
        ticker=ticker,
        action=action,
        side="long",
        leverage=lev,
        quantity_requested=qty_dec,
        quantity_filled=qty_dec,
        status=status,
        price_per_share=price,
        total_value=notional,
        commission=commission,
        realized_pnl=realized_pnl,
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
        "leverage": float(lev),
        "total_value": round(float(notional), 2),
        "commission": float(commission),
        "realized_pnl": round(float(realized_pnl), 2),
        "status": status,
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
        portfolio.margin_used = Decimal("0.0")
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
