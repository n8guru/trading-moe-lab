"""Locked decimal / share policy.

Engine state, orders, fills, cash, and NAV use :class:`decimal.Decimal` only.
Reporting may convert to float at the edge; those conversions are labeled
``display_float64`` and are not fed back into the engine.

Quantization
------------
- Money / NAV / fees: 8 decimal places, ``ROUND_HALF_EVEN``.
- Prices: 4 decimal places, ``ROUND_HALF_EVEN`` (US ETF cents+).
- Shares: non-negative integers (no fractional shares in v0).
- Weights: 10 decimal places, ``ROUND_HALF_EVEN``.

This policy is part of the bake-off contract. Changing it is a breaking
change and must bump ``FLOAT_POLICY_ID``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, ROUND_UP, Decimal, localcontext
from typing import Union

Number = Union[int, str, Decimal]

FLOAT_POLICY_ID = "decimal-v0-8dp-half-even"
MONEY_QUANTUM = Decimal("0.00000001")
PRICE_QUANTUM = Decimal("0.0001")
WEIGHT_QUANTUM = Decimal("0.0000000001")
BPS_UNIT = Decimal("0.0001")  # 1 bp
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


def D(x: Number) -> Decimal:
    """Convert int/str/Decimal to Decimal. Floats are rejected."""
    if isinstance(x, float):
        raise TypeError("float is forbidden in the engine; pass str, int, or Decimal")
    if isinstance(x, Decimal):
        return x
    return Decimal(x)


def q_money(x: Number) -> Decimal:
    return D(x).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def q_price(x: Number) -> Decimal:
    return D(x).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)


def q_weight(x: Number) -> Decimal:
    return D(x).quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_EVEN)


def shares_from_notional(notional: Number, price: Number) -> int:
    """Whole shares that fit in notional at price (floor)."""
    p = q_price(price)
    if p <= 0:
        return 0
    n = D(notional) / p
    return int(n.to_integral_value(rounding="ROUND_DOWN"))


def notional(shares: int, price: Number) -> Decimal:
    if shares < 0:
        raise ValueError("shares must be >= 0 (long-only)")
    return q_money(D(shares) * q_price(price))


def bps_to_fraction(bps: int) -> Decimal:
    return D(bps) * BPS_UNIT


def conservative_buy_price(open_price: Number, adverse_bps: int, cost_bps: int) -> Decimal:
    """Upper bound on cash needed per share: adverse fill + one-way fee, rounded up."""
    px = apply_adverse_price(open_price, "BUY", adverse_bps)
    raw = px * (ONE + bps_to_fraction(cost_bps))
    return raw.quantize(PRICE_QUANTUM, rounding=ROUND_UP)


def apply_adverse_price(open_price: Number, side: str, adverse_bps: int) -> Decimal:
    """Buy pays more than open; sell receives less than open."""
    px = q_price(open_price)
    adj = bps_to_fraction(adverse_bps)
    if side == "BUY":
        return q_price(px * (ONE + adj))
    if side == "SELL":
        return q_price(px * (ONE - adj))
    raise ValueError(f"unknown side {side}")


def fee_on_fill(qty: int, price: Number, cost_bps: int) -> Decimal:
    return q_money(D(qty) * q_price(price) * bps_to_fraction(cost_bps))


def decimal_power(base: Decimal, exp: Decimal) -> Decimal:
    """``base ** exp`` under a wide local context (metrics only)."""
    if base <= 0:
        raise ValueError("base must be positive")
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN
        return base ** exp
