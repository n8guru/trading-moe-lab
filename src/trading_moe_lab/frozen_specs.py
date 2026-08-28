"""Frozen v0 H1/H2/H3 + benchmark ExperimentSpecs."""

from __future__ import annotations

from trading_moe_lab.spec import ExperimentSpec, spec_from_mapping

COMMON = {
    "schema_version": "1.0.0",
    "venue": "LOCAL_SIM",
    "return_semantic": "TOTAL_RETURN",
    "signal_timing": "PREV_CLOSE",
    "execution_timing": "NEXT_OPEN",
    "cash_vehicle": "BIL",
    "benchmark": "SPY",
    "seed": 42,
    "cost": {"bps_1x": 10, "bps_2x": 20, "adverse_bps": 5, "partial_fill_per_mille": 0},
    "research_window": {"start": "2018-01-02", "end": "2021-12-31"},
    "holdout_window": {"start": "2022-01-03", "end": "2023-12-29"},
    "eval_window": {"start": "2018-01-02", "end": "2023-12-29"},
}


def h1_mapping() -> dict:
    return {
        **COMMON,
        "spec_id": "h1-dual-momentum-v0",
        "family": "H1_DUAL_MOMENTUM",
        "name": "H1 dual momentum (absolute + relative, Antonacci-style method)",
        "universe": ["SPY", "EFA", "TLT", "BIL"],
        "risk_assets": ["SPY", "EFA"],
        "crash_asset": "TLT",
        "lookback_days": 252,
        "rebalance": "MONTHLY",
        "top_k": 1,
        "risk": {
            "max_gross_exposure": "1.0",
            "max_name_weight": "1.0",
            "kill_drawdown": "0.35",
            "long_only": True,
            "unlevered": True,
            "vol_target_annual": "0.12",
            "vol_lookback_days": 20,
            "vol_cap": "1.0",
        },
        "notes": (
            "Relative winner of SPY vs EFA; hold winner only if 12m TR > BIL; "
            "else TLT if TLT 12m > BIL else BIL. Vol targeting scale-down only. "
            "Citation is methodological (Antonacci GEM), not a performance claim."
        ),
    }


def h2_mapping() -> dict:
    return {
        **COMMON,
        "spec_id": "h2-cs-momentum-v0",
        "family": "H2_CS_MOMENTUM",
        "name": "H2 cross-sectional relative momentum top-2",
        "universe": ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "VNQ", "BIL"],
        "lookback_days": 252,
        "rebalance": "MONTHLY",
        "top_k": 2,
        "risk": {
            "max_gross_exposure": "1.0",
            "max_name_weight": "0.55",
            "kill_drawdown": "0.35",
            "long_only": True,
            "unlevered": True,
            "vol_target_annual": "0.15",
            "vol_lookback_days": 20,
            "vol_cap": "1.0",
        },
        "notes": "Hold top-2 12m TR names among non-cash universe iff each beats BIL 12m; else sleeve to BIL.",
    }


def h3_mapping() -> dict:
    return {
        **COMMON,
        "spec_id": "h3-reversal-2to5d-v0",
        "family": "H3_REVERSAL",
        "name": "H3 2-5 day reversal (tiny quota; expected INCONCLUSIVE)",
        "universe": ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "BIL"],
        "lookback_days": 5,
        "rebalance": "EVERY_N_DAYS",
        "rebalance_n_days": 5,
        "top_k": 2,
        "risk": {
            "max_gross_exposure": "1.0",
            "max_name_weight": "0.55",
            "kill_drawdown": "0.35",
            "long_only": True,
            "unlevered": True,
            "vol_target_annual": None,
            "vol_lookback_days": 20,
            "vol_cap": "1.0",
        },
        "cost": {"bps_1x": 10, "bps_2x": 20, "adverse_bps": 5, "partial_fill_per_mille": 80},
        "notes": (
            "Buy the two worst 5-session TR names, rebalance every 5 sessions. "
            "High turnover plus 10–20 bps costs plus adverse/partial fills. "
            "Pre-registered expected outcome: INCONCLUSIVE / FAIL after costs. Tiny familywise quota."
        ),
    }


def spy_bh_mapping() -> dict:
    return {
        **COMMON,
        "spec_id": "bench-spy-buyhold-v0",
        "family": "BENCHMARK_SPY",
        "name": "Buy and hold SPY",
        "universe": ["SPY", "BIL"],
        "lookback_days": 2,
        "rebalance": "MONTHLY",
        "top_k": 1,
        "risk": {
            "max_gross_exposure": "1.0",
            "max_name_weight": "1.0",
            "kill_drawdown": "0.90",
            "long_only": True,
            "unlevered": True,
            "vol_target_annual": None,
            "vol_lookback_days": 20,
            "vol_cap": "1.0",
        },
        "notes": "Benchmark. Kill threshold is intentionally high so the benchmark is not frozen.",
    }


def ew_mapping() -> dict:
    return {
        **COMMON,
        "spec_id": "bench-equal-weight-v0",
        "family": "BENCHMARK_EQUAL_WEIGHT",
        "name": "Equal-weight allowlisted non-cash ETFs",
        "universe": ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "VNQ", "BIL"],
        "lookback_days": 2,
        "rebalance": "MONTHLY",
        "top_k": 2,
        "risk": {
            "max_gross_exposure": "1.0",
            "max_name_weight": "0.20",
            "kill_drawdown": "0.90",
            "long_only": True,
            "unlevered": True,
            "vol_target_annual": None,
            "vol_lookback_days": 20,
            "vol_cap": "1.0",
        },
    }


def cash_mapping() -> dict:
    return {
        **COMMON,
        "spec_id": "bench-cash-bil-v0",
        "family": "BENCHMARK_CASH",
        "name": "100% BIL cash vehicle",
        "universe": ["BIL"],
        "lookback_days": 2,
        "rebalance": "MONTHLY",
        "top_k": 1,
        "risk": {
            "max_gross_exposure": "1.0",
            "max_name_weight": "1.0",
            "kill_drawdown": "0.90",
            "long_only": True,
            "unlevered": True,
            "vol_target_annual": None,
            "vol_lookback_days": 20,
            "vol_cap": "1.0",
        },
    }


def frozen_specs() -> dict[str, ExperimentSpec]:
    specs = {
        "H1": spec_from_mapping(h1_mapping()),
        "H2": spec_from_mapping(h2_mapping()),
        "H3": spec_from_mapping(h3_mapping()),
        "SPY": spec_from_mapping(spy_bh_mapping()),
        "EW": spec_from_mapping(ew_mapping()),
        "CASH": spec_from_mapping(cash_mapping()),
    }
    return specs


def write_frozen_specs(dest) -> None:
    from pathlib import Path

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for spec in frozen_specs().values():
        (dest / f"{spec.spec_id}.json").write_text(spec.to_json(), encoding="utf-8")
