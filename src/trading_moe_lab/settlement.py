"""T+1 cash settlement for a long-only unlevered cash account.

Sell proceeds become settled on the next session date in the engine calendar.
Buys spend settled cash only. Sells are processed before buys each session,
but proceeds still settle T+1 (no same-day reuse).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trading_moe_lab.money import ZERO, q_money


@dataclass
class PendingCredit:
    available_on: date
    amount: object  # Decimal


@dataclass
class CashBook:
    def __init__(self, settled: object = ZERO, pending: list[PendingCredit] | None = None):
        self.settled = q_money(settled)
        self.pending = list(pending or [])

    def total(self) -> object:
        s = q_money(self.settled)
        for p in self.pending:
            s = q_money(s + p.amount)
        return s

    def settle(self, session: date) -> object:
        still: list[PendingCredit] = []
        released = ZERO
        for p in self.pending:
            if p.available_on <= session:
                self.settled = q_money(self.settled + p.amount)
                released = q_money(released + p.amount)
            else:
                still.append(p)
        self.pending = still
        return released

    def spend(self, amount) -> None:
        amt = q_money(amount)
        if amt > self.settled:
            raise ValueError(f"insufficient settled cash: need {amt} have {self.settled}")
        self.settled = q_money(self.settled - amt)

    def try_spend(self, amount) -> bool:
        amt = q_money(amount)
        if amt > self.settled:
            return False
        self.settled = q_money(self.settled - amt)
        return True

    def credit_t1(self, amount, next_session: date) -> None:
        amt = q_money(amount)
        if amt <= 0:
            return
        self.pending.append(PendingCredit(available_on=next_session, amount=amt))

    def snapshot(self) -> dict:
        return {
            "settled": str(q_money(self.settled)),
            "pending": [{"available_on": p.available_on.isoformat(), "amount": str(q_money(p.amount))} for p in self.pending],
            "total": str(self.total()),
        }
