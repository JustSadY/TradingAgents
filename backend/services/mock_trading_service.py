import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.models.portfolio import Portfolio, Holding
from backend.models.order import Order

_logger = logging.getLogger(__name__)

# Default simulation commission rate (0.1%). Named constant for clarity and future
# configurability (e.g. reading from SystemSettings).
_DEFAULT_COMMISSION_RATE = Decimal("0.001")


async def _get_price(ticker: str) -> Optional[float]:
    """Fetch live price for a single ticker. Falls back to history if .info is unavailable."""
    import yfinance as yf
    def _fetch():
        try:
            t = yf.Ticker(ticker)  # single instantiation
            info = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price is None:
                hist = t.history(period="1d")  # reuse same instance
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            return float(price) if price is not None else None
        except Exception as e:
            _logger.warning("Price fetch failed for %s: %s", ticker, e)
            return None
    return await asyncio.to_thread(_fetch)


async def _get_prices_batch(tickers: list[str]) -> dict[str, float]:
    """Fetch live prices for multiple tickers in a single yfinance batch call.

    Replaces the previous N individual ``_get_price`` calls in
    ``get_portfolio_with_live_prices``, reducing N HTTP round-trips to 1.
    Falls back to individual ticker fetch for any that are missing from the
    batch result.
    """
    if not tickers:
        return {}
    import yfinance as yf

    def _batch_fetch():
        prices: dict[str, float] = {}
        unique = list(dict.fromkeys(tickers))  # preserve order, deduplicate
        try:
            data = yf.download(
                unique if len(unique) > 1 else unique[0],
                period="2d",
                progress=False,
                auto_adjust=True,
            )
            close = data["Close"] if "Close" in data.columns else data
            if hasattr(close, "columns"):  # multi-ticker DataFrame
                last_row = close.ffill().iloc[-1]
                for t in unique:
                    try:
                        prices[t] = float(last_row[t])
                    except (KeyError, TypeError, ValueError):
                        pass
            else:  # single-ticker Series
                val = float(close.ffill().iloc[-1])
                prices[unique[0]] = val
        except Exception as exc:
            _logger.debug("Batch price fetch failed (%s), will fall back per-ticker: %s", unique, exc)
        return prices

    prices = await asyncio.to_thread(_batch_fetch)
    # Fill any missing tickers with individual fallback
    missing = [t for t in tickers if t not in prices]
    if missing:
        fallbacks = await asyncio.gather(*[_get_price(t) for t in missing], return_exceptions=True)
        for t, p in zip(missing, fallbacks):
            if isinstance(p, float):
                prices[t] = p
    return prices


async def get_or_create_sim_portfolio(
    db: AsyncSession,
    initial_capital: float = 100_000.0,
    user=None,
    portfolio_id: Optional[int] = None,
) -> Portfolio:
    user_id = getattr(user, "id", None) if user is not None else None
    is_admin = getattr(user, "is_admin", False) if user is not None else False

    if portfolio_id is not None:
        q = select(Portfolio).where(Portfolio.id == portfolio_id)
        # IDOR guard: non-admin users can only access their own portfolio.
        if not is_admin and user_id is not None:
            q = q.where(Portfolio.user_id == user_id)
        result = await db.execute(q.options(selectinload(Portfolio.holdings)))
        portfolio = result.scalar_one_or_none()
        if portfolio is not None:
            return portfolio

    user_id = getattr(user, "id", None) if user is not None else None
    q = select(Portfolio).where(Portfolio.mode == "simulation")
    if user_id is not None:
        q = q.where(Portfolio.user_id == user_id)
    else:
        q = q.where(Portfolio.user_id.is_(None))
    result = await db.execute(q.options(selectinload(Portfolio.holdings)))
    portfolio = result.scalar_one_or_none()
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
    portfolio_id: Optional[int] = None,
) -> dict:
    user_id = getattr(user, "id", None) if user is not None else None
    is_admin = getattr(user, "is_admin", False) if user is not None else False

    if portfolio_id is not None:
        q = select(Portfolio).where(Portfolio.id == portfolio_id)
        # IDOR guard: non-admin users can only access their own portfolio.
        if not is_admin and user_id is not None:
            q = q.where(Portfolio.user_id == user_id)
        result = await db.execute(q.options(selectinload(Portfolio.holdings)))
        portfolio = result.scalar_one_or_none()
    else:
        user_id = getattr(user, "id", None) if user is not None else None
        q = select(Portfolio).where(Portfolio.mode == "simulation")
        if user_id is not None:
            q = q.where(Portfolio.user_id == user_id)
        else:
            q = q.where(Portfolio.user_id.is_(None))
        result = await db.execute(q.options(selectinload(Portfolio.holdings)))
        portfolio = result.scalar_one_or_none()
    if portfolio is None:
        portfolio = await get_or_create_sim_portfolio(db, user=user, portfolio_id=portfolio_id)
    tickers = [h.ticker for h in portfolio.holdings]
    prices: dict[str, float] = {}
    if tickers:
        prices = await _get_prices_batch(tickers)
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
        holdings_data.append({
            "ticker": h.ticker,
            "quantity": float(h.quantity),
            "avg_buy_price": float(h.avg_buy_price),
            "current_price": float(price),
            "market_value": round(float(market_value), 2),
            "unrealized_pnl": round(float(unrealized_pnl), 2),
            "pnl_pct": round(float(pnl_pct), 2),
        })
    total_value = portfolio.cash_available + positions_value
    total_pnl = total_value - portfolio.initial_capital
    total_pnl_pct = (total_pnl / portfolio.initial_capital * Decimal("100")) if portfolio.initial_capital else Decimal("0.0")
    portfolio.current_balance = total_value
    try:
        await db.flush()
    except Exception:
        await db.rollback()
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


async def _get_output_lang(db: AsyncSession, user=None) -> str:
    if user is None:
        return "English"
    try:
        from backend.services.settings_service import get_or_create_settings
        settings = await get_or_create_settings(db, user_id=user.id)
        if settings and settings.output_language:
            return settings.output_language
    except Exception:
        pass
    return "English"


async def execute_order(
    db: AsyncSession,
    ticker: str,
    action: str,
    quantity: float,
    analysis_id: Optional[int] = None,
    user=None,
    portfolio_id: Optional[int] = None,
) -> dict:
    action = action.upper()
    if action not in ("BUY", "SELL"):
        raise ValueError("action must be BUY or SELL")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    price_val = await _get_price(ticker)
    if price_val is None:
        raise ValueError(f"Could not fetch price for {ticker}")
    
    price = Decimal(str(price_val))
    qty_dec = Decimal(str(quantity))
    
    lang = await _get_output_lang(db, user)
    is_tr = lang.strip().lower() in ("turkish", "türkçe")
    
    portfolio = await get_or_create_sim_portfolio(db, user=user, portfolio_id=portfolio_id)
    total_cost = price * qty_dec
    commission = (total_cost * _DEFAULT_COMMISSION_RATE).quantize(Decimal("0.0001"))
    if action == "BUY":
        required = total_cost + commission
        if portfolio.cash_available < required:
            if is_tr:
                raise ValueError(
                    f"Yetersiz bakiye. Gerekli: ${float(required):.2f}, Mevcut: ${float(portfolio.cash_available):.2f}"
                )
            else:
                raise ValueError(
                    f"Insufficient funds. Required: ${float(required):.2f}, Available: ${float(portfolio.cash_available):.2f}"
                )
        portfolio.cash_available -= required
        result = await db.execute(
            select(Holding).where(
                Holding.portfolio_id == portfolio.id,
                Holding.ticker == ticker,
            )
        )
        holding = result.scalar_one_or_none()
        if holding:
            new_qty = holding.quantity + qty_dec
            holding.avg_buy_price = (
                (holding.avg_buy_price * holding.quantity + price * qty_dec) / new_qty
            )
            holding.quantity = new_qty
        else:
            db.add(Holding(
                portfolio_id=portfolio.id,
                ticker=ticker,
                quantity=qty_dec,
                avg_buy_price=price,
                current_price=price,
                unrealized_pnl=Decimal("0.0"),
            ))
    else:
        result = await db.execute(
            select(Holding).where(
                Holding.portfolio_id == portfolio.id,
                Holding.ticker == ticker,
            )
        )
        holding = result.scalar_one_or_none()
        if holding is None or holding.quantity < qty_dec:
            available = holding.quantity if holding else Decimal("0.0")
            if is_tr:
                raise ValueError(f"Yetersiz pozisyon. Mevcut: {float(available):.4f}, Satılmak istenen: {quantity}")
            else:
                raise ValueError(f"Insufficient position. Available: {float(available):.4f}, Requested to sell: {quantity}")
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
        executed_at=datetime.now(timezone.utc),
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
    user_id = getattr(user, "id", None) if user is not None else None
    q = select(Portfolio).where(Portfolio.mode == "simulation")
    if user_id is not None:
        q = q.where(Portfolio.user_id == user_id)
    else:
        q = q.where(Portfolio.user_id.is_(None))
    result = await db.execute(q.options(selectinload(Portfolio.holdings)))
    portfolio = result.scalar_one_or_none()
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
    lang = await _get_output_lang(db, user)
    is_tr = lang.strip().lower() in ("turkish", "türkçe")
    msg = "Portföy sıfırlandı" if is_tr else "Portfolio reset"
    return {"message": msg, "initial_capital": initial_capital}


async def get_performance(db: AsyncSession, user=None) -> dict:
    portfolio_data = await get_portfolio_with_live_prices(db, user=user)
    user_id = getattr(user, "id", None) if user is not None else None
    q = select(Portfolio).where(Portfolio.mode == "simulation")
    if user_id is not None:
        q = q.where(Portfolio.user_id == user_id)
    else:
        q = q.where(Portfolio.user_id.is_(None))
    result = await db.execute(q)
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        return portfolio_data
    spy_return_pct = None
    try:
        import yfinance as yf
        def _spy():
            spy = yf.Ticker("SPY").history(period="1y")
            if len(spy) >= 2:
                return float((spy["Close"].iloc[-1] - spy["Close"].iloc[0]) / spy["Close"].iloc[0] * 100)
            return None
        spy_return_pct = await asyncio.to_thread(_spy)
    except Exception:
        pass
    return {
        **portfolio_data,
        "benchmark_ticker": "SPY",
        "benchmark_return_pct": round(spy_return_pct, 2) if spy_return_pct is not None else None,
        "alpha_pct": round(portfolio_data["total_pnl_pct"] - spy_return_pct, 2)
        if spy_return_pct is not None else None,
    }
