"""Immutable ExperimentSpec: the only object that may enter the engine.

Experts may draft these; they cannot execute them. Validation is strict:
LOCAL_SIM only, long-only, unlevered, exposure cap 100%, next-open execution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Mapping

from trading_moe_lab.errors import SpecError
from trading_moe_lab.hashes import canonical_json, sha256_text
from trading_moe_lab.money import D, ONE

SCHEMA_VERSION = "1.0.0"
ALLOWED_FAMILIES = frozenset(
    {
        "H1_DUAL_MOMENTUM",
        "H2_CS_MOMENTUM",
        "H3_REVERSAL",
        "BENCHMARK_SPY",
        "BENCHMARK_EQUAL_WEIGHT",
        "BENCHMARK_CASH",
        "RESEARCH",
    }
)
ALLOWED_VENUES = frozenset({"LOCAL_SIM", "PAPER"})
ALLOWED_RETURN_SEMANTICS = frozenset({"TOTAL_RETURN"})
ALLOWED_SIGNAL_TIMING = frozenset({"PREV_CLOSE"})
ALLOWED_EXECUTION_TIMING = frozenset({"NEXT_OPEN"})
ALLOWED_REBALANCE = frozenset({"DAILY", "EVERY_N_DAYS", "MONTHLY"})
FORBIDDEN_KEYS = frozenset(
    {
        "live",
        "LIVE",
        "enable_live",
        "broker_url",
        "api_key",
        "api_secret",
        "credentials",
        "margin",
        "short",
        "leverage",
        "options",
        "crypto",
    }
)


def _parse_date(label: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SpecError(f"{label} is not ISO YYYY-MM-DD: {value!r}") from exc


@dataclass(frozen=True)
class CostModel:
    bps_1x: int = 10
    bps_2x: int = 20
    adverse_bps: int = 5
    partial_fill_per_mille: int = 0  # 0 = always fill in full

    def cost_bps(self, multiple: str) -> int:
        if multiple in ("1x", "1X"):
            return self.bps_1x
        if multiple in ("2x", "2X"):
            return self.bps_2x
        raise SpecError(f"unknown cost multiple {multiple!r}")


@dataclass(frozen=True)
class RiskSpec:
    max_gross_exposure: str = "1.0"
    max_name_weight: str = "1.0"
    kill_drawdown: str = "0.25"
    long_only: bool = True
    unlevered: bool = True
    vol_target_annual: str | None = "0.12"
    vol_lookback_days: int = 20
    vol_cap: str = "1.0"


@dataclass(frozen=True)
class Window:
    start: str
    end: str

    def start_date(self) -> date:
        return _parse_date("window.start", self.start)

    def end_date(self) -> date:
        return _parse_date("window.end", self.end)


@dataclass(frozen=True)
class ExperimentSpec:
    spec_id: str
    family: str
    name: str
    universe: tuple[str, ...]
    cash_vehicle: str
    benchmark: str
    lookback_days: int
    rebalance: str
    seed: int
    schema_version: str = SCHEMA_VERSION
    venue: str = "LOCAL_SIM"
    return_semantic: str = "TOTAL_RETURN"
    signal_timing: str = "PREV_CLOSE"
    execution_timing: str = "NEXT_OPEN"
    rebalance_n_days: int = 5
    top_k: int = 2
    risk_assets: tuple[str, ...] = ()
    crash_asset: str | None = None
    cost: CostModel = field(default_factory=CostModel)
    risk: RiskSpec = field(default_factory=RiskSpec)
    research_window: Window = field(default_factory=lambda: Window("2018-01-02", "2021-12-31"))
    holdout_window: Window = field(default_factory=lambda: Window("2022-01-03", "2023-12-29"))
    eval_window: Window = field(default_factory=lambda: Window("2018-01-02", "2023-12-29"))
    params: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def canonical_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_dict())

    def spec_hash(self) -> str:
        return sha256_text(self.canonical_json())

    def to_json(self) -> str:
        return json.dumps(self.canonical_dict(), indent=2, sort_keys=True) + "\n"

    def cost_bps(self, multiple: str = "1x") -> int:
        return self.cost.cost_bps(multiple)


def _freeze_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise SpecError(f"{field_name} must be a list of symbols, not a string")
    if not isinstance(value, (list, tuple)):
        raise SpecError(f"{field_name} must be a list")
    out = tuple(str(x).upper() for x in value)
    if any(not s for s in out):
        raise SpecError(f"{field_name} contains an empty symbol")
    return out


def spec_from_mapping(raw: Mapping[str, Any]) -> ExperimentSpec:
    if not isinstance(raw, Mapping):
        raise SpecError("spec must be a JSON object")
    for key in raw.keys():
        if str(key) in FORBIDDEN_KEYS or str(key).lower() in FORBIDDEN_KEYS:
            raise SpecError(f"forbidden key in spec: {key}")
        lowered = str(key).lower()
        if "live" in lowered or "api_key" in lowered or "secret" in lowered:
            raise SpecError(f"forbidden key in spec: {key}")

    venue = str(raw.get("venue", "LOCAL_SIM")).upper()
    if venue == "PAPER":
        venue = "LOCAL_SIM"
    if venue not in ALLOWED_VENUES or venue == "LIVE":
        raise SpecError("venue must be LOCAL_SIM (paper). LIVE is not implemented and never will be in this repo.")

    family = str(raw.get("family", "")).upper()
    if family not in ALLOWED_FAMILIES:
        raise SpecError(f"unknown family {family!r}")

    return_semantic = str(raw.get("return_semantic", "TOTAL_RETURN")).upper()
    if return_semantic not in ALLOWED_RETURN_SEMANTICS:
        raise SpecError("v0 only supports TOTAL_RETURN bars (fixture closes are TR index levels)")

    signal_timing = str(raw.get("signal_timing", "PREV_CLOSE")).upper()
    exec_timing = str(raw.get("execution_timing", "NEXT_OPEN")).upper()
    if signal_timing not in ALLOWED_SIGNAL_TIMING:
        raise SpecError("signal_timing must be PREV_CLOSE")
    if exec_timing not in ALLOWED_EXECUTION_TIMING:
        raise SpecError("execution_timing must be NEXT_OPEN")

    rebalance = str(raw.get("rebalance", "MONTHLY")).upper()
    if rebalance not in ALLOWED_REBALANCE:
        raise SpecError(f"unknown rebalance {rebalance!r}")

    cost_raw = raw.get("cost", {}) or {}
    risk_raw = raw.get("risk", {}) or {}
    rw = raw.get("research_window") or {"start": "2018-01-02", "end": "2021-12-31"}
    hw = raw.get("holdout_window") or {"start": "2022-01-03", "end": "2023-12-29"}
    ew = raw.get("eval_window") or {"start": "2018-01-02", "end": "2023-12-29"}

    universe = _freeze_tuple(raw.get("universe") or [], "universe")
    if not universe:
        raise SpecError("universe must be non-empty")

    cash_vehicle = str(raw.get("cash_vehicle", "BIL")).upper()
    benchmark = str(raw.get("benchmark", "SPY")).upper()
    risk_assets = _freeze_tuple(raw.get("risk_assets") or [], "risk_assets")
    crash = raw.get("crash_asset")
    crash_asset = str(crash).upper() if crash else None

    risk = RiskSpec(
        max_gross_exposure=str(risk_raw.get("max_gross_exposure", "1.0")),
        max_name_weight=str(risk_raw.get("max_name_weight", "1.0")),
        kill_drawdown=str(risk_raw.get("kill_drawdown", "0.25")),
        long_only=bool(risk_raw.get("long_only", True)),
        unlevered=bool(risk_raw.get("unlevered", True)),
        vol_target_annual=(
            None
            if risk_raw.get("vol_target_annual") in (None, "", "null")
            else str(risk_raw.get("vol_target_annual"))
        ),
        vol_lookback_days=int(risk_raw.get("vol_lookback_days", 20)),
        vol_cap=str(risk_raw.get("vol_cap", "1.0")),
    )
    if not risk.long_only:
        raise SpecError("v0 is long-only; risk.long_only must be true")
    if not risk.unlevered:
        raise SpecError("v0 is unlevered; risk.unlevered must be true")
    if D(risk.max_gross_exposure) > ONE:
        raise SpecError("max_gross_exposure cannot exceed 1.0")
    if D(risk.vol_cap) > ONE:
        raise SpecError("vol_cap cannot exceed 1.0 (never >100% exposure)")
    if D(risk.max_name_weight) > ONE:
        raise SpecError("max_name_weight cannot exceed 1.0")
    if D(risk.kill_drawdown) <= 0 or D(risk.kill_drawdown) > ONE:
        raise SpecError("kill_drawdown must be in (0, 1]")

    lookback = int(raw.get("lookback_days", 252))
    if lookback < 2 or lookback > 2000:
        raise SpecError("lookback_days out of range")
    top_k = int(raw.get("top_k", 2))
    if top_k < 1 or top_k > len(universe):
        raise SpecError("top_k out of range")
    seed = int(raw.get("seed", 42))
    if seed < 0:
        raise SpecError("seed must be >= 0")

    spec = ExperimentSpec(
        spec_id=str(raw.get("spec_id") or "").strip(),
        family=family,
        name=str(raw.get("name") or family),
        universe=universe,
        cash_vehicle=cash_vehicle,
        benchmark=benchmark,
        lookback_days=lookback,
        rebalance=rebalance,
        seed=seed,
        schema_version=str(raw.get("schema_version", SCHEMA_VERSION)),
        venue=venue,
        return_semantic=return_semantic,
        signal_timing=signal_timing,
        execution_timing=exec_timing,
        rebalance_n_days=int(raw.get("rebalance_n_days", 5)),
        top_k=top_k,
        risk_assets=risk_assets,
        crash_asset=crash_asset,
        cost=CostModel(
            bps_1x=int(cost_raw.get("bps_1x", 10)),
            bps_2x=int(cost_raw.get("bps_2x", 20)),
            adverse_bps=int(cost_raw.get("adverse_bps", 5)),
            partial_fill_per_mille=int(cost_raw.get("partial_fill_per_mille", 0)),
        ),
        risk=risk,
        research_window=Window(str(rw["start"]), str(rw["end"])),
        holdout_window=Window(str(hw["start"]), str(hw["end"])),
        eval_window=Window(str(ew["start"]), str(ew["end"])),
        params=dict(raw.get("params") or {}),
        notes=str(raw.get("notes") or ""),
    )
    if not spec.spec_id:
        raise SpecError("spec_id is required")
    if spec.schema_version != SCHEMA_VERSION:
        raise SpecError(f"unsupported schema_version {spec.schema_version}")
    if spec.cash_vehicle not in spec.universe and spec.family not in {
        "BENCHMARK_SPY",
        "BENCHMARK_EQUAL_WEIGHT",
        "H3_REVERSAL",
    }:
        # Cash vehicle should generally be in universe; H3 may park in USD.
        if spec.family != "BENCHMARK_CASH":
            raise SpecError("cash_vehicle must be a member of universe")
    if spec.eval_window.start_date() > spec.eval_window.end_date():
        raise SpecError("eval_window inverted")
    if spec.research_window.end_date() >= spec.holdout_window.start_date():
        # Allow touching at boundary? Require strict split.
        if spec.research_window.end_date() >= spec.holdout_window.start_date():
            raise SpecError("research_window must end strictly before holdout_window starts")
    if spec.cost.bps_1x < 0 or spec.cost.bps_2x < spec.cost.bps_1x:
        raise SpecError("cost bps must be >= 0 and 2x >= 1x")
    if spec.cost.adverse_bps < 0 or spec.cost.partial_fill_per_mille < 0:
        raise SpecError("adverse/partial knobs must be >= 0")
    if spec.cost.partial_fill_per_mille > 1000:
        raise SpecError("partial_fill_per_mille cannot exceed 1000")
    return spec


def load_spec(path) -> ExperimentSpec:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return spec_from_mapping(raw)


def dump_spec(spec: ExperimentSpec, path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(spec.to_json())
