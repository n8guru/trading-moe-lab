"""RiskRegimeExpert — vol/regime features; scale-down to cash only (never >100%)."""

from __future__ import annotations

from trading_moe_lab.research import Critique, Proposal, ResearchContext
from trading_moe_lab.frozen_specs import h1_mapping


class RiskRegimeExpert:
    role = "RiskRegimeExpert"

    def propose(self, ctx: ResearchContext) -> list[Proposal]:
        m = dict(h1_mapping())
        m["spec_id"] = "h1-dual-momentum-vol10-v0"
        m["name"] = "H1 dual momentum with 10% vol target"
        risk = dict(m["risk"])
        risk["vol_target_annual"] = "0.10"
        risk["vol_cap"] = "1.0"
        m["risk"] = risk
        m["notes"] = (
            "Same H1 signals; more aggressive scale-down to cash when realized vol is high. "
            "vol_cap locked at 1.0 — this expert must never propose leverage."
        )
        return [
            Proposal(
                expert_role=self.role,
                title="H1 vol-target 10%",
                family="H1_DUAL_MOMENTUM",
                rationale="Regime overlay is exposure reduction to cash, never gross > 100%.",
                spec_draft=m,
            )
        ]

    def critique(self, ctx: ResearchContext, proposals: list[Proposal]) -> list[Critique]:
        out = []
        for p in proposals:
            cap = str((p.spec_draft.get("risk") or {}).get("vol_cap", "1.0"))
            gross = str((p.spec_draft.get("risk") or {}).get("max_gross_exposure", "1.0"))
            issues = []
            if cap not in {"1.0", "1", "1.00"}:
                issues.append(f"vol_cap {cap} would allow >100% if >1")
            if gross not in {"1.0", "1", "1.00"}:
                issues.append(f"max_gross_exposure {gross} exceeds unlevered cap")
            if issues:
                out.append(
                    Critique(
                        expert_role=self.role,
                        target_title=p.title,
                        severity="REJECT",
                        issues=tuple(issues),
                        accept=False,
                    )
                )
        return out
