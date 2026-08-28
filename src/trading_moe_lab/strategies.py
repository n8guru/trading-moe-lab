"""Portfolio construction. Signals use strictly prior closes (asof exclusive)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from trading_moe_lab.bars import BarSet, daily_returns, lookback_return
from trading_moe_lab.money import D, ONE, ZERO, q_weight
from trading_moe_lab.spec import ExperimentSpec
from trading_moe_lab.universe import Universe


def _closes(bars: BarSet, symbol: str, asof: date):
    return bars.close_series(symbol, before=asof)


def _ret(bars: BarSet, symbol: str, asof: date, lookback: int) -> Decimal | None:
    r = lookback_return(_closes(bars, symbol, asof), lookback)
    return D(r) if r is not None else None


def _month_end_before(asof: date, calendar: tuple[date, ...]) -> date | None:
    prior = [d for d in calendar if d < asof]
    if not prior:
        return None
    # Last session of the previous month relative to asof.
    target_month = (asof.year, asof.month)
    prev_month_days = [d for d in prior if (d.year, d.month) != target_month]
    if not prev_month_days:
        return None
    return prev_month_days[-1]


def _is_rebalance_day(asof: date, spec: ExperimentSpec, calendar: tuple[date, ...]) -> bool:
    if spec.rebalance == "DAILY":
        return True
    if spec.rebalance == "MONTHLY":
        # First session of a month (previous calendar session is a different month),
        # or first session in the window.
        idx = calendar.index(asof)
        if idx == 0:
            return True
        prev = calendar[idx - 1]
        return (prev.year, prev.month) != (asof.year, asof.month)
    if spec.rebalance == "EVERY_N_DAYS":
        idx = calendar.index(asof)
        n = max(1, spec.rebalance_n_days)
        return idx % n == 0
    return False


def vol_scale(bars: BarSet, weights: dict[str, Decimal], asof: date, spec: ExperimentSpec) -> Decimal:
    """Scale-down only so that recent weighted vol <= target; never > vol_cap <= 1."""
    if spec.risk.vol_target_annual is None:
        return ONE
    target = D(spec.risk.vol_target_annual)
    cap = D(spec.risk.vol_cap)
    look = spec.risk.vol_lookback_days
    # Align last `look` overlapping daily returns.
    series = {s: daily_returns(_closes(bars, s, asof)) for s in weights}
    n = min((len(v) for v in series.values()), default=0)
    if n < look or look < 2:
        return ONE
    port = []
    for i in range(n - look, n):
        r = ZERO
        for s, w in weights.items():
            rs = series[s]
            r += w * rs[i]
        port.append(r)
    mean = sum(port, ZERO) / D(len(port))
    var = sum((x - mean) * (x - mean) for x in port) / D(len(port) - 1)
    if var <= 0:
        return min(ONE, cap)
    # std * sqrt(252)
    from trading_moe_lab.money import decimal_power

    std = decimal_power(var, D("0.5"))
    ann = std * decimal_power(D(252), D("0.5"))
    if ann <= 0:
        return min(ONE, cap)
    scale = target / ann
    if scale > cap:
        scale = cap
    if scale > ONE:
        scale = ONE
    if scale < 0:
        scale = ZERO
    return q_weight(scale)


def apply_vol_and_cash(
    weights: dict[str, Decimal],
    bars: BarSet,
    asof: date,
    spec: ExperimentSpec,
) -> dict[str, Decimal]:
    raw = {k: v for k, v in weights.items() if v > 0}
    if not raw:
        return {}
    total = sum(raw.values(), ZERO)
    if total > ONE:
        raw = {k: q_weight(v / total) for k, v in raw.items()}
    cash = spec.cash_vehicle
    risk_w = {k: v for k, v in raw.items() if k != cash}
    if not risk_w:
        return {k: q_weight(v) for k, v in raw.items()}
    scale = vol_scale(bars, risk_w, asof, spec)
    scaled = {k: q_weight(v * scale) for k, v in risk_w.items()}
    used = sum(scaled.values(), ZERO)
    leftover = ONE - used
    if leftover < 0:
        leftover = ZERO
    if cash in spec.universe:
        scaled[cash] = q_weight(scaled.get(cash, ZERO) + leftover)
    # drop zeros
    return {k: v for k, v in scaled.items() if v > 0}


class LastTargetCache:
    def __init__(self) -> None:
        self.weights: dict[str, Decimal] = {}


def target_weights(
    spec: ExperimentSpec,
    bars: BarSet,
    universe: Universe,
    asof: date,
    calendar: tuple[date, ...],
    cache: LastTargetCache,
) -> dict[str, Decimal]:
    if asof not in calendar:
        return dict(cache.weights)
    if not _is_rebalance_day(asof, spec, calendar) and cache.weights:
        return dict(cache.weights)
    raw = _compute(spec, bars, universe, asof)
    sized = apply_vol_and_cash(raw, bars, asof, spec)
    cache.weights = dict(sized)
    return sized


def _compute(spec: ExperimentSpec, bars: BarSet, universe: Universe, asof: date) -> dict[str, Decimal]:
    tradable = set(universe.tradable(asof, allowlisted_only=True))
    family = spec.family
    if family == "BENCHMARK_SPY":
        if spec.benchmark in tradable:
            return {spec.benchmark: ONE}
        return {}
    if family == "BENCHMARK_CASH":
        if spec.cash_vehicle in tradable:
            return {spec.cash_vehicle: ONE}
        return {}
    if family == "BENCHMARK_EQUAL_WEIGHT":
        names = [s for s in spec.universe if s in tradable and s != spec.cash_vehicle]
        if not names:
            return {}
        w = q_weight(ONE / D(len(names)))
        return {s: w for s in names}
    if family in ("H1_DUAL_MOMENTUM", "RESEARCH") and spec.params.get("style", "dual") in ("dual", None):
        if family == "H1_DUAL_MOMENTUM" or spec.params.get("style") == "dual":
            return _h1(spec, bars, tradable, asof)
    if family == "H2_CS_MOMENTUM" or spec.params.get("style") == "cs_momentum":
        return _h2(spec, bars, tradable, asof)
    if family == "H3_REVERSAL" or spec.params.get("style") == "reversal":
        return _h3(spec, bars, tradable, asof)
    if family == "RESEARCH":
        style = spec.params.get("style")
        if style == "dual":
            return _h1(spec, bars, tradable, asof)
        if style == "cs_momentum":
            return _h2(spec, bars, tradable, asof)
        if style == "reversal":
            return _h3(spec, bars, tradable, asof)
    return _h1(spec, bars, tradable, asof)


def _h1(spec: ExperimentSpec, bars: BarSet, tradable: set[str], asof: date) -> dict[str, Decimal]:
    """Antonacci-style dual (relative + absolute) momentum. Method citation only."""
    risk = list(spec.risk_assets) or [s for s in spec.universe if s not in {spec.cash_vehicle, spec.crash_asset}]
    risk = [s for s in risk if s in tradable]
    cash = spec.cash_vehicle
    crash = spec.crash_asset or cash
    if not risk:
        return {cash: ONE} if cash in tradable else {}
    rets: dict[str, Decimal] = {}
    for s in list(risk) + [cash, crash]:
        if s not in tradable:
            continue
        r = _ret(bars, s, asof, spec.lookback_days)
        if r is None:
            return {cash: ONE} if cash in tradable else {}
        rets[s] = r
    winner = max(risk, key=lambda s: rets[s])
    bill = rets.get(cash, ZERO)
    if rets[winner] > bill:
        return {winner: ONE}
    if crash in rets and crash != cash and rets[crash] > bill:
        return {crash: ONE}
    return {cash: ONE} if cash in tradable else {}


def _h2(spec: ExperimentSpec, bars: BarSet, tradable: set[str], asof: date) -> dict[str, Decimal]:
    names = [s for s in spec.universe if s in tradable and s != spec.cash_vehicle]
    rets = {}
    for s in names:
        r = _ret(bars, s, asof, spec.lookback_days)
        if r is None:
            return {spec.cash_vehicle: ONE} if spec.cash_vehicle in tradable else {}
        rets[s] = r
    ranked = sorted(names, key=lambda s: rets[s], reverse=True)
    picked = []
    bill = _ret(bars, spec.cash_vehicle, asof, spec.lookback_days) or ZERO
    for s in ranked[: spec.top_k]:
        if rets[s] > bill:
            picked.append(s)
    if not picked:
        return {spec.cash_vehicle: ONE} if spec.cash_vehicle in tradable else {}
    w = q_weight(ONE / D(len(picked)))
    return {s: w for s in picked}


def _h3(spec: ExperimentSpec, bars: BarSet, tradable: set[str], asof: date) -> dict[str, Decimal]:
    names = [s for s in spec.universe if s in tradable and s != spec.cash_vehicle]
    rets = {}
    for s in names:
        r = _ret(bars, s, asof, spec.lookback_days)
        if r is None:
            return {}
        rets[s] = r
    ranked = sorted(names, key=lambda s: rets[s])  # most negative first
    picked = ranked[: spec.top_k]
    if not picked:
        return {}
    w = q_weight(ONE / D(len(picked)))
    return {s: w for s in picked}
