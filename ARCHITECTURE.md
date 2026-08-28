# Architecture — trading-moe-lab

Two trust zones. Crossing them without a typed immutable `ExperimentSpec` is
a bug, not a feature.

```
┌─────────────────────────────────────────────────────────────────┐
│ RESEARCH ZONE  (orchestrator + mixture-of-experts)              │
│  May: read fixture bars, draft ideas, critique, scribe specs    │
│  May write: ExperimentSpec JSON, registry rows, reports         │
│  Must not: place orders, waive risk, unlatch kill, hold secrets │
│  Must not: mutate a champion                                    │
│                                                                 │
│  Orchestrator ──► Momentum / Reversal / RiskRegime /            │
│                   CostStress / Critique / SpecScribe            │
│         │                                                       │
│         ▼  typed ExperimentSpec (schema-validated, hashed)      │
└─────────┼───────────────────────────────────────────────────────┘
          │  the only legal bridge
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ EXECUTION ZONE  (no LLM)                                        │
│  Event loop: data validate → settle T+1 → risk/kill →           │
│  signals (prev close) → next-open LOCAL_SIM fills → costs →     │
│  EOD mark → audit hash chain                                    │
│                                                                 │
│  Kill latch persists; freeze = no new orders, retain positions  │
│  Broker: LocalSimBroker only. There is no live subclass.        │
└─────────────────────────────────────────────────────────────────┘
```

## Orchestrator

- Owns budgets: trial count, wall-clock, expert-call ceiling, token ceiling
  (v0 token ceiling is **0** — offline heuristic experts only).
- Familywise quotas (H3 = 2) for multiple-testing honesty.
- Dedupes by `spec_id`, enforces universe allowlist.
- Persists **REJECTED** trials too (DSR / fishing-expedition audit).
- Never imports the broker.

## Experts (v0 = heuristic stand-ins behind an LLM adapter interface)

| Role | Output |
| --- | --- |
| MomentumExpert | H1 dual + H2 CS drafts; cycle-1 look-ahead *negative example* |
| ReversalExpert | H3 drafts; respects tiny quota |
| RiskRegimeExpert | vol scale-down overlays; rejects leverage |
| CostStressExpert | 1x/2x cost survival requirements |
| CritiqueExpert | look-ahead, PIT, universe bias, quota abuse |
| SpecScribeExpert | `spec_from_mapping` — invalid drafts never become specs |

`LLMAdapter.complete` is implemented by `OfflineHeuristicAdapter` (no
network, no keys). A live adapter is not shipped.

Two offline cycles are the default: cycle 0 proposes + critiques (including
the tainted look-ahead, which is rejected); cycle 1 adds honest variants.

## Execution engine

Deterministic given `(bars, ExperimentSpec, seed)`:

1. Validate session bars (OHLC inequalities; SPY calendar).
2. Settle T+1 cash.
3. If kill latched → skip order generation, keep positions, still mark.
4. Else compute target weights from **strictly prior closes**.
5. Size whole shares from open prices; **sells before buys**.
6. Risk gates: long-only, no oversell, allowlist, PIT tradable, settled cash,
   name/gross caps ≤ 100%.
7. `LocalSimBroker`: adverse price, optional deterministic partials, cash fee.
8. EOD mark at close; update peak NAV; maybe latch kill; persist session.

Session rows are idempotent: same `session_id` + payload hash returns the
cached book; a hash mismatch is a hard error.

## Data

Fixture loader verifies SHA-256. Universe members carry inception/delist.
`OLDZ` / `NEWZ` exist to lock PIT behavior and are not allowlisted.

## Persistence

SQLite WAL (`Store`): trials, holdout leases, kill switch, sessions, NAV,
append-only audit chain (`prev_hash` → `entry_hash`). Champion slot can be
set **only** from an ACCEPTED trial via explicit store API (not experts).

## Float policy

See `docs/FLOAT_POLICY.md`. Engine money is `Decimal`. Bit-stability tests
hash the NAV string series.

## What is intentionally missing

Live venue, broker URLs, API keys, Kubernetes, Kafka, GPU, signal vendors,
client advice, autonomous live trading.
