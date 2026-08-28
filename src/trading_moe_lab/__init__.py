"""trading-moe-lab: paper-only US ETF research + LOCAL_SIM execution."""

__version__ = "0.1.0"

VENUE = "LOCAL_SIM"
# There is no LIVE venue. Importing this package must never enable capital routing.
SUPPORTED_VENUES = frozenset({VENUE, "PAPER"})
