# COMPARE.md — human A/B template (ATD vs trading-moe-lab)

Do **not** claim a winner in this file without pasting both `summary.json`
blobs. This lab ships as a **reproducible competitor artifact**, not as a
performance advertisement.

## Identities

| Field | trading-moe-lab | ATD |
| --- | --- | --- |
| Git / version | | |
| Fixture digest (`digests.json` sha256) | | |
| Eval window | 2018-01-02 .. 2023-12-29 | 2018-01-02 .. 2023-12-29 |
| Initial cash | 1000000.00 | 1000000.00 |
| Cost 1x / 2x / adverse | 10 / 20 / 5 bps | 10 / 20 / 5 bps |
| Return semantic | TOTAL_RETURN | TOTAL_RETURN |
| Float / decimal policy | decimal-v0-8dp-half-even | |
| Venue | LOCAL_SIM | LOCAL_SIM (required) |

## Headline metrics (paste numbers, do not round away signs)

| Metric | Lab H1 1x | ATD H1 1x | Lab H1 2x | ATD H1 2x |
| --- | --- | --- | --- | --- |
| CAGR | | | | |
| Max DD | | | | |
| Sharpe (RF=BIL) | | | | |
| Hit rate | | | | |
| Turnover ann. | | | | |
| Final NAV | | | | |

| Metric | Lab H2 1x | ATD H2 1x | Lab H2 2x | ATD H2 2x |
| --- | --- | --- | --- | --- |
| CAGR | | | | |
| Max DD | | | | |
| Sharpe (RF=BIL) | | | | |
| Hit rate | | | | |
| Turnover ann. | | | | |
| Final NAV | | | | |

| Metric | Lab H3 1x | ATD H3 1x | Lab H3 2x | ATD H3 2x |
| --- | --- | --- | --- | --- |
| CAGR | | | | |
| Max DD | | | | |
| Sharpe (RF=BIL) | | | | |
| Hit rate | | | | |
| Turnover ann. | | | | |
| Final NAV | | | | |

## Benchmarks (same fixtures)

| Series | Lab 1x CAGR | ATD 1x CAGR | Lab final NAV | ATD final NAV |
| --- | --- | --- | --- | --- |
| SPY buy-hold | | | | |
| Equal-weight universe | | | | |
| Cash (BIL) | | | | |

## Outcomes (honest labels only)

| Family | Lab pre-registered | Lab observed | ATD observed |
| --- | --- | --- | --- |
| H1 | SURVIVES_COSTS / INCONCLUSIVE / FAIL | | |
| H2 | SURVIVES_COSTS / INCONCLUSIVE / FAIL | | |
| H3 | INCONCLUSIVE (expected) | | |

## Raw blobs

### trading-moe-lab `summary.json`

```json
(paste)
```

### ATD `summary.json`

```json
(paste)
```

## Notes / discrepancies (calendar, fill rule, settlement)

- 
- 
-
