# Float / decimal policy (locked)

`FLOAT_POLICY_ID = decimal-v0-8dp-half-even`

| Quantity | Type | Quantum | Rounding |
| --- | --- | --- | --- |
| Cash, NAV, fees | `decimal.Decimal` | 8 dp (`0.00000001`) | `ROUND_HALF_EVEN` |
| Prices | `decimal.Decimal` | 4 dp | `ROUND_HALF_EVEN` |
| Shares | `int` ≥ 0 | 1 share | floor when converting notional → shares |
| Weights | `decimal.Decimal` | 10 dp | `ROUND_HALF_EVEN` |

**Forbidden in the engine:** Python `float` as money. `money.D()` raises
`TypeError` on `float`.

**Reporting:** `metrics.display_float64` is a one-way export for charts and
humans. It is never used to size orders.

**Bit-stability:** given the same fixture bars, `ExperimentSpec`, seed, and
this policy, NAV strings and fill prices are deterministic. Tests hash the
NAV series.

**CAGR** uses `Decimal` power with precision 28. Sharpe variance is Decimal.
Changing this file is a breaking bake-off change.
