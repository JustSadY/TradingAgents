"""Agent-facing conditional volatility forecasting.

The trailing volatility in `quant_tools` describes the sample it was measured
over. This tool answers the forward question the risk agents actually need —
what volatility to expect over the next N trading days — by fitting a
GARCH-family model to the return series.

The numbers are computed deterministically in `volatility_service`; the model
receives them already rendered and reasons about them.
"""

import io
import logging
from typing import Annotated

import pandas as pd
from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor

_logger = logging.getLogger(__name__)

# GARCH needs a few hundred observations before the parameters mean much.
_LOOKBACK_YEARS = 2


@tool
async def get_volatility_forecast(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"],
    horizon_days: Annotated[int, "forecast horizon in trading days (1-60)"] = 10,
    model: Annotated[str, "volatility model: 'garch', 'tarch' (asymmetric) or 'egarch'"] = "tarch",
) -> str:
    """Forecast expected volatility and value at risk with a GARCH-family model.

    Use this for forward-looking risk sizing: expected volatility over the next
    N trading days, the value at risk and expected shortfall it implies, and
    whether volatility shocks are currently persistent or mean-reverting.
    """
    from backend.services.volatility_service import (
        VolatilityError,
        describe_forecast,
        forecast_volatility,
        returns_from_prices,
    )

    try:
        start_date = (pd.to_datetime(curr_date) - pd.DateOffset(years=_LOOKBACK_YEARS)).strftime("%Y-%m-%d")
        csv_payload = await route_to_vendor("get_stock_data", symbol, start_date, curr_date)

        lines = [line for line in csv_payload.splitlines() if line and not line.startswith("#")]
        if not lines:
            return f"Error: no price history available for {symbol.upper()}."

        frame = pd.read_csv(io.StringIO("\n".join(lines)))
        if "Close" not in frame.columns:
            return f"Error: price history for {symbol.upper()} has no Close column."

        returns = returns_from_prices(frame["Close"])
        forecast = forecast_volatility(
            returns,
            model=str(model or "tarch").lower(),
            horizon_days=int(horizon_days),
        )
        return describe_forecast(symbol, forecast)
    except VolatilityError as exc:
        # A refusal the agent can act on, not a stack trace.
        return f"Volatility forecast unavailable for {symbol.upper()}: {exc}"
    except Exception as exc:  # noqa: BLE001 — vendor/parse failures must not kill the run
        _logger.warning("Volatility forecast failed for %s: %s", symbol, exc)
        return f"Error: volatility forecast failed for {symbol.upper()}: {exc}"
