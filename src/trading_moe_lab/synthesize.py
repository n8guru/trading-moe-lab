"""Deterministic synthetic total-return bars for the frozen v0 fixture.

No network. SHA-256 keyed noise (not Python's global RNG) so regeneration is
bit-stable across machines. Regime table covers bull / bear / sideways plus
the 2020 crash and 2022 stocks+bonds drawdown.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import date, timedelta
from pathlib import Path

from trading_moe_lab.hashes import sha256_file, sha256_text
from trading_moe_lab.money import q_price

FIXTURE_START = date(2018, 1, 2)
FIXTURE_END = date(2023, 12, 29)
SYNTH_SEED = "trading-moe-lab-fixture-v0"

# Allowlisted liquid ETFs + two PIT probes (not allowlisted).
MEMBERS = [
    {
        "symbol": "SPY",
        "asset_class": "equity_us_large",
        "inception": "1993-01-22",
        "delist": None,
        "allowlisted": True,
        "start_px": "268.0000",
        "beta_eq": 1.00,
        "beta_bd": 0.05,
        "beta_gd": 0.00,
        "idio": 0.35,
    },
    {
        "symbol": "QQQ",
        "asset_class": "equity_us_nasdaq",
        "inception": "1999-03-10",
        "delist": None,
        "allowlisted": True,
        "start_px": "155.5000",
        "beta_eq": 1.20,
        "beta_bd": -0.05,
        "beta_gd": 0.00,
        "idio": 0.55,
    },
    {
        "symbol": "IWM",
        "asset_class": "equity_us_small",
        "inception": "2000-05-22",
        "delist": None,
        "allowlisted": True,
        "start_px": "152.0000",
        "beta_eq": 1.15,
        "beta_bd": 0.00,
        "beta_gd": 0.00,
        "idio": 0.70,
    },
    {
        "symbol": "EFA",
        "asset_class": "equity_eafe",
        "inception": "2001-08-14",
        "delist": None,
        "allowlisted": True,
        "start_px": "70.2500",
        "beta_eq": 0.85,
        "beta_bd": 0.10,
        "beta_gd": 0.05,
        "idio": 0.50,
    },
    {
        "symbol": "EEM",
        "asset_class": "equity_em",
        "inception": "2003-04-11",
        "delist": None,
        "allowlisted": True,
        "start_px": "47.0000",
        "beta_eq": 1.05,
        "beta_bd": 0.05,
        "beta_gd": 0.10,
        "idio": 0.80,
    },
    {
        "symbol": "TLT",
        "asset_class": "bond_us_long",
        "inception": "2002-07-30",
        "delist": None,
        "allowlisted": True,
        "start_px": "126.5000",
        "beta_eq": -0.20,
        "beta_bd": 1.00,
        "beta_gd": 0.05,
        "idio": 0.40,
    },
    {
        "symbol": "GLD",
        "asset_class": "commodity_gold",
        "inception": "2004-11-18",
        "delist": None,
        "allowlisted": True,
        "start_px": "125.0000",
        "beta_eq": 0.05,
        "beta_bd": 0.15,
        "beta_gd": 1.00,
        "idio": 0.45,
    },
    {
        "symbol": "VNQ",
        "asset_class": "equity_us_reit",
        "inception": "2004-09-29",
        "delist": None,
        "allowlisted": True,
        "start_px": "82.0000",
        "beta_eq": 0.75,
        "beta_bd": 0.35,
        "beta_gd": 0.00,
        "idio": 0.60,
    },
    {
        "symbol": "BIL",
        "asset_class": "cash_tbill",
        "inception": "2007-05-30",
        "delist": None,
        "allowlisted": True,
        "start_px": "91.5000",
        "beta_eq": 0.00,
        "beta_bd": 0.02,
        "beta_gd": 0.00,
        "idio": 0.02,
    },
    {
        "symbol": "OLDZ",
        "asset_class": "equity_us_delisted_probe",
        "inception": "2010-01-04",
        "delist": "2020-06-01",
        "allowlisted": False,
        "note": "synthetic PIT delist probe — not in H1/H2/H3",
        "start_px": "40.0000",
        "beta_eq": 1.10,
        "beta_bd": 0.00,
        "beta_gd": 0.00,
        "idio": 1.00,
    },
    {
        "symbol": "NEWZ",
        "asset_class": "equity_us_inception_probe",
        "inception": "2021-01-04",
        "delist": None,
        "allowlisted": False,
        "note": "synthetic PIT inception probe — not in H1/H2/H3",
        "start_px": "25.0000",
        "beta_eq": 0.90,
        "beta_bd": 0.00,
        "beta_gd": 0.00,
        "idio": 0.90,
    },
]


def weekdays(start: date, end: date) -> list[date]:
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _u01(key: str) -> float:
    import hashlib

    h = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") / float(2**64)


def _gauss(key: str) -> float:
    # Box-Muller with a second hash as the sister uniform.
    u1 = max(1e-12, _u01(key + ":a"))
    u2 = _u01(key + ":b")
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _year_equity_drift(d: date) -> float:
    # Annualized baseline equity factor drift (log), before shocks.
    table = {
        2018: -0.04,
        2019: 0.26,
        2020: 0.10,
        2021: 0.22,
        2022: -0.10,
        2023: 0.22,
    }
    return table.get(d.year, 0.08) / 252.0


def _year_bond_drift(d: date) -> float:
    table = {
        2018: -0.02,
        2019: 0.12,
        2020: 0.08,
        2021: -0.03,
        2022: -0.22,
        2023: 0.02,
    }
    return table.get(d.year, 0.02) / 252.0


def _year_gold_drift(d: date) -> float:
    table = {
        2018: -0.02,
        2019: 0.16,
        2020: 0.18,
        2021: -0.04,
        2022: 0.00,
        2023: 0.10,
    }
    return table.get(d.year, 0.04) / 252.0


def _shock(d: date) -> tuple[float, float, float]:
    """Extra daily log-return add-ons (eq, bond, gold)."""
    if date(2020, 2, 20) <= d <= date(2020, 3, 23):
        return (-0.020, 0.007, 0.003)
    if date(2020, 3, 24) <= d <= date(2020, 4, 30):
        return (0.013, -0.003, 0.001)
    if date(2018, 10, 3) <= d <= date(2018, 12, 24):
        return (-0.0045, 0.0015, 0.0005)
    if date(2022, 1, 3) <= d <= date(2022, 10, 14):
        return (-0.0020, -0.0018, 0.0004)
    if date(2019, 5, 6) <= d <= date(2019, 6, 3):
        return (-0.0030, 0.0010, 0.0008)
    return (0.0, 0.0, 0.0)


def _bill_daily(d: date) -> float:
    """Cash vehicle total-return drift, annualized / 252."""
    if d.year in (2018, 2019):
        ann = 0.020
    elif d.year in (2020, 2021):
        ann = 0.001
    elif d.year == 2022:
        # rising rates: 0.1% -> 4%
        frac = (d - date(2022, 1, 1)).days / 365.0
        ann = 0.001 + 0.039 * min(1.0, max(0.0, frac))
    else:
        ann = 0.050
    return ann / 252.0


def _in_window(d: date, inception: str, delist: str | None) -> bool:
    if d < date.fromisoformat(inception):
        return False
    if delist and d >= date.fromisoformat(delist):
        return False
    return True


def synthesize_symbol(member: dict, sessions: list[date]) -> list[dict[str, str]]:
    px = float(member["start_px"])
    rows = []
    symbol = member["symbol"]
    for d in sessions:
        if not _in_window(d, member["inception"], member.get("delist")):
            continue
        sq, sb, sg = _shock(d)
        f_eq = _year_equity_drift(d) + sq + 0.0095 * _gauss(f"{SYNTH_SEED}:{d.isoformat()}:eq")
        f_bd = _year_bond_drift(d) + sb + 0.0065 * _gauss(f"{SYNTH_SEED}:{d.isoformat()}:bd")
        f_gd = _year_gold_drift(d) + sg + 0.0080 * _gauss(f"{SYNTH_SEED}:{d.isoformat()}:gd")
        if symbol == "BIL":
            log_r = _bill_daily(d) + 0.00005 * _gauss(f"{SYNTH_SEED}:{d.isoformat()}:BIL")
        else:
            idio = float(member["idio"]) * 0.0075 * _gauss(f"{SYNTH_SEED}:{d.isoformat()}:{symbol}")
            log_r = (
                float(member["beta_eq"]) * f_eq
                + float(member["beta_bd"]) * f_bd
                + float(member["beta_gd"]) * f_gd
                + idio
            )
        close = px * math.exp(log_r)
        gap = 0.0015 * _gauss(f"{SYNTH_SEED}:{d.isoformat()}:{symbol}:gap")
        open_px = px * math.exp(gap)
        hi_span = abs(0.004 + 0.006 * _u01(f"{SYNTH_SEED}:{d.isoformat()}:{symbol}:hi"))
        lo_span = abs(0.004 + 0.006 * _u01(f"{SYNTH_SEED}:{d.isoformat()}:{symbol}:lo"))
        high = max(open_px, close) * (1.0 + hi_span)
        low = min(open_px, close) * (1.0 - lo_span)
        if low <= 0:
            low = min(open_px, close) * 0.99
        vol = 10_000_000 + int(_u01(f"{SYNTH_SEED}:{d.isoformat()}:{symbol}:vol") * 40_000_000)
        rows.append(
            {
                "date": d.isoformat(),
                "open": str(q_price(f"{open_px:.8f}")),
                "high": str(q_price(f"{high:.8f}")),
                "low": str(q_price(f"{low:.8f}")),
                "close": str(q_price(f"{close:.8f}")),
                "volume": str(vol),
            }
        )
        px = close
    return rows


def universe_payload() -> dict:
    members = []
    for m in MEMBERS:
        members.append(
            {
                "symbol": m["symbol"],
                "asset_class": m["asset_class"],
                "inception": m["inception"],
                "delist": m["delist"],
                "allowlisted": m["allowlisted"],
                "note": m.get("note", ""),
            }
        )
    return {
        "name": "us-liquid-etf-v0",
        "cash_vehicle": "BIL",
        "benchmark": "SPY",
        "return_semantic": "TOTAL_RETURN",
        "calendar": "weekday-union-of-fixture-bars",
        "note": (
            "Synthetic TR bars for bake-off. Not vendor market data. "
            "OLDZ/NEWZ exist only to lock PIT inception/delist behavior."
        ),
        "members": members,
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(rows)


def generate_fixtures(dest: Path) -> dict[str, str]:
    dest = Path(dest)
    bars_dir = dest / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    sessions = weekdays(FIXTURE_START, FIXTURE_END)
    files: dict[str, str] = {}
    for member in MEMBERS:
        rows = synthesize_symbol(member, sessions)
        rel = f"bars/{member['symbol']}.csv"
        write_csv(dest / rel, rows)
        files[rel] = sha256_file(dest / rel)
    uni = universe_payload()
    uni_path = dest / "universe.json"
    uni_path.write_text(json.dumps(uni, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files["universe.json"] = sha256_file(uni_path)
    digest = {
        "algorithm": "sha256",
        "seed": SYNTH_SEED,
        "float_policy_id": "decimal-v0-8dp-half-even",
        "start": FIXTURE_START.isoformat(),
        "end": FIXTURE_END.isoformat(),
        "note": "Content-addressed fixture lock. Tests fail if any file is edited.",
        "files": files,
        "universe_hash": files["universe.json"],
        "manifest_id": sha256_text(json.dumps(files, sort_keys=True, separators=(",", ":"))),
    }
    (dest / "digests.json").write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return files


if __name__ == "__main__":
    from trading_moe_lab.paths import default_fixtures

    generate_fixtures(default_fixtures())
    print("wrote", default_fixtures())
