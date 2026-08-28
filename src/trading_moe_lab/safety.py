"""Live-venue refusal. Imported by CLI and tests."""

from __future__ import annotations

import os

from trading_moe_lab.errors import ConfigError

FORBIDDEN_ENV = (
    "TRADING_MOE_LIVE",
    "ENABLE_LIVE",
    "LIVE_TRADING",
    "BROKER_API_KEY",
    "ALPACA_API_KEY",
    "IBKR_CLIENT_ID",
)


def assert_paper_only() -> None:
    for key in FORBIDDEN_ENV:
        if os.environ.get(key):
            raise ConfigError(
                f"refusing to start: environment variable {key} is set. "
                "This lab is LOCAL_SIM / paper only and has no live trading path."
            )
    venue = (os.environ.get("TRADING_MOE_VENUE") or "LOCAL_SIM").upper()
    if venue not in {"LOCAL_SIM", "PAPER"}:
        raise ConfigError(f"unsupported venue {venue!r}; only LOCAL_SIM is implemented")
