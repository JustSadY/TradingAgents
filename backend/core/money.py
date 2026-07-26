from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MoneyValue = Decimal | float | str | int | None

MONEY_PRECISION = Decimal("0.0001")
STD_PRECISION = Decimal("0.01")


def safe_decimal(value: MoneyValue = None, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return default


def format_money(d: Decimal, places: Decimal = MONEY_PRECISION) -> Decimal:
    return d.quantize(places, rounding=ROUND_HALF_UP)


def to_float_safe(value: MoneyValue = None, default: float = 0.0) -> float:
    return float(safe_decimal(value, default=Decimal(str(default))))
