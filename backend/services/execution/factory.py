from .alpaca import AlpacaTrader
from .base import BaseTraderInterface
from .simulation import SimulationTrader

_REGISTRY: dict[str, type[BaseTraderInterface]] = {
    "simulation": SimulationTrader,
    "alpaca": AlpacaTrader,
}


def get_trader(
    mode: str,
    broker: str,
    portfolio_id: int = 1,
    initial_capital: float = 100_000.0,
    db=None,
) -> BaseTraderInterface:
    key = "alpaca" if broker == "alpaca" else ("simulation" if mode == "simulation" else broker)
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(
            f"No trader implementation for mode={mode!r} broker={broker!r}. Available: {list(_REGISTRY.keys())}"
        )
    if cls is AlpacaTrader:
        # Broker calls are external, irreversible side effects. The adapter
        # therefore ends each short credential/audit DB phase before entering
        # alpaca-py network I/O instead of pinning a SQL connection while the
        # broker responds. Direct AlpacaTrader construction keeps this opt-in
        # so isolated tests and specialist callers can retain manual control.
        return cls(
            portfolio_id=portfolio_id,
            initial_capital=initial_capital,
            db=db,
            mode=mode,
            release_db_before_network=True,
        )
    return cls(portfolio_id=portfolio_id, initial_capital=initial_capital, db=db)
