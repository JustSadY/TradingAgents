import logging
from typing import Dict, List, Optional
from datetime import datetime
logger = logging.getLogger(__name__)
class PortfolioManager:
    def __init__(self, portfolio_id: int, initial_capital: float):
        self.portfolio_id = portfolio_id
        self.initial_capital = initial_capital
        self.cash_available = initial_capital
        self.holdings = {}
        self.total_fees = 0.0
        self.total_dividends = 0.0
    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        positions_value = sum(
            holding["quantity_held"] * current_prices.get(ticker, holding.get("current_price", 0))
            for ticker, holding in self.holdings.items()
        )
        return self.cash_available + positions_value
    def get_holdings_value(self, current_prices: Dict[str, float]) -> float:
        return sum(
            holding["quantity_held"] * current_prices.get(ticker, holding.get("current_price", 0))
            for ticker, holding in self.holdings.items()
        )
    def buy(self, ticker: str, quantity: float, price: float, fees: float = 0.0) -> bool:
        total_cost = quantity * price + fees
        if total_cost > self.cash_available:
            logger.warning(f"Insufficient cash to buy {quantity} {ticker}: "
                          f"need ${total_cost:.2f}, have ${self.cash_available:.2f}")
            return False
        self.cash_available -= total_cost
        self.total_fees += fees
        if ticker in self.holdings:
            holding = self.holdings[ticker]
            total_shares = holding["quantity_held"] + quantity
            holding["avg_buy_price"] = (
                (holding["quantity_held"] * holding["avg_buy_price"] + quantity * price) / total_shares
            )
            holding["quantity_held"] = total_shares
        else:
            self.holdings[ticker] = {
                "quantity_held": quantity,
                "avg_buy_price": price,
                "current_price": price,
                "unrealized_pl": 0.0,
            }
        logger.info(f"Bought {quantity} {ticker} @ ${price:.2f} (fees: ${fees:.2f})")
        return True
    def sell(self, ticker: str, quantity: float, price: float, fees: float = 0.0) -> bool:
        if ticker not in self.holdings or self.holdings[ticker]["quantity_held"] < quantity:
            logger.warning(f"Insufficient position to sell {quantity} {ticker}")
            return False
        proceeds = quantity * price - fees
        self.cash_available += proceeds
        self.total_fees += fees
        avg_cost = self.holdings[ticker]["avg_buy_price"]
        realized_pl = (price - avg_cost) * quantity - fees
        self.holdings[ticker]["quantity_held"] -= quantity
        if self.holdings[ticker]["quantity_held"] <= 0:
            del self.holdings[ticker]
        logger.info(f"Sold {quantity} {ticker} @ ${price:.2f} (fees: ${fees:.2f}, realized P&L: ${realized_pl:.2f})")
        return True
    def add_dividend(self, ticker: str, dividend_cash: float):
        self.cash_available += dividend_cash
        self.total_dividends += dividend_cash
        logger.info(f"Added dividend from {ticker}: ${dividend_cash:.2f}")
    def update_holding_price(self, ticker: str, current_price: float):
        if ticker in self.holdings:
            holding = self.holdings[ticker]
            holding["current_price"] = current_price
            holding["unrealized_pl"] = (current_price - holding["avg_buy_price"]) * holding["quantity_held"]
    def get_holding(self, ticker: str) -> Optional[Dict]:
        return self.holdings.get(ticker)
    def get_all_holdings(self) -> List[Dict]:
        return [{"ticker": ticker, **holding} for ticker, holding in self.holdings.items()]
    def get_unrealized_pl(self) -> float:
        return sum(holding.get("unrealized_pl", 0.0) for holding in self.holdings.values())
    def get_realized_pl(self) -> float:
        return -self.total_fees
    def get_performance_metrics(self, current_prices: Dict[str, float]) -> Dict:
        portfolio_value = self.get_portfolio_value(current_prices)
        positions_value = self.get_holdings_value(current_prices)
        unrealized_pl = self.get_unrealized_pl()
        invested = self.initial_capital - self.cash_available + unrealized_pl + self.total_fees
        total_return = (portfolio_value - self.initial_capital) / self.initial_capital * 100 if self.initial_capital > 0 else 0
        return {
            "portfolio_value": portfolio_value,
            "cash_available": self.cash_available,
            "positions_value": positions_value,
            "unrealized_pl": unrealized_pl,
            "total_fees": self.total_fees,
            "total_dividends": self.total_dividends,
            "invested": invested,
            "total_return_pct": total_return,
            "num_positions": len(self.holdings),
        }
    def to_dict(self) -> Dict:
        return {
            "portfolio_id": self.portfolio_id,
            "initial_capital": self.initial_capital,
            "cash_available": self.cash_available,
            "holdings": self.holdings,
            "total_fees": self.total_fees,
            "total_dividends": self.total_dividends,
            "num_positions": len(self.holdings),
        }
