from __future__ import annotations

from decimal import Decimal, InvalidOperation

MoneyValue = Decimal | float | str | int | None

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
