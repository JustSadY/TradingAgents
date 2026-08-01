import re

_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^]+$")

def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    """Validate *value* for safe use as a filesystem path component."""
    if not isinstance(value, str) or not value:
        raise ValueError("Ticker must be a non-empty string.")
    if len(value) > max_len:
        raise ValueError(f"Ticker too long (max {max_len}): {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(f"Ticker contains invalid characters: {value!r}")
    if set(value) == {"."}:
        raise ValueError(f"Ticker must not consist entirely of dots: {value!r}")
    return value

def resolve_benchmark(ticker: str, config: dict | None = None) -> str:
    """Return the appropriate benchmark ticker for *ticker*.

    Priority chain (mirrors ``performance_service.backfill_returns``):
    1. ``config["benchmark_ticker"]`` — explicit override.
    2. ``config["benchmark_map"]`` suffix match — e.g. ``".NS"`` → ``"^NSEI"``.
    3. ``config["benchmark_map"][""]`` — default entry in the map.
    4. Hard fallback: ``"SPY"``.

    Args:
        ticker:  The stock/asset ticker being analysed (e.g. ``"AAPL"``, ``"RELIANCE.NS"``).
        config:  Optional config dict (as returned by ``get_config()``).  When
                 ``None`` the function attempts to load it automatically.
    """
    if config is None:
        try:
            from backend.trading_agents.dataflows.config import get_config

            config = get_config()
        except Exception:
            config = {}

    explicit = config.get("benchmark_ticker")
    if explicit:
        return str(explicit)

    benchmark_map: dict = config.get("benchmark_map", {})
    ticker_upper = ticker.upper()

    for suffix in sorted(benchmark_map.keys(), key=len, reverse=True):
        if suffix and ticker_upper.endswith(suffix.upper()):
            return benchmark_map[suffix]

    return benchmark_map.get("", "SPY")
