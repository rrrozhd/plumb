"""Money types (AGENTS.md rule 2): RLUSD is Decimal parsed from strings, XRP is int drops. Floats never touch money."""
from decimal import Decimal, InvalidOperation

DROPS_PER_XRP = 1_000_000


def rlusd(value: str) -> Decimal:
    """Parse a non-negative RLUSD amount from its exact string form."""
    if not isinstance(value, str):
        raise TypeError(f"RLUSD amounts must be strings, got {type(value).__name__}")
    try:
        amount = Decimal(value.strip())
    except InvalidOperation:
        raise ValueError(f"not a decimal amount: {value!r}") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"RLUSD amount must be finite and non-negative: {value!r}")
    return amount


def xrp_drops(value: str | int) -> int:
    """Parse a non-negative XRP amount in drops (an integer, or a string of digits)."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError(f"XRP drops must be int or str, got {type(value).__name__}")
    if isinstance(value, str):
        if not value.strip().isdigit():
            raise ValueError(f"XRP drops must be a whole number: {value!r}")
        value = int(value)
    if value < 0:
        raise ValueError(f"XRP drops must be non-negative: {value}")
    return value


def drops_to_rlusd(drops: int, xrp_in_rlusd: Decimal) -> Decimal:
    """Convert drops at a recorded XRP/RLUSD mid price (eval/rubric.md §1.2)."""
    return Decimal(drops) / DROPS_PER_XRP * xrp_in_rlusd
