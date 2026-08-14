from importlib.util import find_spec

from .alpaca import AlpacaTrader
from .base import BaseTraderInterface
from .simulation import SimulationTrader

_REGISTRY: dict[str, type[BaseTraderInterface]] = {
    "simulation": SimulationTrader,
    "alpaca": AlpacaTrader,
}


def _alpaca_class() -> type[BaseTraderInterface]:
    if find_spec("alpaca") is not None:
        from .alpaca_py import AlpacaPyTrader

        return AlpacaPyTrader
    return AlpacaTrader


def get_trader(
    mode: str,
    broker: str,
    portfolio_id: int = 1,
    initial_capital: float = 100_000.0,
    db=None,
) -> BaseTraderInterface:
    key = "alpaca" if broker == "alpaca" else ("simulation" if mode == "simulation" else broker)
    if key == "alpaca":
        cls = _alpaca_class()
        return cls(portfolio_id=portfolio_id, initial_capital=initial_capital, db=db, mode=mode)

    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(
            f"No trader implementation for mode={mode!r} broker={broker!r}. Available: {list(_REGISTRY.keys())}"
        )
    return cls(portfolio_id=portfolio_id, initial_capital=initial_capital, db=db)
