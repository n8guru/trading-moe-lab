"""OHLCV bar loading, validation, and point-in-time slicing.

Fixture closes are **total-return index levels** (dividends economically
reinvested). Price-only return is not used in v0.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trading_moe_lab.errors import DataFault
from trading_moe_lab.hashes import sha256_file
from trading_moe_lab.money import D, q_price


@dataclass(frozen=True)
class Bar:
    session: date
    open: object  # Decimal
    high: object
    low: object
    close: object
    volume: int

    def as_tuple(self) -> tuple:
        return (self.session.isoformat(), str(self.open), str(self.high), str(self.low), str(self.close), self.volume)


@dataclass(frozen=True)
class BarSet:
    """Immutable bars keyed by symbol, each series sorted by session date."""

    by_symbol: dict[str, tuple[Bar, ...]]
    digest_ok: bool

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.by_symbol))

    def calendar(self) -> tuple[date, ...]:
        dates: set[date] = set()
        for series in self.by_symbol.values():
            dates.update(b.session for b in series)
        return tuple(sorted(dates))

    def index(self, symbol: str) -> dict[date, Bar]:
        return {b.session: b for b in self.by_symbol[symbol]}

    def close_series(self, symbol: str, before: date | None = None) -> list[tuple[date, object]]:
        out = []
        for b in self.by_symbol.get(symbol, ()):
            if before is not None and b.session >= before:
                break
            out.append((b.session, b.close))
        return out

    def bar_on(self, symbol: str, session: date) -> Bar | None:
        for b in self.by_symbol.get(symbol, ()):
            if b.session == session:
                return b
            if b.session > session:
                return None
        return None


def parse_bar_row(row: dict[str, str]) -> Bar:
    session = date.fromisoformat(row["date"])
    o = q_price(row["open"])
    h = q_price(row["high"])
    low = q_price(row["low"])
    c = q_price(row["close"])
    vol = int(row["volume"])
    if min(o, h, low, c) <= 0:
        raise DataFault(f"{session} has non-positive OHLC")
    if h < max(o, c) or low > min(o, c) or h < low:
        raise DataFault(f"{session} OHLC inequality failed")
    if vol < 0:
        raise DataFault(f"{session} negative volume")
    return Bar(session, o, h, low, c, vol)


def load_csv_bars(path: Path) -> tuple[Bar, ...]:
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [parse_bar_row(r) for r in reader]
    dates = [b.session for b in rows]
    if dates != sorted(dates):
        raise DataFault(f"{path} is not sorted by date")
    if len(dates) != len(set(dates)):
        raise DataFault(f"{path} has duplicate dates")
    return tuple(rows)


def load_digest_map(path: Path) -> dict[str, str]:
    import json

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    files = raw.get("files") or {}
    return {str(k): str(v) for k, v in files.items()}


def load_barset(fixtures_dir: Path, verify_digests: bool = True) -> BarSet:
    bars_dir = fixtures_dir / "bars"
    digest_path = fixtures_dir / "digests.json"
    by_symbol: dict[str, tuple[Bar, ...]] = {}
    digest_ok = True
    expected = load_digest_map(digest_path) if digest_path.exists() else {}
    for csv_path in sorted(bars_dir.glob("*.csv")):
        rel = f"bars/{csv_path.name}"
        if verify_digests:
            got = sha256_file(csv_path)
            want = expected.get(rel)
            if want is None:
                raise DataFault(f"digest missing for {rel}")
            if got != want:
                raise DataFault(f"digest mismatch for {rel}: got {got} want {want}")
        symbol = csv_path.stem.upper()
        by_symbol[symbol] = load_csv_bars(csv_path)
    if verify_digests:
        extra = set(expected) - {f"bars/{s}.csv" for s in by_symbol}
        # universe.json etc. may also be in digest map
        extra_bars = {k for k in extra if k.startswith("bars/")}
        if extra_bars:
            raise DataFault(f"digest lists missing bar files: {sorted(extra_bars)}")
    if not by_symbol:
        raise DataFault(f"no bars under {bars_dir}")
    return BarSet(by_symbol=by_symbol, digest_ok=digest_ok)


def lookback_return(closes: list[tuple[date, object]], lookback: int) -> object | None:
    """Total return over `lookback` steps using the last two available closes.

    closes must already be truncated to strictly before the execution date.
    """
    if len(closes) < lookback + 1:
        return None
    end = D(closes[-1][1])
    start = D(closes[-1 - lookback][1])
    if start <= 0:
        return None
    return (end / start) - D(1)


def daily_returns(closes: list[tuple[date, object]]) -> list[object]:
    out = []
    for i in range(1, len(closes)):
        a = D(closes[i - 1][1])
        b = D(closes[i][1])
        if a <= 0:
            continue
        out.append((b / a) - D(1))
    return out
