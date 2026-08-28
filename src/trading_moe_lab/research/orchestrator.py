"""Deterministic research orchestrator.

Owns budgets, schedules experts, merges/dedupes, enforces allowlists, and
writes ExperimentSpec candidates + registry rows. Never calls a broker,
never holds secrets, never unlatches kill, never sets a champion.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from trading_moe_lab.bars import BarSet
from trading_moe_lab.errors import BudgetError
from trading_moe_lab.hashes import sha256_json
from trading_moe_lab.research import Critique, Proposal, ResearchContext
from trading_moe_lab.research.cost_stress import CostStressExpert
from trading_moe_lab.research.critique import CritiqueExpert
from trading_moe_lab.research.momentum import MomentumExpert
from trading_moe_lab.research.reversal import ReversalExpert
from trading_moe_lab.research.risk_regime import RiskRegimeExpert
from trading_moe_lab.research.scribe import SpecScribeExpert
from trading_moe_lab.spec import ExperimentSpec
from trading_moe_lab.store import Store
from trading_moe_lab.universe import Universe


@dataclass
class Budget:
    max_trials: int = 16
    max_wall_seconds: float = 60.0
    max_expert_calls: int = 32
    max_tokens: int = 0  # 0 = offline, no LLM tokens permitted
    cycles: int = 2
    family_quotas: dict[str, int] = field(
        default_factory=lambda: {
            "H1_DUAL_MOMENTUM": 8,
            "H2_CS_MOMENTUM": 8,
            "H3_REVERSAL": 2,
            "RESEARCH": 4,
        }
    )


@dataclass
class OrchestratorReport:
    accepted_specs: list[ExperimentSpec]
    rejected: list[dict[str, Any]]
    critiques: list[dict[str, Any]]
    cycles: int
    expert_calls: int
    elapsed_seconds: float
    notes: list[str]


class Orchestrator:
    def __init__(self, store: Store, budget: Budget | None = None):
        self.store = store
        self.budget = budget or Budget()
        self.experts = [
            MomentumExpert(),
            ReversalExpert(),
            RiskRegimeExpert(),
            CostStressExpert(),
            CritiqueExpert(),
            SpecScribeExpert(),
        ]

    def run(self, bars: BarSet, universe: Universe) -> OrchestratorReport:
        t0 = time.perf_counter()
        allow = universe.allowlist()
        accepted: list[ExperimentSpec] = []
        rejected: list[dict[str, Any]] = []
        critique_rows: list[dict[str, Any]] = []
        notes: list[str] = []
        expert_calls = 0
        prior_critiques: list[str] = []
        prior_proposals: list[Proposal] = []
        family_used = {k: self.store.family_trial_count(k) for k in self.budget.family_quotas}

        if self.budget.max_tokens != 0:
            raise BudgetError("v0 orchestrator is offline; max_tokens must be 0")

        for cycle in range(self.budget.cycles):
            if time.perf_counter() - t0 > self.budget.max_wall_seconds:
                raise BudgetError("wall-clock budget exhausted")
            ctx = ResearchContext(
                bars=bars,
                universe=universe,
                allowlist=allow,
                cycle=cycle,
                prior_critiques=tuple(prior_critiques),
                prior_proposals=tuple(prior_proposals),
                family_quotas=dict(self.budget.family_quotas),
                family_used=dict(family_used),
                notes="offline heuristic cycle",
            )
            proposals: list[Proposal] = []
            for ex in self.experts:
                if expert_calls >= self.budget.max_expert_calls:
                    raise BudgetError("expert-call budget exhausted")
                expert_calls += 1
                proposals.extend(ex.propose(ctx))

            # Dedupe by spec_id
            uniq: dict[str, Proposal] = {}
            for p in proposals:
                if p.withdraw:
                    continue
                sid = str(p.spec_draft.get("spec_id") or p.title)
                uniq[sid] = p
            proposals = list(uniq.values())

            critiques: list[Critique] = []
            for ex in self.experts:
                if expert_calls >= self.budget.max_expert_calls:
                    raise BudgetError("expert-call budget exhausted")
                expert_calls += 1
                critiques.extend(ex.critique(ctx, proposals))

            by_title: dict[str, list[Critique]] = {}
            for c in critiques:
                by_title.setdefault(c.target_title, []).append(c)
                critique_rows.append(
                    {
                        "cycle": cycle,
                        "expert": c.expert_role,
                        "target": c.target_title,
                        "severity": c.severity,
                        "issues": list(c.issues),
                        "accept": c.accept,
                    }
                )
                prior_critiques.append(f"{c.severity}:{c.target_title}:{';'.join(c.issues)}")

            scribe = next(e for e in self.experts if e.role == "SpecScribeExpert")
            for p in proposals:
                cs = by_title.get(p.title, [])
                rejected_by = [c for c in cs if not c.accept or c.severity == "REJECT"]
                verdict_reject = bool(rejected_by) or p.tainted
                if verdict_reject:
                    rec = {
                        "cycle": cycle,
                        "title": p.title,
                        "family": p.family,
                        "reasons": [i for c in rejected_by for i in c.issues] or [p.taint_reason],
                    }
                    rejected.append(rec)
                    # Persist REJECTED for DSR / multiple-testing honesty.
                    spec_id = str(p.spec_draft.get("spec_id") or p.title)
                    trial_id = f"rej-{cycle}-{spec_id}"
                    try:
                        self.store.register_trial(
                            trial_id=trial_id,
                            spec_hash=sha256_json(p.spec_draft),
                            spec_json=json.dumps(p.spec_draft, sort_keys=True),
                            family=p.family,
                            status="REJECTED",
                            split="research",
                            source=p.expert_role,
                            notes="; ".join(rec["reasons"]),
                        )
                    except Exception as exc:  # already registered on rerun
                        notes.append(f"skip re-register {trial_id}: {exc}")
                    continue

                if len(accepted) + self._accepted_count() >= self.budget.max_trials:
                    notes.append("max_trials reached; remaining proposals dropped")
                    break
                quota = self.budget.family_quotas.get(p.family)
                if quota is not None and family_used.get(p.family, 0) >= quota:
                    rejected.append(
                        {
                            "cycle": cycle,
                            "title": p.title,
                            "family": p.family,
                            "reasons": [f"familywise quota {quota} exhausted"],
                        }
                    )
                    try:
                        self.store.register_trial(
                            trial_id=f"quota-{cycle}-{p.spec_draft.get('spec_id')}",
                            spec_hash=sha256_json(p.spec_draft),
                            spec_json=sha256_json(p.spec_draft),
                            family=p.family,
                            status="REJECTED",
                            split="research",
                            source="orchestrator",
                            notes="familywise quota",
                        )
                    except Exception:
                        pass
                    continue
                try:
                    spec = scribe.scribe(p)
                except Exception as exc:
                    rejected.append(
                        {"cycle": cycle, "title": p.title, "family": p.family, "reasons": [str(exc)]}
                    )
                    continue
                # Allowlist enforcement
                bad = [s for s in spec.universe if s not in allow]
                if bad:
                    rejected.append(
                        {
                            "cycle": cycle,
                            "title": p.title,
                            "family": p.family,
                            "reasons": [f"not allowlisted: {bad}"],
                        }
                    )
                    continue
                trial_id = f"acc-{spec.spec_id}"
                already = any(s.spec_id == spec.spec_id for s in accepted)
                if already:
                    notes.append(f"skip duplicate spec_id {spec.spec_id} in later cycle")
                    continue
                try:
                    self.store.register_trial(
                        trial_id=trial_id,
                        spec_hash=spec.spec_hash(),
                        spec_json=spec.canonical_json(),
                        family=spec.family,
                        status="REGISTERED",
                        split="research",
                        source=p.expert_role,
                        notes=p.rationale,
                    )
                except Exception as exc:
                    notes.append(f"already registered {trial_id}: {exc}")
                    continue
                family_used[p.family] = family_used.get(p.family, 0) + 1
                accepted.append(spec)
            prior_proposals = list(proposals)

        elapsed = time.perf_counter() - t0
        self.store.audit(
            "ORCHESTRATOR_DONE",
            {
                "accepted": [s.spec_id for s in accepted],
                "n_rejected": len(rejected),
                "cycles": self.budget.cycles,
                "expert_calls": expert_calls,
            },
        )
        return OrchestratorReport(
            accepted_specs=accepted,
            rejected=rejected,
            critiques=critique_rows,
            cycles=self.budget.cycles,
            expert_calls=expert_calls,
            elapsed_seconds=elapsed,
            notes=notes,
        )

    def _accepted_count(self) -> int:
        return sum(1 for t in self.store.list_trials() if t.status in {"REGISTERED", "ACCEPTED"})
