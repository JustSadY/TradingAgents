from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

@dataclass
class OrderRequest:
    ticker: str
    action: str
    quantity: Decimal
    reference_price: Decimal
    analysis_id: int | None = None
    ai_signal: str = ""
    ai_reasoning: str = ""
    leverage: float = 1.0
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    allow_short: bool = False

@dataclass
class OrderResult:
    order_id: str
    status: str
    filled_price: Decimal | None
    filled_quantity: Decimal | None
    commission: Decimal = Decimal("0")
    message: str = ""
    reason_code: str = ""
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

class BaseTraderInterface(ABC):
    @abstractmethod
    async def get_current_price(self, ticker: str) -> float | None: ...
    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult: ...
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...
    @abstractmethod
    async def get_balance(self) -> float: ...
    @abstractmethod
    async def get_positions(self) -> dict[str, dict]: ...
    @property
    @abstractmethod
    def mode(self) -> str: ...
    @property
    @abstractmethod
    def broker_name(self) -> str: ...

    @abstractmethod
    async def close(self) -> None:
        pass
