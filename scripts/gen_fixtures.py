#!/usr/bin/env python3
"""Regenerate content-addressed bake-off fixtures (deterministic, offline)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_moe_lab.frozen_specs import write_frozen_specs
from trading_moe_lab.paths import default_fixtures
from trading_moe_lab.synthesize import generate_fixtures


def main() -> int:
    dest = default_fixtures()
    generate_fixtures(dest)
    write_frozen_specs(dest / "specs")
    print("fixtures at", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
