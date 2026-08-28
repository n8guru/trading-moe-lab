# trading-moe-lab

Standalone **paper / LOCAL_SIM** US-ETF research lab: a Mixture-of-Experts
research zone plus a deterministic next-open execution engine. Built so
humans can A/B this artifact against an internal desk (ATD) on **identical
frozen fixtures**.

This repository does **not** trade live capital. There is no LIVE mode, no
broker endpoint, and no way to “enable live”. LLM/heuristic experts are
batch research only; they cannot place orders, waive risk, unlatch a kill
switch, or promote a champion.

It is a **reproducible competitor artifact**, not a claim that the lab beats
ATD.

## Quick start (offline, < 5 minutes, no API tokens)

```bash
python3 -m unittest discover -s tests -v
python3 bakeoff/run_bakeoff.py
# equivalent: python3 tmoe run-bakeoff
```

Outputs:

- `bakeoff/results/summary.json` — metrics + reproducibility metadata
- `bakeoff/results/equity_curve.png` / `.svg`
- `bakeoff/results/registry.json`

Committed snapshot of a fixture run: `docs/examples/`.

CLI (no `pip install` required):

```bash
python3 tmoe init
python3 tmoe run-sim --spec bakeoff/fixtures/v0/specs/h1-dual-momentum-v0.json --cost 1x
python3 tmoe run-research --offline
python3 tmoe run-bakeoff
```

## Layout

| Path | Role |
| --- | --- |
| `ARCHITECTURE.md` | Trust zones: research MoE vs execution |
| `THREAT_MODEL.md` | LLM exfil, look-ahead, credentials, kill bypass |
| `bakeoff/PROTOCOL.md` | Exact A/B rules vs ATD |
| `bakeoff/COMPARE.md` | Blank template for pasting both `summary.json` files |
| `docs/FLOAT_POLICY.md` | Locked Decimal policy (bit-stable NAV) |
| `src/trading_moe_lab/` | Library (stdlib only) |

Runtime third-party dependencies: **none**. SQLite WAL + `decimal` + `hashlib`.

## Frozen families

- **H1** dual (absolute + relative) momentum, Antonacci-style *method* only
- **H2** cross-sectional relative momentum (top-2)
- **H3** 2–5 day reversal — tiny quota, expected **INCONCLUSIVE** after costs

Return semantic: fixture closes are **total-return** index levels. Costs:
10 bps 1x / 20 bps 2x one-way + 5 bps adverse vs open. Vol targeting
scale-down only, cap 100%. Cash vehicle: BIL. T+1 cash, long-only, unlevered.

Default FAIL / INCONCLUSIVE is an honest success, not a product failure.
