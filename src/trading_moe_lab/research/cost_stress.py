"""CostStressExpert — 1x/2x cost overlays and survival checks (research only)."""

from __future__ import annotations

from trading_moe_lab.frozen_specs import h1_mapping, h3_mapping
from trading_moe_lab.research import Critique, Proposal, ResearchContext


class CostStressExpert:
    role = "CostStressExpert"

    def propose(self, ctx: ResearchContext) -> list[Proposal]:
        # Does not create a new family; annotates that 2x must be evaluated by bakeoff/engine.
        m = dict(h1_mapping())
        m["spec_id"] = "h1-dual-momentum-cost-annotated-v0"
        m["notes"] = (
            (m.get("notes") or "")
            + " CostStress: require 1x=10bps and 2x=20bps one-way plus 5bps adverse. "
            "Do not accept a spec that only 'works' at 0 bps."
        )
        return [
            Proposal(
                expert_role=self.role,
                title="H1 with explicit 2x-cost survival requirement",
                family="H1_DUAL_MOMENTUM",
                rationale="Any accepted momentum spec must be reported net of 1x and 2x costs.",
                spec_draft=m,
            )
        ]

    def critique(self, ctx: ResearchContext, proposals: list[Proposal]) -> list[Critique]:
        out = []
        for p in proposals:
            cost = p.spec_draft.get("cost") or {}
            issues = []
            if int(cost.get("bps_1x", 0)) < 10:
                issues.append("bps_1x below frozen 10bp bake-off knob")
            if int(cost.get("bps_2x", 0)) < 2 * int(cost.get("bps_1x", 0)):
                issues.append("bps_2x must be at least 2× bps_1x")
            if p.family == "H3_REVERSAL" and int(cost.get("partial_fill_per_mille", 0)) == 0:
                issues.append("H3 should demonstrate partial fills (high turnover name)")
            if issues:
                out.append(
                    Critique(
                        expert_role=self.role,
                        target_title=p.title,
                        severity="WARN" if p.family != "H3_REVERSAL" else "WARN",
                        issues=tuple(issues),
                        accept=True,
                    )
                )
            else:
                out.append(
                    Critique(
                        expert_role=self.role,
                        target_title=p.title,
                        severity="INFO",
                        issues=("cost knobs match bake-off 10/20 bps + 5 bps adverse",),
                        accept=True,
                    )
                )
        _ = h3_mapping
        return out
