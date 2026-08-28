# Fixture bake-off report (trading-moe-lab)

This is a **reproducible competitor artifact**, not a claim that this lab beats ATD.
Paste ATD `summary.json` into `bakeoff/COMPARE.md` for a human A/B.

- Generated (UTC): `2026-08-28T09:32:48Z`
- Venue: `LOCAL_SIM`
- Float policy: `decimal-v0-8dp-half-even`
- Fixtures digest file: `d2c2dd1edbdf565c35dd20fb532e989ce1b64e4018e65320cd416d5bfce897bd`
- Eval window: 2018-01-02 .. 2023-12-29
- Initial cash: 1000000.00
- Costs: 10 bps 1x / 20 bps 2x + 5 bps adverse
- Sharpe RF: BIL daily total return (fixture)
- Return semantic: TOTAL_RETURN

## Pre-registered family outcomes

| Family | Outcome | Note |
| --- | --- | --- |
| H1 dual momentum | `INCONCLUSIVE` | Honest label vs costs; not vs ATD |
| H2 CS momentum | `INCONCLUSIVE` | Honest label vs costs; not vs ATD |
| H3 2–5d reversal | `INCONCLUSIVE` | Pre-registered expected INCONCLUSIVE |

## Metrics (Decimal strings; display_float64 is reporting-only)

| Run | CAGR | Max DD | Sharpe | Hit rate | Turnover | Final NAV | Fills |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CASH_1x | 0.01957050 | 0.00116703 | -0.89398177 | 0.80550224 | 0.15417137 | 1121008.55406900 | 2 |
| CASH_2x | 0.01957050 | 0.00116702 | -14.34996870 | 0.80550224 | 0.15417004 | 1119887.78145280 | 1 |
| EW_1x | -0.02974066 | 0.45460828 | -0.31799372 | 0.48880358 | 1.35585551 | 849183.22555900 | 10166 |
| EW_2x | -0.03095287 | 0.45647180 | -0.32759093 | 0.48816379 | 1.35359995 | 842023.76244860 | 10151 |
| H1_1x | -0.08486692 | 0.55457703 | -0.86721277 | 0.56046065 | 3.91504840 | 586933.80679010 | 886 |
| H1_2x | -0.08796100 | 0.55961285 | -0.89607307 | 0.55982086 | 3.92235973 | 574576.34724120 | 870 |
| H2_1x | -0.06116937 | 0.45501134 | -0.84756195 | 0.39155470 | 3.77113486 | 685269.25211360 | 1299 |
| H2_2x | -0.05582395 | 0.44377627 | -0.65509495 | 0.39411388 | 3.62946970 | 708965.70670680 | 1281 |
| H3_1x | -0.09103173 | 0.58721684 | -0.47203495 | 0.47088932 | 17.47617624 | 564680.80192180 | 709 |
| H3_2x | -0.11165622 | 0.61391173 | -0.60860283 | 0.46385157 | 17.84214772 | 492175.38069460 | 642 |
| SPY_1x | -0.07554013 | 0.55803490 | -0.46592572 | 0.48112604 | 0.19933123 | 640022.08924590 | 2 |
| SPY_2x | -0.07553004 | 0.55798295 | -0.46595002 | 0.48112604 | 0.19929943 | 639440.39088700 | 1 |

## How to reproduce offline

```bash
python3 bakeoff/run_bakeoff.py
```

See `bakeoff/PROTOCOL.md`. Labeled equity curve: `equity_curve.svg` (PNG is a compact unlabeled companion).

H3 high turnover plus costs is pre-registered INCONCLUSIVE. H1/H2 INCONCLUSIVE on this synthetic panel is an honest result, not a product failure.
The 1x vs 2x fee overlay can diverge slightly in share count because T+1 leftover cash after fees feeds the next cap; do not assume 2x NAV is monotone in every family.

