"""LOCAL_SIM broker: deterministic adverse + optional partial fills.

Idempotent at the session layer (Store.put_session). This object never talks
to a network. There is no live subclass in this repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from trading_moe_lab.bars import Bar
from trading_moe_lab.errors import DataFault
from trading_moe_lab.hashes import det_u64, sha256_text
from trading_moe_lab.money import apply_adverse_price, fee_on_fill, q_money, q_price


@dataclass(frozen=True)
class Order:
    order_id: str
    session_id: str
    symbol: str
    side: str  # BUY or SELL
    qty: int
    tif: str = "DAY"

    def __post_init__(self) -> None:
        if self.side not in ("BUY", "SELL"):
            raise ValueError(self.side)
        if self.qty <= 0:
            raise ValueError("qty must be positive")


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: str
    qty: int
    price: object
    fee: object
    remaining_cancelled: int


@dataclass
class LocalSimBroker:
    seed: int
    cost_bps: int
    adverse_bps: int
    partial_fill_per_mille: int = 0
    name: str = "LOCAL_SIM"

    def execute(self, session_id: str, session: date, orders: list[Order], opens: dict[str, Bar]) -> list[Fill]:
        fills: list[Fill] = []
        for order in orders:
            bar = opens.get(order.symbol)
            if bar is None:
                raise DataFault(f"no bar for {order.symbol} on {session}")
            fill_qty = self._partial_qty(order, session)
            px = apply_adverse_price(bar.open, order.side, self.adverse_bps)
            fee = fee_on_fill(fill_qty, px, self.cost_bps)
            fill_id = sha256_text(f"{order.order_id}:{session.isoformat()}:{fill_qty}:{px}:{fee}")[:24]
            fills.append(
                Fill(
                    fill_id=fill_id,
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    qty=fill_qty,
                    price=q_price(px),
                    fee=q_money(fee),
                    remaining_cancelled=order.qty - fill_qty,
                )
            )
        return fills

    def _partial_qty(self, order: Order, session: date) -> int:
        if self.partial_fill_per_mille <= 0:
            return order.qty
        key = f"{self.seed}:{order.symbol}:{order.side}:{order.qty}:{session.isoformat()}:partial"
        draw = det_u64(key) % 1000
        if draw >= self.partial_fill_per_mille:
            return order.qty
        # Fill 50–90% deterministically when the partial branch hits.
        frac_bps = 5000 + (det_u64(key + ":frac") % 4001)  # 50.00% .. 90.00%
        qty = max(1, (order.qty * frac_bps) // 10000)
        return min(order.qty, qty)
