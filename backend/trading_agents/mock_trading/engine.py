import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
import yfinance as yf
from .portfolio_manager import PortfolioManager
from .order_manager import OrderManager, PriceType
from .corporate_actions import CorporateActionsHandler
from .database import TradingDatabase
logger = logging.getLogger(__name__)
class MockTradingEngine:
    def __init__(self, portfolio_id: int, initial_capital: float,
                 db: TradingDatabase = None, slippage_tolerance_pct: float = 1.0):
        self.portfolio_id = portfolio_id
        self.portfolio_mgr = PortfolioManager(portfolio_id, initial_capital)
        self.order_mgr = OrderManager()
        self.corporate_actions_handler = CorporateActionsHandler()
        self.db = db
        self.slippage_tolerance_pct = slippage_tolerance_pct
        self.watchlist = {}
    def add_to_watchlist(self, ticker: str):
        try:
            self.watchlist[ticker] = yf.Ticker(ticker)
            logger.info(f"Added {ticker} to watchlist")
        except Exception as e:
            logger.error(f"Failed to add {ticker} to watchlist: {e}")
    def get_current_price(self, ticker: str) -> Optional[float]:
        try:
            if ticker not in self.watchlist:
                self.add_to_watchlist(ticker)
            ticker_obj = self.watchlist[ticker]
            price = ticker_obj.info.get("currentPrice")
            if price is None:
                hist = ticker_obj.history(period="1d")
                if not hist.empty:
                    price = hist["Close"].iloc[-1]
            return price
        except Exception as e:
            logger.error(f"Failed to get price for {ticker}: {e}")
            return None
    def get_historical_prices(self, ticker: str, start_date: str = None,
                             end_date: str = None, period: str = "1mo") -> Dict:
        try:
            if ticker not in self.watchlist:
                self.add_to_watchlist(ticker)
            ticker_obj = self.watchlist[ticker]
            if start_date and end_date:
                hist = ticker_obj.history(start=start_date, end=end_date)
            else:
                hist = ticker_obj.history(period=period)
            result = {}
            for date, row in hist.iterrows():
                result[date.strftime("%Y-%m-%d")] = {
                    "open": float(row["Open"]),
                    "close": float(row["Close"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                }
            return result
        except Exception as e:
            logger.error(f"Failed to get historical prices for {ticker}: {e}")
            return {}
    def create_buy_order(self, ticker: str, quantity: float, price_type: PriceType,
                        reference_price: float) -> str:
        return self.order_mgr.create_order(
            ticker, "BUY", quantity, price_type, reference_price,
            self.slippage_tolerance_pct
        )
    def create_sell_order(self, ticker: str, quantity: float, price_type: PriceType,
                         reference_price: float) -> str:
        return self.order_mgr.create_order(
            ticker, "SELL", quantity, price_type, reference_price,
            self.slippage_tolerance_pct
        )
    def execute_order(self, order_id: str, execution_price: float,
                     quantity_filled: float, available_volume: float,
                     fees: float = 0.0) -> bool:
        order = self.order_mgr.get_order(order_id)
        if not order:
            logger.error(f"Order {order_id} not found")
            return False
        if not self.order_mgr.execute_order(order_id, execution_price,
                                           quantity_filled, available_volume):
            logger.warning(f"Order {order_id} failed/rejected")
            return False
        ticker = order.ticker
        if order.transaction_type == "BUY":
            success = self.portfolio_mgr.buy(ticker, quantity_filled, execution_price, fees)
        else:
            success = self.portfolio_mgr.sell(ticker, quantity_filled, execution_price, fees)
        if success and self.db:
            self.db.add_transaction(
                self.portfolio_id, order.transaction_type, ticker,
                order.quantity_requested, quantity_filled,
                order.status.value, order.price_type.value,
                execution_price, order.get_total_value(),
                self.order_mgr.get_slippage(order_id), fees
            )
        return success
    def update_prices(self, ticker_prices: Dict[str, float]):
        for ticker, price in ticker_prices.items():
            self.portfolio_mgr.update_holding_price(ticker, price)
    def get_portfolio_value(self) -> float:
        prices = {}
        for ticker in self.portfolio_mgr.holdings.keys():
            price = self.get_current_price(ticker)
            if price:
                prices[ticker] = price
        return self.portfolio_mgr.get_portfolio_value(prices)
    def get_portfolio_summary(self) -> Dict:
        prices = {}
        for ticker in self.portfolio_mgr.holdings.keys():
            price = self.get_current_price(ticker)
            if price:
                prices[ticker] = price
        metrics = self.portfolio_mgr.get_performance_metrics(prices)
        return {
            "portfolio_id": self.portfolio_id,
            "initial_capital": self.portfolio_mgr.initial_capital,
            "metrics": metrics,
            "holdings": self.portfolio_mgr.get_all_holdings(),
            "order_summary": self.order_mgr.get_all_orders_summary(),
        }
    def create_daily_snapshot(self, date: str) -> bool:
        if not self.db:
            return False
        prices = {}
        for ticker in self.portfolio_mgr.holdings.keys():
            price = self.get_current_price(ticker)
            if price:
                prices[ticker] = price
        portfolio_value = self.portfolio_mgr.get_portfolio_value(prices)
        positions_value = self.portfolio_mgr.get_holdings_value(prices)
        cash = self.portfolio_mgr.cash_available
        invested = portfolio_value - cash
        daily_return = ((portfolio_value - self.portfolio_mgr.initial_capital) /
                       self.portfolio_mgr.initial_capital * 100) if self.portfolio_mgr.initial_capital > 0 else 0
        try:
            self.db.add_daily_snapshot(
                self.portfolio_id, date, portfolio_value, cash, invested,
                daily_return=daily_return, cumulative_return=daily_return
            )
            logger.info(f"Created daily snapshot for {date}: ${portfolio_value:.2f}")
            return True
        except Exception as e:
            logger.error(f"Failed to create daily snapshot: {e}")
            return False
    def to_dict(self) -> Dict:
        return {
            "portfolio_id": self.portfolio_id,
            "portfolio": self.portfolio_mgr.to_dict(),
            "order_summary": self.order_mgr.get_all_orders_summary(),
            "watchlist": list(self.watchlist.keys()),
            "corporate_actions": self.corporate_actions_handler.to_dict(),
        }
