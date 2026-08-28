"""Bake-off runner: LOCAL_SIM H1/H2/H3 + benchmarks on frozen fixtures."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_moe_lab import __version__
from trading_moe_lab.bars import load_barset
from trading_moe_lab.charts import write_png, write_svg
from trading_moe_lab.engine import run_engine
from trading_moe_lab.frozen_specs import frozen_specs, write_frozen_specs
from trading_moe_lab.hashes import sha256_file, sha256_json, sha256_text
from trading_moe_lab.metrics import metrics_bundle
from trading_moe_lab.money import FLOAT_POLICY_ID
from trading_moe_lab.paths import default_fixtures, repo_root
from trading_moe_lab.store import Store
from trading_moe_lab.universe import load_universe


def _float_nav(nav: list[tuple[str, str]]) -> list[tuple[str, float]]:
    return [(d, float(v)) for d, v in nav]


def run_bakeoff(
    fixtures_dir: Path | None = None,
    out_dir: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root()
    fixtures_dir = Path(fixtures_dir or default_fixtures())
    out_dir = Path(out_dir or (root / "bakeoff" / "results"))
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(db_path or (out_dir / "bakeoff.sqlite"))
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    write_frozen_specs(fixtures_dir / "specs")
    bars = load_barset(fixtures_dir, verify_digests=True)
    universe = load_universe(fixtures_dir / "universe.json")
    store = Store(db_path)
    specs = frozen_specs()

    runs: dict[str, Any] = {}
    nav_chart: dict[str, list[tuple[str, float]]] = {}

    for label, spec in specs.items():
        for multiple in ("1x", "2x"):
            run_id = f"bakeoff-{label}-{multiple}"
            result = run_engine(spec, bars, universe, store, run_id=run_id, cost_multiple=multiple)
            mets = metrics_bundle(result.nav, result.fills, bars)
            key = f"{label}_{multiple}"
            runs[key] = {
                "label": label,
                "spec_id": spec.spec_id,
                "spec_hash": spec.spec_hash(),
                "family": spec.family,
                "cost_multiple": multiple,
                "cost_bps": spec.cost_bps(multiple),
                "adverse_bps": spec.cost.adverse_bps,
                "metrics": mets,
                "final_nav": result.final_nav,
                "initial_cash": result.initial_cash,
                "n_sessions": result.n_sessions,
                "n_orders": len(result.orders),
                "n_fills": len(result.fills),
                "kill": result.kill,
                "run_id": run_id,
            }
            if multiple == "1x":
                nav_chart[label] = _float_nav(result.nav)
            store.register_trial(
                trial_id=run_id,
                spec_hash=spec.spec_hash(),
                spec_json=spec.canonical_json(),
                family=spec.family,
                status="REGISTERED",
                split="bakeoff_eval",
                source="run_bakeoff",
                notes=f"pre-registered bake-off {multiple}",
                metrics=mets,
            )

    # Honest default outcomes for frozen families (science, not marketing).
    def _outcome(label: str) -> str:
        row_1 = runs[f"{label}_1x"]["metrics"]["display_float64"]
        row_2 = runs[f"{label}_2x"]["metrics"]["display_float64"]
        spy = runs["SPY_1x"]["metrics"]["display_float64"]["cagr"]
        c1 = row_1.get("cagr")
        c2 = row_2.get("cagr")
        if label == "H3":
            return "INCONCLUSIVE"
        if c1 is None or c2 is None:
            return "INCONCLUSIVE"
        if c2 < -0.5:
            return "FAIL"
        if label in {"H1", "H2"}:
            if c1 > 0 and c2 > -0.05:
                return "SURVIVES_COSTS"
            return "INCONCLUSIVE"
        return "BENCHMARK"

    outcomes = {lab: _outcome(lab) for lab in ("H1", "H2", "H3")}

    write_svg(out_dir / "equity_curve.svg", nav_chart, "LOCAL_SIM NAV (1x costs) — fixture v0")
    write_png(out_dir / "equity_curve.png", nav_chart, "LOCAL_SIM NAV (1x costs)")

    summary = {
        "lab": "trading-moe-lab",
        "version": __version__,
        "venue": "LOCAL_SIM",
        "claim": (
            "Reproducible competitor artifact. This file is not a claim that the lab beats "
            "autonomous-trading-desk / ATD. Humans paste ATD summary.json into COMPARE.md."
        ),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "float_policy_id": FLOAT_POLICY_ID,
        "fixtures_dir": str(fixtures_dir),
        "digests_sha256": sha256_file(fixtures_dir / "digests.json"),
        "universe_sha256": sha256_file(fixtures_dir / "universe.json"),
        "initial_cash": "1000000.00",
        "date_range": {"start": "2018-01-02", "end": "2023-12-29"},
        "return_semantic": "TOTAL_RETURN",
        "cost_model": {
            "bps_1x": 10,
            "bps_2x": 20,
            "adverse_bps": 5,
            "fee_on": "one-way fill notional",
            "adverse_on": "open (+buy / -sell)",
            "settlement": "T+1 cash, no same-day reuse of sell proceeds",
        },
        "sharpe_rf": "BIL daily total return (fixture)",
        "vol_targeting": "scale-down only, cap 100%",
        "runs": runs,
        "outcomes": outcomes,
        "audit_tip": store.audit_tip(),
        "registry": store.dump_registry(),
    }
    summary["summary_sha256"] = sha256_json({k: v for k, v in summary.items() if k != "summary_sha256"})
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Registry dump (human)
    (out_dir / "registry.json").write_text(
        json.dumps(store.dump_registry(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "bakeoff_report.md").write_text(_markdown_report(summary), encoding="utf-8")
    store.close()
    return summary


def _markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Fixture bake-off report (trading-moe-lab)",
        "",
        "This is a **reproducible competitor artifact**, not a claim that this lab beats ATD.",
        "Paste ATD `summary.json` into `bakeoff/COMPARE.md` for a human A/B.",
        "",
        f"- Generated (UTC): `{summary['generated_utc']}`",
        f"- Venue: `{summary['venue']}`",
        f"- Float policy: `{summary['float_policy_id']}`",
        f"- Fixtures digest file: `{summary['digests_sha256']}`",
        f"- Eval window: {summary['date_range']['start']} .. {summary['date_range']['end']}",
        f"- Initial cash: {summary['initial_cash']}",
        f"- Costs: {summary['cost_model']['bps_1x']} bps 1x / {summary['cost_model']['bps_2x']} bps 2x + {summary['cost_model']['adverse_bps']} bps adverse",
        f"- Sharpe RF: {summary['sharpe_rf']}",
        f"- Return semantic: {summary['return_semantic']}",
        "",
        "## Pre-registered family outcomes",
        "",
        "| Family | Outcome | Note |",
        "| --- | --- | --- |",
        f"| H1 dual momentum | `{summary['outcomes']['H1']}` | Honest label vs costs; not vs ATD |",
        f"| H2 CS momentum | `{summary['outcomes']['H2']}` | Honest label vs costs; not vs ATD |",
        f"| H3 2–5d reversal | `{summary['outcomes']['H3']}` | Pre-registered expected INCONCLUSIVE |",
        "",
        "## Metrics (Decimal strings; display_float64 is reporting-only)",
        "",
        "| Run | CAGR | Max DD | Sharpe | Hit rate | Turnover | Final NAV | Fills |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in sorted(summary["runs"]):
        r = summary["runs"][key]
        m = r["metrics"]
        lines.append(
            f"| {key} | {m.get('cagr')} | {m.get('max_drawdown')} | {m.get('sharpe')} | "
            f"{m.get('hit_rate')} | {m.get('turnover_annualized')} | {r['final_nav']} | {r['n_fills']} |"
        )
    lines.extend(
        [
            "",
            "## How to reproduce offline",
            "",
            "```bash",
            "python3 bakeoff/run_bakeoff.py",
            "```",
            "",
            "See `bakeoff/PROTOCOL.md`. Labeled equity curve: `equity_curve.svg` (PNG is a compact unlabeled companion).",
            "",
            "H3 high turnover plus costs is pre-registered INCONCLUSIVE. H1/H2 INCONCLUSIVE on this synthetic panel is an honest result, not a product failure.",
            "The 1x vs 2x fee overlay can diverge slightly in share count because T+1 leftover cash after fees feeds the next cap; do not assume 2x NAV is monotone in every family.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
