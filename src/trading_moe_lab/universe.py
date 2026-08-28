"""PIT universe membership (inception / delist)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    asset_class: str
    inception: date
    delist: date | None
    allowlisted: bool
    note: str = ""

    def tradable_on(self, session: date) -> bool:
        if session < self.inception:
            return False
        if self.delist is not None and session >= self.delist:
            return False
        return True


@dataclass(frozen=True)
class Universe:
    name: str
    cash_vehicle: str
    benchmark: str
    members: tuple[UniverseMember, ...]

    def by_symbol(self) -> dict[str, UniverseMember]:
        return {m.symbol: m for m in self.members}

    def allowlist(self) -> frozenset[str]:
        return frozenset(m.symbol for m in self.members if m.allowlisted)

    def tradable(self, session: date, allowlisted_only: bool = True) -> tuple[str, ...]:
        out = []
        for m in self.members:
            if allowlisted_only and not m.allowlisted:
                continue
            if m.tradable_on(session):
                out.append(m.symbol)
        return tuple(out)

    def is_tradable(self, symbol: str, session: date) -> bool:
        m = self.by_symbol().get(symbol.upper())
        if m is None:
            return False
        return m.tradable_on(session)


def _d(value: str | None) -> date | None:
    if value in (None, "", "null"):
        return None
    return date.fromisoformat(str(value))


def universe_from_mapping(raw: dict[str, Any]) -> Universe:
    members = []
    for row in raw["members"]:
        members.append(
            UniverseMember(
                symbol=str(row["symbol"]).upper(),
                asset_class=str(row.get("asset_class", "unknown")),
                inception=date.fromisoformat(str(row["inception"])),
                delist=_d(row.get("delist")),
                allowlisted=bool(row.get("allowlisted", True)),
                note=str(row.get("note") or ""),
            )
        )
    return Universe(
        name=str(raw["name"]),
        cash_vehicle=str(raw["cash_vehicle"]).upper(),
        benchmark=str(raw["benchmark"]).upper(),
        members=tuple(members),
    )


def load_universe(path: Path | str) -> Universe:
    with open(path, "r", encoding="utf-8") as fh:
        return universe_from_mapping(json.load(fh))


def assert_symbols_allowlisted(universe: Universe, symbols: Iterable[str]) -> None:
    allow = universe.allowlist()
    bad = [s for s in symbols if s.upper() not in allow]
    if bad:
        raise ValueError(f"symbols not on universe allowlist: {bad}")
