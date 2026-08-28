"""Pre-trade risk gates. Unlevered, long-only, allowlisted, exposure <= 100%."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from trading_moe_lab.broker import Order
from trading_moe_lab.money import D, ONE, conservative_buy_price, q_money, q_weight
from trading_moe_lab.spec import ExperimentSpec
from trading_moe_lab.universe import Universe


def gate_orders(
    orders: list[Order],
    *,
    spec: ExperimentSpec,
    universe: Universe,
    session: date,
    positions: dict[str, int],
    prices: dict[str, object],
    nav,
    settled_cash,
    adverse_bps: int = 0,
    cost_bps: int = 0,
) -> tuple[list[Order], list[str]]:
    """Return (accepted, reject_reasons). Never emits shorts or leverage."""
    accepted: list[Order] = []
    reasons: list[str] = []
    max_name = D(spec.risk.max_name_weight)
    max_gross = D(spec.risk.max_gross_exposure)
    # Simulate fills sequentially: sells first (already sorted by caller).
    sim_pos = dict(positions)
    sim_cash = D(settled_cash)
    sim_nav = D(nav)

    allow = spec.universe
    for order in orders:
        if order.side == "SELL" and order.qty > sim_pos.get(order.symbol, 0):
            reasons.append(f"{order.order_id}: short/oversell blocked")
            continue
        if order.symbol not in allow:
            reasons.append(f"{order.order_id}: {order.symbol} not in spec universe")
            continue
        if not universe.is_tradable(order.symbol, session):
            reasons.append(f"{order.order_id}: {order.symbol} not PIT-tradable on {session}")
            continue
        px = D(prices[order.symbol])
        if order.side == "BUY":
            unit = conservative_buy_price(px, adverse_bps, cost_bps)
            cost = q_money(D(order.qty) * unit)
            if cost > sim_cash:
                reasons.append(f"{order.order_id}: insufficient settled cash")
                continue
            next_shares = sim_pos.get(order.symbol, 0) + order.qty
            name_value = q_money(D(next_shares) * px)
            if sim_nav > 0 and (name_value / sim_nav) > max_name + D("0.0000001"):
                reasons.append(f"{order.order_id}: name weight cap")
                continue
            gross = _gross(sim_pos, order.symbol, next_shares, prices)
            if sim_nav > 0 and (gross / sim_nav) > max_gross + D("0.0000001"):
                reasons.append(f"{order.order_id}: gross exposure cap")
                continue
            sim_cash = q_money(sim_cash - cost)
            sim_pos[order.symbol] = next_shares
        else:
            proceeds = q_money(D(order.qty) * px)
            sim_pos[order.symbol] = sim_pos.get(order.symbol, 0) - order.qty
            # T+1: cash not increased today.
            _ = proceeds
        accepted.append(order)
    return accepted, reasons


def _gross(positions: dict[str, int], symbol: str, shares: int, prices: dict[str, object]):
    total = D(0)
    seen = set(positions)
    seen.add(symbol)
    for s in seen:
        sh = shares if s == symbol else positions.get(s, 0)
        if sh == 0:
            continue
        total += D(sh) * D(prices[s])
    return q_money(total)


def scale_weights(weights: dict[str, Decimal], cap: Decimal = ONE) -> dict[str, Decimal]:
    total = sum(weights.values(), D(0))
    if total <= cap:
        return {k: q_weight(v) for k, v in weights.items() if v > 0}
    if total <= 0:
        return {}
    scale = cap / total
    return {k: q_weight(v * scale) for k, v in weights.items() if v > 0}
