"""Latching kill switch. Experts cannot unlatch. Persisted per run_id."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trading_moe_lab.money import D, ONE, q_money
from trading_moe_lab.store import Store


@dataclass
class KillState:
    latched: bool = False
    reason: str | None = None
    latched_on: str | None = None
    peak_nav: object = D(0)
    nav: object = D(0)

    def as_dict(self) -> dict:
        return {
            "latched": self.latched,
            "reason": self.reason,
            "latched_on": self.latched_on,
            "peak_nav": str(q_money(self.peak_nav)),
            "nav": str(q_money(self.nav)),
        }


class KillSwitch:
    def __init__(self, store: Store, run_id: str, drawdown_limit):
        self.store = store
        self.run_id = run_id
        self.drawdown_limit = D(drawdown_limit)
        self.state = KillState()
        self._load()

    def _load(self) -> None:
        row = self.store.get_kill(self.run_id)
        if not row:
            return
        self.state = KillState(
            latched=bool(row["latched"]),
            reason=row["reason"],
            latched_on=row["latched_on"],
            peak_nav=D(row["peak_nav"]),
            nav=D(row["nav"]),
        )

    def persist(self) -> None:
        self.store.set_kill(
            self.run_id,
            self.state.latched,
            self.state.reason,
            self.state.latched_on,
            str(q_money(self.state.peak_nav)),
            str(q_money(self.state.nav)),
        )

    def observe_nav(self, session: date, nav) -> None:
        nav = q_money(nav)
        self.state.nav = nav
        if nav > self.state.peak_nav:
            self.state.peak_nav = nav
        if self.state.latched:
            self.persist()
            return
        peak = self.state.peak_nav
        if peak > 0:
            dd = ONE - (nav / peak)
            if dd >= self.drawdown_limit:
                self.latch(session, f"DRAWDOWN {dd} >= {self.drawdown_limit}")
                return
        self.persist()

    def latch(self, session: date, reason: str) -> None:
        if self.state.latched:
            return
        self.state.latched = True
        self.state.reason = reason
        self.state.latched_on = session.isoformat()
        self.persist()

    def can_place_orders(self) -> bool:
        return not self.state.latched
