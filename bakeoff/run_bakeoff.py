#!/usr/bin/env python3
"""Offline bake-off entrypoint (no install required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading_moe_lab.bakeoff import run_bakeoff  # noqa: E402
from trading_moe_lab.safety import assert_paper_only  # noqa: E402


def main() -> int:
    assert_paper_only()
    summary = run_bakeoff()
    print("outcomes:", summary["outcomes"])
    print("wrote", ROOT / "bakeoff" / "results" / "summary.json")
    print("equity curve:", ROOT / "bakeoff" / "results" / "equity_curve.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
