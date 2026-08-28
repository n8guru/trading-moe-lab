"""CLI: init, run-sim, run-research, run-bakeoff. Paper / LOCAL_SIM only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trading_moe_lab import VENUE, __version__
from trading_moe_lab.bakeoff import run_bakeoff
from trading_moe_lab.bars import load_barset
from trading_moe_lab.engine import run_engine
from trading_moe_lab.errors import ConfigError, HoldoutError
from trading_moe_lab.frozen_specs import frozen_specs, write_frozen_specs
from trading_moe_lab.metrics import metrics_bundle
from trading_moe_lab.paths import default_fixtures, default_var, repo_root
from trading_moe_lab.research.orchestrator import Budget, Orchestrator
from trading_moe_lab.safety import assert_paper_only
from trading_moe_lab.spec import load_spec
from trading_moe_lab.store import Store
from trading_moe_lab.universe import load_universe


def _cmd_init(args: argparse.Namespace) -> int:
    assert_paper_only()
    dest = Path(args.dir)
    dest.mkdir(parents=True, exist_ok=True)
    cfg = {
        "venue": VENUE,
        "forbid_live": True,
        "fixtures_dir": str(default_fixtures()),
        "db_path": str(dest / "lab.sqlite"),
        "float_policy_id": "decimal-v0-8dp-half-even",
    }
    (dest / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    store = Store(dest / "lab.sqlite")
    store.audit("INIT", {"venue": VENUE, "dir": str(dest)})
    store.close()
    write_frozen_specs(default_fixtures() / "specs")
    print(f"initialized LOCAL_SIM workspace at {dest}")
    print("live trading is not available and cannot be enabled.")
    return 0


def _cmd_run_sim(args: argparse.Namespace) -> int:
    assert_paper_only()
    spec = load_spec(args.spec)
    fixtures = Path(args.fixtures)
    bars = load_barset(fixtures, verify_digests=not args.skip_digest)
    universe = load_universe(fixtures / "universe.json")
    db = Path(args.db)
    store = Store(db)
    result = run_engine(
        spec,
        bars,
        universe,
        store,
        run_id=args.run_id or f"sim-{spec.spec_id}-{args.cost}",
        cost_multiple=args.cost,
    )
    mets = metrics_bundle(result.nav, result.fills, bars)
    out = {
        "run_id": result.run_id,
        "spec_id": spec.spec_id,
        "spec_hash": result.spec_hash,
        "final_nav": result.final_nav,
        "kill": result.kill,
        "metrics": mets,
        "n_orders": len(result.orders),
        "n_fills": len(result.fills),
        "audit_tip": result.audit_tip,
    }
    text = json.dumps(out, indent=2)
    print(text)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    store.close()
    return 0


def _cmd_run_research(args: argparse.Namespace) -> int:
    assert_paper_only()
    if not args.offline:
        raise ConfigError("v0 research is offline-only; pass --offline")
    fixtures = Path(args.fixtures)
    bars = load_barset(fixtures, verify_digests=not args.skip_digest)
    universe = load_universe(fixtures / "universe.json")
    db = Path(args.db)
    store = Store(db)
    orch = Orchestrator(store, Budget(cycles=args.cycles))
    report = orch.run(bars, universe)
    payload = {
        "venue": VENUE,
        "offline": True,
        "cycles": report.cycles,
        "expert_calls": report.expert_calls,
        "elapsed_seconds": report.elapsed_seconds,
        "accepted": [
            {"spec_id": s.spec_id, "family": s.family, "hash": s.spec_hash()} for s in report.accepted_specs
        ],
        "rejected": report.rejected,
        "critiques": report.critiques,
        "notes": report.notes,
        "registry_audit_tip": store.audit_tip(),
        "claim": "Research produced typed specs only. No orders were placed.",
    }
    dest = Path(args.out or (repo_root() / "docs" / "examples" / "research_report.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    spec_dir = dest.parent / "research_specs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    for s in report.accepted_specs:
        (spec_dir / f"{s.spec_id}.json").write_text(s.to_json(), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("accepted", "cycles", "expert_calls")}, indent=2))
    print(f"wrote {dest}")
    store.close()
    return 0


def _cmd_run_bakeoff(args: argparse.Namespace) -> int:
    assert_paper_only()
    summary = run_bakeoff(
        fixtures_dir=Path(args.fixtures) if args.fixtures else None,
        out_dir=Path(args.out) if args.out else None,
        db_path=Path(args.db) if args.db else None,
    )
    print(f"bakeoff complete: {summary['outcomes']}")
    print(f"summary: {args.out or (repo_root() / 'bakeoff' / 'results' / 'summary.json')}")
    return 0


def _cmd_consume_holdout(args: argparse.Namespace) -> int:
    """Human-gated holdout evaluation (one-use). Not callable by experts."""
    assert_paper_only()
    spec = load_spec(args.spec)
    store = Store(args.db)
    try:
        store.consume_holdout(
            spec.family,
            spec.holdout_window.start,
            spec.holdout_window.end,
            args.trial_id,
        )
    except HoldoutError as exc:
        print(f"HOLD OUT REFUSED: {exc}", file=sys.stderr)
        store.close()
        return 2
    print("holdout lease recorded")
    store.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tmoe",
        description="trading-moe-lab — LOCAL_SIM / paper US-ETF research lab (no live trading)",
    )
    p.add_argument("--version", action="version", version=f"trading-moe-lab {__version__} venue={VENUE}")
    sub = p.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="create local paper workspace")
    init.add_argument("--dir", default=str(default_var()))
    init.set_defaults(func=_cmd_init)

    sim = sub.add_parser("run-sim", help="run LOCAL_SIM on a typed ExperimentSpec")
    sim.add_argument("--spec", required=True)
    sim.add_argument("--fixtures", default=str(default_fixtures()))
    sim.add_argument("--db", default=str(default_var() / "lab.sqlite"))
    sim.add_argument("--cost", default="1x", choices=["1x", "2x"])
    sim.add_argument("--run-id", default=None)
    sim.add_argument("--out", default=None)
    sim.add_argument("--skip-digest", action="store_true")
    sim.set_defaults(func=_cmd_run_sim)

    res = sub.add_parser("run-research", help="offline MoE research (writes specs, never orders)")
    res.add_argument("--offline", action="store_true", required=True)
    res.add_argument("--fixtures", default=str(default_fixtures()))
    res.add_argument("--db", default=str(default_var() / "research.sqlite"))
    res.add_argument("--cycles", type=int, default=2)
    res.add_argument("--out", default=None)
    res.add_argument("--skip-digest", action="store_true")
    res.set_defaults(func=_cmd_run_research)

    bak = sub.add_parser("run-bakeoff", help="evaluate frozen H1/H2/H3 on fixture bars")
    bak.add_argument("--fixtures", default=None)
    bak.add_argument("--out", default=None)
    bak.add_argument("--db", default=None)
    bak.set_defaults(func=_cmd_run_bakeoff)

    ho = sub.add_parser("consume-holdout", help="human-gated one-use holdout lease")
    ho.add_argument("--spec", required=True)
    ho.add_argument("--trial-id", required=True)
    ho.add_argument("--db", default=str(default_var() / "lab.sqlite"))
    ho.set_defaults(func=_cmd_consume_holdout)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
