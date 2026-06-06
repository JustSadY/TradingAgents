from .base import BaseTraderInterface
from .simulation import SimulationTrader
_REGISTRY: dict[str, type[BaseTraderInterface]] = {
    "simulation": SimulationTrader,
}
def get_trader(
    mode: str,
    broker: str,
    portfolio_id: int = 1,
    initial_capital: float = 100_000.0,
    db=None,
) -> BaseTraderInterface:
    key = "simulation" if mode == "simulation" else broker
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(
            f"No trader implementation for mode={mode!r} broker={broker!r}. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return cls(portfolio_id=portfolio_id, initial_capital=initial_capital, db=db)
