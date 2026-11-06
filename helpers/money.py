from decimal import Decimal, ROUND_HALF_UP
from typing import Union

def to_cents(amount: Union[float, int, str, Decimal, None]) -> int:
    """
    Convert a dollar/currency amount (float, str, int, Decimal) to integer cents.
    Example: 12.99 -> 1299, 10 -> 1000.
    """
    if amount is None:
        return 0
    dec = Decimal(str(amount))
    return int((dec * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def from_cents(cents: Union[int, None]) -> float:
    """
    Convert integer cents back to decimal float currency.
    Example: 1299 -> 12.99.
    """
    if cents is None:
        return 0.0
    return float(round(cents / 100.0, 2))

def format_money(cents: Union[int, None], currency: str = "$") -> str:
    """
    Format integer cents as a currency string.
    Example: 1299 -> '$12.99'.
    """
    if cents is None:
        cents = 0
    return f"{currency}{cents / 100:.2f}"
