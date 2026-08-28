# Bake-off protocol v0

This is the comparison contract between **trading-moe-lab** (this repo) and an
internal desk (**autonomous-trading-desk / ATD**). Humans A/B the two systems
on **identical frozen fixtures**. Neither `summary.json` is a claim that one
system beats the other.

## Non-negotiable venue

- `LOCAL_SIM` / paper only.
- No live broker, no live API keys, no `LIVE` mode, no silent promotion to capital.
- Long-only, unlevered, cash account, T+1 settlement (sell proceeds available
  next session; no same-day reuse).
- Daily / next-open US ETF style. No HFT, options, crypto, margin, or shorts.

## Fixtures (content-addressed)

| Item | Path |
| --- | --- |
| Universe + PIT dates | `bakeoff/fixtures/v0/universe.json` |
| OHLCV/TR bars | `bakeoff/fixtures/v0/bars/<SYMBOL>.csv` |
| SHA-256 lockfile | `bakeoff/fixtures/v0/digests.json` |
| Frozen specs | `bakeoff/fixtures/v0/specs/*.json` |

Bars are **synthetic total-return index levels** (dividends economically
reinvested). They are not vendor market data. Digests must match or the
harness refuses to run.

**Calendar:** weekday sessions 2018-01-02 .. 2023-12-29 (union via SPY dates).
No exchange-holiday calendar; the fixture *is* the calendar.

**PIT probes:** `OLDZ` delists 2020-06-01; `NEWZ` incepts 2021-01-04. Both are
**not allowlisted** and must not appear in H1/H2/H3 universes.

### Frozen liquid-ETF universe (allowlisted)

SPY, QQQ, IWM, EFA, EEM, TLT, GLD, VNQ, BIL.

Regimes encoded in the synthesizer (bull / bear / sideways, 2020 crash,
2022 stocks-and-bonds drawdown). See `trading_moe_lab/synthesize.py`.

## Locked knobs (both systems must match)

| Knob | Value |
| --- | --- |
| Initial cash | `1000000.00` USD |
| Eval window | 2018-01-02 .. 2023-12-29 |
| Research window | 2018-01-02 .. 2021-12-31 |
| Holdout window | 2022-01-03 .. 2023-12-29 |
| Return semantic | `TOTAL_RETURN` |
| Signal | previous session **close** |
| Execution | **next session open** |
| 1x cost | 10 bps of fill notional, one-way, cash fee |
| 2x cost | 20 bps of fill notional, one-way, cash fee. Share targeting / cash caps use the 2x fee as a conservative bound on **both** 1x and 2x runs so the overlay isolates fees rather than a different share path. |
| Adverse | 5 bps vs official open (buy worse / sell worse) |
| Shares | integers (no fractional) |
| Money | Decimal, 8 dp, `ROUND_HALF_EVEN` (`float_policy_id=decimal-v0-8dp-half-even`) |
| Vol targeting | scale-**down** only, cap **100%**, leftover to cash vehicle |
| Cash vehicle | BIL |
| Benchmarks | SPY buy-hold, equal-weight non-cash allowlist, 100% BIL |
| Sharpe RF | BIL daily TR on the same calendar (declared; not a constant 0 or 2%) |
| Seed | 42 |

Sharpe on the **cash (BIL) benchmark** is not a useful ranking statistic: leftover uninvested USD after whole-share lots makes excess-vs-BIL vol tiny and the ratio explodes. Compare cash on total return / final NAV instead.

ATD may use a different internal engine. For bake-off, it must consume **these
bar files**, **this date range**, **this initial cash**, and **these cost
knobs**, and emit a `summary.json` with the metrics below.

## Frozen experiment families

### H1 — dual / absolute + relative momentum

- Universe: SPY, EFA, TLT, BIL
- Risk assets: SPY vs EFA (12-month / 252-session TR)
- Absolute gate vs BIL; crash sleeve TLT if TLT 12m > BIL else BIL
- Monthly rebalance (first session of month), next-open execution
- Vol target 12% annualized, cap 100%
- Method citation: Antonacci GEM-style **recipe only**, not proof of edge

### H2 — cross-sectional relative momentum

- Universe: SPY, QQQ, IWM, EFA, EEM, TLT, GLD, VNQ, BIL
- Top-2 by 252-session TR among non-cash names, each must beat BIL 12m
- Monthly, vol target 15%, cap 100%, name cap 55%

### H3 — 2–5 day reversal (tiny quota)

- Universe: SPY, QQQ, IWM, EFA, EEM, VNQ, BIL
- Hold the two worst 5-session TR names; rebalance every 5 sessions
- Partial fills enabled (`partial_fill_per_mille=80`)
- **Pre-registered expected outcome: INCONCLUSIVE / FAIL after costs**
- Familywise research quota: **2** trials (multiple-testing honesty)

Default research outcomes of FAIL / INCONCLUSIVE are **success** if the
science is honest.

## Metrics (required in `summary.json`)

For each family at **1x and 2x** costs:

- `cagr` (365.25-day year, from NAV path)
- `max_drawdown` (peak-to-trough of NAV)
- `sharpe` (excess vs BIL daily TR, `sqrt(252)` ; RF declaration in file)
- `hit_rate` (fraction of sessions with positive NAV change)
- `turnover_annualized` (`sum(qty*price)/avg(NAV) * 252/n`)
- `total_return`
- `final_nav`
- vs SPY, vs equal-weight universe, vs cash (compare the benchmark runs)

Engine state is Decimal. `display_float64` is reporting-only and must not be
fed back into fills.

## How to run this lab offline (< 5 minutes, no tokens)

From the repo root, no network:

```bash
python3 bakeoff/run_bakeoff.py
# or
python3 tmoe run-bakeoff
```

Writes:

- `bakeoff/results/summary.json`
- `bakeoff/results/equity_curve.png` (+ `.svg`)
- `bakeoff/results/registry.json`
- `bakeoff/results/bakeoff.sqlite`

Tests:

```bash
python3 -m unittest discover -s tests -v
```

## ATD comparison procedure

1. Run this lab as above. Keep `bakeoff/results/summary.json`.
2. Point ATD at `bakeoff/fixtures/v0` (same bars, same knobs).
3. Export ATD `summary.json` with the same metric keys.
4. Paste both blobs into `bakeoff/COMPARE.md`.
5. Do **not** retune either system after seeing the other's numbers.
6. Holdout windows inside each system's **research** process remain one-use
   and are **not** the bake-off eval window. Bake-off eval is pre-registered
   on the full fixture range.

## What this protocol does not do

- It does not declare a winner.
- It does not authorize live trading.
- It does not require matching internal ATD architecture — only matching
  **inputs, knobs, and metric definitions**.
