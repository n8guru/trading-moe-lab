"""Deterministic daily LOCAL_SIM engine.

Loop: data validate → settle T+1 → risk/kill → signals (prev close) →
next-open execution → costs → EOD mark → audit.

LLMs never enter this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from trading_moe_lab.bars import Bar, BarSet
from trading_moe_lab.broker import Fill, LocalSimBroker, Order
from trading_moe_lab.errors import DataFault
from trading_moe_lab.hashes import canonical_json, sha256_text
from trading_moe_lab.kill import KillSwitch
from trading_moe_lab.money import D, ZERO, conservative_buy_price, notional, q_money, q_price, shares_from_notional
from trading_moe_lab.risk import gate_orders
from trading_moe_lab.settlement import CashBook
from trading_moe_lab.spec import ExperimentSpec
from trading_moe_lab.store import Store
from trading_moe_lab.strategies import LastTargetCache, target_weights
from trading_moe_lab.universe import Universe

INITIAL_CASH_DEFAULT = D("1000000.00")


@dataclass
class EngineResult:
    run_id: str
    spec_hash: str
    nav: list[tuple[str, str]]
    fills: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    kill: dict[str, Any]
    audit_tip: str
    cost_multiple: str
    initial_cash: str
    final_nav: str
    n_sessions: int
    rejected_orders: list[str]
    float_policy_id: str


@dataclass
class Portfolio:
    positions: dict[str, int] = field(default_factory=dict)
    cash: CashBook = field(default_factory=CashBook)

    def shares(self, symbol: str) -> int:
        return int(self.positions.get(symbol, 0))


def _calendar(bars: BarSet, start: date, end: date, universe_symbols: tuple[str, ...]) -> tuple[date, ...]:
    # Intersection of allowlisted series that exist for the whole window is too strict
    # (PIT probes). Use SPY as the session calendar when present, else union.
    if "SPY" in bars.by_symbol:
        dates = [b.session for b in bars.by_symbol["SPY"] if start <= b.session <= end]
        return tuple(dates)
    dates = [d for d in bars.calendar() if start <= d <= end]
    return tuple(dates)


def _validate_session(bars: BarSet, symbols: list[str], session: date) -> dict[str, Bar]:
    out: dict[str, Bar] = {}
    for s in symbols:
        bar = bars.bar_on(s, session)
        if bar is None:
            continue
        out[s] = bar
    if "SPY" in symbols and "SPY" not in out:
        raise DataFault(f"SPY bar missing on {session}")
    return out


def _next_session(calendar: tuple[date, ...], session: date) -> date:
    idx = calendar.index(session)
    if idx + 1 < len(calendar):
        return calendar[idx + 1]
    # Last day: settle "next" as same-day+0 conceptually — credit available immediately after last session.
    return session


def _mark(positions: dict[str, int], closes: dict[str, object], cash: CashBook) -> Decimal:
    equity = ZERO
    for s, q in positions.items():
        if q == 0:
            continue
        if s not in closes:
            raise DataFault(f"cannot mark {s}: no close")
        equity += notional(q, closes[s])
    return q_money(equity + cash.total())


def _gross_exposure(positions: dict[str, int], closes: dict[str, object], nav: Decimal) -> Decimal:
    if nav <= 0:
        return ZERO
    g = ZERO
    for s, q in positions.items():
        if q:
            g += notional(q, closes[s])
    return q_money(g / nav)


def _order_id(run_id: str, session: date, symbol: str, side: str, qty: int) -> str:
    return sha256_text(f"{run_id}:{session.isoformat()}:{symbol}:{side}:{qty}")[:20]


def _desired_shares(
    weights: dict[str, Decimal],
    nav: Decimal,
    opens: dict[str, object],
    *,
    adverse_bps: int,
    cost_bps: int,
    settled_cash,
) -> dict[str, int]:
    desired: dict[str, int] = {}
    for s, w in weights.items():
        if w <= 0 or s not in opens:
            continue
        budget = q_money(nav * w)
        # Target shares at the official open so 1x vs 2x fee overlays keep the same
        # intended book; cash caps below still use adverse+fee as an upper bound.
        desired[s] = shares_from_notional(budget, opens[s])
    # Cap aggregate buy notional to settled cash (T+1: cannot use sale proceeds today).
    # Scaling is applied later when planning buys against cash; keep desired as targets.
    _ = settled_cash
    return desired


def _plan_orders(
    run_id: str,
    session_id: str,
    session: date,
    positions: dict[str, int],
    desired: dict[str, int],
    opens: dict[str, object],
    settled_cash,
    adverse_bps: int,
    cost_bps: int,
) -> list[Order]:
    symbols = sorted(set(positions) | set(desired))
    sells: list[Order] = []
    buys: list[Order] = []
    for s in symbols:
        have = positions.get(s, 0)
        want = desired.get(s, 0)
        if want < have:
            qty = have - want
            sells.append(
                Order(
                    order_id=_order_id(run_id, session, s, "SELL", qty),
                    session_id=session_id,
                    symbol=s,
                    side="SELL",
                    qty=qty,
                )
            )
        elif want > have:
            qty = want - have
            buys.append(
                Order(
                    order_id=_order_id(run_id, session, s, "BUY", qty),
                    session_id=session_id,
                    symbol=s,
                    side="BUY",
                    qty=qty,
                )
            )
    cash = D(settled_cash)
    capped: list[Order] = []
    for o in buys:
        px = conservative_buy_price(opens[o.symbol], adverse_bps, cost_bps)
        max_qty = shares_from_notional(cash, px)
        qty = min(o.qty, max_qty)
        if qty <= 0:
            continue
        if qty != o.qty:
            o = Order(
                order_id=_order_id(run_id, session, o.symbol, "BUY", qty),
                session_id=session_id,
                symbol=o.symbol,
                side="BUY",
                qty=qty,
            )
        cash = q_money(cash - D(qty) * px)
        capped.append(o)
    return sells + capped


def run_engine(
    spec: ExperimentSpec,
    bars: BarSet,
    universe: Universe,
    store: Store,
    *,
    run_id: str,
    cost_multiple: str = "1x",
    initial_cash: Decimal | None = None,
    window: tuple[date, date] | None = None,
) -> EngineResult:
    cash0 = q_money(initial_cash if initial_cash is not None else INITIAL_CASH_DEFAULT)
    start = window[0] if window else spec.eval_window.start_date()
    end = window[1] if window else spec.eval_window.end_date()
    calendar = _calendar(bars, start, end, spec.universe)
    if not calendar:
        raise DataFault("empty calendar")

    broker = LocalSimBroker(
        seed=spec.seed,
        cost_bps=spec.cost_bps(cost_multiple),
        adverse_bps=spec.cost.adverse_bps,
        partial_fill_per_mille=spec.cost.partial_fill_per_mille,
    )
    kill = KillSwitch(store, run_id, spec.risk.kill_drawdown)
    book = Portfolio(cash=CashBook(settled=cash0))
    cache = LastTargetCache()
    fills_log: list[dict[str, Any]] = []
    orders_log: list[dict[str, Any]] = []
    rejected: list[str] = []

    store.audit(
        "ENGINE_START",
        {
            "run_id": run_id,
            "spec_hash": spec.spec_hash(),
            "cost_multiple": cost_multiple,
            "initial_cash": str(cash0),
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        run_id,
    )

    for session in calendar:
        session_id = f"{run_id}:{session.isoformat()}"
        need_symbols = sorted(set(spec.universe) | set(book.positions) | {spec.benchmark, spec.cash_vehicle, "SPY"})
        try:
            today = _validate_session(bars, need_symbols, session)
        except DataFault as exc:
            kill.latch(session, f"DATA_FAULT {exc}")
            store.audit("DATA_FAULT", {"session": session.isoformat(), "err": str(exc)}, run_id)
            break

        payload = {
            "session_id": session_id,
            "positions": {k: v for k, v in sorted(book.positions.items()) if v},
            "cash": book.cash.snapshot(),
            "spec_hash": spec.spec_hash(),
            "cost_multiple": cost_multiple,
        }
        payload_hash = sha256_text(canonical_json(payload))
        existing = store.get_session(session_id)
        if existing:
            # Idempotent replay: do not mutate. Restore from stored result if this is a fresh process
            # that somehow has empty book — bake-off / tests that share a store+run_id must not double fill.
            cached = existing["result_json"]
            store.put_session(session_id, run_id, session.isoformat(), payload_hash, {"cached": True})
            # If payload matches, skip trading; still we need book to stay consistent. Tests that
            # check idempotency re-run the whole engine on the same store/run_id and should see
            # the same NAV series. For a full re-run we require a new run_id OR we reconstruct.
            # Reconstructing is safer: apply cached fills is hard. Instead, if the entire run is
            # replayed with the same run_id, we treat sessions as already processed and LOAD nav
            # at end. For true intra-run crash recovery, result_json holds the post-session book.
            import json

            result = json.loads(existing["result_json"])
            book.positions = {k: int(v) for k, v in result["positions"].items()}
            book.cash.settled = D(result["cash"]["settled"])
            from trading_moe_lab.settlement import PendingCredit

            book.cash.pending = [
                PendingCredit(date.fromisoformat(p["available_on"]), D(p["amount"]))
                for p in result["cash"]["pending"]
            ]
            store.put_nav(run_id, session.isoformat(), result["nav"], result["cash"]["total"], result["gross"])
            continue

        book.cash.settle(session)
        next_sess = _next_session(calendar, session)
        opens = {s: q_price(b.open) for s, b in today.items()}
        closes = {s: q_price(b.close) for s, b in today.items()}

        # Pre-trade NAV at open (positions marked at open + cash) for sizing.
        nav_open = _mark(book.positions, opens, book.cash)

        session_orders: list[Order] = []
        session_fills: list[Fill] = []
        if kill.can_place_orders():
            weights = target_weights(spec, bars, universe, session, calendar, cache)
            desired = _desired_shares(
                weights,
                nav_open,
                opens,
                adverse_bps=spec.cost.adverse_bps,
                cost_bps=spec.cost.bps_2x,  # identical cash cap for 1x/2x overlays
                settled_cash=book.cash.settled,
            )
            planned = _plan_orders(
                run_id,
                session_id,
                session,
                book.positions,
                desired,
                opens,
                book.cash.settled,
                spec.cost.adverse_bps,
                spec.cost.bps_2x,
            )
            gated, reasons = gate_orders(
                planned,
                spec=spec,
                universe=universe,
                session=session,
                positions=book.positions,
                prices=opens,
                nav=nav_open,
                settled_cash=book.cash.settled,
                adverse_bps=spec.cost.adverse_bps,
                cost_bps=spec.cost.bps_2x,
            )
            rejected.extend(reasons)
            session_orders = gated
            if gated:
                session_fills = broker.execute(session_id, session, gated, today)
                for fill in session_fills:
                    _apply_fill(book, fill, next_sess)
        else:
            # Frozen: retain positions, no orders.
            pass

        nav_close = _mark(book.positions, closes, book.cash)
        gross = _gross_exposure(book.positions, closes, nav_close)
        kill.observe_nav(session, nav_close)

        result = {
            "positions": {k: v for k, v in sorted(book.positions.items()) if v},
            "cash": book.cash.snapshot(),
            "nav": str(nav_close),
            "gross": str(gross),
            "n_orders": len(session_orders),
            "n_fills": len(session_fills),
        }
        store.put_session(session_id, run_id, session.isoformat(), payload_hash, result)
        store.put_nav(run_id, session.isoformat(), str(nav_close), str(book.cash.total()), str(gross))
        for o in session_orders:
            orders_log.append(
                {
                    "session": session.isoformat(),
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": o.qty,
                }
            )
        for f in session_fills:
            fills_log.append(
                {
                    "session": session.isoformat(),
                    "fill_id": f.fill_id,
                    "order_id": f.order_id,
                    "symbol": f.symbol,
                    "side": f.side,
                    "qty": f.qty,
                    "price": str(f.price),
                    "fee": str(f.fee),
                    "remaining_cancelled": f.remaining_cancelled,
                }
            )

    nav_series = store.nav_series(run_id)
    final = nav_series[-1][1] if nav_series else str(cash0)
    store.audit("ENGINE_END", {"run_id": run_id, "final_nav": final, "n": len(nav_series)}, run_id)
    return EngineResult(
        run_id=run_id,
        spec_hash=spec.spec_hash(),
        nav=nav_series,
        fills=fills_log,
        orders=orders_log,
        kill=kill.state.as_dict(),
        audit_tip=store.audit_tip(),
        cost_multiple=cost_multiple,
        initial_cash=str(cash0),
        final_nav=final,
        n_sessions=len(nav_series),
        rejected_orders=rejected,
        float_policy_id="decimal-v0-8dp-half-even",
    )


def _apply_fill(book: Portfolio, fill: Fill, next_session: date) -> None:
    if fill.qty <= 0:
        return
    pos = book.positions.get(fill.symbol, 0)
    if fill.side == "BUY":
        cost = q_money(notional(fill.qty, fill.price) + fill.fee)
        book.cash.spend(cost)
        book.positions[fill.symbol] = pos + fill.qty
    else:
        if fill.qty > pos:
            raise DataFault(f"oversell {fill.symbol}")
        proceeds = q_money(notional(fill.qty, fill.price) - fill.fee)
        book.cash.credit_t1(proceeds, next_session)
        book.positions[fill.symbol] = pos - fill.qty
        if book.positions[fill.symbol] == 0:
            del book.positions[fill.symbol]
