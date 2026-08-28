# Threat model — trading-moe-lab v0

Scope: a local paper simulator plus a batch research orchestrator. There is
no production broker. Residual risk is **scientific fraud** and **future
foot-guns** if someone copies this layout into a live system.

## Assets

| Asset | Why it matters |
| --- | --- |
| Fixture bars + digests | Bake-off fairness; look-ahead / tampering |
| ExperimentSpec hashes | Reproducibility; champion integrity |
| Trial registry (including REJECTED) | Multiple-testing honesty |
| Kill latch | Last line of defense inside a sim |
| Human credentials on the box | Must never be read by experts or committed |

## Adversaries / confused deputies

1. **A compromised or hallucinating expert (LLM or heuristic).**
2. **A researcher p-hacking** (holdout reuse, hidden trials, universe stuffing).
3. **A future contributor** adding a "just for debugging" live flag.
4. **Look-ahead in signal code** (using same-bar close or future returns).
5. **Prompt/exfil**: an LLM adapter that concatenates env vars or `.netrc`.

## Controls

### LLM exfil and agency

- Experts receive `ResearchContext` only. Attribute access to `broker`,
  `kill`, `store`, `engine`, `credentials`, `api_key` raises.
- Orchestrator is the only writer to the registry.
- `max_tokens = 0` in v0; `OfflineHeuristicAdapter` never opens a socket.
- CLI refuses to start if `TRADING_MOE_LIVE`, `BROKER_API_KEY`,
  `ALPACA_API_KEY`, `ENABLE_LIVE`, etc. are set.
- Grep tests fail the build if `LIVE` venue, broker URLs, or `enable_live`
  flags appear.

### Look-ahead / PIT leakage

- Signals use `close_series(..., before=asof)` — execution date is excluded.
- Spec schema freezes `PREV_CLOSE` + `NEXT_OPEN`.
- CritiqueExpert rejects `use_future_returns` / look-ahead params (demo
  tainted spec is stored as REJECTED).
- Universe inception/delist enforced in risk gates.
- Digest verification stops silent fixture edits.

### Credential handling

- No API key fields in spec schema (`FORBIDDEN_KEYS`).
- No `.env` loader. No broker client.
- Threat: an LLM adapter that does `os.environ`. Mitigation: do not ship one;
  tests scan research modules for `os.environ` / `socket` / `http`.

### Kill bypass

- Latch is persistent per `run_id` in SQLite.
- `can_place_orders()` is the only branch that builds orders.
- Experts have no unlatch API. There is no "research override" flag.
- Data faults latch rather than trading through missing bars.

### Champion mutation

- `Store.set_champion` requires an existing **ACCEPTED** trial.
- Orchestrator never calls it. Research statuses stop at REGISTERED/REJECTED.
- Bake-off does not promote a champion.

### Holdout one-use / multiple testing

- `holdout_leases` primary key `(family, start, end)`.
- Second consume raises `HoldoutError`.
- H3 quota = 2; extra drafts are REJECTED and recorded.
- Rejected trials persist (Deflated Sharpe / familywise budget).

### Settlement / leverage

- Buys spend **settled** cash only.
- Gross and vol cap cannot exceed 1.0 at spec validation.
- Shorts and oversells are rejected.

## Residual risks

- Synthetic bars can still be curve-fit by *changing the synthesizer* and
  committing new digests — that is a protocol break, visible in git.
- Decimal policy changes break bit-stability; tests pin `FLOAT_POLICY_ID`.
- ATD may compute Sharpe with a different RF if humans skip `PROTOCOL.md`.
- This model does **not** cover a live broker. If someone adds one, treat
  the entire document as void and stop.

## Incident response (paper)

Latch (already automatic on DD / data fault), dump `audit_log`, do not
delete REJECTED rows, do not "fix" NAV by hand.
