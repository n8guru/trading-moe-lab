"""Performance metrics. Engine remains Decimal; display_float64 is reporting-only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from trading_moe_lab.bars import BarSet, daily_returns
from trading_moe_lab.money import D, ONE, ZERO, decimal_power, q_money

TRADING_DAYS = D(252)
RF_DECLARATION = (
    "Sharpe uses excess daily total return versus the BIL cash-vehicle TR series "
    "on the same fixture calendar. When BIL is missing, RF = 0 (declared)."
)


def _nav_decimals(nav: list[tuple[str, str]]) -> list[tuple[date, Decimal]]:
    return [(date.fromisoformat(d), D(v)) for d, v in nav]


def max_drawdown(nav: list[tuple[str, str]]) -> Decimal:
    peak = None
    max_dd = ZERO
    for _, v in _nav_decimals(nav):
        if peak is None or v > peak:
            peak = v
        if peak > 0:
            dd = ONE - (v / peak)
            if dd > max_dd:
                max_dd = dd
    return max_dd


def cagr(nav: list[tuple[str, str]]) -> Decimal | None:
    series = _nav_decimals(nav)
    if len(series) < 2:
        return None
    start, end = series[0][1], series[-1][1]
    if start <= 0 or end <= 0:
        return None
    days = D((series[-1][0] - series[0][0]).days)
    if days <= 0:
        return None
    years = days / D("365.25")
    return decimal_power(end / start, ONE / years) - ONE


def daily_nav_returns(nav: list[tuple[str, str]]) -> list[Decimal]:
    series = _nav_decimals(nav)
    out = []
    for i in range(1, len(series)):
        a, b = series[i - 1][1], series[i][1]
        if a <= 0:
            continue
        out.append((b / a) - ONE)
    return out


def hit_rate(nav: list[tuple[str, str]]) -> Decimal | None:
    rets = daily_nav_returns(nav)
    if not rets:
        return None
    wins = sum(1 for r in rets if r > 0)
    return D(wins) / D(len(rets))


def sharpe(nav: list[tuple[str, str]], rf_daily: list[Decimal] | None) -> Decimal | None:
    rets = daily_nav_returns(nav)
    if len(rets) < 3:
        return None
    if rf_daily is None or len(rf_daily) != len(rets):
        excess = rets
    else:
        excess = [r - f for r, f in zip(rets, rf_daily)]
    mean = sum(excess, ZERO) / D(len(excess))
    var = sum((x - mean) * (x - mean) for x in excess) / D(len(excess) - 1)
    if var <= 0:
        return None
    std = decimal_power(var, D("0.5"))
    return (mean / std) * decimal_power(TRADING_DAYS, D("0.5"))


def bil_rf(bars: BarSet, nav: list[tuple[str, str]]) -> list[Decimal] | None:
    if "BIL" not in bars.by_symbol or len(nav) < 2:
        return None
    idx = bars.index("BIL")
    dates = [date.fromisoformat(d) for d, _ in nav]
    rets = []
    for i in range(1, len(dates)):
        a = idx.get(dates[i - 1])
        b = idx.get(dates[i])
        if a is None or b is None or D(a.close) <= 0:
            return None
        rets.append((D(b.close) / D(a.close)) - ONE)
    return rets


def turnover_annualized(fills: list[dict[str, Any]], nav: list[tuple[str, str]]) -> Decimal | None:
    if not nav:
        return None
    traded = ZERO
    for f in fills:
        traded += D(f["qty"]) * D(f["price"])
    avg_nav = sum((D(v) for _, v in nav), ZERO) / D(len(nav))
    if avg_nav <= 0:
        return None
    n = D(len(nav))
    # sum(traded)/avg_nav over the sample, annualized by 252/n
    return (traded / avg_nav) * (TRADING_DAYS / n)


def total_return(nav: list[tuple[str, str]]) -> Decimal | None:
    if len(nav) < 2:
        return None
    a, b = D(nav[0][1]), D(nav[-1][1])
    if a <= 0:
        return None
    return (b / a) - ONE


def metrics_bundle(
    nav: list[tuple[str, str]],
    fills: list[dict[str, Any]],
    bars: BarSet,
) -> dict[str, Any]:
    rf = bil_rf(bars, nav)
    c = cagr(nav)
    dd = max_drawdown(nav)
    sh = sharpe(nav, rf)
    hr = hit_rate(nav)
    to = turnover_annualized(fills, nav)
    tr = total_return(nav)

    def fmt(x: Decimal | None) -> str | None:
        return None if x is None else str(q_money(x))

    return {
        "cagr": fmt(c),
        "max_drawdown": fmt(dd),
        "sharpe": None if sh is None else str(sh.quantize(D("0.00000001"))),
        "hit_rate": fmt(hr),
        "turnover_annualized": fmt(to),
        "total_return": fmt(tr),
        "n_sessions": len(nav),
        "n_fills": len(fills),
        "rf_declaration": RF_DECLARATION,
        "rf_used": "BIL" if rf is not None else "ZERO",
        "display_float64": {
            "cagr": None if c is None else float(c),
            "max_drawdown": float(dd),
            "sharpe": None if sh is None else float(sh),
            "hit_rate": None if hr is None else float(hr),
            "turnover_annualized": None if to is None else float(to),
            "total_return": None if tr is None else float(tr),
        },
    }
