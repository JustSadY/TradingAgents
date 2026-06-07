from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class OrderRequest:
    ticker: str
    action: str
    quantity: float
    reference_price: float
    ai_signal: str = ""
    ai_reasoning: str = ""


@dataclass
class OrderResult:
    order_id: str
    status: str
    filled_price: float | None
    filled_quantity: float | None
    commission: float = 0.0
    message: str = ""
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
