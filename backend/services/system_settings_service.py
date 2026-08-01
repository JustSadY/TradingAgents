from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import is_live_trading_enabled
from backend.models.system_settings import SystemSettings
from backend.repositories import system_settings as repo

_TRADING_MODES = {"simulation", "live"}
_BROKERS = {"simulation", "alpaca"}
_TRADING_FIELDS = {"trading_mode", "active_broker"}

class InvalidTradingConfiguration(ValueError):
    """Raised when a server trading configuration cannot safely execute."""

def validate_trading_configuration(trading_mode: str, active_broker: str) -> None:
    """Validate the effective mode/broker pair before persisting it.

    The executor independently checks the feature flag as a defense in depth;
    rejecting an invalid update here keeps the admin UI from advertising a
    configuration that will never be allowed to place a real-money order.
    """
    if trading_mode not in _TRADING_MODES:
        raise InvalidTradingConfiguration(f"Unsupported trading mode: {trading_mode!r}")
    if active_broker not in _BROKERS:
        raise InvalidTradingConfiguration(f"Unsupported active broker: {active_broker!r}")
    if trading_mode == "live" and active_broker != "alpaca":
        raise InvalidTradingConfiguration("Live trading requires active_broker='alpaca'.")
    if trading_mode == "live" and not is_live_trading_enabled():
        raise InvalidTradingConfiguration("Live trading is disabled by server configuration.")

async def get_or_create_system_settings(db: AsyncSession) -> SystemSettings:
    ss = await repo.get_system_settings_by_id(db, 1)
    if ss is None:
        ss = await repo.create_system_settings(db, 1)
    return ss

async def update_system_settings(db: AsyncSession, fields: dict) -> SystemSettings:
    ss = await get_or_create_system_settings(db)
    if _TRADING_FIELDS.intersection(fields):
        validate_trading_configuration(
            fields.get("trading_mode", ss.trading_mode),
            fields.get("active_broker", ss.active_broker),
        )
    updated_fields = {**fields, "updated_at": datetime.now(UTC)}
    updated_ss = await repo.update_system_settings_fields(db, ss, **updated_fields)
    return updated_ss
